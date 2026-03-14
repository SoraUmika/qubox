"""Legacy import map for the analysis extraction."""

LEGACY_ANALYSIS_MAP = {
    "qubox_v2.analysis.fitting": "qubox_tools.fitting.routines",
    "qubox_v2.analysis.models": "qubox_tools.fitting.models",
    "qubox_v2.analysis.cQED_models": "qubox_tools.fitting.cqed",
    "qubox_v2.analysis.pulse_train_models": "qubox_tools.fitting.pulse_train",
    "qubox_v2.analysis.calibration_algorithms": "qubox_tools.fitting.calibration",
    "qubox_v2.analysis.plotting": "qubox_tools.plotting.common",
    "qubox_v2.analysis.cQED_plottings": "qubox_tools.plotting.cqed",
    "qubox_v2.analysis.algorithms": "qubox_tools.algorithms.core",
    "qubox_v2.analysis.analysis_tools": "qubox_tools.algorithms.transforms",
    "qubox_v2.analysis.post_process": "qubox_tools.algorithms.post_process",
    "qubox_v2.analysis.post_selection": "qubox_tools.algorithms.post_selection",
    "qubox_v2.analysis.metrics": "qubox_tools.algorithms.metrics",
    "qubox_v2.analysis.output": "qubox_tools.data.containers",
    "qubox_v2.optimization.optimization": "qubox_tools.optimization.bayesian",
    "qubox_v2.optimization.smooth_opt": "qubox_tools.optimization.local",
    "qubox_v2.optimization.stochastic_opt": "qubox_tools.optimization.stochastic",
}
