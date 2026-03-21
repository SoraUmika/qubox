"""Pulse-registration generators for the qubox toolkit.

Helper utilities for building and registering qubit-rotation and displacement
pulses on a PulseOperationManager.  No dependency on ``qubox_v2_legacy``.

Migrated from ``qubox_v2_legacy.tools.generators`` with the following changes:
- ``from ..pulses.manager import PulseOperationManager`` removed (duck-typed).
- ``from ..core.types import MAX_AMPLITUDE`` replaced by the constant below.
"""

from __future__ import annotations

from typing import Dict, Iterable, Optional, Tuple, Union

import numpy as np

from .waveforms import drag_gaussian_pulse_waveforms

# OPX hardware maximum output amplitude (volts peak).
MAX_AMPLITUDE: float = 0.45


# ---------------------------------------------------------------------------
# Single-rotation registration
# ---------------------------------------------------------------------------

def register_qubit_rotation(
    pom,
    *,
    name: str,
    axis: str,
    rlen: float,
    amp: float,
    waveform_type: str = "drag",
    drag_coeff: float | None = None,
    anharmonicity: float | None = None,
    element: str = "qubit",
    sigma: float | None = None,
    persist: bool = True,
    override: bool = True,
) -> None:
    """Register a single qubit rotation on a PulseOperationManager.

    Parameters
    ----------
    pom :
        PulseOperationManager (or any object with ``create_control_pulse``).
    name : str
        Operation name, e.g. ``"x180"``, ``"x90"``.
    axis : {"X", "Y"}
        Rotation axis in the IQ plane.
    rlen : float
        Pulse length in ns.
    amp : float
        Amplitude for this rotation.
    waveform_type : {"constant", "drag", "drag_gaussian_pulse_waveforms"}
        Envelope shape.
    drag_coeff : float, optional
        DRAG coefficient (required for DRAG mode).
    anharmonicity : float, optional
        Qubit anharmonicity in Hz (required for DRAG mode).
    element : str
        Qubit element name.
    sigma : float, optional
        Gaussian sigma in ns (defaults to rlen/6 for DRAG).
    persist, override : bool
        Passed to ``pom.create_control_pulse``.
    """
    axis_u = axis.upper()
    if axis_u not in {"X", "Y"}:
        raise ValueError(f"axis must be 'X' or 'Y', got {axis!r}")

    wf_u = waveform_type.lower()
    if wf_u in {"drag", "drag_gaussian", "drag_gaussian_pulse_waveforms"}:
        wf_mode = "drag"
    elif wf_u == "constant":
        wf_mode = "constant"
    else:
        raise ValueError(
            "waveform_type must be 'constant' or 'drag_gaussian_pulse_waveforms', "
            f"got {waveform_type!r}"
        )

    if wf_mode == "constant":
        z = np.array(amp, dtype=complex)
    else:
        if drag_coeff is None or anharmonicity is None:
            raise ValueError("drag_coeff and anharmonicity must be provided for DRAG mode")
        if sigma is None:
            sigma = rlen / 6.0
        gauss, drag = drag_gaussian_pulse_waveforms(amp, rlen, sigma, drag_coeff, anharmonicity)
        z = np.array(gauss, dtype=float) + 1j * np.array(drag, dtype=float)

    if axis_u == "Y":
        z = z * 1j

    pom.create_control_pulse(
        element=element,
        op=name,
        length=rlen,
        pulse_name=f"{name}_pulse",
        I_wf_name=f"{name}_I_wf",
        Q_wf_name=f"{name}_Q_wf",
        I_samples=z.real,
        Q_samples=z.imag,
        persist=persist,
        override=override,
    )


# ---------------------------------------------------------------------------
# Multi-rotation registration from reference IQ
# ---------------------------------------------------------------------------

def _as_padded_complex(I, Q, *, pad_to_4: bool = True) -> np.ndarray:
    I = np.asarray(I, dtype=float)
    Q = np.asarray(Q, dtype=float)
    if I.shape != Q.shape:
        raise ValueError("I and Q must have the same shape.")
    if pad_to_4:
        pad = (-len(I)) % 4
        if pad:
            I = np.pad(I, (0, pad))
            Q = np.pad(Q, (0, pad))
    return I + 1j * Q


