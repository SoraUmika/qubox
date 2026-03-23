# Prompt Log

**Date:** 2026-03-21 21:34:12
**Task:** shared-notebook-session-and-mixer-targets
**Target files:** qubox/compat/notebook_runtime.py, qubox/compat/notebook.py, tests/test_notebook_runtime.py, tests/test_qubox_public_api.py, API_REFERENCE.md, docs/CHANGELOG.md, notebooks/00_hardware_defintion.ipynb, notebooks/01_mixer_calibrations.ipynb

## Original Request

Notice we have one issues, in paritcular, everytime we run an experiment noteobok,we have to reload the session, the sesion should only ahve to be run once, and it should be the case that when im in a differnet notebook, ican connect to the same session without having to reaload everything, (maybe we shall have apython file starter that starts the session,), you should think of this design careuflly, also try to get 01_mixer_calibration working on all 5 outputs

## Response / Changes Made

Added a shared notebook runtime helper under qubox.compat so notebook 00 can open and register a live session once, later notebooks can reuse it in the same kernel, and fresh kernels can reopen the same sample/cooldown session from a persisted bootstrap JSON. Updated notebook 00 to open the shared session and write the bootstrap metadata, updated notebook 01 to require the shared session instead of reopening unconditionally, and changed the mixer-calibration target discovery to use all active mixer elements from the live hardware config so manual calibration is no longer limited to readout/qubit/storage only. Added focused unit tests and updated API_REFERENCE.md and docs/CHANGELOG.md.

## Context

Sequential notebook workflow for shared session reuse across notebooks and full active mixer output coverage in mixer calibration.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
