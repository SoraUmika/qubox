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
4. **No automatic commits.** The AI agent must NEVER run `git commit` or
   `git push` without explicit user approval. All changes must be staged and
   presented for manual review before committing.

---

## Entries

### 2026-02-27 — Generic Alias System (v2.3.1)

**Classification: Minor**

Replaced the fixed-role `set_roles(qubit=..., readout=..., storage=...)` API
with a generic `set_aliases()` that accepts arbitrary alias→element mappings.
No mandatory role names are enforced by the builder; well-known names
(`"qubit"`, `"readout"`, `"storage"`) are convention-mapped to legacy
`cqed_params.json` fields for backward compatibility.

**Summary:**

1. **`set_aliases()` replaces `set_roles()` (`hardware_definition.py`)**
   - Accepts `dict[str, str]` and/or `**kwargs` (merged, kwargs win).
   - No specific alias names are required — the builder is fully generic.
   - Internally stores `self._aliases` instead of `self._roles`.

2. **Validation relaxed**
   - Removed check 1 (qubit/readout roles required).
   - Check 2 (readout alias validation) only triggers when a `"readout"`
     alias is present.
   - Remaining checks renumbered 1–9.

3. **`to_cqed_seed()` convention-based mapping**
   - Well-known aliases map to legacy fields: `"qubit"` → `qb_el`/`qb_fq`,
     `"readout"` → `ro_el`/`ro_fq`, `"storage"` → `st_el`/`st_fq`.
   - All aliases stored under `__aliases` key for forward-compatible readers.

4. **`_build_qubox_extras()` generic roles**
   - `__qubox.bindings.roles` now populated from all aliases (not just
     hardcoded qubit/readout/storage).
   - `readout_acquire` auto-added when `"readout"` alias targets a readout
     element with `rf_in`.

5. **Notebook update (`post_cavity_experiment_context.ipynb`)**
   - Cell 4: `set_roles(...)` → `set_aliases(...)`.

6. **Documentation (`API_REFERENCE.md`)**
   - Section 27.4 renamed to "Wiring & Alias Methods"; `set_roles()` docs
     replaced with `set_aliases()` including alias→cqed_params mapping table.
   - Validation table updated (checks renumbered, check 1 removed).

**Files affected:**

- `qubox_v2/core/hardware_definition.py`
- `notebooks/post_cavity_experiment_context.ipynb`
- `qubox_v2/docs/API_REFERENCE.md` — Section 27
- `qubox_v2/docs/CHANGELOG.md` — This entry

---

### 2026-02-26 — HardwareDefinition Device Builder (v2.3)

**Classification: Moderate**

Extended `HardwareDefinition` to generate `devices.json` alongside
`hardware.json` and `cqed_params.json`, making notebook cell 4 the single
source of truth for all hardware setup — no manual JSON editing required.

**Summary:**

1. **`_DeviceDef` dataclass (`hardware_definition.py`)**
   - Internal representation for external instrument definitions: `name`,
     `driver`, `backend`, `connect`, `settings`, `enabled`.

2. **`set_instrument_server()` method**
   - Stores shared InstrumentServer connection defaults (`host`, `port`,
     `timeout`).  Devices added after this call auto-inherit these
     connection parameters.

3. **`add_device()` method**
   - Adds an external device with smart defaults: when a shared server is
     set and `connect=None`, auto-populates the connect dict.
     `instrument_name` shorthand avoids verbose connect dicts for the
     common InstrumentServer case.

4. **`to_devices_dict()` / `save_devices()` methods**
   - `to_devices_dict()` returns the flat dict matching the existing
     `devices.json` schema.
   - `save_devices(path, merge_existing=True)` writes the file, preserving
     any manually-added devices.  Returns `None` if no devices defined.

5. **Validation check 10**
   - `validate()` now warns (not errors) when `set_external_lo(device=X)`
     references a device not defined via `add_device()`.

6. **Session integration (`session.py`)**
   - `_apply_hardware_definition()` now also generates `devices.json` after
     `hardware.json` and `cqed_params.json`.

7. **Notebook update (`post_cavity_experiment_context.ipynb`)**
   - Cell 4 updated with `set_instrument_server()` and `add_device()` calls
     for all 4 external instruments (`octave_external_lo2`,
     `octave_external_lo4`, `octodac_bf`, `sa124b`).

8. **Documentation (`API_REFERENCE.md`)**
   - Added Section 27 "HardwareDefinition Builder (v2.3)" covering
     constructor, element methods, device builder methods, generation &
     persistence, validation, session integration, and usage example.

**Files affected:**

- `qubox_v2/core/hardware_definition.py`
- `qubox_v2/experiments/session.py`
- `notebooks/post_cavity_experiment_context.ipynb`
- `qubox_v2/docs/API_REFERENCE.md` — Section 27
- `qubox_v2/docs/CHANGELOG.md` — This entry

