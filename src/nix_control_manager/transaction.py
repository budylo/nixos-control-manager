from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import re
from typing import Any

from .adoption import AdoptionPlan, PlannedFileChange
from .candidate import CandidateValidation, plan_identity
from .errors import TransactionError
from .home_manager_adoption import (
    HomeManagerAdoptionPlan,
    HomeManagerCandidateValidation,
    home_manager_plan_identity,
)
from .managed_plan import (
    ManagedPlan,
    managed_plan_identity,
    require_live_managed_root,
)


FIXTURE_MARKER = ".ncm-transaction-fixture"
FIXTURE_MARKER_CONTENT = "nix-control-manager-transaction-fixture-v1\n"
_MANIFEST_NAME = "manifest.json"
_LOCK_NAME = "transaction.lock"
_TRANSACTION_ID = re.compile(r"^[0-9a-f]{24}$")


class SimulatedTransactionCrash(TransactionError):
    """Test-only exception that leaves a recoverable journal behind."""


@dataclass(frozen=True, slots=True)
class TransactionResult:
    transaction_id: str
    state: str
    journal_path: Path
    changed_files: tuple[str, ...]
    fixture_only: bool = True

    def to_mapping(self) -> dict[str, Any]:
        return {
            "transactionId": self.transaction_id,
            "state": self.state,
            "journalPath": str(self.journal_path),
            "changedFiles": list(self.changed_files),
            "fixtureOnly": self.fixture_only,
            "activationEnabled": False,
        }


def initialize_transaction_fixture(root: Path) -> None:
    """Mark an isolated test root. This helper refuses NixOS' live root."""
    resolved = root.expanduser().resolve()
    _refuse_live_root(resolved)
    resolved.mkdir(parents=True, exist_ok=True)
    marker = resolved / FIXTURE_MARKER
    if marker.is_symlink():
        raise TransactionError("Fixture marker cannot be a symbolic link")
    if marker.exists() and marker.read_text(encoding="utf-8") != FIXTURE_MARKER_CONTENT:
        raise TransactionError(f"Unexpected fixture marker content at {marker}")
    marker.write_text(FIXTURE_MARKER_CONTENT, encoding="utf-8")


def _refuse_live_root(root: Path) -> None:
    normalized = str(root).replace("\\", "/")
    if root.as_posix() == "/etc/nixos" or normalized.endswith("/etc/nixos"):
        raise TransactionError("The fixture transaction engine refuses /etc/nixos")
    default_home_manager = Path("~/.config/home-manager").expanduser().resolve()
    if (
        root == default_home_manager
        or root.as_posix() == "/etc/home-manager"
        or normalized.endswith("/etc/home-manager")
    ):
        raise TransactionError(
            "The fixture transaction engine refuses live Home Manager roots"
        )


def _require_fixture_root(root: Path) -> Path:
    resolved = root.expanduser().resolve()
    _refuse_live_root(resolved)
    marker = resolved / FIXTURE_MARKER
    if marker.is_symlink() or not marker.is_file():
        raise TransactionError(
            f"Fixture marker is required: {marker}. Live configuration writes are disabled."
        )
    try:
        content = marker.read_text(encoding="utf-8")
    except OSError as error:
        raise TransactionError(f"Could not read fixture marker: {error}") from error
    if content != FIXTURE_MARKER_CONTENT:
        raise TransactionError("Fixture marker content is invalid")
    return resolved


def require_transaction_fixture(root: Path) -> Path:
    """Public read-only fixture gate used by the mock helper backend."""
    return _require_fixture_root(root)


def _require_live_home_manager_root(root: Path) -> Path:
    candidate = root.expanduser()
    if candidate.is_symlink():
        raise TransactionError("The live Home Manager root cannot be a symbolic link")
    resolved = candidate.resolve()
    if not resolved.is_dir():
        raise TransactionError("The live Home Manager root must be an existing directory")
    if resolved == Path("/") or resolved.is_relative_to(Path("/nix/store")):
        raise TransactionError("Unsafe live Home Manager configuration root")
    return resolved


def require_live_home_manager_root(root: Path) -> Path:
    """Validate a configured live Home Manager source root without writing."""
    return _require_live_home_manager_root(root)


def _transaction_root(root: Path, *, fixture_only: bool) -> Path:
    if fixture_only:
        return _require_fixture_root(root)
    return _require_live_home_manager_root(root)


