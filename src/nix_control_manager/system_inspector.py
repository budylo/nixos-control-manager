from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import platform
import re
import shlex
from typing import Any

from .errors import ValidationError
from .migration import MigrationPreview, preview_state_migration


_MANAGED_DIR_NAMES = ("ncm", "nix-control-manager")
_MAX_NIX_FILES = 128
_MAX_NIX_FILE_BYTES = 2_000_000


@dataclass(frozen=True, slots=True)
class SystemInspection:
    is_nixos: bool
    os_name: str
    release: str
    hostname: str
    config_root: Path
    configuration_mode: str
    entrypoints: tuple[str, ...]
    managed_status: str
    managed_path: Path | None
    imported_by: tuple[str, ...]
    state_status: str
    state_path: Path | None
    migration: MigrationPreview | None
    warnings: tuple[str, ...] = ()

    def to_mapping(self) -> dict[str, Any]:
        return {
            "platform": {
                "isNixOS": self.is_nixos,
                "name": self.os_name,
                "release": self.release,
                "hostname": self.hostname,
            },
            "configuration": {
                "root": str(self.config_root),
                "mode": self.configuration_mode,
                "entrypoints": list(self.entrypoints),
            },
            "managedModule": {
                "status": self.managed_status,
                "path": str(self.managed_path) if self.managed_path else None,
                "importedBy": list(self.imported_by),
            },
            "state": {
                "status": self.state_status,
                "path": str(self.state_path) if self.state_path else None,
                "migration": self.migration.to_mapping() if self.migration else None,
            },
            "warnings": list(self.warnings),
        }


def _read_os_release(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            try:
                parsed = shlex.split(value, posix=True)
                values[key] = parsed[0] if parsed else ""
            except ValueError:
                values[key] = value.strip('"')
    except OSError:
        return {}
    return values


def _read_hostname(path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip()
        return value or platform.node()
    except OSError:
        return platform.node()


def _strip_nix_comments(content: str) -> str:
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return re.sub(r"(?m)#.*$", "", content)


def _candidate_nix_files(root: Path, managed_path: Path | None) -> list[Path]:
    if not root.is_dir():
        return []
    candidates: list[Path] = []
    try:
        for path in sorted(root.rglob("*.nix")):
            if len(candidates) >= _MAX_NIX_FILES:
                break
            try:
                relative = path.relative_to(root)
                if len(relative.parts) > 4 or path.is_symlink() or not path.is_file():
                    continue
                if managed_path and path.is_relative_to(managed_path):
                    continue
                if path.stat().st_size > _MAX_NIX_FILE_BYTES:
                    continue
            except (OSError, ValueError):
                continue
            candidates.append(path)
    except OSError:
        return candidates
    return candidates


def _find_managed_imports(root: Path, managed_path: Path | None) -> tuple[str, ...]:
    if managed_path is None:
        names = _MANAGED_DIR_NAMES
    else:
        names = (managed_path.name,)
    name_pattern = "|".join(re.escape(name) for name in names)
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_'-])\./(?:{name_pattern})(?:/default\.nix)?(?![A-Za-z0-9_'-])"
    )
    imported_by: list[str] = []
    for path in _candidate_nix_files(root, managed_path):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if pattern.search(_strip_nix_comments(content)):
            imported_by.append(str(path.relative_to(root)))
    return tuple(imported_by)


def _inspect_state(state_path: Path | None) -> tuple[str, MigrationPreview | None, list[str]]:
    if state_path is None or not state_path.is_file():
        return "missing", None, []
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        migration = preview_state_migration(raw)
        status = "migration-available" if migration.requires_migration else "current"
        return status, migration, list(migration.warnings)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        return "invalid", None, [f"Managed state cannot be read: {error}"]


def inspect_system(
    config_root: Path = Path("/etc/nixos"),
    *,
    os_release_path: Path = Path("/etc/os-release"),
    hostname_path: Path = Path("/etc/hostname"),
) -> SystemInspection:
    root = config_root.expanduser().resolve()
    os_release = _read_os_release(os_release_path)
    is_nixos = os_release.get("ID", "").lower() == "nixos"
    os_name = os_release.get("NAME") or ("NixOS" if is_nixos else platform.system())
    release = os_release.get("VERSION_ID", "")
    hostname = _read_hostname(hostname_path)

    flake_path = root / "flake.nix"
    configuration_path = root / "configuration.nix"
    entrypoints: list[str] = []
    if flake_path.is_file():
        entrypoints.append("flake.nix")
    if configuration_path.is_file():
        entrypoints.append("configuration.nix")
    if flake_path.is_file():
        mode = "flake"
    elif configuration_path.is_file():
        mode = "channels"
    else:
        mode = "missing"

    managed_path = next(
        (root / name for name in _MANAGED_DIR_NAMES if (root / name).is_dir()), None
    )
    imported_by = _find_managed_imports(root, managed_path)
    if managed_path and imported_by:
        managed_status = "connected"
    elif managed_path:
        managed_status = "present-not-imported"
    elif imported_by:
        managed_status = "import-missing"
    else:
        managed_status = "not-configured"

    state_path = managed_path / "state.json" if managed_path else None
    state_status, migration, warnings = _inspect_state(state_path)
    return SystemInspection(
        is_nixos=is_nixos,
        os_name=os_name,
        release=release,
        hostname=hostname,
        config_root=root,
        configuration_mode=mode,
        entrypoints=tuple(entrypoints),
        managed_status=managed_status,
        managed_path=managed_path,
        imported_by=imported_by,
        state_status=state_status,
        state_path=state_path,
        migration=migration,
        warnings=tuple(warnings),
    )
