# qubox_v2/calibration/state_machine.py
"""Calibration lifecycle state machine.

Governs the flow from experiment execution through analysis to calibration
commit. Prevents accidental writes by enforcing state transitions.

This module is opt-in. Existing code using ``guarded_calibration_commit()``
continues to work. The state machine provides a stricter alternative for
workflows that require full lifecycle tracking.
"""
from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import Any

_logger = logging.getLogger(__name__)


class CalibrationState(str, Enum):
    """Calibration lifecycle states."""
    IDLE = "idle"
    CONFIGURED = "configured"
    ACQUIRING = "acquiring"
    ACQUIRED = "acquired"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    PLOTTED = "plotted"
    PENDING_APPROVAL = "pending_approval"
    COMMITTING = "committing"
    COMMITTED = "committed"
    FAILED = "failed"
    ABORTED = "aborted"
    ROLLED_BACK = "rolled_back"


# Valid transitions: (from_state, to_state)
ALLOWED_TRANSITIONS: set[tuple[CalibrationState, CalibrationState]] = {
    (CalibrationState.IDLE, CalibrationState.CONFIGURED),
    (CalibrationState.CONFIGURED, CalibrationState.ACQUIRING),
    (CalibrationState.ACQUIRING, CalibrationState.ACQUIRED),
    (CalibrationState.ACQUIRING, CalibrationState.FAILED),
    (CalibrationState.ACQUIRED, CalibrationState.ANALYZING),
    (CalibrationState.ANALYZING, CalibrationState.ANALYZED),
    (CalibrationState.ANALYZING, CalibrationState.FAILED),
    (CalibrationState.ANALYZED, CalibrationState.PLOTTED),
    (CalibrationState.PLOTTED, CalibrationState.PENDING_APPROVAL),
    (CalibrationState.PENDING_APPROVAL, CalibrationState.COMMITTING),
    (CalibrationState.PENDING_APPROVAL, CalibrationState.ABORTED),
    (CalibrationState.COMMITTING, CalibrationState.COMMITTED),
    (CalibrationState.COMMITTING, CalibrationState.FAILED),
    (CalibrationState.COMMITTED, CalibrationState.ROLLED_BACK),
    # Shortcut: ANALYZED → PENDING_APPROVAL (skip explicit plot step)
    (CalibrationState.ANALYZED, CalibrationState.PENDING_APPROVAL),
}

# Any state can transition to ABORTED or FAILED
_UNIVERSAL_TARGETS = {CalibrationState.ABORTED, CalibrationState.FAILED}


class CalibrationStateError(Exception):
    """Raised when an illegal state transition is attempted."""

    def __init__(self, current: CalibrationState, attempted: CalibrationState):
        self.current = current
        self.attempted = attempted
        super().__init__(
            f"Illegal calibration state transition: {current.value} → {attempted.value}. "
            f"See CALIBRATION_POLICY.md for the valid transition graph."
        )


class CalibrationStateMachine:
    """Tracks the lifecycle of a single calibration run.

    Usage
    -----
    >>> sm = CalibrationStateMachine(experiment="power_rabi")
    >>> sm.transition(CalibrationState.CONFIGURED)
    >>> sm.transition(CalibrationState.ACQUIRING)
    >>> # ... run experiment ...
    >>> sm.transition(CalibrationState.ACQUIRED)
    >>> sm.transition(CalibrationState.ANALYZING)
    >>> # ... analyze ...
    >>> sm.transition(CalibrationState.ANALYZED)
    >>> sm.transition(CalibrationState.PENDING_APPROVAL)
    >>> # user reviews ...
    >>> sm.transition(CalibrationState.COMMITTING)
    >>> # apply patch ...
    >>> sm.transition(CalibrationState.COMMITTED)
    """

    def __init__(self, experiment: str):
        self.experiment = experiment
        self._state = CalibrationState.IDLE
        self._history: list[tuple[str, CalibrationState, CalibrationState]] = []
        self._created = datetime.now().isoformat()
        self._patch: CalibrationPatch | None = None
        _logger.debug(
            "CalibrationStateMachine created for %s (state=%s)",
            experiment, self._state.value,
        )

    @property
    def state(self) -> CalibrationState:
        """Current state."""
        return self._state

    @property
    def history(self) -> list[tuple[str, CalibrationState, CalibrationState]]:
        """List of (timestamp, from_state, to_state) transitions."""
        return list(self._history)

    @property
    def patch(self) -> CalibrationPatch | None:
        """The calibration patch, available after ANALYZED state."""
        return self._patch

    @patch.setter
    def patch(self, value: CalibrationPatch) -> None:
        if self._state not in (CalibrationState.ANALYZING, CalibrationState.ANALYZED):
            raise CalibrationStateError(self._state, CalibrationState.ANALYZED)
        self._patch = value

    def transition(self, target: CalibrationState) -> None:
        """Transition to a new state.

        Parameters
        ----------
        target : CalibrationState
            The target state.

        Raises
        ------
        CalibrationStateError
            If the transition is not allowed.
        """
        if target in _UNIVERSAL_TARGETS:
            # Always allowed
            pass
        elif (self._state, target) not in ALLOWED_TRANSITIONS:
            raise CalibrationStateError(self._state, target)

        old = self._state
        self._state = target
        ts = datetime.now().isoformat()
        self._history.append((ts, old, target))
        _logger.info(
            "Calibration[%s]: %s → %s",
            self.experiment, old.value, target.value,
        )

    def can_transition(self, target: CalibrationState) -> bool:
        """Check if a transition is allowed without performing it."""
        if target in _UNIVERSAL_TARGETS:
            return True
        return (self._state, target) in ALLOWED_TRANSITIONS

    def is_committable(self) -> bool:
        """Check if the state machine has reached a committable state."""
        return self._state == CalibrationState.PENDING_APPROVAL and self._patch is not None

    def abort(self, reason: str = "") -> None:
        """Abort the calibration run from any state."""
        self.transition(CalibrationState.ABORTED)
        if reason:
            _logger.info("Calibration[%s] aborted: %s", self.experiment, reason)

    def fail(self, error: str) -> None:
        """Mark the calibration as failed from any state."""
        self.transition(CalibrationState.FAILED)
        _logger.error("Calibration[%s] failed: %s", self.experiment, error)

    def summary(self) -> dict[str, Any]:
        """Return a summary dict for logging/artifacts."""
        return {
            "experiment": self.experiment,
            "state": self._state.value,
            "created": self._created,
            "transitions": len(self._history),
            "has_patch": self._patch is not None,
            "history": [
                {"timestamp": ts, "from": f.value, "to": t.value}
                for ts, f, t in self._history
            ],
        }


