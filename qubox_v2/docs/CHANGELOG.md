# qubox_v2 Change Log

## Change-Log Policy

Every modification to the codebase must be logged in this file.

Each entry must include:

- **Date** — ISO-8601 date of the change.
- **Summary** — concise description of what changed and why.
- **Files affected** — list of modified files.
- **Classification level**:
  - **Minor** — documentation, comments, formatting, trivial fixes.
  - **Moderate** — single-feature additions, non-breaking API changes, bug fixes.
  - **Major** — schema changes, breaking API changes, architectural refactors,
    multi-file structural changes.

**Rules:**

1. Entries must be **appended only** — previous records must never be modified.
2. The AI agent must self-assess the classification level for each change.
3. Each entry should be self-contained and understandable without external context.

---

## Entries

### 2026-02-24 — Namespace Rename: device -> sample

**Classification: Major**

Renamed the experiment database namespace from "device" to "sample" across
the entire codebase.  The sample registry, experiment context, calibration
context, session manager, notebook builder, and on-disk data all now use
`sample_id` as the canonical identifier for physical chip samples.

**Summary:**

1. **Core rename (`qubox_v2/devices/sample_registry.py`)**
   - `DeviceRegistry` -> `SampleRegistry`, `DeviceInfo` -> `SampleInfo`.
   - Field renames: `device_id` -> `sample_id`, `sample_info` -> `metadata`.
   - `DEVICE_LEVEL_FILES` -> `SAMPLE_LEVEL_FILES`.
   - All method renames: `create_device` -> `create_sample`,
     `device_exists` -> `sample_exists`, `device_path` -> `sample_path`,
     `list_devices` -> `list_samples`, `load_device_info` -> `load_sample_info`.
   - On-disk directory: `devices/` -> `samples/`, `device.json` -> `sample.json`.

2. **Experiment context (`qubox_v2/core/experiment_context.py`)**
   - `ExperimentContext.device_id` -> `sample_id`.
   - `matches_device()` -> `matches_sample()`.
   - `from_dict()` accepts legacy `"device_id"` key as fallback.

3. **Session state (`qubox_v2/core/session_state.py`)**
   - `device_id` field -> `sample_id`.
   - `device_config_dir` param -> `sample_config_dir`.

4. **Calibration layer**
   - `CalibrationContext.device_id` -> `sample_id` (`calibration/models.py`).
   - `CalibrationStore` migrates legacy `context.device_id` on load (`calibration/store.py`).
   - `schemas.py` validation accepts both `sample_id` and `device_id` in context.

5. **Context resolver (`qubox_v2/devices/context_resolver.py`)**
   - All `device_id` params -> `sample_id`.

6. **Session manager (`qubox_v2/experiments/session.py`)**
   - Constructor param `device_id` -> `sample_id`.
   - `_device_config_dir` -> `_sample_config_dir`.
   - `from_device()` -> `from_sample()` (alias preserved).

7. **Notebook and tools**
   - `tools/build_context_notebook.py` updated (~25 edits).
   - Notebook regenerated (110 cells).
   - `tools/migrate_device_to_samples.py` created for on-disk data migration.

8. **On-disk data migration**
   - `devices/post_cavity_sample_A/` -> `samples/post_cavity_sample_A/`.
   - `device.json` -> `sample.json` with key renames.
   - 980 files migrated and validated.

9. **Backward compatibility**
   - `DeviceRegistry = SampleRegistry` alias in `devices/__init__.py`.
   - `DeviceInfo = SampleInfo` alias.
   - `SessionManager.from_device = from_sample` alias.
   - `SampleRegistry` falls back to `devices/` dir if `samples/` missing.
   - `from_dict()` methods accept legacy `"device_id"` keys.

10. **Documentation**
    - `API_REFERENCE.md` updated: 74 occurrences across 13 sections.
    - Version bumped to 1.7.0.

**Files affected:**
- qubox_v2/devices/sample_registry.py (renamed from device_registry.py)
- qubox_v2/devices/__init__.py
- qubox_v2/devices/context_resolver.py
- qubox_v2/core/experiment_context.py
- qubox_v2/core/session_state.py
- qubox_v2/core/schemas.py
- qubox_v2/calibration/models.py
- qubox_v2/calibration/store.py
- qubox_v2/experiments/session.py
- qubox_v2/docs/API_REFERENCE.md
- qubox_v2/docs/CHANGELOG.md
- tools/build_context_notebook.py
- tools/migrate_device_to_samples.py (new)
- notebooks/post_cavity_experiment_context.ipynb (regenerated)

