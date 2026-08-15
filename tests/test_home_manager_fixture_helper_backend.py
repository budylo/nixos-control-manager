import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from nix_control_manager.fixture_helper_backend import FixtureWorkflowHelperBackend
from nix_control_manager.helper_service import (
    HOME_MANAGER_APPLY_ACTION_ID,
    HOME_MANAGER_RECOVER_ACTION_ID,
    RECOVER_ACTION_ID,
    HelperDispatcher,
    HelperTarget,
    MockPolkitAuthorizer,
)
from nix_control_manager.home_manager_adoption import (
    plan_home_manager_adoption,
    validate_home_manager_adoption,
)
from nix_control_manager.transaction import (
    apply_home_manager_plan_in_fixture,
    initialize_transaction_fixture,
)


class HomeManagerFixtureHelperBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        temporary = Path(self.temporary.name)
        self.root = temporary / "home-manager-fixture"
        self.journal = temporary / "journals"
        initialize_transaction_fixture(self.root)
        self.original_home = (
            "{ ... }:\n"
            "{\n"
            '  home.username = "alice";\n'
            "}\n"
        )
        (self.root / "home.nix").write_text(self.original_home, encoding="utf-8")
        (self.root / "flake.nix").write_text(
            "{ outputs = { ... }: { homeConfigurations.alice.activationPackage.drvPath = "
            '"/nix/store/fake-home-manager.drv"; }; }\n',
            encoding="utf-8",
        )
        self.legacy_state = self.root / "user-state.local.json"
        self.legacy_content = json.dumps(
            {
                "schemaVersion": 1,
                "users": {
                    "alice": {
                        "integration": "standalone",
                        "packages": ["git"],
                        "options": {"programs.git.enable": True},
                    }
                },
            },
            sort_keys=True,
        )
        self.legacy_state.write_text(self.legacy_content, encoding="utf-8")
        self.plan = self.build_plan()
        self.target = HelperTarget(
            target_id="home-fixture",
            configuration_root=self.root,
            journal_root=self.journal,
            allowed_relative_paths=frozenset(
                change.relative_path for change in self.plan.changes
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

    def build_plan(self):
        return plan_home_manager_adoption(
            self.root,
            standalone_root=self.root,
            user_state_path=self.legacy_state,
            username="alice",
            integration="standalone",
            packages=("firefox", "git"),
        )

    def validate_through_helper(self, uid: int = 1000):
        validation = validate_home_manager_adoption(
            self.plan, runner=self.passing_runner, which=self.fake_which
        )
        self.assertEqual(validation.status, "passed")
        response = self.dispatcher.handle(
            self.request(
                "validate-home-manager-plan",
                {
                    "targetId": self.target.target_id,
                    "planFingerprint": validation.plan_fingerprint,
                    "username": "alice",
                    "integration": "standalone",
                    "packages": ["firefox", "git"],
                    "changes": self.protocol_changes(self.plan),
                },
                "home-validate-01",
            ),
            peer_uid=uid,
        )
        self.assertEqual(response["status"], "ok")
        return validation, response

    def test_authorized_receipt_commits_state_and_is_single_use(self) -> None:
        validation, validated = self.validate_through_helper()
        request = self.request(
            "apply-validated-home-manager-plan",
            {
                "targetId": self.target.target_id,
                "planFingerprint": validation.plan_fingerprint,
                "validationReceipt": validated["result"]["validationReceipt"],
            },
            "home-apply-001",
        )

        denied = self.dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(denied["status"], "denied")
        self.assertFalse((self.root / "ncm").exists())

        self.authorizer.allowed.add((1000, HOME_MANAGER_APPLY_ACTION_ID))
        applied = self.dispatcher.handle(request, peer_uid=1000)

        self.assertEqual(applied["status"], "ok")
        self.assertEqual(applied["result"]["state"], "committed")
        self.assertEqual(applied["result"]["filesWritten"], 3)
        self.assertFalse(applied["result"]["liveWriteEnabled"])
        persisted = json.loads(
            (self.root / "ncm" / "user-state.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            persisted["users"]["alice"]["packages"], ["firefox", "git"]
        )
        self.assertEqual(
            self.legacy_state.read_text(encoding="utf-8"), self.legacy_content
        )

        replay = self.dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(replay["error"]["code"], "invalid-receipt")

    def test_helper_rebuilds_plan_and_rejects_submitted_mutation(self) -> None:
        validation = validate_home_manager_adoption(
            self.plan, runner=self.passing_runner, which=self.fake_which
        )
        changes = self.protocol_changes(self.plan)
        changes[-1]["candidate"] += "\n"
        changes[-1]["candidateSha256"] = hashlib.sha256(
            changes[-1]["candidate"].encode("utf-8")
        ).hexdigest()

        response = self.dispatcher.handle(
            self.request(
                "validate-home-manager-plan",
                {
                    "targetId": self.target.target_id,
                    "planFingerprint": validation.plan_fingerprint,
                    "username": "alice",
                    "integration": "standalone",
                    "packages": ["firefox", "git"],
                    "changes": changes,
                },
                "home-mismatch-1",
            ),
            peer_uid=1000,
        )

        self.assertEqual(response["error"]["code"], "plan-mismatch")
        self.assertNotIn("validationReceipt", response.get("result") or {})
        self.assertFalse(self.journal.exists())

    def test_home_manager_receipt_cannot_authorize_system_apply(self) -> None:
        validation, validated = self.validate_through_helper()
        self.authorizer.allowed.add((1000, HOME_MANAGER_APPLY_ACTION_ID))

        response = self.dispatcher.handle(
            self.request(
                "apply-validated-plan",
                {
                    "targetId": self.target.target_id,
                    "planFingerprint": validation.plan_fingerprint,
                    "validationReceipt": validated["result"]["validationReceipt"],
                },
                "cross-kind-apply",
            ),
            peer_uid=1000,
        )

        self.assertEqual(response["error"]["code"], "invalid-receipt")
        self.assertEqual(self.authorizer.calls, [])
        self.assertFalse((self.root / "ncm").exists())

    def test_edit_between_validation_and_apply_stops_before_transaction(self) -> None:
        validation, validated = self.validate_through_helper()
        external = self.original_home + "# external edit\n"
        (self.root / "home.nix").write_text(external, encoding="utf-8")
        self.authorizer.allowed.add((1000, HOME_MANAGER_APPLY_ACTION_ID))

        response = self.dispatcher.handle(
            self.request(
                "apply-validated-home-manager-plan",
                {
                    "targetId": self.target.target_id,
                    "planFingerprint": validation.plan_fingerprint,
                    "validationReceipt": validated["result"]["validationReceipt"],
                },
                "home-race-001",
            ),
            peer_uid=1000,
        )

        self.assertEqual(response["error"]["code"], "transaction-failed")
        self.assertEqual(
            (self.root / "home.nix").read_text(encoding="utf-8"), external
        )
        self.assertFalse((self.root / "ncm").exists())
        self.assertFalse(self.journal.exists())

    def test_recovery_requires_home_manager_operation_and_action(self) -> None:
        validation = validate_home_manager_adoption(
            self.plan, runner=self.passing_runner, which=self.fake_which
        )
        provisional = apply_home_manager_plan_in_fixture(
            self.plan, validation, journal_root=self.journal
        )
        self.authorizer.allowed.add((1000, RECOVER_ACTION_ID))

        wrong_workflow = self.dispatcher.handle(
            self.request(
                "recover-transaction",
                {
                    "targetId": self.target.target_id,
                    "transactionId": provisional.transaction_id,
                },
                "wrong-recovery-1",
            ),
            peer_uid=1000,
        )
        self.assertEqual(wrong_workflow["error"]["code"], "recovery-failed")
        self.assertTrue((self.root / "ncm" / "user-state.json").exists())

        request = self.request(
            "recover-home-manager-transaction",
            {
                "targetId": self.target.target_id,
                "transactionId": provisional.transaction_id,
            },
            "home-recovery-1",
        )
        denied = self.dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(denied["status"], "denied")

        self.authorizer.allowed.add((1000, HOME_MANAGER_RECOVER_ACTION_ID))
        recovered = self.dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(recovered["result"]["state"], "recovered")
        self.assertFalse((self.root / "ncm").exists())
        self.assertEqual(
            (self.root / "home.nix").read_text(encoding="utf-8"), self.original_home
        )


if __name__ == "__main__":
    unittest.main()