def _digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_target(root: Path, relative_label: str) -> tuple[Path, Path]:
    relative = Path(relative_label)
    if relative.is_absolute() or not relative.parts or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise TransactionError(f"Unsafe transaction path: {relative_label}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise TransactionError(f"Transaction path crosses a symbolic link: {relative_label}")
    return relative, root / relative


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TransactionError(f"Could not read transaction journal {path}: {error}") from error
    if not isinstance(raw, dict) or raw.get("schemaVersion") != 1:
        raise TransactionError(f"Unsupported transaction journal: {path}")
    return raw


def _acquire_lock(journal_root: Path) -> tuple[int, Path]:
    journal_root.mkdir(parents=True, exist_ok=True)
    if journal_root.is_symlink():
        raise TransactionError("Transaction journal root cannot be a symbolic link")
    lock_path = journal_root / _LOCK_NAME
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if os.name == "nt":
            import msvcrt

            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.fsync(descriptor)
        return descriptor, lock_path
    except (OSError, BlockingIOError) as error:
        os.close(descriptor)
        raise TransactionError(f"Another transaction holds {lock_path}") from error


def _release_lock(descriptor: int, lock_path: Path) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _validate_plan(
    plan: AdoptionPlan,
    validation: CandidateValidation,
    root: Path,
) -> str:
    if not plan.safe_to_apply:
        raise TransactionError("The adoption plan is not safe to apply")
    if validation.status != "passed" or not validation.plan_fingerprint:
        raise TransactionError("A successful candidate validation is required")
    fingerprint, candidate_digests = plan_identity(plan, validation.flake_target)
    if fingerprint != validation.plan_fingerprint:
        raise TransactionError("The validated plan fingerprint no longer matches")
    if candidate_digests != validation.candidate_digests:
        raise TransactionError("The validated candidate digests no longer match")
    if plan.inspection.config_root != root:
        raise TransactionError("The adoption plan targets a different configuration root")
    return fingerprint


def _validate_home_manager_plan(
    plan: HomeManagerAdoptionPlan,
    validation: HomeManagerCandidateValidation,
    root: Path,
) -> str:
    if plan.status != "ready" or not plan.changes:
        raise TransactionError("A non-empty Home Manager adoption plan is required")
    if (
        validation.status != "passed"
        or not validation.working_copy_removed
        or not validation.plan_fingerprint
    ):
        raise TransactionError("A successful Home Manager candidate validation is required")
    if not any(
        check.status == "passed" and check.name.startswith("Evaluate")
        for check in validation.checks
    ):
        raise TransactionError("A successful Home Manager evaluation check is required")
    fingerprint, candidate_digests = home_manager_plan_identity(
        plan, validation.flake_target
    )
    if fingerprint != validation.plan_fingerprint:
        raise TransactionError("The validated Home Manager fingerprint no longer matches")
    if candidate_digests != validation.candidate_digests:
        raise TransactionError("The validated Home Manager candidate digests no longer match")
    if plan.root != root:
        raise TransactionError("The Home Manager plan targets a different fixture root")
    return fingerprint


def _validate_managed_plan(
    plan: ManagedPlan,
    validation: CandidateValidation,
    root: Path,
) -> str:
    if not plan.changes:
        raise TransactionError("A non-empty managed plan is required")
    if (
        validation.status != "passed"
        or not validation.working_copy_removed
        or not validation.plan_fingerprint
    ):
        raise TransactionError("A successful managed candidate validation is required")
    if not any(
        check.status == "passed" and check.name.startswith("Evaluate")
        for check in validation.checks
    ):
        raise TransactionError("A successful managed NixOS evaluation is required")
    fingerprint, candidate_digests = managed_plan_identity(plan)
    if fingerprint != validation.plan_fingerprint:
        raise TransactionError("The validated managed fingerprint no longer matches")
    if candidate_digests != validation.candidate_digests:
        raise TransactionError("The validated managed candidate digests no longer match")
    if plan.root != root:
        raise TransactionError("The managed plan targets a different configuration root")
    return fingerprint


def _verification_summary(
    validation: CandidateValidation | HomeManagerCandidateValidation | None,
) -> dict[str, Any] | None:
    if validation is None:
        return None
    summary = {
        "status": validation.status,
        "flakeTarget": validation.flake_target,
        "workingCopyRemoved": validation.working_copy_removed,
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "exitCode": check.exit_code,
                "durationMs": check.duration_ms,
            }
            for check in validation.checks
        ],
    }
    configuration_mode = getattr(validation, "configuration_mode", None)
    if configuration_mode is not None:
        summary["configurationMode"] = configuration_mode
    if isinstance(validation, HomeManagerCandidateValidation):
        summary["integration"] = validation.plan.integration
        summary["username"] = validation.plan.username
    return summary


