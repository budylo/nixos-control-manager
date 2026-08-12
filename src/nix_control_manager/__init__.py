"""Nix Control Manager core package."""

from .model import ManagedState
from .nix_generator import generate_module

__all__ = ["ManagedState", "generate_module"]
__version__ = "0.1.0"
