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
class EffectiveDefinition:
    file: str
    value_available: bool
    value: Any = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "valueAvailable": self.value_available,
            "value": self.value if self.value_available else None,
        }


@dataclass(frozen=True, slots=True)
class EffectiveSetting:
    path: str
    available: bool
    value: Any = None
    option_exists: bool = True
    active_priority: int | None = None
    priority_kind: str = "unknown"
    option_type_name: str = ""
    option_type_description: str = ""
    merge_strategy: str = "equal-or-conflict"
    assessment: str = "unavailable"
    definitions: tuple[EffectiveDefinition, ...] = ()
    declaration_files: tuple[str, ...] = ()
    ownership: str = "unavailable"

    def to_mapping(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "available": self.available,
            "value": self.value,
            "optionExists": self.option_exists,
            "activePriority": self.active_priority,
            "priorityKind": self.priority_kind,
            "optionType": {
                "name": self.option_type_name,
                "description": self.option_type_description,
            },
            "mergeStrategy": self.merge_strategy,
            "assessment": self.assessment,
            "definitions": [definition.to_mapping() for definition in self.definitions],
            "definitionFiles": [definition.file for definition in self.definitions],
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
        EffectiveSetting(
            path=definition["path"],
            available=False,
            option_exists=False,
            merge_strategy=_merge_strategy(definition),
        )
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


def _definitions(value: Any) -> tuple[EffectiveDefinition, ...]:
    if not isinstance(value, list):
        raise ValueError("Nix inspector definitions must be an array")
    normalized: list[EffectiveDefinition] = []
    for item in value[:_MAX_SOURCE_FILES]:
        if not isinstance(item, dict) or set(item) != {
            "file",
            "value",
            "valueAvailable",
        }:
            raise ValueError("Nix inspector returned an invalid definition record")
        file = item["file"]
        value_available = item["valueAvailable"]
        if not isinstance(file, str) or not isinstance(value_available, bool):
            raise ValueError("Nix inspector definition metadata has invalid types")
        normalized.append(
            EffectiveDefinition(
                file=file[:_MAX_SOURCE_PATH_CHARS],
                value_available=value_available,
                value=item["value"] if value_available else None,
            )
        )
    return tuple(normalized)


def _merge_strategy(definition: dict[str, Any]) -> str:
    return (
        "list-concatenation"
        if definition["valueType"] in {"string-list", "integer-list"}
        else "equal-or-conflict"
    )


def _priority_kind(priority: int | None) -> str:
    if priority is None:
        return "unknown"
    if priority <= 50:
        return "forced"
    if priority < 100:
        return "strong-override"
    if priority == 100:
        return "normal"
    if priority < 1000:
        return "weak-override"
    if priority == 1000:
        return "module-default"
    if priority == 1500:
        return "option-default"
    return "weak-default"


def _distinct_definition_values(
    definitions: Sequence[EffectiveDefinition],
) -> int | None:
    if not definitions or any(not definition.value_available for definition in definitions):
        return None
    encoded = {
        json.dumps(
            definition.value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for definition in definitions
    }
    return len(encoded)


def _assessment(
    *,
    option_exists: bool,
    available: bool,
    definitions: Sequence[EffectiveDefinition],
    merge_strategy: str,
) -> str:
    if not option_exists:
        return "option-missing"
    if not available:
        distinct = _distinct_definition_values(definitions)
        if merge_strategy == "equal-or-conflict" and distinct is not None and distinct > 1:
            return "conflict"
        return "evaluation-failed"
    if len(definitions) <= 1:
        return "single-definition"
    if merge_strategy == "list-concatenation":
        return "list-merged"
    distinct = _distinct_definition_values(definitions)
    if distinct == 1:
        return "equal-definitions"
    return "type-merged"


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
    catalog = load_settings_catalog()
    expected = [definition["path"] for definition in catalog]
    records = raw["settings"]
    if len(records) != len(expected):
        raise ValueError("Nix inspector returned an incomplete settings catalog")
    parsed: list[EffectiveSetting] = []
    for definition, expected_path, record in zip(catalog, expected, records, strict=True):
        if not isinstance(record, dict) or record.get("path") != expected_path:
            raise ValueError("Nix inspector returned settings in an unexpected order")
        available = record.get("available")
        option_exists = record.get("optionExists")
        if not isinstance(available, bool) or not isinstance(option_exists, bool):
            raise ValueError(f"Nix inspector availability is invalid for {expected_path}")
        if available and not option_exists:
            raise ValueError(f"Nix inspector availability is inconsistent for {expected_path}")
        active_priority = record.get("activePriority")
        if active_priority is not None and (
            not isinstance(active_priority, int) or isinstance(active_priority, bool)
        ):
            raise ValueError(f"Nix inspector priority is invalid for {expected_path}")
        option_type = record.get("optionType")
        if option_exists:
            if not isinstance(option_type, dict) or set(option_type) != {
                "description",
                "name",
            }:
                raise ValueError(f"Nix inspector type metadata is invalid for {expected_path}")
            if not all(isinstance(value, str) for value in option_type.values()):
                raise ValueError(f"Nix inspector type metadata is invalid for {expected_path}")
        else:
            option_type = {"name": "", "description": ""}
        active_definitions = _definitions(record.get("definitions"))
        declarations = _source_paths(record.get("declarationFiles"))
        merge_strategy = _merge_strategy(definition)
        parsed.append(
            EffectiveSetting(
                path=expected_path,
                available=available,
                value=record.get("value") if available else None,
                option_exists=option_exists,
                active_priority=active_priority,
                priority_kind=_priority_kind(active_priority),
                option_type_name=option_type["name"],
                option_type_description=option_type["description"],
                merge_strategy=merge_strategy,
                assessment=_assessment(
                    option_exists=option_exists,
                    available=available,
                    definitions=active_definitions,
                    merge_strategy=merge_strategy,
                ),
                definitions=active_definitions,
                declaration_files=declarations,
                ownership=(
                    _ownership(
                        [item.file for item in active_definitions],
                        config_root=config_root,
                        output_path=output_path,
                    )
                    if option_exists
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