def _transaction_paths(
    root: Path,
    journal_root: Path,
    transaction_id: str,
) -> tuple[Path, Path]:
    if not _TRANSACTION_ID.fullmatch(transaction_id):
        raise TransactionError("Invalid transaction identifier")
    journal_input = journal_root.expanduser()
    if journal_input.is_symlink():
        raise TransactionError("The transaction journal root cannot be a symbolic link")
    journal = journal_input.resolve()
    if journal == root or journal.is_relative_to(root):
        raise TransactionError("The transaction journal must be outside the configuration root")
    transaction_dir = journal / transaction_id
    if transaction_dir.is_symlink():
        raise TransactionError("Transaction journal entry cannot be a symbolic link")
    return journal, transaction_dir


def _verify_installed_candidates(root: Path, manifest: dict[str, Any]) -> None:
    for entry in manifest["changes"]:
        _, target = _safe_target(root, entry["path"])
        if not target.is_file():
            raise TransactionError(f"Installed candidate is missing: {entry['path']}")
        if _digest_bytes(target.read_bytes()) != entry["candidateSha256"]:
            raise TransactionError(f"Installed candidate changed before finalize: {entry['path']}")


def _verify_change_precondition(root: Path, change: PlannedFileChange) -> tuple[Path, Path]:
    relative, target = _safe_target(root, change.relative_path)
    candidate = change.candidate.encode("utf-8")
    if _digest_bytes(candidate) != change.candidate_sha256:
        raise TransactionError(f"Candidate digest mismatch: {change.relative_path}")
    if change.action == "create":
        if target.exists():
            raise TransactionError(f"Expected an absent file: {change.relative_path}")
    elif change.action == "modify":
        if not target.is_file():
            raise TransactionError(f"Expected an existing regular file: {change.relative_path}")
        if _digest_bytes(target.read_bytes()) != change.previous_sha256:
            raise TransactionError(f"Concurrent edit detected: {change.relative_path}")
    else:
        raise TransactionError(f"Unsupported file action: {change.action}")
    return relative, target


def _create_parents(root: Path, parent: Path) -> list[str]:
    missing: list[Path] = []
    current = parent
    while current != root and not current.exists():
        missing.append(current)
        current = current.parent
    if current != root and current.is_symlink():
        raise TransactionError(f"Parent path is a symbolic link: {current}")
    created: list[str] = []
    for directory in reversed(missing):
        directory.mkdir(mode=0o755)
        directory.chmod(0o755)
        created.append(str(directory.relative_to(root)).replace("\\", "/"))
    return created


def _write_stage(path: Path, content: bytes, mode: int | None) -> None:
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    if mode is not None:
        path.chmod(mode)


def _cleanup_stages_and_directories(root: Path, manifest: dict[str, Any]) -> None:
    for entry in manifest["changes"]:
        _, staged = _safe_target(root, entry["stagedPath"])
        try:
            staged.unlink()
        except FileNotFoundError:
            pass
    for relative in reversed(manifest.get("createdDirectories", [])):
        try:
            (root / relative).rmdir()
        except (FileNotFoundError, OSError):
            pass


def _restore_from_manifest(
    root: Path,
    transaction_dir: Path,
    manifest: dict[str, Any],
) -> None:
    for entry in reversed(manifest["changes"]):
        _, target = _safe_target(root, entry["path"])
        target_digest = _digest_bytes(target.read_bytes()) if target.is_file() else None
        if entry["action"] == "modify":
            if target_digest == entry["previousSha256"]:
                entry["status"] = "rolled-back"
                continue
            if target_digest != entry["candidateSha256"]:
                if entry["status"] == "committed":
                    raise TransactionError(
                        f"Refusing to overwrite a concurrently changed file: {entry['path']}"
                    )
                continue
            _, backup = _safe_target(transaction_dir, entry["backupPath"])
            if not backup.is_file() or _digest_bytes(backup.read_bytes()) != entry["previousSha256"]:
                raise TransactionError(f"Backup verification failed: {entry['path']}")
            restore = target.with_name(f".{target.name}.{manifest['transactionId']}.restore")
            shutil.copyfile(backup, restore)
            _fsync_file(restore)
            os.replace(restore, target)
            _fsync_directory(target.parent)
        elif entry["action"] == "create":
            if target_digest is None:
                entry["status"] = "rolled-back"
                continue
            if target_digest != entry["candidateSha256"]:
                if entry["status"] == "committed":
                    raise TransactionError(
                        f"Refusing to remove a changed created file: {entry['path']}"
                    )
                continue
            target.unlink()
            _fsync_directory(target.parent)
        entry["status"] = "rolled-back"
        _atomic_json(transaction_dir / _MANIFEST_NAME, manifest)
    _cleanup_stages_and_directories(root, manifest)


