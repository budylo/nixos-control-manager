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
from typing import Any, Callable, Sequence

from .adoption import AdoptionPlan, plan_adoption


_MAX_LOG_CHARS = 16_000
_FLAKE_TARGET = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True, slots=True)
class ValidationCheck:
    name: str
    status: str
    command: tuple[str, ...]
    exit_code: int | None
    duration_ms: int
    stdout: str = ""
    stderr: str = ""

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "command": list(self.command),
            "exitCode": self.exit_code,
            "durationMs": self.duration_ms,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(frozen=True, slots=True)
class CandidateValidation:
    status: str
    configuration_mode: str
    flake_target: str | None
    candidate_files: tuple[str, ...]
    checks: tuple[ValidationCheck, ...]
    warnings: tuple[str, ...]
    plan_fingerprint: str | None = None
    candidate_digests: tuple[tuple[str, str], ...] = ()
    working_copy_removed: bool = True

    @property
    def ready_for_apply_protocol(self) -> bool:
        return self.status == "passed"

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "configurationMode": self.configuration_mode,
            "flakeTarget": self.flake_target,
            "candidateFiles": list(self.candidate_files),
            "checks": [check.to_mapping() for check in self.checks],
            "warnings": list(self.warnings),
            "planFingerprint": self.plan_fingerprint,
            "candidateDigests": dict(self.candidate_digests),
            "readyForApplyProtocol": self.ready_for_apply_protocol,
            "workingCopyRemoved": self.working_copy_removed,
            "activationEnabled": False,
        }


Runner = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


def _trim_log(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= _MAX_LOG_CHARS:
        return value
    return value[:_MAX_LOG_CHARS] + "\n… output truncated by Nix Control Manager …\n"


def _run_check(
    name: str,
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: int,
    runner: Runner,
) -> ValidationCheck:
    started = time.monotonic()
    try:
        completed = runner(
            list(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=os.environ.copy(),
        )
        status = "passed" if completed.returncode == 0 else "failed"
        return ValidationCheck(
            name=name,
            status=status,
            command=tuple(command),
            exit_code=completed.returncode,
            duration_ms=round((time.monotonic() - started) * 1000),
            stdout=_trim_log(completed.stdout),
            stderr=_trim_log(completed.stderr),
        )
    except subprocess.TimeoutExpired as error:
        return ValidationCheck(
            name=name,
            status="timed-out",
            command=tuple(command),
            exit_code=None,
            duration_ms=round((time.monotonic() - started) * 1000),
            stdout=_trim_log(error.stdout if isinstance(error.stdout, str) else ""),
            stderr=_trim_log(error.stderr if isinstance(error.stderr, str) else "")
            + f"\nValidation exceeded the {timeout}-second limit.",
        )
    except OSError as error:
        return ValidationCheck(
            name=name,
            status="failed",
            command=tuple(command),
            exit_code=None,
            duration_ms=round((time.monotonic() - started) * 1000),
            stderr=str(error),
        )


def _safe_change_relative(root: Path, path: Path) -> Path:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"Candidate change escapes the configuration root: {path}") from error
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"Unsafe candidate path: {relative}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Candidate path crosses a symbolic link: {relative}")
    return relative


def materialize_candidate(plan: AdoptionPlan, destination: Path) -> tuple[str, ...]:
    root = plan.inspection.config_root
    shutil.copytree(
        root,
        destination,
        symlinks=True,
        ignore=shutil.ignore_patterns(".git", "result", "result-*"),
    )
    candidate_files: list[str] = []
    for change in plan.changes:
        relative = _safe_change_relative(root, change.path)
        candidate_path = destination / relative
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_path.write_text(change.candidate, encoding="utf-8")
        candidate_files.append(change.relative_path)
    return tuple(candidate_files)


def _blocked(
    plan: AdoptionPlan,
    warning: str,
    *,
    flake_target: str | None,
    status: str = "blocked",
) -> CandidateValidation:
    return CandidateValidation(
        status=status,
        configuration_mode=plan.inspection.configuration_mode,
        flake_target=flake_target,
        candidate_files=tuple(change.relative_path for change in plan.changes),
        checks=(),
        warnings=tuple(dict.fromkeys((*plan.warnings, warning))),
    )


def plan_identity(
    plan: AdoptionPlan, flake_target: str | None
) -> tuple[str, tuple[tuple[str, str], ...]]:
    changes = [
        {
            "path": change.relative_path,
            "action": change.action,
            "previousSha256": change.previous_sha256,
            "candidateSha256": change.candidate_sha256,
        }
        for change in plan.changes
    ]
    manifest = {
        "configurationRoot": str(plan.inspection.config_root),
        "configurationMode": plan.inspection.configuration_mode,
        "flakeTarget": flake_target,
        "changes": changes,
    }
    encoded = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digests = tuple(
        (change.relative_path, change.candidate_sha256) for change in plan.changes
    )
    return hashlib.sha256(encoded).hexdigest(), digests


