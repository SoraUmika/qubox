"""qubox_v2.experiments.experiment_base
======================================
Base class for modular experiment types.

Each experiment class wraps one or more QUA program factories from
``qubox_v2.programs.cQED_programs`` and provides a consistent interface
for building, running, and post-processing results.

Experiment classes are lightweight — they hold a reference to the
experiment *context* (``cQED_Experiment`` or ``ExperimentRunner``) which
provides hardware control, pulse management, device access, and
calibration storage.

Usage::

    from qubox_v2.experiments.spectroscopy import ResonatorSpectroscopy

    exp = cQED_Experiment(...)
    spec = ResonatorSpectroscopy(exp)
    result = spec.run(readout_op="readout", rf_begin=8.6e9, rf_end=8.62e9, df=50e3)
"""
from __future__ import annotations

import datetime
import json
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from ..programs import cQED_programs
from ..analysis import post_process as pp
from ..analysis.output import Output
from ..core.logging import get_logger
from ..core.persistence_policy import sanitize_mapping_for_json
from ..hardware.program_runner import RunResult

if TYPE_CHECKING:
    from ..analysis.cQED_attributes import cQED_attributes
    from ..devices.device_manager import DeviceManager
    from ..pulses.manager import PulseOperationManager

_logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Utility functions (formerly module-level in legacy_experiment.py)
# ---------------------------------------------------------------------------
from .config_builder import ConfigSettings

def create_if_frequencies(
    el: str, start_fq: float, end_fq: float, df: float,
    lo_freq: float, base_if_freq: float = ConfigSettings.BASE_IF,
) -> np.ndarray:
    """Compute IF frequency array for a sweep, validating bounds."""
    up_converted_if = lo_freq + base_if_freq
    max_bandwidth = abs(ConfigSettings.MAX_IF_BANDWIDTH - abs(base_if_freq))
    sweep_min = up_converted_if - max_bandwidth
    sweep_max = up_converted_if

    if not (sweep_min <= start_fq <= end_fq <= sweep_max):
        raise ValueError(
            f"Sweep range [{start_fq/1e6:.1f}, {end_fq/1e6:.1f}] MHz outside "
            f"[{sweep_min/1e6:.1f}, {sweep_max/1e6:.1f}] MHz for element "
            f"'{el}' (LO={lo_freq/1e6:.1f}, IF={base_if_freq/1e6:.1f} MHz)"
        )
    return np.arange(start_fq - lo_freq, end_fq - lo_freq - 0.1, df, dtype=int)


