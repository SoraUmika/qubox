from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from qm import generate_qua_script

from . import api as cQED_programs
from .measurement import build_readout_snapshot_from_handle
from .gate_tuning import GateTuningStore

# IR types are now defined in circuit_ir.py; re-exported here for backward compat.
from .circuit_ir import (  # noqa: F401
    _UNSET,
    _stable_payload,
    _stable_text,
    CalibrationReference,
    CircuitBlock,
    CircuitBuildResult,
    ConditionalGate,
    Gate,
    GateCondition,
    MeasurementRecord,
    MeasurementSchema,
    ParameterSource,
    QuantumCircuit,
    StreamSpec,
    SweepAxis,
    SweepSpec,
)



class CircuitRunner:
    """Circuit-based compiler facade (simulator-first).

    This initial implementation intentionally compiles through the same
    program-builder layer used by legacy experiment flows, then validates
    physical fidelity via serialized QUA script comparison.
    """

    def __init__(self, session: Any):
        self.session = session
        store = getattr(session, "gate_tuning_store", None)
        self.gate_tuning_store = store if isinstance(store, GateTuningStore) else GateTuningStore()

    def _apply_gate_tuning(self, circuit: QuantumCircuit) -> QuantumCircuit:
        circuit = circuit.with_stable_gate_names()
        md = dict(circuit.metadata)
        applied: list[dict[str, Any]] = []

        qb_el = md.get("qb_el")
        op = md.get("op")
        if isinstance(qb_el, str) and isinstance(op, str):
            tuned = self.gate_tuning_store.resolve(target=qb_el, operation=op)
            if tuned is not None:
                md.setdefault("tuning", {})
                md["tuning"].update(tuned)
                applied.append(tuned)

        if applied:
            md["tuning_applied"] = applied
        return QuantumCircuit(name=circuit.name, gates=circuit.gates, metadata=md)

    def compile(self, circuit: QuantumCircuit, *, sweep: SweepSpec | None = None) -> CircuitBuildResult:
        """Legacy name-dispatch compiler. Prefer ``CircuitCompiler.compile()`` for new code."""
        import warnings as _w

        _w.warn(
            "CircuitRunner.compile() is a legacy name-dispatch path with 5 hardcoded circuits. "
            "Use CircuitCompiler(session).compile(circuit) for generic gate-lowering compilation.",
            DeprecationWarning,
            stacklevel=2,
        )
        circuit = self._apply_gate_tuning(circuit)
        name = circuit.name.lower().strip()
        if name == "power_rabi":
            return self._compile_power_rabi(circuit, sweep)
        if name == "t1":
            return self._compile_t1(circuit, sweep)
        if name == "readout_ge_discrimination":
            return self._compile_ge(circuit, sweep)
        if name == "readout_butterfly":
            return self._compile_butterfly(circuit, sweep)
        if name == "xy_pair":
            return self._compile_xy_pair(circuit, sweep)
        raise ValueError(f"Unsupported circuit name: {circuit.name!r}")

    def compile_program(self, circuit: QuantumCircuit, *, n_shots: int | None = None):
        from .circuit_compiler import CircuitCompiler

        return CircuitCompiler(self.session).compile(circuit, n_shots=n_shots)

    def visualize_pulses(
        self,
        circuit: QuantumCircuit,
        *,
        sweep: SweepSpec | None = None,
        duration_ns: int = 4000,
        controllers: tuple[str, ...] = ("con1",),
        by_element: bool = True,
        zoom_ns: tuple[float, float] | None = None,
        save_path: str | None = None,
    ):
        import matplotlib.pyplot as plt

        runner = getattr(self.session, "runner", None)
        if runner is None:
            return self._visualize_pulses_from_timing_model(
                circuit,
                zoom_ns=zoom_ns,
                save_path=save_path,
            )

        build = self.compile(circuit, sweep=sweep)
        sim = runner.simulate(build.program, duration=duration_ns, plot=False, controllers=controllers)

        channel_data: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for ctrl in controllers:
            if ctrl not in sim:
                continue
            con = sim[ctrl]
            for name, arr in con.analog.items():
                fs = con.analog_sampling_rate.get(name, 1e9)
                t = (np.arange(len(arr)) / float(fs)) * 1e9
                channel_data[f"{ctrl}:{name}"] = (t, np.asarray(arr))

        if not channel_data:
            raise RuntimeError("No simulated analog channels available for pulse visualization.")

        groups: dict[str, list[str]] = {}
        for ch in channel_data:
            if by_element and ":" in ch:
                element = ch.split(":", 2)[-1].split(":")[0]
                groups.setdefault(element, []).append(ch)
            else:
                groups.setdefault("all", []).append(ch)

        fig, axes = plt.subplots(len(groups), 1, figsize=(11, max(3.0, 2.7 * len(groups))), sharex=True)
        if not isinstance(axes, np.ndarray):
            axes = np.array([axes])

        boundaries_ns = []
        cursor = 0.0
        for gate in circuit.with_stable_gate_names().gates:
            boundaries_ns.append((cursor, gate.instance_name or gate.name))
            cursor += float((gate.duration_clks or 0) * 4)

        for ax, (group, channels) in zip(axes, groups.items()):
            for ch in sorted(channels):
                t, y = channel_data[ch]
                ax.plot(t, y, label=ch, linewidth=1.2)
            for x, name in boundaries_ns:
                if x > 0:
                    ax.axvline(x, color="gray", linestyle="--", alpha=0.25)
                    ax.text(x, 0.95, name, transform=ax.get_xaxis_transform(), fontsize=7, rotation=90, va="top")
            ax.set_ylabel("Amplitude")
            ax.set_title(f"Element: {group}")
            ax.grid(alpha=0.25)
            ax.legend(fontsize=8, loc="upper right")

        axes[-1].set_xlabel("Time (ns)")
        if zoom_ns is not None:
            axes[-1].set_xlim(float(zoom_ns[0]), float(zoom_ns[1]))
        fig.suptitle(f"Compiled Pulse Visualization: {circuit.name}", y=1.02)
        fig.tight_layout()

        if save_path:
            out = Path(save_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(out)
        return fig

    def _visualize_pulses_from_timing_model(
        self,
        circuit: QuantumCircuit,
        *,
        zoom_ns: tuple[float, float] | None = None,
        save_path: str | None = None,
    ):
        import matplotlib.pyplot as plt

        pulse_mgr = getattr(self.session, "pulse_mgr", None)
        if pulse_mgr is None:
            raise RuntimeError("Session has no pulse manager for timing-model pulse visualization.")

        traces: dict[str, dict[str, list[float]]] = {}
        cursor_ns = 0
        boundaries: list[tuple[float, str]] = []

        for gate in circuit.with_stable_gate_names().gates:
            boundaries.append((float(cursor_ns), gate.instance_name or gate.name))
            target = gate.target if isinstance(gate.target, str) else (gate.target[0] if gate.target else "")
            op = str(gate.params.get("op", ""))

            duration_ns = int((gate.duration_clks or 0) * 4)
            i_wave: list[float] = []
            q_wave: list[float] = []

            if target and op:
                pulse = pulse_mgr.get_pulseOp_by_element_op(target, op, strict=False)
                if pulse is not None:
                    i_wave = list(np.asarray(getattr(pulse, "I_wf", []) or [], dtype=float))
                    q_wave = list(np.asarray(getattr(pulse, "Q_wf", []) or [], dtype=float))
                    tuned = self.gate_tuning_store.resolve(target=target, operation=op)
                    if tuned is not None:
                        scale = float(tuned.get("amplitude_scale", 1.0))
                        i_wave = [v * scale for v in i_wave]
                        q_wave = [v * scale for v in q_wave]
                    duration_ns = max(duration_ns, len(i_wave), len(q_wave))

            duration_ns = max(duration_ns, 4)
            if not i_wave:
                i_wave = [0.0] * duration_ns
            if not q_wave:
                q_wave = [0.0] * duration_ns

            if len(i_wave) < duration_ns:
                i_wave.extend([0.0] * (duration_ns - len(i_wave)))
            if len(q_wave) < duration_ns:
                q_wave.extend([0.0] * (duration_ns - len(q_wave)))

            elem = target or "global"
            traces.setdefault(elem, {"I": [], "Q": []})
            traces[elem]["I"].extend(i_wave)
            traces[elem]["Q"].extend(q_wave)

            cursor_ns += duration_ns

        if not traces:
            raise RuntimeError("No pulse traces available from timing model.")

        fig, axes = plt.subplots(len(traces), 1, figsize=(11, max(3.0, 2.7 * len(traces))), sharex=True)
        if not isinstance(axes, np.ndarray):
            axes = np.array([axes])

        for ax, (elem, comps) in zip(axes, sorted(traces.items())):
            t = np.arange(len(comps["I"]), dtype=float)
            ax.plot(t, np.asarray(comps["I"]), label=f"{elem}:I", linewidth=1.2)
            ax.plot(t, np.asarray(comps["Q"]), label=f"{elem}:Q", linewidth=1.2)
            for x, name in boundaries:
                if x > 0:
                    ax.axvline(x, color="gray", linestyle="--", alpha=0.25)
                    ax.text(x, 0.95, name, transform=ax.get_xaxis_transform(), fontsize=7, rotation=90, va="top")
            ax.set_ylabel("Amplitude")
            ax.set_title(f"Element: {elem} (compiled timing model)")
            ax.grid(alpha=0.25)
            ax.legend(fontsize=8, loc="upper right")

        axes[-1].set_xlabel("Time (ns)")
        if zoom_ns is not None:
            axes[-1].set_xlim(float(zoom_ns[0]), float(zoom_ns[1]))
        fig.suptitle(f"Compiled Pulse Visualization (timing-model fallback): {circuit.name}", y=1.02)
        fig.tight_layout()

        if save_path:
            out = Path(save_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(out)
        return fig

    def serialize(self, build: CircuitBuildResult) -> str:
        cfg = self.session.config_engine.build_qm_config()
        return generate_qua_script(build.program, cfg)

    @staticmethod
    def _weight_keys(weight_sets: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
        ordered: list[str] = []
        for spec in weight_sets[:2]:
            for item in spec:
                if item not in ordered:
                    ordered.append(item)
        return tuple(ordered or ("cos", "sin", "minus_sin"))

    def _readout_handle(
        self,
        *,
        alias: str = "resonator",
        operation: str = "readout",
        drive_frequency: float | None = None,
        weight_sets: tuple[tuple[str, ...], ...] | None = None,
    ):
        readout = self.session.readout_handle(alias=alias, operation=operation)
        pulse_info = self.session.pulse_mgr.get_pulseOp_by_element_op(readout.element, operation, strict=False)
        resolved_weight_sets = weight_sets or tuple(
            tuple(spec) if isinstance(spec, (list, tuple)) else (str(spec),)
            for spec in (readout.demod_weight_sets or ())
        )
        if not resolved_weight_sets:
            resolved_weight_sets = (("cos", "sin"), ("minus_sin", "cos"))
        binding = replace(
            readout.binding,
            pulse_op=pulse_info or readout.binding.pulse_op,
            active_op=operation,
            demod_weight_sets=[list(spec) for spec in resolved_weight_sets],
            drive_frequency=(
                float(drive_frequency)
                if drive_frequency is not None
                else readout.binding.drive_frequency
            ),
        )
        cal = replace(
            readout.cal,
            drive_frequency=(
                float(drive_frequency)
                if drive_frequency is not None
                else readout.cal.drive_frequency
            ),
            weight_keys=self._weight_keys(resolved_weight_sets),
            weight_length=(
                getattr(pulse_info, "length", None)
                or getattr(readout.cal, "weight_length", None)
            ),
        )
        return replace(
            readout,
            binding=binding,
            cal=cal,
            operation=operation,
            demod_weight_sets=resolved_weight_sets,
        )

    def _compile_power_rabi(self, circuit: QuantumCircuit, sweep: SweepSpec | None) -> CircuitBuildResult:
        params = dict(circuit.metadata)
        qb_el = params["qb_el"]
        op = params.get("op", "ge_ref_r180")
        qb_therm_clks = int(params["qb_therm_clks"])
        pulse_clock_len = int(params["pulse_clock_len"])
        truncate_clks = params.get("truncate_clks", None)
        n_avg = int(params["n_avg"])

        if sweep is None or not sweep.axes:
            raise ValueError("power_rabi requires one sweep axis for gains")
        gains = np.asarray(sweep.axes[0].values, dtype=float)
        tuning = params.get("tuning") or {}
        gain_scale = float(tuning.get("amplitude_scale", 1.0))
        gains = gains * gain_scale
        params["applied_gain_scale"] = gain_scale

        readout = self._readout_handle()
        prog = cQED_programs.power_rabi(
            pulse_clock_len,
            gains,
            qb_therm_clks,
            op,
            truncate_clks,
            n_avg,
            qb_el=qb_el,
            bindings=getattr(self.session, "bindings", None),
            readout=readout,
        )
        snapshot = build_readout_snapshot_from_handle(readout)
        return CircuitBuildResult(name="PowerRabi", program=prog, sweep=sweep, readout_snapshot=snapshot, metadata=params)

    def _compile_xy_pair(self, circuit: QuantumCircuit, sweep: SweepSpec | None) -> CircuitBuildResult:
        params = dict(circuit.metadata)
        qb_el = params["qb_el"]
        if "qb_therm_clks" not in params:
            raise ValueError(
                "CircuitRunner.xy_pair requires 'qb_therm_clks' in circuit metadata. "
                "Resolve it from calibration or pass it explicitly before compiling."
            )
        qb_therm_clks = int(params["qb_therm_clks"])
        n_avg = int(params.get("n_avg", 64))

        op_a = str(params.get("op_a", "x180"))
        op_b = str(params.get("op_b", "x90"))
        tuning = params.get("tuning") or {}
        params["applied_gain_scale"] = float(tuning.get("amplitude_scale", 1.0))

        readout = self._readout_handle()
        prog = cQED_programs.all_xy(qb_el, [(op_a, op_b)], qb_therm_clks, n_avg, readout=readout)
        snapshot = build_readout_snapshot_from_handle(readout)
        return CircuitBuildResult(
            name="XYPair",
            program=prog,
            sweep=sweep or SweepSpec(averaging=n_avg),
            readout_snapshot=snapshot,
            metadata=params,
        )

    def _compile_t1(self, circuit: QuantumCircuit, sweep: SweepSpec | None) -> CircuitBuildResult:
        params = dict(circuit.metadata)
        qb_el = params["qb_el"]
        r180 = params.get("r180", "x180")
        qb_therm_clks = int(params["qb_therm_clks"])
        n_avg = int(params["n_avg"])

        if sweep is None or not sweep.axes:
            raise ValueError("t1 requires one sweep axis for wait cycles")
        wait_cycles = np.asarray(sweep.axes[0].values, dtype=int)

        readout = self._readout_handle()
        prog = cQED_programs.T1_relaxation(
            r180,
            wait_cycles,
            qb_therm_clks,
            n_avg,
            qb_el=qb_el,
            bindings=getattr(self.session, "bindings", None),
            readout=readout,
        )
        snapshot = build_readout_snapshot_from_handle(readout)
        return CircuitBuildResult(name="T1Relaxation", program=prog, sweep=sweep, readout_snapshot=snapshot, metadata=params)

    def _compile_ge(self, circuit: QuantumCircuit, sweep: SweepSpec | None) -> CircuitBuildResult:
        params = dict(circuit.metadata)
        ro_el = params["ro_el"]
        qb_el = params["qb_el"]
        measure_op = params["measure_op"]
        r180 = params.get("r180", "x180")
        qb_therm_clks = int(params["qb_therm_clks"])
        n_samples = int(params["n_samples"])
        drive_frequency = float(params["drive_frequency"])

        pulse_info = self.session.pulse_mgr.get_pulseOp_by_element_op(ro_el, measure_op, strict=False)
        if pulse_info is None:
            raise RuntimeError(f"Missing pulse mapping for ro_el={ro_el!r}, op={measure_op!r}")

        weight_mapping = pulse_info.int_weights_mapping or {}
        is_readout = (pulse_info.op == "readout")
        op_prefix = "" if is_readout else f"{pulse_info.op}_"
        default_keys = (f"{op_prefix}cos" if op_prefix else "cos", f"{op_prefix}sin" if op_prefix else "sin", f"{op_prefix}minus_sin" if op_prefix else "minus_sin")
        base_weight_keys = params.get("base_weight_keys") or default_keys
        cos_key, sin_key, m_sin_key = base_weight_keys

        if cos_key not in weight_mapping or sin_key not in weight_mapping or m_sin_key not in weight_mapping:
            raise RuntimeError(
                f"Integration weights not found for keys={base_weight_keys!r}. Available={sorted(weight_mapping.keys())}"
            )

        readout = self._readout_handle(
            alias=ro_el,
            operation=measure_op,
            drive_frequency=drive_frequency,
            weight_sets=((cos_key, sin_key), (m_sin_key, cos_key)),
        )

        prog = cQED_programs.iq_blobs(
            ro_el,
            qb_el,
            r180,
            qb_therm_clks,
            n_samples,
            bindings=getattr(self.session, "bindings", None),
            readout=readout,
        )
        snapshot = build_readout_snapshot_from_handle(readout)
        return CircuitBuildResult(name="ReadoutGEDiscrimination", program=prog, sweep=sweep or SweepSpec(averaging=n_samples), readout_snapshot=snapshot, metadata=params)

    def _compile_butterfly(self, circuit: QuantumCircuit, sweep: SweepSpec | None) -> CircuitBuildResult:
        params = dict(circuit.metadata)
        qb_el = params["qb_el"]
        r180 = params.get("r180", "x180")
        n_samples = int(params["n_samples"])
        max_trials = int(params.get("M0_MAX_TRIALS", 16))
        prep_policy = str(params["prep_policy"])
        prep_kwargs = dict(params.get("prep_kwargs") or {})

        readout = self._readout_handle()
        prog = cQED_programs.readout_butterfly_measurement(
            qb_el,
            r180,
            prep_policy,
            prep_kwargs,
            max_trials,
            n_samples,
            bindings=getattr(self.session, "bindings", None),
            readout=readout,
        )
        snapshot = build_readout_snapshot_from_handle(readout)
        return CircuitBuildResult(name="ReadoutButterflyMeasurement", program=prog, sweep=sweep or SweepSpec(averaging=n_samples), readout_snapshot=snapshot, metadata=params)

    @staticmethod
    def _diff_scripts(legacy_script: str, new_script: str) -> dict[str, Any]:
        if legacy_script == new_script:
            return {"status": "identical", "notes": []}

        legacy_lines = [ln.rstrip() for ln in legacy_script.splitlines() if ln.strip()]
        new_lines = [ln.rstrip() for ln in new_script.splitlines() if ln.strip()]

        if len(legacy_lines) == len(new_lines) and sorted(legacy_lines) == sorted(new_lines):
            return {
                "status": "functionally_equivalent_with_timing_notes",
                "notes": ["Line ordering differs but statement multiset matches."],
            }

        return {
            "status": "behaviorally_different",
            "notes": [
                f"Legacy lines={len(legacy_lines)}, New lines={len(new_lines)}",
                "Instruction bodies differ beyond benign reorderings.",
            ],
        }


def make_power_rabi_circuit(*, qb_el: str, qb_therm_clks: int, pulse_clock_len: int, n_avg: int, op: str = "ge_ref_r180", truncate_clks: int | None = None, gains: np.ndarray | None = None) -> tuple[QuantumCircuit, SweepSpec]:
    gains = np.asarray(gains if gains is not None else np.linspace(-0.2, 0.2, 9), dtype=float)
    circuit = QuantumCircuit(
        name="power_rabi",
        gates=(
            Gate("play", target=qb_el, params={"op": op, "amp": "gain"}),
            Gate("measure", target="readout", params={"kind": "iq"}),
        ),
        metadata={
            "qb_el": qb_el,
            "qb_therm_clks": int(qb_therm_clks),
            "pulse_clock_len": int(pulse_clock_len),
            "n_avg": int(n_avg),
            "op": op,
            "truncate_clks": truncate_clks,
        },
    )
    sweep = SweepSpec(axes=(SweepAxis(key="gains", values=gains),), averaging=int(n_avg))
    return circuit, sweep


def make_t1_circuit(*, qb_el: str, qb_therm_clks: int, n_avg: int, waits_clks: np.ndarray, r180: str = "x180") -> tuple[QuantumCircuit, SweepSpec]:
    waits_clks = np.asarray(waits_clks, dtype=int)
    circuit = QuantumCircuit(
        name="t1",
        gates=(
            Gate("play", target=qb_el, params={"op": r180}),
            Gate("wait", target=qb_el, params={"clks": "delay"}),
            Gate("measure", target="readout", params={"kind": "iq"}),
        ),
        metadata={
            "qb_el": qb_el,
            "qb_therm_clks": int(qb_therm_clks),
            "n_avg": int(n_avg),
            "r180": r180,
        },
    )
    sweep = SweepSpec(axes=(SweepAxis(key="wait_cycles", values=waits_clks),), averaging=int(n_avg))
    return circuit, sweep


def make_ge_discrimination_circuit(*, ro_el: str, qb_el: str, measure_op: str, drive_frequency: float, qb_therm_clks: int, n_samples: int, r180: str = "x180", base_weight_keys: tuple[str, str, str] | None = None) -> tuple[QuantumCircuit, SweepSpec]:
    circuit = QuantumCircuit(
        name="readout_ge_discrimination",
        gates=(Gate("measure", target=ro_el, params={"kind": "discriminate"}),),
        metadata={
            "ro_el": ro_el,
            "qb_el": qb_el,
            "measure_op": measure_op,
            "drive_frequency": float(drive_frequency),
            "qb_therm_clks": int(qb_therm_clks),
            "n_samples": int(n_samples),
            "r180": r180,
            "base_weight_keys": base_weight_keys,
        },
    )
    return circuit, SweepSpec(axes=(), averaging=int(n_samples))


def make_butterfly_circuit(*, qb_el: str, n_samples: int, prep_policy: str, prep_kwargs: dict[str, Any], r180: str = "x180", max_trials: int = 16) -> tuple[QuantumCircuit, SweepSpec]:
    circuit = QuantumCircuit(
        name="readout_butterfly",
        gates=(Gate("measure", target="readout", params={"kind": "butterfly"}),),
        metadata={
            "qb_el": qb_el,
            "n_samples": int(n_samples),
            "prep_policy": prep_policy,
            "prep_kwargs": dict(prep_kwargs),
            "r180": r180,
            "M0_MAX_TRIALS": int(max_trials),
        },
    )
    return circuit, SweepSpec(axes=(), averaging=int(n_samples))


def make_xy_pair_circuit(
    *,
    qb_el: str,
    qb_therm_clks: int,
    n_avg: int = 64,
    op_a: str = "x180",
    op_b: str = "x90",
    name_a: str | None = None,
    name_b: str | None = None,
) -> tuple[QuantumCircuit, SweepSpec]:
    circuit = QuantumCircuit(
        name="xy_pair",
        gates=(
            Gate("X", target=qb_el, params={"family": "X", "op": op_a, "angle": "pi"}, duration_clks=16, instance_name=name_a),
            Gate("X", target=qb_el, params={"family": "X", "op": op_b, "angle": "pi/2"}, duration_clks=8, instance_name=name_b),
            Gate("measure", target="readout", params={"kind": "iq"}, duration_clks=8),
        ),
        metadata={
            "qb_el": qb_el,
            "qb_therm_clks": int(qb_therm_clks),
            "n_avg": int(n_avg),
            "op_a": op_a,
            "op_b": op_b,
        },
    )
    return circuit, SweepSpec(axes=(), averaging=int(n_avg))
