from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import hashlib
import json
import math
import os
import time
import traceback
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np

from qualang_tools.units import unit

from qubox.experiments.session import SessionManager
from qubox.experiments import (
    ReadoutTrace,
    ReadoutWeightsOptimization,
    ReadoutGEDiscrimination,
    ReadoutButterflyMeasurement,
    QubitSpectroscopy,
    PowerRabi,
    FockResolvedPowerRabi,
    StorageSpectroscopy,
)
from qubox.core.measurement_config import MeasurementConfig


REFERENCE_SEED = {
    "ro_el": "resonator",
    "qb_el": "qubit",
    "st_el": "storage",
    "ro_fq": 8596222556.078796,
    "qb_fq": 6150369694.524461,
    "st_fq": 5240932800.0,
    "ro_kappa": 4156000.0,
    "ro_chi": -913148.5,
    "anharmonicity": -255669694.5244608,
    "st_chi": -2840421.354241756,
    "st_chi2": -21912.638362342423,
    "st_chi3": -327.37857577643325,
    "st_K": -28844,
    "st_K2": 1406,
    "ro_therm_clks": 1000,
    "qb_therm_clks": 19625,
    "st_therm_clks": 200000.0,
    "qb_T1_relax": 9812.873848245112,
    "qb_T2_ramsey": 6324.73112712837,
    "qb_T2_echo": 8381,
    "r180_amp": 0.08565235748770193,
    "rlen": 16,
    "rsigma": 2.6666666666666665,
    "b_coherent_amp": 0.01958,
    "b_coherent_len": 48,
    "b_alpha": 1,
    "fock_fqs": [
        6150355624.798682,
        6147515785.728024,
        6144636052.64372,
        6141702748.091518,
        6138726201.173695,
        6135701129.575048,
        6132618869.060916,
        6129486767.621506,
    ],
}

RULES = {
    "skip_resonator_spectroscopy": True,
    "full_readout_pipeline": True,
    "include_mixer_cal_best_effort": True,
    "pulse_len_unselective_ns": 16,
    "pulse_len_selective_us": 1.0,
    "pulse_len_displacement_ns": 48,
    "fidelity_threshold": 90.0,
    "repeatability_tolerance_fraction": 0.15,
    "fit_quality_min_r2": 0.75,
    "mixer_retry_count": 1,
}

LEGACY_REFERENCES = {
    "arbitrary_rotation": r"C:\Users\dazzl\Box\Shyam Shankar Quantum Circuits Group\Users\Users_JianJun\JJL_Experiments\post_cavity_calibrations.ipynb",
    "legacy_start_ranges": "post_cavity_experiment_legacy.ipynb",
}

HARDWARE_STAGE_ORDER = ["A", "B1", "B2", "B3", "C", "D", "E", "F", "G"]

_MIXER_UNSTABLE_TOKENS = ("unstable", "ao2", "ao4", "stall", "stalled", "timeout")
_MIXER_UNREACHABLE_TOKENS = (
    "unreachable",
    "not found",
    "failed to connect",
    "connection",
    "refused",
    "device",
    "sa124",
    "spectrum",
)


class HardStopError(RuntimeError):
    pass


@dataclass
class StageOutcome:
    stage: str
    ok: bool
    decision: str
    reason: str = ""
    runtime_s: float | None = None
    metrics: dict[str, Any] | None = None
    warnings: list[str] | None = None


