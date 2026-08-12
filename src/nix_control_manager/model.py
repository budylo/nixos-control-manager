from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping

from .catalog import validate_setting_value
from .errors import ValidationError


SCHEMA_VERSION = 1
_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_'-]*"
_ATTRIBUTE_PATH = re.compile(rf"^{_IDENTIFIER}(?:\.{_IDENTIFIER})*$")
_ALLOWED_FIELDS = {"schemaVersion", "packages", "options"}


def validate_attribute_path(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not _ATTRIBUTE_PATH.fullmatch(value):
        raise ValidationError(
            f"{label} must be a dot-separated Nix attribute path; got {value!r}"
        )
    return value


def _validate_value(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValidationError(f"{path} must be a finite number")
        return value
    if isinstance(value, list):
        return [_validate_value(item, path=f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValidationError(f"{path} contains an invalid attribute name")
            normalized[key] = _validate_value(item, path=f"{path}.{key}")
        return normalized
    raise ValidationError(f"{path} contains an unsupported value of type {type(value).__name__}")


@dataclass(frozen=True, slots=True)
class ManagedState:
    schema_version: int = SCHEMA_VERSION
    packages: tuple[str, ...] = field(default_factory=tuple)
    options: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "ManagedState":
        return cls()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ManagedState":
        if not isinstance(raw, Mapping):
            raise ValidationError("State must be a JSON object")

        unknown = set(raw) - _ALLOWED_FIELDS
        if unknown:
            names = ", ".join(sorted(str(name) for name in unknown))
            raise ValidationError(f"State contains unknown fields: {names}")

        version = raw.get("schemaVersion", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ValidationError(
                f"Unsupported schemaVersion {version!r}; expected {SCHEMA_VERSION}"
            )

        package_values = raw.get("packages", [])
        if not isinstance(package_values, list):
            raise ValidationError("packages must be a JSON array")
        packages = tuple(
            sorted(
                {
                    validate_attribute_path(item, label="Package")
                    for item in package_values
                }
            )
        )

        option_values = raw.get("options", {})
        if not isinstance(option_values, Mapping):
            raise ValidationError("options must be a JSON object")
        options: dict[str, Any] = {}
        for option_path, value in sorted(option_values.items()):
            normalized_path = validate_attribute_path(option_path, label="Option")
            normalized_value = _validate_value(value, path=f"Option {normalized_path}")
            options[normalized_path] = validate_setting_value(
                normalized_path, normalized_value
            )

        return cls(schema_version=version, packages=packages, options=options)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "packages": list(self.packages),
            "options": dict(self.options),
        }
