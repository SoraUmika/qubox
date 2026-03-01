# qubox_v2/calibration/transitions.py
"""Canonical transition identity contracts and naming normalization.

This module defines the single source of truth for:

1. **Transition labels** — ``"ge"`` (ground-excited), ``"ef"`` (excited-f).
2. **Canonical pulse names** — ``ge_ref_r180``, ``ef_ref_r180``, etc.
3. **Canonical pulse resolution** — canonical names and transition-scoped
    bare names are resolved without legacy alias tables.

Every subsystem that stores, looks up, or patches a pulse name must go
through :func:`resolve_pulse_name` so that the calibration store,
artifacts, patch rules, and experiments all speak the same language.

Design rules
------------
* Calibration JSON keys, ``PulseCalibration.pulse_name``, and
  ``PulseSpecEntry`` ``op`` fields **must** use canonical names.
* Bare names are only transition-scoped when an explicit transition is provided.
* The ``transition`` field on calibration/spec models identifies which
  qubit transition a record belongs to.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal


# ---------------------------------------------------------------------------
# Transition labels
# ---------------------------------------------------------------------------

class Transition(str, Enum):
    """Canonical qubit transition labels."""
    GE = "ge"
    EF = "ef"


#: Default transition assumed when no prefix or context is given.
DEFAULT_TRANSITION: Transition = Transition.GE

#: Allowed literal values (useful for Pydantic field types).
TransitionLiteral = Literal["ge", "ef"]


# ---------------------------------------------------------------------------
# Canonical reference pulse names
# ---------------------------------------------------------------------------

#: Reference (calibration-primitive) pulses — only these are stored in
#: ``calibration.json``.  Keyed by ``(transition, bare_ref_name)``.
CANONICAL_REF_PULSES: dict[tuple[Transition, str], str] = {
    (Transition.GE, "ref_r180"):     "ge_ref_r180",
    (Transition.GE, "ref_r90"):      "ge_ref_r90",
    (Transition.GE, "sel_ref_r180"): "ge_sel_ref_r180",
    (Transition.EF, "ref_r180"):     "ef_ref_r180",
    (Transition.EF, "ref_r90"):      "ef_ref_r90",
    (Transition.EF, "sel_ref_r180"): "ef_sel_ref_r180",
}

#: Derived (gate) pulses — generated programmatically by PulseFactory,
#: never stored in calibration.json.
CANONICAL_DERIVED_PULSES: dict[tuple[Transition, str], str] = {
    (Transition.GE, "x180"):  "ge_x180",
    (Transition.GE, "y180"):  "ge_y180",
    (Transition.GE, "x90"):   "ge_x90",
    (Transition.GE, "xn90"):  "ge_xn90",
    (Transition.GE, "y90"):   "ge_y90",
    (Transition.GE, "yn90"):  "ge_yn90",
    (Transition.GE, "r0"):    "ge_r0",
    (Transition.EF, "x180"):  "ef_x180",
    (Transition.EF, "y180"):  "ef_y180",
    (Transition.EF, "x90"):   "ef_x90",
    (Transition.EF, "xn90"):  "ef_xn90",
    (Transition.EF, "y90"):   "ef_y90",
    (Transition.EF, "yn90"):  "ef_yn90",
    (Transition.EF, "r0"):    "ef_r0",
}

#: Every canonical name in one set (for fast membership checks).
ALL_CANONICAL: frozenset[str] = frozenset(
    list(CANONICAL_REF_PULSES.values()) + list(CANONICAL_DERIVED_PULSES.values())
)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def is_canonical(name: str) -> bool:
    """Return True if *name* is already a canonical pulse name."""
    return name in ALL_CANONICAL


def resolve_pulse_name(
    name: str,
    transition: Transition | str | None = None,
) -> str:
    """Resolve a pulse name to its canonical form.

    Resolution order:

    1. If *name* is already canonical, return as-is.
     2. If a *transition* is provided and *name* is a bare suffix
       (e.g. ``"ref_r180"``), prefix with the transition.
     3. Otherwise return *name* unchanged (unknown names pass through so
       that user-defined custom pulses are not blocked).
    """
    if is_canonical(name):
        return name

    # Explicit transition given — build canonical name directly.
    if transition is not None:
        tr = Transition(transition) if not isinstance(transition, Transition) else transition
        candidate = f"{tr.value}_{name}"
        if candidate in ALL_CANONICAL:
            return candidate

    # Unknown name — return as-is for forward compatibility.
    return name


def canonical_ref_pulse(transition: Transition | str, bare: str = "ref_r180") -> str:
    """Build the canonical reference-pulse name for a transition.

    >>> canonical_ref_pulse("ge")
    'ge_ref_r180'
    >>> canonical_ref_pulse(Transition.EF, "sel_ref_r180")
    'ef_sel_ref_r180'
    """
    tr = Transition(transition) if not isinstance(transition, Transition) else transition
    key = (tr, bare)
    if key in CANONICAL_REF_PULSES:
        return CANONICAL_REF_PULSES[key]
    return f"{tr.value}_{bare}"


def canonical_derived_pulse(transition: Transition | str, bare: str) -> str:
    """Build the canonical derived-pulse name for a transition.

    >>> canonical_derived_pulse("ge", "x180")
    'ge_x180'
    >>> canonical_derived_pulse("ef", "y90")
    'ef_y90'
    """
    tr = Transition(transition) if not isinstance(transition, Transition) else transition
    key = (tr, bare)
    if key in CANONICAL_DERIVED_PULSES:
        return CANONICAL_DERIVED_PULSES[key]
    return f"{tr.value}_{bare}"


def extract_transition(canonical_name: str) -> Transition | None:
    """Extract the transition from a canonical pulse name.

    Returns ``None`` if the name is not in canonical form.

    >>> extract_transition("ge_x180")
    <Transition.GE: 'ge'>
    >>> extract_transition("ef_ref_r180")
    <Transition.EF: 'ef'>
    >>> extract_transition("x180") is None
    True
    """
    for tr in Transition:
        if canonical_name.startswith(f"{tr.value}_"):
            return tr
    return None


def strip_transition_prefix(canonical_name: str) -> str:
    """Remove the transition prefix, returning the bare pulse name.

    >>> strip_transition_prefix("ge_ref_r180")
    'ref_r180'
    >>> strip_transition_prefix("ef_x90")
    'x90'
    >>> strip_transition_prefix("custom_pulse")
    'custom_pulse'
    """
    for tr in Transition:
        prefix = f"{tr.value}_"
        if canonical_name.startswith(prefix):
            return canonical_name[len(prefix):]
    return canonical_name


def primitive_family(transition: Transition | str = Transition.GE) -> tuple[str, ...]:
    """Return the canonical derived-pulse family for a transition.

    >>> primitive_family("ge")
    ('ge_x180', 'ge_y180', 'ge_x90', 'ge_xn90', 'ge_y90', 'ge_yn90')
    """
    tr = Transition(transition) if not isinstance(transition, Transition) else transition
    bare_names = ("x180", "y180", "x90", "xn90", "y90", "yn90")
    return tuple(f"{tr.value}_{b}" for b in bare_names)
