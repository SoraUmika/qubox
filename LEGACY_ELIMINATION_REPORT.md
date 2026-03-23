# Legacy Code Elimination Report

**Date:** 2026-03-22 (migration), 2026-03-23 (deletion + final verification)  
**Scope:** Merge `qubox/legacy/` (~150 Python files) into `qubox/` so the repository has a single canonical implementation.  
**Status:** **COMPLETE** — all code merged, all imports updated, 26/26 experiments compile, legacy directory deleted.

---

## 1. Summary

The `qubox.legacy` subpackage (`qubox_v2_legacy v2.0.0`) contained the active working runtime: experiments, hardware control, pulse management, calibration, compilation, simulation, etc. The main `qubox` package (v3.0.0) provided a thin high-level API that delegated to `qubox.legacy` at runtime.

This migration:
- **Moved** 11 non-conflicting directories up one level (from `qubox/legacy/X/` to `qubox/X/`).
- **Merged** 5 conflicting subpackages (`core/`, `experiments/`, `analysis/`, `devices/`, `calibration/`) by combining files and resolving symbol conflicts.
- **Updated** all 22 external Python files that referenced `qubox.legacy.*`.
- **Rewrote** the compatibility layer (`qubox/compat/notebook.py`) — replaced lazy proxy with direct imports.
- **Verified** 20/20 import checks pass and 26/26 QUA programs compile.
- **Deleted** `qubox/legacy/` directory and cleared all `__pycache__` directories.
- **Re-verified** all imports and compilation after deletion — 20/20 pass, 26/26 compile.

---

## 2. What Was Moved

### 2a. Non-Conflicting Directories (direct copy)

These directories existed only in `legacy/` and were copied to `qubox/`:

| Directory | Contents |
|-----------|----------|
| `hardware/` | OPX/Octave controller, config_engine, program runner |
| `pulses/` | Pulse manager, factory, definitions |
| `programs/` | QUA program builders, macros (measure, utility), spectroscopy |
| `gates/` | Gate definitions, fidelity, hardware gates (displacement, SNAP, SQR) |
| `compile/` | Compilation API, evaluators, GPU accelerators, structure search |
| `simulation/` | Simulation backends |
| `verification/` | Waveform regression testing |
| `autotune/` | Automated calibration tuning workflows |
| `optimization/` | Optimization algorithms |
| `migration/` | Internal migration utilities |
| `gui/` | GUI components |

### 2b. Unique Files Copied Into Existing Subpackages

**`core/`** (14 files):
- `artifacts.py`, `artifact_manager.py`, `bindings.py`, `config.py`, `experiment_context.py`
- `hardware_definition.py`, `logging.py`, `measurement_config.py`, `persistence_policy.py`
- `preflight.py`, `protocols.py`, `schemas.py`, `session_state.py`, `utils.py`

**`experiments/`** (7 top-level files + 6 subdirectories):
- Files: `experiment_base.py`, `experiment_registry.py`, `execution_runner.py`, `parameter_resolution.py`, `protocol_templates.py`, `result.py`, `session.py`
- Subdirs: `calibration/`, `cavity/`, `spa/`, `spectroscopy/`, `time_domain/`, `tomography/`

**`analysis/`** (15 files): `cQED_attributes.py` plus 14 re-export wrappers from `qubox_tools`

**`devices/`** (3 files): `context_resolver.py`, `device_manager.py`, `sample_registry.py`

**`calibration/`** (3 files): `algorithms.py`, `mixer_calibration.py`, `pulse_train_tomo.py`

**Support directories**: `tests/` (5 test files), `docs/` (3 markdown files), `examples/` (2 example scripts)

---

## 3. Conflict Resolutions

### 3a. `core/errors.py`

Both v3 and legacy defined error hierarchies rooted in `QuboxError`.

| Aspect | v3 | Legacy | Resolution |
|--------|----|----|------------|
| Base class | `QuboxError(Exception)` | `QuboxError(RuntimeError)` | **Kept `Exception`** (broader) |
| `ContextMismatchError` | inherited `QuboxError` | inherited `ConfigError` | **Changed to inherit `ConfigError`** (backward compat) |

### 3b. `core/types.py`

Both defined enums with overlapping names but different values.

| Enum | v3 values | Legacy values | Resolution |
|------|-----------|---------------|------------|
| `ExecMode` | HARDWARE, SIMULATION | RUN, SIMULATE, CONTINUOUS_WAVE | All combined in one enum |
| `PulseType` | CONSTANT, ARBITRARY, DRAG | CONTROL, MEASUREMENT | All combined |
| `WaveformType` | GAUSSIAN, COSINE, FLATTOP, CONSTANT, KAISER, SLEPIAN | ARBITRARY | Added ARBITRARY |
| `DemodMode` | FULL, SLICED, ACCUMULATED | MOVING_WINDOW | Added MOVING_WINDOW |
| `WeightLabel` | COSINE, SINE | COS, SIN, MINUS_SIN | All combined |

Added type aliases: `WaveformSamples`, `FrequencyHz`, `ClockCycles`, `Nanoseconds`

### 3c. `experiments/__init__.py`

v3 exported only `ExperimentLibrary` and `WorkflowLibrary`. Legacy had 60+ experiment classes across 6 subdirectories. Resolution: export both APIs — `ExperimentLibrary` plus all individual experiment classes.

### 3d. `analysis/__init__.py`

v3 exported `run_named_pipeline`. Legacy re-exported from `qubox_tools`. Resolution: both exported.

### 3e. `devices/__init__.py`