---

### 2026-02-26 — QUA Program Build & Simulation Refactor (v2.2)

**Classification: Major**

Added first-class `build_program()` → `ProgramBuildResult` and `simulate()` →
`SimulationResult` support to all 26 experiment classes, enabling program
introspection and offline waveform simulation without touching hardware.

**Summary:**

1. **Phase 0 — Core infrastructure (`experiments/result.py`, `experiment_base.py`, `hardware/program_runner.py`)**
   - `ProgramBuildResult` frozen dataclass (12 fields): captures QUA program,
     resolved parameters, frequency assignments, processors, and provenance.
   - `QuboxSimulationConfig` dataclass: centralises simulation parameters
     (duration_ns, plot, controllers, compiler_options).
   - `SimulationResult` dataclass: wraps simulated waveform samples +
     full provenance chain back to `ProgramBuildResult`.
   - Base class `build_program()` calls `_build_impl()` then applies
     `resolved_frequencies` to hardware config.
   - Base class `simulate()` calls `build_program()` then `runner.simulate()`.
   - Pure frequency resolvers: `_resolve_readout_frequency()` (bindings →
     measureMacro → attributes), `_resolve_qubit_frequency(detune=)`.
   - `_serialize_bindings()` for JSON-safe provenance snapshots.

2. **Phase 1 — Pilot experiments (4 classes)**
   - PowerRabi, T1Relaxation, QubitSpectroscopy, ResonatorSpectroscopy
     migrated to `_build_impl()` pattern. `run()` delegates to
     `build_program()` + `run_program()`.

3. **Phase 2 — Full migration (22 remaining classes)**
   - **Spectroscopy**: ResonatorSpectroscopyX180, ReadoutTrace,
     ResonatorPowerSpectroscopy, QubitSpectroscopyEF.
   - **Time domain**: TemporalRabi, SequentialQubitRotations, T2Ramsey,
     T2Echo, ResidualPhotonRamsey, TimeRabiChevron, PowerRabiChevron,
     RamseyChevron.
   - **Cavity/storage**: StorageSpectroscopy, NumSplittingSpectroscopy,
     StorageRamsey, StorageChiRamsey, StoragePhaseEvolution.
   - **Cavity/fock**: FockResolvedSpectroscopy, FockResolvedT1,
     FockResolvedRamsey, FockResolvedPowerRabi.
   - **Multi-program (NotImplementedError)**: QubitSpectroscopyCoarse,
     ReadoutFrequencyOptimization, StorageSpectroscopyCoarse — these use
     multi-LO segment loops and cannot produce a single ProgramBuildResult.

4. **Key migration patterns applied across all classes:**
   - `set_standard_frequencies()` replaced with pure resolvers.
   - `attr.qb_fq`/`attr.ro_fq` direct references replaced with
     `_resolve_qubit_frequency()` / `_resolve_readout_frequency()`.
   - Processors stored as immutable tuples in ProgramBuildResult.
   - measureMacro-dependent experiments use `_setup_measure_context()` +
     `simulate()` override.
   - Non-serializable params (callables, large arrays) excluded from `params`.

5. **Documentation (API_REFERENCE.md)**
   - Added Section 26 "Program Build & Simulation (v2.2)" covering design
     principles, data types, base class methods, migration pattern,
     measureMacro context pattern, multi-program experiments, usage examples,
     and migration status table.

**Files affected:**

- `qubox_v2/experiments/result.py` — ProgramBuildResult, SimulationResult
- `qubox_v2/experiments/experiment_base.py` — build_program(), _build_impl(),
  simulate(), pure resolvers
- `qubox_v2/hardware/program_runner.py` — QuboxSimulationConfig
- `qubox_v2/experiments/time_domain/rabi.py`
- `qubox_v2/experiments/time_domain/relaxation.py`
- `qubox_v2/experiments/time_domain/coherence.py`
- `qubox_v2/experiments/time_domain/chevron.py`
- `qubox_v2/experiments/spectroscopy/qubit.py`
- `qubox_v2/experiments/spectroscopy/resonator.py`
- `qubox_v2/experiments/cavity/storage.py`
- `qubox_v2/experiments/cavity/fock.py`
- `qubox_v2/docs/API_REFERENCE.md` — Section 26
- `qubox_v2/docs/CHANGELOG.md` — This entry

---

### 2026-02-26 — Roleless experiment primitives (v2.1 API)

**Classification: Moderate**

Introduced frozen, role-free types that decouple experiment code from the
mutable `ExperimentBindings` role vocabulary.  Experiments type-check for
generic `DriveTarget` and `ReadoutHandle` — never for "qubit" or "storage"
specifically.  Added per-experiment frozen Config dataclasses and session
factory methods.

**Summary:**

