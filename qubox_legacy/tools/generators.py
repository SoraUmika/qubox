
from .waveforms import *
from ..pulse_manager import PulseOperationManager
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
          - "Y": rotated by +π/2 in IQ (phase = +π/2)
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
        z = z * 1j  # e^{iπ/2}

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
from ..gates_legacy import QubitRotation
import numpy as np
from typing import Dict, Iterable, Optional, Tuple, Union


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
    # keep these hooks; they map cleanly onto QubitRotation knobs
    d_lambda_map: Optional[Dict[str, float]] = None,
    d_alpha_map: Optional[Dict[str, float]] = None,
    d_omega_map: Optional[Dict[str, float]] = None,
    # keep your global sign flip (applies to the reference template itself)
):
    """
    Register rotations derived from a reference IQ waveform (assumed to be x180),
    but implemented via QubitRotation.

    Strategy:
      1) Use (ref_I, ref_Q) as the explicit x180 template inside QubitRotation.
      2) For each requested op in {x180,x90,xn90,y180,y90,yn90}, build a QubitRotation
         with the (theta, phi) values for the convention:
            U(theta,phi) = exp[-i theta/2 (cos(phi) sx + sin(phi) sy)]
         where phi=0 -> +X, phi=+pi/2 -> +Y.

    Notes:
      - global_sign multiplies the complex template (I + iQ) before building any pulses.
      - This function assumes your QubitRotation.build() registers a PulseOp into the
        PulseOperationManager. We then alias the created op name to a nice name like
        f"{prefix}x90" by copying/renaming the registered pulse op (best-effort).
    """

    I0 = np.asarray(ref_I, dtype=float)
    Q0 = np.asarray(ref_Q, dtype=float)
    if I0.shape != Q0.shape:
        raise ValueError(f"ref_I shape {I0.shape} != ref_Q shape {Q0.shape}")

    # Apply global sign to the *complex* template (equivalent to I,Q both multiplied)

    if isinstance(rotations, str):
        rotations = (rotations,)
    rot_set = set(rotations)

    allowed = {"ref_r180", "x180", "x90", "xn90", "y180", "y90", "yn90", "all"}
    unknown = rot_set - allowed
    if unknown:
        raise ValueError(f"Unknown rotations: {sorted(unknown)}")

    if "all" in rot_set:
        rot_set = {"ref_r180", "x180", "x90", "xn90", "y180", "y90", "yn90"}

    # Convention table (your requested one)
    THETA_PHI: Dict[str, Tuple[float, float]] = {
        "ref_r180": (np.pi, 0.0),  # Reference x180 rotation (registered separately)
        "x180": (np.pi, 0.0),
        "x90":  (np.pi / 2.0, 0.0),
        "xn90": (-np.pi / 2.0, 0.0),
        "y180": (np.pi, np.pi / 2.0),
        "y90":  (np.pi / 2.0, np.pi / 2.0),
        "yn90": (-np.pi / 2.0, np.pi / 2.0),
    }

    # Default tweak maps
    d_lambda_map = {} if d_lambda_map is None else dict(d_lambda_map)
    d_alpha_map  = {} if d_alpha_map  is None else dict(d_alpha_map)
    d_omega_map  = {} if d_omega_map  is None else dict(d_omega_map)

    created: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}

    def _mk_names(op_full: str):
        # matches your previous naming helper
        return (f"{op_full}_pulse", f"{op_full}_I_wf", f"{op_full}_Q_wf")

    # Optional R0 (zeros) pulse, same as before
    if make_r0:
        op_full = f"{prefix}r0"
        pulse_name, I_wf_name, Q_wf_name = _mk_names(op_full)
        rlen = int(I0.size)
        Izeros = np.zeros(rlen, dtype=float)
        Qzeros = np.zeros(rlen, dtype=float)
        pom.create_control_pulse(
            element=element,
            op=op_full,
            length=rlen,
            pulse_name=pulse_name,
            I_wf_name=I_wf_name,
            Q_wf_name=Q_wf_name,
            I_samples=Izeros,
            Q_samples=Qzeros,
            persist=persist,
            override=override,
        )
        created[op_full] = (Izeros, Qzeros)

    # ---- First, register ref_r180 directly if requested ----
    # This MUST be done before building any QubitRotation objects,
    # since QubitRotation will extract ref_r180_pulse from the manager
    if "ref_r180" in rot_set:
        op_full = f"{prefix}ref_r180"
        pulse_name, I_wf_name, Q_wf_name = _mk_names(op_full)
        rlen = int(I0.size)
        
        pom.create_control_pulse(
            element=element,
            op=op_full,
            length=rlen,
            pulse_name=pulse_name,
            I_wf_name=I_wf_name,
            Q_wf_name=Q_wf_name,
            I_samples=I0,
            Q_samples=Q0,
            persist=persist,
            override=override,
        )
        created[op_full] = (I0, Q0)
        # Remove from rot_set so we don't process it again
        rot_set = rot_set - {"ref_r180"}

    # ---- Build each remaining rotation via QubitRotation ----
    for op in sorted(rot_set):
        theta, phi = THETA_PHI[op]

        gate = QubitRotation(
            theta=theta,
            phi=phi,
            d_lambda=float(d_lambda_map.get(op, 0.0)),
            d_alpha=float(d_alpha_map.get(op, 0.0)),
            d_omega=float(d_omega_map.get(op, 0.0)),
            ref_I_x180_wf=I0,
            ref_Q_x180_wf=Q0,
            target=element,    # QubitRotation calls this "target"
            build=False,
        )

        # Build registers the pulse op into the manager (as per your QubitRotation.build)
        # IMPORTANT: QubitRotation.build uses persist=False/override=True internally.
        # If you need those to respect (persist, override), you should update build().
        gate.build(mgr=pom)

        # The gate.op is a hashed internal name. We'll *also* register a friendly alias
        # op like f"{prefix}{op}" that points to the same waveforms, so your existing
        # code can keep calling "x90", "y180", etc.
        alias_op = f"{prefix}{op}"

        # Extract the waveforms (already padded/processed) directly from gate.waveforms()
        # so we can create the alias pulse with your usual create_control_pulse.
        I_samp, Q_samp, length, marker = gate.waveforms()

        pulse_name, I_wf_name, Q_wf_name = _mk_names(alias_op)

        pom.create_control_pulse(
            element=element,
            op=alias_op,
            length=int(length),
            pulse_name=pulse_name,
            I_wf_name=I_wf_name,
            Q_wf_name=Q_wf_name,
            I_samples=np.asarray(I_samp, dtype=float),
            Q_samples=np.asarray(Q_samp, dtype=float),
            persist=persist,
            override=override,
        )

        created[alias_op] = (np.asarray(I_samp, dtype=float), np.asarray(Q_samp, dtype=float))

    return created
