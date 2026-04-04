from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import shutil

import numpy as np
from qm import generate_qua_script
from qubox.calibration import CalibrationStore
from qubox.programs import api as cQED_programs
from qubox.hardware.config_engine import ConfigEngine
from qubox.pulses.manager import PulseOperationManager
from qubox.core.bindings import ReadoutCal, ReadoutHandle, _merge_readout_cal, bindings_from_hardware_config
from qubox.core.device_metadata import DeviceMetadata
from qubox.core.measurement_config import MeasurementConfig
from qubox.programs.circuit_runner import (
    CircuitRunner,
    make_power_rabi_circuit,
    make_t1_circuit,
    make_ge_discrimination_circuit,
    make_butterfly_circuit,
)


@dataclass
class ValidationCase:
    experiment: str
    sweep_config: str
    n_avg: int
    legacy_script_path: str
    new_script_path: str
    result: str
    timing_notes: list[str]
    verdict: str


@dataclass
class LocalSessionShim:
    config_engine: Any
    pulse_mgr: Any
    bindings: Any
    calibration: CalibrationStore
    _context_snapshot: Any

    def context_snapshot(self) -> Any:
        return self._context_snapshot

    @staticmethod
    def _default_readout_weight_sets(_pulse_info: Any) -> list[list[str]]:
        return [["cos", "sin"], ["minus_sin", "cos"]]

    def apply_measurement_config(self, config: MeasurementConfig) -> None:
        rb = self.bindings.readout
        ctx = self.context_snapshot()
        resolved_element = config.element or getattr(ctx, "ro_el", None) or "resonator"
        resolved_operation = config.operation or rb.active_op or "readout"

        pulse_info = self.pulse_mgr.get_pulseOp_by_element_op(resolved_element, resolved_operation, strict=False)
        if pulse_info is None and resolved_operation != "readout":
            pulse_info = self.pulse_mgr.get_pulseOp_by_element_op(resolved_element, "readout", strict=False)
            if pulse_info is not None:
                resolved_operation = "readout"
        if pulse_info is None:
            raise ValueError(
                f"No readout pulse mapping found for element={resolved_element!r}, operation={resolved_operation!r}."
            )

        weight_sets = [list(spec) for spec in config.weight_sets] if config.weight_sets else self._default_readout_weight_sets(pulse_info)
        rb.pulse_op = pulse_info
        rb.active_op = resolved_operation
        rb.demod_weight_sets = weight_sets
        if config.drive_frequency is not None:
            rb.drive_frequency = float(config.drive_frequency)
        elif rb.drive_frequency is None:
            ctx_drive_freq = getattr(ctx, "ro_fq", None)
            if isinstance(ctx_drive_freq, (int, float)):
                rb.drive_frequency = float(ctx_drive_freq)
        if config.gain is not None:
            rb.gain = float(config.gain)
        if config.weight_length is not None:
            rb.acquire_in.weight_length = int(config.weight_length)

        rb.discrimination.update(config.discrimination_payload())
        rb.quality.update(config.quality_payload())

    def readout_handle(self, alias: str = "resonator", operation: str | None = None) -> ReadoutHandle:
        rb = self.bindings.readout
        ctx = self.context_snapshot()
        element = getattr(ctx, "ro_el", None) or alias
        resolved_operation = operation or rb.active_op or "readout"

        pulse_info = self.pulse_mgr.get_pulseOp_by_element_op(element, resolved_operation, strict=False)
        if pulse_info is None:
            pulse_info = rb.pulse_op

        drive_freq = rb.drive_frequency
        if not isinstance(drive_freq, (int, float)) or drive_freq == 0.0:
            ctx_drive_freq = getattr(ctx, "ro_fq", None)
            drive_freq = float(ctx_drive_freq) if isinstance(ctx_drive_freq, (int, float)) else 0.0

        bound_readout = replace(
            rb,
            pulse_op=pulse_info,
            active_op=resolved_operation,
            drive_frequency=float(drive_freq),
        )
        binding_cal = ReadoutCal.from_readout_binding(bound_readout)
        store_cal = ReadoutCal.from_calibration_store(
            self.calibration,
            (element, alias, rb.physical_id, rb.drive_channel_id),
            drive_freq=drive_freq,
        )
        cal = _merge_readout_cal(binding_cal, store_cal, drive_frequency=float(drive_freq))
        weight_sets = tuple(
            tuple(spec) if isinstance(spec, (list, tuple)) else (spec,)
            for spec in (bound_readout.demod_weight_sets or ())
        )
        return ReadoutHandle(
            binding=bound_readout,
            cal=cal,
            element=element,
            operation=resolved_operation,
            gain=bound_readout.gain,
            demod_weight_sets=weight_sets,
        )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _serialize(session: LocalSessionShim, program: Any) -> str:
    cfg = session.config_engine.build_qm_config()
    return generate_qua_script(program, cfg)


