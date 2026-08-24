import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from nix_control_manager.catalog import load_catalog
from nix_control_manager.package_compatibility import inspect_package_compatibility


class PackageCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _flake(self) -> None:
        (self.root / "flake.nix").write_text("{ outputs = _: { }; }\n", encoding="utf-8")

    def test_missing_configuration_is_read_only_and_unknown(self) -> None:
        result = inspect_package_compatibility(self.root, which=lambda _: None)

        mapping = result.to_mapping()
        self.assertEqual(mapping["status"], "blocked")
        self.assertTrue(mapping["readOnly"])
        self.assertEqual(mapping["summary"]["unknown"], len(load_catalog()))
        self.assertEqual(mapping["summary"]["incompatible"], 0)

    def test_parses_target_specific_compatibility(self) -> None:
        self._flake()
        catalog = load_catalog()
        records = []
        for index, item in enumerate(catalog):
            records.append(
                {
                    "attribute": item["attribute"],
                    "status": "incompatible" if index == 1 else "compatible",
                    "reason": "unsupported-platform" if index == 1 else "available",
                    "unfree": index == 2,
                    "license": "unfree" if index == 2 else "MIT",
                }
            )
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"system": "x86_64-linux", "packages": records}),
            stderr="",
        )

        result = inspect_package_compatibility(
            self.root,
            flake_target="desktop",
            runner=lambda *args, **kwargs: completed,
            which=lambda _: "/run/current-system/sw/bin/nix",
        )

        mapping = result.to_mapping()
        self.assertEqual(mapping["status"], "passed")
        self.assertEqual(mapping["flakeTarget"], "desktop")
        self.assertEqual(mapping["system"], "x86_64-linux")
        self.assertEqual(mapping["summary"]["incompatible"], 1)
        self.assertEqual(mapping["summary"]["unfree"], 1)
        self.assertIn("unavailable", mapping["warnings"][0])

    def test_rejects_incomplete_or_reordered_evaluator_output(self) -> None:
        self._flake()
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"system": "x86_64-linux", "packages": []}),
            stderr="",
        )

        result = inspect_package_compatibility(
            self.root,
            flake_target="desktop",
            runner=lambda *args, **kwargs: completed,
            which=lambda _: "nix",
        )

        self.assertEqual(result.status, "failed")
        self.assertTrue(all(item.status == "unknown" for item in result.packages))
        self.assertIn("invalid", result.warnings[0])

    def test_unsafe_flake_target_never_starts_nix(self) -> None:
        self._flake()
        called = False

        def runner(*args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("runner must not be called")

        result = inspect_package_compatibility(
            self.root,
            flake_target="bad.target",
            runner=runner,
            which=lambda _: "nix",
        )

        self.assertEqual(result.status, "blocked")
        self.assertFalse(called)


if __name__ == "__main__":
    unittest.main()
