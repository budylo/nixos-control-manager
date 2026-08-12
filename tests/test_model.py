import unittest

from nix_control_manager.errors import ValidationError
from nix_control_manager.model import ManagedState


class ManagedStateTests(unittest.TestCase):
    def test_normalizes_packages_and_options(self) -> None:
        state = ManagedState.from_mapping(
            {
                "schemaVersion": 1,
                "packages": ["vlc", "firefox", "vlc", "kdePackages.kate"],
                "options": {"programs.steam.enable": True},
            }
        )

        self.assertEqual(state.packages, ("firefox", "kdePackages.kate", "vlc"))
        self.assertEqual(state.options, {"programs.steam.enable": True})

    def test_rejects_invalid_package_expression(self) -> None:
        with self.assertRaisesRegex(ValidationError, "dot-separated"):
            ManagedState.from_mapping({"packages": ["firefox; builtins.abort"]})

    def test_rejects_unknown_fields(self) -> None:
        with self.assertRaisesRegex(ValidationError, "unknown fields"):
            ManagedState.from_mapping({"packages": [], "command": "rm -rf /"})

    def test_rejects_future_schema(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Unsupported schemaVersion"):
            ManagedState.from_mapping({"schemaVersion": 2})

    def test_known_settings_use_catalog_types_and_normalization(self) -> None:
        state = ManagedState.from_mapping(
            {
                "options": {
                    "networking.firewall.allowedTCPPorts": [443, 80, 443],
                    "services.pipewire.enable": True,
                }
            }
        )
        self.assertEqual(
            state.options["networking.firewall.allowedTCPPorts"], [443, 80]
        )
        with self.assertRaisesRegex(ValidationError, "must be boolean"):
            ManagedState.from_mapping(
                {"options": {"services.pipewire.enable": "enabled"}}
            )

    def test_rejects_explicit_managed_dependency_contradiction(self) -> None:
        with self.assertRaisesRegex(ValidationError, "requires services.pipewire.enable"):
            ManagedState.from_mapping(
                {
                    "options": {
                        "services.pipewire.enable": False,
                        "services.pipewire.pulse.enable": True,
                    }
                }
            )

        inherited_parent = ManagedState.from_mapping(
            {"options": {"services.pipewire.pulse.enable": True}}
        )
        self.assertEqual(inherited_parent.options["services.pipewire.pulse.enable"], True)


if __name__ == "__main__":
    unittest.main()
