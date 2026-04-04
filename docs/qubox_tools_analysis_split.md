# qubox_tools Analysis Split

> **Historical document (2026-03-13).** This records the original extraction of
> analysis code from `qubox_v2_legacy` into `qubox_tools`. The `qubox_v2_legacy`
> package referenced here has since been fully eliminated. The import paths in
> the mapping table below are historical; all analysis code now lives in
> `qubox_tools` and the current package map is in
> [Architecture — Package Map](../site_docs/architecture/package-map.md).

Date: 2026-03-13

## Purpose

`qubox_tools` is the canonical package for reusable analysis logic. It is meant
to be useful both with `qubox_v2_legacy` outputs and in standalone notebook/data
analysis workflows.

## Package Boundary

`qubox_v2_legacy` owns:

- session/runtime concepts
- experiment definitions and execution
- calibration orchestration and persistence
- hardware / QM interaction
- result creation and artifacts

`qubox_tools` owns:

- fit models and fit routines
- cQED analysis models
- plotting helpers
- post-processing transforms
- discrimination and metric helpers
- optimization utilities used by analysis/calibration

Still retained in `qubox_v2_legacy` for runtime coupling reasons:

- `qubox_v2_legacy.analysis.cQED_attributes`
- `qubox_v2_legacy.analysis.pulseOp`

## Extracted Structure

```text
qubox_tools/
  fitting/
    routines.py
    models.py
    cqed.py
    pulse_train.py
    calibration.py
  plotting/
    common.py
    cqed.py
  algorithms/
    core.py
    transforms.py
    post_process.py
    post_selection.py
    metrics.py
  optimization/
    bayesian.py
    local.py
    stochastic.py
  data/
    containers.py
  compat/
    legacy_analysis.py
```

## Compatibility Mapping

| Legacy import | New canonical import |
|---|---|
| `qubox_v2_legacy.analysis.fitting` | `qubox_tools.fitting.routines` |
| `qubox_v2_legacy.analysis.models` | `qubox_tools.fitting.models` |
| `qubox_v2_legacy.analysis.cQED_models` | `qubox_tools.fitting.cqed` |
| `qubox_v2_legacy.analysis.pulse_train_models` | `qubox_tools.fitting.pulse_train` |
| `qubox_v2_legacy.analysis.calibration_algorithms` | `qubox_tools.fitting.calibration` |
| `qubox_v2_legacy.analysis.plotting` | `qubox_tools.plotting.common` |
| `qubox_v2_legacy.analysis.cQED_plottings` | `qubox_tools.plotting.cqed` |
| `qubox_v2_legacy.analysis.algorithms` | `qubox_tools.algorithms.core` |
| `qubox_v2_legacy.analysis.analysis_tools` | `qubox_tools.algorithms.transforms` |
| `qubox_v2_legacy.analysis.post_process` | `qubox_tools.algorithms.post_process` |
| `qubox_v2_legacy.analysis.post_selection` | `qubox_tools.algorithms.post_selection` |
| `qubox_v2_legacy.analysis.metrics` | `qubox_tools.algorithms.metrics` |
| `qubox_v2_legacy.analysis.output` | `qubox_tools.data.containers` |
| `qubox_v2_legacy.optimization.optimization` | `qubox_tools.optimization.bayesian` |
| `qubox_v2_legacy.optimization.smooth_opt` | `qubox_tools.optimization.local` |
| `qubox_v2_legacy.optimization.stochastic_opt` | `qubox_tools.optimization.stochastic` |

## Dependency Policy

- `qubox_tools` now imports lazily at the package level.
- Optional dependencies such as `pandas`, `pycma`, and `scikit-optimize` are
  handled lazily or with informative runtime errors.
- Notebook validation in this task was done without the full QM stack.

## Notebook Validation Boundary

The notebooks now start with a hardware-independent `qubox_tools` sanity cell.

Final verification for this task used:

- `E:\Program Files\Python311\python.exe`
- Python `3.11.8`

Sequential startup validation results:

- `notebooks/post_cavity_experiment_context.ipynb`: first 4 code cells executed successfully, `executed=[2, 4, 6, 8]`
- `notebooks/post_cavity_experiment_quantum_circuit.ipynb`: first 5 code cells executed successfully, `executed=[3, 5, 6, 7, 8]`

What was verified in those startup slices:

- `qubox_tools` import and fit sanity cell
- notebook import cells
- sample registry setup
- session/context startup
- quantum-circuit helper bootstrap

What was intentionally not run end-to-end:

- the later experiment and calibration sections that would trigger full live
  hardware execution rather than startup validation
