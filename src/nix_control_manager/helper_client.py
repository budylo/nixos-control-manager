from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import socket
import sys
from typing import Any

from .adoption import plan_adoption
from .candidate import effective_flake_target, plan_identity
from .home_manager_adoption import (
    home_manager_plan_identity,
    plan_home_manager_adoption,
)
from .home_manager_inspector import inspect_home_manager
from .helper_transport import send_unix_request
from .managed_plan import managed_plan_identity, plan_managed_state
from .model import ManagedState


DEFAULT_SOCKET = Path("/run/nix-control-manager/helper.sock")


def _request(operation: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "requestId": f"client-{secrets.token_hex(8)}",
        "operation": operation,
        "payload": payload,
    }


def build_validate_request(
    config_root: Path, *, target_id: str, flake_target: str | None
) -> dict[str, Any]:
    plan = plan_adoption(config_root.expanduser().resolve())
    if not plan.safe_to_apply or not plan.changes:
        raise ValueError(f"No safe adoption changes are available: {plan.status}")
    fingerprint, _ = plan_identity(plan, effective_flake_target(plan, flake_target))
    return _request(
        "validate-plan",
        {
            "targetId": target_id,
            "planFingerprint": fingerprint,
            "changes": [
                {
                    "relativePath": change.relative_path,
                    "action": change.action,
                    "previousSha256": change.previous_sha256,
                    "candidateSha256": change.candidate_sha256,
                    "candidate": change.candidate,
                }
                for change in plan.changes
            ],
        },
    )


def build_activation_preview_request(
    config_root: Path,
    *,
    target_id: str,
    flake_target: str | None,
    system_path: str,
    expected_fingerprint: str,
) -> dict[str, Any]:
    request = build_validate_request(
        config_root, target_id=target_id, flake_target=flake_target
    )
    if request["payload"]["planFingerprint"] != expected_fingerprint:
        raise ValueError("The adoption plan changed after the candidate build")
    request["operation"] = "preview-activation"
    request["payload"]["systemPath"] = system_path
    return request


def build_home_manager_validate_request(
    config_root: Path,
    *,
    target_id: str,
    username: str,
    integration: str,
    packages: tuple[str, ...],
    flake_target: str | None,
) -> dict[str, Any]:
    root = config_root.expanduser().resolve()
    legacy_state = root / "user-state.local.json"
    inspection = inspect_home_manager(
        root,
        standalone_root=root,
        user_state_path=legacy_state,
        current_user=username,
    )
    plan = plan_home_manager_adoption(
        root,
        standalone_root=root,
        user_state_path=legacy_state,
        username=username,
        integration=integration,
        packages=packages,
        inspection=inspection,
    )
    if plan.status != "ready" or not plan.changes:
        raise ValueError(f"No safe Home Manager adoption changes are available: {plan.status}")
    effective_target = flake_target
    if integration == "nixos-module" and (root / "flake.nix").is_file():
        effective_target = effective_target or socket.gethostname()
    fingerprint, _ = home_manager_plan_identity(plan, effective_target)
    return _request(
        "validate-home-manager-plan",
        {
            "targetId": target_id,
            "planFingerprint": fingerprint,
            "username": username,
            "integration": integration,
            "packages": list(packages),
            "changes": [
                {
                    "relativePath": change.relative_path,
                    "action": change.action,
                    "previousSha256": change.previous_sha256,
                    "candidateSha256": change.candidate_sha256,
                    "candidate": change.candidate,
                }
                for change in plan.changes
            ],
        },
    )


def build_managed_validate_request(
    config_root: Path,
    state: ManagedState,
    *,
    target_id: str,
    flake_target: str | None,
) -> dict[str, Any]:
    plan = plan_managed_state(
        config_root.expanduser().resolve(), state, flake_target=flake_target
    )
    if not plan.changes:
        raise ValueError("The managed state already matches the generated module")
    fingerprint, _ = managed_plan_identity(plan)
    return _request(
        "validate-managed-plan",
        {
            "targetId": target_id,
            "planFingerprint": fingerprint,
            "changes": [
                {
                    "relativePath": change.relative_path,
                    "action": change.action,
                    "previousSha256": change.previous_sha256,
                    "candidateSha256": change.candidate_sha256,
                    "candidate": change.candidate,
                }
                for change in plan.changes
            ],
        },
    )


def build_test_activation_request(
    *, target_id: str, system_path: str, plan_fingerprint: str, test_receipt: str
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "requestId": f"client-{secrets.token_hex(8)}",
        "operation": "test-activation",
        "payload": {
            "targetId": target_id,
            "planFingerprint": plan_fingerprint,
            "systemPath": system_path,
            "testReceipt": test_receipt,
        },
    }


