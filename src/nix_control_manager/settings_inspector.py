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
from typing import Any, Callable, Sequence

from .catalog import load_settings_catalog
from .system_inspector import inspect_system


_FLAKE_TARGET = re.compile(r"^[A-Za-z0-9_-]+$")
_MAX_DIAGNOSTIC_CHARS = 8_000
_MAX_SOURCE_FILES = 32
_MAX_SOURCE_PATH_CHARS = 2_048

Runner = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


@dataclass(frozen=True, slots=True)
class EffectiveSetting:
    path: str
    available: bool
    value: Any = None
    definition_files: tuple[str, ...] = ()
    declaration_files: tuple[str, ...] = ()
    ownership: str = "unavailable"

    def to_mapping(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "available": self.available,
            "value": self.value,
            "definitionFiles": list(self.definition_files),
            "declarationFiles": list(self.declaration_files),
            "ownership": self.ownership,
        }


@dataclass(frozen=True, slots=True)
class EffectiveSettingsInspection:
    status: str
    configuration_mode: str
    flake_target: str | None
    settings: tuple[EffectiveSetting, ...]
    warnings: tuple[str, ...] = ()
    duration_ms: int = 0

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "readOnly": True,
            "configurationMode": self.configuration_mode,
            "flakeTarget": self.flake_target,
            "settings": [setting.to_mapping() for setting in self.settings],
            "warnings": list(self.warnings),
            "durationMs": self.duration_ms,
        }


def _trim_diagnostic(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip()
    if len(value) <= _MAX_DIAGNOSTIC_CHARS:
        return value
    return value[:_MAX_DIAGNOSTIC_CHARS] + "\n… diagnostic truncated …"


def _empty_settings() -> tuple[EffectiveSetting, ...]:
    return tuple(
        EffectiveSetting(path=definition["path"], available=False)
        for definition in load_settings_catalog()
    )


def _result(
    status: str,
    mode: str,
    target: str | None,
    *,
    settings: tuple[EffectiveSetting, ...] | None = None,
    warning: str | None = None,
    duration_ms: int = 0,
) -> EffectiveSettingsInspection:
    return EffectiveSettingsInspection(
        status=status,
        configuration_mode=mode,
        flake_target=target,
        settings=settings if settings is not None else _empty_settings(),
        warnings=(warning,) if warning else (),
        duration_ms=duration_ms,
    )


def _source_paths(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError("Nix inspector source locations must be an array")
    normalized: list[str] = []
    for item in value[:_MAX_SOURCE_FILES]:
        if not isinstance(item, str):
            raise ValueError("Nix inspector returned a non-string source location")
        item = item[:_MAX_SOURCE_PATH_CHARS]
        if item not in normalized:
            normalized.append(item)
    return tuple(normalized)


def _managed_source_markers(config_root: Path, output_path: Path) -> tuple[str, ...]:
    markers = [
        str(output_path.resolve()).replace("\\", "/"),
        "/ncm/managed.nix",
        "/ncm/packages.nix",
        "/nix-control-manager/managed.nix",
        "/nix-control-manager/packages.nix",
    ]
    try:
        relative = output_path.resolve().relative_to(config_root.resolve())
    except ValueError:
        pass
    else:
        markers.append("/" + relative.as_posix())
    return tuple(dict.fromkeys(markers))


def _ownership(
    definition_files: Sequence[str], *, config_root: Path, output_path: Path
) -> str:
    if not definition_files:
        return "inherited"
    markers = _managed_source_markers(config_root, output_path)
    managed = [
        source
        for source in definition_files
        if any(source.replace("\\", "/").endswith(marker) for marker in markers)
    ]
    if not managed:
        return "inherited"
    return "managed" if len(managed) == len(definition_files) else "shared"


def _parse_settings(
    raw: Any, *, config_root: Path, output_path: Path
) -> tuple[EffectiveSetting, ...]:
    if not isinstance(raw, dict) or not isinstance(raw.get("settings"), list):
        raise ValueError("Nix inspector returned an invalid top-level document")
    expected = [definition["path"] for definition in load_settings_catalog()]
    records = raw["settings"]
    if len(records) != len(expected):
        raise ValueError("Nix inspector returned an incomplete settings catalog")
    parsed: list[EffectiveSetting] = []
    for expected_path, record in zip(expected, records, strict=True):
        if not isinstance(record, dict) or record.get("path") != expected_path:
            raise ValueError("Nix inspector returned settings in an unexpected order")
        available = record.get("available")
        if not isinstance(available, bool):
            raise ValueError(f"Nix inspector availability is invalid for {expected_path}")
        definitions = _source_paths(record.get("definitionFiles"))
        declarations = _source_paths(record.get("declarationFiles"))
        parsed.append(
            EffectiveSetting(
                path=expected_path,
                available=available,
                value=record.get("value") if available else None,
                definition_files=definitions,
                declaration_files=declarations,
                ownership=(
                    _ownership(
                        definitions, config_root=config_root, output_path=output_path
                    )
                    if available
                    else "unavailable"
                ),
            )
        )
    return tuple(parsed)


def inspect_effective_settings(
    config_root: Path = Path("/etc/nixos"),
    *,
    output_path: Path = Path("managed.local.nix"),
    flake_target: str | None = None,
    timeout: int = 120,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
) -> EffectiveSettingsInspection:
    """Evaluate catalog values and definition locations without building or writing."""
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
            warning="The nix command is unavailable; effective settings were not inspected.",
        )

    expression = files("nix_control_manager").joinpath("data/inspect_settings.nix")
    catalog = files("nix_control_manager").joinpath("data/settings_catalog.json")
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
            warning=f"Effective-settings inspection exceeded {timeout} seconds.",
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
                "Nix could not evaluate the current configuration."
                + (f"\n{diagnostic}" if diagnostic else "")
            ),
            duration_ms=duration,
        )
    try:
        raw = json.loads(completed.stdout)
        settings = _parse_settings(
            raw, config_root=inspection.config_root, output_path=output_path
        )
    except (json.JSONDecodeError, ValueError) as error:
        return _result(
            "failed",
            mode,
            target,
            warning=f"Nix returned an invalid effective-settings document: {error}",
            duration_ms=duration,
        )
    missing = sum(not setting.available for setting in settings)
    warning = (
        f"{missing} catalog settings are unavailable in this NixOS configuration."
        if missing
        else None
    )
    return _result(
        "passed",
        mode,
        target,
        settings=settings,
        warning=warning,
        duration_ms=duration,
    )
