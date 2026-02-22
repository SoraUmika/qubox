# Pulse Specification Schema

**Version**: 1.0.0
**Date**: 2026-02-21
**Status**: Governing Document

---

## 1. Purpose

`pulse_specs.json` replaces `pulses.json` as the source of truth for pulse definitions. It stores **declarative recipes** — scalar parameters that deterministically produce waveform arrays at runtime. No waveform sample arrays are persisted.

---

## 2. File Structure

```json
{
  "schema_version": 1,

  "specs": {
    "<spec_name>": {
      "shape": "<shape_type>",
      "element": "<element_name>",
      "op": "<operation_name>",
      "params": { ... },
      "constraints": { ... },
      "metadata": { ... }
    }
  },

  "integration_weights": {
    "<weight_name>": {
      "type": "constant" | "segmented",
      "cosine": <value_or_segments>,
      "sine": <value_or_segments>,
      "length": <int_ns>
    }
  },

  "element_operations": {
    "<element>": {
      "<op>": "<spec_name>"
    }
  }
}
```

---

## 3. Supported Shapes

### 3.1 `constant`

```json
{
  "shape": "constant",
  "element": "resonator",
  "op": "const",
  "params": {
    "amplitude_I": 0.4,
    "amplitude_Q": 0.0,
    "length": 100
  }
}
```

**Compilation**: Produces constant I/Q waveforms of the specified amplitude and length.

### 3.2 `zero`

```json
{
  "shape": "zero",
  "element": "qubit",
  "op": "zero",
  "params": {
    "length": 16
  }
}
```

**Compilation**: Produces zero-amplitude I/Q waveforms. Every element must have a `zero` spec.

### 3.3 `drag_gaussian`

```json
{
  "shape": "drag_gaussian",
  "element": "qubit",
  "op": "ref_r180",
  "params": {
    "amplitude": 0.11165,
    "length": 16,
    "sigma": 2.6667,
    "drag_coeff": 0.0,
    "anharmonicity": 255750000.0,
    "detuning": 0.0,
    "subtracted": true
  }
}
```

**Compilation**: Calls `drag_gaussian_pulse_waveforms()` from `tools/waveforms.py`. Must produce bit-identical output to legacy for identical parameters.

### 3.4 `drag_cosine`

```json
{
  "shape": "drag_cosine",
  "element": "qubit",
  "op": "cos_x180",
  "params": {
    "amplitude": 0.1,
    "length": 20,
    "alpha": 0.5,
    "anharmonicity": 255750000.0,
    "detuning": 0.0
  }
}
```

**Compilation**: Calls `drag_cosine_pulse_waveforms()`.

### 3.5 `kaiser`

```json
{
  "shape": "kaiser",
  "element": "qubit",
  "op": "sel_x180",
  "params": {
    "amplitude": 0.1,
    "length": 200,
    "beta": 4.0,
    "detuning": 0.0,
    "alpha": 0.0,
    "anharmonicity": 0.0
  }
}
```

**Compilation**: Calls `kaiser_pulse_waveforms()`.

### 3.6 `slepian`

```json
{
  "shape": "slepian",
  "element": "qubit",
  "op": "slepian_x180",
  "params": {
    "amplitude": 0.1,
    "length": 200,
    "NW": 4.0,
    "detuning": 0.0,
    "alpha": 0.0,
    "anharmonicity": 0.0
  }
}
```

**Compilation**: Calls `slepian_pulse_waveforms()`.

### 3.7 `flattop_gaussian`

```json
{
  "shape": "flattop_gaussian",
  "element": "storage",
  "op": "readout_flat",
  "params": {
    "amplitude": 0.2,
    "flat_length": 200,
    "rise_fall_length": 20
  }
}
```

**Compilation**: Calls `flattop_gaussian_waveform()`.

### 3.8 `flattop_cosine`

Same parameters as `flattop_gaussian`. Calls `flattop_cosine_waveform()`.

### 3.9 `flattop_tanh`

Same parameters as `flattop_gaussian`. Calls `flattop_tanh_waveform()`.

### 3.10 `flattop_blackman`

Same parameters as `flattop_gaussian`. Calls `flattop_blackman_waveform()`.

### 3.11 `clear`

```json
{
  "shape": "clear",
  "element": "resonator",
  "op": "readout_clear",
  "params": {
    "t_duration": 400,
    "t_kick": 20,
    "A_steady": 0.2,
    "A_rise_hi": 0.4,
    "A_rise_lo": 0.1,
    "A_fall_lo": -0.1,
    "A_fall_hi": -0.4
  }
}
```

**Compilation**: Calls `CLEAR_waveform()`.

### 3.12 `rotation_derived`

```json
{
  "shape": "rotation_derived",
  "element": "qubit",
  "op": "x90",
  "params": {
    "reference_spec": "ref_r180",
    "theta": 1.5707963,
    "phi": 0.0,
    "d_lambda": 0.0,
    "d_alpha": 0.0,
    "d_omega": 0.0
  }
}
```

**Compilation**: Loads the reference spec's waveform, applies the rotation transform `w_new = amp_scale × w0 × exp(-j × phi_eff)` matching `register_rotations_from_ref_iq()`.