def register_rotations_from_ref_iq(
    pom,
    ref_I,
    ref_Q,
    *,
    element: str = "qubit",
    prefix: str = "",
    rotations: Union[str, Iterable[str]] = ("ref_r180",),
    make_r0: bool = True,
    override: bool = True,
    persist: bool = False,
    d_lambda_map: Optional[Dict[str, float]] = None,
    d_alpha_map: Optional[Dict[str, float]] = None,
    d_omega_map: Optional[Dict[str, float]] = None,
) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """Register rotations derived from a reference IQ waveform (x180).

    Core waveform formula::

        w0       = pad_to_4(ref_I + 1j*ref_Q)
        phi_eff  = phi + d_alpha
        amp_scale = (theta / pi) * (1 + d_lambda / lam0)
        w_new    = amp_scale * w0 * exp(-1j * phi_eff)

    Convention table::

        x180  → theta=π,   phi=0
        x90   → theta=π/2, phi=0
        xn90  → theta=−π/2,phi=0
        y180  → theta=π,   phi=π/2
        y90   → theta=π/2, phi=π/2
        yn90  → theta=−π/2,phi=π/2

    Parameters
    ----------
    pom :
        PulseOperationManager instance (duck-typed).
    ref_I, ref_Q : array-like
        I and Q samples of the reference x180 waveform.
    element : str
        Qubit element name.
    prefix : str
        Optional name prefix for all registered operations.
    rotations : str or iterable of str
        Which rotations to register; use ``"all"`` for the full set.
    make_r0 : bool
        If True, also register a zero-amplitude ``r0`` pulse.
    override, persist : bool
        Passed to ``pom.create_control_pulse``.
    d_lambda_map, d_alpha_map, d_omega_map : dict, optional
        Per-rotation correction maps (amplitude, phase, detuning).

    Returns
    -------
    dict mapping op_name → (I_samples, Q_samples).
    """
    I0 = np.asarray(ref_I, dtype=float)
    Q0 = np.asarray(ref_Q, dtype=float)
    if I0.shape != Q0.shape:
        raise ValueError(f"ref_I shape {I0.shape} != ref_Q shape {Q0.shape}")

    if isinstance(rotations, str):
        rotations = (rotations,)
    rot_set = set(rotations)

    allowed = {"ref_r180", "x180", "x90", "xn90", "y180", "y90", "yn90", "all"}
    unknown = rot_set - allowed
    if unknown:
        raise ValueError(f"Unknown rotations: {sorted(unknown)}")
    if "all" in rot_set:
        rot_set = {"ref_r180", "x180", "x90", "xn90", "y180", "y90", "yn90"}

    THETA_PHI: Dict[str, Tuple[float, float]] = {
        "ref_r180": (np.pi, 0.0),
        "x180":  (np.pi, 0.0),
        "x90":   (np.pi / 2.0, 0.0),
        "xn90":  (-np.pi / 2.0, 0.0),
        "y180":  (np.pi, np.pi / 2.0),
        "y90":   (np.pi / 2.0, np.pi / 2.0),
        "yn90":  (-np.pi / 2.0, np.pi / 2.0),
    }

    d_lambda_map = {} if d_lambda_map is None else dict(d_lambda_map)
    d_alpha_map  = {} if d_alpha_map  is None else dict(d_alpha_map)
    d_omega_map  = {} if d_omega_map  is None else dict(d_omega_map)

    created: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    w0 = _as_padded_complex(I0, Q0, pad_to_4=True)
    N = len(w0)

    def _mk_names(op_full: str):
        return (f"{op_full}_pulse", f"{op_full}_I_wf", f"{op_full}_Q_wf")

    if make_r0:
        op_full = f"{prefix}r0"
        pulse_name, I_wf_name, Q_wf_name = _mk_names(op_full)
        Iz = np.zeros(N, dtype=float)
        Qz = np.zeros(N, dtype=float)
        pom.create_control_pulse(
            element=element, op=op_full, length=N,
            pulse_name=pulse_name, I_wf_name=I_wf_name, Q_wf_name=Q_wf_name,
            I_samples=Iz, Q_samples=Qz, persist=persist, override=override,
        )
        created[op_full] = (Iz, Qz)

    if "ref_r180" in rot_set:
        op_full = f"{prefix}ref_r180"
        pulse_name, I_wf_name, Q_wf_name = _mk_names(op_full)
        I_padded = np.real(w0).astype(float)
        Q_padded = np.imag(w0).astype(float)
        pom.create_control_pulse(
            element=element, op=op_full, length=N,
            pulse_name=pulse_name, I_wf_name=I_wf_name, Q_wf_name=Q_wf_name,
            I_samples=I_padded, Q_samples=Q_padded, persist=persist, override=override,
        )
        created[op_full] = (I_padded, Q_padded)
        rot_set = rot_set - {"ref_r180"}

    for op in sorted(rot_set):
        theta, phi = THETA_PHI[op]
        dlam = float(d_lambda_map.get(op, 0.0))
        dalp = float(d_alpha_map.get(op, 0.0))
        phi_eff = phi + dalp

        dt = 1e-9
        T = N * dt
        lam0 = (np.pi / (2.0 * T)) if T != 0.0 else 1.0
        amp_scale = (theta / np.pi) * (1.0 + dlam / lam0)

        w_new = amp_scale * w0 * np.exp(-1j * phi_eff)

        dome = float(d_omega_map.get(op, 0.0))
        if dome != 0.0:
            t_arr = (np.arange(N) - (N - 1) / 2.0) * dt
            w_new = w_new * np.exp(1j * dome * t_arr)

        I_samp = np.real(w_new).astype(float)
        Q_samp = np.imag(w_new).astype(float)
        alias_op = f"{prefix}{op}"
        pulse_name, I_wf_name, Q_wf_name = _mk_names(alias_op)
        pom.create_control_pulse(
            element=element, op=alias_op, length=N,
            pulse_name=pulse_name, I_wf_name=I_wf_name, Q_wf_name=Q_wf_name,
            I_samples=I_samp, Q_samples=Q_samp, persist=persist, override=override,
        )
        created[alias_op] = (I_samp, Q_samp)

    return created


