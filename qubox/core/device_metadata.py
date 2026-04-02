"""Device element mapping with live CalibrationStore access.

``DeviceMetadata`` replaces the legacy ``cQED_attributes`` class.  Element
names are the only stored state; all physics parameters (frequencies,
coherence times, chi values) are resolved **on access** from the
``CalibrationStore`` — never cached or snapshotted.

This eliminates the "dual-store" divergence problem where cQED_attributes
could drift from CalibrationStore.

Migration notes
---------------
- ``attr.qb_el`` / ``attr.ro_el`` / ``attr.st_el`` → same
- ``attr.qb_fq``  → live property reading CalibrationStore
- ``attr.st_chi``  → live property reading CalibrationStore
- ``attr.get_fock_frequencies(...)`` → same signature, reads from CalibrationStore
- ``cQED_attributes.load(path)`` → ``DeviceMetadata.from_hardware_json(path)``
  or ``DeviceMetadata(qb_el=..., ro_el=..., _calibration=store)``
"""
from __future__ import annotations

import logging
import numbers
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from ..calibration.store import CalibrationStore

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeviceMetadata:
    """Read-only device-element mapping with live CalibrationStore access.

    Element names identify physical hardware channels.  All physics
    parameters are resolved from ``CalibrationStore`` on access — never
    cached.  This is the single-source-of-truth replacement for
    ``cQED_attributes``.

    Parameters
    ----------
    qb_el : str
        Qubit drive element name (default ``"qubit"``).
    ro_el : str
        Readout element name (default ``"resonator"``).
    st_el : str | None
        Storage element name (optional).
    dt_s : float
        Hardware timestep in seconds (default 1 ns for OPX+).
    max_fock_level : int
        Maximum Fock level for gate compilation (runtime setting).
    """

    # ---- Element names (core identity) ----
    qb_el: str = "qubit"
    ro_el: str = "resonator"
    st_el: str | None = None

    # ---- Runtime settings (not from CalibrationStore) ----
    dt_s: float = 1e-9
    max_fock_level: int = 10
    b_coherent_amp: float | None = None
    b_coherent_len: int | None = None
    b_alpha: float | None = None

    # ---- CalibrationStore reference (live access, not snapshotted) ----
    _calibration: Any = field(default=None, repr=False, compare=False)

    # ------------------------------------------------------------------
    # Generic parameter resolution (used by properties below)
    # ------------------------------------------------------------------

    def get_cqed_param(self, alias: str, param_field: str) -> Any:
        """Resolve a cQED parameter from CalibrationStore.

        Parameters
        ----------
        alias : str
            Category alias (``"transmon"``, ``"resonator"``, ``"storage"``).
        param_field : str
            Field name on the ``CQEDParams`` model.

        Returns
        -------
        Any
            Resolved value, or ``None`` if CalibrationStore is not
            available or the parameter is not set.
        """
        if self._calibration is None:
            return None
        params = self._calibration.get_cqed_params(alias)
        return getattr(params, param_field, None) if params is not None else None

    def get_frequency(self, element: str, freq_field: str = "qubit_freq") -> float | None:
        """Resolve a frequency from CalibrationStore.

        Parameters
        ----------
        element : str
            Element name to look up.
        freq_field : str
            Frequency field name (``"qubit_freq"``, ``"resonator_freq"``,
            ``"storage_freq"``, ``"if_freq"``, ``"lo_freq"``).

        Returns
        -------
        float | None
        """
        if self._calibration is None:
            return None
        try:
            entry = self._calibration.get_frequencies(element)
        except Exception:
            return None
        if entry is None:
            return None
        val = getattr(entry, freq_field, None)
        return float(val) if isinstance(val, (int, float)) else None

    def get_pulse_calibration(self, pulse_name: str, cal_field: str) -> Any:
        """Resolve a pulse calibration value from CalibrationStore."""
        if self._calibration is None:
            return None
        cal = self._calibration.get_pulse_calibration(pulse_name)
        return getattr(cal, cal_field, None) if cal is not None else None

    # ------------------------------------------------------------------
    # Live frequency properties (backward-compat with cQED_attributes)
    # ------------------------------------------------------------------

    @property
    def qb_fq(self) -> float | None:
        """Qubit frequency (Hz) from CalibrationStore."""
        return self.get_frequency(self.qb_el, "qubit_freq")

    @property
    def ro_fq(self) -> float | None:
        """Readout / resonator frequency (Hz) from CalibrationStore."""
        val = self.get_frequency(self.ro_el, "resonator_freq")
        if val is not None:
            return val
        # Fall back to IF + LO reconstruction
        if_val = self.get_frequency(self.ro_el, "if_freq")
        lo_val = self.get_frequency(self.ro_el, "lo_freq")
        if if_val is not None and lo_val is not None:
            return lo_val + if_val
        return None

    @property
    def st_fq(self) -> float | None:
        """Storage frequency (Hz) from CalibrationStore."""
        if not self.st_el:
            return None
        val = self.get_frequency(self.st_el, "storage_freq")
        if val is not None:
            return val
        return self.get_frequency(self.st_el, "qubit_freq")

    # ------------------------------------------------------------------
    # Live cQED parameter properties
    # ------------------------------------------------------------------

    @property
    def anharmonicity(self) -> float | None:
        return self.get_cqed_param("transmon", "anharmonicity")

    @property
    def ro_kappa(self) -> float | None:
        return self.get_cqed_param("resonator", "kappa")

    @property
    def ro_chi(self) -> float | None:
        return self.get_cqed_param("resonator", "chi")

    @property
    def st_chi(self) -> float | None:
        return self.get_cqed_param("storage", "chi")

    @property
    def st_chi2(self) -> float | None:
        return self.get_cqed_param("storage", "chi2")

    @property
    def st_chi3(self) -> float | None:
        return self.get_cqed_param("storage", "chi3")

    @property
    def st_K(self) -> float | None:
        return self.get_cqed_param("storage", "kerr")

    @property
    def st_K2(self) -> float | None:
        return self.get_cqed_param("storage", "kerr2")

    @property
    def qb_T1_relax(self) -> float | None:
        return self.get_cqed_param("transmon", "T1_us")

    @property
    def qb_T2_ramsey(self) -> float | None:
        return self.get_cqed_param("transmon", "T2_star_us")

    @property
    def qb_T2_echo(self) -> float | None:
        return self.get_cqed_param("transmon", "T2_echo_us")

    @property
    def fock_fqs(self) -> np.ndarray | None:
        val = self.get_cqed_param("storage", "fock_freqs")
        if val is not None and not isinstance(val, np.ndarray):
            return np.asarray(val, dtype=float)
        return val

    # ------------------------------------------------------------------
    # Thermalization clocks
    # ------------------------------------------------------------------

    @property
    def qb_therm_clks(self) -> int | None:
        return self.get_cqed_param("transmon", "qb_therm_clks")

    @property
    def ro_therm_clks(self) -> int | None:
        return self.get_cqed_param("resonator", "ro_therm_clks")

    @property
    def st_therm_clks(self) -> int | None:
        return self.get_cqed_param("storage", "st_therm_clks")

    # ------------------------------------------------------------------
    # Pulse calibration properties
    # ------------------------------------------------------------------

    @property
    def ge_r180_amp(self) -> float | None:
        return self.get_pulse_calibration("ge_ref_r180", "amplitude")

    @property
    def ge_rlen(self) -> float | None:
        return self.get_pulse_calibration("ge_ref_r180", "length")

    @property
    def ge_rsigma(self) -> int | None:
        val = self.get_pulse_calibration("ge_ref_r180", "sigma")
        return int(val) if val is not None else None

    @property
    def ef_r180_amp(self) -> float | None:
        return self.get_pulse_calibration("ef_ref_r180", "amplitude")

    @property
    def ef_rlen(self) -> float | None:
        return self.get_pulse_calibration("ef_ref_r180", "length")

    @property
    def ef_rsigma(self) -> int | None:
        val = self.get_pulse_calibration("ef_ref_r180", "sigma")
        return int(val) if val is not None else None

    # ------------------------------------------------------------------
    # Fock frequency computation
    # ------------------------------------------------------------------

    def get_fock_frequencies(self, fock_levels: int | list | np.ndarray, *, from_chi: bool = True) -> np.ndarray:
        """Compute per-Fock-level frequencies.

        Parameters
        ----------
        fock_levels : int | list | ndarray
            If ``int``, return frequencies for levels ``0..fock_levels-1``.
            If list/array, return frequencies for those specific levels.
        from_chi : bool
            If ``True`` (default), compute from chi polynomial.
            If ``False``, use pre-calibrated ``fock_fqs`` from
            CalibrationStore.

        Returns
        -------
        np.ndarray
            Frequencies in Hz.
        """
        if not from_chi:
            cal_fqs = self.fock_fqs
            if cal_fqs is None:
                raise ValueError("No calibrated fock_fqs in CalibrationStore.")
            if isinstance(fock_levels, numbers.Integral):
                if fock_levels < 0:
                    raise ValueError("fock_levels must be non-negative")
                if fock_levels > len(cal_fqs):
                    raise ValueError(
                        f"Requested {fock_levels} levels but only "
                        f"{len(cal_fqs)} calibrated frequencies available."
                    )
                return cal_fqs[:fock_levels]
            levels_arr = np.asarray(fock_levels, dtype=int)
            if levels_arr.max() >= len(cal_fqs):
                raise ValueError(
                    f"Requested fock level {levels_arr.max()} but only "
                    f"{len(cal_fqs)} calibrated frequencies available."
                )
            return cal_fqs[levels_arr]

        # Compute from chi polynomial
        qb_fq = self.qb_fq
        chi = self.st_chi
        chi2 = self.st_chi2 or 0.0
        chi3 = self.st_chi3 or 0.0

        if isinstance(fock_levels, numbers.Integral):
            if fock_levels < 0:
                raise ValueError("fock_levels must be non-negative")
            n_vals = np.arange(fock_levels, dtype=float)
        else:
            n_vals = np.asarray(fock_levels, dtype=float)

        delta = chi * n_vals + chi2 * n_vals * (n_vals - 1) + chi3 * n_vals * (n_vals - 1) * (n_vals - 2)
        if qb_fq is not None:
            return qb_fq + delta
        return delta

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_roles(
        cls,
        roles: dict[str, str],
        *,
        calibration: CalibrationStore | None = None,
        **runtime_settings: Any,
    ) -> DeviceMetadata:
        """Build from a roles mapping (e.g. from hardware.json ``__qubox.bindings.roles``).

        Parameters
        ----------
        roles : dict
            Mapping like ``{"qubit": "transmon", "readout": "resonator", "storage": "storage"}``.
        calibration : CalibrationStore | None
            Live calibration store for parameter resolution.
        **runtime_settings
            Extra fields like ``dt_s``, ``max_fock_level``.
        """
        qb = roles.get("qubit", "qubit")
        ro = roles.get("readout_drive") or roles.get("readout", "resonator")
        st = roles.get("storage")
        return cls(
            qb_el=str(qb),
            ro_el=str(ro),
            st_el=str(st) if st else None,
            _calibration=calibration,
            **{k: v for k, v in runtime_settings.items() if v is not None},
        )

    def _log_bindings(self) -> None:
        """Log which elements are bound."""
        bound = []
        if self.ro_el:
            fq = self.ro_fq
            fq_str = f" @ {fq / 1e9:.4f} GHz" if fq else ""
            bound.append(f"readout='{self.ro_el}'{fq_str}")
        if self.qb_el:
            fq = self.qb_fq
            fq_str = f" @ {fq / 1e9:.4f} GHz" if fq else ""
            bound.append(f"qubit='{self.qb_el}'{fq_str}")
        if self.st_el:
            fq = self.st_fq
            fq_str = f" @ {fq / 1e9:.4f} GHz" if fq else ""
            bound.append(f"storage='{self.st_el}'{fq_str}")
        if bound:
            _logger.info("Element bindings: %s", ", ".join(bound))
        else:
            _logger.warning("No element bindings in DeviceMetadata")

    def __repr__(self) -> str:
        parts = [f"qb_el={self.qb_el!r}", f"ro_el={self.ro_el!r}"]
        if self.st_el:
            parts.append(f"st_el={self.st_el!r}")
        has_cal = self._calibration is not None
        parts.append(f"calibration={'connected' if has_cal else 'None'}")
        return f"DeviceMetadata({', '.join(parts)})"
