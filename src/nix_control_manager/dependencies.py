from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .catalog import load_settings_catalog
from .errors import ValidationError


_MISSING = object()


@dataclass(frozen=True, slots=True)
class DependencyIssue:
    path: str
    required_path: str
    required_value: Any
    message: str
    status: str
    source: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "requiredPath": self.required_path,
            "requiredValue": self.required_value,
            "message": self.message,
            "status": self.status,
            "source": self.source,
        }


def _rule_is_active(when: str, value: Any) -> bool:
    if when == "always":
        return True
    if when == "true":
        return value is True
    if when == "non-empty":
        return isinstance(value, list) and bool(value)
    raise AssertionError(f"Unsupported dependency trigger: {when}")


def analyze_setting_dependencies(
    managed_options: Mapping[str, Any],
    *,
    effective_options: Mapping[str, Any] | None = None,
) -> tuple[DependencyIssue, ...]:
    """Analyze dependencies activated by settings currently managed by NCM."""
    effective = effective_options or {}
    issues: list[DependencyIssue] = []
    for definition in load_settings_catalog():
        path = definition["path"]
        if path not in managed_options:
            continue
        child_value = managed_options[path]
        for rule in definition.get("requires", []):
            if not _rule_is_active(rule["when"], child_value):
                continue
            required_path = rule["path"]
            if required_path in managed_options:
                actual = managed_options[required_path]
                source = "managed"
            else:
                actual = effective.get(required_path, _MISSING)
                source = "effective" if actual is not _MISSING else "unknown"
            status = (
                "unknown"
                if actual is _MISSING
                else ("satisfied" if actual == rule["requiredValue"] else "unsatisfied")
            )
            issues.append(
                DependencyIssue(
                    path=path,
                    required_path=required_path,
                    required_value=rule["requiredValue"],
                    message=rule["message"],
                    status=status,
                    source=source,
                )
            )
    return tuple(issues)


def validate_managed_setting_dependencies(options: Mapping[str, Any]) -> None:
    """Reject contradictions that are fully explicit inside the managed state."""
    for issue in analyze_setting_dependencies(options):
        if issue.source == "managed" and issue.status == "unsatisfied":
            raise ValidationError(
                f"Option {issue.path} requires {issue.required_path} "
                f"to be {issue.required_value!r}. {issue.message}"
            )