def _normalize_script(script: str) -> list[str]:
    out: list[str] = []
    for line in script.splitlines():
        ln = line.rstrip()
        if ln.startswith("# Single QUA script generated at "):
            continue
        out.append(ln)
    return out


def _diff_scripts(legacy_script: str, new_script: str) -> tuple[str, list[str]]:
    if legacy_script == new_script:
        return "Identical", []

    norm_legacy = _normalize_script(legacy_script)
    norm_new = _normalize_script(new_script)
    if norm_legacy == norm_new:
        return (
            "Functionally equivalent with timing notes",
            [
                "Serialized scripts differ only in non-semantic metadata (generation timestamp header).",
            ],
        )

    legacy_lines = [ln.rstrip() for ln in legacy_script.splitlines() if ln.strip()]
    new_lines = [ln.rstrip() for ln in new_script.splitlines() if ln.strip()]

    if len(legacy_lines) == len(new_lines) and sorted(legacy_lines) == sorted(new_lines):
        return (
            "Functionally equivalent with timing notes",
            ["Instruction multiset matches; ordering differs in generated script."],
        )

    return (
        "Behaviorally different",
        [
            f"Legacy non-empty lines: {len(legacy_lines)}",
            f"New non-empty lines: {len(new_lines)}",
            "Script statements differ beyond harmless reordering.",
        ],
    )


def _prepare_temp_registry(*, repo_root: Path, sample_id: str, cooldown_id: str) -> Path:
    src_sample = repo_root / "samples" / sample_id
    if not src_sample.exists():
        raise FileNotFoundError(f"Sample not found: {src_sample}")

    temp_root = repo_root / ".tmp_serialization_validation"
    temp_sample = temp_root / "samples" / sample_id

    if temp_sample.exists():
        shutil.rmtree(temp_sample)
    temp_sample.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_sample, temp_sample)

    cal_path = temp_sample / "cooldowns" / cooldown_id / "config" / "calibration.json"
    if cal_path.exists():
        raw = json.loads(cal_path.read_text(encoding="utf-8"))
        if not isinstance(raw.get("context"), dict):
            raw["context"] = {
                "sample_id": sample_id,
                "cooldown_id": cooldown_id,
                "wiring_rev": "",
                "schema_version": str(raw.get("version", "5.0.0")),
                "config_hash": "",
                "created": datetime.now().isoformat(),
            }
            cal_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    return temp_root


def _seed_calibration_from_cqed_params(calibration: CalibrationStore, cqed_path: Path) -> dict[str, str]:
    raw = json.loads(cqed_path.read_text(encoding="utf-8"))
    roles = {
        "qubit": str(raw.get("qb_el") or "transmon"),
        "readout": str(raw.get("ro_el") or "resonator"),
        "storage": str(raw.get("st_el") or "storage"),
    }

    qb_freqs = calibration.get_frequencies(roles["qubit"])
    qb_params = calibration.get_cqed_params(roles["qubit"])
    qb_updates: dict[str, float] = {}
    if raw.get("qb_fq") is not None and getattr(qb_freqs, "qubit_freq", None) is None:
        qb_updates["qubit_freq"] = float(raw["qb_fq"])
    if raw.get("anharmonicity") is not None and getattr(qb_params, "anharmonicity", None) is None:
        qb_updates["anharmonicity"] = float(raw["anharmonicity"])
    if qb_updates:
        calibration.set_cqed_params(roles["qubit"], **qb_updates)

    ro_freqs = calibration.get_frequencies(roles["readout"])
    ro_updates: dict[str, float] = {}
    if raw.get("ro_fq") is not None and getattr(ro_freqs, "resonator_freq", None) is None:
        ro_updates["resonator_freq"] = float(raw["ro_fq"])
    if ro_updates:
        calibration.set_cqed_params(roles["readout"], **ro_updates)

    st_freqs = calibration.get_frequencies(roles["storage"])
    st_updates: dict[str, float] = {}
    if raw.get("st_fq") is not None and getattr(st_freqs, "storage_freq", None) is None:
        st_updates["storage_freq"] = float(raw["st_fq"])
    if st_updates:
        calibration.set_cqed_params(roles["storage"], **st_updates)

    return roles


