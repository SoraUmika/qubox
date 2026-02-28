# Legacy Backward-Compatibility Audit — qubox_v2

**Date:** 2026-02-28  
**Scope:** All source files under `qubox_v2/`, top-level `notebooks/`, `tools/`, and `qubox_legacy/`  
**Methodology:** Read-only static analysis. No source files were modified.  
**Analyst:** GitHub Copilot — automated code review + manual pattern matching  

---

## 1. Executive Summary

`qubox_v2` is a well-structured, actively-refactored experiment orchestration framework for
circuit-QED on Quantum Machines OPX+ hardware. The API has stabilised around a set of mature
components: `SessionState`, `Artifact`/`ArtifactManager`, `CalibrationStore` (v5.0.0 schema),
`ExperimentBase` + modular experiment classes, `PulseFactory` with declarative `pulse_specs.json`,
and the `Patch/Orchestrator` pipeline.

However, a substantial compatibility layer remains — partially intentional (shim modules during
migration) and partially organic (dead-code accumulation). Based on static analysis:

| Metric | Value |
|--------|-------|
| Total Python LoC in `qubox_v2/` | **60,210** |
| Lines in explicitly-named legacy files | **~8,000** (`legacy_experiment.py` 5,214 + `gates_legacy.py` 1,923 + `compat/` ~200 + `migration/pulses_converter.py` ~340 + `verification/legacy_parity.py` ~330) |
| Additional compatibility code in otherwise-modern files | **~600** |
| **Total estimated legacy-attributable LoC** | **~8,600 (~14% of codebase)** |

### High-level Risk Assessment

| Risk Level | Count | Description |
|------------|-------|-------------|
| 🟢 Safe to remove immediately | **6** | Isolated shim modules, migration one-shot tools |
| 🟡 Requires minor refactor | **12** | Compatibility fallbacks, deprecated arg aliases |
| 🔴 Deep architectural dependency | **3** | God-class, schema auto-migration chain, measureMacro singleton |

### Recommended Cleanup Phase Plan (Summary)

| Phase | Focus | Version Bump |
|-------|-------|-------------|
| **1** | Remove trivial compatibility wrappers & one-shot migration tools | patch/minor |
| **2** | Remove dual-schema support and legacy config paths | minor |
| **3** | Enforce strict new schema; remove god-class `cQED_Experiment` | **major** |
| **4** | Complete `measureMacro` → `ReadoutBinding` migration; remove `gates_legacy.py` | **major** |

---

## 2. Detailed Table of Legacy Code

### 2.1 Explicit Legacy / Compat Modules

