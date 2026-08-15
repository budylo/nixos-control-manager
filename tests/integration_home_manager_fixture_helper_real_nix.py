"""Run the Home Manager fixture helper protocol over a real Linux socket."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import threading

from nix_control_manager.fixture_helper_backend import FixtureWorkflowHelperBackend
from nix_control_manager.helper_service import (
    HOME_MANAGER_APPLY_ACTION_ID,
    HelperDispatcher,
    HelperTarget,
    MockPolkitAuthorizer,
)
from nix_control_manager.helper_transport import UnixJsonHelperServer, send_unix_request
from nix_control_manager.home_manager_adoption import (
    plan_home_manager_adoption,
    validate_home_manager_adoption,
)
from nix_control_manager.transaction import initialize_transaction_fixture


def _request(operation: str, payload: dict, request_id: str) -> dict:
    return {
        "schemaVersion": 1,
        "requestId": request_id,
        "operation": operation,
        "payload": payload,
    }


def _changes(plan) -> list[dict]:
    return [
        {
            "relativePath": change.relative_path,
            "action": change.action,
            "previousSha256": change.previous_sha256,
            "candidateSha256": change.candidate_sha256,
            "candidate": change.candidate,
        }
        for change in plan.changes
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "posix" or not hasattr(socket, "SO_PEERCRED"):
        raise RuntimeError("Linux SO_PEERCRED is required")

    initialize_transaction_fixture(args.root)
    (args.root / "home.nix").write_text(
        '{ pkgs, ... }:\n{\n  home.username = "fixture-user";\n}\n',
        encoding="utf-8",
    )
    (args.root / "flake.nix").write_text(
        "{\n"
        "  outputs = { ... }:\n"
        "    let\n"
        '      pkgs = { git = "git-package-sentinel"; };\n'
        "      home = import ./home.nix { inherit pkgs; config = { }; };\n"
        "      managed = import (builtins.head home.imports) { inherit pkgs; };\n"
        "      activationPackage = assert managed.home.packages == [ pkgs.git ]; {\n"
        '        drvPath = "/nix/store/ncm-home-helper-fixture.drv";\n'
        "      };\n"
        "    in { homeConfigurations.fixture-user = { inherit activationPackage; }; };\n"
        "}\n",
        encoding="utf-8",
    )
    legacy_state = args.root / "user-state.local.json"
    plan = plan_home_manager_adoption(
        args.root,
        standalone_root=args.root,
        user_state_path=legacy_state,
        username="fixture-user",
        integration="standalone",
        packages=("git",),
    )
    validation = validate_home_manager_adoption(plan, timeout=120)
    if validation.status != "passed" or validation.plan_fingerprint is None:
        raise RuntimeError(f"Initial validation failed: {validation.to_mapping()}")

    uid = os.getuid()
    authorizer = MockPolkitAuthorizer(
        allowed={(uid, HOME_MANAGER_APPLY_ACTION_ID)}
    )
    dispatcher = HelperDispatcher(
        targets=(
            HelperTarget(
                target_id="home-fixture",
                configuration_root=args.root,
                journal_root=args.journal,
                allowed_relative_paths=frozenset(
                    change.relative_path for change in plan.changes
                ),
            ),
        ),
        authorizer=authorizer,
        backend=FixtureWorkflowHelperBackend(timeout=120),
    )
    stop = threading.Event()
    with UnixJsonHelperServer(args.socket, dispatcher) as server:
        thread = threading.Thread(
            target=server.serve_until, args=(stop,), daemon=True
        )
        thread.start()
        try:
            validated = send_unix_request(
                args.socket,
                _request(
                    "validate-home-manager-plan",
                    {
                        "targetId": "home-fixture",
                        "planFingerprint": validation.plan_fingerprint,
                        "username": "fixture-user",
                        "integration": "standalone",
                        "packages": ["git"],
                        "changes": _changes(plan),
                    },
                    "home-real-valid",
                ),
                timeout=180,
            )
            if validated["status"] != "ok":
                raise RuntimeError(f"Helper validation failed: {validated}")
            applied = send_unix_request(
                args.socket,
                _request(
                    "apply-validated-home-manager-plan",
                    {
                        "targetId": "home-fixture",
                        "planFingerprint": validation.plan_fingerprint,
                        "validationReceipt": validated["result"][
                            "validationReceipt"
                        ],
                    },
                    "home-real-apply",
                ),
                timeout=180,
            )
        finally:
            stop.set()
            thread.join(timeout=2)

    if applied["status"] != "ok" or applied["result"]["state"] != "committed":
        raise RuntimeError(f"Helper apply did not commit: {applied}")
    canonical = args.root / "ncm" / "user-state.json"
    state = json.loads(canonical.read_text(encoding="utf-8"))
    if state["users"]["fixture-user"]["packages"] != ["git"]:
        raise RuntimeError("Canonical state does not match the validated selection")
    if legacy_state.exists():
        raise RuntimeError("The helper unexpectedly wrote legacy user-state")
    if authorizer.calls[0][1] != uid:
        raise RuntimeError("The helper did not authorize the kernel-derived peer UID")

    print(json.dumps(applied["result"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
