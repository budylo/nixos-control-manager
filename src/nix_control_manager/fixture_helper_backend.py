from __future__ import annotations

from dataclasses import dataclass
import shutil
import subprocess
from typing import Any, Mapping

from .adoption import AdoptionPlan
from .apply_workflow import execute_fixture_apply_workflow
from .candidate import CandidateValidation, Runner, Which, validate_adoption
from .errors import TransactionError
from .helper_backend_common import (
    match_local_adoption_plan,
    match_local_home_manager_plan,
)
from .helper_protocol import ValidateHomeManagerPlanPayload, ValidatePlanPayload
from .helper_service import (
    HelperBackendError,
    HelperTarget,
    PendingValidatedHomeManagerPlan,
    PendingValidatedPlan,
)
from .home_manager_adoption import (
    HomeManagerAdoptionPlan,
    HomeManagerCandidateValidation,
    validate_home_manager_adoption,
)
from .home_manager_apply_workflow import execute_home_manager_fixture_apply_workflow
from .transaction import (
    recover_pending_fixture_transactions,
)


@dataclass(frozen=True, slots=True)
class _PreparedFixturePlan:
    payload: ValidatePlanPayload
    plan: AdoptionPlan
    validation: CandidateValidation


@dataclass(frozen=True, slots=True)
class _PreparedHomeManagerFixturePlan:
    payload: ValidateHomeManagerPlanPayload
    plan: HomeManagerAdoptionPlan
    validation: HomeManagerCandidateValidation


