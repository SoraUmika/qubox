"""Primitive pulse rotation seeding.

Ensures DRAG rotation waveforms are registered on a session's pulse
manager.  No notebook dependency — works with any object exposing
``pulse_mgr`` and ``burn_pulses``.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..tools.generators import register_rotations_from_ref_iq
from ..tools.waveforms import drag_gaussian_pulse_waveforms


def ensure_primitive_rotations(
    session_obj: Any,
    *,
    qb_element: str,
    amplitude: float,
    length: int,
    sigma: float,
    alpha: float,
    anharmonicity_hz: float,
    detuning_hz: float = 0.0,
    sampling_rate: float = 1e9,
    required_ops: Sequence[str] = ("x180", "x90"),
    rotations: Sequence[str] = ("ref_r180", "x180", "x90", "xn90", "y180", "y90", "yn90"),
    ref_op: str = "ref_r180",
    persist: bool = True,
    override: bool = True,
    force_register: bool = False,
) -> dict[str, Any]:
    """Seed primitive DRAG rotation pulses on a session's pulse manager.

    Parameters
    ----------
    session_obj:
        Object with ``pulse_mgr`` attribute and ``burn_pulses()`` method.
    qb_element:
        Target qubit element name.
    amplitude, length, sigma, alpha, anharmonicity_hz, detuning_hz:
        DRAG waveform parameters.
    sampling_rate:
        Waveform sampling rate in Hz.
    required_ops:
        Operations that must exist; seeding is triggered if any are missing.
    rotations:
        Full set of rotation operations to generate.
    ref_op:
        Name of the reference rotation pulse.
    persist, override:
        Forwarded to the pulse manager.
    force_register:
        If *True*, register even when all required_ops already exist.

    Returns
    -------
    dict with keys ``created``, ``created_ops``, ``missing_required_ops``,
    ``ref_op``, ``ref_i_samples``, ``ref_q_samples``.
    """
    pulse_mgr = session_obj.pulse_mgr
    missing_required_ops: list[str] = []
    for op_name in required_ops:
        try:
            pulse_mgr.get_pulseOp_by_element_op(qb_element, op_name, strict=True)
        except Exception:
            missing_required_ops.append(op_name)

    ref_i_samples, ref_q_samples = drag_gaussian_pulse_waveforms(
        amplitude=float(amplitude),
        length=int(length),
        sigma=float(sigma),
        alpha=float(alpha),
        anharmonicity=float(anharmonicity_hz),
        detuning=float(detuning_hz),
        subtracted=True,
        sampling_rate=float(sampling_rate),
    )

    created_ops: list[str] = []
    if force_register or missing_required_ops:
        pulse_mgr.create_control_pulse(
            element=qb_element,
            op=ref_op,
            length=int(length),
            I_samples=ref_i_samples,
            Q_samples=ref_q_samples,
            override=override,
            persist=persist,
        )
        created_ops = list(
            register_rotations_from_ref_iq(
                pulse_mgr,
                ref_i_samples,
                ref_q_samples,
                element=qb_element,
                rotations=tuple(rotations),
                persist=persist,
                override=override,
            )
        )
        session_obj.burn_pulses(include_volatile=True)

    return {
        "created": bool(force_register or missing_required_ops),
        "created_ops": created_ops,
        "missing_required_ops": missing_required_ops,
        "ref_op": ref_op,
        "ref_i_samples": list(ref_i_samples),
        "ref_q_samples": list(ref_q_samples),
    }


__all__ = ["ensure_primitive_rotations"]
