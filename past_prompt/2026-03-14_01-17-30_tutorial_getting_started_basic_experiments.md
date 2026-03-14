# Prompt Log

## Timestamp
2026-03-14 01:17:30 America/Chicago

## Request
Create a new tutorial Jupyter notebook under `tutorials/` for the qubox repository that teaches a new user how to start a session, inspect saved artifacts, run baseline experiments, perform calibration workflows, preview/apply patches, and understand outputs. Use the real current API, inspect the repo first, keep the notebook runnable, and make any fixes minimal.

## Work Performed
- Audited the current public session, experiment, artifact, and calibration APIs across `README.md`, `API_REFERENCE.md`, `standard_experiments.md`, `qubox`, `qubox_v2`, `qubox_tools`, and the existing notebooks.
- Added a new onboarding tutorial notebook at `tutorials/01_getting_started_basic_experiments.ipynb`.
- Extended `qubox.compat.notebook` with notebook-facing exports for `RunResult`, `AnalysisResult`, `ProgramBuildResult`, and `save_run_summary` so the tutorial could stay under the `qubox` namespace while still using real runtime result and artifact helpers.
- Updated `API_REFERENCE.md` to document those notebook-facing compatibility imports.
- Updated `docs/CHANGELOG.md` with the new tutorial and notebook compat additions.
- Added assertions to `tests/test_qubox_public_api.py` for the new compat surface.

## Validation
Using `E:\Program Files\Python311\python.exe`:
- `pytest tests/test_qubox_public_api.py -q` passed.
- `tools/validate_notebooks.py --max-code-cells 12 tutorials/01_getting_started_basic_experiments.ipynb` passed.
- `tools/validate_notebooks.py --max-code-cells 20 tutorials/01_getting_started_basic_experiments.ipynb` passed.
- `tools/validate_notebooks.py --max-code-cells 24 tutorials/01_getting_started_basic_experiments.ipynb` passed, including the cleanup cell.
- `rg -n "qubox_v2" tutorials/01_getting_started_basic_experiments.ipynb` returned no source matches.

## Notes
- The tutorial intentionally uses `CONNECT_QM=True` and `RUN_HARDWARE=False` by default. That keeps build-time inspection real while avoiding fresh experiment execution unless the user opts in.
- The tutorial restores the original in-memory calibration snapshot before closing the session when `APPLY_PATCHES=False`, so the temporary `qb_therm_clks` tutorial setup does not persist accidentally.
- Plot cells emit `FigureCanvasAgg is non-interactive` warnings during CLI validation because the validator runs outside Jupyter; the notebook itself remains valid and runnable.
