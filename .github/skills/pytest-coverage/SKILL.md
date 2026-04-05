---
name: pytest-coverage
description: "Run pytest with coverage analysis and iteratively increase test coverage for the qubox codebase. Use when: checking test coverage, finding untested code, writing tests to cover missing lines, running pytest with --cov, or any request like 'increase coverage', 'what is untested', 'add tests', 'check coverage', or 'coverage report'."
argument-hint: "Module or directory to check coverage for (e.g., 'qubox/calibration', 'qubox/legacy/experiments')"
---

# Pytest Coverage

## Procedure

1. **Generate report:** `pytest --cov=<module> --cov-report=annotate:cov_annotate --cov-report=term-missing -v`
2. **Identify gaps:** Read `cov_annotate/` files — lines starting with `!` are uncovered.
3. **Prioritize:** calibration (contract-critical) → experiments (lifecycle) → backends (hardware) → session → analysis.
4. **Write tests:** Use `conftest.py` fixtures, mock hardware connections, assert specific outcomes (not just no-exception). Follow `test_{module_name}.py` naming.
5. **Verify:** Re-run coverage. Clean up `cov_annotate/` (don't commit it).

## Rules

- Mock hardware; never require live OPX+ in unit tests
- `from __future__ import annotations` in every test module
- Tests must assert outcomes, not just absence of exceptions
- Follow existing patterns in `tests/conftest.py`
