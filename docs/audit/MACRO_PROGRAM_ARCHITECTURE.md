# Macro & Program Architecture Summary

**Version**: 1.0.0
**Date**: 2026-02-22
**Status**: Audit Document — Deliverable 1 of Macro System Audit

---

## Table of Contents

1. [measureMacro](#1-measuremacro)
2. [sequenceMacros](#2-sequencemacros)
3. [cQED\_programs](#3-cqed_programs)
4. [Cross-Component Data Flow](#4-cross-component-data-flow)
5. [Summary of Architectural Concerns](#5-summary-of-architectural-concerns)

---

## 1. measureMacro

**Module**: `qubox_v2/programs/macros/measure.py`
**Type**: Module-level singleton class (non-instantiable; raises `TypeError` on `__new__`)
**Lines**: ~1611

### 1.1 Data Model (Class-Level State)

All state is stored as **mutable class variables** — there is no instance.

| Variable | Type | Default | Purpose |
|----------|------|---------|---------|
| `_pulse_op` | `PulseOp \| None` | `None` | Bound measurement pulse definition |
| `_active_op` | `str \| None` | `None` | QUA operation handle override |
| `_demod_weight_sets` | `list[list[str]]` | `[["cos","sin"],["minus_sin","cos"]]` | Integration weight label pairs |
| `_demod_weight_len` | `int \| None` | `None` | Override for demod integration length |
| `_demod_fn` | `callable` | `dual_demod.full` | QUA demodulator function |
| `_demod_args` | `tuple` | `()` | Positional args for demod function |
| `_demod_kwargs` | `dict` | `{}` | Keyword args for demod function |
| `_per_fn` | `list \| None` | `None` | Per-output demodulator overrides |
| `_per_args` | `list \| None` | `None` | Per-output demod positional args |
| `_per_kwargs` | `list \| None` | `None` | Per-output demod keyword args |
| `_gain` | `float \| None` | `None` | Amplitude scaling factor |
| `_drive_frequency` | `float \| None` | `None` | Readout drive IF frequency |
| `_save_raw_data` | `bool` | `False` | Persistence flag for KDE dataset |
| `_ro_disc_params` | `dict` | See below | Discrimination parameters |
| `_ro_quality_params` | `dict` | See below | Butterfly/quality parameters |
| `_post_select_config` | `PostSelectionConfig \| None` | `None` | Post-selection policy |
| `_state_stack` | `list[tuple[str, dict]]` | `[]` | Saved-state stack for push/restore |
| `_state_index` | `dict[str, int]` | `{}` | state_id → stack index |
| `_state_counter` | `int` | `0` | Auto-increment ID counter |

**`_ro_disc_params` schema:**
```python
{
    "threshold": float | None,
    "angle": float | None,
    "fidelity": float | None,
    "rot_mu_g": complex | None,
    "unrot_mu_g": complex | None,
    "sigma_g": float | None,
    "rot_mu_e": complex | None,
    "unrot_mu_e": complex | None,
    "sigma_e": float | None,
    "norm_params": dict,
}
```

**`_ro_quality_params` schema:**
```python
{
    "alpha": float | None,
    "beta": float | None,
    "F": float | None,              # Fidelity
    "Q": float | None,              # QND-ness
    "V": float | None,              # Visibility
    "t01": float | None,            # 0→1 transition rate
    "t10": float | None,            # 1→0 transition rate
    "eta_g": float | None,
    "eta_e": float | None,
    "confusion_matrix": ndarray | None,
    "transition_matrix": ndarray | None,
    "affine_n": dict | None,        # Per-Fock affine correction
}
```

### 1.2 Public Methods

#### Core Properties (Read-Only)

| Method | Signature | Return | Description |
|--------|-----------|--------|-------------|
| `active_element` | `() -> str` | `str` | Element from bound PulseOp |
| `active_op` | `() -> str` | `str` | Resolved QUA operation handle |
| `active_length` | `() -> int \| None` | `int \| None` | Readout pulse length in ns |

#### Configuration Setters

| Method | Signature | Side Effects |
|--------|-----------|--------------|
| `set_pulse_op` | `(pulse_op, *, active_op, weights, weight_len)` | Binds PulseOp + weights + length |
| `set_active_op` | `(op_handle: str)` | Overrides active QUA op |
| `set_gain` | `(gain)` | Sets amplitude scaling |
| `set_demod_weight_len` | `(demod_weight_len)` | Sets integration length |
| `set_drive_frequency` | `(freq)` | Sets readout IF frequency |
| `set_demodulator` | `(fn, *args, **kwargs)` | Sets demod function + args |
| `set_per_output_demodulators` | `(fns, args_list, kwargs_list)` | Per-output demod overrides |
| `set_outputs` | `(weight_specs, weight_len=None)` | Sets integration weight labels |
| `set_output_ports` | `(ports: list[str])` | Clones demod config per-port |
| `set_IQ_mod` | `(I_mod_weights, Q_mod_weights)` | Two-channel weight shorthand |
| `add_output` | `(weight_spec)` | Appends an output channel |
| `set_post_select_config` | `(cfg, *, copy=True)` | Sets post-selection policy |

#### Readout Calibration Mutators

| Method | Signature | Description |
|--------|-----------|-------------|
| `_update_readout_discrimination` | `(out: dict)` | Merges discrimination params from analysis output |
| `_update_readout_quality` | `(out: dict)` | Merges butterfly/quality params from analysis output |

These are **underscore-prefixed** but called **directly by experiment code** (see Entanglement Report).

#### Computation

| Method | Signature | Return | Description |
|--------|-----------|--------|-------------|
| `compute_Pe_from_S` | `(S)` | `float \| ndarray` | Linear projection of IQ signal to P(e) |
| `compute_posterior_weights` | `(S, model_type, pi_e, require_finite)` | `(w_g, w_e)` | Bayesian posterior from Gaussian model |
| `compute_posterior_state_weight` | `(S, target_state, ...)` | `ndarray` | Single-state convenience wrapper |

#### State Stack (Push/Restore)

| Method | Signature | Return | Description |
|--------|-----------|--------|-------------|
| `push_settings` | `(state_id=None) -> str` | `str` | Save snapshot to stack; returns ID |
| `restore_settings` | `(state_id=None)` | `None` | Pop or retrieve by ID |
| `retrieve_state` | `(state_id)` | — | Alias for `restore_settings(state_id=…)` |

#### Context Managers

| Method | Description |
|--------|-------------|
| `using_defaults(*, pulse_op, active_op, weight_len)` | Temp default config; auto push/restore |

#### Persistence (JSON)

| Method | Signature | Description |
|--------|-----------|-------------|
| `save_json` | `(path: str)` | Serialize current state to `measureConfig.json` (v5) |
| `load_json` | `(path: str)` | Deserialize from JSON; supports v3/v4/v5 formats |
| `to_json_dict` | `() -> dict` | In-memory dict representation |

#### Introspection

| Method | Signature | Description |
|--------|-----------|-------------|
| `show_settings` | `(*, return_dict=False)` | Pretty-print or return settings dict |
| `get_readout_calibration` | `() -> dict` | Merged disc + quality params |
| `export_readout_calibration` | `() -> dict` | Structured {discrimination, butterfly} export |
| `get_outputs` | `() -> list` | Current weight specs |
| `get_gain` | `() -> float \| None` | Current gain |
| `get_IQ_mod` | `() -> tuple` | Current IQ modulation pair |
| `get_drive_frequency` | `() -> float \| None` | Current drive frequency |
| `get_demod_weight_len` | `() -> int \| None` | Current weight length |

#### Reset

| Method | Description |
|--------|-------------|
| `reset()` | Full reset to defaults + clear stack |
| `reset_pulse()` | Clear pulse binding |
| `reset_weights()` | Revert to base weight set |
| `reset_demodulator()` | Revert to `dual_demod.full` |
| `reset_gain()` | Clear gain |
| `default()` | Alias for `reset()` |

#### QUA Code Generation

| Method | Description |
|--------|-------------|
| `measure(*, with_state, gain, timestamp_stream, adc_stream, state, targets, axis, x90, yn90, qb_el)` | **Emits QUA `measure()` statement** — the core code-generation method used by all programs |

### 1.3 Persistence Lifecycle

```
SessionManager.__init__()
    └→ (calibration store, POM loaded)

SessionManager.open()
    └→ _load_measure_config()
       └→ measureMacro.load_json("config/measureConfig.json")  ← restores singleton state

session.override_readout_operation()
    └→ measureMacro.set_pulse_op(...)
    └→ measureMacro.save_json(...)                              ← persists measureConfig.json

CalibrateReadoutFull.run()
    └→ measureMacro._update_readout_discrimination(out)        ← mutates disc params
    └→ measureMacro._update_readout_quality(payload)           ← mutates quality params
    └→ measureMacro.save_json(...)                              ← persists

CalibrationOrchestrator.apply_patch() [PersistMeasureConfig op]
    └→ measureMacro.save_json(...)                              ← persists

SessionManager.close()
    └→ (no explicit measureMacro.save_json; relies on prior saves)
```

### 1.4 Key Design Observations

1. **Global mutable state**: All state is class-level.  Any import of `measureMacro` shares the same state across the entire process.
2. **Dual-truth problem**: Discrimination params in `_ro_disc_params` overlap with `CalibrationStore.discrimination` — no enforced sync.
3. **Direct private-method mutation**: `_update_readout_discrimination` and `_update_readout_quality` are called directly by experiment `analyze()` methods, bypassing the calibration state machine.
4. **QUA code emission**: `measure()` generates QUA IR at call-time — it is a **compile-time** operation within a `with program()` block, not a runtime call.
5. **Callable serialization**: Demod functions are serialized via a string registry (`_callable_registry`), introducing a fragile mapping between JSON keys and QM SDK callables.

---

## 2. sequenceMacros

**Module**: `qubox_v2/programs/macros/sequence.py`
**Type**: Static class (all `@classmethod`)
**Lines**: ~479

### 2.1 Data Model

`sequenceMacros` has **no persistent state**.  It is a stateless collection of QUA code-generation utilities.  It imports `measureMacro` and delegates readout calls to it.

### 2.2 Public Methods

| Method | Signature | Description | Depends On |
|--------|-----------|-------------|------------|
| `qubit_ramsey` | `(delay_clk, qb_el, r90_1, r90_2)` | Two π/2 pulses with delay | — |
| `qubit_echo` | `(delay_clk_1, delay_clk_2, qb_el, r90, r180)` | Hahn echo sequence | — |
| `conditional_reset_ground` | `(I, thr, r180, qb_el)` | Conditional π if I > threshold | — |
| `conditional_reset_excited` | `(I, thr, r180, qb_el)` | Conditional π if I < threshold | — |
| `qubit_state_tomography` | `(state, *, state_prep, state_st, therm_clks, targets, axis, qb_el, x90, yn90, qb_probe_if, selective_pulse, selective_freq, wait_after, wait_after_clks)` | Full tomography macro with optional selective pulse | **measureMacro** |
| `num_splitting_spectroscopy` | `(probe_ifs, state_prep, I, Q, I_st, Q_st, st_therm_clks, *, qb_el, st_el, sel_r180)` | Number-splitting scan | **measureMacro** |
| `fock_resolved_spectroscopy` | `(fock_ifs, state_prep, I, Q, I_st, Q_st, st_therm_clks, *, qb_el, st_el, sel_r180)` | Fock-resolved frequency scan | **measureMacro** |
| `prepare_state` | `(*, target_state, policy, r180, qb_el, max_trials, targets, state, **prep_kwargs)` | Active qubit reset with configurable acceptance policy (ZSCORE, AFFINE, HYSTERESIS, BLOBS, scalar) | **measureMacro** |
| `post_select` | `(*, accept, I, Q, target_state, policy, **kwargs)` | Post-selection acceptance rule (same policy set) | `measureMacro._threshold` (legacy ref) |

### 2.3 Key Design Observations

1. **Stateless helper** — no persistence, no data model.  Good separation in principle.
2. **Hard dependency on measureMacro singleton** — calls `measureMacro.measure()`, `measureMacro.active_element()`.  Cannot be tested or used without configuring the singleton first.
3. **QUA code emission** — all methods emit QUA IR (play, wait, measure, assign, etc.) and must be called inside `with program()` blocks.
4. **Post-selection references stale `_threshold`** — `post_select` references `getattr(measureMacro, "_threshold", 0.0)` which is a legacy attribute no longer set in the v2 data model.
5. **Import consumers**: Used directly only by `cQED_programs.py` and `gates_legacy.py`.

---

## 3. cQED_programs

**Module**: `qubox_v2/programs/cQED_programs.py`
**Type**: Monolithic module of QUA program factory functions
**Lines**: 2914

### 3.1 Imports

```python
from qm.qua import *
from qualang_tools.loops import from_array
from .macros.measure import measureMacro       # singleton
from .macros.sequence import sequenceMacros    # stateless helper
import numpy as np
from ..experiments.gates_legacy import Gate, GateArray, Measure
```

### 3.2 Program Families

**46 public functions** grouped into logical families:

#### Spectroscopy (8 functions)

| Function | Line | measureMacro? | sequenceMacros? |
|----------|------|:---:|:---:|
| `readout_trace` | 10 | **Yes** | — |
| `resonator_spectroscopy` | 40 | **Yes** | — |
| `resonator_power_spectroscopy` | 75 | **Yes** | — |
| `qubit_spectroscopy` | 111 | **Yes** | — |
| `qubit_spectroscopy_ef` | 151 | **Yes** | — |
| `resonator_spectroscopy_x180` | 620 | **Yes** | — |
| `storage_spectroscopy` | 1752 | **Yes** | — |
| `num_splitting_spectroscopy` | 1781 | **Yes** | **Yes** |

#### Time-Domain (10 functions)

| Function | Line | measureMacro? | sequenceMacros? |
|----------|------|:---:|:---:|
| `temporal_rabi` | 194 | **Yes** | — |
| `power_rabi` | 230 | **Yes** | — |
| `time_rabi_chevron` | 267 | **Yes** | — |
| `power_rabi_chevron` | 310 | **Yes** | — |
| `ramsey_chevron` | 351 | **Yes** | — |
| `T1_relaxation` | 397 | **Yes** | — |
| `T2_ramsey` | 433 | **Yes** | **Yes** |
| `T2_echo` | 468 | **Yes** | **Yes** |
| `ac_stark_shift` | 733 | **Yes** | — |
| `residual_photon_ramsey` | 776 | **Yes** | — |

#### Readout / IQ Calibration (6 functions)

| Function | Line | measureMacro? | Notable |
|----------|------|:---:|---------|
| `iq_blobs` | 699 | **Yes** | — |
| `readout_ge_raw_trace` | 816 | **Yes** | — |
| `readout_ge_integrated_trace` | 856 | **Yes** | **Mutates measureMacro** (calls `set_outputs`, `set_demodulator`) |
| `readout_core_efficiency_calibration` | 967 | **Yes** | Complex multi-role function (~280 lines) |
| `readout_butterfly_measurement` | 1094 | **Yes** | — |
| `readout_leakage_benchmarking` | 1250 | **Yes** | — |

#### Gate Calibration (7 functions)

| Function | Line | measureMacro? | sequenceMacros? |
|----------|------|:---:|:---:|
| `all_xy` | 1299 | **Yes** | — |
| `randomized_benchmarking` | 1329 | **Yes** | — |
| `qubit_pulse_train_legacy` | 1420 | **Yes** | — |
| `qubit_pulse_train` | 1537 | **Yes** | — |
| `drag_calibration_YALE` | 1629 | **Yes** | — |
| `drag_calibration_GOOGLE` | 1680 | **Yes** | — |
| `sequential_qb_rotations` | 666 | **Yes** | — |

#### Cavity / Fock-Resolved (11 functions)

| Function | Line | measureMacro? | sequenceMacros? |
|----------|------|:---:|:---:|
| `sel_r180_calibration0` | 1800 | **Yes** | **Yes** |
| `fock_resolved_spectroscopy` | 1903 | **Yes** | **Yes** |
| `fock_resolved_T1_relaxation` | 2104 | **Yes** | — |
| `fock_resolved_power_rabi` | 2155 | **Yes** | — |
| `fock_resolved_qb_ramsey` | 2187 | **Yes** | — |
| `fock_resolved_state_tomography` | 2215 | **Yes** | **Yes** |
| `storage_wigner_tomography` | 2411 | **Yes** | — |
| `phase_evolution_prog` | 2473 | **Yes** | — |
| `storage_chi_ramsey` | 2530 | **Yes** | — |
| `storage_ramsey` | 2572 | **Yes** | — |
| `qubit_state_tomography` | 506 | **Yes** | **Yes** |

#### Reset / Benchmark (2 functions)

| Function | Line | measureMacro? | sequenceMacros? |
|----------|------|:---:|:---:|
| `qubit_reset_benchmark` | 2623 | **Yes** | **Yes** |
| `active_qubit_reset_benchmark` | 2699 | **Yes** | **Yes** |

#### Utility (2 functions)

| Function | Line | measureMacro? | Description |
|----------|------|:---:|-------------|
| `continuous_wave` | 2844 | — | CW debug output |
| `SPA_flux_optimization` | 2855 | **Yes** | SPA flux scan |
| `sequential_simulation` | 2880 | **Yes** | Gate-based circuit execution |

### 3.3 Re-Export Wrapper Modules

Six thin wrapper modules exist in `qubox_v2/programs/` that re-export subsets from `cQED_programs`:

| Module | Functions Re-Exported |
|--------|-----------------------|
| `programs/spectroscopy.py` | `readout_trace`, `resonator_spectroscopy`, `resonator_power_spectroscopy`, `resonator_spectroscopy_x180`, `qubit_spectroscopy`, `qubit_spectroscopy_ef`, `storage_spectroscopy`, `num_splitting_spectroscopy` |
| `programs/time_domain.py` | `temporal_rabi`, `power_rabi`, `time_rabi_chevron`, `power_rabi_chevron`, `ramsey_chevron`, `T1_relaxation`, `T2_ramsey`, `T2_echo`, `ac_stark_shift`, `residual_photon_ramsey` |
| `programs/readout.py` | `iq_blobs`, `readout_ge_raw_trace`, `readout_ge_integrated_trace`, `readout_core_efficiency_calibration`, `readout_butterfly_measurement`, `readout_leakage_benchmarking`, `qubit_reset_benchmark`, `active_qubit_reset_benchmark` |
| `programs/calibration.py` | `all_xy`, `randomized_benchmarking`, `drag_calibration_YALE`, `drag_calibration_GOOGLE`, `sequential_qb_rotations`, `qubit_pulse_train`, `qubit_pulse_train_legacy` |
| `programs/cavity.py` | `storage_wigner_tomography`, `storage_chi_ramsey`, `storage_ramsey`, `phase_evolution_prog`, `fock_resolved_spectroscopy`, `fock_resolved_T1_relaxation`, `fock_resolved_power_rabi`, `fock_resolved_qb_ramsey`, `sel_r180_calibration0`, `SPA_flux_optimization`, `continuous_wave` |
| `programs/tomography.py` | `qubit_state_tomography`, `fock_resolved_state_tomography`, `sequential_simulation` |

**These wrappers only re-export — no code has been migrated out of the monolith.**

### 3.4 Key Design Observations

1. **Universal measureMacro dependency**: 44 of 46 functions call `measureMacro.measure()` or `measureMacro.active_element()`.  The singleton is the implicit readout contract.
2. **No session/context parameter**: Functions receive raw physics parameters (element names, frequency arrays, pulse names) but have no reference to `SessionManager` or calibration state.  The singleton bridges this gap implicitly.
3. **Side-effecting program builder**: `readout_ge_integrated_trace` (line 856) mutates `measureMacro` state (`set_outputs`, `set_demodulator`, `set_output_ports`) during program construction — mixing code generation with configuration mutation.
4. **Monolithic structure**: 2914 lines in a single file with no internal organization beyond linear listing.  Related functions are not grouped by namespace.
5. **Circular import risk**: Imports `Gate`/`GateArray`/`Measure` from `experiments.gates_legacy` — a Layer 6 module importing from Layer 6, routed through the programs package.

---

## 4. Cross-Component Data Flow

### 4.1 Program Construction Flow

```
Notebook / ExperimentBase.run()
    │
    │  1) set_standard_frequencies()
    │     └→ reads measureMacro._drive_frequency
    │
    │  2) calls cQED_programs.<function>(physics_params...)
    │     │
    │     │  inside `with program()`:
    │     │    ├→ measureMacro.active_element()    ← reads _pulse_op.element
    │     │    ├→ measureMacro.active_op()          ← reads _active_op or _pulse_op.op
    │     │    ├→ measureMacro.measure(...)          ← reads _demod_weight_sets, _demod_fn,
    │     │    │                                        _gain, _ro_disc_params["threshold"]
    │     │    ├→ sequenceMacros.qubit_ramsey(...)  ← stateless QUA emit
    │     │    └→ sequenceMacros.prepare_state(...) ← reads measureMacro threshold/params
    │     │
    │     └→ returns QUA program object
    │
    │  3) ProgramRunner.run_program(prog, ...)
    │     └→ QM.execute(prog)
    │
    └→ RunResult
```

### 4.2 Calibration Update Flow (Readout Path)

```
CalibrateReadoutFull.run()
    │
    │  sub-experiment: ReadoutGEDiscrimination.analyze()
    │    └→ measureMacro._update_readout_discrimination(out)    ← DIRECT MUTATION
    │    └→ measureMacro.set_pulse_op(...)                       ← rebind weights
    │
    │  sub-experiment: ReadoutButterflyMeasurement.analyze()
    │    └→ measureMacro._update_readout_quality(payload)       ← DIRECT MUTATION
    │
    │  CalibrationStore.set_discrimination(...)                  ← parallel update
    │  measureMacro.save_json(measureConfig.json)                ← persist macro state
    │
    └→ Two stores now contain overlapping discrimination data
```

### 4.3 Orchestrator Patch Flow

```
CalibrationOrchestrator.apply_patch()
    │
    ├→ SetCalibration    → CalibrationStore.set_*()
    ├→ SetMeasureWeights → measureMacro.set_pulse_op(...)
    ├→ PersistMeasureConfig → measureMacro.save_json(...)
    └→ TriggerPulseRecompile → session.burn_pulses()
```

---

## 5. Summary of Architectural Concerns

| # | Concern | Severity | Components |
|---|---------|----------|------------|
| A1 | **Global mutable singleton** — measureMacro state is process-global; no isolation between notebook cells or test fixtures | High | `measure.py` |
| A2 | **Dual-truth stores** — discrimination params in both `measureConfig.json` and `calibration.json` with no enforced sync | High | `measure.py`, `store.py` |
| A3 | **Direct private-method mutation** — `_update_readout_*` called by experiments bypassing calibration state machine | High | `readout.py`, `measure.py` |
| A4 | **Monolithic 2914-line cQED_programs** — no internal structure; re-export wrappers exist but contain no migrated code | Medium | `cQED_programs.py` |
| A5 | **Implicit singleton contract** — all 44 program functions assume measureMacro is pre-configured; no parameter or protocol-based alternative | Medium | `cQED_programs.py`, `measure.py` |
| A6 | **Program-builder side effects** — `readout_ge_integrated_trace` mutates macro state during code generation | Medium | `cQED_programs.py:856` |
| A7 | **Stale legacy references** — `sequenceMacros.post_select` references `_threshold` which no longer exists | Low | `sequence.py:380` |
| A8 | **Circular layer dependency** — `cQED_programs` imports from `experiments.gates_legacy` (Layer 3 → Layer 6) | Low | `cQED_programs.py:8` |
| A9 | **Callable serialization fragility** — demod function ↔ string mapping in `_callable_registry` is manually maintained | Low | `measure.py:1509` |

---

*Cross-reference: API Reference §14, §15; audit docs: LEAKS.md §A, PATHS_AND_OWNERSHIP.md Obs 1-2.*