---

### 2026-02-23 — Time-Unit Audit + Frequency Binding Hardening

**Classification: Major**

Targeted audit and fixes for time-unit consistency (`_clks` vs `ns`) and
runtime frequency binding to calibrated state.

**Summary:**

1. **Canonical coherence unit enforcement (seconds)**
   - T1 analysis now emits explicit `T1_ns`, `T1_s`, and `T1_us` metrics.
   - Patch generation writes `coherence.<qb>.T1` in **seconds**.
   - Added backward-compatible T1 patch rule handling for legacy keys.

2. **Legacy coherence migration guard**
   - Calibration store now normalizes legacy coherence values that were
     accidentally persisted in ns to canonical seconds (using `*_us` when
     available as authoritative companion values).

3. **Butterfly T1-decay correction unit fix**
   - `measureMacro.active_length()` is now treated explicitly as ns.
   - Conversion path is explicit and validated:
     `ns -> clks (internal canonical) -> seconds`.
   - Added metrics for `readout_duration_ns`, `readout_duration_clks`, and
     robust legacy T1 fallback handling.

4. **Additional time mismatch fix from codebase sweep**
   - `programs/builders/spectroscopy.py` had a confirmed mismatch:
     depletion wait argument documented/passed as clock cycles but divided
     by 4 internally.
   - Fixed to use clock cycles directly.
   - Added backward-compatible alias handling (`depletion_len` ->
     `depletion_clks`) with validation.

5. **Explicit time naming for residual-photon Ramsey**
   - `ResidualPhotonRamsey.run()` now uses explicit `t_relax_ns` and
     `t_buffer_ns` naming, with backward-compatible aliases
     (`t_relax`, `t_buffer`) and 4 ns grid validation.

6. **Frequency binding to calibrated state**
   - Added calibrated-frequency resolution helpers in `ExperimentBase`.
   - Ramsey and related detuned paths now use calibrated qubit frequency
     source first, then attributes fallback.
   - After patch commit, session now refreshes runtime attributes from
     calibration frequencies so `attr.qb_fq` tracks the calibrated state.

7. **Notebook context diagnostics (Section 7.5 builder)**
   - Added explicit prints for butterfly readout duration in ns/clks,
     T1 decay factor, and calibrated-vs-runtime qubit frequency delta.

**Files affected:**

- `qubox_v2/experiments/time_domain/relaxation.py`
- `qubox_v2/calibration/patch_rules.py`
- `qubox_v2/calibration/store.py`
- `qubox_v2/experiments/calibration/readout.py`
- `qubox_v2/programs/builders/spectroscopy.py`
- `qubox_v2/experiments/time_domain/coherence.py`
- `qubox_v2/experiments/experiment_base.py`
- `qubox_v2/experiments/session.py`
- `qubox_v2/calibration/orchestrator.py`
- `qubox_v2/experiments/calibration/gates.py`
- `tools/build_context_notebook.py`
- `qubox_v2/docs/CHANGELOG.md`

### 2026-02-23 — Calibration Schema + Notebook Refactor + Changelog Policy

**Classification: Major**

Structured refactor of the calibration schema, readout calibration workflow,
and API documentation.

**Summary:**

1. **Calibration schema refactor (`models.py`)**
   - `ElementFrequencies.lo_freq` and `if_freq` changed from required `float`
     to optional `float | None = None`.
   - Added `rf_freq: float | None = None` for explicit RF frequency storage.
   - `PulseCalibration.element` changed from required `str` to
     `str | None = None`.
   - Added readout calibration metadata fields to `DiscriminationParams` and
     `ReadoutQuality`: `n_shots`, `integration_time_ns`, `demod_weights`,
     `state_prep_ops`.
   - `CalibrationData.version` default changed from `"3.0.0"` to `"4.0.0"`.

2. **Calibration store refactor (`store.py`)**
   - `_atomic_write()` now uses `model_dump(exclude_none=True)` — unset
     optional fields are omitted from persisted JSON.
   - `set_frequencies()` no longer defaults `lo_freq`/`if_freq` to `0.0`.
   - `set_pulse_calibration()` no longer defaults `element` to `""`.

