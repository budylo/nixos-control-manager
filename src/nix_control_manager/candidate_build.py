from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable, Sequence

from .adoption import plan_adoption
from .candidate import effective_flake_target, materialize_candidate, plan_identity
from .errors import NcmError
from .home_manager_adoption import (
    home_manager_plan_identity,
    materialize_home_manager_candidate,
    plan_home_manager_adoption,
    validate_home_manager_adoption,
)
from .home_manager_inspector import inspect_home_manager


_ACTIVE_STATUSES = {
    "queued",
    "preparing",
    "running",
    "analyzing",
    "cancelling",
    "cleaning",
}
_TERMINAL_STATUSES = {"passed", "failed", "cancelled", "blocked", "unavailable", "stale"}
_FLAKE_TARGET = re.compile(r"^[A-Za-z0-9_-]+$")
_JOB_ID = re.compile(r"^[0-9a-f]{24}$")
_STORE_PATH = re.compile(r"^/nix/store/[0-9a-z]{32}-[^\s]+$")
_MAX_EVENTS = 2_000
_MAX_EVENT_CHARS = 4_000


class BuildPreviewError(NcmError):
    """A safe build-preview request could not be accepted."""


LineSink = Callable[[str, str], None]
BuildExecutor = Callable[
    [Sequence[str], Path, threading.Event, LineSink], tuple[int, tuple[str, ...]]
]
Which = Callable[[str], str | None]
EffectiveUid = Callable[[], int | None]
PathIsDir = Callable[[str], bool]


def _effective_uid() -> int | None:
    return os.geteuid() if hasattr(os, "geteuid") else None


def _terminate_process(process: subprocess.Popen[str], *, force: bool = False) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        elif force:
            process.kill()
        else:
            process.terminate()
    except (OSError, ProcessLookupError):
        return


def execute_build_process(
    command: Sequence[str],
    cwd: Path,
    cancel_event: threading.Event,
    line_sink: LineSink,
) -> tuple[int, tuple[str, ...]]:
    """Run one fixed build argv, stream both pipes, and terminate its process group."""
    creationflags = 0
    if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=os.environ.copy(),
        start_new_session=os.name == "posix",
        creationflags=creationflags,
    )
    stdout_lines: list[str] = []

    def read_pipe(pipe, stream: str) -> None:
        if pipe is None:
            return
        try:
            for raw_line in iter(pipe.readline, ""):
                line = raw_line.rstrip("\r\n")
                if stream == "stdout":
                    stdout_lines.append(line)
                line_sink(stream, line)
        finally:
            pipe.close()

    readers = [
        threading.Thread(target=read_pipe, args=(process.stdout, "stdout"), daemon=True),
        threading.Thread(target=read_pipe, args=(process.stderr, "stderr"), daemon=True),
    ]
    for reader in readers:
        reader.start()

    termination_sent = False
    termination_started = 0.0
    while process.poll() is None:
        if cancel_event.is_set() and not termination_sent:
            termination_sent = True
            termination_started = time.monotonic()
            _terminate_process(process)
        elif termination_sent and time.monotonic() - termination_started >= 2.0:
            _terminate_process(process, force=True)
        try:
            process.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            continue

    for reader in readers:
        reader.join(timeout=2)
    return process.returncode, tuple(stdout_lines)


