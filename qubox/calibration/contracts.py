"""qubox.calibration.contracts — calibration result and patch contracts.

Migrated from ``qubox_v2_legacy.calibration.contracts``.
No external dependencies.

These dataclasses form the contract between experiment analysis code and
the :class:`~qubox.calibration.store.CalibrationStore`:

- :class:`Artifact` — raw experiment output (arrays + metadata).
- :class:`CalibrationResult` — typed analysis output (params + quality).
- :class:`UpdateOp` — a single atomic mutation to the calibration store.
- :class:`Patch` — an ordered collection of :class:`UpdateOp` items.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Artifact:
    """Raw experiment output, ready for persistence.

    Parameters
    ----------
    name : str
        Human-readable experiment name (e.g. ``"T1Relaxation"``).
    data : dict
        Output arrays and scalars from the experiment run.
    raw : any, optional
        Full raw QM job result (kept in memory only, not persisted).
    meta : dict
        Run metadata (timestamps, program hashes, etc.).
    artifact_id : str
        Auto-generated UUID for traceability.
    """

    name: str
    data: dict[str, Any]
    raw: Any = None
    meta: dict[str, Any] = field(default_factory=dict)
    artifact_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class CalibrationResult:
    """Typed analysis output from a single calibration experiment.

    Parameters
    ----------
    kind : str
        Calibration kind key, e.g. ``"t1"``, ``"pi_amp"``.
        Must match a key in :func:`~qubox.calibration.patch_rules.default_patch_rules`.
    transition : str, optional
        Qubit transition (``"ge"`` or ``"ef"``). ``None`` means GE.
    params : dict
        Fitted / extracted calibration parameters.
    uncertainties : dict
        Parameter uncertainties (1-sigma), if available.
    quality : dict
        Fit quality indicators: ``r_squared``, ``passed``, ``failure_reason``.
    evidence : dict
        Traceability metadata (artifact_id, analysis_metadata).
    """

    kind: str
    transition: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    uncertainties: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """True if the quality gate was met."""
        return bool(self.quality.get("passed", True))


@dataclass
class UpdateOp:
    """A single atomic mutation to the calibration store.

    Parameters
    ----------
    op : str
        Operation name.  Recognised ops:

        - ``"SetCalibration"``   — set a value at a dotted path in the store.
        - ``"SetPulseParam"``    — update a single field on a PulseCalibration.
        - ``"SetMeasureWeights"`` — push new integration weights.
        - ``"SetMeasureDiscrimination"`` — push new discrimination params.
        - ``"SetMeasureQuality"`` — push new readout quality metrics.
        - ``"PersistMeasureConfig"`` — write measureConfig.json to disk.
        - ``"TriggerPulseRecompile"`` — recompile all volatile pulses.

    payload : dict
        Op-specific parameters.
    """

    op: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Patch:
    """An ordered, auditable collection of calibration mutations.

    Parameters
    ----------
    updates : list[UpdateOp]
        Ordered list of mutations to apply.
    reason : str
        Human-readable description of why this patch was generated.
    provenance : dict
        Machine-readable metadata (kind, timestamp, quality evidence).
    """

    updates: list[UpdateOp] = field(default_factory=list)
    reason: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def add(self, op: str, **payload: Any) -> "Patch":
        """Append an :class:`UpdateOp` and return ``self`` for chaining."""
        if "provenance" not in self.provenance:
            self.provenance.setdefault("created", datetime.now().isoformat())
        self.updates.append(UpdateOp(op=op, payload=dict(payload)))
        return self

    def __len__(self) -> int:
        return len(self.updates)
