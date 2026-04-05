"""Stage management and checkpoint persistence.

Portable logic for saving and loading experiment-stage checkpoints.
No notebook or shared-session dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from ..devices import SampleRegistry


@dataclass(frozen=True, slots=True)
class WorkflowConfig:
    """Immutable configuration for a multi-stage experiment workflow."""

    registry_base: Path
    sample_id: str
    cooldown_id: str
    qop_ip: str
    cluster_name: str
    legacy_cqed_params_path: Path | None = None


@dataclass(frozen=True, slots=True)
class StageCheckpoint:
    """Typed representation of a persisted stage checkpoint."""

    stage_name: str
    status: str
    summary: str
    sample_id: str
    cooldown_id: str
    created_at_utc: str
    consumed_inputs: dict[str, Any]
    persisted_outputs: dict[str, Any]
    advisory_outputs: dict[str, Any]
    next_stage: str | None
    notes: list[str]
    metrics: dict[str, Any]


def build_workflow_config(
    *,
    registry_base: str | Path,
    sample_id: str,
    cooldown_id: str,
    qop_ip: str,
    cluster_name: str,
    legacy_cqed_params_path: str | Path | None = None,
) -> WorkflowConfig:
    """Construct a :class:`WorkflowConfig`."""
    return WorkflowConfig(
        registry_base=Path(registry_base),
        sample_id=sample_id,
        cooldown_id=cooldown_id,
        qop_ip=qop_ip,
        cluster_name=cluster_name,
        legacy_cqed_params_path=None if legacy_cqed_params_path is None else Path(legacy_cqed_params_path),
    )


def _json_ready(value: Any) -> Any:
    """Recursively convert value to JSON-serialisable primitives."""
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


def get_stage_checkpoint_path(
    *,
    registry_base: str | Path,
    sample_id: str,
    cooldown_id: str,
    stage_name: str,
) -> Path:
    """Return the checkpoint file path for a given stage."""
    registry = SampleRegistry(registry_base)
    runtime_dir = registry.cooldown_path(sample_id, cooldown_id) / "artifacts" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    slug = stage_name.strip().lower().replace(" ", "_")
    return runtime_dir / f"notebook_stage_{slug}.json"


def load_legacy_reference(path: str | Path | None) -> dict[str, Any]:
    """Load a legacy cQED-params reference file, returning ``{}`` if absent."""
    if path is None:
        return {}
    reference_path = Path(path)
    if not reference_path.exists():
        return {}
    try:
        payload = json.loads(reference_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed legacy reference JSON at {reference_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(
            f"Legacy reference {reference_path} must contain a JSON object, got {type(payload).__name__}"
        )
    return payload


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
    """Persist a stage checkpoint to the cooldown runtime artifacts."""
    checkpoint_path = get_stage_checkpoint_path(
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
    """Load a stage checkpoint, returning ``None`` if the file does not exist."""
    checkpoint_path = get_stage_checkpoint_path(
        registry_base=registry_base,
        sample_id=sample_id,
        cooldown_id=cooldown_id,
        stage_name=stage_name,
    )
    if not checkpoint_path.exists():
        return None
    try:
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed stage checkpoint JSON at {checkpoint_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(
            f"Stage checkpoint {checkpoint_path} must contain a JSON object, got {type(payload).__name__}"
        )
    return payload


__all__ = [
    "StageCheckpoint",
    "WorkflowConfig",
    "build_workflow_config",
    "get_stage_checkpoint_path",
    "load_legacy_reference",
    "load_stage_checkpoint",
    "save_stage_checkpoint",
]
