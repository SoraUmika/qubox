# qubox_v2/hardware/qua_program_manager.py
"""
QuaProgramManager: backward-compatibility facade.

The v2 monolithic ``QuaProgramManager`` was split into four v3 classes:
    - ConfigEngine     (config loading / saving / building)
    - HardwareController (QM instance, element LO/IF/gain, octave)
    - ProgramRunner    (execute / simulate QUA programs)
    - QueueManager     (multi-job queue operations)

This thin compatibility wrapper re-composes those pieces under the old
single-class API so that legacy code (particularly ``cQED_Experiment``)
keeps working unchanged.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from qm import QuantumMachinesManager

from .config_engine import ConfigEngine
from .controller import HardwareController
from .program_runner import ProgramRunner, RunResult, ExecMode
from .queue_manager import QueueManager

_logger = logging.getLogger(__name__)


class QuaProgramManager:
    """Drop-in replacement for the old monolithic manager.

    Parameters
    ----------
    qop_ip : str
        OPX+ IP / hostname.
    cluster_name : str
        QM cluster identifier.
    oct_cal_path : str | Path
        Path to Octave calibration database.
    hardware_path : str | Path | None
        Path to hardware.json.  If None, call ``load_hardware()`` later.
    **kwargs
        Forwarded to ``HardwareController`` (e.g. ``default_output_mode``,
        ``override_octave_json_mode``).
    """

    def __init__(
        self,
        qop_ip: str,
        cluster_name: str,
        oct_cal_path: str | Path = "./",
        *,
        hardware_path: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        self._qop_ip = qop_ip
        self._cluster_name = cluster_name
        self._oct_cal_path = Path(oct_cal_path)

        # Pop controller-specific kwargs
        default_output_mode = kwargs.pop("default_output_mode", None)
        # override_octave_json_mode is a legacy knob — just absorb it
        kwargs.pop("override_octave_json_mode", None)

        # --- 1. Config engine ---
        self._config_engine: Optional[ConfigEngine] = None
        self._hardware_path: Optional[Path] = None

        if hardware_path is not None:
            self.load_hardware(hardware_path)

        # --- 2. QMM connection ---
        self._qmm = QuantumMachinesManager(
            host=qop_ip, cluster_name=cluster_name,
        )

        # --- 3. HardwareController ---
        hw_kwargs: dict[str, Any] = {}
        if default_output_mode is not None:
            hw_kwargs["default_output_mode"] = default_output_mode

        if self._config_engine is not None:
            self._hw = HardwareController(
                qmm=self._qmm,
                config_engine=self._config_engine,
                **hw_kwargs,
            )
        else:
            self._hw = None

        # --- 4. ProgramRunner ---
        self._runner: Optional[ProgramRunner] = None
        if self._hw is not None and self._config_engine is not None:
            self._runner = ProgramRunner(
                qmm=self._qmm,
                controller=self._hw,
                config_engine=self._config_engine,
            )

        # --- 5. QueueManager ---
        self._queue: Optional[QueueManager] = None
        if self._runner is not None:
            self._queue = QueueManager(runner=self._runner)

        _logger.info("QuaProgramManager (compat) created for %s / %s",
                      qop_ip, cluster_name)

    # ------------------------------------------------------------------
    # Config / hardware loading
    # ------------------------------------------------------------------
    @property
    def hardware(self):
        """Return the raw hardware config dict, or None if not loaded."""
        if self._config_engine is None:
            return None
        return self._config_engine.hardware_base

    @property
    def cluster_name(self) -> str:
        return self._cluster_name

    def load_hardware(self, path: str | Path) -> None:
        """Load hardware.json and (re-)create the config engine."""
        path = Path(path)
        self._hardware_path = path
        self._config_engine = ConfigEngine(hardware_path=path)
        _logger.info("Hardware loaded from %s", path)

        # Rebuild dependent objects if QMM is ready
        if hasattr(self, "_qmm") and self._qmm is not None:
            self._hw = HardwareController(
                qmm=self._qmm,
                config_engine=self._config_engine,
            )
            self._runner = ProgramRunner(
                qmm=self._qmm,
                controller=self._hw,
                config_engine=self._config_engine,
            )
            self._queue = QueueManager(runner=self._runner)

    def burn_pulse_to_qm(self, pulse_op_mngr, include_volatile: bool = True) -> None:
        """Merge PulseOperationManager pulses into the hardware config."""
        if self._config_engine is None:
            raise RuntimeError("No hardware loaded; call load_hardware() first.")
        # Use ConfigEngine.merge_pulses which properly separates pulse data
        # from element operations (avoids overwriting element RF_inputs/outputs)
        self._config_engine.merge_pulses(pulse_op_mngr, include_volatile=include_volatile)
        _logger.info("Pulses burned into QM config.")

    def init_qm(self) -> None:
        """Open the QM instance with the current config."""
        if self._hw is None:
            raise RuntimeError("HardwareController not initialised.")
        self._hw.open_qm()

    def init_config(self, output_mode=None, **kwargs) -> None:
        """Initialise octave outputs and apply output mode."""
        if self._hw is None:
            raise RuntimeError("HardwareController not initialised.")
        self._hw.init_config(output_mode=output_mode)

    # ------------------------------------------------------------------
    # Element control  (delegated to HardwareController)
    # ------------------------------------------------------------------
    def set_element_fq(self, el: str, freq: float) -> None:
        self._hw.set_element_fq(el, freq)

    def set_element_lo(self, el: str, lo_freq: float) -> None:
        self._hw.set_element_lo(el, lo_freq)

    def get_element_lo(self, el):
        return self._hw.get_element_lo(el)

    def get_element_if(self, el):
        return self._hw.get_element_if(el)

    def set_octave_output(self, el: str, mode) -> None:
        self._hw.set_octave_output(el, mode)

    def set_device_manager(self, dm) -> None:
        self._hw.set_device_manager(dm)

    def set_spa_pump(self, sc) -> None:
        self._hw.set_spa_pump(sc)

    # ------------------------------------------------------------------
    # Program execution  (delegated to ProgramRunner)
    # ------------------------------------------------------------------
    def run_program(self, qua_prog, n_total: int = 1, **kwargs) -> RunResult:
        if self._runner is None:
            raise RuntimeError("ProgramRunner not initialised.")
        return self._runner.run_program(qua_prog, n_total=n_total, **kwargs)

    def set_exec_mode(self, mode) -> None:
        if self._runner is None:
            raise RuntimeError("ProgramRunner not initialised.")
        self._runner.set_exec_mode(mode)

    def get_exec_mode(self) -> ExecMode:
        if self._runner is None:
            raise RuntimeError("ProgramRunner not initialised.")
        return self._runner.get_exec_mode()

    # ------------------------------------------------------------------
    # Queue operations  (delegated to QueueManager)
    # ------------------------------------------------------------------
    def queue_submit_many_with_progress(self, programs, **kwargs):
        if self._queue is None:
            raise RuntimeError("QueueManager not initialised.")
        return self._queue.submit_many_with_progress(programs, **kwargs)

    def queue_run_many(self, pendings, **kwargs):
        if self._queue is None:
            raise RuntimeError("QueueManager not initialised.")
        return self._queue.run_many(pendings, **kwargs)
