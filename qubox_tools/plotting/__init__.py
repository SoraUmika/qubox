"""Reusable plotting helpers for cQED analysis."""

from importlib import import_module

from .common import plot_hm

_SUBMODULES = {"common", "cqed"}


def __getattr__(name):
    if name in _SUBMODULES:
        module = import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["common", "cqed", "plot_hm"]
