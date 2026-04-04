# Prompt Log

**Date:** 2026-04-03 20:19:14
**Task:** remove-measuremacro-readout-calibration
**Target files:** qubox/programs/macros/measure.py,qubox/programs/macros/__init__.py,qubox/experiments/calibration/readout.py,qubox/programs/circuit_compiler.py,qubox/experiments/result.py,qubox/backends/qm/runtime.py,qubox/autotune/run_post_cavity_autotune_v1_1.py,tools/validate_circuit_runner_serialization.py,tools/validate_gate_tuning_visualization.py,tools/test_all_simulations.py,tools/build_context_notebook.py,notebooks/verify_compilation.py,notebooks/post_cavity_experiment_context.ipynb,notebooks/post_cavity_experiment_quantum_circuit.ipynb,tests/test_readout_binding_ownership.py,tests/test_qubox_public_api.py,tests/gate_architecture/test_gate_architecture.py,qubox/tests/test_workflow_safety_refactor.py,qubox/tests/test_calibration_fixes.py,API_REFERENCE.md,docs/CHANGELOG.md,docs/codebase_refactor_plan.md

## Original Request

Modify all the readout-calibration experiments so that we can remove measureMacro completely.

Constraints:
- Preserve validated QUA behavior and notebook workflows.
- Python 3.12.10 only.
- QM/QUA API 1.2.6 only.
- Hosted validation target: 10.157.36.68 / Cluster_2.
- Update docs/changelog/notebooks for any public workflow changes.
- Run focused tests and simulator validation for QUA-touching changes.

## Response / Changes Made

Removed the remaining active measureMacro dependency from the readout-calibration path and related notebook/tool surfaces. Readout calibration experiments now use explicit MeasurementConfig/ReadoutHandle flow with set_active_readout / update_readout_config, qubox.programs.macros now exports only emit_measurement() and sequenceMacros, notebook verification helpers no longer seed hidden global readout state, and stale test-only legacy imports were migrated to current qubox/qubox_tools modules. Validation completed with py_compile, notebook JSON parsing, 89 focused pytest passes, serialization/visualization validators passing, and the hosted standard-experiment simulator trust gate staying green at 20/20 on 2026-04-03 against 10.157.36.68 / Cluster_2.

## Context

Readout-calibration refactor slice to remove measureMacro completely while preserving hosted simulator trust-gate behavior and notebook workflows.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
