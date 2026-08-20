from pathlib import Path
import tempfile
import unittest

from nix_control_manager.generation_inspector import inspect_generations


class GenerationInspectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.profiles = self.root / "profiles"
        self.run = self.root / "run"
        self.store = self.root / "nix" / "store"
        self.profiles.mkdir(parents=True)
        self.run.mkdir()
        self.store.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def system(self, digest: str, name: str, version: str) -> Path:
        path = self.store / f"{digest}-{name}"
        path.mkdir()
        (path / "nixos-version").write_text(version + "\n", encoding="utf-8")
        return path

    def link(self, source: Path, destination: Path) -> None:
        try:
            destination.symlink_to(source, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symbolic links are unavailable: {error}")

    def test_reports_profile_runtime_and_booted_roles(self) -> None:
        first = self.system("a" * 32, "nixos-system-host-1", "25.11")
        second = self.system("b" * 32, "nixos-system-host-2", "26.05")
        self.link(first, self.profiles / "system-1-link")
        self.link(second, self.profiles / "system-2-link")
        self.link(self.profiles / "system-2-link", self.profiles / "system")
        self.link(second, self.run / "current-system")
        self.link(first, self.run / "booted-system")

        result = inspect_generations(
            profiles_root=self.profiles,
            current_system=self.run / "current-system",
            booted_system=self.run / "booted-system",
            store_root=self.store,
        ).to_mapping()

        self.assertEqual(result["status"], "detected")
        self.assertEqual([item["number"] for item in result["generations"]], [2, 1])
        self.assertTrue(result["generations"][0]["currentProfile"])
        self.assertTrue(result["generations"][0]["currentRuntime"])
        self.assertTrue(result["generations"][1]["booted"])
        self.assertEqual(result["generations"][0]["nixosVersion"], "26.05")
        self.assertTrue(result["readOnly"])
        self.assertFalse(result["switchEnabled"])
        self.assertFalse(result["rollbackEnabled"])

    def test_ignores_broken_and_non_generation_links(self) -> None:
        self.link(self.store / ("c" * 32 + "-missing"), self.profiles / "system-4-link")
        (self.profiles / "system-3-link").mkdir()
        self.link(self.store, self.profiles / "user-1-link")

        result = inspect_generations(
            profiles_root=self.profiles,
            current_system=self.run / "current-system",
            booted_system=self.run / "booted-system",
            store_root=self.store,
        ).to_mapping()

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["generations"], [])
        self.assertTrue(any("system-4-link" in warning for warning in result["warnings"]))

    def test_missing_profile_directory_is_safe(self) -> None:
        result = inspect_generations(
            profiles_root=self.root / "missing",
            current_system=self.run / "current-system",
            booted_system=self.run / "booted-system",
            store_root=self.store,
        ).to_mapping()
        self.assertEqual(result["status"], "unavailable")
        self.assertTrue(result["warnings"])


if __name__ == "__main__":
    unittest.main()
