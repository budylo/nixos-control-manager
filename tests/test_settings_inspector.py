import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from nix_control_manager.catalog import load_settings_catalog
from nix_control_manager.settings_inspector import inspect_effective_settings


class SettingsInspectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "etc-nixos"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _document(definition_files=None):
        records = []
        for index, definition in enumerate(load_settings_catalog()):
            records.append(
                {
                    "path": definition["path"],
                    "available": True,
                    "value": index,
                    "definitionFiles": (
                        definition_files[index]
                        if definition_files and index < len(definition_files)
                        else [f"/nix/store/source/{definition['path']}.nix"]
                    ),
                    "declarationFiles": ["/nix/store/source/declaration.nix"],
                }
            )
        return {"settings": records}

    def test_channels_evaluation_is_fixed_read_only_and_classifies_sources(self) -> None:
        (self.root / "configuration.nix").write_text("{ ... }: { }\n", encoding="utf-8")
        output = self.root / "ncm" / "managed.nix"
        sources = [
            [str(output)],
            [str(output), "/etc/nixos/configuration.nix"],
        ]
        captured = {}

        def runner(command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(
                command, 0, stdout=json.dumps(self._document(sources)), stderr=""
            )

        result = inspect_effective_settings(
            self.root,
            output_path=output,
            runner=runner,
            which=lambda name: "/run/current-system/sw/bin/nix" if name == "nix" else None,
        )

        self.assertEqual(result.status, "passed")
        self.assertEqual(result.configuration_mode, "channels")
        self.assertEqual(result.settings[0].ownership, "managed")
        self.assertEqual(result.settings[1].ownership, "shared")
        self.assertEqual(result.settings[2].ownership, "inherited")
        command = captured["command"]
        self.assertIn("--no-write-lock-file", command)
        self.assertIn("allow-import-from-derivation", command)
        self.assertNotIn("build", command)
        self.assertNotIn("switch", command)
        self.assertNotIn(str(self.root), command)
        environment = captured["kwargs"]["env"]
        self.assertEqual(environment["NCM_INSPECT_CONFIG_ROOT"], str(self.root.resolve()))
        self.assertEqual(environment["NCM_INSPECT_MODE"], "channels")

    def test_flake_target_rejects_unsafe_value(self) -> None:
        (self.root / "flake.nix").write_text("{ outputs = _: { }; }\n", encoding="utf-8")
        result = inspect_effective_settings(
            self.root,
            output_path=self.root / "managed.nix",
            flake_target="bad.target",
            runner=lambda *args, **kwargs: self.fail("runner must not be called"),
            which=lambda name: "/bin/nix",
        )
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.flake_target, "bad.target")
        self.assertTrue(all(not setting.available for setting in result.settings))

    def test_missing_nix_is_reported_without_evaluation(self) -> None:
        (self.root / "configuration.nix").write_text("{ ... }: { }\n", encoding="utf-8")
        result = inspect_effective_settings(
            self.root,
            output_path=self.root / "managed.nix",
            which=lambda name: None,
        )
        self.assertEqual(result.status, "unavailable")
        self.assertIn("unavailable", result.warnings[0])

    def test_invalid_evaluator_document_fails_closed(self) -> None:
        (self.root / "configuration.nix").write_text("{ ... }: { }\n", encoding="utf-8")
        result = inspect_effective_settings(
            self.root,
            output_path=self.root / "managed.nix",
            runner=lambda command, **kwargs: subprocess.CompletedProcess(
                command, 0, stdout='{"settings": []}', stderr=""
            ),
            which=lambda name: "/bin/nix",
        )
        self.assertEqual(result.status, "failed")
        self.assertTrue(all(not setting.available for setting in result.settings))


if __name__ == "__main__":
    unittest.main()
