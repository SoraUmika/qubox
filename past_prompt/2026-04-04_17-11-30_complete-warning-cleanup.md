# Prompt Log

**Date:** 2026-04-04 17:11:30
**Task:** complete-warning-cleanup
**Target files:** qubox/tests/test_workflow_safety_refactor.py,qubox/tests/test_calibration_fixes.py,qubox/tests/test_parameter_resolution_policy.py,qubox_tools/fitting/calibration.py,pyproject.toml,tools/validate_standard_experiments_simulation.py,docs/CHANGELOG.md,tools/simulation_validation_report.json

## Original Request

yes go ahead all do a complete cleanup

## Response / Changes Made

Cleaned the remaining validation noise by fixing the custom dotted-module loaders in qubox/tests so they no longer trigger __package__/__spec__ import warnings, making the legacy CircuitRunner.compile deprecation explicit in its regression test, suppressing the non-fatal covariance warning in qubox_tools.fitting.calibration.fit_number_splitting when the fit still succeeds, filtering the known third-party QM/Marshmallow deprecations in pytest, and updating the hosted simulator validation tool to suppress those same SDK warnings around the simulate path. Revalidated with the broad pytest suite (157 passed, no warnings summary) and the hosted standard-experiment simulator validation (20 passed, 0 failed, 0 errors, report timestamp 2026-04-04T17:10:27).

## Context

(none)

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
