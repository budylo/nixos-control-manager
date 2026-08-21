from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import stat
import subprocess
from typing import Any

from .system_inspector import inspect_system
from .version import RELEASE_CHANNEL, RELEASE_VERSION


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    check_id: str
    status: str
    title: str
    detail: str

    def to_mapping(self) -> dict[str, str]:
        return {
            "id": self.check_id,
            "status": self.status,
            "title": self.title,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class DoctorReport:
    status: str
    checks: tuple[DoctorCheck, ...]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "application": "nix-control-manager",
            "version": RELEASE_VERSION,
            "releaseChannel": RELEASE_CHANNEL,
            "status": self.status,
            "checks": [check.to_mapping() for check in self.checks],
            "readOnly": True,
        }


def _nix_check() -> DoctorCheck:
    executable = shutil.which("nix")
    if executable is None:
        return DoctorCheck(
            "nix",
            "failed",
            "Nix command",
            "nix was not found in PATH.",
        )
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return DoctorCheck("nix", "failed", "Nix command", f"Cannot run nix: {error}")
    output = (result.stdout or result.stderr).strip()
    if result.returncode != 0:
        return DoctorCheck(
            "nix", "failed", "Nix command", output or f"Exited with {result.returncode}."
        )
    return DoctorCheck("nix", "passed", "Nix command", output or executable)


def _helper_check(path: Path) -> DoctorCheck:
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return DoctorCheck(
            "helper",
            "warning",
            "System helper",
            f"No helper socket at {path}; the graphical client remains preview-only.",
        )
    except OSError as error:
        return DoctorCheck("helper", "warning", "System helper", f"Cannot inspect {path}: {error}")
    if not stat.S_ISSOCK(mode):
        return DoctorCheck("helper", "failed", "System helper", f"{path} is not a Unix socket.")
    if not os.access(path, os.R_OK | os.W_OK):
        return DoctorCheck(
            "helper",
            "warning",
            "System helper",
            f"The socket exists but the current user cannot access {path}.",
        )
    return DoctorCheck("helper", "passed", "System helper", f"Socket available at {path}.")


def run_doctor(
    config_root: Path = Path("/etc/nixos"),
    *,
    helper_socket: Path = Path("/run/nix-control-manager/helper.sock"),
) -> DoctorReport:
    inspection = inspect_system(config_root)
    checks: list[DoctorCheck] = [
        DoctorCheck(
            "release",
            "passed",
            "Application release",
            f"Nix Control Manager {RELEASE_VERSION} ({RELEASE_CHANNEL}).",
        ),
        DoctorCheck(
            "platform",
            "passed" if inspection.is_nixos else "warning",
            "Operating system",
            (
                f"NixOS {inspection.release or '(version unavailable)'} on {inspection.hostname}."
                if inspection.is_nixos
                else f"Detected {inspection.os_name}; NixOS live integration is unavailable."
            ),
        ),
        _nix_check(),
    ]
    if inspection.configuration_mode == "missing":
        checks.append(
            DoctorCheck(
                "configuration",
                "failed",
                "NixOS configuration",
                f"No flake.nix or configuration.nix found under {inspection.config_root}.",
            )
        )
    else:
        entrypoints = ", ".join(inspection.entrypoints)
        checks.append(
            DoctorCheck(
                "configuration",
                "passed",
                "NixOS configuration",
                f"Detected {inspection.configuration_mode}: {entrypoints}.",
            )
        )
    managed_detail = {
        "connected": "The managed NCM module is connected.",
        "present-not-imported": "Managed files exist but are not imported yet.",
        "import-missing": "An NCM import exists but its managed directory is missing.",
        "not-configured": "No managed NCM module exists yet; first-run adoption is required.",
    }.get(inspection.managed_status, inspection.managed_status)
    checks.append(
        DoctorCheck(
            "managed-module",
            "passed" if inspection.managed_status == "connected" else "warning",
            "Managed module",
            managed_detail,
        )
    )
    checks.append(_helper_check(helper_socket))
    statuses = {check.status for check in checks}
    overall = "failed" if "failed" in statuses else "warning" if "warning" in statuses else "passed"
    return DoctorReport(overall, tuple(checks))