| File | Class / Function | Legacy Pattern Type | Description | Removal Risk | Suggested Action |
|------|-----------------|---------------------|-------------|--------------|-----------------|
| `qubox_v2/compat/__init__.py` | `_LegacyFinder`, `_REDIRECTS` | Import shim / backward-compat redirects | 70+ `qubox.*` → `qubox_v2.*` import redirects via `MetaPathFinder`. Active only when `import qubox_v2.compat.legacy` is called. | 🟢 | Remove once all notebooks are ported to `qubox_v2.*` imports. Guard with a `FutureWarning` window first. |
| `qubox_v2/compat/legacy.py` | module | Import shim activation | Single-line activator: `from . import _finder`. Exists purely so `import qubox_v2.compat.legacy` works. | 🟢 | Remove with `compat/__init__.py`. |
| `qubox_v2/experiments/legacy_experiment.py` | `cQED_Experiment` (5,214 lines) | Legacy god-class | Monolithic experiment class with 100+ methods, pre-refactor wiring of hardware/pulses/devices. Still imported by notebooks. Duplicates `ExperimentBase` subclasses for every physics domain. | 🔴 | Formal deprecation warning in `__init__()`. Port remaining unique methods to `ExperimentBase` subclasses. Remove in v3.0.0. |
| `qubox_v2/experiments/gates_legacy.py` | `Gate`, `QubitRotation`, `SNAP`, `Displacement`, `SQR`, `Measure` (1,923 lines) | Legacy gate/channel classes | Complete reimplementation of gate primitives from before the `ExperimentBase` + `PulseFactory` era. Still used by `programs/builders/cavity.py` and `programs/builders/simulation.py`. | 🔴 | Migrate `cavity.py` and `simulation.py` imports to `qubox_v2.gates.*`. Remove file in Phase 4. |
| `qubox_v2/migration/pulses_converter.py` | `convert()`, `main()` | One-shot migration tool | CLI + API for converting legacy `pulses.json` waveform arrays to declarative `pulse_specs.json`. Intended as a one-time migration aid. | 🟢 | Archive (move to `tools/` or a standalone script). Remove from core package once all configs are migrated. |
| `qubox_v2/migration/strip_raw_artifacts.py` | `sanitize_json_file()`, `sanitize_tree()` | One-shot migration tool | Strips shot-level raw arrays from persisted JSON artifacts. One-time data cleanup utility. | 🟢 | Archive to `tools/`. Remove from core package. |
| `qubox_v2/verification/legacy_parity.py` | `run_parity_check()`, `extract_legacy_waveforms()`, `compare_waveforms()` | Legacy parity harness | Automated regression harness comparing `PulseFactory` (v2) output against legacy `pulses.json` waveforms. Useful during migration only. | 🟢 | Remove once all experiments are confirmed to use `pulse_specs.json`. Retain golden-reference regression in `waveform_regression.py`. |
| `qubox_v2/programs/cQED_programs.py` | module | Backward-compat re-export shim | Wildcard-re-exports all `builders/*` submodules so that `from ...programs import cQED_programs` continues to work. | 🟢 | Remove after updating all internal and notebook imports to `qubox_v2.programs.builders.*`. |

---

### 2.2 Dual Code Paths — Old vs New Flows

