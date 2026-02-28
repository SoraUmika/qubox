# QUBOX_V2 Codebase Survey

Date: 2026-02-27  
Mode: Read-only audit (no code changes)  
Scope: `qubox_v2/`, `README.md`, `docs/CHANGELOG.md`, `notebooks/post_cavity_experiment_context.ipynb`

## Executive Summary

`qubox_v2` has a strong architectural direction: typed calibration models, explicit orchestrator contracts (`Artifact` → `CalibrationResult` → `Patch`), context-aware sample/cooldown isolation, and meaningful verification modules.

The largest risks are **consistency gaps between intended patch/orchestrator semantics and actual runtime mutation paths**. In several places, patch-intent metadata is produced but either filtered out or bypassed via direct singleton/file mutations. This can create diverging runtime vs persisted readout/calibration state.

Top risks identified:
- Patch op mismatch causes declared readout patch intents to be dropped.
- Readout code references `calibration_orchestrator` while session exposes `orchestrator`.
- Multiple direct mutation/persistence paths bypass the orchestrator contract.
- API/documentation drift: referenced docs and interfaces are missing or stale.

Strengths:
- `CalibrationStore` schema/version/context handling is robust and explicit.
- `SessionState` and `ExperimentContext` provide good provenance/context guards.
- Verification tooling (`verification/*`) and targeted calibration regression tests exist and are useful.

## Remediation Log (Implemented)

This section records the concrete fixes applied for all Red/Orange issues.

### Fixed CRIT-01 — Readout patch intents dropped
- **Change**: expanded executable patch-op whitelist.
- **Implementation**:
  - Updated `WeightRegistrationRule.allowed_ops` to include:
    - `SetMeasureDiscrimination`
    - `SetMeasureQuality`
- **File/Symbol**: `qubox_v2/calibration/patch_rules.py` → `WeightRegistrationRule`

### Fixed CRIT-02 — Orchestrator naming mismatch
- **Change**: introduced backward-compatible orchestrator alias and robust lookup.
- **Implementation**:
  - Added `SessionManager.calibration_orchestrator = self.orchestrator`.
  - Updated readout persistence paths to resolve orchestrator by:
    - `ctx.orchestrator` first
    - fallback `ctx.calibration_orchestrator`
- **File/Symbols**:
  - `qubox_v2/experiments/session.py` → `SessionManager.__init__`
  - `qubox_v2/experiments/calibration/readout.py` → `_persist_measure_macro_state`, `CalibrateReadoutFull.run`

### Fixed HIGH-01 — Stale `ExperimentRunner` → `ConfigEngine` API usage
- **Change**: switched to current constructor argument.
- **Implementation**:
  - Replaced `ConfigEngine(hardware_json=..., pulse_json=...)`
  - With `ConfigEngine(hardware_path=...)`
- **File/Symbol**: `qubox_v2/experiments/base.py` → `ExperimentRunner.__init__`

### Fixed HIGH-02 — Fragmented calibration-run artifact pathing
- **Change**: standardized calibration-run artifact location under runtime lane.
- **Implementation**:
  - `ExperimentBase.guarded_calibration_commit` path changed to:
    - `artifacts/runtime/calibration_runs`
  - `HardwareController._write_auto_calibration_artifact` path changed to:
    - `artifacts/runtime/calibration_runs`
- **File/Symbols**:
  - `qubox_v2/experiments/experiment_base.py` → `guarded_calibration_commit`
  - `qubox_v2/hardware/controller.py` → `_write_auto_calibration_artifact`

### Fixed HIGH-03 — Hidden singleton mutation in strict mode and session override
- **Change**: removed strict-mode inline measureMacro mutation; routed threshold override through orchestrator patch.
- **Implementation**:
  - In strict mode, rotated-weight macro mutation is now skipped and deferred to patch application.
  - Discrimination runtime mutation now runs only when inline mutations are allowed.
  - `SessionManager.override_readout_operation` now applies threshold via patch op:
    - `SetMeasureDiscrimination`
    - instead of direct `measureMacro._ro_disc_params[...]` write.
