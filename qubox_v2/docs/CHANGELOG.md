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
