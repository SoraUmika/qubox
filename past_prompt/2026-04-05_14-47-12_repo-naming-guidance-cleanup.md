# Prompt Log

**Date:** 2026-04-05 14:47:12
**Task:** repo-naming-guidance-cleanup
**Target files:** .cursorrules, .clinerules, .windsurfrules, qubox/programs/spectroscopy.py, qubox/programs/readout.py, qubox/programs/calibration.py, qubox/programs/cavity.py, qubox/programs/time_domain.py, qubox/programs/tomography.py, qubox/programs/builders/__init__.py, qubox/experiments/experiment_base.py, qubox/experiments/result.py, qubox/experiments/configs.py, qubox/calibration/algorithms.py, qubox/calibration/pulse_train_tomo.py, qubox/core/hardware_definition.py, qubox/core/logging.py, qubox/notebook/workflow.py, qubox/experiments/cavity/fock.py, qubox/experiments/cavity/storage.py, docs/CHANGELOG.md

## Original Request

work on these cleanup based on the findings

## Response / Changes Made

Fixed stale agent instruction files (.cursorrules, .clinerules, .windsurfrules): replaced non-existent qubox/legacy/ guidance with correct messaging, fixed Python version 3.12.13->3.12.10. Updated 13 source files with stale qubox_v2 docstrings to qubox.*. Fixed misleading deprecated directive in notebook/workflow.py. Dated temporary compatibility paths in cavity experiments. Added removal guidance to qubox_v2 logger mapping. All 97 tests pass, 18/18 import checks pass.

## Context

(none)

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