| File | Function / Class | Legacy Pattern Type | Description | Removal Risk | Suggested Action |
|------|-----------------|---------------------|-------------|--------------|-----------------|
| `qubox_v2/calibration/store.py` | `_load_or_create()` lines 106–120 | Schema auto-migration chain | Auto-migrates calibration JSON v3.0.0 → v4.0.0 → v5.0.0 **in memory** on every load. Includes `device_id` → `sample_id` remap in context block. | 🟡 | After confirmed migration of all `calibration.json` files to v5.0.0, remove the v3/v4 migration branches. Add hard error if `version < "5.0.0"` is detected instead. |
| `qubox_v2/calibration/store.py` | `_normalize_coherence_units()` | Unit normalisation shim | Detects legacy coherence values stored in nanoseconds and converts them to seconds on load. Also triggered by unit mismatch between `T2_ramsey` and `T2_star_us`. | 🟡 | Fix `T2RamseyRule` / `T2EchoRule` to write seconds directly (see `qubox_v2_code_survey.md` HIGH-02). After unit-correct patch rules are in place, remove this shim. |
| `qubox_v2/calibration/store.py` | `_migrate_pulse_cal_keys()` | Naming migration on load | Renames bare pulse keys (`x180`, `ref_r180`) to canonical `ge_*` names in the raw JSON dict before Pydantic validation. Runs on every load. | 🟡 | After all `calibration.json` files are saved with canonical keys (which happens on the next `CalibrationStore.save()` call), this migration is a no-op and can be removed. |
| `qubox_v2/calibration/store.py` | `_validate_context()` lines 515–522 | Legacy v3 context skip | Skips context validation with a warning for calibration files that have no `context` block ("legacy v3 file"). | 🟡 | Remove the skip once all files are confirmed at v5.0.0. Convert the guard into a hard error. |
| `qubox_v2/devices/sample_registry.py` | `__init__()` lines 91–96 | Dual directory layout | Falls back to `devices/` directory when `samples/` is not found, with a deprecation warning. Also accepts `device.json` alongside `sample.json` for per-sample metadata. | 🟡 | Run `tools/migrate_device_to_samples.py` on all lab setups. Remove `devices/` fallback and `device.json` compatibility after confirmed migration. |
| `qubox_v2/devices/sample_registry.py` | `SampleInfo.from_dict()` line 71 | Field name alias | `d.get("sample_id", d.get("device_id", ""))` — reads `device_id` as fallback when `sample_id` is absent. | 🟡 | Remove `device_id` fallback once all `sample.json` / `device.json` files are updated. |
| `qubox_v2/experiments/session.py` | `SessionManager.__init__()` lines 55, 135–136 | Legacy (path-only) mode | When `sample_id` is not provided, `SessionManager` operates in "legacy mode" using a raw `experiment_path`. Context validation, schema checks, and registry lookups are skipped. | 🟡 | Deprecate `experiment_path`-only construction. Require `sample_id + cooldown_id` or a resolved `ExperimentContext`. Issue `DeprecationWarning` in Phase 2. |
| `qubox_v2/experiments/session.py` | `_get_cqed_param()` lines 569–596 | Dual config fallback | Two-step attribute lookup: new `cqed_params.json` fields first, then deprecated fields with a warning. `cqed_params.json` itself is marked as a backward-compat source of truth. | 🟡 | After `ExperimentBindings` adoption is complete, remove `cqed_params.json` fallback entirely. |
| `qubox_v2/pulses/factory.py` lines 9–10 | module docstring | Dual pulse loading comment | Documents that `PulseOperationManager` (legacy `pulses.json`) continues to work alongside the new `PulseFactory` (`pulse_specs.json`). | 🟡 | Remove note when `PulseOperationManager` is retired. |
| `qubox_v2/core/schemas.py` | `_SCHEMA_DEFS["calibration"]` | Dual schema version support | Accepts both `"3.0.0"` and `"4.0.0"` as valid calibration schema versions, in addition to the current `"5.0.0"`. | 🟡 | Remove `"3.0.0"` and `"4.0.0"` from the supported list after confirmed migration. The `CalibrationStore` auto-migration already handles the upgrade path. |
| `qubox_v2/analysis/post_process.py` | `proc_default_legacy()` | Legacy default processor | Old default post-processing function retained alongside the new multi-target version. Referenced by name in legacy experiment notebooks. | 🟡 | Mark as deprecated. Remove when notebook migration is complete. |

---

### 2.3 Deprecated Naming Still Supported

