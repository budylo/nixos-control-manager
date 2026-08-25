from __future__ import annotations

from functools import lru_cache
from importlib.resources import files
from copy import deepcopy
import json
import re
from typing import Any, Mapping

from .errors import ValidationError


SETTING_VALUE_TYPES = frozenset(
    {"boolean", "string", "enum", "integer", "string-list", "integer-list"}
)
PACKAGE_SCOPES = frozenset({"system", "home-manager"})
DESKTOP_ENVIRONMENTS = frozenset(
    {"plasma", "gnome", "xfce", "cinnamon", "mate", "hyprland", "sway"}
)
FORM_FACTORS = frozenset({"laptop", "desktop", "unknown"})
GPU_VENDORS = frozenset({"amd", "intel", "microsoft", "nvidia", "virtio", "other"})
CONFIGURATION_FLAGS = frozenset({"bluetooth", "libvirtd", "pipewire", "steam", "wsl"})
SERVICE_CATEGORIES = frozenset(
    {"connectivity", "desktop", "hardware", "maintenance", "security", "virtualization"}
)
SERVICE_MODES = frozenset({"background", "integration", "scheduled"})
SERVICE_EXPOSURES = frozenset({"none", "local-network", "remote-access"})
SERVICE_PLATFORMS = frozenset({"nixos", "wsl"})
DRIVER_CATEGORIES = frozenset({"firmware", "graphics"})
DRIVER_GUIDANCE = frozenset({"manual", "recommended"})
DRIVER_PLATFORMS = frozenset({"nixos"})
_SETTING_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_'-]*(?:\.[A-Za-z_][A-Za-z0-9_'-]*)+$")
_PACKAGE_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_'-]*(?:\.[A-Za-z_][A-Za-z0-9_'-]*)*$")
_PRESET_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@lru_cache(maxsize=1)
def _catalog_by_attribute() -> dict[str, dict[str, Any]]:
    resource = files("nix_control_manager").joinpath("data/catalog.json")
    raw = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise RuntimeError("Package catalog must be a JSON array")
    definitions: dict[str, dict[str, Any]] = {}
    required = {
        "attribute", "name", "description", "category", "featured", "symbol",
        "tags", "scopes",
    }
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or set(item) != required:
            raise RuntimeError(f"Package catalog entry {index} must use the exact schema")
        attribute = item["attribute"]
        if not isinstance(attribute, str) or not _PACKAGE_PATH.fullmatch(attribute):
            raise RuntimeError(f"Invalid package attribute at entry {index}: {attribute!r}")
        if attribute in definitions:
            raise RuntimeError(f"Duplicate package attribute: {attribute}")
        for field in ("name", "description", "category", "symbol"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise RuntimeError(f"{attribute}.{field} must be a non-empty string")
        if not isinstance(item["featured"], bool):
            raise RuntimeError(f"{attribute}.featured must be boolean")
        tags = item["tags"]
        scopes = item["scopes"]
        if (
            not isinstance(tags, list)
            or not tags
            or any(not isinstance(tag, str) or not tag.strip() for tag in tags)
            or len(tags) != len(set(tags))
        ):
            raise RuntimeError(f"{attribute}.tags must be a unique non-empty string array")
        if (
            not isinstance(scopes, list)
            or not scopes
            or any(scope not in PACKAGE_SCOPES for scope in scopes)
            or len(scopes) != len(set(scopes))
        ):
            raise RuntimeError(f"{attribute}.scopes contains an invalid or duplicate scope")
        definitions[attribute] = item
    return definitions


def load_catalog() -> list[dict[str, Any]]:
    return deepcopy(list(_catalog_by_attribute().values()))


def _string_array(
    value: Any,
    *,
    label: str,
    allowed: frozenset[str] | None = None,
    allow_empty: bool = False,
) -> list[str]:
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise RuntimeError(f"{label} must be a unique string array")
    if allowed is not None and any(item not in allowed for item in value):
        raise RuntimeError(f"{label} contains an unsupported value")
    return value


@lru_cache(maxsize=1)
def _catalog_guidance() -> dict[str, Any]:
    resource = files("nix_control_manager").joinpath("data/catalog_guidance.json")
    raw = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {
        "schemaVersion",
        "alternativeGroups",
        "companions",
        "contextRecommendations",
    }:
        raise RuntimeError("Catalog guidance must use the exact top-level schema")
    if raw["schemaVersion"] != 1:
        raise RuntimeError("Catalog guidance schemaVersion must be 1")
    packages = _catalog_by_attribute()

    groups = raw["alternativeGroups"]
    if not isinstance(groups, list):
        raise RuntimeError("alternativeGroups must be an array")
    group_ids: set[str] = set()
    grouped_packages: set[str] = set()
    for index, group in enumerate(groups):
        label = f"alternativeGroups[{index}]"
        if not isinstance(group, dict) or set(group) != {
            "id", "title", "description", "members",
        }:
            raise RuntimeError(f"{label} must use the exact schema")
        group_id = group["id"]
        if not isinstance(group_id, str) or not _PRESET_ID.fullmatch(group_id) or group_id in group_ids:
            raise RuntimeError(f"{label}.id is invalid or duplicated")
        group_ids.add(group_id)
        for field in ("title", "description"):
            if not isinstance(group[field], str) or not group[field].strip():
                raise RuntimeError(f"{label}.{field} must be non-empty")
        members = group["members"]
        if not isinstance(members, list) or len(members) < 2:
            raise RuntimeError(f"{label}.members must contain at least two packages")
        local_members: set[str] = set()
        for member_index, member in enumerate(members):
            member_label = f"{label}.members[{member_index}]"
            if not isinstance(member, dict) or set(member) != {
                "attribute", "desktopEnvironments",
            }:
                raise RuntimeError(f"{member_label} must use the exact schema")
            attribute = member["attribute"]
            if attribute not in packages or attribute in local_members or attribute in grouped_packages:
                raise RuntimeError(f"{member_label}.attribute is unknown or duplicated")
            local_members.add(attribute)
            grouped_packages.add(attribute)
            _string_array(
                member["desktopEnvironments"],
                label=f"{member_label}.desktopEnvironments",
                allowed=DESKTOP_ENVIRONMENTS,
                allow_empty=True,
            )

    companions = raw["companions"]
    if not isinstance(companions, list):
        raise RuntimeError("companions must be an array")
    companion_pairs: set[tuple[str, str]] = set()
    for index, companion in enumerate(companions):
        label = f"companions[{index}]"
        if not isinstance(companion, dict) or set(companion) != {"source", "target", "reason"}:
            raise RuntimeError(f"{label} must use the exact schema")
        source = companion["source"]
        target = companion["target"]
        pair = (source, target)
        if source not in packages or target not in packages or source == target or pair in companion_pairs:
            raise RuntimeError(f"{label} references an unknown or duplicate package pair")
        companion_pairs.add(pair)
        if not isinstance(companion["reason"], str) or not companion["reason"].strip():
            raise RuntimeError(f"{label}.reason must be non-empty")

    recommendations = raw["contextRecommendations"]
    if not isinstance(recommendations, list):
        raise RuntimeError("contextRecommendations must be an array")
    recommendation_ids: set[str] = set()
    match_fields = {
        "desktopEnvironments": DESKTOP_ENVIRONMENTS,
        "formFactors": FORM_FACTORS,
        "gpuVendors": GPU_VENDORS,
        "configurationFlags": CONFIGURATION_FLAGS,
    }
    for index, recommendation in enumerate(recommendations):
        label = f"contextRecommendations[{index}]"
        if not isinstance(recommendation, dict) or set(recommendation) != {
            "id", "title", "reason", "match", "packages",
        }:
            raise RuntimeError(f"{label} must use the exact schema")
        recommendation_id = recommendation["id"]
        if (
            not isinstance(recommendation_id, str)
            or not _PRESET_ID.fullmatch(recommendation_id)
            or recommendation_id in recommendation_ids
        ):
            raise RuntimeError(f"{label}.id is invalid or duplicated")
        recommendation_ids.add(recommendation_id)
        for field in ("title", "reason"):
            if not isinstance(recommendation[field], str) or not recommendation[field].strip():
                raise RuntimeError(f"{label}.{field} must be non-empty")
        match = recommendation["match"]
        if not isinstance(match, dict) or not match or set(match) - (set(match_fields) | {"kvmAvailable"}):
            raise RuntimeError(f"{label}.match contains unsupported conditions")
        for field, allowed in match_fields.items():
            if field in match:
                _string_array(match[field], label=f"{label}.match.{field}", allowed=allowed)
        if "kvmAvailable" in match and not isinstance(match["kvmAvailable"], bool):
            raise RuntimeError(f"{label}.match.kvmAvailable must be boolean")
        for attribute in _string_array(recommendation["packages"], label=f"{label}.packages"):
            if attribute not in packages:
                raise RuntimeError(f"{label} references unknown package {attribute!r}")
    return raw


def load_catalog_guidance() -> dict[str, Any]:
    return deepcopy(_catalog_guidance())


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
        "service",
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
        service = item.get("service")
        if service is not None:
            if value_type != "boolean" or not isinstance(service, dict) or set(service) != {
                "category",
                "mode",
                "exposure",
                "platforms",
            }:
                raise RuntimeError(f"{path}.service must use the exact boolean-service schema")
            if service["category"] not in SERVICE_CATEGORIES:
                raise RuntimeError(f"{path}.service.category is invalid")
            if service["mode"] not in SERVICE_MODES:
                raise RuntimeError(f"{path}.service.mode is invalid")
            if service["exposure"] not in SERVICE_EXPOSURES:
                raise RuntimeError(f"{path}.service.exposure is invalid")
            platforms = service["platforms"]
            if (
                not isinstance(platforms, list)
                or not platforms
                or any(platform not in SERVICE_PLATFORMS for platform in platforms)
                or len(platforms) != len(set(platforms))
            ):
                raise RuntimeError(f"{path}.service.platforms is invalid")
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
    return deepcopy(list(_settings_by_path().values()))


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


@lru_cache(maxsize=1)
def _driver_profiles_by_id() -> dict[str, dict[str, Any]]:
    resource = files("nix_control_manager").joinpath("data/driver_profiles.json")
    raw = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"schemaVersion", "profiles"}:
        raise RuntimeError("Driver profiles must use the exact top-level schema")
    if raw["schemaVersion"] != 1 or not isinstance(raw["profiles"], list):
        raise RuntimeError("Driver profiles schemaVersion must be 1 and profiles an array")
    settings = _settings_by_path()
    definitions: dict[str, dict[str, Any]] = {}
    required = {
        "id",
        "name",
        "description",
        "category",
        "risk",
        "guidance",
        "vendors",
        "platforms",
        "formFactors",
        "configurationFlags",
        "options",
        "warnings",
    }
    for index, item in enumerate(raw["profiles"]):
        label = f"driver profiles[{index}]"
        if not isinstance(item, dict) or set(item) != required:
            raise RuntimeError(f"{label} must use the exact schema")
        profile_id = item["id"]
        if (
            not isinstance(profile_id, str)
            or not _PRESET_ID.fullmatch(profile_id)
            or profile_id in definitions
        ):
            raise RuntimeError(f"{label}.id is invalid or duplicated")
        for field in ("name", "description"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise RuntimeError(f"{profile_id}.{field} must be non-empty")
        if item["category"] not in DRIVER_CATEGORIES:
            raise RuntimeError(f"{profile_id}.category is invalid")
        if item["risk"] not in {"low", "medium", "high"}:
            raise RuntimeError(f"{profile_id}.risk is invalid")
        if item["guidance"] not in DRIVER_GUIDANCE:
            raise RuntimeError(f"{profile_id}.guidance is invalid")
        _string_array(
            item["vendors"],
            label=f"{profile_id}.vendors",
            allowed=GPU_VENDORS,
            allow_empty=True,
        )
        _string_array(
            item["platforms"],
            label=f"{profile_id}.platforms",
            allowed=DRIVER_PLATFORMS,
        )
        _string_array(
            item["formFactors"],
            label=f"{profile_id}.formFactors",
            allowed=FORM_FACTORS,
            allow_empty=True,
        )
        _string_array(
            item["configurationFlags"],
            label=f"{profile_id}.configurationFlags",
            allowed=CONFIGURATION_FLAGS,
            allow_empty=True,
        )
        warnings = item["warnings"]
        if (
            not isinstance(warnings, list)
            or not warnings
            or any(not isinstance(warning, str) or not warning.strip() for warning in warnings)
            or len(warnings) != len(set(warnings))
        ):
            raise RuntimeError(f"{profile_id}.warnings must be a unique non-empty string array")
        options = item["options"]
        if not isinstance(options, dict) or not options:
            raise RuntimeError(f"{profile_id}.options must be a non-empty object")
        for path, value in options.items():
            if path not in settings:
                raise RuntimeError(f"{profile_id} references unknown setting {path!r}")
            try:
                validate_setting_value(path, value)
            except ValidationError as error:
                raise RuntimeError(f"Invalid option in driver profile {profile_id}: {error}") from error
        for path, value in options.items():
            for rule in settings[path].get("requires", []):
                if (
                    _dependency_rule_active(rule["when"], value)
                    and options.get(rule["path"]) != rule["requiredValue"]
                ):
                    raise RuntimeError(
                        f"Driver profile {profile_id} must explicitly satisfy "
                        f"{path} dependency {rule['path']}"
                    )
        definitions[profile_id] = item
    return definitions


def load_driver_profiles() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "profiles": deepcopy(list(_driver_profiles_by_id().values())),
    }


