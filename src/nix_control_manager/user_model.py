from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping
import re

from .errors import ValidationError
from .model import validate_attribute_path


USER_STATE_SCHEMA_VERSION = 1
USER_INTEGRATIONS = frozenset({"nixos-module", "standalone"})
_USER_NAME = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
_STATE_FIELDS = {"schemaVersion", "users"}
_PROFILE_FIELDS = {"integration", "packages", "options"}


def _json_value(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValidationError(f"{path} must be a finite number")
        return value
    if isinstance(value, list):
        return [_json_value(item, path=f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ValidationError(f"{path} contains an invalid attribute name")
            normalized[key] = _json_value(item, path=f"{path}.{key}")
        return normalized
    raise ValidationError(
        f"{path} contains an unsupported value of type {type(value).__name__}"
    )


@dataclass(frozen=True, slots=True)
class UserProfileState:
    integration: str
    packages: tuple[str, ...] = field(default_factory=tuple)
    options: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, username: str, raw: Mapping[str, Any]) -> "UserProfileState":
        if not isinstance(raw, Mapping):
            raise ValidationError(f"User {username!r} profile must be a JSON object")
        unknown = set(raw) - _PROFILE_FIELDS
        if unknown:
            raise ValidationError(
                f"User {username!r} profile contains unknown fields: "
                + ", ".join(sorted(str(name) for name in unknown))
            )
        integration = raw.get("integration")
        if integration not in USER_INTEGRATIONS:
            raise ValidationError(
                f"User {username!r} integration must be nixos-module or standalone"
            )
        package_values = raw.get("packages", [])
        if not isinstance(package_values, list):
            raise ValidationError(f"User {username!r} packages must be a JSON array")
        packages = tuple(
            sorted(
                {
                    validate_attribute_path(item, label=f"User {username!r} package")
                    for item in package_values
                }
            )
        )
        option_values = raw.get("options", {})
        if not isinstance(option_values, Mapping):
            raise ValidationError(f"User {username!r} options must be a JSON object")
        options = {
            validate_attribute_path(path, label=f"User {username!r} option"): _json_value(
                value, path=f"User {username!r} option {path}"
            )
            for path, value in sorted(option_values.items())
        }
        return cls(integration=integration, packages=packages, options=options)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "integration": self.integration,
            "packages": list(self.packages),
            "options": dict(self.options),
        }


@dataclass(frozen=True, slots=True)
class UserManagedState:
    schema_version: int = USER_STATE_SCHEMA_VERSION
    users: Mapping[str, UserProfileState] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "UserManagedState":
        return cls()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "UserManagedState":
        if not isinstance(raw, Mapping):
            raise ValidationError("User state must be a JSON object")
        unknown = set(raw) - _STATE_FIELDS
        if unknown:
            raise ValidationError(
                "User state contains unknown fields: "
                + ", ".join(sorted(str(name) for name in unknown))
            )
        version = raw.get("schemaVersion", USER_STATE_SCHEMA_VERSION)
        if version != USER_STATE_SCHEMA_VERSION:
            raise ValidationError(
                f"Unsupported user-state schemaVersion {version!r}; "
                f"expected {USER_STATE_SCHEMA_VERSION}"
            )
        user_values = raw.get("users", {})
        if not isinstance(user_values, Mapping):
            raise ValidationError("User state users must be a JSON object")
        users: dict[str, UserProfileState] = {}
        for username, profile in sorted(user_values.items()):
            if not isinstance(username, str) or not _USER_NAME.fullmatch(username):
                raise ValidationError(f"Invalid managed user name: {username!r}")
            users[username] = UserProfileState.from_mapping(username, profile)
        return cls(schema_version=version, users=users)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "users": {
                username: profile.to_mapping()
                for username, profile in self.users.items()
            },
        }