def build_test_recovery_request(*, target_id: str, session_id: str) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "requestId": f"client-{secrets.token_hex(8)}",
        "operation": "recover-test-activation",
        "payload": {"targetId": target_id, "sessionId": session_id},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ncm-helper-client",
        description="Typed diagnostic client for the Nix Control Manager helper",
    )
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--timeout", type=float, default=300.0)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    subparsers.add_parser("capabilities")

    validate = subparsers.add_parser("validate-plan")
    validate.add_argument("--target", required=True)
    validate.add_argument("--config-root", required=True, type=Path)
    validate.add_argument("--flake-target")

    apply = subparsers.add_parser("apply-plan")
    apply.add_argument("--target", required=True)
    apply.add_argument("--plan-fingerprint", required=True)
    apply.add_argument("--receipt", required=True)

    recover = subparsers.add_parser("recover-transaction")
    recover.add_argument("--target", required=True)
    recover.add_argument("--transaction-id", required=True)

    validate_home = subparsers.add_parser("validate-home-manager-plan")
    validate_home.add_argument("--target", required=True)
    validate_home.add_argument("--config-root", required=True, type=Path)
    validate_home.add_argument("--user", required=True)
    validate_home.add_argument(
        "--integration", required=True, choices=("nixos-module", "standalone")
    )
    validate_home.add_argument("--package", action="append", default=[])
    validate_home.add_argument("--flake-target")

    apply_home = subparsers.add_parser("apply-home-manager-plan")
    apply_home.add_argument("--target", required=True)
    apply_home.add_argument("--plan-fingerprint", required=True)
    apply_home.add_argument("--receipt", required=True)

    recover_home = subparsers.add_parser("recover-home-manager-transaction")
    recover_home.add_argument("--target", required=True)
    recover_home.add_argument("--transaction-id", required=True)

    validate_managed = subparsers.add_parser("validate-managed-plan")
    validate_managed.add_argument("--target", required=True)
    validate_managed.add_argument("--config-root", required=True, type=Path)
    validate_managed.add_argument("--state", required=True, type=Path)
    validate_managed.add_argument("--flake-target")

    apply_managed = subparsers.add_parser("apply-managed-plan")
    apply_managed.add_argument("--target", required=True)
    apply_managed.add_argument("--plan-fingerprint", required=True)
    apply_managed.add_argument("--receipt", required=True)

    recover_managed = subparsers.add_parser("recover-managed-transaction")
    recover_managed.add_argument("--target", required=True)
    recover_managed.add_argument("--transaction-id", required=True)

    activation = subparsers.add_parser("preview-activation")
    activation.add_argument("--target", required=True)
    activation.add_argument("--config-root", required=True, type=Path)
    activation.add_argument("--flake-target")
    activation.add_argument("--system-path", required=True)
    activation.add_argument("--plan-fingerprint", required=True)

    test_activation = subparsers.add_parser("test-activation")
    test_activation.add_argument("--target", required=True)
    test_activation.add_argument("--system-path", required=True)
    test_activation.add_argument("--plan-fingerprint", required=True)
    test_activation.add_argument("--receipt", required=True)

    recover_test = subparsers.add_parser("recover-test-activation")
    recover_test.add_argument("--target", required=True)
    recover_test.add_argument("--session-id", required=True)
    return parser


def run(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.timeout <= 0 or arguments.timeout > 900:
        raise ValueError("timeout must be between 0 and 900 seconds")
    if arguments.operation == "capabilities":
        request = _request("capabilities", {})
    elif arguments.operation == "validate-plan":
        request = build_validate_request(
            arguments.config_root,
            target_id=arguments.target,
            flake_target=arguments.flake_target,
        )
    elif arguments.operation == "apply-plan":
        request = _request(
            "apply-validated-plan",
            {
                "targetId": arguments.target,
                "planFingerprint": arguments.plan_fingerprint,
                "validationReceipt": arguments.receipt,
            },
        )
    elif arguments.operation == "recover-transaction":
        request = _request(
            "recover-transaction",
            {
                "targetId": arguments.target,
                "transactionId": arguments.transaction_id,
            },
        )
    elif arguments.operation == "validate-home-manager-plan":
        request = build_home_manager_validate_request(
            arguments.config_root,
            target_id=arguments.target,
            username=arguments.user,
            integration=arguments.integration,
            packages=tuple(arguments.package),
            flake_target=arguments.flake_target,
        )
    elif arguments.operation == "apply-home-manager-plan":
        request = _request(
            "apply-validated-home-manager-plan",
            {
                "targetId": arguments.target,
                "planFingerprint": arguments.plan_fingerprint,
                "validationReceipt": arguments.receipt,
            },
        )
    elif arguments.operation == "recover-home-manager-transaction":
        request = _request(
            "recover-home-manager-transaction",
            {
                "targetId": arguments.target,
                "transactionId": arguments.transaction_id,
            },
        )
    elif arguments.operation == "validate-managed-plan":
        raw_state = json.loads(arguments.state.read_text(encoding="utf-8"))
        request = build_managed_validate_request(
            arguments.config_root,
            ManagedState.from_mapping(raw_state),
            target_id=arguments.target,
            flake_target=arguments.flake_target,
        )
    elif arguments.operation == "apply-managed-plan":
        request = _request(
            "apply-validated-managed-plan",
            {
                "targetId": arguments.target,
                "planFingerprint": arguments.plan_fingerprint,
                "validationReceipt": arguments.receipt,
            },
        )
    elif arguments.operation == "recover-managed-transaction":
        request = _request(
            "recover-managed-transaction",
            {
                "targetId": arguments.target,
                "transactionId": arguments.transaction_id,
            },
        )
    elif arguments.operation == "preview-activation":
        request = build_activation_preview_request(
            arguments.config_root,
            target_id=arguments.target,
            flake_target=arguments.flake_target,
            system_path=arguments.system_path,
            expected_fingerprint=arguments.plan_fingerprint,
        )
    elif arguments.operation == "test-activation":
        request = build_test_activation_request(
            target_id=arguments.target,
            system_path=arguments.system_path,
            plan_fingerprint=arguments.plan_fingerprint,
            test_receipt=arguments.receipt,
        )
    elif arguments.operation == "recover-test-activation":
        request = build_test_recovery_request(
            target_id=arguments.target,
            session_id=arguments.session_id,
        )
    else:
        raise AssertionError(f"Unhandled operation: {arguments.operation}")
    return send_unix_request(
        arguments.socket.expanduser().resolve(),
        request,
        timeout=arguments.timeout,
    )


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        response = run(arguments)
    except (OSError, TimeoutError, ValueError) as error:
        print(f"ncm-helper-client: {error}", file=sys.stderr)
        return 1
    print(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if response.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
