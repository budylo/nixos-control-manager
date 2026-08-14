from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from nix_control_manager.errors import TransactionError
from nix_control_manager.home_manager_adoption import (
    plan_home_manager_adoption,
    validate_home_manager_adoption,
)
from nix_control_manager.home_manager_apply_workflow import (
    execute_home_manager_fixture_apply_workflow,
)
from nix_control_manager.transaction import (
    SimulatedTransactionCrash,
    apply_home_manager_plan_in_fixture,
    initialize_transaction_fixture,
    recover_pending_fixture_transactions,
)


class HomeManagerFixtureApplyWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        temporary = Path(self.temporary.name)
        self.root = temporary / "home-manager-fixture"
        self.journal = temporary / "journals"
        self.state = temporary / "user-state.json"
        initialize_transaction_fixture(self.root)
        self.original = (
            "{ ... }:\n\n{\n  imports = [\n"
            "    ./hardware-configuration.nix\n  ];\n"
            "  home-manager.users.alice = ./alice.nix;\n}\n"
        )
        (self.root / "configuration.nix").write_text(
            self.original, encoding="utf-8"
        )
        (self.root / "hardware-configuration.nix").write_text(
            "{ ... }: { }\n", encoding="utf-8"
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
    def failing_runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "evaluation failed")

    def prepare(self, *, integration="nixos-module"):
        plan = plan_home_manager_adoption(
            self.root,
            standalone_root=self.root,
            user_state_path=self.state,
            username="alice",
            integration=integration,
            packages=("firefox", "git"),
        )
        validation = validate_home_manager_adoption(
            plan,
            runner=self.passing_runner,
            which=self.fake_which,
        )
        self.assertEqual(plan.status, "ready")
        self.assertEqual(validation.status, "passed")
        self.assertEqual(len(validation.plan_fingerprint or ""), 64)
        return plan, validation

    def only_manifest(self) -> dict:
        paths = list(self.journal.glob("*/manifest.json"))
        self.assertEqual(len(paths), 1)
        return json.loads(paths[0].read_text(encoding="utf-8"))

    def test_successful_nixos_module_transaction_is_committed(self) -> None:
        plan, pre_validation = self.prepare()

        result = execute_home_manager_fixture_apply_workflow(
            plan,
            pre_validation,
            journal_root=self.journal,
            runner=self.passing_runner,
            which=self.fake_which,
        )

        self.assertEqual(result.state, "committed")
        self.assertEqual(result.post_validation.status, "passed")
        self.assertEqual(result.post_validation.candidate_files, ())
        self.assertFalse(result.to_mapping()["liveWriteEnabled"])
        self.assertFalse(result.to_mapping()["activationEnabled"])
        self.assertIn(
            "./ncm/home-manager-alice.nix",
            (self.root / "configuration.nix").read_text(encoding="utf-8"),
        )
        self.assertTrue((self.root / "ncm" / "managed-home-alice.nix").is_file())
        manifest = self.only_manifest()
        self.assertEqual(manifest["state"], "committed")
        self.assertEqual(manifest["transactionKind"], "home-manager-adoption")
        self.assertEqual(manifest["planFingerprint"], pre_validation.plan_fingerprint)
        self.assertTrue(
            any(
                check["name"].startswith("Evaluate")
                and check["status"] == "passed"
                for check in manifest["postVerification"]["checks"]
            )
        )

    def test_failed_post_commit_evaluation_rolls_back_all_files(self) -> None:
        plan, pre_validation = self.prepare()

        result = execute_home_manager_fixture_apply_workflow(
            plan,
            pre_validation,
            journal_root=self.journal,
            runner=self.failing_runner,
            which=self.fake_which,
        )

        self.assertEqual(result.state, "rolled-back")
        self.assertEqual(
            (self.root / "configuration.nix").read_text(encoding="utf-8"),
            self.original,
        )
        self.assertFalse((self.root / "ncm").exists())
        self.assertEqual(self.only_manifest()["state"], "rolled-back")

    def test_changed_fingerprint_is_rejected_before_any_write(self) -> None:
        plan, validation = self.prepare()
        changed = replace(validation, plan_fingerprint="0" * 64)

        with self.assertRaisesRegex(TransactionError, "fingerprint"):
            apply_home_manager_plan_in_fixture(
                plan, changed, journal_root=self.journal
            )

        self.assertEqual(
            (self.root / "configuration.nix").read_text(encoding="utf-8"),
            self.original,
        )
        self.assertFalse((self.root / "ncm").exists())
        self.assertFalse(self.journal.exists())

    def test_interrupted_partial_commit_is_recovered_from_shared_journal(self) -> None:
        plan, validation = self.prepare()

        with self.assertRaises(SimulatedTransactionCrash):
            apply_home_manager_plan_in_fixture(
                plan,
                validation,
                journal_root=self.journal,
                fault_after_commits=2,
                simulate_crash=True,
            )
        self.assertNotEqual(
            (self.root / "configuration.nix").read_text(encoding="utf-8"),
            self.original,
        )

        recovered = recover_pending_fixture_transactions(
            self.root, journal_root=self.journal
        )

        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].state, "recovered")
        self.assertEqual(
            (self.root / "configuration.nix").read_text(encoding="utf-8"),
            self.original,
        )
        self.assertFalse((self.root / "ncm").exists())

    def test_fixture_marker_and_full_evaluation_are_both_required(self) -> None:
        plan, validation = self.prepare()
        (self.root / ".ncm-transaction-fixture").unlink()
        with self.assertRaisesRegex(TransactionError, "Fixture marker"):
            apply_home_manager_plan_in_fixture(
                plan, validation, journal_root=self.journal
            )

        initialize_transaction_fixture(self.root)
        syntax_only = replace(
            validation,
            checks=tuple(
                check for check in validation.checks if not check.name.startswith("Evaluate")
            ),
        )
        with self.assertRaisesRegex(TransactionError, "evaluation"):
            apply_home_manager_plan_in_fixture(
                plan, syntax_only, journal_root=self.journal
            )
        self.assertFalse((self.root / "ncm").exists())

    def test_fixture_initializer_refuses_live_home_manager_paths(self) -> None:
        live_shaped = Path(self.temporary.name) / "fake" / "etc" / "home-manager"

        with self.assertRaisesRegex(TransactionError, "live Home Manager"):
            initialize_transaction_fixture(live_shaped)

        self.assertFalse(live_shaped.exists())

    def test_successful_standalone_flake_transaction(self) -> None:
        (self.root / "configuration.nix").unlink()
        (self.root / "hardware-configuration.nix").unlink()
        (self.root / "home.nix").write_text(
            '{ ... }:\n{\n  home.username = "alice";\n}\n', encoding="utf-8"
        )
        (self.root / "flake.nix").write_text(
            '{ outputs = _: { homeConfigurations.alice = null; }; }\n',
            encoding="utf-8",
        )
        plan, pre_validation = self.prepare(integration="standalone")

        result = execute_home_manager_fixture_apply_workflow(
            plan,
            pre_validation,
            journal_root=self.journal,
            runner=self.passing_runner,
            which=self.fake_which,
        )

        self.assertEqual(result.state, "committed")
        self.assertIn(
            "./ncm/managed-home-alice.nix",
            (self.root / "home.nix").read_text(encoding="utf-8"),
        )
        self.assertEqual(self.only_manifest()["transactionKind"], "home-manager-adoption")


if __name__ == "__main__":
    unittest.main()
