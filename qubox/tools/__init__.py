"""Pulse-generation and registration utilities for the qubox toolkit.

All symbols here are free of ``qubox_v2_legacy`` dependencies.

Sub-modules
-----------
waveforms
    Pure NumPy / SciPy waveform generators (DRAG, Kaiser, CLEAR, flat-top, …).
generators
    Pulse-registration helpers for ``PulseOperationManager``
    (rotation suites, displacement pulses).
"""

from .waveforms import (
    drag_gaussian_pulse_waveforms,
    drag_cosine_pulse_waveforms,
    kaiser_pulse_waveforms,
    slepian_pulse_waveforms,
    flattop_gaussian_waveform,
    flattop_cosine_waveform,
    flattop_tanh_waveform,
    flattop_blackman_waveform,
    blackman_integral_waveform,
    CLEAR_waveform,
    design_clear_kicks_from_rates,
    build_CLEAR_waveform_from_physics,
    gaussian_amp_for_same_rotation,
)
from .generators import (
    register_qubit_rotation,
    register_rotations_from_ref_iq,
    ensure_displacement_ops,
    validate_displacement_ops,
    MAX_AMPLITUDE,
)

__all__ = [
    # waveforms
    "drag_gaussian_pulse_waveforms",
    "drag_cosine_pulse_waveforms",
    "kaiser_pulse_waveforms",
    "slepian_pulse_waveforms",
    "flattop_gaussian_waveform",
    "flattop_cosine_waveform",
    "flattop_tanh_waveform",
    "flattop_blackman_waveform",
    "blackman_integral_waveform",
    "CLEAR_waveform",
    "design_clear_kicks_from_rates",
    "build_CLEAR_waveform_from_physics",
    "gaussian_amp_for_same_rotation",
    # generators
    "register_qubit_rotation",
    "register_rotations_from_ref_iq",
    "ensure_displacement_ops",
    "validate_displacement_ops",
    "MAX_AMPLITUDE",
]
