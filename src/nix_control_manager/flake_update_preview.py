from __future__ import annotations

from collections import deque
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import threading
import time
from typing import Any, Callable, Sequence

from .candidate_build import execute_build_process
from .errors import NcmError
from .flake_inspector import FlakeInput, parse_flake_lock


_ACTIVE_STATUSES = {
    "queued",
    "preparing",
    "running",
    "analyzing",
    "cancelling",
    "cleaning",
}
_TERMINAL_STATUSES = {
    "passed",
    "no-change",
    "failed",
    "cancelled",
    "blocked",
    "unavailable",
}
_INPUT_NAME = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_JOB_ID = re.compile(r"^[0-9a-f]{24}$")
_MAX_EVENTS = 256
_MAX_EVENT_CHARS = 1_000
_MAX_FILES = 8_192
_MAX_SOURCE_BYTES = 128 * 1024 * 1024
_MAX_LOCK_BYTES = 4_000_000
_MAX_DIFF_CHARS = 128_000
_UNSUPPORTED_TYPES = {"follows", "indirect", "path", "unknown"}


class FlakeUpdatePreviewError(NcmError):
    """A Flake update-preview request could not be accepted safely."""


LineSink = Callable[[str, str], None]
PreviewExecutor = Callable[
    [Sequence[str], Path, threading.Event, LineSink], tuple[int, tuple[str, ...]]
]
Which = Callable[[str], str | None]
EffectiveUid = Callable[[], int | None]


def _effective_uid() -> int | None:
    return os.geteuid() if hasattr(os, "geteuid") else None


def _ignored_name(name: str) -> bool:
    return name == ".git" or name == "result" or name.startswith("result-")


def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if _ignored_name(name)}


def _manifest(root: Path, *, exclude_lock: bool = False) -> tuple[str, int, int]:
    """Hash one bounded source tree without following symbolic links."""
    if not root.is_dir() or root.is_symlink():
        raise ValueError("The Flake configuration root must be a real directory")
    records: list[tuple[str, str, str]] = []
    file_count = 0
    total_bytes = 0
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        kept_directories: list[str] = []
        for name in sorted(directory_names):
            if _ignored_name(name):
                continue
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                target = os.readlink(path)
                records.append(("link", relative, target))
                file_count += 1
                total_bytes += len(target.encode("utf-8", errors="replace"))
            else:
                kept_directories.append(name)
        directory_names[:] = kept_directories
        for name in sorted(file_names):
            if _ignored_name(name):
                continue
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if exclude_lock and relative == "flake.lock":
                continue
            if path.is_symlink():
                target = os.readlink(path)
                records.append(("link", relative, target))
                size = len(target.encode("utf-8", errors="replace"))
            elif path.is_file():
                digest = hashlib.sha256()
                size = 0
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        size += len(chunk)
                        if total_bytes + size > _MAX_SOURCE_BYTES:
                            raise ValueError("The Flake source exceeds the preview size limit")
                        digest.update(chunk)
                records.append(("file", relative, digest.hexdigest()))
            else:
                raise ValueError(f"Unsupported special file in Flake source: {relative}")
            file_count += 1
            total_bytes += size
            if file_count > _MAX_FILES:
                raise ValueError("The Flake source contains too many files for preview")
            if total_bytes > _MAX_SOURCE_BYTES:
                raise ValueError("The Flake source exceeds the preview size limit")
    encoded = json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest(), file_count, total_bytes


def _read_lock(path: Path) -> tuple[str, dict[str, Any]]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("flake.lock must be a regular file")
    if path.stat().st_size > _MAX_LOCK_BYTES:
        raise ValueError("flake.lock exceeds the preview size limit")
    text = path.read_text(encoding="utf-8")
    value = json.loads(text)
    if not isinstance(value, dict) or not isinstance(value.get("nodes"), dict):
        raise ValueError("flake.lock has an invalid node table")
    nodes = value["nodes"]
    if any(
        not isinstance(name, str)
        or not name
        or len(name) > 128
        or not isinstance(node, dict)
        for name, node in nodes.items()
    ):
        raise ValueError("flake.lock contains an invalid node")
    return text, value


def _input_by_name(inputs: tuple[FlakeInput, ...], name: str) -> FlakeInput | None:
    return next((item for item in inputs if item.name == name), None)


def _input_mapping(value: FlakeInput | None) -> dict[str, Any] | None:
    return value.to_mapping() if value is not None else None


