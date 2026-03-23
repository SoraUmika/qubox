# Prompt Log: Remove Legacy cqed_params from Notebooks

**Date:** 2026-03-22 14:44
**Task:** Remove all legacy cqed_params code, comparison logic, and legacy analysis imports from notebooks 00–06

## Original Prompt

Remove all legacy cqed_params code, references, and comparison logic from every notebook. Notebooks should rely only on the current parameter/configuration path and should no longer import, check, or compare against any legacy cqed_params structures. Also make notebooks 00–06 workflow simpler and easier to follow.

## Changes Made

### `notebooks/05_qubit_spectroscopy_pulse_calibration.ipynb`
- **Cell 12**: Replaced `from qubox.legacy.analysis.analysis_tools import project_complex_to_line_real` → `from qubox_tools.algorithms.transforms import project_complex_to_line_real`

### `notebooks/06_coherence_experiments.ipynb`
- **Cell 4**: Replaced two-step `RUNTIME_QB_THERM_CLKS` / `COHERENCE_QB_THERM_CLKS` fallback pattern with single `QB_THERM_CLKS = int(getattr(attr, "qb_therm_clks", 10000) or 10000)`. Removed "resolved fallback" print.
- **Cell 6**: Removed entire `if RUNTIME_QB_THERM_CLKS <= 0:` block that patched `cqed_params.transmon.qb_therm_clks` via `SetCalibration`. Updated all `COHERENCE_QB_THERM_CLKS` references to `QB_THERM_CLKS`.
- **Cell 8**: Replaced `from qubox.legacy.analysis import cQED_models` → `from qubox_tools.fitting import cqed as cQED_models`. Replaced `from qubox.legacy.analysis.analysis_tools import project_complex_to_line_real` → `from qubox_tools.algorithms.transforms import project_complex_to_line_real`.

### `notebooks/00_hardware_defintion.ipynb`
- **Cell 7** (markdown): Removed `cqed_params.json` from the list of files that `WRITE_SAMPLE_HARDWARE_DEFINITION` overwrites.
- **Cell 8**: Removed `sample_cqed_params_path` variable, `"cqed_params_path"` from preview dict, `hardware_definition.save_cqed_params(...)` call, and `print(f"cqed_params.json -> ...")` line.
- **Cell 12**: Removed `"cqed_params.json"` from the session-state config file copy loop.

## Canonical replacements used
| Legacy import | Modern replacement |
|---|---|
| `qubox.legacy.analysis.analysis_tools.project_complex_to_line_real` | `qubox_tools.algorithms.transforms.project_complex_to_line_real` |
| `qubox.legacy.analysis.cQED_models` | `qubox_tools.fitting.cqed` (as `cQED_models`) |

## Assumptions
- `qubox_tools.fitting.cqed` exposes `T1_relaxation_model`, `T2_ramsey_model`, `T2_echo_model` with identical signatures (confirmed by grepping `qubox_tools/fitting/cqed.py`)
- `qubox_tools.algorithms.transforms.project_complex_to_line_real` is the canonical non-legacy implementation (confirmed by source inspection)
- `cqed_params.json` is not required by `SessionState.from_config_dir()` or `validate_config_dir()` (confirmed: file_order list in cell 12 does not include it, all checks use `if src.exists()`)
- The `cqed_params.transmon.qb_therm_clks` patch path was targeting the old cqed_params store; the experiments now receive `qb_therm_clks` directly as a run parameter

## Validation
- All 7 notebooks checked for remaining `cqed_params` and `from qubox.legacy.analysis` references — none found
- `QB_THERM_CLKS` used consistently in notebook 06 cells 4 and 6
- No QUA changes; no new abstractions introduced