### 3.13 `arbitrary_blob`

```json
{
  "shape": "arbitrary_blob",
  "element": "storage",
  "op": "custom_drive",
  "params": {
    "I_samples_b64": "<base64-encoded float64 array>",
    "Q_samples_b64": "<base64-encoded float64 array>",
    "length": 100
  }
}
```

**Purpose**: Fallback for waveforms that have no declarative recipe. Used during migration from `pulses.json`. Emits a deprecation warning on every compilation.

**Compilation**: Decodes base64 → numpy float64 array. This is explicitly a transitional format.

---

## 4. Constraints

Optional constraints applied during compilation:

```json
{
  "constraints": {
    "max_amplitude": 0.45,
    "normalize_area": false,
    "pad_to_multiple_of": 4,
    "clip": true
  }
}
```

| Constraint | Default | Description |
|-----------|---------|-------------|
| `max_amplitude` | 0.45 | Hard clip at this voltage (OPX+ DAC limit) |
| `normalize_area` | false | Scale so ∫|envelope|dt = 1 (for selective pulses) |
| `pad_to_multiple_of` | 4 | Zero-pad to nearest multiple of N samples |
| `clip` | true | Clip samples exceeding max_amplitude (vs. raise) |

---

## 5. Integration Weights

### 5.1 Constant Weights

```json
{
  "readout_cosine_weights": {
    "type": "constant",
    "cosine": 1.0,
    "sine": 0.0,
    "length": 400
  }
}
```

### 5.2 Segmented Weights

```json
{
  "opt_readout_cosine_weights": {
    "type": "segmented",
    "cosine_segments": [[0.5, 100], [0.3, 100], [0.1, 100], [0.05, 100]],
    "sine_segments": [[-0.1, 100], [-0.2, 100], [-0.1, 100], [-0.05, 100]]
  }
}
```

Each segment is `[amplitude, length_in_ns]`. Length must be divisible by 4.

---

## 6. Measurement Pulses

Measurement pulses combine a waveform spec with integration weight references:

```json
{
  "shape": "constant",
  "element": "resonator",
  "op": "readout",
  "params": {
    "amplitude_I": 0.2,
    "amplitude_Q": 0.0,
    "length": 400
  },
  "metadata": {
    "pulse_type": "measurement",
    "digital_marker": "ON",
    "int_weights_mapping": {
      "cos": "readout_cosine_weights",
      "sin": "readout_sine_weights",
      "minus_sin": "readout_minus_weights"
    }
  }
}
```

---

## 7. Compilation Flow

```
pulse_specs.json ──→ PulseFactory.compile_all()
                          │
                          ├── For each spec:
                          │     ├── Resolve shape handler
                          │     ├── Call waveform generator with params
                          │     ├── Apply constraints (pad, clip)
                          │     └── Register in PulseOperationManager
                          │
                          ├── For each integration_weight:
                          │     └── Register in PulseOperationManager
                          │
                          └── For each element_operation:
                                └── Bind element → op → pulse
```

### 7.1 Determinism Guarantee

Given identical `pulse_specs.json` and `calibration.json`, `PulseFactory.compile_all()` must produce bit-identical waveform arrays across:
- Different Python sessions
- Different operating systems
- Different numpy versions (within the same major version)

This is guaranteed because all generators use deterministic math with no random state.

---

## 8. Migration from pulses.json

### 8.1 Converter Tool

```bash
python -m qubox_v2.migration.pulses_converter \
    --input config/pulses.json \
    --output config/pulse_specs.json \
    --definitions config/pulses.json  # extract any existing pulse_definitions
```

### 8.2 Conversion Strategy

| Source in pulses.json | Target in pulse_specs.json |
|----------------------|---------------------------|
| `pulse_definitions.drag_gaussian` | `shape: "drag_gaussian"` with params |
| `pulse_definitions.constant` | `shape: "constant"` with params |
| Constant waveform (`type: "constant"`) | `shape: "constant"` |
| Arbitrary waveform matching known shape | `shape: "<detected_shape>"` with fitted params |
| Arbitrary waveform, unknown shape | `shape: "arbitrary_blob"` with base64 samples |

### 8.3 Shape Detection

The converter attempts to match arbitrary waveform arrays against known generators:

1. For each known shape and a grid of parameter candidates, generate the expected waveform.
2. Compare L2 distance to the stored samples.
3. If L2 < 1e-10, declare a match and store the declarative params.
4. If no match, fall back to `arbitrary_blob`.

Shape detection is best-effort. The converter reports its confidence level.

---

## 9. Invariants

1. `pulse_specs.json` must never contain waveform sample arrays (except `arbitrary_blob` during migration).
2. Every `shape` value must map to a registered handler in `PulseFactory`.
3. Every `element` referenced in specs must exist in `hardware.json`.
4. Every element must have at least `const` and `zero` specs.
5. `rotation_derived` specs must reference an existing `reference_spec`.
6. Integration weight segment lengths must be divisible by 4.
7. All amplitudes must be within `[-MAX_AMPLITUDE, MAX_AMPLITUDE]`.
