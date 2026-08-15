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
    apply_home_manager_plan_live,
    finalize_home_manager_fixture_transaction,
    finalize_home_manager_live_transaction,
    rollback_home_manager_live_transaction,
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
    fixture_only: bool = True

    def to_mapping(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "transaction": self.transaction.to_mapping(),
            "preValidation": self.pre_validation.to_mapping(),
            "postValidation": (
                self.post_validation.to_mapping() if self.post_validation else None
            ),
            "failureReason": self.failure_reason,
            "fixtureOnly": self.fixture_only,
            "writeEnabled": True,
            "liveWriteEnabled": not self.fixture_only,
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


def _execute_home_manager_apply_workflow(
    plan: HomeManagerAdoptionPlan,
    pre_validation: HomeManagerCandidateValidation,
    *,
    journal_root: Path,
    timeout: int = 120,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
    simulate_interruption_after_commit: bool = False,
    fixture_only: bool,
) -> HomeManagerFixtureApplyWorkflowResult:
    apply_plan = (
        apply_home_manager_plan_in_fixture
        if fixture_only
        else apply_home_manager_plan_live
    )
    rollback_transaction = (
        rollback_fixture_transaction
        if fixture_only
        else rollback_home_manager_live_transaction
    )
    finalize_transaction = (
        finalize_home_manager_fixture_transaction
        if fixture_only
        else finalize_home_manager_live_transaction
    )
    provisional = apply_plan(
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
        rollback = rollback_transaction(
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
        rollback = rollback_transaction(
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
            fixture_only=fixture_only,
        )

    try:
        committed = finalize_transaction(
            plan.root,
            journal_root=journal_root,
            transaction_id=provisional.transaction_id,
            verification=post_validation,
        )
    except Exception as error:
        try:
            rollback = rollback_transaction(
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
            fixture_only=fixture_only,
        )

    return HomeManagerFixtureApplyWorkflowResult(
        state="committed",
        transaction=committed,
        pre_validation=pre_validation,
        post_validation=post_validation,
        fixture_only=fixture_only,
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
    return _execute_home_manager_apply_workflow(
        plan,
        pre_validation,
        journal_root=journal_root,
        timeout=timeout,
        runner=runner,
        which=which,
        simulate_interruption_after_commit=simulate_interruption_after_commit,
        fixture_only=True,
    )


def execute_home_manager_live_apply_workflow(
    plan: HomeManagerAdoptionPlan,
    pre_validation: HomeManagerCandidateValidation,
    *,
    journal_root: Path,
    timeout: int = 120,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
    simulate_interruption_after_commit: bool = False,
) -> HomeManagerFixtureApplyWorkflowResult:
    """Persist Home Manager source files atomically without activation."""
    return _execute_home_manager_apply_workflow(
        plan,
        pre_validation,
        journal_root=journal_root,
        timeout=timeout,
        runner=runner,
        which=which,
        simulate_interruption_after_commit=simulate_interruption_after_commit,
        fixture_only=False,
    )
