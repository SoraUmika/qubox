from __future__ import annotations

from pathlib import Path

from .circuit_ir import CircuitBlock, Gate, MeasurementRecord, QuantumCircuit


def _measurement_records(circuit: QuantumCircuit) -> dict[str, MeasurementRecord]:
    return {record.key: record for record in circuit.measurement_schema.records}


def _fit_cell(text: str, width: int, *, align: str = "center", fill: str = " ") -> str:
    raw = " ".join(str(text).split())
    if len(raw) > width:
        raw = raw[: max(0, width - 3)] + "..."
    if align == "left":
        return raw.ljust(width, fill)
    if align == "right":
        return raw.rjust(width, fill)
    return raw.center(width, fill)


def _measure_record_for_gate(circuit: QuantumCircuit, gate: Gate, *, gate_index: int) -> MeasurementRecord | None:
    key = str(gate.params.get("measure_key") or gate.instance_name or gate.resolved_name(index=gate_index))
    return _measurement_records(circuit).get(key)


def _block_label(block: CircuitBlock) -> str:
    mode = str(block.metadata.get("mode") or "").strip().lower()
    if mode == "analysis_only":
        return f"{block.label} [analysis-only]"
    if mode == "real_time_branching_requested":
        return f"{block.label} [rt-branch requested]"
    return block.label


def _base_gate_summary(circuit: QuantumCircuit, gate: Gate, *, gate_index: int) -> str:
    gate_type = gate.gate_type
    if gate_type in {"measure", "measure_iq"}:
        record = _measure_record_for_gate(circuit, gate, gate_index=gate_index)
        key = str(gate.params.get("measure_key") or gate.instance_name or gate.resolved_name(index=gate_index))
        stream_text = "I,Q"
        if record is not None:
            stream_text = ",".join(stream.name for stream in record.streams)
        return f"MeasureIQ {key}[{stream_text}]"
    if gate_type in {"idle", "wait"}:
        duration = gate.duration_clks if gate.duration_clks is not None else gate.params.get("duration_clks", "?")
        return f"Idle {duration} clks"
    if gate_type == "frame_update":
        parts: list[str] = ["FrameUpdate"]
        if "phase" in gate.params:
            parts.append(f"phase={gate.params['phase']}")
        if "detune" in gate.params:
            parts.append(f"detune={gate.params['detune']}")
        return " ".join(parts)
    if gate_type in {"play", "play_pulse"}:
        op = gate.params.get("op", gate.params.get("operation", gate.gate_type))
        return f"Play {op}"
    if gate_type == "qubit_rotation":
        op = gate.params.get("op")
        angle = gate.params.get("angle")
        if op is not None:
            return f"QRot {op}"
        if angle is not None:
            return f"QRot theta={angle}"
        return "QRot"
    if gate_type == "displacement":
        alpha = gate.params.get("alpha", "?")
        return f"Displacement alpha={alpha}"
    if gate_type == "sqr":
        return "SQR"
    op = gate.params.get("op")
    if op is not None:
        return f"{gate_type} {op}"
    return gate_type


def _gate_summary(circuit: QuantumCircuit, gate: Gate, *, gate_index: int) -> str:
    summary = _base_gate_summary(circuit, gate, gate_index=gate_index)
    if gate.condition is not None:
        return f"IF {gate.condition.to_text()} -> {summary}"
    return summary


def _gate_plot_label(
    circuit: QuantumCircuit,
    gate: Gate,
    *,
    gate_index: int,
    include_gate_names: bool,
) -> str:
    summary = _gate_summary(circuit, gate, gate_index=gate_index)
    if include_gate_names and gate.instance_name:
        return f"{summary}\n{gate.instance_name}"
    return summary


def _block_cells(block: CircuitBlock, *, n_steps: int, cell_width: int) -> list[str]:
    cells = [""] * n_steps
    start = max(0, int(block.start))
    stop = min(n_steps, int(block.stop))
    label = _block_label(block)
    if stop <= start:
        return cells
    if stop - start == 1:
        cells[start] = _fit_cell(f"[{label}]", cell_width)
        return cells
    cells[start] = _fit_cell(f"[{label}", cell_width, align="left", fill="-")
    for index in range(start + 1, stop - 1):
        cells[index] = "-" * cell_width
    cells[stop - 1] = _fit_cell("]", cell_width, align="right", fill="-")
    return cells