def _load_local_session(*, repo_root: Path, sample_id: str, cooldown_id: str) -> LocalSessionShim:
    temp_root = _prepare_temp_registry(repo_root=repo_root, sample_id=sample_id, cooldown_id=cooldown_id)

    sample_dir = temp_root / "samples" / sample_id
    sample_cfg = sample_dir / "config"
    cooldown_cfg = sample_dir / "cooldowns" / cooldown_id / "config"

    hardware_path = sample_cfg / "hardware.json"
    cqed_path = sample_cfg / "cqed_params.json"
    pulses_path = cooldown_cfg / "pulses.json"
    measure_cfg_path = cooldown_cfg / "measureConfig.json"

    cfg_engine = ConfigEngine(hardware_path=hardware_path)
    pulse_mgr = PulseOperationManager.from_json(pulses_path)
    cfg_engine.merge_pulses(pulse_mgr, include_volatile=True)

    calibration = CalibrationStore(cooldown_cfg / "calibration.json")
    seeded_roles = _seed_calibration_from_cqed_params(calibration, cqed_path)
    roles = ((cfg_engine.hardware.get_qubox_extras().bindings or {}).get("roles") or {})
    if not isinstance(roles, dict) or not roles:
        roles = seeded_roles
    ctx = DeviceMetadata.from_roles(roles, calibration=calibration)
    bindings = bindings_from_hardware_config(cfg_engine.hardware, ctx)

    session = LocalSessionShim(
        config_engine=cfg_engine,
        pulse_mgr=pulse_mgr,
        bindings=bindings,
        calibration=calibration,
        _context_snapshot=ctx,
    )

    if measure_cfg_path.exists():
        session.apply_measurement_config(MeasurementConfig.load_json(measure_cfg_path))

    return session


def _resolve_ge_weight_keys(session: LocalSessionShim, *, measure_op: str, ro_el: str) -> tuple[tuple[str, str, str], Any]:
    pulse_info = session.pulse_mgr.get_pulseOp_by_element_op(ro_el, measure_op, strict=False)
    if pulse_info is None:
        raise RuntimeError(f"No pulse mapping for (element={ro_el!r}, op={measure_op!r})")

    weight_mapping = pulse_info.int_weights_mapping or {}
    is_readout = (pulse_info.op == "readout")
    op_prefix = "" if is_readout else f"{pulse_info.op}_"

    candidates = [
        (f"{op_prefix}cos", f"{op_prefix}sin", f"{op_prefix}minus_sin"),
        ("cos", "sin", "minus_sin"),
    ]
    selected = None
    for triplet in candidates:
        if all(k in weight_mapping for k in triplet):
            selected = triplet
            break
    if selected is None:
        raise RuntimeError(
            f"Could not resolve GE weight keys for op={measure_op!r}. Available={sorted(weight_mapping.keys())}"
        )

    return selected, pulse_info