| File | Location | Legacy Pattern Type | Description | Removal Risk | Suggested Action |
|------|----------|---------------------|-------------|--------------|-----------------|
| `qubox_v2/calibration/transitions.py` | `_LEGACY_ALIASES` dict | Legacy pulse name aliases | Maps 9 bare names (`x180`, `ref_r180`, `sel_ref_r180`, etc.) to canonical `ge_*` equivalents. `resolve_pulse_name()` transparently upgrades old names. | 🟡 | Keep the resolver function but remove the `_LEGACY_ALIASES` dict entries once all stored calibration files use canonical names. Aliases are safe to remove after Phase 3. |
| `qubox_v2/analysis/cQED_attributes.py` | `r180_amp`, `rlen`, `rsigma` (lines 66–68) | Legacy bare pulse fields | Three dataclass fields that duplicate `ge_r180_amp`, `ge_rlen`, `ge_rsigma`. Promoted to canonical fields in `__post_init__`. Present in legacy `cqed_params.json` files. | 🟡 | Remove bare fields after all `cqed_params.json` files are updated to use `ge_*` prefixes. |
| `qubox_v2/analysis/cQED_attributes.py` | `_DEPRECATED_WORKFLOW_FIELDS` + `from_json()` | Deprecated workflow fields | `ro_therm_clks`, `qb_therm_clks`, `st_therm_clks`, `b_coherent_amp`, `b_coherent_len`, `b_alpha` — loaded with a `DeprecationWarning`. These are now session/calibration-level configs. | 🟡 | Remove from `cQED_attributes` dataclass and the `from_json` warning logic. Move them fully to `CalibrationStore` after confirming no active notebooks depend on them. |
| `qubox_v2/experiments/calibration/readout_config.py` | `ReadoutConfig.weight_extraction_method` (line 134), `threshold_extraction` (line 136) | Legacy method name defaults | Default values `"legacy_ge_diff_norm"` and `"legacy_discriminator"` are named after old code paths. Validation (lines 171–181) **only accepts** these exact strings — the new API has no alternative values yet. | 🔴 | Define new method names (e.g., `"ge_diff_norm"`, `"optimal_discriminator"`). Implement new logic. Accept old names with a warning for one release cycle, then remove. |
| `qubox_v2/experiments/calibration/readout.py` | `legacy_update_measure`, `legacy_k`, `legacy_k_g`, `legacy_k_e` kwargs (lines 425–444) | Deprecated keyword aliases | Old keyword argument names for the `ReadoutGEDiscrimination.run()` call interface. Pop them from `**kwargs` and silently map to new parameters. | 🟢 | Remove after confirming no caller uses these names. Add a one-release `DeprecationWarning` if uncertain. |
| `qubox_v2/tools/waveforms.py` | `delta` parameter (lines 33, 115, 122, 207, 214, 282) | Deprecated parameter alias | `delta` accepted as a synonym for `anharmonicity` in `drag_gaussian_pulse_waveforms()`, `drag_cosine_pulse_waveforms()`. Prints a console message (not a formal `DeprecationWarning`). | 🟢 | Replace `print()` with `warnings.warn(..., DeprecationWarning)`. Remove `delta` support in Phase 1 with a single-release warning period. |
| `qubox_v2/core/config.py` | `QuboxExtras.normalize_lo_map()` (lines 109–115) | Legacy JSON format | `external_lo_map` accepts both legacy string format (bare device name) and new dict format `{"device": ..., "lo_port": ...}`. | 🟡 | Enforce dict-only format. Remove string fallback after updating all `hardware.json` files. |
| `qubox_v2/programs/builders/spectroscopy.py` | `depletion_len` parameter (lines 71, 121) | Deprecated parameter | `depletion_len` is accepted but raises `ValueError` if it disagrees with `depletion_clks`. This is a dead-on-conflict check — effectively unused but not removed. | 🟢 | Remove `depletion_len` parameter entirely. Only `depletion_clks` is correct. |

---

### 2.4 Legacy Schema Translators / Data Patchers

| File | Function / Class | Legacy Pattern Type | Description | Removal Risk | Suggested Action |
|------|-----------------|---------------------|-------------|--------------|-----------------|
| `qubox_v2/calibration/store.py` | `_normalize_coherence_units()` | Schema patcher — units | Detects and fixes coherence values stored in ns (legacy) by converting to seconds on reload. Called from `__init__()` every time the store is opened. | 🟡 | Remove once `T2RamseyRule` / `T2EchoRule` are fixed to write seconds, and all `calibration.json` files have been re-saved. |
| `qubox_v2/calibration/store.py` | `_migrate_pulse_cal_keys()` | Schema patcher — key names | Renames bare pulse-calibration keys (`x180` → `ge_x180`) in raw JSON before Pydantic validation. Runs on every load. | 🟡 | Remove once all files are stored with canonical keys. |
| `qubox_v2/core/schemas.py` | `_migrate_calibration_3_to_4()` + `register_migration("calibration", 4, ...)` | Schema migration function | Registered migration step for calibration schema v3 → v4. Used by `migrate_file()` and the `CalibrationStore` auto-migration. | 🟡 | Remove after all files are at v5.0.0 and v3/v4 support is dropped from `_SCHEMA_DEFS`. |
| `qubox_v2/devices/context_resolver.py` | `resolve_legacy()` | Legacy context resolution | Builds a minimal `ExperimentContext` from a bare directory (no sample registry). Sets `cooldown_id="legacy"` and `schema_version="4.0.0"`. | 🟡 | Remove once all experiments are registered in the `SampleRegistry`. Keep as a helper for one-off forensic use if needed (move to `tools/`). |

