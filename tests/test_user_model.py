import unittest

from nix_control_manager.errors import ValidationError
from nix_control_manager.user_model import UserManagedState


class UserManagedStateTests(unittest.TestCase):
    def test_empty_state_is_separate_and_versioned(self) -> None:
        self.assertEqual(
            UserManagedState.empty().to_mapping(),
            {"schemaVersion": 1, "users": {}},
        )

    def test_normalizes_user_packages_and_options(self) -> None:
        state = UserManagedState.from_mapping(
            {
                "schemaVersion": 1,
                "users": {
                    "alice@laptop": {
                        "integration": "nixos-module",
                        "packages": ["git", "firefox", "git"],
                        "options": {
                            "programs.git.enable": True,
                            "home.sessionVariables": {"EDITOR": "vim"},
                        },
                    }
                },
            }
        )
        profile = state.users["alice@laptop"]
        self.assertEqual(profile.packages, ("firefox", "git"))
        self.assertTrue(profile.options["programs.git.enable"])

    def test_rejects_invalid_users_profiles_and_future_schema(self) -> None:
        cases = (
            ({"schemaVersion": 2}, "schemaVersion"),
            ({"users": {"Alice!": {"integration": "standalone"}}}, "user name"),
            ({"users": {"alice": {"integration": "other"}}}, "integration"),
            (
                {
                    "users": {
                        "alice": {
                            "integration": "standalone",
                            "packages": ["git; builtins.abort"],
                        }
                    }
                },
                "dot-separated",
            ),
            (
                {
                    "users": {
                        "alice": {
                            "integration": "standalone",
                            "options": {"home.packages": []},
                        }
                    }
                },
                "packages field",
            ),
        )
        for raw, message in cases:
            with self.subTest(raw=raw), self.assertRaisesRegex(ValidationError, message):
                UserManagedState.from_mapping(raw)


if __name__ == "__main__":
    unittest.main()
