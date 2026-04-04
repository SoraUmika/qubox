# QUA Program Compilation Verification Report

> **Historical document (2026-03-22).** This verifies compilation of experiments
> at a point when `qubox.legacy` still existed. That package has since been
> eliminated. The experiment classes now live directly in `qubox.experiments`.

**Date:** 2026-03-22  
**qubox version:** 3.0.0  
**QUA SDK:** 1.2.6  
**Hardware:** OPX+ + Octave (oct1), Cluster_2  

---

## Executive Summary

All **26 compilable experiments** successfully compile into valid QUA programs against the **new repository configuration** (qubox v3). This verifies that the notebook migration (Sessions 1–7) preserved full QUA program generation capability.

| Metric | Count |
|--------|-------|
| Total experiments tested | 29 |
| Skipped (no single QUA program) | 3 |
| **Compile OK — new config** | **26/26 (100%)** |
| Compile OK — legacy config | 4/26 |
| Compile OK — both configs | 4/26 |
| **Failed to compile** | **0/26** |

---

## Per-Experiment Results

| # | Experiment | Notebook | New | Legacy | Status |
|---|-----------|----------|-----|--------|--------|
| 1 | ContinuousWave | NB07 | OK | OK | Waveform ports match |
| 2 | ResonatorSpectroscopy | NB09 | OK | OK | Waveform ports match |
| 3 | ResonatorPowerSpectroscopy | NB09 | OK | OK | Waveform ports match |
| 4 | QubitSpectroscopy | NB10 | OK | FAIL | New only |
| 5 | QubitSpectroscopyEF | NB10 | OK | FAIL | New only |
| 6 | PowerRabi | NB11 | OK | FAIL | New only |
| 7 | TemporalRabi | NB11 | OK | FAIL | New only |
| 8 | T1Relaxation | NB12 | OK | FAIL | New only |
| 9 | T2Ramsey | NB12 | OK | FAIL | New only |
| 10 | T2Echo | NB12 | OK | FAIL | New only |
| 11 | AllXY | NB11 | OK | FAIL | New only |
| 12 | DRAGCalibration | NB11 | OK | FAIL | New only |
| 13 | RandomizedBenchmarking | NB17 | SKIP | SKIP | Multi-circuit; no single QUA program |
| 14 | IQBlob | NB08 | OK | FAIL | New only |
| 15 | ReadoutGEDiscrimination | NB08 | OK | FAIL | New only |
| 16 | ReadoutButterflyMeasurement | NB08 | OK | FAIL | New only |
| 17 | ReadoutWeightsOptimization | NB08 | OK | FAIL | New only |
| 18 | StorageSpectroscopy | NB13 | OK | FAIL | New only |
| 19 | NumSplittingSpectroscopy | NB13 | OK | FAIL | New only |
| 20 | FockResolvedSpectroscopy | NB22 | OK | FAIL | New only |
| 21 | FockResolvedT1 | NB22 | OK | FAIL | New only |
| 22 | FockResolvedRamsey | NB22 | OK | FAIL | New only |
| 23 | SPAFluxOptimization | NB19 | SKIP | SKIP | Device-side DC sweeps |
| 24 | SPAPumpFrequencyOptimization | NB19 | SKIP | SKIP | Nested sub-runs |
| 25 | QubitStateTomography | NB23 | OK | FAIL | New only |
| 26 | StorageWignerTomography | NB23 | OK | FAIL | New only |
| 27 | FockResolvedPowerRabi | NB22 | OK | FAIL | New only |
| 28 | ReadoutTrace | NB08 | OK | OK | Waveform ports match |
| 29 | StorageChiRamsey | NB13 | OK | FAIL | New only |

---

## Waveform Comparison (Both-Config Experiments)

Four experiments compile on **both** new and legacy configs with identical waveform port outputs:

1. **ContinuousWave** — waveform ports match
2. **ResonatorSpectroscopy** — waveform ports match
3. **ResonatorPowerSpectroscopy** — waveform ports match
4. **ReadoutTrace** — waveform ports match

These are all resonator-only experiments that don't use the `transmon` element, which explains why they work on both configs (legacy config uses element name `qubit` instead of `transmon`).

---

## Legacy Config Failures (22 Experiments) — Root Cause

All 22 "new only" experiments fail on the legacy config for a **single structural reason**: the new repository uses element name `transmon` while the legacy config uses `qubit`. The QUA compiler correctly rejects programs that reference an element not present in the config.

This is **expected and correct behavior** — it confirms that the new config's element naming convention (`transmon`) is consistently used by all experiment builders.

---

## Code Bugs Found and Fixed

### Bug 1: Operator Precedence in Wigner Builder
**File:** `qubox/legacy/programs/builders/cavity.py` (line ~574)  
**Impact:** StorageWignerTomography would crash when displacement norm ≠ 0  
```python
# BEFORE (wrong — Python evaluates as: c=ratio.real/norm; s=(B if norm else D))
c, s = ratio.real / norm, ratio.imag / norm   if norm else (0.0, 0.0)

# AFTER (correct)
(c, s) = (ratio.real / norm, ratio.imag / norm) if norm else (0.0, 0.0)
```

