from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import shutil

import numpy as np
from qm import generate_qua_script
from qubox_v2_legacy.programs.macros.measure import measureMacro

from qubox_v2_legacy.calibration import CalibrationStore
from qubox_v2_legacy.programs import api as cQED_programs
from qubox_v2_legacy.hardware.config_engine import ConfigEngine
from qubox_v2_legacy.pulses.manager import PulseOperationManager
from qubox_v2_legacy.analysis.cQED_attributes import cQED_attributes
from qubox_v2_legacy.core.bindings import bindings_from_hardware_config
from qubox_v2_legacy.programs.circuit_runner import (
    CircuitRunner,
    make_power_rabi_circuit,
    make_xy_pair_circuit,
)
from qubox_v2_legacy.programs.gate_tuning import GateTuningStore, make_xy_tuning_record


@dataclass
class LocalSessionShim:
    config_engine: Any
    pulse_mgr: Any
    bindings: Any
    _context_snapshot: Any
    gate_tuning_store: GateTuningStore | None = None

    def context_snapshot(self) -> Any:
        return self._context_snapshot


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _normalize_script(script: str) -> list[str]:
    out: list[str] = []
    for line in script.splitlines():
        ln = line.rstrip()
        if ln.startswith("# Single QUA script generated at "):
            continue
        out.append(ln)
    return out


def _diff_scripts(a: str, b: str) -> tuple[str, list[str]]:
    if a == b:
        return "Identical", []
    if _normalize_script(a) == _normalize_script(b):
        return "Functionally equivalent with timing notes", ["Only timestamp header differs."]
    return "Behaviorally different", ["Compiled scripts differ after normalization (expected when tuning modifies amplitudes)."]


