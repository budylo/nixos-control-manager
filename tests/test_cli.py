from __future__ import annotations

import io
import unittest
from unittest.mock import Mock, patch

from nix_control_manager.cli import build_parser, main
from nix_control_manager.version import RELEASE_VERSION


class CliTests(unittest.TestCase):
    def test_version_flag_reports_public_release_version(self) -> None:
        with (
            patch("sys.stdout", new_callable=io.StringIO) as stdout,
            self.assertRaises(SystemExit) as exit_context,
        ):
            build_parser().parse_args(["--version"])

        self.assertEqual(exit_context.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), f"ncm {RELEASE_VERSION}")

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
