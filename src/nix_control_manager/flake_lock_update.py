from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable

from .adoption import PlannedFileChange
from .candidate import ValidationCheck
from .flake_inspector import FlakeInput, parse_flake_lock


MAX_LOCK_UPDATE_BYTES = 1_000_000
MAX_SOURCE_FILES = 8_192
MAX_SOURCE_BYTES = 128 * 1024 * 1024
_INPUT_NAME = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_FLAKE_TARGET = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_UNSUPPORTED_TYPES = {"follows", "indirect", "path", "unknown"}

Runner = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


@dataclass(frozen=True, slots=True)
class FlakeLockUpdatePlan:
    root: Path
    input_name: str
    source_fingerprint: str
    source_without_lock_fingerprint: str
    change: PlannedFileChange
    changed_nodes: tuple[str, ...]
    plan_fingerprint: str


@dataclass(frozen=True, slots=True)
class FlakeLockValidation:
    status: str
    flake_target: str
    plan_fingerprint: str
    checks: tuple[ValidationCheck, ...]
    warnings: tuple[str, ...]
    working_copy_removed: bool

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "flakeTarget": self.flake_target,
            "planFingerprint": self.plan_fingerprint,
            "checks": [check.to_mapping() for check in self.checks],
            "warnings": list(self.warnings),
            "workingCopyRemoved": self.working_copy_removed,
            "writeScope": ["flake.lock"],
            "activationEnabled": False,
            "buildEnabled": False,
            "switchEnabled": False,
        }


def _ignored_name(name: str) -> bool:
    return name == ".git" or name == "result" or name.startswith("result-")


def copy_ignore(_directory: str, names: list[str]) -> set[str]:
    return {name for name in names if _ignored_name(name)}


def source_manifest(root: Path, *, exclude_lock: bool = False) -> tuple[str, int, int]:
    """Hash a bounded source tree without following symbolic links."""
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
                        if total_bytes + size > MAX_SOURCE_BYTES:
                            raise ValueError("The Flake source exceeds the size limit")
                        digest.update(chunk)
                records.append(("file", relative, digest.hexdigest()))
            else:
                raise ValueError(f"Unsupported special file in Flake source: {relative}")
            file_count += 1
            total_bytes += size
            if file_count > MAX_SOURCE_FILES:
                raise ValueError("The Flake source contains too many files")
            if total_bytes > MAX_SOURCE_BYTES:
                raise ValueError("The Flake source exceeds the size limit")
    encoded = json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest(), file_count, total_bytes


def read_lock(path: Path) -> tuple[str, dict[str, Any]]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("flake.lock must be a regular file")
    if path.stat().st_size > MAX_LOCK_UPDATE_BYTES:
        raise ValueError("flake.lock exceeds the transactional size limit")
    text = path.read_bytes().decode("utf-8")
    value = json.loads(text)
    if not isinstance(value, dict) or not isinstance(value.get("nodes"), dict):
        raise ValueError("flake.lock has an invalid node table")
    return text, value


def _input_by_name(inputs: tuple[FlakeInput, ...], name: str) -> FlakeInput | None:
    return next((item for item in inputs if item.name == name), None)


def _input_mapping(value: FlakeInput | None) -> dict[str, Any] | None:
    return value.to_mapping() if value is not None else None