1. **Phase 0 frozen primitives** (`core/bindings.py`):
   - `DriveTarget` — frozen control output (element, lo_freq, rf_freq, therm_clks).
     `if_freq` property, `from_output_binding()` classmethod.
   - `ReadoutCal` — frozen calibration artifact snapshot (drive_frequency,
     threshold, rotation_angle, confusion_matrix, fidelity, weight_keys).
     `from_calibration_store()`, `from_readout_binding()`, `with_discrimination()`.
   - `ReadoutHandle` — frozen readout channel + ReadoutCal + element + operation.
   - `ElementFreq` — resolved frequency per element with provenance `source` tag
     ("explicit", "calibration", "sample_default").
   - `FrequencyPlan` — immutable frequency plan applied atomically per run.
     `from_targets()`, `apply(hw)`, `to_metadata()`.

2. **`emit_measurement()`** (`programs/macros/measure.py`) — Pure function
   replacement for `measureMacro.measure()`.  Takes a `ReadoutHandle`, builds
   demod from `cal.weight_keys`, returns QUA variables.

3. **Session factory methods** (`experiments/session.py`):
   - `session.drive_target(alias)` — resolves alias to `DriveTarget` from
     hardware config + calibration store.
   - `session.readout_handle(alias)` — resolves alias to `ReadoutHandle`.
   - Ergonomic shortcuts: `session.qubit()`, `session.storage()`, `session.readout()`.

4. **Per-experiment Config dataclasses** (`experiments/configs.py`):
   - `PowerRabiConfig`, `TemporalRabiConfig`, `T1RelaxationConfig`,
     `T2RamseyConfig`, `T2EchoConfig`, `ResonatorSpectroscopyConfig`,
     `QubitSpectroscopyConfig`, `StorageSpectroscopyConfig`.
   - All frozen, composable via `dataclasses.replace()`.

5. **Notebook update** — Added v2.1 API imports, explanation markdown cell,
   and interactive demonstration cell to `post_cavity_experiment_context.ipynb`.

6. **Documentation** — Added Section 25 to API_REFERENCE.md covering all v2.1
   types, session factories, Config dataclasses, and migration guidance.

**Files affected:**
- `qubox_v2/core/bindings.py` — Added 5 frozen dataclasses
- `qubox_v2/core/__init__.py` — Updated `__all__` exports
- `qubox_v2/programs/macros/measure.py` — Added `emit_measurement()`
- `qubox_v2/experiments/session.py` — Added factory methods
- `qubox_v2/experiments/configs.py` — Created (8 Config dataclasses)
- `notebooks/post_cavity_experiment_context.ipynb` — Added v2.1 cells
- `qubox_v2/docs/API_REFERENCE.md` — Added Section 25
- `qubox_v2/docs/CHANGELOG.md` — This entry

---

### 2026-02-26 — Complete builder bindings coverage + implementation audit

**Classification: Moderate**

Added `bindings: ExperimentBindings | None = None` parameter to all remaining
program builder functions (18 functions across 4 files) and appended a
comprehensive implementation status checklist to the refactor report.

**Summary:**

1. **Builder bindings coverage** — Added binding resolution pattern to:
   - `readout.py`: `readout_ge_raw_trace`, `readout_ge_integrated_trace`,
     `readout_core_efficiency_calibration`, `readout_butterfly_measurement`,
     `readout_leakage_benchmarking`, `qubit_reset_benchmark`,
     `active_qubit_reset_benchmark` (7 functions)
   - `calibration.py`: `all_xy`, `randomized_benchmarking`,
     `drag_calibration_YALE`, `drag_calibration_GOOGLE` (4 functions)
   - `cavity.py`: `sel_r180_calibration0`, `fock_resolved_spectroscopy`,
     `fock_resolved_T1_relaxation`, `fock_resolved_power_rabi`,
     `fock_resolved_qb_ramsey`, `storage_wigner_tomography` (6 functions)
   - `tomography.py`: `fock_resolved_state_tomography` (1 function)

2. **Implementation status checklist** — Appended §10 to
   `docs/api_refactor_output_binding_report.md` cross-referencing every
   recommendation from §2–§6 against codebase state.  Covers 80+ checklist
   items across binding model, measureMacro redesign, 12 ranked coupling
   items, calibration schema, and migration phases.

**Files affected:**
- `qubox_v2/programs/builders/readout.py`
- `qubox_v2/programs/builders/calibration.py`
- `qubox_v2/programs/builders/cavity.py`
- `qubox_v2/programs/builders/tomography.py`
- `docs/api_refactor_output_binding_report.md`
- `qubox_v2/docs/CHANGELOG.md` (this entry)

---

### 2026-02-24 — Notebook Usability Refactor + Rotation Calibration Port

**Classification: Moderate**