def _analysis_rows(circuit: QuantumCircuit, *, n_steps: int) -> list[tuple[str, list[str]]]:
    rows: list[tuple[str, list[str]]] = []
    key_to_index: dict[str, int] = {}
    for index, gate in enumerate(circuit.gates):
        if gate.gate_type in {"measure", "measure_iq"}:
            key = str(gate.params.get("measure_key") or gate.instance_name or gate.resolved_name(index=index))
            key_to_index[key] = index

    for block in circuit.blocks:
        analysis_steps = block.metadata.get("analysis_steps") or []
        if not analysis_steps:
            continue
        cells = [""] * n_steps
        for step in analysis_steps:
            measure_key = str(step.get("measure_key") or "").strip()
            if not measure_key or measure_key not in key_to_index:
                continue
            state_output = step.get("state_output") or f"{measure_key}.state"
            action = step.get("action") or "external action"
            cells[key_to_index[measure_key]] = f"derive_state -> {state_output}; {action}"
        rows.append((f"{block.label}:analysis", cells))
    return rows


def _analysis_lines(circuit: QuantumCircuit) -> list[str]:
    lines: list[str] = []
    for block in circuit.blocks:
        for step in block.metadata.get("analysis_steps") or []:
            measure_key = str(step.get("measure_key") or "").strip()
            if not measure_key:
                continue
            state_output = step.get("state_output") or f"{measure_key}.state"
            action = step.get("action") or "external action"
            lines.append(
                f"- {block.label}: MeasureIQ {measure_key} -> derive_state({state_output}) -> {action}"
            )
    return lines


def _branch_lines(circuit: QuantumCircuit) -> list[str]:
    lines: list[str] = []
    for index, gate in enumerate(circuit.gates):
        if gate.condition is None:
            continue
        gate_name = gate.instance_name or gate.resolved_name(index=index)
        lines.append(f"- {gate_name}: IF {gate.condition.to_text()} -> {_base_gate_summary(circuit, gate, gate_index=index)}")
    return lines


def circuit_to_diagram_text(circuit: QuantumCircuit, *, cell_width: int = 20) -> str:
    circuit = circuit.with_stable_gate_names()
    lanes = circuit.lane_names()
    n_steps = max(1, len(circuit.gates))
    analysis_rows = _analysis_rows(circuit, n_steps=n_steps)
    label_width = max(
        [
            8,
            len("timeline"),
            *(len(lane) for lane in lanes),
            *(len(_block_label(block)) for block in circuit.blocks or ()),
            *(len(label) for label, _ in analysis_rows),
        ]
    )

    def _row(label: str, cells: list[str]) -> str:
        rendered = [_fit_cell(cell, cell_width, align="left") if cell else (" " * cell_width) for cell in cells]
        return f"{label:<{label_width}}|" + "|".join(rendered) + "|"

    rows = [f"diagram: {circuit.name}"]
    rows.append(_row("step", [f"{i:02d}" for i in range(n_steps)]))
    for block in circuit.blocks:
        rows.append(_row(_block_label(block), _block_cells(block, n_steps=n_steps, cell_width=cell_width)))

    for lane in lanes:
        lane_cells = [""] * n_steps
        for index, gate in enumerate(circuit.gates):
            if lane in gate.targets:
                lane_cells[index] = _gate_summary(circuit, gate, gate_index=index)
        rows.append(_row(lane, lane_cells))

    for label, cells in analysis_rows:
        rows.append(_row(label, cells))

    if circuit.blocks:
        rows.append("blocks:")
        for block in circuit.blocks:
            lane_text = ",".join(block.lanes) if block.lanes else "<inferred>"
            rows.append(
                f"- {_block_label(block)}: type={block.block_type} gates=[{int(block.start):02d},{int(block.stop):02d}) "
                f"lanes={lane_text}"
            )

    analysis_lines = _analysis_lines(circuit)
    if analysis_lines:
        rows.append("analysis:")
        rows.extend(analysis_lines)

    branch_lines = _branch_lines(circuit)
    if branch_lines:
        rows.append("branches:")
        rows.extend(branch_lines)

    warnings = list(circuit.metadata.get("warnings", []))
    if warnings:
        rows.append("warnings:")
        rows.extend(f"- {warning}" for warning in warnings)

    rows.append("measurement_schema:")
    rows.extend(circuit.measurement_schema.to_text().splitlines()[1:] if circuit.measurement_schema.records else ["- []"])
    return "\n".join(rows) + "\n"


