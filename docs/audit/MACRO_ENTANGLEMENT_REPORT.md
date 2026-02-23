# Macro System Entanglement Report

**Version**: 1.0.0
**Date**: 2026-02-22
**Status**: Audit Document — Deliverable 2 of Macro System Audit

---

## Table of Contents

1. [Category A: Experiment ↔ Macro Configuration/Mutation](#category-a-experiment--macro-configurationmutation)
2. [Category B: Program Construction ↔ Macro Internals](#category-b-program-construction--macro-internals)
3. [Category C: Persistence Side-Effects](#category-c-persistence-side-effects)
4. [Category D: Dual-Truth and Sync Failures](#category-d-dual-truth-and-sync-failures)
5. [Category E: Implicit Contracts](#category-e-implicit-contracts)

---

## Category A: Experiment ↔ Macro Configuration/Mutation

### A1. Direct private-method mutation of discrimination params

**File**: `qubox_v2/experiments/calibration/readout.py:806-807`
**Symbol**: `measureMacro._update_readout_discrimination(metrics)`

**Current behavior**: `ReadoutGEDiscrimination.analyze()` calls the underscore-prefixed
`_update_readout_discrimination()` directly on the singleton, merging analysis
output (threshold, angle, fidelity, mu_g/mu_e, sigma) into the
process-global `_ro_disc_params` dict.

**Why problematic**:
- Bypasses the calibration state machine entirely — no `PENDING_APPROVAL` or
  `COMMITTING` transition.
- Violates the "analyze is idempotent and contacts no side effects" contract
  (API Reference §3.6).
- Creates an unlabeled mutation: the caller cannot distinguish "calibration
  was updated in-memory only" from "calibration was committed to disk."

**Recommended direction**: Replace direct mutation with a patch operation
produced by analyze (e.g., `SetMeasureDiscrimination` patch entry) that flows
through `CalibrationOrchestrator.apply_patch()`.  `analyze()` should return
the proposed params in `AnalysisResult.metadata["proposed_discrimination"]`
without mutating any store.

---

### A2. Direct private-method mutation of quality params

**File**: `qubox_v2/experiments/calibration/readout.py:1794`
**Symbol**: `measureMacro._update_readout_quality(payload)`

**Current behavior**: `ReadoutButterflyMeasurement.analyze()` — called from
inside `CalibrateReadoutFull.run()` — directly merges butterfly metrics
(F, Q, V, confusion_matrix, transition_matrix) into the singleton's
`_ro_quality_params`.

**Why problematic**:
- Same state-machine bypass as A1.
- Called from inside `run()`, not `analyze()`, violating the separation
  between acquisition and calibration mutation.
- Confusion matrix (numpy array) stored in `_ro_quality_params` has no
  version or provenance tracking.

**Recommended direction**: Same as A1 — produce a patch entry; apply via
orchestrator.  The `_ro_quality_params` should be populated only through
`CalibrationOrchestrator.apply_patch()` → `SetMeasureQuality` op.

---

### A3. Direct access to singleton private dict for confusion matrix

**Files**:
- `qubox_v2/experiments/calibration/gates.py:91` (AllXY.analyze)
- `qubox_v2/experiments/calibration/gates.py:548` (DRAGCalibration.analyze)
- `qubox_v2/experiments/calibration/gates.py:884` (QubitPulseTrain.analyze)

**Symbol**: `measureMacro._ro_quality_params.get("confusion_matrix", None)`

**Current behavior**: Three separate experiment `analyze()` methods reach
directly into `measureMacro._ro_quality_params` to read the confusion matrix
for readout-error correction.  This is a **read** operation, not a mutation,
but it creates tight coupling.

**Why problematic**:
- Experiments are coupled to the internal dict schema of the singleton.
- If the confusion matrix key name or structure changes, three experiment
  files silently break.
- No fallback to `CalibrationStore.get_readout_quality()` which is the
  canonical source.

**Recommended direction**: Expose a public method on `ExperimentBase` (or a
helper in the calibration module) such as
`get_confusion_matrix(element) -> ndarray | None` that reads from
`CalibrationStore` first, with fallback to `measureMacro` for backward
compatibility.

---

### A4. measureMacro.set_pulse_op inside experiment run() methods

**Files**:
- `qubox_v2/experiments/calibration/readout.py:248` (ReadoutGEDiscrimination.run)
- `qubox_v2/experiments/calibration/readout.py:613` (set_post_select_config in readout pipeline)
- `qubox_v2/experiments/calibration/readout.py:1357` (set_outputs in CalibrateReadoutFull)

**Current behavior**: These `run()` methods mutate the measureMacro singleton
to configure readout parameters before building a QUA program.  Some use
`push_settings()`/`restore_settings()` guards, others do not.

**Why problematic**:
- `run()` is supposed to acquire data, not modify global configuration state.
- Without push/restore, later experiment cells inherit mutated readout config.
- Success of `run()` depends on a correctly pre-configured singleton that has
  no validation contract.

**Recommended direction**: All macro configuration for program construction
should happen inside a `using_defaults()` context manager (some already do —
e.g., `ResonatorSpectroscopy` at `spectroscopy/resonator.py:47`).
Non-guarded mutations inside `run()` should be wrapped in push/restore or
moved to an explicit pre-configuration step outside the experiment.

---

### A5. Stale legacy reference in sequenceMacros.post_select

**File**: `qubox_v2/programs/macros/sequence.py:380`
**Symbol**: `getattr(measureMacro, "_threshold", 0.0)`

**Current behavior**: `post_select()` reads `measureMacro._threshold` which
no longer exists in the v2 data model.  The threshold is now stored in
`measureMacro._ro_disc_params["threshold"]`.

**Why problematic**:
- Always evaluates to `0.0` (the default), making the scalar-threshold policy
  non-functional unless `kwargs["threshold"]` is explicitly provided.
- Silent failure — no warning or error is raised.

**Recommended direction**: Replace with
`measureMacro._ro_disc_params.get("threshold", 0.0)` or better, expose a
`measureMacro.get_threshold() -> float` public accessor.

---

## Category B: Program Construction ↔ Macro Internals

### B1. readout_ge_integrated_trace mutates macro during program build

**File**: `qubox_v2/programs/cQED_programs.py:856-885`
**Symbols**: `measureMacro.set_outputs(...)`, `measureMacro.set_demodulator(demod.sliced, div_clks)`, `measureMacro.set_output_ports(output_ports)`

**Current behavior**: The program factory function reconfigures the singleton's
demodulation settings as part of constructing the QUA program.  The calling
experiment (`ReadoutGEIntegratedTrace.run()` at `readout.py:247`) wraps this
in `push_settings()`/`restore_settings()`.

**Why problematic**:
- The program factory is supposed to be a pure function: parameters in →
  QUA program out.  Side-effecting the global singleton violates this.
- If push/restore is forgotten (or throws), the singleton is left in a
  modified state for all subsequent programs.
- The knowledge that `readout_ge_integrated_trace` needs special weight
  configuration is encoded in the program builder rather than in the
  experiment class where it belongs.

**Recommended direction**: Move the `set_outputs()`/`set_demodulator()` calls
into the experiment's `run()` method (inside a `using_defaults()` context).
The program factory should accept the weight/demod configuration as explicit
parameters.

---

### B2. All program functions implicitly read measureMacro

**File**: `qubox_v2/programs/cQED_programs.py` (44 of 46 functions)
**Symbol**: `measureMacro.measure(...)`, `measureMacro.active_element()`

**Current behavior**: Every program factory function calls
`measureMacro.measure()` to emit the QUA `measure()` statement.  This reads
the singleton's `_pulse_op`, `_active_op`, `_demod_weight_sets`,
`_ro_disc_params["threshold"]`, and `_gain` at program-compile time.

**Why problematic**:
- There is no parameter-based alternative — the readout configuration is
  always implicit.
- Testing a program factory in isolation requires configuring the global
  singleton first.
- The "contract" between experiment and program is invisible: the experiment
  must know which singleton fields the program will read.

**Recommended direction**: See Refactor Proposal §3 for the
`MeasurementSpec` abstraction that makes the readout configuration explicit.

---

### B3. sequenceMacros hard-codes measureMacro.active_element() calls

**File**: `qubox_v2/programs/macros/sequence.py:65,81,137`
**Symbol**: `measureMacro.active_element()`

**Current behavior**: `qubit_state_tomography`, `fock_resolved_spectroscopy`,
and `num_splitting_spectroscopy` call `measureMacro.active_element()` to get
the readout element for `align()` directives.

**Why problematic**:
- The readout element is implicitly sourced from the singleton rather than
  passed as a parameter.
- Makes these helpers non-reusable for multi-readout-element configurations.

**Recommended direction**: Accept `ro_el` as an explicit parameter with
fallback to `measureMacro.active_element()` for backward compatibility.

---

## Category C: Persistence Side-Effects

### C1. measureMacro.save_json inside experiment run pipelines

**Files**:
- `qubox_v2/experiments/calibration/readout.py:817` (ReadoutGEDiscrimination.analyze → save)
- `qubox_v2/experiments/calibration/readout.py:2198` (CalibrateReadoutFull nested save)

**Current behavior**: `analyze()` and the CalibrateReadoutFull pipeline
call `measureMacro.save_json(...)` to persist the updated singleton state to
`measureConfig.json`.

**Why problematic**:
- `analyze()` performing disk I/O violates the idempotency contract.
- Persistence happens outside the `CalibrationOrchestrator` path, so the
  `PersistMeasureConfig` patch operation is redundant/concurrent.
- If the save succeeds but a subsequent calibration.json write fails,
  the two files are out of sync.

**Recommended direction**: Remove direct `save_json()` calls from
experiment code.  All persistence should flow through
`CalibrationOrchestrator.apply_patch()` which already has the
`PersistMeasureConfig` operation type.

---

### C2. SessionManager.override_readout_operation persistence

**File**: `qubox_v2/experiments/session.py:556-559`

**Current behavior**: `override_readout_operation(persist_measure_config=True)`
writes `measureConfig.json` immediately after reconfiguring the singleton.

**Why problematic**:
- This is a **session-level** method that directly serializes macro state.
- The write happens before any experiment validates whether the new readout
  configuration actually works.
- If `override_readout_operation` is called multiple times, each call
  overwrites the previous file — no transactional grouping.

**Recommended direction**: This is acceptable as an explicit user action
(session-level override).  However, the method should stamp the
`measureConfig.json` with a provenance record (timestamp, source="user_override")
to distinguish from experiment-generated saves.

---

### C3. SessionManager.close() does not save measureConfig

**File**: `qubox_v2/experiments/session.py:588-599`

**Current behavior**: `close()` saves `pulses.json`, `session_runtime.json`,
and `calibration.json`, but does **not** call `measureMacro.save_json()`.

**Why problematic**:
- If an experiment mutated `measureMacro._ro_disc_params` in-memory but
  did not explicitly save, the changes are lost on close.
- Other stores (`calibration.json`, `pulses.json`) are saved — the
  asymmetry is confusing.

**Recommended direction**: Add `measureMacro.save_json()` to `close()` with
the same try/except pattern, or document that `measureConfig.json` is only
written by explicit calls.

---

## Category D: Dual-Truth and Sync Failures

### D1. Discrimination params in two stores

**Files**:
- `qubox_v2/programs/macros/measure.py:148-159` (`_ro_disc_params`)
- `qubox_v2/calibration/store.py` (`CalibrationStore.discrimination`)

**Current behavior**: Discrimination parameters (threshold, angle, fidelity,
mu_g, mu_e, sigma) exist in:

1. `measureMacro._ro_disc_params` → persisted as `measureConfig.json`
2. `CalibrationStore.discrimination[element]` → persisted as `calibration.json`

Both are written during the readout calibration pipeline, but:
- `ReadoutGEDiscrimination.analyze()` writes to **both** via separate code paths
  (line 636 for CalibrationStore, line 807 for measureMacro).
- The orchestrator `DiscriminationRule` writes to CalibrationStore;
  `WeightRegistrationRule` writes to measureMacro (lines 170-204 in
  orchestrator.py).

**Why problematic**:
- No reconciliation on load — `SessionManager.open()` loads both independently.
- If only one is updated (e.g., manual CalibrationStore edit), the other is stale.
- Experiment code reads from whichever is convenient — some read
  `measureMacro._ro_disc_params`, others read `CalibrationStore`.

**Recommended direction**: Designate `CalibrationStore` as the single source
of truth.  `measureMacro._ro_disc_params` should be populated **from**
`CalibrationStore` on session open, and re-synced after any calibration commit.
The sync direction should always be `CalibrationStore → measureMacro`, never
the reverse.

---

### D2. Readout quality params in two stores

**Files**:
- `qubox_v2/programs/macros/measure.py:161-174` (`_ro_quality_params`)
- `qubox_v2/calibration/store.py` (`CalibrationStore.readout_quality`)

**Current behavior**: Same dual-truth pattern as D1 but for butterfly/quality
metrics (F, Q, V, confusion matrix).

**Why problematic**: Same as D1, amplified by the fact that the confusion
matrix (a numpy array) is serialized differently in each store:
- `measureConfig.json`: via `sanitize_mapping_for_json()` with potential
  array truncation.
- `calibration.json`: via Pydantic model serialization.

**Recommended direction**: Same as D1.

---

### D3. Drive frequency in three locations

**Files**:
- `qubox_v2/programs/macros/measure.py:145` (`_drive_frequency`)
- `qubox_v2/calibration/models.py` (`ElementFrequencies.if_freq`)
- `qubox_v2/core/attributes.py` (`cQED_attributes.ro_fq`)

**Current behavior**: `ExperimentBase.set_standard_frequencies()` (line 228-233
of experiment_base.py) reads `measureMacro._drive_frequency` first, falling
back to `cqed_attributes.ro_fq`.  `CalibrationStore.frequencies` is a third
source.

**Why problematic**: Three-way source of truth with different update cadences.

**Recommended direction**: `CalibrationStore.frequencies` should be canonical.
`measureMacro._drive_frequency` should be initialized from it.
`cqed_attributes.ro_fq` should be deprecated (it's already read-only in v2).

---

## Category E: Implicit Contracts

### E1. measureMacro must be configured before any program construction

**File**: `qubox_v2/programs/cQED_programs.py` (all 44 program functions)

**Current behavior**: Every program function calls
`measureMacro.active_element()` and `measureMacro.active_op()`, which raise
`RuntimeError` if no PulseOp has been bound.  The precondition is enforced
at runtime but not at the type level or API level.

**Why problematic**:
- The contract is invisible — there is no type signature or protocol that
  indicates "measureMacro must be configured."
- Failure messages reference internal method names (`set_pulse_op`) that
  are implementation details.

**Recommended direction**: Make the readout configuration an explicit
parameter of program construction (see Refactor Proposal §3), or at minimum
add a `measureMacro.is_configured() -> bool` guard with a clear error.

---

### E2. Storage experiments assume measureMacro outputs are configured

**File**: `qubox_v2/experiments/cavity/storage.py:438-442`

**Current behavior**: `StorageChiRamsey.run()` checks
`measureMacro._demod_weight_sets` and raises if empty, with the guidance:
*"Run CalibrateReadoutFull (or measureMacro.set_outputs()) first."*

**Why problematic**:
- This is a runtime guard for a precondition that should be part of session
  setup, not scattered across individual experiments.
- Only this one experiment has the guard; others will fail with cryptic
  QM-level errors if weights are not configured.

**Recommended direction**: Move the "readout is calibrated" check to
`SessionManager.validate_runtime_elements()` or a dedicated
`session.validate_readout_ready()` method called during `open()`.

---

### E3. Circular import: cQED_programs → experiments.gates_legacy

**File**: `qubox_v2/programs/cQED_programs.py:8`
**Symbol**: `from ..experiments.gates_legacy import Gate, GateArray, Measure`

**Current behavior**: The program module (Layer 3/programs) imports from
the experiment module (Layer 6).  This works because Python resolves it at
import time, but it violates the layer dependency rule.

**Why problematic**:
- Layer 3 should not depend on Layer 6.
- The `Gate`/`GateArray`/`Measure` types are only used by
  `sequential_simulation()` — a single function.
- This import makes the entire programs package depend on the experiments
  package.

**Recommended direction**: Move `Gate`/`GateArray`/`Measure` to a lower-layer
module (e.g., `core/gate_types.py` or `gates/gate_types.py`), or move
`sequential_simulation()` to a separate module in `programs/`.

---

## Summary Table

| ID | Category | Severity | File(s) | Line(s) |
|----|----------|----------|---------|---------|
| A1 | Macro mutation | **High** | `calibration/readout.py` | 806-807 |
| A2 | Macro mutation | **High** | `calibration/readout.py` | 1794 |
| A3 | Private dict read | Medium | `calibration/gates.py` | 91, 548, 884 |
| A4 | Run-time macro config | Medium | `calibration/readout.py` | 248, 613, 1357 |
| A5 | Stale reference | Low | `macros/sequence.py` | 380 |
| B1 | Side-effecting builder | Medium | `cQED_programs.py` | 856-885 |
| B2 | Implicit singleton read | Medium | `cQED_programs.py` | 44 functions |
| B3 | Implicit element source | Low | `macros/sequence.py` | 65, 81, 137 |
| C1 | analyze() disk I/O | Medium | `calibration/readout.py` | 817, 2198 |
| C2 | Override persistence | Low | `session.py` | 556-559 |
| C3 | Missing close save | Low | `session.py` | 588-599 |
| D1 | Dual-truth disc | **High** | `measure.py`, `store.py` | 148, — |
| D2 | Dual-truth quality | **High** | `measure.py`, `store.py` | 161, — |
| D3 | Triple-truth freq | Medium | `measure.py`, `models.py`, `attributes.py` | 145, —, — |
| E1 | Implicit precondition | Medium | `cQED_programs.py` | all |
| E2 | Scattered guards | Low | `cavity/storage.py` | 438-442 |
| E3 | Circular import | Low | `cQED_programs.py` | 8 |

---

*Cross-reference: MACRO_PROGRAM_ARCHITECTURE.md §5, API Reference §14-15,
LEAKS.md §A, PATHS_AND_OWNERSHIP.md Obs 1-2, STALE_CALIBRATION_RISK_REPORT.md R3.*
