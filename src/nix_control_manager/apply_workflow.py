from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .adoption import AdoptionPlan
from .candidate import CandidateValidation, Runner, Which, validate_adoption
from .errors import TransactionError
from .transaction import (
    SimulatedTransactionCrash,
    TransactionResult,
    apply_plan_in_fixture,
    finalize_fixture_transaction,
    rollback_fixture_transaction,
)


@dataclass(frozen=True, slots=True)
class FixtureApplyWorkflowResult:
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
            "fixtureOnly": True,
            "activationEnabled": False,
        }


def execute_fixture_apply_workflow(
    plan: AdoptionPlan,
    pre_validation: CandidateValidation,
    *,
    journal_root: Path,
    timeout: int = 120,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
    simulate_interruption_after_commit: bool = False,
) -> FixtureApplyWorkflowResult:
    """Commit, re-evaluate, and finalize only inside a marked disposable fixture."""
    provisional = apply_plan_in_fixture(
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
        post_validation = validate_adoption(
            plan.inspection.config_root,
            flake_target=pre_validation.flake_target,
            timeout=timeout,
            runner=runner,
            which=which,
        )
    except Exception as error:
        rollback = rollback_fixture_transaction(
            plan.inspection.config_root,
            journal_root=journal_root,
            transaction_id=provisional.transaction_id,
            reason=f"Post-commit validation raised an exception: {error}",
        )
        raise TransactionError(
            f"Post-commit validation crashed; transaction {rollback.transaction_id} was rolled back"
        ) from error

    if post_validation.status != "passed":
        reason = f"Post-commit validation returned {post_validation.status}"
        rollback = rollback_fixture_transaction(
            plan.inspection.config_root,
            journal_root=journal_root,
            transaction_id=provisional.transaction_id,
            reason=reason,
            verification=post_validation,
        )
        return FixtureApplyWorkflowResult(
            state="rolled-back",
            transaction=rollback,
            pre_validation=pre_validation,
            post_validation=post_validation,
            failure_reason=reason,
        )

    try:
        committed = finalize_fixture_transaction(
            plan.inspection.config_root,
            journal_root=journal_root,
            transaction_id=provisional.transaction_id,
            verification=post_validation,
        )
    except Exception as error:
        try:
            rollback = rollback_fixture_transaction(
                plan.inspection.config_root,
                journal_root=journal_root,
                transaction_id=provisional.transaction_id,
                reason=f"Finalize failed after verification: {error}",
                verification=post_validation,
            )
        except Exception as recovery_error:
            raise TransactionError(
                f"Finalize failed and rollback needs manual attention: {recovery_error}"
            ) from error
        return FixtureApplyWorkflowResult(
            state="rolled-back",
            transaction=rollback,
            pre_validation=pre_validation,
            post_validation=post_validation,
            failure_reason=str(error),
        )

    return FixtureApplyWorkflowResult(
        state="committed",
        transaction=committed,
        pre_validation=pre_validation,
        post_validation=post_validation,
    )
