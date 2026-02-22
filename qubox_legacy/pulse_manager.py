from __future__ import annotations
import json, warnings
from typing import Any, Dict, List, Union
import numpy as np
import matplotlib.pyplot as plt
from .analysis.pulseOp import PulseOp
from .analysis.algorithms import compute_waveform_fft
import logging

_logger = logging.getLogger(__name__)

MAX_AMPLITUDE  = 0.45
BASE_AMPLITUDE = 0.24

# ═════════════════════════════════════════════════════════════════
#  Helpers
# ═════════════════════════════════════════════════════════════════

class _ResourceStore:
    """Container for waveforms, pulses, weights and element-op mappings."""

    def __init__(self) -> None:
        self.waveforms: Dict[str, Dict[str, Any]] = {}
        self.dig_waveforms: Dict[str, Dict[str, Any]] = {}
        self.pulses:    Dict[str, Dict[str, Any]] = {}
        self.weights:   Dict[str, Dict[str, Any]] = {}
        self.el_ops:    Dict[str, Dict[str, str]] = {}

    # ─── merge this store into an arbitrary QM config dict ────
    def merge_into(self, cfg: Dict[str, Any]) -> None:
        cfg.setdefault("waveforms",            {}).update(self.waveforms)
        cfg.setdefault("digital_waveforms",{}).update(self.dig_waveforms)
        cfg.setdefault("pulses",               {}).update(self.pulses)
        cfg.setdefault("integration_weights",  {}).update(self.weights)
        elems = cfg.setdefault("elements", {})
        for el, ops in self.el_ops.items():
            elems.setdefault(el, {}).setdefault("operations", {}).update(ops)

    # ─── serialization helpers (perm store only) ──────────────
    def as_dict(self):
        return dict(
            waveforms=self.waveforms,
            digital_waveforms=self.dig_waveforms,
            pulses=self.pulses,
            integration_weights=self.weights,
            element_operations=self.el_ops,
        )

    def load_from_dict(self, d: Dict[str, Any]):
        self.waveforms.update(d.get("waveforms", {}))
        self.dig_waveforms.update(d.get("digital_waveforms", {}))
        self.pulses.update(d.get("pulses", {}))
        self.weights.update(d.get("integration_weights", {}))
        self.el_ops.update(d.get("element_operations", {}))

    def clear(self):
        self.waveforms.clear(); self.pulses.clear()
        self.weights.clear();   self.el_ops.clear()

    
