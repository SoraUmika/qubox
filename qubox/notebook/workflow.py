"""Notebook stage workflow helpers.

Thin wrapper around :mod:`qubox.workflow` that adds shared-session integration
for Jupyter notebook environments.  Core logic (checkpoints, fit gates, patch
preview, pulse seeding) lives in ``qubox.workflow`` and is reusable from
scripts and CI without a notebook kernel.

.. deprecated::
    Direct imports from ``qubox.notebook.workflow`` are still supported but
    new code should prefer ``qubox.workflow`` for portable primitives.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Re-export portable primitives from qubox.workflow
from ..workflow.stages import (  # noqa: F401
    WorkflowConfig,
    build_workflow_config,
    get_stage_checkpoint_path,
    load_legacy_reference,
    load_stage_checkpoint,
    save_stage_checkpoint,
)
from ..workflow.calibration_helpers import preview_or_apply_patch_ops  # noqa: F401
from ..workflow.fit_gates import fit_center_inside_window, fit_quality_gate  # noqa: F401
from ..workflow.pulse_seeding import ensure_primitive_rotations  # noqa: F401

from .runtime import (
    close_shared_session,
    get_notebook_session_bootstrap_path,
    get_shared_session,
    require_shared_session,
)


# ---------------------------------------------------------------------------
# Notebook-specific types (add bootstrap_path via shared session)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class NotebookWorkflowConfig:
    """Immutable configuration for a multi-notebook experiment workflow.

    Extends :class:`~qubox.workflow.WorkflowConfig` with a convenience
    ``bootstrap_path`` property that uses the notebook runtime helpers.
    """

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
    """Context object returned by :func:`open_notebook_stage`."""

    workflow: NotebookWorkflowConfig
    stage_name: str
    session: Any
    attr: Any
    bootstrap_path: Path
    checkpoint_path: Path
    legacy_reference: dict[str, Any]
    had_live_session: bool


# ---------------------------------------------------------------------------
# Backward-compat aliases
# ---------------------------------------------------------------------------

def build_notebook_workflow_config(
    *,
    registry_base: str | Path,
    sample_id: str,
    cooldown_id: str,
    qop_ip: str,
    cluster_name: str,
    legacy_cqed_params_path: str | Path | None = None,
) -> NotebookWorkflowConfig:
    """Construct a :class:`NotebookWorkflowConfig`."""
    return NotebookWorkflowConfig(
        registry_base=Path(registry_base),
        sample_id=sample_id,
        cooldown_id=cooldown_id,
        qop_ip=qop_ip,
        cluster_name=cluster_name,
        legacy_cqed_params_path=None if legacy_cqed_params_path is None else Path(legacy_cqed_params_path),
    )


# Alias so existing notebook code using the old name still works
get_notebook_stage_checkpoint_path = get_stage_checkpoint_path


# ---------------------------------------------------------------------------
# Notebook-specific: open_notebook_stage (requires shared session)
# ---------------------------------------------------------------------------

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
    simulation_mode: bool = True,
) -> NotebookStageContext:
    """Open a numbered-notebook stage, returning a context bundle.

    This is the notebook-specific orchestrator that combines workflow config,
    shared session management, and checkpoint path resolution.
    """
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
        simulation_mode=simulation_mode,
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
        checkpoint_path=get_stage_checkpoint_path(
            registry_base=workflow.registry_base,
            sample_id=workflow.sample_id,
            cooldown_id=workflow.cooldown_id,
            stage_name=stage_name,
        ),
        legacy_reference=load_legacy_reference(workflow.legacy_cqed_params_path),
        had_live_session=had_live_session,
    )


__all__ = [
    # Notebook-specific
    "NotebookStageContext",
    "NotebookWorkflowConfig",
    "build_notebook_workflow_config",
    "open_notebook_stage",
    # Re-exports from qubox.workflow (backward compat)
    "get_notebook_stage_checkpoint_path",
    "ensure_primitive_rotations",
    "fit_center_inside_window",
    "fit_quality_gate",
    "load_legacy_reference",
    "load_stage_checkpoint",
    "preview_or_apply_patch_ops",
    "save_stage_checkpoint",
]
