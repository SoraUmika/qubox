"""Fit models and fitting routines."""

from importlib import import_module

from .routines import build_fit_legend, fit_and_wrap, generalized_fit

_SUBMODULES = {"calibration", "cqed", "models", "pulse_train", "routines"}


def __getattr__(name):
    if name in _SUBMODULES:
        module = import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "build_fit_legend",
    "calibration",
    "cqed",
    "fit_and_wrap",
    "generalized_fit",
    "models",
    "pulse_train",
    "routines",
]