# ═════════════════════════════════════════════════════════════════
class PulseOperationManager:
    # ─────────────────────────────────────────────────────────────
    #  Construction / persistence
    # ─────────────────────────────────────────────────────────────

    READOUT_PULSE_NAME      = "readout_pulse"
    READOUT_I_WF_NAME       = "readout_I_wf"
    READOUT_Q_WF_NAME       = "readout_Q_wf"
    READOUT_IW_COS_NAME     = "readout_cosine_weights"
    READOUT_IW_SIN_NAME     = "readout_sine_weights"
    READOUT_IW_MINUS_NAME   = "readout_minus_weights"

    _RESERVED_PULSE_NAMES    = {READOUT_PULSE_NAME}
    _RESERVED_WAVEFORM_NAMES = {READOUT_I_WF_NAME, READOUT_Q_WF_NAME}
    _RESERVED_WEIGHT_NAMES   = {
        READOUT_IW_COS_NAME,
        READOUT_IW_SIN_NAME,
        READOUT_IW_MINUS_NAME,
    }
    _RESERVED_OP_IDS         = {"readout"}  # op_id reserved for readout_pulse

    def __init__(self, elements: List[str] | None = None) -> None:
        self._perm      = _ResourceStore()
        self._volatile  = _ResourceStore()
        self.elements   = elements or []
        self._init_defaults()

    def _is_reserved_pulse_name(self, name: str) -> bool:
        return name in self._RESERVED_PULSE_NAMES

    def _is_reserved_waveform_name(self, name: str) -> bool:
        return name in self._RESERVED_WAVEFORM_NAMES

    def _is_reserved_weight_name(self, name: str) -> bool:
        return name in self._RESERVED_WEIGHT_NAMES

    def _init_defaults(self):
        # ----- generic non-reserved defaults via helpers -----------------
        self.add_waveform("zero_wf",  "constant", 0.0)
        self.add_waveform("const_wf", "constant", BASE_AMPLITUDE)
        self.add_digital_waveform("ON",  [(1, 0)])
        self.add_digital_waveform("OFF", [(0, 0)])
        self.add_pulse("const_pulse", "control", 1000, "const_wf", "zero_wf")
        self.add_pulse("zero_pulse",  "control", 1000, "zero_wf",  "zero_wf")
        self._perm.el_ops = {"*": {"const": "const_pulse", "zero": "zero_pulse"}}

        # ----- reserved readout resources: write directly to perm store ---
        readout_len = 1000  # default length

        # reserved I/Q waveforms
        self._perm.waveforms[self.READOUT_I_WF_NAME] = {
            "type": "constant",
            "sample": BASE_AMPLITUDE,
        }
        self._perm.waveforms[self.READOUT_Q_WF_NAME] = {
            "type": "constant",
            "sample": 0.0,
        }

        # reserved integration weights
        self._perm.weights[self.READOUT_IW_COS_NAME] = {
            "cosine": [(1.0,  readout_len)],
            "sine":   [(0.0,  readout_len)],
        }
        self._perm.weights[self.READOUT_IW_SIN_NAME] = {
            "cosine": [(0.0,  readout_len)],
            "sine":   [(1.0,  readout_len)],
        }
        self._perm.weights[self.READOUT_IW_MINUS_NAME] = {
            "cosine": [(0.0,   readout_len)],
            "sine":   [(-1.0,  readout_len)],
        }

        # canonical readout pulse
        self._perm.pulses[self.READOUT_PULSE_NAME] = {
            "operation": "measurement",
            "length":    readout_len,
            "waveforms": {
                "I": self.READOUT_I_WF_NAME,
                "Q": self.READOUT_Q_WF_NAME,
            },
            "digital_marker": "ON",
            "integration_weights": {
                "cos":       self.READOUT_IW_COS_NAME,
                "sin":       self.READOUT_IW_SIN_NAME,
                "minus_sin": self.READOUT_IW_MINUS_NAME,
            },
        }

        # wildcard element mapping for readout op-id
        self._perm.el_ops.setdefault("*", {})["readout"] = self.READOUT_PULSE_NAME

    # ---- small internal helpers ---------------------------------------
    def _store(self, *, persist: bool) -> _ResourceStore:
        """Convenience: choose permanent vs. volatile store."""
        return self._perm if persist else self._volatile

    def _pulse_store(
        self,
        name: str,
        *,
        include_volatile: bool = True,
    ) -> _ResourceStore | None:
        """Return the store that contains `name` as a pulse, or None."""
        if include_volatile and name in self._volatile.pulses:
            return self._volatile
        if name in self._perm.pulses:
            return self._perm
        return None

    def _weight_store(
        self,
        name: str,
        *,
        include_volatile: bool = True,
    ) -> _ResourceStore | None:
        """Return the store that contains `name` as an integration-weight, or None."""
        if include_volatile and name in self._volatile.weights:
            return self._volatile
        if name in self._perm.weights:
            return self._perm
        return None

    def _choose_store_for_name(
        self,
        name: str,
        *,
        persist: bool | None,
        kind: str,
    ) -> _ResourceStore:
        """
        Decide which store (perm/volatile) to use for an existing object (pulse, wf, etc.).

        If persist is None and the name exists in *both* stores, we require the caller
        to disambiguate by passing persist=True/False.
        """
        candidates: list[_ResourceStore] = []
        if name in self._perm.pulses:
            candidates.append(self._perm)
        if name in self._volatile.pulses:
            candidates.append(self._volatile)

        if not candidates:
            raise KeyError(f"{kind} '{name}' not found in any store.")

        if persist is None:
            if len(candidates) > 1:
                raise ValueError(
                    f"{kind} '{name}' exists in both permanent and volatile stores; "
                    "pass persist=True/False to choose which one to use."
                )
            return candidates[0]

        return self._perm if persist else self._volatile


    def _ensure_weight_exists(self, name: str) -> None:
        """Raise if `name` is not a known integration-weight in either store."""
        if (name not in self._volatile.weights) and (name not in self._perm.weights):
            raise KeyError(f"integration_weight '{name}' not found in stores.")

    @staticmethod
    def _normalize_digital_marker(dm: str | bool | None) -> str:
        """Normalize digital_marker to 'ON'/'OFF'/string, default 'ON'."""
        if dm is True or dm is None:
            return "ON"
        if dm is False:
            return "OFF"
        return str(dm)
    

    def _unique_name(self, base: str, kind: str) -> str:
        """
        Generate a name that is unique across perm+volatile stores.

        kind: "pulse" or "waveform".
        """
        if kind == "pulse":
            dicts = [self._perm.pulses, self._volatile.pulses]
        elif kind == "waveform":
            dicts = [self._perm.waveforms, self._volatile.waveforms]
        else:
            raise ValueError(f"Unknown kind for _unique_name: {kind!r}")

        existing: set[str] = set()
        for d in dicts:
            existing.update(d.keys())

        name = base
        i = 1
        while name in existing:
            name = f"{base}_{i}"
            i += 1
        return name
    
    
    @staticmethod
    def _normalize_wf_samples(samples, *, label: str = "waveform"):
        """
        Normalize waveform samples so they are safe for serialization:

        - 1D numpy array      -> list[float]
        - numpy scalar        -> float
        - list/tuple          -> list[float]
        - other numeric types -> unchanged

        Raises on non-1D arrays.
        """

        # 1D numpy array -> list[float]
        if isinstance(samples, np.ndarray):
            if samples.ndim != 1:
                raise ValueError(f"{label}: numpy array must be 1D, got shape {samples.shape}.")
            return [float(x) for x in samples.tolist()]

        # numpy scalar -> float
        if hasattr(samples, "item") and not isinstance(samples, (list, tuple, dict, str, bytes)):
            try:
                return float(samples.item())
            except Exception:
                # if .item() misbehaves, fall through
                pass

        # list/tuple -> list[float]
        if isinstance(samples, (list, tuple)):
            return [float(x) for x in samples]

        # leave plain ints/floats (constants) and anything already clean
        return samples
    
    
    # ---------- save / load permanent part only -----------------
    def save_json(self, path: str):
        json.dump(self._perm.as_dict(), open(path, "w"), indent=2)

    @classmethod
    def from_json(cls, path: str) -> "PulseOperationManager":
        mgr = cls()
        mgr._perm.clear()
        mgr._perm.load_from_dict(json.load(open(path)))
        mgr._volatile.clear()
        _logger.info(f"Loaded pulse files from: {path}")
        return mgr

    def clear_temporary(self):                 # toss volatile store
        self._volatile.clear()

    # ─────────────────────────────────────────────────────────────
    #  Low-level validators
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def _validate_waveform(kind: str, sample):
        if kind not in ("constant", "arbitrary"):
            raise ValueError("Waveform kind must be 'constant' or 'arbitrary'.")
        if kind == "constant":
            if abs(sample) > MAX_AMPLITUDE:
                raise ValueError("Amplitude exceeds MAX_AMPLITUDE.")
        else:
            if not isinstance(sample, list):
                raise ValueError("Arbitrary waveform requires sample list.")
            if any(abs(x) > MAX_AMPLITUDE for x in sample):
                raise ValueError("Sample exceeds MAX_AMPLITUDE.")

    def _assert_element_known(self, element: str) -> None:
        """
        Optional safety check: verify that `element` is in the manager's known list.

        Behavior:
        - If self.elements is empty, do *not* enforce anything (accept all elements).
        - If self.elements is non-empty, require that `element` appears in it (or is '*').
        """
        # No element list provided -> accept anything
        if not getattr(self, "elements", None):
            return

        if element not in self.elements and element != "*":
            raise ValueError(
                f"Element {element!r} is not in PulseOperationManager.elements: "
                f"{sorted(self.elements)!r}."
            )


    # ─────────────────────────────────────────────────────────────
    #  Public add-helpers  (persist = True ➜ permanent store)
    # ─────────────────────────────────────────────────────────────
    def add_waveform(
        self,
        name: str,
        kind: str,
        sample,
        *,
        persist: bool = True,
    ):
        """
        Register or overwrite an analog waveform.

        kind: 'constant' or 'arbitrary'
        sample:
        - constant: scalar
        - arbitrary: 1D list/array of floats
        """
        # NEW: protect reserved waveform IDs from being created/overwritten here
        if self._is_reserved_waveform_name(name):
            raise ValueError(
                f"Waveform name {name!r} is reserved for the canonical readout. "
                "Use modify_waveform(...) to change its contents instead."
            )

        if kind == "arbitrary":
            sample = self._normalize_wf_samples(sample, label=f"waveform '{name}'")

        self._validate_waveform(kind, sample)
        target = self._store(persist=persist)
        target.waveforms[name] = {
            "type": kind,
            ("sample" if kind == "constant" else "samples"): sample,
        }


    def create_control_pulse(
        self,
        element: str,
        op: str,
        *,
        length: int,
        pulse_name: str | None = None,
        I_wf_name: str | None = None,
        Q_wf_name: str | None = None,
        I_samples=None,
        Q_samples=None,
        digital_marker: str | bool | None = "ON",
        persist: bool = False,
        override: bool = False,
    ) -> PulseOp:
        """
        Strict helper for creating a *control* pulse bound to (element, op).

        - Validates element name.
        - Respects reserved op_ids and pulse names.
        - Errors on accidental overwrite unless override=True.
        """
        self._assert_element_known(element)

        if op in self._RESERVED_OP_IDS:
            raise ValueError(
                f"Operation id {op!r} is reserved for the built-in readout pulse; "
                "use modify_pulse()/modify_waveform() instead of create_control_pulse(...)."
            )

        if pulse_name is not None and self._is_reserved_pulse_name(pulse_name):
            raise ValueError(
                f"Pulse name {pulse_name!r} is reserved; you cannot create it explicitly."
            )

        store = self._store(persist=persist)

        if pulse_name is not None and (not override) and (pulse_name in store.pulses):
            raise ValueError(
                f"Pulse '{pulse_name}' already exists in "
                f"{'permanent' if persist else 'volatile'} store. "
                "Use modify_pulse(...) or pass override=True if you really want to overwrite it."
            )

        # Optional: disallow silent op remap unless override
        if not override and hasattr(self, "operations") and op in self.operations:
            raise ValueError(
                f"Operation id '{op}' already mapped to pulse '{self.operations[op]}'. "
                "Pass override=True if you want to remap it."
            )

        patch = PulseOp(
            element=element,
            op=op,
            pulse=pulse_name,
            type="control",
            length=int(length),
            digital_marker=digital_marker,
            I_wf_name=I_wf_name,
            Q_wf_name=Q_wf_name,
            I_wf=I_samples,
            Q_wf=Q_samples,
            int_weights_mapping=None,
            int_weights_defs=None,
        )

        self.register_pulse_op(patch, override=override, persist=persist)
        return self.get_pulseOp_by_element_op(element, op, include_volatile=not persist)

    def create_measurement_pulse(
        self,
        element: str,
        op: str,
        *,
        length: int,
        pulse_name: str | None = None,
        I_wf_name: str | None = None,
        Q_wf_name: str | None = None,
        I_samples=None,
        Q_samples=None,
        digital_marker: str | bool | None = "ON",
        int_weights_mapping: dict[str, str] | str | None = None,
        int_weights_defs: dict[str, tuple[float, float, int]] | None = None,
        persist: bool = False,
        override: bool = False,
    ) -> PulseOp:
        """
        Strict helper for creating a *measurement* pulse.

        You may *not* use this to create or replace the canonical readout pulse.
        """
        self._assert_element_known(element)

        # Canonical readout is built-in and reserved.
        if op in self._RESERVED_OP_IDS or pulse_name == self.READOUT_PULSE_NAME:
            raise ValueError(
                "The canonical readout pulse is created automatically and is reserved. "
                "Tune it via modify_pulse(), modify_waveform() and update_integration_weight()."
            )

        store = self._store(persist=persist)

        if pulse_name is not None and (not override) and (pulse_name in store.pulses):
            raise ValueError(
                f"Pulse '{pulse_name}' already exists in "
                f"{'permanent' if persist else 'volatile'} store. "
                "Use modify_pulse(...) or pass override=True if you really want to overwrite it."
            )

        if not override and hasattr(self, "operations") and op in self.operations:
            raise ValueError(
                f"Operation id '{op}' already mapped to pulse '{self.operations[op]}'. "
                "Pass override=True if you want to remap it."
            )

        patch = PulseOp(
            element=element,
            op=op,
            pulse=pulse_name,
            type="measurement",
            length=int(length),
            digital_marker=digital_marker,
            I_wf_name=I_wf_name,
            Q_wf_name=Q_wf_name,
            I_wf=I_samples,
            Q_wf=Q_samples,
            int_weights_mapping=int_weights_mapping,
            int_weights_defs=int_weights_defs,
        )

        self.register_pulse_op(patch, override=override, persist=persist)
        return self.get_pulseOp_by_element_op(element, op, include_volatile=not persist)


    def remove_pulse(self, pulse_name: str, *, persist: bool | None = None) -> None:
        """
        Remove a pulse from the manager and clean up all mappings.

        - Refuses to delete reserved pulses (e.g., 'readout_pulse').
        - If the name exists in both permanent and volatile stores and
          persist is None, forces the caller to disambiguate.
        """
        if self._is_reserved_pulse_name(pulse_name):
            raise ValueError(
                f"Pulse '{pulse_name}' is reserved and cannot be removed. "
                "You can still modify its length, waveforms and integration-weights."
            )

        # Determine which store to touch
        candidates: list[_ResourceStore] = []
        if pulse_name in self._perm.pulses:
            candidates.append(self._perm)
        if pulse_name in self._volatile.pulses:
            candidates.append(self._volatile)

        if not candidates:
            raise KeyError(f"Pulse '{pulse_name}' not found in any store.")

        if persist is None:
            if len(candidates) > 1:
                raise ValueError(
                    f"Pulse '{pulse_name}' exists in both permanent and volatile stores; "
                    "pass persist=True/False to choose which one to delete."
                )
            store = candidates[0]
        else:
            store = self._perm if persist else self._volatile
            if pulse_name not in store.pulses:
                raise KeyError(
                    f"Pulse '{pulse_name}' not found in "
                    f"{'permanent' if persist else 'volatile'} store."
                )

        # Remove from the chosen store
        del store.pulses[pulse_name]

        # Remove any element-op mappings pointing to this pulse in both stores
        for s in (self._perm, self._volatile):
            for el, ops in list(s.el_ops.items()):
                for op_id, p_name in list(ops.items()):
                    if p_name == pulse_name:
                        del ops[op_id]
                if not ops:
                    del s.el_ops[el]

        # Remove global op-id mappings that refer to this pulse
        if hasattr(self, "operations"):
            for op_id, p_name in list(self.operations.items()):
                if p_name == pulse_name:
                    del self.operations[op_id]


    def add_digital_waveform(
        self,
        name: str,
        samples: list[tuple[int, int]],
        *,
        persist: bool = True,
    ):
        """
        Register or overwrite a digital waveform.

        *samples* must be a list of (value, duration_cc) with value ∈ {0,1}.
        """
        for idx, (v, _) in enumerate(samples):
            if v not in (0, 1):
                raise ValueError(f"digital_waveform[{idx}] has value {v}; must be 0 or 1.")
        self._store(persist=persist).dig_waveforms[name] = {"samples": samples}



    def add_pulse(
        self,
        name: str,
        op_type: str,
        length: int,
        I_wf_name: str,
        Q_wf_name: str,
        *,
        digital_marker: str | bool | None = "ON",
        int_weights_mapping: dict[str, str] | str | None = None,
        int_weights_defs: dict[str, tuple[float, float, int]] | None = None,
        persist: bool = True,
    ):
        """
        Register or overwrite a pulse in the chosen store.
        """
        target = self._store(persist=persist)

        pulse: dict[str, Any] = {
            "operation": op_type,
            "length": length,
            "waveforms": {"I": I_wf_name, "Q": Q_wf_name},
            "digital_marker": self._normalize_digital_marker(digital_marker),
        }

        iw_map = self._resolve_int_weights_for_measurement(
            pulse_name=name,
            op_type=op_type,
            length=length,
            target=target,
            persist=persist,
            int_weights_mapping=int_weights_mapping,
            int_weights_defs=int_weights_defs,
        )
        if iw_map is not None:
            pulse["integration_weights"] = iw_map

        target.pulses[name] = pulse


    def add_int_weight(
        self,
        name: str,
        cos_w,
        sin_w,
        length: int,
        *,
        persist: bool = True,
    ):
        """
        Convenience: single-segment integration weight.
        """
        # NEW: prevent creating reserved readout weights via add_int_weight
        if self._is_reserved_weight_name(name):
            raise ValueError(
                f"integration_weight '{name}' is reserved for the canonical readout. "
                "Use update_integration_weight(...) to change its contents instead."
            )

        self._store(persist=persist).weights[name] = {
            "cosine": [(cos_w, length)],
            "sine":   [(sin_w, length)],
        }

    def add_int_weight_segments(
        self,
        name: str,
        cosine_segments: list[tuple[float, int]],
        sine_segments: list[tuple[float, int]],
        *,
        persist: bool = True,
    ):
        """
        Register a time-dependent integration-weight: lists of (amplitude, length_cc).
        """

        if self._is_reserved_weight_name(name):
            raise ValueError(
                f"integration_weight '{name}' is reserved for the canonical readout. "
                "Use update_integration_weight(...) to change its contents instead."
            )
    
        if not (isinstance(cosine_segments, list) and isinstance(sine_segments, list)):
            raise TypeError("cosine_segments and sine_segments must be lists of (amp, len_cc)")

        for lab, segs in (("cosine", cosine_segments), ("sine", sine_segments)):
            for i, (amp, L) in enumerate(segs):
                if not isinstance(L, int) or L <= 0:
                    raise ValueError(f"{lab}[{i}] has invalid length {L} (must be positive int)")
                if not isinstance(amp, (int, float)):
                    raise ValueError(f"{lab}[{i}] amplitude must be a number")

        self._store(persist=persist).weights[name] = {
            "cosine": list(cosine_segments),
            "sine":   list(sine_segments),
        }

    def add_operation(self, op_id: str, pulse_name: str):
        """
        Register or overwrite the global mapping  op_id → pulse_name.
        """
        if not hasattr(self, "operations"):
            self.operations: Dict[str, str] = {
                "const": "const_pulse",
                "zero":  "zero_pulse",
            }

        # NEW: don't let 'readout' be mapped to anything but the canonical pulse
        if op_id in self._RESERVED_OP_IDS and pulse_name != self.READOUT_PULSE_NAME:
            raise ValueError(
                f"Operation id {op_id!r} is reserved for '{self.READOUT_PULSE_NAME}'. "
                f"You tried to map it to '{pulse_name}'."
            )

        self.operations[op_id] = pulse_name


    # ─────────────────────────────────────────────────────────────
    #  High-level helper  register_pulse_op
    # ─────────────────────────────────────────────────────────────
    def register_pulse_op(
        self,
        p: PulseOp,
        *,
        override: bool = False,
        persist: bool = False,
        warning_flag: bool = True,
    ):
        """
        Register a PulseOp.

        Minimal required:
          - p.element
          - p.op OR p.pulse
          - p.type
          - p.length
          - at least one of (I_wf / I_wf_name) or (Q_wf / Q_wf_name)

        If p.pulse is missing, a unique name is auto-generated:
            "<element>_<op>_pulse[_N]"

        If only one quadrature is provided (I or Q), the other is auto-filled
        with zeros (if the provided one has samples).

        If waveform samples are provided but names are missing, unique names are
        auto-generated:
            "<element>_<op>_I[_N]", "<element>_<op>_Q[_N]"
        """
        store = self._store(persist=persist)

        # ---- basic sanity checks ----------------------------------------
        if not p.element:
            raise ValueError("PulseOp.element is required.")
        if p.type is None or p.length is None:
            raise ValueError("PulseOp.type and PulseOp.length are required.")
        if p.op is None and p.pulse is None:
            raise ValueError("At least one of PulseOp.op or PulseOp.pulse must be provided.")

        if (
            p.I_wf_name is None and p.I_wf is None
        ) and (
            p.Q_wf_name is None and p.Q_wf is None
        ):
            raise ValueError(
                "You must provide at least one of "
                "(I_wf or I_wf_name) or (Q_wf or Q_wf_name) to define the pulse shape."
            )

        # ---- determine op_id early --------------------------------------
        if p.op is not None:
            op_id = p.op
        elif p.pulse is not None:
            op_id = p.pulse.split("_pulse")[0]
        else:
            raise ValueError("Cannot infer op_id; provide PulseOp.op or PulseOp.pulse.")

        # ---- auto-generate pulse name if needed -------------------------
        if p.pulse is None:
            base_pulse_name = f"{p.element}_{op_id}_pulse"
            p.pulse = self._unique_name(base_pulse_name, kind="pulse")

        # ---- fast path: pulse exists and we're not overriding -----------
        if p.pulse in store.pulses and not override:
            store.el_ops.setdefault(p.element, {})[op_id] = p.pulse
            self.add_operation(op_id, p.pulse)
            return

        # ---- fill missing quadrature with zeros when samples exist ------
        def _zero_like(other):
            """Return a zero waveform with 'similar shape' to `other`."""
            if isinstance(other, np.ndarray):
                return np.zeros_like(other) if other.ndim == 1 else 0.0
            if isinstance(other, (list, tuple)):
                return [0.0] * len(other)
            return 0.0

        if p.I_wf is None and p.I_wf_name is None and p.Q_wf is not None:
            p.I_wf = _zero_like(p.Q_wf)
        if p.Q_wf is None and p.Q_wf_name is None and p.I_wf is not None:
            p.Q_wf = _zero_like(p.I_wf)

        # ---- auto-generate waveform names when we have samples ----------
        if p.I_wf is not None and p.I_wf_name is None:
            base_I = f"{p.element}_{op_id}_I"
            p.I_wf_name = self._unique_name(base_I, kind="waveform")
        if p.Q_wf is not None and p.Q_wf_name is None:
            base_Q = f"{p.element}_{op_id}_Q"
            p.Q_wf_name = self._unique_name(base_Q, kind="waveform")

        # final guard: must have both names resolved
        if p.I_wf_name is None or p.Q_wf_name is None:
            raise ValueError(
                "I_wf_name and Q_wf_name must be resolvable. "
                "This usually means neither samples nor names were provided "
                "for one of the quadratures."
            )

        # ---- create / update waveforms ----------------------------------
        for ch, name, data in (("I", p.I_wf_name, p.I_wf), ("Q", p.Q_wf_name, p.Q_wf)):
            if data is None:
                if name not in store.waveforms:
                    raise ValueError(f"{ch}-waveform '{name}' missing samples.")
                continue

            # If it's a reserved waveform, route via modify_waveform instead of add_waveform
            if self._is_reserved_waveform_name(name):
                # make sure it exists already
                if name not in store.waveforms:
                    raise ValueError(
                        f"Reserved waveform '{name}' does not exist in the target store."
                    )
                self.modify_waveform(name, data, persist=None)
                continue

            data_norm = self._normalize_wf_samples(
                data,
                label=f"{ch}-waveform '{name}'",
            )
            kind = "constant" if isinstance(data_norm, (int, float)) else "arbitrary"
            self.add_waveform(name, kind, data_norm, persist=persist)

        # ---- integration-weight defaults / stemless handling ------------

        # ---- integration-weight defaults / handling --------------------
        if p.type == "measurement" and not (p.int_weights_mapping or p.int_weights_defs):
            if warning_flag:
                _logger.info(
                    "Measurement pulse '%s' has no integration-weights mapping; "
                    "defaults will be used.",
                    p.pulse,
                )

        # Special case: canonical readout op ("readout"), no IW mapping given.
        # Do NOT create any length-suffixed / duration-based labels here.
        # Just ensure the reserved triplet exists with the correct length,
        # and keep mapping 'cos','sin','minus_sin' → reserved readout_* weights.
        # ---- integration-weight defaults / readout special-case ---------
        is_canonical_readout = (
            p.type == "measurement"
            and (self._is_reserved_pulse_name(p.pulse) or op_id in self._RESERVED_OP_IDS)
        )

        if is_canonical_readout:
            # Canonical readout pulse:
            #  - Always use the reserved readout_*_weights
            #  - Keep any extra labels (e.g. 'rot_cos') the user added
            names = self._ensure_reserved_readout_triplet_len(p.length)

            base_map: dict[str, str] = {}
            if isinstance(p.int_weights_mapping, dict):
                base_map.update(p.int_weights_mapping)

            # Force the core labels to point at the reserved names
            base_map["cos"]       = names["cos"]
            base_map["sin"]       = names["sin"]
            base_map["minus_sin"] = names["minus_sin"]

            iw_mapping = base_map
            iw_defs    = None

        else:
            # Non-canonical measurement pulses keep the old behaviour
            if p.type == "measurement" and not (p.int_weights_mapping or p.int_weights_defs):
                if warning_flag:
                    _logger.info(
                        "Measurement pulse '%s' has no integration-weights mapping; "
                        "length-matched defaults will be used.",
                        p.pulse,
                    )

            use_stemless = (
                p.type == "measurement"
                and op_id == "readout"
                and (p.int_weights_mapping is None)
                and (p.int_weights_defs is None)
            )

            if use_stemless:
                # “readout-like” measurement pulses that are *not* the canonical one
                self._ensure_default_iw_triplet_stemless(store, p.length, persist=persist)
                iw_mapping = ""   # sentinel: handled in _resolve_int_weights_for_measurement
                iw_defs    = None
            else:
                iw_mapping = p.int_weights_mapping
                iw_defs    = p.int_weights_defs


        # ---- (re)create the pulse in the store --------------------------
        self.add_pulse(
            p.pulse,
            p.type,
            p.length,
            p.I_wf_name,
            p.Q_wf_name,
            digital_marker=p.digital_marker,
            int_weights_mapping=iw_mapping,
            int_weights_defs=iw_defs,
            persist=persist,
        )

        # ---- mappings ----------------------------------------------------
        self.add_operation(op_id, p.pulse)
        store.el_ops.setdefault(p.element, {})[op_id] = p.pulse
        _logger.info(f"pulse {p.pulse} with len {p.length} registered!")

    def get_pulse_waveforms(
        self,
        pulse_name: str,
        *,
        include_volatile: bool = True,
    ) -> tuple[float | list[float] | None, float | list[float] | None]:
        """
        Return the (I, Q) waveform data for `pulse_name`, or (None, None) if not found.
        Prints a warning rather than raising if missing.
        """
        store = self._pulse_store(pulse_name, include_volatile=include_volatile)
        if store is None:
            warnings.warn(f"Pulse '{pulse_name}' not found in any store; returning (None, None).")
            return None, None

        wf_map = store.pulses[pulse_name].get("waveforms", {})
        I_name = wf_map.get("I")
        Q_name = wf_map.get("Q")
        if I_name is None or Q_name is None:
            warnings.warn(
                f"Pulse '{pulse_name}' missing I/Q waveform assignment; returning (None, None)."
            )
            return None, None

        def _get_wf_data(name: str):
            # search volatile first if allowed
            if include_volatile and name in self._volatile.waveforms:
                wf = self._volatile.waveforms[name]
            elif name in self._perm.waveforms:
                wf = self._perm.waveforms[name]
            else:
                warnings.warn(f"Waveform '{name}' not found; returning None.")
                return None
            if wf["type"] == "constant":
                return wf.get("sample")
            return wf.get("samples")

        return _get_wf_data(I_name), _get_wf_data(Q_name)


    def get_pulseOp_by_element_op(
        self,
        element: str,
        op: str,
        *,
        include_volatile: bool = True,
        strict: bool = True,
    ) -> PulseOp | None:
        """
        Return a PulseOp determined *uniquely* by (element, op).

        Lookup order (no "search", just dict lookups):
        1) volatile.el_ops[element][op]  (if include_volatile)
        2) perm.el_ops[element][op]

        If the (element, op) mapping doesn't exist (or maps to a pulse not found),
        either raise (strict=True) or return None (strict=False).
        """
        # ---- 1) find pulse_name from the (element, op) mapping -----------
        pulse_name = None

        if include_volatile:
            maybe_ops = self._volatile.el_ops.get(element, {})
            if op in maybe_ops:
                pulse_name = maybe_ops[op]

        if pulse_name is None:
            maybe_ops = self._perm.el_ops.get(element, {})
            if op in maybe_ops:
                pulse_name = maybe_ops[op]

        if pulse_name is None:
            if strict:
                raise KeyError(f"(element={element!r}, op={op!r}) not mapped to any pulse.")
            return None

        # ---- 2) fetch the pulse def (prefer same store as the mapping) ----
        store = self._pulse_store(pulse_name, include_volatile=include_volatile)
        if store is None:
            if strict:
                raise KeyError(f"Pulse '{pulse_name}' for (element={element}, op={op}) not found.")
            return None

        pulse_def = store.pulses[pulse_name]

        # ---- 3) resolve waveforms and integration weights ----------------
        I_name = pulse_def.get("waveforms", {}).get("I")
        Q_name = pulse_def.get("waveforms", {}).get("Q")
        I_wf, Q_wf = self.get_pulse_waveforms(pulse_name, include_volatile=include_volatile)
        int_w = pulse_def.get("integration_weights")

        # ---- 4) build PulseOp (op is exactly the provided `op`) ----------
        return PulseOp(
            element=element,
            op=op,
            pulse=pulse_name,
            type=pulse_def.get("operation"),
            length=pulse_def.get("length"),
            digital_marker=pulse_def.get("digital_marker", True),
            I_wf_name=I_name,
            Q_wf_name=Q_name,
            I_wf=I_wf,
            Q_wf=Q_wf,
            int_weights_mapping=int_w,
            int_weights_defs=None,
        )


    def modify_pulse(
        self,
        pulse_name: str,
        *,
        new_length: int | None = None,
        new_digital_marker: str | bool | None = None,
        new_I_wf_name: str | None = None,
        new_Q_wf_name: str | None = None,
        persist: bool | None = None,
    ) -> PulseOp:
        """
        Modify basic properties of an existing pulse:

            - length
            - digital_marker
            - I/Q waveform bindings (names only)

        Does NOT allow renaming the pulse or changing its type.
        """
        store = self._pulse_store(pulse_name, include_volatile=True)
        if store is None:
            raise KeyError(f"Pulse '{pulse_name}' not found in any store.")

        # If persist is unspecified, default to the store where it currently lives
        if persist is None:
            persist = (store is self._perm)

        patch = PulseOp(
            element=None,   # will be inferred
            op=None,        # will be inferred
            pulse=pulse_name,
            type=None,
            length=new_length,
            digital_marker=new_digital_marker,
            I_wf_name=new_I_wf_name,
            Q_wf_name=new_Q_wf_name,
            I_wf=None,
            Q_wf=None,
            int_weights_mapping=None,   # keep existing mapping
            int_weights_defs=None,
        )

        self.modify_pulse_op(patch, persist=persist)

        # Return the updated PulseOp (if we can infer element/op)
        for s in (self._volatile, self._perm):
            for el, ops in s.el_ops.items():
                for op_id, p_name in ops.items():
                    if p_name == pulse_name:
                        return self.get_pulseOp_by_element_op(el, op_id, include_volatile=True)

        # Fallback: we modified the pulse but there's no element/op mapping
        return PulseOp(pulse=pulse_name)

    def modify_waveform(
        self,
        name: str,
        new_samples,
        *,
        persist: bool | None = None,
        allow_type_change: bool = False,
    ) -> None:
        """
        Replace the internal sample data of an existing waveform.

        - Keeps the waveform name.
        - By default preserves the existing type ('constant' or 'arbitrary').
        - If allow_type_change=True, allows:
            * constant  -> arbitrary (vector)
            * arbitrary -> constant  (scalar)
        - Enforces MAX_AMPLITUDE.
        - If present in both stores and persist is None, forces disambiguation.
        """
        candidates: list[_ResourceStore] = []
        if name in self._perm.waveforms:
            candidates.append(self._perm)
        if name in self._volatile.waveforms:
            candidates.append(self._volatile)

        if not candidates:
            raise KeyError(f"Waveform '{name}' not found in any store.")

        if persist is None:
            if len(candidates) > 1:
                raise ValueError(
                    f"Waveform '{name}' exists in both permanent and volatile stores; "
                    "pass persist=True/False to choose which one to edit."
                )
            store = candidates[0]
        else:
            store = self._perm if persist else self._volatile
            if name not in store.waveforms:
                raise KeyError(
                    f"Waveform '{name}' not found in "
                    f"{'permanent' if persist else 'volatile'} store."
                )

        wf = store.waveforms[name]
        kind = wf.get("type")

        if kind not in ("constant", "arbitrary"):
            raise ValueError(
                f"Waveform '{name}' has unknown type {kind!r}; expected 'constant' or 'arbitrary'."
            )

        # Helper: decide whether new_samples is “scalar-like” or “array-like”
        try:
            arr = np.asarray(new_samples)
        except Exception:
            arr = None

        is_scalar_like = (
            np.isscalar(new_samples)
            or (arr is not None and arr.ndim == 0)
        )

        # ---- existing type: CONSTANT -----------------------------------
        if kind == "constant":
            if is_scalar_like:
                # stay constant
                try:
                    sample = float(new_samples)
                except Exception as exc:
                    raise TypeError(
                        f"Waveform '{name}' is 'constant'; new_samples must be scalar-convertible."
                    ) from exc
                if abs(sample) > MAX_AMPLITUDE:
                    raise ValueError(
                        f"Waveform '{name}': amplitude {sample} exceeds "
                        f"MAX_AMPLITUDE={MAX_AMPLITUDE}."
                    )
                wf["type"] = "constant"
                wf["sample"] = sample
                wf.pop("samples", None)
            else:
                # vector-like new_samples
                if not allow_type_change:
                    raise TypeError(
                        f"Waveform '{name}' is 'constant'; new_samples must be scalar-convertible, "
                        "or pass allow_type_change=True to upgrade it to 'arbitrary'."
                    )
                # upgrade to arbitrary
                samples = self._normalize_wf_samples(
                    new_samples,
                    label=f"waveform '{name}'",
                )
                self._validate_waveform("arbitrary", samples)
                wf["type"] = "arbitrary"
                wf.pop("sample", None)
                wf["samples"] = samples

        # ---- existing type: ARBITRARY ----------------------------------
        else:  # kind == "arbitrary"
            if is_scalar_like and allow_type_change:
                # downgrade to constant
                try:
                    sample = float(new_samples)
                except Exception as exc:
                    raise TypeError(
                        f"Waveform '{name}' is 'arbitrary'; scalar new_samples must be numeric."
                    ) from exc
                if abs(sample) > MAX_AMPLITUDE:
                    raise ValueError(
                        f"Waveform '{name}': amplitude {sample} exceeds "
                        f"MAX_AMPLITUDE={MAX_AMPLITUDE}."
                    )
                wf["type"] = "constant"
                wf["sample"] = sample
                wf.pop("samples", None)
            else:
                # stay arbitrary; treat scalar as length-1 array if allow_type_change=False
                samples = self._normalize_wf_samples(
                    new_samples,
                    label=f"waveform '{name}'",
                )
                self._validate_waveform("arbitrary", samples)
                wf["type"] = "arbitrary"
                wf.pop("sample", None)
                wf["samples"] = samples

        store.waveforms[name] = wf

    def modify_integration_weights(
        self,
        pulse_name: str,
        new_mapping: dict[str, str],
        *,
        include_volatile: bool = True,
        allow_new_labels: bool = False,
    ) -> dict[str, str]:
        """
        Replace/update the integration_weights mapping for a MEASUREMENT pulse.

        - Verifies the pulse is measurement-type.
        - Verifies referenced integration_weights exist.
        - By default, only updates existing labels; if allow_new_labels=True,
          new labels can be added.
        - For the reserved readout pulse, protects the core 'cos', 'sin',
          'minus_sin' labels from being remapped away from the reserved weights.
        """
        store = self._pulse_store(pulse_name, include_volatile=include_volatile)
        if store is None:
            raise KeyError(f"Pulse '{pulse_name}' not found in any store.")

        pulse = store.pulses[pulse_name]
        if pulse.get("operation") != "measurement":
            raise ValueError(f"Pulse '{pulse_name}' is not a 'measurement' pulse.")

        # Protect core labels for the canonical readout pulse
        if self._is_reserved_pulse_name(pulse_name):
            forbidden = {"cos", "sin", "minus_sin"}
            touched = [k for k in new_mapping if k in forbidden]
            if touched:
                raise ValueError(
                    "The built-in readout pulse must keep its 'cos', 'sin' and 'minus_sin' "
                    "labels mapped to the reserved readout_*_weights. "
                    "Modify the weight contents instead via update_integration_weight(...)."
                )

        current = pulse.get("integration_weights", {}) or {}
        cur_labels = set(current.keys())
        new_labels = set(new_mapping.keys())

        if not allow_new_labels and not new_labels.issubset(cur_labels):
            unknown = sorted(new_labels - cur_labels)
            raise ValueError(
                f"Pulse '{pulse_name}' does not currently have integration-weight labels {unknown!r}. "
                "Pass allow_new_labels=True if you really want to add them."
            )

        # Ensure all referenced weights exist
        for wname in new_mapping.values():
            self._ensure_weight_exists(wname)

        updated = dict(current)
        updated.update(new_mapping)
        pulse["integration_weights"] = updated
        return updated

    # ─────────────────────────────────────────────────────────────
    #  High-level helper  modify_pulse_op  (partial-update version)
    # ─────────────────────────────────────────────────────────────
    def modify_pulse_op(
        self,
        p: PulseOp,
        *,
        persist: bool = False,
    ):
        """
        Partial-update version of register_pulse_op.

        - p.pulse MUST already exist in the chosen store (permanent vs. volatile).
        - Any field left as None on `p` is inherited from the existing pulse
          (except I_wf/Q_wf, which are only updated if provided).
        - If measurement and the length changes, default integration-weights are
          refreshed to the new length (stemless for readout).
        """
        store = self._store(persist=persist)

        if p.pulse not in store.pulses:
            other = self._store(persist=not persist)
            if p.pulse in other.pulses:
                where = "permanent" if persist else "volatile"
                raise KeyError(
                    f"Pulse '{p.pulse}' not found in {where} store "
                    f"(it exists in the other store). Choose the correct `persist`."
                )
            raise KeyError(
                f"Pulse '{p.pulse}' not found in "
                f"{'permanent' if persist else 'volatile'} store. "
                "Use `register_pulse_op` to create it first."
            )

        old = store.pulses[p.pulse]

        # ---- infer element/op if missing from mappings / operations -----
        element = p.element
        op_id   = p.op

        def _find_existing_element_and_op():
            cand: list[tuple[str, str]] = []
            for el, ops in store.el_ops.items():
                for k, v in ops.items():
                    if v == p.pulse:
                        cand.append((el, k))
            return cand

        if element is None or op_id is None:
            cand = _find_existing_element_and_op()
            if not cand and op_id is None and hasattr(self, "operations"):
                for k, v in self.operations.items():
                    if v == p.pulse:
                        op_id = k
                        break

            if element is None or op_id is None:
                if len(cand) == 1:
                    if element is None:
                        element = cand[0][0]
                    if op_id is None:
                        op_id = cand[0][1]
                elif len(cand) > 1:
                    raise ValueError(
                        f"modify_pulse_op needs element/op; '{p.pulse}' "
                        f"is mapped to multiple element/op pairs: {cand}"
                    )
                if op_id is None:
                    op_id = p.pulse.split("_pulse")[0]

        # ---- compute merged PulseOp -------------------------------------
        # ---- compute merged PulseOp -------------------------------------
        new_len = p.length if p.length is not None else old["length"]
        length_was_given = (p.length is not None)

        merged = PulseOp(
            element   = element,
            pulse     = p.pulse,
            op        = op_id,
            type      = p.type or old["operation"],
            length    = new_len,
            digital_marker = (
                p.digital_marker
                if p.digital_marker is not None
                else old.get("digital_marker", "ON")
            ),
            I_wf_name      = p.I_wf_name or old["waveforms"]["I"],
            Q_wf_name      = p.Q_wf_name or old["waveforms"]["Q"],
            I_wf           = p.I_wf,
            Q_wf           = p.Q_wf,
            int_weights_mapping = (
                p.int_weights_mapping
                if p.int_weights_mapping is not None
                else old.get("integration_weights")
            ),
            int_weights_defs    = p.int_weights_defs,
        )

        if merged.type == "measurement" and length_was_given:
            current_map = merged.int_weights_mapping or old.get("integration_weights") or {}

            if self._is_reserved_pulse_name(merged.pulse):
                # Canonical readout pulse: enforce reserved triplet has the new length
                self._ensure_reserved_readout_triplet_len(new_len)
                merged.int_weights_mapping = current_map

            else:
                # If the pulse is using stemless defaults, overwrite them to new_len.
                # (This is the "default integration weights" case you asked for.)
                is_dict_map = isinstance(current_map, dict)
                is_stemless_default = (
                    is_dict_map
                    and current_map.get("cos") == "cos_weights"
                    and current_map.get("sin") == "sin_weights"
                    and current_map.get("minus_sin") == "minus_sin_weights"
                )

                if is_stemless_default:
                    # overwrite cos_weights/sin_weights/minus_sin_weights to match new_len
                    self._ensure_default_iw_triplet_stemless(store, new_len, persist=persist)
                    merged.int_weights_mapping = current_map

                # If not stemless default, keep the existing behavior for mapping updates
                # (only switch to length-matched defaults when the pulse length actually changed).
                elif new_len != old["length"]:
                    if op_id == "readout":
                        names = self._ensure_default_iw_triplet_stemless(store, new_len, persist=persist)
                    else:
                        names = self._ensure_default_iw_triplet(store, new_len, persist=persist)
                    merged.int_weights_mapping = self._merge_iw_user_wins(names, current_map)

        # Recreate/overwrite via the common path; also updates el_ops/operations
        self.register_pulse_op(merged, override=True, persist=persist)


    def _resolve_int_weights_for_measurement(
        self,
        *,
        pulse_name: str,
        op_type: str,
        length: int,
        target: _ResourceStore,
        persist: bool,
        int_weights_mapping: dict[str, str] | str | None,
        int_weights_defs: dict[str, tuple[float, float, int]] | None,
    ) -> dict[str, str] | None:
        """
        Common logic for mapping integration-weights on a MEASUREMENT pulse.

        - If op_type != 'measurement' -> return None (no mapping).
        - If int_weights_defs is provided, new weights are created (error if exist).
        - If int_weights_mapping is a string:
            ""     -> stemless triplet: cos_weights, sin_weights, minus_sin_weights
            "760"  -> cos760_weights, sin760_weights, minus_sin760_weights
        - If mapping is dict, used as-is (after existence checks).
        - If nothing specified, create/use a length-suffixed default triplet.
        """
        if op_type != "measurement":
            return None

        # 0) Create new defs if requested
        if int_weights_defs:
            self._ensure_weights_do_not_exist_and_create(
                target,
                int_weights_defs,
                persist=persist,
            )

        # 1) Parse mapping intent
        user_map: dict[str, str] | None = None
        if isinstance(int_weights_mapping, str):
            stem = int_weights_mapping.strip()
            if stem == "":
                # stemless triplet
                user_map = {
                    "cos":       "cos_weights",
                    "sin":       "sin_weights",
                    "minus_sin": "minus_sin_weights",
                }
            else:
                user_map = {
                    "cos":       f"cos{stem}_weights",
                    "sin":       f"sin{stem}_weights",
                    "minus_sin": f"minus_sin{stem}_weights",
                }
        elif isinstance(int_weights_mapping, dict):
            user_map = dict(int_weights_mapping)

        # 2) If mapping provided but no defs, verify referenced weights exist
        if user_map and not int_weights_defs:
            missing = [w for w in user_map.values() if w not in target.weights]
            if missing:
                raise ValueError(
                    f"int_weights_mapping for pulse '{pulse_name}' references "
                    f"unknown integration_weights: {missing}. "
                    "Define them first (via add_int_weight or int_weights_defs=...)."
                )

        # 3) Defaults: create/use length-suffixed triplet if nothing specified
        if not user_map and not int_weights_defs:
            return self._ensure_default_iw_triplet(target, length, persist=persist)

        return user_map or {}


    # ─────────────────────────────────────────────────────────────
    #  Export to QM and inspection helpers
    # ─────────────────────────────────────────────────────────────
    def burn_to_config(self, cfg: Dict[str, Any], *, include_volatile=True):
        self._perm.merge_into(cfg)
        if include_volatile:
            self._volatile.merge_into(cfg)
        return cfg

    def print_state(self, *, include_volatile=True):
        import pprint
        def head(tag): print("="*30, tag, "="*30)
        head("PERMANENT")
        pprint.pprint(self._perm.as_dict())
        if include_volatile and any(
            (self._volatile.waveforms, self._volatile.pulses)):
            head("VOLATILE")
            pprint.pprint(self._volatile.as_dict())

    @staticmethod
    def _merge_iw_user_wins(
        base_defaults: dict[str, str],
        user_iw: dict[str, str] | None,
    ) -> dict[str, str]:
        """
        Merge integration-weight label maps so that user-specified labels override defaults.
        """
        final = dict(base_defaults)
        if user_iw:
            final.update(user_iw)
        return final

    @staticmethod
    def _default_iw_names_stemless() -> dict[str, str]:
        """Triplet without length suffix: cos/sin/minus_sin → *_weights."""
        return {
            "cos":       "cos_weights",
            "sin":       "sin_weights",
            "minus_sin": "minus_sin_weights",
        }

    def _ensure_reserved_readout_triplet_len(self, length: int) -> dict[str, str]:
        """
        Ensure the canonical reserved readout weights exist in the permanent store
        and have the specified length. Returns the canonical label->name mapping.
        """
        L = int(length)
        names = {
            "cos":       self.READOUT_IW_COS_NAME,
            "sin":       self.READOUT_IW_SIN_NAME,
            "minus_sin": self.READOUT_IW_MINUS_NAME,
        }

        for label, wname in names.items():
            try:
                # Explicitly set amplitudes + length; do not rely on name heuristics
                if label == "cos":
                    self.update_integration_weight(
                        wname,
                        cos_w=1.0,
                        sin_w=0.0,
                        length=L,
                        include_volatile=False,
                    )
                elif label == "sin":
                    self.update_integration_weight(
                        wname,
                        cos_w=0.0,
                        sin_w=1.0,
                        length=L,
                        include_volatile=False,
                    )
                else:  # "minus_sin"
                    self.update_integration_weight(
                        wname,
                        cos_w=0.0,
                        sin_w=-1.0,
                        length=L,
                        include_volatile=False,
                    )
            except KeyError:
                # If it doesn't exist yet in this manager, create it directly in perm store
                if label == "cos":
                    c_amp, s_amp = 1.0, 0.0
                elif label == "sin":
                    c_amp, s_amp = 0.0, 1.0
                else:  # "minus_sin"
                    c_amp, s_amp = 0.0, -1.0

                self._perm.weights[wname] = {
                    "cosine": [(c_amp, L)],
                    "sine":   [(s_amp, L)],
                }

        return names

    def _ensure_default_iw_triplet_stemless(
        self,
        target: _ResourceStore,
        length: int,
        *,
        persist: bool,
    ) -> dict[str, str]:
        """
        Ensure the stemless triplet exists with the given `length`.
        Overwrites existing ones (simple, predictable behavior).

        NOTE: `target` is kept for API compatibility; the actual store is
        chosen by `persist` inside add_int_weight.
        """
        names = self._default_iw_names_stemless()
        self.add_int_weight(names["cos"],       1.0,  0.0, length, persist=persist)
        self.add_int_weight(names["sin"],       0.0,  1.0, length, persist=persist)
        self.add_int_weight(names["minus_sin"], 0.0, -1.0, length, persist=persist)
        return names

    @staticmethod
    def _default_iw_names_for_length(length: int) -> dict[str, str]:
        """Triplet with length suffix: cosN_weights, sinN_weights, minus_sinN_weights."""
        L = int(length)
        return {
            "cos":       f"cos{L}_weights",
            "sin":       f"sin{L}_weights",
            "minus_sin": f"minus_sin{L}_weights",
        }

    def _ensure_default_iw_triplet(
        self,
        target: _ResourceStore,
        length: int,
        *,
        persist: bool,
    ) -> dict[str, str]:
        """
        Ensure a length-matched default integration-weight triplet exists in `target`.

        - Creates any missing weights
        - Never overwrites existing ones
        """
        names = self._default_iw_names_for_length(length)
        for key, (c, s) in {
            "cos":       (1.0,  0.0),
            "sin":       (0.0,  1.0),
            "minus_sin": (0.0, -1.0),
        }.items():
            wname = names[key]
            if wname not in target.weights:
                self.add_int_weight(wname, c, s, length, persist=persist)
        return names

    def _ensure_weights_do_not_exist_and_create(
        self,
        target: _ResourceStore,
        defs: dict[str, tuple[float, float, int]],
        *,
        persist: bool,
    ) -> None:
        """
        For each (name -> (cos, sin, len)) in defs:
        - error if weight name already exists in target
        - otherwise create it via add_int_weight
        """
        for wname in defs:
            if wname in target.weights:
                raise ValueError(
                    f"integration_weight '{wname}' already exists; refusing to overwrite. "
                    "Choose a new name."
                )
        for wname, (c, s, L) in defs.items():
            self.add_int_weight(wname, c, s, L, persist=persist)

    # ─────────────────────────────────────────────────────────────
    #  Integration-weight queries
    # ─────────────────────────────────────────────────────────────

    def get_integration_weights(
        self,
        name: str,
        *,
        include_volatile: bool = True,
        strict: bool = False,
    ) -> tuple[list[tuple[float, int]], list[tuple[float, int]]]:
        """
        Fetch an integration-weight definition by its *name*.

        Search order:
            1) volatile.weights[name] (if include_volatile)
            2) permanent.weights[name]

        Returns
        -------
        (cosine_segments, sine_segments)
            Each is a list of (amplitude: float, length_cc: int).

        Behavior if missing
        -------------------
        - strict=False (default): emits a warning and returns ([], []).
        - strict=True: raises KeyError.
        """
        store = self._weight_store(name, include_volatile=include_volatile)
        if store is None:
            msg = f"integration_weight '{name}' not found in stores."
            if strict:
                raise KeyError(msg)
            warnings.warn(msg)
            return [], []

        raw = store.weights[name]

        def _norm(lst):
            out: list[tuple[float, int]] = []
            for item in lst or []:
                try:
                    amp, L = item
                except Exception:
                    raise ValueError(
                        f"Malformed segment {item!r} in integration_weight '{name}'. "
                        "Expected (amplitude, length_cc)."
                    )
                if not isinstance(L, int) or L <= 0:
                    raise ValueError(
                        f"Invalid segment length {L!r} in integration_weight '{name}' "
                        "(must be positive int)."
                    )
                out.append((float(amp), int(L)))
            return out

        cosine = _norm(raw.get("cosine", []))
        sine   = _norm(raw.get("sine", []))
        return cosine, sine

    def get_integration_weight_info(
        self,
        name: str,
        *,
        include_volatile: bool = True,
        strict: bool = False,
    ) -> dict:
        """
        Inspect an integration weight and return segmentation info assuming:

          - cosine[i] and sine[i] describe the SAME time segment i
          - cosine[i][1] == sine[i][1] for all i

        Returns
        -------
        {
            "name": <str>,
            "num_segments": <int>,
            "segment_len": <int>,
            "segment_lens": [L0, L1, ...],
            "total_len": <int>,
            "cosine": [(amp_c, Lc), ...],
            "sine":   [(amp_s, Ls), ...],
        }
        """
        cosine, sine = self.get_integration_weights(
            name,
            include_volatile=include_volatile,
            strict=strict,
        )

        if not cosine and not sine:
            if strict:
                raise KeyError(f"integration_weight '{name}' not found or empty.")
            warnings.warn(
                f"get_integration_weight_info('{name}'): no segments found; returning empty dict."
            )
            return {}

        if len(cosine) != len(sine):
            msg = (
                f"Integration weight '{name}' has cosine[{len(cosine)}] vs "
                f"sine[{len(sine)}] segments. Expected same length."
            )
            if strict:
                raise ValueError(msg)
            warnings.warn(msg)

        num_segments = min(len(cosine), len(sine))
        segment_lens: list[int] = []

        for idx in range(num_segments):
            _, Lc = cosine[idx]
            _, Ls = sine[idx]
            if Lc != Ls:
                msg = (
                    f"Integration weight '{name}' segment {idx} length mismatch: "
                    f"cosine={Lc}, sine={Ls}. Expected identical."
                )
                if strict:
                    raise ValueError(msg)
                warnings.warn(msg)
            segment_lens.append(int(Lc))

        if not segment_lens:
            if strict:
                raise ValueError(
                    f"Integration weight '{name}' has no valid (cos,sin) segments."
                )
        uniq_lens = sorted(set(segment_lens))
        segment_len = uniq_lens[0]
        if len(uniq_lens) > 1:
            warnings.warn(
                f"Integration weight '{name}' has non-uniform segment lengths {uniq_lens}; "
                f"using first ({segment_len})."
            )

        total_len = sum(segment_lens)
        return {
            "name": name,
            "num_segments": num_segments,
            "segment_len": int(segment_len),
            "segment_lens": segment_lens[:],
            "total_len": int(total_len),
            "cosine": cosine,
            "sine": sine,
        }

    def get_integration_weight_len(
        self,
        name: str,
        *,
        include_volatile: bool = True,
        strict: bool = False,
    ) -> int | None:
        """
        Return the per-segment demod window length (segment_len from
        get_integration_weight_info). This is what measureMacro calls
        `_demod_weight_len`.

        If the weight can't be found and strict=False, return None;
        if strict=True, we'll raise from inside get_integration_weight_info.
        """
        info = self.get_integration_weight_info(
            name,
            include_volatile=include_volatile,
            strict=strict,
        )
        if not info:
            return None
        return info["segment_len"]

    def get_integration_weight_meta(
        self,
        name: str,
        *,
        include_volatile: bool = True,
        strict: bool = False,
    ) -> dict:
        """
        Return metadata for an integration-weight by *name*:
            {
              "name": <str>,
              "type": "scalar" | "segments",
              "cosine": [(amp, len_cc), ...],
              "sine":   [(amp, len_cc), ...],
              "num_cos_segments": <int>,
              "num_sin_segments": <int>
            }
        """
        cos, sin = self.get_integration_weights(
            name, include_volatile=include_volatile, strict=strict
        )
        ncos, nsin = len(cos), len(sin)
        iw_type = "segments" if (ncos > 1 or nsin > 1) else "scalar"
        return {
            "name": name,
            "type": iw_type,
            "cosine": cos,
            "sine": sin,
            "num_cos_segments": ncos,
            "num_sin_segments": nsin,
        }

    def is_segmented_integration_weight(
        self,
        name: str,
        *,
        include_volatile: bool = True,
        strict: bool = False,
    ) -> bool:
        """True if the weight has >1 segment on either cosine/sine."""
        meta = self.get_integration_weight_meta(
            name, include_volatile=include_volatile, strict=strict
        )
        return meta["type"] == "segments"

    def get_integration_weight_segments(
        self,
        name: str,
        *,
        include_volatile: bool = True,
        strict: bool = False,
    ) -> tuple[list[tuple[float, int]], list[tuple[float, int]]]:
        """
        Alias of get_integration_weights(...) for readability where 'segments'
        semantics are expected.
        """
        return self.get_integration_weights(
            name, include_volatile=include_volatile, strict=strict
        )

    @staticmethod
    def lincomb_segments(
        a: float,
        b: float,
        segA: list[tuple[float, int]],
        segB: list[tuple[float, int]],
    ) -> list[tuple[float, int]]:
        """
        Combine two segment lists (same segmentation) into a*segA + b*segB.
        Raises if segment counts or lengths differ.
        """
        if len(segA) != len(segB):
            raise ValueError("Segmented weights mismatch: different number of segments.")
        out: list[tuple[float, int]] = []
        for (ampA, LA), (ampB, LB) in zip(segA, segB):
            if LA != LB:
                raise ValueError("Segmented weights mismatch: segment lengths differ.")
            out.append((a * float(ampA) + b * float(ampB), int(LA)))
        return out

    # ─────────────────────────────────────────────────────────────
    #  Integration-weight updates and mappings
    # ─────────────────────────────────────────────────────────────

    def update_integration_weight(
        self,
        name: str,
        *,
        # Option A: constant form (any channel you pass will be overwritten)
        cos_w: float | None = None,
        sin_w: float | None = None,
        length: int | None = None,
        # Option B: full segment form (overwrites the provided channels)
        cosine_segments: list[tuple[float, int]] | None = None,
        sine_segments: list[tuple[float, int]] | None = None,
        include_volatile: bool = True,
    ):
        """
        Update an existing integration-weight (by *name*).

        Search order:
            1) volatile.weights[name] (if include_volatile)
            2) permanent.weights[name]

        You can update with either:
        - Constant form: cos_w/sin_w with length (sets to [(amp, length)])
        - Segment form: cosine_segments / sine_segments = list[(amp, len_cc)]
        - NEW: If ONLY 'length' is provided, use a default by inferring from the name:
            * "...cos..."        -> (cos=+1, sin=0)
            * "...minus_sin..."  -> (cos=0,  sin=-1)
            * "...sin..."        -> (cos=0,  sin=+1)
            * otherwise -> keep current amplitudes, update to the new length (warn)
        """
        store = self._weight_store(name, include_volatile=include_volatile)
        if store is None:
            raise KeyError(f"integration_weight '{name}' not found in any store.")

        current = store.weights[name]

        def _norm_and_validate(label: str, segs):
            if not isinstance(segs, list):
                raise ValueError(f"{label} must be a list of (amp, length_cc)")
            out: list[tuple[float, int]] = []
            for i, item in enumerate(segs):
                try:
                    amp, L = item
                except Exception:
                    raise ValueError(
                        f"{label}[{i}] malformed: {item!r}; expected (amp, length_cc)"
                    )
                if not isinstance(L, int) or L <= 0:
                    raise ValueError(f"{label}[{i}] invalid length {L!r}; must be positive int")
                if not isinstance(amp, (int, float)):
                    raise ValueError(f"{label}[{i}] amplitude must be a number")
                out.append((float(amp), int(L)))
            return out

        const_any = (cos_w is not None) or (sin_w is not None) or (length is not None)
        seg_any   = (cosine_segments is not None) or (sine_segments is not None)
        if const_any and seg_any:
            raise ValueError("Provide either constant form OR segment lists, not both.")

        if length is None and ((cos_w is not None) or (sin_w is not None)):
            raise ValueError("When using constant form, 'length' must be provided.")

        new_cos = current.get("cosine", [])
        new_sin = current.get("sine", [])

        if seg_any:
            if cosine_segments is not None:
                new_cos = _norm_and_validate("cosine_segments", cosine_segments)
            if sine_segments is not None:
                new_sin = _norm_and_validate("sine_segments", sine_segments)

        elif const_any:
            if length is not None and (not isinstance(length, int) or length <= 0):
                raise ValueError("length must be a positive int")

            if cos_w is not None:
                if not isinstance(cos_w, (int, float)):
                    raise ValueError("cos_w must be numeric")
                new_cos = [(float(cos_w), int(length))]
            if sin_w is not None:
                if not isinstance(sin_w, (int, float)):
                    raise ValueError("sin_w must be numeric")
                new_sin = [(float(sin_w), int(length))]

            if (cos_w is None) and (sin_w is None) and (length is not None):
                lname = name.lower()

                def _set_both(c_amp: float, s_amp: float):
                    return [(float(c_amp), length)], [(float(s_amp), length)]

                if "minus_sin" in lname or "minus-sin" in lname or "m_sin" in lname:
                    new_cos, new_sin = _set_both(0.0, -1.0)
                elif "cos" in lname:
                    new_cos, new_sin = _set_both(1.0, 0.0)
                elif "sin" in lname:
                    new_cos, new_sin = _set_both(0.0, 1.0)
                else:
                    warnings.warn(
                        f"update_integration_weight('{name}'): unrecognized type; "
                        "keeping current amplitudes and applying the new length."
                    )

                    def _rewrite_len(segs):
                        if not segs:
                            return [(0.0, length)]
                        return [(float(segs[0][0]), length)]

                    new_cos = _rewrite_len(new_cos)
                    new_sin = _rewrite_len(new_sin)

        store.weights[name] = {"cosine": new_cos, "sine": new_sin}

    def update_integration_weight_mapping(
        self,
        pulse_name: str,
        map_label: str,
        new_weight_name: str,
        *,
        include_volatile: bool = True,
    ):
        """
        Update an existing integration-weight mapping on a MEASUREMENT pulse.

        This method requires that `map_label` already exists for the pulse.
        If you want to add a new label, use `append_integration_weight_mapping`.

        Returns
        -------
        tuple[str, str]
            (old_weight_name, new_weight_name)
        """
        store = self._pulse_store(pulse_name, include_volatile=include_volatile)
        if store is None:
            raise KeyError(f"Pulse '{pulse_name}' not found in any store.")

        pulse = store.pulses[pulse_name]
        if pulse.get("operation") != "measurement":
            raise ValueError(f"Pulse '{pulse_name}' is not a 'measurement' pulse.")

        iw_map = pulse.get("integration_weights")
        if not isinstance(iw_map, dict):
            raise ValueError(
                f"Pulse '{pulse_name}' has no 'integration_weights' dict to update."
            )

        if map_label not in iw_map:
            raise KeyError(
                f"Label '{map_label}' does not exist on '{pulse_name}'. "
                f"Use append_integration_weight_mapping(...) to add it first."
            )

        self._ensure_weight_exists(new_weight_name)

        old_weight = iw_map[map_label]
        iw_map[map_label] = new_weight_name
        pulse["integration_weights"] = iw_map
        return old_weight, new_weight_name

    def append_integration_weight_mapping(
        self,
        pulse_name: str,
        map_label: str,
        weight_name: str,
        *,
        include_volatile: bool = True,
        override: bool = False,
    ):
        """
        Append a single integration-weight mapping to an existing MEASUREMENT pulse.

        Parameters
        ----------
        pulse_name : str
            Name of the measurement pulse (e.g., "readout_pulse").
        map_label : str
            The label/key to add under 'integration_weights' (e.g., "opt", "cos2").
        weight_name : str
            Name of an existing integration weight to map (e.g., "cos760_weights").
        override : bool, optional
            If False (default) and the label already exists, raise ValueError.

        Returns
        -------
        dict
            The updated integration_weights mapping.
        """
        store = self._pulse_store(pulse_name, include_volatile=include_volatile)
        if store is None:
            raise KeyError(f"Pulse '{pulse_name}' not found in any store.")

        pulse = store.pulses[pulse_name]
        if pulse.get("operation") != "measurement":
            raise ValueError(f"Pulse '{pulse_name}' is not a 'measurement' pulse.")

        self._ensure_weight_exists(weight_name)

        iw_map = pulse.setdefault("integration_weights", {})
        if (map_label in iw_map) and not override:
            raise ValueError(
                f"Label '{map_label}' already mapped on pulse '{pulse_name}'. "
                "Pass override=True to replace it."
            )

        iw_map[map_label] = weight_name
        pulse["integration_weights"] = iw_map
        return dict(iw_map)


    def display_op(
        self,
        target: str,
        op: str,
        domain: str = "both",
        *,
        include_volatile: bool = True,
        dt: float = 1e-9,
        zero_pad_factor: int = 16,
        freq_range: tuple[float, float] | None = (-10, 10),
        time_window: tuple[int, int] | None = None,
    ):
        """
        Plot the pulse bound to EXACT (element=target, op=op).

        Resolution (strict):
        1) volatile.el_ops[target][op]   (only if include_volatile=True)
        2) perm.el_ops[target][op]
        No wildcard, no global-fallback.  Errors if not found,
        or if the mapped pulse is missing in the same store.
        """

        # ---- exact element mapping (no wildcard, no global map) ----
        pulse_name = None
        mapping_store = None

        if include_volatile:
            pulse_name = self._volatile.el_ops.get(target, {}).get(op)
            if pulse_name is not None:
                mapping_store = "volatile"

        if pulse_name is None:
            pn = self._perm.el_ops.get(target, {}).get(op)
            if pn is not None:
                pulse_name = pn
                mapping_store = "permanent"

        if pulse_name is None:
            raise KeyError(
                f"No mapping for (element={target!r}, op={op!r}). "
                "This method does not use wildcard or global fallbacks."
            )

        # ---- the mapped pulse MUST exist in the SAME store as the mapping ----
        if mapping_store == "volatile":
            if pulse_name not in self._volatile.pulses:
                raise KeyError(
                    f"Mapping found in VOLATILE, but pulse '{pulse_name}' is not in volatile.pulses."
                )
        else:  # "permanent"
            if pulse_name not in self._perm.pulses:
                raise KeyError(
                    f"Mapping found in PERMANENT, but pulse '{pulse_name}' is not in perm.pulses."
                )

        # ---- delegate to pulse display ----
        return self.display_pulse(
            pulse_name,
            domain,
            include_volatile=include_volatile,
            dt=dt,
            zero_pad_factor=zero_pad_factor,
            freq_range=freq_range,
            time_window=time_window,
        )

    def display_pulse(
        self,
        pulse: str,
        domain="both",
        *,
        include_volatile: bool = True,
        dt=1e-9,
        zero_pad_factor=16,
        freq_range=(-10, 10),
        time_window=None,
    ):
        """
        Plot a complex pulse in time and/or frequency domains.

        Frequency-domain view shows TWO plots:
        1) Normalized |FFT| (linear scale)
        2) Raw |FFT| (log-scale on y-axis)

        Parameters
        ----------
        domain : {"both","time","frequency"}, optional
            Which domain(s) to plot. Default "both".
        dt : float, optional
            Sample spacing in seconds (default 1e-9).
        zero_pad_factor : int, optional
            Factor to extend the FFT length via zero-padding (default 16).
        freq_range : tuple(float, float) or None, optional
            (f_min, f_max) in MHz for the frequency plot x-axis.
        time_window : (int, int) or None, optional
            (t_begin, t_end) using 1-based sample numbers, inclusive of t_end.
            By convention, z[0] ↔ t=1. The window is applied to both plots and to the FFT.
        include_volatile : bool, optional
            Passed through to get_pulse_waveforms.

        Returns
        -------
        z : np.ndarray
            The complex waveform (after windowing if time_window was specified).
        """
        # Get waveform from pulse manager
        I_wf, Q_wf = self.get_pulse_waveforms(pulse, include_volatile=include_volatile)
        I_wf, Q_wf = np.array(I_wf), np.array(Q_wf)
        z_full = I_wf + 1j * Q_wf

        # Build window note for plot titles
        window_note = ""
        if time_window is not None:
            if isinstance(time_window, (tuple, list)) and len(time_window) == 2:
                t_begin, t_end = time_window
                window_note = f" (t={t_begin}..{t_end})"

        # Call compute_waveform_fft to handle all plotting
        t, z_windowed, f, mag_norm, mag_log = compute_waveform_fft(
            z_full,
            dt=dt,
            zero_pad_factor=zero_pad_factor,
            freq_range=freq_range,
            time_window=time_window,
            domain=domain,
            window_note=window_note,
        )

        return z_windowed


