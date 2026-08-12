"""Run the UI against an in-process live-read-only helper for manual QA."""

from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import threading

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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-root", type=Path, default=Path("/etc/nixos"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--flake-target")
    arguments = parser.parse_args()
    root = arguments.config_root.expanduser().resolve()
    plan = plan_adoption(root)
    if not plan.safe_to_apply or not plan.changes:
        raise RuntimeError(f"No safe live adoption changes: {plan.status}")

    with tempfile.TemporaryDirectory(prefix="ncm-live-ui-manual-") as temporary:
        workspace = Path(temporary)
        socket_path = workspace / "helper.sock"
        stop = threading.Event()
        dispatcher = HelperDispatcher(
            targets=(
                HelperTarget(
                    target_id="live",
                    configuration_root=root,
                    journal_root=None,
                    allowed_relative_paths=frozenset(
                        change.relative_path for change in plan.changes
                    ),
                    fixture_only=False,
                    apply_enabled=False,
                    flake_target=arguments.flake_target,
                ),
            ),
            authorizer=MockPolkitAuthorizer(),
            backend=LiveReadOnlyHelperBackend(),
        )
        with UnixJsonHelperServer(socket_path, dispatcher) as helper:
            helper_thread = threading.Thread(
                target=helper.serve_until, args=(stop,), daemon=True
            )
            helper_thread.start()
            web = NcmServer(
                ("127.0.0.1", arguments.port),
                RequestHandler,
                state_path=workspace / "state.json",
                output_path=workspace / "managed.nix",
                config_root=root,
                flake_target=arguments.flake_target,
                validation_timeout=180,
                helper_adapter=HelperUiAdapter(
                    socket_path=socket_path,
                    target_id="live",
                    config_root=root,
                    flake_target=arguments.flake_target,
                    timeout=180,
                ),
            )
            print(
                f"Manual live-read-only UI: http://127.0.0.1:{web.server_port}/",
                flush=True,
            )
            try:
                web.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                web.server_close()
                stop.set()
                helper_thread.join(timeout=2)


if __name__ == "__main__":
    main()
