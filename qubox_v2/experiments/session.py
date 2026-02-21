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

        # --- 7. Experiment attributes (cQED parameters) ---
        self.attributes = self._load_attributes()

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
        arrays, meta = {}, {}
        for k, v in data.items():
            if isinstance(v, np.ndarray):
                arrays[k] = v
            else:
                meta[k] = v

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
        return self

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
