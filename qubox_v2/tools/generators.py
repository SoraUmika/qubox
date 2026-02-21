
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

