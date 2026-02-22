from __future__ import annotations

import datetime
import logging
import warnings
from typing import Optional
from dataclasses import dataclass, asdict, field, fields
import json
from .analysis_tools import complex_encoder, complex_decoder
from pathlib import Path
import numbers
import numpy as np

_logger = logging.getLogger(__name__)

# Fields that must be non-None for a context to be usable
_REQUIRED_FIELDS = ("ro_el", "qb_el", "ro_fq", "qb_fq")

_DEPRECATED_WORKFLOW_FIELDS = (
    "ro_therm_clks",
    "qb_therm_clks",
    "st_therm_clks",
    "b_coherent_amp",
    "b_coherent_len",
    "b_alpha",
)


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

    # Metadata (not persisted, tracked for provenance)
    _source_path: Optional[Path] = field(default=None, init=False, repr=False)
    _loaded_at: Optional[str] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Convert fock_fqs to numpy array if it's a list."""
        if self.fock_fqs is not None and isinstance(self.fock_fqs, list):
            self.fock_fqs = np.array(self.fock_fqs)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        """Return all attributes as a dict (excludes internal metadata)."""
        data = asdict(self)
        # Remove internal metadata fields
        data.pop("_source_path", None)
        data.pop("_loaded_at", None)
        # Convert numpy arrays to lists for better serialization
        if data.get('fock_fqs') is not None and isinstance(data['fock_fqs'], np.ndarray):
            data['fock_fqs'] = data['fock_fqs'].tolist()
        return data

    def to_json(self, filepath: str | Path) -> None:
        """Save attributes to a JSON file."""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        # Remove internal metadata fields
        data.pop("_source_path", None)
        data.pop("_loaded_at", None)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, default=complex_encoder, indent=4)
        _logger.info("Experiment context saved to %s", filepath)

    # Alias so both names work (SessionManager used save_json)
    save_json = to_json

    def save(self, filepath: str | Path | None = None) -> Path:
        """Save to *filepath* or back to the original source path.

        Returns the path that was written.
        """
        target = Path(filepath) if filepath else self._source_path
        if target is None:
            raise ValueError(
                "No filepath specified and no source path recorded. "
                "Pass a filepath or use load() first."
            )
        self.to_json(target)
        return target

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    @classmethod
    def from_json(cls, filepath: str | Path) -> cQED_attributes:
        """Load an instance from a JSON file containing the same fields."""
        filepath = Path(filepath)
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f, object_hook=complex_decoder)
        # Convert fock_fqs list back to numpy array if present
        if data.get('fock_fqs') is not None and isinstance(data['fock_fqs'], list):
            data['fock_fqs'] = np.array(data['fock_fqs'])
        # Filter to known fields only (ignore unknown keys in the JSON)
        known = {f.name for f in fields(cls) if not f.name.startswith("_")}
        filtered = {k: v for k, v in data.items() if k in known}

        present_deprecated = [k for k in _DEPRECATED_WORKFLOW_FIELDS if filtered.get(k) is not None]
        if present_deprecated:
            warnings.warn(
                "cqed_params.json contains deprecated workflow/calibration keys "
                f"{present_deprecated}. Move these to calibration/session-level config; "
                "cqed_params.json support is kept for backward compatibility.",
                DeprecationWarning,
                stacklevel=2,
            )
            _logger.warning(
                "Deprecated cqed_params keys loaded for backward compatibility: %s",
                present_deprecated,
            )

        unknown = set(data) - known
        if unknown:
            _logger.debug("Ignoring unknown fields in %s: %s", filepath, unknown)
        obj = cls(**filtered)
        obj._source_path = filepath
        obj._loaded_at = datetime.datetime.now().isoformat()
        return obj

    @classmethod
    def load(
        cls,
        experiment_path: str | Path,
        *,
        filename: str = "cqed_params.json",
        validate: bool = True,
    ) -> cQED_attributes:
        """Load experiment context from an experiment directory.

        Searches for *filename* in ``<experiment_path>/config/`` and then
        ``<experiment_path>/``.  Raises ``FileNotFoundError`` with a clear
        message if neither location contains the file.

        Parameters
        ----------
        experiment_path : str | Path
            Root experiment directory (e.g. ``seq_1_device``).
        filename : str
            Name of the params JSON file.
        validate : bool
            If *True*, call :meth:`validate` after loading and raise on
            missing required fields.

        Returns
        -------
        cQED_attributes
        """
        root = Path(experiment_path)
        candidates = [root / "config" / filename, root / filename]
        for p in candidates:
            if p.exists():
                _logger.info("Loading experiment context from %s", p)
                obj = cls.from_json(p)
                obj._log_bindings()
                if validate:
                    obj.validate()
                return obj
        raise FileNotFoundError(
            f"Experiment context file '{filename}' not found. "
            f"Searched: {[str(c) for c in candidates]}"
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self, *, required: tuple[str, ...] | None = None) -> None:
        """Check that required fields are populated.

        Raises ``ValueError`` listing any missing required fields.
        """
        check = required or _REQUIRED_FIELDS
        missing = [f for f in check if getattr(self, f, None) is None]
        if missing:
            raise ValueError(
                f"Experiment context is missing required fields: {missing}. "
                f"Check your cqed_params.json file."
            )

    def _log_bindings(self) -> None:
        """Log which elements and frequencies were loaded."""
        bound = []
        if self.ro_el:
            fq = f" @ {self.ro_fq/1e9:.4f} GHz" if self.ro_fq else ""
            bound.append(f"readout='{self.ro_el}'{fq}")
        if self.qb_el:
            fq = f" @ {self.qb_fq/1e9:.4f} GHz" if self.qb_fq else ""
            bound.append(f"qubit='{self.qb_el}'{fq}")
        if self.st_el:
            fq = f" @ {self.st_fq/1e9:.4f} GHz" if self.st_fq else ""
            bound.append(f"storage='{self.st_el}'{fq}")
        if bound:
            _logger.info("Element bindings: %s", ", ".join(bound))
        else:
            _logger.warning("No element bindings found in experiment context")

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