# ---------------------------------------------------------------------------
# CalibrationPatch
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field as dc_field


@dataclass(frozen=True)
class PatchEntry:
    """A single key-value change in a calibration patch."""
    path: str          # Dotted key path: "frequencies.resonator.if_freq"
    old_value: Any     # Previous value (None if new key)
    new_value: Any     # Proposed value
    dtype: str = ""    # Expected type (for validation)


@dataclass(frozen=True)
class PatchValidation:
    """Validation results for a calibration patch."""
    passed: bool
    checks: dict[str, bool] = dc_field(default_factory=dict)
    reasons: list[str] = dc_field(default_factory=list)

    def summary(self) -> str:
        lines = [f"Validation: {'PASSED' if self.passed else 'FAILED'}"]
        for check, ok in self.checks.items():
            lines.append(f"  {'✓' if ok else '✗'} {check}")
        if self.reasons:
            lines.append("Reasons:")
            for r in self.reasons:
                lines.append(f"  - {r}")
        return "\n".join(lines)


@dataclass
class CalibrationPatch:
    """Explicit diff object for calibration updates.

    A CalibrationPatch describes exactly what changes will be made to
    calibration.json. It must be inspected and approved before application.

    Attributes
    ----------
    experiment : str
        Name of the experiment that produced this patch.
    timestamp : str
        ISO 8601 timestamp of patch creation.
    changes : list[PatchEntry]
        Ordered list of key-value changes.
    validation : PatchValidation
        Quality gate results.
    metadata : dict
        Additional context (fit params, R², etc.).
    """
    experiment: str
    timestamp: str = dc_field(default_factory=lambda: datetime.now().isoformat())
    changes: list[PatchEntry] = dc_field(default_factory=list)
    validation: PatchValidation = dc_field(
        default_factory=lambda: PatchValidation(passed=False)
    )
    metadata: dict[str, Any] = dc_field(default_factory=dict)
    _overrides: dict[str, str] = dc_field(default_factory=dict, repr=False)

    def add_change(
        self,
        path: str,
        old_value: Any,
        new_value: Any,
        dtype: str = "",
    ) -> None:
        """Add a change entry to the patch."""
        self.changes.append(PatchEntry(
            path=path,
            old_value=old_value,
            new_value=new_value,
            dtype=dtype,
        ))

    def override_validation(self, gate: str, reason: str, user: str = "") -> None:
        """Override a failed validation gate with justification.

        The override is recorded in metadata for audit purposes.
        """
        self._overrides[gate] = reason
        self.metadata.setdefault("validation_overrides", []).append({
            "gate": gate,
            "reason": reason,
            "user": user,
            "timestamp": datetime.now().isoformat(),
        })
        _logger.warning(
            "Validation gate '%s' overridden: %s (user=%s)",
            gate, reason, user or "unknown",
        )

    def is_approved(self) -> bool:
        """Check if the patch is ready for commit.

        Returns True if validation passed or all failed gates have overrides.
        """
        if self.validation.passed:
            return True
        failed_gates = [g for g, ok in self.validation.checks.items() if not ok]
        return all(g in self._overrides for g in failed_gates)

    def summary(self) -> str:
        """Human-readable summary of the patch."""
        lines = [
            f"CalibrationPatch: {self.experiment} ({self.timestamp})",
            f"Changes ({len(self.changes)}):",
        ]
        for c in self.changes:
            lines.append(f"  {c.path}: {c.old_value!r} → {c.new_value!r}")
        lines.append("")
        lines.append(self.validation.summary())
        if self._overrides:
            lines.append(f"Overrides: {list(self._overrides.keys())}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for history/artifact storage."""
        return {
            "experiment": self.experiment,
            "timestamp": self.timestamp,
            "changes": [
                {"path": c.path, "old": c.old_value,
                 "new": c.new_value, "dtype": c.dtype}
                for c in self.changes
            ],
            "validation": {
                "passed": self.validation.passed,
                "checks": self.validation.checks,
                "reasons": self.validation.reasons,
            },
            "overrides": self._overrides,
            "metadata": self.metadata,
        }
