# Session Attributes Removal and Calibration Resolution Audit

## Executive Summary

This refactor removes the `session.attributes` workflow from the active `SessionManager` path and replaces it with calibration-backed parameter resolution plus explicit per-call overrides.

Key changes:

- `SessionManager` no longer exposes or persists `session.attributes`; runtime lookups now flow through `context_snapshot()` plus calibration-backed helpers.
- `ExperimentBase` now centralizes parameter resolution with provenance tracking in `resolve_param()` / `resolve_override_or_attr()`.
- Representative experiments now follow the required precedence:
  1. explicit override
  2. calibration (`calibration.json` / `CalibrationStore`)
  3. explicit code default when intentionally retained
  4. clear error when required calibration is missing
- Run/build metadata now records resolved parameter values and their sources.
- Repository grep is clean for `session.attributes`, `.attributes`, `save_attributes()`, and `refresh_attribute_frequencies_from_calibration()`.

What to watch out for:

- A few experiment families still retain explicit zero-fallback thermalization waits. These no longer rely on hidden session state, but they can still bypass calibration if those paths are used without overrides.
- Some lower-level direct APIs (`CircuitRunner`, low-level builders, roleless binding defaults) still embed legacy thermalization defaults and should be hardened if those APIs are part of the supported surface.

## Inventory of Migrated Parameters

The following parameters were migrated off implicit `session.attributes` lookup and now resolve through calibration-backed utilities or `context_snapshot()`:

| Parameter | Canonical calibration path | Notes |
|---|---|---|
| `qb_therm_clks` | `cqed_params.transmon.qb_therm_clks` | Explicit override supported across representative gate/time-domain/spectroscopy/tomography experiments |
| `ro_therm_clks` | `cqed_params.resonator.ro_therm_clks` | Used by resonator/readout experiments |
| `st_therm_clks` | `cqed_params.storage.st_therm_clks` | Added to calibration schema and legacy migration |
| `qubit_freq` | `cqed_params.transmon.qubit_freq` | Used by qubit spectroscopy, Rabi, Ramsey, relaxation, etc. |
| `resonator_freq` | `cqed_params.resonator.resonator_freq` | Used by resonator spectroscopy and readout paths |
| `storage_freq` | `cqed_params.storage.storage_freq` | Added as canonical storage-frequency slot |
| `ef_freq` | `cqed_params.transmon.ef_freq` | Used by EF spectroscopy paths |
| `ro_fq` / `qb_fq` / `st_fq` legacy aliases | Derived into `context_snapshot()` from calibration | Compatibility layer only; no longer a mutable source of truth |
| active readout element/runtime readout selection | `session_runtime.json` (`active_readout_element`) | Replaces attribute mutation in `override_readout_operation()` |

## Changes Made

- Core session/runtime:
  - `qubox_v2/experiments/session.py`
  - `qubox_v2/experiments/experiment_base.py`
  - `qubox_v2/experiments/result.py`
- Calibration schema/store:
  - `qubox_v2/calibration/models.py`
  - `qubox_v2/calibration/store.py`
- Calibration/orchestration helpers:
  - `qubox_v2/calibration/orchestrator.py`
  - `qubox_v2/calibration/patch_rules.py`
- Context consumers migrated off `.attributes`:
  - `qubox_v2/core/artifacts.py`
  - `qubox_v2/core/preflight.py`
  - `qubox_v2/gates/hardware/*.py`
  - `tools/validate_gate_tuning_visualization.py`
  - `tools/validate_circuit_runner_serialization.py`
- Representative experiments updated for override > calibration:
  - `AllXY`
  - `PowerRabi`
  - `T2Ramsey` / `T2Echo` / `ResidualPhotonRamsey`
  - `ResonatorSpectroscopy`
  - `QubitSpectroscopy`
  - selected readout, reset, and tomography paths
- Docs/notebooks/examples updated:
  - `README.md`
  - `tools/build_context_notebook.py`
  - `notebooks/post_cavity_experiment_context.ipynb`
  - `notebooks/post_cavity_experiment_context_SIM.ipynb`

## Inconsistencies / Bugs Found

Ordered highest risk to lowest.

### 1. Remaining silent `st_therm_clks=0` fallback in storage/fock experiments

- Files:
  - `qubox_v2/experiments/cavity/storage.py:328`
  - `qubox_v2/experiments/cavity/storage.py:459`
  - `qubox_v2/experiments/cavity/storage.py:578`
  - `qubox_v2/experiments/cavity/storage.py:729`
  - `qubox_v2/experiments/cavity/fock.py:45`
  - `qubox_v2/experiments/cavity/fock.py:207`
  - `qubox_v2/experiments/cavity/fock.py:409`
  - `qubox_v2/experiments/cavity/fock.py:614`
