# qubox_v2 Full Codebase Audit Report

**Date:** 2026-02-25
**Scope:** Legacy parity, bug/risk assessment, doc-vs-code conformance
**Constraint:** Read-only -- no code modifications

---

## 1. Executive Summary

**Parity status:** qubox_v2 covers **~85%** of legacy experiment functionality. 50 of ~62 distinct legacy experiment workflows have direct v2 class counterparts. The remaining ~12 are niche parametric sweeps, optimization frameworks (Bayes), or specialized cavity experiments (Kerr Ramsey, SQR gate, CLEAR waveform). The core calibration loop (spectroscopy -> Rabi -> T1/T2 -> DRAG -> readout -> AllXY/RB) is fully ported with structural improvements.

**Architecture quality:** The v2 refactor is well-structured -- 9-layer architecture, typed Pydantic models, CalibrationOrchestrator patch lifecycle, context-mode scoping. The main risks are not in the architecture itself but in subtle interaction issues between the layers.

### Top 5 Risks

| # | Risk | Severity | Location |
|---|------|----------|----------|
| 1 | **Duplicate patch operations**: PiAmpRule + WeightRegistrationRule both emit SetCalibration for the same calibration path, causing double-writes | Medium | `patch_rules.py:28-48`, `patch_rules.py:232-246` |
| 2 | **Silent `except Exception: pass`** in SPAPumpFrequencyOptimization swallows all errors during 2D sweep, leaving NaN entries with no diagnostic trail | High | `experiments/spa/` SPAPumpFrequencyOptimization |
| 3 | **`update_calibration` parameter accepted but ignored** in 6+ experiment classes (all Fock-resolved, StorageSpectroscopyCoarse, NumSplittingSpectroscopy) -- violates ExperimentBase contract | Medium | `cavity/fock.py`, `cavity/storage.py` |
| 4 | **Non-transactional session close**: crash between calibration save and pulse save can leave config in inconsistent state | Medium | `experiments/session.py` (documented as open risk in API_REFERENCE.md S15.6) |
| 5 | **Wigner negativity miscalculation**: uses `np.sum(np.abs(W[W < 0]))` instead of `np.sum(W[W < 0])`, always returning positive values for a quantity that should be negative by definition | Low | `tomography/wigner_tomo.py` |

---

## 2. Experiment Parity Matrix

### Legend
- **Match** = v2 class exists with equivalent physical sequence
- **Partial** = v2 class exists but with behavioral differences
- **Missing** = no v2 class equivalent
- **Cal** = calibration patching supported (via orchestrator or direct)

