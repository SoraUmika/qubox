"""PulseFactory — compile declarative pulse specs into waveform arrays.

PulseFactory reads ``pulse_specs.json`` and produces concrete waveform arrays
at runtime. It never persists waveform arrays — only the declarative specs
are source of truth.

This module is additive. The existing PulseOperationManager continues to work
for pulses loaded from the legacy ``pulses.json``. PulseFactory provides the
new declarative compilation path.
"""
from __future__ import annotations

import base64
import logging
import warnings
from typing import Any, Callable

import numpy as np

from ..core.types import MAX_AMPLITUDE
from ..tools.waveforms import (
    drag_gaussian_pulse_waveforms,
    kaiser_pulse_waveforms,
    slepian_pulse_waveforms,
    drag_cosine_pulse_waveforms,
    flattop_gaussian_waveform,
    flattop_cosine_waveform,
    flattop_tanh_waveform,
    flattop_blackman_waveform,
    CLEAR_waveform,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shape handler registry
# ---------------------------------------------------------------------------

ShapeHandler = Callable[[dict[str, Any]], tuple[list[float], list[float]]]
_SHAPE_REGISTRY: dict[str, ShapeHandler] = {}


def register_shape(name: str, handler: ShapeHandler) -> None:
    """Register a waveform shape handler."""
    _SHAPE_REGISTRY[name] = handler


def _handle_constant(params: dict) -> tuple[list[float], list[float]]:
    amp_I = float(params.get("amplitude_I", params.get("amplitude", 0.0)))
    amp_Q = float(params.get("amplitude_Q", 0.0))
    length = int(params["length"])
    return [amp_I] * length, [amp_Q] * length


def _handle_zero(params: dict) -> tuple[list[float], list[float]]:
    length = int(params.get("length", 16))
    return [0.0] * length, [0.0] * length


def _handle_drag_gaussian(params: dict) -> tuple[list[float], list[float]]:
    return drag_gaussian_pulse_waveforms(
        amplitude=float(params["amplitude"]),
        length=int(params["length"]),
        sigma=float(params["sigma"]),
        alpha=float(params.get("drag_coeff", params.get("alpha", 0.0))),
        anharmonicity=float(params.get("anharmonicity", 0.0)),
        detuning=float(params.get("detuning", 0.0)),
        subtracted=bool(params.get("subtracted", True)),
    )


def _handle_drag_cosine(params: dict) -> tuple[list[float], list[float]]:
    return drag_cosine_pulse_waveforms(
        amplitude=float(params["amplitude"]),
        length=int(params["length"]),
        alpha=float(params.get("drag_coeff", params.get("alpha", 0.0))),
        anharmonicity=float(params.get("anharmonicity", 0.0)),
        detuning=float(params.get("detuning", 0.0)),
    )


def _handle_kaiser(params: dict) -> tuple[list[float], list[float]]:
    return kaiser_pulse_waveforms(
        amplitude=float(params["amplitude"]),
        length=int(params["length"]),
        beta=float(params["beta"]),
        detuning=float(params.get("detuning", 0.0)),
        alpha=float(params.get("alpha", 0.0)),
        anharmonicity=float(params.get("anharmonicity", 0.0)),
    )


def _handle_slepian(params: dict) -> tuple[list[float], list[float]]:
    return slepian_pulse_waveforms(
        amplitude=float(params["amplitude"]),
        length=int(params["length"]),
        NW=float(params["NW"]),
        detuning=float(params.get("detuning", 0.0)),
        alpha=float(params.get("alpha", 0.0)),
        anharmonicity=float(params.get("anharmonicity", 0.0)),
    )


def _handle_flattop_gaussian(params: dict) -> tuple[list[float], list[float]]:
    wf = flattop_gaussian_waveform(
        amplitude=float(params["amplitude"]),
        flat_length=int(params["flat_length"]),
        rise_fall_length=int(params["rise_fall_length"]),
    )
    return wf, [0.0] * len(wf)


def _handle_flattop_cosine(params: dict) -> tuple[list[float], list[float]]:
    wf = flattop_cosine_waveform(
        amplitude=float(params["amplitude"]),
        flat_length=int(params["flat_length"]),
        rise_fall_length=int(params["rise_fall_length"]),
    )
    return wf, [0.0] * len(wf)


def _handle_flattop_tanh(params: dict) -> tuple[list[float], list[float]]:
    wf = flattop_tanh_waveform(
        amplitude=float(params["amplitude"]),
        flat_length=int(params["flat_length"]),
        rise_fall_length=int(params["rise_fall_length"]),
    )
    return wf, [0.0] * len(wf)


def _handle_flattop_blackman(params: dict) -> tuple[list[float], list[float]]:
    wf = flattop_blackman_waveform(
        amplitude=float(params["amplitude"]),
        flat_length=int(params["flat_length"]),
        rise_fall_length=int(params["rise_fall_length"]),
    )
    return wf, [0.0] * len(wf)


def _handle_clear(params: dict) -> tuple[list[float], list[float]]:
    env = CLEAR_waveform(
        t_duration=int(params["t_duration"]),
        t_kick=params["t_kick"],
        A_steady=float(params["A_steady"]),
        A_rise_hi=float(params["A_rise_hi"]),
        A_rise_lo=float(params["A_rise_lo"]),
        A_fall_lo=float(params["A_fall_lo"]),
        A_fall_hi=float(params["A_fall_hi"]),
    )
    I_wf = env.tolist() if isinstance(env, np.ndarray) else list(env)
    return I_wf, [0.0] * len(I_wf)


def _handle_arbitrary_blob(params: dict) -> tuple[list[float], list[float]]:
    warnings.warn(
        "arbitrary_blob pulse shape is a transitional format. "
        "Convert to a declarative shape when possible.",
        DeprecationWarning,
        stacklevel=3,
    )
    I_b64 = params.get("I_samples_b64", "")
    Q_b64 = params.get("Q_samples_b64", "")
    I_arr = np.frombuffer(base64.b64decode(I_b64), dtype=np.float64) if I_b64 else np.zeros(int(params.get("length", 16)))
    Q_arr = np.frombuffer(base64.b64decode(Q_b64), dtype=np.float64) if Q_b64 else np.zeros(len(I_arr))
    return I_arr.tolist(), Q_arr.tolist()


# Register all built-in shapes
register_shape("constant", _handle_constant)
register_shape("zero", _handle_zero)
register_shape("drag_gaussian", _handle_drag_gaussian)
register_shape("drag_cosine", _handle_drag_cosine)
register_shape("kaiser", _handle_kaiser)
register_shape("slepian", _handle_slepian)
register_shape("flattop_gaussian", _handle_flattop_gaussian)
register_shape("flattop_cosine", _handle_flattop_cosine)
register_shape("flattop_tanh", _handle_flattop_tanh)
register_shape("flattop_blackman", _handle_flattop_blackman)
register_shape("clear", _handle_clear)
register_shape("arbitrary_blob", _handle_arbitrary_blob)


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

def _apply_constraints(
    I_wf: list[float],
    Q_wf: list[float],
    constraints: dict[str, Any] | None,
) -> tuple[list[float], list[float]]:
    """Apply post-generation constraints to waveforms."""
    if not constraints:
        return I_wf, Q_wf

    max_amp = float(constraints.get("max_amplitude", MAX_AMPLITUDE))
    clip = bool(constraints.get("clip", True))
    pad_to = int(constraints.get("pad_to_multiple_of", 4))

    I_arr = np.asarray(I_wf, dtype=float)
    Q_arr = np.asarray(Q_wf, dtype=float)

    # Clipping
    if clip:
        peak = max(np.max(np.abs(I_arr)), np.max(np.abs(Q_arr)))
        if peak > max_amp:
            scale = max_amp / peak
            I_arr *= scale
            Q_arr *= scale
            _logger.warning(
                "Waveform clipped: peak=%.4f → max_amplitude=%.4f (scale=%.4f)",
                peak, max_amp, scale,
            )

    # Area normalization
    if constraints.get("normalize_area", False):
        total_area = np.sum(np.abs(I_arr + 1j * Q_arr))
        if total_area > 0:
            I_arr /= total_area
            Q_arr /= total_area

    # Zero-padding to multiple of N
    if pad_to > 1:
        pad_needed = (-len(I_arr)) % pad_to
        if pad_needed > 0:
            I_arr = np.pad(I_arr, (0, pad_needed))
            Q_arr = np.pad(Q_arr, (0, pad_needed))

    return I_arr.tolist(), Q_arr.tolist()


# ---------------------------------------------------------------------------
# PulseFactory
# ---------------------------------------------------------------------------

class PulseFactory:
    """Compile declarative pulse specs into waveform arrays.

    PulseFactory takes a ``pulse_specs.json``-format dict and produces
    concrete I/Q waveform pairs that can be registered in
    PulseOperationManager.

    Parameters
    ----------
    specs_data : dict
        Parsed contents of ``pulse_specs.json``.
    """

    def __init__(self, specs_data: dict[str, Any]):
        self._raw = specs_data
        self._specs: dict[str, dict] = specs_data.get("specs", {})
        self._weights: dict[str, dict] = specs_data.get("integration_weights", {})
        self._el_ops: dict[str, dict] = specs_data.get("element_operations", {})

    @property
    def spec_names(self) -> list[str]:
        """List of all defined pulse spec names."""
        return list(self._specs.keys())

    def compile_one(self, spec_name: str) -> tuple[list[float], list[float], dict]:
        """Compile a single pulse spec into I/Q waveforms.

        Parameters
        ----------
        spec_name : str
            Name of the spec in ``specs_data["specs"]``.

        Returns
        -------
        I_wf : list[float]
            In-phase waveform samples.
        Q_wf : list[float]
            Quadrature waveform samples.
        meta : dict
            Metadata including element, op, shape, and any measurement info.

        Raises
        ------
        KeyError
            If the spec name is not found.
        ValueError
            If the shape is not registered.
        """
        if spec_name not in self._specs:
            raise KeyError(f"Pulse spec '{spec_name}' not found. Available: {self.spec_names}")

        spec = self._specs[spec_name]
        shape = spec["shape"]
        params = dict(spec.get("params", {}))
        constraints = spec.get("constraints")
        metadata = dict(spec.get("metadata", {}))

        # Handle rotation_derived: resolve reference spec first
        if shape == "rotation_derived":
            return self._compile_rotation_derived(spec_name, spec)

        if shape not in _SHAPE_REGISTRY:
            raise ValueError(
                f"Unknown pulse shape '{shape}' in spec '{spec_name}'. "
                f"Registered shapes: {sorted(_SHAPE_REGISTRY.keys())}"
            )

        handler = _SHAPE_REGISTRY[shape]
        I_wf, Q_wf = handler(params)
        I_wf, Q_wf = _apply_constraints(I_wf, Q_wf, constraints)

        meta = {
            "element": spec.get("element", ""),
            "op": spec.get("op", ""),
            "shape": shape,
            "length": len(I_wf),
            **metadata,
        }

        return I_wf, Q_wf, meta

    def _compile_rotation_derived(
        self,
        spec_name: str,
        spec: dict,
    ) -> tuple[list[float], list[float], dict]:
        """Compile a rotation_derived spec by transforming a reference waveform."""
        params = spec.get("params", {})
        ref_name = params["reference_spec"]

        if ref_name not in self._specs:
            raise KeyError(
                f"Rotation spec '{spec_name}' references '{ref_name}' which is not defined."
            )

        # Compile reference (recursion handles chained derivations)
        ref_I, ref_Q, _ = self.compile_one(ref_name)
        w0 = np.asarray(ref_I) + 1j * np.asarray(ref_Q)

        theta = float(params.get("theta", np.pi))
        phi = float(params.get("phi", 0.0))
        d_lambda = float(params.get("d_lambda", 0.0))
        d_alpha = float(params.get("d_alpha", 0.0))
        d_omega = float(params.get("d_omega", 0.0))

        N = len(w0)
        phi_eff = phi + d_alpha

        dt = 1e-9
        T = N * dt
        lam0 = (np.pi / (2.0 * T)) if T > 0 else 1.0
        amp_scale = (theta / np.pi) * (1.0 + d_lambda / lam0)

        w_new = amp_scale * w0 * np.exp(-1j * phi_eff)

        if d_omega != 0.0:
            t_arr = (np.arange(N) - (N - 1) / 2.0) * dt
            w_new = w_new * np.exp(1j * d_omega * t_arr)

        I_wf = np.real(w_new).tolist()
        Q_wf = np.imag(w_new).tolist()

        constraints = spec.get("constraints")
        I_wf, Q_wf = _apply_constraints(I_wf, Q_wf, constraints)

        meta = {
            "element": spec.get("element", ""),
            "op": spec.get("op", ""),
            "shape": "rotation_derived",
            "reference": ref_name,
            "length": len(I_wf),
        }

        return I_wf, Q_wf, meta

    def compile_all(self) -> dict[str, tuple[list[float], list[float], dict]]:
        """Compile all pulse specs.

        Returns
        -------
        dict[str, tuple[list[float], list[float], dict]]
            Mapping from spec name to (I_wf, Q_wf, metadata).
        """
        results = {}
        for name in self._specs:
            try:
                results[name] = self.compile_one(name)
            except Exception as exc:
                _logger.error("Failed to compile pulse spec '%s': %s", name, exc)
                raise
        _logger.info("Compiled %d pulse specs", len(results))
        return results

    def register_all(self, pom, *, persist: bool = True, override: bool = True) -> int:
        """Compile all specs and register them in a PulseOperationManager.

        Parameters
        ----------
        pom : PulseOperationManager
            Target pulse manager.
        persist : bool
            Store in permanent (vs volatile) store.
        override : bool
            Overwrite existing pulses.

        Returns
        -------
        int
            Number of pulses registered.
        """
        compiled = self.compile_all()
        count = 0

        for name, (I_wf, Q_wf, meta) in compiled.items():
            element = meta.get("element", "")
            op = meta.get("op", "")
            if not element or not op:
                _logger.warning("Spec '%s' missing element/op, skipping registration", name)
                continue

            pulse_type = meta.get("pulse_type", "control")

            if pulse_type == "measurement":
                int_weights_mapping = meta.get("int_weights_mapping")
                pom.create_measurement_pulse(
                    element=element,
                    op=op,
                    length=len(I_wf),
                    I_samples=I_wf,
                    Q_samples=Q_wf,
                    int_weights_mapping=int_weights_mapping,
                    persist=persist,
                    override=override,
                )
            else:
                pom.create_control_pulse(
                    element=element,
                    op=op,
                    length=len(I_wf),
                    I_samples=I_wf,
                    Q_samples=Q_wf,
                    persist=persist,
                    override=override,
                )
            count += 1

        # Register integration weights
        for w_name, w_def in self._weights.items():
            w_type = w_def.get("type", "constant")
            if w_type == "constant":
                pom.add_int_weight(
                    w_name,
                    cos_w=float(w_def.get("cosine", 1.0)),
                    sin_w=float(w_def.get("sine", 0.0)),
                    length=int(w_def.get("length", 400)),
                )
            elif w_type == "segmented":
                cos_seg = [tuple(s) for s in w_def.get("cosine_segments", [])]
                sin_seg = [tuple(s) for s in w_def.get("sine_segments", [])]
                pom.add_int_weight_segments(w_name, cos_seg, sin_seg, persist=persist)

        _logger.info("Registered %d pulses from specs", count)
        return count
