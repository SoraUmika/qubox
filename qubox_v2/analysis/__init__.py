"""Legacy analysis namespace preserved for backward compatibility.

New analysis code should import from `qubox_tools`. Execution/runtime code
continues to live in `qubox_v2`.
"""

from . import cQED_attributes, pulseOp
from qubox_tools.algorithms import core as algorithms
from qubox_tools.algorithms import metrics, post_process, post_selection, transforms as analysis_tools
from qubox_tools.data import containers as output
from qubox_tools.fitting import cqed as cQED_models
from qubox_tools.fitting import models, pulse_train as pulse_train_models, routines as fitting
from qubox_tools.plotting import common as plotting
from qubox_tools.plotting import cqed as cQED_plottings

__all__ = [
    "algorithms",
    "analysis_tools",
    "cQED_attributes",
    "cQED_models",
    "cQED_plottings",
    "fitting",
    "metrics",
    "models",
    "output",
    "plotting",
    "post_process",
    "post_selection",
    "pulseOp",
    "pulse_train_models",
]
