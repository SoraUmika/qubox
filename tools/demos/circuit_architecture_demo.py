from __future__ import annotations

from pathlib import Path
from typing import Any

from qubox.programs.circuit_execution import run_compiled_circuit
from qubox.programs.circuit_protocols import EchoProtocol, RamseyProtocol


def demo_gate_protocol_circuits(
    session: Any,
    *,
    tau_clks: int = 12,
    n_shots: int = 64,
    save_dir: str | Path | None = None,
):
    """Build, display, and compile Ramsey/Echo circuits without running hardware."""

    circuits = (
        RamseyProtocol(tau_clks=tau_clks, n_shots=n_shots).build(),
        EchoProtocol(tau_clks=tau_clks, n_shots=n_shots).build(),
    )

    output_dir = Path(save_dir) if save_dir is not None else None
    results = []
    for circuit in circuits:
        execution = run_compiled_circuit(session, circuit, run_on_opx=False)
        print(f"=== {circuit.name} ===")
        print(execution.diagram_text, end="")
        print(execution.build.metadata["resolution_report_text"], end="")

        figure = circuit.draw(include_gate_names=True)
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            figure.savefig(output_dir / f"{circuit.name}_diagram.png")
        results.append(execution)
    return results


if __name__ == "__main__":
    raise SystemExit(
        "Import demo_gate_protocol_circuits(session, ...) from an existing qubox session. "
        "This script defaults to compile/display only and does not auto-connect to hardware."
    )
