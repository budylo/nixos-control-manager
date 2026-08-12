from __future__ import annotations

from .adoption import AdoptionPlan, plan_adoption
from .candidate import effective_flake_target, plan_identity
from .helper_protocol import CandidateFile, ValidatePlanPayload
from .helper_service import HelperBackendError, HelperTarget
from .transaction import require_transaction_fixture


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
    if not plan.safe_to_apply or not plan.changes:
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
