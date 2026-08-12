from pathlib import Path
import tempfile
import unittest

from nix_control_manager.model import ManagedState
from nix_control_manager.preview import build_preview
from nix_control_manager.storage import load_state, save_generated_module, save_state


class StorageTests(unittest.TestCase):
    def test_state_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            expected = ManagedState.from_mapping({"packages": ["firefox"]})
            save_state(path, expected)
            self.assertEqual(load_state(path), expected)

    def test_generated_module_creates_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "managed.nix"
            save_generated_module(path, "first\n")
            save_generated_module(path, "second\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "second\n")
            self.assertEqual(
                path.with_name("managed.nix.bak").read_text(encoding="utf-8"),
                "first\n",
            )

    def test_preview_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "managed.nix"
            preview = build_preview(
                ManagedState.from_mapping({"packages": ["vlc"]}), path
            )
            self.assertFalse(path.exists())
            self.assertIn("pkgs.vlc", preview["generated"])
            self.assertIn("candidate", preview["diff"])
            self.assertIn("--- managed.nix", preview["diff"])
            self.assertNotIn(str(path.parent), preview["diff"])


if __name__ == "__main__":
    unittest.main()