---

### 2.5 Notebook Compatibility Glue

| File | Description | Legacy Pattern Type | Removal Risk | Suggested Action |
|------|-------------|---------------------|--------------|-----------------|
| `notebooks/post_cavity_experiment_legacy.ipynb` | Notebook using old flat `qubox.*` imports and `cQED_Experiment` directly. | Legacy import style + god-class usage | 🟡 | Port to `qubox_v2.*` imports + `ExperimentBase` subclasses. Archive the `_legacy` version. |
| `notebooks/post_cavity_experiment_context.ipynb` | Notebook bridging context-mode session startup with auto-detection of legacy calibration storage. Contains logic to detect whether `calibration.json` is at v3 or v4. | Auto-detection of legacy calibration storage | 🟡 | Remove version-detection logic once all calibration files are at v5.0.0. |
| `tools/migrate_device_to_samples.py` | CLI script to rename `devices/` → `samples/` directory tree in an experiment setup. | One-shot migration tool | 🟢 | Run once per lab setup. Move to `docs/migration_guides/` as a reference script; remove from active `tools/`. |
| `tools/build_context_notebook.py` | Helper to auto-generate a notebook context block. References legacy path layout. | Migration helper | 🟡 | Update to use the new `SampleRegistry` + `ContextResolver` path after migration. |

---

## 3. Dependency Impact Analysis

### 3.1 Which Modules Depend on Legacy Paths?

```
qubox_v2/compat/__init__.py
  ← notebooks/post_cavity_experiment_legacy.ipynb  (via `import qubox.…`)
  ← Any legacy notebook or script using flat `qubox.*` imports

qubox_v2/experiments/legacy_experiment.py  (cQED_Experiment)
  ← notebooks/post_cavity_experiment_legacy.ipynb
  ← notebooks/post_cavity_experiment_context.ipynb (partial use)
  ← qubox_v2/experiments/__init__.py  (re-exports cQED_Experiment)

qubox_v2/experiments/gates_legacy.py
  ← qubox_v2/programs/builders/cavity.py      (Gate base class)
  ← qubox_v2/programs/builders/simulation.py  (Gate, Measure)
  ← qubox_v2/tools/generators.py              (waveform math reference)

qubox_v2/programs/cQED_programs.py
  ← qubox_v2/compat/__init__.py  (redirect target for qubox.cQED_programs)
  ← legacy notebooks using `from qubox_v2.programs import cQED_programs`

qubox_v2/analysis/post_process.py::proc_default_legacy
  ← legacy_experiment.py  (called in output pipeline)
  ← legacy notebooks

qubox_v2/calibration/transitions.py::_LEGACY_ALIASES
  ← qubox_v2/calibration/store.py::get_pulse_calibration()
  ← qubox_v2/calibration/store.py::set_pulse_calibration()
  ← qubox_v2/calibration/patch_rules.py  (PiAmpRule, DragAlphaRule, PulseTrainRule)

qubox_v2/analysis/cQED_attributes.py  (legacy bare fields)
  ← qubox_v2/experiments/legacy_experiment.py
  ← qubox_v2/experiments/base.py
  ← qubox_v2/experiments/session.py
  ← Anywhere cqed_params.json is loaded

qubox_v2/core/schemas.py (v3/v4 schema versions)
  ← qubox_v2/calibration/store.py::_load_or_create()
  ← qubox_v2/verification/schema_checks.py
```

### 3.2 Which Experiments Would Break?

