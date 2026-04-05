from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.logging import get_logger
from ..experiments.result import ProgramBuildResult
from .circuit_compiler import CircuitCompiler
from .circuit_ir import QuantumCircuit

_logger = get_logger(__name__)

DEFAULT_OPX_CLUSTER = "Cluster_2"


@dataclass(frozen=True)
class CompiledCircuitExecution:
    build: ProgramBuildResult
    diagram_text: str
    cluster_name: str
    dry_run: bool
    connection: dict[str, Any]
    run_result: Any = None


def _resolve_cluster_candidates(session: Any) -> list[str]:
    candidates: list[str] = []
    for obj in (
        session,
        getattr(session, "hw", None),
        getattr(session, "hardware", None),
        getattr(session, "quaProgMngr", None),
        getattr(session, "_qmm", None),
    ):
        if obj is None:
            continue
        for attr_name in ("cluster_name", "_cluster_name"):
            value = getattr(obj, attr_name, None)
            if value is not None:
                text = str(value).strip()
                if text and text not in candidates:
                    candidates.append(text)
    return candidates


def _resolve_qop_host(session: Any) -> str | None:
    config_engine = getattr(session, "config_engine", None)
    extras = getattr(config_engine, "hardware_extras", None)
    if isinstance(extras, dict):
        host = extras.get("qop_ip")
        if host:
            return str(host)
    return None


def _resolve_runner(session: Any) -> Any:
    runner = getattr(session, "runner", None)
    if runner is not None:
        return runner
    session_manager = getattr(session, "session_manager", None)
    if session_manager is not None:
        return getattr(session_manager, "runner", None)
    return None


def run_compiled_circuit(
    session: Any,
    circuit: QuantumCircuit,
    *,
    cluster: str = DEFAULT_OPX_CLUSTER,
    run_on_opx: bool = False,
    n_shots: int | None = None,
    execution_kwargs: dict[str, Any] | None = None,
) -> CompiledCircuitExecution:
    requested_cluster = str(cluster).strip()
    if not requested_cluster:
        raise ValueError(
            "Refusing OPX execution because the requested cluster is empty."
        )

    compiler = CircuitCompiler(session)
    build = compiler.compile(circuit, n_shots=n_shots)
    diagram_text = circuit.to_diagram_text()
    cluster_candidates = _resolve_cluster_candidates(session)
    connection = {
        "requested_cluster": requested_cluster,
        "session_clusters": cluster_candidates,
        "qop_ip": _resolve_qop_host(session),
        "run_on_opx": bool(run_on_opx),
    }

    _logger.warning(
        "run_compiled_circuit: requested_cluster=%s session_clusters=%s qop_ip=%s run_on_opx=%s",
        requested_cluster,
        cluster_candidates or ["<unknown>"],
        connection["qop_ip"] or "<unknown>",
        run_on_opx,
    )

    if not run_on_opx:
        return CompiledCircuitExecution(
            build=build,
            diagram_text=diagram_text,
            cluster_name=requested_cluster,
            dry_run=True,
            connection=connection,
            run_result=None,
        )

    if not cluster_candidates:
        raise RuntimeError(
            "Refusing hardware execution because the session cluster is ambiguous. "
            f"Expose session.cluster_name and ensure it is {requested_cluster}."
        )
    if len(cluster_candidates) > 1:
        raise RuntimeError(
            f"Refusing hardware execution because the session exposes multiple cluster names: {cluster_candidates!r}."
        )
    if cluster_candidates[0] != requested_cluster:
        raise RuntimeError(
            f"Refusing hardware execution because the session is bound to {cluster_candidates[0]!r}, "
            f"not {requested_cluster!r}."
        )

    if bool(getattr(session, "simulation_mode", False)):
        raise RuntimeError(
            "Refusing hardware execution because the session is in simulation mode. "
            "Open the session with simulation_mode=False first."
        )

    hardware = getattr(session, "hw", getattr(session, "hardware", getattr(session, "quaProgMngr", None)))
    if hardware is None:
        raise RuntimeError("Session has no hardware controller for OPX execution.")

    qm_handle = getattr(hardware, "qm", None)
    if qm_handle is None:
        raise RuntimeError(
            "Refusing hardware execution because no QM is open on the session hardware controller. "
            "Dry-run remains available with run_on_opx=False."
        )

    set_freq = getattr(hardware, "set_element_fq", None)
    if callable(set_freq):
        for element, freq in sorted((build.resolved_frequencies or {}).items()):
            set_freq(element, float(freq))

    runner = _resolve_runner(session)
    if runner is not None and callable(getattr(runner, "run_program", None)):
        run_program = runner.run_program
    else:
        run_program = getattr(hardware, "run_program", None)
    if not callable(run_program):
        raise RuntimeError(
            "Session does not expose a callable run_program() on either runner or hardware controller."
        )

    result = run_program(
        build.program,
        n_total=build.n_total,
        processors=build.processors,
        **dict(build.run_program_kwargs),
        **dict(execution_kwargs or {}),
    )
    return CompiledCircuitExecution(
        build=build,
        diagram_text=diagram_text,
        cluster_name=requested_cluster,
        dry_run=False,
        connection=connection,
        run_result=result,
    )
