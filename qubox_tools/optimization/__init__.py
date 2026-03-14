"""Optimization helpers for calibration and analysis workflows."""

from importlib import import_module

_SUBMODULES = {"bayesian", "local", "stochastic"}


def __getattr__(name):
    if name in _SUBMODULES:
        module = import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["bayesian", "local", "stochastic"]
