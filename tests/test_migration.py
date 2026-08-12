import unittest

from nix_control_manager.errors import ValidationError
from nix_control_manager.migration import preview_state_migration


class MigrationTests(unittest.TestCase):
    def test_current_state_does_not_require_migration(self) -> None:
        preview = preview_state_migration(
            {"schemaVersion": 1, "packages": ["firefox"], "options": {}}
        )
        self.assertEqual(preview.source_format, "current")
        self.assertFalse(preview.requires_migration)

    def test_legacy_empty_package_map_and_metadata(self) -> None:
        preview = preview_state_migration(
            {
                "schemaVersion": 1,
                "nixosRelease": "26.05",
                "generatedAt": "2026-08-10T22:12:41Z",
                "packages": {},
                "options": {},
            }
        )
        self.assertEqual(preview.source_format, "legacy-package-map")
        self.assertTrue(preview.requires_migration)
        self.assertEqual(preview.state.packages, ())
        self.assertEqual(preview.ignored_fields, ("generatedAt", "nixosRelease"))

    def test_legacy_selection_flags_are_migrated_conservatively(self) -> None:
        preview = preview_state_migration(
            {
                "packages": {
                    "firefox": True,
                    "vlc": {"enabled": True, "name": "VLC"},
                    "gimp": {"selected": False},
                    "krita": {"name": "Krita"},
                }
            }
        )
        self.assertEqual(preview.state.packages, ("firefox", "vlc"))
        self.assertTrue(any("krita" in warning for warning in preview.warnings))

    def test_rejects_unknown_schema(self) -> None:
        with self.assertRaisesRegex(ValidationError, "Unsupported schemaVersion"):
            preview_state_migration({"schemaVersion": 99, "packages": {}})


if __name__ == "__main__":
    unittest.main()