from typing import Type

def build_pulse_operation_manager_from_config(
    config: dict,
    mgr_cls: Type["PulseOperationManager"] = None,
) -> "PulseOperationManager":
    """
    Parse an existing QM-style configuration dictionary and return a
    PulseOperationManager whose *permanent* store reproduces that config.

    Everything found in the dict (waveforms, pulses, integration_weights,
    element-operation maps) is treated as PERMANENT. The volatile store
    is cleared.

    Raises
    ------
    ValueError – on any structural inconsistency.
    """
    if mgr_cls is None:
        mgr_cls = PulseOperationManager

    mgr = mgr_cls()
    # start with a clean slate
    mgr._perm.clear()
    mgr._volatile.clear()
    perm = mgr._perm

    # ── 1) Waveforms ────────────────────────────────────────────────
    wfs = config.get("waveforms")
    if not isinstance(wfs, dict):
        raise ValueError("Configuration missing or invalid 'waveforms' key (must be dict).")

    for wf_id, wf in wfs.items():
        if "type" not in wf:
            raise ValueError(f"Waveform '{wf_id}' missing 'type'.")
        kind = wf["type"]
        if kind == "constant":
            if "sample" not in wf:
                raise ValueError(f"Constant waveform '{wf_id}' missing 'sample'.")
        elif kind == "arbitrary":
            if "samples" not in wf:
                raise ValueError(f"Arbitrary waveform '{wf_id}' missing 'samples'.")
        else:
            raise ValueError(f"Waveform '{wf_id}' has invalid type '{kind}'.")
        perm.waveforms[wf_id] = wf

    # ── 1b) Digital waveforms ───────────────────────────────────────
    digs = config.get("digital_waveforms", {})
    if not isinstance(digs, dict):
        raise ValueError("'digital_waveforms' must be a dictionary if present.")
    for dw_name, dw in digs.items():
        samples = dw.get("samples")
        if not isinstance(samples, list):
            raise ValueError(f"Digital waveform '{dw_name}' needs a 'samples' list.")
        for idx, (v, _) in enumerate(samples):
            if v not in (0, 1):
                raise ValueError(
                    f"Digital waveform '{dw_name}' sample {idx} has value {v}; must be 0/1."
                )
        perm.dig_waveforms[dw_name] = dw

    # ── 2) Integration weights ──────────────────────────────────────
    weights = config.get("integration_weights")
    if not isinstance(weights, dict):
        raise ValueError("Configuration missing or invalid 'integration_weights' key (must be dict).")
    for iw_id, iw in weights.items():
        if "cosine" not in iw or "sine" not in iw:
            raise ValueError(f"Integration-weight '{iw_id}' needs 'cosine' and 'sine'.")
        perm.weights[iw_id] = iw

    # ── 3) Pulses ───────────────────────────────────────────────────
    pls = config.get("pulses")
    if not isinstance(pls, dict):
        raise ValueError("Configuration missing or invalid 'pulses' key (must be dict).")

    for p_id, p in pls.items():
        for req in ("operation", "length", "waveforms", "digital_marker"):
            if req not in p:
                raise ValueError(f"Pulse '{p_id}' missing '{req}'.")
        if p["operation"] not in ("control", "measurement"):
            raise ValueError(f"Pulse '{p_id}' has invalid op type '{p['operation']}'.")

        # waveform refs exist?
        for ch in ("I", "Q"):
            wf_name = p["waveforms"].get(ch)
            if wf_name not in perm.waveforms:
                raise ValueError(
                    f"Pulse '{p_id}' references unknown waveform '{wf_name}' on channel {ch}."
                )

        # measurement → validate int-weights
        if p["operation"] == "measurement":
            iw_map = p.get("integration_weights")
            if not isinstance(iw_map, dict):
                raise ValueError(f"Measurement pulse '{p_id}' needs 'integration_weights' dict.")
            for lbl, iw_name in iw_map.items():
                if iw_name not in perm.weights:
                    raise ValueError(
                        f"Pulse '{p_id}' integration_weights['{lbl}'] "
                        f"references unknown weight '{iw_name}'."
                    )

        perm.pulses[p_id] = p

    # ── 4) Element-specific operation maps ──────────────────────────
    perm.el_ops.clear()
    elems = config.get("elements", {})
    if not isinstance(elems, dict):
        if "elements" in config:
            raise ValueError("'elements' must be a dictionary if present.")
        # else: no elements defined is fine; leave el_ops empty.

    for el_id, el_cfg in elems.items():
        ops = el_cfg.get("operations", {})
        if not isinstance(ops, dict):
            raise ValueError(f"Element '{el_id}' operations must be a dict.")
        for op_name, pulse_name in ops.items():
            if pulse_name not in perm.pulses:
                raise ValueError(
                    f"Element '{el_id}' op '{op_name}' references unknown pulse '{pulse_name}'."
                )
        perm.el_ops[el_id] = dict(ops)

    return mgr


if __name__ == "__main__":
    pass