| # | Legacy Experiment | v2 Class | Match | Cal | Notes |
|----|---|---|---|---|---|
| 1 | `resonator_spectroscopy` | `ResonatorSpectroscopy` | Full | Yes | Lorentzian fit + `f0`, `kappa` |
| 2 | `resonator_power_spectroscopy` | `ResonatorPowerSpectroscopy` | Full | No | 2D freq x gain sweep |
| 3 | `resonator_spectroscopy_x180` | `ResonatorSpectroscopyX180` | Full | Yes | chi extraction |
| 4 | `readout_trace` / Time of Flight | `ReadoutTrace` | Full | No | Raw ADC traces |
| 5 | `qubit_spectroscopy` | `QubitSpectroscopy` | Full | Yes | FrequencyRule patches `qubit_freq` |
| 6 | `qubit_spectroscopy_ef` | `QubitSpectroscopyEF` | Full | No | e-f transition |
| 7 | `power_rabi` | `PowerRabi` | Full | Yes | PiAmpRule: `amp *= g_pi` |
| 8 | `temporal_rabi` | `TemporalRabi` | Full | Yes | `pi_length` via guarded commit |
| 9 | `T1_relaxation` | `T1Relaxation` | Full | Yes | T1Rule + `qb_therm_clks` |
| 10 | `T2_ramsey` | `T2Ramsey` | Full | Yes | T2RamseyRule + freq correction |
| 11 | `T2_echo` | `T2Echo` | Full | Yes | T2EchoRule |
| 12 | `iq_blobs` | `IQBlob` | Full | No | g/e IQ scatter |
| 13 | `readout_ge_raw_trace` | `ReadoutGERawTrace` | Full | No | Time-resolved g/e readout |
| 14 | `readout_ge_integrated_trace` | `ReadoutGEIntegratedTrace` | Full | No | |
| 15 | `readout_ge_discrimination` | `ReadoutGEDiscrimination` | Full | Yes | DiscriminationRule: angle, threshold, confusion |
| 16 | `readout_butterfly_measurement` | `ReadoutButterflyMeasurement` | Full | Yes | ReadoutQualityRule: F, Q, V |
| 17 | `readout_weight_optimization` | `ReadoutWeightsOptimization` | Full | Yes | WeightRegistrationRule |
| 18 | `calibrate_readout_full` | `CalibrateReadoutFull` | Full | Yes | Pipeline: weights -> GE -> butterfly |
| 19 | `all_XY` | `AllXY` | Full | No | 21-point gate error diagnostic |
| 20 | `drag_calibration_YALE` | `DRAGCalibration` | Full | Yes | DragAlphaRule: patches `ref_r180` only |
| 21 | `randomized_benchmarking` | `RandomizedBenchmarking` | Full | No | 24-Clifford RB |
| 22 | Pulse train calibration (r180) | `PulseTrainCalibration` | Full | Yes | PulseTrainRule: DE+LS global fit |
| 23 | Pulse train calibration (r90) | `PulseTrainCalibration` | Full | Yes | Same class, different theta |
| 24 | `sequential_qb_rotations` | `SequentialQubitRotations` | Full | No | |
| 25 | `storage_spectroscopy` | `StorageSpectroscopy` | Full | Yes | Proposed patch via metadata |
| 26 | `storage_spectroscopy_coarse` | `StorageSpectroscopyCoarse` | Partial | No | `update_calibration` ignored |
| 27 | `storage_ramsey` | `StorageRamsey` | Full | No | |
| 28 | `storage_chi_ramsey` | `StorageChiRamsey` | Full | Yes | `guarded_calibration_commit` |
| 29 | `num_splitting_spectroscopy` | `NumSplittingSpectroscopy` | Full | No | |
| 30 | `fock_resolved_spectroscopy` | `FockResolvedSpectroscopy` | Full | No | `update_calibration` ignored |
| 31 | `fock_resolved_T1` | `FockResolvedT1` | Full | No | `update_calibration` ignored |
| 32 | `fock_resolved_ramsey` | `FockResolvedRamsey` | Full | No | `update_calibration` ignored |
| 33 | `fock_resolved_power_rabi` | `FockResolvedPowerRabi` | Full | No | `update_calibration` ignored |
| 34 | `qubit_state_tomography` | `QubitStateTomography` | Full | No | 3-axis Bloch vector |
| 35 | Fock-resolved state tomo | `FockResolvedStateTomography` | Full | No | Per-Fock Bloch vectors |
| 36 | `wigner_tomography` | `StorageWignerTomography` | Full | No | Negativity calculation has bug |
| 37 | SNAP optimization | `SNAPOptimization` | Full | No | Near-duplicate of FockResolvedStateTomography |
| 38 | `spa_flux_optimization` | `SPAFluxOptimization` | Full | No | |
| 39 | SPA flux v2 | `SPAFluxOptimization2` | Full | No | 5 unused params |
| 40 | `spa_pump_freq_optimization` | `SPAPumpFrequencyOptimization` | Full | No | Silent exception swallowing |
| 41 | `readout_amp_len_opt` | `ReadoutAmpLenOpt` | Full | No | |
| 42 | `readout_frequency_optimization` | `ReadoutFrequencyOptimization` | Full | No | |
| 43 | `residual_photon_ramsey` | `ResidualPhotonRamsey` | Full | No | |
| 44 | Time Rabi Chevron | `TimeRabiChevron` | Full | No | |
| 45 | Power Rabi Chevron | `PowerRabiChevron` | Full | No | |
| 46 | Ramsey Chevron | `RamseyChevron` | Full | No | |
| 47 | Qubit reset benchmark | `QubitResetBenchmark` | Full | No | |
| 48 | Active qubit reset | `ActiveQubitResetBenchmark` | Full | No | `show_analysis` unused |
| 49 | Readout leakage | `ReadoutLeakageBenchmarking` | Full | No | |
| 50 | `StoragePhaseEvolution` | `StoragePhaseEvolution` | Full | No | SNAP phase tracking |

