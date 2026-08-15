from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest

from nix_control_manager.candidate_build import (
    BuildPreviewError,
    HomeManagerBuildManager,
)
from nix_control_manager.home_manager_adoption import (
    home_manager_plan_identity,
    plan_home_manager_adoption,
)


class HomeManagerBuildManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.config = self.base / "etc-nixos"
        self.standalone = self.base / "home-manager"
        self.state = self.base / "user-state.json"
        self.config.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def fake_which(name: str) -> str:
        return f"/tools/{name}"

    @staticmethod
    def wait_for_terminal(manager: HomeManagerBuildManager, job_id: str) -> dict:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = manager.poll(job_id)
            if not result["cancellable"]:
                return result
            time.sleep(0.01)
        raise AssertionError("Home Manager build-preview job did not finish")

    def create_standalone_flake(self) -> str:
        self.standalone.mkdir()
        home = (
            '{ ... }:\n{\n  home.username = "alice";\n'
            '  home.stateVersion = "26.05";\n}\n'
        )
        (self.standalone / "home.nix").write_text(home, encoding="utf-8")
        (self.standalone / "flake.nix").write_text(
            '{ outputs = _: { homeConfigurations.alice = null; }; }\n',
            encoding="utf-8",
        )
        return home

    def standalone_plan(self):
        return plan_home_manager_adoption(
            self.config,
            standalone_root=self.standalone,
            user_state_path=self.state,
            username="alice",
            integration="standalone",
            packages=("firefox", "git"),
        )

    def manager(self, *, executor, validator, **kwargs):
        return HomeManagerBuildManager(
            config_root=self.config,
            standalone_root=self.standalone,
            user_state_path=self.state,
            executor=executor,
            validator=validator,
            which=self.fake_which,
            path_is_dir=lambda _: True,
            **kwargs,
        )

    def test_standalone_flake_builds_exact_activation_package_without_activation(self) -> None:
        original = self.create_standalone_flake()
        plan = self.standalone_plan()
        fingerprint, _ = home_manager_plan_identity(plan, None)
        commands: list[tuple[str, ...]] = []
        candidate_roots: list[Path] = []

        def validator(candidate, **kwargs):
            self.assertTrue(candidate.safe_to_validate)
            candidate_fingerprint, _ = home_manager_plan_identity(candidate, None)
            return SimpleNamespace(
                status="passed",
                flake_target=None,
                plan_fingerprint=candidate_fingerprint,
                working_copy_removed=True,
            )

        def executor(command, cwd, cancel_event, line_sink):
            commands.append(tuple(command))
            candidate_roots.append(cwd)
            self.assertIn(
                "managed-home-alice.nix",
                (cwd / "home.nix").read_text(encoding="utf-8"),
            )
            output = "/nix/store/" + "a" * 32 + "-home-manager-generation"
            line_sink("stdout", output)
            return 0, (output,)

        manager = self.manager(executor=executor, validator=validator)
        started = manager.start(
            username="alice",
            integration="standalone",
            packages=("firefox", "git"),
            plan_fingerprint=fingerprint,
        )
        result = self.wait_for_terminal(manager, started["jobId"])
        manager.close()

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["workflow"], "home-manager")
        self.assertIn('.#homeConfigurations."alice".activationPackage', commands[0])
        self.assertIn("--no-link", commands[0])
        self.assertIn("--no-write-lock-file", commands[0])
        self.assertNotIn("home-manager switch", " ".join(commands[0]))
        self.assertEqual(result["activationPackagePath"], result["outputPaths"][0])
        self.assertFalse(result["configurationWriteEnabled"])
        self.assertFalse(result["homeManagerActivationEnabled"])
        self.assertFalse(result["activationPreviewReady"])
        self.assertTrue(result["workingCopyRemoved"])
        self.assertTrue(all(not path.exists() for path in candidate_roots))
        self.assertEqual((self.standalone / "home.nix").read_text(encoding="utf-8"), original)
        self.assertFalse((self.standalone / "ncm").exists())

    def test_changed_fingerprint_is_blocked_before_nix_build(self) -> None:
        self.create_standalone_flake()
        def validator(candidate, **kwargs):
            candidate_fingerprint, _ = home_manager_plan_identity(candidate, None)
            return SimpleNamespace(
                status="passed",
                flake_target=None,
                plan_fingerprint=candidate_fingerprint,
                working_copy_removed=True,
            )

        manager = self.manager(
            executor=lambda *args: self.fail("executor must not run"),
            validator=validator,
        )
        started = manager.start(
            username="alice",
            integration="standalone",
            packages=("firefox",),
            plan_fingerprint="0" * 64,
        )
        result = self.wait_for_terminal(manager, started["jobId"])
        manager.close()

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error"]["code"], "plan-fingerprint-mismatch")
        self.assertEqual(result["expectedPlanFingerprint"], "0" * 64)

    def test_nixos_flake_uses_fixed_user_activation_attribute(self) -> None:
        (self.config / "flake.nix").write_text(
            '{ outputs = _: { nixosConfigurations.desktop = null; }; }\n',
            encoding="utf-8",
        )
        (self.config / "configuration.nix").write_text(
            "{ ... }:\n{\n  imports = [\n  ];\n  home-manager.users.alice = ./alice.nix;\n}\n",
            encoding="utf-8",
        )
        plan = plan_home_manager_adoption(
            self.config,
            standalone_root=self.standalone,
            user_state_path=self.state,
            username="alice",
            integration="nixos-module",
            packages=("git",),
        )
        fingerprint, _ = home_manager_plan_identity(plan, "desktop")
        commands: list[tuple[str, ...]] = []

        def executor(command, cwd, cancel_event, line_sink):
            commands.append(tuple(command))
            output = "/nix/store/" + "b" * 32 + "-home-manager-generation"
            return 0, (output,)

        def validator(candidate, **kwargs):
            candidate_fingerprint, _ = home_manager_plan_identity(
                candidate, "desktop"
            )
            return SimpleNamespace(
                status="passed",
                flake_target="desktop",
                plan_fingerprint=candidate_fingerprint,
                working_copy_removed=True,
            )

        manager = self.manager(
            executor=executor,
            validator=validator,
            flake_target="desktop",
        )
        started = manager.start(
            username="alice",
            integration="nixos-module",
            packages=("git",),
            plan_fingerprint=fingerprint,
        )
        result = self.wait_for_terminal(manager, started["jobId"])
        manager.close()

        self.assertEqual(result["status"], "passed")
        self.assertIn(
            '.#nixosConfigurations.desktop.config.home-manager.users."alice".home.activationPackage',
            commands[0],
        )

    def test_cancel_and_root_rejection_fail_closed(self) -> None:
        self.create_standalone_flake()
        plan = self.standalone_plan()
        fingerprint, _ = home_manager_plan_identity(plan, None)
        entered = threading.Event()

        def executor(command, cwd, cancel_event, line_sink):
            entered.set()
            self.assertTrue(cancel_event.wait(timeout=3))
            return 143, ()

        def validator(candidate, **kwargs):
            candidate_fingerprint, _ = home_manager_plan_identity(candidate, None)
            return SimpleNamespace(
                status="passed",
                flake_target=None,
                plan_fingerprint=candidate_fingerprint,
                working_copy_removed=True,
            )
        manager = self.manager(executor=executor, validator=validator)
        started = manager.start(
            username="alice",
            integration="standalone",
            packages=("firefox", "git"),
            plan_fingerprint=fingerprint,
        )
        self.assertTrue(entered.wait(timeout=2))
        with self.assertRaises(BuildPreviewError):
            manager.start(
                username="alice",
                integration="standalone",
                packages=("firefox", "git"),
                plan_fingerprint=fingerprint,
            )
        manager.cancel(started["jobId"])
        result = self.wait_for_terminal(manager, started["jobId"])
        manager.close()
        self.assertEqual(result["status"], "cancelled")

        root_manager = self.manager(
            executor=lambda *args: self.fail("executor must not run as root"),
            validator=validator,
            effective_uid=lambda: 0,
        )
        root_job = root_manager.start(
            username="alice",
            integration="standalone",
            packages=("firefox", "git"),
            plan_fingerprint=fingerprint,
        )
        root_result = self.wait_for_terminal(root_manager, root_job["jobId"])
        root_manager.close()
        self.assertEqual(root_result["status"], "blocked")
        self.assertEqual(root_result["error"]["code"], "privileged-execution")


if __name__ == "__main__":
    unittest.main()
