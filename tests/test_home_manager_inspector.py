import json
from pathlib import Path
import tempfile
import unittest

from nix_control_manager.home_manager_inspector import inspect_home_manager


class HomeManagerInspectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = self.root / "etc-nixos"
        self.standalone = self.root / "home-manager"
        self.state = self.root / "user-state.json"
        self.config.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def inspect(self):
        return inspect_home_manager(
            self.config,
            standalone_root=self.standalone,
            user_state_path=self.state,
            current_user="fixture-user",
        )

    def test_detects_flake_nixos_module_users_without_evaluation(self) -> None:
        (self.config / "flake.nix").write_text(
            """
            { home-manager, ... }: {
              modules = [ home-manager.nixosModules.home-manager ];
              home-manager.users.alice = ./alice.nix;
              home-manager.users.\"bob-dev\" = { ... }: { };
            }
            """,
            encoding="utf-8",
        )
        inspection = self.inspect()
        self.assertEqual(inspection.status, "detected")
        self.assertEqual(inspection.integrations, ("nixos-module",))
        self.assertEqual([user.name for user in inspection.users], ["alice", "bob-dev"])
        self.assertFalse(inspection.to_mapping()["writeEnabled"])

    def test_detects_channel_module_and_ignores_comments(self) -> None:
        (self.config / "configuration.nix").write_text(
            """
            { ... }: {
              # home-manager.users.fake = { };
              imports = [ <home-manager/nixos> ];
              home-manager.users.carol = import ./home.nix;
            }
            """,
            encoding="utf-8",
        )
        inspection = self.inspect()
        self.assertEqual([user.name for user in inspection.users], ["carol"])

    def test_detects_standalone_root_and_valid_user_state(self) -> None:
        self.standalone.mkdir()
        (self.standalone / "flake.nix").write_text(
            "{ outputs = _: { }; }\n", encoding="utf-8"
        )
        (self.standalone / "home.nix").write_text(
            '{ ... }: { home.username = "dana"; }\n', encoding="utf-8"
        )
        self.state.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "users": {
                        "dana": {
                            "integration": "standalone",
                            "packages": [],
                            "options": {},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        inspection = self.inspect()
        self.assertEqual(inspection.integrations, ("standalone",))
        self.assertEqual(inspection.users[0].name, "dana")
        self.assertEqual(inspection.user_state.status, "current")
        self.assertEqual(len(inspection.user_state.state.users), 1)

    def test_missing_and_invalid_user_state_are_reported_without_writes(self) -> None:
        inspection = self.inspect()
        self.assertEqual(inspection.status, "not-detected")
        self.assertEqual(inspection.user_state.status, "missing")
        self.assertFalse(self.state.exists())

        self.state.write_text("not-json", encoding="utf-8")
        invalid = self.inspect()
        self.assertEqual(invalid.user_state.status, "invalid")
        self.assertTrue(invalid.warnings)

    def test_canonical_state_is_discovered_and_overrides_legacy_profile(self) -> None:
        self.standalone.mkdir()
        (self.standalone / "home.nix").write_text(
            '{ ... }: { home.username = "dana"; }\n', encoding="utf-8"
        )
        self.state.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "users": {
                        "dana": {
                            "integration": "standalone",
                            "packages": ["git"],
                            "options": {},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        canonical = self.standalone / "ncm" / "user-state.json"
        canonical.parent.mkdir()
        canonical.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "users": {
                        "dana": {
                            "integration": "standalone",
                            "packages": ["firefox"],
                            "options": {},
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        inspection = self.inspect()

        self.assertEqual(inspection.user_state.path, canonical.resolve())
        self.assertEqual(
            inspection.user_state.state.users["dana"].packages, ("firefox",)
        )
        self.assertEqual(
            inspection.user_state.sources, (canonical.resolve(), self.state.resolve())
        )
        self.assertIn("overrides legacy", inspection.user_state.warning)

    def test_conflicting_canonical_roots_fail_closed(self) -> None:
        config_state = self.config / "ncm" / "user-state.json"
        standalone_state = self.standalone / "ncm" / "user-state.json"
        config_state.parent.mkdir()
        standalone_state.parent.mkdir(parents=True)
        profile = {
            "schemaVersion": 1,
            "users": {
                "alice": {
                    "integration": "nixos-module",
                    "packages": ["git"],
                    "options": {},
                }
            },
        }
        config_state.write_text(json.dumps(profile), encoding="utf-8")
        profile["users"]["alice"]["packages"] = ["firefox"]
        standalone_state.write_text(json.dumps(profile), encoding="utf-8")

        inspection = self.inspect()

        self.assertEqual(inspection.user_state.status, "invalid")
        self.assertIn("Conflicting canonical profiles", inspection.user_state.warning)


if __name__ == "__main__":
    unittest.main()
