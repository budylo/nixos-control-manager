import json
from pathlib import Path
import tempfile
import unittest

from nix_control_manager.helper_daemon import (
    HelperConfigurationError,
    HelperDaemonConfig,
)
from nix_control_manager.transaction import initialize_transaction_fixture


class HelperDaemonConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.fixture = root / "fixture"
        self.journal = root / "journal"
        self.socket = root / "run" / "helper.sock"
        self.pkcheck = root / "pkcheck"
        self.pkcheck.write_text("placeholder\n", encoding="utf-8")
        initialize_transaction_fixture(self.fixture)
        self.config_path = root / "helper.json"
        self.raw = {
            "schemaVersion": 1,
            "socketPath": str(self.socket),
            "polkitExecutable": str(self.pkcheck),
            "validationTimeout": 120,
            "targets": [
                {
                    "targetId": "fixture",
                    "configurationRoot": str(self.fixture),
                    "journalRoot": str(self.journal),
                    "allowedRelativePaths": ["configuration.nix", "ncm/state.json"],
                    "fixtureOnly": True,
                    "flakeTarget": None,
                }
            ],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, raw: dict) -> None:
        self.config_path.write_text(json.dumps(raw), encoding="utf-8")

    def test_loads_one_strict_fixture_target(self) -> None:
        self.write(self.raw)

        config = HelperDaemonConfig.load(self.config_path)

        self.assertEqual(config.socket_path, self.socket.resolve())
        self.assertEqual(config.targets[0].configuration_root, self.fixture.resolve())
        self.assertTrue(config.targets[0].fixture_only)

    def test_rejects_unknown_fields_and_non_fixture_target(self) -> None:
        unknown = dict(self.raw)
        unknown["extra"] = True
        self.write(unknown)
        with self.assertRaises(HelperConfigurationError):
            HelperDaemonConfig.load(self.config_path)

        non_fixture = json.loads(json.dumps(self.raw))
        non_fixture["targets"][0]["fixtureOnly"] = False
        self.write(non_fixture)
        with self.assertRaisesRegex(HelperConfigurationError, "fixtureOnly"):
            HelperDaemonConfig.load(self.config_path)

    def test_rejects_live_nixos_and_nested_journal(self) -> None:
        live = json.loads(json.dumps(self.raw))
        live["targets"][0]["configurationRoot"] = "/etc/nixos"
        self.write(live)
        with self.assertRaises(HelperConfigurationError):
            HelperDaemonConfig.load(self.config_path)

        nested = json.loads(json.dumps(self.raw))
        nested["targets"][0]["journalRoot"] = str(self.fixture / "journal")
        self.write(nested)
        with self.assertRaisesRegex(HelperConfigurationError, "outside"):
            HelperDaemonConfig.load(self.config_path)

    def test_schema_v2_loads_live_read_only_without_fixture_marker(self) -> None:
        live = Path(self.temporary.name) / "live-configuration"
        live.mkdir()
        raw = json.loads(json.dumps(self.raw))
        raw["schemaVersion"] = 2
        raw["targets"] = [
            {
                "targetId": "live",
                "mode": "live-read-only",
                "configurationRoot": str(live),
                "journalRoot": None,
                "allowedRelativePaths": [
                    "configuration.nix",
                    "ncm/state.json",
                ],
                "flakeTarget": None,
            }
        ]
        self.write(raw)

        config = HelperDaemonConfig.load(self.config_path)

        target = config.targets[0]
        self.assertEqual(target.configuration_root, live.resolve())
        self.assertFalse(target.fixture_only)
        self.assertFalse(target.apply_enabled)
        self.assertIsNone(target.journal_root)

    def test_schema_v5_loads_only_exact_live_managed_scope(self) -> None:
        live = Path(self.temporary.name) / "etc" / "nixos"
        live.mkdir(parents=True)
        raw = {
            **{key: value for key, value in self.raw.items() if key != "targets"},
            "schemaVersion": 5,
            "targets": [
                {
                    "targetId": "managed",
                    "mode": "live-managed",
                    "configurationRoot": str(live),
                    "journalRoot": None,
                    "testJournalRoot": None,
                    "testTimeoutSeconds": 300,
                    "homeManagerRoot": None,
                    "homeManagerJournalRoot": None,
                    "managedJournalRoot": str(Path(self.temporary.name) / "managed-journal"),
                    "allowedRelativePaths": [
                        "ncm/state.json",
                        "ncm/packages.nix",
                    ],
                    "flakeTarget": None,
                }
            ],
        }
        self.write(raw)
        target = HelperDaemonConfig.load(self.config_path).targets[0]
        self.assertTrue(target.managed_write_enabled)
        self.assertFalse(target.apply_enabled)
        self.assertEqual(
            target.allowed_relative_paths,
            frozenset({"ncm/state.json", "ncm/packages.nix"}),
        )

        raw["targets"][0]["allowedRelativePaths"].append("configuration.nix")
        self.write(raw)
        with self.assertRaisesRegex(HelperConfigurationError, "two-file"):
            HelperDaemonConfig.load(self.config_path)

    def test_schema_v6_combines_only_exact_managed_test_and_switch_scope(self) -> None:
        live = Path(self.temporary.name) / "etc" / "nixos"
        live.mkdir(parents=True)
        raw = {
            **{key: value for key, value in self.raw.items() if key != "targets"},
            "schemaVersion": 6,
            "targets": [
                {
                    "targetId": "control",
                    "mode": "live-control",
                    "configurationRoot": str(live),
                    "journalRoot": None,
                    "testJournalRoot": str(Path(self.temporary.name) / "test-journal"),
                    "testTimeoutSeconds": 300,
                    "homeManagerRoot": None,
                    "homeManagerJournalRoot": None,
                    "managedJournalRoot": str(Path(self.temporary.name) / "managed-journal"),
                    "allowedRelativePaths": ["ncm/state.json", "ncm/packages.nix"],
                    "flakeTarget": None,
                }
            ],
        }
        self.write(raw)
        target = HelperDaemonConfig.load(self.config_path).targets[0]
        self.assertTrue(target.test_activation_enabled)
        self.assertTrue(target.managed_write_enabled)
        self.assertTrue(target.permanent_switch_enabled)
        self.assertFalse(target.apply_enabled)

        raw["targets"][0]["testJournalRoot"] = raw["targets"][0]["managedJournalRoot"]
        self.write(raw)
        with self.assertRaisesRegex(HelperConfigurationError, "separate"):
            HelperDaemonConfig.load(self.config_path)

    def test_schema_v7_adds_only_an_explicit_separate_flake_lock_journal(self) -> None:
        live = Path(self.temporary.name) / "etc" / "nixos"
        live.mkdir(parents=True, exist_ok=True)
        raw = {
            **{key: value for key, value in self.raw.items() if key != "targets"},
            "schemaVersion": 7,
            "targets": [
                {
                    "targetId": "control",
                    "mode": "live-control",
                    "configurationRoot": str(live),
                    "journalRoot": None,
                    "testJournalRoot": str(Path(self.temporary.name) / "test-journal"),
                    "testTimeoutSeconds": 300,
                    "homeManagerRoot": None,
                    "homeManagerJournalRoot": None,
                    "managedJournalRoot": str(Path(self.temporary.name) / "managed-journal"),
                    "flakeLockJournalRoot": str(Path(self.temporary.name) / "flake-journal"),
                    "allowedRelativePaths": ["ncm/state.json", "ncm/packages.nix"],
                    "flakeTarget": "desktop",
                }
            ],
        }
        self.write(raw)
        target = HelperDaemonConfig.load(self.config_path).targets[0]
        self.assertTrue(target.flake_lock_write_enabled)
        self.assertEqual(target.flake_lock_journal_root, Path(self.temporary.name) / "flake-journal")

        raw["targets"][0]["flakeLockJournalRoot"] = raw["targets"][0]["managedJournalRoot"]
        self.write(raw)
        with self.assertRaisesRegex(HelperConfigurationError, "separate"):
            HelperDaemonConfig.load(self.config_path)

    def test_schema_v2_rejects_writable_live_target_shapes(self) -> None:
        raw = json.loads(json.dumps(self.raw))
        raw["schemaVersion"] = 2
        raw["targets"] = [
            {
                "targetId": "live",
                "mode": "live-read-only",
                "configurationRoot": str(self.fixture),
                "journalRoot": str(self.journal),
                "allowedRelativePaths": ["configuration.nix"],
                "flakeTarget": None,
            }
        ]
        self.write(raw)
        with self.assertRaisesRegex(HelperConfigurationError, "journalRoot to null"):
            HelperDaemonConfig.load(self.config_path)

        raw["targets"][0]["journalRoot"] = None
        raw["targets"][0]["mode"] = "live-write"
        self.write(raw)
        with self.assertRaisesRegex(HelperConfigurationError, "target mode"):
            HelperDaemonConfig.load(self.config_path)

    def test_schema_v2_keeps_fixture_marker_requirement(self) -> None:
        raw = json.loads(json.dumps(self.raw))
        raw["schemaVersion"] = 2
        raw["targets"] = [
            {
                "targetId": "fixture",
                "mode": "fixture",
                "configurationRoot": str(Path(self.temporary.name) / "unmarked"),
                "journalRoot": str(self.journal),
                "allowedRelativePaths": ["configuration.nix"],
                "flakeTarget": None,
            }
        ]
        self.write(raw)
        with self.assertRaises(HelperConfigurationError):
            HelperDaemonConfig.load(self.config_path)

    def test_schema_v3_live_test_requires_a_separate_journal(self) -> None:
        live = Path(self.temporary.name) / "live-configuration"
        live.mkdir()
        test_journal = Path(self.temporary.name) / "test-activations"
        raw = json.loads(json.dumps(self.raw))
        raw["schemaVersion"] = 3
        raw["targets"] = [
            {
                "targetId": "live-test",
                "mode": "live-test",
                "configurationRoot": str(live),
                "journalRoot": None,
                "testJournalRoot": str(test_journal),
                "testTimeoutSeconds": 60,
                "allowedRelativePaths": ["configuration.nix"],
                "flakeTarget": None,
            }
        ]
        self.write(raw)

        target = HelperDaemonConfig.load(self.config_path).targets[0]

        self.assertFalse(target.apply_enabled)
        self.assertTrue(target.test_activation_enabled)
        self.assertEqual(target.test_journal_root, test_journal.resolve())
        self.assertEqual(target.test_timeout_seconds, 60)

        raw["targets"][0]["testJournalRoot"] = None
        self.write(raw)
        with self.assertRaises(HelperConfigurationError):
            HelperDaemonConfig.load(self.config_path)

    def test_schema_v4_live_home_manager_is_separate_from_system_apply(self) -> None:
        live = Path(self.temporary.name) / "live-home-manager"
        live.mkdir()
        home_journal = Path(self.temporary.name) / "home-manager-journal"
        raw = json.loads(json.dumps(self.raw))
        raw["schemaVersion"] = 4
        raw["targets"] = [
            {
                "targetId": "live-home",
                "mode": "live-home-manager",
                "configurationRoot": str(live),
                "journalRoot": None,
                "testJournalRoot": None,
                "testTimeoutSeconds": 300,
                "homeManagerRoot": str(live),
                "homeManagerJournalRoot": str(home_journal),
                "allowedRelativePaths": ["ncm/user-state.json"],
                "flakeTarget": None,
            }
        ]
        self.write(raw)

        target = HelperDaemonConfig.load(self.config_path).targets[0]

        self.assertFalse(target.fixture_only)
        self.assertFalse(target.apply_enabled)
        self.assertFalse(target.test_activation_enabled)
        self.assertTrue(target.home_manager_apply_enabled)
        self.assertEqual(target.home_manager_root, live.resolve())
        self.assertEqual(target.home_manager_journal_root, home_journal.resolve())

        raw["targets"][0]["homeManagerJournalRoot"] = str(live / "journal")
        self.write(raw)
        with self.assertRaisesRegex(HelperConfigurationError, "outside"):
            HelperDaemonConfig.load(self.config_path)


if __name__ == "__main__":
    unittest.main()