def _lock_diff(before: str, after: str) -> str:
    value = "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="flake.lock (current)",
            tofile="flake.lock (preview)",
        )
    )
    if len(value) <= _MAX_DIFF_CHARS:
        return value
    return value[:_MAX_DIFF_CHARS] + "\n… diff truncated by Nix Control Manager …\n"


class FlakeUpdatePreviewManager:
    """Own one networked single-input preview in a disposable source copy."""

    def __init__(
        self,
        *,
        config_root: Path,
        timeout: int = 120,
        executor: PreviewExecutor = execute_build_process,
        which: Which = shutil.which,
        effective_uid: EffectiveUid = _effective_uid,
    ) -> None:
        if timeout < 1:
            raise ValueError("Flake update-preview timeout must be positive")
        self.config_root = config_root.resolve()
        self.timeout = timeout
        self.executor = executor
        self.which = which
        self.effective_uid = effective_uid
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._job_order: deque[str] = deque()
        self._active_job_id: str | None = None
        self._closed = False

    def start(self, input_name: str) -> dict[str, Any]:
        if not isinstance(input_name, str) or not _INPUT_NAME.fullmatch(input_name):
            raise FlakeUpdatePreviewError("A safe direct Flake input name is required")
        with self._lock:
            if self._closed:
                raise FlakeUpdatePreviewError("Flake update-preview manager is closed")
            if self._active_job_id is not None:
                active = self._jobs[self._active_job_id]
                if active["status"] in _ACTIVE_STATUSES or active["finishedAt"] is None:
                    raise FlakeUpdatePreviewError("A Flake update preview is already running")
            job_id = secrets.token_hex(12)
            effective_uid = self.effective_uid()
            job: dict[str, Any] = {
                "jobId": job_id,
                "status": "queued",
                "inputName": input_name,
                "createdAt": time.time(),
                "startedAt": None,
                "finishedAt": None,
                "durationMs": None,
                "command": [],
                "exitCode": None,
                "before": None,
                "after": None,
                "changedNodes": [],
                "changedNodeCount": 0,
                "lockDiff": "",
                "sourceFingerprint": None,
                "sourceUnchanged": False,
                "candidateOnlyChanges": False,
                "temporaryCopyRemoved": True,
                "cancelRequested": False,
                "timedOut": False,
                "effectiveUid": effective_uid,
                "privileged": effective_uid == 0,
                "error": None,
                "events": deque(maxlen=_MAX_EVENTS),
                "nextSequence": 1,
                "cancelEvent": threading.Event(),
                "thread": None,
            }
            self._jobs[job_id] = job
            self._job_order.append(job_id)
            while len(self._job_order) > 8:
                expired = self._job_order.popleft()
                if expired != self._active_job_id:
                    self._jobs.pop(expired, None)
            self._active_job_id = job_id
            self._event(job, "status", "Flake input update preview queued")
            thread = threading.Thread(
                target=self._run_job,
                args=(job_id,),
                name=f"ncm-flake-preview-{job_id[:8]}",
                daemon=True,
            )
            job["thread"] = thread
            thread.start()
            return self._snapshot(job, after=0)

    def latest(self, *, after: int = 0) -> dict[str, Any]:
        with self._lock:
            if not self._job_order:
                return self._idle_snapshot()
            return self._snapshot(self._jobs[self._job_order[-1]], after=after)

    def poll(self, job_id: str, *, after: int = 0) -> dict[str, Any]:
        if not _JOB_ID.fullmatch(job_id):
            raise FlakeUpdatePreviewError("Invalid Flake update-preview job identifier")
        if after < 0:
            raise FlakeUpdatePreviewError("Flake update-preview cursor cannot be negative")
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise FlakeUpdatePreviewError("Unknown Flake update-preview job")
            return self._snapshot(job, after=after)

    def cancel(self, job_id: str) -> dict[str, Any]:
        if not _JOB_ID.fullmatch(job_id):
            raise FlakeUpdatePreviewError("Invalid Flake update-preview job identifier")
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise FlakeUpdatePreviewError("Unknown Flake update-preview job")
            if job["status"] in _TERMINAL_STATUSES:
                return self._snapshot(job, after=0)
            job["cancelRequested"] = True
            job["cancelEvent"].set()
            job["status"] = "cancelling"
            self._event(job, "status", "Flake update preview cancellation requested")
            return self._snapshot(job, after=0)

    def close(self) -> None:
        thread: threading.Thread | None = None
        with self._lock:
            self._closed = True
            if self._active_job_id is not None:
                job = self._jobs[self._active_job_id]
                if job["status"] in _ACTIVE_STATUSES:
                    job["cancelRequested"] = True
                    job["cancelEvent"].set()
                    job["status"] = "cancelling"
                    self._event(job, "status", "Server shutdown requested cancellation")
                    thread = job["thread"]
        if thread is not None:
            thread.join(timeout=5)

    def _event(self, job: dict[str, Any], stream: str, message: str) -> None:
        sequence = job["nextSequence"]
        job["nextSequence"] += 1
        job["events"].append(
            {
                "sequence": sequence,
                "timestamp": time.time(),
                "stream": stream,
                "message": message[:_MAX_EVENT_CHARS],
            }
        )

    def _fail(self, job: dict[str, Any], status: str, code: str, message: str) -> None:
        job["status"] = status
        job["error"] = {"code": code, "message": message}
        self._event(job, "error", message)

    def _run_job(self, job_id: str) -> None:
        started = time.monotonic()
        candidate_root: Path | None = None
        source_fingerprint: str | None = None
        terminal_status: str | None = None
        terminal_message = ""
        with self._lock:
            job = self._jobs[job_id]
            job["status"] = "preparing"
            job["startedAt"] = time.time()
            self._event(job, "status", "Checking the locked input and source boundary")
        try:
            if job["privileged"]:
                with self._lock:
                    self._fail(
                        job,
                        "blocked",
                        "privileged-execution",
                        "Flake update preview refuses to run with effective UID 0",
                    )
                return
            root = self.config_root
            flake_path = root / "flake.nix"
            lock_path = root / "flake.lock"
            if (
                not flake_path.is_file()
                or flake_path.is_symlink()
                or not lock_path.is_file()
                or lock_path.is_symlink()
            ):
                with self._lock:
                    self._fail(
                        job,
                        "blocked",
                        "missing-flake-files",
                        "Regular flake.nix and flake.lock files are required",
                    )
                return
            lock_status, _, _, inputs, warnings = parse_flake_lock(lock_path)
            if lock_status != "valid" or warnings:
                with self._lock:
                    self._fail(
                        job,
                        "blocked",
                        "unsafe-lock",
                        "flake.lock must pass strict read-only inspection before preview",
                    )
                return
            before_input = _input_by_name(inputs, job["inputName"])
            if before_input is None:
                with self._lock:
                    self._fail(
                        job,
                        "blocked",
                        "unknown-input",
                        "The selected name is not a direct locked Flake input",
                    )
                return
            if (
                not before_input.locked
                or before_input.follows
                or before_input.input_type in _UNSUPPORTED_TYPES
            ):
                with self._lock:
                    self._fail(
                        job,
                        "blocked",
                        "unsupported-input",
                        "This direct input type is not eligible for network update preview",
                    )
                return
            nix = self.which("nix")
            if nix is None:
                with self._lock:
                    self._fail(
                        job,
                        "unavailable",
                        "nix-unavailable",
                        "The nix command is unavailable",
                    )
                return
            if job["cancelEvent"].is_set():
                terminal_status = "cancelled"
                terminal_message = "Flake update preview cancelled before execution"
                return

            source_fingerprint, _, _ = _manifest(root)
            source_without_lock, _, _ = _manifest(root, exclude_lock=True)
            before_text, before_document = _read_lock(lock_path)
            with self._lock:
                job["before"] = _input_mapping(before_input)
                job["sourceFingerprint"] = source_fingerprint

            with tempfile.TemporaryDirectory(prefix="ncm-flake-update-preview-") as temporary:
                candidate_root = Path(temporary) / "configuration"
                shutil.copytree(
                    root,
                    candidate_root,
                    symlinks=True,
                    ignore=_copy_ignore,
                )
                copied_source, _, _ = _manifest(candidate_root)
                source_after_copy, _, _ = _manifest(root)
                if copied_source != source_fingerprint or source_after_copy != source_fingerprint:
                    with self._lock:
                        self._fail(
                            job,
                            "blocked",
                            "source-race",
                            "The Flake source changed while the disposable copy was created",
                        )
                    return
                command = (
                    nix,
                    "--extra-experimental-features",
                    "nix-command flakes",
                    "--option",
                    "accept-flake-config",
                    "false",
                    "--option",
                    "allow-import-from-derivation",
                    "false",
                    "--no-use-registries",
                    "--refresh",
                    "flake",
                    "update",
                    job["inputName"],
                    "--flake",
                    f"path:{candidate_root}",
                )
                with self._lock:
                    job["command"] = list(command)
                    job["temporaryCopyRemoved"] = False
                    job["status"] = "running"
                    self._event(
                        job,
                        "status",
                        "Disposable copy ready; resolving the selected input over the network",
                    )

                def request_timeout() -> None:
                    with self._lock:
                        if job["status"] in {"running", "analyzing"}:
                            job["timedOut"] = True
                            job["cancelEvent"].set()
                            job["status"] = "cancelling"
                            self._event(
                                job,
                                "error",
                                f"Flake update preview exceeded {self.timeout} seconds",
                            )

                timer = threading.Timer(self.timeout, request_timeout)
                timer.daemon = True
                timer.start()
                try:
                    return_code, _ = self.executor(
                        command,
                        candidate_root,
                        job["cancelEvent"],
                        lambda _stream, _line: None,
                    )
                finally:
                    timer.cancel()
                with self._lock:
                    job["exitCode"] = return_code
                if job["timedOut"]:
                    with self._lock:
                        self._fail(
                            job,
                            "failed",
                            "preview-timed-out",
                            f"Flake update preview exceeded {self.timeout} seconds",
                        )
                    return
                if job["cancelEvent"].is_set():
                    terminal_status = "cancelled"
                    terminal_message = "Flake update preview cancelled"
                    return
                if return_code != 0:
                    with self._lock:
                        self._fail(
                            job,
                            "failed",
                            "update-failed",
                            f"Nix Flake update preview exited with status {return_code}",
                        )
                    return

                with self._lock:
                    job["status"] = "analyzing"
                    self._event(job, "status", "Validating the candidate lock diff")
                after_text, after_document = _read_lock(candidate_root / "flake.lock")
                candidate_without_lock, _, _ = _manifest(
                    candidate_root, exclude_lock=True
                )
                source_after, _, _ = _manifest(root)
                with self._lock:
                    job["sourceUnchanged"] = source_after == source_fingerprint
                    job["candidateOnlyChanges"] = (
                        candidate_without_lock == source_without_lock
                    )
                if source_after != source_fingerprint:
                    with self._lock:
                        self._fail(
                            job,
                            "failed",
                            "source-changed",
                            "The original Flake source changed during preview",
                        )
                    return
                if candidate_without_lock != source_without_lock:
                    with self._lock:
                        self._fail(
                            job,
                            "failed",
                            "candidate-scope-changed",
                            "The preview command changed a candidate file other than flake.lock",
                        )
                    return
                after_status, _, _, after_inputs, after_warnings = parse_flake_lock(
                    candidate_root / "flake.lock"
                )
                if after_status != "valid" or after_warnings:
                    with self._lock:
                        self._fail(
                            job,
                            "failed",
                            "invalid-candidate-lock",
                            "Nix produced a lock file that failed strict inspection",
                        )
                    return
                before_names = {item.name for item in inputs}
                after_names = {item.name for item in after_inputs}
                before_root = before_document["nodes"][before_document["root"]].get(
                    "inputs"
                )
                after_root = after_document["nodes"][after_document["root"]].get(
                    "inputs"
                )
                if before_names != after_names or before_root != after_root:
                    with self._lock:
                        self._fail(
                            job,
                            "failed",
                            "direct-input-shape-changed",
                            "The preview unexpectedly changed the direct input graph",
                        )
                    return
                after_input = _input_by_name(after_inputs, job["inputName"])
                changed_direct = {
                    item.name
                    for item in inputs
                    if _input_mapping(item)
                    != _input_mapping(_input_by_name(after_inputs, item.name))
                }
                if changed_direct - {job["inputName"]}:
                    with self._lock:
                        self._fail(
                            job,
                            "failed",
                            "other-direct-input-changed",
                            "The preview unexpectedly changed another direct input",
                        )
                    return
                before_nodes = before_document["nodes"]
                after_nodes = after_document["nodes"]
                changed_nodes = sorted(
                    name
                    for name in set(before_nodes) | set(after_nodes)
                    if before_nodes.get(name) != after_nodes.get(name)
                )
                with self._lock:
                    job["after"] = _input_mapping(after_input)
                    job["changedNodes"] = changed_nodes
                    job["changedNodeCount"] = len(changed_nodes)
                    job["lockDiff"] = _lock_diff(before_text, after_text)
                    terminal_status = "no-change" if before_text == after_text else "passed"
                    terminal_message = (
                        "The selected input is already current"
                        if terminal_status == "no-change"
                        else "Exact temporary flake.lock update preview is ready"
                    )
                    job["status"] = "cleaning"
                    self._event(job, "status", "Removing the disposable Flake copy")
            with self._lock:
                job["temporaryCopyRemoved"] = (
                    candidate_root is not None and not candidate_root.exists()
                )
                job["status"] = terminal_status or "failed"
                self._event(job, "status", terminal_message or "Preview ended")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            with self._lock:
                self._fail(job, "failed", "preview-io-error", str(error))
        except ValueError as error:
            with self._lock:
                self._fail(job, "blocked", "preview-boundary-error", str(error))
        except Exception as error:  # defensive worker boundary
            with self._lock:
                self._fail(job, "failed", "internal-error", str(error))
        finally:
            with self._lock:
                if candidate_root is not None:
                    job["temporaryCopyRemoved"] = not candidate_root.exists()
                if source_fingerprint is not None:
                    try:
                        current_fingerprint, _, _ = _manifest(self.config_root)
                        job["sourceUnchanged"] = current_fingerprint == source_fingerprint
                    except (OSError, ValueError):
                        job["sourceUnchanged"] = False
                if terminal_status == "cancelled" and job["status"] in _ACTIVE_STATUSES:
                    job["status"] = "cancelled"
                    self._event(job, "status", terminal_message)
                elif job["status"] in _ACTIVE_STATUSES:
                    self._fail(
                        job,
                        "failed",
                        "incomplete-preview",
                        "Flake update preview ended without a terminal result",
                    )
                job["finishedAt"] = time.time()
                job["durationMs"] = round((time.monotonic() - started) * 1000)

    def _snapshot(self, job: dict[str, Any], *, after: int) -> dict[str, Any]:
        events = list(job["events"])
        first_sequence = events[0]["sequence"] if events else job["nextSequence"]
        selected = [event.copy() for event in events if event["sequence"] > after]
        status = job["status"]
        if status in _TERMINAL_STATUSES and job["finishedAt"] is None:
            status = "cleaning"
        return {
            "schemaVersion": 1,
            "jobId": job["jobId"],
            "status": status,
            "inputName": job["inputName"],
            "createdAt": job["createdAt"],
            "startedAt": job["startedAt"],
            "finishedAt": job["finishedAt"],
            "durationMs": job["durationMs"],
            "command": list(job["command"]),
            "exitCode": job["exitCode"],
            "before": dict(job["before"]) if job["before"] else None,
            "after": dict(job["after"]) if job["after"] else None,
            "changedNodes": list(job["changedNodes"]),
            "changedNodeCount": job["changedNodeCount"],
            "lockDiff": job["lockDiff"],
            "sourceFingerprint": job["sourceFingerprint"],
            "sourceUnchanged": job["sourceUnchanged"],
            "candidateOnlyChanges": job["candidateOnlyChanges"],
            "temporaryCopyRemoved": job["temporaryCopyRemoved"],
            "cancelRequested": job["cancelRequested"],
            "timedOut": job["timedOut"],
            "cancellable": status in _ACTIVE_STATUSES,
            "effectiveUid": job["effectiveUid"],
            "privileged": job["privileged"],
            "error": dict(job["error"]) if job["error"] else None,
            "events": selected,
            "nextCursor": events[-1]["sequence"] if events else after,
            "logsTruncated": bool(events and after < first_sequence - 1),
            "networkRequired": True,
            "sourceWriteEnabled": False,
            "temporaryLockWriteEnabled": True,
            "nixStoreWriteExpected": True,
            "applyEnabled": False,
            "activationEnabled": False,
        }

    @staticmethod
    def _idle_snapshot() -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "jobId": None,
            "status": "idle",
            "inputName": None,
            "createdAt": None,
            "startedAt": None,
            "finishedAt": None,
            "durationMs": None,
            "command": [],
            "exitCode": None,
            "before": None,
            "after": None,
            "changedNodes": [],
            "changedNodeCount": 0,
            "lockDiff": "",
            "sourceFingerprint": None,
            "sourceUnchanged": True,
            "candidateOnlyChanges": True,
            "temporaryCopyRemoved": True,
            "cancelRequested": False,
            "timedOut": False,
            "cancellable": False,
            "effectiveUid": None,
            "privileged": False,
            "error": None,
            "events": [],
            "nextCursor": 0,
            "logsTruncated": False,
            "networkRequired": True,
            "sourceWriteEnabled": False,
            "temporaryLockWriteEnabled": True,
            "nixStoreWriteExpected": True,
            "applyEnabled": False,
            "activationEnabled": False,
        }
