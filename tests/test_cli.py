from __future__ import annotations

import io
import unittest
from unittest.mock import Mock, patch

from nix_control_manager.cli import main


class CliTests(unittest.TestCase):
    def test_keyboard_interrupt_is_a_clean_shutdown(self) -> None:
        parser = Mock()
        parser.parse_args.return_value = Mock()

        with (
            patch("nix_control_manager.cli.build_parser", return_value=parser),
            patch("nix_control_manager.cli.run", side_effect=KeyboardInterrupt),
            patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            result = main([])

        self.assertEqual(result, 0)
        self.assertIn("Stopped.", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
