from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .errors import TransactionError
from .home_manager_adoption import (
    HomeManagerAdoptionPlan,
    HomeManagerCandidateValidation,
    Runner,
    Which,
    plan_home_manager_adoption,
    validate_home_manager_adoption,
)
from .home_manager_inspector import inspect_home_manager, managed_user_state_path
from .transaction import (
    SimulatedTransactionCrash,
    TransactionResult,
    apply_home_manager_plan_in_fixture,
    finalize_home_manager_fixture_transaction,
    rollback_fixture_transaction,
)
from .user_model import UserManagedState


@dataclass(frozen=True, slots=True)
class HomeManagerFixtureApplyWorkflowResult:
    state: str
    transaction: TransactionResult
    pre_validation: HomeManagerCandidateValidation
    post_validation: HomeManagerCandidateValidation | None
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
            "writeEnabled": True,
            "liveWriteEnabled": False,
            "activationEnabled": False,
            "buildEnabled": False,
        }


def _installed_plan(plan: HomeManagerAdoptionPlan) -> HomeManagerAdoptionPlan:
    state = UserManagedState.from_mapping(plan.candidate_state)
    profile = state.users.get(plan.username)
    if profile is None or profile.integration != plan.integration:
        raise TransactionError("The Home Manager candidate state no longer matches the plan")

    state_path = managed_user_state_path(plan.root)
    inspection = inspect_home_manager(
        plan.root,
        standalone_root=plan.root,
        user_state_path=state_path,
        current_user=plan.username,
    )
    return plan_home_manager_adoption(
        plan.root,
        standalone_root=plan.root,
        user_state_path=state_path,
        username=plan.username,
        integration=plan.integration,
        packages=profile.packages,
        inspection=inspection,
    )


def execute_home_manager_fixture_apply_workflow(
    plan: HomeManagerAdoptionPlan,
    pre_validation: HomeManagerCandidateValidation,
    *,
    journal_root: Path,
    timeout: int = 120,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
    simulate_interruption_after_commit: bool = False,
) -> HomeManagerFixtureApplyWorkflowResult:
    """Commit and re-evaluate Home Manager files only in a marked fixture."""
    provisional = apply_home_manager_plan_in_fixture(
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
        post_plan = _installed_plan(plan)
        if post_plan.status != "no-changes" or post_plan.changes:
            raise TransactionError(
                "Installed Home Manager files still produce adoption changes"
            )
        post_validation = validate_home_manager_adoption(
            post_plan,
            flake_target=pre_validation.flake_target,
            timeout=timeout,
            runner=runner,
            which=which,
        )
    except Exception as error:
        rollback = rollback_fixture_transaction(
            plan.root,
            journal_root=journal_root,
            transaction_id=provisional.transaction_id,
            reason=f"Post-commit Home Manager validation raised an exception: {error}",
        )
        raise TransactionError(
            f"Post-commit Home Manager validation crashed; transaction "
            f"{rollback.transaction_id} was rolled back"
        ) from error

    if post_validation.status != "passed":
        reason = f"Post-commit Home Manager validation returned {post_validation.status}"
        rollback = rollback_fixture_transaction(
            plan.root,
            journal_root=journal_root,
            transaction_id=provisional.transaction_id,
            reason=reason,
            verification=post_validation,
        )
        return HomeManagerFixtureApplyWorkflowResult(
            state="rolled-back",
            transaction=rollback,
            pre_validation=pre_validation,
            post_validation=post_validation,
            failure_reason=reason,
        )

    try:
        committed = finalize_home_manager_fixture_transaction(
            plan.root,
            journal_root=journal_root,
            transaction_id=provisional.transaction_id,
            verification=post_validation,
        )
    except Exception as error:
        try:
            rollback = rollback_fixture_transaction(
                plan.root,
                journal_root=journal_root,
                transaction_id=provisional.transaction_id,
                reason=f"Home Manager finalize failed after verification: {error}",
                verification=post_validation,
            )
        except Exception as recovery_error:
            raise TransactionError(
                "Home Manager finalize failed and rollback needs manual attention: "
                f"{recovery_error}"
            ) from error
        return HomeManagerFixtureApplyWorkflowResult(
            state="rolled-back",
            transaction=rollback,
            pre_validation=pre_validation,
            post_validation=post_validation,
            failure_reason=str(error),
        )

    return HomeManagerFixtureApplyWorkflowResult(
        state="committed",
        transaction=committed,
        pre_validation=pre_validation,
        post_validation=post_validation,
    )
