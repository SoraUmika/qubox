# Prompt Log

**Date:** 2026-04-02 23:43:30
**Task:** control-ir-kickoff
**Target files:** qubox/control/__init__.py, qubox/control/models.py, qubox/control/adapters.py, qubox/sequence/models.py, qubox/circuit/models.py, tests/test_control_program.py, API_REFERENCE.md, docs/CHANGELOG.md

## Original Request

Start implementation

## Response / Changes Made

Added the first simulator/hardware bridge slice by creating qubox.control, introducing a symbolic ControlProgram IR with provenance-aware instruction types, adding sequence/circuit lowering adapters and new to_control_program methods, plus targeted tests and API/changelog updates.

## Context

First implementation slice for the planned simulator/hardware bridge redesign. Kept the existing QM execution path unchanged and introduced a canonical symbolic control artifact reachable from the current Sequence and QuantumCircuit authoring surfaces. Validation: get_errors clean, pytest tests/test_control_program.py -q passed, broader public API test module still has unrelated pre-existing failures, and ruff is unavailable in the active Python environment.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
