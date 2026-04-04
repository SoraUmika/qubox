# Codebase Refactor Plan

**Date:** 2026-04-03
**Status:** In Progress
**Goal:** Reduce hidden global state and duplicated execution semantics without destabilizing the validated QM path.

---

## Priorities

### 1. Measurement Context Isolation

**Status:** Completed for the active `qubox` path.

**Outcome:**

1. Compiler-side measurement lowering now consumes explicit `ReadoutHandle` / `MeasurementConfig` inputs.
2. Readout-calibration experiments and validation helpers seed explicit readout fixtures instead of hidden singleton state.
3. The active `qubox.programs.macros` surface now exposes `emit_measurement()` only.

**Notes:**

- Legacy `measureConfig.json` payloads remain readable through `MeasurementConfig.load_json(...)`.
- The earlier singleton-removal migration plan is now historical background for the completed live-code migration.

### 2. Declarative Experiment Specs

**Problem:** QM runtime adapters and simulator validation helpers duplicate experiment parameter semantics in parallel handwritten mappings.

**Plan:**

1. Introduce a declarative experiment-spec layer for template argument normalization.
2. Reuse the same spec definitions in `QMRuntime`, simulator trust gates, and notebook validation helpers.
3. Delete one-off adapter helpers once the spec layer is authoritative.

### 3. Control Realization Hardening

**Problem:** `qubox.control.realizer` currently falls back to unresolved semantic instructions too quietly, which can hide incomplete simulator-to-hardware translation.

**Plan:**

1. Classify realizations as exact, best-effort, or unresolved.
2. Surface unresolved instructions in build metadata and validation output.
3. Add targeted trust-gate coverage for mixed semantic and pulse-native control programs.

### 4. State-Rule Contract Tightening

**Problem:** Measurement discrimination loss can degrade into a missing `StateRule` without a strong signal to the caller.

**Plan:**

1. Make readout discrimination availability explicit in lowering metadata.
2. Fail loudly where real-time or derived-state behavior depends on missing thresholds.
3. Remove silent `None` paths where they hide a real contract break.

### 5. Provenance Completion

**Problem:** `RunManifest` captures useful provenance, but important details still degrade silently when version or hardware snapshot collection fails.

**Plan:**

1. Make provenance collection structured and explicit about missing fields.
2. Include control-program and lowered-circuit identity in manifests.
3. Reuse the same manifest logic across template and custom execution paths.

---

## Execution Order

1. Collapse runtime adapter duplication behind declarative experiment specs.
2. Tighten control-realization and state-rule contracts.
3. Expand manifest/provenance fidelity.

---

## Validation Rules

- Every QUA-touching slice must keep unit coverage green.
- Any change to pulse lowering or scheduling must rerun simulator trust gates.
- The compiled QUA program remains the source of truth for behavior.
