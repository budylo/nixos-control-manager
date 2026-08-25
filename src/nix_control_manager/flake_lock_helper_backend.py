from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess
from typing import Any, Mapping

from .candidate import Runner, Which
from .errors import TransactionError
from .flake_lock_update import (
    FlakeLockUpdatePlan,
    plan_flake_lock_update,
    source_manifest,
    validate_flake_lock_plan,
)
from .helper_protocol import CandidateFile, ValidateFlakeLockUpdatePayload
from .helper_service import HelperBackendError, HelperTarget, PendingValidatedFlakeLockUpdate
from .transaction import (
    apply_flake_lock_update_live,
    finalize_flake_lock_live_transaction,
    recover_pending_flake_lock_live_transactions,
    rollback_flake_lock_live_transaction,
)


@dataclass(frozen=True, slots=True)
class _PreparedFlakeLockUpdate:
    payload: ValidateFlakeLockUpdatePayload
    plan: FlakeLockUpdatePlan
    validation: Any


class LiveFlakeLockHelperBackend:
    """Validate and persist exactly one previewed flake.lock candidate."""

    def __init__(
        self,
        *,
        timeout: int = 120,
        runner: Runner = subprocess.run,
        which: Which = shutil.which,
    ) -> None:
        self.timeout = timeout
        self.runner = runner
        self.which = which
        self._prepared: dict[tuple[str, str, int], _PreparedFlakeLockUpdate] = {}

    @staticmethod
    def _key(target: HelperTarget, fingerprint: str, uid: int) -> tuple[str, str, int]:
        return target.target_id, fingerprint, uid

    @staticmethod
    def _candidate(change: Any) -> CandidateFile:
        return CandidateFile(
            relative_path="flake.lock",
            action="modify",
            previous_sha256=change.previous_sha256,
            candidate_sha256=change.candidate_sha256,
            candidate=change.candidate,
        )

    def _match(
        self, target: HelperTarget, payload: ValidateFlakeLockUpdatePayload
    ) -> FlakeLockUpdatePlan:
        if (
            not target.flake_lock_write_enabled
            or target.flake_lock_journal_root is None
            or target.flake_target is None
        ):
            raise HelperBackendError("operation-disabled", "Flake lock writes are disabled")
        if len(payload.changes) != 1 or payload.changes[0].relative_path != "flake.lock":
            raise HelperBackendError("path-not-allowed", "Only flake.lock may be written")
        remote = payload.changes[0]
        try:
            plan = plan_flake_lock_update(
                target.configuration_root,
                input_name=payload.input_name,
                source_fingerprint=payload.source_fingerprint,
                candidate=remote.candidate,
            )
        except (OSError, ValueError) as error:
            raise HelperBackendError("plan-mismatch", str(error)) from error
        if plan.plan_fingerprint != payload.plan_fingerprint:
            raise HelperBackendError("plan-mismatch", "Flake lock fingerprint mismatch")
        if self._candidate(plan.change) != remote:
            raise HelperBackendError("plan-mismatch", "Flake lock candidate is not exact")
        return plan

    def validate_flake_lock_update(
        self, target: HelperTarget, payload: ValidateFlakeLockUpdatePayload, peer_uid: int
    ) -> Mapping[str, Any]:
        plan = self._match(target, payload)
        validation = validate_flake_lock_plan(
            plan,
            flake_target=target.flake_target or "",
            timeout=self.timeout,
            runner=self.runner,
            which=self.which,
        )
        if validation.status == "passed" and validation.working_copy_removed:
            self._prepared[self._key(target, payload.plan_fingerprint, peer_uid)] = (
                _PreparedFlakeLockUpdate(payload, plan, validation)
            )
        return validation.to_mapping()

    def apply_validated_flake_lock_update(
        self,
        target: HelperTarget,
        pending: PendingValidatedFlakeLockUpdate,
        peer_uid: int,
    ) -> Mapping[str, Any]:
        prepared = self._prepared.pop(
            self._key(target, pending.payload.plan_fingerprint, peer_uid), None
        )
        if prepared is None or prepared.payload != pending.payload:
            raise HelperBackendError(
                "validated-plan-missing", "The exact flake.lock plan is no longer retained"
            )
        journal = target.flake_lock_journal_root
        if journal is None:
            raise HelperBackendError("invalid-target", "Flake lock journal is unavailable")
        provisional = None
        try:
            provisional = apply_flake_lock_update_live(
                prepared.plan.change,
                root=prepared.plan.root,
                plan_fingerprint=prepared.plan.plan_fingerprint,
                validation=prepared.validation.to_mapping(),
                journal_root=journal,
            )
            post = validate_flake_lock_plan(
                prepared.plan,
                flake_target=target.flake_target or "",
                timeout=self.timeout,
                runner=self.runner,
                which=self.which,
                installed=True,
            )
            current_without_lock, _, _ = source_manifest(
                prepared.plan.root, exclude_lock=True
            )
            if current_without_lock != prepared.plan.source_without_lock_fingerprint:
                raise TransactionError(
                    "A configuration source other than flake.lock changed during the transaction"
                )
            post_mapping = post.to_mapping()
            if post.status != "passed" or not post.working_copy_removed:
                rolled_back = rollback_flake_lock_live_transaction(
                    prepared.plan.root,
                    journal_root=journal,
                    transaction_id=provisional.transaction_id,
                    reason=f"Installed flake.lock validation returned {post.status}",
                    verification=post_mapping,
                )
                return {
                    "state": "rolled-back",
                    "transaction": rolled_back.to_mapping(),
                    "preValidation": prepared.validation.to_mapping(),
                    "postValidation": post_mapping,
                    "filesWritten": 0,
                    "fixtureOnly": False,
                    "flakeLockWriteEnabled": True,
                    "activationEnabled": False,
                    "buildRequired": True,
                    "switchEnabled": False,
                }
            committed = finalize_flake_lock_live_transaction(
                prepared.plan.root,
                journal_root=journal,
                transaction_id=provisional.transaction_id,
                plan_fingerprint=prepared.plan.plan_fingerprint,
                verification=post_mapping,
            )
        except (OSError, TransactionError, ValueError) as error:
            if provisional is not None:
                try:
                    rollback_flake_lock_live_transaction(
                        prepared.plan.root,
                        journal_root=journal,
                        transaction_id=provisional.transaction_id,
                        reason=f"Flake lock verification/finalization failed: {error}",
                    )
                except (OSError, TransactionError, ValueError) as recovery_error:
                    raise HelperBackendError(
                        "recovery-required",
                        f"Flake lock transaction requires recovery: {recovery_error}",
                    ) from error
            raise HelperBackendError("transaction-failed", str(error)) from error
        return {
            "state": "committed",
            "transaction": committed.to_mapping(),
            "preValidation": prepared.validation.to_mapping(),
            "postValidation": post_mapping,
            "filesWritten": 1,
            "fixtureOnly": False,
            "flakeLockWriteEnabled": True,
            "activationEnabled": False,
            "buildRequired": True,
            "switchEnabled": False,
        }

    def recover_flake_lock_transaction(
        self, target: HelperTarget, transaction_id: str, peer_uid: int
    ) -> Mapping[str, Any]:
        if not target.flake_lock_write_enabled or target.flake_lock_journal_root is None:
            raise HelperBackendError("operation-disabled", "Flake lock recovery is disabled")
        try:
            recovered = recover_pending_flake_lock_live_transactions(
                target.configuration_root,
                journal_root=target.flake_lock_journal_root,
                transaction_id=transaction_id,
            )
        except (OSError, TransactionError, ValueError) as error:
            raise HelperBackendError("recovery-failed", str(error)) from error
        if not recovered:
            return {
                "state": "no-pending-transaction",
                "transactionId": transaction_id,
                "filesWritten": 0,
                "fixtureOnly": False,
                "flakeLockWriteEnabled": True,
                "activationEnabled": False,
            }
        return {
            **recovered[0].to_mapping(),
            "filesWritten": 1,
            "flakeLockWriteEnabled": True,
            "activationEnabled": False,
        }

    def discard_validated_flake_lock_update(
        self, target: HelperTarget, payload: ValidateFlakeLockUpdatePayload, peer_uid: int
    ) -> None:
        self._prepared.pop(self._key(target, payload.plan_fingerprint, peer_uid), None)
