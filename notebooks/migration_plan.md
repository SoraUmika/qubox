# Migration Plan: Legacy Notebook â†’ qubox Notebooks

> **Historical document.** This plan describes the migration from the legacy
> notebook to qubox v3 notebooks. Many experiments listed here have been
> migrated. References to qubox_v2_legacy and qubox.legacy describe
> packages that have since been eliminated. The canonical import surfaces are
> now qubox, qubox.notebook, and qubox_tools.


> **Source**: `post_cavity_experiment_legacy.ipynb` (94 experiments, ~11,800 lines, 343 cells)
> **Target**: `E:\qubox\notebooks/` â€” individual, modular notebooks using qubox v3 Session API
> **Reference**: `post_cavity_experiment_legacy_migration_survey.md` (full 94-experiment catalog)

---

## Table of Contents

1. [Migration Principles](#1-migration-principles)
2. [Architecture Overview](#2-architecture-overview)
3. [Already-Migrated Notebooks (00â€“06)](#3-already-migrated-notebooks-0006)
4. [New Notebook Plan (07â€“24)](#4-new-notebook-plan-0724)
5. [Experiment-to-Notebook Assignment Matrix](#5-experiment-to-notebook-assignment-matrix)
6. [API Coverage Summary](#6-api-coverage-summary)
7. [Calibration State Flow](#7-calibration-state-flow)
8. [Migration Priority & Phasing](#8-migration-priority--phasing)
9. [Per-Notebook Specifications](#9-per-notebook-specifications)
10. [Gap Analysis & Required Development](#10-gap-analysis--required-development)
11. [Validation Protocol](#11-validation-protocol)

---

## 1. Migration Principles

### 1.1 One Experiment Per Migration Task
Per `AGENTS.md Â§14`, each experiment is migrated independently. Legacy is the source of truth. Validation follows the **compile â†’ simulate â†’ compare** pipeline.

### 1.2 Import Discipline
- **Sole import surface**: `from qubox.notebook import ...`
- **Native API**: `session.exp.<category>.<method>(...)` for standard experiments
- **Legacy proxy**: `qubox.notebook.<ExperimentClass>` for classes not yet wrapped
- **Banned**: Never import `qubox_v2_legacy` or `qubox.legacy.*` directly

### 1.3 Notebook Conventions
- Each notebook is **self-contained**: starts with session bootstrap, ends with checkpoint save
- Calibration state flows between notebooks via `save_stage_checkpoint()` / `load_stage_checkpoint()`
- Notebooks are numbered sequentially; domain groupings keep related experiments together
- Each cell has a clear purpose: setup, run, analyze, visualize, or calibrate

### 1.4 Calibration Flow
- Use `CalibrationOrchestrator.run_analysis_patch_cycle()` for calibration experiments
- Always `preview_or_apply_patch_ops()` before committing parameter changes
- Store snapshots in `samples/<SAMPLE_ID>/cooldowns/<COOLDOWN_ID>/config/`

---

## 2. Architecture Overview

### 2.1 qubox Three-Tier Stack

| Layer | Package | Role |
|-------|---------|------|
| **User API** | `qubox` | Session, ExperimentLibrary, CalibrationOrchestrator, Sequence/Circuit IR |
| **Analysis** | `qubox_tools` | Fitting, plotting, optimization (separate install) |
| **Legacy Backend** | `qubox_v2_legacy` | Deprecated runtime; drives OPX+ hardware via `LegacyExperimentAdapter` |

### 2.2 Session Lifecycle
```python
from qubox.notebook import *

session = Session.open(
    sample_id="seq_1",
    cooldown_id="cd_001",
    config_dir="path/to/config",
)
session.preflight()  # validates wiring, calibration integrity

# Run experiments
result = session.exp.qubit.t1(target="qubit")
result.plot()
proposal = result.proposal()  # CalibrationProposal

# Apply calibration
session.calibration.preview_or_apply_patch_ops(proposal)
session.calibration.apply_patch()

# Checkpoint
save_stage_checkpoint(session, "06_coherence_experiments")
```

### 2.3 ExperimentLibrary Categories (20 Standard Experiments)

| Category | Methods |
|----------|---------|
| **Readout** | `trace`, `iq_blobs`, `butterfly` |
| **Resonator** | `spectroscopy`, `power_spectroscopy` |
| **Qubit** | `spectroscopy`, `temporal_rabi`, `power_rabi`, `time_rabi_chevron`, `power_rabi_chevron`, `t1`, `ramsey`, `echo` |
| **Calibration** | `all_xy`, `drag` |
| **Storage** | `spectroscopy`, `t1_decay`, `num_splitting` |
| **Tomography** | `qubit_state`, `wigner` |
| **Reset** | `active` |

### 2.4 Operation Library (session.ops)
`x90`, `x180`, `y90`, `y180`, `virtual_z`, `wait`, `measure`, `play`, `displacement`, `sqr`, `reset`

---

## 3. Already-Migrated Notebooks (00â€“06)

These notebooks are complete and define the calibration pipeline baseline. They cover legacy experiments 1â€“7, 11, 20, 22, 26.

| Notebook | Legacy Exp | Description | Checkpoint |
|----------|-----------|-------------|------------|
| `00_hardware_definition.ipynb` | Exp 1 | Bootstrap, SampleRegistry, Session.open, preflight | `00_hardware_definition` |
| `01_mixer_calibrations.ipynb` | Exp 2 | Auto/manual mixer cal via MixerCalibrationConfig, SA helper | `01_mixer_calibrations` |
| `02_time_of_flight.ipynb` | Exp 4 | ReadoutTrace â€” ADC envelope timing | `02_time_of_flight` |
| `03_resonator_spectroscopy.ipynb` | Exp 5 | ResonatorSpectroscopy + frequency patch | `03_resonator_spectroscopy` |
| `04_resonator_power_chevron.ipynb` | Exp 6 | ResonatorPowerSpectroscopy (2D; no calibration applied) | `04_resonator_power_chevron` |
| `05_qubit_spectroscopy_pulse_calibration.ipynb` | Exp 7, 11 | QubitSpectroscopy + PowerRabi + TemporalRabi, ref_r180 seed | `05_qubit_spectroscopy_pulse_calibration` |
| `06_coherence_experiments.ipynb` | Exp 20, 22, 26 | T1, T2 Ramsey, T2 Echo w/ optional freq correction | `06_coherence_experiments` |

**Remaining**: 84 experiments across Exp 3, 8â€“10, 12â€“19, 21, 23â€“25, 27â€“94.

---

## 4. New Notebook Plan (07â€“24)

New notebooks are organized by **experimental domain**, grouping related experiments that share calibration prerequisites and analysis patterns.

### Notebook Index

| # | Notebook Name | Legacy Exps | Experiment Count |
|---|--------------|------------|-----------------|
| 07 | `07_cw_diagnostics.ipynb` | 3 | 1 |
| 08 | `08_pulse_waveform_definition.ipynb` | 8, 9, 10, 59 | 4 |
| 09 | `09_qutrit_spectroscopy_calibration.ipynb` | 12, 15 | 2 |
| 10 | `10_sideband_transitions.ipynb` | 16, 17, 18, 19 | 4 |
| 11 | `11_coherence_2d_pump_sweeps.ipynb` | 21, 23, 24, 25 | 4 |
| 12 | `12_chevron_experiments.ipynb` | 27, 28, 29 | 3 |
| 13 | `13_dispersive_shift_measurement.ipynb` | 30 | 1 |
| 14 | `14_gate_calibration_benchmarking.ipynb` | 13, 31, 32, 33, 34, 35 | 6 |
| 15 | `15_qubit_state_tomography.ipynb` | 36, 37, 38 | 3 |
| 16 | `16_readout_calibration.ipynb` | 39, 40, 41, 42, 43, 44, 45, 46, 47, 49, 50, 51, 53, 54 | 14 |
| 17 | `17_readout_bayesian_optimization.ipynb` | 52 | 1 |
| 18 | `18_active_reset_benchmarking.ipynb` | 48, 55, 92 | 3 |
| 19 | `19_spa_optimization.ipynb` | 56, 57 | 2 |
| 20 | `20_readout_leakage_benchmarking.ipynb` | 58 | 1 |
| 21 | `21_storage_cavity_characterization.ipynb` | 60, 61, 62, 63, 64, 72, 73, 74 | 8 |
| 22 | `22_fock_resolved_experiments.ipynb` | 65, 66, 67, 68, 69, 70, 71 | 7 |
| 23 | `23_quantum_state_preparation.ipynb` | 75, 76, 77, 78, 79, 80, 81 | 7 |
| 24 | `24_free_evolution_tomography.ipynb` | 82, 83 | 2 |
| 25 | `25_context_aware_sqr_calibration.ipynb` | 84, 93, 94 | 3 |
| 26 | `26_sequential_simulation_benchmarking.ipynb` | 85, 86, 87, 88, 89, 90 | 6 |
| 27 | `27_cluster_state_evolution.ipynb` | 91 | 1 |
| | **TOTAL** | | **83** |

> Note: Exp 14 (IQ Blob 3-state) is a prerequisite shared between notebooks 09 and 16; it is placed in **16_readout_calibration** as the canonical location, with a cross-reference from 09.

---

## 5. Experiment-to-Notebook Assignment Matrix

| Legacy Exp | Experiment Title | Target Notebook | qubox API | Migration Type |
|-----------|-----------------|----------------|-----------|---------------|
| **Exp 1** | System Initialization | **00** (done) | `Session.open()` | âœ… Migrated |
| **Exp 2** | Mixer Calibration | **01** (done) | `MixerCalibrationConfig` | âœ… Migrated |
| **Exp 3** | CW Diagnostics | **07** | `continuous_wave()` (legacy proxy) | Legacy proxy |
| **Exp 4** | Time of Flight | **02** (done) | `session.exp.readout.trace()` | âœ… Migrated |
| **Exp 5** | Resonator Spectroscopy | **03** (done) | `session.exp.resonator.spectroscopy()` | âœ… Migrated |
| **Exp 6** | Resonator Amplitude Chevron | **04** (done) | `session.exp.resonator.power_spectroscopy()` | âœ… Migrated |
| **Exp 7** | Qubit Spectroscopy (gâ†’e) | **05** (done) | `session.exp.qubit.spectroscopy()` | âœ… Migrated |
| **Exp 8** | Pulse Waveform â€” Constant | **08** | `register_rotations_from_ref_iq()` | Workflow |
| **Exp 9** | Pulse Waveform â€” DRAG (gâ†’e) | **08** | `drag_gaussian_pulse_waveforms()` | Workflow |
| **Exp 10** | Pulse Waveform â€” DRAG (eâ†’f) | **08** | `drag_gaussian_pulse_waveforms()` | Workflow |
| **Exp 11** | Power Rabi (gâ†’e) | **05** (done) | `session.exp.qubit.power_rabi()` | âœ… Migrated |
| **Exp 12** | Power Rabi (eâ†’f) | **09** | `PowerRabi` (proxy, eâ†’f config) | Legacy proxy + custom |
| **Exp 13** | Single Qubit Sequential Rotations | **14** | Custom sequence via `session.ops` | Custom sequence |
| **Exp 14** | IQ Blob (g/e/f) | **16** | `IQBlob` (proxy) / `session.exp.readout.iq_blobs()` | Native + proxy |
| **Exp 15** | Qubit eâ†’f Spectroscopy | **09** | `QubitSpectroscopyEF` (proxy) | Legacy proxy |
| **Exp 16** | GF Readout Sideband Spectroscopy | **10** | `readout_sideband_reset_spectroscopy()` | API method |
| **Exp 17** | Readout-GF Sideband Power Rabi | **10** | Custom power sweep | Custom sequence |
| **Exp 18** | GF Storage Sideband Spectroscopy | **10** | `gf_storage_sideband_spectroscopy()` | API method |
| **Exp 19** | Storage-GF Sideband Power Rabi | **10** | Custom power sweep | Custom sequence |
| **Exp 20** | T1 Relaxation | **06** (done) | `session.exp.qubit.t1()` | âœ… Migrated |
| **Exp 21** | T1 vs. Second Pump (2D) | **11** | Loop `T1Relaxation` + SignalCore | Workflow (ext. instrument) |
| **Exp 22** | T2 Ramsey | **06** (done) | `session.exp.qubit.ramsey()` | âœ… Migrated |
| **Exp 23** | T2/Detuning vs. Pump â€” Wide | **11** | Loop `T2Ramsey` + SignalCore | Workflow (ext. instrument) |
| **Exp 24** | T2/Detuning vs. Pump â€” Symmetric | **11** | Loop `T2Ramsey` + SignalCore | Workflow (ext. instrument) |
| **Exp 25** | T1 from Detunings (companion) | **11** | Loop `T1Relaxation` + SignalCore | Workflow (ext. instrument) |
| **Exp 26** | T2 Echo | **06** (done) | `session.exp.qubit.echo()` | âœ… Migrated |
| **Exp 27** | Time Rabi Chevron | **12** | `session.exp.qubit.time_rabi_chevron()` | Native API |
| **Exp 28** | Power Rabi Chevron | **12** | `session.exp.qubit.power_rabi_chevron()` | Native API |
| **Exp 29** | Ramsey Chevron | **12** | `ramsey_chevron()` | API method |
| **Exp 30** | Resonator Spectroscopy w/ x180 | **13** | `ResonatorSpectroscopyX180` (proxy) | Legacy proxy |
| **Exp 31** | DRAG Calibration (Yale) | **14** | `session.exp.calibration.drag()` | Native API |
| **Exp 32** | All-XY | **14** | `session.exp.calibration.all_xy()` | Native API |
| **Exp 33** | Randomized Benchmarking | **14** | `RandomizedBenchmarking` (proxy) | Legacy proxy |
| **Exp 34** | Interleaved RB â€” Unselective | **14** | `RandomizedBenchmarking` (IRB config) | Legacy proxy + config |
| **Exp 35** | Interleaved RB â€” Selective | **14** | `RandomizedBenchmarking` (IRB config) | Legacy proxy + config |
| **Exp 36** | Qubit State Tomography | **15** | `session.exp.tomography.qubit_state()` | Native API |
| **Exp 37** | Convention Calibration (Pulse Suite) | **15** | `qubit_state_tomography()` loop | Workflow |
| **Exp 38** | Tomography Pulse Train | **15** | `qubit_state_tomography()` + N-loop | Workflow |
| **Exp 39** | CLEAR Readout Pulse Registration | **16** | `build_CLEAR_waveform_from_physics()` | Workflow |
| **Exp 40** | Square Waveform Readout | **16** | `readout_ge_integrated_trace()` | API method |
| **Exp 41** | CLEAR Waveform Readout | **16** | `readout_ge_integrated_trace()` | API method |
| **Exp 42** | Readout g/e Raw Trace | **16** | `readout_ge_raw_trace()` | API method |
| **Exp 43** | Readout g/e Discrimination | **16** | `ReadoutGEDiscrimination` (proxy) | Legacy proxy |
| **Exp 44** | Readout g/e Integrated Trace | **16** | `readout_ge_integrated_trace()` | API method |
| **Exp 45** | Readout Loss Îº Measurement | **16** | `readout_ge_raw_trace()` + ring-down fit | Workflow |
| **Exp 46** | Residual Photon Ramsey | **16** | `residual_photon_ramsey()` | API method |
| **Exp 47** | Butterfly Measurement | **16** | `session.exp.readout.butterfly()` | Native API |
| **Exp 48** | Active Qubit Reset Benchmarking | **18** | `qubit_reset_benchmark()` | API method |
| **Exp 49** | Readout Amplitude & Length Opt | **16** | `readout_amp_len_opt()` | API method |
| **Exp 50** | Readout Frequency Optimization | **16** | `readout_frequency_optimization()` | API method |
| **Exp 51** | CLEAR Readout Variants (Int. Trace + Butterfly) | **16** | Compose readout methods | Workflow |
| **Exp 52** | Readout Bayesian Optimization | **17** | ipywidgets + scikit-optimize loop | Workflow (external) |
| **Exp 53** | Readout Weight Optimization | **16** | `ReadoutWeightsOptimization` (proxy) | Legacy proxy |
| **Exp 54** | Readout Full Calibration | **16** | `CalibrateReadoutFull` (proxy) | Legacy proxy |
| **Exp 55** | Qubit Reset Benchmark | **18** | `qubit_reset_benchmark()` | API method |
| **Exp 56** | SPA DC Tune-Up | **19** | `SPAFluxOptimization` (proxy) | Legacy proxy |
| **Exp 57** | SPA Pump Power/Freq Opt. | **19** | `SPAPumpFrequencyOptimization` (proxy) | Legacy proxy |
| **Exp 58** | Readout Leakage Benchmarking | **20** | `qubit_readout_leakage_benchmarking()` | API method |
| **Exp 59** | Default Displacement + Selective Pi | **08** | `ensure_displacement_ops()` | Workflow |
| **Exp 60** | Cavity Spectroscopy | **21** | `session.exp.storage.spectroscopy()` | Native API |
| **Exp 61** | Storage Ramsey | **21** | `storage_ramsey()` | API method |
| **Exp 62** | Storage T1 Decay | **21** | `session.exp.storage.t1_decay()` | Native API |
| **Exp 63** | Storage Chi Ramsey | **21** | `storage_chi_ramsey()` | API method |
| **Exp 64** | Kerr Ramsey | **21** | `storage_chi_ramsey()` (variant) | API method (renamed) |
| **Exp 65** | Î±=1 Displacement Calibration | **22** | `fock_resolved_spectroscopy()` sweep | Workflow |
| **Exp 66** | Fock-Resolved Spectroscopy | **22** | `fock_resolved_spectroscopy()` | API method |
| **Exp 67** | Fock-Resolved Power Rabi | **22** | `fock_resolved_power_rabi()` | API method |
| **Exp 68** | Fock-Resolved T1 | **22** | `fock_resolved_T1_relaxation()` | API method |
| **Exp 69** | Fock-Resolved T2 Ramsey | **22** | `fock_resolved_qb_ramsey()` | API method |
| **Exp 70** | Fock-Resolved Affine Readout Cal | **22** | Workflow: collect + fit affine model | Workflow |
| **Exp 71** | Quick Fock-Resolved State Tomo | **22** | `fock_resolved_state_tomography()` | API method |
| **Exp 72** | Storage Raman 2-Tone Power Chevron | **21** | `storage_raman_two_tone_power_chevron()` | API method |
| **Exp 73** | Number-Splitting Spectroscopy | **21** | `fock_resolved_spectroscopy()` + fit | API method (workaround) |
| **Exp 74** | Displacement Calibration (Î±) | **21** | `fock_resolved_spectroscopy()` sweep | Workflow |
| **Exp 75** | SQR Gate Test | **23** | `session.ops.sqr()` + tomography | Custom sequence |
| **Exp 76** | Fock |1âŸ© Prep (D-SNAP-D) | **23** | `session.ops.displacement()` + `SNAPOptimization` | Custom sequence |
| **Exp 77** | Fock |2âŸ© Prep (D-SNAP-DÃ—3) | **23** | Multi-gate composition | Custom sequence |
| **Exp 78** | SNAP Rotation Opt (8-param) | **23** | `snap_optimization()` | API method |
| **Exp 79** | SNAP Rotation Opt â€” Fast 2-Stage | **23** | `snap_optimization()` (multi-fidelity) | API method |
| **Exp 80** | SNAP Phase Optimization | **23** | Placeholder (incomplete in legacy) | Deferred |
| **Exp 81** | Wigner Tomography | **23** | `session.exp.tomography.wigner()` | Native API |
| **Exp 82** | Free Evolution State Tomo | **24** | `free_evolution_state_tomography()` | API method |
| **Exp 83** | Fock-Resolved Free Evo Tomo | **24** | `free_evolution_fock_state_tomography()` | API method |
| **Exp 84** | Context-Aware SQR Calibration | **25** | Domain workflow (context_aware_sqr) | Workflow |
| **Exp 85** | Sequential Wigner Tomo | **26** | Loop `session.exp.tomography.wigner()` | Workflow |
| **Exp 86** | Sequential Sim â€” ZZ (v1) | **26** | `sequential_simulation()` | API method |
| **Exp 87** | Sequential Sim â€” X, Y, Z | **26** | `sequential_simulation()` | API method |
| **Exp 88** | Sequential Sim â€” ZZ (v2) | **26** | `sequential_simulation()` | API method |
| **Exp 89** | Sequential Sim â€” XX | **26** | `sequential_simulation()` | API method |
| **Exp 90** | Sequential Sim â€” YY | **26** | `sequential_simulation()` | API method |
| **Exp 91** | Cluster State Evolution | **27** | Simulation + hardware comparison | Workflow (holographic_sim) |
| **Exp 92** | Active Reset Debug | **18** | `session.ops.reset(mode="active")` | Custom sequence |
| **Exp 93** | CASE_A Ideal Reference | **25** | Simulation-only | Workflow |
| **Exp 94** | SQR Artifact Single-Gate Swap | **25** | Decomposition patching | Workflow |

---

## 6. API Coverage Summary

| Migration Type | Count | Description |
|---------------|-------|-------------|
| âœ… **Already migrated** (00â€“06) | 10 | Complete in existing notebooks |
| ðŸŸ¢ **Native API** (`session.exp.*`) | 14 | Direct ExperimentLibrary calls |
| ðŸ”µ **API method** (cQED_experiments) | 28 | Available via cQED experiment API |
| ðŸŸ¡ **Legacy proxy** (compat.notebook) | 13 | Lazy-loaded from qubox_v2_legacy |
| ðŸŸ  **Workflow** (notebook-level) | 23 | Composition of API calls + analysis loops |
| ðŸ”´ **Custom sequence** | 5 | Build from ops + custom QUA programs |
| âšª **Deferred** | 1 | Exp 80 â€” incomplete in legacy |
| **Total** | **94** | |

---

## 7. Calibration State Flow

### 7.1 Full Pipeline Dependency Graph

```
00_hardware_definition
 â†“
01_mixer_calibrations
 â†“
02_time_of_flight
 â†“
03_resonator_spectroscopy â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
 â†“                                               â”‚
04_resonator_power_chevron (advisory)            â”‚
 â†“                                               â”‚
05_qubit_spectroscopy_pulse_calibration          â”‚
 â†“                                               â”‚
06_coherence_experiments                         â”‚
 â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”                    â”‚
 â”‚                          â”‚                    â”‚
 â†“                          â†“                    â†“
07_cw_diagnostics      08_pulse_waveform    13_dispersive_shift
                        â†“
                   09_qutrit_spectroscopy
                    â†“
                   10_sideband_transitions
                    â†“                              
          â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
          â†“         â†“
    11_2d_pump   12_chevron
          â”‚
          â†“
    14_gate_benchmarking â”€â”€â”€â”€â”€â†’ 15_qubit_state_tomography
          â”‚
          â†“
    16_readout_calibration â”€â”€â†’ 17_bayesian_opt
          â”‚                 â””â”€â†’ 18_active_reset
          â”‚                 â””â”€â†’ 19_spa_optimization
          â”‚                 â””â”€â†’ 20_readout_leakage
          â†“
    21_storage_cavity â”€â”€â”€â”€â”€â”€â†’ 22_fock_resolved
                                â†“
                           23_quantum_state_prep
                                â†“
                           24_free_evolution_tomo
                                â†“
                           25_sqr_calibration
                                â†“
                           26_sequential_sim â”€â”€â†’ 27_cluster_state
```

### 7.2 Checkpoint Dependencies

| Notebook | Requires Checkpoint | Provides Checkpoint |
|----------|-------------------|-------------------|
| 07 | `06_coherence` | `07_cw_diagnostics` |
| 08 | `06_coherence` | `08_pulse_waveform` |
| 09 | `08_pulse_waveform` | `09_qutrit` |
| 10 | `09_qutrit` | `10_sideband` |
| 11 | `06_coherence` | `11_2d_pump` |
| 12 | `06_coherence` | `12_chevron` |
| 13 | `06_coherence` | `13_dispersive` |
| 14 | `06_coherence` | `14_gate_benchmarking` |
| 15 | `14_gate_benchmarking` | `15_tomography` |
| 16 | `06_coherence` | `16_readout` |
| 17 | `16_readout` | `17_bayesian_opt` |
| 18 | `16_readout` | `18_active_reset` |
| 19 | `16_readout` | `19_spa` |
| 20 | `16_readout` | `20_leakage` |
| 21 | `16_readout` | `21_storage` |
| 22 | `21_storage` | `22_fock_resolved` |
| 23 | `22_fock_resolved` | `23_state_prep` |
| 24 | `23_state_prep` | `24_free_evo_tomo` |
| 25 | `24_free_evo_tomo` | `25_sqr_calibration` |
| 26 | `25_sqr_calibration` | `26_sequential_sim` |
| 27 | `26_sequential_sim` | `27_cluster_state` |

---

## 8. Migration Priority & Phasing

### Phase 0 â€” Validation of Existing (Done)
Verify notebooks 00â€“06 against legacy experiments. Confirm checkpoint compatibility.

### Phase 1 â€” Core Calibration Pipeline (High Priority)
Target: Complete the fundamental experiment chain that all downstream notebooks depend on.

| Priority | Notebook | Rationale |
|----------|---------|-----------|
| P1.1 | **08** Pulse Waveform Definition | Required for selective pi pulses (Fock operations, sidebands) |
| P1.2 | **09** Qutrit Spectroscopy | Required for eâ†’f transitions, 3-level readout |
| P1.3 | **10** Sideband Transitions | Required for storage operations, cavity reset |
| P1.4 | **13** Dispersive Shift | Required for accurate readout modeling |
| P1.5 | **16** Readout Calibration | 14 experiments; gate-keeping for all subsequent work |

### Phase 2 â€” Characterization & Benchmarking (Medium-High Priority)
Target: Complete qubit and readout characterization.

| Priority | Notebook | Rationale |
|----------|---------|-----------|
| P2.1 | **14** Gate Calibration & Benchmarking | Validates single-qubit operations |
| P2.2 | **15** Qubit State Tomography | Required for convention validation |
| P2.3 | **12** Chevron Experiments | Diagnostic, useful for tuning |
| P2.4 | **18** Active Reset | Enables fast experiment repetition |
| P2.5 | **19** SPA Optimization | Enables high-fidelity readout |

### Phase 3 â€” Storage Cavity & Fock-Space (Medium Priority)
Target: Enable bosonic qubit experiments.

| Priority | Notebook | Rationale |
|----------|---------|-----------|
| P3.1 | **21** Storage Cavity Characterization | Foundation for cavity experiments |
| P3.2 | **22** Fock-Resolved Experiments | Required for selective operations |
| P3.3 | **23** Quantum State Preparation | SQR, SNAP, Wigner |
| P3.4 | **24** Free Evolution Tomography | Cavity dynamics diagnostics |

### Phase 4 â€” Advanced Workflows (Lower Priority)
Target: Research-specific notebooks.

| Priority | Notebook | Rationale |
|----------|---------|-----------|
| P4.1 | **25** Context-Aware SQR Calibration | Active research workflow |
| P4.2 | **26** Sequential Simulation Benchmarking | Validation framework |
| P4.3 | **27** Cluster State Evolution | Simulation comparison |
| P4.4 | **11** Coherence 2D Pump Sweeps | Requires external SignalCore instrument |
| P4.5 | **07** CW Diagnostics | Diagnostic-only |
| P4.6 | **17** Readout Bayesian Optimization | Optional advanced calibration |
| P4.7 | **20** Readout Leakage Benchmarking | Specialized diagnostic |

---

## 9. Per-Notebook Specifications

### 9.1 â€” Notebook 07: CW Diagnostics

**File**: `07_cw_diagnostics.ipynb`
**Legacy**: Exp 3
**Experiments**: Continuous wave output on all elements for spectrum analyzer verification

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
    continuous_wave,
)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("06_coherence_experiments")`
2. Configure CW target elements (qubit, readout, storage)
3. Run CW program â€” `continuous_wave(session, elements=[...])`
4. Manual SA verification (markdown instructions)
5. `save_stage_checkpoint(session, "07_cw_diagnostics")`

**Migration Notes**: `continuous_wave` is a legacy proxy utility. Keep as-is until a native wrapper emerges.

---

### 9.2 â€” Notebook 08: Pulse Waveform Definition

**File**: `08_pulse_waveform_definition.ipynb`
**Legacy**: Exp 8, 9, 10, 59
**Experiments**: Define constant, DRAG-Gaussian (gâ†’e, eâ†’f), and number-selective waveforms

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
    drag_gaussian_pulse_waveforms, kaiser_pulse_waveforms,
    register_rotations_from_ref_iq, ensure_displacement_ops,
    CalibrationOrchestrator, preview_or_apply_patch_ops,
)
```

**Cells**:
1. Session bootstrap + load checkpoint
2. Define constant (square) pulse parameters for Fock-selective rotations
3. Build DRAG-Gaussian waveforms for gâ†’e transition â€” `drag_gaussian_pulse_waveforms()`
4. Build DRAG-Gaussian waveforms for eâ†’f transition
5. Register all rotations â€” `register_rotations_from_ref_iq()`
6. Set up displacement operations â€” `ensure_displacement_ops()`
7. Validate waveform shapes (plot)
8. Apply to calibration store â€” `preview_or_apply_patch_ops()`
9. `save_stage_checkpoint(session, "08_pulse_waveform")`

**Migration Notes**: This consolidates 4 legacy experiments into a single setup notebook. All waveform generators are already migrated (not proxied).

---

### 9.3 â€” Notebook 09: Qutrit Spectroscopy & Calibration

**File**: `09_qutrit_spectroscopy_calibration.ipynb`
**Legacy**: Exp 12, 15
**Experiments**: eâ†’f spectroscopy & power Rabi for qutrit operations

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
    QubitSpectroscopyEF, PowerRabi,
    CalibrationOrchestrator, preview_or_apply_patch_ops,
)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("08_pulse_waveform")`
2. Run eâ†’f spectroscopy â€” `QubitSpectroscopyEF(session, ...)`
3. Analyze & fit eâ†’f frequency (anharmonicity)
4. Run Power Rabi (eâ†’f) â€” `PowerRabi(session, transition="ef", ...)`
5. Fit eâ†’f Ï€-pulse amplitude
6. Apply calibration patches
7. `save_stage_checkpoint(session, "09_qutrit")`

**Migration Notes**: Both classes are legacy proxies. Monitor for native `session.exp.qubit.spectroscopy_ef()` and `session.exp.qubit.power_rabi(transition="ef")` wrapping.

---

### 9.4 â€” Notebook 10: Sideband Transitions

**File**: `10_sideband_transitions.ipynb`
**Legacy**: Exp 16, 17, 18, 19
**Experiments**: GF sideband spectroscopy + power Rabi for readout and storage

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
    CalibrationOrchestrator, preview_or_apply_patch_ops,
)
# API methods via cQED_experiments
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("09_qutrit")`
2. GF Readout sideband spectroscopy â€” find |f,0_râŸ© â†” |g,1_râŸ©
3. Readout-GF sideband power Rabi â€” calibrate sideband Ï€-pulse
4. GF Storage sideband spectroscopy â€” find |g,1âŸ© â†” |f,0âŸ©
5. Storage-GF sideband power Rabi â€” calibrate amplitude
6. Apply sideband calibration patches
7. `save_stage_checkpoint(session, "10_sideband")`

**Migration Notes**: Sideband experiments use API methods `readout_sideband_reset_spectroscopy()` and `gf_storage_sideband_spectroscopy()`. Power Rabi variants need custom parameter sweeps.

---

### 9.5 â€” Notebook 11: Coherence 2D Pump Sweeps

**File**: `11_coherence_2d_pump_sweeps.ipynb`
**Legacy**: Exp 21, 23, 24, 25
**Experiments**: T1 and T2 vs. second pump tone (power Ã— detuning 2D sweeps)

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
    T1Relaxation, T2Ramsey,
)
# External instrument control (SignalCore)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("06_coherence_experiments")`
2. Configure SignalCore synthesizer (pump frequency, power grid)
3. T1 vs. pump (2D sweep) â€” nested loop: set pump â†’ run `T1Relaxation` â†’ collect
4. Heatmap visualization: T1(power, detuning)
5. T2 Ramsey vs. pump â€” wide detuning (Exp 23)
6. T2 Ramsey vs. pump â€” symmetric detuning (Exp 24)
7. T1 companion measurements at same grid points (Exp 25)
8. AC Stark shift analysis
9. `save_stage_checkpoint(session, "11_2d_pump")`

**Migration Notes**: Requires external SignalCore instrument control. This is a **workflow notebook** â€” no new API classes needed, just parameter grid loops over existing experiments. SignalCore communication needs a clean abstraction (currently hardcoded COM port in legacy).

---

### 9.6 â€” Notebook 12: Chevron Experiments

**File**: `12_chevron_experiments.ipynb`
**Legacy**: Exp 27, 28, 29
**Experiments**: Time Rabi, Power Rabi, and Ramsey chevrons

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("06_coherence_experiments")`
2. Time Rabi Chevron â€” `session.exp.qubit.time_rabi_chevron()`
3. Plot 2D (detuning Ã— duration)
4. Power Rabi Chevron â€” `session.exp.qubit.power_rabi_chevron()`
5. Plot 2D (detuning Ã— gain)
6. Ramsey Chevron â€” `ramsey_chevron()` (if available as API; else custom)
7. Plot 2D (frequency Ã— wait)
8. `save_stage_checkpoint(session, "12_chevron")`

**Migration Notes**: Time Rabi and Power Rabi chevrons have native `session.exp.qubit.*` support. Ramsey Chevron (Exp 29) was flagged as a copy-paste duplicate in legacy â€” verify implementation.

---

### 9.7 â€” Notebook 13: Dispersive Shift Measurement

**File**: `13_dispersive_shift_measurement.ipynb`
**Legacy**: Exp 30
**Experiments**: Resonator spectroscopy with and without Ï€-pulse for Ï‡ measurement

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
    ResonatorSpectroscopyX180,
    CalibrationOrchestrator, preview_or_apply_patch_ops,
)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("06_coherence_experiments")`
2. Run resonator spectroscopy (ground state, from notebook 03)
3. Run resonator spectroscopy w/ x180 pre-pulse â€” `ResonatorSpectroscopyX180(session, ...)`
4. Extract dispersive shift Ï‡ = f_g - f_e
5. Update `cqed_params.json` with measured Ï‡
6. `save_stage_checkpoint(session, "13_dispersive")`

---

### 9.8 â€” Notebook 14: Gate Calibration & Benchmarking

**File**: `14_gate_calibration_benchmarking.ipynb`
**Legacy**: Exp 13, 31, 32, 33, 34, 35
**Experiments**: Sequential rotations, DRAG, AllXY, RB (standard + interleaved)

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
    RandomizedBenchmarking,
    CalibrationOrchestrator, preview_or_apply_patch_ops,
)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("06_coherence_experiments")`
2. Single-qubit sequential rotations â€” compose via `session.ops` (Exp 13)
3. DRAG calibration â€” `session.exp.calibration.drag()` (Exp 31)
4. Apply DRAG coefficient to calibration store
5. All-XY â€” `session.exp.calibration.all_xy()` (Exp 32)
6. Analyze all-XY deviation pattern
7. Standard RB â€” `RandomizedBenchmarking(session, ...)` (Exp 33)
8. Report: average Clifford gate fidelity
9. Interleaved RB â€” unselective pulses (Exp 34) â€” configure `RandomizedBenchmarking` with interleaving gate
10. Interleaved RB â€” selective pulses (Exp 35)
11. Report: per-gate fidelities
12. `save_stage_checkpoint(session, "14_gate_benchmarking")`

**Migration Notes**: Standard and interleaved RB use `RandomizedBenchmarking` proxy. If native `session.exp.calibration.rb()` and `.interleaved_rb()` methods become available, prefer those.

---

### 9.9 â€” Notebook 15: Qubit State Tomography

**File**: `15_qubit_state_tomography.ipynb`
**Legacy**: Exp 36, 37, 38
**Experiments**: Qubit state tomography, full convention calibration, pulse train error amplification

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("14_gate_benchmarking")`
2. Single-state tomography â€” `session.exp.tomography.qubit_state()` (Exp 36)
3. Plot Bloch vector
4. Convention calibration â€” loop named pulses through tomography (Exp 37)
5. Cross-validate named pulse vs. parametric `QubitRotation` angles
6. Pulse train error amplification â€” sweep N repetitions (Exp 38)
7. Plot accumulated error vs. N
8. `save_stage_checkpoint(session, "15_tomography")`

---

### 9.10 â€” Notebook 16: Readout Calibration

**File**: `16_readout_calibration.ipynb`
**Legacy**: Exp 14, 39, 40, 41, 42, 43, 44, 45, 46, 47, 49, 50, 51, 53, 54
**Experiments**: Comprehensive readout pipeline â€” 14 experiments

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
    IQBlob, ReadoutGEDiscrimination, ReadoutWeightsOptimization,
    CalibrateReadoutFull, ReadoutButterflyMeasurement,
    CalibrationOrchestrator, preview_or_apply_patch_ops,
)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("06_coherence_experiments")`
2. **IQ Blob (g/e/f)** â€” `IQBlob(session, ...)` â†’ 3-state scatter (Exp 14)
3. **CLEAR readout registration** â€” build CLEAR waveform, register (Exp 39)
4. **Square readout baseline** â€” `readout_ge_integrated_trace()` (Exp 40)
5. **CLEAR readout test** â€” same with CLEAR waveform (Exp 41)
6. **Readout g/e raw trace** â€” `readout_ge_raw_trace()` (Exp 42)
7. **Readout g/e discrimination** â€” `ReadoutGEDiscrimination(session, ...)` (Exp 43)
8. **Readout g/e integrated trace** â€” time-resolved IQ (Exp 44)
9. **Readout Îº measurement** â€” ring-down fit from raw trace (Exp 45)
10. **Residual photon Ramsey** â€” `residual_photon_ramsey()` (Exp 46)
11. **Butterfly measurement** â€” `session.exp.readout.butterfly()` (Exp 47)
12. **Readout amp & length optimization** â€” `readout_amp_len_opt()` (Exp 49)
13. **Readout frequency optimization** â€” `readout_frequency_optimization()` (Exp 50)
14. **CLEAR variant comparison** (Int. Trace + Butterfly) â€” side-by-side (Exp 51)
15. **Readout weight optimization** â€” `ReadoutWeightsOptimization(session, ...)` (Exp 53)
16. **Readout full calibration** â€” `CalibrateReadoutFull(session, ...)` (Exp 54)
17. Apply all readout calibration patches
18. `save_stage_checkpoint(session, "16_readout")`

**Migration Notes**: This is the largest new notebook (14 experiments). Consider splitting into `16a_readout_characterization` and `16b_readout_optimization` if cell count exceeds ~40.

---

### 9.11 â€” Notebook 17: Readout Bayesian Optimization

**File**: `17_readout_bayesian_optimization.ipynb`
**Legacy**: Exp 52
**Experiments**: Automated Bayesian optimization of readout FÃ—Q

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
)
import ipywidgets
from skopt import gp_minimize  # scikit-optimize
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("16_readout")`
2. Define objective function: FÃ—Q from butterfly + discrimination
3. Define parameter bounds (amplitude, length, frequency, SPA power)
4. Interactive widget: configure Bayesian optimization parameters
5. Run optimization loop â€” `gp_minimize(objective, bounds, n_calls=...)`
6. Plot convergence and parameter landscape
7. Apply best parameters
8. `save_stage_checkpoint(session, "17_bayesian_opt")`

**Migration Notes**: External dependency on `scikit-optimize` and `ipywidgets`. Pure workflow notebook â€” no new API classes.

---

### 9.12 â€” Notebook 18: Active Reset Benchmarking

**File**: `18_active_reset_benchmarking.ipynb`
**Legacy**: Exp 48, 55, 92
**Experiments**: Active qubit reset protocol â€” QUA-level feedback + benchmarking

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("16_readout")`
2. Active reset benchmarking â€” `qubit_reset_benchmark()` (Exp 48)
3. Plot: reset fidelity vs. number of mid-circuit measurements
4. Qubit reset benchmark â€” `qubit_reset_benchmark()` variant (Exp 55)
5. Compare passive vs. active reset residual excitation
6. Debug active reset QUA program (Exp 92) â€” `session.ops.reset(mode="active", ...)`
7. Validate conditional feedback timing
8. `save_stage_checkpoint(session, "18_active_reset")`

---

### 9.13 â€” Notebook 19: SPA Optimization

**File**: `19_spa_optimization.ipynb`
**Legacy**: Exp 56, 57
**Experiments**: Superconducting Parametric Amplifier DC bias & pump optimization

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
    SPAFluxOptimization, SPAPumpFrequencyOptimization,
)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("16_readout")`
2. SPA DC flux tune-up â€” `SPAFluxOptimization(session, ...)` (Exp 56)
3. Find & lock optimal DC bias point
4. SPA pump power/frequency optimization â€” `SPAPumpFrequencyOptimization(session, ...)` (Exp 57)
5. 2D sweep: pump frequency Ã— pump power
6. Apply optimal SPA parameters
7. `save_stage_checkpoint(session, "19_spa")`

**Migration Notes**: Both classes are legacy proxies. Requires external DC source (octoDAC) configuration in `devices.json`.

---

### 9.14 â€” Notebook 20: Readout Leakage Benchmarking

**File**: `20_readout_leakage_benchmarking.ipynb`
**Legacy**: Exp 58
**Experiments**: Measurement-induced leakage characterization

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("16_readout")`
2. Run leakage benchmarking â€” `qubit_readout_leakage_benchmarking()`
3. Correlate repeated measurement outcomes to bit patterns
4. Plot: leakage probability vs. measurement count
5. `save_stage_checkpoint(session, "20_leakage")`

---

### 9.15 â€” Notebook 21: Storage Cavity Characterization

**File**: `21_storage_cavity_characterization.ipynb`
**Legacy**: Exp 60, 61, 62, 63, 64, 72, 73, 74
**Experiments**: Storage cavity spectroscopy, Ramsey, T1, Ï‡, Kerr, Raman, number splitting, displacement

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
    StorageSpectroscopy, NumSplittingSpectroscopy, StorageChiRamsey,
    CalibrationOrchestrator, preview_or_apply_patch_ops,
)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("16_readout")`
2. **Cavity spectroscopy** â€” `session.exp.storage.spectroscopy()` (Exp 60)
3. Fit cavity resonance, update cqed_params
4. **Storage Ramsey** â€” `storage_ramsey()` (Exp 61)
5. Extract storage T2
6. **Storage T1** â€” `session.exp.storage.t1_decay()` (Exp 62)
7. **Storage Chi Ramsey** â€” `storage_chi_ramsey()` (Exp 63)
8. Extract dispersive shift Ï‡_s
9. **Kerr Ramsey** â€” `storage_chi_ramsey()` variant w/ 2D amplitude sweep (Exp 64)
10. Extract self-Kerr K
11. **Raman two-tone power chevron** â€” `storage_raman_two_tone_power_chevron()` (Exp 72)
12. **Number-splitting spectroscopy** â€” `fock_resolved_spectroscopy()` + multi-peak fit (Exp 73)
13. **Displacement calibration (Î±)** â€” sweep DAC amplitude, fit Poisson distribution (Exp 74)
14. Apply cavity calibration patches (f_cav, Ï‡_s, K, displacement_gain)
15. `save_stage_checkpoint(session, "21_storage")`

---

### 9.16 â€” Notebook 22: Fock-Resolved Experiments

**File**: `22_fock_resolved_experiments.ipynb`
**Legacy**: Exp 65, 66, 67, 68, 69, 70, 71
**Experiments**: Per-Fock-level characterization â€” spectroscopy, Rabi, T1, T2, affine cal, tomography

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
    FockResolvedSpectroscopy, FockResolvedT1, FockResolvedRamsey,
    FockResolvedPowerRabi,
    CalibrationOrchestrator, preview_or_apply_patch_ops,
)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("21_storage")`
2. **Î±=1 displacement calibration** â€” sweep gain, fit âŸ¨nâŸ©=1 (Exp 65)
3. **Fock-resolved spectroscopy** â€” `fock_resolved_spectroscopy()` (Exp 66)
4. Fit per-Fock qubit frequencies
5. **Fock-resolved power Rabi** â€” `fock_resolved_power_rabi()` (Exp 67)
6. Calibrate selective Ï€-pulse gains per |nâŸ©
7. **Fock-resolved T1** â€” `fock_resolved_T1_relaxation()` (Exp 68)
8. Extract per-Fock T1, fit intrinsic cavity T1
9. **Fock-resolved T2 Ramsey** â€” `fock_resolved_qb_ramsey()` (Exp 69)
10. Calibrate number-split frequencies
11. **Fock-resolved affine readout calibration** â€” collect â†’ fit affine model (Exp 70)
12. Build per-Fock readout-error correction matrix
13. **Quick Fock-resolved state tomography** â€” `fock_resolved_state_tomography()` (Exp 71)
14. Validate corrected Bloch vectors
15. Apply Fock-resolved calibration patches
16. `save_stage_checkpoint(session, "22_fock_resolved")`

---

### 9.17 â€” Notebook 23: Quantum State Preparation

**File**: `23_quantum_state_preparation.ipynb`
**Legacy**: Exp 75, 76, 77, 78, 79, 80, 81
**Experiments**: SQR gates, SNAP, D-SNAP-D preparation, Bayesian optimization, Wigner

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
    SNAPOptimization,
)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("22_fock_resolved")`
2. **SQR gate test** â€” build sequence via `session.ops.sqr()` + tomography (Exp 75)
3. Visualize SQR pulse and Fock-space rotation
4. **Fock |1âŸ© prep (D-SNAP-D)** â€” compose: `displacement â†’ sqr/snap â†’ displacement` (Exp 76)
5. Verify via Fock-resolved tomography
6. **Fock |2âŸ© prep (D-SNAP-D-SNAP-D-SNAP)** â€” 6-gate sequence (Exp 77)
7. **SNAP rotation optimization (8-param Bayesian)** â€” `snap_optimization()` (Exp 78)
8. **SNAP rotation optimization (fast 2-stage)** â€” multi-fidelity (Exp 79)
9. **SNAP phase optimization** â€” Exp 80 (deferred/placeholder â€” mark as TODO)
10. **Wigner tomography** â€” `session.exp.tomography.wigner()` (Exp 81)
11. Plot Wigner function
12. `save_stage_checkpoint(session, "23_state_prep")`

---

### 9.18 â€” Notebook 24: Free Evolution Tomography

**File**: `24_free_evolution_tomography.ipynb`
**Legacy**: Exp 82, 83
**Experiments**: Time-resolved Bloch vector and per-Fock dynamics

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("22_fock_resolved")`
2. **Free evolution state tomography** â€” `free_evolution_state_tomography()` (Exp 82)
3. Plot: Bloch vector components vs. time
4. Fit: extract precession frequencies and decay rates
5. **Fock-resolved free evolution** â€” `free_evolution_fock_state_tomography()` (Exp 83)
6. Plot: per-Fock frequency trajectories
7. Extract Ï‡-dependent frequencies, compare to calibrated values
8. `save_stage_checkpoint(session, "24_free_evo_tomo")`

---

### 9.19 â€” Notebook 25: Context-Aware SQR Calibration

**File**: `25_context_aware_sqr_calibration.ipynb`
**Legacy**: Exp 84, 93, 94
**Experiments**: End-to-end SQR calibration workflow, ideal reference, artifact transfer

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
)
# Domain-specific imports from calibrations/
from calibrations.context_aware_sqr_workflow import (
    run_context_sqr_calibration,
    load_decomposition_manifest,
)
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("23_state_prep")`
2. Load decomposition manifest from `decomposition/` directory
3. **CASE_A ideal reference computation** â€” simulation baseline (Exp 93)
4. **Context-aware SQR workflow** â€” prefix tomography, compare to ideal (Exp 84)
5. Analyze systematic errors
6. **SQR artifact single-gate swap** â€” transfer simulator-optimized gate to hardware (Exp 94)
7. Validate via decomposition patching
8. `save_stage_checkpoint(session, "25_sqr_calibration")`

**Migration Notes**: Heavy integration with `calibrations/` workflow scripts. Consider importing from the existing Python modules rather than reimplementing.

---

### 9.20 â€” Notebook 26: Sequential Simulation Benchmarking

**File**: `26_sequential_simulation_benchmarking.ipynb`
**Legacy**: Exp 85, 86, 87, 88, 89, 90
**Experiments**: Sequential Wigner, holographic simulation validation (X, Y, Z, ZZ, XX, YY)

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
)
# Holographic sim imports
from holographic_sim_updated import sequential_simulator  # or equivalent
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("23_state_prep")`
2. **Sequential Wigner tomography** â€” loop decomposition + `session.exp.tomography.wigner()` (Exp 85)
3. Visualize cavity state evolution through gate sequence
4. **Sequential simulation â€” ZZ v1** â€” `sequential_simulation()` (Exp 86)
5. **Sequential simulation â€” X, Y, Z** â€” `sequential_simulation()` variations (Exp 87)
6. **Sequential simulation â€” ZZ v2** â€” error decomposition analysis (Exp 88)
7. **Sequential simulation â€” XX** (Exp 89)
8. **Sequential simulation â€” YY** (Exp 90)
9. Compare hardware vs. simulation predictions across all correlators
10. `save_stage_checkpoint(session, "26_sequential_sim")`

**Migration Notes**: Depends on `holographic_sim_updated/` package. The `sequential_simulation()` function is parametrized by gate type â€” a single experiment with different configurations.

---

### 9.21 â€” Notebook 27: Cluster State Evolution

**File**: `27_cluster_state_evolution.ipynb`
**Legacy**: Exp 91
**Experiments**: Cluster state unitary decomposition gate-by-gate validation

**Imports**:
```python
from qubox.notebook import (
    Session, load_stage_checkpoint, save_stage_checkpoint,
)
from holographic_sim_updated import cluster_state_evolution  # or equivalent
```

**Cells**:
1. Session bootstrap + `load_stage_checkpoint("26_sequential_sim")`
2. Load cluster state unitary decomposition
3. Run gate-by-gate evolution on hardware
4. Compare to ideal simulation at each step
5. Fidelity analysis: cumulative error vs. gate index
6. `save_stage_checkpoint(session, "27_cluster_state")`

---

## 10. Gap Analysis & Required Development

### 10.1 Missing Native API Wrappers (Desirable but Not Blocking)

| Experiment | Current Workaround | Native API Target |
|-----------|-------------------|------------------|
| Interleaved RB (Exp 34, 35) | `RandomizedBenchmarking` proxy with IRB config | `session.exp.calibration.interleaved_rb()` |
| Number-Splitting Spectroscopy (Exp 73) | `fock_resolved_spectroscopy()` + multi-peak fit | `session.exp.storage.num_splitting()` |
| Kerr Ramsey (Exp 64) | `storage_chi_ramsey()` with 2D amplitude sweep | `session.exp.storage.kerr_ramsey()` or parameter overload |
| eâ†’f Power Rabi (Exp 12) | `PowerRabi` proxy with `transition="ef"` | `session.exp.qubit.power_rabi(transition="ef")` |
| eâ†’f Spectroscopy (Exp 15) | `QubitSpectroscopyEF` proxy | `session.exp.qubit.spectroscopy_ef()` |

### 10.2 External Instrument Dependencies

| Notebook | Instrument | Interface |
|----------|-----------|-----------|
| 11 (2D pump sweeps) | SignalCore SC5511A | Direct COM/USB; needs clean wrapper |
| 19 (SPA optimization) | octoDAC (DC flux bias) | Via `devices.json` config |
| 07 (CW diagnostics) | Spectrum Analyzer | Manual (SA helper for automated) |

### 10.3 External Python Dependencies

| Notebook | Package | Purpose |
|----------|---------|---------|
| 17 (Bayesian opt) | `scikit-optimize` | `gp_minimize` for readout tuning |
| 17 (Bayesian opt) | `ipywidgets` | Interactive parameter UI |
| 25, 26, 27 | `holographic_sim_updated` | Sequential simulation engine |

### 10.4 Incomplete Legacy Experiments

| Exp | Issue | Action |
|-----|-------|--------|
| Exp 29 (Ramsey Chevron) | Copy-paste duplicate in legacy | Reimplement from scratch |
| Exp 80 (SNAP Phase Opt) | Empty/placeholder | Skip or implement as new feature |

---

## 11. Validation Protocol

Per `AGENTS.md Â§14`, each migrated experiment must pass:

### 11.1 Compile Validation
```python
# Every experiment produces a valid QUA program
program = experiment.build_program()
assert program is not None
```

### 11.2 Simulate Validation
```python
# Simulation produces expected signal shapes
config = QuboxSimulationConfig(duration_ns=10_000)
sim_result = session.simulate(program, config)
# Visual inspection of simulated waveforms
```

### 11.3 Hardware Comparison
```python
# Hardware results match legacy within tolerance
legacy_result = load_legacy_reference(experiment_name)
new_result = experiment.run()
assert np.allclose(new_result.data, legacy_result.data, atol=tolerance)
```

### 11.4 Acceptance Checklist (per notebook)
- [ ] All cells execute without error
- [ ] Calibration checkpoints load/save correctly
- [ ] Fit results agree with legacy within measurement uncertainty
- [ ] Plots match expected format (axes, labels, colorbars)
- [ ] No direct imports from `qubox_v2_legacy` or `qubox.legacy.*`
- [ ] All hardcoded values replaced with calibration store lookups
- [ ] Session state is not mutated outside calibration orchestrator

---

## Appendix A: File Naming Convention

```
E:\qubox\notebooks\
â”œâ”€â”€ 00_hardware_definition.ipynb         â† existing
â”œâ”€â”€ 01_mixer_calibrations.ipynb          â† existing
â”œâ”€â”€ 02_time_of_flight.ipynb              â† existing
â”œâ”€â”€ 03_resonator_spectroscopy.ipynb      â† existing
â”œâ”€â”€ 04_resonator_power_chevron.ipynb     â† existing
â”œâ”€â”€ 05_qubit_spectroscopy_pulse_calibration.ipynb  â† existing
â”œâ”€â”€ 06_coherence_experiments.ipynb       â† existing
â”œâ”€â”€ 07_cw_diagnostics.ipynb              â† NEW
â”œâ”€â”€ 08_pulse_waveform_definition.ipynb   â† NEW
â”œâ”€â”€ 09_qutrit_spectroscopy_calibration.ipynb  â† NEW
â”œâ”€â”€ 10_sideband_transitions.ipynb        â† NEW
â”œâ”€â”€ 11_coherence_2d_pump_sweeps.ipynb    â† NEW
â”œâ”€â”€ 12_chevron_experiments.ipynb         â† NEW
â”œâ”€â”€ 13_dispersive_shift_measurement.ipynb â† NEW
â”œâ”€â”€ 14_gate_calibration_benchmarking.ipynb â† NEW
â”œâ”€â”€ 15_qubit_state_tomography.ipynb      â† NEW
â”œâ”€â”€ 16_readout_calibration.ipynb         â† NEW
â”œâ”€â”€ 17_readout_bayesian_optimization.ipynb â† NEW
â”œâ”€â”€ 18_active_reset_benchmarking.ipynb   â† NEW
â”œâ”€â”€ 19_spa_optimization.ipynb            â† NEW
â”œâ”€â”€ 20_readout_leakage_benchmarking.ipynb â† NEW
â”œâ”€â”€ 21_storage_cavity_characterization.ipynb â† NEW
â”œâ”€â”€ 22_fock_resolved_experiments.ipynb   â† NEW
â”œâ”€â”€ 23_quantum_state_preparation.ipynb   â† NEW
â”œâ”€â”€ 24_free_evolution_tomography.ipynb   â† NEW
â”œâ”€â”€ 25_context_aware_sqr_calibration.ipynb â† NEW
â”œâ”€â”€ 26_sequential_simulation_benchmarking.ipynb â† NEW
â”œâ”€â”€ 27_cluster_state_evolution.ipynb     â† NEW
â”œâ”€â”€ helper/                              â† shared utilities
â”œâ”€â”€ post_cavity_experiment_context.ipynb  â† reference (keep)
â”œâ”€â”€ post_cavity_experiment_quantum_circuit.ipynb â† reference (keep)
â””â”€â”€ migration_plan.md                    â† this document
```

## Appendix B: Notebook Template

Every new notebook follows this skeleton:

```python
# Cell 1: Imports & Bootstrap
from qubox.notebook import *

# Cell 2: Session Open
session = Session.open(sample_id="...", cooldown_id="...", config_dir="...")
session.preflight()
prev = load_stage_checkpoint(session, "<previous_checkpoint>")

# Cell 3..N-1: Experiment Cells
# Each cell: (1) configure, (2) run, (3) analyze/plot, (4) patch if calibration

# Cell N: Checkpoint Save
save_stage_checkpoint(session, "<this_notebook_checkpoint>")
```

## Appendix C: Migration Tracking Template

Use this table to track progress as experiments are migrated:

| Notebook | Status | Date Created | Notes |
|----------|--------|-------------|-------|
| 07 | âœ… Created | 2025-07 | CW diagnostics â€” SA verification |
| 08 | âœ… Created | 2025-07 | Pulse waveforms (const, DRAG, displacement) |
| 09 | âœ… Created | 2025-07 | Qutrit spectroscopy + eâ†’f Rabi |
| 10 | âœ… Created | 2025-07 | Sideband transitions (GF spec + Rabi) |
| 11 | âœ… Created | 2025-07 | 2D pump sweeps (T1/T2 vs SignalCore) |
| 12 | âœ… Created | 2025-07 | Chevron experiments (Time/Power Rabi, Ramsey) |
| 13 | âœ… Created | 2025-07 | Dispersive shift Ï‡ measurement |
| 14 | âœ… Created | 2025-07 | Gate cal + benchmarking (DRAG, AllXY, RB, IRB) |
| 15 | âœ… Created | 2025-07 | Qubit state + Wigner tomography |
| 16 | âœ… Created | 2025-07 | Full readout calibration (14 experiments) |
| 17 | âœ… Created | 2025-07 | Bayesian readout optimization (skopt) |
| 18 | âœ… Created | 2025-07 | Active reset + pulse-train calibration |
| 19 | âœ… Created | 2025-07 | SPA optimization (flux, pump, discrim, IQ) |
| 20 | âœ… Created | 2025-07 | Readout leakage benchmarking |
| 21 | âœ… Created | 2025-07 | Storage cavity characterization (5 experiments) |
| 22 | âœ… Created | 2025-07 | Fock-resolved Ramsey, Power Rabi, cavity T2 |
| 23 | âœ… Created | 2025-07 | Quantum state prep (SNAP, ECD, GRAPE, cat) |
| 24 | âœ… Created | 2025-07 | Free evolution + time-resolved Wigner tomo |
| 25 | âœ… Created | 2025-07 | Context-aware SQR calibration pipeline |
| 26 | âœ… Created | 2025-07 | Sequential Trotter simulation |
| 27 | âœ… Created | 2025-07 | Cluster state evolution + Wigner verification |
