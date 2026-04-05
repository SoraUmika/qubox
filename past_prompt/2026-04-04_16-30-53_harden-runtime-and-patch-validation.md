# Prompt Log

**Date:** 2026-04-04 16:30:53
**Task:** harden-runtime-and-patch-validation
**Target files:** qubox/hardware/program_runner.py,qubox/hardware/queue_manager.py,qubox/programs/circuit_execution.py,qubox/calibration/orchestrator.py,qubox/experiments/base.py,qubox/verification/persistence_verifier.py,tests/gate_architecture/conftest.py,tests/gate_architecture/test_gate_architecture.py,tests/test_connection_policy.py,qubox/tests/test_calibration_fixes.py,docs/CHANGELOG.md

## Original Request

go aheaD AND FIX IT

## Response / Changes Made

Hardened ProgramRunner and QueueManager to fail closed on fetch and processor errors unless partial results are explicitly allowed, fixed compiled circuit execution to use the canonical runner and the repository-standard Cluster_2 flow, added fail-fast calibration patch validation and unknown-op rejection, made ExperimentRunner.run reject ignored simulation-mode flags, disabled pickle in the persistence verifier, updated the changelog, and added focused regression tests. Focused pytest passed for tests/test_connection_policy.py, tests/gate_architecture/test_gate_architecture.py, and qubox/tests/test_calibration_fixes.py.

## Context

(none)

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
