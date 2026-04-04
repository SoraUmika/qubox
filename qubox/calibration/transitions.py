"""qubox.calibration.transitions — canonical pulse naming conventions.

No external dependencies.

The *transition* system enforces a consistent naming scheme for all
qubit pulses.  Every reference pulse and derived rotation follows a
predictable pattern:

    <transition>_<family>_<rotation>

Examples::

    ge_ref_r180   — GE reference π pulse
    ge_x90        — GE X+π/2 rotation (derived from ge_ref_r180)
    ef_ref_r180   — EF reference π pulse
    ge_sel_ref_r180 — GE selective reference π pulse

The :func:`resolve_pulse_name` function maps legacy names (e.g. ``"x180"``,
``"pi_pulse"``) to their canonical equivalents before storage.
"""
from __future__ import annotations

from enum import Enum


class Transition(str, Enum):
    """Qubit transition identifiers."""

    GE = "ge"
    EF = "ef"


#: Default transition for experiments that don't specify one.
DEFAULT_TRANSITION: Transition = Transition.GE


# ---------------------------------------------------------------------------
# Canonical pulse name tables
# ---------------------------------------------------------------------------

#: Reference pulses: {transition} → canonical reference pulse name
CANONICAL_REF_PULSES: dict[str, str] = {
    "ge": "ge_ref_r180",
    "ef": "ef_ref_r180",
}

#: Derived rotation names for each transition
CANONICAL_DERIVED_PULSES: dict[str, list[str]] = {
    "ge": ["ge_x180", "ge_x90", "ge_xn90", "ge_y180", "ge_y90", "ge_yn90"],
    "ef": ["ef_x180", "ef_x90", "ef_xn90", "ef_y180", "ef_y90", "ef_yn90"],
}

# ---------------------------------------------------------------------------
# Legacy name → canonical name mapping
# ---------------------------------------------------------------------------

_LEGACY_NAME_MAP: dict[str, str] = {
    # bare rotation names → GE canonical
    "x180":     "ge_x180",
    "x90":      "ge_x90",
    "xn90":     "ge_xn90",
    "x-90":     "ge_xn90",
    "y180":     "ge_y180",
    "y90":      "ge_y90",
    "yn90":     "ge_yn90",
    "y-90":     "ge_yn90",
    "ref_r180": "ge_ref_r180",
    "r0":       "ge_r0",
    # legacy pi/2 aliases
    "pi_pulse":    "ge_x180",
    "pi_2_pulse":  "ge_x90",
    "pi_2":        "ge_x90",
    "pi":          "ge_x180",
}


def resolve_pulse_name(name: str) -> str:
    """Return the canonical pulse name for *name*, resolving legacy aliases.

    If *name* is already canonical (starts with a known transition prefix),
    it is returned unchanged.  Unknown names pass through unchanged.

    Parameters
    ----------
    name : str
        Pulse name (canonical or legacy).

    Returns
    -------
    str
        Canonical pulse name.

    Examples
    --------
    >>> resolve_pulse_name("x180")
    'ge_x180'
    >>> resolve_pulse_name("ge_ref_r180")
    'ge_ref_r180'
    >>> resolve_pulse_name("my_custom_pulse")
    'my_custom_pulse'
    """
    if name in _LEGACY_NAME_MAP:
        return _LEGACY_NAME_MAP[name]
    return name


def canonical_ref_pulse(transition: str | Transition) -> str:
    """Return the canonical reference pulse name for *transition*.

    Parameters
    ----------
    transition : str | Transition
        ``"ge"`` or ``"ef"`` (or the enum variants).

    Returns
    -------
    str
        E.g. ``"ge_ref_r180"`` or ``"ef_ref_r180"``.

    Raises
    ------
    ValueError
        If *transition* is not recognised.
    """
    key = str(transition).lower()
    if key not in CANONICAL_REF_PULSES:
        raise ValueError(
            f"Unknown transition {transition!r}. "
            f"Valid transitions: {sorted(CANONICAL_REF_PULSES)}"
        )
    return CANONICAL_REF_PULSES[key]


def canonical_derived_pulse(transition: str | Transition, rotation: str) -> str:
    """Return the canonical derived pulse name for *transition* + *rotation*.

    Parameters
    ----------
    transition : str | Transition
        ``"ge"`` or ``"ef"``.
    rotation : str
        Short rotation name, e.g. ``"x180"``, ``"y90"``, ``"xn90"``.

    Returns
    -------
    str
        E.g. ``"ge_x180"``, ``"ef_y90"``.
    """
    key = str(transition).lower()
    rot_lower = str(rotation).lower().lstrip("_")
    return f"{key}_{rot_lower}"


def extract_transition(pulse_name: str) -> str | None:
    """Extract the transition prefix from a canonical pulse name.

    Returns ``"ge"``, ``"ef"``, or ``None`` if no known prefix is found.

    Examples
    --------
    >>> extract_transition("ge_ref_r180")
    'ge'
    >>> extract_transition("ef_x90")
    'ef'
    >>> extract_transition("readout")
    None
    """
    for prefix in ("ge_", "ef_"):
        if pulse_name.startswith(prefix):
            return prefix.rstrip("_")
    return None


def strip_transition_prefix(pulse_name: str) -> str:
    """Remove the leading transition prefix from a pulse name.

    Examples
    --------
    >>> strip_transition_prefix("ge_ref_r180")
    'ref_r180'
    >>> strip_transition_prefix("x180")
    'x180'
    """
    for prefix in ("ge_", "ef_"):
        if pulse_name.startswith(prefix):
            return pulse_name[len(prefix):]
    return pulse_name


def primitive_family(pulse_name: str) -> str:
    """Return the rotation family of a derived pulse name.

    The family is the rotation axis + angle portion with the transition
    prefix stripped, e.g. ``"x180"``, ``"y90"``, ``"ref_r180"``.

    Examples
    --------
    >>> primitive_family("ge_x90")
    'x90'
    >>> primitive_family("ge_ref_r180")
    'ref_r180'
    """
    return strip_transition_prefix(pulse_name)
