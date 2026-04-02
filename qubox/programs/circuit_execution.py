from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..core.logging import get_logger
from ..experiments.result import ProgramBuildResult
from .circuit_runner import QuantumCircuit, CircuitRunner

_logger = get_logger(__name__)

SAFE_OPX_CLUSTER = "Cluster_1"


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


def run_compiled_circuit(
    session: Any,
    circuit: QuantumCircuit,
    *,
    cluster: str = SAFE_OPX_CLUSTER,
    run_on_opx: bool = False,
    n_shots: int | None = None,
    execution_kwargs: dict[str, Any] | None = None,
) -> CompiledCircuitExecution:
    requested_cluster = str(cluster).strip()
    if requested_cluster != SAFE_OPX_CLUSTER:
        raise ValueError(
            f"Refusing OPX execution for cluster={requested_cluster!r}. "
            f"Only {SAFE_OPX_CLUSTER!r} is allowed."
        )

    compiler = CircuitRunner(session)
    build = compiler.compile_program(circuit, n_shots=n_shots)
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
            "Expose session.cluster_name and ensure it is Cluster_1."
        )
    if len(cluster_candidates) > 1:
        raise RuntimeError(
            f"Refusing hardware execution because the session exposes multiple cluster names: {cluster_candidates!r}."
        )
    if cluster_candidates[0] != SAFE_OPX_CLUSTER:
        raise RuntimeError(
            f"Refusing hardware execution because the session is bound to {cluster_candidates[0]!r}, "
            f"not {SAFE_OPX_CLUSTER!r}."
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

    run_program = getattr(hardware, "run_program", None)
    if not callable(run_program):
        raise RuntimeError("Session hardware controller does not expose run_program().")

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
