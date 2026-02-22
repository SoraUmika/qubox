# Verification Strategy

**Version**: 1.0.0
**Date**: 2026-02-21
**Status**: Governing Document

---

## 1. Verification Philosophy

Verification is not optional. Every component that generates waveforms, manages calibration data, or produces QM config must have automated tests that run before any deployment to hardware.

The verification suite has three tiers:

| Tier | Purpose | Speed | When to Run |
|------|---------|-------|------------|
| **Unit** | Individual function correctness | < 1 min | Every code change |
| **Integration** | Component interaction correctness | < 5 min | Before hardware session |
| **Legacy Parity** | Behavioral equivalence with legacy | < 10 min | Before any release |

---

## 2. Test Categories

### 2.1 Waveform Generation Tests

**Location**: `qubox_v2/verification/waveform_regression.py`

Every waveform generator in `tools/waveforms.py` must have a test that verifies:

| Check | Description |
|-------|------------|
| **Determinism** | Same parameters → identical output across runs |
| **Length** | Output length matches `length` parameter exactly |
| **Amplitude bounds** | All samples within `[-MAX_AMPLITUDE, MAX_AMPLITUDE]` |
| **Subtraction** | If `subtracted=True`, first and last samples are 0.0 |
| **Known values** | Specific parameter sets produce known-good reference arrays |

Required generators to test:

```
drag_gaussian_pulse_waveforms
kaiser_pulse_waveforms
slepian_pulse_waveforms
drag_cosine_pulse_waveforms
flattop_gaussian_waveform
flattop_cosine_waveform
flattop_tanh_waveform
flattop_blackman_waveform
blackman_integral_waveform
CLEAR_waveform
```

### 2.2 Sign Convention Tests

**Location**: `qubox_v2/verification/waveform_regression.py`

DRAG waveforms have specific sign conventions that must never change:

| Test | Expected Behavior |
|------|------------------|
| `alpha > 0, anharmonicity > 0` | Q component has specific sign pattern matching legacy |
| `alpha < 0, anharmonicity > 0` | Q component reverses sign |
| `alpha = 0` | Q component is all zeros |
| DRAG denominator | Must be `2π × anharmonicity - 2π × detuning` (not `2π × (anharmonicity - detuning)` — these are the same mathematically but the test guards against refactoring errors) |

Rotation gate waveforms:

| Test | Expected Behavior |
|------|------------------|
| `x180` | I = ref_I, Q = ref_Q (unmodified template) |
| `y180` | `w_new = w0 × exp(-j × π/2)` — I and Q swap with sign |
| `x90` | Half amplitude of x180 |
| `xn90` | Negative half amplitude of x180 |

### 2.3 Normalization Tests

| Test | Expected Behavior |
|------|------------------|
| `_normalize_complex_array` | Unit L2 norm, then scaled by max abs |
| Constant waveform | `sample` field is a float, not a list |
| Arbitrary waveform | `samples` field is a list of floats |
| Zero-padding | Pulse lengths are multiples of 4 ns |

### 2.4 Readout Pipeline Tests

| Test | Expected Behavior |
|------|------------------|
| Weight optimization trace | `g_trace` and `e_trace` are complex arrays |
| `ge_diff_norm` | Normalized within ±1 |
| Integration weight segments | Each segment `(amplitude, length_in_cc)` with length divisible by 4 |
| Weight key naming | `opt_cos` = `"opt_" + cos_w_key` |
| Sliced demod `div_clks` | `(pulse_len // num_div) // 4` for any valid `num_div` |
| Valid pairs | Only `(d, pulse_len // d // 4)` where `pulse_len % d == 0` and `(pulse_len // d) % 4 == 0` |

### 2.5 Calibration Integrity Tests

| Test | Expected Behavior |
|------|------------------|
| CalibrationStore round-trip | `save()` then `load()` produces identical data |
| CalibrationPatch apply | Patch changes exactly the listed keys, nothing else |
| Stale patch rejection | Patch with wrong `old_value` raises error |
| Schema validation | Invalid types in calibration data raise validation errors |
| Snapshot creation | Snapshot file created before every commit |
| History append | History file grows by exactly one line per commit |

### 2.6 Schema Validation Tests

| Test | Expected Behavior |
|------|------------------|
| hardware.json schema | Validates against HardwareConfig model |
| calibration.json schema | Validates against CalibrationData model |
| pulse_specs.json schema | Validates against PulseSpecFile model |
| Unknown version rejection | File with `schema_version: 999` raises `UnsupportedSchemaError` |
| Missing version handling | File without version field gets default version 1 |

### 2.7 Session State Tests

| Test | Expected Behavior |
|------|------------------|
| Build hash stability | Same inputs → same hash |
| Build hash sensitivity | Any input change → different hash |
| Immutability | Attempting to mutate SessionState raises error |
| Summary completeness | `summary()` includes all schema versions |

---

## 3. Legacy Parity Harness

### 3.1 Purpose

The legacy parity harness compares waveform generation between `qubox_v2` and `qubox_legacy` for identical parameters. This is the primary guard against behavioral drift.

### 3.2 Comparison Metrics

For each pulse type and parameter set:

| Metric | Formula | Pass Threshold |
|--------|---------|---------------|
| **L2 norm difference** | `‖v2 - legacy‖₂` | < 1e-12 |
| **Normalized dot product** | `Re(v2 · legacy*) / (‖v2‖ × ‖legacy‖)` | > 1 - 1e-10 |
| **Peak amplitude difference** | `|max(|v2|) - max(|legacy|)|` | < 1e-12 |
| **Area difference** | `|∑v2 - ∑legacy|` | < 1e-10 |
| **Phase consistency** | `max(|angle(v2) - angle(legacy)|)` where both > threshold | < 1e-10 rad |