def _dependency_rule_active(when: str, value: Any) -> bool:
    return (
        when == "always"
        or (when == "true" and value is True)
        or (when == "non-empty" and isinstance(value, list) and bool(value))
    )


@lru_cache(maxsize=1)
def _presets_by_id() -> dict[str, dict[str, Any]]:
    resource = files("nix_control_manager").joinpath("data/presets.json")
    raw = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise RuntimeError("Preset catalog must be a JSON array")
    packages = _catalog_by_attribute()
    settings = _settings_by_path()
    definitions: dict[str, dict[str, Any]] = {}
    required = {
        "id", "name", "description", "category", "symbol", "packages", "options",
    }
    for index, item in enumerate(raw):
        if not isinstance(item, dict) or set(item) != required:
            raise RuntimeError(f"Preset catalog entry {index} must use the exact schema")
        preset_id = item["id"]
        if not isinstance(preset_id, str) or not _PRESET_ID.fullmatch(preset_id):
            raise RuntimeError(f"Invalid preset id at entry {index}: {preset_id!r}")
        if preset_id in definitions:
            raise RuntimeError(f"Duplicate preset id: {preset_id}")
        for field in ("name", "description", "category", "symbol"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise RuntimeError(f"{preset_id}.{field} must be a non-empty string")
        preset_packages = item["packages"]
        if (
            not isinstance(preset_packages, list)
            or not preset_packages
            or len(preset_packages) != len(set(preset_packages))
        ):
            raise RuntimeError(f"{preset_id}.packages must be a unique non-empty array")
        for attribute in preset_packages:
            if attribute not in packages:
                raise RuntimeError(f"{preset_id} references unknown package {attribute!r}")
            if "system" not in packages[attribute]["scopes"]:
                raise RuntimeError(f"{preset_id} package {attribute!r} is not system-scoped")
        options = item["options"]
        if not isinstance(options, dict):
            raise RuntimeError(f"{preset_id}.options must be an object")
        for path, value in options.items():
            if path not in settings:
                raise RuntimeError(f"{preset_id} references unknown setting {path!r}")
            try:
                validate_setting_value(path, value)
            except ValidationError as error:
                raise RuntimeError(f"Invalid option in preset {preset_id}: {error}") from error
        for path, value in options.items():
            for rule in settings[path].get("requires", []):
                if _dependency_rule_active(rule["when"], value) and options.get(rule["path"]) != rule["requiredValue"]:
                    raise RuntimeError(
                        f"Preset {preset_id} must explicitly satisfy {path} dependency {rule['path']}"
                    )
        definitions[preset_id] = item
    return definitions


def load_presets() -> list[dict[str, Any]]:
    return deepcopy(list(_presets_by_id().values()))
