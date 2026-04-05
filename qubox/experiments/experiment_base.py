"""qubox.experiments.experiment_base
=====================================
Base class for modular experiment types.

Each experiment class wraps one or more QUA program factories from
``qubox.programs`` and provides a consistent interface
for building, running, and post-processing results.

Experiment classes are lightweight — they hold a reference to the
experiment *context* (``cQED_Experiment`` or ``ExperimentRunner``) which
provides hardware control, pulse management, device access, and
calibration storage.

Usage::

    from qubox.experiments.spectroscopy import ResonatorSpectroscopy

    exp = cQED_Experiment(...)
    spec = ResonatorSpectroscopy(exp)
    result = spec.run(readout_op="readout", rf_begin=8.6e9, rf_end=8.62e9, df=50e3)
"""
from __future__ import annotations

import datetime
import json
import warnings
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import numpy as np

from ..programs import api as cQED_programs
from qubox_tools.algorithms import post_process as pp
from qubox_tools.data.containers import Output
from ..core.logging import get_logger
from ..core.persistence import sanitize_mapping_for_json
from ..hardware.program_runner import RunResult

if TYPE_CHECKING:
    from ..core.device_metadata import DeviceMetadata
    from ..core.protocols import SessionProtocol
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

    def __init__(self, ctx: SessionProtocol | Any) -> None:
        if ctx is None:
            raise ValueError(
                "Experiment context is not set. Pass a SessionManager or "
                "ExperimentRunner instance when creating an experiment."
            )
        self._ctx = ctx
        self._last_build = None
        self._resolved_param_trace: dict[str, dict[str, Any]] = {}

    @property
    def name(self) -> str:
        return type(self).__name__

    # ------------------------------------------------------------------
    # Context accessors (work with both legacy and new interfaces)
    # ------------------------------------------------------------------
    @property
    def attr(self) -> DeviceMetadata:
        snapshot = getattr(self._ctx, "context_snapshot", None)
        if callable(snapshot):
            return snapshot()
        a = getattr(self._ctx, "attributes", None)
        if a is None:
            raise RuntimeError(
                "Experiment context has no calibration-backed context snapshot."
            )
        return a

    @property
    def pulse_mgr(self) -> PulseOperationManager:
        pm = getattr(self._ctx, "pulse_mgr", None)
        if pm is None:
            raise RuntimeError(
                "Experiment context has no pulse manager. Check that "
                "SessionManager or ExperimentRunner initialised correctly."
            )
        return pm

    @property
    def hw(self):
        """Hardware controller (HardwareController)."""
        h = getattr(self._ctx, "hardware",
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
    def readout_handle(self):
        """Build a binding-backed ReadoutHandle for the current experiment context.

        Returns a frozen, immutable snapshot of the current readout
        configuration. Pass this to builder functions instead of
        letting them read from the singleton.
        """
        return self._build_readout_handle()

    @staticmethod
    def _normalize_readout_weight_sets(weights: Any) -> tuple[tuple[str, ...], ...] | None:
        if weights is None:
            return None
        iterable = weights if isinstance(weights, (list, tuple)) else [weights]
        normalized: list[tuple[str, ...]] = []
        for spec in iterable:
            if isinstance(spec, str):
                normalized.append((spec,))
                continue
            if isinstance(spec, (list, tuple)):
                values = tuple(str(item) for item in spec if item is not None)
                if values:
                    normalized.append(values)
        return tuple(normalized) or None

    @staticmethod
    def _weight_keys_from_sets(weight_sets: tuple[tuple[str, ...], ...] | None) -> tuple[str, ...]:
        if not weight_sets:
            return ("cos", "sin", "minus_sin")
        ordered: list[str] = []
        for spec in weight_sets[:2]:
            for item in spec:
                if item not in ordered:
                    ordered.append(item)
        return tuple(ordered or ("cos", "sin", "minus_sin"))

    def _build_readout_handle(
        self,
        *,
        element: str | None = None,
        operation: str | None = None,
        drive_frequency: float | None = None,
        weights: Any = None,
        weight_length: int | None = None,
        pulse_op: Any = None,
        gain: float | None = None,
    ):
        from ..core.bindings import ReadoutHandle

        resolved_element = element or getattr(self.attr, "ro_el", None) or "resonator"

        resolved_operation = operation
        if resolved_operation is None:
            bindings = self._bindings_or_none
            if bindings is not None and getattr(bindings.readout, "active_op", None):
                resolved_operation = bindings.readout.active_op
            else:
                resolved_operation = "readout"

        session_builder = getattr(self._ctx, "readout_handle", None)
        if callable(session_builder):
            base_handle = session_builder(alias=resolved_element, operation=resolved_operation)
        else:
            from ..core.bindings import ReadoutCal

            bindings = self.bindings
            rb = bindings.readout
            base_cal = ReadoutCal.from_readout_binding(rb)
            base_handle = ReadoutHandle(
                binding=rb,
                cal=base_cal,
                element=resolved_element,
                operation=resolved_operation,
                gain=rb.gain,
                demod_weight_sets=tuple(
                    tuple(spec) if isinstance(spec, (list, tuple)) else (str(spec),)
                    for spec in (rb.demod_weight_sets or ())
                ),
            )

        resolved_pulse = pulse_op or getattr(base_handle.binding, "pulse_op", None)
        if resolved_pulse is None or resolved_operation != getattr(base_handle, "operation", None):
            candidate = self.pulse_mgr.get_pulseOp_by_element_op(resolved_element, resolved_operation, strict=False)
            if candidate is not None:
                resolved_pulse = candidate

        weight_sets = self._normalize_readout_weight_sets(weights)
        if weight_sets is None:
            weight_sets = self._normalize_readout_weight_sets(base_handle.demod_weight_sets)
        if weight_sets is None:
            weight_sets = (("cos", "sin"), ("minus_sin", "cos"))

        resolved_drive_frequency = drive_frequency
        if resolved_drive_frequency is None:
            current_drive_frequency = getattr(base_handle.cal, "drive_frequency", None)
            if isinstance(current_drive_frequency, (int, float, np.floating)) and np.isfinite(current_drive_frequency):
                resolved_drive_frequency = float(current_drive_frequency)
            else:
                resolved_drive_frequency = self.get_readout_frequency()

        resolved_gain = gain if gain is not None else getattr(base_handle, "gain", None)
        bound_weights = [list(spec) if len(spec) > 1 else spec[0] for spec in weight_sets]
        binding = replace(
            base_handle.binding,
            pulse_op=resolved_pulse,
            active_op=resolved_operation,
            demod_weight_sets=bound_weights,
            drive_frequency=float(resolved_drive_frequency),
            gain=resolved_gain,
        )
        cal = replace(
            base_handle.cal,
            drive_frequency=float(resolved_drive_frequency),
            weight_keys=self._weight_keys_from_sets(weight_sets),
            weight_length=(
                weight_length
                or getattr(base_handle.cal, "weight_length", None)
                or getattr(resolved_pulse, "length", None)
            ),
        )

        return replace(
            base_handle,
            binding=binding,
            cal=cal,
            element=resolved_element,
            operation=resolved_operation,
            gain=resolved_gain,
            demod_weight_sets=weight_sets,
        )

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
    def _record_resolved_param(
        self,
        name: str,
        value: Any,
        *,
        source: str,
        calibration_path: str | None = None,
    ) -> Any:
        self._resolved_param_trace[name] = {
            "value": value,
            "source": source,
        }
        if calibration_path:
            self._resolved_param_trace[name]["calibration_path"] = calibration_path
        _logger.info("Resolved %s=%r (source=%s)", name, value, source)
        return value

    def _calibration_cqed_value(self, alias: str, field: str) -> Any:
        cal = getattr(self._ctx, "calibration", None)
        if cal is None:
            return None
        try:
            params = cal.get_cqed_params(alias)
        except Exception:
            return None
        return getattr(params, field, None) if params is not None else None

    def resolve_param(
        self,
        name: str,
        *,
        override: Any = None,
        calibration_value: Any = None,
        calibration_path: str | None = None,
        default: Any = None,
        has_default: bool = False,
        required: bool = True,
        owner: str | None = None,
        cast: Callable[[Any], Any] | None = None,
    ) -> Any:
        resolved = override
        source = None
        if resolved is not None:
            source = "override"
        elif calibration_value is not None:
            resolved = calibration_value
            source = "calibration"
        elif has_default:
            resolved = default
            source = "default"
        elif not required:
            return None
        else:
            where = f" in {calibration_path}" if calibration_path else ""
            raise ValueError(
                f"{owner or self.name}: missing required parameter '{name}'. "
                f"Provide '{name}=...' explicitly or add it to calibration{where}."
            )

        if cast is not None:
            try:
                resolved = cast(resolved)
            except Exception as exc:
                raise ValueError(
                    f"{owner or self.name}: invalid value for '{name}': {resolved!r}"
                ) from exc
        return self._record_resolved_param(
            name,
            resolved,
            source=source,
            calibration_path=calibration_path,
        )

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
        """Return active qubit frequency in Hz from calibration."""
        resolved = self.get_calibrated_frequency(self.attr.qb_el, field="qubit_freq", fallback=None)
        if resolved is None:
            raise ValueError(
                f"{self.name}: missing required calibration 'cqed_params.transmon.qubit_freq'. "
                "Provide an explicit qubit frequency or populate calibration.json."
            )
        return float(
            self._record_resolved_param(
                "qubit_freq",
                float(resolved),
                source="calibration",
                calibration_path="cqed_params.transmon.qubit_freq",
            )
        )

    def get_readout_frequency(self) -> float:
        """Return active readout frequency in Hz from calibration."""
        freq_entry = None
        cal = getattr(self._ctx, "calibration", None)
        if cal is not None:
            try:
                freq_entry = cal.get_frequencies(self.attr.ro_el)
            except Exception:
                freq_entry = None

        if freq_entry is not None:
            ro = getattr(freq_entry, "resonator_freq", None)
            if isinstance(ro, (int, float, np.floating)) and np.isfinite(ro):
                return float(
                    self._record_resolved_param(
                        "resonator_freq",
                        float(ro),
                        source="calibration",
                        calibration_path="cqed_params.resonator.resonator_freq",
                    )
                )

            if_val = getattr(freq_entry, "if_freq", None)
            if isinstance(if_val, (int, float, np.floating)) and np.isfinite(if_val):
                lo_val = getattr(freq_entry, "lo_freq", None)
                if not (isinstance(lo_val, (int, float, np.floating)) and np.isfinite(lo_val)):
                    try:
                        lo_val = self.get_readout_lo()
                    except Exception:
                        lo_val = None
                if isinstance(lo_val, (int, float, np.floating)) and np.isfinite(lo_val):
                    return float(
                        self._record_resolved_param(
                            "resonator_freq",
                            float(lo_val) + float(if_val),
                            source="calibration",
                            calibration_path="cqed_params.resonator.if_freq",
                        )
                    )

        raise ValueError(
            f"{self.name}: missing required calibration for readout frequency "
            f"at element '{self.attr.ro_el}'. Populate 'cqed_params.resonator.resonator_freq' "
            "or 'cqed_params.resonator.if_freq'+'lo_freq'."
        )

    def get_storage_frequency(self) -> float:
        """Return active storage frequency in Hz from calibration."""
        if not getattr(self.attr, "st_el", None):
            raise ValueError(f"{self.name}: no storage element is configured for this session.")
        for field, path in (
            ("storage_freq", "cqed_params.storage.storage_freq"),
            ("qubit_freq", "cqed_params.storage.qubit_freq"),
            ("rf_freq", "cqed_params.storage.rf_freq"),
        ):
            resolved = self.get_calibrated_frequency(self.attr.st_el, field=field, fallback=None)
            if resolved is not None:
                return float(
                    self._record_resolved_param(
                        "storage_freq",
                        float(resolved),
                        source="calibration",
                        calibration_path=path,
                    )
                )
        raise ValueError(
            f"{self.name}: missing required calibration for storage frequency "
            f"at element '{self.attr.st_el}'."
        )

    def set_standard_frequencies(self, *, qb_fq: float | None = None) -> None:
        """Set readout and qubit element frequencies to calibrated values.

        Resolution order for readout frequency:
          0. ``CalibrationStore`` resonator frequency (or IF+LO reconstruction)
          1. ``bindings.readout.drive_frequency`` (binding-driven path)
          2. ``attr.ro_fq`` (attributes fallback)
        """
        ro_fq = self.get_readout_frequency()
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
        """Resolve readout frequency with calibration precedence.

        Unlike ``set_standard_frequencies`` this method does **not** apply
        the frequency — it only returns the resolved value.
        """
        return self.get_readout_frequency()

    def _resolve_qubit_frequency(self, detune: float = 0.0) -> float:
        """Resolve qubit frequency with optional detuning (no side-effects).

        Parameters
        ----------
        detune : float
            Additive detuning in Hz (default 0).
        """
        return self.get_qubit_frequency() + detune

    def _resolve_storage_frequency(self) -> float:
        return self.get_storage_frequency()

    def _serialize_bindings(self) -> dict[str, Any] | None:
        """Serialise current bindings state for provenance logging."""
        b = self._bindings_or_none
        if b is None:
            return None
        try:
            payload, _ = sanitize_mapping_for_json({
                "qubit": str(b.qubit) if b.qubit else None,
                "readout": str(b.readout) if b.readout else None,
                "storage": str(b.storage) if b.storage else None,
            })
            return payload
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
        """Resolve thermalization clocks from calibration with optional default."""
        key_map = {
            "qb": ("qb_therm_clks", "transmon", "qb_therm_clks"),
            "qubit": ("qb_therm_clks", "transmon", "qb_therm_clks"),
            "ro": ("ro_therm_clks", "resonator", "ro_therm_clks"),
            "readout": ("ro_therm_clks", "resonator", "ro_therm_clks"),
            "st": ("st_therm_clks", "storage", "st_therm_clks"),
            "storage": ("st_therm_clks", "storage", "st_therm_clks"),
        }
        name, alias, field = key_map.get(
            str(channel).lower(),
            (f"{channel}_therm_clks", None, None),
        )
        calibration_value = None
        calibration_path = None
        if alias is not None:
            calibration_value = self._calibration_cqed_value(alias, field)
            calibration_path = f"cqed_params.{alias}.{field}"
        return self.resolve_param(
            name,
            calibration_value=calibration_value,
            calibration_path=calibration_path,
            default=fallback,
            has_default=fallback is not None,
            required=False,
            owner=self.name,
            cast=int,
        )

    def resolve_override_or_attr(
        self,
        *,
        value: Any,
        attr_name: str,
        owner: str,
        cast: Callable[[Any], Any] | None = None,
    ) -> Any:
        """Compatibility wrapper around calibration-backed parameter resolution."""
        mapping = {
            "qb_therm_clks": ("transmon", "qb_therm_clks"),
            "ro_therm_clks": ("resonator", "ro_therm_clks"),
            "st_therm_clks": ("storage", "st_therm_clks"),
        }
        alias, field = mapping.get(attr_name, (None, None))
        calibration_value = None
        calibration_path = None
        if alias is not None:
            calibration_value = self._calibration_cqed_value(alias, field)
            calibration_path = f"cqed_params.{alias}.{field}"
        return self.resolve_param(
            attr_name,
            override=value,
            calibration_value=calibration_value,
            calibration_path=calibration_path,
            owner=owner,
            cast=cast,
        )

    def get_displacement_reference(self) -> dict[str, Any]:
        """Resolve displacement reference parameters from runtime settings."""
        getter = getattr(self._ctx, "get_displacement_reference", None)
        if callable(getter):
            ref = getter()
            if isinstance(ref, dict):
                return ref

        return {
            "coherent_amp": getattr(self.attr, "b_coherent_amp", None),
            "coherent_len": getattr(self.attr, "b_coherent_len", None),
            "b_alpha": getattr(self.attr, "b_alpha", None),
        }

    def run_program(
        self, prog, *, n_total: int, processors: list | None = None,
        process_in_sim: bool = False, **kw,
    ) -> RunResult:
        """Run a QUA program via the ProgramRunner (or legacy QuaProgramManager)."""
        self._log_run_element_frequencies(n_total=n_total)
        # New path: SessionManager / ExperimentRunner expose a ProgramRunner
        runner = getattr(self._ctx, "runner", None)
        if runner is not None:
            result = runner.run_program(
                prog, n_total=n_total,
                processors=processors or [pp.proc_default],
                process_in_sim=process_in_sim, **kw,
            )
        else:
            # Legacy path: QuaProgramManager has run_program directly
            result = self.hw.run_program(
                prog, n_total=n_total,
                processors=processors or [pp.proc_default],
                process_in_sim=process_in_sim, **kw,
            )

        build = getattr(self, "_last_build", None)
        if build is not None:
            metadata = dict(getattr(result, "metadata", {}) or {})
            metadata.setdefault("resolved_parameters", dict(build.resolved_parameter_sources or {}))
            metadata.setdefault("resolved_frequencies", dict(build.resolved_frequencies or {}))
            result.metadata = metadata
        return result

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
        self._resolved_param_trace = {}
        build = self._build_impl(**params)
        if not getattr(build, "resolved_parameter_sources", None) and self._resolved_param_trace:
            build = replace(
                build,
                resolved_parameter_sources=dict(self._resolved_param_trace),
            )
        # Apply resolved frequencies to hardware so the QM config is
        # correct for both execution and simulation.
        for element, freq in build.resolved_frequencies.items():
            self.hw.set_element_fq(element, float(freq))

        # Capture calibration snapshot for reproducibility if not already set.
        if build.calibration_snapshot is None:
            try:
                from ..calibration.models import CalibrationSnapshot
                cal = getattr(self._ctx, "calibration", None)
                if cal is not None and hasattr(cal, "to_dict"):
                    snapshot = CalibrationSnapshot(
                        source_path=str(getattr(cal, "path", "<in-memory>")),
                        data=dict(cal.to_dict()),
                        version=str(cal.to_dict().get("version", "")),
                    )
                    build = replace(build, calibration_snapshot=snapshot)
            except Exception:
                pass  # Don't fail the build if snapshot capture fails

        self._last_build = build
        return build

    def _elements_for_run_logging(self) -> list[str]:
        """Infer elements associated with the next run for frequency logging."""
        elements: set[str] = set()

        build = getattr(self, "_last_build", None)
        if build is not None:
            resolved = getattr(build, "resolved_frequencies", {}) or {}
            if isinstance(resolved, dict):
                for name in resolved.keys():
                    if isinstance(name, str) and name:
                        elements.add(name)

        hw_elements = set((getattr(self.hw, "elements", {}) or {}).keys())
        for field in ("ro_el", "qb_el", "st_el"):
            try:
                name = getattr(self.attr, field, None)
            except Exception:
                name = None
            if isinstance(name, str) and name in hw_elements:
                elements.add(name)

        return sorted(elements)

    def _log_run_element_frequencies(self, *, n_total: int) -> None:
        """Emit per-element frequency trace prior to execution.

        Logged at DEBUG level with LO / IF and reconstructed RF frequency.
        """
        elements = self._elements_for_run_logging()
        if not elements:
            _logger.debug("RUN_FREQ experiment=%s n_total=%s elements=[]", self.name, n_total)
            return

        _logger.debug("RUN_FREQ experiment=%s n_total=%s elements=%s", self.name, n_total, elements)
        for element in elements:
            lo_hz = None
            if_hz = None
            rf_hz = None
            try:
                lo_hz = float(self.hw.get_element_lo(element))
            except Exception:
                lo_hz = None
            try:
                if_hz = float(self.hw.get_element_if(element))
            except Exception:
                if_hz = None
            if lo_hz is not None and if_hz is not None:
                rf_hz = lo_hz + if_hz

            _logger.debug(
                "RUN_FREQ element=%s lo_hz=%s if_hz=%s rf_hz=%s",
                element,
                lo_hz,
                if_hz,
                rf_hz,
            )

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

        # 3. Fallback to the explicit readout snapshot before consulting compat state.
        try:
            cm = getattr(self.readout_handle.cal, "confusion_matrix", None)
            if cm is not None:
                return _np.asarray(cm)
        except Exception:
            pass
        return None