def _apply_validated_changes(
    *,
    root: Path,
    changes: tuple[PlannedFileChange, ...],
    fingerprint: str,
    journal_root: Path,
    transaction_kind: str,
    fixture_only: bool,
    fault_after_commits: int | None = None,
    simulate_crash: bool = False,
) -> TransactionResult:
    journal_input = journal_root.expanduser()
    if journal_input.is_symlink():
        raise TransactionError("The transaction journal root cannot be a symbolic link")
    journal = journal_input.resolve()
    if journal == root or journal.is_relative_to(root):
        raise TransactionError("The transaction journal must be outside the configuration root")
    if fault_after_commits is not None and fault_after_commits < 1:
        raise TransactionError("fault_after_commits must be at least one")

    verified: list[tuple[PlannedFileChange, Path, Path]] = []
    for change in changes:
        relative, target = _verify_change_precondition(root, change)
        verified.append((change, relative, target))

    lock_descriptor, lock_path = _acquire_lock(journal)
    transaction_id = secrets.token_hex(12)
    transaction_dir = journal / transaction_id
    manifest: dict[str, Any] = {
        "schemaVersion": 1,
        "transactionId": transaction_id,
        "configurationRoot": str(root),
        "transactionKind": transaction_kind,
        "fixtureOnly": fixture_only,
        "planFingerprint": fingerprint,
        "state": "preparing",
        "createdDirectories": [],
        "changes": [],
        "error": None,
    }
    try:
        transaction_dir.mkdir()
        (transaction_dir / "backups").mkdir()
        for index, (change, relative, target) in enumerate(verified):
            staged_name = f".{target.name}.ncm-{transaction_id}-{index}.tmp"
            manifest["changes"].append(
                {
                    "path": str(relative).replace("\\", "/"),
                    "action": change.action,
                    "previousSha256": change.previous_sha256,
                    "candidateSha256": change.candidate_sha256,
                    "backupPath": (
                        f"backups/{index:04d}.bin" if change.action == "modify" else None
                    ),
                    "stagedPath": str((relative.parent / staged_name)).replace("\\", "/"),
                    "status": "planned",
                }
            )
        _atomic_json(transaction_dir / _MANIFEST_NAME, manifest)
    except Exception:
        _release_lock(lock_descriptor, lock_path)
        raise

    try:
        for index, (change, _, target) in enumerate(verified):
            created = _create_parents(root, target.parent)
            manifest["createdDirectories"].extend(created)
            entry = manifest["changes"][index]
            if change.action == "modify":
                backup = transaction_dir / entry["backupPath"]
                shutil.copyfile(target, backup)
                _fsync_file(backup)
                if _digest_bytes(backup.read_bytes()) != change.previous_sha256:
                    raise TransactionError(f"Backup digest mismatch: {change.relative_path}")
                mode = target.stat().st_mode & 0o777
            else:
                mode = 0o644
            _, staged = _safe_target(root, entry["stagedPath"])
            _write_stage(staged, change.candidate.encode("utf-8"), mode)
            entry["status"] = "prepared"
            _atomic_json(transaction_dir / _MANIFEST_NAME, manifest)

        manifest["state"] = "committing"
        _atomic_json(transaction_dir / _MANIFEST_NAME, manifest)
        for index, (change, _, target) in enumerate(verified):
            entry = manifest["changes"][index]
            _, staged = _safe_target(root, entry["stagedPath"])
            _verify_change_precondition(root, change)
            os.replace(staged, target)
            _fsync_directory(target.parent)
            entry["status"] = "committed"
            _atomic_json(transaction_dir / _MANIFEST_NAME, manifest)
            if fault_after_commits == index + 1:
                if simulate_crash:
                    raise SimulatedTransactionCrash(
                        f"Simulated crash after {index + 1} committed files"
                    )
                raise TransactionError(f"Injected failure after {index + 1} committed files")

        manifest["state"] = "awaiting-verification"
        _atomic_json(transaction_dir / _MANIFEST_NAME, manifest)
        return TransactionResult(
            transaction_id=transaction_id,
            state="awaiting-verification",
            journal_path=transaction_dir / _MANIFEST_NAME,
            changed_files=tuple(change.relative_path for change in changes),
            fixture_only=fixture_only,
        )
    except SimulatedTransactionCrash:
        raise
    except Exception as error:
        manifest["state"] = "rolling-back"
        manifest["error"] = str(error)
        _atomic_json(transaction_dir / _MANIFEST_NAME, manifest)
        try:
            _restore_from_manifest(root, transaction_dir, manifest)
            manifest["state"] = "rolled-back"
            _atomic_json(transaction_dir / _MANIFEST_NAME, manifest)
        except Exception as recovery_error:
            manifest["state"] = "recovery-required"
            manifest["recoveryError"] = str(recovery_error)
            _atomic_json(transaction_dir / _MANIFEST_NAME, manifest)
            raise TransactionError(
                f"Transaction failed and automatic recovery also failed: {recovery_error}"
            ) from error
        raise TransactionError(f"Transaction failed and was rolled back: {error}") from error
    finally:
        _release_lock(lock_descriptor, lock_path)