- Functions/classes:
  - `NumSplittingSpectroscopy`
  - `StorageRamsey`
  - `StorageChiRamsey`
  - `StoragePhaseEvolution`
  - `FockResolvedSpectroscopy`
  - `FockResolvedT1`
  - `FockResolvedRamsey`
  - `FockResolvedPowerRabi`
- Description:
  - These paths still call `self.get_therm_clks("st", fallback=0) or 0`.
- Impact:
  - Missing storage cooldown calibration silently collapses to zero wait, which is a direct silent-miscalibration risk for cavity experiments.
- Recommended fix:
  - Add explicit `st_therm_clks: int | None = None` overrides to these experiment APIs and route them through `resolve_param(..., calibration_path="cqed_params.storage.st_therm_clks")`.

### 2. Remaining silent zero-fallback thermalization in readout calibration experiments

- Files:
  - `qubox_v2/experiments/calibration/readout.py:121`
  - `qubox_v2/experiments/calibration/readout.py:235`
  - `qubox_v2/experiments/calibration/readout.py:333`
- Functions/classes:
  - `IQBlob._build_impl`
  - `ReadoutGERawTrace._build_impl`
  - `ReadoutGEIntegratedTrace._build_impl`
- Description:
  - These code paths still use `get_therm_clks(..., fallback=0)`.
- Impact:
  - Missing cooldown calibration can bias readout quality and discrimination data while appearing valid.
- Recommended fix:
  - Promote `qb_therm_clks` / `ro_therm_clks` to explicit optional API kwargs with calibration-backed resolution and provenance logging.

### 3. Direct circuit path still bakes in legacy `qb_therm_clks=250_000`

- File:
  - `qubox_v2/programs/circuit_runner.py:425`
- Function/class:
  - `CircuitRunner` legacy-to-circuit translation path for AllXY
- Description:
  - `qb_therm_clks = int(params.get("qb_therm_clks", 250_000))`
- Impact:
  - Direct circuit compilation can still bypass the new missing-calibration failure mode and silently use a stale legacy wait.
- Recommended fix:
  - Make `qb_therm_clks` required in this path or plumb a calibration-aware resolver into the circuit runner layer.

### 4. Roleless binding defaults still encode a legacy thermalization constant

- Files:
  - `qubox_v2/core/bindings.py:324`
  - `qubox_v2/core/bindings.py:338`
- Functions/classes:
  - `DriveTarget`
  - `DriveTarget.from_physical`
- Description:
  - `therm_clks` still defaults to `250_000`.
- Impact:
  - Consumers that instantiate roleless targets directly may inherit stale waits without touching calibration.
- Recommended fix:
  - Remove the default or require explicit injection from `SessionManager.context_snapshot()` / calibration when building targets.

### 5. Low-level builder default still encodes `qb_therm_clks=4`

- File:
  - `qubox_v2/programs/builders/spectroscopy.py:137`
- Function/class:
  - `qubit_spectroscopy(...)`
- Description:
  - The low-level builder keeps a default argument `qb_therm_clks:int=4`.
- Impact:
  - Not a problem for the updated experiment layer, but direct builder users can still get a silent legacy default.
- Recommended fix:
  - Remove the default or document this function as an internal primitive whose caller must already have resolved calibration-backed parameters.

## Fixed During This Task

- Removed hidden `qb_therm_clks=25000` fallbacks from:
  - `qubox_v2/experiments/time_domain/rabi.py`
  - `qubox_v2/experiments/time_domain/relaxation.py`
  - `qubox_v2/experiments/time_domain/coherence.py`
  - `qubox_v2/experiments/spectroscopy/qubit.py`
  - `qubox_v2/experiments/spectroscopy/resonator.py`
- Renamed the readout override API knob from `apply_to_attributes` to `apply_to_runtime_context`.
- Updated notebooks that still patched `attributes.*` calibration paths to use `cqed_params.transmon.*`.

## Test Coverage Summary

Updated/added tests:

- `qubox_v2/tests/test_parameter_resolution_policy.py`
  - `AllXY`: explicit override beats calibration
  - `AllXY`: missing calibration raises clear error
  - `PowerRabi`: calibration fallback
  - `PowerRabi`: missing calibration raises clear error
  - `T2Ramsey`: calibration fallback
  - `ResonatorSpectroscopy`: explicit override beats calibration
  - `QubitSpectroscopy`: calibration fallback
- `qubox_v2/tests/test_calibration_cqed_params.py`
  - validates calibration schema/storage support for `cqed_params` mappings used by the new resolver

Validation executed:

- `pytest qubox_v2/tests/test_parameter_resolution_policy.py qubox_v2/tests/test_calibration_cqed_params.py -q`
- Result: `9 passed`

Repository hygiene checks:

- `rg -n "session\\.attributes|save_attributes\\(|refresh_attribute_frequencies_from_calibration|apply_to_attributes|\\.attributes\\b" . --glob '!qubox_legacy/**'`
- Result: no matches
