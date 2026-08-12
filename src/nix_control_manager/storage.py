from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from .errors import StorageError, ValidationError
from .model import ManagedState


def load_state(path: Path) -> ManagedState:
    if not path.exists():
        return ManagedState.empty()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return ManagedState.from_mapping(raw)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        if isinstance(error, ValidationError):
            raise
        raise StorageError(f"Could not read state from {path}: {error}") from error


def _atomic_write(path: Path, content: str, *, backup: bool) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if backup and path.exists():
            shutil.copy2(path, path.with_name(f"{path.name}.bak"))

        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
    except OSError as error:
        raise StorageError(f"Could not write {path}: {error}") from error


def save_state(path: Path, state: ManagedState) -> None:
    _atomic_write(path, serialize_state(state), backup=True)


def serialize_state(state: ManagedState) -> str:
    return json.dumps(
        state.to_mapping(), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"


def save_generated_module(path: Path, content: str) -> None:
    _atomic_write(path, content, backup=True)


def read_text_if_exists(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError as error:
        raise StorageError(f"Could not read {path}: {error}") from error