def apply_plan_in_fixture(
    plan: AdoptionPlan,
    validation: CandidateValidation,
    *,
    journal_root: Path,
    fault_after_commits: int | None = None,
    simulate_crash: bool = False,
) -> TransactionResult:
    """Apply a NixOS adoption plan only to a marked disposable fixture."""
    root = _require_fixture_root(plan.inspection.config_root)
    fingerprint = _validate_plan(plan, validation, root)
    return _apply_validated_changes(
        root=root,
        changes=plan.changes,
        fingerprint=fingerprint,
        journal_root=journal_root,
        transaction_kind="nixos-adoption",
        fixture_only=True,
        fault_after_commits=fault_after_commits,
        simulate_crash=simulate_crash,
    )


def apply_home_manager_plan_in_fixture(
    plan: HomeManagerAdoptionPlan,
    validation: HomeManagerCandidateValidation,
    *,
    journal_root: Path,
    fault_after_commits: int | None = None,
    simulate_crash: bool = False,
) -> TransactionResult:
    """Apply a Home Manager plan only to a marked disposable fixture."""
    root = _require_fixture_root(plan.root)
    fingerprint = _validate_home_manager_plan(plan, validation, root)
    return _apply_validated_changes(
        root=root,
        changes=plan.changes,
        fingerprint=fingerprint,
        journal_root=journal_root,
        transaction_kind="home-manager-adoption",
        fixture_only=True,
        fault_after_commits=fault_after_commits,
        simulate_crash=simulate_crash,
    )


def apply_home_manager_plan_live(
    plan: HomeManagerAdoptionPlan,
    validation: HomeManagerCandidateValidation,
    *,
    journal_root: Path,
    fault_after_commits: int | None = None,
    simulate_crash: bool = False,
) -> TransactionResult:
    """Apply an exact validated Home Manager plan without activating it."""
    root = _require_live_home_manager_root(plan.root)
    fingerprint = _validate_home_manager_plan(plan, validation, root)
    return _apply_validated_changes(
        root=root,
        changes=plan.changes,
        fingerprint=fingerprint,
        journal_root=journal_root,
        transaction_kind="home-manager-adoption",
        fixture_only=False,
        fault_after_commits=fault_after_commits,
        simulate_crash=simulate_crash,
    )


def apply_managed_plan_live(
    plan: ManagedPlan,
    validation: CandidateValidation,
    *,
    journal_root: Path,
    fault_after_commits: int | None = None,
    simulate_crash: bool = False,
) -> TransactionResult:
    """Persist only the exact validated NCM state and generated module."""
    root = require_live_managed_root(plan.root)
    fingerprint = _validate_managed_plan(plan, validation, root)
    allowed = {"ncm/state.json", "ncm/packages.nix"}
    if {change.relative_path for change in plan.changes} - allowed:
        raise TransactionError("Managed transaction exceeds its exact two-file scope")
    return _apply_validated_changes(
        root=root,
        changes=plan.changes,
        fingerprint=fingerprint,
        journal_root=journal_root,
        transaction_kind="managed-state",
        fixture_only=False,
        fault_after_commits=fault_after_commits,
        simulate_crash=simulate_crash,
    )


