"""Advanced / infrastructure imports for ``qubox.notebook``.

This module exposes calibration data models, internal store types, device
registry details, artifact management, schemas, verification, and other
symbols that are not needed in everyday experiment notebooks but are
required for infrastructure work, debugging, or advanced calibration flows.

Usage::

    from qubox.notebook.advanced import CalibrationStore, FitRecord, SampleRegistry
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Calibration data models & store
# ---------------------------------------------------------------------------
from ..calibration import (
    CalibrationStore,
    CalibrationResult,
    Artifact,
    DiscriminationParams,
    ReadoutQuality,
    CQEDParams,
    CoherenceParams,
    ElementFrequencies,
    PulseCalibration,
    FitRecord,
    PulseTrainResult,
    FockSQRCalibration,
    MultiStateCalibration,
    CalibrationData,
    CalibrationContext,
    Transition,
    resolve_pulse_name,
    canonical_ref_pulse,
    canonical_derived_pulse,
    extract_transition,
    strip_transition_prefix,
    primitive_family,
    list_snapshots as list_calibration_snapshots,
    load_snapshot as load_calibration_snapshot,
    diff_snapshots as diff_calibration_snapshots,
    default_patch_rules,
)

# ---------------------------------------------------------------------------
# Device registry
# ---------------------------------------------------------------------------
from ..devices import SampleRegistry, SampleInfo

# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------
from ..artifacts import (
    ArtifactManager,
    save_config_snapshot,
    save_run_summary,
    cleanup_artifacts,
)

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------
from ..preflight import preflight_check

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
from ..schemas import validate_config_dir, ValidationResult

# ---------------------------------------------------------------------------
# Core types, errors, context
# ---------------------------------------------------------------------------
from ..core.errors import ContextMismatchError
from ..core.experiment_context import ExperimentContext, compute_wiring_rev
from ..core.session_state import SessionState

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
from ..verification.waveform_regression import run_all_checks

# ---------------------------------------------------------------------------
# Runtime helpers less commonly used
# ---------------------------------------------------------------------------
from .runtime import (
    get_notebook_session_bootstrap_path,
    load_notebook_session_bootstrap,
    register_shared_session,
    save_notebook_session_bootstrap,
)

# ---------------------------------------------------------------------------
# Module aliases
# ---------------------------------------------------------------------------
from ..experiments.calibration import readout as readout_mod  # noqa: F811
from ..experiments.calibration import gates as gates_mod

__all__ = [
    # calibration data models
    "CalibrationStore",
    "CalibrationResult",
    "Artifact",
    "DiscriminationParams",
    "ReadoutQuality",
    "CQEDParams",
    "CoherenceParams",
    "ElementFrequencies",
    "PulseCalibration",
    "FitRecord",
    "PulseTrainResult",
    "FockSQRCalibration",
    "MultiStateCalibration",
    "CalibrationData",
    "CalibrationContext",
    "Transition",
    "resolve_pulse_name",
    "canonical_ref_pulse",
    "canonical_derived_pulse",
    "extract_transition",
    "strip_transition_prefix",
    "primitive_family",
    "list_calibration_snapshots",
    "load_calibration_snapshot",
    "diff_calibration_snapshots",
    "default_patch_rules",
    # devices
    "SampleRegistry",
    "SampleInfo",
    # artifacts
    "ArtifactManager",
    "save_config_snapshot",
    "save_run_summary",
    "cleanup_artifacts",
    # preflight
    "preflight_check",
    # schemas
    "validate_config_dir",
    "ValidationResult",
    # core
    "ContextMismatchError",
    "ExperimentContext",
    "compute_wiring_rev",
    "SessionState",
    # verification
    "run_all_checks",
    # runtime extras
    "get_notebook_session_bootstrap_path",
    "load_notebook_session_bootstrap",
    "register_shared_session",
    "save_notebook_session_bootstrap",
    # module aliases
    "readout_mod",
    "gates_mod",
]
