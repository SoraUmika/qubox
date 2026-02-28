# qubox_v2/hardware/controller.py
"""
HardwareController: live element control (LO, IF, gain, output mode, calibration).

Extracted from QuaProgramManager — this class owns the QM instance and
provides methods to interact with hardware in real time.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import logging
import threading
import warnings
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional, Union

import numpy as np
from grpclib.exceptions import StreamTerminatedError
from octave_sdk import RFOutputMode, OctaveLOSource
from qm import QuantumMachine, QuantumMachinesManager

from ..core.errors import ConfigError, ConnectionError
from ..core.persistence_policy import sanitize_mapping_for_json
from ..core.utils import get_nested, key_like, numeric_keys_to_ints, require, with_retries
from .config_engine import ConfigEngine, QM_TOPLEVEL_WHITELIST

_logger = logging.getLogger(__name__)

# String → OctaveLOSource mapping
LO_SOURCE_MAP: Dict[str, OctaveLOSource] = {
    "internal": OctaveLOSource.Internal,
    "lo1": OctaveLOSource.LO1,
    "lo2": OctaveLOSource.LO2,
    "lo3": OctaveLOSource.LO3,
    "lo4": OctaveLOSource.LO4,
    "lo5": OctaveLOSource.LO5,
}


class HardwareController:
    """
    Owns the QM connection and provides live hardware control.

    Depends on:
        - ConfigEngine (for building configs)
        - Optional DeviceManager (for external LO routing)
    """

    def __init__(
        self,
        qmm: QuantumMachinesManager,
        config_engine: ConfigEngine,
        *,
        default_output_mode: Optional[RFOutputMode] = RFOutputMode.on,
    ):
        self._qmm = qmm
        self.config = config_engine
        self.qm: Optional[QuantumMachine] = None
        self._lock = threading.RLock()

        # Element tracking: {name: {"LO": float, "IF": float, "gain": float}}
        self.elements: Dict[str, Dict[str, float]] = {}
        self._default_output_mode = default_output_mode

        # External device manager (optional, set via set_device_manager)
        self._device_manager = None
        self.spa_pump_sc = None

        # Octave calibration DB directory (set by SessionManager)
        self._cal_db_dir: Path | None = None
        self._last_auto_calibration: dict[str, Any] | None = None

    # ─── Connection lifecycle ─────────────────────────────────────
    def open_qm(self, config_dict: Optional[dict] = None, *, close_other_machines: bool = True) -> None:
        """Open a QM instance with the given or auto-built config."""
        with self._lock:
            if self.qm is not None:
                _logger.warning("open_qm() called while QM already open; closing existing instance first.")
                self.close()
            cfg = config_dict or self.config.build_qm_config()
            cfg_qm = {k: v for k, v in numeric_keys_to_ints(cfg).items() if k in QM_TOPLEVEL_WHITELIST}
            try:
                self.qm = with_retries(
                    lambda: self._qmm.open_qm(cfg_qm, close_other_machines=close_other_machines),
                    exc_types=(StreamTerminatedError,),
                )
            except StreamTerminatedError as e:
                raise ConnectionError("open_qm failed repeatedly.") from e

            self.elements = self._build_element_table()
            _logger.info("QM opened successfully.")

    def close(self) -> None:
        """Close all elements and QMs."""
        for element in list(self.elements.keys()):
            with contextlib.suppress(Exception):
                self.set_octave_output(element, RFOutputMode.off)
        self._qmm.close_all_qms()
        self.qm = None
        _logger.info("All QMs closed; controller reset.")

    def apply_changes(self, *, save_hardware: bool = False) -> None:
        """Rebuild config, reopen QM, re-init elements."""
        with self._lock:
            new_cfg = self.config.build_qm_config()
            self.open_qm(new_cfg)
            if save_hardware:
                self.config.save_hardware()

    # ─── Element table ────────────────────────────────────────────
    def _build_element_table(self) -> Dict[str, Dict]:
        require(self.qm is not None, "QM not initialized", ConfigError)
        cfg = self.qm.get_config()
        elems: Dict[str, Dict] = {}
        for el, info in (cfg.get("elements") or {}).items():
            if el.startswith("__"):
                continue
            lo_freq = None
            if "mixInputs" in info:
                lo_freq = info["mixInputs"].get("lo_frequency")
            elif "singleInput" in info:
                lo_freq = info["singleInput"].get("lo_frequency")
            if_freq = info.get("intermediate_frequency", 0.0)
            elems[el] = {"LO": lo_freq, "IF": if_freq}
        return elems

    def _resolve_active_mixer_elements(self) -> tuple[list[str], list[str]]:
        """Return (valid_active_elements, skipped_internal_or_unknown)."""
        self._require_qm()
        cfg = self.qm.get_config()
        elements_cfg = (cfg.get("elements") or {})
        hw_elements = set((self.elements or {}).keys())

        active: list[str] = []
        skipped: list[str] = []
        for el_name, el_cfg in elements_cfg.items():
            mix_inputs = (el_cfg.get("mixInputs") or {})
            has_mixer = bool(mix_inputs and "mixer" in mix_inputs)
            known_to_hw = el_name in hw_elements
            is_internal = el_name.startswith("__oct__") or el_name.endswith("_analyzer")
            if has_mixer and known_to_hw and not is_internal:
                active.append(el_name)
            elif has_mixer and (is_internal or not known_to_hw):
                skipped.append(el_name)

        preferred = []
        for attr_name in ("ro_el", "qb_el", "st_el"):
            try:
                val = getattr(self.config.attr, attr_name, None)
            except Exception:
                val = None
            if isinstance(val, str):
                preferred.append(val)

        ordered: list[str] = []
        for el_name in preferred:
            if el_name in active and el_name not in ordered:
                ordered.append(el_name)
        for el_name in active:
            if el_name not in ordered:
                ordered.append(el_name)

        return ordered, skipped

    def get_active_mixer_elements(self, *, include_skipped: bool = False):
        """Get active, calibratable mixer elements from the live QM config.

        Filters out internal Octave analyser helper elements and unknown entries.
        """
        active, skipped = self._resolve_active_mixer_elements()
        if include_skipped:
            return {"active": active, "skipped": skipped}
        return active

    def _require_qm(self) -> None:
        require(self.qm is not None, "QM not initialized; call open_qm() or apply_changes().", ConfigError)

    def _check_el(self, el: str) -> None:
        require(el in self.elements, f"Unknown element '{el}'", ConfigError)

    # ─── External LO helpers ─────────────────────────────────────
    def set_device_manager(self, dm) -> None:
        self._device_manager = dm

    def set_spa_pump(self, spa_pump_sc) -> None:
        self.spa_pump_sc = spa_pump_sc

    def _element_octave_rf_out(self, el: str) -> tuple[str, int] | None:
        """Return (octave_name, rf_out_port) for an element, or None."""
        # Use the original hardware config (not qm.get_config() which strips RF_inputs)
        cfg = self.config.hardware_base or {}
        el_cfg = (cfg.get("elements") or {}).get(el)
        if not isinstance(el_cfg, dict):
            return None
        rf_in = el_cfg.get("RF_inputs")
        if not isinstance(rf_in, dict):
            return None
        port = rf_in.get("port")
        if isinstance(port, (list, tuple)) and len(port) >= 2:
            return (str(port[0]), int(port[1]))
        return None

    def _is_external_lo(self, el: str) -> bool:
        """True if the element's octave RF output uses an external LO source."""
        tup = self._element_octave_rf_out(el)
        if tup is None:
            return False
        octave_name, rf_port = tup
        # Use the original hardware config (not qm.get_config() which normalizes octave data)
        cfg = self.config.hardware_base or {}
        rf_outs = get_nested(cfg, ["octaves", octave_name, "RF_outputs"], {})
        if not isinstance(rf_outs, dict):
            return False
        k = key_like(rf_outs, rf_port)
        ch = rf_outs.get(k)
        if isinstance(ch, dict):
            return str(ch.get("LO_source", "")).lower() == "external"
        return False

    def _external_lo_info(self, el: str) -> dict | None:
        """Return external LO info dict for an element, or None."""
        tup = self._element_octave_rf_out(el)
        if tup is None:
            return None
        octave_name, rf_port = tup
        qubox = (self.config.hardware_extras or {}).get("__qubox") or {}
        lo_map = qubox.get("external_lo_map") or {}
        entry = lo_map.get(f"{octave_name}:{rf_port}")
        if entry is None:
            return None
        if isinstance(entry, str):
            return {"device": entry}
        if isinstance(entry, dict):
            return entry
        return None

    def _external_lo_device_name(self, el: str) -> str | None:
        info = self._external_lo_info(el)
        return info.get("device") if info else None

    def get_external_lo_power(self, el: str) -> float | None:
        """Get external LO source power (dBm) for an element when available."""
        self._check_el(el)
        if not self._is_external_lo(el):
            return None
        if self._device_manager is None:
            return None
        dev_name = self._external_lo_device_name(el)
        if not dev_name:
            return None

        try:
            try:
                snap = self._device_manager.snapshot(dev_name)
            except TypeError:
                all_snaps = self._device_manager.snapshot()
                snap = (all_snaps or {}).get(dev_name)
        except Exception:
            _logger.exception("Failed to snapshot external LO device '%s'", dev_name)
            return None

        params = (((snap or {}).get("instrument") or {}).get("parameters") or {})
        p = params.get("power")
        if p is None:
            return None
        try:
            return float(p)
        except Exception:
            return None

    def set_external_lo_power(self, el: str, power_dbm: float) -> None:
        """Set external LO source power (dBm) for an element."""
        self._check_el(el)
        if not self._is_external_lo(el):
            raise ConfigError(f"Element '{el}' is not configured for external LO.")
        if self._device_manager is None:
            raise ConfigError("DeviceManager required for external LO control. Set it via set_device_manager().")

        dev_name = self._external_lo_device_name(el)
        if not dev_name:
            raise ConfigError(f"No external LO device mapping found for element '{el}'.")

        self._device_manager.apply(dev_name, power=float(power_dbm))
        _logger.info("Set external LO power for '%s' via '%s' to %.2f dBm", el, dev_name, float(power_dbm))

    def _configure_lo_source(self, el: str) -> None:
        """Tell the Octave which physical LO input port to route for an external-LO element."""
        info = self._external_lo_info(el)
        if info is None:
            return
        lo_port_str = info.get("lo_port")
        if lo_port_str is None:
            _logger.warning("No lo_port specified for element '%s'; skipping set_lo_source.", el)
            return
        lo_port = LO_SOURCE_MAP.get(lo_port_str.lower().strip())
        if lo_port is None:
            _logger.warning("Unknown lo_port '%s' for element '%s'; skipping.", lo_port_str, el)
            return
        self.qm.octave.set_lo_source(el, lo_port)
        _logger.info("Set LO source for element '%s' to %s", el, lo_port.name)

    # ─── Live hardware commands ───────────────────────────────────
    def init_config(self, output_mode: Optional[RFOutputMode] = None) -> None:
        """Initialize all elements: configure LO sources and output modes."""
        self._require_qm()
        mode = output_mode if output_mode is not None else self._default_output_mode
        _logger.info("Initializing default element configurations")
        for el in self.qm.get_config().get("elements", {}):
            if el.startswith("__"):
                continue
            if self._is_external_lo(el):
                self._configure_lo_source(el)
            self.set_element_lo(el, self.get_element_lo(el))
            if mode is not None:
                self.set_octave_output(el, mode)

    def set_element_lo(self, el: str, el_lo: float) -> None:
        self._require_qm()
        self._check_el(el)

        if self._is_external_lo(el):
            dev_name = self._external_lo_device_name(el)
            if dev_name and self._device_manager is not None:
                self._device_manager.apply(dev_name, frequency=int(el_lo))
                _logger.info("Set external LO for '%s' via '%s' to %.6f GHz", el, dev_name, el_lo * 1e-9)
            else:
                _logger.warning("External LO for '%s' but no DeviceManager available.", el)
        else:
            self.qm.octave.set_lo_frequency(el, el_lo)
            _logger.info("Set LO for '%s' to %.3f MHz", el, el_lo * 1e-6)

        self.elements[el]["LO"] = el_lo

    def scan_external_lo_power(
        self,
        el: str,
        powers_dbm: Iterable[float],
        *,
        target_LO: Optional[float] = None,
        target_IF: Optional[float] = None,
        sa_device_name: str = "sa124b",
        mixer_cal_config: Any = None,
        settle_s: float = 0.05,
        keep_best: bool = True,
    ) -> dict[str, Any]:
        """Sweep external LO power and measure LO/IRR with CW + SA.

        Returns per-power SA metrics and keeps best power by LO+IRR score when
        ``keep_best=True``. Otherwise restores initial power if readable.
        """
        from ..calibration.mixer_calibration import MixerCalibrationConfig, SAMeasurementHelper
        from ..programs import cQED_programs

        self._require_qm()
        self._check_el(el)
        if not self._is_external_lo(el):
            raise ConfigError(f"Element '{el}' is not configured for external LO.")
        if self._device_manager is None:
            raise ConfigError("DeviceManager required for external LO scan. Set it via set_device_manager().")

        sa_dev = self._device_manager.get(sa_device_name)
        if sa_dev is None:
            raise ConfigError(f"SA device '{sa_device_name}' not found in DeviceManager.")

        cfg = mixer_cal_config if isinstance(mixer_cal_config, MixerCalibrationConfig) else MixerCalibrationConfig()
        sa_helper = SAMeasurementHelper(sa_dev, cfg)
        lo_hz = float(self.get_element_lo(el) if target_LO is None else target_LO)
        if_hz = float(self.get_element_if(el) if target_IF is None else target_IF)

        initial_power = self.get_external_lo_power(el)
        rows: list[dict[str, float]] = []

        self.set_octave_output(el, RFOutputMode.on)
        prog = cQED_programs.continuous_wave(
            target_el=el,
            pulse=cfg.cw_pulse,
            gain=float(cfg.cw_gain),
            truncate_clks=int(cfg.cw_truncate_clks),
        )
        job = self.qm.execute(prog)
        try:
            for pwr in powers_dbm:
                pwr = float(pwr)
                self.set_external_lo_power(el, pwr)
                if settle_s > 0:
                    import time
                    time.sleep(float(settle_s))
                tones = sa_helper.measure_tones(lo_hz, if_hz)
                row = {
                    "power_dbm": pwr,
                    "P_target_dBm": float(tones.get("P_des_dBm", float("nan"))),
                    "P_lo_dBm": float(tones.get("P_LO_dBm", float("nan"))),
                    "P_image_dBm": float(tones.get("P_img_dBm", float("nan"))),
                    "LO_leak_dBc": float(tones.get("LO_leak_dBc", float("nan"))),
                    "IRR_dBc": float(tones.get("IRR_dBc", float("nan"))),
                }
                row["score"] = float(row["LO_leak_dBc"] + row["IRR_dBc"])
                rows.append(row)
        finally:
            job.halt()

        if not rows:
            raise RuntimeError("No external LO scan samples were collected.")

        best_row = max(rows, key=lambda r: float(r.get("score", float("-inf"))))
        applied_power = best_row["power_dbm"]

        if keep_best:
            self.set_external_lo_power(el, float(applied_power))
        elif initial_power is not None:
            self.set_external_lo_power(el, float(initial_power))
            applied_power = float(initial_power)

        return {
            "element": el,
            "f_lo": lo_hz,
            "f_if": if_hz,
            "initial_power_dbm": initial_power,
            "applied_power_dbm": float(applied_power),
            "best": dict(best_row),
            "results": rows,
            "kept_best": bool(keep_best),
        }

    def set_element_fq(self, el: str, freq: float) -> None:
        self._require_qm()
        self._check_el(el)
        if_freq = self.calculate_el_if_fq(el, freq)
        self.qm.set_intermediate_frequency(el, float(if_freq))
        self.elements[el]["IF"] = float(if_freq)
        _logger.info("Set '%s' to freq %.3f MHz → IF %.3f MHz", el, freq * 1e-6, if_freq * 1e-6)

    def set_octave_output(self, el: str, mode: RFOutputMode) -> None:
        self._require_qm()
        self._check_el(el)
        self.qm.octave.set_rf_output_mode(el, mode)
        _logger.info("Set output for '%s' to %s", el, mode)

    def set_octave_gain(self, el: str, gain: float) -> None:
        self._require_qm()
        self._check_el(el)
        self.qm.octave.set_rf_output_gain(el, gain)
        self.elements[el]["gain"] = gain
        _logger.info("Set gain for '%s' to %.1f dB", el, gain)

    def get_element_lo(self, el: Union[str, Iterable[str]]) -> Union[float, list[float]]:
        if isinstance(el, (list, tuple)):
            return [self.elements[e]["LO"] for e in el]
        self._check_el(el)
        return self.elements[el]["LO"]

    def get_element_if(self, el: Union[str, Iterable[str]]) -> Union[float, list[float]]:
        if isinstance(el, (list, tuple)):
            return [self.elements[e]["IF"] for e in el]
        self._check_el(el)
        return self.elements[el]["IF"]

    def calculate_el_if_fq(
        self,
        el: str,
        freq: Union[float, Iterable[float], np.ndarray],
        lo_freq: Optional[float] = None,
        *,
        max_if_hz: float = 500e6,
        as_int: bool = False,
    ) -> Union[float, np.ndarray]:
        self._check_el(el)
        lo = self.elements[el]["LO"] if lo_freq is None else lo_freq
        if lo is None:
            raise ConfigError(f"Element '{el}' LO is undefined.")

        was_scalar = np.isscalar(freq)
        f_arr = np.asarray(freq, dtype=float).reshape(-1)
        if_arr = f_arr - float(lo)

        too_big = np.abs(if_arr) > float(max_if_hz)
        if np.any(too_big):
            bad = if_arr[too_big] / 1e6
            raise ValueError(f"IF(s) exceed ±{max_if_hz / 1e6:.0f} MHz for '{el}': {bad[:5]}")

        if as_int:
            if_arr = np.rint(if_arr).astype(int)

        return if_arr.item() if was_scalar else if_arr

    # ─── Calibration ──────────────────────────────────────────────
    def calibrate_element(
        self,
        el: Optional[Union[str, Iterable[str]]] = None,
        target_LO: Optional[Union[float, list[float]]] = None,
        target_IF: Optional[Union[float, list[float]]] = None,
        save_to_db: bool = True,
        output_mode: RFOutputMode = RFOutputMode.on,
        *,
        method: Literal["auto", "manual_scan_2d", "manual_minimizer"] = "auto",
        sa_device_name: str = "sa124b",
        mixer_cal_config: Any = None,
        auto_sa_validate: bool = False,
        auto_sa_restart_qm: bool = False,
        auto_sa_device_name: str = "sa124b",
        auto_calibration_params: Any = None,
    ) -> Any:
        """Calibrate Octave IQ mixer for one or more elements.

        Parameters
        ----------
        method : ``"auto"`` | ``"manual_scan_2d"`` | ``"manual_minimizer"``
            ``"auto"`` uses QM's built-in Octave calibration (default).
            Manual methods use an external SA124B spectrum analyser accessed
            through the instrument server.
        sa_device_name : str
            DeviceManager key for the spectrum analyser (default ``"sa124b"``).
        mixer_cal_config : MixerCalibrationConfig, optional
            Override default SA / grid-search / minimiser parameters.
        """
        self._require_qm()

        # ── Auto calibration (existing behaviour) ─────────────
        if method == "auto":
            self._calibrate_auto(
                el,
                target_LO,
                target_IF,
                save_to_db,
                output_mode,
                auto_sa_validate=auto_sa_validate,
                auto_sa_restart_qm=auto_sa_restart_qm,
                auto_sa_device_name=auto_sa_device_name,
                mixer_cal_config=mixer_cal_config,
                auto_calibration_params=auto_calibration_params,
            )
            return None

        # ── Manual calibration ────────────────────────────────
        from ..calibration.mixer_calibration import (
            ManualMixerCalibrator,
            MixerCalibrationConfig,
            SAMeasurementHelper,
        )

        if self._device_manager is None:
            raise ConfigError("DeviceManager required for manual calibration. "
                              "Set it via set_device_manager().")

        sa_dev = self._device_manager.get(sa_device_name)
        if sa_dev is None:
            raise ConfigError(f"SA device '{sa_device_name}' not found in DeviceManager.")

        cfg = mixer_cal_config if isinstance(mixer_cal_config, MixerCalibrationConfig) else MixerCalibrationConfig()

        db_dir = self._cal_db_dir
        if db_dir is None:
            raise ConfigError("Calibration DB directory not set. "
                              "Use SessionManager or set hw._cal_db_dir.")
        db_path = db_dir / "calibration_db.json"

        sa_helper = SAMeasurementHelper(sa_dev, cfg)
        calibrator = ManualMixerCalibrator(self, sa_helper, db_path, cfg)

        return self._manual_calibrate_elements(
            calibrator, el, target_LO, target_IF, save_to_db, output_mode, method,
        )

    # ── Auto calibration (original implementation) ────────────
    def _calibrate_auto(
        self,
        el: Optional[Union[str, Iterable[str]]],
        target_LO: Optional[Union[float, list[float]]],
        target_IF: Optional[Union[float, list[float]]],
        save_to_db: bool,
        output_mode: RFOutputMode,
        *,
        auto_sa_validate: bool = False,
        auto_sa_restart_qm: bool = False,
        auto_sa_device_name: str = "sa124b",
        mixer_cal_config: Any = None,
        auto_calibration_params: Any = None,
    ) -> None:
        sa_helper = None
        sa_results: list[dict[str, Any]] = []
        auto_runs: list[dict[str, Any]] = []
        failed_runs: list[dict[str, Any]] = []
        cfg = None

        def _contains_non_finite_numbers(obj: Any) -> bool:
            if isinstance(obj, dict):
                return any(_contains_non_finite_numbers(v) for v in obj.values())
            if isinstance(obj, (list, tuple)):
                return any(_contains_non_finite_numbers(v) for v in obj)
            if isinstance(obj, np.ndarray):
                return bool(np.any(~np.isfinite(obj)))
            if isinstance(obj, np.generic):
                obj = obj.item()
            if isinstance(obj, (float, int)):
                return not np.isfinite(float(obj))
            return False

        def _format_suppression_report(rows: list[dict[str, Any]]) -> str:
            lines = [
                "",
                "Auto mixer SA validation report (CW post-check):",
                f"{'Element':18s} {'LO(dBc)':>10s} {'IRR(dBc)':>10s} {'Ptarget(dBm)':>14s}",
            ]
            for row in rows:
                lines.append(
                    f"{row['element']:18s} "
                    f"{row['lo_suppression_dBc']:10.2f} "
                    f"{row['irr_dBc']:10.2f} "
                    f"{row['P_target_dBm']:14.2f}"
                )
            return "\n".join(lines)

        def _measure_with_cw(e: str, lo_hz: float, if_hz: float) -> dict[str, float]:
            from ..programs import cQED_programs

            if cfg is None:
                return sa_helper.measure_tones(float(lo_hz), float(if_hz))

            qm_cfg = self.qm.get_config()
            ops = sorted((qm_cfg.get("elements", {}).get(e, {}).get("operations", {}) or {}).keys())
            if cfg.cw_pulse not in ops:
                raise ValueError(
                    f"Auto SA validation CW op '{cfg.cw_pulse}' not found for element '{e}'. "
                    f"Available operations: {ops}"
                )

            self.set_octave_output(e, RFOutputMode.on)
            prog = cQED_programs.continuous_wave(
                target_el=e,
                pulse=cfg.cw_pulse,
                gain=float(cfg.cw_gain),
                truncate_clks=int(cfg.cw_truncate_clks),
            )
            job = self.qm.execute(prog)
            try:
                settle = float(getattr(cfg, "iq_settle", 0.0) or 0.0)
                if settle > 0:
                    import time
                    time.sleep(settle)
                return sa_helper.measure_tones(float(lo_hz), float(if_hz))
            finally:
                job.halt()

        def _resolve_auto_params(params: Any):
            if params is None:
                return None
            if isinstance(params, dict):
                from qm.octave.octave_mixer_calibration import AutoCalibrationParams
                return AutoCalibrationParams(**params)
            return params

        qm_auto_params = _resolve_auto_params(auto_calibration_params)

        if auto_sa_validate:
            from ..calibration.mixer_calibration import MixerCalibrationConfig, SAMeasurementHelper

            if self._device_manager is None:
                raise ConfigError("DeviceManager required for auto SA validation. Set it via set_device_manager().")
            sa_dev = self._device_manager.get(auto_sa_device_name)
            if sa_dev is None:
                raise ConfigError(f"SA device '{auto_sa_device_name}' not found in DeviceManager.")
            cfg = (
                mixer_cal_config
                if isinstance(mixer_cal_config, MixerCalibrationConfig)
                else MixerCalibrationConfig()
            )
            sa_helper = SAMeasurementHelper(sa_dev, cfg)

        def _calibrate_one(e: str, lo_val, if_val):
            if lo_val is None:
                lo_val = float(self.get_element_lo(e))
            if if_val is None:
                if_val = float(self.get_element_if(e))
            _logger.info("Calibrating '%s' with LO=%.3f MHz, IF=%.3f MHz", e, lo_val * 1e-6, if_val * 1e-6)
            warning_msgs: list[str] = []
            auto_result: Any = None
            warning_indicates_failure = False

            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("error", RuntimeWarning)
                try:
                    auto_result = self.qm.calibrate_element(
                        e,
                        {lo_val: (if_val,)},
                        save_to_db=save_to_db,
                        params=qm_auto_params,
                    )
                except RuntimeWarning as exc:
                    warning_msgs = [str(exc)]
                    warning_indicates_failure = True
                    with contextlib.suppress(Exception):
                        running_job = self.qm.get_running_job()
                        if running_job is not None:
                            running_job.halt()

            if not warning_msgs:
                warning_msgs = [str(w.message) for w in caught_warnings if issubclass(w.category, RuntimeWarning)]

            warning_text = " | ".join(warning_msgs).lower()
            warning_indicates_failure = warning_indicates_failure or (
                "invalid value encountered" in warning_text
                or "nan" in warning_text
                or "out of range" in warning_text
            )
            non_finite_result = _contains_non_finite_numbers(auto_result)
            failed = bool(warning_indicates_failure or non_finite_result)

            if warning_msgs:
                for msg in warning_msgs:
                    _logger.warning("Auto calibration warning for '%s': %s", e, msg)

            if failed:
                reasons = []
                if warning_indicates_failure:
                    reasons.append("runtime_warning")
                if non_finite_result:
                    reasons.append("non_finite_result")
                failed_runs.append(
                    {
                        "element": e,
                        "reasons": reasons,
                        "warnings": warning_msgs,
                    }
                )
                _logger.error(
                    "Auto calibration considered FAILED for '%s' (reasons=%s).",
                    e,
                    ",".join(reasons),
                )

            auto_runs.append(
                {
                    "element": e,
                    "lo_hz": float(lo_val),
                    "if_hz": float(if_val),
                    "lo_if_map": {float(lo_val): [float(if_val)]},
                    "auto_result_type": type(auto_result).__name__,
                    "auto_result_keys": [str(k) for k in auto_result.keys()] if isinstance(auto_result, dict) else None,
                    "warnings": warning_msgs,
                    "status": "failed" if failed else "ok",
                }
            )
            self.set_octave_output(e, output_mode)

            if save_to_db:
                self._sanitize_calibration_db_file()

            if sa_helper is not None:
                if not failed:
                    tones = _measure_with_cw(e, float(lo_val), float(if_val))
                    sa_results.append(
                        {
                            "element": e,
                            "lo_hz": float(lo_val),
                            "if_hz": float(if_val),
                            "sideband": tones.get("sideband"),
                            "f_target_hz": float(tones.get("f_target", float("nan"))),
                            "f_image_hz": float(tones.get("f_image", float("nan"))),
                            "P_target_dBm": float(tones.get("P_des_dBm", float("nan"))),
                            "P_lo_dBm": float(tones.get("P_LO_dBm", float("nan"))),
                            "P_image_dBm": float(tones.get("P_img_dBm", float("nan"))),
                            "lo_suppression_dBc": float(tones.get("LO_leak_dBc", float("nan"))),
                            "irr_dBc": float(tones.get("IRR_dBc", float("nan"))),
                        }
                    )

        if el is None:
            elements = self.get_active_mixer_elements()
        else:
            elements = [el] if isinstance(el, str) else list(el)
        n = len(elements)

        lo_list = list(target_LO) if isinstance(target_LO, (list, tuple)) else [target_LO] * n
        if_list = list(target_IF) if isinstance(target_IF, (list, tuple)) else [target_IF] * n

        for e, lo_val, if_val in zip(elements, lo_list, if_list):
            _calibrate_one(e, lo_val, if_val)

        self._last_auto_calibration = {
            "elements": auto_runs,
            "failed_elements": failed_runs,
            "save_to_db": bool(save_to_db),
            "auto_calibration_params": auto_calibration_params,
        }

        if auto_sa_validate:
            self._write_auto_calibration_artifact(sa_results, cfg, auto_sa_device_name)
            report = _format_suppression_report(sa_results)
            print(report)
            _logger.info(report)

        if auto_sa_restart_qm:
            _logger.info("Restarting QM after auto mixer calibration.")
            self.apply_changes()

        if failed_runs:
            failed_names = ", ".join(str(item.get("element", "?")) for item in failed_runs)
            summary = (
                "Auto mixer calibration finished with failures for element(s): "
                f"{failed_names}."
            )
            _logger.warning(summary)
            print(summary)
            for item in failed_runs:
                elem = str(item.get("element", "?"))
                reasons = ",".join(str(r) for r in (item.get("reasons") or [])) or "unknown"
                print(f"  - element calibration failed: {elem} (reasons={reasons})")

    def _sanitize_calibration_db_file(self) -> None:
        """Replace non-finite numbers in calibration_db.json with 0.0."""
        if self._cal_db_dir is None:
            return
        db_path = self._cal_db_dir / "calibration_db.json"
        if not db_path.exists():
            return

        def _sanitize(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitize(v) for v in obj]
            if isinstance(obj, tuple):
                return [_sanitize(v) for v in obj]
            if isinstance(obj, np.generic):
                obj = obj.item()
            if isinstance(obj, (float, int)):
                return float(obj) if np.isfinite(float(obj)) else 0.0
            return obj

        try:
            raw = json.loads(db_path.read_text(encoding="utf-8-sig"))
        except Exception:
            _logger.exception("Failed reading calibration DB for sanitization: %s", db_path)
            return

        sanitized = _sanitize(raw)
        if sanitized != raw:
            with open(db_path, "w", encoding="utf-8") as f:
                json.dump(sanitized, f, indent=2, allow_nan=False)
            _logger.warning("Sanitized non-finite values in calibration DB: %s", db_path)

    def _write_auto_calibration_artifact(
        self,
        sa_results: list[dict[str, Any]],
        cfg: Any,
        sa_device_name: str,
    ) -> None:
        base = self._cal_db_dir or Path(".")
        art_dir = base / "artifacts" / "runtime" / "calibration_runs"
        art_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = art_dir / f"auto_mixer_sa_validation_{ts}.json"

        payload = {
            "timestamp": ts,
            "method": "auto",
            "sa_device": sa_device_name,
            "sa_config": {
                "sideband": getattr(cfg, "sideband", None),
                "sa_span_hz": getattr(cfg, "sa_span_hz", None),
                "sa_rbw": getattr(cfg, "sa_rbw", None),
                "sa_vbw": getattr(cfg, "sa_vbw", None),
                "sa_avg": getattr(cfg, "sa_avg", None),
                "sa_level": getattr(cfg, "sa_level", None),
            },
            "results": sa_results,
        }
        payload_sanitized, dropped = sanitize_mapping_for_json(payload)
        if dropped:
            payload_sanitized["_persistence"] = {
                "raw_data_policy": "drop_shot_level_arrays",
                "dropped_fields": dropped,
            }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload_sanitized, f, indent=2, default=str)
        _logger.info("Saved auto mixer SA validation artifact: %s", path)

    # ── Manual calibration loop ───────────────────────────────
    def _manual_calibrate_elements(
        self,
        calibrator,
        el: Optional[Union[str, Iterable[str]]],
        target_LO: Optional[Union[float, list[float]]],
        target_IF: Optional[Union[float, list[float]]],
        save_to_db: bool,
        output_mode: RFOutputMode,
        method: str,
    ) -> Any:
        if el is None:
            elements = list(self.elements.keys())
        elif isinstance(el, str):
            elements = [el]
        else:
            elements = list(el)
        n = len(elements)

        lo_list = list(target_LO) if isinstance(target_LO, (list, tuple)) else [target_LO] * n
        if_list = list(target_IF) if isinstance(target_IF, (list, tuple)) else [target_IF] * n

        results = []
        for e, lo_val, if_val in zip(elements, lo_list, if_list):
            if lo_val is None:
                lo_val = float(self.get_element_lo(e))
            if if_val is None:
                if_val = float(self.get_element_if(e))

            _logger.info(
                "Auto reference bootstrap for manual calibration '%s': LO=%.3f MHz, IF=%.3f MHz",
                e,
                lo_val * 1e-6,
                if_val * 1e-6,
            )
            try:
                self._calibrate_auto(
                    el=e,
                    target_LO=lo_val,
                    target_IF=if_val,
                    save_to_db=True,
                    output_mode=output_mode,
                    auto_sa_validate=False,
                )
            except Exception:
                _logger.exception(
                    "Auto reference bootstrap failed for '%s'; continuing manual calibration with existing DB values.",
                    e,
                )

            _logger.info(
                "Manual calibration '%s' (%s): LO=%.3f MHz, IF=%.3f MHz",
                e, method, lo_val * 1e-6, if_val * 1e-6,
            )
            try:
                if method == "manual_scan_2d":
                    result = calibrator.scan_2d(e, lo_val, if_val, save_to_db=save_to_db)
                elif method == "manual_minimizer":
                    result = calibrator.minimizer(e, lo_val, if_val, save_to_db=save_to_db)
                else:
                    result = None
            except Exception as exc:
                _logger.exception("Manual calibration failed for '%s' (%s)", e, method)
                result = {
                    "element": e,
                    "f_lo": float(lo_val),
                    "f_if": float(if_val),
                    "status": "failed",
                    "error": str(exc),
                    "method": method,
                }
            finally:
                self.set_octave_output(e, output_mode)
            results.append(result)

        if len(results) == 1:
            return results[0]
        return results

    # ─── QM info ──────────────────────────────────────────────────
    def list_open_qms(self) -> list[str]:
        return list(self._qmm.list_open_quantum_machines())

    def attach_to_open_qm(self, qm_id: Optional[str] = None) -> str:
        qms = self.list_open_qms()
        require(len(qms) > 0, "No open QMs found.", ConnectionError)
        if qm_id is None:
            qm_id = qms[0]
        require(qm_id in qms, f"QM '{qm_id}' not found.", ConnectionError)
        with self._lock:
            self.qm = self._qmm.get_qm(qm_id)
            self.elements = self._build_element_table()
        _logger.info("Attached to existing QM: %s", qm_id)
        return qm_id