- **File/Symbols**:
  - `qubox_v2/experiments/calibration/readout.py` → `ReadoutGEDiscrimination.analyze`
  - `qubox_v2/experiments/session.py` → `override_readout_operation`

### Fixed HIGH-04 — Missing referenced docs / API entrypoints
- **Change**: restored missing referenced docs with compatibility entrypoints.
- **Created**:
  - `docs/SCHEMA_VERSIONING.md`
  - `docs/VERIFICATION_STRATEGY.md`
  - `docs/PULSE_SPEC_SCHEMA.md`
  - `API_REFERENCE.md`
  - `ARCHITECTURE.md`
  - `qubox_v2/docs/API_REFERENCE.md`
  - `qubox_v2/docs/ARCHITECTURE.md`
- **Outcome**: references used by verification/migration modules and changelog are now resolvable.

## Critical Issues (Red)

### CRIT-01 — Readout patch intents can be silently dropped by patch-rule filtering
- **Risk**: readout state updates are emitted by analysis but may never become executable patch ops.
- **Evidence**:
  - `qubox_v2.experiments.calibration.readout.ReadoutGEDiscrimination.analyze` emits `SetMeasureDiscrimination` in `proposed_patch_ops`.
  - `qubox_v2.experiments.calibration.readout.ReadoutButterflyMeasurement.analyze` emits `SetMeasureQuality` in `proposed_patch_ops`.
  - `qubox_v2.calibration.patch_rules.WeightRegistrationRule.allowed_ops` does **not** include `SetMeasureDiscrimination` or `SetMeasureQuality`.
- **Location**:
  - `qubox_v2/experiments/calibration/readout.py` (`ReadoutGEDiscrimination.analyze`, `ReadoutButterflyMeasurement.analyze`)
  - `qubox_v2/calibration/patch_rules.py` (`WeightRegistrationRule.allowed_ops`)
- **Impact**: runtime and persisted readout discrimination/quality can diverge despite “patch intent emitted” logs.

### CRIT-02 — Orchestrator naming mismatch breaks intended patch persistence path
- **Risk**: readout code attempts orchestrator patch persistence through a non-existent session attribute, then falls back to direct file writes.
- **Evidence**:
  - Session defines `self.orchestrator = CalibrationOrchestrator(self)`.
  - Readout helper checks/uses `self._ctx.calibration_orchestrator` in `_persist_measure_macro_state` and `CalibrateReadoutFull.run`.
- **Location**:
  - `qubox_v2/experiments/session.py` (`SessionManager.__init__`)
  - `qubox_v2/experiments/calibration/readout.py` (`_persist_measure_macro_state`, `CalibrateReadoutFull.run`)
- **Impact**: contract says “persist via orchestrator patch op,” but actual behavior can bypass it and write `measureConfig.json` directly.

## High Risk Issues (Orange)

### HIGH-01 — `ExperimentRunner` appears API-stale against `ConfigEngine`
- **Evidence**:
  - `ExperimentRunner.__init__` calls `ConfigEngine(hardware_json=..., pulse_json=...)`.
  - `ConfigEngine.__init__` accepts `hardware_path` and no `pulse_json`.
- **Location**:
  - `qubox_v2/experiments/base.py` (`ExperimentRunner.__init__`)
  - `qubox_v2/hardware/config_engine.py` (`ConfigEngine.__init__`)
- **Impact**: if `ExperimentRunner` path is used, initialization can fail at runtime.

### HIGH-02 — Multiple persistence lanes fragment artifact provenance
- **Evidence**:
  - `CalibrationOrchestrator.persist_artifact`: `artifacts/runtime/*.npz + .meta.json`
  - `ExperimentBase.guarded_calibration_commit`: `artifacts/calibration_runs/*.json`
  - `HardwareController._write_auto_calibration_artifact`: `<cal_db>/artifacts/calibration_runs/*.json`
  - `core.artifact_manager.ArtifactManager`: build-hash keyed root `artifacts/<build_hash>/`