### Missing from v2 (no standalone class)

| # | Legacy Experiment | Category | Impact |
|---|---|---|---|
| M1 | Interleaved RB (unselective pulse) | Benchmarking | Medium -- standard fidelity metric |
| M2 | Interleaved RB (selective pulse) | Benchmarking | Medium -- characterizes selective gates |
| M3 | Kerr Ramsey | Cavity | Low -- specialized nonlinear cavity measurement |
| M4 | CLEAR waveform optimization | Readout | Low -- niche readout technique |
| M5 | Readout Bayes optimization | Readout | Low -- optimization framework, not a QUA experiment |
| M6 | Bayes pulse optimization (TOMO) | Pulse cal | Low -- optimization framework |
| M7 | Displacement calibration | Cavity | Medium -- needed for Fock-state preparation fidelity |
| M8 | SQR gate test | Cavity | Low -- specialized gate diagnostic |
| M9 | T1 vs pump power sweep | Parametric | Low -- composed from T1 + parameter loop |
| M10 | T2 vs pump detuning sweep | Parametric | Low -- composed from T2 + parameter loop |
| M11 | T1 from detunings sweep | Parametric | Low -- composed from T1 + parameter loop |
| M12 | Convention calibration | Diagnostic | Low -- one-off sign convention check |

---

## 3. Detailed Mismatch Findings

### 3.1 PowerRabi: Duplicate Patch Operations (Medium)

**Location:** `patch_rules.py:28-48` (PiAmpRule) + `patch_rules.py:232-246` (WeightRegistrationRule)

When `PowerRabi.analyze(update_calibration=True)` is called through the orchestrator:
1. `PowerRabi.analyze()` computes `patched_amp = current_amp * g_pi` and stores it in `metadata["proposed_patch_ops"]`
2. The orchestrator runs `PiAmpRule`, which independently computes `ref_amp_new = ref_amp_old * g_pi`
3. The orchestrator also runs `WeightRegistrationRule`, which picks up the `proposed_patch_ops` from metadata

Result: Two `SetCalibration` ops and two `TriggerPulseRecompile` ops for the same path. Observable in the notebook output (cell 32):
```
SetCalibration pulse_calibrations.ref_r180.amplitude = 0.096143  (from PiAmpRule)
SetPulseParam  ref_r180.amplitude = 0.096143
TriggerPulseRecompile
SetCalibration pulse_calibrations.ref_r180.amplitude = 0.096143  (from WeightRegistrationRule)
TriggerPulseRecompile
```

Currently harmless (values are identical), but fragile if the two codepaths ever read different state.

### 3.2 Fock-Resolved Experiments: Dead `update_calibration` Parameter (Medium)

**Location:** `cavity/fock.py` (all 4 classes), `cavity/storage.py` (StorageSpectroscopyCoarse, NumSplittingSpectroscopy)

These 6 experiment classes accept `update_calibration` as a keyword argument but never use it. The parameter silently does nothing. This violates the ExperimentBase contract documented in API_REFERENCE.md Section 3.

### 3.3 Inconsistent Calibration Update Patterns in Storage Experiments (Medium)

**Location:** `cavity/storage.py`

