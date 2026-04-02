"""Post-processing, metrics, and analysis algorithms."""

from importlib import import_module

_SUBMODULES = {"core", "metrics", "post_process", "post_selection", "readout_analysis", "transforms"}


def __getattr__(name):
    if name in _SUBMODULES:
        module = import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["core", "metrics", "post_process", "post_selection", "readout_analysis", "transforms"]
