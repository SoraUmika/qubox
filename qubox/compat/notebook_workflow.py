from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

from ..calibration import CalibrationOrchestrator, Patch
from ..devices import SampleRegistry
from ..tools.generators import register_rotations_from_ref_iq
from ..tools.waveforms import drag_gaussian_pulse_waveforms
from .notebook_runtime import (
    close_shared_session,
    get_notebook_session_bootstrap_path,
    get_shared_session,
    require_shared_session,
)


@dataclass(frozen=True, slots=True)
class NotebookWorkflowConfig:
    registry_base: Path
    sample_id: str
    cooldown_id: str
    qop_ip: str
    cluster_name: str
    legacy_cqed_params_path: Path | None = None

    @property
    def bootstrap_path(self) -> Path:
        return get_notebook_session_bootstrap_path(
            sample_id=self.sample_id,
            cooldown_id=self.cooldown_id,
            registry_base=self.registry_base,
        )


@dataclass(slots=True)
class NotebookStageContext:
    workflow: NotebookWorkflowConfig
    stage_name: str
    session: Any
    attr: Any
    bootstrap_path: Path
    checkpoint_path: Path
    legacy_reference: dict[str, Any]
    had_live_session: bool


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return [_json_ready(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    return value


def build_notebook_workflow_config(
    *,
    registry_base: str | Path,
    sample_id: str,
    cooldown_id: str,
    qop_ip: str,
    cluster_name: str,
    legacy_cqed_params_path: str | Path | None = None,
) -> NotebookWorkflowConfig:
    return NotebookWorkflowConfig(
        registry_base=Path(registry_base),
        sample_id=sample_id,
        cooldown_id=cooldown_id,
        qop_ip=qop_ip,
        cluster_name=cluster_name,
        legacy_cqed_params_path=None if legacy_cqed_params_path is None else Path(legacy_cqed_params_path),
    )


def load_legacy_reference(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    reference_path = Path(path)
    if not reference_path.exists():
        return {}
    return json.loads(reference_path.read_text(encoding="utf-8"))


def get_notebook_stage_checkpoint_path(
    *,
    registry_base: str | Path,
    sample_id: str,
    cooldown_id: str,
    stage_name: str,
) -> Path:
    registry = SampleRegistry(registry_base)
    runtime_dir = registry.cooldown_path(sample_id, cooldown_id) / "artifacts" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    slug = stage_name.strip().lower().replace(" ", "_")
    return runtime_dir / f"notebook_stage_{slug}.json"


def open_notebook_stage(
    *,
    stage_name: str,
    registry_base: str | Path,
    sample_id: str,
    cooldown_id: str,
    qop_ip: str,
    cluster_name: str,
    legacy_cqed_params_path: str | Path | None = None,
    force_reopen: bool = False,
    close_existing: bool = True,
) -> NotebookStageContext:
    workflow = build_notebook_workflow_config(
        registry_base=registry_base,
        sample_id=sample_id,
        cooldown_id=cooldown_id,
        qop_ip=qop_ip,
        cluster_name=cluster_name,
        legacy_cqed_params_path=legacy_cqed_params_path,
    )
    live_session = get_shared_session()
    had_live_session = live_session is not None
    if force_reopen and close_existing and live_session is not None:
        close_shared_session()
    session = require_shared_session(
        registry_base=workflow.registry_base,
        sample_id=workflow.sample_id,
        cooldown_id=workflow.cooldown_id,
        qop_ip=workflow.qop_ip,
        cluster_name=workflow.cluster_name,
        force_reopen=force_reopen,
    )
    context_snapshot = getattr(session, "context_snapshot", None)
    attr = context_snapshot() if callable(context_snapshot) else getattr(session, "attributes", None)
    if attr is None:
        raise RuntimeError("Unable to resolve the cQED attribute snapshot from the shared session.")
    return NotebookStageContext(
        workflow=workflow,
        stage_name=stage_name,
        session=session,
        attr=attr,
        bootstrap_path=workflow.bootstrap_path,
        checkpoint_path=get_notebook_stage_checkpoint_path(
            registry_base=workflow.registry_base,
            sample_id=workflow.sample_id,
            cooldown_id=workflow.cooldown_id,
            stage_name=stage_name,
        ),
        legacy_reference=load_legacy_reference(workflow.legacy_cqed_params_path),
        had_live_session=had_live_session,
    )


def save_stage_checkpoint(
    *,
    registry_base: str | Path,
    sample_id: str,
    cooldown_id: str,
    stage_name: str,
    status: str,
    summary: str,
    consumed_inputs: dict[str, Any] | None = None,
    persisted_outputs: dict[str, Any] | None = None,
    advisory_outputs: dict[str, Any] | None = None,
    next_stage: str | None = None,
    notes: Sequence[str] | None = None,
    metrics: dict[str, Any] | None = None,
) -> Path:
    checkpoint_path = get_notebook_stage_checkpoint_path(
        registry_base=registry_base,
        sample_id=sample_id,
        cooldown_id=cooldown_id,
        stage_name=stage_name,
    )
    payload = {
        "stage_name": stage_name,
        "status": status,
        "summary": summary,
        "sample_id": sample_id,
        "cooldown_id": cooldown_id,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "consumed_inputs": consumed_inputs or {},
        "persisted_outputs": persisted_outputs or {},
        "advisory_outputs": advisory_outputs or {},
        "next_stage": next_stage,
        "notes": list(notes or ()),
        "metrics": metrics or {},
    }
    checkpoint_path.write_text(json.dumps(_json_ready(payload), indent=2, sort_keys=True), encoding="utf-8")
    return checkpoint_path


def load_stage_checkpoint(
    *,
    registry_base: str | Path,
    sample_id: str,
    cooldown_id: str,
    stage_name: str,
) -> dict[str, Any] | None:
    checkpoint_path = get_notebook_stage_checkpoint_path(
        registry_base=registry_base,
        sample_id=sample_id,
        cooldown_id=cooldown_id,
        stage_name=stage_name,
    )
    if not checkpoint_path.exists():
        return None
    return json.loads(checkpoint_path.read_text(encoding="utf-8"))


def preview_or_apply_patch_ops(
    session_obj: Any,
    *,
    reason: str,
    proposed_patch_ops: Iterable[dict[str, Any]],
    apply: bool = False,
    print_fn=print,
) -> tuple[Patch | None, dict[str, Any] | None, dict[str, Any] | None]:
    patch_ops = list(proposed_patch_ops)
    if not patch_ops:
        print_fn(f"{reason}: no calibration updates were proposed by the fit.")
        return None, None, None

    patch = Patch(reason=reason)
    for patch_op in patch_ops:
        patch.add(patch_op["op"], **patch_op.get("payload", {}))

    orchestrator = CalibrationOrchestrator(session_obj)
    preview = orchestrator.apply_patch(patch, dry_run=True)
    print_fn(f"{reason} patch preview ({preview['n_updates']} updates):")
    for index, update in enumerate(preview.get("preview", []), start=1):
        print_fn(f"  {index}. {update['op']}: {update['payload']}")

    apply_result = None
    if apply:
        apply_result = orchestrator.apply_patch(patch, dry_run=False)
        print_fn(
            f"Applied patch with {apply_result['n_updates']} updates; "
            f"sync_ok={apply_result['sync_ok']}"
        )
    else:
        print_fn("Patch not applied. Enable the stage apply flag to commit the calibration.")

    return patch, preview, apply_result


def fit_quality_gate(analysis: Any, *, r_squared_min: float = 0.5) -> tuple[bool, str]:
    fit = getattr(analysis, "fit", None)
    if fit is None or not getattr(fit, "params", None):
        return False, "fit produced no parameters"
    if getattr(fit, "success", True) is False:
        return False, "fit reported failure"
    r_squared = getattr(fit, "r_squared", np.nan)
    if np.isfinite(r_squared) and r_squared < r_squared_min:
        return False, f"fit r_squared below threshold: {r_squared:.3f} < {r_squared_min:.3f}"
    return True, "fit quality passed"


def fit_center_inside_window(
    fitted_value_hz: float,
    frequencies_hz: Iterable[float],
    *,
    margin_points: int = 2,
) -> tuple[bool, str]:
    frequencies = np.asarray(list(frequencies_hz), dtype=float)
    if frequencies.size == 0 or not np.isfinite(fitted_value_hz):
        return False, "fit produced no finite center frequency"
    left_guard = frequencies[min(margin_points, frequencies.size - 1)]
    right_guard = frequencies[max(0, frequencies.size - 1 - margin_points)]
    if fitted_value_hz <= left_guard:
        return False, f"fit center is pinned near the low-frequency edge ({fitted_value_hz / 1e6:.3f} MHz)"
    if fitted_value_hz >= right_guard:
        return False, f"fit center is pinned near the high-frequency edge ({fitted_value_hz / 1e6:.3f} MHz)"
    return True, "fit center lies safely inside the scan window"


def ensure_primitive_rotations(
    session_obj: Any,
    *,
    qb_element: str,
    amplitude: float,
    length: int,
    sigma: float,
    alpha: float,
    anharmonicity_hz: float,
    detuning_hz: float = 0.0,
    sampling_rate: float = 1e9,
    required_ops: Sequence[str] = ("x180", "x90"),
    rotations: Sequence[str] = ("ref_r180", "x180", "x90", "xn90", "y180", "y90", "yn90"),
    ref_op: str = "ref_r180",
    persist: bool = True,
    override: bool = True,
    force_register: bool = False,
) -> dict[str, Any]:
    pulse_mgr = session_obj.pulse_mgr
    missing_required_ops: list[str] = []
    for op_name in required_ops:
        try:
            pulse_mgr.get_pulseOp_by_element_op(qb_element, op_name, strict=True)
        except Exception:
            missing_required_ops.append(op_name)

    ref_i_samples, ref_q_samples = drag_gaussian_pulse_waveforms(
        amplitude=float(amplitude),
        length=int(length),
        sigma=float(sigma),
        alpha=float(alpha),
        anharmonicity=float(anharmonicity_hz),
        detuning=float(detuning_hz),
        subtracted=True,
        sampling_rate=float(sampling_rate),
    )

    created_ops: list[str] = []
    if force_register or missing_required_ops:
        pulse_mgr.create_control_pulse(
            element=qb_element,
            op=ref_op,
            length=int(length),
            I_samples=ref_i_samples,
            Q_samples=ref_q_samples,
            override=override,
            persist=persist,
        )
        created_ops = list(
            register_rotations_from_ref_iq(
                pulse_mgr,
                ref_i_samples,
                ref_q_samples,
                element=qb_element,
                rotations=tuple(rotations),
                persist=persist,
                override=override,
            )
        )
        session_obj.burn_pulses(include_volatile=True)

    return {
        "created": bool(force_register or missing_required_ops),
        "created_ops": created_ops,
        "missing_required_ops": missing_required_ops,
        "ref_op": ref_op,
        "ref_i_samples": list(ref_i_samples),
        "ref_q_samples": list(ref_q_samples),
    }


__all__ = [
    "NotebookStageContext",
    "NotebookWorkflowConfig",
    "build_notebook_workflow_config",
    "ensure_primitive_rotations",
    "fit_center_inside_window",
    "fit_quality_gate",
    "get_notebook_stage_checkpoint_path",
    "load_legacy_reference",
    "load_stage_checkpoint",
    "open_notebook_stage",
    "preview_or_apply_patch_ops",
    "save_stage_checkpoint",
]