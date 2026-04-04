# Prompt Log

**Date:** 2026-04-03 00:17:07
**Task:** resolve-simulator-validation-errors
**Target files:** tools/validate_standard_experiments_simulation.py, qubox/experiments/time_domain/chevron.py, qubox/programs/builders/cavity.py, qubox/backends/qm/runtime.py, tools/simulation_validation_report.json, limitations/qua_related_limitations.md, docs/CHANGELOG.md

## Original Request

try to reoslve the errors

## Response / Changes Made

Fixed the eight standard-experiment simulator errors by correcting the validation helper inputs, registering the missing AllXY idle pulse, enforcing a legal minimum TimeRabiChevron pulse duration, and making storage Wigner tomography accept callable state-preparation macros through the QM runtime path. Re-ran targeted failing cases and then the full simulator trust-gate suite; tools/simulation_validation_report.json now reports 20 passes and 0 errors on the hosted QM simulator.

## Context

(none)

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
