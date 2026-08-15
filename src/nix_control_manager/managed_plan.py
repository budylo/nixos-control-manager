from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff
import hashlib
import json
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .adoption import PlannedFileChange
from .candidate import CandidateValidation, Runner, Which, _run_check
from .model import ManagedState
from .nix_generator import generate_module
from .storage import serialize_state
from .system_inspector import inspect_system


MANAGED_STATE_PATH = "ncm/state.json"
MANAGED_MODULE_PATH = "ncm/packages.nix"
MANAGED_RELATIVE_PATHS = frozenset({MANAGED_STATE_PATH, MANAGED_MODULE_PATH})


@dataclass(frozen=True, slots=True)
class ManagedPlan:
    root: Path
    configuration_mode: str
    flake_target: str | None
    state: ManagedState
    changes: tuple[PlannedFileChange, ...]
    warnings: tuple[str, ...] = ()

    @property
    def status(self) -> str:
        return "ready" if self.changes else "no-changes"

    @property
    def combined_diff(self) -> str:
        parts = [change.diff.rstrip() for change in self.changes if change.diff]
        return "\n".join(parts).rstrip() + ("\n" if parts else "")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "safeToValidate": True,
            "configurationMode": self.configuration_mode,
            "flakeTarget": self.flake_target,
            "changes": [change.to_mapping() for change in self.changes],
            "combinedDiff": self.combined_diff,
            "warnings": list(self.warnings),
            "writeScope": sorted(MANAGED_RELATIVE_PATHS),
            "activationEnabled": False,
        }


def _safe_managed_root(root: Path) -> Path:
    candidate = root.expanduser()
    if candidate.is_symlink():
        raise ValueError("The managed configuration root cannot be a symbolic link")
    resolved = candidate.resolve()
    if not resolved.is_dir():
        raise ValueError("The managed configuration root must be an existing directory")
    if resolved == Path("/") or resolved.is_relative_to(Path("/nix/store")):
        raise ValueError("Unsafe managed configuration root")
    managed = resolved / "ncm"
    if managed.is_symlink():
        raise ValueError("The managed ncm directory cannot be a symbolic link")
    for relative in MANAGED_RELATIVE_PATHS:
        path = resolved / relative
        if path.is_symlink():
            raise ValueError(f"Managed path cannot be a symbolic link: {relative}")
        if path.exists() and not path.is_file():
            raise ValueError(f"Managed path must be a regular file: {relative}")
    return resolved


def require_live_managed_root(root: Path) -> Path:
    """Validate the source root used by the exact two-file live workflow."""
    resolved = _safe_managed_root(root)
    normalized = str(resolved).replace("\\", "/")
    if resolved.as_posix() != "/etc/nixos" and not normalized.endswith("/etc/nixos"):
        raise ValueError("Live managed writes are restricted to /etc/nixos")
    return resolved


def _change(root: Path, relative: str, candidate: str, reason: str) -> PlannedFileChange | None:
    path = root / relative
    try:
        previous = path.read_bytes().decode("utf-8") if path.is_file() else ""
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"Could not read managed path {relative}: {error}") from error
    if previous == candidate:
        return None
    action = "modify" if path.exists() else "create"
    diff = "".join(
        unified_diff(
            previous.splitlines(keepends=True),
            candidate.splitlines(keepends=True),
            fromfile=relative,
            tofile=f"{relative} (candidate)",
        )
    )
    return PlannedFileChange(
        path=path,
        relative_path=relative,
        action=action,
        reason=reason,
        previous=previous,
        candidate=candidate,
        diff=diff,
    )


def plan_managed_state(
    root: Path,
    state: ManagedState,
    *,
    flake_target: str | None = None,
) -> ManagedPlan:
    resolved = _safe_managed_root(root)
    inspection = inspect_system(resolved)
    if inspection.configuration_mode not in {"channels", "flake"}:
        raise ValueError("A readable NixOS configuration entrypoint is required")
    effective_target = flake_target
    if inspection.configuration_mode == "flake":
        effective_target = effective_target or inspection.hostname or socket.gethostname()
    changes = tuple(
        change
        for change in (
            _change(
                resolved,
                MANAGED_STATE_PATH,
                serialize_state(state),
                "Persist the versioned Nix Control Manager state",
            ),
            _change(
                resolved,
                MANAGED_MODULE_PATH,
                generate_module(state),
                "Regenerate the NixOS module from the exact state",
            ),
        )
        if change is not None
    )
    return ManagedPlan(
        root=resolved,
        configuration_mode=inspection.configuration_mode,
        flake_target=effective_target,
        state=state,
        changes=changes,
        warnings=tuple(inspection.warnings),
    )


