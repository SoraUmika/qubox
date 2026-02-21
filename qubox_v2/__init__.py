# qubox_v2 — Restructured Quantum Box API
# =========================================
#
# This is the modernized, modular version of the qubox package.
# All public symbols are re-exported here for convenience.
#
# Architecture layers:
#   core/        — Config models, protocols, errors, logging
#   hardware/    — OPX+/Octave control (config, controller, runner, queue)
#   devices/     — External instrument management (DeviceManager)
#   pulses/      — Waveform & pulse lifecycle (PulseOperationManager)
#   programs/    — QUA program factories + macros
#   experiments/ — Experiment orchestration (one class per experiment type)
#   gates/       — Gate models, noise, Kraus/superoperator algebra
#   compile/     — Gate compilation via ansatz optimization
#   simulation/  — cQED Hamiltonian + Lindblad solver (QuTiP)
#   analysis/    — Fitting, metrics, output containers, plotting
#   tools/       — Waveform generators
#   compat/      — Backward-compatibility shim for old import paths
#

__version__ = "2.0.0"

from .core.logging import configure_global_logging, get_logger

# Configure once on import
configure_global_logging(level="INFO")

__all__ = [
    "__version__",
    "configure_global_logging",
    "get_logger",
]
