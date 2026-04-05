# Prompt Log

**Date:** 2026-04-04 17:11:39
**Task:** complete-warning-cleanup
**Target files:** qubox/tests/test_workflow_safety_refactor.py,qubox/tests/test_calibration_fixes.py,qubox/tests/test_parameter_resolution_policy.py,qubox_tools/fitting/calibration.py,pyproject.toml,tools/validate_standard_experiments_simulation.py,docs/CHANGELOG.md,tools/simulation_validation_report.json

## Original Request

yes go ahead all do a complete cleanup

## Response / Changes Made

Cleaned remaining test and validation warning noise, fixed local test-loader warnings, captured the legacy CircuitRunner warning explicitly, suppressed the non-fatal fit covariance warning on successful number-splitting fits, filtered third-party QM and Marshmallow warning noise in pytest, and updated the standard simulator validator to suppress known QM deprecation output around simulation. Validation: pytest tests qubox/tests -q -ra passed with 157 passed and no warnings summary; tools/validate_standard_experiments_simulation.py passed with total=20, passed=20, failed=0, errors=0 at 2026-04-04T17:10:27.

## Context

(none)

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
