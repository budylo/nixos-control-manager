from __future__ import annotations

from difflib import unified_diff
from pathlib import Path

from .model import ManagedState
from .nix_generator import generate_module
from .storage import read_text_if_exists


def build_preview(state: ManagedState, output_path: Path) -> dict[str, str]:
    previous = read_text_if_exists(output_path)
    generated = generate_module(state)
    diff = "".join(
        unified_diff(
            previous.splitlines(keepends=True),
            generated.splitlines(keepends=True),
            fromfile=output_path.name,
            tofile=f"{output_path.name} (candidate)",
        )
    )
    return {"generated": generated, "diff": diff}