def managed_plan_identity(
    plan: ManagedPlan,
) -> tuple[str, tuple[tuple[str, str], ...]]:
    manifest = {
        "configurationRoot": str(plan.root),
        "configurationMode": plan.configuration_mode,
        "flakeTarget": plan.flake_target,
        "workflow": "managed-state-v1",
        "changes": [
            {
                "path": change.relative_path,
                "action": change.action,
                "previousSha256": change.previous_sha256,
                "candidateSha256": change.candidate_sha256,
            }
            for change in plan.changes
        ],
    }
    encoded = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digests = tuple(
        (change.relative_path, change.candidate_sha256) for change in plan.changes
    )
    return hashlib.sha256(encoded).hexdigest(), digests


def validate_managed_state(
    root: Path,
    state: ManagedState,
    *,
    flake_target: str | None = None,
    timeout: int = 120,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
) -> CandidateValidation:
    plan = plan_managed_state(root, state, flake_target=flake_target)
    fingerprint, digests = managed_plan_identity(plan)
    instantiate = which("nix-instantiate")
    nix = which("nix") if plan.configuration_mode == "flake" else None
    warnings = list(plan.warnings)
    checks = []
    candidate_files = tuple(change.relative_path for change in plan.changes)
    if timeout < 1:
        warnings.append("Validation timeout must be at least one second.")
    elif not instantiate:
        warnings.append("nix-instantiate is unavailable; validation was not run.")
    elif plan.configuration_mode == "flake" and not nix:
        warnings.append("The nix command is unavailable; flake validation was not run.")
    else:
        try:
            with tempfile.TemporaryDirectory(prefix="ncm-managed-") as temporary:
                candidate_root = Path(temporary) / "configuration"
                shutil.copytree(
                    plan.root,
                    candidate_root,
                    symlinks=True,
                    ignore=shutil.ignore_patterns(".git", "result", "result-*"),
                )
                for change in plan.changes:
                    candidate = candidate_root / change.relative_path
                    candidate.parent.mkdir(parents=True, exist_ok=True)
                    candidate.write_text(change.candidate, encoding="utf-8")
                module = candidate_root / MANAGED_MODULE_PATH
                checks.append(
                    _run_check(
                        f"Parse {MANAGED_MODULE_PATH}",
                        (instantiate, "--parse", str(module)),
                        cwd=candidate_root,
                        timeout=timeout,
                        runner=runner,
                    )
                )
                if checks[-1].status == "passed":
                    if plan.configuration_mode == "channels":
                        command = (
                            instantiate,
                            "<nixpkgs/nixos>",
                            "-A",
                            "system",
                            "-I",
                            f"nixos-config={candidate_root / 'configuration.nix'}",
                        )
                        name = "Evaluate installed NixOS system derivation"
                    else:
                        command = (
                            nix,
                            "--extra-experimental-features",
                            "nix-command flakes",
                            "eval",
                            "--raw",
                            "--no-write-lock-file",
                            f".#nixosConfigurations.{plan.flake_target}.config.system.build.toplevel.drvPath",
                        )
                        name = "Evaluate installed flake NixOS system derivation"
                    checks.append(
                        _run_check(
                            name,
                            command,
                            cwd=candidate_root,
                            timeout=timeout,
                            runner=runner,
                        )
                    )
        except (OSError, ValueError) as error:
            warnings.append(f"Managed candidate workspace failed safely: {error}")
    passed = bool(checks) and all(check.status == "passed" for check in checks)
    return CandidateValidation(
        status="passed" if passed else "failed",
        configuration_mode=plan.configuration_mode,
        flake_target=plan.flake_target,
        candidate_files=candidate_files,
        checks=tuple(checks),
        warnings=tuple(dict.fromkeys(warnings)),
        plan_fingerprint=fingerprint,
        candidate_digests=digests,
        working_copy_removed=True,
    )
