from __future__ import annotations

from dataclasses import dataclass
import getpass
import json
import os
from pathlib import Path
import re
from typing import Any

from .errors import ValidationError
from .user_model import UserManagedState


_MAX_NIX_FILES = 128
_MAX_DIRECTORIES = 512
_MAX_NIX_FILE_BYTES = 2_000_000
_DIRECT_USER = re.compile(
    r"home-manager\.users\.(?:\"([^\"]+)\"|([A-Za-z_][A-Za-z0-9_'-]*))\s*="
)
_HOME_CONFIGURATION = re.compile(
    r"homeConfigurations\.(?:\"([^\"]+)\"|([A-Za-z_][A-Za-z0-9_'-]*))\s*="
)
_HOME_USERNAME = re.compile(r"home\.username\s*=\s*\"([^\"]+)\"\s*;")


@dataclass(frozen=True, slots=True)
class DetectedHomeUser:
    name: str
    integration: str
    source: str

    def to_mapping(self) -> dict[str, str]:
        return {"name": self.name, "integration": self.integration, "source": self.source}


@dataclass(frozen=True, slots=True)
class UserStateInspection:
    status: str
    path: Path
    state: UserManagedState
    warning: str | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "path": str(self.path),
            "profileCount": len(self.state.users),
            "state": self.state.to_mapping(),
            "warning": self.warning,
        }


@dataclass(frozen=True, slots=True)
class HomeManagerInspection:
    status: str
    integrations: tuple[str, ...]
    users: tuple[DetectedHomeUser, ...]
    sources: tuple[str, ...]
    config_root: Path
    standalone_root: Path
    user_state: UserStateInspection
    warnings: tuple[str, ...] = ()

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "readOnly": True,
            "writeEnabled": False,
            "activationEnabled": False,
            "integrations": list(self.integrations),
            "users": [user.to_mapping() for user in self.users],
            "sources": list(self.sources),
            "configRoot": str(self.config_root),
            "standaloneRoot": str(self.standalone_root),
            "userState": self.user_state.to_mapping(),
            "warnings": list(self.warnings),
        }


def _strip_comments(content: str) -> str:
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    return re.sub(r"(?m)#.*$", "", content)


def _nix_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    files: list[Path] = []
    directories_seen = 0
    try:
        for directory, child_directories, child_files in os.walk(
            root, topdown=True, followlinks=False
        ):
            directories_seen += 1
            if directories_seen > _MAX_DIRECTORIES:
                break
            current = Path(directory)
            try:
                depth = len(current.relative_to(root).parts)
            except ValueError:
                child_directories[:] = []
                continue
            if depth >= 5:
                child_directories[:] = []
            else:
                child_directories[:] = sorted(
                    name
                    for name in child_directories
                    if not (current / name).is_symlink()
                )
            for name in sorted(child_files):
                if len(files) >= _MAX_NIX_FILES:
                    return files
                if not name.endswith(".nix"):
                    continue
                path = current / name
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                    if path.stat().st_size > _MAX_NIX_FILE_BYTES:
                        continue
                except OSError:
                    continue
                files.append(path)
    except OSError:
        pass
    return files


def _load_user_state(path: Path) -> UserStateInspection:
    if not path.is_file():
        return UserStateInspection("missing", path, UserManagedState.empty())
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        state = UserManagedState.from_mapping(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        return UserStateInspection("invalid", path, UserManagedState.empty(), str(error))
    return UserStateInspection("current", path, state)


def inspect_home_manager(
    config_root: Path = Path("/etc/nixos"),
    *,
    standalone_root: Path = Path("~/.config/home-manager"),
    user_state_path: Path = Path("user-state.local.json"),
    current_user: str | None = None,
) -> HomeManagerInspection:
    root = config_root.expanduser().resolve()
    standalone = standalone_root.expanduser().resolve()
    state_path = user_state_path.expanduser().resolve()
    integrations: set[str] = set()
    sources: set[str] = set()
    users: dict[tuple[str, str], DetectedHomeUser] = {}

    for path in _nix_files(root):
        try:
            content = _strip_comments(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        relative = path.relative_to(root).as_posix()
        module_signal = bool(
            re.search(r"home-manager\.nixosModules\.(?:home-manager|default)", content)
            or re.search(r"<home-manager/nixos(?:\.nix)?>", content)
            or "home-manager.users" in content
        )
        if module_signal:
            integrations.add("nixos-module")
            sources.add(relative)
        for match in _DIRECT_USER.finditer(content):
            name = match.group(1) or match.group(2)
            users[(name, "nixos-module")] = DetectedHomeUser(
                name, "nixos-module", relative
            )
        for match in _HOME_CONFIGURATION.finditer(content):
            name = match.group(1) or match.group(2)
            integrations.add("standalone")
            sources.add(relative)
            users[(name, "standalone")] = DetectedHomeUser(name, "standalone", relative)

    standalone_files = _nix_files(standalone)
    if (standalone / "home.nix").is_file() or (standalone / "flake.nix").is_file():
        integrations.add("standalone")
        for path in standalone_files:
            relative = path.relative_to(standalone).as_posix()
            sources.add(f"standalone:{relative}")
            try:
                content = _strip_comments(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            names = [match.group(1) for match in _HOME_USERNAME.finditer(content)]
            if not names and path.name == "home.nix":
                names = [current_user or getpass.getuser()]
            for name in names:
                users[(name, "standalone")] = DetectedHomeUser(
                    name, "standalone", f"standalone:{relative}"
                )

    warnings: list[str] = []
    if integrations and not users:
        warnings.append(
            "Home Manager integration was detected, but no user could be identified statically."
        )
    user_state = _load_user_state(state_path)
    if user_state.warning:
        warnings.append(f"User state cannot be read: {user_state.warning}")
    status = "detected" if integrations else "not-detected"
    return HomeManagerInspection(
        status=status,
        integrations=tuple(sorted(integrations)),
        users=tuple(sorted(users.values(), key=lambda item: (item.name, item.integration))),
        sources=tuple(sorted(sources)),
        config_root=root,
        standalone_root=standalone,
        user_state=user_state,
        warnings=tuple(warnings),
    )
