"""Manual Linux integration: local web API -> Unix helper -> real Nix evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from nix_control_manager.adoption import plan_adoption
from nix_control_manager.helper_service import (
    HelperDispatcher,
    HelperTarget,
    MockPolkitAuthorizer,
)
from nix_control_manager.helper_transport import UnixJsonHelperServer
from nix_control_manager.live_read_only_backend import LiveReadOnlyHelperBackend
from nix_control_manager.server import NcmServer, RequestHandler
from nix_control_manager.ui_helper import HelperUiAdapter


def _tree_digests(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _json_request(url: str, *, method: str = "GET", token: str | None = None):
    headers = {"X-NCM-Token": token} if token else {}
    request = Request(url, headers=headers, method=method)
    with urlopen(request, timeout=300) as response:
        return json.loads(response.read())


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

    with tempfile.TemporaryDirectory(prefix="ncm-live-ui-") as temporary:
        workspace = Path(temporary)
        socket_path = workspace / "helper.sock"
        authorizer = MockPolkitAuthorizer()
        dispatcher = HelperDispatcher(
            targets=(
                HelperTarget(
                    target_id="live",
                    configuration_root=source,
                    journal_root=None,
                    allowed_relative_paths=frozenset(
                        change.relative_path for change in plan.changes
                    ),
                    fixture_only=False,
                    apply_enabled=False,
                    flake_target=flake_target,
                ),
            ),
            authorizer=authorizer,
            backend=LiveReadOnlyHelperBackend(),
        )
        helper_stop = threading.Event()
        with UnixJsonHelperServer(socket_path, dispatcher) as helper:
            helper_thread = threading.Thread(
                target=helper.serve_until, args=(helper_stop,), daemon=True
            )
            helper_thread.start()
            web = NcmServer(
                ("127.0.0.1", 0),
                RequestHandler,
                state_path=workspace / "state.json",
                output_path=workspace / "managed.nix",
                config_root=source,
                flake_target=flake_target,
                validation_timeout=180,
                helper_adapter=HelperUiAdapter(
                    socket_path=socket_path,
                    target_id="live",
                    config_root=source,
                    flake_target=flake_target,
                    timeout=180,
                ),
            )
            web_thread = threading.Thread(target=web.serve_forever, daemon=True)
            web_thread.start()
            base_url = f"http://127.0.0.1:{web.server_port}"
            try:
                token = _json_request(base_url + "/api/config")["token"]
                helper_status = _json_request(base_url + "/api/helper")
                try:
                    _json_request(
                        base_url + "/api/helper/validate-adoption", method="POST"
                    )
                    raise RuntimeError("Helper validation accepted a request without token")
                except HTTPError as error:
                    if error.code != 403:
                        raise
                validation = _json_request(
                    base_url + "/api/helper/validate-adoption",
                    method="POST",
                    token=token,
                )
            finally:
                web.shutdown()
                web.server_close()
                web_thread.join(timeout=2)
                helper_stop.set()
                helper_thread.join(timeout=2)

    after = _tree_digests(source)
    if before != after:
        raise RuntimeError("The live configuration changed through the UI workflow")
    if not helper_status["available"] or helper_status["applyEnabled"]:
        raise RuntimeError(f"Unsafe helper status reached the UI: {helper_status}")
    if validation["status"] != "passed":
        raise RuntimeError(f"UI helper validation failed: {validation}")
    if validation["validationReceiptIssued"]:
        raise RuntimeError("UI workflow received a forbidden validation receipt")
    if authorizer.calls:
        raise RuntimeError("Read-only UI workflow unexpectedly reached Polkit")
    return {
        "workflow": "local-web-api -> unix-helper -> real-nix",
        "source": str(source),
        "sourceFilesUnchanged": len(before),
        "helperAvailable": True,
        "validationChecks": len(validation["checks"]),
        "validationReceiptIssued": False,
        "applyEnabled": False,
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
