"""qubox_v2.compat.legacy
========================
Backward-compatibility shim for code that imports the old flat
``qubox`` layout (e.g. ``from qubox.program_manager import …``).

Usage
-----
Add this *once* at the very top of a legacy notebook::

    import qubox_v2.compat.legacy      # patches sys.modules

After that, ``import qubox.program_manager`` etc. will transparently
redirect to the restructured ``qubox_v2`` sub-packages.

.. warning::

   This is a convenience bridge during migration.  New code should
   import directly from the ``qubox_v2.*`` namespace.
"""
from __future__ import annotations

import importlib
import sys
import types
import warnings

# ---------------------------------------------------------------------------
# Mapping: old module path → new module path
# ---------------------------------------------------------------------------
_REDIRECTS: dict[str, str] = {
    # Hardware layer
    "qubox.program_manager":        "qubox_v2.hardware",
    # Devices
    "qubox.device_manager":         "qubox_v2.devices.device_manager",
    # Pulses
    "qubox.pulse_manager":          "qubox_v2.pulses.manager",
    # Programs & macros
    "qubox.cQED_programs":          "qubox_v2.programs.cQED_programs",
    "qubox.macros.measure_macro":   "qubox_v2.programs.macros.measure",
    "qubox.macros.sequence_macro":  "qubox_v2.programs.macros.sequence",
    # Experiments
    "qubox.cQED_experiments":       "qubox_v2.experiments.legacy_experiment",
    # Config
    "qubox.config_builder":         "qubox_v2.experiments.config_builder",
    # Gates
    "qubox.gates_legacy":           "qubox_v2.experiments.gates_legacy",
    # Logging
    "qubox.logging_config":         "qubox_v2.core.logging",
    # Analysis (sub-package)
    "qubox.analysis":               "qubox_v2.analysis",
    "qubox.analysis.output":        "qubox_v2.analysis.output",
    "qubox.analysis.fitting":       "qubox_v2.analysis.fitting",
    "qubox.analysis.algorithms":    "qubox_v2.analysis.algorithms",
    "qubox.analysis.plotting":      "qubox_v2.analysis.plotting",
    "qubox.analysis.cQED_models":   "qubox_v2.analysis.cQED_models",
    "qubox.analysis.cQED_attributes": "qubox_v2.analysis.cQED_attributes",
    "qubox.analysis.cQED_plottings": "qubox_v2.analysis.cQED_plottings",
    "qubox.analysis.analysis_tools": "qubox_v2.analysis.analysis_tools",
    "qubox.analysis.post_process":  "qubox_v2.analysis.post_process",
    "qubox.analysis.post_selection": "qubox_v2.analysis.post_selection",
    "qubox.analysis.pulseOp":       "qubox_v2.analysis.pulseOp",
    "qubox.analysis.metrics":       "qubox_v2.analysis.metrics",
    "qubox.analysis.models":        "qubox_v2.analysis.models",
    # Simulation (sub-package)
    "qubox.simulation":             "qubox_v2.simulation",
    "qubox.simulation.cQED":        "qubox_v2.simulation.cQED",
    # Compile (sub-package)
    "qubox.compile":                "qubox_v2.compile",
    # Gates (new sub-package)
    "qubox.gates":                  "qubox_v2.gates",
    # Tools
    "qubox.tools.generators":       "qubox_v2.tools.generators",
    "qubox.tools.waveforms":        "qubox_v2.tools.waveforms",
    # GUI
    "qubox.program_GUI":            "qubox_v2.gui.program_gui",
    # ── v3 additions ──
    # Calibration layer
    "qubox.calibration":            "qubox_v2.calibration",
    "qubox.calibration.store":      "qubox_v2.calibration.store",
    "qubox.calibration.models":     "qubox_v2.calibration.models",
    "qubox.calibration.history":    "qubox_v2.calibration.history",
    # Program category modules
    "qubox.programs":               "qubox_v2.programs",
    "qubox.programs.spectroscopy":  "qubox_v2.programs.spectroscopy",
    "qubox.programs.time_domain":   "qubox_v2.programs.time_domain",
    "qubox.programs.calibration":   "qubox_v2.programs.calibration",
    "qubox.programs.readout":       "qubox_v2.programs.readout",
    "qubox.programs.cavity":        "qubox_v2.programs.cavity",
    "qubox.programs.tomography":    "qubox_v2.programs.tomography",
    # Pulse registry
    "qubox.pulses":                 "qubox_v2.pulses",
    "qubox.pulses.pulse_registry":  "qubox_v2.pulses.pulse_registry",
    "qubox.pulses.integration_weights": "qubox_v2.pulses.integration_weights",
    "qubox.pulses.waveforms":       "qubox_v2.pulses.waveforms",
    # Experiment subdirectories
    "qubox.experiments":            "qubox_v2.experiments",
    "qubox.experiments.session":    "qubox_v2.experiments.session",
    "qubox.experiments.result":     "qubox_v2.experiments.result",
    "qubox.experiments.spectroscopy": "qubox_v2.experiments.spectroscopy",
    "qubox.experiments.time_domain":  "qubox_v2.experiments.time_domain",
    "qubox.experiments.calibration":  "qubox_v2.experiments.calibration",
    "qubox.experiments.cavity":       "qubox_v2.experiments.cavity",
    "qubox.experiments.tomography":   "qubox_v2.experiments.tomography",
    "qubox.experiments.spa":          "qubox_v2.experiments.spa",
    # Core types
    "qubox.core":                   "qubox_v2.core",
    "qubox.core.types":             "qubox_v2.core.types",
}


class _LegacyFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Custom import finder/loader that intercepts ``qubox.*`` imports."""

    def find_module(self, fullname: str, path=None):
        if fullname in _REDIRECTS:
            return self
        return None

    def load_module(self, fullname: str):
        if fullname in sys.modules:
            return sys.modules[fullname]

        new_name = _REDIRECTS[fullname]
        warnings.warn(
            f"Deprecated import '{fullname}' — use '{new_name}' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        mod = importlib.import_module(new_name)
        sys.modules[fullname] = mod
        return mod


# Install the finder on first import of this module
_finder = _LegacyFinder()
if _finder not in sys.meta_path:
    sys.meta_path.insert(0, _finder)

# Also inject a stub 'qubox' package so attribute access works
if "qubox" not in sys.modules:
    _qubox_stub = types.ModuleType("qubox")
    _qubox_stub.__path__ = []  # type: ignore[attr-defined]
    _qubox_stub.__doc__ = "Legacy compatibility stub — see qubox_v2"
    sys.modules["qubox"] = _qubox_stub