def effective_flake_target(
    plan: AdoptionPlan, flake_target: str | None
) -> str | None:
    if plan.inspection.configuration_mode == "flake":
        return flake_target or plan.inspection.hostname
    return flake_target


def validate_adoption(
    config_root: Path = Path("/etc/nixos"),
    *,
    flake_target: str | None = None,
    timeout: int = 120,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
) -> CandidateValidation:
    """Evaluate an adoption plan in a disposable copy without building or activating it."""
    plan = plan_adoption(config_root)
    mode = plan.inspection.configuration_mode
    if timeout < 1:
        return _blocked(
            plan,
            "Validation timeout must be at least one second.",
            flake_target=flake_target,
        )
    if not plan.safe_to_apply:
        return _blocked(
            plan,
            "The adoption plan is not safe enough to validate automatically.",
            flake_target=flake_target,
        )
    if not plan.inspection.config_root.is_dir():
        return _blocked(
            plan,
            "The configuration root is not a readable directory.",
            flake_target=flake_target,
        )

    instantiate = which("nix-instantiate")
    if not instantiate:
        return _blocked(
            plan,
            "nix-instantiate is unavailable; validation was not run.",
            flake_target=flake_target,
            status="unavailable",
        )
    nix = None
    flake_target = effective_flake_target(plan, flake_target)
    if mode == "flake":
        if not flake_target or not _FLAKE_TARGET.fullmatch(flake_target):
            return _blocked(
                plan,
                "A flake target containing only letters, digits, underscores, or hyphens is required.",
                flake_target=flake_target,
            )
        nix = which("nix")
        if not nix:
            return _blocked(
                plan,
                "The nix command is unavailable; flake validation was not run.",
                flake_target=flake_target,
                status="unavailable",
            )

    checks: list[ValidationCheck] = []
    warnings = list(plan.warnings)
    candidate_files: tuple[str, ...] = ()
    plan_fingerprint, candidate_digests = plan_identity(plan, flake_target)
    try:
        with tempfile.TemporaryDirectory(prefix="ncm-candidate-") as temporary:
            candidate_root = Path(temporary) / "configuration"
            candidate_files = materialize_candidate(plan, candidate_root)
            changed_nix = [
                candidate_root / change.relative_path
                for change in plan.changes
                if change.relative_path.endswith(".nix")
            ]
            for path in changed_nix:
                check = _run_check(
                    f"Parse {path.relative_to(candidate_root)}",
                    (instantiate, "--parse", str(path)),
                    cwd=candidate_root,
                    timeout=timeout,
                    runner=runner,
                )
                checks.append(check)
                if check.status != "passed":
                    break

            if all(check.status == "passed" for check in checks):
                if mode == "channels":
                    command = (
                        instantiate,
                        "<nixpkgs/nixos>",
                        "-A",
                        "system",
                        "-I",
                        f"nixos-config={candidate_root / 'configuration.nix'}",
                    )
                    checks.append(
                        _run_check(
                            "Evaluate NixOS system derivation",
                            command,
                            cwd=candidate_root,
                            timeout=timeout,
                            runner=runner,
                        )
                    )
                elif mode == "flake" and nix:
                    installable = (
                        f".#nixosConfigurations.{flake_target}.config.system.build.toplevel.drvPath"
                    )
                    command = (
                        nix,
                        "--extra-experimental-features",
                        "nix-command flakes",
                        "eval",
                        "--raw",
                        "--no-write-lock-file",
                        installable,
                    )
                    checks.append(
                        _run_check(
                            "Evaluate flake NixOS system derivation",
                            command,
                            cwd=candidate_root,
                            timeout=timeout,
                            runner=runner,
                        )
                    )
    except (OSError, ValueError) as error:
        warnings.append(f"Candidate workspace could not be created safely: {error}")
        return CandidateValidation(
            status="blocked",
            configuration_mode=mode,
            flake_target=flake_target,
            candidate_files=candidate_files,
            checks=tuple(checks),
            warnings=tuple(dict.fromkeys(warnings)),
            plan_fingerprint=plan_fingerprint,
            candidate_digests=candidate_digests,
        )

    passed = bool(checks) and all(check.status == "passed" for check in checks)
    return CandidateValidation(
        status="passed" if passed else "failed",
        configuration_mode=mode,
        flake_target=flake_target,
        candidate_files=candidate_files,
        checks=tuple(checks),
        warnings=tuple(dict.fromkeys(warnings)),
        plan_fingerprint=plan_fingerprint,
        candidate_digests=candidate_digests,
    )
