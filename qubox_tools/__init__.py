"""Analysis-first tools for qubox experiment results.

`qubox_tools` is the canonical home for reusable fitting, plotting,
post-processing, and optimization helpers. The execution-facing API
remains in `qubox`.
"""

from importlib import import_module

from .data.containers import Output, OutputArray
from .fitting.routines import build_fit_legend, fit_and_wrap, generalized_fit

_SUBMODULES = {
    "algorithms",
    "data",
    "fitting",
    "optimization",
    "plotting",
}
_EXPORTS = {
    "PostSelectionConfig": ("qubox_tools.algorithms.post_selection", "PostSelectionConfig"),
    "plot_hm": ("qubox_tools.plotting.common", "plot_hm"),
}


def __getattr__(name):
    if name in _SUBMODULES:
        module = import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    if name in _EXPORTS:
        module_name, attr = _EXPORTS[name]
        value = getattr(import_module(module_name), attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Output",
    "OutputArray",
    "PostSelectionConfig",
    "algorithms",
    "build_fit_legend",
    "data",
    "fit_and_wrap",
    "fitting",
    "generalized_fit",
    "optimization",
    "plot_hm",
    "plotting",
]
