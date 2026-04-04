# Prompt Log

**Date:** 2026-04-04 03:10:00
**Task:** reorganize-noncore-package-helpers
**Target files:** tools/program_gui.py, tools/demos/quickstart.py, tools/demos/circuit_architecture_demo.py, tools/demos/session_startup_demo.py, tools/autotune/run_post_cavity_autotune_v1_1.py, qubox/gui, qubox/examples, qubox/migration, qubox/autotune/__init__.py, qubox/verification/waveform_regression.py, qubox/verification/schema_checks.py, README.md, API_REFERENCE.md, site_docs/architecture/package-map.md, docs/CHANGELOG.md

## Original Request

fix the remaindings, and also reorganize the qubox code structure so that everything is nicely organized

## Response / Changes Made

Moved the non-core demo and GUI helper scripts out of the `qubox` package into top-level `tools/` entrypoints, removed the dead `qubox.gui`, `qubox.examples`, and `qubox.migration` package files, added a top-level autotune wrapper entrypoint under `tools/autotune/`, cleaned the remaining verification docstrings to use the current `qubox` import path, and updated the canonical docs to state that non-core scripts now live under `tools/` rather than the `qubox` import namespace.

## Context

This pass kept the core runtime path intact: `qubox.operations` and `qubox.verification` remain because they are still wired into `session.ops` and notebook-facing verification flows. The autotune implementation was not fully relocated because it is a large experimental workflow module, but the supported script entrypoint now exists under `tools/autotune/` and the internal package docstring marks it as implementation detail.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [x] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks or equivalent user-facing docs)
- [x] Focused import smoke validation for removed package names and new tool entrypoints
- [x] Static error check on changed Python files
