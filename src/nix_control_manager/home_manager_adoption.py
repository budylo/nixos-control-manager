from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
from typing import Any, Callable, Sequence

from .adoption import PlannedFileChange
from .errors import ValidationError
from .home_manager_generator import candidate_user_state, generate_home_module
from .home_manager_inspector import (
    HomeManagerInspection,
    inspect_home_manager,
    load_user_state,
    managed_user_state_path,
)
from .user_model import UserManagedState, serialize_user_state, validate_user_name


_SAFE_IMPORTS_LINE = re.compile(r"(?m)^(?P<indent>[ \t]*)imports\s*=\s*\[\s*(?:#.*)?$")
_SIMPLE_MODULE_BODY = re.compile(
    r"(?m)^[^\n]*\}:\s*\n(?:[ \t]*\n)*(?P<indent>[ \t]*)\{\s*(?:#.*)?$"
)
_SIMPLE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_'-]*$")
_MAX_LOG_CHARS = 16_000
_FLAKE_TARGET = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True, slots=True)
class HomeManagerAdoptionPlan:
    status: str
    username: str
    integration: str
    root: Path
    changes: tuple[PlannedFileChange, ...]
    warnings: tuple[str, ...]
    candidate_state: dict[str, Any]
    files_requiring_staging: tuple[str, ...] = ()

    @property
    def safe_to_validate(self) -> bool:
        return self.status in {"ready", "no-changes"}

    @property
    def combined_diff(self) -> str:
        parts = [change.diff.rstrip() for change in self.changes if change.diff]
        return "\n".join(parts).rstrip() + ("\n" if parts else "")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "username": self.username,
            "integration": self.integration,
            "root": str(self.root),
            "safeToValidate": self.safe_to_validate,
            "safeToApply": False,
            "readOnly": True,
            "writeEnabled": False,
            "activationEnabled": False,
            "flakeInputMutationEnabled": False,
            "changes": [change.to_mapping() for change in self.changes],
            "combinedDiff": self.combined_diff,
            "candidateState": self.candidate_state,
            "warnings": list(self.warnings),
            "git": {"filesRequiringStaging": list(self.files_requiring_staging)},
        }


@dataclass(frozen=True, slots=True)
class HomeManagerValidationCheck:
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
class HomeManagerCandidateValidation:
    status: str
    plan: HomeManagerAdoptionPlan
    checks: tuple[HomeManagerValidationCheck, ...]
    warnings: tuple[str, ...]
    working_copy_removed: bool = True
    flake_target: str | None = None
    plan_fingerprint: str | None = None
    candidate_digests: tuple[tuple[str, str], ...] = ()

    @property
    def candidate_files(self) -> tuple[str, ...]:
        return tuple(change.relative_path for change in self.plan.changes)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "username": self.plan.username,
            "integration": self.plan.integration,
            "candidateFiles": [change.relative_path for change in self.plan.changes],
            "checks": [check.to_mapping() for check in self.checks],
            "warnings": list(self.warnings),
            "workingCopyRemoved": self.working_copy_removed,
            "flakeTarget": self.flake_target,
            "planFingerprint": self.plan_fingerprint,
            "candidateDigests": dict(self.candidate_digests),
            "readOnly": True,
            "writeEnabled": False,
            "activationEnabled": False,
            "buildEnabled": False,
            "flakeInputMutationEnabled": False,
        }


def home_manager_plan_identity(
    plan: HomeManagerAdoptionPlan, flake_target: str | None
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
        "root": str(plan.root),
        "username": plan.username,
        "integration": plan.integration,
        "flakeTarget": flake_target,
        "candidateState": plan.candidate_state,
        "changes": changes,
    }
    encoded = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digests = tuple(
        (change.relative_path, change.candidate_sha256) for change in plan.changes
    )
    return hashlib.sha256(encoded).hexdigest(), digests


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _file_change(
    root: Path, path: Path, candidate: str, reason: str
) -> PlannedFileChange | None:
    previous = path.read_bytes().decode("utf-8") if path.is_file() else ""
    if previous == candidate:
        return None
    relative = _relative(root, path)
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
        action="modify" if path.exists() else "create",
        reason=reason,
        previous=previous,
        candidate=candidate,
        diff=diff,
    )


