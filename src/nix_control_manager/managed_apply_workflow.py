from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .candidate import CandidateValidation, Runner, Which
from .errors import TransactionError
from .managed_plan import ManagedPlan, plan_managed_state, validate_managed_state
from .transaction import (
    SimulatedTransactionCrash,
    TransactionResult,
    apply_managed_plan_live,
    finalize_managed_live_transaction,
    rollback_managed_live_transaction,
)


@dataclass(frozen=True, slots=True)
class ManagedApplyWorkflowResult:
    state: str
    transaction: TransactionResult
    pre_validation: CandidateValidation
    post_validation: CandidateValidation | None
    failure_reason: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "transaction": self.transaction.to_mapping(),
            "preValidation": self.pre_validation.to_mapping(),
            "postValidation": (
                self.post_validation.to_mapping() if self.post_validation else None
            ),
            "failureReason": self.failure_reason,
            "fixtureOnly": False,
            "writeEnabled": True,
            "managedWriteEnabled": True,
            "activationEnabled": False,
            "buildEnabled": False,
            "switchEnabled": False,
        }


def execute_managed_live_apply_workflow(
    plan: ManagedPlan,
    pre_validation: CandidateValidation,
    *,
    journal_root: Path,
    timeout: int = 120,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
    simulate_interruption_after_commit: bool = False,
) -> ManagedApplyWorkflowResult:
    provisional = apply_managed_plan_live(
        plan,
        pre_validation,
        journal_root=journal_root,
    )
    if provisional.state != "awaiting-verification":
        raise TransactionError(
            f"Unexpected provisional transaction state: {provisional.state}"
        )
    if simulate_interruption_after_commit:
        raise SimulatedTransactionCrash(
            f"Simulated interruption after provisional commit {provisional.transaction_id}"
        )
    try:
        installed = plan_managed_state(
            plan.root, plan.state, flake_target=pre_validation.flake_target
        )
        if installed.changes:
            raise TransactionError("Installed managed files still produce changes")
        post_validation = validate_managed_state(
            plan.root,
            plan.state,
            flake_target=pre_validation.flake_target,
            timeout=timeout,
            runner=runner,
            which=which,
        )
    except Exception as error:
        rollback = rollback_managed_live_transaction(
            plan.root,
            journal_root=journal_root,
            transaction_id=provisional.transaction_id,
            reason=f"Post-commit managed validation raised an exception: {error}",
        )
        raise TransactionError(
            f"Post-commit managed validation crashed; transaction "
            f"{rollback.transaction_id} was rolled back"
        ) from error
    if post_validation.status != "passed":
        reason = f"Post-commit managed validation returned {post_validation.status}"
        rollback = rollback_managed_live_transaction(
            plan.root,
            journal_root=journal_root,
            transaction_id=provisional.transaction_id,
            reason=reason,
            verification=post_validation,
        )
        return ManagedApplyWorkflowResult(
            state="rolled-back",
            transaction=rollback,
            pre_validation=pre_validation,
            post_validation=post_validation,
            failure_reason=reason,
        )
    try:
        committed = finalize_managed_live_transaction(
            plan.root,
            journal_root=journal_root,
            transaction_id=provisional.transaction_id,
            verification=post_validation,
        )
    except Exception as error:
        rollback = rollback_managed_live_transaction(
            plan.root,
            journal_root=journal_root,
            transaction_id=provisional.transaction_id,
            reason=f"Managed finalize failed after verification: {error}",
            verification=post_validation,
        )
        return ManagedApplyWorkflowResult(
            state="rolled-back",
            transaction=rollback,
            pre_validation=pre_validation,
            post_validation=post_validation,
            failure_reason=str(error),
        )
    return ManagedApplyWorkflowResult(
        state="committed",
        transaction=committed,
        pre_validation=pre_validation,
        post_validation=post_validation,
    )
