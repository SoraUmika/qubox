# qubox Refactor Verification

Date: 2026-03-13

## Verdict

The earlier major `qubox` refactor was only partially completed.

It added a new `qubox` facade and some new documentation/tests, but it did not
fully replace the working `qubox_v2_legacy` runtime architecture, did not finish the
rename consistently, and did not separate analysis concerns into a dedicated
package.

## Fully Completed

- A new `qubox` package exists with `Session`, `Sequence`, `QuantumCircuit`,
  sweep, acquisition, and calibration proposal facades.
- Experiment-template and custom-sequence style entry points were prototyped.
- Public-facing documentation for the `qubox` facade was added.
- Basic tests for the `qubox` facade were added.
- Representative notebooks were partially updated toward the new facade.

## Partially Completed

- Experiment templates, sequence-level custom control, and `QuantumCircuit`
  support exist, but largely as a facade over the existing `qubox_v2_legacy` stack.
- Architectural cleanup happened at the wrapper level, not as a full runtime
  consolidation.
- Rename direction toward `qubox` was started in docs and packaging metadata,
  but the mature execution path still lives in `qubox_v2_legacy`.
- Notebook migration was partial: startup paths changed, but the notebooks
  still relied on the legacy experiment classes underneath.

## Missed or Implemented Superficially

- `qubox_v2_legacy` was not actually retired as the execution-facing API.
- Multiple overlapping runtime abstractions still coexist.
- Analysis code remained inside `qubox_v2_legacy.analysis` until this follow-up task.
- The README and package messaging overstated how complete the `qubox`
  migration was.
- The previous pass did not provide a clean compatibility story for users who
  still depend on `qubox_v2_legacy.analysis.*`.

## Corrective Actions Taken In This Follow-Up

- Created `qubox_tools` as the dedicated analysis package.
- Moved fitting, plotting, post-processing, and optimization code into
  `qubox_tools`.
- Preserved `qubox_v2_legacy.analysis.*` and `qubox_v2_legacy.optimization.*` through
  compatibility wrappers.
- Kept execution ownership in `qubox_v2_legacy`.
- Updated repository-level docs so they no longer claim the `qubox` runtime
  migration is complete.
- Added notebook-local `qubox_tools` sanity cells and explicit hardware
  boundary markers.
- Added notebook validation tooling and tests covering the extracted analysis
  surface.
- Re-ran validation with `E:\Program Files\Python311\python.exe` and confirmed
  that the extracted analysis layer also passes an existing `qubox_v2_legacy`
  workflow-safety compatibility test suite.
