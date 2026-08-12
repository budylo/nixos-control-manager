import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from nix_control_manager.adoption import plan_adoption
from nix_control_manager.candidate import validate_adoption
from nix_control_manager.fixture_helper_backend import FixtureWorkflowHelperBackend
from nix_control_manager.helper_service import (
    APPLY_ACTION_ID,
    RECOVER_ACTION_ID,
    HelperDispatcher,
    HelperTarget,
    MockPolkitAuthorizer,
)
from nix_control_manager.transaction import (
    apply_plan_in_fixture,
    initialize_transaction_fixture,
)


class FixtureHelperBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        temporary = Path(self.temporary.name)
        self.root = temporary / "configuration-root"
        self.journal = temporary / "journals"
        initialize_transaction_fixture(self.root)
        self.original = (
            "{ ... }:\n\n{\n  imports = [\n"
            "    ./hardware-configuration.nix\n  ];\n}\n"
        )
        (self.root / "configuration.nix").write_text(
            self.original, encoding="utf-8"
        )
        (self.root / "hardware-configuration.nix").write_text(
            "{ ... }: { }\n", encoding="utf-8"
        )
        self.target = HelperTarget(
            target_id="fixture",
            configuration_root=self.root,
            journal_root=self.journal,
            allowed_relative_paths=frozenset(
                {
                    "configuration.nix",
                    "ncm/default.nix",
                    "ncm/managed.nix",
                    "ncm/state.json",
                }
            ),
        )
        self.authorizer = MockPolkitAuthorizer()
        self.backend = FixtureWorkflowHelperBackend(
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

    def validate_through_helper(self, uid: int = 1000):
        plan = plan_adoption(self.root)
        validation = validate_adoption(
            self.root, runner=self.passing_runner, which=self.fake_which
        )
        response = self.dispatcher.handle(
            self.request(
                "validate-plan",
                {
                    "targetId": "fixture",
                    "planFingerprint": validation.plan_fingerprint,
                    "changes": self.protocol_changes(plan),
                },
                "adapter-validate1",
            ),
            peer_uid=uid,
        )
        self.assertEqual(response["status"], "ok")
        return plan, validation, response

    def test_authorized_receipt_runs_full_fixture_workflow(self) -> None:
        _, validation, validated = self.validate_through_helper()
        self.authorizer.allowed.add((1000, APPLY_ACTION_ID))

        response = self.dispatcher.handle(
            self.request(
                "apply-validated-plan",
                {
                    "targetId": "fixture",
                    "planFingerprint": validation.plan_fingerprint,
                    "validationReceipt": validated["result"]["validationReceipt"],
                },
                "adapter-apply001",
            ),
            peer_uid=1000,
        )

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["state"], "committed")
        self.assertEqual(response["result"]["filesWritten"], 4)
        self.assertFalse(response["result"]["activationEnabled"])
        self.assertEqual(plan_adoption(self.root).status, "no-changes")
        manifests = list(self.journal.glob("*/manifest.json"))
        self.assertEqual(len(manifests), 1)

    def test_helper_rebuilds_local_plan_and_rejects_submitted_content_mismatch(self) -> None:
        plan = plan_adoption(self.root)
        validation = validate_adoption(
            self.root, runner=self.passing_runner, which=self.fake_which
        )
        changes = self.protocol_changes(plan)
        changes[-1]["candidate"] += "# submitted mutation\n"
        changes[-1]["candidateSha256"] = hashlib.sha256(
            changes[-1]["candidate"].encode("utf-8")
        ).hexdigest()

        response = self.dispatcher.handle(
            self.request(
                "validate-plan",
                {
                    "targetId": "fixture",
                    "planFingerprint": validation.plan_fingerprint,
                    "changes": changes,
                },
                "adapter-mismatch",
            ),
            peer_uid=1000,
        )

        self.assertEqual(response["error"]["code"], "plan-mismatch")
        self.assertNotIn("validationReceipt", response.get("result") or {})
        self.assertEqual(
            (self.root / "configuration.nix").read_text(encoding="utf-8"),
            self.original,
        )
        self.assertFalse(self.journal.exists())

    def test_edit_between_validate_and_apply_stops_before_transaction(self) -> None:
        _, validation, validated = self.validate_through_helper()
        external = "# external edit after validation\n"
        (self.root / "configuration.nix").write_text(external, encoding="utf-8")
        self.authorizer.allowed.add((1000, APPLY_ACTION_ID))

        response = self.dispatcher.handle(
            self.request(
                "apply-validated-plan",
                {
                    "targetId": "fixture",
                    "planFingerprint": validation.plan_fingerprint,
                    "validationReceipt": validated["result"]["validationReceipt"],
                },
                "adapter-race001",
            ),
            peer_uid=1000,
        )

        self.assertEqual(response["error"]["code"], "transaction-failed")
        self.assertEqual(
            (self.root / "configuration.nix").read_text(encoding="utf-8"), external
        )
        self.assertFalse((self.root / "ncm").exists())
        self.assertFalse(self.journal.exists())

    def test_authorized_recovery_targets_only_requested_transaction(self) -> None:
        plan = plan_adoption(self.root)
        validation = validate_adoption(
            self.root, runner=self.passing_runner, which=self.fake_which
        )
        provisional = apply_plan_in_fixture(
            plan, validation, journal_root=self.journal
        )
        self.assertEqual(provisional.state, "awaiting-verification")
        self.authorizer.allowed.add((1000, RECOVER_ACTION_ID))

        response = self.dispatcher.handle(
            self.request(
                "recover-transaction",
                {
                    "targetId": "fixture",
                    "transactionId": provisional.transaction_id,
                },
                "adapter-recover1",
            ),
            peer_uid=1000,
        )

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["state"], "recovered")
        self.assertEqual(response["result"]["transactionId"], provisional.transaction_id)
        self.assertEqual(
            (self.root / "configuration.nix").read_text(encoding="utf-8"),
            self.original,
        )
        self.assertFalse((self.root / "ncm").exists())


if __name__ == "__main__":
    unittest.main()