def apply_flake_lock_update_live(
    change: PlannedFileChange,
    *,
    root: Path,
    plan_fingerprint: str,
    validation: dict[str, Any],
    journal_root: Path,
    fault_after_commits: int | None = None,
    simulate_crash: bool = False,
) -> TransactionResult:
    """Persist one exact prevalidated flake.lock candidate without activation."""
    root = require_live_managed_root(root)
    if (
        change.relative_path != "flake.lock"
        or change.path != root / "flake.lock"
        or change.action != "modify"
        or not re.fullmatch(r"[0-9a-f]{64}", plan_fingerprint)
        or validation.get("status") != "passed"
        or validation.get("workingCopyRemoved") is not True
        or validation.get("planFingerprint") != plan_fingerprint
        or validation.get("writeScope") != ["flake.lock"]
    ):
        raise TransactionError("Flake lock transaction exceeds its exact one-file scope")
    return _apply_validated_changes(
        root=root,
        changes=(change,),
        fingerprint=plan_fingerprint,
        journal_root=journal_root,
        transaction_kind="flake-lock-update",
        fixture_only=False,
        fault_after_commits=fault_after_commits,
        simulate_crash=simulate_crash,
    )


def finalize_flake_lock_live_transaction(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str,
    plan_fingerprint: str,
    verification: dict[str, Any],
) -> TransactionResult:
    transaction_root = require_live_managed_root(root)
    journal, transaction_dir = _transaction_paths(
        transaction_root, journal_root, transaction_id
    )
    lock_descriptor, lock_path = _acquire_lock(journal)
    try:
        manifest_path = transaction_dir / _MANIFEST_NAME
        manifest = _load_manifest(manifest_path)
        if (
            manifest.get("configurationRoot") != str(transaction_root)
            or manifest.get("fixtureOnly", True) is not False
            or manifest.get("transactionKind") != "flake-lock-update"
            or manifest.get("planFingerprint") != plan_fingerprint
            or manifest.get("state") != "awaiting-verification"
        ):
            raise TransactionError("Flake lock transaction cannot be finalized")
        if (
            verification.get("status") != "passed"
            or verification.get("workingCopyRemoved") is not True
            or verification.get("planFingerprint") != plan_fingerprint
        ):
            raise TransactionError("Successful installed flake.lock validation is required")
        _verify_installed_candidates(transaction_root, manifest)
        manifest["postVerification"] = verification
        manifest["state"] = "committed"
        _atomic_json(manifest_path, manifest)
        return TransactionResult(
            transaction_id=transaction_id,
            state="committed",
            journal_path=manifest_path,
            changed_files=("flake.lock",),
            fixture_only=False,
        )
    finally:
        _release_lock(lock_descriptor, lock_path)


def _finalize_validated_transaction(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str,
    verification: CandidateValidation | HomeManagerCandidateValidation,
    transaction_kind: str,
    fixture_only: bool,
) -> TransactionResult:
    transaction_root = _transaction_root(root, fixture_only=fixture_only)
    journal, transaction_dir = _transaction_paths(
        transaction_root, journal_root, transaction_id
    )
    lock_descriptor, lock_path = _acquire_lock(journal)
    try:
        manifest_path = transaction_dir / _MANIFEST_NAME
        manifest = _load_manifest(manifest_path)
        if manifest.get("configurationRoot") != str(transaction_root):
            raise TransactionError("Transaction journal targets a different root")
        if manifest.get("fixtureOnly", True) is not fixture_only:
            raise TransactionError("Transaction journal has a different safety mode")
        if manifest.get("transactionKind", "nixos-adoption") != transaction_kind:
            raise TransactionError("Transaction journal belongs to a different workflow")
        if manifest.get("state") != "awaiting-verification":
            raise TransactionError(
                f"Transaction cannot be finalized from state {manifest.get('state')}"
            )
        if verification.status != "passed" or not verification.working_copy_removed:
            raise TransactionError("Successful installed-configuration verification is required")
        if verification.candidate_files:
            raise TransactionError(
                "Post-commit verification proposed additional changes instead of evaluating installed files"
            )
        if not any(
            check.status == "passed" and check.name.startswith("Evaluate")
            for check in verification.checks
        ):
            raise TransactionError("The post-commit evaluation check is missing")
        _verify_installed_candidates(transaction_root, manifest)
        manifest["postVerification"] = _verification_summary(verification)
        manifest["state"] = "committed"
        _atomic_json(manifest_path, manifest)
        return TransactionResult(
            transaction_id=transaction_id,
            state="committed",
            journal_path=manifest_path,
            changed_files=tuple(entry["path"] for entry in manifest["changes"]),
            fixture_only=fixture_only,
        )
    finally:
        _release_lock(lock_descriptor, lock_path)