def _crosses_symlink(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            return True
    return False


def _owned_or_missing(root: Path, path: Path) -> bool:
    if _crosses_symlink(root, path):
        return False
    if not path.exists():
        return True
    try:
        return path.is_file() and path.read_text(encoding="utf-8").startswith(
            "# Generated by Nix Control Manager."
        )
    except (OSError, UnicodeDecodeError):
        return False


def _insert_import(
    path: Path, relative_import: str, *, allow_new_block: bool
) -> tuple[str | None, str | None]:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return None, f"Cannot read {path}: {error}"
    if re.search(
        rf"(?<![A-Za-z0-9_./'-]){re.escape(relative_import)}(?![A-Za-z0-9_./'-])",
        content,
    ):
        return content, None
    match = _SAFE_IMPORTS_LINE.search(content)
    if match:
        insertion = (
            f"{match.group('indent')}  {relative_import} "
            "# managed by Nix Control Manager\n"
        )
        return content[: match.end()] + "\n" + insertion + content[match.end() + 1 :], None
    if allow_new_block:
        body = _SIMPLE_MODULE_BODY.search(content)
        if body:
            indent = body.group("indent")
            insertion = (
                "\n"
                f"{indent}  imports = [\n"
                f"{indent}    {relative_import} # managed by Nix Control Manager\n"
                f"{indent}  ];\n"
            )
            return content[: body.end()] + insertion + content[body.end() :], None
    return None, (
        f"{path.name} does not contain a conservative module body or simple "
        "multiline `imports = [` block; automatic insertion is disabled."
    )


def _nix_key(value: str) -> str:
    if _SIMPLE_KEY.fullmatch(value):
        return value
    return json.dumps(value, ensure_ascii=False)


def _wiring_module(username: str, managed_name: str) -> str:
    return (
        "# Generated by Nix Control Manager. DO NOT EDIT BY HAND.\n"
        "# Connects one managed Home Manager module to its NixOS user.\n\n"
        "{ ... }:\n\n"
        "{\n"
        f"  home-manager.users.{_nix_key(username)}.imports = [\n"
        f"    ./{managed_name}\n"
        "  ];\n"
        "}\n"
    )


def _git_staging(root: Path, changes: Sequence[PlannedFileChange]) -> tuple[str, ...]:
    git_root = next((item for item in (root, *root.parents) if (item / ".git").exists()), None)
    if git_root is None:
        return ()
    paths: list[str] = []
    for change in changes:
        if change.action == "create":
            try:
                paths.append(change.path.relative_to(git_root).as_posix())
            except ValueError:
                paths.append(str(change.path))
    return tuple(paths)


def plan_home_manager_adoption(
    config_root: Path,
    *,
    standalone_root: Path,
    user_state_path: Path,
    username: str,
    integration: str,
    packages: Sequence[str],
    inspection: HomeManagerInspection | None = None,
) -> HomeManagerAdoptionPlan:
    validate_user_name(username)
    inspection = inspection or inspect_home_manager(
        config_root,
        standalone_root=standalone_root,
        user_state_path=user_state_path,
    )
    root = (
        inspection.config_root
        if integration == "nixos-module"
        else inspection.standalone_root
    )
    warnings: list[str] = []
    empty_state: dict[str, Any] = inspection.user_state.state.to_mapping()

    if not any(
        user.name == username and user.integration == integration
        for user in inspection.users
    ):
        warnings.append("The exact Home Manager user integration was not detected.")
        return HomeManagerAdoptionPlan(
            "blocked", username, integration, root, (), tuple(warnings), empty_state
        )
    if inspection.user_state.status == "invalid":
        warnings.append("Invalid user-state must be repaired before planning adoption.")
        return HomeManagerAdoptionPlan(
            "blocked", username, integration, root, (), tuple(warnings), empty_state
        )
    if not root.is_dir():
        warnings.append("The selected Home Manager configuration root is unavailable.")
        return HomeManagerAdoptionPlan(
            "blocked", username, integration, root, (), tuple(warnings), empty_state
        )
    previous = inspection.user_state.state.users.get(username)
    if previous is not None and previous.integration != integration:
        warnings.append("Detected integration conflicts with the existing user-state profile.")
        return HomeManagerAdoptionPlan(
            "blocked", username, integration, root, (), tuple(warnings), empty_state
        )

    canonical_state_path = managed_user_state_path(root)
    if _crosses_symlink(root, canonical_state_path):
        warnings.append("The canonical user-state path crosses a symbolic link.")
        return HomeManagerAdoptionPlan(
            "manual", username, integration, root, (), tuple(warnings), empty_state
        )
    canonical_state = load_user_state(canonical_state_path)
    if canonical_state.status == "invalid":
        warnings.append("The canonical ncm/user-state.json is invalid or unreadable.")
        return HomeManagerAdoptionPlan(
            "manual", username, integration, root, (), tuple(warnings), empty_state
        )

    root_users = dict(canonical_state.state.users)
    roots_are_shared = inspection.config_root == inspection.standalone_root
    migrated = False
    for detected_name, profile in inspection.user_state.state.users.items():
        if detected_name in root_users:
            continue
        if roots_are_shared or profile.integration == integration:
            root_users[detected_name] = profile
            migrated = True
    base_state = UserManagedState(
        schema_version=inspection.user_state.state.schema_version,
        users=root_users,
    )
    if migrated:
        warnings.append(
            "Legacy user-state profiles will be copied into ncm/user-state.json; "
            "the legacy source remains unchanged."
        )

    state = candidate_user_state(
        base_state,
        username=username,
        integration=integration,
        packages=packages,
    )

    managed_dir = root / "ncm"
    managed_path = managed_dir / f"managed-home-{username}.nix"
    if not _owned_or_missing(root, managed_path):
        warnings.append(f"Refusing to replace unowned file: {_relative(root, managed_path)}")
        return HomeManagerAdoptionPlan(
            "manual", username, integration, root, (), tuple(warnings), state.to_mapping()
        )

    changes: list[PlannedFileChange] = []
    module_change = _file_change(
        root,
        managed_path,
        generate_home_module(state.users[username]),
        "Create the previewed Home Manager package module",
    )
    if module_change:
        changes.append(module_change)
    state_change = _file_change(
        root,
        canonical_state_path,
        serialize_user_state(state),
        "Persist the versioned Home Manager user-state beside managed modules",
    )
    if state_change:
        changes.append(state_change)

    if integration == "nixos-module":
        wiring_path = managed_dir / f"home-manager-{username}.nix"
        if not _owned_or_missing(root, wiring_path):
            warnings.append(f"Refusing to replace unowned file: {_relative(root, wiring_path)}")
            return HomeManagerAdoptionPlan(
                "manual", username, integration, root, (), tuple(warnings), state.to_mapping()
            )
        configuration_path = root / "configuration.nix"
        if configuration_path.is_symlink() or not configuration_path.is_file():
            warnings.append("configuration.nix is required for conservative NixOS wiring.")
            return HomeManagerAdoptionPlan(
                "manual", username, integration, root, (), tuple(warnings), state.to_mapping()
            )
        wiring_change = _file_change(
            root,
            wiring_path,
            _wiring_module(username, managed_path.name),
            "Connect the managed user module through Home Manager's NixOS module",
        )
        candidate, warning = _insert_import(
            configuration_path,
            f"./ncm/{wiring_path.name}",
            allow_new_block=False,
        )
        if candidate is None:
            warnings.append(warning or "The NixOS import could not be planned safely.")
            return HomeManagerAdoptionPlan(
                "manual", username, integration, root, (), tuple(warnings), state.to_mapping()
            )
        config_change = _file_change(
            root,
            configuration_path,
            candidate,
            "Import the isolated Home Manager wiring module",
        )
        if config_change:
            changes.insert(0, config_change)
        if wiring_change:
            changes.append(wiring_change)
    else:
        home_path = root / "home.nix"
        if home_path.is_symlink() or not home_path.is_file():
            warnings.append("home.nix is required for conservative standalone wiring.")
            return HomeManagerAdoptionPlan(
                "manual", username, integration, root, (), tuple(warnings), state.to_mapping()
            )
        candidate, warning = _insert_import(
            home_path,
            f"./ncm/{managed_path.name}",
            allow_new_block=True,
        )
        if candidate is None:
            warnings.append(warning or "The standalone import could not be planned safely.")
            return HomeManagerAdoptionPlan(
                "manual", username, integration, root, (), tuple(warnings), state.to_mapping()
            )
        home_change = _file_change(
            root,
            home_path,
            candidate,
            "Import the managed package module from standalone home.nix",
        )
        if home_change:
            changes.insert(0, home_change)

    staging = _git_staging(root, changes)
    if staging:
        warnings.append("New files must be staged before a Git-backed flake can evaluate them.")
    return HomeManagerAdoptionPlan(
        "ready" if changes else "no-changes",
        username,
        integration,
        root,
        tuple(changes),
        tuple(warnings),
        state.to_mapping(),
        staging,
    )


Runner = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


def _trim(value: str | None) -> str:
    if not value:
        return ""
    return value if len(value) <= _MAX_LOG_CHARS else value[:_MAX_LOG_CHARS] + "\n… truncated …\n"


def _run(
    name: str,
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: int,
    runner: Runner,
) -> HomeManagerValidationCheck:
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
        return HomeManagerValidationCheck(
            name,
            "passed" if completed.returncode == 0 else "failed",
            tuple(command),
            completed.returncode,
            round((time.monotonic() - started) * 1000),
            _trim(completed.stdout),
            _trim(completed.stderr),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        timed_out = isinstance(error, subprocess.TimeoutExpired)
        return HomeManagerValidationCheck(
            name,
            "timed-out" if timed_out else "failed",
            tuple(command),
            None,
            round((time.monotonic() - started) * 1000),
            stderr=str(error),
        )


def _safe_relative(root: Path, path: Path) -> Path:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValidationError(f"Candidate path escapes the Home Manager root: {path}") from error
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValidationError(f"Unsafe candidate path: {relative}")
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValidationError(f"Candidate path crosses a symbolic link: {relative}")
    return relative


def validate_home_manager_adoption(
    plan: HomeManagerAdoptionPlan,
    *,
    flake_target: str | None = None,
    timeout: int = 120,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
) -> HomeManagerCandidateValidation:
    warnings = list(plan.warnings)
    if timeout < 1 or not plan.safe_to_validate or not plan.root.is_dir():
        warnings.append("The Home Manager plan is not safe enough to validate.")
        return HomeManagerCandidateValidation("blocked", plan, (), tuple(dict.fromkeys(warnings)))
    instantiate = which("nix-instantiate")
    if not instantiate:
        warnings.append("nix-instantiate is unavailable; validation was not run.")
        return HomeManagerCandidateValidation("unavailable", plan, (), tuple(dict.fromkeys(warnings)))

    effective_flake_target = (
        flake_target or socket.gethostname()
        if plan.integration == "nixos-module" and (plan.root / "flake.nix").is_file()
        else flake_target
    )
    plan_fingerprint, candidate_digests = home_manager_plan_identity(
        plan, effective_flake_target
    )
    checks: list[HomeManagerValidationCheck] = []
    try:
        with tempfile.TemporaryDirectory(prefix="ncm-home-candidate-") as temporary:
            candidate_root = Path(temporary) / "configuration"
            shutil.copytree(
                plan.root,
                candidate_root,
                symlinks=True,
                ignore=shutil.ignore_patterns(".git", "result", "result-*"),
            )
            for change in plan.changes:
                relative = _safe_relative(plan.root, change.path)
                candidate = candidate_root / relative
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_text(change.candidate, encoding="utf-8")
                if relative.suffix == ".nix":
                    check = _run(
                        f"Parse {relative.as_posix()}",
                        (instantiate, "--parse", str(candidate)),
                        cwd=candidate_root,
                        timeout=timeout,
                        runner=runner,
                    )
                    checks.append(check)
                    if check.status != "passed":
                        break
                elif relative.as_posix() == "ncm/user-state.json":
                    started = time.monotonic()
                    try:
                        UserManagedState.from_mapping(
                            json.loads(candidate.read_text(encoding="utf-8"))
                        )
                        status = "passed"
                        error = ""
                    except (OSError, json.JSONDecodeError, ValidationError) as exception:
                        status = "failed"
                        error = str(exception)
                    check = HomeManagerValidationCheck(
                        "Validate ncm/user-state.json schema",
                        status,
                        (),
                        0 if status == "passed" else 1,
                        round((time.monotonic() - started) * 1000),
                        stderr=error,
                    )
                    checks.append(check)
                    if check.status != "passed":
                        break

            if all(check.status == "passed" for check in checks):
                if plan.integration == "nixos-module":
                    if (candidate_root / "flake.nix").is_file():
                        target = effective_flake_target or ""
                        nix = which("nix")
                        if not nix or not _FLAKE_TARGET.fullmatch(target):
                            warnings.append(
                                "A safe flake target and the nix command are required for full NixOS evaluation."
                            )
                            return HomeManagerCandidateValidation(
                                "unavailable",
                                plan,
                                tuple(checks),
                                tuple(dict.fromkeys(warnings)),
                                flake_target=effective_flake_target,
                                plan_fingerprint=plan_fingerprint,
                                candidate_digests=candidate_digests,
                            )
                        checks.append(
                            _run(
                                "Evaluate NixOS system derivation with Home Manager candidate",
                                (
                                    nix,
                                    "--extra-experimental-features",
                                    "nix-command flakes",
                                    "eval",
                                    "--raw",
                                    "--no-write-lock-file",
                                    f".#nixosConfigurations.{target}.config.system.build.toplevel.drvPath",
                                ),
                                cwd=candidate_root,
                                timeout=timeout,
                                runner=runner,
                            )
                        )
                    else:
                        checks.append(
                            _run(
                                "Evaluate NixOS system derivation with Home Manager candidate",
                                (
                                    instantiate,
                                    "<nixpkgs/nixos>",
                                    "-A",
                                    "system",
                                    "-I",
                                    f"nixos-config={candidate_root / 'configuration.nix'}",
                                ),
                                cwd=candidate_root,
                                timeout=timeout,
                                runner=runner,
                            )
                        )
                elif (candidate_root / "flake.nix").is_file():
                    nix = which("nix")
                    if not nix:
                        warnings.append("nix is unavailable; standalone flake evaluation was skipped.")
                    else:
                        attribute = _nix_key(plan.username)
                        checks.append(
                            _run(
                                "Evaluate standalone Home Manager activation derivation",
                                (
                                    nix,
                                    "--extra-experimental-features",
                                    "nix-command flakes",
                                    "eval",
                                    "--raw",
                                    "--no-write-lock-file",
                                    f'.#homeConfigurations.{attribute}.activationPackage.drvPath',
                                ),
                                cwd=candidate_root,
                                timeout=timeout,
                                runner=runner,
                            )
                        )
                else:
                    warnings.append(
                        "Legacy standalone configuration received syntax-only validation; build and activation remain disabled."
                    )
    except (OSError, ValidationError) as error:
        warnings.append(f"Disposable Home Manager copy could not be created safely: {error}")
        return HomeManagerCandidateValidation(
            "blocked",
            plan,
            tuple(checks),
            tuple(dict.fromkeys(warnings)),
            flake_target=effective_flake_target,
            plan_fingerprint=plan_fingerprint,
            candidate_digests=candidate_digests,
        )

    passed = bool(checks) and all(check.status == "passed" for check in checks)
    return HomeManagerCandidateValidation(
        "passed" if passed else "failed",
        plan,
        tuple(checks),
        tuple(dict.fromkeys(warnings)),
        flake_target=effective_flake_target,
        plan_fingerprint=plan_fingerprint,
        candidate_digests=candidate_digests,
    )