class CandidateBuildManager:
    """Own one unprivileged, disposable NixOS candidate build at a time."""

    def __init__(
        self,
        *,
        config_root: Path,
        flake_target: str | None = None,
        timeout: int = 3_600,
        executor: BuildExecutor = execute_build_process,
        which: Which = shutil.which,
        effective_uid: EffectiveUid = _effective_uid,
        path_is_dir: PathIsDir = lambda value: Path(value).is_dir(),
        current_system_path: Path = Path("/run/current-system"),
    ) -> None:
        if timeout < 1:
            raise ValueError("Build timeout must be at least one second")
        self.config_root = config_root
        self.flake_target = flake_target
        self.timeout = timeout
        self.executor = executor
        self.which = which
        self.effective_uid = effective_uid
        self.path_is_dir = path_is_dir
        self.current_system_path = current_system_path
        self._lock = threading.RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._job_order: deque[str] = deque()
        self._active_job_id: str | None = None
        self._closed = False
        self._source_epoch = 0

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self._closed:
                raise BuildPreviewError("Build-preview manager is closed")
            if self._active_job_id is not None:
                active = self._jobs[self._active_job_id]
                if active["status"] in _ACTIVE_STATUSES:
                    raise BuildPreviewError("A build preview is already running")
            job_id = secrets.token_hex(12)
            effective_uid = self.effective_uid()
            job: dict[str, Any] = {
                "jobId": job_id,
                "status": "queued",
                "createdAt": time.time(),
                "startedAt": None,
                "finishedAt": None,
                "durationMs": None,
                "configurationMode": None,
                "flakeTarget": None,
                "candidateFiles": [],
                "planFingerprint": None,
                "command": [],
                "exitCode": None,
                "outputPaths": [],
                "impactCommand": [],
                "impactExitCode": None,
                "closureDiff": "",
                "impactAvailable": False,
                "currentSystemPath": None,
                "workingCopyRemoved": True,
                "cancelRequested": False,
                "timedOut": False,
                "effectiveUid": effective_uid,
                "privileged": effective_uid == 0,
                "error": None,
                "events": deque(maxlen=_MAX_EVENTS),
                "nextSequence": 1,
                "cancelEvent": threading.Event(),
                "thread": None,
                "sourceEpoch": self._source_epoch,
            }
            self._jobs[job_id] = job
            self._job_order.append(job_id)
            while len(self._job_order) > 8:
                expired = self._job_order.popleft()
                if expired != self._active_job_id:
                    self._jobs.pop(expired, None)
            self._active_job_id = job_id
            self._event(job, "status", "Build preview queued")
            thread = threading.Thread(
                target=self._run_job,
                args=(job_id,),
                name=f"ncm-build-{job_id[:8]}",
                daemon=True,
            )
            job["thread"] = thread
            thread.start()
            return self._snapshot(job, after=0)

    def invalidate(self, reason: str) -> None:
        """Revoke every old build result after a configuration-source write."""
        with self._lock:
            self._source_epoch += 1
            for job in self._jobs.values():
                if job["sourceEpoch"] == self._source_epoch:
                    continue
                if job["status"] in _ACTIVE_STATUSES:
                    job["cancelRequested"] = True
                    job["cancelEvent"].set()
                job["status"] = "stale"
                job["outputPaths"] = []
                job["error"] = {"code": "source-changed", "message": reason}
                self._event(job, "error", reason)

    def latest(self, *, after: int = 0) -> dict[str, Any]:
        with self._lock:
            if not self._job_order:
                return self._idle_snapshot()
            return self._snapshot(self._jobs[self._job_order[-1]], after=after)

    def poll(self, job_id: str, *, after: int = 0) -> dict[str, Any]:
        if not _JOB_ID.fullmatch(job_id):
            raise BuildPreviewError("Invalid build-preview job identifier")
        if after < 0:
            raise BuildPreviewError("Build-preview cursor cannot be negative")
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise BuildPreviewError("Unknown build-preview job")
            return self._snapshot(job, after=after)

    def cancel(self, job_id: str) -> dict[str, Any]:
        if not _JOB_ID.fullmatch(job_id):
            raise BuildPreviewError("Invalid build-preview job identifier")
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise BuildPreviewError("Unknown build-preview job")
            if job["status"] in _TERMINAL_STATUSES:
                return self._snapshot(job, after=0)
            job["cancelRequested"] = True
            job["cancelEvent"].set()
            job["status"] = "cancelling"
            self._event(job, "status", "Cancellation requested")
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
        text = message[:_MAX_EVENT_CHARS]
        sequence = job["nextSequence"]
        job["nextSequence"] += 1
        job["events"].append(
            {
                "sequence": sequence,
                "timestamp": time.time(),
                "stream": stream,
                "message": text,
            }
        )

    def _line_sink(self, job_id: str, stream: str, line: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                self._event(job, stream, line)

    def _fail(self, job: dict[str, Any], status: str, code: str, message: str) -> None:
        job["status"] = status
        job["error"] = {"code": code, "message": message}
        self._event(job, "error", message)

    def _run_job(self, job_id: str) -> None:
        started = time.monotonic()
        candidate_root: Path | None = None
        terminal_result: tuple[str, str | None, str] | None = None
        with self._lock:
            job = self._jobs[job_id]
            job["status"] = "preparing"
            job["startedAt"] = time.time()
            self._event(job, "status", "Preparing an isolated candidate copy")
        try:
            if job["privileged"]:
                with self._lock:
                    self._fail(
                        job,
                        "blocked",
                        "privileged-execution",
                        "Build preview refuses to run with effective UID 0",
                    )
                return
            plan = plan_adoption(self.config_root)
            mode = plan.inspection.configuration_mode
            target = effective_flake_target(plan, self.flake_target)
            with self._lock:
                job["configurationMode"] = mode
                job["flakeTarget"] = target

            if not plan.safe_to_apply:
                with self._lock:
                    self._fail(
                        job,
                        "blocked",
                        "unsafe-plan",
                        "The adoption plan is not safe enough to build automatically",
                    )
                return
            if not plan.inspection.config_root.is_dir():
                with self._lock:
                    self._fail(
                        job,
                        "blocked",
                        "missing-root",
                        "The configuration root is not a readable directory",
                    )
                return
            if mode == "flake":
                if not target or not _FLAKE_TARGET.fullmatch(target):
                    with self._lock:
                        self._fail(
                            job,
                            "blocked",
                            "invalid-flake-target",
                            "A safe nixosConfigurations target is required",
                        )
                    return
                executable = self.which("nix")
            elif mode == "channels":
                executable = self.which("nix-build")
            else:
                executable = None
            if executable is None:
                with self._lock:
                    self._fail(
                        job,
                        "unavailable",
                        "nix-unavailable",
                        "The required Nix build command is unavailable",
                    )
                return
            if job["cancelEvent"].is_set():
                with self._lock:
                    job["status"] = "cancelled"
                    self._event(job, "status", "Build preview cancelled before execution")
                return

            fingerprint, _ = plan_identity(plan, target)
            with tempfile.TemporaryDirectory(prefix="ncm-build-preview-") as temporary:
                candidate_root = Path(temporary) / "configuration"
                candidate_files = materialize_candidate(plan, candidate_root)
                if mode == "flake":
                    installable = (
                        f".#nixosConfigurations.{target}.config.system.build.toplevel"
                    )
                    command = (
                        executable,
                        "--extra-experimental-features",
                        "nix-command flakes",
                        "build",
                        "--no-link",
                        "--print-out-paths",
                        "--print-build-logs",
                        "--no-write-lock-file",
                        installable,
                    )
                else:
                    command = (
                        executable,
                        "<nixpkgs/nixos>",
                        "-A",
                        "system",
                        "-I",
                        f"nixos-config={candidate_root / 'configuration.nix'}",
                        "--no-out-link",
                    )
                with self._lock:
                    job["candidateFiles"] = list(candidate_files)
                    job["planFingerprint"] = fingerprint
                    job["command"] = list(command)
                    job["workingCopyRemoved"] = False
                    job["status"] = "running"
                    self._event(
                        job,
                        "status",
                        "Candidate ready; starting an unprivileged Nix store build",
                    )
                    self._event(job, "command", "$ " + " ".join(command))

                def request_timeout() -> None:
                    with self._lock:
                        if job["status"] in {"running", "analyzing"}:
                            job["timedOut"] = True
                            job["cancelEvent"].set()
                            job["status"] = "cancelling"
                            self._event(
                                job,
                                "error",
                                f"Build preview exceeded the {self.timeout}-second limit",
                            )

                timer = threading.Timer(self.timeout, request_timeout)
                timer.daemon = True
                timer.start()
                try:
                    return_code, stdout_lines = self.executor(
                        command,
                        candidate_root,
                        job["cancelEvent"],
                        lambda stream, line: self._line_sink(job_id, stream, line),
                    )
                    output_paths = tuple(
                        dict.fromkeys(
                            line.strip()
                            for line in stdout_lines
                            if _STORE_PATH.fullmatch(line.strip())
                        )
                    )
                    if (
                        return_code == 0
                        and not job["cancelEvent"].is_set()
                        and len(output_paths) == 1
                        and self.path_is_dir(output_paths[0])
                    ):
                        nix = self.which("nix")
                        current_link = self.current_system_path
                        if nix and current_link.exists():
                            current_system = str(current_link.resolve())
                            impact_command = (
                                nix,
                                "--extra-experimental-features",
                                "nix-command",
                                "store",
                                "diff-closures",
                                current_system,
                                output_paths[0],
                            )
                            with self._lock:
                                job["status"] = "analyzing"
                                job["currentSystemPath"] = current_system
                                job["impactCommand"] = list(impact_command)
                                self._event(
                                    job,
                                    "status",
                                    "Build complete; comparing candidate and active closures",
                                )
                                self._event(
                                    job, "command", "$ " + " ".join(impact_command)
                                )
                            impact_return, impact_lines = self.executor(
                                impact_command,
                                candidate_root,
                                job["cancelEvent"],
                                lambda stream, line: self._line_sink(
                                    job_id,
                                    "impact" if stream == "stdout" else stream,
                                    line,
                                ),
                            )
                            with self._lock:
                                job["impactExitCode"] = impact_return
                                job["closureDiff"] = "\n".join(impact_lines)[:64_000]
                                job["impactAvailable"] = impact_return == 0
                finally:
                    timer.cancel()
                with self._lock:
                    job["exitCode"] = return_code
                    job["outputPaths"] = list(output_paths)
                    if job["timedOut"]:
                        terminal_result = (
                            "failed",
                            "build-timed-out",
                            f"Build preview exceeded the {self.timeout}-second limit",
                        )
                    elif return_code == 0:
                        if job["cancelEvent"].is_set():
                            terminal_result = (
                                "cancelled",
                                None,
                                "Build preview cancelled",
                            )
                        else:
                            terminal_result = (
                                "passed",
                                None,
                                "Build and closure-impact preview completed successfully",
                            )
                    elif job["cancelEvent"].is_set():
                        terminal_result = (
                            "cancelled",
                            None,
                            "Build preview cancelled",
                        )
                    else:
                        terminal_result = (
                            "failed",
                            "build-failed",
                            f"Nix build exited with status {return_code}",
                        )
                    job["status"] = "cleaning"
                    self._event(job, "status", "Removing the disposable candidate copy")
            with self._lock:
                job["workingCopyRemoved"] = candidate_root is not None and not candidate_root.exists()
                if terminal_result is None:
                    self._fail(
                        job,
                        "failed",
                        "incomplete-build",
                        "Build preview ended without a terminal result",
                    )
                else:
                    status, code, message = terminal_result
                    if code is None:
                        job["status"] = status
                        self._event(job, "status", message)
                    else:
                        self._fail(job, status, code, message)
        except OSError as error:
            with self._lock:
                self._fail(job, "failed", "process-error", str(error))
        except ValueError as error:
            with self._lock:
                self._fail(job, "blocked", "candidate-error", str(error))
        except Exception as error:  # defensive worker boundary
            with self._lock:
                self._fail(job, "failed", "internal-error", str(error))
        finally:
            with self._lock:
                if candidate_root is not None:
                    job["workingCopyRemoved"] = not candidate_root.exists()
                job["finishedAt"] = time.time()
                job["durationMs"] = round((time.monotonic() - started) * 1000)
                if job["sourceEpoch"] != self._source_epoch:
                    job["status"] = "stale"
                    job["outputPaths"] = []
                    job["error"] = {
                        "code": "source-changed",
                        "message": "Configuration source changed; a new build is required",
                    }
                elif job["status"] in _ACTIVE_STATUSES:
                    if job["cancelEvent"].is_set():
                        job["status"] = "cancelled"
                        self._event(job, "status", "Build preview cancelled")
                    else:
                        self._fail(
                            job,
                            "failed",
                            "incomplete-build",
                            "Build preview ended without a terminal result",
                        )

    def _snapshot(self, job: dict[str, Any], *, after: int) -> dict[str, Any]:
        events = list(job["events"])
        first_sequence = events[0]["sequence"] if events else job["nextSequence"]
        selected = [event.copy() for event in events if event["sequence"] > after]
        return {
            "jobId": job["jobId"],
            "status": job["status"],
            "createdAt": job["createdAt"],
            "startedAt": job["startedAt"],
            "finishedAt": job["finishedAt"],
            "durationMs": job["durationMs"],
            "configurationMode": job["configurationMode"],
            "flakeTarget": job["flakeTarget"],
            "candidateFiles": list(job["candidateFiles"]),
            "planFingerprint": job["planFingerprint"],
            "command": list(job["command"]),
            "exitCode": job["exitCode"],
            "outputPaths": list(job["outputPaths"]),
            "impactCommand": list(job["impactCommand"]),
            "impactExitCode": job["impactExitCode"],
            "closureDiff": job["closureDiff"],
            "impactAvailable": job["impactAvailable"],
            "currentSystemPath": job["currentSystemPath"],
            "workingCopyRemoved": job["workingCopyRemoved"],
            "cancelRequested": job["cancelRequested"],
            "timedOut": job["timedOut"],
            "cancellable": job["status"] in _ACTIVE_STATUSES,
            "error": job["error"],
            "events": selected,
            "nextCursor": events[-1]["sequence"] if events else after,
            "logsTruncated": bool(events and after < first_sequence - 1),
            "effectiveUid": job["effectiveUid"],
            "privileged": job["privileged"],
            "sourceEpoch": job["sourceEpoch"],
            "stale": job["status"] == "stale",
            "configurationWriteEnabled": False,
            "nixStoreWriteExpected": True,
            "activationEnabled": False,
            "testEnabled": False,
            "switchEnabled": False,
            "dryActivateExecuted": False,
            "activationPreviewReady": (
                job["status"] == "passed"
                and len(job["outputPaths"]) == 1
                and isinstance(job["planFingerprint"], str)
            ),
            "impactReportIncomplete": True,
        }

    def _idle_snapshot(self) -> dict[str, Any]:
        return {
            "jobId": None,
            "status": "idle",
            "events": [],
            "nextCursor": 0,
            "logsTruncated": False,
            "cancellable": False,
            "privileged": False,
            "sourceEpoch": self._source_epoch,
            "stale": False,
            "configurationWriteEnabled": False,
            "nixStoreWriteExpected": True,
            "activationEnabled": False,
            "testEnabled": False,
            "switchEnabled": False,
            "dryActivateExecuted": False,
            "activationPreviewReady": False,
            "impactAvailable": False,
            "closureDiff": "",
            "impactReportIncomplete": True,
        }


class HomeManagerBuildManager(CandidateBuildManager):
    """Own one unprivileged build of an exact validated activationPackage."""

    def __init__(
        self,
        *,
        config_root: Path,
        standalone_root: Path,
        user_state_path: Path,
        flake_target: str | None = None,
        validation_timeout: int = 120,
        timeout: int = 3_600,
        executor: BuildExecutor = execute_build_process,
        which: Which = shutil.which,
        effective_uid: EffectiveUid = _effective_uid,
        path_is_dir: PathIsDir = lambda value: Path(value).is_dir(),
        inspector: Callable[..., Any] = inspect_home_manager,
        planner: Callable[..., Any] = plan_home_manager_adoption,
        validator: Callable[..., Any] = validate_home_manager_adoption,
    ) -> None:
        super().__init__(
            config_root=config_root,
            flake_target=flake_target,
            timeout=timeout,
            executor=executor,
            which=which,
            effective_uid=effective_uid,
            path_is_dir=path_is_dir,
        )
        if validation_timeout < 1:
            raise ValueError("Validation timeout must be at least one second")
        self.standalone_root = standalone_root
        self.user_state_path = user_state_path
        self.validation_timeout = validation_timeout
        self.inspector = inspector
        self.planner = planner
        self.validator = validator

    def start(
        self,
        *,
        username: str,
        integration: str,
        packages: Sequence[str],
        plan_fingerprint: str,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f]{64}", plan_fingerprint):
            raise BuildPreviewError("A lowercase SHA-256 plan fingerprint is required")
        with self._lock:
            if self._closed:
                raise BuildPreviewError("Home Manager build-preview manager is closed")
            if self._active_job_id is not None:
                active = self._jobs[self._active_job_id]
                if active["status"] in _ACTIVE_STATUSES:
                    raise BuildPreviewError("A Home Manager build preview is already running")
            job_id = secrets.token_hex(12)
            effective_uid = self.effective_uid()
            job: dict[str, Any] = {
                "jobId": job_id,
                "workflow": "home-manager",
                "status": "queued",
                "createdAt": time.time(),
                "startedAt": None,
                "finishedAt": None,
                "durationMs": None,
                "username": username,
                "integration": integration,
                "packages": tuple(packages),
                "configurationMode": None,
                "flakeTarget": None,
                "candidateFiles": [],
                "expectedPlanFingerprint": plan_fingerprint,
                "planFingerprint": None,
                "command": [],
                "exitCode": None,
                "outputPaths": [],
                "activationPackagePath": None,
                "workingCopyRemoved": True,
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
            self._event(job, "status", "Home Manager build preview queued")
            thread = threading.Thread(
                target=self._run_job,
                args=(job_id,),
                name=f"ncm-home-build-{job_id[:8]}",
                daemon=True,
            )
            job["thread"] = thread
            thread.start()
            return self._snapshot(job, after=0)

    def _run_job(self, job_id: str) -> None:
        started = time.monotonic()
        candidate_root: Path | None = None
        terminal_result: tuple[str, str | None, str] | None = None
        with self._lock:
            job = self._jobs[job_id]
            job["status"] = "preparing"
            job["startedAt"] = time.time()
            self._event(job, "status", "Reconstructing and validating the exact Home Manager candidate")
        try:
            if job["privileged"]:
                with self._lock:
                    self._fail(
                        job,
                        "blocked",
                        "privileged-execution",
                        "Home Manager build preview refuses to run with effective UID 0",
                    )
                return
            inspection = self.inspector(
                self.config_root,
                standalone_root=self.standalone_root,
                user_state_path=self.user_state_path,
            )
            plan = self.planner(
                self.config_root,
                standalone_root=self.standalone_root,
                user_state_path=self.user_state_path,
                username=job["username"],
                integration=job["integration"],
                packages=job["packages"],
                inspection=inspection,
            )
            if not plan.safe_to_validate:
                with self._lock:
                    self._fail(job, "blocked", "unsafe-plan", "The Home Manager plan is not safe enough to build")
                return
            validation = self.validator(
                plan,
                flake_target=self.flake_target,
                timeout=self.validation_timeout,
            )
            fingerprint, _ = home_manager_plan_identity(plan, validation.flake_target)
            with self._lock:
                job["flakeTarget"] = validation.flake_target
                job["planFingerprint"] = fingerprint
                job["configurationMode"] = (
                    "flake" if (plan.root / "flake.nix").is_file() else "legacy"
                )
            if job["cancelEvent"].is_set():
                with self._lock:
                    job["status"] = "cancelled"
                    self._event(
                        job,
                        "status",
                        "Home Manager build preview cancelled after validation",
                    )
                return
            if validation.status != "passed":
                with self._lock:
                    self._fail(
                        job,
                        (
                            "blocked"
                            if validation.status == "blocked"
                            else "unavailable"
                            if validation.status == "unavailable"
                            else "failed"
                        ),
                        "validation-not-passed",
                        "The Home Manager candidate must pass validation before build-preview",
                    )
                return
            if (
                validation.plan_fingerprint != fingerprint
                or validation.working_copy_removed is not True
            ):
                with self._lock:
                    self._fail(
                        job,
                        "blocked",
                        "invalid-validation-result",
                        "Home Manager validation did not confirm the exact disposable candidate",
                    )
                return
            if fingerprint != job["expectedPlanFingerprint"]:
                with self._lock:
                    self._fail(
                        job,
                        "blocked",
                        "plan-fingerprint-mismatch",
                        "The Home Manager plan changed after validation; validate it again",
                    )
                return
            if not (plan.root / "flake.nix").is_file() and plan.integration == "standalone":
                with self._lock:
                    self._fail(
                        job,
                        "unavailable",
                        "legacy-standalone-build-unavailable",
                        "Automatic build-preview requires a standalone Home Manager flake",
                    )
                return
            if job["cancelEvent"].is_set():
                with self._lock:
                    job["status"] = "cancelled"
                    self._event(job, "status", "Home Manager build preview cancelled before execution")
                return

            executable = self.which("nix" if (plan.root / "flake.nix").is_file() else "nix-build")
            if executable is None:
                with self._lock:
                    self._fail(job, "unavailable", "nix-unavailable", "The required Nix build command is unavailable")
                return

            with tempfile.TemporaryDirectory(prefix="ncm-home-build-preview-") as temporary:
                candidate_root = Path(temporary) / "configuration"
                candidate_files = materialize_home_manager_candidate(plan, candidate_root)
                attribute = json.dumps(job["username"], ensure_ascii=True)
                if (candidate_root / "flake.nix").is_file():
                    if plan.integration == "nixos-module":
                        target = validation.flake_target or ""
                        if not _FLAKE_TARGET.fullmatch(target):
                            with self._lock:
                                self._fail(job, "blocked", "invalid-flake-target", "A safe nixosConfigurations target is required")
                            return
                        installable = (
                            f".#nixosConfigurations.{target}.config.home-manager.users."
                            f"{attribute}.home.activationPackage"
                        )
                    else:
                        installable = f".#homeConfigurations.{attribute}.activationPackage"
                    command = (
                        executable,
                        "--extra-experimental-features",
                        "nix-command flakes",
                        "build",
                        "--no-link",
                        "--print-out-paths",
                        "--print-build-logs",
                        "--no-write-lock-file",
                        installable,
                    )
                else:
                    command = (
                        executable,
                        "<nixpkgs/nixos>",
                        "-A",
                        f"config.home-manager.users.{attribute}.home.activationPackage",
                        "-I",
                        f"nixos-config={candidate_root / 'configuration.nix'}",
                        "--no-out-link",
                    )
                with self._lock:
                    job["candidateFiles"] = list(candidate_files)
                    job["command"] = list(command)
                    job["workingCopyRemoved"] = False
                    job["status"] = "running"
                    self._event(job, "status", "Validated candidate ready; building activationPackage without activation")
                    self._event(job, "command", "$ " + " ".join(command))

                def request_timeout() -> None:
                    with self._lock:
                        if job["status"] == "running":
                            job["timedOut"] = True
                            job["cancelEvent"].set()
                            job["status"] = "cancelling"
                            self._event(job, "error", f"Home Manager build preview exceeded the {self.timeout}-second limit")

                timer = threading.Timer(self.timeout, request_timeout)
                timer.daemon = True
                timer.start()
                try:
                    return_code, stdout_lines = self.executor(
                        command,
                        candidate_root,
                        job["cancelEvent"],
                        lambda stream, line: self._line_sink(job_id, stream, line),
                    )
                finally:
                    timer.cancel()
                output_paths = tuple(
                    dict.fromkeys(
                        line.strip()
                        for line in stdout_lines
                        if _STORE_PATH.fullmatch(line.strip())
                    )
                )
                with self._lock:
                    job["exitCode"] = return_code
                    job["outputPaths"] = list(output_paths)
                    if job["timedOut"]:
                        terminal_result = ("failed", "build-timed-out", f"Home Manager build preview exceeded the {self.timeout}-second limit")
                    elif job["cancelEvent"].is_set():
                        terminal_result = ("cancelled", None, "Home Manager build preview cancelled")
                    elif return_code != 0:
                        terminal_result = ("failed", "build-failed", f"Nix build exited with status {return_code}")
                    elif len(output_paths) != 1:
                        terminal_result = ("failed", "unexpected-build-output", "Nix build did not return exactly one activationPackage store path")
                    elif not self.path_is_dir(output_paths[0]):
                        terminal_result = ("failed", "invalid-store-path", "The reported activationPackage store path is unavailable")
                    else:
                        job["activationPackagePath"] = output_paths[0]
                        terminal_result = ("passed", None, "Home Manager activationPackage built successfully; activation was not run")
                    job["status"] = "cleaning"
                    self._event(job, "status", "Removing the disposable Home Manager candidate copy")
            with self._lock:
                job["workingCopyRemoved"] = candidate_root is not None and not candidate_root.exists()
                status, code, message = terminal_result or ("failed", "incomplete-build", "Home Manager build preview ended without a terminal result")
                if code is None:
                    job["status"] = status
                    self._event(job, "status", message)
                else:
                    self._fail(job, status, code, message)
        except (OSError, ValueError) as error:
            with self._lock:
                self._fail(job, "blocked", "candidate-error", str(error))
        except Exception as error:  # defensive worker boundary
            with self._lock:
                self._fail(job, "failed", "internal-error", str(error))
        finally:
            with self._lock:
                if candidate_root is not None:
                    job["workingCopyRemoved"] = not candidate_root.exists()
                job["finishedAt"] = time.time()
                job["durationMs"] = round((time.monotonic() - started) * 1000)
                if job["status"] in _ACTIVE_STATUSES:
                    if job["cancelEvent"].is_set():
                        job["status"] = "cancelled"
                        self._event(job, "status", "Home Manager build preview cancelled")
                    else:
                        self._fail(job, "failed", "incomplete-build", "Home Manager build preview ended without a terminal result")

    def _snapshot(self, job: dict[str, Any], *, after: int) -> dict[str, Any]:
        events = list(job["events"])
        first_sequence = events[0]["sequence"] if events else job["nextSequence"]
        selected = [event.copy() for event in events if event["sequence"] > after]
        return {
            "jobId": job["jobId"],
            "workflow": "home-manager",
            "status": job["status"],
            "createdAt": job["createdAt"],
            "startedAt": job["startedAt"],
            "finishedAt": job["finishedAt"],
            "durationMs": job["durationMs"],
            "username": job["username"],
            "integration": job["integration"],
            "configurationMode": job["configurationMode"],
            "flakeTarget": job["flakeTarget"],
            "candidateFiles": list(job["candidateFiles"]),
            "expectedPlanFingerprint": job["expectedPlanFingerprint"],
            "planFingerprint": job["planFingerprint"],
            "command": list(job["command"]),
            "exitCode": job["exitCode"],
            "outputPaths": list(job["outputPaths"]),
            "activationPackagePath": job["activationPackagePath"],
            "workingCopyRemoved": job["workingCopyRemoved"],
            "cancelRequested": job["cancelRequested"],
            "timedOut": job["timedOut"],
            "cancellable": job["status"] in _ACTIVE_STATUSES,
            "error": job["error"],
            "events": selected,
            "nextCursor": events[-1]["sequence"] if events else after,
            "logsTruncated": bool(events and after < first_sequence - 1),
            "effectiveUid": job["effectiveUid"],
            "privileged": job["privileged"],
            "configurationWriteEnabled": False,
            "nixStoreWriteExpected": True,
            "activationEnabled": False,
            "homeManagerActivationEnabled": False,
            "testEnabled": False,
            "switchEnabled": False,
            "flakeInputMutationEnabled": False,
            "lockFileWriteEnabled": False,
            "activationPreviewReady": False,
            "impactAvailable": False,
        }

    @staticmethod
    def _idle_snapshot() -> dict[str, Any]:
        return {
            "jobId": None,
            "workflow": "home-manager",
            "status": "idle",
            "events": [],
            "nextCursor": 0,
            "logsTruncated": False,
            "cancellable": False,
            "privileged": False,
            "configurationWriteEnabled": False,
            "nixStoreWriteExpected": True,
            "activationEnabled": False,
            "homeManagerActivationEnabled": False,
            "testEnabled": False,
            "switchEnabled": False,
            "flakeInputMutationEnabled": False,
            "lockFileWriteEnabled": False,
            "activationPreviewReady": False,
            "impactAvailable": False,
        }
