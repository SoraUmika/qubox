
import numpy as np

from .waveforms import *
from ..pulses.manager import PulseOperationManager
from typing import Dict, Iterable, Tuple, Union, Optional
def register_qubit_rotation(
    pom: PulseOperationManager,
    *,
    name: str,
    axis: str,                 # "X" or "Y"
    rlen: float,               # pulse length (ns)
    amp: float,                # amplitude for THIS rotation
    waveform_type: str = "drag",
    # DRAG-specific params (only used if waveform_type == "drag_gaussian_pulse_waveforms")
    drag_coeff: float | None = None,
    anharmonicity: float | None = None,
    element: str = "qubit",
    sigma: float | None = None,
    persist: bool = True,
    override: bool = True,
):
    """
    Register a single qubit rotation on the PulseOperationManager.

    Parameters
    ----------
    pom : PulseOperationManager
        Your PulseOperationManager instance.
    name : str
        Operation name to register (e.g. "x180", "x90", "y180", "y90").
    axis : {"X", "Y"}
        Rotation axis in the IQ plane:
          - "X": aligned along I (phase = 0)
          - "Y": rotated by +pi_val/2 in IQ (phase = +pi_val/2)
    rlen : float
        Pulse length (ns).
    amp : float
        Amplitude for this specific rotation (used as given).
    waveform_type : {"constant", "drag_gaussian_pulse_waveforms"}
        - "constant": flat complex envelope with magnitude = amp.
        - "drag_gaussian_pulse_waveforms": use your DRAG Gaussian generator.
    drag_coeff : float, optional
        DRAG coefficient (required if waveform_type is "drag_gaussian_pulse_waveforms").
    anharmonicity : float, optional
        Qubit anharmonicity in Hz (required if waveform_type is "drag_gaussian_pulse_waveforms").
    element : str, optional
        Qubit element name (default "qubit").
    sigma : float, optional
        Gaussian sigma (ns). If None, defaults to rlen / 6 for DRAG.
        Ignored for "constant".
    persist, override : bool, optional
        Passed to pom.create_control_pulse.
    """

    axis_u = axis.upper()
    if axis_u not in {"X", "Y"}:
        raise ValueError(f"axis must be 'X' or 'Y', got {axis!r}")

    wf_u = waveform_type.lower()
    # Allow both exact string and a shorter alias "drag"
    if wf_u in {"drag", "drag_gaussian", "drag_gaussian_pulse_waveforms"}:
        wf_mode = "drag"
    elif wf_u == "constant":
        wf_mode = "constant"
    else:
        raise ValueError(
            "waveform_type must be 'constant' or 'drag_gaussian_pulse_waveforms', "
            f"got {waveform_type!r}"
        )

    # --------------------------
    # Build complex envelope z(t)
    # --------------------------
    if wf_mode == "constant":
        # Simplest: treat as a single complex sample with magnitude = amp.
        # OPX / your pom typically supports scalar waveforms and treats them as const.
        z = np.array(amp, dtype=complex)
    else:
        # DRAG Gaussian envelope
        if drag_coeff is None or anharmonicity is None:
            raise ValueError(
                "drag_coeff and anharmonicity must be provided for "
                "waveform_type='drag'"
            )

        if sigma is None:
            sigma = rlen / 6.0

        gauss, drag = drag_gaussian_pulse_waveforms(
            amp, rlen, sigma, drag_coeff, anharmonicity
        )
        z = np.array(gauss, dtype=float) + 1j * np.array(drag, dtype=float)

    if axis_u == "Y":
        z = z * 1j  # e^{ipi_val/2}

    I_samples = z.real
    Q_samples = z.imag

    pom.create_control_pulse(
        element=element,
        op=name,
        length=rlen,
        pulse_name=f"{name}_pulse",
        I_wf_name=f"{name}_I_wf",
        Q_wf_name=f"{name}_Q_wf",
        I_samples=I_samples,
        Q_samples=Q_samples,
        persist=persist,
        override=override,
    )

import numpy as np
from typing import Dict, Iterable, Optional, Tuple, Union


