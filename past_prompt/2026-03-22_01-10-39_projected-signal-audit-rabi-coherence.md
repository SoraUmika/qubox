# Task Log

## Original Prompt
Please review the Rabi experiments and coherence experiments, and verify that the analysis is using the projected signal data rather than raw IQ data.

Specific requirements:
- Confirm the raw IQ data is first projected into the appropriate signal basis.
- Confirm the analysis uses the projected S_I data.
- Confirm fitted quantities such as oscillation amplitude, decay constants, coherence times, or any other reported metrics are all derived from that projected I-quadrature signal.
- Confirm there is no unintended use of raw I/Q traces, magnitude, or unprojected data in the fitting pipeline.
- If any experiment is not currently using projected S_I, update it so the analysis is consistent across the Rabi and coherence workflows.
- Clearly report which files/functions were using the wrong signal source and what changed.

## Context
Audit and tighten the time-domain Rabi and coherence analysis paths in the legacy experiment layer and notebook diagnostics. Preserve the existing public API and make the smallest correct change.

## Changes Made
- Verified the core fit paths in `TemporalRabi`, `PowerRabi`, `T1Relaxation`, `T2Ramsey`, `T2Echo`, and `ResidualPhotonRamsey` all project complex `S` data before fitting.
- Updated `qubox/legacy/experiments/time_domain/rabi.py` so `PowerRabi.analyze()` fits the direct projected `S_I` trace and persists it in `analysis.data["projected_S"]`.
- Updated `qubox/legacy/experiments/time_domain/relaxation.py` so `T1Relaxation.analyze()` persists the projected fit trace and the plot reuses it.
- Updated `qubox/legacy/experiments/time_domain/coherence.py` so `T2Ramsey`, `T2Echo`, and `ResidualPhotonRamsey` persist the projected fit trace and their plots reuse it.
- Updated notebook diagnostics in `notebooks/05_qubit_spectroscopy_pulse_calibration.ipynb` to remove the Rabi magnitude fallback and always use projected `S_I`.
- Updated notebook fit views in `notebooks/06_coherence_experiments.ipynb` to prefer the stored projected trace used by the analysis.
- Added `qubox/legacy/tests/test_projected_signal_analysis.py` to regress the projection-to-fit data path.
- Appended a matching entry to `docs/CHANGELOG.md`.

## Validation
- Ran `e:/qubox/.venv/Scripts/python.exe -m pytest qubox/legacy/tests/test_projected_signal_analysis.py`
- Result: 4 tests passed.
- Checked modified Python files with the editor diagnostics tool: no errors found.

## Notes
- The configured workspace interpreter is Python 3.12.10, which differs from the repository instruction target of Python 3.12.13. The task was still validated under 3.12.10 and this version mismatch should remain visible in the completion report.
