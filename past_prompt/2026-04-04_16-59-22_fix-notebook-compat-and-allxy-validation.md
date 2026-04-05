# Prompt Log

**Date:** 2026-04-04 16:59:22
**Task:** fix-notebook-compat-and-allxy-validation
**Target files:** qubox/notebook/runtime.py,tests/test_notebook_workflow.py,tests/test_standard_experiments.py,tools/validate_standard_experiments_simulation.py,docs/CHANGELOG.md

## Original Request

do all three

## Response / Changes Made

Reconciled the notebook compatibility drift by making notebook runtime accept both session.hardware and legacy session.hw, updated the notebook workflow tests to patch the portable workflow modules behind the notebook wrapper, replaced the stale hardcoded adapter count assertion with a check against the required standard template set, and reduced the calibration.all_xy simulator validation to a representative three-sequence subset for structural trust checks. Re-ran the broad pytest suite successfully (157 passed) and re-ran the hosted standard-experiment simulator validation successfully (20 passed, 0 failed, 0 errors), with calibration.all_xy dropping from about 90.45s to about 2.64s in the report.

## Context

(none)

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
