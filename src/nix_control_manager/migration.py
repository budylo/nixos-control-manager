from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .errors import StorageError, ValidationError
from .model import ManagedState, SCHEMA_VERSION, validate_attribute_path


_STATE_FIELDS = {"schemaVersion", "packages", "options"}
_LEGACY_SELECTION_FLAGS = ("enabled", "selected", "installed")


@dataclass(frozen=True, slots=True)
class MigrationPreview:
    state: ManagedState
    source_format: str
    warnings: tuple[str, ...] = ()
    ignored_fields: tuple[str, ...] = ()

    @property
    def requires_migration(self) -> bool:
        return self.source_format != "current" or bool(self.ignored_fields)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "sourceFormat": self.source_format,
            "requiresMigration": self.requires_migration,
            "packageCount": len(self.state.packages),
            "warnings": list(self.warnings),
            "ignoredFields": list(self.ignored_fields),
            "normalizedState": self.state.to_mapping(),
        }


def _legacy_package_selected(attribute: str, value: Any) -> tuple[bool, str | None]:
    if value is True:
        return True, None
    if value is False or value is None:
        return False, None
    if isinstance(value, Mapping):
        present_flags = [flag for flag in _LEGACY_SELECTION_FLAGS if flag in value]
        if not present_flags:
            return False, (
                f"Skipped legacy package {attribute!r}: no explicit selection flag"
            )
        for flag in present_flags:
            if not isinstance(value[flag], bool):
                return False, (
                    f"Skipped legacy package {attribute!r}: {flag} must be boolean"
                )
        return any(value[flag] for flag in present_flags), None
    return False, f"Skipped legacy package {attribute!r}: unsupported legacy value"


def preview_state_migration(raw: Mapping[str, Any]) -> MigrationPreview:
    if not isinstance(raw, Mapping):
        raise ValidationError("State must be a JSON object")

    version = raw.get("schemaVersion", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        raise ValidationError(
            f"Unsupported schemaVersion {version!r}; expected {SCHEMA_VERSION}"
        )

    packages_value = raw.get("packages", [])
    warnings: list[str] = []
    if isinstance(packages_value, list):
        source_format = "current"
        normalized_packages = packages_value
    elif isinstance(packages_value, Mapping):
        source_format = "legacy-package-map"
        normalized_packages = []
        for attribute, value in sorted(packages_value.items(), key=lambda pair: str(pair[0])):
            normalized_attribute = validate_attribute_path(attribute, label="Package")
            selected, warning = _legacy_package_selected(normalized_attribute, value)
            if selected:
                normalized_packages.append(normalized_attribute)
            if warning:
                warnings.append(warning)
    else:
        raise ValidationError("packages must be a JSON array or a legacy package map")

    options = raw.get("options", {})
    normalized = ManagedState.from_mapping(
        {
            "schemaVersion": version,
            "packages": normalized_packages,
            "options": options,
        }
    )
    ignored = tuple(sorted(str(field) for field in set(raw) - _STATE_FIELDS))
    if ignored:
        warnings.append(
            "Metadata fields are not part of managed state and will be omitted: "
            + ", ".join(ignored)
        )
    return MigrationPreview(
        state=normalized,
        source_format=source_format,
        warnings=tuple(warnings),
        ignored_fields=ignored,
    )


def load_migration_preview(path: Path) -> MigrationPreview:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StorageError(f"Could not read state from {path}: {error}") from error
    return preview_state_migration(raw)