def run_validation(
    *,
    sample_id: str = "post_cavity_sample_A",
    cooldown_id: str = "cd_2025_02_22",
) -> list[ValidationCase]:
    output_dir = Path("docs") / "circuit_serialized"
    output_dir.mkdir(parents=True, exist_ok=True)

    repo_root = Path(__file__).resolve().parent.parent
    session = _load_local_session(
        repo_root=repo_root,
        sample_id=sample_id,
        cooldown_id=cooldown_id,
    )
    ctx = session.context_snapshot()
    qb_therm_clks = int(getattr(ctx, "qb_therm_clks", 250_000) or 250_000)

    runner = CircuitRunner(session)
    cases: list[ValidationCase] = []

    # --- 1) Power Rabi ---
    op = "x180"
    pulse_info = session.pulse_mgr.get_pulseOp_by_element_op(ctx.qb_el, op)
    if pulse_info is None:
        raise RuntimeError(f"PowerRabi validation requires op={op!r} on element={ctx.qb_el!r}")

    gains = np.arange(-0.15, 0.15 + 1e-12, 0.05, dtype=float)
    pr_legacy_prog = cQED_programs.power_rabi(
        round(int(pulse_info.length) / 4),
        gains,
        qb_therm_clks,
        op,
        None,
        64,
        qb_el=ctx.qb_el,
        bindings=session.bindings,
        readout=session.readout_handle(),
    )
    pr_circuit, pr_sweep = make_power_rabi_circuit(
        qb_el=ctx.qb_el,
        qb_therm_clks=qb_therm_clks,
        pulse_clock_len=round(int(pulse_info.length) / 4),
        n_avg=64,
        op=op,
        truncate_clks=None,
        gains=gains,
    )
    pr_new = runner.compile(pr_circuit, sweep=pr_sweep)

    pr_legacy_script = _serialize(session, pr_legacy_prog)
    pr_new_script = runner.serialize(pr_new)
    pr_legacy_path = output_dir / "power_rabi_legacy.py"
    pr_new_path = output_dir / "power_rabi_circuit.py"
    _write_text(pr_legacy_path, pr_legacy_script)
    _write_text(pr_new_path, pr_new_script)
    pr_result, pr_notes = _diff_scripts(pr_legacy_script, pr_new_script)
    cases.append(
        ValidationCase(
            experiment="Power Rabi",
            sweep_config="gains=-0.15..0.15 step 0.05",
            n_avg=64,
            legacy_script_path=str(pr_legacy_path).replace('\\', '/'),
            new_script_path=str(pr_new_path).replace('\\', '/'),
            result=pr_result,
            timing_notes=pr_notes,
            verdict="PASS" if pr_result != "Behaviorally different" else "REVIEW",
        )
    )

    # --- 2) T1 ---
    waits_clks = np.arange(2, 21, 2, dtype=int)
    t1_legacy_prog = cQED_programs.T1_relaxation(
        "x180",
        waits_clks,
        qb_therm_clks,
        64,
        qb_el=ctx.qb_el,
        bindings=session.bindings,
        readout=session.readout_handle(),
    )
    t1_circuit, t1_sweep = make_t1_circuit(
        qb_el=ctx.qb_el,
        qb_therm_clks=qb_therm_clks,
        n_avg=64,
        waits_clks=waits_clks,
        r180="x180",
    )
    t1_new = runner.compile(t1_circuit, sweep=t1_sweep)

    t1_legacy_script = _serialize(session, t1_legacy_prog)
    t1_new_script = runner.serialize(t1_new)
    t1_legacy_path = output_dir / "t1_legacy.py"
    t1_new_path = output_dir / "t1_circuit.py"
    _write_text(t1_legacy_path, t1_legacy_script)
    _write_text(t1_new_path, t1_new_script)
    t1_result, t1_notes = _diff_scripts(t1_legacy_script, t1_new_script)
    cases.append(
        ValidationCase(
            experiment="T1",
            sweep_config="wait_cycles=2..20 step 2",
            n_avg=64,
            legacy_script_path=str(t1_legacy_path).replace('\\', '/'),
            new_script_path=str(t1_new_path).replace('\\', '/'),
            result=t1_result,
            timing_notes=t1_notes,
            verdict="PASS" if t1_result != "Behaviorally different" else "REVIEW",
        )
    )

    # --- 3) Readout GE discrimination ---
    ro_el = ctx.ro_el
    qb_el = ctx.qb_el
    measure_op = "readout"
    drive_frequency = float(getattr(ctx, "ro_fq", 0.0) or 0.0)
    base_weight_keys, _ = _resolve_ge_weight_keys(
        session,
        measure_op=measure_op,
        ro_el=ro_el,
    )

    n_samples = 2048
    ge_legacy_prog = cQED_programs.iq_blobs(
        ro_el,
        qb_el,
        "x180",
        qb_therm_clks,
        n_samples,
        bindings=session.bindings,
        readout=session.readout_handle(),
    )

    ge_circuit, ge_sweep = make_ge_discrimination_circuit(
        ro_el=ro_el,
        qb_el=qb_el,
        measure_op=measure_op,
        drive_frequency=drive_frequency,
        qb_therm_clks=qb_therm_clks,
        n_samples=n_samples,
        r180="x180",
        base_weight_keys=base_weight_keys,
    )
    ge_new = runner.compile(ge_circuit, sweep=ge_sweep)

    ge_legacy_script = _serialize(session, ge_legacy_prog)
    ge_new_script = runner.serialize(ge_new)
    ge_legacy_path = output_dir / "readout_ge_discrimination_legacy.py"
    ge_new_path = output_dir / "readout_ge_discrimination_circuit.py"
    _write_text(ge_legacy_path, ge_legacy_script)
    _write_text(ge_new_path, ge_new_script)
    ge_result, ge_notes = _diff_scripts(ge_legacy_script, ge_new_script)
    cases.append(
        ValidationCase(
            experiment="Readout GE discrimination",
            sweep_config="single-point acquisition, no sweep",
            n_avg=n_samples,
            legacy_script_path=str(ge_legacy_path).replace('\\', '/'),
            new_script_path=str(ge_new_path).replace('\\', '/'),
            result=ge_result,
            timing_notes=ge_notes,
            verdict="PASS" if ge_result != "Behaviorally different" else "REVIEW",
        )
    )

    # --- 4) Butterfly measurement ---
    readout = session.readout_handle()
    thr = getattr(getattr(readout, "cal", None), "threshold", None)
    if thr is None:
        thr = (getattr(readout.binding, "discrimination", {}) or {}).get("threshold")
    if thr is None:
        thr = 0.0
    prep_policy = "THRESHOLD"
    prep_kwargs = {"threshold": float(thr)}

    bfly_legacy_prog = cQED_programs.readout_butterfly_measurement(
        qb_el,
        "x180",
        prep_policy,
        prep_kwargs,
        8,
        n_samples,
        bindings=session.bindings,
        readout=session.readout_handle(),
    )
    bfly_circuit, bfly_sweep = make_butterfly_circuit(
        qb_el=qb_el,
        n_samples=n_samples,
        prep_policy=prep_policy,
        prep_kwargs=prep_kwargs,
        r180="x180",
        max_trials=8,
    )
    bfly_new = runner.compile(bfly_circuit, sweep=bfly_sweep)

    bfly_legacy_script = _serialize(session, bfly_legacy_prog)
    bfly_new_script = runner.serialize(bfly_new)
    bfly_legacy_path = output_dir / "butterfly_legacy.py"
    bfly_new_path = output_dir / "butterfly_circuit.py"
    _write_text(bfly_legacy_path, bfly_legacy_script)
    _write_text(bfly_new_path, bfly_new_script)
    bfly_result, bfly_notes = _diff_scripts(bfly_legacy_script, bfly_new_script)
    cases.append(
        ValidationCase(
            experiment="Butterfly measurement",
            sweep_config="single-point acquisition, policy=THRESHOLD",
            n_avg=n_samples,
            legacy_script_path=str(bfly_legacy_path).replace('\\', '/'),
            new_script_path=str(bfly_new_path).replace('\\', '/'),
            result=bfly_result,
            timing_notes=bfly_notes,
            verdict="PASS" if bfly_result != "Behaviorally different" else "REVIEW",
        )
    )

    return cases