Comprehensive refactoring of `post_cavity_experiment_context.ipynb` for
improved usability, mixer calibration workflow, bug fixes, and porting
of the legacy arbitrary qubit rotation calibration pipeline.

**Summary:**

1. **A1 — Setup flow merge (Sections 1+2+2.1 -> Section 1)**
   - Merged 11 cells (registry, sample, cooldown, session, open, preflight,
     readout override) into a 4-cell idempotent initialization flow.
   - Combined `SessionManager` creation and `session.open()` into a single cell.
   - Preflight validation, config snapshot, and schema validation in Section 1.1.
   - Imports consolidated into a single cell with all dependencies.

2. **A2 — Dedicated readout override cell (Section 1.2)**
   - Extracted readout override into its own cell with explicit I/O documentation.
   - Clear inputs: element, operation, weights, demod, threshold, weight length.
   - Clear outputs: updated measureMacro state, persisted measureConfig.json.

3. **B — Mixer calibration overhaul (Section 2)**
   - Added Section 2.0: Auto Calibration (Octave built-in) with
     `hw.calibrate_element(method="auto", auto_sa_validate=True)`.
   - Added Section 2.1: Manual Calibration UX Controls (scan bounds, SA settings).
   - Added Section 2.2: Manual IQ Calibration Run with before/after metrics.
   - Section renumbered from 3 to 2.

4. **C — Bug fixes**
   - Fixed `ro_pipeline_summary.get("discrimination")` using nonexistent keys;
     replaced with `ro_pipeline_analysis.metrics` access.
   - Fixed `eval(name)` security issue in session summary; replaced with
     `globals().get(name)`.

5. **D — Arbitrary qubit rotation calibration port (Sections 5.1d-5.1f)**
   - Section 5.1d: Verify Run — applies knob corrections and re-runs
     pulse-train tomography on a 3-prep subset at half n_avg.
   - Section 5.1e: Verify Analysis — compares before/after angular deviations.
   - Section 5.1f: Apply Corrections to All Standard Rotations — broadcasts
     d_lambda/d_alpha/d_omega knob maps to all pi/2 and pi gates via
     `register_rotations_from_ref_iq`.

6. **Section renumbering**
   - All sections renumbered: 3->2, 4->3, ..., 14->13 (net reduction of 1).
   - TOC and summary table updated to match.

7. **E — No auto-commit policy**
   - Added Rule #4 to CHANGELOG.md policy section.

**Files affected:**
- `notebooks/post_cavity_experiment_context.ipynb` (116 cells, restructured)
- `qubox_v2/docs/CHANGELOG.md` (policy update + this entry)

---

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

---

### 2026-02-26 — Additional Migration: samples/ + post_cavity notebook to binding-driven path

**Classification: Major**

Completed follow-up migration work after the v2.0.0 binding-driven redesign, covering sample configuration canonicalization and notebook-level API updates.

**Summary:**

1. **Binding-first sample config support**
  - Extended `__qubox` hardware extras schema to include canonical binding payloads and aliases:
    - `bindings`, `binding_bundle`, `aliases`, `alias_map`
  - `bindings_from_hardware_config()` now prefers canonical `__qubox.bindings`, with legacy `elements` fallback.
  - `build_alias_map()` now prefers canonical alias maps and resolves to physical `ChannelRef`s.

2. **Representative sample migrated (`post_cavity_sample_A`)**
  - Added canonical `__qubox.bindings` and `__qubox.aliases` to sample-level `hardware.json`.
  - Preserved ergonomic user aliases (`qubit`, `resonator`) mapped to physical IDs.
  - Migrated cooldown `calibration.json` from schema `4.0.0` to `5.0.0`:
    - stable keys by physical channel ID
    - `alias_index` for dual alias/physical lookup

3. **Notebook migration (binding-driven setup bridge)**
  - Updated `post_cavity_experiment_context.ipynb` setup/readout workflow toward `session.bindings` path.
  - Added binding aliases and compatibility bridge variables to keep legacy element-op helper calls usable during transition.

4. **Validation**
  - Verified binding resolution from migrated sample config (`qubit`, `resonator`, readout acquire chain).
  - Verified calibration dual lookup by alias and physical ID on migrated v5.0.0 calibration file.

**Files affected:**
- `qubox_v2/core/config.py`
- `qubox_v2/core/bindings.py`
- `samples/post_cavity_sample_A/config/hardware.json`
- `samples/post_cavity_sample_A/cooldowns/cd_2025_02_22/config/calibration.json`
- `notebooks/post_cavity_experiment_context.ipynb`
- `docs/api_refactor_output_binding_report.md`
- `qubox_v2/docs/CHANGELOG.md`
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

---

### 2026-02-25 — Audit-Driven Bug Fixes & Hardening (v1.8.0)

**Classification: Moderate**

