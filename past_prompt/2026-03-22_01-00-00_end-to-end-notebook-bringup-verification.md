# Prompt Log

**Date:** 2026-03-22 01:00:00
**Task:** end-to-end-notebook-bringup-verification
**Target files:** docs/CHANGELOG.md, notebooks/01_mixer_calibrations.ipynb, notebooks/02_time_of_flight.ipynb, notebooks/03_resonator_spectroscopy.ipynb, notebooks/04_resonator_power_chevron.ipynb, notebooks/05_qubit_spectroscopy_pulse_calibration.ipynb, notebooks/06_coherence_experiments.ipynb

## Original Request

perform a full end-to-end verification pass of the notebook workflow for notebooks 00 through 06, keep each experiment lightweight enough for bring-up, fix anything that is broken, simplify the notebooks for real users, and make sure the workflow still follows the legacy experiment style where the experiment is run first, then plotted and fitted, then calibration is previewed or applied. Also fix the frozen notebook 02 time-of-flight cell because each experiment should not take more than 4 to 5 minutes.

## Response / Changes Made

Validated the numbered notebook chain live from notebook 00 through notebook 06. Simplified notebook controls, fixed notebook 01 mixer-target plotting, hardened notebooks 02 through 05 to reopen a fresh shared session after QM restarts, shortened notebook 02 and added an automatic one-time reconnect, widened notebook 04 and fixed its missing ro_therm_clks override, and tightened notebook 06 so non-physical coherence fits do not apply calibration patches. Re-ran the live workflow, restored the qubit frequency after an earlier Ramsey gate allowed a bad fit through during validation, and appended a matching docs/CHANGELOG.md entry.

## Context

Live validation used the shared post-cavity sample and cooldown workflow against the hosted QM endpoint. Notebook 01 auto mixer calibration restarts the QM, which invalidates stale notebook session handles unless later notebooks explicitly reopen the shared session. The pass also confirmed residual experimental risk: notebook 05 Temporal Rabi still reports a physically dubious short pi-length, and notebook 06 Ramsey and Echo fits can become numerically non-physical under reduced-cost settings even when the structural execution path is correct.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
