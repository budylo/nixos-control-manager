from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any, Callable

from .catalog import load_catalog
from .system_inspector import inspect_system


_FLAKE_TARGET = re.compile(r"^[A-Za-z0-9_-]+$")
_ASSESSMENT_STATUSES = frozenset({"compatible", "incompatible", "unknown"})
_ASSESSMENT_REASONS = frozenset(
    {
        "available",
        "missing-attribute",
        "unsupported-platform",
        "broken-package",
        "evaluation-rejected",
        "inspection-unavailable",
    }
)
_MAX_DIAGNOSTIC_CHARS = 8_000

Runner = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


@dataclass(frozen=True, slots=True)
class PackageAssessment:
    attribute: str
    status: str
    reason: str
    unfree: bool = False
    license_name: str = ""

    def to_mapping(self) -> dict[str, Any]:
        return {
            "attribute": self.attribute,
            "status": self.status,
            "reason": self.reason,
            "unfree": self.unfree,
            "license": self.license_name,
        }


@dataclass(frozen=True, slots=True)
class PackageCompatibilityInspection:
    status: str
    configuration_mode: str
    flake_target: str | None
    system: str
    packages: tuple[PackageAssessment, ...]
    warnings: tuple[str, ...] = ()
    duration_ms: int = 0

    def to_mapping(self) -> dict[str, Any]:
        counts = {"compatible": 0, "incompatible": 0, "unknown": 0, "unfree": 0}
        for package in self.packages:
            counts[package.status] += 1
            if package.unfree:
                counts["unfree"] += 1
        return {
            "schemaVersion": 1,
            "status": self.status,
            "readOnly": True,
            "configurationMode": self.configuration_mode,
            "flakeTarget": self.flake_target,
            "system": self.system,
            "summary": counts,
            "packages": [package.to_mapping() for package in self.packages],
            "warnings": list(self.warnings),
            "durationMs": self.duration_ms,
        }


def _unknown_packages() -> tuple[PackageAssessment, ...]:
    return tuple(
        PackageAssessment(
            attribute=item["attribute"],
            status="unknown",
            reason="inspection-unavailable",
        )
        for item in load_catalog()
    )


def _result(
    status: str,
    mode: str,
    target: str | None,
    *,
    system: str = "",
    packages: tuple[PackageAssessment, ...] | None = None,
    warning: str | None = None,
    duration_ms: int = 0,
) -> PackageCompatibilityInspection:
    return PackageCompatibilityInspection(
        status=status,
        configuration_mode=mode,
        flake_target=target,
        system=system,
        packages=packages if packages is not None else _unknown_packages(),
        warnings=(warning,) if warning else (),
        duration_ms=duration_ms,
    )