Three different patterns coexist:
1. `StorageSpectroscopy`: puts ops in `metadata["proposed_patch_ops"]` (requires orchestrator to apply)
2. `StorageChiRamsey`: uses `self.guarded_calibration_commit()` (direct write)
3. `StorageSpectroscopyCoarse` / `NumSplittingSpectroscopy`: ignores `update_calibration` entirely

### 3.4 FockResolvedSpectroscopy: Incomplete Fock Frequency Extraction (Low)

**Location:** `cavity/fock.py:~99`

Creates a `fock_freqs` list but only assigns `float(mag.min())` as placeholder instead of actual spectral peak locations.

### 3.5 SNAPOptimization / FockResolvedStateTomography Code Duplication (Low)

**Location:** `tomography/wigner_tomo.py:~144-185` vs `tomography/fock_tomo.py`

`SNAPOptimization.analyze()` and `SNAPOptimization.plot()` are near-identical copies of `FockResolvedStateTomography`.

### 3.6 SPAFluxOptimization2: 5 Dead Parameters (Low)

**Location:** `experiments/spa/` SPAFluxOptimization2

Parameters `peak_score_thresh`, `lock_min_delta`, `lock_loss_frac`, `approach_direction`, `approach_reset` are accepted but never referenced.

---

## 4. Suspected Bugs

### BUG-1: Wigner Negativity Always Positive (Low)

**Location:** `tomography/wigner_tomo.py:~67`
**Code:** `negativity = np.sum(np.abs(W[W < 0]))`
**Expected:** `negativity = np.sum(W[W < 0])` or `negativity = -np.sum(W[W < 0])`
**Impact:** The `np.abs()` makes negativity always positive, losing sign convention.

### BUG-2: Silent Exception Swallowing in SPA Pump Optimization (High)

**Location:** `experiments/spa/` SPAPumpFrequencyOptimization, line ~342
**Code:** `try: ... except Exception: pass`
**Impact:** Any exception during the 2D pump sweep is silently caught. NaN entries appear with no log message.

### BUG-3: T1Rule Heuristic Unit Guess Can Misfire (Medium)

**Location:** `patch_rules.py:67-68`
**Code:**
```python
t1_raw = float(params["T1"])
t1_s = t1_raw * 1e-9 if t1_raw > 1.0 else t1_raw
```
**Impact:** If T1 is reported as `2.0` (meaning 2.0 seconds), it incorrectly multiplies by 1e-9.
**Mitigation:** The explicit `T1_s` and `T1_ns` keys bypass this heuristic.

### BUG-4: QubitStateTomography Plot Reads Reduced Metrics (Low)

**Location:** `tomography/qubit_tomo.py`
**Issue:** `plot()` reads from `analysis.metrics` (scalar means) instead of `analysis.data` (full arrays).

### BUG-5: Mixer Auto-Calibration NaN in sqrt for qubit2 (Observed)

**Location:** `hardware/controller.py` `_calibrate_auto()`
**Observation:** Notebook output: "Auto calibration warning for 'qubit2': invalid value encountered in sqrt"
**Note:** May be a hardware/firmware issue; the error reporting path could be more informative.

---

## 5. High-Risk Codebase Hotspots

### 5.1 Non-Transactional Session Close

**Location:** `experiments/session.py`
**Risk:** Session persistence writes calibration.json, pulses.json, and measureConfig.json as separate operations. A crash between writes leaves config inconsistent.

### 5.2 CalibrationStore Context Validation Bypass

**Location:** `calibration/store.py`
**Risk:** Legacy v3 calibration files without context block load with a warning instead of `ContextMismatchError`. The first `save()` stamps the context.

### 5.3 PulseOperationManager Dual-Store Complexity

**Location:** `pulses/manager.py`
**Risk:** Permanent and volatile stores with merge logic during `burn_to_config()`. Out-of-order burns could desync QM config from calibration store.

### 5.4 measureMacro Singleton State

