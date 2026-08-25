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
_DESKTOP_ENVIRONMENTS = frozenset(
    {"plasma", "gnome", "xfce", "cinnamon", "mate", "hyprland", "sway"}
)
_CONFIGURATION_FLAGS = frozenset({"bluetooth", "libvirtd", "pipewire", "steam", "wsl"})
_GPU_VENDOR_IDS = {
    "0x1002": "amd",
    "0x10de": "nvidia",
    "0x1414": "microsoft",
    "0x1af4": "virtio",
    "0x8086": "intel",
}
_LAPTOP_CHASSIS_TYPES = frozenset({"8", "9", "10", "14", "30", "31", "32"})
_DESKTOP_CHASSIS_TYPES = frozenset({"3", "4", "5", "6", "7", "15", "16", "17", "23", "24"})

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
class TargetContext:
    desktop_environments: tuple[str, ...] = ()
    configuration_flags: tuple[str, ...] = ()
    video_drivers: tuple[str, ...] = ()
    form_factor: str = "unknown"
    gpu_vendors: tuple[str, ...] = ()
    kvm_available: bool = False
    runtime_hardware_inspected: bool = False

    def to_mapping(self) -> dict[str, Any]:
        return {
            "desktopEnvironments": list(self.desktop_environments),
            "configurationFlags": list(self.configuration_flags),
            "videoDrivers": list(self.video_drivers),
            "formFactor": self.form_factor,
            "gpuVendors": list(self.gpu_vendors),
            "kvmAvailable": self.kvm_available,
            "runtimeHardwareInspected": self.runtime_hardware_inspected,
        }


@dataclass(frozen=True, slots=True)
class PackageCompatibilityInspection:
    status: str
    configuration_mode: str
    flake_target: str | None
    system: str
    packages: tuple[PackageAssessment, ...]
    context: TargetContext = TargetContext()
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
            "context": self.context.to_mapping(),
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
    context: TargetContext = TargetContext(),
    warning: str | None = None,
    duration_ms: int = 0,
) -> PackageCompatibilityInspection:
    return PackageCompatibilityInspection(
        status=status,
        configuration_mode=mode,
        flake_target=target,
        system=system,
        packages=packages if packages is not None else _unknown_packages(),
        context=context,
        warnings=(warning,) if warning else (),
        duration_ms=duration_ms,
    )


def _trim_diagnostic(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip()
    return value if len(value) <= _MAX_DIAGNOSTIC_CHARS else value[:_MAX_DIAGNOSTIC_CHARS] + "\n… diagnostic truncated …"


def _string_tuple(value: Any, *, allowed: frozenset[str] | None = None) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
        or (allowed is not None and any(item not in allowed for item in value))
    ):
        raise ValueError("Nix inspector returned invalid target context metadata")
    return tuple(value)


def _parse_packages(
    raw: Any,
) -> tuple[str, tuple[PackageAssessment, ...], TargetContext]:
    if not isinstance(raw, dict) or set(raw) != {"context", "packages", "system"}:
        raise ValueError("Nix inspector returned an invalid top-level document")
    system = raw["system"]
    records = raw["packages"]
    if not isinstance(system, str) or not system:
        raise ValueError("Nix inspector returned an invalid host system")
    if not isinstance(records, list):
        raise ValueError("Nix inspector package records must be an array")
    context_raw = raw["context"]
    if not isinstance(context_raw, dict) or set(context_raw) != {
        "configurationFlags", "desktopEnvironments", "videoDrivers",
    }:
        raise ValueError("Nix inspector returned invalid target context")
    nix_context = TargetContext(
        desktop_environments=_string_tuple(
            context_raw["desktopEnvironments"], allowed=_DESKTOP_ENVIRONMENTS
        ),
        configuration_flags=_string_tuple(
            context_raw["configurationFlags"], allowed=_CONFIGURATION_FLAGS
        ),
        video_drivers=_string_tuple(context_raw["videoDrivers"]),
    )
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
    return system, tuple(parsed), nix_context


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip().lower()
    except (OSError, UnicodeDecodeError):
        return ""


