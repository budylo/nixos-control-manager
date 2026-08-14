from pathlib import Path
import subprocess
import tempfile
import unittest

from nix_control_manager.home_manager_adoption import (
    plan_home_manager_adoption,
    validate_home_manager_adoption,
)
from nix_control_manager.errors import ValidationError


class HomeManagerAdoptionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = self.root / "etc-nixos"
        self.standalone = self.root / "home-manager"
        self.state = self.root / "user-state.json"
        self.config.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_rejects_detected_username_that_is_unsafe_for_a_managed_path(self) -> None:
        with self.assertRaises(ValidationError):
            plan_home_manager_adoption(
                self.config,
                standalone_root=self.standalone,
                user_state_path=self.state,
                username="../../escape",
                integration="standalone",
                packages=("git",),
            )

    def plan(self, username="alice", integration="nixos-module"):
        return plan_home_manager_adoption(
            self.config,
            standalone_root=self.standalone,
            user_state_path=self.state,
            username=username,
            integration=integration,
            packages=("firefox", "git"),
        )

    def test_nixos_module_plan_uses_isolated_wiring_and_changes_nothing(self) -> None:
        configuration = self.config / "configuration.nix"
        original = (
            "{ ... }:\n\n{\n  imports = [\n"
            "    ./hardware-configuration.nix\n  ];\n"
            "  home-manager.users.alice = ./alice.nix;\n}\n"
        )
        configuration.write_text(original, encoding="utf-8")

        plan = self.plan()

        self.assertEqual(plan.status, "ready")
        self.assertTrue(plan.safe_to_validate)
        self.assertEqual(
            [change.relative_path for change in plan.changes],
            [
                "configuration.nix",
                "ncm/managed-home-alice.nix",
                "ncm/home-manager-alice.nix",
            ],
        )
        self.assertIn("./ncm/home-manager-alice.nix", plan.combined_diff)
        self.assertIn("home-manager.users.alice.imports", plan.combined_diff)
        self.assertIn("home.packages", plan.combined_diff)
        self.assertEqual(configuration.read_text(encoding="utf-8"), original)
        self.assertFalse((self.config / "ncm").exists())
        self.assertFalse(plan.to_mapping()["safeToApply"])

    def test_standalone_plan_adds_import_to_standard_home_module(self) -> None:
        self.standalone.mkdir()
        home = self.standalone / "home.nix"
        original = (
            '{ config, pkgs, ... }:\n\n{\n  home.username = "alice";\n'
            '  home.stateVersion = "26.05";\n}\n'
        )
        home.write_text(original, encoding="utf-8")

        plan = self.plan(integration="standalone")

        self.assertEqual(plan.status, "ready")
        self.assertEqual(
            [change.relative_path for change in plan.changes],
            ["home.nix", "ncm/managed-home-alice.nix"],
        )
        self.assertIn("imports = [", plan.changes[0].candidate)
        self.assertIn("./ncm/managed-home-alice.nix", plan.changes[0].candidate)
        self.assertEqual(home.read_text(encoding="utf-8"), original)

    def test_nonstandard_standalone_and_unowned_collision_require_manual_review(self) -> None:
        self.standalone.mkdir()
        (self.standalone / "home.nix").write_text(
            '{ ... }: { home.username = "alice"; }\n', encoding="utf-8"
        )
        plan = self.plan(integration="standalone")
        self.assertEqual(plan.status, "manual")
        self.assertEqual(plan.changes, ())

        (self.standalone / "ncm").mkdir()
        (self.standalone / "ncm" / "managed-home-alice.nix").write_text(
            "# user owned\n", encoding="utf-8"
        )
        collision = self.plan(integration="standalone")
        self.assertEqual(collision.status, "manual")
        self.assertTrue(any("unowned" in item for item in collision.warnings))

    @staticmethod
    def fake_which(name: str) -> str:
        return f"/tools/{name}"

    def test_validation_materializes_then_removes_nixos_candidate(self) -> None:
        configuration = self.config / "configuration.nix"
        original = (
            "{ ... }:\n{\n  imports = [\n  ];\n"
            "  home-manager.users.alice = ./alice.nix;\n}\n"
        )
        configuration.write_text(original, encoding="utf-8")
        plan = self.plan()
        working: list[Path] = []

        def runner(command, **kwargs):
            cwd = Path(kwargs["cwd"])
            working.append(cwd)
            self.assertNotEqual(cwd, self.config)
            if any(str(item).startswith("nixos-config=") for item in command):
                self.assertTrue((cwd / "ncm" / "managed-home-alice.nix").is_file())
            return subprocess.CompletedProcess(command, 0, "/nix/store/fake.drv\n", "")

        result = validate_home_manager_adoption(
            plan, runner=runner, which=self.fake_which
        )

        self.assertEqual(result.status, "passed")
        self.assertEqual(len(result.checks), 4)
        self.assertIn("Evaluate NixOS", result.checks[-1].name)
        self.assertTrue(all(not path.exists() for path in working))
        self.assertEqual(configuration.read_text(encoding="utf-8"), original)
        self.assertFalse(result.to_mapping()["buildEnabled"])

    def test_standalone_flake_validation_uses_no_write_lock_file(self) -> None:
        self.standalone.mkdir()
        (self.standalone / "home.nix").write_text(
            '{ ... }:\n{\n  home.username = "alice";\n}\n', encoding="utf-8"
        )
        (self.standalone / "flake.nix").write_text(
            '{ outputs = _: { homeConfigurations.alice = null; }; }\n',
            encoding="utf-8",
        )
        plan = self.plan(integration="standalone")
        commands: list[list[str]] = []

        def runner(command, **kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, "/nix/store/fake.drv", "")

        result = validate_home_manager_adoption(
            plan, runner=runner, which=self.fake_which
        )
        self.assertEqual(result.status, "passed")
        self.assertIn("--no-write-lock-file", commands[-1])
        self.assertIn("homeConfigurations.alice", commands[-1][-1])

    def test_missing_nix_and_undetected_user_fail_closed(self) -> None:
        (self.config / "configuration.nix").write_text(
            "{ ... }:\n{\n  imports = [\n  ];\n}\n", encoding="utf-8"
        )
        blocked = self.plan()
        self.assertEqual(blocked.status, "blocked")
        result = validate_home_manager_adoption(blocked, which=lambda _: None)
        self.assertEqual(result.status, "blocked")


if __name__ == "__main__":
    unittest.main()
