from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from ...analysis import run_named_pipeline
from ...calibration import CalibrationSnapshot
from ...data import ExecutionRequest, ExperimentResult
from .lowering import lower_to_legacy_circuit


@dataclass(frozen=True)
class LegacyExperimentAdapter:
    experiment_cls: type
    artifact_tag: str
    arg_builder: Callable[[Any, ExecutionRequest], dict[str, Any]]
    run_state_builder: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    measure_context_key: str | None = None


def _primary_axis(request: ExecutionRequest):
    sweep = request.sweep
    if sweep is None:
        return None
    if hasattr(sweep, "primary_axis"):
        return sweep.primary_axis()
    return None


def _resolve_numeric_axis(session, axis, *, default_parameter: str) -> np.ndarray:
    if axis is None:
        raise ValueError(f"{default_parameter} sweep is required.")
    values = np.asarray(axis.values, dtype=float)
    if axis.center is not None:
        center = session.resolve_center(axis.center)
        values = values + float(center)
    return values


def _require_uniform_step(values: np.ndarray, *, name: str) -> float:
    if values.size < 2:
        raise ValueError(f"{name} sweep requires at least two points.")
    diffs = np.diff(values)
    if not np.allclose(diffs, diffs[0]):
        raise ValueError(f"{name} sweep requires uniform spacing for the legacy adapter path.")
    return float(diffs[0])