def _runtime_hardware_context(sysfs_root: Path, dev_root: Path) -> TargetContext:
    battery = False
    power_root = sysfs_root / "class/power_supply"
    try:
        battery = any(
            _read_text(path / "type") == "battery"
            for path in power_root.iterdir()
            if path.is_dir()
        )
    except OSError:
        pass
    chassis = _read_text(sysfs_root / "class/dmi/id/chassis_type")
    if battery or chassis in _LAPTOP_CHASSIS_TYPES:
        form_factor = "laptop"
    elif chassis in _DESKTOP_CHASSIS_TYPES:
        form_factor = "desktop"
    else:
        form_factor = "unknown"

    gpu_vendors: list[str] = []
    pci_root = sysfs_root / "bus/pci/devices"
    try:
        for device in list(pci_root.iterdir())[:512]:
            if not _read_text(device / "class").startswith("0x03"):
                continue
            vendor = _GPU_VENDOR_IDS.get(_read_text(device / "vendor"), "other")
            if vendor not in gpu_vendors:
                gpu_vendors.append(vendor)
    except OSError:
        pass
    return TargetContext(
        form_factor=form_factor,
        gpu_vendors=tuple(gpu_vendors),
        kvm_available=(dev_root / "kvm").exists(),
        runtime_hardware_inspected=sysfs_root.is_dir(),
    )


def _merge_context(nix_context: TargetContext, runtime: TargetContext) -> TargetContext:
    return TargetContext(
        desktop_environments=nix_context.desktop_environments,
        configuration_flags=nix_context.configuration_flags,
        video_drivers=nix_context.video_drivers,
        form_factor=runtime.form_factor,
        gpu_vendors=runtime.gpu_vendors,
        kvm_available=runtime.kvm_available,
        runtime_hardware_inspected=runtime.runtime_hardware_inspected,
    )


def inspect_package_compatibility(
    config_root: Path = Path("/etc/nixos"),
    *,
    flake_target: str | None = None,
    timeout: int = 120,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
    sysfs_root: Path = Path("/sys"),
    dev_root: Path = Path("/dev"),
) -> PackageCompatibilityInspection:
    """Evaluate catalog package availability against the target configuration."""
    started = time.monotonic()
    inspection = inspect_system(config_root)
    runtime_context = _runtime_hardware_context(sysfs_root, dev_root)
    mode = inspection.configuration_mode
    target = flake_target
    if timeout < 1:
        return _result(
            "blocked", mode, target, context=runtime_context,
            warning="Inspection timeout must be positive.",
        )
    if mode == "missing":
        return _result(
            "blocked",
            mode,
            target,
            context=runtime_context,
            warning="No configuration.nix or flake.nix entrypoint was found.",
        )
    if not inspection.config_root.is_dir():
        return _result(
            "blocked",
            mode,
            target,
            context=runtime_context,
            warning="The configuration root is not a readable directory.",
        )
    if mode == "flake":
        target = target or inspection.hostname
        if not target or not _FLAKE_TARGET.fullmatch(target):
            return _result(
                "blocked",
                mode,
                target,
                context=runtime_context,
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
            context=runtime_context,
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
            context=runtime_context,
            warning=f"Package compatibility inspection exceeded {timeout} seconds.",
            duration_ms=round((time.monotonic() - started) * 1000),
        )
    except OSError as error:
        return _result(
            "failed",
            mode,
            target,
            context=runtime_context,
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
            context=runtime_context,
            warning=(
                "Nix could not evaluate package compatibility."
                + (f"\n{diagnostic}" if diagnostic else "")
            ),
            duration_ms=duration,
        )
    try:
        system, packages, nix_context = _parse_packages(json.loads(completed.stdout))
    except (json.JSONDecodeError, ValueError) as error:
        return _result(
            "failed",
            mode,
            target,
            context=runtime_context,
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
        context=_merge_context(nix_context, runtime_context),
        warning=warning,
        duration_ms=duration,
    )
