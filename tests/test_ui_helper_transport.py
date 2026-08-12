import hashlib
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest

from nix_control_manager.adoption import plan_adoption
from nix_control_manager.helper_service import (
    HelperDispatcher,
    HelperTarget,
    MockPolkitAuthorizer,
)
from nix_control_manager.helper_transport import UnixJsonHelperServer
from nix_control_manager.live_read_only_backend import LiveReadOnlyHelperBackend
from nix_control_manager.ui_helper import HelperUiAdapter


@unittest.skipUnless(
    os.name == "posix" and hasattr(socket, "SO_PEERCRED"),
    "Linux SO_PEERCRED is required",
)
class HelperUiTransportTests(unittest.TestCase):
    @staticmethod
    def fake_which(name: str) -> str:
        return f"/tools/{name}"

    @staticmethod
    def passing_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "/nix/store/fake.drv\n", "")

    def test_ui_adapter_uses_real_socket_and_leaves_live_root_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            root = workspace / "etc-nixos"
            root.mkdir()
            (root / "configuration.nix").write_text(
                "{ ... }: {\n  imports = [\n  ];\n}\n", encoding="utf-8"
            )
            plan = plan_adoption(root)
            socket_path = workspace / "helper.sock"
            authorizer = MockPolkitAuthorizer()
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
                    ),
                ),
                authorizer=authorizer,
                backend=LiveReadOnlyHelperBackend(
                    runner=self.passing_runner,
                    which=self.fake_which,
                ),
            )
            before = {
                path.relative_to(root).as_posix(): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in root.rglob("*")
                if path.is_file()
            }
            stop = threading.Event()
            with UnixJsonHelperServer(socket_path, dispatcher) as helper:
                thread = threading.Thread(
                    target=helper.serve_until, args=(stop,), daemon=True
                )
                thread.start()
                try:
                    adapter = HelperUiAdapter(
                        socket_path=socket_path,
                        target_id="live",
                        config_root=root,
                    )
                    status = adapter.status()
                    result = adapter.validate_adoption()
                finally:
                    stop.set()
                    thread.join(timeout=2)

            after = {
                path.relative_to(root).as_posix(): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in root.rglob("*")
                if path.is_file()
            }
            self.assertTrue(status["available"])
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["source"], "system-helper")
            self.assertFalse(result["validationReceiptIssued"])
            self.assertEqual(authorizer.calls, [])
            self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
