# Prompt Log

**Date:** 2026-03-21 22:03:28
**Task:** numbered-notebook-expansion
**Target files:** docs/CHANGELOG.md, notebooks/01_mixer_calibrations.ipynb, notebooks/02_resonator_spectroscopy.ipynb, notebooks/03_power_rabi_temporal_rabi.ipynb

## Original Request

1.) For the calibrations, we should have one cell that does auto calibrations and one cell that does manual calibrations, also we should calibrate all targets.
2.) Once done with step 2, lets start writing other notebooks, start with 02_resonator_spectroscopy which will contain resonator_spectroscopy experiment and a resonator power chevron experiment, then we do 03 power rabi temporal rabi, refer to the typical values used in legacy notebook code.

## Response / Changes Made

Updated notebooks/01_mixer_calibrations.ipynb so the auto and manual execution cells stay preview-first by default and the manual path calibrates all active mixer targets. Added notebooks/02_resonator_spectroscopy.ipynb and notebooks/03_power_rabi_temporal_rabi.ipynb with shared-session bootstrap cells and legacy-aligned default sweeps for resonator spectroscopy, resonator power chevron, power Rabi, and temporal Rabi. Validated notebook parsing and preview cells, and updated docs/CHANGELOG.md.

## Context

Legacy defaults were harvested from the external post_cavity_experiment_legacy.ipynb notebook, while temporal Rabi defaults were matched to the migrated context notebook when the exact legacy cell was not readily identifiable.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
