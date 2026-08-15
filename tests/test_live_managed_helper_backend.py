import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from nix_control_manager.helper_client import build_managed_validate_request
from nix_control_manager.helper_service import (
    MANAGED_APPLY_ACTION_ID,
    HelperDispatcher,
    HelperTarget,
    MockPolkitAuthorizer,
)
from nix_control_manager.managed_helper_backend import LiveManagedHelperBackend
from nix_control_manager.model import ManagedState
from nix_control_manager.nix_generator import generate_module
from nix_control_manager.storage import serialize_state


class LiveManagedHelperBackendTests(unittest.TestCase):
    def test_exact_validated_plan_commits_without_activation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "etc" / "nixos"
            managed = root / "ncm"
            managed.mkdir(parents=True)
            configuration = root / "configuration.nix"
            configuration.write_text(
                "{ ... }: { imports = [ ./ncm ]; }\n", encoding="utf-8"
            )
            initial = ManagedState.empty()
            (managed / "state.json").write_text(
                serialize_state(initial), encoding="utf-8"
            )
            (managed / "packages.nix").write_text(
                generate_module(initial), encoding="utf-8"
            )
            configuration_before = configuration.read_bytes()
            journal = base / "managed-journal"
            target = HelperTarget(
                target_id="managed",
                configuration_root=root,
                allowed_relative_paths=frozenset(
                    {"ncm/state.json", "ncm/packages.nix"}
                ),
                fixture_only=False,
                apply_enabled=False,
                managed_write_enabled=True,
                managed_journal_root=journal,
            )

            def runner(command, **kwargs):
                return subprocess.CompletedProcess(command, 0, "/nix/store/test.drv\n", "")

            authorizer = MockPolkitAuthorizer(
                allowed={(1000, MANAGED_APPLY_ACTION_ID)}
            )
            dispatcher = HelperDispatcher(
                targets=(target,),
                authorizer=authorizer,
                backend=LiveManagedHelperBackend(
                    runner=runner,
                    which=lambda name: (
                        f"/bin/{name}" if name == "nix-instantiate" else None
                    ),
                ),
            )
            state = ManagedState.from_mapping(
                {"schemaVersion": 1, "packages": ["git"], "options": {}}
            )
            request = build_managed_validate_request(
                root, state, target_id="managed", flake_target=None
            )
            validated = dispatcher.handle(request, peer_uid=1000)
            self.assertEqual(validated["status"], "ok")
            result = validated["result"]
            applied = dispatcher.handle(
                {
                    "schemaVersion": 1,
                    "requestId": "managed-apply1",
                    "operation": "apply-validated-managed-plan",
                    "payload": {
                        "targetId": "managed",
                        "planFingerprint": result["planFingerprint"],
                        "validationReceipt": result["validationReceipt"],
                    },
                },
                peer_uid=1000,
            )
            self.assertEqual(applied["status"], "ok", applied)
            self.assertEqual(applied["result"]["state"], "committed")
            self.assertEqual(applied["result"]["filesWritten"], 2)
            self.assertFalse(applied["result"]["activationEnabled"])
            self.assertFalse(applied["result"]["switchEnabled"])
            self.assertEqual(configuration.read_bytes(), configuration_before)
            self.assertEqual(
                json.loads((managed / "state.json").read_text(encoding="utf-8"))["packages"],
                ["git"],
            )
            manifests = list(journal.glob("*/manifest.json"))
            self.assertEqual(len(manifests), 1)
            manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
            self.assertEqual(manifest["transactionKind"], "managed-state")
            self.assertEqual(
                {change["path"] for change in manifest["changes"]},
                {"ncm/state.json", "ncm/packages.nix"},
            )


if __name__ == "__main__":
    unittest.main()
