# tools/pulses_converter.py
"""Convert legacy pulses.json to declarative pulse_specs.json.

This module provides the ``convert`` function and CLI entry point for
migrating from the legacy waveform-array format to the declarative
pulse specification format.

See docs/PULSE_SPEC_SCHEMA.md § 8 for the full migration specification.

Usage (CLI)
-----------
::

    python tools/pulses_converter.py \\
        --input config/pulses.json \\
        --output config/pulse_specs.json

Usage (API)
-----------
>>> from tools.pulses_converter import convert
>>> result = convert("config/pulses.json")
>>> result.save("config/pulse_specs.json")
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conversion result
# ---------------------------------------------------------------------------

@dataclass
class ConversionResult:
    """Result of a pulses.json → pulse_specs.json conversion."""
    specs: dict[str, dict] = field(default_factory=dict)
    integration_weights: dict[str, dict] = field(default_factory=dict)
    element_operations: dict[str, dict[str, str]] = field(default_factory=dict)
    matched: list[str] = field(default_factory=list)
    blobs: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise as a pulse_specs.json-format dict."""
        return {
            "schema_version": 1,
            "specs": self.specs,
            "integration_weights": self.integration_weights,
            "element_operations": self.element_operations,
        }

    def save(self, output_path: str | Path) -> Path:
        """Write the converted specs to a JSON file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            f.write("\n")
        _logger.info("Saved pulse_specs.json: %s", path)
        return path

    def summary(self) -> str:
        """Human-readable conversion summary."""
        lines = [
            f"Conversion Summary",
            f"  Total specs:  {len(self.specs)}",
            f"  Matched:      {len(self.matched)} (declarative)",
            f"  Blobs:        {len(self.blobs)} (arbitrary_blob fallback)",
            f"  Skipped:      {len(self.skipped)}",
            f"  Errors:       {len(self.errors)}",
        ]
        if self.blobs:
            lines.append(f"\n  Blobs (need manual conversion):")
            for b in self.blobs:
                lines.append(f"    - {b}")
        if self.errors:
            lines.append(f"\n  Errors:")
            for e in self.errors:
                lines.append(f"    - {e}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Shape detection
# ---------------------------------------------------------------------------

def _detect_shape(
    I_samples: np.ndarray,
    Q_samples: np.ndarray,
    pulse_name: str,
    pulse_data: dict,
) -> tuple[str, dict[str, Any]] | None:
    """Attempt to detect the declarative shape and parameters for a waveform.

    Returns (shape, params) if matched, or None if no match found.
    """
    # Check for constant waveform
    if _is_constant(I_samples, Q_samples):
        return "constant", {
            "amplitude_I": float(I_samples[0]) if len(I_samples) > 0 else 0.0,
            "amplitude_Q": float(Q_samples[0]) if len(Q_samples) > 0 else 0.0,
            "length": len(I_samples),
        }

    # Check for zero waveform
    if np.allclose(I_samples, 0.0, atol=1e-15) and np.allclose(Q_samples, 0.0, atol=1e-15):
        return "zero", {"length": len(I_samples)}

    # Check pulse_definitions for explicit shape info
    definitions = pulse_data.get("pulse_definitions", {})
    if definitions:
        detected = _match_from_definitions(definitions, I_samples, Q_samples, pulse_name)
        if detected is not None:
            return detected

    # Try DRAG Gaussian detection via parameter grid
    match = _try_drag_gaussian_fit(I_samples, Q_samples)
    if match is not None:
        return match

    return None


def _is_constant(I: np.ndarray, Q: np.ndarray) -> bool:
    """Check if waveform is constant (all samples identical)."""
    if len(I) == 0:
        return True
    return np.allclose(I, I[0], atol=1e-15) and np.allclose(Q, Q[0], atol=1e-15)


def _match_from_definitions(
    definitions: dict,
    I_samples: np.ndarray,
    Q_samples: np.ndarray,
    pulse_name: str,
) -> tuple[str, dict] | None:
    """Try to match against pulse_definitions section of pulses.json."""
    for def_name, def_data in definitions.items():
        shape_type = def_data.get("type", "")

        if shape_type == "drag_gaussian":
            params = {
                "amplitude": float(def_data.get("amplitude", 0.0)),
                "length": int(def_data.get("length", 16)),
                "sigma": float(def_data.get("sigma", 2.6667)),
                "drag_coeff": float(def_data.get("drag_coeff", def_data.get("alpha", 0.0))),
                "anharmonicity": float(def_data.get("anharmonicity", 0.0)),
                "detuning": float(def_data.get("detuning", 0.0)),
                "subtracted": bool(def_data.get("subtracted", True)),
            }
            # Verify by regenerating
            if _verify_drag_gaussian(I_samples, Q_samples, params):
                return "drag_gaussian", params

        elif shape_type == "drag_cosine":
            params = {
                "amplitude": float(def_data.get("amplitude", 0.0)),
                "length": int(def_data.get("length", 20)),
                "alpha": float(def_data.get("alpha", 0.0)),
                "anharmonicity": float(def_data.get("anharmonicity", 0.0)),
                "detuning": float(def_data.get("detuning", 0.0)),
            }
            if _verify_drag_cosine(I_samples, Q_samples, params):
                return "drag_cosine", params

    return None


def _try_drag_gaussian_fit(
    I_samples: np.ndarray,
    Q_samples: np.ndarray,
) -> tuple[str, dict] | None:
    """Brute-force DRAG Gaussian parameter detection."""
    from qubox_v2.tools.waveforms import drag_gaussian_pulse_waveforms

    length = len(I_samples)
    peak_amp = float(np.max(np.abs(I_samples)))

    if peak_amp < 1e-10:
        return None

    # Parameter grid (coarse)
    for sigma in [length / 6, length / 5, length / 4, length / 3]:
        for subtracted in [True, False]:
            try:
                I_gen, Q_gen = drag_gaussian_pulse_waveforms(
                    amplitude=peak_amp,
                    length=length,
                    sigma=sigma,
                    alpha=0.0,
                    anharmonicity=0.0,
                    detuning=0.0,
                    subtracted=subtracted,
                )
                I_gen = np.array(I_gen)
                Q_gen = np.array(Q_gen)

                if len(I_gen) != length:
                    continue

                # Scale to match
                if np.max(np.abs(I_gen)) > 0:
                    scale = np.max(np.abs(I_samples)) / np.max(np.abs(I_gen))
                    I_gen *= scale

                l2 = np.sqrt(np.sum((I_gen - I_samples) ** 2 + (Q_gen - Q_samples) ** 2))
                if l2 < 1e-10:
                    return "drag_gaussian", {
                        "amplitude": float(peak_amp * scale) if 'scale' in dir() else float(peak_amp),
                        "length": length,
                        "sigma": float(sigma),
                        "drag_coeff": 0.0,
                        "anharmonicity": 0.0,
                        "detuning": 0.0,
                        "subtracted": subtracted,
                    }
            except Exception:
                continue

    return None


def _verify_drag_gaussian(
    I_target: np.ndarray,
    Q_target: np.ndarray,
    params: dict,
) -> bool:
    """Verify that params reproduce the target waveform."""
    from qubox_v2.tools.waveforms import drag_gaussian_pulse_waveforms

    try:
        I_gen, Q_gen = drag_gaussian_pulse_waveforms(
            amplitude=params["amplitude"],
            length=params["length"],
            sigma=params["sigma"],
            alpha=params.get("drag_coeff", 0.0),
            anharmonicity=params.get("anharmonicity", 0.0),
            detuning=params.get("detuning", 0.0),
            subtracted=params.get("subtracted", True),
        )
        I_gen = np.array(I_gen)
        Q_gen = np.array(Q_gen)

        if len(I_gen) != len(I_target):
            return False

        l2 = np.sqrt(np.sum((I_gen - I_target) ** 2 + (Q_gen - Q_target) ** 2))
        return l2 < 1e-10
    except Exception:
        return False


def _verify_drag_cosine(
    I_target: np.ndarray,
    Q_target: np.ndarray,
    params: dict,
) -> bool:
    """Verify that params reproduce the target waveform."""
    from qubox_v2.tools.waveforms import drag_cosine_pulse_waveforms

    try:
        I_gen, Q_gen = drag_cosine_pulse_waveforms(
            amplitude=params["amplitude"],
            length=params["length"],
            alpha=params.get("alpha", 0.0),
            anharmonicity=params.get("anharmonicity", 0.0),
            detuning=params.get("detuning", 0.0),
        )
        I_gen = np.array(I_gen)
        Q_gen = np.array(Q_gen)

        if len(I_gen) != len(I_target):
            return False

        l2 = np.sqrt(np.sum((I_gen - I_target) ** 2 + (Q_gen - Q_target) ** 2))
        return l2 < 1e-10
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Core conversion
# ---------------------------------------------------------------------------

def convert(
    pulses_json_path: str | Path,
    *,
    definitions_path: str | Path | None = None,
) -> ConversionResult:
    """Convert a legacy pulses.json to pulse_specs.json format.

    Parameters
    ----------
    pulses_json_path : str | Path
        Path to the legacy pulses.json.
    definitions_path : str | Path | None
        Optional path to an additional file containing pulse_definitions.

    Returns
    -------
    ConversionResult
    """
    path = Path(pulses_json_path)
    data = json.loads(path.read_bytes())
    result = ConversionResult()

    wf_defs = data.get("waveforms", {})
    pulse_defs = data.get("pulses", {})
    int_weights_section = data.get("integration_weights", {})
    definitions = data.get("pulse_definitions", {})

    # Load additional definitions if provided
    if definitions_path is not None:
        def_path = Path(definitions_path)
        if def_path.exists():
            extra = json.loads(def_path.read_bytes())
            definitions.update(extra.get("pulse_definitions", {}))

    # Convert integration weights
    for w_name, w_data in int_weights_section.items():
        result.integration_weights[w_name] = _convert_weight(w_name, w_data)

    # Convert each pulse
    for pulse_name, pulse_data in pulse_defs.items():
        try:
            spec = _convert_pulse(pulse_name, pulse_data, wf_defs, definitions)
            if spec is not None:
                result.specs[pulse_name] = spec
                if spec["shape"] == "arbitrary_blob":
                    result.blobs.append(pulse_name)
                else:
                    result.matched.append(pulse_name)

                # Track element_operations
                element = spec.get("element", "")
                op = spec.get("op", "")
                if element and op:
                    result.element_operations.setdefault(element, {})[op] = pulse_name
            else:
                result.skipped.append(pulse_name)
        except Exception as exc:
            result.errors.append(f"{pulse_name}: {exc}")
            _logger.error("Failed to convert pulse '%s': %s", pulse_name, exc)

    return result


def _convert_pulse(
    pulse_name: str,
    pulse_data: dict,
    wf_defs: dict,
    definitions: dict,
) -> dict | None:
    """Convert a single pulse entry to a spec dict."""
    operation = pulse_data.get("operation", "control")
    length = int(pulse_data.get("length", 16))

    # Extract element and op from pulse name or structure
    # Legacy convention: "<element>_<op>" or just the pulse name
    element, op = _parse_pulse_name(pulse_name)

    # Resolve waveforms
    wf_refs = pulse_data.get("waveforms", {})
    I_ref = wf_refs.get("I")
    Q_ref = wf_refs.get("Q")

    I_wf_data = wf_defs.get(I_ref, {}) if I_ref else {}
    Q_wf_data = wf_defs.get(Q_ref, {}) if Q_ref else {}

    # Get samples
    I_samples = _get_samples(I_wf_data, length)
    Q_samples = _get_samples(Q_wf_data, length)

    if I_samples is None:
        return None

    # Try shape detection
    detected = _detect_shape(I_samples, Q_samples, pulse_name, {"pulse_definitions": definitions})

    if detected is not None:
        shape, params = detected
    else:
        # Fall back to arbitrary_blob
        shape = "arbitrary_blob"
        params = {
            "I_samples_b64": base64.b64encode(I_samples.tobytes()).decode("ascii"),
            "Q_samples_b64": base64.b64encode(Q_samples.tobytes()).decode("ascii"),
            "length": len(I_samples),
        }

    spec: dict[str, Any] = {
        "shape": shape,
        "element": element,
        "op": op,
        "params": params,
    }

    # Measurement pulse metadata
    if operation == "measurement":
        int_weights = pulse_data.get("integration_weights", {})
        digital_marker = pulse_data.get("digital_marker", "ON")
        spec["metadata"] = {
            "pulse_type": "measurement",
            "digital_marker": digital_marker,
            "int_weights_mapping": int_weights,
        }

    return spec


def _get_samples(wf_data: dict, fallback_length: int) -> np.ndarray | None:
    """Extract waveform samples from a waveform definition."""
    if not wf_data:
        return np.zeros(fallback_length)

    wf_type = wf_data.get("type", "arbitrary")

    if wf_type == "constant":
        sample = float(wf_data.get("sample", 0.0))
        return np.full(fallback_length, sample)

    if wf_type == "arbitrary":
        samples = wf_data.get("samples")
        if samples is not None:
            return np.array(samples, dtype=np.float64)

    return None


def _parse_pulse_name(name: str) -> tuple[str, str]:
    """Parse a legacy pulse name into (element, operation).

    Heuristics:
    - "qubit_x180" → ("qubit", "x180")
    - "resonator_readout" → ("resonator", "readout")
    - "x180" → ("qubit", "x180")  (common default)
    - "readout_pulse" → ("resonator", "readout")
    """
    parts = name.split("_", 1)

    known_elements = {"qubit", "resonator", "storage", "coupler"}

    if len(parts) == 2 and parts[0] in known_elements:
        return parts[0], parts[1]

    # Check for common operation prefixes
    op_prefixes = {"x180", "x90", "y180", "y90", "xn90", "yn90", "ref_r180",
                   "readout", "const", "zero"}
    if name in op_prefixes:
        element = "resonator" if "readout" in name else "qubit"
        return element, name

    # Default: first part is element, or use full name as op
    if len(parts) == 2:
        return parts[0], parts[1]

    return "", name


def _convert_weight(name: str, data: dict) -> dict:
    """Convert a legacy integration weight to spec format."""
    # Legacy format can be either constant-value or list-of-tuples
    if isinstance(data, dict):
        # Already structured
        cosine = data.get("cosine", data.get("cos", []))
        sine = data.get("sine", data.get("sin", []))

        if isinstance(cosine, (int, float)):
            # Constant weight
            return {
                "type": "constant",
                "cosine": float(cosine),
                "sine": float(sine) if isinstance(sine, (int, float)) else 0.0,
                "length": int(data.get("length", 400)),
            }
        elif isinstance(cosine, list):
            if cosine and isinstance(cosine[0], (list, tuple)):
                # Segmented
                return {
                    "type": "segmented",
                    "cosine_segments": [[float(s[0]), int(s[1])] for s in cosine],
                    "sine_segments": [[float(s[0]), int(s[1])] for s in (sine if isinstance(sine, list) else [])],
                }
            else:
                # List of values → segmented with 1-sample segments
                return {
                    "type": "segmented",
                    "cosine_segments": [[float(v), 4] for v in cosine],
                    "sine_segments": [[float(v), 4] for v in (sine if isinstance(sine, list) else [])],
                }

    return {"type": "constant", "cosine": 1.0, "sine": 0.0, "length": 400}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """CLI entry point for pulses.json → pulse_specs.json conversion."""
    parser = argparse.ArgumentParser(
        description="Convert legacy pulses.json to declarative pulse_specs.json",
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to legacy pulses.json",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output path for pulse_specs.json (default: same directory)",
    )
    parser.add_argument(
        "--definitions",
        default=None,
        help="Optional path to additional pulse_definitions file",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        return 1

    output_path = args.output
    if output_path is None:
        output_path = input_path.parent / "pulse_specs.json"

    result = convert(
        input_path,
        definitions_path=args.definitions,
    )

    result.save(output_path)
    print(result.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
