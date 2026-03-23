# Prompt Log

**Date:** 2026-03-22 02:08:34
**Task:** remove-legacy-cqed-params-notebook-comparisons
**Target files:** docs/CHANGELOG.md, notebooks/00_hardware_defintion.ipynb, notebooks/02_time_of_flight.ipynb, notebooks/03_resonator_spectroscopy.ipynb, notebooks/04_resonator_power_chevron.ipynb, notebooks/05_qubit_spectroscopy_pulse_calibration.ipynb, notebooks/06_coherence_experiments.ipynb

## Original Request

please remove all the legacy cqed params code or comparison for all th enotebooks

## Response / Changes Made

Removed legacy cqed_params loading, legacy comparison prints, and legacy comparison plot markers from the numbered notebooks. Notebook 00 now shows runtime-only sanity plots, notebooks 02-04 use runtime-only diagnostics, and notebooks 05-06 no longer depend on legacy cqed_params values for defaults or reporting. Added a CHANGELOG entry for the notebook workflow update.

## Context

Notebook-only workflow cleanup. Legacy cqed_params code paths were removed from numbered notebooks, but old saved cell outputs may still show legacy comparison text until those cells are cleared or rerun.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
