"""Explicit readout emission helpers for QUA programs."""

from __future__ import annotations

from typing import Any

from qm.qua import Math, align, amp, assign, declare, dual_demod, fixed, measure, play


def emit_measurement(
    readout: "ReadoutHandle",
    *,
    targets: list | None = None,
    with_state: bool = False,
    state: Any | None = None,
    gain: float | None = None,
    timestamp_stream: Any | None = None,
    adc_stream: Any | None = None,
    axis: str = "z",
    x90: str = "x90",
    yn90: str = "yn90",
    qb_el: str | None = None,
) -> tuple:
    """Emit a QUA ``measure()`` statement using an explicit ``ReadoutHandle``."""
    from ...core.bindings import ReadoutHandle as _ReadoutHandle

    if not isinstance(readout, _ReadoutHandle):
        raise TypeError(
            f"emit_measurement: expected ReadoutHandle, got {type(readout).__name__}"
        )

    element = readout.element
    operation = readout.operation
    cal = readout.cal

    if targets is None:
        targets = [declare(fixed), declare(fixed)]

    weight_keys = cal.weight_keys
    outputs: list[Any] = []
    if len(weight_keys) >= 2:
        outputs.append(dual_demod.full(weight_keys[0], weight_keys[1], targets[0]))
    if len(weight_keys) >= 3 and len(targets) >= 2:
        outputs.append(dual_demod.full(weight_keys[2], weight_keys[0], targets[1]))

    pulse = operation if gain is None else operation * amp(gain)

    if axis == "x" and qb_el is not None:
        play(yn90, qb_el)
        align(qb_el, element)
    elif axis == "y" and qb_el is not None:
        play(x90, qb_el)
        align(qb_el, element)

    measure(
        pulse,
        element,
        None,
        *outputs,
        timestamp_stream=timestamp_stream,
        adc_stream=adc_stream,
    )
    align()

    make_state = with_state or (state is not None)
    if make_state and state is None:
        state = declare(bool)

    threshold = cal.threshold if cal is not None else None
    if make_state and threshold is not None:
        i_var = targets[0]
        if cal.rotation_angle is not None:
            q_var = targets[1] if len(targets) > 1 else None
            if q_var is not None:
                i_rot = declare(fixed)
                assign(
                    i_rot,
                    Math.cos2pi(cal.rotation_angle / (2.0 * 3.141592653589793)) * i_var
                    - Math.sin2pi(cal.rotation_angle / (2.0 * 3.141592653589793)) * q_var,
                )
                assign(state, i_rot > cal.threshold)
            else:
                assign(state, i_var > cal.threshold)
        else:
            assign(state, i_var > cal.threshold)
        return (*targets, state)

    return tuple(targets)


__all__ = ["emit_measurement"]
