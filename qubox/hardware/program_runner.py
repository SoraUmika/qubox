"""
ProgramRunner: execute and simulate QUA programs.

Extracted from QuaProgramManager — this class handles:
  - run_program() with optional queue support
  - simulate() with custom plotting
  - serialize_program()
  - ExecMode / RunResult
"""
from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional, Union

import matplotlib.pyplot as plt
import numpy as np
from grpclib.exceptions import StreamTerminatedError
from matplotlib.gridspec import GridSpec
from octave_sdk import RFOutputMode
from qm import QuantumMachinesManager, SimulationConfig, generate_qua_script, qua
from qm.jobs.running_qm_job import RunningQmJob
from qm.simulate import SimulatorControllerSamples, SimulatorSamples
from tqdm import tqdm

from ..core.errors import ConfigError, ConnectionError, JobError
from ..core.utils import require, numeric_keys_to_ints, get_nested
from ..core.logging import get_logger

_logger = get_logger(__name__)


# ────────────────────────── ExecMode / RunResult ──────────────────────────────
class ExecMode(str, Enum):
    HARDWARE = "hardware"
    SIMULATE = "simulate"


def coerce_exec_mode(mode: "ExecMode | str | None") -> ExecMode:
    if mode is None:
        return ExecMode.HARDWARE
    if isinstance(mode, ExecMode):
        return mode
    s = str(mode).strip().lower()
    if s in ("hardware", "hw"):
        return ExecMode.HARDWARE
    if s in ("simulate", "sim"):
        return ExecMode.SIMULATE
    raise ValueError(f"Unknown ExecMode: {mode!r}")


@dataclass
class RunResult:
    mode: ExecMode
    output: Any  # Output dict-like
    sim_samples: Optional[Any] = None
    metadata: dict | None = None


# Default plotting behavior for simulate()
_DEFAULT_PLOT_PARAMS: Dict[str, Any] = {
    "which": "both",
    "channels": None,
    "time_unit": "ns",
    "xlim": None,
    "ylim": None,
    "digital_ylim": None,
    "title": None,
    "legend": True,
    "grid": True,
}


