import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from nix_control_manager.adoption import plan_adoption
from nix_control_manager.apply_workflow import execute_fixture_apply_workflow
from nix_control_manager.candidate import validate_adoption
from nix_control_manager.transaction import (
    SimulatedTransactionCrash,
    initialize_transaction_fixture,
    recover_pending_fixture_transactions,
)


class FixtureApplyWorkflowTests(unittest.TestCase):
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

    def prepare(self):
        plan = plan_adoption(self.root)
        validation = validate_adoption(
            self.root,
            runner=self.passing_runner,
            which=self.fake_which,
        )
        self.assertEqual(validation.status, "passed")
        return plan, validation

    def only_manifest(self) -> dict:
        paths = list(self.journal.glob("*/manifest.json"))
        self.assertEqual(len(paths), 1)
        return json.loads(paths[0].read_text(encoding="utf-8"))

    def test_successful_post_commit_evaluation_finalizes_transaction(self) -> None:
        plan, pre_validation = self.prepare()

        result = execute_fixture_apply_workflow(
            plan,
            pre_validation,
            journal_root=self.journal,
            runner=self.passing_runner,
            which=self.fake_which,
        )

        self.assertEqual(result.state, "committed")
        self.assertEqual(result.transaction.state, "committed")
        self.assertEqual(result.post_validation.status, "passed")
        self.assertEqual(result.post_validation.candidate_files, ())
        self.assertFalse(result.to_mapping()["activationEnabled"])
        self.assertEqual(plan_adoption(self.root).status, "no-changes")
        manifest = self.only_manifest()
        self.assertEqual(manifest["state"], "committed")
        self.assertEqual(manifest["postVerification"]["status"], "passed")
        self.assertTrue(
            any(
                check["name"].startswith("Evaluate")
                and check["status"] == "passed"
                for check in manifest["postVerification"]["checks"]
            )
        )

    def test_failed_post_commit_evaluation_rolls_back_every_file(self) -> None:
        plan, pre_validation = self.prepare()

        result = execute_fixture_apply_workflow(
            plan,
            pre_validation,
            journal_root=self.journal,
            runner=self.failing_runner,
            which=self.fake_which,
        )

        self.assertEqual(result.state, "rolled-back")
        self.assertEqual(result.post_validation.status, "failed")
        self.assertEqual(
            (self.root / "configuration.nix").read_text(encoding="utf-8"),
            self.original,
        )
        self.assertFalse((self.root / "ncm").exists())
        manifest = self.only_manifest()
        self.assertEqual(manifest["state"], "rolled-back")
        self.assertEqual(manifest["postVerification"]["status"], "failed")
        self.assertIn("Post-commit validation returned failed", manifest["error"])

    def test_unavailable_post_commit_nix_also_rolls_back(self) -> None:
        plan, pre_validation = self.prepare()

        result = execute_fixture_apply_workflow(
            plan,
            pre_validation,
            journal_root=self.journal,
            which=lambda _: None,
        )

        self.assertEqual(result.state, "rolled-back")
        self.assertEqual(result.post_validation.status, "unavailable")
        self.assertEqual(
            (self.root / "configuration.nix").read_text(encoding="utf-8"),
            self.original,
        )
        self.assertFalse((self.root / "ncm").exists())

    def test_interruption_before_finalize_is_recovered_on_next_start(self) -> None:
        plan, pre_validation = self.prepare()

        with self.assertRaises(SimulatedTransactionCrash):
            execute_fixture_apply_workflow(
                plan,
                pre_validation,
                journal_root=self.journal,
                runner=self.passing_runner,
                which=self.fake_which,
                simulate_interruption_after_commit=True,
            )
        self.assertIn(
            "./ncm",
            (self.root / "configuration.nix").read_text(encoding="utf-8"),
        )
        self.assertEqual(self.only_manifest()["state"], "awaiting-verification")

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


if __name__ == "__main__":
    unittest.main()
