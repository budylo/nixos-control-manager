"""Nix Control Manager core package."""

from .model import ManagedState
from .nix_generator import generate_module
from .version import RELEASE_VERSION as __version__

__all__ = ["ManagedState", "generate_module"]
