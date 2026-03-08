---
description: "Use when writing or modifying tests for qubox. Covers pytest conventions, golden snapshot testing, and test organization."
applyTo: ["qubox_v2/tests/**", "tests/**"]
---

# Test Instructions

## Conventions

- Use `pytest` with fixtures in `conftest.py`
- Golden snapshot tests in `tests/gate_architecture/golden/` — update with `--update-snapshots` flag
- Test files mirror source structure: `test_{module_name}.py`
- Mock hardware connections; never require live OPX+ in unit tests

## Running Tests

```bash
pytest                                    # full suite
pytest tests/gate_architecture/ -v        # gate architecture with snapshots
pytest qubox_v2/tests/ -v                 # core unit tests
ruff check qubox_v2/                      # lint check
```