### 3.3 Test Cases

#### DRAG Gaussian Parity

```python
# Reference parameters
params = {
    "amplitude": 0.11164994955929838,
    "length": 16,
    "sigma": 16/6,
    "alpha": 0.0,       # and also alpha=1.0, alpha=-0.5
    "anharmonicity": 255750000.0,
    "detuning": 0.0,
    "subtracted": True,
}

v2_I, v2_Q = tools.waveforms.drag_gaussian_pulse_waveforms(**params)
legacy_I, legacy_Q = legacy.pulse_manager.drag_gaussian_pulse_waveforms(**params)

assert_parity(v2_I, legacy_I, "DRAG Gaussian I")
assert_parity(v2_Q, legacy_Q, "DRAG Gaussian Q")
```

#### Rotation Gate Parity

```python
# Generate reference waveform
ref_I, ref_Q = drag_gaussian_pulse_waveforms(amp, 16, 16/6, 0.0, anh)

# V2 rotation generation
v2_created = register_rotations_from_ref_iq(pom, ref_I, ref_Q, rotations="all")

# Legacy rotation generation
legacy_created = legacy.gates_legacy.QubitRotation.generate_all(ref_I, ref_Q)

for gate_name in ["x180", "x90", "xn90", "y180", "y90", "yn90"]:
    assert_parity(v2_created[gate_name][0], legacy_created[gate_name][0], f"{gate_name} I")
    assert_parity(v2_created[gate_name][1], legacy_created[gate_name][1], f"{gate_name} Q")
```

#### Integration Weight Parity

```python
# For sliced demod with known trace
ge_diff = e_trace - g_trace
v2_norm = ReadoutWeightsOptimization._normalize_complex_array(ge_diff)
legacy_norm = legacy._normalize_complex_array(ge_diff)

assert_parity(v2_norm, legacy_norm, "ge_diff normalization")
```

### 3.4 Output Format

The parity harness produces:

**Markdown report** (`verification/reports/legacy_parity_<timestamp>.md`):
```markdown
# Legacy Parity Report - 2026-02-21T23:15:00

## Summary
- Tests run: 47
- Passed: 47
- Failed: 0
- Max L2 difference: 2.3e-16

## Details
| Test | L2 Diff | Dot Product | Peak Diff | Status |
|------|---------|-------------|-----------|--------|
| DRAG Gaussian (alpha=0) | 0.0 | 1.0 | 0.0 | PASS |
| DRAG Gaussian (alpha=1.0) | 1.2e-16 | 1.0-1e-15 | 0.0 | PASS |
| ... | ... | ... | ... | ... |
```

**JSON metrics** (`verification/reports/legacy_parity_<timestamp>.json`):
```json
{
  "timestamp": "2026-02-21T23:15:00",
  "total": 47,
  "passed": 47,
  "failed": 0,
  "tests": [...]
}
```

---

## 4. Regression Testing

### 4.1 Golden Reference Files

For each supported pulse shape and a set of canonical parameters, store the expected output as golden reference arrays:

```
verification/golden/
├── drag_gaussian_alpha0.json       # Known-good I/Q for alpha=0
├── drag_gaussian_alpha1.json       # Known-good I/Q for alpha=1.0
├── kaiser_beta4.json
├── rotation_x180.json
├── rotation_y90.json
└── ...
```

Tests compare generated output against golden references with tolerance < 1e-12.

### 4.2 Golden Reference Generation

Golden references are generated once from legacy code:

```python
python -m qubox_v2.verification.generate_golden --legacy-path qubox_legacy/
```

This script runs legacy generators and saves outputs. Golden files are committed to version control and never regenerated unless the legacy code is updated.

### 4.3 CI Integration

The verification suite must be runnable as:

```bash
python -m pytest qubox_v2/verification/ -v
```

All tests must pass before merging any PR that touches:
- `tools/waveforms.py`
- `tools/generators.py`
- `pulses/factory.py`
- `pulses/manager.py`
- `calibration/store.py`
- `experiments/calibration/readout.py`

---

## 5. Runtime Verification

### 5.1 Preflight Checks

`core/preflight.py` runs before experiments:

| Check | Action on Failure |
|-------|------------------|
| QM connection alive | ERROR — halt |
| Required elements exist | ERROR — halt |
| Baseline ops (const, zero) mapped | ERROR — halt |
| Readout weights present | WARN — log |
| Calibration file readable | WARN — log |
| Experiment dir writable | ERROR — halt |
| measureConfig exists | WARN — log |

### 5.2 Post-Commit Verification

After every calibration commit:

1. Re-read `calibration.json` and verify the written values match the patch.
2. Verify `calibration_history.jsonl` has a new entry.
3. If the patch affected integration weights, verify the weights are reflected in the POM.

---

## 6. What Is Not Tested (And Why)

| Item | Reason |
|------|--------|
| QUA program compilation | Requires QM SDK and hardware connection |
| Actual hardware execution | Cannot be automated without physical setup |
| matplotlib rendering | Visual verification is manual |
| Network timeouts | Environment-specific |
| Octave calibration quality | Depends on RF hardware state |

These items are verified through manual testing during hardware sessions and documented in run artifacts.