def _trim_diagnostic(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip()
    return value if len(value) <= _MAX_DIAGNOSTIC_CHARS else value[:_MAX_DIAGNOSTIC_CHARS] + "\n… diagnostic truncated …"


def _parse_packages(raw: Any) -> tuple[str, tuple[PackageAssessment, ...]]:
    if not isinstance(raw, dict) or set(raw) != {"packages", "system"}:
        raise ValueError("Nix inspector returned an invalid top-level document")
    system = raw["system"]
    records = raw["packages"]
    if not isinstance(system, str) or not system:
        raise ValueError("Nix inspector returned an invalid host system")
    if not isinstance(records, list):
        raise ValueError("Nix inspector package records must be an array")
    expected = [item["attribute"] for item in load_catalog()]
    if len(records) != len(expected):
        raise ValueError("Nix inspector returned an incomplete package catalog")
    parsed: list[PackageAssessment] = []
    for attribute, record in zip(expected, records, strict=True):
        if not isinstance(record, dict) or set(record) != {
            "attribute",
            "license",
            "reason",
            "status",
            "unfree",
        }:
            raise ValueError(f"Nix inspector returned an invalid record for {attribute}")
        if record["attribute"] != attribute:
            raise ValueError("Nix inspector returned packages in an unexpected order")
        status = record["status"]
        reason = record["reason"]
        unfree = record["unfree"]
        license_name = record["license"]
        if status not in _ASSESSMENT_STATUSES or reason not in _ASSESSMENT_REASONS:
            raise ValueError(f"Nix inspector returned an unknown assessment for {attribute}")
        if status == "compatible" and reason != "available":
            raise ValueError(f"Nix inspector returned an inconsistent assessment for {attribute}")
        if status == "incompatible" and reason in {"available", "inspection-unavailable"}:
            raise ValueError(f"Nix inspector returned an inconsistent assessment for {attribute}")
        if not isinstance(unfree, bool) or not isinstance(license_name, str):
            raise ValueError(f"Nix inspector returned invalid metadata for {attribute}")
        parsed.append(
            PackageAssessment(
                attribute=attribute,
                status=status,
                reason=reason,
                unfree=unfree,
                license_name=license_name[:256],
            )
        )
    return system, tuple(parsed)


def inspect_package_compatibility(
    config_root: Path = Path("/etc/nixos"),
    *,
    flake_target: str | None = None,
    timeout: int = 120,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
) -> PackageCompatibilityInspection:
    """Evaluate catalog package availability against the target configuration."""
    started = time.monotonic()
    inspection = inspect_system(config_root)
    mode = inspection.configuration_mode
    target = flake_target
    if timeout < 1:
        return _result("blocked", mode, target, warning="Inspection timeout must be positive.")
    if mode == "missing":
        return _result(
            "blocked",
            mode,
            target,
            warning="No configuration.nix or flake.nix entrypoint was found.",
        )
    if not inspection.config_root.is_dir():
        return _result(
            "blocked",
            mode,
            target,
            warning="The configuration root is not a readable directory.",
        )
    if mode == "flake":
        target = target or inspection.hostname
        if not target or not _FLAKE_TARGET.fullmatch(target):
            return _result(
                "blocked",
                mode,
                target,
                warning=(
                    "A flake target containing only letters, digits, underscores, "
                    "or hyphens is required."
                ),
            )
    nix = which("nix")
    if not nix:
        return _result(
            "unavailable",
            mode,
            target,
            warning="The nix command is unavailable; package compatibility was not inspected.",
        )

    expression = files("nix_control_manager").joinpath("data/inspect_packages.nix")
    catalog = files("nix_control_manager").joinpath("data/catalog.json")
    command = (
        nix,
        "--extra-experimental-features",
        "nix-command flakes",
        "eval",
        "--json",
        "--impure",
        "--no-write-lock-file",
        "--option",
        "allow-import-from-derivation",
        "false",
        "--file",
        str(expression),
    )
    environment = os.environ.copy()
    environment.update(
        {
            "NCM_INSPECT_CONFIG_ROOT": str(inspection.config_root),
            "NCM_INSPECT_CATALOG_PATH": str(catalog),
            "NCM_INSPECT_MODE": mode,
            "NCM_INSPECT_FLAKE_TARGET": target or "",
        }
    )
    try:
        completed = runner(
            list(command),
            cwd=inspection.config_root,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        return _result(
            "timed-out",
            mode,
            target,
            warning=f"Package compatibility inspection exceeded {timeout} seconds.",
            duration_ms=round((time.monotonic() - started) * 1000),
        )
    except OSError as error:
        return _result(
            "failed",
            mode,
            target,
            warning=f"The nix evaluator could not be started: {error}",
            duration_ms=round((time.monotonic() - started) * 1000),
        )

    duration = round((time.monotonic() - started) * 1000)
    if completed.returncode != 0:
        diagnostic = _trim_diagnostic(completed.stderr or completed.stdout)
        return _result(
            "failed",
            mode,
            target,
            warning=(
                "Nix could not evaluate package compatibility."
                + (f"\n{diagnostic}" if diagnostic else "")
            ),
            duration_ms=duration,
        )
    try:
        system, packages = _parse_packages(json.loads(completed.stdout))
    except (json.JSONDecodeError, ValueError) as error:
        return _result(
            "failed",
            mode,
            target,
            warning=f"Nix returned an invalid package compatibility document: {error}",
            duration_ms=duration,
        )
    incompatible = sum(item.status == "incompatible" for item in packages)
    warning = (
        f"{incompatible} catalog packages are unavailable for {system}."
        if incompatible
        else None
    )
    return _result(
        "passed",
        mode,
        target,
        system=system,
        packages=packages,
        warning=warning,
        duration_ms=duration,
    )