v3 had `SampleRegistry`, `SampleInfo`. Legacy had `DeviceManager`, `ContextResolver`. Resolution: export all, plus backward-compat aliases (`DeviceRegistry = SampleRegistry`, `DeviceInfo = SampleInfo`).

### 3f. `calibration/__init__.py`

v3 had `CalibrationStore`, `Transition`, etc. Legacy added `MixerCalibrationConfig`, `SAMeasurementHelper`. Resolution: export all. Added missing `DEFAULT_TRANSITION: Transition = Transition.GE`.

---

## 4. Import Updates

### Bulk replacement: `qubox.legacy.` → `qubox.`

22 files updated automatically:

- `qubox/autotune/run_post_cavity_autotune_v1_1.py`
- `qubox/backends/qm/lowering.py`, `runtime.py`
- `qubox/calibration/orchestrator.py`
- `qubox/compat/notebook.py`, `__init__.py`
- `qubox/compile/api.py`, `evaluators.py`, `gpu_accelerators.py`, `objectives.py`, `structure_search.py`, `templates.py`
- `qubox/experiments/workflows/library.py`
- `qubox/gates/fidelity.py`, `hardware/displacement.py`, `hardware/qubit_rotation.py`, `hardware/snap.py`, `hardware/sqr.py`
- `qubox/session/session.py`
- `qubox/tests/test_calibration_cqed_params.py`, `test_parameter_resolution_policy.py`, `test_projected_signal_analysis.py`

### `qubox/compat/notebook.py` — Complete rewrite

Removed:
- `_LEGACY_ATTR_MAP` (45-entry lazy proxy dictionary)
- `_LEGACY_MODULE_MAP` (2-entry module proxy)
- `_MIGRATED_NAMES` set
- `__getattr__` function (dynamic import resolver)
- `from importlib import import_module`

Replaced with: Direct imports from canonical `qubox.*` subpackages (experiments, calibration, programs, hardware, verification).

### `notebooks/verify_compilation.py`

Updated 4 imports from `qubox.legacy.*` to `qubox.*`:
- `qubox.legacy.experiments.session` → `qubox.experiments.session`
- `qubox.legacy.hardware.config_engine` → `qubox.hardware.config_engine`
- `qubox.legacy.pulses.manager` → `qubox.pulses.manager`
- `qubox.legacy.programs.macros.measure` → `qubox.programs.macros.measure`

---

## 5. Verification Results

### 5a. Import Verification (test_migration.py)

20 comprehensive import checks covering all migrated subpackages:

```
Results: 20 OK, 0 FAIL out of 20 checks
ALL CHECKS PASSED
```

### 5b. QUA Compilation Verification (verify_compilation.py)

29 experiments tested against new config (OPX+ + Octave hardware):

| Result | Count | Details |
|--------|-------|---------|
| **New config — compiled** | **26** | All non-skipped experiments |
| New config — failed | 0 | — |
| Legacy config — compiled | 4 | ContinuousWave, ResonatorSpectroscopy, ResonatorPowerSpectroscopy, StorageChiRamsey |
| Legacy config — failed | 22 | Expected: legacy config uses `qubit` element name vs new config `transmon` |
| Skipped | 3 | RB (batched), SPAFlux (DC-only), SPAPumpFreq (nested sub-runs) |

All 26 compilable experiments pass on the new config. Legacy config failures are **pre-existing** (element name mismatch, not a migration issue).

### 5c. Notebooks

Zero notebook cells contain `import qubox.legacy` — all 21 notebooks (07-27) import from canonical `qubox.*` paths.

---

## 6. Known Issues

1. **`qubox/gates/fidelity.py:39`**: Pre-existing `SyntaxWarning` — invalid escape sequence `\d` in docstring. Not introduced by migration.

2. **Unicode logging on Windows**: `\u2192` (→) in `hardware/controller.py` log messages causes `UnicodeEncodeError` when stdout uses CP1252. Non-blocking; only affects redirected output.

3. **`qubox/legacy/` directory deleted** (2026-03-23): Successfully removed via `shutil.rmtree()`. All 30 `__pycache__` directories cleared. Post-deletion verification: 20/20 imports pass, return code 0.

---

## 7. Architecture After Migration

```
qubox/
├── __init__.py          # v3 public API: Session, Sequence, QuantumCircuit
├── core/                # Errors, types (merged enums), config, logging, context
├── experiments/         # 60+ experiment classes + ExperimentLibrary
│   ├── calibration/     # ReadoutOptimization, DRAGCalibration, etc.
│   ├── cavity/          # StorageSpectroscopy, NumSplitting, etc.
│   ├── spa/             # SPAFlux, SPAPump optimization
│   ├── spectroscopy/    # ResonatorSpec, QubitSpec, etc.
│   ├── time_domain/     # T1, T2Ramsey, T2Echo, Rabi, etc.
│   └── tomography/      # QubitStateTomo, WignerTomo, etc.
├── hardware/            # OPX controller, config engine
├── pulses/              # Pulse manager and factory
├── programs/            # QUA program builders and macros
├── calibration/         # CalibrationStore, transitions, mixer cal
├── analysis/            # cQED attributes + qubox_tools re-exports
├── devices/             # DeviceManager, ContextResolver, SampleRegistry
├── gates/               # Gate definitions, hardware gates
├── compile/             # Compilation pipeline
├── simulation/          # Simulation backends
├── verification/        # Waveform regression
├── compat/              # notebook.py (direct imports, no proxy)
├── session/             # Session management
├── backends/            # QM backend
├── autotune/            # Auto-calibration
├── optimization/        # Optimization algorithms
└── (legacy/ deleted)    # Removed 2026-03-23
```
