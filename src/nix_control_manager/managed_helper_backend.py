from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
import subprocess
from typing import Any, Mapping

from .candidate import CandidateValidation, Runner, Which
from .errors import TransactionError, ValidationError
from .helper_protocol import CandidateFile, ValidatePlanPayload
from .helper_service import (
    HelperBackendError,
    HelperTarget,
    PendingValidatedManagedPlan,
)
from .managed_apply_workflow import execute_managed_live_apply_workflow
from .managed_plan import (
    MANAGED_MODULE_PATH,
    MANAGED_RELATIVE_PATHS,
    MANAGED_STATE_PATH,
    ManagedPlan,
    managed_plan_identity,
    plan_managed_state,
    require_live_managed_root,
    validate_managed_state,
)
from .model import ManagedState
from .transaction import recover_pending_managed_live_transactions


@dataclass(frozen=True, slots=True)
class _PreparedManagedPlan:
    payload: ValidatePlanPayload
    plan: ManagedPlan
    validation: CandidateValidation


class LiveManagedHelperBackend:
    """Validate and persist only the two canonical files owned by NCM."""

    def __init__(
        self,
        *,
        timeout: int = 120,
        runner: Runner = subprocess.run,
        which: Which = shutil.which,
    ) -> None:
        if timeout < 1:
            raise ValueError("timeout must be at least one second")
        self.timeout = timeout
        self.runner = runner
        self.which = which
        self._prepared: dict[tuple[str, str, int], _PreparedManagedPlan] = {}

    @staticmethod
    def _key(target: HelperTarget, fingerprint: str, peer_uid: int) -> tuple[str, str, int]:
        return target.target_id, fingerprint, peer_uid

    @staticmethod
    def _candidate_mapping(plan: ManagedPlan) -> dict[str, CandidateFile]:
        return {
            change.relative_path: CandidateFile(
                relative_path=change.relative_path,
                action=change.action,
                previous_sha256=change.previous_sha256,
                candidate_sha256=change.candidate_sha256,
                candidate=change.candidate,
            )
            for change in plan.changes
        }

    def _match(
        self, target: HelperTarget, payload: ValidatePlanPayload
    ) -> ManagedPlan:
        if not target.managed_write_enabled or target.managed_journal_root is None:
            raise HelperBackendError("operation-disabled", "Managed writes are disabled")
        root = require_live_managed_root(target.configuration_root)
        remote = {change.relative_path: change for change in payload.changes}
        if set(remote) - MANAGED_RELATIVE_PATHS:
            raise HelperBackendError("path-not-allowed", "Managed plan exceeds its scope")
        state_candidate = remote.get(MANAGED_STATE_PATH)
        try:
            raw = json.loads(
                state_candidate.candidate
                if state_candidate is not None
                else (root / MANAGED_STATE_PATH).read_text(encoding="utf-8")
            )
            state = ManagedState.from_mapping(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise HelperBackendError("invalid-managed-state", str(error)) from error
        plan = plan_managed_state(root, state, flake_target=target.flake_target)
        if not plan.changes:
            raise HelperBackendError("plan-mismatch", "The managed plan has no changes")
        fingerprint, _ = managed_plan_identity(plan)
        if fingerprint != payload.plan_fingerprint:
            raise HelperBackendError(
                "plan-mismatch", "The submitted fingerprint does not match the local plan"
            )
        if self._candidate_mapping(plan) != remote:
            raise HelperBackendError(
                "plan-mismatch", "Submitted managed candidates are not canonical"
            )
        module = remote.get(MANAGED_MODULE_PATH)
        if module is not None and module.candidate != self._candidate_mapping(plan)[
            MANAGED_MODULE_PATH
        ].candidate:
            raise HelperBackendError("plan-mismatch", "The generated module is not canonical")
        return plan

    def validate_managed_plan(
        self, target: HelperTarget, payload: ValidatePlanPayload, peer_uid: int
    ) -> Mapping[str, Any]:
        try:
            plan = self._match(target, payload)
            validation = validate_managed_state(
                target.configuration_root,
                plan.state,
                flake_target=target.flake_target,
                timeout=self.timeout,
                runner=self.runner,
                which=self.which,
            )
        except HelperBackendError:
            raise
        except (OSError, TransactionError, ValueError) as error:
            raise HelperBackendError("validation-failed", str(error)) from error
        if (
            validation.status != "passed"
            or validation.plan_fingerprint != payload.plan_fingerprint
        ):
            return {
                "status": validation.status,
                "warnings": list(validation.warnings),
                "checks": [check.to_mapping() for check in validation.checks],
                "workingCopyRemoved": validation.working_copy_removed,
                "fixtureOnly": False,
                "managedWriteEnabled": True,
                "activationEnabled": False,
                "buildEnabled": False,
            }
        self._prepared[self._key(target, payload.plan_fingerprint, peer_uid)] = (
            _PreparedManagedPlan(payload, plan, validation)
        )
        return {
            "status": "passed",
            "planFingerprint": validation.plan_fingerprint,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status,
                    "exitCode": check.exit_code,
                    "durationMs": check.duration_ms,
                }
                for check in validation.checks
            ],
            "warnings": list(validation.warnings),
            "workingCopyRemoved": True,
            "fixtureOnly": False,
            "managedWriteEnabled": True,
            "writeScope": sorted(MANAGED_RELATIVE_PATHS),
            "activationEnabled": False,
            "buildEnabled": False,
        }

    def apply_validated_managed_plan(
        self,
        target: HelperTarget,
        pending: PendingValidatedManagedPlan,
        peer_uid: int,
    ) -> Mapping[str, Any]:
        prepared = self._prepared.pop(
            self._key(target, pending.payload.plan_fingerprint, peer_uid), None
        )
        if prepared is None or prepared.payload != pending.payload:
            raise HelperBackendError(
                "validated-plan-missing", "The backend no longer holds the managed plan"
            )
        if target.managed_journal_root is None:
            raise HelperBackendError("invalid-target", "Managed journal is unavailable")
        try:
            result = execute_managed_live_apply_workflow(
                prepared.plan,
                prepared.validation,
                journal_root=target.managed_journal_root,
                timeout=self.timeout,
                runner=self.runner,
                which=self.which,
            )
        except (OSError, TransactionError, ValueError) as error:
            raise HelperBackendError("transaction-failed", str(error)) from error
        return {
            **result.to_mapping(),
            "filesWritten": (
                len(result.transaction.changed_files)
                if result.state == "committed"
                else 0
            ),
        }

    def recover_managed_transaction(
        self, target: HelperTarget, transaction_id: str, peer_uid: int
    ) -> Mapping[str, Any]:
        if not target.managed_write_enabled or target.managed_journal_root is None:
            raise HelperBackendError("operation-disabled", "Managed recovery is disabled")
        try:
            recovered = recover_pending_managed_live_transactions(
                target.configuration_root,
                journal_root=target.managed_journal_root,
                transaction_id=transaction_id,
            )
        except (OSError, TransactionError, ValueError) as error:
            raise HelperBackendError("recovery-failed", str(error)) from error
        if not recovered:
            return {
                "state": "no-pending-transaction",
                "transactionId": transaction_id,
                "fixtureOnly": False,
                "filesWritten": 0,
                "managedWriteEnabled": True,
                "activationEnabled": False,
            }
        result = recovered[0]
        return {
            **result.to_mapping(),
            "filesWritten": len(result.changed_files),
            "managedWriteEnabled": True,
            "activationEnabled": False,
        }

    def discard_validated_managed_plan(
        self, target: HelperTarget, payload: ValidatePlanPayload, peer_uid: int
    ) -> None:
        self._prepared.pop(
            self._key(target, payload.plan_fingerprint, peer_uid), None
        )