- **Location**:
  - `qubox_v2/calibration/orchestrator.py`
  - `qubox_v2/experiments/experiment_base.py`
  - `qubox_v2/hardware/controller.py`
  - `qubox_v2/core/artifact_manager.py`
- **Impact**: provenance is harder to trace and compare across runs; policy enforcement becomes inconsistent.

### HIGH-03 — Hidden singleton mutations remain in session and readout flows
- **Evidence**:
  - `SessionManager.override_readout_operation` directly writes `measureMacro._ro_disc_params["threshold"]` and saves config.
  - `readout.py` still directly updates runtime macro state in strict mode (`_apply_rotated_measure_macro`, `_apply_discrimination_measure_macro`) while declaring patch-based semantics.
- **Location**:
  - `qubox_v2/experiments/session.py` (`override_readout_operation`)
  - `qubox_v2/experiments/calibration/readout.py`
- **Impact**: state can change without explicit orchestrator patch application.

### HIGH-04 — Doc/source-of-truth references are internally inconsistent
- **Evidence**:
  - Workspace has no `qubox_v2/docs/` directory.
  - `docs/CHANGELOG.md` and several module docstrings reference files like `qubox_v2/docs/API_REFERENCE.md`, `docs/SCHEMA_VERSIONING.md`, `docs/VERIFICATION_STRATEGY.md` that are absent.
  - The architecture/API content appears consolidated into root `README.md`.
- **Location**:
  - `docs/CHANGELOG.md`
  - `qubox_v2/verification/*.py`, `qubox_v2/migration/*.py`, `qubox_v2/core/schemas.py`
  - `README.md`
- **Impact**: onboarding, auditability, and policy traceability are degraded.

## Medium Issues (Yellow)

### MED-01 — Patch contract vs inline-commit gate is conceptually split
- `SessionManager.allow_inline_mutations` defaults false; many `analyze(update_calibration=True)` paths rely on `guarded_calibration_commit` and may suppress commits unless orchestrator flow is explicitly used.
- This is safe by design, but operationally easy to misuse from notebooks.
- **Location**: `qubox_v2/experiments/experiment_base.py`, `qubox_v2/experiments/session.py`, notebook workflow cells.

### MED-02 — Binary readout semantics are hard-coded in multiple layers
- Assumptions like `target_state in ("g", "e")`, 2x2 confusion/transition matrices, branch A/B for g/e, and boolean state streams are pervasive.
- **Location**:
  - `qubox_v2/programs/macros/measure.py`
  - `qubox_v2/programs/builders/readout.py`
  - `qubox_v2/analysis/metrics.py`
- **Impact**: extending to multi-state discrimination requires non-local changes.

### MED-03 — Broad exception handling can mask state sync failures
- `CalibrationOrchestrator.apply_patch` catches and logs broad exceptions for sync steps and returns `sync_ok=False`, but commit still persists calibration/pulses.
- Several experiment/session paths also use broad catches with fallback behavior.
- **Location**:
  - `qubox_v2/calibration/orchestrator.py`
  - `qubox_v2/experiments/calibration/readout.py`
  - `qubox_v2/experiments/session.py`
- **Impact**: partial success states may be easy to miss in automated pipelines.

### MED-04 — Competing experiment infrastructure classes remain active
- Both `SessionManager` and legacy-style `ExperimentRunner` are exported; their initialization and config/persistence paths differ significantly.
- **Location**: `qubox_v2/experiments/session.py`, `qubox_v2/experiments/base.py`, `qubox_v2/experiments/__init__.py`

## Low Issues (Green)

### LOW-01 — Documentation placement is non-uniform
- Root `README.md` functions as API+architecture reference, while modules still point to non-existent `docs/*` files.

