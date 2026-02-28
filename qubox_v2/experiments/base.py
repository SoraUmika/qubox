"""qubox_v2.experiments.base
===========================
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
from ..hardware.program_runner import ExecMode, ProgramRunner, RunResult
from ..hardware.queue_manager import QueueManager
from ..pulses.manager import PulseOperationManager
from ..devices.device_manager import DeviceManager
from ..analysis.cQED_attributes import cQED_attributes
from ..analysis.output import Output
from ..analysis.post_selection import PostSelectionConfig
from ..core.persistence_policy import split_output_for_persistence

_logger = get_logger(__name__)


class ExperimentRunner:
    """Lightweight experiment base class.

    Parameters
    ----------
    experiment_path : str | Path
        Root directory for this experiment.  Config, data, and
        calibration artefacts are stored under it.
    qop_ip : str | None
        OPX+ IP / hostname.  If *None*, ``ConfigEngine`` resolves from
        the hardware JSON.
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
        host = qop_ip or self.config_engine.hardware_extras.get("qop_ip", "localhost")
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

        # ---- 6. Experiment attributes ----
        self.attributes = self._load_attributes()

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

    def _load_attributes(self) -> cQED_attributes:
        """Load or create experiment attributes."""
        try:
            return cQED_attributes.load(self.experiment_path)
        except FileNotFoundError:
            _logger.info("No cqed_params.json found — using defaults")
            return cQED_attributes()

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
        """Run a QUA program.  Delegates to ``ProgramRunner``."""
        return self.runner.run_program(program, mode=mode, **kw)

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
        include_attributes: bool = True,
    ) -> Path:
        """Save experiment output (data + optional attributes) to disk."""
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

        if include_attributes:
            self.save_attributes()

        _logger.info("Output saved to %s", path)
        return path

    def save_attributes(self) -> None:
        """Persist current cQED attributes to JSON."""
        p = self.experiment_path / "config" / "cqed_params.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        self.attributes.save_json(p)

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
