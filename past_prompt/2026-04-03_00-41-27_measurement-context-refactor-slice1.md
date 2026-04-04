# Prompt Log

**Date:** 2026-04-03 00:41:27
**Task:** measurement-context-refactor-slice1
**Target files:** docs/codebase_refactor_plan.md, qubox/programs/measurement.py, qubox/programs/circuit_compiler.py, qubox/session/session.py, qubox/experiments/result.py, tests/gate_architecture/test_gate_architecture.py

## Original Request

Save this refactor plan and start refactoring

## Response / Changes Made

Saved the prioritized refactor roadmap in docs/codebase_refactor_plan.md and started the first slice by moving CircuitCompiler measurement lowering onto explicit readout handles. measurement_config now produces build-time readout snapshots without mutating the global measureMacro singleton, Session.readout_handle accepts alias/operation passthrough, and a regression test locks that behavior in.

## Context

(none)

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
