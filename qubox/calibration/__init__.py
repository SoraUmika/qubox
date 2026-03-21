"""qubox.calibration — typed calibration data, store, and patch lifecycle.

Public API
----------
Data models (Pydantic v2):
    CalibrationData, CalibrationContext, DiscriminationParams, ReadoutQuality,
    CQEDParams, CoherenceParams, ElementFrequencies, PulseCalibration,
    FitRecord, PulseTrainResult, FockSQRCalibration, MultiStateCalibration

Contracts (dataclasses):
    Artifact, CalibrationResult, UpdateOp, Patch

Transitions:
    Transition, resolve_pulse_name, canonical_ref_pulse, canonical_derived_pulse,
    extract_transition, strip_transition_prefix, primitive_family

Store:
    CalibrationStore

Orchestrator:
    CalibrationOrchestrator

Patch rules:
    PiAmpRule, T1Rule, T2RamseyRule, T2EchoRule, FrequencyRule, DragAlphaRule,
    DiscriminationRule, ReadoutQualityRule, WeightRegistrationRule, PulseTrainRule,
    default_patch_rules

History:
    list_snapshots, load_snapshot, diff_snapshots

qubox-native workflow types (pre-existing):
    CalibrationProposal, CalibrationSnapshot
"""

# qubox-native workflow types (pre-existing in this package)
from .models import CalibrationProposal, CalibrationSnapshot

# Pydantic v2 data models
from .store_models import (
    CalibrationData,
    CalibrationContext,
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
)

# Contracts
from .contracts import Artifact, CalibrationResult, UpdateOp, Patch

# Transitions
from .transitions import (
    Transition,
    CANONICAL_REF_PULSES,
    CANONICAL_DERIVED_PULSES,
    resolve_pulse_name,
    canonical_ref_pulse,
    canonical_derived_pulse,
    extract_transition,
    strip_transition_prefix,
    primitive_family,
)

# Store
from .store import CalibrationStore

# Orchestrator
from .orchestrator import CalibrationOrchestrator

# Patch rules
from .patch_rules import (
    PiAmpRule,
    T1Rule,
    T2RamseyRule,
    T2EchoRule,
    FrequencyRule,
    DragAlphaRule,
    DiscriminationRule,
    ReadoutQualityRule,
    WeightRegistrationRule,
    PulseTrainRule,
    default_patch_rules,
)

# History
from .history import list_snapshots, load_snapshot, diff_snapshots

__all__ = [
    # qubox-native
    "CalibrationProposal",
    "CalibrationSnapshot",
    # data models
    "CalibrationData",
    "CalibrationContext",
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
    # contracts
    "Artifact",
    "CalibrationResult",
    "UpdateOp",
    "Patch",
    # transitions
    "Transition",
    "CANONICAL_REF_PULSES",
    "CANONICAL_DERIVED_PULSES",
    "resolve_pulse_name",
    "canonical_ref_pulse",
    "canonical_derived_pulse",
    "extract_transition",
    "strip_transition_prefix",
    "primitive_family",
    # store
    "CalibrationStore",
    # orchestrator
    "CalibrationOrchestrator",
    # patch rules
    "PiAmpRule",
    "T1Rule",
    "T2RamseyRule",
    "T2EchoRule",
    "FrequencyRule",
    "DragAlphaRule",
    "DiscriminationRule",
    "ReadoutQualityRule",
    "WeightRegistrationRule",
    "PulseTrainRule",
    "default_patch_rules",
    # history
    "list_snapshots",
    "load_snapshot",
    "diff_snapshots",
]
