from __future__ import annotations

import datetime
import logging
import warnings
from typing import ClassVar, Optional
from dataclasses import dataclass, asdict, field, fields
import json
from .analysis_tools import complex_encoder, complex_decoder
from pathlib import Path
import numbers
import numpy as np

_logger = logging.getLogger(__name__)

# Fields that must be non-None for a context to be usable
_REQUIRED_FIELDS = ("ro_el", "qb_el", "ro_fq", "qb_fq")


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
    qb_T1_relax:     Optional[float] = None
    qb_T2_ramsey:    Optional[float] = None
    qb_T2_echo:      Optional[float] = None

    # Canonical transition-prefixed pulse fields (preferred)
    ge_r180_amp:     Optional[float] = None
    ge_rlen:         Optional[float] = None
    ge_rsigma:       Optional[int] = None
    ef_r180_amp:     Optional[float] = None
    ef_rlen:         Optional[float] = None
    ef_rsigma:       Optional[int] = None

    fock_fqs :       Optional[np.ndarray] = None

    # Metadata (not persisted, tracked for provenance)
    _source_path: Optional[Path] = field(default=None, init=False, repr=False)
    _loaded_at: Optional[str] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        """Convert fock_fqs to numpy array if it's a list.

        Also convert fock_fqs lists to numpy arrays.
        """
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

    def to_bindings(self, hw: "Any") -> "Any":
        """Construct ExperimentBindings from this attribute set and a HardwareConfig.

        Parameters
        ----------
        hw : HardwareConfig
            Parsed hardware.json configuration.

        Returns
        -------
        ExperimentBindings

        Notes
        -----
        This is the reverse-compatibility bridge: cQED_attributes carries the
        element names; this method translates them into the binding-driven
        API.  ``ro_el`` / ``qb_el`` / ``st_el`` become derived properties
        from bindings rather than stored directly.
        """
        from ..core.bindings import bindings_from_hardware_config
        return bindings_from_hardware_config(hw, self)

    # ------------------------------------------------------------------
    # CalibrationStore bridge (P1.1 — single source of truth)
    # ------------------------------------------------------------------
    # Canonical name mapping: cQED_attributes → CQEDParams / PulseCalibration
    _CQED_FIELD_MAP: ClassVar[dict[str, tuple[str, str]]] = {
        # (alias_category, cqed_params_field)
        "ro_fq":        ("resonator", "resonator_freq"),
        "qb_fq":        ("transmon",  "qubit_freq"),
        "st_fq":        ("storage",   "storage_freq"),
        "ro_kappa":     ("resonator", "kappa"),
        "anharmonicity":("transmon",  "anharmonicity"),
        "st_chi":       ("storage",   "chi"),
        "st_chi2":      ("storage",   "chi2"),
        "st_chi3":      ("storage",   "chi3"),
        "st_K":         ("storage",   "kerr"),
        "st_K2":        ("storage",   "kerr2"),
        "qb_T1_relax":  ("transmon",  "T1"),
        "qb_T2_ramsey": ("transmon",  "T2_ramsey"),
        "qb_T2_echo":   ("transmon",  "T2_echo"),
    }

    _PULSE_FIELD_MAP: ClassVar[dict[str, tuple[str, str]]] = {
        # (pulse_name_in_store, pulse_calibration_field)
        "ge_r180_amp":  ("ge_ref_r180", "amplitude"),
        "ge_rlen":      ("ge_ref_r180", "length"),
        "ge_rsigma":    ("ge_ref_r180", "sigma"),
        "ef_r180_amp":  ("ef_ref_r180", "amplitude"),
        "ef_rlen":      ("ef_ref_r180", "length"),
        "ef_rsigma":    ("ef_ref_r180", "sigma"),
    }

    def verify_consistency(
        self,
        store: "Any",
        *,
        rtol: float = 1e-6,
        raise_on_mismatch: bool = False,
    ) -> list[str]:
        """Compare this snapshot against a CalibrationStore.

        Parameters
        ----------
        store : CalibrationStore
            The single-source-of-truth calibration store.
        rtol : float
            Relative tolerance for numeric comparisons.
        raise_on_mismatch : bool
            If True, raise ``ValueError`` on the first mismatch.

        Returns
        -------
        list[str]
            Human-readable list of mismatches (empty = consistent).

        .. versionadded:: 2.1.0  (P1.1 — CalibrationStore as single source of truth)
        """
        mismatches: list[str] = []

        for attr_field, (alias, store_field) in self._CQED_FIELD_MAP.items():
            attr_val = getattr(self, attr_field, None)
            if attr_val is None:
                continue
            cqed = store.get_cqed_params(alias)
            if cqed is None:
                mismatches.append(
                    f"{attr_field}: cQED_attributes={attr_val} but CalibrationStore "
                    f"has no cqed_params for alias '{alias}'"
                )
                continue
            store_val = getattr(cqed, store_field, None)
            if store_val is None:
                continue
            if isinstance(attr_val, (int, float)) and isinstance(store_val, (int, float)):
                if abs(attr_val - store_val) > rtol * max(abs(attr_val), abs(store_val), 1e-30):
                    mismatches.append(
                        f"{attr_field}: cQED_attributes={attr_val} vs "
                        f"CalibrationStore.{alias}.{store_field}={store_val}"
                    )
            elif attr_val != store_val:
                mismatches.append(
                    f"{attr_field}: cQED_attributes={attr_val!r} vs "
                    f"CalibrationStore.{alias}.{store_field}={store_val!r}"
                )

        for attr_field, (pulse_name, cal_field) in self._PULSE_FIELD_MAP.items():
            attr_val = getattr(self, attr_field, None)
            if attr_val is None:
                continue
            cal = store.get_pulse_calibration(pulse_name)
            if cal is None:
                mismatches.append(
                    f"{attr_field}: cQED_attributes={attr_val} but CalibrationStore "
                    f"has no pulse_calibration for '{pulse_name}'"
                )
                continue
            store_val = getattr(cal, cal_field, None)
            if store_val is None:
                continue
            if isinstance(attr_val, (int, float)) and isinstance(store_val, (int, float)):
                if abs(attr_val - store_val) > rtol * max(abs(attr_val), abs(store_val), 1e-30):
                    mismatches.append(
                        f"{attr_field}: cQED_attributes={attr_val} vs "
                        f"CalibrationStore.{pulse_name}.{cal_field}={store_val}"
                    )
            elif attr_val != store_val:
                mismatches.append(
                    f"{attr_field}: cQED_attributes={attr_val!r} vs "
                    f"CalibrationStore.{pulse_name}.{cal_field}={store_val!r}"
                )

        if mismatches:
            _logger.warning(
                "cQED_attributes ↔ CalibrationStore divergence detected:\n  %s",
                "\n  ".join(mismatches),
            )
            if raise_on_mismatch:
                raise ValueError(
                    f"{len(mismatches)} mismatch(es) between cQED_attributes and "
                    f"CalibrationStore:\n  " + "\n  ".join(mismatches)
                )
        return mismatches

    @classmethod
    def from_calibration_store(
        cls,
        store: "Any",
        *,
        ro_el: str | None = None,
        qb_el: str | None = None,
        st_el: str | None = None,
    ) -> "cQED_attributes":
        """Build a read-only snapshot from a CalibrationStore.

        This is the preferred way to create a ``cQED_attributes`` when
        ``CalibrationStore`` is the single source of truth (P1.1).

        .. versionadded:: 2.1.0
        """
        from typing import Any as _Any
        kw: dict[str, _Any] = {"ro_el": ro_el, "qb_el": qb_el, "st_el": st_el}

        # Pull cQED params
        for attr_field, (alias, store_field) in cls._CQED_FIELD_MAP.items():
            cqed = store.get_cqed_params(alias)
            if cqed is not None:
                val = getattr(cqed, store_field, None)
                if val is not None:
                    kw[attr_field] = val

        # Pull pulse calibrations
        for attr_field, (pulse_name, cal_field) in cls._PULSE_FIELD_MAP.items():
            cal = store.get_pulse_calibration(pulse_name)
            if cal is not None:
                val = getattr(cal, cal_field, None)
                if val is not None:
                    kw[attr_field] = val

        # fock_fqs from storage cqed_params
        storage_cqed = store.get_cqed_params("storage")
        if storage_cqed is not None:
            fock = getattr(storage_cqed, "fock_freqs", None)
            if fock is not None:
                kw["fock_fqs"] = np.array(fock)

        return cls(**kw)

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
