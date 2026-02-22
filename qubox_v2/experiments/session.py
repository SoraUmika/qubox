"""qubox_v2.experiments.session
================================
SessionManager: wires together all qubox services for an experiment session.

Replaces the "god-object" wiring role of the legacy ``cQED_Experiment`` class
while staying thinner — it owns the infrastructure components and lets
individual experiment classes handle the physics.

Usage::

    from qubox_v2.experiments.session import SessionManager

    with SessionManager("./cooldown_2025", qop_ip="10.0.0.1") as session:
        from qubox_v2.experiments.spectroscopy import QubitSpectroscopy
        spec = QubitSpectroscopy(session)
        result = spec.run(pulse="x180", freq_start=6.13e9, ...)
"""
from __future__ import annotations

import logging
import json
import warnings
from pathlib import Path
from typing import Any, Optional

from ..core.errors import ConfigError
from ..core.logging import get_logger
from ..hardware.config_engine import ConfigEngine
from ..hardware.controller import HardwareController
from ..hardware.program_runner import ProgramRunner
from ..hardware.queue_manager import QueueManager
from ..pulses.manager import PulseOperationManager
from ..pulses.pulse_registry import PulseRegistry
from ..devices.device_manager import DeviceManager
from ..calibration.store import CalibrationStore
from ..analysis.cQED_attributes import cQED_attributes
from ..analysis.output import Output
from ..core.persistence_policy import split_output_for_persistence

_logger = get_logger(__name__)


