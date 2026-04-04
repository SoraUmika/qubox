# Prompt Log

**Date:** 2026-04-03 01:32:00
**Task:** refactor-readout-ownership
**Target files:** qubox/core/bindings.py,qubox/programs/macros/measure.py,qubox/experiments/session.py,qubox/experiments/experiment_base.py,qubox/experiments/calibration/readout.py,qubox/calibration/orchestrator.py,tests/test_readout_binding_ownership.py

## Original Request

We will allow breaking of each experiemtn for now, and we will fix/redesign expeiremnt later one, lets run the refactor and then perfroam the validaitons

## Response / Changes Made

Refactored readout ownership so session bindings and explicit ReadoutHandle snapshots are authoritative during program construction. Updated the session readout factory, experiment readout helper, calibration orchestrator sync path, and the ReadoutGEIntegratedTrace / ReadoutGEDiscrimination builders to compile from explicit handles instead of preloading measureMacro. Added focused regression tests, validated the local pytest slice, and ran hosted simulator checks: targeted readout builder simulations passed, while the broader standard experiment simulator script hit QM sample-pull QMSimulationError failures on untouched standard cases.

## Context

(none)

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
