# Prompt Log

**Date:** 2026-04-03 00:27:30
**Task:** codebase-weakness-refactor-review
**Target files:** qubox/programs/macros/measure.py, qubox/backends/qm/runtime.py, qubox/backends/qm/lowering.py, qubox/programs/circuit_compiler.py, qubox/control/realizer.py, qubox/experiments/templates/library.py, qubox/session/session.py, qubox/data/models.py, tools/validate_standard_experiments_simulation.py, docs/architecture_audit.md

## Original Request

consider the codebase again, check for weakness and suggest refactoring

## Response / Changes Made

Reviewed the current control bridge, QM runtime, compiler, measurement macro, and simulator validation harness. Identified five priority weaknesses: global measureMacro state, duplicated experiment semantics across runtime adapters and validation helpers, partial/silent control-program realization, silent loss of state classification when discrimination is missing, and weak provenance capture in RunManifest. Recommended starting with an instance-scoped measurement context refactor, then collapsing the adapter/validation duplication into a declarative experiment spec layer.

## Context

(none)

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