| Legacy Component Removed | Experiments / Workflows Broken |
|--------------------------|-------------------------------|
| `compat/__init__.py` | All notebooks using `import qubox.…` flat imports |
| `legacy_experiment.py` | All workflows using `cQED_Experiment` directly; legacy notebooks |
| `gates_legacy.py` | `CavityFockExperiment`, `StorageSpectroscopy`, and any cavity/simulation QUA programs using `Gate` base class |
| `proc_default_legacy()` | Legacy output pipelines in `cQED_Experiment` methods |
| `_LEGACY_ALIASES` in `transitions.py` | Any `CalibrationStore` access using bare pulse names (`x180`, `ref_r180`) |
| `devices/` fallback in `sample_registry.py` | Lab setups that have not yet run `migrate_device_to_samples.py` |
| `cqed_params.json` deprecated fields | Sessions relying on `ro_therm_clks`, `b_coherent_amp`, etc. from `cqed_params.json` |

### 3.3 Which Calibration Pipelines Rely on Compatibility Layers?

| Pipeline | Compatibility Layer Used | Notes |
|----------|--------------------------|-------|
| T1 / T2 Ramsey / T2 Echo | `_normalize_coherence_units()` in `CalibrationStore` | Corrects unit mismatch (ns vs s) on reload. Will silently accept wrong values until the shim runs. |
| Any pulse calibration lookup | `_migrate_pulse_cal_keys()` + `_LEGACY_ALIASES` | Old calibration files using bare names (`x180`) rely on both for transparent access. |
| Session startup | `_load_or_create()` v3→v4→v5 migration chain | Old `calibration.json` files must pass through this migration on every open. |
| Readout discrimination | `legacy_ge_diff_norm` / `legacy_discriminator` default values in `ReadoutConfig` | These are the **only** accepted extraction method names — no new-API alternative exists yet. |
| Readout opt. kwargs | `legacy_k`, `legacy_k_g`, `legacy_k_e`, `legacy_update_measure` | Absorbed silently from `**kwargs` — no error raised if unused. |
| Resonator spectroscopy | `resolve_legacy()` in `ContextResolver` | Used when no `SampleRegistry` is configured. |

---

## 4. Recommended Removal Plan

### Phase 1 — Remove Trivial Compatibility Wrappers  
**Target: patch/minor version (e.g., v2.2.0)**  
*Low risk; isolated modules with no deep dependencies.*

1. **`qubox_v2/migration/pulses_converter.py`** — Archive to `tools/` (standalone CLI script). Remove from `qubox_v2` package. Confirm all `pulses.json` → `pulse_specs.json` conversions are complete.  
2. **`qubox_v2/migration/strip_raw_artifacts.py`** — Archive to `tools/`. Remove from package.  
3. **`qubox_v2/verification/legacy_parity.py`** — Remove. Replace with `waveform_regression.py` golden-reference checks only.  
4. **`tools/migrate_device_to_samples.py`** — Move to `docs/migration_guides/` as a reference script.  
5. **`qubox_v2/tools/waveforms.py` `delta` parameter** — Replace `print()` with `warnings.warn(..., DeprecationWarning, stacklevel=2)`. Remove `delta` support in the next minor release.  
6. **`programs/builders/spectroscopy.py` `depletion_len`** — Remove parameter. Keep only `depletion_clks`.  
7. **`experiments/calibration/readout.py` legacy kwargs** — Remove `legacy_update_measure`, `legacy_k`, `legacy_k_g`, `legacy_k_e` from `**kwargs` extraction. (Add a one-release `DeprecationWarning` if any lab uses these.)  

**Deliverable:** `CHANGELOG.md` entry marking these items as removed. No API breakage for code using `qubox_v2.*` directly.

---

### Phase 2 — Remove Dual-Schema Support  
**Target: minor version (e.g., v2.3.0) after all lab setups migrated**  
*Requires: all `calibration.json` files at v5.0.0; all lab directories renamed to `samples/`.*