### Bug 2–3: measure() Return Value Unpacking
**File:** `qubox/legacy/programs/builders/cavity.py` (lines ~613, ~738)  
**Impact:** StorageWignerTomography and StorageChiRamsey crash with "cannot unpack non-iterable NoneType"  
```python
# BEFORE (wrong — measure() returns None without with_state=True)
I, Q = measureMacro.measure(targets=[I, Q])

# AFTER (correct)
measureMacro.measure(targets=[I, Q])
```

### Bug 4–5: QUA Minimum Wait Duration
**File:** `qubox/legacy/experiments/cavity/storage.py` (line ~359), `fock.py` (line ~75)  
**Impact:** NumSplittingSpectroscopy and FockResolvedSpectroscopy fail with "play or wait duration shorter than 4 cycles"  
```python
# BEFORE (wrong — QUA minimum is 4 clock cycles)
def state_prep():
    wait(1)

# AFTER (correct)
def state_prep():
    wait(4)
```

---

## Pulse Gap Analysis

The new config defines **13 pulses** while the legacy config defines **75 pulses**. To enable compilation, **45 placeholder pulses** were injected at runtime by copying definitions from the legacy config:

- 11 constant-envelope qubit pulses (`const_x180_pulse`, `const_y90_pulse`, etc.)
- 9 number-selective pulses (`sel_x180_pulse`, `sel_y90_pulse`, etc.)
- 9 EF-transition pulses (`ef_x180_pulse`, `ef_y90_pulse`, etc.)
- 9 EF pulses (alternate naming: `efx180_pulse`, etc.)
- 3 displacement pulses (`disp_n0_pulse`, `disp_n1_pulse`, `disp_n2_pulse`) — via `ensure_displacement_ops()`
- 4 additional pulses (`x360_pulse`, `y360_pulse`, `x90n_pulse`, `y90n_pulse`, `saturation`)

**Recommendation:** These 45 pulses should be formally registered in the new repository's pulse definitions before running experiments on hardware. The placeholder mechanism proves compilation viability but uses legacy waveform definitions.

---

## Calibration Prerequisites

Several experiments required calibration values that are not present in the default config:

| Parameter | Value Used | Experiments Affected |
|-----------|------------|---------------------|
| `ro_therm_clks` | 10000 | ResonatorSpectroscopy, ResonatorPowerSpectroscopy |
| `st_therm_clks` | 10000 | StorageSpectroscopy, NumSplitting, FockResolved*, StorageWigner, StorageChiRamsey |
| `storage_freq` | 5.35 GHz | StorageWignerTomography |
| `fock_fqs` | [6.15, 6.148, 6.146] GHz | FockResolvedT1, FockResolvedRamsey, FockResolvedPowerRabi |
| `measureMacro._ro_disc_params` | threshold=0.0 | AllXY, QubitStateTomography |

---

## Legacy Dependency Analysis

- **Notebooks 07–27:** ZERO direct legacy imports — all experiment access is via `qubox.notebook`
- **`qubox.notebook`:** Re-exports 29 experiment classes from `qubox.legacy`
- **Runtime path:** Still executes legacy code; the notebook surface provides clean namespace isolation
- **No native QUA builders:** qubox v3 does not yet have non-legacy program builders

---

## Architectural Observations

1. **Element naming gap:** Legacy uses `qubit`/`readout_gf`; new uses `transmon`/`resonator_gf`. This is the sole reason experiments can't compile on both configs.

2. **measureMacro singleton:** The `measureMacro` class-level state is shared between legacy and new code paths. Discrimination parameters must be set before experiments that use `with_state=True`.

3. **PulseOperationManager vs raw config:** Displacement pulses must be registered via `PulseOperationManager.create_control_pulse()`, not just added to the QM config dict. The `validate_displacement_ops()` check looks up the POM's internal `el_ops` store.

---

## Test Harness

The verification script is at `E:\qubox\notebooks\verify_compilation.py`. It:

1. Creates a qubox v3 session with hardware QM connection
2. Registers displacement pulses via `ensure_displacement_ops()`
3. Injects 45 placeholder pulses from legacy definitions
4. Sets calibration store values (thermalization, storage frequency, discrimination)
5. Builds and compiles all 26 experiments against both new and legacy configs
6. Compares waveform outputs for experiments that compile on both configs
7. Produces JSON report at `compilation_verification_report.json`

---

## Conclusion

The migration from the legacy monolithic notebook to 21 modular notebooks is **compilation-complete**. All 26 experiment classes produce valid QUA programs. Five genuine code bugs were found and fixed during this process. The 45-pulse gap between new and legacy configurations is documented and can be addressed incrementally as experiments are calibrated on the new system.
