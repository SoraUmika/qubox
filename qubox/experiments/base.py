"""qubox.experiments.base
========================
Generic, reusable base class for qubox experiments.

``ExperimentRunner`` distils the *infrastructure* plumbing that every
experiment shares — hardware connection, pulse management, device
wiring, configuration persistence — while **leaving out** the 60+
physics-specific methods that live in ``cQED_Experiment``.

New experiments can inherit ``ExperimentRunner`` instead of (or in
addition to) the legacy monolith, picking up:

* Typed configuration via ``ConfigBuilder``
* Automatic pulse → hardware burn
* Device manager bootstrap
* Attribute persistence
* Standardised save / load helpers
"""
from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from ..core.errors import ConfigError, ConnectionError
from ..core.logging import get_logger, temporarily_set_levels
from ..hardware.config_engine import ConfigEngine
from ..hardware.controller import HardwareController
from ..hardware.program_runner import ExecMode, ProgramRunner, RunResult, coerce_exec_mode
from ..hardware.queue_manager import QueueManager
from ..pulses.manager import PulseOperationManager
from ..devices.device_manager import DeviceManager
from ..core.device_metadata import DeviceMetadata
from ..core.utils import resolve_qop_host
from qubox_tools.data.containers import Output
from qubox_tools.algorithms.post_selection import PostSelectionConfig
from ..core.persistence import split_output_for_persistence

_logger = get_logger(__name__)


