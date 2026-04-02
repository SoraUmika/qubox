---
name: pytest-coverage
description: "Run pytest with coverage analysis and iteratively increase test coverage for the qubox codebase. Use when: checking test coverage, finding untested code, writing tests to cover missing lines, running pytest with --cov, or any request like 'increase coverage', 'what is untested', 'add tests', 'check coverage', or 'coverage report'."
argument-hint: "Module or directory to check coverage for (e.g., 'qubox/calibration', 'qubox/legacy/experiments')"
---

# Pytest Coverage Skill

## When to Use

- Checking test coverage for a module or the entire codebase
- Finding lines of code not covered by tests
- Writing tests to increase coverage for specific modules
- After a refactor, verifying coverage hasn't dropped
- Any request mentioning "coverage", "untested", "add tests", or "test gaps"

## Procedure

### Step 1 — Generate Coverage Report

Run pytest with coverage for the target scope:

```bash
# Full codebase
pytest --cov=qubox --cov-report=annotate:cov_annotate --cov-report=term-missing -v

# Specific module
pytest --cov=qubox.calibration --cov-report=annotate:cov_annotate --cov-report=term-missing -v

# Specific test file targeting a module
pytest tests/test_calibration.py --cov=qubox.calibration --cov-report=annotate:cov_annotate -v
```

### Step 2 — Identify Gaps

1. Read the `cov_annotate/` directory — one file per source file
2. Files with 100% coverage can be skipped
3. For each file with gaps, open the annotated version
4. Lines starting with `!` are NOT covered by tests — these are the targets

### Step 3 — Prioritize

Focus coverage efforts in this order:

| Priority | Location | Reason |
|----------|----------|--------|
| 1 | `qubox/calibration/` | Contract-critical: FitResult, patches |
| 2 | `qubox/legacy/experiments/` | Experiment lifecycle correctness |
| 3 | `qubox/backends/qm/` | Hardware interaction paths |
| 4 | `qubox/session/` | Session state management |
| 5 | `qubox_tools/` | Analysis and fitting |

### Step 4 — Write Tests

For each uncovered line:

1. Read the function containing the uncovered line
2. Understand what input would exercise that code path
3. Write a test that:
   - Uses existing `conftest.py` fixtures (mock sessions, configs)
   - Mocks hardware connections (never connect to real OPX+)
   - Asserts specific outcomes, not just "no exception"
   - Follows naming convention: `test_{module_name}.py`

### Step 5 — Verify

```bash
# Re-run coverage after adding tests
pytest --cov=qubox --cov-report=term-missing -v

# Clean up annotated files when done
Remove-Item -Recurse cov_annotate/
```

### Step 6 — Report

```markdown
## Coverage Report

| Module | Before | After | Lines Added |
|--------|--------|-------|-------------|
| ... | ...% | ...% | N |

### Tests Added
- `tests/test_X.py::test_Y` — covers [description]

### Remaining Gaps
- [uncoverable lines with justification]
```

## Rules

- Mock hardware; never require live OPX+ in unit tests
- Use `from __future__ import annotations` in every test module
- Tests must assert outcomes, not just absence of exceptions
- Clean up `cov_annotate/` after analysis (don't commit it)
- Follow existing test patterns in `tests/conftest.py`
