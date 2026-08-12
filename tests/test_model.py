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


if __name__ == "__main__":
    unittest.main()
