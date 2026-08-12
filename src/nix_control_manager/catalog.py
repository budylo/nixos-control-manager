from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
import json
import re
from typing import Any, Mapping

from .errors import ValidationError


SETTING_VALUE_TYPES = frozenset(
    {"boolean", "string", "enum", "integer", "string-list", "integer-list"}
)
_SETTING_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_'-]*(?:\.[A-Za-z_][A-Za-z0-9_'-]*)+$")


def load_catalog() -> list[dict[str, Any]]:
    resource = files("nix_control_manager").joinpath("data/catalog.json")
    return json.loads(resource.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _settings_by_path() -> dict[str, dict[str, Any]]:
    resource = files("nix_control_manager").joinpath("data/settings_catalog.json")
    raw = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise RuntimeError("Settings catalog must be a JSON array")
    definitions: dict[str, dict[str, Any]] = {}
    required = {
        "path",
        "name",
        "description",
        "category",
        "valueType",
        "nixosType",
        "default",
        "risk",
    }
    allowed = required | {
        "choices",
        "suggestions",
        "minimum",
        "maximum",
        "unit",
        "pattern",
        "patternMessage",
        "requires",
    }
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise RuntimeError(f"Settings catalog entry {index} must be an object")
        missing = required - set(item)
        unknown = set(item) - allowed
        if missing or unknown:
            raise RuntimeError(
                f"Invalid settings catalog entry {index}: missing={sorted(missing)}, "
                f"unknown={sorted(unknown)}"
            )
        path = item["path"]
        value_type = item["valueType"]
        if not isinstance(path, str) or not _SETTING_PATH.fullmatch(path):
            raise RuntimeError(f"Invalid settings path at entry {index}: {path!r}")
        if path in definitions:
            raise RuntimeError(f"Duplicate settings path: {path}")
        if value_type not in SETTING_VALUE_TYPES:
            raise RuntimeError(f"Unsupported valueType for {path}: {value_type!r}")
        for field in ("name", "description", "category", "nixosType", "risk"):
            if not isinstance(item[field], str) or not item[field]:
                raise RuntimeError(f"{path}.{field} must be a non-empty string")
        if item["risk"] not in {"low", "medium", "high"}:
            raise RuntimeError(f"{path}.risk is invalid")
        if "pattern" in item:
            if value_type != "string" or not isinstance(item["pattern"], str):
                raise RuntimeError(f"{path}.pattern is valid only for string settings")
            try:
                re.compile(item["pattern"])
            except re.error as error:
                raise RuntimeError(f"{path}.pattern is invalid: {error}") from error
            if not isinstance(item.get("patternMessage"), str) or not item["patternMessage"]:
                raise RuntimeError(f"{path}.patternMessage must explain the constraint")
        choices = item.get("choices")
        if value_type == "enum":
            if not isinstance(choices, list) or not choices:
                raise RuntimeError(f"{path}.choices must be a non-empty array")
            values = [choice.get("value") for choice in choices if isinstance(choice, dict)]
            if len(values) != len(choices) or any(not isinstance(value, str) for value in values):
                raise RuntimeError(f"{path}.choices contain an invalid value")
            if len(set(values)) != len(values):
                raise RuntimeError(f"{path}.choices contain duplicate values")
        definitions[path] = item
    for path, definition in definitions.items():
        _validate_known_setting(definition, definition["default"], label=f"Default for {path}")
        rules = definition.get("requires", [])
        if not isinstance(rules, list) or len(rules) > 8:
            raise RuntimeError(f"{path}.requires must be an array with at most 8 rules")
        dependency_paths: set[str] = set()
        for index, rule in enumerate(rules):
            label = f"{path}.requires[{index}]"
            if not isinstance(rule, dict) or set(rule) != {
                "message",
                "path",
                "requiredValue",
                "when",
            }:
                raise RuntimeError(f"{label} must use the exact dependency schema")
            dependency_path = rule["path"]
            if (
                not isinstance(dependency_path, str)
                or dependency_path == path
                or dependency_path not in definitions
                or dependency_path in dependency_paths
            ):
                raise RuntimeError(f"{label}.path must name one other catalog setting")
            dependency_paths.add(dependency_path)
            when = rule["when"]
            allowed_when = {"always"}
            if definition["valueType"] == "boolean":
                allowed_when.add("true")
            if definition["valueType"] in {"string-list", "integer-list"}:
                allowed_when.add("non-empty")
            if when not in allowed_when:
                raise RuntimeError(f"{label}.when is incompatible with {path}")
            message = rule["message"]
            if not isinstance(message, str) or not message or len(message) > 512:
                raise RuntimeError(f"{label}.message must be a concise non-empty string")
            _validate_known_setting(
                definitions[dependency_path],
                rule["requiredValue"],
                label=f"Required value for {dependency_path}",
            )
    return definitions


def load_settings_catalog() -> list[dict[str, Any]]:
    return [dict(definition) for definition in _settings_by_path().values()]


def setting_definition(path: str) -> Mapping[str, Any] | None:
    return _settings_by_path().get(path)


def _validate_known_setting(definition: Mapping[str, Any], value: Any, *, label: str) -> Any:
    value_type = definition["valueType"]
    if value_type == "boolean":
        if not isinstance(value, bool):
            raise ValidationError(f"{label} must be boolean")
        return value
    if value_type in {"string", "enum"}:
        if not isinstance(value, str):
            raise ValidationError(f"{label} must be a string")
        if len(value) > 512:
            raise ValidationError(f"{label} is too long")
        if value_type == "enum":
            allowed = {choice["value"] for choice in definition["choices"]}
            if value not in allowed:
                raise ValidationError(
                    f"{label} must be one of: {', '.join(sorted(allowed))}"
                )
        pattern = definition.get("pattern")
        if pattern is not None and not re.fullmatch(pattern, value):
            raise ValidationError(f"{label} {definition['patternMessage']}")
        return value
    if value_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValidationError(f"{label} must be an integer")
        minimum = definition.get("minimum")
        maximum = definition.get("maximum")
        if minimum is not None and value < minimum:
            raise ValidationError(f"{label} must be at least {minimum}")
        if maximum is not None and value > maximum:
            raise ValidationError(f"{label} must be at most {maximum}")
        return value
    if value_type in {"string-list", "integer-list"}:
        if not isinstance(value, list):
            raise ValidationError(f"{label} must be an array")
        if len(value) > 128:
            raise ValidationError(f"{label} contains too many items")
        normalized: list[str | int] = []
        for index, item in enumerate(value):
            item_label = f"{label}[{index}]"
            if value_type == "string-list":
                if not isinstance(item, str) or not item or len(item) > 256:
                    raise ValidationError(f"{item_label} must be a non-empty string")
            else:
                if not isinstance(item, int) or isinstance(item, bool):
                    raise ValidationError(f"{item_label} must be an integer")
                minimum = definition.get("minimum")
                maximum = definition.get("maximum")
                if minimum is not None and item < minimum:
                    raise ValidationError(f"{item_label} must be at least {minimum}")
                if maximum is not None and item > maximum:
                    raise ValidationError(f"{item_label} must be at most {maximum}")
            if item not in normalized:
                normalized.append(item)
        return normalized
    raise ValidationError(f"{label} uses an unsupported catalog type")


def validate_setting_value(path: str, value: Any) -> Any:
    definition = setting_definition(path)
    if definition is None:
        return value
    return _validate_known_setting(definition, value, label=f"Option {path}")
