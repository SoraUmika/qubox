---
description: "Use when writing or modifying tests for qubox. Covers pytest conventions, golden snapshot testing, and test organization."
applyTo: ["qubox/legacy/tests/**", "tests/**"]
---

# Test Instructions

## Conventions

- Use `pytest` with fixtures in `conftest.py`
- Golden snapshot tests in `tests/gate_architecture/golden/` — update with `--update-snapshots` flag
- Test files mirror source structure: `test_{module_name}.py`
- Mock hardware connections; never require live OPX+ in unit tests
- Use `from __future__ import annotations` in every test module

## Running Tests

```bash
pytest                                    # full suite
pytest tests/gate_architecture/ -v        # gate architecture with snapshots
pytest tests/ -v                          # all tests
ruff check qubox/                         # lint check
```

## Procedure

1. Before writing a test, read the module under test and any existing tests for it.
2. Place test files in `tests/` mirroring the source structure.
3. Use `conftest.py` fixtures for shared test data (mock sessions, configs, hardware stubs).
4. For QUA-related tests, mock the QM API — never connect to real hardware in unit tests.
5. Run `pytest -v` after adding tests to verify they pass.
6. If adding snapshot tests, run `pytest --update-snapshots` to generate golden files, then commit them.