### LOW-02 — Terminology drift still visible (`device` vs `sample`)
- Backward compatibility is implemented well, but mixed naming appears in migration and model adapters.
- **Location**: `qubox_v2/devices/sample_registry.py`, `qubox_v2/core/experiment_context.py`, `tools/migrate_device_to_samples.py`.

### LOW-03 — Legacy compatibility surface remains large
- `legacy_experiment.py` and `gates_legacy.py` still contain substantial logic and broad exception paths, increasing cognitive load.

## Architectural Observations

- **Strong**: `CalibrationStore` (`qubox_v2/calibration/store.py`) is one of the cleanest components: typed schema, atomic writes, context validation, migration hooks.
- **Strong**: context-scoping model (`SampleRegistry` + `ContextResolver` + `ExperimentContext` + `SessionState`) is coherent and lowers stale-calibration risk.
- **Weak boundary**: readout pipeline still crosses layers via singleton macro internals (`measureMacro._ro_*`) from experiments/builders/session utilities.
- **Weak boundary**: artifact persistence is distributed across core/experiment/hardware rather than mediated by one policy owner.

## API Consistency Review

- Naming inconsistency: `SessionManager.orchestrator` vs readout expecting `calibration_orchestrator`.
- Constructor inconsistency: `ExperimentRunner` passes outdated `ConfigEngine` kwargs.
- Return/schema inconsistency: readout fidelity appears as percent in some places and fraction-normalized in notebook handling (manual normalization logic appears in notebook readout cells).
- Docstring/behavior drift: readout code advertises orchestrator patch persistence but includes direct-save fallback paths.

## Calibration Pipeline Integrity Review

Intended pipeline: `Run -> Artifacts -> Patch -> Apply`.

Observed integrity gaps:
- Proposed patch ops emitted in analysis are not guaranteed to survive `WeightRegistrationRule` filtering.
- Some flows mutate runtime singleton state directly before/without patch apply.
- Multiple artifact destinations reduce single-source provenance.

Observed strengths:
- `CalibrationOrchestrator.run_analysis_patch_cycle` provides dry-run preview and skips non-passing apply.
- `Patch`, `CalibrationResult`, and rule-based patch synthesis are clean abstractions.

## Hardware Abstraction Review

- `HardwareDefinition` and context-mode sample/cooldown layout are clear and practical.
- Channel-binding abstraction (`ChannelRef`, `ReadoutBinding`, `ReadoutCal`) is a strong step toward roleless API design.
- Boundary overlap remains: hardware controller writes calibration artifacts; session/readout layers persist macro/config directly.

## Recommended Strategic Improvements (Non-Breaking)

1. Align orchestrator naming (`orchestrator` vs `calibration_orchestrator`) with a compatibility alias and deprecation warning path.
2. Expand `WeightRegistrationRule.allowed_ops` to include emitted readout ops, or stop emitting unsupported ops.
3. Define one artifact policy owner and route all artifact writes through it (or publish explicit sanctioned lanes).
4. Add a strict-mode audit log/report object that records every deferred vs applied mutation and `sync_ok` outcomes.
5. Normalize fidelity unit conventions (percent vs fraction) in one shared utility and metadata field.
6. Consolidate docs references: either create the referenced `docs/*` files or update all pointers to `README.md` sections.

## Long-Term Refactor Suggestions

1. Complete migration from singleton `measureMacro` internals to binding-driven immutable `ReadoutHandle` + explicit state transitions.
2. Retire or hard-freeze `ExperimentRunner` and route users through `SessionManager` only.
3. Introduce a formal mutation ledger: every calibration change as a typed patch event with pre/post checks and replay support.
4. Generalize readout semantics beyond binary g/e in models/builders/metrics for multi-state workflows.
5. Collapse legacy and v2 persistence checks into one CI-facing verification package with mandatory doc linkage checks.