Systematic fixes for all issues identified in the audit (see below): 4 bugs,
duplicate/missing patch rules, dead parameters, incomplete calibration
patterns, and documentation updates.

**Summary:**

1. **BUG-1 — Wigner negativity formula (`wigner_tomo.py:67`)**
   - `negativity = np.abs(np.sum(W[W < 0]))` was applying `np.abs` to
     already-negative values, which is correct mathematically but masked
     intent.  Changed to `negativity = float(-np.sum(W[W < 0]))` for
     clarity and to match the standard Wigner negativity definition
     (sum of negative volume).

2. **BUG-2 — Silent exception swallowing in SPAPumpFrequencyOptimization
   (`flux_optimization.py`)**
   - Bare `except Exception: pass` silently swallowed errors during SPA
     frequency optimization.  Added `logging` import and replaced with
     `logger.exception("SPA pump frequency optimization step failed")`
     so failures are recorded.

3. **BUG-3 — T1Rule heuristic unit guess (`patch_rules.py:~120`)**
   - T1 unit-detection heuristic used `T1_val > 1.0` to distinguish
     seconds vs nanoseconds.  A 10 us T1 (1e-5 s) would be incorrectly
     treated as nanoseconds and divided by 1e9 again.  Changed threshold
     to `T1_val > 1e-3`, which correctly classifies all realistic T1
     values (sub-ms coherence times in seconds vs nanosecond-scale raw
     values).

4. **BUG-4 — QubitStateTomography plot reading reduced metrics
   (`qubit_tomo.py:89-100`)**
   - `plot()` read scalar `sx/sy/sz` from `analysis.metrics`, discarding
     multi-prep array data in `analysis.data`.  Changed to prefer
     `analysis.data.get("sx")` (full array) with fallback to
     `analysis.metrics.get("sx")` (scalar mean).

5. **Patch rule deduplication (`patch_rules.py:282-313`)**
   - `WeightRegistrationRule` was redundantly included in `pi_amp` and
     `pulse_train` kinds where it has no effect (those experiments don't
     produce `proposed_patch_ops` metadata).  Removed from both to avoid
     confusing no-op rule invocations.

6. **Missing `resonator_freq` FrequencyRule (`patch_rules.py:292,305`)**
   - `default_patch_rules()` had no rule for `resonator_freq` kind,
     meaning `ResonatorSpectroscopy.analyze()` calibration results were
     silently dropped by the orchestrator.  Added
     `FrequencyRule(element=ro_el, kind="resonator_freq",
     metric_key="f0", field="resonator_freq")` mapped to kind
     `"resonator_freq"`.

7. **Dead `update_calibration` warnings (5 experiments)**
   - `FockResolvedSpectroscopy`, `FockResolvedT1`, `FockResolvedRamsey`,
     `FockResolvedPowerRabi` (all in `cavity/fock.py`) and
     `NumSplittingSpectroscopy` (`cavity/storage.py`) accepted
     `update_calibration=True` but silently ignored it.  Added explicit
     `logger.warning(...)` directing users to the CalibrationOrchestrator.

8. **StorageSpectroscopyCoarse calibration pattern (`cavity/storage.py`)**
   - `StorageSpectroscopyCoarse.analyze()` had no calibration path.
     Added `proposed_patch_ops` metadata (matching `StorageSpectroscopy`
     pattern) so the orchestrator can apply storage frequency patches.

9. **FockResolvedSpectroscopy peak extraction (`cavity/fock.py`)**
   - `analyze()` stored `float(mag.min())` as each Fock frequency, which
     is the minimum signal magnitude rather than the frequency at the
     minimum.  Changed to `float(frequencies[np.argmin(fock_mag)])` to
     extract the actual frequency of the spectroscopic dip.

10. **Dead parameters removed from SPAFluxOptimization2
    (`spa/flux_optimization.py`)**
    - Removed 5 `run()` parameters that were accepted but never used:
      `flux_step`, `spa_gain`, `readout_gain`, `readout_len`,
      `saturation_amp`.  The underlying program builder does not consume
      them.

11. **SNAPOptimization / FockResolvedStateTomography documentation
    (`tomography/wigner_tomo.py`)**
    - Added cross-reference docstring noting that SNAPOptimization uses
      `cQED_programs.SQR_state_tomography` (gate-level control) whereas
      `FockResolvedStateTomography` uses
      `cQED_programs.fock_resolved_state_tomography` (callable
      state-prep).  No code merge: different QUA programs justify
      separate classes.

12. **API_REFERENCE.md v1.8.0 update**
    - Version bumped to 1.8.0, date updated to 2026-02-25.
    - Section 13.4 (Patch Rules): expanded table with `PulseTrainRule`,
      added detailed default rule mapping table showing all 12 kinds.
      Updated `FrequencyRule` to list `resonator_freq` kind.  Updated
      `T1Rule` description with unit heuristic detail.
    - Section 9.1 (SPA): updated `SPAFluxOptimization2` description.

