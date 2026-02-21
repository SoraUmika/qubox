from typing import Optional
from dataclasses import dataclass, asdict
import json
from .analysis_tools import complex_encoder, complex_decoder
from pathlib import Path
import numbers
import numpy as np

@dataclass
class cQED_attributes:
    ro_el:           Optional[str] = None
    qb_el:           Optional[str] = None
    st_el:           Optional[str] = None
    ro_fq:           Optional[int] = None
    qb_fq:           Optional[int] = None
    st_fq:           Optional[int] = None
    ro_kappa:        Optional[int] = None
    ro_chi:           Optional[int] = None
    anharmonicity:   Optional[int] = None
    st_chi:          Optional[float] = None
    st_chi2:         Optional[float] = None
    st_chi3:         Optional[float] = None
    st_K:            Optional[float] = None
    st_K2:           Optional[float] = None
    ro_therm_clks:   Optional[int] = None
    qb_therm_clks:   Optional[int] = None
    st_therm_clks:   Optional[int] = None
    qb_T1_relax:     Optional[float] = None
    qb_T2_ramsey:    Optional[float] = None
    qb_T2_echo:      Optional[float] = None
    r180_amp       : Optional[float] = None
    rlen           : Optional[float] = None
    rsigma         : Optional[int] = None
    b_coherent_amp : Optional[float] = None
    b_coherent_len : Optional[int] = None
    b_alpha :        Optional[float] = None
    fock_fqs :       Optional[np.ndarray] = None

    def __post_init__(self):
        """Convert fock_fqs to numpy array if it's a list."""
        if self.fock_fqs is not None and isinstance(self.fock_fqs, list):
            self.fock_fqs = np.array(self.fock_fqs)

    def to_dict(self) -> dict:
        """
        Return all attributes as a dict.
        Converts numpy arrays to lists for serialization compatibility.
        """
        data = asdict(self)
        # Convert numpy arrays to lists for better serialization
        if data.get('fock_fqs') is not None and isinstance(data['fock_fqs'], np.ndarray):
            data['fock_fqs'] = data['fock_fqs'].tolist()
        return data
    
    def to_json(self, filepath: str | Path) -> None:
        """Save this instanceâ€™s attributes to a JSON file."""
        data = asdict(self)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, default=complex_encoder, indent=4)

    @classmethod
    def from_json(cls, filepath: str | Path) -> 'cQED_attributes':
        """Load an instance from a JSON file containing the same fields."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f, object_hook=complex_decoder)
        # Convert fock_fqs list back to numpy array if present
        if data.get('fock_fqs') is not None and isinstance(data['fock_fqs'], list):
            data['fock_fqs'] = np.array(data['fock_fqs'])
        return cls(**data)

    def get_fock_frequencies(self, fock_levels, from_chi: bool = True) -> np.ndarray:
        if not from_chi:
            # Use the calibrated fock frequencies directly
            if self.fock_fqs is None:
                raise ValueError("fock_fqs is not set. Cannot retrieve calibrated frequencies.")
            
            if isinstance(fock_levels, numbers.Integral):
                if fock_levels < 0:
                    raise ValueError("fock_levels must be non-negative")
                if fock_levels > len(self.fock_fqs):
                    raise ValueError(f"Requested {fock_levels} levels but only {len(self.fock_fqs)} calibrated frequencies available.")
                return self.fock_fqs[:fock_levels]
            
            elif isinstance(fock_levels, (list, tuple, np.ndarray)):
                iterable = (
                    fock_levels.tolist() if isinstance(fock_levels, np.ndarray) else fock_levels
                )
                if not all(isinstance(n, numbers.Integral) for n in iterable):
                    raise TypeError("All elements in fock_levels must be integers.")
                if max(iterable) >= len(self.fock_fqs):
                    raise ValueError(f"Requested fock level {max(iterable)} but only {len(self.fock_fqs)} calibrated frequencies available.")
                return self.fock_fqs[iterable]
            
            else:
                raise TypeError("fock_levels must be an integer or a list/array of integers.")
        
        # Calculate from chi (original behavior)
        qb_fq, chi, chi2, chi3 = self.qb_fq, self.st_chi, self.st_chi2, self.st_chi3
        if isinstance(fock_levels, numbers.Integral):
            if fock_levels < 0:
                raise ValueError("fock_levels must be non-negative")
            n_vals = range(fock_levels)

        elif isinstance(fock_levels, (list, tuple, np.ndarray)):
            iterable = (
                fock_levels.tolist() if isinstance(fock_levels, np.ndarray) else fock_levels
            )
            if not all(isinstance(n, numbers.Integral) for n in iterable):
                raise TypeError("All elements in fock_levels must be integers.")
            n_vals = iterable

        else:
            raise TypeError("fock_levels must be an integer or a list/array of integers.")

        fock_fqs = [qb_fq + chi*n + chi2*n*(n-1) + chi3*n*(n-1)*(n-2) for n in n_vals]
        return np.array(fock_fqs)