def create_clks_array(
    t_begin: float, t_end: float, dt: float,
    time_per_clk: float = 4,
) -> np.ndarray:
    """Convert time range to clock-cycle array with rounding warnings."""
    if t_end < t_begin:
        raise ValueError("t_end must be >= t_begin")
    if dt <= 0:
        raise ValueError("dt must be positive")

    def _snap(v, label):
        snapped = round(v / time_per_clk) * time_per_clk
        if snapped != v:
            warnings.warn(
                f"{label} {v} rounded to {snapped} (grid={time_per_clk})",
                RuntimeWarning, stacklevel=3,
            )
        return snapped

    t_begin = _snap(t_begin, "t_begin")
    t_end = _snap(t_end, "t_end")
    dt = _snap(dt, "dt")

    clk_begin = int(t_begin // time_per_clk)
    clk_end = int(t_end // time_per_clk)
    clk_step = int(dt // time_per_clk)
    return np.arange(clk_begin, clk_end + 1, clk_step, dtype=int)


def make_lo_segments(rf_begin: float, rf_end: float) -> list[float]:
    """Compute LO frequency list for multi-segment coarse sweeps."""
    M = ConfigSettings.MAX_IF_BANDWIDTH
    B = ConfigSettings.BASE_IF
    if M <= abs(B):
        raise ValueError("MAX_IF_BANDWIDTH must be greater than |BASE_IF|")
    span = M + B
    if (rf_end - rf_begin) <= span:
        return [rf_begin + M]
    los: list[float] = []
    LO = rf_begin + M
    last = rf_end - B
    while LO < last:
        los.append(LO)
        LO += span
    if los[-1] < last:
        los.append(last)
    return los


def if_freqs_for_segment(LO: float, rf_end: float, df: float) -> np.ndarray:
    """Compute IF frequency array for one segment of a coarse sweep."""
    M = ConfigSettings.MAX_IF_BANDWIDTH
    B = ConfigSettings.BASE_IF
    max_if = (rf_end - LO) if (rf_end - LO) < (M + B) else B
    return np.arange(-M, max_if + 1e-12, df, dtype=int)


def merge_segment_outputs(
    outputs: list[Output], freqs: list[np.ndarray],
) -> Output:
    """Stitch multiple segment outputs into one."""
    merged: dict[str, Any] = {}
    for key in outputs[0]:
        vals = [o[key] for o in outputs if key in o]
        if isinstance(vals[0], np.ndarray):
            try:
                merged[key] = np.concatenate(vals, axis=0)
            except Exception:
                merged[key] = vals
        elif isinstance(vals[0], list):
            merged[key] = sum(vals, [])
        else:
            merged[key] = vals[0] if all(v == vals[0] for v in vals) else vals
    merged["frequencies"] = np.concatenate(freqs, axis=0)
    return Output(merged)


# ---------------------------------------------------------------------------
# ExperimentBase
# ---------------------------------------------------------------------------
class ExperimentBase:
    """Base class for modular experiment types.

    Provides unified access to the experiment infrastructure regardless
    of whether the context is a ``cQED_Experiment`` (legacy) or the
    new ``ExperimentRunner``.

    Parameters
    ----------
    ctx
        Experiment context — either ``cQED_Experiment`` or
        ``ExperimentRunner``.
    """

    def __init__(self, ctx: Any) -> None:
        if ctx is None:
            raise ValueError(
                "Experiment context is not set. Pass a SessionManager or "
                "ExperimentRunner instance when creating an experiment."
            )
        self._ctx = ctx

    @property
    def name(self) -> str:
        return type(self).__name__

    # ------------------------------------------------------------------
    # Context accessors (work with both legacy and new interfaces)
    # ------------------------------------------------------------------
    @property
    def attr(self) -> cQED_attributes:
        a = getattr(self._ctx, "attributes", None)
        if a is None:
            raise RuntimeError(
                "Experiment context has no 'attributes'. Ensure cqed_params.json "
                "exists in your experiment directory and was loaded successfully."
            )
        return a

    @property
    def pulse_mgr(self) -> PulseOperationManager:
        pm = getattr(self._ctx, "pulseOpMngr",
                     getattr(self._ctx, "pulse_mgr", None))
        if pm is None:
            raise RuntimeError(
                "Experiment context has no pulse manager. Check that "
                "SessionManager or ExperimentRunner initialised correctly."
            )
        return pm

    @property
    def hw(self):
        """Hardware controller (QuaProgramManager or HardwareController)."""
        h = getattr(self._ctx, "quaProgMngr",
                    getattr(self._ctx, "hw", None))
        if h is None:
            raise RuntimeError(
                "Experiment context has no hardware controller. Check that "
                "SessionManager or ExperimentRunner initialised correctly."
            )
        return h

    @property
    def device_manager(self) -> DeviceManager | None:
        return getattr(self._ctx, "device_manager", None)

    @property
    def measure_macro(self):
        """Access the measurement macro singleton."""
        from ..programs.macros.measure import measureMacro
        return measureMacro

    @property
    def bindings(self):
        """Access ExperimentBindings from the session context.

        Returns the session's binding bundle if available, or raises
        RuntimeError.
        """
        b = getattr(self._ctx, "bindings", None)
        if b is not None:
            return b
        # Fallback: try to construct from attributes + hardware config
        from ..core.bindings import bindings_from_hardware_config
        hw = getattr(self._ctx, "config_engine", None)
        if hw is not None:
            return bindings_from_hardware_config(hw.hardware, self.attr)
        raise RuntimeError(
            "Experiment context has no bindings. Use a SessionManager "
            "with hardware.json and cqed_params.json."
        )

    @property
    def _bindings_or_none(self):
        """Return ExperimentBindings if available, else None."""
        try:
            return self.bindings
        except (RuntimeError, AttributeError):
            return None

    # ------------------------------------------------------------------
    # Common helpers
    # ------------------------------------------------------------------
    def get_calibrated_frequency(
        self,
        element: str,
        *,
        field: str = "qubit_freq",
        fallback: float | None = None,
    ) -> float | None:
        """Resolve a calibrated frequency (Hz) from CalibrationStore when available.

        Returns ``fallback`` when the calibration entry is unavailable or invalid.
        """
        cal = getattr(self._ctx, "calibration", None)
        if cal is None:
            return fallback
        try:
            freq_entry = cal.get_frequencies(element)
        except Exception:
            return fallback
        if freq_entry is None:
            return fallback
        value = getattr(freq_entry, field, None)
        if isinstance(value, (int, float, np.floating)) and np.isfinite(value):
            return float(value)
        return fallback

    def get_qubit_frequency(self) -> float:
        """Return active qubit frequency in Hz (calibrated first, attributes fallback)."""
        fallback = float(self.attr.qb_fq)
        resolved = self.get_calibrated_frequency(self.attr.qb_el, field="qubit_freq", fallback=fallback)
        return float(resolved if resolved is not None else fallback)

    def set_standard_frequencies(self, *, qb_fq: float | None = None) -> None:
        """Set readout and qubit element frequencies to calibrated values.

        Resolution order for readout frequency:
          1. ``bindings.readout.drive_frequency`` (binding-driven path)
          2. ``measureMacro._drive_frequency`` (singleton compat)
          3. ``attr.ro_fq`` (attributes fallback)
        """
        ro_fq = None
        b = self._bindings_or_none
        if b is not None and b.readout is not None:
            ro_fq = getattr(b.readout, "drive_frequency", None)
        if not isinstance(ro_fq, (int, float, np.floating)) or not np.isfinite(ro_fq):
            mm = self.measure_macro
            ro_fq = getattr(mm, "_drive_frequency", None)
        if not isinstance(ro_fq, (int, float, np.floating)) or not np.isfinite(ro_fq):
            ro_fq = self.attr.ro_fq
        self.hw.set_element_fq(self.attr.ro_el, float(ro_fq))
        target_qb_fq = float(qb_fq) if qb_fq is not None else self.get_qubit_frequency()
        self.hw.set_element_fq(self.attr.qb_el, target_qb_fq)

    def get_readout_lo(self) -> float:
        """Return readout LO frequency, preferring bindings when available."""
        b = self._bindings_or_none
        if b is not None and b.readout is not None:
            lo = getattr(b.readout.drive_out, "lo_frequency", None)
            if lo is not None:
                return float(lo)
        return self.hw.get_element_lo(self.attr.ro_el)

    def get_qubit_lo(self) -> float:
        """Return qubit LO frequency, preferring bindings when available."""
        b = self._bindings_or_none
        if b is not None and b.qubit is not None:
            lo = getattr(b.qubit, "lo_frequency", None)
            if lo is not None:
                return float(lo)
        return self.hw.get_element_lo(self.attr.qb_el)

    # ------------------------------------------------------------------
    # Pure frequency resolvers (no side-effects)
    # ------------------------------------------------------------------
    def _resolve_readout_frequency(self) -> float:
        """Resolve readout frequency: bindings → measureMacro → attributes.

        Unlike ``set_standard_frequencies`` this method does **not** apply
        the frequency — it only returns the resolved value.
        """
        b = self._bindings_or_none
        if b is not None and b.readout is not None:
            ro_fq = getattr(b.readout, "drive_frequency", None)
            if isinstance(ro_fq, (int, float, np.floating)) and np.isfinite(ro_fq):
                return float(ro_fq)
        mm = self.measure_macro
        ro_fq = getattr(mm, "_drive_frequency", None)
        if isinstance(ro_fq, (int, float, np.floating)) and np.isfinite(ro_fq):
            return float(ro_fq)
        return float(self.attr.ro_fq)

    def _resolve_qubit_frequency(self, detune: float = 0.0) -> float:
        """Resolve qubit frequency with optional detuning (no side-effects).

        Parameters
        ----------
        detune : float
            Additive detuning in Hz (default 0).
        """
        return self.get_qubit_frequency() + detune

    def _serialize_bindings(self) -> dict[str, Any] | None:
        """Serialise current bindings state for provenance logging."""
        b = self._bindings_or_none
        if b is None:
            return None
        try:
            return sanitize_mapping_for_json({
                "qubit": str(b.qubit) if b.qubit else None,
                "readout": str(b.readout) if b.readout else None,
                "storage": str(b.storage) if b.storage else None,
            })
        except Exception:
            return None

    def burn_pulses(self, include_volatile: bool = True) -> None:
        """Push registered pulses into QM config via context."""
        ctx_burn = getattr(self._ctx, "burn_pulses", None)
        if callable(ctx_burn):
            ctx_burn(include_volatile=include_volatile)
        else:
            raise RuntimeError("Experiment context has no burn_pulses method.")

    def get_therm_clks(self, channel: str, *, fallback: int | None = None) -> int | None:
        """Resolve thermalization clocks via session runtime settings first."""
        getter = getattr(self._ctx, "get_therm_clks", None)
        if callable(getter):
            val = getter(channel, default=None)
            if val is not None:
                return int(val)

        legacy_attr = f"{channel}_therm_clks"
        legacy_val = getattr(self.attr, legacy_attr, None)
        if legacy_val is not None:
            warnings.warn(
                f"Using deprecated cqed_params fallback for '{legacy_attr}'. "
                "Prefer session runtime settings.",
                DeprecationWarning,
                stacklevel=3,
            )
            return int(legacy_val)

        return fallback

    def get_displacement_reference(self) -> dict[str, Any]:
        """Resolve displacement reference parameters from runtime settings first."""
        getter = getattr(self._ctx, "get_displacement_reference", None)
        if callable(getter):
            ref = getter()
            if isinstance(ref, dict):
                return ref

        out = {
            "coherent_amp": getattr(self.attr, "b_coherent_amp", None),
            "coherent_len": getattr(self.attr, "b_coherent_len", None),
            "b_alpha": getattr(self.attr, "b_alpha", None),
        }
        if any(v is not None for v in out.values()):
            warnings.warn(
                "Using deprecated cqed_params displacement reference fields. "
                "Prefer session runtime settings.",
                DeprecationWarning,
                stacklevel=3,
            )
        return out

    def run_program(
        self, prog, *, n_total: int, processors: list | None = None,
        process_in_sim: bool = False, **kw,
    ) -> RunResult:
        """Run a QUA program via the ProgramRunner (or legacy QuaProgramManager)."""
        # New path: SessionManager / ExperimentRunner expose a ProgramRunner
        runner = getattr(self._ctx, "runner", None)
        if runner is not None:
            return runner.run_program(
                prog, n_total=n_total,
                processors=processors or [pp.proc_default],
                process_in_sim=process_in_sim, **kw,
            )
        # Legacy path: QuaProgramManager has run_program directly
        return self.hw.run_program(
            prog, n_total=n_total,
            processors=processors or [pp.proc_default],
            process_in_sim=process_in_sim, **kw,
        )

    def save_output(self, output, tag: str = "") -> None:
        """Persist experiment output to disk."""
        orchestrator = getattr(self._ctx, "orchestrator", None)
        if orchestrator is not None:
            try:
                from ..calibration.contracts import Artifact
                from datetime import datetime

                data = dict(output) if hasattr(output, "items") else dict(output)
                artifact = Artifact(
                    name=tag or self.name,
                    data=data,
                    raw=None,
                    meta={"timestamp": datetime.now().isoformat(), "source": self.name},
                )
                orchestrator.persist_artifact(artifact)
                return
            except Exception:
                pass
        if hasattr(self._ctx, "save_output"):
            self._ctx.save_output(output, tag)

    # ------------------------------------------------------------------
    # Default protocol methods (override in subclasses)
    # ------------------------------------------------------------------
    def build_program(self, **params: Any) -> "ProgramBuildResult":
        """Build the QUA program without executing it.

        Calls the subclass ``_build_impl()`` to construct the program and
        resolve parameters, then applies the resolved frequencies to the
        hardware config so that both ``run()`` and ``simulate()`` see the
        correct IF values.

        Returns
        -------
        ProgramBuildResult
            Frozen snapshot with QUA program, processors, and provenance.
        """
        build = self._build_impl(**params)
        # Apply resolved frequencies to hardware so the QM config is
        # correct for both execution and simulation.
        for element, freq in build.resolved_frequencies.items():
            self.hw.set_element_fq(element, float(freq))
        return build

    def _build_impl(self, **params: Any) -> "ProgramBuildResult":
        """Subclass override point for ``build_program()``.

        Must return a ``ProgramBuildResult`` containing the QUA program and
        all resolved metadata.  Must **not** call ``run_program()`` or
        ``set_standard_frequencies()`` — frequency values go into
        ``resolved_frequencies``; the base class applies them.
        """
        raise NotImplementedError(
            f"{self.name}._build_impl() not implemented. "
            "Migrate the build portion of run() to _build_impl()."
        )

    def simulate(
        self,
        sim_config: Any = None,
        **params: Any,
    ) -> "SimulationResult":
        """Build the QUA program, then simulate it.

        Parameters
        ----------
        sim_config : QuboxSimulationConfig, optional
            Simulation parameters.  If ``None``, uses defaults
            (4000 ns, plot=True).
        **params
            Forwarded to ``build_program()``.  Must match the subclass
            ``_build_impl()`` signature (same kwargs as ``run()``).

        Returns
        -------
        SimulationResult
            Simulated waveform samples plus full provenance chain.
        """
        from ..hardware.program_runner import QuboxSimulationConfig
        from .result import SimulationResult

        if sim_config is None:
            sim_config = QuboxSimulationConfig()

        build = self.build_program(**params)

        runner = getattr(self._ctx, "runner", None)
        if runner is None:
            raise RuntimeError(
                "No ProgramRunner available.  Call session.open() first."
            )

        sim_samples = runner.simulate(
            build.program,
            duration=sim_config.duration_ns,
            plot=sim_config.plot,
            plot_params=sim_config.plot_params,
            controllers=sim_config.controllers,
            t_begin=sim_config.t_begin,
            t_end=sim_config.t_end,
            compiler_options=sim_config.compiler_options,
        )

        return SimulationResult(
            samples=sim_samples,
            build=build,
            config_snapshot=runner.config.build_qm_config(),
            sim_config=sim_config,
            duration_ns=sim_config.duration_ns,
        )

    def run(self, **params: Any) -> RunResult:
        raise NotImplementedError(
            f"{self.name}.run() not implemented"
        )

    def process(self, raw_output: Any, **params: Any) -> Any:
        """Post-process raw output. Default: return as-is."""
        return raw_output

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **params: Any) -> Any:
        """Analyze experiment results. Override in subclasses.

        Parameters
        ----------
        result : RunResult
            The raw experiment result from :meth:`run`.
        update_calibration : bool
            If ``True``, write derived parameters into the
            :pyattr:`calibration_store` (when available).

        Returns
        -------
        AnalysisResult
            A container with fitted parameters, metrics, and data.
        """
        raise NotImplementedError(
            f"{self.name}.analyze() not implemented"
        )

    def plot(self, analysis, *, ax=None, **kwargs: Any) -> Any:
        """Plot experiment results. Override in subclasses.

        Parameters
        ----------
        analysis : AnalysisResult
            The analysis result from :meth:`analyze`.
        ax : matplotlib.axes.Axes, optional
            If provided, draw into this axes instead of creating a new
            figure.  Useful for subplot layouts.

        Returns
        -------
        matplotlib.figure.Figure or None
        """
        raise NotImplementedError(
            f"{self.name}.plot() not implemented"
        )

    def guarded_calibration_commit(
        self,
        *,
        analysis,
        run_result: RunResult,
        calibration_tag: str,
        apply_update,
        require_fit: bool = True,
        min_r2: float | None = None,
        required_metrics: dict[str, tuple[float | None, float | None]] | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Two-phase calibration persistence: artifact first, then conditional commit.

        Phase A: always persist a timestamped run artifact with validation summary.
        Phase B: apply calibration update only if validation gates pass.
        """
        exp_path = Path(getattr(self._ctx, "experiment_path", "."))
        art_dir = exp_path / "artifacts" / "runtime" / "calibration_runs"
        art_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        artifact_path = art_dir / f"{calibration_tag}_{ts}.json"

        errors: list[str] = []
        fit = getattr(analysis, "fit", None)
        metrics = dict(getattr(analysis, "metrics", {}) or {})

        if require_fit:
            if fit is None:
                errors.append("No fit object available")
            elif not getattr(fit, "params", None):
                errors.append("Fit has no parameters")

        if min_r2 is not None:
            r2 = None if fit is None else getattr(fit, "r_squared", None)
            if r2 is None or not np.isfinite(r2) or r2 < float(min_r2):
                errors.append(f"Fit r_squared below threshold: {r2} < {min_r2}")

        if required_metrics:
            for key, (lo, hi) in required_metrics.items():
                val = metrics.get(key)
                if val is None or not np.isfinite(float(val)):
                    errors.append(f"Metric '{key}' missing or non-finite")
                    continue
                fval = float(val)
                if lo is not None and fval < lo:
                    errors.append(f"Metric '{key}' below minimum: {fval} < {lo}")
                if hi is not None and fval > hi:
                    errors.append(f"Metric '{key}' above maximum: {fval} > {hi}")

        payload = {
            "timestamp": ts,
            "experiment": self.name,
            "calibration_tag": calibration_tag,
            "validation_passed": len(errors) == 0,
            "validation_errors": errors,
            "fit": {
                "model": getattr(fit, "model_name", None) if fit else None,
                "params": getattr(fit, "params", None) if fit else None,
                "uncertainties": getattr(fit, "uncertainties", None) if fit else None,
                "r_squared": getattr(fit, "r_squared", None) if fit else None,
            },
            "metrics": metrics,
            "run_metadata": dict(getattr(run_result, "metadata", {}) or {}),
            "extra_metadata": extra_metadata or {},
        }
        payload_sanitized, dropped = sanitize_mapping_for_json(payload)
        if dropped:
            payload_sanitized["_persistence"] = {
                "raw_data_policy": "drop_shot_level_arrays",
                "dropped_fields": dropped,
            }
        with open(artifact_path, "w", encoding="utf-8") as f:
            json.dump(payload_sanitized, f, indent=2, default=str)

        if errors:
            _logger.warning(
                "Calibration commit skipped for %s. Artifact saved at %s. Errors: %s",
                calibration_tag, artifact_path, errors,
            )
            return False

        allow_inline = bool(getattr(self._ctx, "allow_inline_mutations", False))
        if allow_inline:
            apply_update()
            _logger.info(
                "Calibration commit applied for %s. Artifact saved at %s",
                calibration_tag, artifact_path,
            )
            return True

        _logger.info(
            "Inline calibration mutation suppressed for %s (strict mode). "
            "Artifact written at %s; orchestrator patch application required.",
            calibration_tag,
            artifact_path,
        )
        return False

    @property
    def calibration_store(self):
        """Access the CalibrationStore from the context, if available."""
        return getattr(self._ctx, "calibration", None)

    def get_confusion_matrix(self, element: str | None = None):
        """Return the readout confusion matrix, preferring bindings then CalibrationStore.

        Falls back to ``measureMacro._ro_quality_params`` if no other source
        provides a confusion matrix.

        Parameters
        ----------
        element : str or None
            Readout element.  Defaults to ``self.attr.ro_el``.

        Returns
        -------
        numpy.ndarray or None
        """
        import numpy as _np

        # 1. Try bindings (ReadoutBinding.quality)
        try:
            b = self.bindings
            cm = b.readout.quality.get("confusion_matrix")
            if cm is not None:
                return _np.asarray(cm)
        except (RuntimeError, AttributeError):
            pass

        # 2. Try CalibrationStore
        el = element or self.attr.ro_el
        cal = self.calibration_store
        if cal is not None:
            rq = cal.get_readout_quality(el)
            if rq is not None and rq.confusion_matrix is not None:
                return _np.asarray(rq.confusion_matrix)

        # 3. Fallback to measureMacro singleton
        return self.measure_macro._ro_quality_params.get("confusion_matrix")