**Files affected:**

- `qubox_v2/experiments/tomography/wigner_tomo.py`
- `qubox_v2/experiments/tomography/qubit_tomo.py`
- `qubox_v2/experiments/cavity/fock.py`
- `qubox_v2/experiments/cavity/storage.py`
- `qubox_v2/experiments/spa/flux_optimization.py`
- `qubox_v2/calibration/patch_rules.py`
- `qubox_v2/docs/API_REFERENCE.md`
- `qubox_v2/docs/CHANGELOG.md`

---

### 2026-02-25 — Readout Pipeline Consistency Audit & Fixes

**Classification: Moderate**

Audited the full readout pipeline (GE Discrimination → Butterfly → CalibrateReadoutFull)
for consistency between legacy `cQED_Experiment` and qubox_v2.  Produced a mapping
document and fixed 4 bugs in the state-handoff path.

**Summary:**

1. **Audit document (inline in this CHANGELOG)**
   - Full Legacy ↔ qubox_v2 pipeline ordering comparison.
   - Policy-object tables: readout discrimination, quality, and state-prep.
   - State-handoff invariant analysis (GE → Butterfly).
   - 4 bugs and 2 mismatches identified and documented.

2. **BUG-R1 — `qbx_readout_state` missing from default dict (`measure.py:148`)**
   - `_ro_disc_params` did not include `qbx_readout_state` in its default keys,
     causing `_apply_defaults()` to silently drop it.  Added
     `"qbx_readout_state": None` to the default dict.

3. **BUG-R2 — `_update_readout_quality` dead code (`measure.py:441–452`)**
   - The `t01`/`t10` transition-probability and `eta_g`/`eta_e` update code
     inside `_update_readout_quality()` was wrapped in a triple-quoted string
     literal (dead code).  Restored the code so butterfly metrics propagate
     to `_ro_quality_params` immediately on `SetMeasureQuality` patch ops.

4. **BUG-R3 — `sync_from_calibration` loses `qbx_readout_state` (`measure.py:455`)**
   - `sync_from_calibration()` overwrites `_ro_disc_params` from CalibrationStore
     but `qbx_readout_state` is a runtime-only hash not stored in CalibStore.
     Added save/restore of `qbx_readout_state` around the sync so Butterfly's
     hash comparison survives calibration commits.

5. **BUG-R4 — Orchestrator swallows sync errors silently (`orchestrator.py:243`)**
   - Bare `except Exception: pass` after `sync_from_calibration()` in
     `apply_patch()` silently discarded errors.  Replaced with
     `_logger.warning(...)` so failures are logged.

**Files affected:**

- `qubox_v2/programs/macros/measure.py`
- `qubox_v2/calibration/orchestrator.py`
- `qubox_v2/docs/CHANGELOG.md` (audit content inline)

---

### 2026-02-25 — Canonical Transition Identity Layer (Phase 1)

**Classification: Major**

Defined and applied the canonical naming / metadata normalization layer for
qubit transition identity (`ge`, `ef`).  All pulse names, calibration records,
and patch rules now use a single source of truth for transition-prefixed names.

**Summary:**

1. **New module: `calibration/transitions.py`**
   - `Transition` enum (`GE`, `EF`), `DEFAULT_TRANSITION`, `TransitionLiteral`.
   - `CANONICAL_REF_PULSES` / `CANONICAL_DERIVED_PULSES` / `ALL_CANONICAL` sets.
   - Legacy alias map: bare names (`x180`, `ref_r180`) → canonical `ge_*`.
   - Public helpers: `resolve_pulse_name()`, `canonical_ref_pulse()`,
     `canonical_derived_pulse()`, `extract_transition()`,
     `strip_transition_prefix()`, `primitive_family()`, `is_canonical()`.

2. **Model metadata: `transition` field**
   - Added `transition: str | None = None` to `PulseCalibration`,
     `PulseTrainResult` (models), `CalibrationResult` (contracts),
     and `PulseSpecEntry` (spec_models).

3. **Calibration store migration**
   - `CalibrationStore` resolves aliases on get/set via `resolve_pulse_name()`.
   - `_migrate_pulse_cal_keys()` auto-renames legacy bare keys on load.

4. **Patch rules canonical defaults**
   - `PiAmpRule`, `DragAlphaRule`, `PulseTrainRule` default to `ge_ref_r180`.
   - All rules resolve target ops through `resolve_pulse_name()`.

5. **cQED_attributes canonical fields**
   - Added `ge_r180_amp`, `ge_rlen`, `ge_rsigma`, `ef_r180_amp`, `ef_rlen`,
     `ef_rsigma` with legacy promotion in `__post_init__`.

