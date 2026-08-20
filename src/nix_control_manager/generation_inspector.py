from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any


_GENERATION_LINK = re.compile(r"^system-([1-9][0-9]*)-link$")
_STORE_NAME = re.compile(r"^[0-9a-z]{32}-[^/\s]+$")


def _resolved_store_path(path: Path, store_root: Path) -> str | None:
    try:
        if not path.exists() and not path.is_symlink():
            return None
        resolved = str(path.resolve(strict=True))
    except OSError:
        return None
    resolved_path = Path(resolved)
    try:
        relative = resolved_path.relative_to(store_root.resolve(strict=True))
    except (OSError, ValueError):
        return None
    return resolved if len(relative.parts) == 1 and _STORE_NAME.fullmatch(relative.name) else None


def _read_text(path: Path, *, limit: int = 256) -> str | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            return None
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


@dataclass(frozen=True, slots=True)
class Generation:
    number: int
    system_path: str
    created_at: str | None
    nixos_version: str | None
    current_profile: bool
    current_runtime: bool
    booted: bool

    def to_mapping(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "systemPath": self.system_path,
            "createdAt": self.created_at,
            "nixosVersion": self.nixos_version,
            "currentProfile": self.current_profile,
            "currentRuntime": self.current_runtime,
            "booted": self.booted,
        }


@dataclass(frozen=True, slots=True)
class GenerationInspection:
    status: str
    generations: tuple[Generation, ...]
    profile_path: str | None
    runtime_path: str | None
    booted_path: str | None
    warnings: tuple[str, ...] = ()

    def to_mapping(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "generations": [item.to_mapping() for item in self.generations],
            "generationCount": len(self.generations),
            "profilePath": self.profile_path,
            "runtimePath": self.runtime_path,
            "bootedPath": self.booted_path,
            "warnings": list(self.warnings),
            "readOnly": True,
            "switchEnabled": False,
            "rollbackEnabled": False,
            "arbitraryCommandsAccepted": False,
        }


def inspect_generations(
    *,
    profiles_root: Path = Path("/nix/var/nix/profiles"),
    current_system: Path = Path("/run/current-system"),
    booted_system: Path = Path("/run/booted-system"),
    store_root: Path = Path("/nix/store"),
) -> GenerationInspection:
    """Inspect NixOS generation links without invoking Nix or changing profiles."""

    profile_path = _resolved_store_path(profiles_root / "system", store_root)
    runtime_path = _resolved_store_path(current_system, store_root)
    booted_path = _resolved_store_path(booted_system, store_root)
    warnings: list[str] = []
    generations: list[Generation] = []

    try:
        entries = tuple(profiles_root.iterdir())
    except OSError as error:
        entries = ()
        warnings.append(f"NixOS generation profile directory is unavailable: {error}")

    for link in entries:
        match = _GENERATION_LINK.fullmatch(link.name)
        if match is None:
            continue
        system_path = _resolved_store_path(link, store_root)
        if system_path is None:
            warnings.append(f"Ignored unsafe or broken generation link: {link.name}")
            continue
        try:
            timestamp = datetime.fromtimestamp(
                link.lstat().st_mtime, tz=timezone.utc
            ).isoformat().replace("+00:00", "Z")
        except (OSError, OverflowError, ValueError):
            timestamp = None
        generations.append(
            Generation(
                number=int(match.group(1)),
                system_path=system_path,
                created_at=timestamp,
                nixos_version=_read_text(Path(system_path) / "nixos-version"),
                current_profile=system_path == profile_path,
                current_runtime=system_path == runtime_path,
                booted=system_path == booted_path,
            )
        )

    generations.sort(key=lambda item: item.number, reverse=True)
    status = "detected" if generations else "unavailable"
    if generations and profile_path is None:
        warnings.append("The current system profile link could not be resolved safely")
    return GenerationInspection(
        status=status,
        generations=tuple(generations),
        profile_path=profile_path,
        runtime_path=runtime_path,
        booted_path=booted_path,
        warnings=tuple(warnings),
    )
