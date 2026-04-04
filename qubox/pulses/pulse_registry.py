"""Clean pulse registration API.

PulseRegistry provides a simplified interface for adding, modifying, and
removing pulses.  It wraps the dual permanent/volatile ResourceStore pattern
from the original PulseOperationManager but with a cleaner API surface.

The original ``manager.py`` (PulseOperationManager) is preserved for backward
compatibility; this module delegates to the same underlying stores.
"""
from __future__ import annotations

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Union

import numpy as np

from qubox.core.pulse_op import PulseOp
from ..core.logging import get_logger
from ..core.types import MAX_AMPLITUDE, PulseType, WaveformType
from .integration_weights import IntegrationWeightManager
from .models import ResourceStore
from .waveforms import normalize_samples

_logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Reserved names
# ---------------------------------------------------------------------------
_RESERVED_PULSE_NAMES = frozenset({"readout_pulse"})
_RESERVED_WF_NAMES = frozenset({"readout_I_wf", "readout_Q_wf"})
# NOTE: "readout" is no longer a reserved operation as of the binding-driven
# API redesign.  Readout pulse registration now happens explicitly via
# ReadoutBinding → ConfigBuilder flow.  The readout pulse and waveforms
# remain reserved _names_ so they aren't accidentally overwritten.
_RESERVED_OPS: frozenset[str] = frozenset()


