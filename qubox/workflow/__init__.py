"""Workflow primitives for stage management, checkpoints, and fit gates.

This package provides the core workflow building blocks used by both notebook
and script-based experiment pipelines.  The ``qubox.notebook.workflow`` module
is a thin convenience wrapper that adds shared-session integration on top.
"""

from __future__ import annotations

from .stages import (
    StageCheckpoint,
    WorkflowConfig,
    build_workflow_config,
    get_stage_checkpoint_path,
    load_legacy_reference,
    load_stage_checkpoint,
    save_stage_checkpoint,
)
from .calibration_helpers import preview_or_apply_patch_ops
from .fit_gates import fit_center_inside_window, fit_quality_gate
from .pulse_seeding import ensure_primitive_rotations

__all__ = [
    "StageCheckpoint",
    "WorkflowConfig",
    "build_workflow_config",
    "ensure_primitive_rotations",
    "fit_center_inside_window",
    "fit_quality_gate",
    "get_stage_checkpoint_path",
    "load_legacy_reference",
    "load_stage_checkpoint",
    "preview_or_apply_patch_ops",
    "save_stage_checkpoint",
]