def finalize_fixture_transaction(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str,
    verification: CandidateValidation,
) -> TransactionResult:
    return _finalize_validated_transaction(
        root,
        journal_root=journal_root,
        transaction_id=transaction_id,
        verification=verification,
        transaction_kind="nixos-adoption",
        fixture_only=True,
    )


def finalize_home_manager_fixture_transaction(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str,
    verification: HomeManagerCandidateValidation,
) -> TransactionResult:
    return _finalize_validated_transaction(
        root,
        journal_root=journal_root,
        transaction_id=transaction_id,
        verification=verification,
        transaction_kind="home-manager-adoption",
        fixture_only=True,
    )


def finalize_home_manager_live_transaction(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str,
    verification: HomeManagerCandidateValidation,
) -> TransactionResult:
    return _finalize_validated_transaction(
        root,
        journal_root=journal_root,
        transaction_id=transaction_id,
        verification=verification,
        transaction_kind="home-manager-adoption",
        fixture_only=False,
    )


def finalize_managed_live_transaction(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str,
    verification: CandidateValidation,
) -> TransactionResult:
    require_live_managed_root(root)
    return _finalize_validated_transaction(
        root,
        journal_root=journal_root,
        transaction_id=transaction_id,
        verification=verification,
        transaction_kind="managed-state",
        fixture_only=False,
    )


def _rollback_transaction(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str,
    reason: str,
    verification: CandidateValidation | HomeManagerCandidateValidation | None = None,
    fixture_only: bool,
    transaction_kind: str | None = None,
    verification_mapping: dict[str, Any] | None = None,
) -> TransactionResult:
    transaction_root = _transaction_root(root, fixture_only=fixture_only)
    journal, transaction_dir = _transaction_paths(
        transaction_root, journal_root, transaction_id
    )
    lock_descriptor, lock_path = _acquire_lock(journal)
    try:
        manifest_path = transaction_dir / _MANIFEST_NAME
        manifest = _load_manifest(manifest_path)
        if manifest.get("configurationRoot") != str(transaction_root):
            raise TransactionError("Transaction journal targets a different root")
        if manifest.get("fixtureOnly", True) is not fixture_only:
            raise TransactionError("Transaction journal has a different safety mode")
        if (
            transaction_kind is not None
            and manifest.get("transactionKind", "nixos-adoption") != transaction_kind
        ):
            raise TransactionError("Transaction journal belongs to a different workflow")
        if manifest.get("state") in {"committed", "rolled-back", "recovered"}:
            raise TransactionError(
                f"Transaction cannot be rolled back from state {manifest.get('state')}"
            )
        manifest["state"] = "rolling-back"
        manifest["error"] = reason
        manifest["postVerification"] = (
            verification_mapping
            if verification_mapping is not None
            else _verification_summary(verification)
        )
        _atomic_json(manifest_path, manifest)
        try:
            _restore_from_manifest(transaction_root, transaction_dir, manifest)
        except Exception as error:
            manifest["state"] = "recovery-required"
            manifest["recoveryError"] = str(error)
            _atomic_json(manifest_path, manifest)
            raise TransactionError(
                f"Rollback needs manual attention for {transaction_id}: {error}"
            ) from error
        manifest["state"] = "rolled-back"
        _atomic_json(manifest_path, manifest)
        return TransactionResult(
            transaction_id=transaction_id,
            state="rolled-back",
            journal_path=manifest_path,
            changed_files=tuple(entry["path"] for entry in manifest["changes"]),
            fixture_only=fixture_only,
        )
    finally:
        _release_lock(lock_descriptor, lock_path)


def rollback_fixture_transaction(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str,
    reason: str,
    verification: CandidateValidation | HomeManagerCandidateValidation | None = None,
) -> TransactionResult:
    return _rollback_transaction(
        root,
        journal_root=journal_root,
        transaction_id=transaction_id,
        reason=reason,
        verification=verification,
        fixture_only=True,
    )


def rollback_home_manager_live_transaction(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str,
    reason: str,
    verification: HomeManagerCandidateValidation | None = None,
) -> TransactionResult:
    return _rollback_transaction(
        root,
        journal_root=journal_root,
        transaction_id=transaction_id,
        reason=reason,
        verification=verification,
        fixture_only=False,
        transaction_kind="home-manager-adoption",
    )


def rollback_managed_live_transaction(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str,
    reason: str,
    verification: CandidateValidation | None = None,
) -> TransactionResult:
    require_live_managed_root(root)
    return _rollback_transaction(
        root,
        journal_root=journal_root,
        transaction_id=transaction_id,
        reason=reason,
        verification=verification,
        fixture_only=False,
        transaction_kind="managed-state",
    )


