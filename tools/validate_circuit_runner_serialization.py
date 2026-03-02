from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import shutil

import numpy as np
from qm import generate_qua_script
from qm.qua import dual_demod

from qubox_v2.calibration import CalibrationStore
from qubox_v2.programs import api as cQED_programs
from qubox_v2.programs.macros.measure import measureMacro
from qubox_v2.hardware.config_engine import ConfigEngine
from qubox_v2.pulses.manager import PulseOperationManager
from qubox_v2.analysis.cQED_attributes import cQED_attributes
from qubox_v2.core.bindings import bindings_from_hardware_config
from qubox_v2.programs.circuit_runner import (
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
    _context_snapshot: Any

    def context_snapshot(self) -> Any:
        return self._context_snapshot


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

    ctx = cQED_attributes.from_json(cqed_path)
    calibration = CalibrationStore(cooldown_cfg / "calibration.json")
    _overlay_calibration_context(ctx, calibration)
    bindings = bindings_from_hardware_config(cfg_engine.hardware, ctx)

    if measure_cfg_path.exists():
        measureMacro.load_json(str(measure_cfg_path))

    return LocalSessionShim(
        config_engine=cfg_engine,
        pulse_mgr=pulse_mgr,
        bindings=bindings,
        _context_snapshot=ctx,
    )


def _overlay_calibration_context(ctx: cQED_attributes, calibration: CalibrationStore) -> None:
    resonator = calibration.get_cqed_params("resonator")
    transmon = calibration.get_cqed_params("transmon")
    storage = calibration.get_cqed_params("storage")

    if resonator is not None:
        if resonator.resonator_freq is not None:
            ctx.ro_fq = resonator.resonator_freq
        if resonator.kappa is not None:
            ctx.ro_kappa = resonator.kappa
        if resonator.ro_therm_clks is not None:
            setattr(ctx, "ro_therm_clks", resonator.ro_therm_clks)

    if transmon is not None:
        if transmon.qubit_freq is not None:
            ctx.qb_fq = transmon.qubit_freq
        if transmon.anharmonicity is not None:
            ctx.anharmonicity = transmon.anharmonicity
        if transmon.qb_therm_clks is not None:
            setattr(ctx, "qb_therm_clks", transmon.qb_therm_clks)

    if storage is not None:
        if storage.storage_freq is not None:
            ctx.st_fq = storage.storage_freq
        if storage.chi is not None:
            ctx.st_chi = storage.chi
        if storage.chi2 is not None:
            ctx.st_chi2 = storage.chi2
        if storage.chi3 is not None:
            ctx.st_chi3 = storage.chi3
        if storage.kerr is not None:
            ctx.st_K = storage.kerr
        if storage.kerr2 is not None:
            ctx.st_K2 = storage.kerr2
        if storage.fock_freqs is not None:
            ctx.fock_fqs = np.asarray(storage.fock_freqs, dtype=float)
        if storage.st_therm_clks is not None:
            setattr(ctx, "st_therm_clks", storage.st_therm_clks)


def _prepare_ge_measure_macro(session: LocalSessionShim, *, measure_op: str, drive_frequency: float, ro_el: str) -> tuple[tuple[str, str, str], Any]:
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

    cos_key, sin_key, m_sin_key = selected
    measureMacro.set_demodulator(dual_demod.full)
    measureMacro.set_pulse_op(
        pulse_info,
        active_op=measure_op,
        weights=[[cos_key, sin_key], [m_sin_key, cos_key]],
        weight_len=pulse_info.length,
    )
    measureMacro.set_drive_frequency(drive_frequency)
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
    base_weight_keys, _ = _prepare_ge_measure_macro(
        session,
        measure_op=measure_op,
        drive_frequency=drive_frequency,
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
    thr = (getattr(measureMacro, "_ro_disc_params", {}) or {}).get("threshold")
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