def write_report(cases: list[ValidationCase], report_path: Path) -> None:
    lines: list[str] = []
    lines.append("# Circuit Runner Serialization Validation")
    lines.append("")
    lines.append("Validation method: QUA serialization comparison (legacy vs new CircuitRunner), simulator-only compile flow (no hardware execution).")
    lines.append("")
    lines.append("## Environment")
    lines.append("")
    lines.append("- `qop_ip`: `10.157.36.68` (target cluster information provided)")
    lines.append("- `cluster_name`: `Cluster_2` (target cluster information provided)")
    lines.append("- Execution mode: **No hardware runs** (program build + serialization only)")
    lines.append("")
    for case in cases:
        lines.append(f"## {case.experiment}")
        lines.append("")
        lines.append(f"- Sweep configuration: {case.sweep_config}")
        lines.append(f"- n_avg / n_samples: {case.n_avg}")
        lines.append(f"- Legacy serialized QUA: [{case.legacy_script_path}]({case.legacy_script_path})")
        lines.append(f"- CircuitRunner serialized QUA: [{case.new_script_path}]({case.new_script_path})")
        lines.append(f"- Serialized comparison result: **{case.result}**")
        if case.timing_notes:
            lines.append("- Timing / ordering notes:")
            for note in case.timing_notes:
                lines.append(f"  - {note}")
        else:
            lines.append("- Timing / ordering notes: none")
        lines.append(f"- Final verdict: **{case.verdict}**")
        lines.append("")

    overall = "PASS" if all(c.verdict == "PASS" for c in cases) else "REVIEW"
    lines.append("## Overall verdict")
    lines.append("")
    lines.append(f"**{overall}**")
    lines.append("")
    lines.append("Any `Behaviorally different` result requires investigation before hardware execution.")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    cases = run_validation()
    write_report(cases, Path("docs") / "circuit_runner_serialization_validation.md")
    print("Validation report written to docs/circuit_runner_serialization_validation.md")
    for c in cases:
        print(f"- {c.experiment}: {c.result} ({c.verdict})")
    if any(c.verdict != "PASS" for c in cases):
        raise SystemExit(1)