class SessionManager:
    """Central service container for a qubox experiment session.

    Owns all infrastructure components and provides a unified context that
    experiment classes can reference.  Can be used as a context-manager for
    automatic cleanup.

    Parameters
    ----------
    experiment_path : str | Path
        Root directory for this experiment (config, data, calibration live here).
    qop_ip : str | None
        OPX+ IP / hostname.  Resolved from hardware JSON if *None*.
    cluster_name : str | None
        QM cluster identifier.
    load_devices : bool | list[str]
        Which external instruments to initialise on startup.
    oct_cal_path : str | Path | None
        Path to Octave calibration database.
    auto_save_calibration : bool
        If True, calibration data auto-saves on every mutation.
    kwargs
        Forwarded to ``ConfigEngine`` / ``HardwareController``.
    """

    def __init__(
        self,
        experiment_path: str | Path,
        *,
        qop_ip: str | None = None,
        cluster_name: str | None = None,
        load_devices: bool | list[str] = True,
        oct_cal_path: str | Path | None = None,
        auto_save_calibration: bool = False,
        **kwargs: Any,
    ) -> None:
        self.experiment_path = Path(experiment_path)
        self.experiment_path.mkdir(parents=True, exist_ok=True)

        _logger.info("SessionManager initialising at %s", self.experiment_path)

        # --- 1. Configuration engine ---
        self.config_engine = ConfigEngine(
            hardware_path=self._resolve_path("hardware.json", required=True),
        )

        # --- 2. QM connection ---
        from qm import QuantumMachinesManager
        host = qop_ip or self.config_engine.hardware_extras.get("qop_ip", "localhost")
        cal_db = str(oct_cal_path) if oct_cal_path else str(self.experiment_path)
        self._qmm = QuantumMachinesManager(
            host=host,
            cluster_name=cluster_name,
            octave_calibration_db_path=cal_db,
        )

        self.hardware = HardwareController(
            qmm=self._qmm,
            config_engine=self.config_engine,
        )
        self.hardware._cal_db_dir = Path(cal_db)

        # --- 3. Program runner + queue ---
        self.runner = ProgramRunner(
            qmm=self._qmm,
            controller=self.hardware,
            config_engine=self.config_engine,
        )
        self.queue = QueueManager(runner=self.runner)

        # --- 4. Pulse management (both legacy POM and new PulseRegistry) ---
        pl_path = self._resolve_path("pulses.json", required=False)
        if pl_path:
            self.pulse_mgr = PulseOperationManager.from_json(pl_path)
        else:
            self.pulse_mgr = PulseOperationManager()
        self.pulses = PulseRegistry()

        # --- 5. Calibration store ---
        cal_path = self.experiment_path / "config" / "calibration.json"
        self.calibration = CalibrationStore(
            cal_path, auto_save=auto_save_calibration,
        )

        # --- 6. External devices ---
        device_path = self._resolve_path("devices.json", required=False)
        if device_path is None:
            device_path = self.experiment_path / "devices.json"
        self.devices = DeviceManager(device_path)
        if load_devices is True:
            self.devices.instantiate_all()
        elif isinstance(load_devices, (list, tuple, set)):
            if load_devices:
                self.devices.instantiate(list(load_devices))
        self.hardware.set_device_manager(self.devices)

        # --- 7. Experiment attributes (cQED parameters) ---
        self.attributes = self._load_attributes()
        self._runtime_settings = self._load_runtime_settings()

        _logger.info("SessionManager ready.")

    # ------------------------------------------------------------------
    # Compatibility properties — experiment classes access these via ctx
    # ------------------------------------------------------------------
    @property
    def hw(self) -> HardwareController:
        """Alias for experiment_base.py compatibility."""
        return self.hardware

    @property
    def pulseOpMngr(self) -> PulseOperationManager:
        """Alias for legacy code that accesses ``ctx.pulseOpMngr``."""
        return self.pulse_mgr

    @property
    def quaProgMngr(self):
        """Alias used by legacy experiment code."""
        return self.hardware

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------
    def _resolve_path(self, filename: str, *, required: bool = False) -> Path | None:
        """Look for *filename* in config/ or experiment root."""
        candidates = [
            self.experiment_path / "config" / filename,
            self.experiment_path / filename,
        ]
        for p in candidates:
            if p.exists():
                return p
        if required:
            raise ConfigError(
                f"Required file '{filename}' not found. Searched: "
                f"{[str(c) for c in candidates]}"
            )
        return None

    @property
    def device_manager(self) -> DeviceManager:
        """Alias so ExperimentBase can access ``ctx.device_manager``."""
        return self.devices

    def _load_attributes(self) -> cQED_attributes:
        """Load or create cQED experiment attributes."""
        try:
            return cQED_attributes.load(self.experiment_path)
        except FileNotFoundError:
            _logger.info("No cqed_params.json found — using default attributes")
            return cQED_attributes()

    def _runtime_settings_path(self) -> Path:
        return self.experiment_path / "config" / "session_runtime.json"

    def _load_runtime_settings(self) -> dict[str, Any]:
        """Load runtime/session-owned workflow settings.

        Precedence policy for migrated workflow knobs:
        1) ``config/session_runtime.json``
        2) deprecated ``cqed_params.json`` fields (fallback with warning)
        """
        path = self._runtime_settings_path()
        data: dict[str, Any] = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
                    _logger.info("Loaded runtime settings from %s", path)
            except Exception as exc:
                _logger.warning("Failed to load runtime settings from %s: %s", path, exc)

        attr = self.attributes
        defaults = {
            "ro_therm_clks": getattr(attr, "ro_therm_clks", None),
            "qb_therm_clks": getattr(attr, "qb_therm_clks", None),
            "st_therm_clks": getattr(attr, "st_therm_clks", None),
            "b_coherent_amp": getattr(attr, "b_coherent_amp", None),
            "b_coherent_len": getattr(attr, "b_coherent_len", None),
            "b_alpha": getattr(attr, "b_alpha", None),
        }
        for key, fallback in defaults.items():
            if key not in data and fallback is not None:
                data[key] = fallback
                warnings.warn(
                    f"Using deprecated cqed_params.json fallback for '{key}'. "
                    "Move this setting to config/session_runtime.json.",
                    DeprecationWarning,
                    stacklevel=2,
                )

        return data

    def save_runtime_settings(self) -> Path:
        path = self._runtime_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._runtime_settings, f, indent=2, default=str)
        _logger.info("Saved runtime settings to %s", path)
        return path

    def get_runtime_setting(self, key: str, default: Any = None) -> Any:
        return self._runtime_settings.get(key, default)

    def set_runtime_setting(self, key: str, value: Any, *, persist: bool = True) -> None:
        self._runtime_settings[key] = value
        if persist:
            self.save_runtime_settings()

    def get_therm_clks(self, channel: str, default: int | None = None) -> int | None:
        key = f"{channel}_therm_clks"
        val = self.get_runtime_setting(key, None)
        if val is None:
            return default
        return int(val)

    def get_displacement_reference(self) -> dict[str, Any]:
        return {
            "coherent_amp": self.get_runtime_setting("b_coherent_amp", None),
            "coherent_len": self.get_runtime_setting("b_coherent_len", None),
            "b_alpha": self.get_runtime_setting("b_alpha", None),
        }

    # ------------------------------------------------------------------
    # Pulse helpers
    # ------------------------------------------------------------------
    def burn_pulses(self, include_volatile: bool = True) -> None:
        """Push all registered pulses into the QM config."""
        self.config_engine.merge_pulses(self.pulse_mgr, include_volatile=include_volatile)
        self.hardware.apply_changes()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save_attributes(self) -> None:
        """Persist cQED attributes to JSON."""
        p = self.experiment_path / "config" / "cqed_params.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        self.attributes.save_json(p)

    def save_pulses(self, path: str | Path | None = None) -> Path:
        """Persist PulseOperationManager permanent store to pulses.json."""
        dst = Path(path) if path is not None else (self.experiment_path / "config" / "pulses.json")
        dst.parent.mkdir(parents=True, exist_ok=True)
        self.pulse_mgr.save_json(str(dst))
        _logger.info("Saved pulse manager state to %s", dst)
        return dst

    def save_output(self, output: Output | dict, tag: str = "") -> Path:
        """Save experiment output data to disk."""
        import datetime
        from typing import Mapping
        import numpy as np

        target = self.experiment_path / "data"
        target.mkdir(parents=True, exist_ok=True)

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"{tag}_{ts}" if tag else ts
        path = target / f"{stem}.npz"

        data = dict(output) if isinstance(output, Mapping) else output
        arrays, meta, dropped = split_output_for_persistence(data)
        if dropped:
            meta["_persistence"] = {
                "raw_data_policy": "drop_shot_level_arrays",
                "dropped_fields": dropped,
            }

        np.savez_compressed(path, **arrays)

        import json
        meta_path = path.with_suffix(".meta.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2, default=str)

        self.save_attributes()
        _logger.info("Output saved to %s", path)
        return path

    # ------------------------------------------------------------------
    # Open QM connection
    # ------------------------------------------------------------------
    def open(self) -> "SessionManager":
        """Open the QM connection and initialise hardware elements."""
        self.config_engine.merge_pulses(self.pulse_mgr)
        self.hardware.open_qm()
        self._load_measure_config()
        self.validate_runtime_elements(auto_map=True, verbose=True)
        return self

    def validate_runtime_elements(self, *, auto_map: bool = True, verbose: bool = True) -> dict[str, Any]:
        """Validate configured attributes against live QM element names.

        Returns a summary with available/missing/mapped entries and applies safe
        aliases when ``auto_map=True``.
        """
        qm_elements = set((self.hardware.elements or {}).keys())
        attr = self.attributes
        requested = {
            "ro_el": getattr(attr, "ro_el", None),
            "qb_el": getattr(attr, "qb_el", None),
            "st_el": getattr(attr, "st_el", None),
        }

        mapped: dict[str, str] = {}
        missing: dict[str, str] = {}
        notes: list[str] = []

        for field, name in requested.items():
            if not name:
                continue
            if name in qm_elements:
                mapped[field] = name
                continue
            low = str(name).lower()
            candidate = None
            if low == "readout" and "resonator" in qm_elements:
                candidate = "resonator"
            if candidate and auto_map:
                setattr(attr, field, candidate)
                mapped[field] = candidate
                notes.append(f"{field}: '{name}' -> '{candidate}'")
            else:
                missing[field] = name

        summary = {
            "available": sorted(qm_elements),
            "requested": requested,
            "mapped": mapped,
            "missing": missing,
            "notes": notes,
        }

        if verbose:
            _logger.info("Runtime element validation: available=%s", sorted(qm_elements))
            for note in notes:
                _logger.warning("Runtime element auto-map applied: %s", note)
            for field, name in missing.items():
                _logger.error(
                    "Runtime element mismatch: %s='%s' not in QM config. Available=%s",
                    field,
                    name,
                    sorted(qm_elements),
                )
        return summary

    def override_readout_operation(
        self,
        *,
        element: str,
        operation: str,
        weights: list | tuple | str | None = None,
        drive_frequency: float | None = None,
        demod: str | None = None,
        threshold: float | None = None,
        weight_len: int | None = None,
        apply_to_attributes: bool = True,
        persist_measure_config: bool = True,
    ) -> dict[str, Any]:
        """Override active readout op/weights at runtime via ``measureMacro``."""
        from ..programs.macros.measure import measureMacro

        pulse_info = self.pulse_mgr.get_pulseOp_by_element_op(element, operation, strict=False)
        if pulse_info is None:
            cfg = self.config_engine.build_qm_config()
            available_ops = sorted((cfg.get("elements", {}).get(element, {}).get("operations", {}) or {}).keys())
            raise ValueError(
                f"No pulse mapping for element={element!r}, operation={operation!r}. "
                f"Available operations for element: {available_ops}"
            )

        selected_weights = weights
        if selected_weights is None:
            iw_map = pulse_info.int_weights_mapping or {}
            if all(k in iw_map for k in ("cos", "sin", "minus_sin")):
                selected_weights = [["cos", "sin"], ["minus_sin", "cos"]]
            else:
                selected_weights = [["cos", "sin"], ["minus_sin", "cos"]]

        measureMacro.set_pulse_op(
            pulse_info,
            active_op=operation,
            weights=selected_weights,
            weight_len=(weight_len or pulse_info.length),
        )

        if drive_frequency is not None:
            measureMacro.set_drive_frequency(drive_frequency)

        if demod:
            from qm.qua import dual_demod
            if demod == "dual_demod.full":
                measureMacro.set_demodulator(dual_demod.full)

        if threshold is not None and hasattr(measureMacro, "_ro_disc_params"):
            measureMacro._ro_disc_params["threshold"] = float(threshold)

        if apply_to_attributes:
            self.attributes.ro_el = element

        dst = None
        if persist_measure_config:
            dst = self.experiment_path / "config" / "measureConfig.json"
            dst.parent.mkdir(parents=True, exist_ok=True)
            measureMacro.save_json(str(dst))

        return {
            "element": element,
            "operation": operation,
            "pulse": pulse_info.pulse,
            "weights": selected_weights,
            "attributes_ro_el": self.attributes.ro_el,
            "measure_config_path": str(dst) if dst else None,
            "qm_config_entry": f"elements.{element}.operations.{operation} -> {pulse_info.pulse}",
        }

    def _load_measure_config(self) -> None:
        """Load measureMacro state from measureConfig.json if it exists."""
        from ..programs.macros.measure import measureMacro

        path = self._resolve_path("measureConfig.json", required=False)
        if path is not None:
            measureMacro.load_json(str(path))
            _logger.info("Loaded measureMacro state from %s", path)
        else:
            _logger.warning(
                "No measureConfig.json found — measureMacro will use defaults. "
                "Run readout calibration to populate it."
            )

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Release hardware and device connections."""
        try:
            self.hardware.close()
        except Exception as e:
            _logger.warning("Error closing hardware: %s", e)
        for name, handle in self.devices.handles.items():
            try:
                handle.disconnect()
            except Exception as e:
                _logger.warning("Error disconnecting device '%s': %s", name, e)
        try:
            self.save_pulses()
        except Exception as e:
            _logger.warning("Error saving pulses: %s", e)
        try:
            self.save_runtime_settings()
        except Exception as e:
            _logger.warning("Error saving runtime settings: %s", e)
        self.calibration.save()
        _logger.info("SessionManager closed.")

    def __enter__(self) -> "SessionManager":
        return self.open()

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return f"SessionManager(path={self.experiment_path})"