class ArtifactWriter:
    def __init__(self, root: Path):
        self.root = root
        self.journal = root / "autotune_journal.md"
        self.patchset = root / "autotune_patchset.json"
        self.summary = root / "autotune_summary.md"
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self._bootstrap_patchset()

    def _bootstrap_patchset(self) -> None:
        baseline = {
            "version": "autotune-v1.1",
            "started_at": self.started_at,
            "baseline_seed": REFERENCE_SEED,
            "legacy_references": LEGACY_REFERENCES,
            "rules": RULES,
            "applied": [],
            "previewed": [],
            "skipped": [],
            "rolled_back": [],
            "notes": [],
        }
        if self.patchset.exists():
            try:
                current = json.loads(self.patchset.read_text(encoding="utf-8"))
            except Exception:
                current = {}
            for key, value in baseline.items():
                current.setdefault(key, value)
            payload = current
        else:
            payload = baseline
        self.patchset.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _json_safe(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {str(k): self._json_safe(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._json_safe(v) for v in obj]
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        return obj

    def append_journal(self, entry: dict[str, Any]) -> None:
        ts = datetime.now().isoformat(timespec="seconds")
        lines = [
            f"\n## {ts} — {entry.get('stage', 'unknown')} / {entry.get('experiment', 'unknown')}",
            f"- purpose: {entry.get('purpose', '')}",
            f"- code_path: {entry.get('code_path', '')}",
            f"- snapshot_hash: {entry.get('snapshot_hash', '')}",
            f"- element_aliases: {self._json_safe(entry.get('element_aliases', {}))}",
            f"- inputs: {self._json_safe(entry.get('inputs', {}))}",
            f"- sweep: {self._json_safe(entry.get('sweep', {}))}",
            f"- runtime_s: {entry.get('runtime_s', None)}",
            f"- artifacts: {self._json_safe(entry.get('artifacts', {}))}",
            f"- output_keys: {self._json_safe(entry.get('output_keys', []))}",
            f"- fit_model: {entry.get('fit_model', '')}",
            f"- fit_params: {self._json_safe(entry.get('fit_params', {}))}",
            f"- fit_uncertainties: {self._json_safe(entry.get('fit_uncertainties', {}))}",
            f"- fit_metrics: {self._json_safe(entry.get('fit_metrics', {}))}",
            f"- checks: {self._json_safe(entry.get('checks', {}))}",
            f"- decision: {entry.get('decision', '')}",
            f"- decision_reason: {entry.get('decision_reason', '')}",
            f"- patch_diff: {self._json_safe(entry.get('patch_diff', {}))}",
            f"- rollback: {self._json_safe(entry.get('rollback', {}))}",
            f"- warnings: {self._json_safe(entry.get('warnings', []))}",
            f"- errors: {self._json_safe(entry.get('errors', []))}",
        ]
        with self.journal.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    def append_patch(self, decision: str, payload: dict[str, Any]) -> None:
        data = json.loads(self.patchset.read_text(encoding="utf-8"))
        key = {
            "patch_applied": "applied",
            "patch_preview": "previewed",
            "patch_skipped": "skipped",
            "rollback": "rolled_back",
        }.get(decision, "notes")
        if key == "notes":
            data.setdefault("notes", []).append(str(payload))
        else:
            data.setdefault(key, []).append(self._json_safe(payload))
        self.patchset.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def write_summary(self, outcomes: dict[str, Any], hard_stop: str | None = None) -> None:
        passed = sum(1 for _, v in outcomes.items() if isinstance(v, dict) and v.get("ok"))
        total = len(outcomes)
        lines = [
            "# autotune_summary",
            "",
            f"Run started: {self.started_at}",
            f"Updated: {datetime.now().isoformat(timespec='seconds')}",
            "",
            "## Policy",
            "- Non-interactive execution: enabled",
            "- Phase order: dry-run/build-only then hardware-run",
            f"- Skip resonator spectroscopy: {RULES['skip_resonator_spectroscopy']}",
            f"- Full readout pipeline required: {RULES['full_readout_pipeline']}",
            f"- SA mixer calibration best effort: {RULES['include_mixer_cal_best_effort']}",
            "",
            "## Legacy references",
            f"- {LEGACY_REFERENCES['arbitrary_rotation']}",
            f"- {LEGACY_REFERENCES['legacy_start_ranges']}",
            "",
            "## Stage outcomes",
        ]
        for stage, payload in outcomes.items():
            lines.append(f"- {stage}: {payload}")
        lines.extend([
            "",
            "## Completion",
            f"- Passed stages: {passed}/{total}",
            f"- Hard stop: {hard_stop or 'none'}",
            f"- Journal: {self.journal}",
            f"- Patchset: {self.patchset}",
            f"- Summary: {self.summary}",
        ])
        self.summary.write_text("\n".join(lines), encoding="utf-8")


def _snapshot_hash(attr: Any) -> str:
    payload = {}
    for key in sorted(REFERENCE_SEED.keys()):
        payload[key] = getattr(attr, key, REFERENCE_SEED.get(key)) if attr is not None else REFERENCE_SEED.get(key)
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _extract_output(output: Any) -> dict[str, Any]:
    if output is None:
        return {}
    if isinstance(output, dict):
        return output
    try:
        return dict(output)
    except Exception:
        return {}


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    try:
        arr = np.asarray(value)
        return arr.size > 0
    except Exception:
        try:
            return len(value) > 0
        except Exception:
            return False


def _health_check(output_map: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "non_empty": False,
        "finite": True,
        "saturation": False,
        "keys": sorted(list(output_map.keys())),
    }
    if not output_map:
        checks["finite"] = False
        return checks

    populated = []
    for key, value in output_map.items():
        if not _is_non_empty(value):
            continue
        populated.append(key)
        try:
            arr = np.asarray(value)
            if np.issubdtype(arr.dtype, np.number):
                if np.any(~np.isfinite(arr)):
                    checks["finite"] = False
                if key.lower().startswith("adc") and np.any(np.abs(arr) > 0.499):
                    checks["saturation"] = True
        except Exception:
            continue

    checks["non_empty"] = len(populated) > 0
    checks["populated_keys"] = populated
    checks["pass"] = bool(checks["non_empty"] and checks["finite"] and not checks["saturation"])
    return checks


def _metric_from_analysis(analysis: Any, candidates: list[str]) -> float | None:
    if analysis is None:
        return None
    metrics = getattr(analysis, "metrics", {}) or {}
    for key in candidates:
        if key in metrics and metrics[key] is not None:
            try:
                return float(np.asarray(metrics[key]).reshape(-1)[0])
            except Exception:
                continue
    return None


def _fit_quality_check(analysis: Any) -> dict[str, Any]:
    fit = getattr(analysis, "fit", None)
    if fit is None:
        return {"has_fit": False, "pass": True, "reason": "no_fit_object"}

    r2 = getattr(fit, "r_squared", None)
    params = getattr(fit, "params", {}) or {}
    has_params = bool(params)

    if r2 is None:
        return {"has_fit": True, "r_squared": None, "has_params": has_params, "pass": has_params, "reason": "missing_r2"}

    try:
        r2f = float(r2)
    except Exception:
        return {"has_fit": True, "r_squared": r2, "has_params": has_params, "pass": False, "reason": "invalid_r2"}

    ok = bool(np.isfinite(r2f) and has_params and r2f >= RULES["fit_quality_min_r2"])
    return {
        "has_fit": True,
        "r_squared": r2f,
        "has_params": has_params,
        "threshold": RULES["fit_quality_min_r2"],
        "pass": ok,
        "reason": "ok" if ok else "below_threshold_or_missing_params",
    }


def _seed_session_state(attr: Any) -> dict[str, Any]:
    seeded: dict[str, Any] = {}
    for key, value in REFERENCE_SEED.items():
        current = getattr(attr, key, None)
        if current is None:
            setattr(attr, key, value)
            seeded[key] = value

    fixed_updates = {
        "rlen": int(RULES["pulse_len_unselective_ns"]),
        "b_coherent_len": int(RULES["pulse_len_displacement_ns"]),
    }
    for key, value in fixed_updates.items():
        if getattr(attr, key, None) != value:
            setattr(attr, key, value)
            seeded[key] = value

    if getattr(attr, "fock_fqs", None) is None:
        setattr(attr, "fock_fqs", list(REFERENCE_SEED["fock_fqs"]))
        seeded["fock_fqs"] = list(REFERENCE_SEED["fock_fqs"])

    return seeded


def _assert_safe_bounds(stage: str, run_kwargs: dict[str, Any]) -> None:
    amp_keys = ["max_gain", "qb_gain", "gain"]
    for key in amp_keys:
        if key in run_kwargs:
            val = float(run_kwargs[key])
            if abs(val) > 0.5:
                raise HardStopError(f"{stage}: safety bound violation for {key}={val}")

    freq_keys = ["drive_frequency", "rf_begin", "rf_end", "fock_fq", "fock_fqs", "probe_fqs"]
    for key in freq_keys:
        if key not in run_kwargs:
            continue
        val = run_kwargs[key]
        values = val if isinstance(val, (list, tuple, np.ndarray)) else [val]
        for item in values:
            fv = float(item)
            if fv < 1e9 or fv > 12e9:
                raise HardStopError(f"{stage}: safety bound violation for {key}={fv}")


def _stage_measure_context(session: SessionManager, attr: Any, stage_name: str):
    if stage_name != "A":
        return nullcontext()

    ro_el = getattr(attr, "ro_el", REFERENCE_SEED["ro_el"])
    ro_info = session.pulse_mgr.get_pulseOp_by_element_op(ro_el, "readout", strict=False)
    if ro_info is None:
        raise HardStopError(
            f"{stage_name}: no readout PulseOp found for element={ro_el!r}; required for IO sanity stage"
        )
    weight_len = int(ro_info.length) if ro_info.length is not None else None
    apply_config = getattr(session, "_apply_measurement_config", None)
    current_config = getattr(session, "current_measurement_config", None)
    if not callable(apply_config) or not callable(current_config):
        return nullcontext()

    base_config = current_config()
    staged_config = replace(
        base_config if isinstance(base_config, MeasurementConfig) else MeasurementConfig(),
        element=ro_el,
        operation="readout",
        drive_frequency=float(getattr(attr, "ro_fq", REFERENCE_SEED["ro_fq"])),
        weight_sets=(("cos", "sin"), ("minus_sin", "cos")),
        weight_length=weight_len,
        source="autotune_stage_context",
    )

    @contextmanager
    def _configured_readout():
        apply_config(staged_config)
        try:
            yield
        finally:
            apply_config(base_config)

    return _configured_readout()


def _run_build_only(exp: Any, run_kwargs: dict[str, Any]) -> dict[str, Any]:
    build = exp.build_program(**run_kwargs)
    return {
        "build_ok": True,
        "experiment_name": getattr(build, "experiment_name", type(exp).__name__),
        "builder": getattr(build, "builder_function", "unknown"),
        "n_total": getattr(build, "n_total", None),
        "params": getattr(build, "params", {}),
    }


def _run_once(exp: Any, run_kwargs: dict[str, Any], analyze_kwargs: dict[str, Any]) -> tuple[Any, Any, dict[str, Any], float]:
    t0 = time.perf_counter()
    result = exp.run(**run_kwargs)
    analysis = exp.analyze(result, **analyze_kwargs)
    dt = time.perf_counter() - t0
    output_map = _extract_output(getattr(result, "output", {}))
    checks = _health_check(output_map)
    return result, analysis, checks, dt


def _run_with_retry(
    stage: str,
    exp_factory: Callable[[], Any],
    run_kwargs: dict[str, Any],
    analyze_kwargs: dict[str, Any],
) -> tuple[Any, Any, dict[str, Any], float, dict[str, Any]]:
    diagnostics = {"attempts": []}

    for attempt in (1, 2):
        exp = exp_factory()
        kw = dict(run_kwargs)
        if attempt == 2 and "n_avg" in kw:
            kw["n_avg"] = max(100, int(kw["n_avg"] // 2))
        if attempt == 2 and "n_samples" in kw:
            kw["n_samples"] = max(1000, int(kw["n_samples"] // 2))

        result, analysis, checks, runtime_s = _run_once(exp, kw, analyze_kwargs)
        diagnostics["attempts"].append({
            "attempt": attempt,
            "run_kwargs": kw,
            "checks": checks,
            "runtime_s": runtime_s,
        })

        if checks["pass"]:
            return result, analysis, checks, runtime_s, diagnostics

        if attempt == 2 and checks.get("saturation"):
            raise HardStopError(f"{stage}: persistent ADC saturation/clipping after mitigation attempt")
        if attempt == 2 and (not checks.get("non_empty") or not checks.get("finite")):
            raise HardStopError(f"{stage}: repeated missing/invalid streams after rebuild+retry")

    raise HardStopError(f"{stage}: unreachable retry state")


def _repeatability_check(
    stage: str,
    exp_factory: Callable[[], Any],
    run_kwargs: dict[str, Any],
    analyze_kwargs: dict[str, Any],
    metric_keys: list[str],
) -> dict[str, Any]:
    values = []
    for _ in range(2):
        exp = exp_factory()
        _, analysis, checks, runtime_s = _run_once(exp, run_kwargs, analyze_kwargs)
        val = _metric_from_analysis(analysis, metric_keys)
        values.append({"metric": val, "checks": checks, "runtime_s": runtime_s})

    m1 = values[0]["metric"]
    m2 = values[1]["metric"]
    if m1 is None or m2 is None:
        return {"pass": False, "reason": "missing repeatability metric", "values": values}

    denom = max(abs(m1), abs(m2), 1e-12)
    frac = abs(m1 - m2) / denom
    ok = frac <= RULES["repeatability_tolerance_fraction"]
    return {"pass": ok, "fractional_diff": frac, "values": values}


def _apply_attr_patch(attr: Any, updates: dict[str, Any]) -> dict[str, Any]:
    before = {k: getattr(attr, k, None) for k in updates}
    for key, value in updates.items():
        setattr(attr, key, value)
    return before


def _restore_attr_patch(attr: Any, before: dict[str, Any]) -> None:
    for key, value in before.items():
        setattr(attr, key, value)


def _open_session_with_retry(session: SessionManager, writer: ArtifactWriter) -> None:
    errs = []
    for attempt in (1, 2):
        try:
            session.open()
            return
        except Exception as exc:
            errs.append(str(exc))
            writer.append_journal(
                {
                    "stage": "PHASE2",
                    "experiment": "SessionOpen",
                    "purpose": "Open hardware connection",
                    "code_path": "SessionManager.open",
                    "decision": "retry" if attempt == 1 else "hard_stop",
                    "warnings": [str(exc)],
                }
            )
            time.sleep(1.0)
    raise HardStopError(
        "Hardware connection failure (OPX/Octave/SA unreachable) after one retry: " + " | ".join(errs)
    )


def _ensure_session_open(session: SessionManager, writer: ArtifactWriter) -> None:
    if not bool(getattr(session, "_opened", False)):
        _open_session_with_retry(session, writer)


def _maybe_run_mixer_calibration(session: SessionManager, attr: Any) -> dict[str, Any]:
    hw = getattr(session, "hw", None)
    if hw is None or not hasattr(hw, "calibrate_element"):
        return {
            "attempted_any": False,
            "status": "not_available",
            "warnings": ["Hardware controller calibrate_element API is not available"],
            "best_so_far": {},
        }

    elements = [
        getattr(attr, "qb_el", REFERENCE_SEED["qb_el"]),
        getattr(attr, "ro_el", REFERENCE_SEED["ro_el"]),
    ]

    outcomes: list[dict[str, Any]] = []
    warnings: list[str] = []
    best_so_far: dict[str, Any] = {}

    for el in elements:
        el_out = {"element": el, "attempted": True, "status": "completed", "retries": 0, "unstable": False}
        for attempt in range(RULES["mixer_retry_count"] + 1):
            try:
                el_out["retries"] = attempt
                hw.calibrate_element(
                    el=el,
                    method="manual_minimizer",
                    sa_device_name="sa124b",
                    save_to_db=True,
                )
                best_so_far[el] = {"status": "completed", "attempt": attempt}
                break
            except Exception as exc:
                msg = str(exc)
                low = msg.lower()
                warnings.append(f"{el}/attempt{attempt + 1}: {msg}")

                if any(tok in low for tok in _MIXER_UNSTABLE_TOKENS):
                    el_out["status"] = "degraded_unstable"
                    el_out["unstable"] = True
                    best_so_far.setdefault(el, {})
                    best_so_far[el]["status"] = "kept_best_so_far"
                    best_so_far[el]["reason"] = "AO2/AO4 unstable or stalled"
                    break

                if any(tok in low for tok in _MIXER_UNREACHABLE_TOKENS):
                    if attempt < RULES["mixer_retry_count"]:
                        time.sleep(1.0)
                        continue
                    raise HardStopError(
                        f"Hardware connection failure (OPX/Octave/SA unreachable) in Stage C after one retry: {el}: {msg}"
                    ) from exc

                el_out["status"] = "degraded_error"
                break

        outcomes.append(el_out)

    return {
        "attempted_any": True,
        "status": "completed_with_best_effort",
        "elements": outcomes,
        "warnings": warnings,
        "best_so_far": best_so_far,
    }


def _stage_specs(attr: Any, u: Any) -> list[dict[str, Any]]:
    qb_fq = float(getattr(attr, "qb_fq", REFERENCE_SEED["qb_fq"]))
    ro_fq = float(getattr(attr, "ro_fq", REFERENCE_SEED["ro_fq"]))
    st_fq = float(getattr(attr, "st_fq", REFERENCE_SEED["st_fq"]))

    return [
        {
            "stage": "A",
            "experiment": ReadoutTrace,
            "name": "ReadoutTrace",
            "run_kwargs": {
                "drive_frequency": ro_fq,
                "ro_therm_clks": int(getattr(attr, "ro_therm_clks", REFERENCE_SEED["ro_therm_clks"])),
                "n_avg": 2000,
            },
            "analyze_kwargs": {"update_calibration": False},
            "required": True,
            "metric_keys": ["trace_length"],
            "patch_kind": "none",
        },
        {
            "stage": "B1",
            "experiment": ReadoutWeightsOptimization,
            "name": "ReadoutWeightsOptimization",
            "run_kwargs": {
                "ro_op": "readout",
                "drive_frequency": ro_fq,
                "cos_w_key": "cos",
                "sin_w_key": "sin",
                "m_sin_w_key": "minus_sin",
                "r180": "x180",
                "n_avg": 10000,
                "persist": False,
                "set_active_readout": True,
                "make_plots": False,
                "revert_on_no_improvement": True,
            },
            "analyze_kwargs": {"update_calibration": False},
            "required": True,
            "metric_keys": ["ge_diff_norm_max"],
            "patch_kind": "preview",
        },
        {
            "stage": "B2",
            "experiment": ReadoutGEDiscrimination,
            "name": "ReadoutGEDiscrimination",
            "run_kwargs": {
                "measure_op": "readout",
                "drive_frequency": ro_fq,
                "r180": "x180",
                "update_readout_config": True,
                "apply_rotated_weights": True,
                "persist": False,
                "n_samples": 6000,
            },
            "analyze_kwargs": {"update_calibration": False},
            "required": True,
            "metric_keys": ["fidelity"],
            "patch_kind": "discrimination",
        },
        {
            "stage": "B3",
            "experiment": ReadoutButterflyMeasurement,
            "name": "ReadoutButterflyMeasurement",
            "run_kwargs": {
                "prep_policy": "THRESHOLD",
                "prep_kwargs": {"threshold": 0.0},
                "n_samples": 3000,
                "update_readout_config": True,
            },
            "analyze_kwargs": {"update_calibration": False},
            "required": True,
            "metric_keys": ["F", "fidelity"],
            "patch_kind": "quality",
        },
        {
            "stage": "D",
            "experiment": QubitSpectroscopy,
            "name": "QubitSpectroscopy",
            "run_kwargs": {
                "pulse": "saturation",
                "rf_begin": qb_fq - 1.5 * u.MHz,
                "rf_end": qb_fq + 1.5 * u.MHz,
                "df": 0.1 * u.MHz,
                "qb_gain": 0.2,
                "qb_len": 1000,
                "n_avg": 300,
            },
            "analyze_kwargs": {"update_calibration": False},
            "required": False,
            "metric_keys": ["f0"],
            "patch_kind": "qb_freq",
        },
        {
            "stage": "E",
            "experiment": PowerRabi,
            "name": "PowerRabi",
            "run_kwargs": {
                "max_gain": 0.2,
                "dg": 0.01,
                "op": "ge_ref_r180",
                "length": int(RULES["pulse_len_unselective_ns"]),
                "n_avg": 400,
            },
            "analyze_kwargs": {"update_calibration": False},
            "required": False,
            "metric_keys": ["g_pi", "pi_amp", "A_pi"],
            "patch_kind": "r180",
        },
        {
            "stage": "F",
            "experiment": FockResolvedPowerRabi,
            "name": "FockResolvedPowerRabi",
            "run_kwargs": {
                "fock_fqs": list(REFERENCE_SEED["fock_fqs"]),
                "gains": np.linspace(0.02, 0.25, 12),
                "sel_qb_pulse": "sel_x180",
                "disp_n_list": [f"disp_n{i}" for i in range(len(REFERENCE_SEED["fock_fqs"]))],
                "n_avg": 200,
            },
            "analyze_kwargs": {"update_calibration": False},
            "required": False,
            "metric_keys": ["g_pi_fock_0"],
            "patch_kind": "selective_pi",
        },
        {
            "stage": "G",
            "experiment": StorageSpectroscopy,
            "name": "StorageSpectroscopy",
            "run_kwargs": {
                "disp": "const_alpha",
                "rf_begin": st_fq - 10 * u.MHz,
                "rf_end": st_fq + 10 * u.MHz,
                "df": 0.2 * u.MHz,
                "storage_therm_time": int(getattr(attr, "st_therm_clks", REFERENCE_SEED["st_therm_clks"])),
                "n_avg": 40,
            },
            "analyze_kwargs": {"update_calibration": False},
            "required": False,
            "metric_keys": ["f_storage"],
            "patch_kind": "displacement",
        },
    ]


def _apply_stage_patch(
    session: SessionManager,
    attr: Any,
    stage: dict[str, Any],
    analysis: Any,
    writer: ArtifactWriter,
    exp_factory: Callable[[], Any],
) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    patch_kind = stage.get("patch_kind", "none")
    stage_name = stage["stage"]
    metrics = getattr(analysis, "metrics", {}) or {}

    if patch_kind in ("none", "preview"):
        return "patch_preview" if patch_kind == "preview" else "patch_skipped", "No direct patch target", {}, {}

    if patch_kind == "discrimination":
        fidelity = float(metrics.get("fidelity", np.nan)) if metrics.get("fidelity") is not None else None
        if fidelity is None or not np.isfinite(fidelity):
            return "patch_skipped", "Missing discrimination fidelity", {}, {}
        if fidelity < RULES["fidelity_threshold"]:
            return "patch_skipped", f"Fidelity below threshold: {fidelity:.2f}", {}, {}

        repeat = _repeatability_check(stage_name, exp_factory, stage["run_kwargs"], stage["analyze_kwargs"], ["fidelity"])
        if not repeat.get("pass"):
            return "patch_skipped", f"Repeatability failed: {repeat}", {}, {"repeatability": repeat}

        required = ["threshold", "angle", "sigma_g", "sigma_e"]
        if any(metrics.get(k) is None for k in required):
            return "patch_preview", "Discrimination metrics missing fields for calibration write", {}, {"metrics": metrics}

        ro_el = getattr(attr, "ro_el", REFERENCE_SEED["ro_el"])
        mu_g = metrics.get("mu_g")
        mu_e = metrics.get("mu_e")
        if not (isinstance(mu_g, (list, tuple)) and isinstance(mu_e, (list, tuple)) and len(mu_g) == 2 and len(mu_e) == 2):
            return "patch_preview", "Missing centroid vectors for discrimination patch", {}, {"metrics": metrics}

        before = session.calibration.get_discrimination(ro_el)
        before_dump = before.model_dump() if before is not None else {}

        session.calibration.set_discrimination(
            ro_el,
            threshold=float(metrics["threshold"]),
            angle=float(metrics["angle"]),
            mu_g=[float(mu_g[0]), float(mu_g[1])],
            mu_e=[float(mu_e[0]), float(mu_e[1])],
            sigma_g=float(metrics["sigma_g"]),
            sigma_e=float(metrics["sigma_e"]),
            fidelity=float(fidelity),
            confusion_matrix=[
                [float(metrics.get("gg", 0.0)), float(metrics.get("ge", 0.0))],
                [float(metrics.get("eg", 0.0)), float(metrics.get("ee", 0.0))],
            ],
            n_shots=int(stage["run_kwargs"].get("n_samples", 0)),
        )
        session.calibration.save()

        verify = _repeatability_check(stage_name, exp_factory, stage["run_kwargs"], stage["analyze_kwargs"], ["fidelity"])
        if not verify.get("pass"):
            if before is None:
                session.calibration._data.discrimination.pop(ro_el, None)
            else:
                session.calibration.set_discrimination(ro_el, params=before)
            session.calibration.save()
            return "rollback", "Verification failed after patch; rolled back", before_dump, {"verify": verify}

        after = session.calibration.get_discrimination(ro_el)
        after_dump = after.model_dump() if after is not None else {}
        return "patch_applied", "Applied discrimination parameters", before_dump, after_dump

    if patch_kind == "quality":
        ro_el = getattr(attr, "ro_el", REFERENCE_SEED["ro_el"])
        quality_fields = {
            "F": metrics.get("F", metrics.get("fidelity")),
            "Q": metrics.get("Q"),
            "V": metrics.get("V"),
            "t01": metrics.get("t01"),
            "t10": metrics.get("t10"),
        }
        if all(v is None for v in quality_fields.values()):
            return "patch_preview", "Butterfly quality fields not available", {}, {"metrics": metrics}

        repeat = _repeatability_check(stage_name, exp_factory, stage["run_kwargs"], stage["analyze_kwargs"], ["F", "fidelity"])
        if not repeat.get("pass"):
            return "patch_skipped", f"Repeatability failed: {repeat}", {}, {"repeatability": repeat}

        before = session.calibration.get_readout_quality(ro_el)
        before_dump = before.model_dump() if before is not None else {}
        session.calibration.set_readout_quality(
            ro_el,
            F=float(quality_fields["F"]) if quality_fields["F"] is not None else None,
            Q=float(quality_fields["Q"]) if quality_fields["Q"] is not None else None,
            V=float(quality_fields["V"]) if quality_fields["V"] is not None else None,
            t01=float(quality_fields["t01"]) if quality_fields["t01"] is not None else None,
            t10=float(quality_fields["t10"]) if quality_fields["t10"] is not None else None,
            n_shots=int(stage["run_kwargs"].get("n_samples", 0)),
        )
        session.calibration.save()

        verify = _repeatability_check(stage_name, exp_factory, stage["run_kwargs"], stage["analyze_kwargs"], ["F", "fidelity"])
        if not verify.get("pass"):
            if before is None:
                session.calibration._data.readout_quality.pop(ro_el, None)
            else:
                session.calibration.set_readout_quality(ro_el, params=before)
            session.calibration.save()
            return "rollback", "Verification failed after patch; rolled back", before_dump, {"verify": verify}

        after = session.calibration.get_readout_quality(ro_el)
        return "patch_applied", "Applied butterfly readout quality", before_dump, (after.model_dump() if after else {})

    if patch_kind == "qb_freq":
        f0 = _metric_from_analysis(analysis, ["f0"]) 
        if f0 is None or not np.isfinite(f0):
            return "patch_skipped", "Missing f0 from qubit spectroscopy", {}, {}
        old = float(getattr(attr, "qb_fq", REFERENCE_SEED["qb_fq"]))
        shift = abs(f0 - old)
        if shift < 2e5:
            return "patch_skipped", f"Shift below threshold ({shift:.1f} Hz)", {"qb_fq": old}, {"qb_fq": old}

        repeat = _repeatability_check(stage_name, exp_factory, stage["run_kwargs"], stage["analyze_kwargs"], ["f0"])
        if not repeat.get("pass"):
            return "patch_skipped", f"Repeatability failed: {repeat}", {"qb_fq": old}, {}

        before = _apply_attr_patch(attr, {"qb_fq": float(f0)})
        try:
            session.calibration.set_frequencies(getattr(attr, "qb_el", REFERENCE_SEED["qb_el"]), qubit_freq=float(f0))
            session.calibration.save()
            session.calibration.save()
            verify = _repeatability_check(stage_name, exp_factory, stage["run_kwargs"], stage["analyze_kwargs"], ["f0"])
            if not verify.get("pass"):
                _restore_attr_patch(attr, before)
                session.calibration.set_frequencies(getattr(attr, "qb_el", REFERENCE_SEED["qb_el"]), qubit_freq=float(before["qb_fq"]))
                session.calibration.save()
                session.calibration.save()
                return "rollback", "Verification failed after patch; rolled back", before, {"verify": verify}
            return "patch_applied", f"Updated qb_fq by {f0-old:+.1f} Hz", before, {"qb_fq": float(f0)}
        except Exception as exc:
            _restore_attr_patch(attr, before)
            session.calibration.save()
            return "rollback", f"Patch failed and rolled back: {exc}", before, before

    if patch_kind == "r180":
        a_pi = _metric_from_analysis(analysis, ["g_pi", "pi_amp", "A_pi"])
        if a_pi is None or not np.isfinite(a_pi):
            return "patch_skipped", "No pi-amplitude metric from PowerRabi", {}, {}

        repeat = _repeatability_check(stage_name, exp_factory, stage["run_kwargs"], stage["analyze_kwargs"], ["g_pi", "pi_amp", "A_pi"])
        if not repeat.get("pass"):
            return "patch_skipped", f"Repeatability failed: {repeat}", {}, {}

        before = _apply_attr_patch(attr, {"r180_amp": float(a_pi), "rlen": int(RULES["pulse_len_unselective_ns"])})
        try:
            session.calibration.set_pulse_calibration(
                "ge_ref_r180",
                pulse_name="ge_ref_r180",
                element=getattr(attr, "qb_el", REFERENCE_SEED["qb_el"]),
                transition="ge",
                amplitude=float(a_pi),
                length=int(RULES["pulse_len_unselective_ns"]),
                sigma=float(REFERENCE_SEED["rsigma"]),
            )
            session.calibration.save()
            session.calibration.save()
            verify = _repeatability_check(stage_name, exp_factory, stage["run_kwargs"], stage["analyze_kwargs"], ["g_pi", "pi_amp", "A_pi"])
            if not verify.get("pass"):
                _restore_attr_patch(attr, before)
                session.calibration.set_pulse_calibration(
                    "ge_ref_r180",
                    pulse_name="ge_ref_r180",
                    element=getattr(attr, "qb_el", REFERENCE_SEED["qb_el"]),
                    transition="ge",
                    amplitude=float(before.get("r180_amp", REFERENCE_SEED["r180_amp"])),
                    length=int(before.get("rlen", RULES["pulse_len_unselective_ns"])),
                    sigma=float(REFERENCE_SEED["rsigma"]),
                )
                session.calibration.save()
                session.calibration.save()
                return "rollback", "Verification failed after patch; rolled back", before, {"verify": verify}
            return "patch_applied", "Applied primitive pi amplitude patch", before, {"r180_amp": float(a_pi)}
        except Exception as exc:
            _restore_attr_patch(attr, before)
            session.calibration.save()
            return "rollback", f"Pulse patch failed and rolled back: {exc}", before, before

    if patch_kind == "selective_pi":
        gpi = _metric_from_analysis(analysis, ["g_pi_fock_0"])
        if gpi is None or not np.isfinite(gpi):
            return "patch_preview", "Selective pi metric missing; keep as manual-review candidate", {}, {"metrics": metrics}
        return "patch_preview", "Selective pi candidate measured; apply through dedicated selective pulse path", {}, {"g_pi_fock_0": gpi}

    if patch_kind == "displacement":
        f_storage = _metric_from_analysis(analysis, ["f_storage"]) 
        old = float(getattr(attr, "b_coherent_amp", REFERENCE_SEED["b_coherent_amp"]))
        if f_storage is None or not np.isfinite(f_storage):
            return "patch_preview", "Storage metric unavailable; displacement patch deferred", {"b_coherent_amp": old}, {"b_coherent_amp": old}
        return "patch_preview", "Displacement scan executed; no automatic amplitude model available", {"b_coherent_amp": old}, {"b_coherent_amp": old}

    return "patch_skipped", f"Unknown patch kind: {patch_kind}", {}, {}


def _run_stage(
    session: SessionManager,
    attr: Any,
    stage: dict[str, Any],
    writer: ArtifactWriter,
    execute: bool,
) -> dict[str, Any]:
    stage_name = stage["stage"]
    exp_cls = stage["experiment"]
    run_kwargs = dict(stage["run_kwargs"])
    analyze_kwargs = dict(stage.get("analyze_kwargs", {}))

    _assert_safe_bounds(stage_name, run_kwargs)
    measure_ctx = _stage_measure_context(session, attr, stage_name)

    exp_factory = lambda: exp_cls(session)
    exp = exp_factory()

    with measure_ctx:
        build_info = _run_build_only(exp, run_kwargs)
    if not execute:
        writer.append_journal(
            {
                "stage": stage_name,
                "experiment": stage["name"],
                "purpose": "Phase 1 build-only validation",
                "code_path": f"{exp_cls.__module__}.{exp_cls.__name__}",
                "snapshot_hash": _snapshot_hash(attr),
                "element_aliases": {
                    "ro_el": getattr(attr, "ro_el", REFERENCE_SEED["ro_el"]),
                    "qb_el": getattr(attr, "qb_el", REFERENCE_SEED["qb_el"]),
                    "st_el": getattr(attr, "st_el", REFERENCE_SEED["st_el"]),
                },
                "inputs": run_kwargs,
                "sweep": {k: run_kwargs[k] for k in ["rf_begin", "rf_end", "df", "n_avg", "n_samples"] if k in run_kwargs},
                "fit_model": "build-only",
                "checks": {"build_ok": True},
                "decision": "continue",
                "decision_reason": "Build succeeded",
                "fit_metrics": {"builder": build_info.get("builder"), "n_total": build_info.get("n_total")},
            }
        )
        return {"ok": True, "phase": "build", **build_info}

    with _stage_measure_context(session, attr, stage_name):
        result, analysis, checks, runtime_s, diagnostics = _run_with_retry(
            stage_name,
            exp_factory,
            run_kwargs,
            analyze_kwargs,
        )

    output_map = _extract_output(getattr(result, "output", {}))
    fit = getattr(analysis, "fit", None)
    fit_model = getattr(fit, "model_name", "") if fit is not None else ""
    fit_params = getattr(fit, "params", {}) if fit is not None else {}
    fit_unc = getattr(fit, "uncertainties", {}) if fit is not None else {}
    fit_metrics = {
        "r_squared": getattr(fit, "r_squared", None) if fit is not None else None,
        "residual_norm": float(np.linalg.norm(getattr(fit, "residuals", np.array([])))) if fit is not None and getattr(fit, "residuals", None) is not None else None,
    }
    fit_quality = _fit_quality_check(analysis)

    patch_kind = stage.get("patch_kind", "none")
    requires_fit_quality = patch_kind in {"qb_freq", "r180"}

    if requires_fit_quality and not fit_quality.get("pass", False):
        decision = "patch_skipped"
        reason = f"Fit quality gate failed: {fit_quality}"
        patch_before, patch_after = {}, {"fit_quality": fit_quality}
    else:
        decision, reason, patch_before, patch_after = _apply_stage_patch(
            session,
            attr,
            stage,
            analysis,
            writer,
            exp_factory,
        )

    patch_payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "stage": stage_name,
        "experiment": stage["name"],
        "decision": decision,
        "reason": reason,
        "before": patch_before,
        "after": patch_after,
        "metrics": getattr(analysis, "metrics", {}),
    }
    writer.append_patch(decision, patch_payload)

    writer.append_journal(
        {
            "stage": stage_name,
            "experiment": stage["name"],
            "purpose": "Phase 2 hardware run",
            "code_path": f"{exp_cls.__module__}.{exp_cls.__name__}",
            "snapshot_hash": _snapshot_hash(attr),
            "element_aliases": {
                "ro_el": getattr(attr, "ro_el", REFERENCE_SEED["ro_el"]),
                "qb_el": getattr(attr, "qb_el", REFERENCE_SEED["qb_el"]),
                "st_el": getattr(attr, "st_el", REFERENCE_SEED["st_el"]),
            },
            "inputs": run_kwargs,
            "sweep": {k: run_kwargs[k] for k in ["rf_begin", "rf_end", "df", "n_avg", "n_samples", "max_gain", "dg"] if k in run_kwargs},
            "runtime_s": runtime_s,
            "artifacts": {"run_data_dir": str(session.experiment_path / "data")},
            "output_keys": sorted(list(output_map.keys())),
            "fit_model": fit_model,
            "fit_params": fit_params,
            "fit_uncertainties": fit_unc,
            "fit_metrics": fit_metrics,
            "checks": {**checks, "retry_diagnostics": diagnostics},
            "fit_quality": fit_quality,
            "decision": decision,
            "decision_reason": reason,
            "patch_diff": {"before": patch_before, "after": patch_after},
            "warnings": [],
        }
    )

    ok = decision in {"patch_applied", "patch_preview", "patch_skipped"}
    return {
        "ok": bool(ok),
        "phase": "hardware",
        "decision": decision,
        "reason": reason,
        "metrics": getattr(analysis, "metrics", {}),
        "runtime_s": runtime_s,
    }


def run_autotune(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    writer = ArtifactWriter(root)
    outcomes: dict[str, Any] = {}

    writer.append_journal(
        {
            "stage": "INIT",
            "experiment": "AutotuneRunner",
            "purpose": "Initialize autonomous tune-up run",
            "code_path": "qubox_v2.autotune.run_post_cavity_autotune_v1_1",
            "snapshot_hash": hashlib.sha256(json.dumps(REFERENCE_SEED, sort_keys=True).encode("utf-8")).hexdigest()[:16],
            "inputs": vars(args),
            "fit_model": "n/a",
            "checks": {"non_interactive": True, "two_phase": True},
            "decision": "continue",
            "decision_reason": "Automatic execution started",
            "fit_params": {"reference_seed": REFERENCE_SEED},
            "artifacts": {
                "journal": str(writer.journal),
                "patchset": str(writer.patchset),
                "summary": str(writer.summary),
            },
        }
    )

    session_kwargs = {
        "sample_id": args.sample_id,
        "cooldown_id": args.cooldown_id,
        "registry_base": Path(args.root),
        "strict_context": not args.disable_strict_context,
    }
    if args.qop_ip:
        session_kwargs["qop_ip"] = args.qop_ip
    if args.qop_cluster:
        session_kwargs["cluster_name"] = args.qop_cluster

    hard_stop_msg = None

    session = None
    bootstrap_errors: list[str] = []
    bootstrap_attempt_kwargs = [dict(session_kwargs)]
    if not args.disable_strict_context:
        relaxed = dict(session_kwargs)
        relaxed["strict_context"] = False
        bootstrap_attempt_kwargs.append(relaxed)

    for idx, skw in enumerate(bootstrap_attempt_kwargs, start=1):
        try:
            session = SessionManager(**skw)
            if idx > 1:
                writer.append_journal(
                    {
                        "stage": "INIT",
                        "experiment": "SessionManager",
                        "purpose": "Session bootstrap fallback",
                        "code_path": "qubox_v2.experiments.session.SessionManager",
                        "decision": "continue",
                        "decision_reason": "strict_context fallback used",
                        "warnings": bootstrap_errors,
                    }
                )
            break
        except Exception as exc:
            bootstrap_errors.append(str(exc))
            writer.append_journal(
                {
                    "stage": "INIT",
                    "experiment": "SessionManager",
                    "purpose": "Session bootstrap",
                    "code_path": "qubox_v2.experiments.session.SessionManager",
                    "checks": {"attempt": idx, "max_attempts": len(bootstrap_attempt_kwargs)},
                    "decision": "retry" if idx < len(bootstrap_attempt_kwargs) else "hard_stop",
                    "decision_reason": str(exc),
                    "warnings": [str(exc)],
                }
            )
            if idx < len(bootstrap_attempt_kwargs):
                time.sleep(1.0)

    if session is None:
        hard_stop_msg = (
            "Hardware connection failure (OPX/Octave/SA unreachable) after one retry during session bootstrap: "
            + " | ".join(bootstrap_errors)
        )
        writer.append_journal(
            {
                "stage": "HARD_STOP",
                "experiment": "AutotuneRunner",
                "purpose": "Stop condition triggered at bootstrap",
                "code_path": "qubox_v2.autotune.run_post_cavity_autotune_v1_1",
                "decision": "hard_stop",
                "decision_reason": hard_stop_msg,
                "errors": bootstrap_errors,
            }
        )
        writer.write_summary(outcomes, hard_stop=hard_stop_msg)
        raise HardStopError(hard_stop_msg)

    try:
        attr = getattr(session, "attr", None) or getattr(session, "attributes", None)
        _ensure_session_open(session, writer)
        seeded_updates = _seed_session_state(attr)
        if seeded_updates:
            session.calibration.save()
        writer.append_journal(
            {
                "stage": "INIT",
                "experiment": "SeedInitialization",
                "purpose": "Initialize session state from reference seed and fixed pulse policy",
                "code_path": "qubox_v2.autotune.run_post_cavity_autotune_v1_1._seed_session_state",
                "snapshot_hash": _snapshot_hash(attr),
                "element_aliases": {
                    "ro_el": getattr(attr, "ro_el", REFERENCE_SEED["ro_el"]),
                    "qb_el": getattr(attr, "qb_el", REFERENCE_SEED["qb_el"]),
                    "st_el": getattr(attr, "st_el", REFERENCE_SEED["st_el"]),
                },
                "fit_model": "seed_reference_v1_1",
                "fit_params": {"reference_seed_verbatim": REFERENCE_SEED},
                "checks": {
                    "seeded_or_fixed_fields": sorted(list(seeded_updates.keys())),
                    "rlen_ns": getattr(attr, "rlen", None),
                    "b_coherent_len_ns": getattr(attr, "b_coherent_len", None),
                },
                "decision": "continue",
                "decision_reason": "Seed initialized and persisted",
            }
        )
        u = unit()

        # Phase 1: build-only
        specs = _stage_specs(attr, u)
        for stage in specs:
            if stage["stage"] == "C":
                continue
            try:
                outcomes[f"{stage['stage']}_build"] = _run_stage(session, attr, stage, writer, execute=False)
            except HardStopError:
                raise
            except Exception as exc:
                outcomes[f"{stage['stage']}_build"] = {
                    "ok": False,
                    "phase": "build",
                    "decision": "manual_review",
                    "reason": str(exc),
                }
                writer.append_journal(
                    {
                        "stage": f"{stage['stage']}_BUILD",
                        "experiment": stage["name"],
                        "purpose": "Build-only validation",
                        "code_path": f"{stage['experiment'].__module__}.{stage['experiment'].__name__}",
                        "snapshot_hash": _snapshot_hash(attr),
                        "decision": "manual_review",
                        "decision_reason": str(exc),
                        "errors": [traceback.format_exc()],
                    }
                )
            finally:
                writer.write_summary(outcomes, hard_stop=hard_stop_msg)

        # Phase 2: hardware-run
        _ensure_session_open(session, writer)

        specs_by_stage = {s["stage"]: s for s in specs}

        for stage_code in HARDWARE_STAGE_ORDER:
            if stage_code == "C":
                mixer_result = _maybe_run_mixer_calibration(session, attr)
                outcomes["C"] = {
                    "ok": bool(mixer_result.get("attempted_any", False)),
                    "phase": "hardware",
                    "decision": "patch_preview" if mixer_result.get("attempted_any", False) else "manual_review",
                    "reason": "Best-effort SA mixer calibration",
                    "metrics": mixer_result,
                }
                writer.append_patch(
                    "patch_preview" if mixer_result.get("attempted_any", False) else "patch_skipped",
                    {
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "stage": "C",
                        "decision": "patch_preview" if mixer_result.get("attempted_any", False) else "patch_skipped",
                        "reason": "SA-driven mixer calibration best effort",
                        "details": mixer_result,
                    },
                )
                writer.append_journal(
                    {
                        "stage": "C",
                        "experiment": "MixerCalibration(SA)",
                        "purpose": "Minimize LO feedthrough and image sideband",
                        "code_path": "qubox_v2.hardware.controller.HardwareController.calibrate_element",
                        "snapshot_hash": _snapshot_hash(attr),
                        "inputs": {"method": "manual_minimizer", "sa_device_name": "sa124b", "best_effort": True},
                        "checks": {"attempted": mixer_result.get("attempted_any", False)},
                        "decision": "patch_preview" if mixer_result.get("attempted_any", False) else "manual_review",
                        "decision_reason": "Continue on unstable AO2/AO4 objectives; keep best-so-far",
                        "warnings": mixer_result.get("warnings", []),
                        "fit_metrics": mixer_result,
                    }
                )
                writer.write_summary(outcomes, hard_stop=hard_stop_msg)
                continue

            stage = specs_by_stage[stage_code]
            try:
                outcomes[stage["stage"]] = _run_stage(session, attr, stage, writer, execute=True)
            except HardStopError:
                raise
            except Exception as exc:
                outcomes[stage["stage"]] = {
                    "ok": False,
                    "phase": "hardware",
                    "decision": "manual_review",
                    "reason": str(exc),
                }
                writer.append_patch(
                    "patch_skipped",
                    {
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "stage": stage["stage"],
                        "decision": "patch_skipped",
                        "reason": f"Stage failed; continue as manual review: {exc}",
                    },
                )
                writer.append_journal(
                    {
                        "stage": stage["stage"],
                        "experiment": stage["name"],
                        "purpose": "Phase 2 hardware run",
                        "code_path": f"{stage['experiment'].__module__}.{stage['experiment'].__name__}",
                        "snapshot_hash": _snapshot_hash(attr),
                        "inputs": stage["run_kwargs"],
                        "checks": {"pass": False},
                        "decision": "manual_review",
                        "decision_reason": str(exc),
                        "errors": [traceback.format_exc()],
                    }
                )
            finally:
                writer.write_summary(outcomes, hard_stop=hard_stop_msg)

    except HardStopError as stop_exc:
        hard_stop_msg = str(stop_exc)
        writer.append_journal(
            {
                "stage": "HARD_STOP",
                "experiment": "AutotuneRunner",
                "purpose": "Stop condition triggered",
                "code_path": "qubox_v2.autotune.run_post_cavity_autotune_v1_1",
                "decision": "hard_stop",
                "decision_reason": hard_stop_msg,
                "errors": [traceback.format_exc()],
            }
        )
        writer.write_summary(outcomes, hard_stop=hard_stop_msg)
        raise
    finally:
        try:
            session.close()
        except Exception:
            pass

    writer.write_summary(outcomes, hard_stop=hard_stop_msg)
    return outcomes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run post-cavity autotune v1.1 end-to-end (non-interactive)")
    parser.add_argument("--root", default=os.getenv("QUBOX_ROOT", r"E:\qubox"), help="Workspace root path")
    parser.add_argument("--sample-id", default="post_cavity_sample_A")
    parser.add_argument("--cooldown-id", default="cd_2025_02_22")
    parser.add_argument("--qop-ip", default=os.getenv("QOP_IP", ""))
    parser.add_argument("--qop-cluster", default=os.getenv("QOP_CLUSTER", ""))
    parser.add_argument("--disable-strict-context", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        outcomes = run_autotune(args)
        print("Autotune completed.")
        print(json.dumps(outcomes, indent=2, default=str))
        return 0
    except HardStopError as exc:
        print(f"AUTOTUNE HARD STOP: {exc}")
        return 2
    except Exception as exc:
        print(f"AUTOTUNE FAILED: {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
