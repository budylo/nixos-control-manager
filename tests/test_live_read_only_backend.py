import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from nix_control_manager.adoption import plan_adoption
from nix_control_manager.candidate import validate_adoption
from nix_control_manager.helper_service import (
    HelperDispatcher,
    HelperTarget,
    MockPolkitAuthorizer,
)
from nix_control_manager.helper_client import build_validate_request
from nix_control_manager.live_read_only_backend import LiveReadOnlyHelperBackend


class LiveReadOnlyHelperBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "live-configuration"
        self.root.mkdir()
        (self.root / "configuration.nix").write_text(
            "{ ... }:\n\n{\n  imports = [\n"
            "    ./hardware-configuration.nix\n  ];\n}\n",
            encoding="utf-8",
        )
        (self.root / "hardware-configuration.nix").write_text(
            "{ ... }: { }\n", encoding="utf-8"
        )
        self.target = HelperTarget(
            target_id="live",
            configuration_root=self.root,
            journal_root=None,
            allowed_relative_paths=frozenset(
                {
                    "configuration.nix",
                    "ncm/default.nix",
                    "ncm/managed.nix",
                    "ncm/packages.nix",
                    "ncm/state.json",
                }
            ),
            fixture_only=False,
            apply_enabled=False,
        )
        self.authorizer = MockPolkitAuthorizer()
        self.backend = LiveReadOnlyHelperBackend(
            runner=self.passing_runner,
            which=self.fake_which,
        )
        self.dispatcher = HelperDispatcher(
            targets=(self.target,),
            authorizer=self.authorizer,
            backend=self.backend,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def fake_which(name: str) -> str:
        return f"/tools/{name}"

    @staticmethod
    def passing_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "/nix/store/fake.drv\n", "")

    @staticmethod
    def request(operation: str, payload: dict, request_id: str) -> dict:
        return {
            "schemaVersion": 1,
            "requestId": request_id,
            "operation": operation,
            "payload": payload,
        }

    @staticmethod
    def protocol_changes(plan) -> list[dict]:
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

    def snapshot(self) -> dict[str, bytes]:
        return {
            str(path.relative_to(self.root)): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }

    def validation_request(self) -> tuple[dict, str]:
        plan = plan_adoption(self.root)
        validation = validate_adoption(
            self.root, runner=self.passing_runner, which=self.fake_which
        )
        return (
            self.request(
                "validate-plan",
                {
                    "targetId": "live",
                    "planFingerprint": validation.plan_fingerprint,
                    "changes": self.protocol_changes(plan),
                },
                "live-validate-01",
            ),
            validation.plan_fingerprint,
        )

    def test_validation_is_read_only_and_never_issues_a_receipt(self) -> None:
        before = self.snapshot()
        request, fingerprint = self.validation_request()

        response = self.dispatcher.handle(request, peer_uid=1000)

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["planFingerprint"], fingerprint)
        self.assertTrue(response["result"]["readOnly"])
        self.assertFalse(response["result"]["applyEnabled"])
        self.assertNotIn("validationReceipt", response["result"])
        self.assertTrue(response["result"]["validation"]["liveTarget"])
        self.assertEqual(self.authorizer.calls, [])
        self.assertEqual(self.snapshot(), before)

    def test_apply_and_recovery_stop_before_polkit_or_backend(self) -> None:
        apply_response = self.dispatcher.handle(
            self.request(
                "apply-validated-plan",
                {
                    "targetId": "live",
                    "planFingerprint": "1" * 64,
                    "validationReceipt": "A" * 32,
                },
                "live-apply-0001",
            ),
            peer_uid=1000,
        )
        recovery_response = self.dispatcher.handle(
            self.request(
                "recover-transaction",
                {"targetId": "live", "transactionId": "a" * 24},
                "live-recover-01",
            ),
            peer_uid=1000,
        )

        self.assertEqual(apply_response["error"]["code"], "operation-disabled")
        self.assertEqual(recovery_response["error"]["code"], "operation-disabled")
        self.assertEqual(self.authorizer.calls, [])

    def test_submitted_candidate_must_match_the_local_plan_exactly(self) -> None:
        request, _ = self.validation_request()
        candidate = request["payload"]["changes"][-1]
        candidate["candidate"] += "# mutation\n"
        candidate["candidateSha256"] = hashlib.sha256(
            candidate["candidate"].encode("utf-8")
        ).hexdigest()

        response = self.dispatcher.handle(request, peer_uid=1000)

        self.assertEqual(response["error"]["code"], "plan-mismatch")
        self.assertEqual(self.authorizer.calls, [])

    def test_capabilities_publish_hard_read_only_boundary(self) -> None:
        response = self.dispatcher.handle(
            self.request("capabilities", {}, "live-capabilities"), peer_uid=1000
        )

        target = response["result"]["targets"][0]
        self.assertTrue(target["liveTarget"])
        self.assertTrue(target["readOnly"])
        self.assertFalse(target["applyEnabled"])
        self.assertFalse(target["recoveryEnabled"])
        self.assertTrue(target["dryActivatePreviewEnabled"])
        self.assertIn("preview-activation", response["result"]["operations"])

    def test_implicit_flake_hostname_has_one_consistent_fingerprint(self) -> None:
        (self.root / "flake.nix").write_text(
            "{ outputs = _: { }; }\n", encoding="utf-8"
        )
        request = build_validate_request(
            self.root, target_id="live", flake_target=None
        )
        request["requestId"] = "live-flake-host"

        response = self.dispatcher.handle(request, peer_uid=1000)

        self.assertEqual(response["status"], "ok")
        self.assertEqual(
            response["result"]["planFingerprint"],
            response["result"]["validation"]["planFingerprint"],
        )


if __name__ == "__main__":
    unittest.main()
