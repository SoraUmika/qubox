# qubox_v2/hardware/controller.py
"""
HardwareController: live element control (LO, IF, gain, output mode, calibration).

Extracted from QuaProgramManager — this class owns the QM instance and
provides methods to interact with hardware in real time.
"""
from __future__ import annotations

import contextlib
import logging
import threading
from copy import deepcopy
from typing import Any, Callable, Dict, Iterable, List, Optional, Union

import numpy as np
from grpclib.exceptions import StreamTerminatedError
from octave_sdk import RFOutputMode, OctaveLOSource
from qm import QuantumMachine, QuantumMachinesManager

from ..core.errors import ConfigError, ConnectionError
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

    # ─── Connection lifecycle ─────────────────────────────────────
    def open_qm(self, config_dict: Optional[dict] = None, *, close_other_machines: bool = True) -> None:
        """Open a QM instance with the given or auto-built config."""
        with self._lock:
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
    ) -> None:
        """Calibrate Octave for one or more elements."""
        self._require_qm()

        def _calibrate_one(e: str, lo_val, if_val):
            if lo_val is None:
                lo_val = float(self.get_element_lo(e))
            if if_val is None:
                if_val = float(self.get_element_if(e))
            _logger.info("Calibrating '%s' with LO=%.3f MHz, IF=%.3f MHz", e, lo_val * 1e-6, if_val * 1e-6)
            self.qm.calibrate_element(e, {lo_val: (if_val,)}, save_to_db=save_to_db)
            self.set_octave_output(e, output_mode)

        if el is None:
            for e in self.elements:
                _calibrate_one(e, None, None)
            return

        elements = [el] if isinstance(el, str) else list(el)
        n = len(elements)

        lo_list = list(target_LO) if isinstance(target_LO, (list, tuple)) else [target_LO] * n
        if_list = list(target_IF) if isinstance(target_IF, (list, tuple)) else [target_IF] * n

        for e, lo_val, if_val in zip(elements, lo_list, if_list):
            _calibrate_one(e, lo_val, if_val)

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