# ---------------------------------------------------------------------------
# Displacement pulse registration
# ---------------------------------------------------------------------------

def ensure_displacement_ops(
    pom,
    *,
    element: str = "storage",
    n_list: list[int] | None = None,
    n_max: int = 3,
    alpha_list: list[complex] | None = None,
    coherent_amp: float = 0.2,
    coherent_len: int = 100,
    b_alpha: complex = 1.0,
    persist: bool = False,
    override: bool = True,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Register displacement pulses ``disp_n0``, ``disp_n1``, ... for Fock-resolved experiments.

    Parameters
    ----------
    pom :
        PulseOperationManager (duck-typed).
    element : str
        Storage cavity element name.
    n_list : list[int], optional
        Fock numbers to generate. Defaults to ``range(n_max)``.
    n_max : int
        If *n_list* is None, generate for ``range(n_max)``.
    alpha_list : list[complex], optional
        Per-Fock displacement amplitudes. Auto-scaled if None.
    coherent_amp : float
        Base waveform amplitude for the constant displacement.
    coherent_len : int
        Pulse length in ns (>= 16, divisible by 4).
    b_alpha : complex
        Reference displacement amplitude for scaling.
    persist, override : bool
        Passed to ``pom.create_control_pulse``.

    Returns
    -------
    dict mapping op_name → (I_wf, Q_wf).
    """
    if n_list is None:
        n_list = list(range(n_max))
    if not n_list:
        return {}

    if coherent_len < 16:
        raise ValueError(f"coherent_len must be >= 16, got {coherent_len}")
    pad_len = coherent_len + ((-coherent_len) % 4)

    if alpha_list is None:
        if abs(b_alpha) == 0:
            raise ValueError("b_alpha must be nonzero for auto-scaling")
        alpha_list = [b_alpha * np.sqrt(n + 0.5) for n in n_list]

    if len(alpha_list) != len(n_list):
        raise ValueError(
            f"alpha_list length ({len(alpha_list)}) must match n_list length ({len(n_list)})"
        )

    created: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    I_tpl = np.ones(pad_len, dtype=float) * float(coherent_amp)
    Q_tpl = np.zeros(pad_len, dtype=float)

    for n, alpha_n in zip(n_list, alpha_list):
        alpha_n = complex(alpha_n)
        op_name = f"disp_n{n}"

        ratio = (alpha_n / complex(b_alpha)) if abs(b_alpha) > 0 else complex(1.0, 0.0)
        c, s = float(np.real(ratio)), float(np.imag(ratio))
        I_new = c * I_tpl - s * Q_tpl
        Q_new = s * I_tpl + c * Q_tpl

        amp_max = max(np.max(np.abs(I_new)), np.max(np.abs(Q_new)))
        if amp_max > MAX_AMPLITUDE:
            scale = MAX_AMPLITUDE / amp_max
            I_new *= scale
            Q_new *= scale

        pom.create_control_pulse(
            element=element,
            op=op_name,
            length=pad_len,
            pulse_name=f"{op_name}_pulse",
            I_wf_name=f"{op_name}_I_wf",
            Q_wf_name=f"{op_name}_Q_wf",
            I_samples=I_new,
            Q_samples=Q_new,
            persist=persist,
            override=override,
        )
        created[op_name] = (I_new, Q_new)

    return created


def validate_displacement_ops(pom, element: str, disp_names: list[str]) -> list[str]:
    """Return a list of displacement op names that are not yet registered.

    Parameters
    ----------
    pom :
        PulseOperationManager (duck-typed; must have ``get_pulseOp_by_element_op``).
    element : str
        Storage element name.
    disp_names : list[str]
        Expected displacement operation names.
    """
    return [
        name for name in disp_names
        if pom.get_pulseOp_by_element_op(element, name, strict=False) is None
    ]
