from pathlib import Path
import subprocess
import tempfile
import unittest

from nix_control_manager.managed_plan import (
    MANAGED_MODULE_PATH,
    MANAGED_STATE_PATH,
    managed_plan_identity,
    plan_managed_state,
    validate_managed_state,
)
from nix_control_manager.model import ManagedState
from nix_control_manager.nix_generator import generate_module
from nix_control_manager.storage import serialize_state


class ManagedPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "etc" / "nixos"
        (self.root / "ncm").mkdir(parents=True)
        (self.root / "configuration.nix").write_text(
            "{ ... }: { imports = [ ./ncm ]; }\n", encoding="utf-8"
        )
        initial = ManagedState.empty()
        (self.root / MANAGED_STATE_PATH).write_text(
            serialize_state(initial), encoding="utf-8"
        )
        (self.root / MANAGED_MODULE_PATH).write_text(
            generate_module(initial), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_plan_is_canonical_and_limited_to_two_owned_files(self) -> None:
        state = ManagedState.from_mapping(
            {"schemaVersion": 1, "packages": ["git", "firefox"], "options": {}}
        )
        plan = plan_managed_state(self.root, state)
        self.assertEqual(
            {change.relative_path for change in plan.changes},
            {MANAGED_STATE_PATH, MANAGED_MODULE_PATH},
        )
        changes = {change.relative_path: change for change in plan.changes}
        self.assertEqual(changes[MANAGED_STATE_PATH].candidate, serialize_state(state))
        self.assertEqual(changes[MANAGED_MODULE_PATH].candidate, generate_module(state))
        self.assertIn("pkgs.firefox", plan.combined_diff)
        fingerprint, digests = managed_plan_identity(plan)
        self.assertEqual(len(fingerprint), 64)
        self.assertEqual(len(digests), 2)
        self.assertFalse((self.root / MANAGED_STATE_PATH).read_text(encoding="utf-8").find("git") >= 0)

    def test_disposable_validation_evaluates_without_build_or_activation(self) -> None:
        state = ManagedState.from_mapping(
            {"schemaVersion": 1, "packages": ["git"], "options": {}}
        )
        calls = []

        def runner(command, **kwargs):
            calls.append(tuple(command))
            return subprocess.CompletedProcess(command, 0, "/nix/store/test.drv\n", "")

        result = validate_managed_state(
            self.root,
            state,
            runner=runner,
            which=lambda name: f"/bin/{name}" if name == "nix-instantiate" else None,
        )
        self.assertEqual(result.status, "passed")
        self.assertTrue(result.working_copy_removed)
        self.assertEqual(len(result.candidate_files), 2)
        flattened = " ".join(part for command in calls for part in command)
        self.assertNotIn("nixos-rebuild", flattened)
        self.assertNotIn("switch", flattened)
        self.assertNotIn("--build", flattened)


if __name__ == "__main__":
    unittest.main()