class PulseRegistry:
    """Simplified pulse registration with dual permanent/volatile stores.

    Parameters
    ----------
    elements : list[str] | None
        Known element names for validation.  If empty/None, accept all.
    readout_length : int
        Default canonical readout pulse length in ns.
    """

    def __init__(
        self,
        elements: list[str] | None = None,
        readout_length: int = 1000,
    ) -> None:
        self._perm = ResourceStore()
        self._volatile = ResourceStore()
        self.elements = elements or []
        self.weights = IntegrationWeightManager(readout_length)
        self._readout_length = readout_length
        self._init_defaults()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def _init_defaults(self) -> None:
        """Set up default waveforms, pulses, and the canonical readout."""
        # Default utility waveforms
        self._perm.waveforms["zero_wf"] = {"type": "constant", "sample": 0.0}
        self._perm.waveforms["const_wf"] = {"type": "constant", "sample": 0.24}

        # Digital waveforms
        self._perm.dig_waveforms["ON"] = {"samples": [(1, 0)]}
        self._perm.dig_waveforms["OFF"] = {"samples": [(0, 0)]}

        # Default control pulses
        self._perm.pulses["const_pulse"] = {
            "operation": "control", "length": 1000,
            "waveforms": {"I": "const_wf", "Q": "zero_wf"},
            "digital_marker": "ON",
        }
        self._perm.pulses["zero_pulse"] = {
            "operation": "control", "length": 1000,
            "waveforms": {"I": "zero_wf", "Q": "zero_wf"},
            "digital_marker": "ON",
        }
        self._perm.el_ops["*"] = {
            "const": "const_pulse",
            "zero": "zero_pulse",
            # NOTE: "readout" removed from wildcard mapping as of binding-driven
            # API redesign.  Readout ops are registered explicitly per-element
            # via ReadoutBinding → ConfigBuilder.
        }

        # Canonical readout pulse
        rl = self._readout_length
        self._perm.waveforms["readout_I_wf"] = {"type": "constant", "sample": 0.24}
        self._perm.waveforms["readout_Q_wf"] = {"type": "constant", "sample": 0.0}
        self._perm.pulses["readout_pulse"] = {
            "operation": "measurement",
            "length": rl,
            "waveforms": {"I": "readout_I_wf", "Q": "readout_Q_wf"},
            "digital_marker": "ON",
            "integration_weights": {
                "cos": "readout_cosine_weights",
                "sin": "readout_sine_weights",
                "minus_sin": "readout_minus_weights",
            },
        }

    # ------------------------------------------------------------------
    # Store selection helpers
    # ------------------------------------------------------------------
    def _store(self, persist: bool) -> ResourceStore:
        return self._perm if persist else self._volatile

    def _find_pulse(self, name: str) -> ResourceStore | None:
        if name in self._volatile.pulses:
            return self._volatile
        if name in self._perm.pulses:
            return self._perm
        return None

    # ------------------------------------------------------------------
    # Add control pulse
    # ------------------------------------------------------------------
    def add_control_pulse(
        self,
        element: str,
        op: str,
        *,
        I_wf: Any,
        Q_wf: Any = 0.0,
        length: int,
        pulse_name: str | None = None,
        digital_marker: str = "ON",
        persist: bool = True,
        override: bool = False,
    ) -> str:
        """Add a control pulse bound to (element, op).

        Parameters
        ----------
        element : str
            Target element name.
        op : str
            Operation identifier (e.g., "x180", "displacement").
        I_wf : scalar or list
            In-phase waveform. Scalar for constant, list for arbitrary.
        Q_wf : scalar or list
            Quadrature waveform. Defaults to 0.
        length : int
            Pulse length in ns.
        pulse_name : str | None
            Explicit pulse name. Auto-generated if None.
        digital_marker : str
            Digital marker ("ON" or "OFF").
        persist : bool
            If True, store in permanent store; else volatile.
        override : bool
            If True, overwrite existing pulse of same name.

        Returns
        -------
        str
            The pulse name.
        """
        self._validate_element(element)
        self._check_reserved_op(op)

        if pulse_name and pulse_name in _RESERVED_PULSE_NAMES:
            raise ValueError(f"Pulse name '{pulse_name}' is reserved.")

        store = self._store(persist)
        pulse_name = pulse_name or self._unique_name(f"{element}_{op}_pulse", store.pulses)

        if not override and pulse_name in store.pulses:
            raise ValueError(
                f"Pulse '{pulse_name}' already exists. Use override=True to overwrite."
            )

        # Register waveforms
        I_name = self._register_waveform(f"{element}_{op}_I", I_wf, length, store)
        Q_name = self._register_waveform(f"{element}_{op}_Q", Q_wf, length, store)

        # Register pulse
        store.pulses[pulse_name] = {
            "operation": "control",
            "length": int(length),
            "waveforms": {"I": I_name, "Q": Q_name},
            "digital_marker": digital_marker,
        }

        # Map element → operation → pulse
        store.el_ops.setdefault(element, {})[op] = pulse_name

        _logger.debug("Registered control pulse '%s' → %s.%s", pulse_name, element, op)
        return pulse_name

    # ------------------------------------------------------------------
    # Add measurement pulse
    # ------------------------------------------------------------------
    def add_measurement_pulse(
        self,
        element: str,
        op: str,
        *,
        I_wf: Any,
        Q_wf: Any = 0.0,
        length: int,
        pulse_name: str | None = None,
        digital_marker: str = "ON",
        weight_mapping: dict[str, str] | None = None,
        persist: bool = True,
        override: bool = False,
    ) -> str:
        """Add a measurement pulse bound to (element, op).

        Parameters
        ----------
        weight_mapping : dict | None
            Custom integration weight mapping {label: weight_name}.
            If None, uses the default cos/sin/minus_sin triplet.

        Returns
        -------
        str
            The pulse name.
        """
        self._validate_element(element)

        if op in _RESERVED_OPS:
            raise ValueError(
                f"Op '{op}' is reserved for canonical readout. "
                "Use modify_pulse() to change readout parameters."
            )

        store = self._store(persist)
        pulse_name = pulse_name or self._unique_name(f"{element}_{op}_pulse", store.pulses)

        if not override and pulse_name in store.pulses:
            raise ValueError(
                f"Pulse '{pulse_name}' already exists. Use override=True to overwrite."
            )

        # Register waveforms
        I_name = self._register_waveform(f"{element}_{op}_I", I_wf, length, store)
        Q_name = self._register_waveform(f"{element}_{op}_Q", Q_wf, length, store)

        # Integration weights
        if weight_mapping is None:
            weight_mapping = self.weights.default_triplet(length)

        store.pulses[pulse_name] = {
            "operation": "measurement",
            "length": int(length),
            "waveforms": {"I": I_name, "Q": Q_name},
            "digital_marker": digital_marker,
            "integration_weights": weight_mapping,
        }

        store.el_ops.setdefault(element, {})[op] = pulse_name

        _logger.debug("Registered measurement pulse '%s' → %s.%s", pulse_name, element, op)
        return pulse_name

    # ------------------------------------------------------------------
    # Modify / remove
    # ------------------------------------------------------------------
    def modify_pulse(
        self,
        pulse_name: str,
        *,
        I_wf: Any = None,
        Q_wf: Any = None,
        length: int | None = None,
        digital_marker: str | None = None,
    ) -> None:
        """Modify an existing pulse's properties (including reserved pulses)."""
        store = self._find_pulse(pulse_name)
        if store is None:
            raise KeyError(f"Pulse '{pulse_name}' not found.")

        pulse = store.pulses[pulse_name]

        if length is not None:
            pulse["length"] = int(length)

        if digital_marker is not None:
            pulse["digital_marker"] = digital_marker

        if I_wf is not None:
            I_wf_name = pulse["waveforms"]["I"]
            self._update_waveform(I_wf_name, I_wf, store)

        if Q_wf is not None:
            Q_wf_name = pulse["waveforms"]["Q"]
            self._update_waveform(Q_wf_name, Q_wf, store)

    def modify_waveform(self, name: str, samples: Any) -> None:
        """Modify an existing waveform's samples (works for reserved waveforms too)."""
        for s in (self._volatile, self._perm):
            if name in s.waveforms:
                self._update_waveform(name, samples, s)
                return
        raise KeyError(f"Waveform '{name}' not found.")

    def remove_pulse(self, pulse_name: str, *, persist: bool | None = None) -> None:
        """Remove a non-reserved pulse and clean up element-op mappings."""
        if pulse_name in _RESERVED_PULSE_NAMES:
            raise ValueError(f"Cannot remove reserved pulse '{pulse_name}'.")

        stores = []
        if pulse_name in self._perm.pulses:
            stores.append(("perm", self._perm))
        if pulse_name in self._volatile.pulses:
            stores.append(("volatile", self._volatile))

        if not stores:
            raise KeyError(f"Pulse '{pulse_name}' not found.")

        if persist is None and len(stores) > 1:
            raise ValueError(
                f"Pulse '{pulse_name}' in both stores. Specify persist=True/False."
            )

        target = self._perm if persist else self._volatile if persist is not None else stores[0][1]
        del target.pulses[pulse_name]

        # Clean element-op mappings
        for s in (self._perm, self._volatile):
            for el, ops in list(s.el_ops.items()):
                for op_id, p_name in list(ops.items()):
                    if p_name == pulse_name:
                        del ops[op_id]
                if not ops and el != "*":
                    del s.el_ops[el]

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    def get_pulse(self, name: str) -> dict[str, Any]:
        """Get pulse definition dict by name."""
        store = self._find_pulse(name)
        if store is None:
            raise KeyError(f"Pulse '{name}' not found.")
        return store.pulses[name]

    def list_pulses(self, *, element: str | None = None) -> list[str]:
        """List pulse names, optionally filtered by element."""
        all_pulses = set(self._perm.pulses) | set(self._volatile.pulses)
        if element is None:
            return sorted(all_pulses)

        # Filter by element mapping
        mapped = set()
        for s in (self._perm, self._volatile):
            for op, pname in s.el_ops.get(element, {}).items():
                mapped.add(pname)
            for op, pname in s.el_ops.get("*", {}).items():
                mapped.add(pname)
        return sorted(all_pulses & mapped)

    def get_element_ops(self, element: str) -> dict[str, str]:
        """Get operation→pulse mapping for an element (merged with wildcards)."""
        ops = {}
        for s in (self._perm, self._volatile):
            ops.update(s.el_ops.get("*", {}))
            ops.update(s.el_ops.get(element, {}))
        return ops

    # ------------------------------------------------------------------
    # Burn to QM config
    # ------------------------------------------------------------------
    def burn_to_config(
        self, cfg: dict[str, Any], *, include_volatile: bool = True
    ) -> dict[str, Any]:
        """Merge all pulse definitions into a QM config dict.

        Parameters
        ----------
        cfg : dict
            The QM configuration dict (modified in-place and returned).
        include_volatile : bool
            Whether to include volatile (session-only) pulses.

        Returns
        -------
        dict
            The modified config dict.
        """
        self._perm.merge_into(cfg)
        if include_volatile:
            self._volatile.merge_into(cfg)
        self.weights.merge_into(cfg)

        # Expand wildcard element ops to all known elements
        wildcard_ops = {}
        for s in (self._perm, self._volatile if include_volatile else ResourceStore()):
            wildcard_ops.update(s.el_ops.pop("*", {}))
        if wildcard_ops:
            for el_name in cfg.get("elements", {}):
                el_cfg = cfg["elements"][el_name]
                el_cfg.setdefault("operations", {}).update(wildcard_ops)

        return cfg

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save_json(self, path: str | Path) -> None:
        """Save permanent store to JSON."""
        data = self._perm.as_dict()
        data["integration_weights"] = self.weights.as_dict()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        _logger.info("Pulses saved to %s", path)

    def load_json(self, path: str | Path) -> None:
        """Load permanent store from JSON (clears existing perm data)."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._perm.clear()
        self._perm.load_from_dict(data)
        if "integration_weights" in data:
            self.weights.load_from_dict(data["integration_weights"])
        self._init_defaults()  # re-add reserved defaults if missing
        _logger.info("Pulses loaded from %s", path)

    @classmethod
    def from_json(cls, path: str | Path) -> PulseRegistry:
        """Create a PulseRegistry from a JSON file."""
        registry = cls()
        registry.load_json(path)
        return registry

    def clear_volatile(self) -> None:
        """Discard all volatile (session-only) pulses."""
        self._volatile.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _validate_element(self, element: str) -> None:
        if self.elements and element not in self.elements and element != "*":
            raise ValueError(
                f"Element '{element}' not in known elements: {sorted(self.elements)}"
            )

    @staticmethod
    def _check_reserved_op(op: str) -> None:
        if op in _RESERVED_OPS:
            raise ValueError(
                f"Op '{op}' is reserved for canonical readout. "
                "Use modify_pulse() instead."
            )

    def _register_waveform(
        self, base_name: str, samples: Any, length: int, store: ResourceStore
    ) -> str:
        """Register a waveform and return its name."""
        samples = normalize_samples(samples, label=base_name)
        name = self._unique_name(base_name, store.waveforms)

        if isinstance(samples, (int, float)):
            if abs(samples) > MAX_AMPLITUDE:
                raise ValueError(f"Amplitude {samples} exceeds MAX_AMPLITUDE.")
            store.waveforms[name] = {"type": "constant", "sample": float(samples)}
        else:
            for s in samples:
                if abs(s) > MAX_AMPLITUDE:
                    raise ValueError(f"Sample {s} exceeds MAX_AMPLITUDE.")
            store.waveforms[name] = {"type": "arbitrary", "samples": samples}

        return name

    def _update_waveform(self, name: str, samples: Any, store: ResourceStore) -> None:
        """Update an existing waveform's data."""
        if name not in store.waveforms:
            raise KeyError(f"Waveform '{name}' not found in store.")
        samples = normalize_samples(samples, label=name)
        if isinstance(samples, (int, float)):
            store.waveforms[name] = {"type": "constant", "sample": float(samples)}
        else:
            store.waveforms[name] = {"type": "arbitrary", "samples": samples}

    @staticmethod
    def _unique_name(base: str, existing: dict) -> str:
        name = base
        i = 1
        while name in existing:
            name = f"{base}_{i}"
            i += 1
        return name
