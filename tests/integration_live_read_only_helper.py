"""Manual Linux integration: validate /etc/nixos directly without write authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import threading

from nix_control_manager.adoption import plan_adoption
from nix_control_manager.candidate import plan_identity
from nix_control_manager.helper_service import (
    HelperDispatcher,
    HelperTarget,
    MockPolkitAuthorizer,
)
from nix_control_manager.helper_transport import UnixJsonHelperServer, send_unix_request
from nix_control_manager.live_read_only_backend import LiveReadOnlyHelperBackend


def _tree_digests(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _request(operation: str, payload: dict, request_id: str) -> dict:
    return {
        "schemaVersion": 1,
        "requestId": request_id,
        "operation": operation,
        "payload": payload,
    }


def run(source: Path, *, flake_target: str | None = None) -> dict:
    if os.name != "posix" or not hasattr(socket, "SO_PEERCRED"):
        raise RuntimeError("Linux SO_PEERCRED is required")
    source = source.expanduser().resolve()
    if not source.is_dir():
        raise RuntimeError(f"Configuration source is not a directory: {source}")
    before = _tree_digests(source)
    plan = plan_adoption(source)
    if not plan.safe_to_apply or not plan.changes:
        raise RuntimeError(f"No safe live adoption changes: {plan.status}")
    fingerprint, _ = plan_identity(plan, flake_target)
    authorizer = MockPolkitAuthorizer()
    target = HelperTarget(
        target_id="live",
        configuration_root=source,
        journal_root=None,
        allowed_relative_paths=frozenset(
            change.relative_path for change in plan.changes
        ),
        fixture_only=False,
        apply_enabled=False,
        flake_target=flake_target,
    )
    dispatcher = HelperDispatcher(
        targets=(target,),
        authorizer=authorizer,
        backend=LiveReadOnlyHelperBackend(),
    )

    with tempfile.TemporaryDirectory(prefix="ncm-live-read-only-") as temporary:
        socket_path = Path(temporary) / "helper.sock"
        stop = threading.Event()
        with UnixJsonHelperServer(socket_path, dispatcher) as server:
            thread = threading.Thread(
                target=server.serve_until, args=(stop,), daemon=True
            )
            thread.start()
            try:
                capabilities = send_unix_request(
                    socket_path,
                    _request("capabilities", {}, "live-real-capabilities"),
                    timeout=180,
                )
                validated = send_unix_request(
                    socket_path,
                    _request(
                        "validate-plan",
                        {
                            "targetId": "live",
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
                        "live-real-validate",
                    ),
                    timeout=180,
                )
                apply_attempt = send_unix_request(
                    socket_path,
                    _request(
                        "apply-validated-plan",
                        {
                            "targetId": "live",
                            "planFingerprint": fingerprint,
                            "validationReceipt": "A" * 32,
                        },
                        "live-real-apply",
                    ),
                    timeout=180,
                )
                recovery_attempt = send_unix_request(
                    socket_path,
                    _request(
                        "recover-transaction",
                        {"targetId": "live", "transactionId": "a" * 24},
                        "live-real-recover",
                    ),
                    timeout=180,
                )
            finally:
                stop.set()
                thread.join(timeout=2)

    if capabilities["status"] != "ok":
        raise RuntimeError(f"Capabilities failed: {capabilities}")
    advertised = capabilities["result"]["targets"][0]
    if not advertised["readOnly"] or advertised["applyEnabled"]:
        raise RuntimeError(f"Unsafe live capabilities: {advertised}")
    if validated["status"] != "ok":
        raise RuntimeError(f"Live validation failed: {validated}")
    if "validationReceipt" in validated["result"]:
        raise RuntimeError("Read-only validation unexpectedly issued a receipt")
    for label, response in (
        ("apply", apply_attempt),
        ("recovery", recovery_attempt),
    ):
        if response.get("error", {}).get("code") != "operation-disabled":
            raise RuntimeError(f"Live {label} was not disabled: {response}")
    after = _tree_digests(source)
    if before != after:
        raise RuntimeError("The live configuration changed during validation")
    if authorizer.calls:
        raise RuntimeError("Read-only operations unexpectedly reached Polkit")
    return {
        "source": str(source),
        "sourceFilesUnchanged": len(before),
        "validationChecks": len(validated["result"]["validation"]["checks"]),
        "validationReceiptIssued": False,
        "applyError": apply_attempt["error"]["code"],
        "recoveryError": recovery_attempt["error"]["code"],
        "polkitCalls": 0,
        "activationEnabled": False,
        "temporaryWorkspaceRemoved": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", type=Path, default=Path("/etc/nixos"))
    parser.add_argument("--flake-target")
    arguments = parser.parse_args()
    print(
        json.dumps(
            run(arguments.source, flake_target=arguments.flake_target),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
