from __future__ import annotations

from importlib.resources import files
import json
from typing import Any


def load_catalog() -> list[dict[str, Any]]:
    resource = files("nix_control_manager").joinpath("data/catalog.json")
    return json.loads(resource.read_text(encoding="utf-8"))