def draw_circuit(
    circuit: QuantumCircuit,
    *,
    figsize: tuple[float, float] | None = None,
    save_path: str | None = None,
    include_gate_names: bool = False,
):
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    circuit = circuit.with_stable_gate_names()
    lanes = circuit.lane_names()
    if not lanes:
        raise ValueError("Circuit has no target lanes to draw.")

    n_steps = max(1, len(circuit.gates))
    if figsize is None:
        figsize = (max(10.0, 1.8 * n_steps), max(3.6, 1.5 * len(lanes)))

    fig, ax = plt.subplots(figsize=figsize)
    y_positions = {lane: (len(lanes) - 1 - index) for index, lane in enumerate(lanes)}

    for lane, y in y_positions.items():
        ax.hlines(y=y, xmin=0.4, xmax=n_steps + 0.6, color="#64748b", linewidth=1.0, zorder=0)
        ax.text(0.1, y, lane, va="center", ha="right", fontsize=10, color="#0f172a")

    palette = {
        "idle": ("#e2e8f0", "#475569"),
        "wait": ("#e2e8f0", "#475569"),
        "measure": ("#fde68a", "#92400e"),
        "measure_iq": ("#fde68a", "#92400e"),
        "frame_update": ("#bfdbfe", "#1d4ed8"),
        "play": ("#ddd6fe", "#6d28d9"),
        "play_pulse": ("#ddd6fe", "#6d28d9"),
        "qubit_rotation": ("#dbeafe", "#1d4ed8"),
        "displacement": ("#ccfbf1", "#0f766e"),
        "sqr": ("#fecdd3", "#be123c"),
    }

    for block in circuit.blocks:
        if block.lanes:
            block_lanes = [lane for lane in block.lanes if lane in y_positions]
        else:
            block_lanes = []
            for gate in circuit.gates[block.start:block.stop]:
                for lane in gate.targets:
                    if lane in y_positions and lane not in block_lanes:
                        block_lanes.append(lane)
        if not block_lanes:
            block_lanes = list(lanes)

        y_values = [y_positions[lane] for lane in block_lanes]
        y_min = min(y_values) - 0.48
        y_max = max(y_values) + 0.48
        x0 = max(0.5, float(block.start) + 0.52)
        width = max(0.7, float(block.stop - block.start) - 0.04)
        analysis_only = block.metadata.get("mode") == "analysis_only"
        rect = FancyBboxPatch(
            (x0, y_min),
            width,
            y_max - y_min,
            boxstyle="round,pad=0.04,rounding_size=0.08",
            linewidth=1.2,
            edgecolor="#7c2d12" if analysis_only else "#0f172a",
            facecolor="#fed7aa" if analysis_only else "#cbd5e1",
            alpha=0.15,
            linestyle="--" if analysis_only else "-",
            zorder=0.2,
        )
        ax.add_patch(rect)
        ax.text(
            x0 + 0.08,
            y_max + 0.08,
            _block_label(block),
            ha="left",
            va="bottom",
            fontsize=10,
            color="#7c2d12" if analysis_only else "#0f172a",
        )

    for index, gate in enumerate(circuit.gates, start=1):
        facecolor, edgecolor = palette.get(gate.gate_type, ("#f8fafc", "#334155"))
        label = _gate_plot_label(
            circuit,
            gate,
            gate_index=index - 1,
            include_gate_names=include_gate_names,
        )
        for target in gate.targets:
            y = y_positions[target]
            rect = FancyBboxPatch(
                (index - 0.38, y - 0.26),
                0.76,
                0.52,
                boxstyle="round,pad=0.02,rounding_size=0.06",
                linewidth=1.3,
                edgecolor=edgecolor,
                facecolor=facecolor,
                linestyle="--" if gate.condition is not None else "-",
                zorder=1.0,
            )
            ax.add_patch(rect)
            ax.text(
                index,
                y,
                label,
                ha="center",
                va="center",
                fontsize=8,
                color="#0f172a",
                zorder=1.2,
            )

    top_y = len(lanes) - 0.2
    for block in circuit.blocks:
        analysis_steps = block.metadata.get("analysis_steps") or []
        for step in analysis_steps:
            measure_key = str(step.get("measure_key") or "").strip()
            action = step.get("action") or "external action"
            for gate_index, gate in enumerate(circuit.gates, start=1):
                gate_key = str(
                    gate.params.get("measure_key")
                    or gate.instance_name
                    or gate.resolved_name(index=gate_index - 1)
                )
                if gate_key != measure_key:
                    continue
                ax.text(
                    gate_index,
                    top_y + 0.25,
                    f"analysis-only\n{step.get('state_output')}\n{action}",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                    color="#9a3412",
                    zorder=1.3,
                )

    ax.set_xlim(-0.1, n_steps + 0.9)
    ax.set_ylim(-0.8, len(lanes) + 0.6)
    ax.set_xticks(range(1, n_steps + 1))
    ax.set_xticklabels([f"{index:02d}" for index in range(n_steps)])
    ax.set_yticks([])
    ax.set_xlabel("Gate order")
    ax.set_title(f"Circuit Diagram: {circuit.name}")
    ax.grid(axis="x", alpha=0.15)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    fig.tight_layout()

    if save_path:
        path = Path(save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path)

    return fig