class ExperimentRunner:
    """Lightweight experiment base class.

    Parameters
    ----------
    experiment_path : str | Path
        Root directory for this experiment.  Config, data, and
        calibration artefacts are stored under it.
    qop_ip : str | None
        OPX+ IP / hostname. If omitted, ``hardware.json`` must persist a
        ``qop_ip`` entry in ``hardware_extras``. qubox will not fall back to
        ``localhost``.
    cluster_name : str | None
        QM cluster identifier.
    load_devices : bool | list[str]
        Which external instruments to initialise.
    oct_cal_path : str | Path | None
        Path to Octave calibration DB.
    kwargs
        Forwarded to ``ConfigEngine`` / ``HardwareController``.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    def __init__(
        self,
        experiment_path: str | Path,
        *,
        qop_ip: str | None = None,
        cluster_name: str | None = None,
        load_devices: bool | list[str] = True,
        oct_cal_path: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        self.experiment_path = Path(experiment_path)
        self.experiment_path.mkdir(parents=True, exist_ok=True)

        _logger.info("Initialising ExperimentRunner at %s", self.experiment_path)

        # ---- 1. Configuration engine ----
        self.config_engine = ConfigEngine(
            hardware_path=self._resolve_hardware_json(),
        )

        # ---- 2. Hardware controller (connection) ----
        from qm import QuantumMachinesManager
        host = resolve_qop_host(qop_ip, self.config_engine.hardware_extras)
        if host is None:
            raise ConfigError(
                "QOP host is required. Pass qop_ip explicitly or persist qop_ip in hardware.json; "
                "qubox will not fall back to localhost."
            )
        cal_db = str(oct_cal_path) if oct_cal_path else str(self.experiment_path)
        self._qmm = QuantumMachinesManager(
            host=host,
            cluster_name=cluster_name,
            octave_calibration_db_path=cal_db,
        )
        self.hw = HardwareController(
            qmm=self._qmm,
            config_engine=self.config_engine,
            **{k: v for k, v in kwargs.items()
               if k in ("default_output_mode",)},
        )

        # ---- 3. Program runner + queue ----
        self.runner = ProgramRunner(
            qmm=self._qmm,
            controller=self.hw,
            config_engine=self.config_engine,
        )
        self.queue = QueueManager(runner=self.runner)

        # ---- 4. Pulse operations ----
        self.pulse_mgr = PulseOperationManager(self.config_engine)

        # ---- 5. External devices ----
        self.device_manager = DeviceManager(
            self.experiment_path / "devices.json",
            autoload=load_devices,
        )

        # ---- 6. Experiment context snapshot ----
        self._context_snapshot = self._load_context_snapshot()

        # ---- 7. Post-selection (opt-in) ----
        self.post_sel_config: PostSelectionConfig | None = None

    # ------------------------------------------------------------------
    # Path helpers (override in subclasses for custom layouts)
    # ------------------------------------------------------------------
    def _resolve_hardware_json(self) -> Path:
        """Return path to the hardware config JSON."""
        candidates = [
            self.experiment_path / "config" / "hardware.json",
            self.experiment_path / "hardware.json",
        ]
        for p in candidates:
            if p.exists():
                return p
        raise ConfigError(
            f"No hardware.json found in {self.experiment_path}. "
            f"Searched: {[str(c) for c in candidates]}"
        )

    def _resolve_pulse_json(self) -> Path | None:
        """Return path to pulse library JSON, or *None* if not found."""
        p = self.experiment_path / "config" / "pulses.json"
        return p if p.exists() else None

    def _load_context_snapshot(self) -> DeviceMetadata:
        """Build a DeviceMetadata from hardware config binding roles.

        Element names are resolved from ``__qubox.bindings.roles`` in the
        hardware JSON.  CalibrationStore provides parameter access.
        """
        extras = self.config_engine.hardware_extras or {}
        qubox = extras.get("__qubox") or {}
        roles = (qubox.get("bindings") or {}).get("roles") or {}
        calibration = getattr(self, "calibration", None)
        return DeviceMetadata.from_roles(roles, calibration=calibration)

    def context_snapshot(self) -> DeviceMetadata:
        """Return the current experiment context snapshot."""
        return self._context_snapshot

    # ------------------------------------------------------------------
    # Pulse helpers
    # ------------------------------------------------------------------
    def register_pulse(self, name: str, **kw: Any) -> None:
        """Register (or update) a pulse in the operation manager."""
        self.pulse_mgr.register(name, **kw)

    def burn_pulses(self, include_volatile: bool = True) -> None:
        """Push all registered pulses into the QM config."""
        self.config_engine.merge_pulses(self.pulse_mgr, include_volatile=include_volatile)
        self.hw.apply_changes()

    # ------------------------------------------------------------------
    # Run helpers
    # ------------------------------------------------------------------
    def run(self, program, *, mode: ExecMode = ExecMode.HARDWARE, **kw: Any) -> RunResult:
        """Run a QUA program in hardware mode.

        ``simulate()`` is the explicit simulation entry point. Rejecting
        non-hardware modes here avoids silently forwarding ignored mode
        arguments into ``ProgramRunner.run_program()``.
        """
        resolved_mode = coerce_exec_mode(mode)
        if resolved_mode is not ExecMode.HARDWARE:
            raise ValueError("ExperimentRunner.run() is hardware-only; use simulate() for simulation mode.")
        return self.runner.run_program(program, **kw)

    def simulate(self, program, duration: int = 10_000, **kw: Any):
        """Simulate a QUA program.  Delegates to ``ProgramRunner``."""
        return self.runner.simulate(program, duration=duration, **kw)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save_output(
        self,
        output: Output | dict,
        target_folder: str | Path | None = None,
        *,
        tag: str = "",
        include_context_snapshot: bool = True,
    ) -> Path:
        """Save experiment output (data + optional context snapshot) to disk."""
        if target_folder is None:
            target_folder = self.experiment_path / "data"
        target_folder = Path(target_folder)
        target_folder.mkdir(parents=True, exist_ok=True)

        # Build filename
        import datetime
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"{tag}_{ts}" if tag else ts
        path = target_folder / f"{stem}.npz"

        # Separate persistable arrays from metadata and drop raw/large buffers
        data = dict(output) if isinstance(output, Mapping) else output
        arrays, meta, dropped = split_output_for_persistence(data)
        if dropped:
            meta["_persistence"] = {
                "raw_data_policy": "drop_shot_level_arrays",
                "dropped_fields": dropped,
            }

        np.savez_compressed(path, **arrays)

        # Save metadata side-car
        meta_path = path.with_suffix(".meta.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2, default=str)

        if include_context_snapshot:
            self.save_context_snapshot()

        _logger.info("Output saved to %s", path)
        return path

    def save_context_snapshot(self) -> None:
        """Persist the current legacy-compatible context snapshot to JSON."""
        p = self.experiment_path / "config" / "cqed_params.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        self._context_snapshot.save_json(p)

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Release hardware and device connections."""
        self.hw.close()
        self.device_manager.close_all()
        _logger.info("ExperimentRunner closed.")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