def _build_qubit_spec_args(session, request: ExecutionRequest) -> dict[str, Any]:
    axis = request.params.get("freq") or _primary_axis(request)
    values = _resolve_numeric_axis(session, axis, default_parameter="freq")
    df = _require_uniform_step(values, name="freq")
    pulse = str(request.params.get("pulse", "x180"))
    qubit_target = session.resolve_alias(request.targets.get("qubit", "qubit"), role_hint="qubit")
    return {
        "pulse": pulse,
        "rf_begin": float(values[0]),
        "rf_end": float(values[-1] + df),
        "df": float(df),
        "qb_gain": float(request.params.get("drive_amp", request.params.get("qb_gain", 0.02))),
        "qb_len": int(request.params.get("qb_len") or session.resolve_pulse_length(qubit_target, pulse, default=16)),
        "n_avg": int(request.shots or request.params.get("n_avg", 200)),
        "transition": str(request.params.get("transition", "ge")),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


def _build_resonator_spec_args(session, request: ExecutionRequest) -> dict[str, Any]:
    axis = request.params.get("freq") or _primary_axis(request)
    values = _resolve_numeric_axis(session, axis, default_parameter="freq")
    df = _require_uniform_step(values, name="freq")
    return {
        "readout_op": str(request.params.get("readout_op", request.params.get("operation", "readout"))),
        "rf_begin": float(values[0]),
        "rf_end": float(values[-1] + df),
        "df": float(df),
        "n_avg": int(request.shots or request.params.get("n_avg", 200)),
        "ro_therm_clks": request.params.get("ro_therm_clks"),
    }


def _build_power_rabi_args(session, request: ExecutionRequest) -> dict[str, Any]:
    axis = request.params.get("amplitude") or _primary_axis(request)
    values = _resolve_numeric_axis(session, axis, default_parameter="amplitude")
    dg = _require_uniform_step(values, name="amplitude")
    op = str(request.params.get("pulse", request.params.get("op", "ge_ref_r180")))
    qubit_target = session.resolve_alias(request.targets.get("qubit", "qubit"), role_hint="qubit")
    return {
        "max_gain": float(values[-1]),
        "dg": float(dg),
        "op": op,
        "length": request.params.get("length")
        or session.resolve_pulse_length(qubit_target, op, default=None),
        "truncate_clks": request.params.get("truncate_clks"),
        "n_avg": int(request.shots or request.params.get("n_avg", 500)),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
        "use_circuit_runner": bool(request.params.get("use_circuit_runner", True)),
    }


def _build_ramsey_args(session, request: ExecutionRequest) -> dict[str, Any]:
    axis = request.params.get("delay") or _primary_axis(request)
    values = _resolve_numeric_axis(session, axis, default_parameter="delay")
    dt = _require_uniform_step(values, name="delay")
    detuning_hz = request.params.get("detuning")
    if detuning_hz is None and request.params.get("qb_detune_MHz") is not None:
        detuning_hz = float(request.params["qb_detune_MHz"]) * 1e6
    if detuning_hz is None:
        detuning_hz = 0.0
    return {
        "qb_detune": int(round(float(detuning_hz))),
        "delay_end": int(round(float(values[-1]))),
        "dt": int(round(float(dt))),
        "delay_begin": int(round(float(values[0]))),
        "r90": str(request.params.get("prep", request.params.get("r90", "x90"))),
        "n_avg": int(request.shots or request.params.get("n_avg", 500)),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
        "qb_detune_MHz": request.params.get("qb_detune_MHz"),
    }


def _build_active_reset_args(session, request: ExecutionRequest) -> dict[str, Any]:
    readout_target = session.resolve_alias(request.targets.get("readout", "readout"), role_hint="readout")
    threshold = request.params.get("threshold", "calibrated")
    if threshold == "calibrated":
        disc = session.resolve_discrimination(readout_target)
        threshold = float(disc.threshold) if disc is not None else 0.0
    return {
        "post_sel_policy": str(request.params.get("policy", "threshold")),
        "post_sel_kwargs": {"threshold": float(threshold)},
        "show_analysis": bool(request.params.get("show_analysis", True)),
        "MAX_PREP_TRIALS": int(request.params.get("max_attempts", 5)),
        "n_shots": int(request.shots or request.params.get("n_avg", 200)),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


_ADAPTERS: dict[str, LegacyExperimentAdapter] | None = None


def _load_adapters() -> dict[str, LegacyExperimentAdapter]:
    global _ADAPTERS
    if _ADAPTERS is None:
        from qubox_v2_legacy.experiments import (
            ActiveQubitResetBenchmark,
            PowerRabi,
            QubitSpectroscopy,
            ResonatorSpectroscopy,
            T2Ramsey,
        )

        _ADAPTERS = {
            "qubit.spectroscopy": LegacyExperimentAdapter(
                experiment_cls=QubitSpectroscopy,
                artifact_tag="qubitSpectroscopy",
                arg_builder=_build_qubit_spec_args,
            ),
            "resonator.spectroscopy": LegacyExperimentAdapter(
                experiment_cls=ResonatorSpectroscopy,
                artifact_tag="resonatorSpectroscopy",
                arg_builder=_build_resonator_spec_args,
                measure_context_key="readout_op",
            ),
            "qubit.power_rabi": LegacyExperimentAdapter(
                experiment_cls=PowerRabi,
                artifact_tag="powerRabi",
                arg_builder=_build_power_rabi_args,
                run_state_builder=lambda params: {"op": params["op"]},
            ),
            "qubit.ramsey": LegacyExperimentAdapter(
                experiment_cls=T2Ramsey,
                artifact_tag="T2Ramsey",
                arg_builder=_build_ramsey_args,
            ),
            "reset.active": LegacyExperimentAdapter(
                experiment_cls=ActiveQubitResetBenchmark,
                artifact_tag="activeResetBenchmark",
                arg_builder=_build_active_reset_args,
            ),
        }
    return _ADAPTERS


class QMRuntime:
    """Canonical QM runtime for the new `qubox` API."""

    circuit_runner_cls = None

    def __init__(self, session):
        self.session = session

    def run(self, request: ExecutionRequest) -> ExperimentResult:
        if request.kind == "custom":
            return self._run_custom(request)
        if request.kind == "template":
            return self._run_template(request)
        raise ValueError(f"Unsupported execution kind: {request.kind!r}")

    def build(self, request: ExecutionRequest) -> ExperimentResult:
        if request.kind == "custom":
            return self._run_custom(request, execute=False)
        if request.kind == "template":
            return self._run_template(request, execute=False)
        raise ValueError(f"Unsupported execution kind: {request.kind!r}")

    def _run_template(self, request: ExecutionRequest, *, execute: bool = True) -> ExperimentResult:
        adapter = _load_adapters()[request.template]
        legacy_params = adapter.arg_builder(self.session, request)
        experiment = adapter.experiment_cls(self.session.legacy_session)
        ctx = nullcontext()
        if adapter.measure_context_key is not None and hasattr(experiment, "_setup_measure_context"):
            ctx = experiment._setup_measure_context(legacy_params[adapter.measure_context_key])

        with ctx:
            build = experiment.build_program(**legacy_params)
            if adapter.run_state_builder is not None:
                experiment._run_params = adapter.run_state_builder(legacy_params)

            run_result = None
            artifact_path = None
            analysis = None
            if execute:
                run_result = experiment.run_program(
                    build.program,
                    n_total=build.n_total,
                    processors=list(build.processors),
                    **dict(build.run_program_kwargs),
                )
                artifact_path = str(experiment.save_output(run_result.output, adapter.artifact_tag))
                try:
                    analysis = experiment.analyze(run_result)
                except Exception:
                    analysis = None

        return ExperimentResult(
            request=request,
            build=build,
            run=run_result,
            analysis=analysis,
            calibration_snapshot=CalibrationSnapshot.from_session(self.session),
            artifact_path=artifact_path,
            compiler_report=dict(getattr(build, "metadata", {}) or {}),
            plotter=(lambda *args, **kwargs: experiment.plot(analysis, *args, **kwargs))
            if analysis is not None and hasattr(experiment, "plot")
            else None,
            source=experiment,
        )

    def _run_custom(self, request: ExecutionRequest, *, execute: bool = True) -> ExperimentResult:
        body = request.sequence or request.circuit
        if body is None:
            raise ValueError("Custom execution requires a Sequence or QuantumCircuit body.")

        legacy_circuit = lower_to_legacy_circuit(
            self.session,
            body=body,
            sweep=request.sweep,
            acquisition=request.acquisition,
        )
        n_shots = int(request.shots or getattr(request.sweep, "averaging", 1) or 1)
        if self.circuit_runner_cls is None:
            from qubox_v2_legacy.programs.circuit_runner import CircuitRunner

            self.circuit_runner_cls = CircuitRunner
        runner = self.circuit_runner_cls(self.session.legacy_session)
        build = runner.compile_v2(legacy_circuit, n_shots=n_shots)

        run_result = None
        artifact_path = None
        analysis = None
        if execute:
            for element, freq in dict(getattr(build, "resolved_frequencies", {}) or {}).items():
                self.session.legacy_session.hw.set_element_fq(element, float(freq))
            run_result = self.session.legacy_session.runner.run_program(
                build.program,
                n_total=build.n_total,
                processors=list(build.processors),
                **dict(build.run_program_kwargs),
            )
            artifact_path = str(self.session.legacy_session.save_output(run_result.output, request.template))
            analysis = run_named_pipeline(request.analysis, run_result=run_result, build=build)

        return ExperimentResult(
            request=request,
            build=build,
            run=run_result,
            analysis=analysis,
            calibration_snapshot=CalibrationSnapshot.from_session(self.session),
            artifact_path=artifact_path,
            compiler_report=dict(getattr(build, "metadata", {}) or {}),
            source=legacy_circuit,
        )
