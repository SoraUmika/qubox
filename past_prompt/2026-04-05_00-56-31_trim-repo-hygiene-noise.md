# Prompt Log

**Date:** 2026-04-05 00:56:31
**Task:** trim-repo-hygiene-noise
**Target files:** .gitignore, API_REFERENCE.md, docs/CHANGELOG.md, qubox/experiments/config_builder.py, qubox/workflow/__init__.py, tests/test_qubox_public_api.py, tools/validate_import_surface.py, test_migration.py, test_output.txt, qubox.egg-info/PKG-INFO, qubox.egg-info/SOURCES.txt, qubox.egg-info/dependency_links.txt, qubox.egg-info/requires.txt, qubox.egg-info/top_level.txt

## Original Request

go ahead

## Response / Changes Made

Reduced low-risk repository noise without touching the active hardware/runtime paths. Cleaned the legacy ConfigBuilder compatibility module by removing mojibake/duplicate import clutter and duplicate method/script leftovers while preserving its public API, exported load_legacy_reference() on the canonical qubox.workflow surface and added a public API regression test for it, moved the root-level import verification script to tools/validate_import_surface.py, deleted the disposable root test_output.txt artifact, removed generated qubox.egg-info metadata from version control, and updated .gitignore plus API_REFERENCE.md and docs/CHANGELOG.md. Validation: c:/python312/python.exe -m pytest tests/test_qubox_public_api.py tests/test_connection_policy.py -q -ra passed with 21 passed in 11.03s; c:/python312/python.exe tools/validate_import_surface.py passed with 18 OK and 0 FAIL.

## Context

Follow-up to the read-only repo-noise review. This pass intentionally targeted the low-risk cleanup items first: root artifact clutter, the ConfigBuilder quality outlier, and documentation/API noise around the portable workflow surface. It intentionally did not remove site/ or the simulator report artifact, and it did not refactor the remaining legacy lowering/runtime seams because those are more structural and riskier.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
