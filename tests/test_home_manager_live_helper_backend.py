import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from nix_control_manager.fixture_helper_backend import FixtureWorkflowHelperBackend
from nix_control_manager.helper_service import (
    HOME_MANAGER_APPLY_ACTION_ID,
    HOME_MANAGER_RECOVER_ACTION_ID,
    HelperDispatcher,
    HelperTarget,
    MockPolkitAuthorizer,
)
from nix_control_manager.home_manager_adoption import (
    plan_home_manager_adoption,
    validate_home_manager_adoption,
)
from nix_control_manager.transaction import apply_home_manager_plan_live


class HomeManagerLiveHelperBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        temporary = Path(self.temporary.name)
        self.root = temporary / "live-home-manager"
        self.root.mkdir()
        self.journal = temporary / "live-journal"
        (self.root / "home.nix").write_text(
            "{ ... }:\n"
            "{\n"
            '  home.username = "alice";\n'
            "}\n",
            encoding="utf-8",
        )
        (self.root / "flake.nix").write_text(
            "{ outputs = { ... }: { "
            "homeConfigurations.alice.activationPackage.drvPath = "
            '"/nix/store/fake-home-manager.drv"; }; }\n',
            encoding="utf-8",
        )
        self.state = self.root / "user-state.local.json"
        self.state.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "users": {
                        "alice": {
                            "integration": "standalone",
                            "packages": ["git"],
                            "options": {},
                        }
                    },
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        self.plan = self._plan()
        self.target = HelperTarget(
            target_id="live-home",
            configuration_root=self.root,
            allowed_relative_paths=frozenset(
                change.relative_path for change in self.plan.changes
            ),
            fixture_only=False,
            apply_enabled=False,
            home_manager_apply_enabled=True,
            home_manager_root=self.root,
            home_manager_journal_root=self.journal,
        )
        self.authorizer = MockPolkitAuthorizer()
        self.dispatcher = HelperDispatcher(
            targets=(self.target,),
            authorizer=self.authorizer,
            backend=FixtureWorkflowHelperBackend(
                runner=self._passing_runner,
                which=self._which,
            ),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _which(name: str) -> str:
        return f"/tools/{name}"

    @staticmethod
    def _passing_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "/nix/store/fake.drv\n", "")

    def _plan(self):
        return plan_home_manager_adoption(
            self.root,
            standalone_root=self.root,
            user_state_path=self.state,
            username="alice",
            integration="standalone",
            packages=("firefox", "git"),
        )

    @staticmethod
    def _request(operation: str, payload: dict, request_id: str) -> dict:
        return {
            "schemaVersion": 1,
            "requestId": request_id,
            "operation": operation,
            "payload": payload,
        }

    @staticmethod
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

    def _validation(self):
        return validate_home_manager_adoption(
            self.plan,
            runner=self._passing_runner,
            which=self._which,
        )

    def test_opt_in_live_target_persists_only_home_manager_sources(self) -> None:
        capabilities = self.dispatcher.handle(
            self._request("capabilities", {}, "live-capabilities"), peer_uid=1000
        )
        advertised = capabilities["result"]["targets"][0]
        self.assertFalse(advertised["applyEnabled"])
        self.assertFalse(advertised["recoveryEnabled"])
        self.assertTrue(advertised["homeManagerApplyEnabled"])
        self.assertTrue(advertised["homeManagerLiveWriteEnabled"])
        self.assertFalse(advertised["dryActivatePreviewEnabled"])

        validation = self._validation()
        validated = self.dispatcher.handle(
            self._request(
                "validate-home-manager-plan",
                {
                    "targetId": "live-home",
                    "planFingerprint": validation.plan_fingerprint,
                    "username": "alice",
                    "integration": "standalone",
                    "packages": ["firefox", "git"],
                    "changes": self._changes(self.plan),
                },
                "live-validate",
            ),
            peer_uid=1000,
        )
        self.assertEqual(validated["status"], "ok")
        self.assertFalse(validated["result"]["fixtureOnly"])
        self.assertTrue(validated["result"]["liveWriteEnabled"])

        apply_request = self._request(
            "apply-validated-home-manager-plan",
            {
                "targetId": "live-home",
                "planFingerprint": validation.plan_fingerprint,
                "validationReceipt": validated["result"]["validationReceipt"],
            },
            "live-apply",
        )
        denied = self.dispatcher.handle(apply_request, peer_uid=1000)
        self.assertEqual(denied["status"], "denied")
        self.assertFalse((self.root / "ncm").exists())

        self.authorizer.allowed.add((1000, HOME_MANAGER_APPLY_ACTION_ID))
        applied = self.dispatcher.handle(apply_request, peer_uid=1000)
        self.assertEqual(applied["status"], "ok")
        self.assertEqual(applied["result"]["state"], "committed")
        self.assertFalse(applied["result"]["fixtureOnly"])
        self.assertTrue(applied["result"]["liveWriteEnabled"])
        self.assertFalse(applied["result"]["activationEnabled"])
        self.assertTrue((self.root / "ncm" / "user-state.json").is_file())

    def test_live_recovery_uses_its_own_polkit_action_and_journal_kind(self) -> None:
        validation = self._validation()
        provisional = apply_home_manager_plan_live(
            self.plan, validation, journal_root=self.journal
        )
        request = self._request(
            "recover-home-manager-transaction",
            {
                "targetId": "live-home",
                "transactionId": provisional.transaction_id,
            },
            "live-recover",
        )

        denied = self.dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(denied["status"], "denied")
        self.assertTrue((self.root / "ncm" / "user-state.json").is_file())

        self.authorizer.allowed.add((1000, HOME_MANAGER_RECOVER_ACTION_ID))
        recovered = self.dispatcher.handle(request, peer_uid=1000)
        self.assertEqual(recovered["result"]["state"], "recovered")
        self.assertFalse(recovered["result"]["fixtureOnly"])
        self.assertFalse((self.root / "ncm").exists())


if __name__ == "__main__":
    unittest.main()
