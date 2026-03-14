"""Compatibility notes and migration helpers for legacy users."""

from importlib import import_module

LEGACY_PACKAGE = "qubox_v2_legacy"


def __getattr__(name: str):
    if name == "notebook":
        module = import_module(f"{__name__}.notebook")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["LEGACY_PACKAGE", "notebook"]