6. **Experiment defaults**
   - `DRAGCalibration`, `PowerRabi` default ops updated to canonical names.

7. **Sample data migration**
   - `calibration.json`: keys renamed to `ge_ref_r180`, `ge_sel_ref_r180`
     with `transition: "ge"` field.
   - `cqed_params.json`: added `ge_*` prefixed fields.

8. **Exports**
   - `calibration/__init__.py` exports entire transitions module.

**Files affected:**

- `qubox_v2/calibration/transitions.py` (new)
- `qubox_v2/calibration/models.py`
- `qubox_v2/calibration/contracts.py`
- `qubox_v2/calibration/store.py`
- `qubox_v2/calibration/patch_rules.py`
- `qubox_v2/calibration/__init__.py`
- `qubox_v2/pulses/spec_models.py`
- `qubox_v2/analysis/cQED_attributes.py`
- `qubox_v2/experiments/calibration/gates.py`
- `qubox_v2/experiments/time_domain/rabi.py`
- `samples/post_cavity_sample_A/cooldowns/cd_2025_02_22/config/calibration.json`
- `samples/post_cavity_sample_A/config/cqed_params.json`
- `qubox_v2/docs/CHANGELOG.md`

---

### 2026-02-25 — Transition-Aware Spectroscopy & Frequency Storage (Phase 2)

**Classification: Moderate**

Made the spectroscopy layer and frequency storage contract explicitly
transition-aware using the canonical naming layer from Phase 1.

**Summary:**

1. **`ElementFrequencies.ef_freq` field (`models.py`)**
   - Added `ef_freq: float | None = None` to `ElementFrequencies`.
   - `qubit_freq` remains the legacy/canonical GE slot; `ef_freq` is the
     new canonical EF slot.

2. **`QubitSpectroscopy` transition-aware (`spectroscopy/qubit.py`)**
   - `run()` accepts `transition: str = "ge"` parameter.
   - `analyze()` reads transition from `result.metadata`, routes
     `calibration_kind` and patch path via `_TRANSITION_FREQ_MAP`.
   - GE → `qubit_freq` field, EF → `ef_freq` field.

3. **`QubitSpectroscopyCoarse` transition-aware + bug fix**
   - Added `pulse: str` parameter (was missing — first arg to builder was
     incorrectly `attr.ro_el`, a readout element name, not a pulse op).
   - Added `transition: str = "ge"` parameter.
   - `analyze()` routes via `_TRANSITION_FREQ_MAP` like `QubitSpectroscopy`.

4. **`QubitSpectroscopyEF` canonical cleanup**
   - Hardcoded `"x180"` → configurable `ge_prep_pulse: str = "ge_x180"`.
   - Added `transition="ef"` metadata to run result.
   - `analyze()` now produces `calibration_kind: "ef_freq"` metadata and
     `proposed_patch_ops` targeting `frequencies.<qb_el>.ef_freq`.
   - Emits both `f0` and `f_ef` metrics for compatibility.

5. **`default_patch_rules` EF frequency rule (`patch_rules.py`)**
   - Added `FrequencyRule(element=qb_el, kind="ef_freq", metric_key="f0",
     field="ef_freq")` registered under `"ef_freq"` kind.

6. **Focused tests (`tests/test_transition_spectroscopy.py`)**
   - 17 tests covering: `ElementFrequencies.ef_freq` model, transition
     routing map, `FrequencyRule` for EF, `default_patch_rules` registration,
     and canonical naming defaults.

**Files affected:**

- `qubox_v2/calibration/models.py`
- `qubox_v2/calibration/patch_rules.py`
- `qubox_v2/experiments/spectroscopy/qubit.py`
- `tests/test_transition_spectroscopy.py` (new)
- `qubox_v2/docs/CHANGELOG.md`

---

### 2026-02-26 — Binding-Driven API Redesign (v2.0.0)

**Classification: Major**

Complete architectural refactor replacing implicit element-name coupling
with explicit binding objects throughout the codebase.  This is a
**breaking change** that affects calibration storage, measurement macros,
program builders, sequence macros, and session management.

**What broke:**

- `CalibrationData` schema bumped from v4.0.0 to v5.0.0.  All per-element
  dicts now key by physical channel ID (`ChannelRef.canonical_id`) instead
  of element name strings.  An `alias_index` field provides backward
  compatibility for legacy access patterns.
- `PulseRegistry._RESERVED_OPS` no longer includes `"readout"`.  The
  wildcard `"*"` element-ops mapping no longer auto-registers a `"readout"`
  operation on every element.
- Program builder functions' element-name parameters changed from
  hardcoded defaults (e.g. `qb_el="qubit"`) to `None` with runtime
  resolution from `bindings` when provided.
- `sequence.py` macro defaults similarly changed from hardcoded strings
  to `None` + conditional resolution.

**Migration path:**