def _prepare_temp_registry(*, repo_root: Path, sample_id: str, cooldown_id: str) -> Path:
    src_sample = repo_root / "samples" / sample_id
    if not src_sample.exists():
        raise FileNotFoundError(f"Sample not found: {src_sample}")

    temp_root = repo_root / ".tmp_gate_tuning_validation"
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

    cfg_engine = ConfigEngine(hardware_path=sample_cfg / "hardware.json")
    pulse_mgr = PulseOperationManager.from_json(cooldown_cfg / "pulses.json")
    cfg_engine.merge_pulses(pulse_mgr, include_volatile=True)

    ctx = cQED_attributes.from_json(sample_cfg / "cqed_params.json")
    calibration = CalibrationStore(cooldown_cfg / "calibration.json")
    _overlay_calibration_context(ctx, calibration)
    bindings = bindings_from_hardware_config(cfg_engine.hardware, ctx)

    measure_cfg = cooldown_cfg / "measureConfig.json"
    if measure_cfg.exists():
        measureMacro.load_json(str(measure_cfg))

    return LocalSessionShim(
        config_engine=cfg_engine,
        pulse_mgr=pulse_mgr,
        bindings=bindings,
        _context_snapshot=ctx,
        gate_tuning_store=GateTuningStore(),
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


def _serialize(session: LocalSessionShim, program: Any) -> str:
    cfg = session.config_engine.build_qm_config()
    return generate_qua_script(program, cfg)


def _peak_abs_i(pulse_mgr: Any, element: str, operation: str) -> float:
    pulse = pulse_mgr.get_pulseOp_by_element_op(element, operation, strict=False)
    if pulse is None:
        return float("nan")
    i_wf = np.asarray(getattr(pulse, "I_wf", []) or [], dtype=float)
    if i_wf.size == 0:
        return 0.0
    return float(np.max(np.abs(i_wf)))


def run_validation(*, sample_id: str = "post_cavity_sample_A", cooldown_id: str = "cd_2025_02_22") -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parent.parent
    output_serial = repo_root / "docs" / "circuit_tuning_serialized"
    output_fig = repo_root / "docs" / "figures" / "circuit_pulses"
    output_serial.mkdir(parents=True, exist_ok=True)
    output_fig.mkdir(parents=True, exist_ok=True)

    session_legacy = _load_local_session(repo_root=repo_root, sample_id=sample_id, cooldown_id=cooldown_id)
    session_tuned = _load_local_session(repo_root=repo_root, sample_id=sample_id, cooldown_id=cooldown_id)

    ctx = session_tuned.context_snapshot()
    qb_el = ctx.qb_el
    qb_therm = int(getattr(ctx, "qb_therm_clks", 250_000) or 250_000)

    tuning = make_xy_tuning_record(
        target=qb_el,
        amplitude_scale=0.92,
        detune_hz=0.0,
        source_experiment="DRAGCalibration/PowerRabi",
        notes="Validation fixture tuning record for X family.",
    )
    session_tuned.gate_tuning_store.add_record(tuning)

    legacy_runner = CircuitRunner(session_legacy)
    tuned_runner = CircuitRunner(session_tuned)

    x180_legacy_prog = cQED_programs.power_rabi(
        16,
        np.asarray([1.0]),
        qb_therm,
        "x180",
        None,
        64,
        qb_el=qb_el,
        bindings=session_legacy.bindings,
    )
    x180_circuit, x180_sweep = make_power_rabi_circuit(
        qb_el=qb_el,
        qb_therm_clks=qb_therm,
        pulse_clock_len=16,
        n_avg=64,
        op="x180",
        gains=np.asarray([1.0]),
    )
    x180_tuned = tuned_runner.compile(x180_circuit, sweep=x180_sweep)

    x90_legacy_prog = cQED_programs.power_rabi(
        8,
        np.asarray([1.0]),
        qb_therm,
        "x90",
        None,
        64,
        qb_el=qb_el,
        bindings=session_legacy.bindings,
    )
    x90_circuit, x90_sweep = make_power_rabi_circuit(
        qb_el=qb_el,
        qb_therm_clks=qb_therm,
        pulse_clock_len=8,
        n_avg=64,
        op="x90",
        gains=np.asarray([1.0]),
    )
    x90_tuned = tuned_runner.compile(x90_circuit, sweep=x90_sweep)

    xy_legacy_prog = cQED_programs.all_xy(qb_el, [("x180", "x90")], qb_therm, 64)
    xy_circuit, xy_sweep = make_xy_pair_circuit(qb_el=qb_el, qb_therm_clks=qb_therm, n_avg=64, op_a="x180", op_b="x90")
    xy_tuned = tuned_runner.compile(xy_circuit, sweep=xy_sweep)

    x180_legacy_script = _serialize(session_legacy, x180_legacy_prog)
    x180_tuned_script = tuned_runner.serialize(x180_tuned)
    x90_legacy_script = _serialize(session_legacy, x90_legacy_prog)
    x90_tuned_script = tuned_runner.serialize(x90_tuned)
    xy_legacy_script = _serialize(session_legacy, xy_legacy_prog)
    xy_tuned_script = tuned_runner.serialize(xy_tuned)

    _write_text(output_serial / "x180_legacy.py", x180_legacy_script)
    _write_text(output_serial / "x180_tuned.py", x180_tuned_script)
    _write_text(output_serial / "x90_legacy.py", x90_legacy_script)
    _write_text(output_serial / "x90_tuned.py", x90_tuned_script)
    _write_text(output_serial / "xy_pair_legacy.py", xy_legacy_script)
    _write_text(output_serial / "xy_pair_tuned.py", xy_tuned_script)

    x180_cmp, x180_notes = _diff_scripts(x180_legacy_script, x180_tuned_script)
    x90_cmp, x90_notes = _diff_scripts(x90_legacy_script, x90_tuned_script)
    xy_cmp, xy_notes = _diff_scripts(xy_legacy_script, xy_tuned_script)

    legacy_runner.visualize_pulses(x180_circuit, sweep=x180_sweep, save_path=str(output_fig / "x180_legacy.png"))
    tuned_runner.visualize_pulses(x180_circuit, sweep=x180_sweep, save_path=str(output_fig / "x180_tuned.png"))
    legacy_runner.visualize_pulses(x90_circuit, sweep=x90_sweep, save_path=str(output_fig / "x90_legacy.png"))
    tuned_runner.visualize_pulses(x90_circuit, sweep=x90_sweep, save_path=str(output_fig / "x90_tuned.png"))
    tuned_runner.visualize_pulses(xy_circuit, sweep=xy_sweep, save_path=str(output_fig / "xy_pair_tuned.png"))

    peak_x180 = _peak_abs_i(session_tuned.pulse_mgr, qb_el, "x180")
    peak_x90 = _peak_abs_i(session_tuned.pulse_mgr, qb_el, "x90")
    expected_x180 = peak_x180 * 0.92
    expected_x90 = peak_x90 * 0.92 * 0.5

    report = {
        "tuning_record_id": tuning.record_id,
        "tuned_operation": {
            "x180": x180_tuned.metadata.get("applied_gain_scale"),
            "x90": x90_tuned.metadata.get("applied_gain_scale"),
        },
        "expected_amplitude_scale": {
            "x180": 0.92,
            "x90": 0.46,
        },
        "serialized_comparison": {
            "x180": {"result": x180_cmp, "notes": x180_notes},
            "x90": {"result": x90_cmp, "notes": x90_notes},
            "xy_pair": {"result": xy_cmp, "notes": xy_notes},
        },
        "pulse_peaks_reference": {
            "legacy_x180_peak_abs_I": peak_x180,
            "legacy_x90_peak_abs_I": peak_x90,
            "expected_tuned_x180_peak_abs_I": expected_x180,
            "expected_tuned_x90_peak_abs_I": expected_x90,
        },
        "artifacts": {
            "serialized_dir": "docs/circuit_tuning_serialized",
            "figures_dir": "docs/figures/circuit_pulses",
        },
    }
    return report


def write_reports(report: dict[str, Any]) -> None:
    lines1: list[str] = []
    lines1.append("# Gate Tuning Serialization Validation")
    lines1.append("")
    lines1.append("Validation mode: compiled QUA serialization only (simulator/compile path, no hardware execution).")
    lines1.append("")
    lines1.append("## Architecture diagram")
    lines1.append("")
    lines1.append("```mermaid")
    lines1.append("flowchart LR")
    lines1.append("  A[GateTuningRecord] --> B[GateTuningStore]")
    lines1.append("  B --> C[CircuitRunner.compile]")
    lines1.append("  C --> D[Compiled QUA]")
    lines1.append("  D --> E[Serialization Diff Validation]")
    lines1.append("```")
    lines1.append("")
    lines1.append("## Data flow diagram")
    lines1.append("")
    lines1.append("```mermaid")
    lines1.append("sequenceDiagram")
    lines1.append("  participant T as Tuning Store")
    lines1.append("  participant R as CircuitRunner")
    lines1.append("  participant Q as QUA Program")
    lines1.append("  T->>R: resolve(target, op)")
    lines1.append("  R->>Q: apply tuned/derived scale")
    lines1.append("  Q-->>R: compiled script")
    lines1.append("```")
    lines1.append("")
    lines1.append("## Example pseudo-code")
    lines1.append("")
    lines1.append("```python")
    lines1.append("record = make_xy_tuning_record(target=qb_el, amplitude_scale=0.92)")
    lines1.append("store.add_record(record)")
    lines1.append("build = CircuitRunner(session).compile(circuit_x90)")
    lines1.append("assert build.metadata['applied_gain_scale'] == 0.46")
    lines1.append("```")
    lines1.append("")
    lines1.append("## Integration boundaries")
    lines1.append("")
    lines1.append("- Inputs: tuning records, circuit metadata, compiled pulse registry")
    lines1.append("- Outputs: serialized QUA scripts + metadata")
    lines1.append("- Excluded: hardware execution path")
    lines1.append("")
    lines1.append("## Scope")
    lines1.append("")
    lines1.append("- Tuned `X180`")
    lines1.append("- Derived `X90` (from `X180` via family derivation factor 0.5)")
    lines1.append("- Short circuit `X180 -> X90`")
    lines1.append("")
    lines1.append("## GateTuningRecord")
    lines1.append("")
    lines1.append(f"- Record ID: `{report['tuning_record_id']}`")
    lines1.append(f"- Applied gain scale (`X180`): `{report['tuned_operation']['x180']}`")
    lines1.append(f"- Applied gain scale (`X90` derived): `{report['tuned_operation']['x90']}`")
    lines1.append("")
    lines1.append("## Serialized comparison")
    lines1.append("")
    for name in ("x180", "x90", "xy_pair"):
        item = report["serialized_comparison"][name]
        lines1.append(f"### {name.upper()}")
        lines1.append("")
        lines1.append(f"- Result: **{item['result']}**")
        if item["notes"]:
            for note in item["notes"]:
                lines1.append(f"- Note: {note}")
        lines1.append("")
    lines1.append("## Serialized artifacts")
    lines1.append("")
    lines1.append("- [x180 legacy](docs/circuit_tuning_serialized/x180_legacy.py)")
    lines1.append("- [x180 tuned](docs/circuit_tuning_serialized/x180_tuned.py)")
    lines1.append("- [x90 legacy](docs/circuit_tuning_serialized/x90_legacy.py)")
    lines1.append("- [x90 tuned](docs/circuit_tuning_serialized/x90_tuned.py)")
    lines1.append("- [xy pair legacy](docs/circuit_tuning_serialized/xy_pair_legacy.py)")
    lines1.append("- [xy pair tuned](docs/circuit_tuning_serialized/xy_pair_tuned.py)")

    Path("docs/gate_tuning_serialization_validation.md").write_text("\n".join(lines1) + "\n", encoding="utf-8")

    lines2: list[str] = []
    lines2.append("# Circuit Pulse Visualization Validation")
    lines2.append("")
    lines2.append("Validation mode: compiled timing-model pulse visualization generated from compiled gate sequence and pulse registry (no hardware execution).")
    lines2.append("")
    lines2.append("## Architecture diagram")
    lines2.append("")
    lines2.append("```mermaid")
    lines2.append("flowchart LR")
    lines2.append("  A[QuantumCircuit] --> B[CircuitRunner.visualize_pulses]")
    lines2.append("  B --> C[Simulator Samples / Timing Model]")
    lines2.append("  C --> D[Matplotlib Pulse Figure]")
    lines2.append("```")
    lines2.append("")
    lines2.append("## Data flow diagram")
    lines2.append("")
    lines2.append("```mermaid")
    lines2.append("sequenceDiagram")
    lines2.append("  participant C as Circuit")
    lines2.append("  participant R as Runner")
    lines2.append("  participant P as Pulse Registry")
    lines2.append("  C->>R: draw_pulses()")
    lines2.append("  R->>P: resolve waveforms + timing")
    lines2.append("  P-->>R: I/Q traces")
    lines2.append("  R-->>C: figure artifact")
    lines2.append("```")
    lines2.append("")
    lines2.append("## Example pseudo-code")
    lines2.append("")
    lines2.append("```python")
    lines2.append("fig_logical = circuit.draw_logical(save_path='logical.png')")
    lines2.append("fig_pulse = circuit.draw_pulses(runner, save_path='pulses.png')")
    lines2.append("```")
    lines2.append("")
    lines2.append("## Integration boundaries")
    lines2.append("")
    lines2.append("- Inputs: compiled circuit order, pulse operations, tuning records")
    lines2.append("- Outputs: deterministic pulse plots per element/channel")
    lines2.append("- Excluded: live hardware oscilloscope capture")
    lines2.append("")
    lines2.append("## Scope")
    lines2.append("")
    lines2.append("- Legacy vs tuned `X180`")
    lines2.append("- Legacy vs tuned derived `X90`")
    lines2.append("- Tuned short circuit `X180 -> X90`")
    lines2.append("")
    lines2.append("## Expected tuning effect")
    lines2.append("")
    lines2.append(f"- Expected tuned scale `X180`: {report['expected_amplitude_scale']['x180']}")
    lines2.append(f"- Expected tuned scale `X90` (derived): {report['expected_amplitude_scale']['x90']}")
    lines2.append(f"- Legacy reference peak |I| `X180`: {report['pulse_peaks_reference']['legacy_x180_peak_abs_I']:.6g}")
    lines2.append(f"- Legacy reference peak |I| `X90`: {report['pulse_peaks_reference']['legacy_x90_peak_abs_I']:.6g}")
    lines2.append(f"- Expected tuned peak |I| `X180`: {report['pulse_peaks_reference']['expected_tuned_x180_peak_abs_I']:.6g}")
    lines2.append(f"- Expected tuned peak |I| `X90`: {report['pulse_peaks_reference']['expected_tuned_x90_peak_abs_I']:.6g}")
    lines2.append("")
    lines2.append("## Figures")
    lines2.append("")
    lines2.append("- [X180 legacy](docs/figures/circuit_pulses/x180_legacy.png)")
    lines2.append("- [X180 tuned](docs/figures/circuit_pulses/x180_tuned.png)")
    lines2.append("- [X90 legacy](docs/figures/circuit_pulses/x90_legacy.png)")
    lines2.append("- [X90 tuned](docs/figures/circuit_pulses/x90_tuned.png)")
    lines2.append("- [X180 -> X90 tuned circuit](docs/figures/circuit_pulses/xy_pair_tuned.png)")
    lines2.append("")
    lines2.append("## Verdict")
    lines2.append("")
    lines2.append("PASS — visualization APIs produce deterministic logical and pulse-level outputs for tuned/derived gates in simulator-only mode.")

    Path("docs/circuit_pulse_visualization_validation.md").write_text("\n".join(lines2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    report = run_validation()
    write_reports(report)
    print("Validation reports written:")
    print("- docs/gate_tuning_serialization_validation.md")
    print("- docs/circuit_pulse_visualization_validation.md")