1. **`CalibrationStore._load_or_create()`** — Remove v3.0.0 → v4.0.0 and v4.0.0 → v5.0.0 in-memory migration branches. Add a hard `ValueError` if `version < "5.0.0"` is detected. Document migration path in error message.  
2. **`CalibrationStore._normalize_coherence_units()`** — Remove after `T2RamseyRule` / `T2EchoRule` are fixed to write seconds directly (apply HIGH-02 fix first).  
3. **`CalibrationStore._migrate_pulse_cal_keys()`** — Remove. All stored files will have canonical keys after the next save cycle.  
4. **`CalibrationStore._validate_context()` legacy v3 skip** — Convert to hard error: if no `context` block is present, raise `ContextMismatchError` instead of logging a warning.  
5. **`core/schemas.py`** — Remove `"3.0.0"` and `"4.0.0"` from `_SCHEMA_DEFS["calibration"]` supported list. Remove `_migrate_calibration_3_to_4()`.  
6. **`devices/sample_registry.py`** — Remove `devices/` directory fallback and `device.json` fallback (lines 91–96, 116, 127, 132–136). Remove `device_id` fallback in `SampleInfo.from_dict()`.  
7. **`core/config.py` `normalize_lo_map()`** — Remove string format acceptance. Require dict format only.  
8. **`devices/context_resolver.py` `resolve_legacy()`** — Remove. Move to `tools/` if forensic use is anticipated.  
9. **`transitions.py` `_LEGACY_ALIASES`** — Remove all 9 entries. Keep `resolve_pulse_name()` function but remove the alias branch. Code that passes bare names will receive them unchanged (passthrough).  
10. **`analysis/cQED_attributes.py` bare fields** — Remove `r180_amp`, `rlen`, `rsigma` fields and the `__post_init__` promotion logic.  
11. **`analysis/cQED_attributes.py` deprecated workflow fields** — Remove `_DEPRECATED_WORKFLOW_FIELDS` entries from the dataclass and the `from_json()` warning logic.  
12. **`experiments/session.py` `experiment_path`-only mode** — Add `DeprecationWarning`. In Phase 3, require `sample_id + cooldown_id`.  

**Deliverable:** Schema freeze announcement. All serialised files must be at v5.0.0.

---

### Phase 3 — Enforce Strict New Schema; Begin God-Class Deprecation  
**Target: major version bump — v3.0.0**  
*Breaking change: `cQED_Experiment` is removed. All code must use `ExperimentBase` subclasses.*

1. **`experiments/legacy_experiment.py`** — Add `DeprecationWarning` to `cQED_Experiment.__init__()` in v2.x. Remove the entire file in v3.0.0.  
2. **`experiments/__init__.py`** — Remove `cQED_Experiment` from re-exports.  
3. **Port remaining unique methods** — Audit all 100+ `cQED_Experiment` methods; port any not yet covered by `ExperimentBase` subclasses (spectroscopy, cavity, SPA experiments).  
4. **`programs/cQED_programs.py`** — Remove the wildcard-import shim. All code should import from `qubox_v2.programs.builders.*` directly.  
5. **`analysis/post_process.py` `proc_default_legacy()`** — Remove. All call sites should use the new multi-target version.  
6. **`compat/__init__.py` + `compat/legacy.py`** — Remove the entire `compat/` package. All notebooks must use `qubox_v2.*` imports.  
7. **`experiments/session.py` path-only mode** — Remove `experiment_path`-only construction entirely. Require `sample_id + cooldown_id`.  
8. **`ReadoutConfig.weight_extraction_method` / `threshold_extraction`** — Implement new method names. Accept old names with a `DeprecationWarning` for the entire v2.x life.  

**Deliverable:** v3.0.0 release notes listing all removed APIs. Migration guide document.

---

