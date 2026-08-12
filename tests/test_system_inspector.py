from pathlib import Path
import tempfile
import unittest

from nix_control_manager.system_inspector import inspect_system


class SystemInspectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.os_release = self.root / "os-release"
        self.hostname = self.root / "hostname"
        self.config_root = self.root / "etc-nixos"
        self.config_root.mkdir()
        self.os_release.write_text(
            'ID=nixos\nNAME="NixOS"\nVERSION_ID="26.05"\n', encoding="utf-8"
        )
        self.hostname.write_text("test-host\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def inspect(self):
        return inspect_system(
            self.config_root,
            os_release_path=self.os_release,
            hostname_path=self.hostname,
        )

    def test_detects_connected_channel_configuration_and_legacy_state(self) -> None:
        (self.config_root / "configuration.nix").write_text(
            "{ ... }: { imports = [ ./ncm ]; }\n", encoding="utf-8"
        )
        managed = self.config_root / "ncm"
        managed.mkdir()
        (managed / "default.nix").write_text("{ ... }: { }\n", encoding="utf-8")
        (managed / "state.json").write_text(
            '{"schemaVersion":1,"nixosRelease":"26.05","packages":{},"options":{}}',
            encoding="utf-8",
        )

        inspection = self.inspect()

        self.assertTrue(inspection.is_nixos)
        self.assertEqual(inspection.release, "26.05")
        self.assertEqual(inspection.hostname, "test-host")
        self.assertEqual(inspection.configuration_mode, "channels")
        self.assertEqual(inspection.managed_status, "connected")
        self.assertEqual(inspection.imported_by, ("configuration.nix",))
        self.assertEqual(inspection.state_status, "migration-available")

    def test_flake_takes_precedence_and_comments_do_not_count_as_import(self) -> None:
        (self.config_root / "flake.nix").write_text("{ outputs = _: { }; }\n", encoding="utf-8")
        (self.config_root / "configuration.nix").write_text(
            "{ ... }: { # imports = [ ./ncm ];\n}\n", encoding="utf-8"
        )
        (self.config_root / "ncm").mkdir()

        inspection = self.inspect()

        self.assertEqual(inspection.configuration_mode, "flake")
        self.assertEqual(inspection.managed_status, "present-not-imported")
        self.assertEqual(inspection.state_status, "missing")

    def test_invalid_state_is_reported_without_raising(self) -> None:
        (self.config_root / "configuration.nix").write_text(
            "{ ... }: { imports = [ ./ncm ]; }\n", encoding="utf-8"
        )
        managed = self.config_root / "ncm"
        managed.mkdir()
        (managed / "state.json").write_text("not-json", encoding="utf-8")

        inspection = self.inspect()

        self.assertEqual(inspection.state_status, "invalid")
        self.assertTrue(inspection.warnings)


if __name__ == "__main__":
    unittest.main()
