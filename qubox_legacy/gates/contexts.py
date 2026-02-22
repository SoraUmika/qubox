# qubox/gates_v2/contexts.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .hash_utils import stable_hash

from dataclasses import dataclass
from typing import Optional, Dict
from .hash_utils import stable_hash

@dataclass(frozen=True)
class ModelContext:
    """
    Pure-model context: only things that affect ideal matrices.

    - Physics parameters used by models (chi, Kerr, etc.)
    - Default durations for gates (used for noise application when NoiseConfig.dt is None)
    - Hilbert space dimensions (qubit and cavity)
    """
    dt_s: Optional[float] = None

    # storage dispersive params (Hz, not rad/s)
    st_chi: Optional[float] = None
    st_chi2: Optional[float] = None
    st_chi3: Optional[float] = None

    st_kerr: Optional[float] = None  
    st_kerr2: Optional[float] = None

    # Hilbert space dimensions
    # qubit_dim: dimension of qubit subspace (default 2 for transmon qubit)
    # Set to 1 for cavity-only operations (no qubit)
    qubit_dim: int = 2
    
    # cavity_dim: dimension of cavity/fock subspace (will be n_max+1)
    # This is computed automatically from n_max, but can be overridden
    # Set to 1 for qubit-only operations (no cavity)
    # Note: This is typically derived from n_max, not set directly

    # Default gate durations in seconds.
    # Keys are gate_type strings (e.g. "SQR", "Displacement", "QubitRotation", "SNAP")
    gate_durations_s: Dict[str, float] = None  # type: ignore[assignment]

    def __post_init__(self):
        # dataclass(frozen=True) => need object.__setattr__
        if self.gate_durations_s is None:
            object.__setattr__(self, "gate_durations_s", {})

    def duration_for(self, gate_type: str, default: float = 0.0) -> float:
        return float(self.gate_durations_s.get(str(gate_type), default))

    def key(self) -> str:
        # stable hash of fields; include durations dict and dimensions
        return stable_hash({
            "dt_s": self.dt_s,
            "st_chi": self.st_chi,
            "st_chi2": self.st_chi2,
            "st_chi3": self.st_chi3,
            "st_kerr": self.st_kerr,
            "st_kerr2": self.st_kerr2,
            "qubit_dim": self.qubit_dim,
            "gate_durations_s": dict(self.gate_durations_s),
        })


@dataclass(frozen=True)
class NoiseConfig:
    """
    Noise config for compiling a channel.
    dt: if None, can be taken from gate.duration_s(ctx).
    """
    dt: Optional[float] = None
    T1: Optional[float] = None
    T2: Optional[float] = None
    order: str = "noise_after"  # 'noise_after' or 'noise_before'

    def key(self) -> str:
        return stable_hash(self.__dict__)

@dataclass(frozen=True)
class HardwareContext:
    """
    Hardware context kept separate so model code never imports QUA/mgr types.
    Store the objects as 'object' to avoid importing hardware deps here.
    """
    mgr: object
    attributes: object
