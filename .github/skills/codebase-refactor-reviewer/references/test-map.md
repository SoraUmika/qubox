# Test Map — Module-to-Test File Mapping

## Test Locations

| Source Module | Test File(s) | Test Type |
|--------------|-------------|-----------|
| `calibration/orchestrator.py` | `qubox/tests/test_calibration_fixes.py` | Unit |
| `calibration/patch_rules.py` | `qubox/tests/test_calibration_fixes.py` | Unit |
| `calibration/*` | `qubox/tests/test_calibration_cqed_params.py` | Integration |
| `core/session_state.py` | `qubox/tests/test_workflow_safety_refactor.py` | Unit |
| `core/persistence_policy.py` | `qubox/tests/test_workflow_safety_refactor.py` | Unit |
| `core/bindings.py` | `qubox/tests/test_parameter_resolution_policy.py` | Unit |
| `gates/*` | `tests/gate_architecture/test_gate_architecture.py` | Golden snapshot |

## Golden Snapshot Tests

Located in `tests/gate_architecture/golden/`:
- `active_reset_analysis_snapshot.txt`
- `active_reset_circuit.txt`
- `ramsey_circuit.txt`
- `ramsey_diagram.txt`
- `ramsey_measurement_schema.json`
- `ramsey_resolution.txt`

Update golden files when intentionally changing output format: `pytest tests/gate_architecture/ --update-snapshots`

## Coverage Gaps (Known)

- `hardware/` — No dedicated unit tests
- `experiments/` subclasses — No per-experiment tests (relies on integration)
- `analysis/fitting.py` — No dedicated fit regression tests
- `compile/` — No GPU accelerator tests
- `pulses/` — No pulse registry/factory tests