def flake_lock_plan_fingerprint(
    *,
    root: Path,
    input_name: str,
    source_fingerprint: str,
    previous_sha256: str,
    candidate_sha256: str,
    changed_nodes: tuple[str, ...],
) -> str:
    manifest = {
        "configurationRoot": str(root.resolve()),
        "inputName": input_name,
        "sourceFingerprint": source_fingerprint,
        "previousSha256": previous_sha256,
        "candidateSha256": candidate_sha256,
        "changedNodes": list(changed_nodes),
        "writeScope": ["flake.lock"],
    }
    encoded = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def plan_flake_lock_update(
    root: Path,
    *,
    input_name: str,
    source_fingerprint: str,
    candidate: str,
) -> FlakeLockUpdatePlan:
    root = root.expanduser().resolve()
    if not _INPUT_NAME.fullmatch(input_name):
        raise ValueError("A safe direct Flake input name is required")
    if not re.fullmatch(r"[0-9a-f]{64}", source_fingerprint):
        raise ValueError("A lowercase source fingerprint is required")
    if len(candidate.encode("utf-8")) > MAX_LOCK_UPDATE_BYTES or "\x00" in candidate:
        raise ValueError("The candidate flake.lock exceeds the transactional boundary")
    current_fingerprint, _, _ = source_manifest(root)
    if current_fingerprint != source_fingerprint:
        raise ValueError("The Flake source changed after the displayed preview")
    source_without_lock_fingerprint, _, _ = source_manifest(root, exclude_lock=True)
    lock_path = root / "flake.lock"
    before_text, before_document = read_lock(lock_path)
    if candidate == before_text:
        raise ValueError("The candidate flake.lock contains no change")
    with tempfile.TemporaryDirectory(prefix="ncm-flake-lock-parse-") as temporary:
        candidate_path = Path(temporary) / "flake.lock"
        candidate_path.write_bytes(candidate.encode("utf-8"))
        after_text, after_document = read_lock(candidate_path)
        before_status, _, _, before_inputs, before_warnings = parse_flake_lock(lock_path)
        after_status, _, _, after_inputs, after_warnings = parse_flake_lock(candidate_path)
    if before_status != "valid" or before_warnings:
        raise ValueError("The current flake.lock does not pass strict inspection")
    if after_status != "valid" or after_warnings:
        raise ValueError("The candidate flake.lock does not pass strict inspection")
    before_input = _input_by_name(before_inputs, input_name)
    after_input = _input_by_name(after_inputs, input_name)
    if before_input is None or after_input is None:
        raise ValueError("The selected input is not a direct locked input")
    if (
        not before_input.locked
        or before_input.follows
        or before_input.input_type in _UNSUPPORTED_TYPES
    ):
        raise ValueError("The selected input type cannot be updated transactionally")
    before_root = before_document["nodes"][before_document["root"]].get("inputs")
    after_root = after_document["nodes"][after_document["root"]].get("inputs")
    if before_root != after_root:
        raise ValueError("The candidate changed the direct input graph")
    changed_direct = {
        item.name
        for item in before_inputs
        if _input_mapping(item) != _input_mapping(_input_by_name(after_inputs, item.name))
    }
    if changed_direct != {input_name}:
        raise ValueError("Exactly the selected direct input must change")
    before_nodes = before_document["nodes"]
    after_nodes = after_document["nodes"]
    changed_nodes = tuple(
        sorted(
            name
            for name in set(before_nodes) | set(after_nodes)
            if before_nodes.get(name) != after_nodes.get(name)
        )
    )
    previous_sha256 = hashlib.sha256(before_text.encode("utf-8")).hexdigest()
    candidate_sha256 = hashlib.sha256(after_text.encode("utf-8")).hexdigest()
    fingerprint = flake_lock_plan_fingerprint(
        root=root,
        input_name=input_name,
        source_fingerprint=source_fingerprint,
        previous_sha256=previous_sha256,
        candidate_sha256=candidate_sha256,
        changed_nodes=changed_nodes,
    )
    change = PlannedFileChange(
        path=lock_path,
        relative_path="flake.lock",
        action="modify",
        reason=f"Update only the locked {input_name} input",
        previous=before_text,
        candidate=after_text,
        diff="",
    )
    return FlakeLockUpdatePlan(
        root=root,
        input_name=input_name,
        source_fingerprint=source_fingerprint,
        source_without_lock_fingerprint=source_without_lock_fingerprint,
        change=change,
        changed_nodes=changed_nodes,
        plan_fingerprint=fingerprint,
    )


def validate_flake_lock_plan(
    plan: FlakeLockUpdatePlan,
    *,
    flake_target: str,
    timeout: int = 120,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
    installed: bool = False,
) -> FlakeLockValidation:
    if not _FLAKE_TARGET.fullmatch(flake_target):
        raise ValueError("A safe nixosConfigurations target is required")
    nix = which("nix")
    if nix is None:
        return FlakeLockValidation(
            "unavailable", flake_target, plan.plan_fingerprint, (),
            ("The nix command is unavailable.",), True,
        )
    candidate_root: Path | None = None
    checks: list[ValidationCheck] = []
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="ncm-flake-lock-validation-") as temporary:
            candidate_root = Path(temporary) / "configuration"
            shutil.copytree(plan.root, candidate_root, symlinks=True, ignore=copy_ignore)
            if not installed:
                (candidate_root / "flake.lock").write_bytes(
                    plan.change.candidate.encode("utf-8")
                )
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
                "eval",
                "--raw",
                "--no-write-lock-file",
                f".#nixosConfigurations.{flake_target}.config.system.build.toplevel.drvPath",
            )
            check_started = time.monotonic()
            try:
                completed = runner(
                    list(command), cwd=candidate_root, capture_output=True, text=True,
                    timeout=timeout, check=False, env=os.environ.copy(),
                )
                checks.append(
                    ValidationCheck(
                        name="Evaluate exact flake.lock NixOS system derivation",
                        status="passed" if completed.returncode == 0 else "failed",
                        command=command,
                        exit_code=completed.returncode,
                        duration_ms=round((time.monotonic() - check_started) * 1000),
                        stdout=(completed.stdout or "")[:16_000],
                        stderr=(completed.stderr or "")[:16_000],
                    )
                )
            except subprocess.TimeoutExpired as error:
                checks.append(
                    ValidationCheck(
                        name="Evaluate exact flake.lock NixOS system derivation",
                        status="timed-out",
                        command=command,
                        exit_code=None,
                        duration_ms=round((time.monotonic() - check_started) * 1000),
                        stderr=f"Validation exceeded {timeout} seconds: {error}",
                    )
                )
    except OSError as error:
        return FlakeLockValidation(
            "blocked", flake_target, plan.plan_fingerprint, tuple(checks),
            (str(error),), candidate_root is None or not candidate_root.exists(),
        )
    status = "passed" if checks and all(check.status == "passed" for check in checks) else "failed"
    return FlakeLockValidation(
        status=status,
        flake_target=flake_target,
        plan_fingerprint=plan.plan_fingerprint,
        checks=tuple(checks),
        warnings=(),
        working_copy_removed=candidate_root is not None and not candidate_root.exists(),
    )
