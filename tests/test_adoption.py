from pathlib import Path
import tempfile
import unittest

from nix_control_manager.adoption import plan_adoption


class AdoptionPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "etc-nixos"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_plans_legacy_connected_migration_without_touching_entrypoint(self) -> None:
        configuration = self.root / "configuration.nix"
        configuration.write_text(
            "{ ... }: {\n  imports = [\n    ./ncm\n  ];\n}\n", encoding="utf-8"
        )
        managed = self.root / "ncm"
        managed.mkdir()
        (managed / "default.nix").write_text(
            "{ ... }: { imports = [ ./packages.nix ]; }\n", encoding="utf-8"
        )
        (managed / "packages.nix").write_text(
            "{ pkgs, ... }: { environment.systemPackages = with pkgs; [ ]; }\n",
            encoding="utf-8",
        )
        (managed / "state.json").write_text(
            '{"schemaVersion":1,"nixosRelease":"26.05","packages":{},"options":{}}',
            encoding="utf-8",
        )

        plan = plan_adoption(self.root)

        self.assertEqual(plan.status, "migration-ready")
        self.assertTrue(plan.safe_to_apply)
        paths = {change.relative_path for change in plan.changes}
        self.assertEqual(paths, {"ncm/packages.nix", "ncm/state.json"})
        self.assertNotIn("configuration.nix (candidate)", plan.combined_diff)
        for change in plan.to_mapping()["changes"]:
            self.assertEqual(len(change["previousSha256"]), 64)
            self.assertEqual(len(change["candidateSha256"]), 64)

    def test_plans_isolated_module_for_standard_channel_configuration(self) -> None:
        (self.root / "configuration.nix").write_text(
            "{ ... }:\n\n{\n  imports = [\n    ./hardware-configuration.nix\n  ];\n}\n",
            encoding="utf-8",
        )

        plan = plan_adoption(self.root)

        self.assertEqual(plan.status, "ready")
        self.assertTrue(plan.safe_to_apply)
        paths = [change.relative_path for change in plan.changes]
        self.assertEqual(
            paths,
            [
                "configuration.nix",
                "ncm/default.nix",
                "ncm/managed.nix",
                "ncm/state.json",
            ],
        )
        config_candidate = plan.changes[0].candidate
        self.assertIn("./ncm # managed by Nix Control Manager", config_candidate)
        self.assertIsNone(plan.changes[1].previous_sha256)

    def test_refuses_to_guess_inline_import_format(self) -> None:
        (self.root / "configuration.nix").write_text(
            "{ ... }: { imports = [ ./hardware-configuration.nix ]; }\n",
            encoding="utf-8",
        )

        plan = plan_adoption(self.root)

        self.assertEqual(plan.status, "manual")
        self.assertFalse(plan.safe_to_apply)
        self.assertTrue(any("multiline" in warning for warning in plan.warnings))

    def test_git_flake_reports_new_files_that_require_staging(self) -> None:
        (self.root / ".git").mkdir()
        (self.root / "flake.nix").write_text("{ outputs = _: { }; }\n", encoding="utf-8")
        (self.root / "configuration.nix").write_text(
            "{ ... }: {\n  imports = [\n  ];\n}\n", encoding="utf-8"
        )

        plan = plan_adoption(self.root)

        self.assertEqual(plan.status, "ready")
        self.assertEqual(
            plan.files_requiring_staging,
            ("ncm/default.nix", "ncm/managed.nix", "ncm/state.json"),
        )
        self.assertTrue(any("staged" in warning for warning in plan.warnings))

    def test_invalid_connected_state_blocks_migration(self) -> None:
        (self.root / "configuration.nix").write_text(
            "{ ... }: {\n  imports = [\n    ./ncm\n  ];\n}\n", encoding="utf-8"
        )
        managed = self.root / "ncm"
        managed.mkdir()
        (managed / "default.nix").write_text(
            "{ ... }: { imports = [ ./packages.nix ]; }\n", encoding="utf-8"
        )
        (managed / "state.json").write_text("broken", encoding="utf-8")

        plan = plan_adoption(self.root)

        self.assertEqual(plan.status, "blocked")
        self.assertFalse(plan.safe_to_apply)
        self.assertEqual(plan.changes, ())


if __name__ == "__main__":
    unittest.main()