**Location:** `programs/macros/measure.py`
**Risk:** Process-wide singleton mutated by multiple experiment classes during `run()`. Mid-run failures can leave the macro in a partial state.

### 5.5 WeightRegistrationRule as Universal Passthrough

**Location:** `patch_rules.py:220-246`
**Risk:** Promotes any `proposed_patch_ops` from metadata into executable ops. Included in 11 of 12 patch rule lists. Fragile pattern.

---

## 6. Doc vs Code Discrepancies

### 6.1 Undocumented Experiment Classes

| Class | Status |
|---|---|
| `SPAFluxOptimization2` | Exists in code, not in API_REFERENCE.md |
| `StorageSpectroscopyCoarse` | Exists in code, not in API_REFERENCE.md |
| `ReadoutGERawTrace` | Listed as `ReadoutTrace` in docs (name collision) |

### 6.2 T1 Time-Unit Audit vs Patch Rules

CHANGELOG v1.5.0 states all coherence times stored in seconds. T1Rule has a heuristic guess (BUG-3) that can misfire.

### 6.3 Missing resonator_freq FrequencyRule

`default_patch_rules()` maps `resonator_freq` to `[WeightRegistrationRule]` only -- no typed `FrequencyRule`. Resonator frequency patching relies entirely on metadata passthrough.

### 6.4 Context-Mode strict_context Default

API docs describe `strict_context=True` for production. The notebook uses the default (non-strict), which is why legacy v3 calibration loads with a warning.

### 6.5 Appendix B Known Inconsistencies (Confirmed)

1. `blob_k_g` default of 3.0 is consistent in notebook usage.
2. `pulses.json` vs `pulse_specs.json` coexistence confirmed -- no collision mechanism.
3. `cqed_params.json` unversioned and excluded from build hash.

---

## 7. Recommended Next Steps

### Priority 1: Bug Fixes
1. Fix silent exception in SPAPumpFrequencyOptimization
2. Fix Wigner negativity calculation
3. Resolve duplicate patch operations in PiAmpRule/WeightRegistrationRule

### Priority 2: Contract Enforcement
4. Make `update_calibration` functional or remove it from 6 experiments that ignore it
5. Unify storage experiment calibration patterns

### Priority 3: Robustness
6. Add `resonator_freq` FrequencyRule to `default_patch_rules`
7. Remove dead parameters from SPAFluxOptimization2
8. Stamp context block proactively on v3 load

### Priority 4: Missing Experiments
9. Port Interleaved RB
10. Port Displacement Calibration

### Priority 5: Verification
11. Add integration test for patch roundtrip
12. Reconcile tolerance inconsistency between legacy_parity.py and waveform_regression.py

---

## Appendix A: File Coverage

| Category | Files Read |
|---|---|
| Documentation | `API_REFERENCE.md` (4070 lines), `CHANGELOG.md` (443 lines) |
| Legacy | `cQED_experiments.py` (5197 lines), `legacy/calibration.py` (310 lines) |
| Session | `experiments/session.py`, `core/session_state.py`, `core/experiment_context.py` |
| Calibration | `calibration/store.py`, `calibration/orchestrator.py`, `calibration/patch_rules.py`, `calibration/contracts.py`, `calibration/models.py` |
| Hardware | `hardware/controller.py`, `hardware/config_engine.py`, `hardware/program_runner.py`, `hardware/qua_program_manager.py` |
| Devices | `devices/context_resolver.py`, `devices/sample_registry.py` |
| Experiments | All files in `spectroscopy/`, `time_domain/`, `calibration/`, `cavity/`, `tomography/`, `spa/` |
| Programs | `programs/cQED_programs.py`, `programs/builders/readout.py`, `programs/macros/measure.py` |
| Verification | `verification/legacy_parity.py`, `verification/waveform_regression.py` |
| Compat | `compat/legacy.py` |
| Notebooks | `post_cavity_experiment_context.ipynb` (121 cells), `post_cavity_experiment_legacy.ipynb` (307 cells) |