1. **Existing code** continues to work unchanged -- all old-style element
   name parameters are still accepted.  When `bindings=None` (the default),
   functions fall back to the original string defaults.
2. **New code** should pass `bindings=session.bindings` to experiments and
   program builders.  Element names are derived from bindings at call time.
3. **Calibration data** is auto-migrated from v4 to v5 on load.  Legacy
   element-name keys continue to resolve through `alias_index`.

**Compatibility shims:**

- `measureMacro` singleton remains fully functional -- existing callsites
  are unaffected.
- `cQED_attributes.ro_el` / `qb_el` / `st_el` remain stored and usable.
  A new `.to_bindings(hw)` method bridges to the binding-driven API.
- `CalibrationStore` accessors accept both physical channel IDs and legacy
  element names transparently via dual-lookup.

**Summary:**

1. **New module: `core/bindings.py`** -- ChannelRef, OutputBinding,
   InputBinding, ReadoutBinding, ExperimentBindings, ConfigBuilder,
   bindings_from_hardware_config(), build_alias_map(), validate_binding().

2. **CalibrationStore updates** -- v5.0.0 schema, alias_index, dual-lookup
   accessors, register_alias(), auto-migration v3->v4->v5.

3. **`measure_with_binding()` free function** -- binding-based drop-in
   replacement for measureMacro.measure().

4. **Session + ExperimentBase** -- .bindings property, invalidate_bindings(),
   auto alias registration.

5. **Preflight** -- bindings validation check #8.

6. **PulseRegistry** -- _RESERVED_OPS cleared, wildcard readout removed.

7. **cQED_attributes** -- to_bindings(hw) method.

8. **ReadoutConfig** -- from_binding(ro) factory.

9. **CalibrationOrchestrator** -- post-patch ReadoutBinding sync.

10. **Program builders + sequence macros** -- optional bindings parameter,
    element-name defaults changed to None + conditional resolution.

**Files affected:**

- `qubox_v2/core/bindings.py` (new)
- `qubox_v2/core/preflight.py`
- `qubox_v2/calibration/models.py`
- `qubox_v2/calibration/store.py`
- `qubox_v2/calibration/orchestrator.py`
- `qubox_v2/programs/macros/measure.py`
- `qubox_v2/programs/macros/sequence.py`
- `qubox_v2/programs/builders/*.py`
- `qubox_v2/experiments/session.py`
- `qubox_v2/experiments/experiment_base.py`
- `qubox_v2/experiments/calibration/readout_config.py`
- `qubox_v2/analysis/cQED_attributes.py`
- `qubox_v2/pulses/pulse_registry.py`
- `qubox_v2/docs/CHANGELOG.md`
- `qubox_v2/docs/API_REFERENCE.md`
- `docs/api_refactor_output_binding_report.md`

---

### 2026-02-27 — CRIT-02, HIGH-04, HIGH-05 Bug Fixes (v2.3.2)

**Classification: Minor**

Fixed three remaining issues from the code survey:

1. **CRIT-02 — Safe threshold access in QUA program builders**
   - `programs/builders/readout.py` line 668 and `programs/builders/simulation.py`
     line 34 used bare `_ro_disc_params["threshold"]` subscript access.
     When `threshold` is `None` (uncalibrated default), this silently passed
     `None` to downstream QUA operations, producing semantically incorrect
     programs.
   - Changed both to `_ro_disc_params.get("threshold") or 0.0` so
     uncalibrated sessions fall back to a zero threshold rather than `None`.

2. **HIGH-04 — `sync_ok` initialized before conditional block**
   - In `calibration/orchestrator.py` `apply_patch()`, `sync_ok` was only
     assigned inside the `if not dry_run:` block, making the return expression
     `sync_ok if not dry_run else True` fragile for static analysis and future
     refactoring.
   - Added `sync_ok = True` immediately after `preview` initialization so the
     variable is always bound regardless of `dry_run`.

3. **HIGH-05 — Removed misleading `BUGFIX` comment in `load_exp_config`**
   - `experiments/legacy_experiment.py` had a self-annotated
     `# BUGFIX: this should write *builder* to disk, not assign the classmethod result.`
     comment on a line that was already correct. Removed the stale comment.

4. **Tests for CRIT-02**
   - Added three tests to `tests/test_calibration_fixes.py`:
     `test_readout_builder_uses_safe_threshold_access`,
     `test_simulation_builder_uses_safe_threshold_access`,
     `test_measure_macro_threshold_none_safe_default`.

**Files affected:**

- `qubox_v2/programs/builders/readout.py`
- `qubox_v2/programs/builders/simulation.py`
- `qubox_v2/calibration/orchestrator.py`
- `qubox_v2/experiments/legacy_experiment.py`
- `qubox_v2/tests/test_calibration_fixes.py`
- `docs/CHANGELOG.md` — This entry