class FixtureWorkflowHelperBackend:
    """Connect the helper protocol to the apply workflow, still fixture-only."""

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
        self._prepared: dict[tuple[str, str, int], _PreparedFixturePlan] = {}
        self._prepared_home_manager: dict[
            tuple[str, str, int], _PreparedHomeManagerFixturePlan
        ] = {}

    @staticmethod
    def _key(target: HelperTarget, fingerprint: str, peer_uid: int) -> tuple[str, str, int]:
        return target.target_id, fingerprint, peer_uid

    def validate_plan(
        self, target: HelperTarget, plan: ValidatePlanPayload, peer_uid: int
    ) -> Mapping[str, Any]:
        try:
            if target.journal_root is None:
                raise HelperBackendError(
                    "invalid-target", "The fixture target has no transaction journal root"
                )
            local_plan = match_local_adoption_plan(
                target, plan, require_fixture=True
            )
            validation = validate_adoption(
                target.configuration_root,
                flake_target=target.flake_target,
                timeout=self.timeout,
                runner=self.runner,
                which=self.which,
            )
        except HelperBackendError:
            raise
        except (OSError, TransactionError, ValueError) as error:
            raise HelperBackendError("validation-failed", str(error)) from error
        if validation.status != "passed" or validation.plan_fingerprint != plan.plan_fingerprint:
            return {
                "status": validation.status,
                "warnings": list(validation.warnings),
                "checks": [check.to_mapping() for check in validation.checks],
                "workingCopyRemoved": validation.working_copy_removed,
                "fixtureOnly": True,
                "activationEnabled": False,
            }
        self._prepared[self._key(target, plan.plan_fingerprint, peer_uid)] = (
            _PreparedFixturePlan(plan, local_plan, validation)
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
            "workingCopyRemoved": validation.working_copy_removed,
            "fixtureOnly": True,
            "activationEnabled": False,
        }

    def apply_validated_plan(
        self, target: HelperTarget, plan: PendingValidatedPlan, peer_uid: int
    ) -> Mapping[str, Any]:
        key = self._key(target, plan.payload.plan_fingerprint, peer_uid)
        prepared = self._prepared.pop(key, None)
        if prepared is None or prepared.payload != plan.payload:
            raise HelperBackendError(
                "validated-plan-missing", "The backend no longer holds the validated plan"
            )
        assert target.journal_root is not None
        try:
            result = execute_fixture_apply_workflow(
                prepared.plan,
                prepared.validation,
                journal_root=target.journal_root,
                timeout=self.timeout,
                runner=self.runner,
                which=self.which,
            )
        except (OSError, TransactionError, ValueError) as error:
            raise HelperBackendError("transaction-failed", str(error)) from error
        return {
            **result.to_mapping(),
            "filesWritten": (
                len(result.transaction.changed_files) if result.state == "committed" else 0
            ),
        }

    def validate_home_manager_plan(
        self,
        target: HelperTarget,
        payload: ValidateHomeManagerPlanPayload,
        peer_uid: int,
    ) -> Mapping[str, Any]:
        try:
            if target.journal_root is None:
                raise HelperBackendError(
                    "invalid-target", "The fixture target has no transaction journal root"
                )
            local_plan, effective_target = match_local_home_manager_plan(target, payload)
            validation = validate_home_manager_adoption(
                local_plan,
                flake_target=effective_target,
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
                "fixtureOnly": True,
                "writeEnabled": False,
                "liveWriteEnabled": False,
                "activationEnabled": False,
                "buildEnabled": False,
            }
        key = self._key(target, payload.plan_fingerprint, peer_uid)
        self._prepared_home_manager[key] = _PreparedHomeManagerFixturePlan(
            payload, local_plan, validation
        )
        return {
            "status": "passed",
            "planFingerprint": validation.plan_fingerprint,
            "username": local_plan.username,
            "integration": local_plan.integration,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status,
                    "exitCode": check.exit_code,
                    "durationMs": check.duration_ms,
                }
                for check in validation.checks
            ],
            "workingCopyRemoved": validation.working_copy_removed,
            "fixtureOnly": True,
            "writeEnabled": False,
            "liveWriteEnabled": False,
            "activationEnabled": False,
            "buildEnabled": False,
        }

    def apply_validated_home_manager_plan(
        self,
        target: HelperTarget,
        pending: PendingValidatedHomeManagerPlan,
        peer_uid: int,
    ) -> Mapping[str, Any]:
        key = self._key(target, pending.payload.plan_fingerprint, peer_uid)
        prepared = self._prepared_home_manager.pop(key, None)
        if prepared is None or prepared.payload != pending.payload:
            raise HelperBackendError(
                "validated-plan-missing",
                "The backend no longer holds the validated Home Manager plan",
            )
        assert target.journal_root is not None
        try:
            result = execute_home_manager_fixture_apply_workflow(
                prepared.plan,
                prepared.validation,
                journal_root=target.journal_root,
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

    def recover_transaction(
        self, target: HelperTarget, transaction_id: str, peer_uid: int
    ) -> Mapping[str, Any]:
        if not target.fixture_only or target.journal_root is None:
            raise HelperBackendError("fixture-required", "Recovery target is not a fixture")
        try:
            recovered = recover_pending_fixture_transactions(
                target.configuration_root,
                journal_root=target.journal_root,
                transaction_id=transaction_id,
                transaction_kind="nixos-adoption",
            )
        except (OSError, TransactionError, ValueError) as error:
            raise HelperBackendError("recovery-failed", str(error)) from error
        if not recovered:
            return {
                "state": "no-pending-transaction",
                "transactionId": transaction_id,
                "fixtureOnly": True,
                "filesWritten": 0,
                "activationEnabled": False,
            }
        result = recovered[0]
        return {
            **result.to_mapping(),
            "filesWritten": len(result.changed_files),
        }

    def recover_home_manager_transaction(
        self, target: HelperTarget, transaction_id: str, peer_uid: int
    ) -> Mapping[str, Any]:
        if not target.fixture_only or target.journal_root is None:
            raise HelperBackendError("fixture-required", "Recovery target is not a fixture")
        try:
            recovered = recover_pending_fixture_transactions(
                target.configuration_root,
                journal_root=target.journal_root,
                transaction_id=transaction_id,
                transaction_kind="home-manager-adoption",
            )
        except (OSError, TransactionError, ValueError) as error:
            raise HelperBackendError("recovery-failed", str(error)) from error
        if not recovered:
            return {
                "state": "no-pending-transaction",
                "transactionId": transaction_id,
                "fixtureOnly": True,
                "filesWritten": 0,
                "liveWriteEnabled": False,
                "activationEnabled": False,
            }
        result = recovered[0]
        return {
            **result.to_mapping(),
            "filesWritten": len(result.changed_files),
            "liveWriteEnabled": False,
            "activationEnabled": False,
        }

    def discard_validated_plan(
        self, target: HelperTarget, plan: ValidatePlanPayload, peer_uid: int
    ) -> None:
        self._prepared.pop(self._key(target, plan.plan_fingerprint, peer_uid), None)

    def discard_validated_home_manager_plan(
        self,
        target: HelperTarget,
        plan: ValidateHomeManagerPlanPayload,
        peer_uid: int,
    ) -> None:
        self._prepared_home_manager.pop(
            self._key(target, plan.plan_fingerprint, peer_uid), None
        )