@dataclass
class QuboxSimulationConfig:
    """qubox-specific wrapper around QM's ``SimulationConfig``.

    Provides sensible defaults and centralises the ns → clock-cycle
    conversion that is scattered in legacy code.
    """

    duration_ns: int = 4000
    """Simulation duration in **nanoseconds**."""

    plot: bool = True
    """Whether to auto-plot simulated waveforms."""

    plot_params: Dict[str, Any] | None = None
    """Override keys from ``_DEFAULT_PLOT_PARAMS``."""

    controllers: tuple[str, ...] = ("con1",)
    """Controller names to include in plots."""

    t_begin: float | None = None
    """Plot time window start (in ``time_unit``)."""

    t_end: float | None = None
    """Plot time window end (in ``time_unit``)."""

    compiler_options: Any = None
    """Forwarded to ``qmm.simulate()``."""

    def to_qm_sim_config(self) -> SimulationConfig:
        """Convert to QM SDK ``SimulationConfig`` (clock cycles = ns // 4)."""
        return SimulationConfig(duration=int(self.duration_ns // 4))


def _prog_flag(prog, name: str, default=None):
    return getattr(prog, name, default)


def _format_runtime_errors(stage: str, errors: list[str]) -> str:
    preview = "; ".join(errors[:3])
    if len(errors) > 3:
        preview = f"{preview}; ... ({len(errors)} total)"
    return f"{stage} failed: {preview}"


class ProgramRunner:
    """
    Execute or simulate QUA programs.

    Depends on:
        - HardwareController (for QM instance access & element management)
        - ConfigEngine (for building configs)
        - Optional processors list
    """

    def __init__(
        self,
        qmm: QuantumMachinesManager,
        controller,  # HardwareController
        config_engine,  # ConfigEngine
    ):
        self._qmm = qmm
        self.hw = controller
        self.config = config_engine
        self._lock = threading.RLock()

        # Execution state
        self.exec_mode = ExecMode.HARDWARE
        self.job: Optional[RunningQmJob] = None
        self.processors: List[Callable] = []

        # Program memory (for serialize_program())
        self.current_program = None
        self._last_program_cfg: dict | None = None
        self._last_program_meta: dict = {}
        self._last_program_ts: float | None = None

    # ─── Program memory ───────────────────────────────────────────
    def _remember_program(self, qua_prog, *, cfg: dict | None = None, meta: dict | None = None) -> None:
        with self._lock:
            self.current_program = qua_prog
            self._last_program_ts = time.time()
            if cfg is not None:
                self._last_program_cfg = deepcopy(cfg)
            if meta:
                self._last_program_meta = {**self._last_program_meta, **deepcopy(meta)}

    def register_processor(self, processor: Callable) -> None:
        require(callable(processor), "processor must be callable")
        self.processors.append(processor)

    # ─── ExecMode ─────────────────────────────────────────────────
    def set_exec_mode(self, mode: ExecMode | str) -> None:
        self.exec_mode = coerce_exec_mode(mode)
        _logger.info("Exec mode set to: %s", self.exec_mode)

    def get_exec_mode(self) -> ExecMode:
        return self.exec_mode

    @staticmethod
    def _program_exec_mode(qua_prog) -> ExecMode | None:
        if getattr(qua_prog, "_simulate_only", False):
            return ExecMode.SIMULATE
        m = getattr(qua_prog, "_exec_mode", None)
        if m is None:
            return None
        try:
            return coerce_exec_mode(m)
        except Exception:
            raise ConfigError(f"Invalid qua_prog._exec_mode = {m!r}")

    # ─── Run (hardware) ──────────────────────────────────────────
    def run_program(
        self,
        qua_prog,
        n_total: int,
        print_report: bool = True,
        show_progress: bool = True,
        processors: list | None = None,
        progress_handle: str = "iteration",
        auto_job_halt: bool = True,
        process_in_sim: bool | None = None,
        *,
        use_queue: bool = False,
        queue_to_start: bool = False,
        queue_only: bool = False,
        allow_partial_results: bool = False,
        timeout_sec: float | None = None,
        **kwargs,
    ) -> RunResult:
        """Execute a QUA program on hardware."""
        # Manager-wide guard
        if self.exec_mode == ExecMode.SIMULATE:
            raise JobError(
                "run_program() is hardware-only, but ProgramRunner is in ExecMode.SIMULATE. "
                "Call set_exec_mode('hardware') or use simulate()."
            )

        # Program-level guard
        p_mode = self._program_exec_mode(qua_prog)
        if p_mode == ExecMode.SIMULATE:
            raise JobError("This QUA program is marked SIMULATE-only. Use simulate() instead.")

        require(self.hw.qm is not None, "QM not initialized.", ConfigError)

        _t0 = time.monotonic()

        # Config snapshot
        cfg_snapshot = self.config.build_qm_config()
        self._remember_program(qua_prog, cfg=cfg_snapshot, meta={"last_mode": "hardware", "use_queue": bool(use_queue)})

        # Lazy import to avoid circular dependency
        from qubox_tools.data.containers import Output
        out = Output()
        sim_samples = None
        pending = None
        fetch_errors: list[str] = []

        try:
            with self._pump_on():
                # Start job
                try:
                    if use_queue:
                        pending = (
                            self.hw.qm.queue.add_to_start(qua_prog)
                            if queue_to_start
                            else self.hw.qm.queue.add(qua_prog)
                        )

                        if queue_only:
                            meta = {
                                "n_total": int(n_total), "queued": True, "queue_only": True,
                                "pending_job": pending,
                                "job_id": getattr(pending, "job_id", None),
                                "time_added": getattr(pending, "time_added", None),
                                "user_added": getattr(pending, "user_added", None),
                            }
                            self._remember_program(qua_prog, cfg=cfg_snapshot, meta=meta)
                            return RunResult(mode=ExecMode.HARDWARE, output=Output(), sim_samples=None, metadata=meta)

                        self.job = pending.wait_for_execution()
                    else:
                        self.job = self.hw.qm.execute(qua_prog)

                except StreamTerminatedError as e:
                    raise ConnectionError("Connection lost during execute/queue.") from e
                except Exception as e:
                    raise JobError(f"Failed to start job: {e}") from e

                # Progress
                if show_progress:
                    self._report_progress(self.job, n_total, progress_handle, show_progress=True, timeout_sec=timeout_sec, t0=_t0)

                # Execution report
                if print_report:
                    with contextlib.suppress(Exception):
                        report = self.job.execution_report()
                        if report:
                            _logger.info("Execution report:\n%s", report)

                # Fetch results
                for name, handle in list(self.job.result_handles.items()):
                    try:
                        out[name] = handle.fetch_all()
                    except Exception as e:
                        fetch_errors.append(f"handle={name!r}: {e}")
                        _logger.error("Fetch failed for handle '%s': %s", name, e)

        finally:
            if auto_job_halt:
                with contextlib.suppress(Exception):
                    self.halt_job()

        if fetch_errors and not allow_partial_results:
            raise JobError(_format_runtime_errors("Result fetch", fetch_errors))

        # Processing
        procs = processors or self.processors
        processor_errors: list[str] = []
        if procs:
            for proc in procs:
                try:
                    out = proc(out, **kwargs)
                except Exception as e:
                    processor_errors.append(f"processor={getattr(proc, '__name__', repr(proc))}: {e}")
                    _logger.error("Processor %s failed: %s", getattr(proc, "__name__", repr(proc)), e)

        if processor_errors and not allow_partial_results:
            raise JobError(_format_runtime_errors("Post-processing", processor_errors))

        meta = {"n_total": int(n_total)}
        if use_queue:
            meta.update({
                "queued": True, "queue_only": False,
                "job_id": getattr(pending, "job_id", None) if pending else None,
                "time_added": getattr(pending, "time_added", None) if pending else None,
                "user_added": getattr(pending, "user_added", None) if pending else None,
            })
        if fetch_errors:
            meta["fetch_errors"] = list(fetch_errors)
        if processor_errors:
            meta["processor_errors"] = list(processor_errors)
        if allow_partial_results:
            meta["allow_partial_results"] = True
        return RunResult(mode=ExecMode.HARDWARE, output=out, sim_samples=sim_samples, metadata=meta)

    def halt_job(self) -> None:
        if not self.job:
            return
        try:
            self.job.halt()
            _logger.info("Job halted successfully.")
        except StreamTerminatedError:
            _logger.warning("Connection lost while halting job.")
        except Exception as e:
            _logger.error("Failed to halt job: %s", e)

    def _report_progress(self, job: RunningQmJob, n_total: int, handle: str, *, show_progress: bool = True, timeout_sec: float | None = None, t0: float = 0.0) -> None:
        if not n_total:
            _logger.info("n_total not passed; skipping progress.")
            return
        handles = job.result_handles

        # Try the requested handle, then common fallback names
        actual_handle = None
        for candidate in (handle, "iteration", "n", "avg_counter"):
            if candidate in handles.keys():
                actual_handle = candidate
                break

        if actual_handle is None:
            _logger.info("No progress handle found (tried '%s' + fallbacks); waiting for completion...", handle)
            while handles.is_processing():
                if timeout_sec is not None and (time.monotonic() - t0) > timeout_sec:
                    _logger.error("Program execution timed out after %.1f s", timeout_sec)
                    with contextlib.suppress(Exception):
                        self.halt_job()
                    raise JobError(f"Program execution timed out after {timeout_sec:.1f} s")
                time.sleep(0.1)
            _logger.info("Job complete.")
            return

        with tqdm(total=n_total, desc="Running Program...", disable=not show_progress) as bar:
            while handles.is_processing():
                if timeout_sec is not None and (time.monotonic() - t0) > timeout_sec:
                    _logger.error("Program execution timed out after %.1f s", timeout_sec)
                    with contextlib.suppress(Exception):
                        self.halt_job()
                    raise JobError(f"Program execution timed out after {timeout_sec:.1f} s")
                time.sleep(0.05)
                with contextlib.suppress(Exception):
                    h = handles.get(actual_handle)
                    if h:
                        bar.n = h.fetch_all()
                        bar.refresh()
            with contextlib.suppress(Exception):
                h = handles.get(actual_handle)
                if h:
                    bar.n = h.fetch_all()
                    bar.refresh()

    @contextlib.contextmanager
    def _pump_on(self):
        try:
            if self.hw.spa_pump_sc:
                self.hw.spa_pump_sc.do_set_output_status(True)
            yield
        finally:
            if self.hw.spa_pump_sc:
                with contextlib.suppress(Exception):
                    self.hw.spa_pump_sc.do_set_output_status(False)

    # ─── Serialize ────────────────────────────────────────────────
    def serialize_program(
        self,
        qua_prog=None,
        path: Path | str = "",
        filename: str = "debug.py",
        *,
        use_last_snapshot: bool = True,
    ) -> str:
        with self._lock:
            if qua_prog is None:
                qua_prog = self.current_program
            require(qua_prog is not None, "No program to serialize.", JobError)

            if use_last_snapshot and (qua_prog is self.current_program) and self._last_program_cfg is not None:
                cfg = deepcopy(self._last_program_cfg)
            else:
                cfg = self.config.build_qm_config()

        full_path = Path(path) / filename
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, "w") as f:
            print(generate_qua_script(qua_prog, cfg), file=f)
        return str(full_path)

    # ─── Simulate ─────────────────────────────────────────────────
    def simulate(
        self,
        program,
        *,
        duration: int = 4000,
        plot: bool = True,
        plot_params: Optional[Dict[str, Any]] = None,
        controllers=("con1",),
        t_begin: float | None = None,
        t_end: float | None = None,
        compiler_options=None,
    ):
        cfg = self.config.build_qm_config()
        require(cfg, "No config available for simulation.")

        pp = deepcopy(_DEFAULT_PLOT_PARAMS)
        if plot_params:
            pp.update(plot_params)

        sim_config = SimulationConfig(duration=int(int(duration) / 4))
        job = self._qmm.simulate(cfg, program, sim_config, compiler_options=compiler_options)
        sim_raw = job.get_simulated_samples()
        sim_labeled = self._relabel_simulator_samples(sim_raw)

        if plot:
            self._plot_sim_custom(sim_labeled, plot_params=pp, controllers=controllers,
                                  t_begin=t_begin, t_end=t_end)
        return sim_labeled

    # ─── Simulator relabeling ─────────────────────────────────────
    def _octave_links(self) -> list[dict]:
        ex = self.config.hardware_extras or {}
        if "octave_links" in ex:
            return list(ex["octave_links"] or [])
        qubox = ex.get("__qubox") or {}
        return list(qubox.get("octave_links") or [])

    def _build_ao_aliases_from_config(self) -> Dict[str, Dict[str, str]]:
        cfg = self.config.build_qm_config()
        elements = cfg.get("elements", {}) or {}
        links = self._octave_links()

        rf_to_ao: Dict[tuple[str, int], tuple[str, int, int]] = {}
        for it in links:
            try:
                rf_to_ao[(str(it["octave"]), int(it["rf_out"]))] = (
                    str(it["controller"]), int(it["ao_i"]), int(it["ao_q"]))
            except Exception:
                continue

        per_ctrl: Dict[str, Dict[str, str]] = {}
        for el_name, el in elements.items():
            rf_in = el.get("RF_inputs")
            if not isinstance(rf_in, dict):
                continue
            port = rf_in.get("port")
            if not (isinstance(port, (list, tuple)) and len(port) >= 2):
                continue
            tup = rf_to_ao.get((str(port[0]), int(port[1])))
            if not tup:
                continue
            ctrl, ao_i, ao_q = tup
            m = per_ctrl.setdefault(ctrl, {})
            m[f"1-{ao_i}"] = f"{el_name}:I"
            m[f"1-{ao_q}"] = f"{el_name}:Q"
        return per_ctrl

    def _build_do_aliases_from_config(self) -> Dict[str, Dict[str, str]]:
        cfg = self.config.build_qm_config()
        elements = cfg.get("elements", {}) or {}
        per_ctrl: Dict[str, Dict[str, str]] = {}
        for el_name, el in elements.items():
            for label, meta in (el.get("digitalInputs") or {}).items():
                port = meta.get("port")
                if not (isinstance(port, (list, tuple)) and len(port) >= 2):
                    continue
                ctrl, dport = str(port[0]), int(port[1])
                per_ctrl.setdefault(ctrl, {})[f"1-{dport}"] = f"{el_name}:{label}"
        return per_ctrl

    def _relabel_simulator_samples(self, sim) -> "SimulatorSamples":
        ao_aliases = self._build_ao_aliases_from_config()
        do_aliases = self._build_do_aliases_from_config()
        relabeled = {}
        for ctrl, con in sim.items():
            a_alias = ao_aliases.get(ctrl, {})
            d_alias = do_aliases.get(ctrl, {})
            analog_new, sr_new = {}, {}
            for raw_key, arr in con.analog.items():
                new_key = a_alias.get(raw_key, raw_key)
                analog_new[new_key] = arr
                sr_new[new_key] = con.analog_sampling_rate.get(str(raw_key), 1e9)
            digital_new = {d_alias.get(k, k): v for k, v in con.digital.items()}
            relabeled[ctrl] = SimulatorControllerSamples(
                analog=analog_new, digital=digital_new, analog_sampling_rate=sr_new)
        return SimulatorSamples(relabeled)

    # ─── Simulation plotting ─────────────────────────────────────
    def _plot_sim_custom(self, sim, *, plot_params, controllers=("con1",),
                         t_begin=None, t_end=None):
        pp = plot_params or {}
        which = pp.get("which", "both")
        channels = pp.get("channels", None)
        time_unit = str(pp.get("time_unit", "ns"))
        xlim = pp.get("xlim", None)
        ylim = pp.get("ylim", None)
        dylim = pp.get("digital_ylim", None)
        title = pp.get("title", None)
        grid = bool(pp.get("grid", True))
        legend = bool(pp.get("legend", True))

        unit_scale = {"ns": 1.0, "us": 1e-3, "ms": 1e-6}.get(time_unit, 1.0)

        def t_axis(n, fs_hz):
            return (np.arange(n) / float(fs_hz)) * 1e9 * unit_scale

        if t_begin is not None or t_end is not None:
            tb = 0.0 if t_begin is None else float(t_begin)
            te = float("inf") if t_end is None else float(t_end)
            if tb < 0:
                raise ValueError("t_begin must be >= 0")
            if not np.isinf(te) and te <= tb:
                raise ValueError("t_end must be > t_begin")
        else:
            tb = te = None

        include_analog = which in ("analog", "both")
        include_digital = which in ("digital", "both")

        fig = plt.figure(constrained_layout=True, figsize=(8.5, 4.2))
        gs = GridSpec(nrows=1, ncols=2, figure=fig, width_ratios=[1.0, 0.45], wspace=0.06)
        ax = fig.add_subplot(gs[0, 0])
        ax2 = None
        ax_leg = fig.add_subplot(gs[0, 1])
        ax_leg.set_axis_off()

        analog_plotted = digital_plotted = False

        for ctrl in controllers:
            if ctrl not in sim:
                continue
            con = sim[ctrl]

            if include_analog:
                for name, y in con.analog.items():
                    if channels and name not in channels:
                        continue
                    if len(y) == 0 or not np.any(y):
                        continue
                    fs = con.analog_sampling_rate.get(name, 1e9)
                    t = t_axis(len(y), fs)
                    y_arr = np.asarray(y)
                    if tb is not None:
                        mask = (t >= tb) & (t <= te)
                        if not np.any(mask):
                            continue
                        t, y_arr = t[mask], y_arr[mask]
                    ax.plot(t, y_arr, label=f"{ctrl}:{name}")
                    analog_plotted = True

            if include_digital:
                for name, d in con.digital.items():
                    if channels and name not in channels:
                        continue
                    if len(d) == 0 or not np.any(d):
                        continue
                    if ax2 is None:
                        ax2 = ax.twinx()
                    t = t_axis(len(d), 1e9)
                    d_arr = np.asarray(d, dtype=float)
                    if tb is not None:
                        mask = (t >= tb) & (t <= te)
                        if not np.any(mask):
                            continue
                        t, d_arr = t[mask], d_arr[mask]
                    ax2.step(t, d_arr, where="post", linestyle="--", label=f"{ctrl}:{name} (D)")
                    digital_plotted = True

        ax.set_xlabel(f"Time [{time_unit}]")
        if analog_plotted:
            ax.set_ylabel("Voltage [V]")
        if digital_plotted and ax2 is not None:
            ax2.set_ylabel("Digital")
            ax2.set_ylim(*(dylim if dylim else (-0.1, 1.1)))
        if title:
            ax.set_title(title)
        if grid:
            ax.grid(True, which="both", axis="both", alpha=0.3)
        if xlim:
            ax.set_xlim(*xlim)
            if ax2:
                ax2.set_xlim(*xlim)
        elif tb is not None:
            x_max = te if not np.isinf(te) else ax.get_xlim()[1]
            ax.set_xlim(tb, x_max)
            if ax2:
                ax2.set_xlim(tb, x_max)
        if ylim and analog_plotted:
            ax.set_ylim(*ylim)
        if legend:
            h1, l1 = ax.get_legend_handles_labels()
            h2, l2 = (ax2.get_legend_handles_labels() if ax2 else ([], []))
            handles = h1 + h2
            labels = l1 + l2
            if handles:
                ax_leg.legend(handles, labels, loc="center left", frameon=False)
        plt.show()

    # ─── Continuous wave helper ───────────────────────────────────
    def run_continuous_wave(self, elements: list, el_freqs: list, pulses: list, gain=1.0):
        require(self.hw.qm is not None, "QM not initialized.", ConfigError)
        require(len(elements) == len(el_freqs), "elements and frequencies must match.")
        for el, if_freq in zip(elements, el_freqs):
            self.hw.qm.set_intermediate_frequency(el, if_freq)
        with qua.program() as cw_prog:
            with qua.infinite_loop_():
                for el, pulse in zip(elements, pulses):
                    qua.play(pulse * qua.amp(gain), el)
        self.run_program(cw_prog, n_total=1, print_report=False, show_progress=False, auto_job_halt=False)

    # ─── Utility ──────────────────────────────────────────────────
    @staticmethod
    def _progress_value(x) -> int:
        if x is None:
            return 0
        if isinstance(x, (int, np.integer)):
            return int(x)
        if isinstance(x, (float, np.floating)):
            return int(x)
        if isinstance(x, (list, tuple)) and len(x) > 0:
            return int(x[-1])
        if isinstance(x, np.ndarray):
            return int(x.reshape(-1)[-1]) if x.size else 0
        try:
            return int(x)
        except Exception:
            return 0

    def _collect_output_from_job(self, job, *, print_report: bool, allow_partial_results: bool = False):
        from qubox_tools.data.containers import Output
        out = Output()
        fetch_errors: list[str] = []
        if print_report:
            with contextlib.suppress(Exception):
                report = job.execution_report()
                if report:
                    _logger.info("Execution report:\n%s", report)
        for name, handle in list(job.result_handles.items()):
            try:
                out[name] = handle.fetch_all()
            except Exception as e:
                fetch_errors.append(f"handle={name!r}: {e}")
                _logger.error("Fetch failed for handle '%s': %s", name, e)
        if fetch_errors and not allow_partial_results:
            raise JobError(_format_runtime_errors("Result fetch", fetch_errors))
        return out
