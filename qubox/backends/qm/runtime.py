from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from qubox_tools.algorithms.pipelines import run_named_pipeline
from ...calibration import CalibrationSnapshot
from ...data import ExecutionRequest, ExperimentResult, RunManifest
from .lowering import lower_to_legacy_circuit


def _qubox_version() -> str:
    """Return the qubox package version, falling back gracefully."""
    try:
        from qubox import __version__
        return str(__version__)
    except Exception:
        return ""


@dataclass(frozen=True)
class TemplateExperimentAdapter:
    experiment_cls: type
    artifact_tag: str
    arg_builder: Callable[[Any, ExecutionRequest], dict[str, Any]]
    run_state_builder: Callable[[dict[str, Any]], dict[str, Any]] | None = None


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


# ---------------------------------------------------------------------------
# New arg builders for standard experiments (16 additional adapters)
# ---------------------------------------------------------------------------

# ── readout ──

def _build_readout_trace_args(session, request: ExecutionRequest) -> dict[str, Any]:
    return {
        "drive_frequency": float(request.params.get("drive_frequency", 0.0)),
        "ro_therm_clks": int(request.params.get("ro_therm_clks", 10000)),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
    }


def _build_iq_blobs_args(session, request: ExecutionRequest) -> dict[str, Any]:
    return {
        "r180": str(request.params.get("r180", request.params.get("pulse", "x180"))),
        "n_runs": int(request.shots or request.params.get("n_runs", 1000)),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


def _build_butterfly_args(session, request: ExecutionRequest) -> dict[str, Any]:
    readout_target = session.resolve_alias(request.targets.get("readout", "readout"), role_hint="readout")
    threshold = request.params.get("threshold", "calibrated")
    if threshold == "calibrated":
        disc = session.resolve_discrimination(readout_target)
        threshold = float(disc.threshold) if disc is not None else 0.0
    return {
        "prep_policy": str(request.params.get("prep_policy", request.params.get("policy", "threshold"))),
        "prep_kwargs": request.params.get("prep_kwargs", {"threshold": float(threshold)}),
        "k": request.params.get("k"),
        "r180": str(request.params.get("r180", "x180")),
        "update_readout_config": bool(request.params.get("update_readout_config", False)),
        "show_analysis": bool(request.params.get("show_analysis", False)),
        "n_samples": int(request.shots or request.params.get("n_samples", 10_000)),
        "M0_MAX_TRIALS": int(request.params.get("max_trials", 16)),
    }


# ── resonator ──

def _build_resonator_power_spec_args(session, request: ExecutionRequest) -> dict[str, Any]:
    axis = request.params.get("freq") or _primary_axis(request)
    values = _resolve_numeric_axis(session, axis, default_parameter="freq")
    df = _require_uniform_step(values, name="freq")
    return {
        "readout_op": str(request.params.get("readout_op", request.params.get("operation", "readout"))),
        "rf_begin": float(values[0]),
        "rf_end": float(values[-1] + df),
        "df": float(df),
        "g_min": float(request.params.get("gain_min", request.params.get("g_min", 1e-3))),
        "g_max": float(request.params.get("gain_max", request.params.get("g_max", 0.5))),
        "N_a": int(request.params.get("n_gain_points", request.params.get("N_a", 50))),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "ro_therm_clks": request.params.get("ro_therm_clks"),
    }


# ── qubit (time domain) ──

def _build_temporal_rabi_args(session, request: ExecutionRequest) -> dict[str, Any]:
    axis = request.params.get("duration") or _primary_axis(request)
    values = _resolve_numeric_axis(session, axis, default_parameter="duration")
    dt = _require_uniform_step(values, name="duration")
    return {
        "pulse": str(request.params.get("pulse", "x180")),
        "pulse_len_begin": int(round(float(values[0]))),
        "pulse_len_end": int(round(float(values[-1]))),
        "dt": int(round(float(dt))),
        "pulse_gain": float(request.params.get("pulse_gain", 1.0)),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


def _build_time_rabi_chevron_args(session, request: ExecutionRequest) -> dict[str, Any]:
    return {
        "if_span": float(request.params["freq_span"]),
        "df": float(request.params["df"]),
        "max_pulse_duration": int(request.params["max_duration"]),
        "dt": int(request.params.get("dt", 4)),
        "pulse": str(request.params.get("pulse", "x180")),
        "pulse_gain": float(request.params.get("pulse_gain", 1.0)),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


def _build_power_rabi_chevron_args(session, request: ExecutionRequest) -> dict[str, Any]:
    return {
        "if_span": float(request.params["freq_span"]),
        "df": float(request.params["df"]),
        "max_gain": float(request.params["max_gain"]),
        "dg": float(request.params.get("dg", 0.01)),
        "pulse": str(request.params.get("pulse", "x180")),
        "pulse_duration": int(request.params.get("pulse_duration", 100)),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


def _build_t1_args(session, request: ExecutionRequest) -> dict[str, Any]:
    axis = request.params.get("delay") or _primary_axis(request)
    values = _resolve_numeric_axis(session, axis, default_parameter="delay")
    dt = _require_uniform_step(values, name="delay")
    return {
        "delay_end": int(round(float(values[-1]))),
        "dt": int(round(float(dt))),
        "delay_begin": int(round(float(values[0]))),
        "r180": str(request.params.get("r180", request.params.get("pulse", "x180"))),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "use_circuit_runner": bool(request.params.get("use_circuit_runner", True)),
    }


def _build_echo_args(session, request: ExecutionRequest) -> dict[str, Any]:
    axis = request.params.get("delay") or _primary_axis(request)
    values = _resolve_numeric_axis(session, axis, default_parameter="delay")
    dt = _require_uniform_step(values, name="delay")
    return {
        "delay_end": int(round(float(values[-1]))),
        "dt": int(round(float(dt))),
        "delay_begin": int(round(float(values[0]))),
        "r180": str(request.params.get("r180", "x180")),
        "r90": str(request.params.get("r90", "x90")),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


# ── calibration ──

def _build_all_xy_args(session, request: ExecutionRequest) -> dict[str, Any]:
    return {
        "gate_indices": request.params.get("gate_indices"),
        "prefix": str(request.params.get("prefix", "")),
        "qb_detuning": int(request.params.get("qb_detuning", 0)),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


def _build_drag_args(session, request: ExecutionRequest) -> dict[str, Any]:
    amps = request.params.get("amps")
    if amps is None:
        axis = _primary_axis(request)
        if axis is not None:
            amps = np.asarray(axis.values, dtype=float)
    if amps is None:
        raise ValueError("DRAG calibration requires 'amps' parameter.")
    return {
        "amps": np.asarray(amps, dtype=float),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "base_alpha": float(request.params.get("base_alpha", 1.0)),
        "calibration_op": str(request.params.get("calibration_op", "ge_ref_r180")),
        "x180": str(request.params.get("x180", "ge_x180")),
        "x90": str(request.params.get("x90", "ge_x90")),
        "y180": str(request.params.get("y180", "ge_y180")),
        "y90": str(request.params.get("y90", "ge_y90")),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


# ── tomography ──

def _build_qubit_tomo_args(session, request: ExecutionRequest) -> dict[str, Any]:
    state_prep = request.params.get("state_prep")
    if state_prep is None:
        raise ValueError("Qubit state tomography requires 'state_prep' parameter.")
    return {
        "state_prep": state_prep,
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "x90_pulse": str(request.params.get("x90_pulse", "x90")),
        "yn90_pulse": str(request.params.get("yn90_pulse", "yn90")),
        "therm_clks": request.params.get("therm_clks", request.params.get("qb_therm_clks")),
    }


def _build_wigner_args(session, request: ExecutionRequest) -> dict[str, Any]:
    gates = request.params.get("gates", request.params.get("state_prep"))
    if gates is None:
        raise ValueError("Wigner tomography requires 'state_prep' parameter.")
    if hasattr(gates, "play") or callable(gates):
        gates = [gates]
    else:
        gates = list(gates)
    x_vals = request.params.get("x_vals")
    p_vals = request.params.get("p_vals")
    if x_vals is None or p_vals is None:
        raise ValueError("Wigner tomography requires 'x_vals' and 'p_vals' parameters.")
    return {
        "gates": gates,
        "x_vals": np.asarray(x_vals, dtype=float),
        "p_vals": np.asarray(p_vals, dtype=float),
        "base_alpha": float(request.params.get("base_alpha", 10.0)),
        "r90_pulse": str(request.params.get("r90_pulse", "x90")),
        "n_avg": int(request.shots or request.params.get("n_avg", 200)),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


# ── storage / cavity ──

def _build_storage_spec_args(session, request: ExecutionRequest) -> dict[str, Any]:
    axis = request.params.get("freq") or _primary_axis(request)
    values = _resolve_numeric_axis(session, axis, default_parameter="freq")
    df = _require_uniform_step(values, name="freq")
    return {
        "disp": str(request.params["disp"]),
        "rf_begin": float(values[0]),
        "rf_end": float(values[-1] + df),
        "df": float(df),
        "storage_therm_time": int(request.params["storage_therm_time"]),
        "sel_r180": str(request.params.get("sel_r180", "sel_x180")),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
    }


def _build_storage_t1_args(session, request: ExecutionRequest) -> dict[str, Any]:
    axis = request.params.get("delay") or _primary_axis(request)
    values = _resolve_numeric_axis(session, axis, default_parameter="delay")
    dt = _require_uniform_step(values, name="delay")
    return {
        "fock_fqs": request.params.get("fock_fqs"),
        "fock_disps": request.params.get("fock_disps"),
        "delay_end": int(round(float(values[-1]))),
        "dt": int(round(float(dt))),
        "delay_begin": int(round(float(values[0]))),
        "sel_r180": str(request.params.get("sel_r180", "sel_x180")),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "st_therm_clks": request.params.get("st_therm_clks", request.params.get("storage_therm_clks")),
    }


def _build_num_splitting_args(session, request: ExecutionRequest) -> dict[str, Any]:
    rf_centers = request.params.get("rf_centers")
    rf_spans = request.params.get("rf_spans")
    if rf_centers is None or rf_spans is None:
        raise ValueError("Number splitting spectroscopy requires 'rf_centers' and 'rf_spans' parameters.")
    return {
        "rf_centers": list(rf_centers),
        "rf_spans": list(rf_spans),
        "df": float(request.params.get("df", 50e3)),
        "sel_r180": str(request.params.get("sel_r180", "sel_x180")),
        "state_prep": request.params.get("state_prep"),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "st_therm_clks": request.params.get("st_therm_clks", request.params.get("storage_therm_clks")),
    }


# ---------------------------------------------------------------------------
# Arg builders for newly registered adapters
# ---------------------------------------------------------------------------

def _build_qubit_spec_ef_args(session, request: ExecutionRequest) -> dict[str, Any]:
    axis = request.params.get("freq") or _primary_axis(request)
    values = _resolve_numeric_axis(session, axis, default_parameter="freq")
    df = _require_uniform_step(values, name="freq")
    qubit_target = session.resolve_alias(request.targets.get("qubit", "qubit"), role_hint="qubit")
    pulse = str(request.params.get("pulse", "x180"))
    return {
        "pulse": pulse,
        "rf_begin": float(values[0]),
        "rf_end": float(values[-1] + df),
        "df": float(df),
        "qb_gain": float(request.params.get("drive_amp", request.params.get("qb_gain", 0.02))),
        "qb_len": int(request.params.get("qb_len") or session.resolve_pulse_length(qubit_target, pulse, default=16)),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "ge_prep_pulse": str(request.params.get("ge_prep_pulse", "ge_x180")),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


def _build_resonator_spec_x180_args(session, request: ExecutionRequest) -> dict[str, Any]:
    axis = request.params.get("freq") or _primary_axis(request)
    values = _resolve_numeric_axis(session, axis, default_parameter="freq")
    df = _require_uniform_step(values, name="freq")
    return {
        "rf_begin": float(values[0]),
        "rf_end": float(values[-1] + df),
        "df": float(df),
        "r180": str(request.params.get("r180", "x180")),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "ro_therm_clks": request.params.get("ro_therm_clks"),
    }


def _build_sequential_rotations_args(session, request: ExecutionRequest) -> dict[str, Any]:
    return {
        "rotations": list(request.params.get("rotations") or ["x180"]),
        "apply_avg": bool(request.params.get("apply_avg", False)),
        "n_shots": int(request.shots or request.params.get("n_shots", 1000)),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


def _build_ramsey_chevron_args(session, request: ExecutionRequest) -> dict[str, Any]:
    return {
        "if_span": float(request.params["freq_span"]),
        "df": float(request.params["df"]),
        "max_delay_duration": int(request.params["max_delay"]),
        "dt": int(request.params.get("dt", 4)),
        "r90": str(request.params.get("r90", "x90")),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


def _build_readout_ge_raw_trace_args(session, request: ExecutionRequest) -> dict[str, Any]:
    return {
        "ro_freq": float(request.params.get("ro_freq", 0.0)),
        "r180": str(request.params.get("r180", "x180")),
        "ro_depl_clks": int(request.params.get("ro_depl_clks", 10000)),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


def _build_qubit_reset_benchmark_args(session, request: ExecutionRequest) -> dict[str, Any]:
    return {
        "bit_size": int(request.params.get("bit_size", 1000)),
        "num_shots": int(request.shots or request.params.get("num_shots", 20_000)),
        "r180": str(request.params.get("r180", "x180")),
        "random_seed": request.params.get("random_seed"),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


def _build_readout_leakage_args(session, request: ExecutionRequest) -> dict[str, Any]:
    return {
        "control_bits": list(request.params.get("control_bits", [0, 1])),
        "r180": str(request.params.get("r180", "x180")),
        "num_sequences": int(request.params.get("num_sequences", 10)),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "qb_therm_clks": request.params.get("qb_therm_clks"),
    }


def _build_storage_ramsey_args(session, request: ExecutionRequest) -> dict[str, Any]:
    axis = request.params.get("delay") or _primary_axis(request)
    values = _resolve_numeric_axis(session, axis, default_parameter="delay")
    return {
        "delay_ticks": np.asarray(values, dtype=int),
        "st_detune": int(request.params.get("st_detune", 0)),
        "disp_pulse": str(request.params.get("disp_pulse", "const_alpha")),
        "sel_r180": str(request.params.get("sel_r180", "sel_x180")),
        "n_avg": int(request.shots or request.params.get("n_avg", 200)),
        "st_therm_clks": request.params.get("st_therm_clks", request.params.get("storage_therm_clks")),
    }


def _build_fock_spectroscopy_args(session, request: ExecutionRequest) -> dict[str, Any]:
    probe_fqs = request.params.get("probe_fqs")
    if probe_fqs is None:
        raise ValueError("Fock-resolved spectroscopy requires 'probe_fqs' parameter.")
    return {
        "probe_fqs": list(probe_fqs),
        "state_prep": request.params.get("state_prep"),
        "sel_r180": str(request.params.get("sel_r180", "sel_x180")),
        "n_avg": int(request.shots or request.params.get("n_avg", 100)),
        "st_therm_clks": request.params.get("st_therm_clks", request.params.get("storage_therm_clks")),
        "allow_default_state_prep": bool(request.params.get("allow_default_state_prep", True)),
    }


def _build_fock_ramsey_args(session, request: ExecutionRequest) -> dict[str, Any]:
    axis = request.params.get("delay") or _primary_axis(request)
    if axis is not None:
        values = _resolve_numeric_axis(session, axis, default_parameter="delay")
        dt = _require_uniform_step(values, name="delay")
        delay_begin = int(round(float(values[0])))
        delay_end = int(round(float(values[-1])))
    else:
        delay_begin = int(request.params.get("delay_begin", 4))
        delay_end = int(request.params.get("delay_end", 40000))
        dt = int(request.params.get("dt", 100))
    return {
        "fock_fqs": request.params.get("fock_fqs"),
        "detunings": request.params.get("detunings"),
        "disps": request.params.get("disps"),
        "delay_end": delay_end,
        "dt": dt,
        "delay_begin": delay_begin,
        "sel_r90": str(request.params.get("sel_r90", "sel_x90")),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "st_therm_clks": request.params.get("st_therm_clks", request.params.get("storage_therm_clks")),
    }


def _build_fock_power_rabi_args(session, request: ExecutionRequest) -> dict[str, Any]:
    return {
        "fock_fqs": request.params.get("fock_fqs"),
        "gains": request.params.get("gains"),
        "sel_qb_pulse": str(request.params.get("sel_qb_pulse", "sel_x180")),
        "disp_n_list": request.params.get("disp_n_list"),
        "n_avg": int(request.shots or request.params.get("n_avg", 1000)),
        "st_therm_clks": request.params.get("st_therm_clks", request.params.get("storage_therm_clks")),
    }


_ADAPTERS: dict[str, TemplateExperimentAdapter] | None = None


def _load_adapters() -> dict[str, TemplateExperimentAdapter]:
    global _ADAPTERS
    if _ADAPTERS is None:
        from qubox.experiments import (
            ActiveQubitResetBenchmark,
            AllXY,
            DRAGCalibration,
            FockResolvedPowerRabi,
            FockResolvedRamsey,
            FockResolvedSpectroscopy,
            FockResolvedT1,
            IQBlob,
            NumSplittingSpectroscopy,
            PowerRabi,
            PowerRabiChevron,
            QubitResetBenchmark,
            QubitSpectroscopy,
            QubitSpectroscopyEF,
            QubitStateTomography,
            RamseyChevron,
            ReadoutButterflyMeasurement,
            ReadoutGERawTrace,
            ReadoutLeakageBenchmarking,
            ReadoutTrace,
            ResonatorPowerSpectroscopy,
            ResonatorSpectroscopy,
            ResonatorSpectroscopyX180,
            SequentialQubitRotations,
            StorageRamsey,
            StorageSpectroscopy,
            StorageWignerTomography,
            T1Relaxation,
            T2Echo,
            T2Ramsey,
            TemporalRabi,
            TimeRabiChevron,
        )

        _ADAPTERS = {
            # ── spectroscopy (existing) ──
            "qubit.spectroscopy": TemplateExperimentAdapter(
                experiment_cls=QubitSpectroscopy,
                artifact_tag="qubitSpectroscopy",
                arg_builder=_build_qubit_spec_args,
            ),
            "resonator.spectroscopy": TemplateExperimentAdapter(
                experiment_cls=ResonatorSpectroscopy,
                artifact_tag="resonatorSpectroscopy",
                arg_builder=_build_resonator_spec_args,
            ),
            # ── qubit time domain (existing + new) ──
            "qubit.power_rabi": TemplateExperimentAdapter(
                experiment_cls=PowerRabi,
                artifact_tag="powerRabi",
                arg_builder=_build_power_rabi_args,
                run_state_builder=lambda params: {"op": params["op"]},
            ),
            "qubit.ramsey": TemplateExperimentAdapter(
                experiment_cls=T2Ramsey,
                artifact_tag="T2Ramsey",
                arg_builder=_build_ramsey_args,
            ),
            "qubit.temporal_rabi": TemplateExperimentAdapter(
                experiment_cls=TemporalRabi,
                artifact_tag="temporalRabi",
                arg_builder=_build_temporal_rabi_args,
            ),
            "qubit.time_rabi_chevron": TemplateExperimentAdapter(
                experiment_cls=TimeRabiChevron,
                artifact_tag="timeRabiChevron",
                arg_builder=_build_time_rabi_chevron_args,
            ),
            "qubit.power_rabi_chevron": TemplateExperimentAdapter(
                experiment_cls=PowerRabiChevron,
                artifact_tag="powerRabiChevron",
                arg_builder=_build_power_rabi_chevron_args,
            ),
            "qubit.t1": TemplateExperimentAdapter(
                experiment_cls=T1Relaxation,
                artifact_tag="T1Relaxation",
                arg_builder=_build_t1_args,
            ),
            "qubit.echo": TemplateExperimentAdapter(
                experiment_cls=T2Echo,
                artifact_tag="T2Echo",
                arg_builder=_build_echo_args,
            ),
            # ── resonator (new) ──
            "resonator.power_spectroscopy": TemplateExperimentAdapter(
                experiment_cls=ResonatorPowerSpectroscopy,
                artifact_tag="resonatorPowerSpectroscopy",
                arg_builder=_build_resonator_power_spec_args,
            ),
            # ── readout (new) ──
            "readout.trace": TemplateExperimentAdapter(
                experiment_cls=ReadoutTrace,
                artifact_tag="readoutTrace",
                arg_builder=_build_readout_trace_args,
            ),
            "readout.iq_blobs": TemplateExperimentAdapter(
                experiment_cls=IQBlob,
                artifact_tag="iqBlobs",
                arg_builder=_build_iq_blobs_args,
            ),
            "readout.butterfly": TemplateExperimentAdapter(
                experiment_cls=ReadoutButterflyMeasurement,
                artifact_tag="butterflyMeasurement",
                arg_builder=_build_butterfly_args,
            ),
            # ── calibration (new) ──
            "calibration.all_xy": TemplateExperimentAdapter(
                experiment_cls=AllXY,
                artifact_tag="allXY",
                arg_builder=_build_all_xy_args,
            ),
            "calibration.drag": TemplateExperimentAdapter(
                experiment_cls=DRAGCalibration,
                artifact_tag="dragCalibration",
                arg_builder=_build_drag_args,
            ),
            # ── tomography (new) ──
            "tomography.qubit_state": TemplateExperimentAdapter(
                experiment_cls=QubitStateTomography,
                artifact_tag="qubitStateTomography",
                arg_builder=_build_qubit_tomo_args,
            ),
            "tomography.wigner": TemplateExperimentAdapter(
                experiment_cls=StorageWignerTomography,
                artifact_tag="wignerTomography",
                arg_builder=_build_wigner_args,
            ),
            # ── storage / cavity (new) ──
            "storage.spectroscopy": TemplateExperimentAdapter(
                experiment_cls=StorageSpectroscopy,
                artifact_tag="storageSpectroscopy",
                arg_builder=_build_storage_spec_args,
            ),
            "storage.t1_decay": TemplateExperimentAdapter(
                experiment_cls=FockResolvedT1,
                artifact_tag="storageT1Decay",
                arg_builder=_build_storage_t1_args,
            ),
            "storage.num_splitting": TemplateExperimentAdapter(
                experiment_cls=NumSplittingSpectroscopy,
                artifact_tag="numSplittingSpectroscopy",
                arg_builder=_build_num_splitting_args,
            ),
            # ── reset (existing) ──
            "reset.active": TemplateExperimentAdapter(
                experiment_cls=ActiveQubitResetBenchmark,
                artifact_tag="activeResetBenchmark",
                arg_builder=_build_active_reset_args,
            ),
            # ── newly registered: spectroscopy ──
            "qubit.spectroscopy_ef": TemplateExperimentAdapter(
                experiment_cls=QubitSpectroscopyEF,
                artifact_tag="qubitSpectroscopyEF",
                arg_builder=_build_qubit_spec_ef_args,
            ),
            "resonator.spectroscopy_x180": TemplateExperimentAdapter(
                experiment_cls=ResonatorSpectroscopyX180,
                artifact_tag="resonatorSpectroscopyX180",
                arg_builder=_build_resonator_spec_x180_args,
            ),
            # ── newly registered: time domain ──
            "qubit.sequential_rotations": TemplateExperimentAdapter(
                experiment_cls=SequentialQubitRotations,
                artifact_tag="sequentialRotations",
                arg_builder=_build_sequential_rotations_args,
            ),
            "qubit.ramsey_chevron": TemplateExperimentAdapter(
                experiment_cls=RamseyChevron,
                artifact_tag="ramseyChevron",
                arg_builder=_build_ramsey_chevron_args,
            ),
            # ── newly registered: readout ──
            "readout.ge_raw_trace": TemplateExperimentAdapter(
                experiment_cls=ReadoutGERawTrace,
                artifact_tag="readoutGERawTrace",
                arg_builder=_build_readout_ge_raw_trace_args,
            ),
            # ── newly registered: reset & benchmarking ──
            "reset.passive_benchmark": TemplateExperimentAdapter(
                experiment_cls=QubitResetBenchmark,
                artifact_tag="qubitResetBenchmark",
                arg_builder=_build_qubit_reset_benchmark_args,
            ),
            "readout.leakage_benchmark": TemplateExperimentAdapter(
                experiment_cls=ReadoutLeakageBenchmarking,
                artifact_tag="readoutLeakageBenchmark",
                arg_builder=_build_readout_leakage_args,
            ),
            # ── newly registered: storage / cavity ──
            "storage.ramsey": TemplateExperimentAdapter(
                experiment_cls=StorageRamsey,
                artifact_tag="storageRamsey",
                arg_builder=_build_storage_ramsey_args,
            ),
            "storage.fock_spectroscopy": TemplateExperimentAdapter(
                experiment_cls=FockResolvedSpectroscopy,
                artifact_tag="fockResolvedSpectroscopy",
                arg_builder=_build_fock_spectroscopy_args,
            ),
            "storage.fock_ramsey": TemplateExperimentAdapter(
                experiment_cls=FockResolvedRamsey,
                artifact_tag="fockResolvedRamsey",
                arg_builder=_build_fock_ramsey_args,
            ),
            "storage.fock_power_rabi": TemplateExperimentAdapter(
                experiment_cls=FockResolvedPowerRabi,
                artifact_tag="fockResolvedPowerRabi",
                arg_builder=_build_fock_power_rabi_args,
            ),
        }
    return _ADAPTERS


class QMRuntime:
    """Canonical QM runtime for the new `qubox` API."""

    _circuit_compiler_cls = None

    def __init__(self, session):
        self.session = session

    def _build_manifest(
        self,
        request: ExecutionRequest,
        cal_snapshot: CalibrationSnapshot | None,
    ) -> RunManifest:
        """Construct a RunManifest capturing full provenance for this run."""
        import subprocess

        git_sha: str | None = None
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0:
                git_sha = result.stdout.strip()[:12]
        except Exception:
            pass

        hw_hash = ""
        try:
            cfg = self.session.config_engine.build_qm_config()
            import hashlib, json
            canonical = json.dumps(cfg, sort_keys=True, separators=(",", ":"))
            hw_hash = hashlib.sha256(canonical.encode()).hexdigest()[:12]
        except Exception:
            pass

        return RunManifest(
            execution_request=request,
            calibration_snapshot=cal_snapshot,
            hardware_config_hash=hw_hash,
            qubox_version=_qubox_version(),
            git_sha=git_sha,
        )

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
        experiment = adapter.experiment_cls(self.session.session_manager)
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

        cal_snap = CalibrationSnapshot.from_session(self.session)
        return ExperimentResult(
            request=request,
            build=build,
            run=run_result,
            analysis=analysis,
            calibration_snapshot=cal_snap,
            manifest=self._build_manifest(request, cal_snap),
            artifact_path=artifact_path,
            compiler_report=dict(getattr(build, "metadata", {}) or {}),
            plotter=(lambda *args, **kwargs: experiment.plot(analysis, *args, **kwargs))
            if analysis is not None and hasattr(experiment, "plot")
            else None,
            source=experiment,
        )

    def _run_custom(self, request: ExecutionRequest, *, execute: bool = True) -> ExperimentResult:
        body = request.control_program or request.sequence or request.circuit
        if body is None:
            raise ValueError("Custom execution requires a Sequence, QuantumCircuit, or ControlProgram body.")

        legacy_circuit = lower_to_legacy_circuit(
            self.session,
            body=body,
            sweep=request.sweep,
            acquisition=request.acquisition,
        )
        control_averaging = getattr(getattr(request.control_program, "sweep_plan", None), "averaging", 1)
        n_shots = int(request.shots or getattr(request.sweep, "averaging", control_averaging) or 1)
        if self._circuit_compiler_cls is None:
            from qubox.programs.circuit_compiler import CircuitCompiler

            self._circuit_compiler_cls = CircuitCompiler
        compiler = self._circuit_compiler_cls(self.session.session_manager)
        build = compiler.compile(legacy_circuit, n_shots=n_shots)

        run_result = None
        artifact_path = None
        analysis = None
        if execute:
            for element, freq in dict(getattr(build, "resolved_frequencies", {}) or {}).items():
                self.session.session_manager.hardware.set_element_fq(element, float(freq))
            run_result = self.session.session_manager.runner.run_program(
                build.program,
                n_total=build.n_total,
                processors=list(build.processors),
                **dict(build.run_program_kwargs),
            )
            artifact_path = str(self.session.session_manager.save_output(run_result.output, request.template))
            analysis = run_named_pipeline(request.analysis, run_result=run_result, build=build)

        cal_snap = CalibrationSnapshot.from_session(self.session)
        return ExperimentResult(
            request=request,
            build=build,
            run=run_result,
            analysis=analysis,
            calibration_snapshot=cal_snap,
            manifest=self._build_manifest(request, cal_snap),
            artifact_path=artifact_path,
            compiler_report=dict(getattr(build, "metadata", {}) or {}),
            source=legacy_circuit,
        )