### Phase 4 — Complete `measureMacro` → `ReadoutBinding` Migration; Remove `gates_legacy.py`  
**Target: major version (v3.1.0 or v4.0.0)**  
*Completes the architectural modernisation.*

1. **`measureMacro` singleton** — Move all class-level attributes to instance-level `__init__`. Store the instance on `SessionManager`. Expose via `ExperimentBase.measure_macro` property. Deprecate direct class-attribute access.  
2. **`gates_legacy.py`** — Migrate all consumers (`programs/builders/cavity.py`, `programs/builders/simulation.py`) to use `qubox_v2.gates.*` hierarchy. Remove `gates_legacy.py`.  
3. **`ReadoutConfig` legacy method names** — Remove `"legacy_ge_diff_norm"` and `"legacy_discriminator"` after new implementations land.  
4. **`cqed_params.json` dependency** — Complete `ExperimentBindings` migration. Remove `cqed_params.json` fallback from `SessionManager._get_cqed_param()`.  
5. **`qubox_legacy/` directory** — Archive to a separate branch or remove entirely from the repo. No `qubox_v2` code imports from it.  

**Deliverable:** Architecture diagram updated. `qubox_legacy/` tagged and archived. v4.0.0 release.

---

## 5. Metrics

### 5.1 Legacy Reference Counts (by file)

| File | Legacy/Compat References |
|------|--------------------------|
| `experiments/legacy_experiment.py` | entire file (~5,214 lines) |
| `experiments/gates_legacy.py` | entire file (~1,923 lines) |
| `experiments/calibration/readout.py` | 25 references |
| `calibration/store.py` | 15 references |
| `analysis/cQED_attributes.py` | 10 references |
| `experiments/session.py` | 9 references |
| `compat/__init__.py` | entire file (~130 lines) |
| `calibration/transitions.py` | 8 references |
| `programs/macros/measure.py` | 7 references |
| `experiments/calibration/readout_config.py` | 6 references |
| `devices/sample_registry.py` | 5 references |
| `tools/waveforms.py` | 5 references |
| `analysis/post_process.py` | 4 references |
| `programs/builders/tomography.py` | 4 references |
| `core/schemas.py` | 4 references |
| Other files (1–3 each) | ~30 references |
| **Total** | **~385 references across ~60 files** |

### 5.2 LoC Attributable to Compatibility

| Category | LoC |
|----------|-----|
| `experiments/legacy_experiment.py` | 5,214 |
| `experiments/gates_legacy.py` | 1,923 |
| `compat/` module | ~200 |
| `migration/` module | ~500 |
| `verification/legacy_parity.py` | ~330 |
| Inline compat code (all other files) | ~600 |
| **Total** | **~8,767 (~14.6% of 60,210 LoC)** |

### 5.3 Most Affected Modules

| Module | Legacy Dependency Level |
|--------|------------------------|
| `experiments/` | ⬛⬛⬛⬛⬛ Very High — hosts god-class and two legacy files |
| `calibration/` | ⬛⬛⬛⬛ High — store/schema migration chain, legacy aliases |
| `programs/` | ⬛⬛⬛ Medium — cQED_programs shim, gates_legacy dependency |
| `analysis/` | ⬛⬛⬛ Medium — cQED_attributes bare fields, proc_default_legacy |
| `devices/` | ⬛⬛ Low-Medium — device.json / devices/ fallbacks |
| `core/` | ⬛⬛ Low-Medium — schema version support for v3/v4 |
| `tools/` | ⬛ Low — waveform `delta` alias |
| `compile/` | ✅ None — no legacy compatibility code |
| `gates/` | ✅ None — no legacy compatibility code |
| `optimization/` | ✅ None — no legacy compatibility code |
| `simulation/` | ✅ None — no legacy compatibility code |
| `hardware/` | ✅ Minimal — one format fallback in `config_engine.py` |

---

*Report generated by read-only static analysis of all Python source files under `qubox_v2/`, top-level notebooks, and tools. No source files were modified.*
