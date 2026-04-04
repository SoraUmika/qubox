# Prompt Log

**Date:** 2026-04-03 02:17:37
**Task:** fix-simulator-uncertainties
**Target files:** tools/validate_standard_experiments_simulation.py, tests/test_standard_experiments_simulation_helper.py, docs/CHANGELOG.md, tools/simulation_validation_report.json

## Original Request

go ahead and fix all the uncertains

## Response / Changes Made

Hardened the hosted standard-experiment simulator validator against intermittent QM sample-pull failures by retrying get_simulated_samples(), preferring get_simulated_waveform_report() as the fallback reconstruction source, keeping the legacy waveform-metadata fallback as a backup, and adding focused regression coverage. Revalidated the readout binding ownership slice, reran the hosted standard simulator trust gate on 10.157.36.68 / Cluster_2, and produced a fresh tools/simulation_validation_report.json with 20 passes and 0 errors.

## Context

(none)

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
