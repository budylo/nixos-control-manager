from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from nix_control_manager.doctor import run_doctor
from nix_control_manager.version import RELEASE_VERSION


def inspection(*, mode: str = "flake", managed: str = "connected") -> SimpleNamespace:
    return SimpleNamespace(
        is_nixos=True,
        release="26.05",
        hostname="alpha-host",
        os_name="NixOS",
        configuration_mode=mode,
        config_root=Path("/etc/nixos"),
        entrypoints=("flake.nix",),
        managed_status=managed,
    )


class DoctorTests(unittest.TestCase):
    def test_ready_configuration_without_optional_helper_is_a_warning(self) -> None:
        completed = subprocess.CompletedProcess(
            ["/run/current-system/sw/bin/nix", "--version"], 0, "nix (Nix) 2.31.2\n", ""
        )
        with (
            patch("nix_control_manager.doctor.inspect_system", return_value=inspection()),
            patch("nix_control_manager.doctor.shutil.which", return_value="/run/current-system/sw/bin/nix"),
            patch("nix_control_manager.doctor.subprocess.run", return_value=completed),
        ):
            report = run_doctor(Path("/etc/nixos"), helper_socket=Path("/missing/helper.sock"))

        self.assertEqual(report.status, "warning")
        self.assertEqual(report.to_mapping()["version"], RELEASE_VERSION)
        self.assertTrue(report.to_mapping()["readOnly"])
        self.assertEqual(
            {check.check_id: check.status for check in report.checks},
            {
                "release": "passed",
                "platform": "passed",
                "nix": "passed",
                "configuration": "passed",
                "managed-module": "passed",
                "helper": "warning",
            },
        )

    def test_missing_nix_and_configuration_fail(self) -> None:
        with (
            patch(
                "nix_control_manager.doctor.inspect_system",
                return_value=inspection(mode="missing", managed="not-configured"),
            ),
            patch("nix_control_manager.doctor.shutil.which", return_value=None),
        ):
            report = run_doctor(Path("/etc/nixos"), helper_socket=Path("/missing/helper.sock"))

        self.assertEqual(report.status, "failed")
        failed = {check.check_id for check in report.checks if check.status == "failed"}
        self.assertEqual(failed, {"nix", "configuration"})


if __name__ == "__main__":
    unittest.main()
