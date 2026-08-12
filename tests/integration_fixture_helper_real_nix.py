"""Manual Linux integration: real Nix evaluation through the fixture helper socket.

This script copies the source configuration to a temporary directory. It never
marks or writes the source tree and the transaction backend still refuses
``/etc/nixos`` as a direct target.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
import threading

from nix_control_manager.adoption import plan_adoption
from nix_control_manager.candidate import plan_identity
from nix_control_manager.fixture_helper_backend import FixtureWorkflowHelperBackend
from nix_control_manager.helper_service import (
    APPLY_ACTION_ID,
    HelperDispatcher,
    HelperTarget,
    MockPolkitAuthorizer,
)
from nix_control_manager.helper_transport import UnixJsonHelperServer, send_unix_request
from nix_control_manager.transaction import initialize_transaction_fixture


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


def run(source: Path) -> dict:
    if os.name != "posix" or not hasattr(socket, "SO_PEERCRED"):
        raise RuntimeError("Linux SO_PEERCRED is required")
    source = source.expanduser().resolve()
    if not source.is_dir():
        raise RuntimeError(f"Configuration source is not a directory: {source}")
    before = _tree_digests(source)

    with tempfile.TemporaryDirectory(prefix="ncm-real-helper-") as temporary:
        workspace = Path(temporary)
        fixture = workspace / "configuration"
        journal = workspace / "journals"
        socket_path = workspace / "helper.sock"
        shutil.copytree(source, fixture, symlinks=True)
        initialize_transaction_fixture(fixture)

        plan = plan_adoption(fixture)
        if not plan.safe_to_apply or not plan.changes:
            raise RuntimeError(
                f"Copied configuration has no safe adoption changes: {plan.status}"
            )
        fingerprint, _ = plan_identity(plan, None)
        uid = os.getuid()
        authorizer = MockPolkitAuthorizer(allowed={(uid, APPLY_ACTION_ID)})
        dispatcher = HelperDispatcher(
            targets=(
                HelperTarget(
                    target_id="fixture",
                    configuration_root=fixture,
                    journal_root=journal,
                    allowed_relative_paths=frozenset(
                        change.relative_path for change in plan.changes
                    ),
                ),
            ),
            authorizer=authorizer,
            backend=FixtureWorkflowHelperBackend(),
        )

        stop = threading.Event()
        with UnixJsonHelperServer(socket_path, dispatcher) as server:
            thread = threading.Thread(
                target=server.serve_until, args=(stop,), daemon=True
            )
            thread.start()
            try:
                validated = send_unix_request(
                    socket_path,
                    _request(
                        "validate-plan",
                        {
                            "targetId": "fixture",
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
                        "real-nix-validate",
                    ),
                    timeout=180,
                )
                if validated["status"] != "ok":
                    raise RuntimeError(f"Helper validation failed: {validated}")
                applied = send_unix_request(
                    socket_path,
                    _request(
                        "apply-validated-plan",
                        {
                            "targetId": "fixture",
                            "planFingerprint": fingerprint,
                            "validationReceipt": validated["result"][
                                "validationReceipt"
                            ],
                        },
                        "real-nix-apply",
                    ),
                    timeout=180,
                )
            finally:
                stop.set()
                thread.join(timeout=2)

        if applied["status"] != "ok" or applied["result"]["state"] != "committed":
            raise RuntimeError(f"Helper apply did not commit: {applied}")
        if plan_adoption(fixture).status != "no-changes":
            raise RuntimeError("Committed fixture still proposes adoption changes")
        after = _tree_digests(source)
        if before != after:
            raise RuntimeError("The read-only source configuration changed")
        return {
            "source": str(source),
            "sourceFilesUnchanged": len(before),
            "transportPeerUid": authorizer.calls[0][1],
            "validationChecks": len(
                validated["result"]["validation"].get("checks", [])
            ),
            "transactionState": applied["result"]["state"],
            "filesWrittenToTemporaryFixture": applied["result"]["filesWritten"],
            "activationEnabled": applied["result"]["activationEnabled"],
            "temporaryWorkspaceRemoved": True,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", type=Path, default=Path("/etc/nixos"))
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.source), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