def rollback_flake_lock_live_transaction(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str,
    reason: str,
    verification: dict[str, Any] | None = None,
) -> TransactionResult:
    require_live_managed_root(root)
    return _rollback_transaction(
        root,
        journal_root=journal_root,
        transaction_id=transaction_id,
        reason=reason,
        fixture_only=False,
        transaction_kind="flake-lock-update",
        verification_mapping=verification,
    )


def _recover_pending_transactions(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str | None = None,
    transaction_kind: str | None = None,
    fixture_only: bool,
) -> tuple[TransactionResult, ...]:
    transaction_root = _transaction_root(root, fixture_only=fixture_only)
    if transaction_id is not None and not _TRANSACTION_ID.fullmatch(transaction_id):
        raise TransactionError("Invalid transaction identifier")
    journal_input = journal_root.expanduser()
    if journal_input.is_symlink():
        raise TransactionError("The transaction journal root cannot be a symbolic link")
    journal = journal_input.resolve()
    if not journal.is_dir():
        return ()
    lock_descriptor, lock_path = _acquire_lock(journal)
    recovered: list[TransactionResult] = []
    try:
        for transaction_dir in sorted(journal.iterdir()):
            if transaction_id is not None and transaction_dir.name != transaction_id:
                continue
            manifest_path = transaction_dir / _MANIFEST_NAME
            if transaction_dir.is_symlink():
                raise TransactionError(
                    f"Transaction journal entry cannot be a symbolic link: {transaction_dir}"
                )
            if not transaction_dir.is_dir() or not manifest_path.is_file():
                continue
            manifest = _load_manifest(manifest_path)
            if manifest.get("configurationRoot") != str(transaction_root):
                continue
            if manifest.get("fixtureOnly", True) is not fixture_only:
                if transaction_id is not None:
                    raise TransactionError(
                        "Transaction journal has a different safety mode"
                    )
                continue
            manifest_kind = manifest.get("transactionKind", "nixos-adoption")
            if transaction_kind is not None and manifest_kind != transaction_kind:
                if transaction_id is not None:
                    raise TransactionError(
                        "Transaction journal belongs to a different workflow"
                    )
                continue
            if manifest.get("state") in {"committed", "rolled-back", "recovered"}:
                continue
            manifest["state"] = "recovering"
            _atomic_json(manifest_path, manifest)
            try:
                _restore_from_manifest(transaction_root, transaction_dir, manifest)
            except Exception as error:
                manifest["state"] = "recovery-required"
                manifest["recoveryError"] = str(error)
                _atomic_json(manifest_path, manifest)
                raise TransactionError(
                    f"Recovery needs manual attention for {manifest['transactionId']}: {error}"
                ) from error
            manifest["state"] = "recovered"
            _atomic_json(manifest_path, manifest)
            recovered.append(
                TransactionResult(
                    transaction_id=manifest["transactionId"],
                    state="recovered",
                    journal_path=manifest_path,
                    changed_files=tuple(entry["path"] for entry in manifest["changes"]),
                    fixture_only=fixture_only,
                )
            )
    finally:
        _release_lock(lock_descriptor, lock_path)
    return tuple(recovered)


def recover_pending_fixture_transactions(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str | None = None,
    transaction_kind: str | None = None,
) -> tuple[TransactionResult, ...]:
    return _recover_pending_transactions(
        root,
        journal_root=journal_root,
        transaction_id=transaction_id,
        transaction_kind=transaction_kind,
        fixture_only=True,
    )


def recover_pending_home_manager_live_transactions(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str | None = None,
) -> tuple[TransactionResult, ...]:
    return _recover_pending_transactions(
        root,
        journal_root=journal_root,
        transaction_id=transaction_id,
        transaction_kind="home-manager-adoption",
        fixture_only=False,
    )


def recover_pending_managed_live_transactions(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str | None = None,
) -> tuple[TransactionResult, ...]:
    require_live_managed_root(root)
    return _recover_pending_transactions(
        root,
        journal_root=journal_root,
        transaction_id=transaction_id,
        transaction_kind="managed-state",
        fixture_only=False,
    )


def recover_pending_flake_lock_live_transactions(
    root: Path,
    *,
    journal_root: Path,
    transaction_id: str | None = None,
) -> tuple[TransactionResult, ...]:
    require_live_managed_root(root)
    return _recover_pending_transactions(
        root,
        journal_root=journal_root,
        transaction_id=transaction_id,
        transaction_kind="flake-lock-update",
        fixture_only=False,
    )
