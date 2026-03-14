# qubox Architecture Overview

Date: 2026-03-13

## Public API

The canonical public surface is:

- `qubox.Session`
- `session.exp.*` for standard experiment templates
- `session.sequence()` for ordered custom control
- `session.circuit()` for gate-sequence-style prototyping
- `session.sweep.*` for first-class sweep objects
- `session.acquire.*` for acquisition specs
- `session.ops.*` for calibration-backed semantic operations

## Layering

The new package is organized around these layers:

1. `session`
   - runtime entry point
   - sample/cooldown context
   - calibration snapshot access
   - proxy to legacy services when needed
2. `experiments`
   - template namespaces for standard lab workflows
   - workflow namespaces for multi-stage calibration flows
3. `sequence`
   - ordered control-body IR
   - sweeps
   - acquisition specs
4. `circuit`
   - circuit-friendly alias over the shared body IR
5. `operations`
   - semantic calibrated operations such as `x90`, `measure`, `reset`
6. `backends.qm`
   - canonical QM runtime adapter
   - lowering from `Sequence` / `QuantumCircuit` to the existing compiler path
7. `data`
   - frozen `ExecutionRequest`
   - unified `ExperimentResult`
8. `calibration`
   - frozen calibration snapshots
   - explicit proposals for shared calibration updates

## Design Intent

The architecture is intentionally not purely circuit-first.

Standard experiments should feel experiment-template-driven.
Custom control should feel sequence-driven.
`QuantumCircuit` should stay available for quick prototyping and familiar
gate-sequence thinking, but it is not the only top-level model.

## Backend Policy

New production-facing code should enter the QM stack through the `qubox`
runtime adapter, not by directly choosing between multiple historical compiler
paths. Internally the adapter still delegates some work to stable `qubox_v2`
experiment classes and the existing `compile_v2` path while the migration is
completed.

## Calibration Policy

The intended calibration model is:

- one canonical shared calibration store
- frozen per-run snapshots
- explicit proposals for updates
- explicit apply/promotion flow for shared calibration mutations

`ExperimentResult.proposal()` is the new public hook for template-driven patch
proposals when an analysis returns `proposed_patch_ops`.