3. **Calibration JSON cleanup (`calibration.json`)**
   - Removed `x180` entry from `pulse_calibrations` — derived pulses must
     not be stored in calibration.
   - Fixed `element: ""` to `element: "qubit"` for `ref_r180` and
     `sel_ref_r180`.
   - Removed `lo_freq: 0.0` / `if_freq: 0.0` placeholders from qubit
     frequencies block.
   - Removed all `null` placeholder fields (confusion_matrix, alpha, beta,
     affine_n, qubit-only params in resonator block, etc.).

4. **Patch rules update (`patch_rules.py`)**
   - `DragAlphaRule` now patches only `ref_r180.drag_coeff` — derived
     primitives inherit via `PulseFactory` `rotation_derived`.

5. **Notebook refactor (`post_cavity_experiment_context.ipynb`)**
   - Section 7.5 (Full Readout Calibration): refactored to explicit
     Run → Analyze → Patch workflow.  `analyze()` called with
     `update_calibration=False`; calibration patched explicitly in
     section 7.6.
   - Section 8.3 replaced: new "Selective Pulse Calibration Update"
     following the same explicit patch pattern as section 5.7.
   - Old section 8.3 (Register Storage Cavity Pulse Definitions) moved
     to section 9.0 as the first subsection of Storage Cavity.

6. **API Reference update (`API_REFERENCE.md`)**
   - Version bumped to 1.6.0.
   - Section 4.4: updated data model table, added null-handling policy,
     frequency convention, and pulse calibration storage policy.
   - Section 4.5: readout calibration example updated to explicit patch model.
   - Section 7.2: calibration.json structure updated to v4.0.0 schema with
     context block and new conventions.
   - Section 7.4: calibration version updated from "3.0.0" to "4.0.0".

7. **Changelog policy (`CHANGELOG.md`)**
   - Introduced formal append-only change-log policy.

**Files affected:**

- `qubox_v2/calibration/models.py`
- `qubox_v2/calibration/store.py`
- `qubox_v2/calibration/patch_rules.py`
- `qubox_v2/docs/API_REFERENCE.md`
- `qubox_v2/docs/CHANGELOG.md` (new)
- `devices/post_cavity_sample_A/cooldowns/cd_2025_02_22/config/calibration.json`
- `notebooks/post_cavity_experiment_context.ipynb`

### 2026-02-23 — Derived-Pulse Calibration Write Cleanup (Consistency Scan)

**Classification: Moderate**

Post-refactor consistency scan: removed all remaining code paths that wrote
derived pulse names (x180, y180, etc.) or the deprecated
`propagate_drag_to_primitives` parameter to calibration stores, patch ops,
or orchestrator defaults.

**Summary:**

1. **DRAGCalibration analysis (`gates.py`)**
   - Removed `x180` `SetCalibration` op from `proposed_patch_ops` in
     `DRAGCalibration.analyze()`.
   - Removed the entire `propagate_drag_to_primitives` loop that generated
     per-derived-pulse `SetCalibration` ops.
   - Now emits only `ref_r180.drag_coeff` + `TriggerPulseRecompile`.

2. **Rabi experiments (`rabi.py`)**
   - `TemporalRabi.analyze()`: Changed calibration commit target from
     `name="x180"` to `name="ref_r180"`.
   - `PowerRabi.run()`: Changed default `op` parameter from `"x180"` to
     `"ref_r180"`.
   - `PowerRabi.analyze()`: Changed fallback `target_op` from `"x180"` to
     `"ref_r180"`.

3. **Orchestrator (`orchestrator.py`)**
   - `_set_pulse_param()`: Removed `"element": ""` from the fallback dict
     when no existing calibration is found, preventing empty-string element
     values from being written.

4. **API Reference (`API_REFERENCE.md`)**
   - Removed `propagate_drag_to_primitives=True` from two DRAG calibration
     examples (sections 4.5 and 9.3).

5. **Notebooks**
   - `post_cavity_experiment_context.ipynb`: Removed
     `"propagate_drag_to_primitives": True` from DRAG orchestrator
     `analyze_kwargs`.
   - `post_cavity_experiment.ipynb`: Same removal from DRAG calibration cell.

**Files affected:**

- `qubox_v2/experiments/calibration/gates.py`
- `qubox_v2/experiments/time_domain/rabi.py`
- `qubox_v2/calibration/orchestrator.py`
- `qubox_v2/docs/API_REFERENCE.md`
- `notebooks/post_cavity_experiment_context.ipynb`
- `notebooks/post_cavity_experiment.ipynb`
- `tools/build_context_notebook.py`
- `qubox_v2/examples/session_startup_demo.py`

