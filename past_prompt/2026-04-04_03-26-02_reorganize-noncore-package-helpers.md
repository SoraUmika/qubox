# Prompt Log

**Date:** 2026-04-04 03:26:02
**Task:** reorganize-noncore-package-helpers
**Target files:** tools/program_gui.py, tools/demos/quickstart.py, tools/demos/circuit_architecture_demo.py, tools/demos/session_startup_demo.py, tools/autotune/run_post_cavity_autotune_v1_1.py, qubox/autotune/__init__.py, qubox/verification/waveform_regression.py, qubox/verification/schema_checks.py, README.md, API_REFERENCE.md, site_docs/architecture/package-map.md, docs/CHANGELOG.md

## Original Request

fix the remaindings, and also reorganize the qubox code structure so that everything is nicely organized

## Response / Changes Made

Moved non-core demo and GUI helpers out of the qubox package into top-level tools entrypoints, removed the dead qubox.gui, qubox.examples, and qubox.migration package files, added a tools autotune wrapper, cleaned verification docstrings, and synced README, API reference, package-map, and changelog to the tighter package boundary.

## Context

(none)

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
