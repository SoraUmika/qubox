# Task Log

## Original Request
For both the auto and manual calibration in this notebook, it should do calibration on all outputs, and then print out the calibration results by running verification through the spectrum analyzer.

## Context
- Target notebook: notebooks/01_mixer_calibrations.ipynb
- Constraint: do not execute live hardware calibration during this edit.
- Goal: ensure both auto and manual flows iterate over all active mixer outputs and print spectrum-analyzer verification results.

## Changes Made
- Updated the auto calibration settings cell to enable SA verification by default and expose SA verification settings.
- Updated the auto calibration execution cell to:
  - resolve all active mixer outputs explicitly,
  - calibrate all active outputs in one call,
  - pass explicit LO/IF targets for each output,
  - run SA verification through the controller,
  - print a readable controller summary per output after calibration.
- Updated the manual calibration execution cell to:
  - calibrate all active outputs,
  - run SA measurements before and after each calibration,
  - print per-output verification metrics and a summary table.

## Files Modified
- notebooks/01_mixer_calibrations.ipynb

## Validation
- Inspected the relevant notebook cells after editing.
- Validated the new auto and manual cell code with Python 3.12 syntax checks.
- Did not execute notebook cells or hardware-facing calibration commands.

## Assumptions
- The intended meaning of "all outputs" is all active mixer outputs returned by resolve_active_mixer_targets(session, include_skipped=True)["active"].
- Existing hardware/controller APIs remain the source of truth for auto calibration and SA verification behavior.
