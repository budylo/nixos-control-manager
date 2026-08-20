from __future__ import annotations

import socket

from .adoption import AdoptionPlan, plan_adoption
from .candidate import effective_flake_target, plan_identity
from .helper_protocol import (
    CandidateFile,
    ValidateHomeManagerPlanPayload,
    ValidatePlanPayload,
)
from .helper_service import HelperBackendError, HelperTarget
from .home_manager_adoption import (
    HomeManagerAdoptionPlan,
    home_manager_plan_identity,
    plan_home_manager_adoption,
)
from .home_manager_inspector import inspect_home_manager
from .transaction import require_live_home_manager_root, require_transaction_fixture


def _change_mapping(plan: AdoptionPlan) -> dict[str, CandidateFile]:
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


def match_local_adoption_plan(
    target: HelperTarget,
    payload: ValidatePlanPayload,
    *,
    require_fixture: bool,
) -> AdoptionPlan:
    if require_fixture:
        if not target.fixture_only:
            raise HelperBackendError("fixture-required", "The target is not a fixture")
        require_transaction_fixture(target.configuration_root)
    elif target.fixture_only or target.apply_enabled:
        raise HelperBackendError(
            "read-only-target-required", "The target is not a read-only live target"
        )
    plan = plan_adoption(target.configuration_root)
    if not plan.safe_to_apply or (
        not plan.changes and not target.permanent_switch_enabled
    ):
        raise HelperBackendError(
            "plan-mismatch", "The configured target has no matching safe adoption plan"
        )
    fingerprint, _ = plan_identity(
        plan, effective_flake_target(plan, target.flake_target)
    )
    if fingerprint != payload.plan_fingerprint:
        raise HelperBackendError(
            "plan-mismatch", "The submitted fingerprint does not match the local plan"
        )
    local = _change_mapping(plan)
    remote = {change.relative_path: change for change in payload.changes}
    if local != remote:
        raise HelperBackendError(
            "plan-mismatch", "Submitted candidate files do not match the local plan"
        )
    return plan


def _home_manager_change_mapping(
    plan: HomeManagerAdoptionPlan,
) -> dict[str, CandidateFile]:
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


def match_local_home_manager_plan(
    target: HelperTarget,
    payload: ValidateHomeManagerPlanPayload,
) -> tuple[HomeManagerAdoptionPlan, str | None]:
    fixture_enabled = target.fixture_only and target.apply_enabled
    if not fixture_enabled and not target.home_manager_apply_enabled:
        raise HelperBackendError(
            "operation-disabled", "Home Manager helper writes are disabled"
        )
    if target.fixture_only:
        root = require_transaction_fixture(target.configuration_root)
    else:
        if target.home_manager_root is None:
            raise HelperBackendError(
                "invalid-target", "The live Home Manager root is not configured"
            )
        root = require_live_home_manager_root(target.home_manager_root)
    legacy_state = root / "user-state.local.json"
    inspection = inspect_home_manager(
        root,
        standalone_root=root,
        user_state_path=legacy_state,
        current_user=payload.username,
    )
    plan = plan_home_manager_adoption(
        root,
        standalone_root=root,
        user_state_path=legacy_state,
        username=payload.username,
        integration=payload.integration,
        packages=payload.packages,
        inspection=inspection,
    )
    if plan.status != "ready" or not plan.changes:
        raise HelperBackendError(
            "plan-mismatch", "The configured target has no matching Home Manager plan"
        )
    effective_target = target.flake_target
    if (
        plan.integration == "nixos-module"
        and (plan.root / "flake.nix").is_file()
        and effective_target is None
    ):
        effective_target = socket.gethostname()
    fingerprint, _ = home_manager_plan_identity(plan, effective_target)
    if fingerprint != payload.plan_fingerprint:
        raise HelperBackendError(
            "plan-mismatch", "The submitted fingerprint does not match the local Home Manager plan"
        )
    local = _home_manager_change_mapping(plan)
    remote = {change.relative_path: change for change in payload.changes}
    if local != remote:
        raise HelperBackendError(
            "plan-mismatch",
            "Submitted Home Manager candidate files do not match the local plan",
        )
    return plan, effective_target