def _as_padded_complex(I, Q, *, pad_to_4: bool = True) -> np.ndarray:
    """Combine I/Q into complex array, optionally padded to multiple of 4."""
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
):
    """
    Register rotations derived from a reference IQ waveform (assumed to be x180).

    Uses the same waveform math as gates_legacy.QubitRotation but without requiring
    Gate.attributes or Gate.mgr to be set.  The core formula is:

        w0 = pad_to_4(ref_I + 1j*ref_Q)
        phi_eff = phi + d_alpha
        amp_scale = (theta / pi) * (1.0 + d_lambda / lam0)
        w_new = amp_scale * w0 * exp(-1j * phi_eff)

    Convention table:
        x180  -> theta=pi,    phi=0
        x90   -> theta=pi/2,  phi=0
        xn90  -> theta=-pi/2, phi=0
        y180  -> theta=pi,    phi=pi/2
        y90   -> theta=pi/2,  phi=pi/2
        yn90  -> theta=-pi/2, phi=pi/2
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
        "x180": (np.pi, 0.0),
        "x90":  (np.pi / 2.0, 0.0),
        "xn90": (-np.pi / 2.0, 0.0),
        "y180": (np.pi, np.pi / 2.0),
        "y90":  (np.pi / 2.0, np.pi / 2.0),
        "yn90": (-np.pi / 2.0, np.pi / 2.0),
    }

    d_lambda_map = {} if d_lambda_map is None else dict(d_lambda_map)
    d_alpha_map  = {} if d_alpha_map  is None else dict(d_alpha_map)
    d_omega_map  = {} if d_omega_map  is None else dict(d_omega_map)

    created: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}

    # Build padded complex template once
    w0 = _as_padded_complex(I0, Q0, pad_to_4=True)
    N = len(w0)

    def _mk_names(op_full: str):
        return (f"{op_full}_pulse", f"{op_full}_I_wf", f"{op_full}_Q_wf")

    # Optional R0 (zeros) pulse
    if make_r0:
        op_full = f"{prefix}r0"
        pulse_name, I_wf_name, Q_wf_name = _mk_names(op_full)
        Izeros = np.zeros(N, dtype=float)
        Qzeros = np.zeros(N, dtype=float)
        pom.create_control_pulse(
            element=element,
            op=op_full,
            length=N,
            pulse_name=pulse_name,
            I_wf_name=I_wf_name,
            Q_wf_name=Q_wf_name,
            I_samples=Izeros,
            Q_samples=Qzeros,
            persist=persist,
            override=override,
        )
        created[op_full] = (Izeros, Qzeros)

    # Register ref_r180 directly (unmodified template) if requested
    if "ref_r180" in rot_set:
        op_full = f"{prefix}ref_r180"
        pulse_name, I_wf_name, Q_wf_name = _mk_names(op_full)
        I_padded = np.real(w0).astype(float)
        Q_padded = np.imag(w0).astype(float)
        pom.create_control_pulse(
            element=element,
            op=op_full,
            length=N,
            pulse_name=pulse_name,
            I_wf_name=I_wf_name,
            Q_wf_name=Q_wf_name,
            I_samples=I_padded,
            Q_samples=Q_padded,
            persist=persist,
            override=override,
        )
        created[op_full] = (I_padded, Q_padded)
        rot_set = rot_set - {"ref_r180"}

    # Build each remaining rotation using direct waveform math
    # matching gates_legacy.QubitRotation.waveforms() convention
    for op in sorted(rot_set):
        theta, phi = THETA_PHI[op]
        dlam = float(d_lambda_map.get(op, 0.0))
        dalp = float(d_alpha_map.get(op, 0.0))

        phi_eff = phi + dalp

        # d_lambda correction: lam0 = pi / (2*T) where T = N * dt
        # but since amp_scale = (theta/pi) * (1 + dlam/lam0) and
        # lam0 cancels dt, we just need N (length in samples) and
        # a nominal dt.  Use dt=1e-9 matching the default.
        dt = 1e-9
        T = N * dt
        lam0 = (np.pi / (2.0 * T)) if T != 0.0 else 1.0
        amp_scale = (theta / np.pi) * (1.0 + dlam / lam0)

        w_new = amp_scale * w0 * np.exp(-1j * phi_eff)

        # d_omega modulation (centered time array)
        dome = float(d_omega_map.get(op, 0.0))
        if dome != 0.0:
            t_arr = (np.arange(N) - (N - 1) / 2.0) * dt
            w_new = w_new * np.exp(1j * dome * t_arr)

        I_samp = np.real(w_new).astype(float)
        Q_samp = np.imag(w_new).astype(float)

        alias_op = f"{prefix}{op}"
        pulse_name, I_wf_name, Q_wf_name = _mk_names(alias_op)

        pom.create_control_pulse(
            element=element,
            op=alias_op,
            length=N,
            pulse_name=pulse_name,
            I_wf_name=I_wf_name,
            Q_wf_name=Q_wf_name,
            I_samples=I_samp,
            Q_samples=Q_samp,
            persist=persist,
            override=override,
        )

        created[alias_op] = (I_samp, Q_samp)

    return created


def ensure_displacement_ops(
    pom: PulseOperationManager,
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
    """Generate displacement pulses ``disp_n0, disp_n1, ...`` for Fock-resolved experiments.

    This is the canonical helper for creating displacement pulses that the
    Fock-resolved experiment classes expect.  It registers each displacement
    as a control pulse on the specified storage element.

    Parameters
    ----------
    pom : PulseOperationManager
        Pulse manager to register pulses into.
    element : str
        Storage cavity element name (default ``"storage"``).
    n_list : list[int], optional
        Fock numbers to generate displacements for.  Defaults to
        ``range(n_max)``.
    n_max : int
        If *n_list* is None, generate ``disp_n0`` through ``disp_n{n_max-1}``.
    alpha_list : list[complex], optional
        Displacement amplitudes per Fock number.  Length must match *n_list*.
        If None, uses linearly scaled amplitudes from ``b_alpha``:
        ``alpha_n = b_alpha * sqrt(n+1) / sqrt(1)`` (placeholder scaling).
    coherent_amp : float
        Base waveform amplitude for the constant displacement pulse.
    coherent_len : int
        Pulse length in ns (must be >= 16 and divisible by 4).
    b_alpha : complex
        Reference displacement alpha for scaling.
    persist : bool
        If True, store in permanent POM store.
    override : bool
        If True, overwrite existing pulses.

    Returns
    -------
    dict[str, tuple[np.ndarray, np.ndarray]]
        Mapping from op name (e.g. ``"disp_n0"``) to ``(I_wf, Q_wf)``.

    Example
    -------
    >>> from qubox_v2.tools.generators import ensure_displacement_ops
    >>> created = ensure_displacement_ops(
    ...     session.pulse_mgr,
    ...     element="storage",
    ...     n_max=3,
    ...     coherent_amp=0.2,
    ...     coherent_len=100,
    ... )
    >>> session.burn_pulses()
    """
    if n_list is None:
        n_list = list(range(n_max))
    if not n_list:
        return {}

    # Validate pulse length
    if coherent_len < 16:
        raise ValueError(f"coherent_len must be >= 16, got {coherent_len}")
    # Pad to multiple of 4
    pad_len = coherent_len + ((-coherent_len) % 4)

    # Build alpha list if not provided
    if alpha_list is None:
        if abs(b_alpha) == 0:
            raise ValueError("b_alpha must be nonzero for auto-scaling")
        # Simple scaling: alpha_n proportional to sqrt(n+1)
        alpha_list = [b_alpha * np.sqrt(n + 1) for n in n_list]

    if len(alpha_list) != len(n_list):
        raise ValueError(
            f"alpha_list length ({len(alpha_list)}) must match "
            f"n_list length ({len(n_list)})"
        )

    created: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    # Reference template: constant amplitude I, zero Q
    I_tpl = np.ones(pad_len, dtype=float) * float(coherent_amp)
    Q_tpl = np.zeros(pad_len, dtype=float)

    for n, alpha_n in zip(n_list, alpha_list):
        alpha_n = complex(alpha_n)
        op_name = f"disp_n{n}"

        # Scale by ratio to reference
        if abs(b_alpha) > 0:
            ratio = alpha_n / complex(b_alpha)
        else:
            ratio = complex(1.0, 0.0)

        c, s = float(np.real(ratio)), float(np.imag(ratio))
        I_new = c * I_tpl - s * Q_tpl
        Q_new = s * I_tpl + c * Q_tpl

        # Clip to MAX_AMPLITUDE
        from ..core.types import MAX_AMPLITUDE
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


def validate_displacement_ops(
    pom: PulseOperationManager,
    element: str,
    disp_names: list[str],
) -> list[str]:
    """Check that displacement ops exist for an element.

    Returns a list of missing operation names.  If the list is empty,
    all required displacement pulses are registered.

    Parameters
    ----------
    pom : PulseOperationManager
        Pulse manager to check.
    element : str
        Storage element name.
    disp_names : list[str]
        Expected displacement operation names (e.g. ``["disp_n0", "disp_n1"]``).

    Raises
    ------
    Nothing — returns missing names for the caller to handle.
    """
    missing = []
    for name in disp_names:
        info = pom.get_pulseOp_by_element_op(element, name, strict=False)
        if info is None:
            missing.append(name)
    return missing