### 2026-02-23 — Codebase Audit Cleanup (Post-Refactor Sweep)

**Classification: Major**

Comprehensive codebase audit and cleanup covering ~30 distinct issues across
all modules. Removes dead `CalibrationStateMachine` subsystem per architecture
decision to standardize on `CalibrationOrchestrator`.

**Summary:**

1. **Architecture: Remove CalibrationStateMachine (H1/H2)**
   - Deleted `calibration/state_machine.py` and `calibration/patch.py` (dead code).
   - Removed CalibrationStateMachine demo from `examples/session_startup_demo.py`.
   - Updated notebook cells referencing state machines (cells 44, 45, 104, 112).
   - Updated `API_REFERENCE.md` sections 4.2, 4.3, 4.6 and 7.5 to remove
     CalibrationStateMachine references, replaced with CalibrationOrchestrator
     and Contracts documentation.

2. **Critical field mismatches (C1)**
   - Added `T1_us`, `T2_star_us`, `T2_echo_us`, `qb_therm_clks` to
     `CoherenceParams` in `calibration/models.py`.
   - Added `phase_offset` to `PulseCalibration` in `calibration/models.py`.

3. **Return type fix (C2)**
   - `compute_probabilities()` in `analysis/analysis_tools.py` now returns
     `dict` matching its `-> Mapping[str, float]` annotation.

4. **Missing exports (C3, C4, H5)**
   - Exported `SNAPHardware` from `gates/hardware/__init__.py`.
   - Exported `PulseTrainRule` from `calibration/__init__.py`.
   - Exported `PulseError`, `CalibrationError` from `core/__init__.py`.

5. **Standardize qua.align() (H6)**
   - `DisplacementHardware.play_qua()`: `qua.align(self.target)` → `qua.align()`.

6. **Stub analyze/plot methods (H3)**
   - Added `analyze()` and `plot()` to `TimeRabiChevron`, `PowerRabiChevron`,
     `RamseyChevron` in `experiments/time_domain/chevron.py`.
   - Added `analyze()` and `plot()` to `SequentialQubitRotations` in
     `experiments/time_domain/rabi.py`.

7. **Orchestrator: list_applied_patches() (notebook support)**
   - Added `_applied_patches` tracking list and `list_applied_patches()` method
     to `CalibrationOrchestrator`.

8. **Deduplicate constants (M6)**
   - `pulses/manager.py` now imports `MAX_AMPLITUDE`, `BASE_AMPLITUDE` from
     `core/types.py` instead of redefining them.

9. **Remove duplicate imports (M7)**
   - Cleaned duplicate imports in `tools/waveforms.py`, `gates/contexts.py`,
     `analysis/analysis_tools.py`, `analysis/cQED_models.py`.

10. **Fix analysis/__all__ (M8)**
    - Removed misleading `"calibration_algorithms"` from `analysis/__init__.py`
      `__all__` (lazy-loaded module, not eagerly imported).

11. **Unused import removal (L1)**
    - Removed unused `from dataclasses import asdict` in `calibration/orchestrator.py`.

12. **Encoding artifact fix (L5)**
    - Fixed UTF-8 mojibake in `analysis/cQED_plottings.py` line 443.

**Files affected:**

- `qubox_v2/calibration/state_machine.py` (deleted)
- `qubox_v2/calibration/patch.py` (deleted)
- `qubox_v2/calibration/models.py`
- `qubox_v2/calibration/__init__.py`
- `qubox_v2/calibration/orchestrator.py`
- `qubox_v2/analysis/analysis_tools.py`
- `qubox_v2/analysis/cQED_models.py`
- `qubox_v2/analysis/cQED_plottings.py`
- `qubox_v2/analysis/__init__.py`
- `qubox_v2/core/__init__.py`
- `qubox_v2/gates/hardware/__init__.py`
- `qubox_v2/gates/hardware/displacement.py`
- `qubox_v2/gates/contexts.py`
- `qubox_v2/pulses/manager.py`
- `qubox_v2/tools/waveforms.py`
- `qubox_v2/experiments/time_domain/chevron.py`
- `qubox_v2/experiments/time_domain/rabi.py`
- `qubox_v2/examples/session_startup_demo.py`
- `qubox_v2/docs/API_REFERENCE.md`
- `qubox_v2/docs/CHANGELOG.md`
- `notebooks/post_cavity_experiment_context.ipynb`
