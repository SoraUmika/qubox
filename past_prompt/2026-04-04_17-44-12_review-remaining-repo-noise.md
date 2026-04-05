# Prompt Log

**Date:** 2026-04-04 17:44:12
**Task:** review-remaining-repo-noise
**Target files:** README.md, pyproject.toml, tools/validate_standard_experiments_simulation.py, qubox/backends/qm/runtime.py, qubox/backends/qm/lowering.py, qubox/notebook/runtime.py, qubox/notebook/workflow.py, qubox/experiments/config_builder.py, qubox/docs/API_REFERENCE.md, qubox/docs/ARCHITECTURE.md, site/index.html, qubox.egg-info/PKG-INFO, tools/simulation_validation_report.json, test_output.txt, test_migration.py

## Original Request

what remains messy /noisy in this repo?

## Response / Changes Made

Performed a read-only cleanliness review focused on remaining noise after the recent safety and deprecation cleanup work. Identified the main remaining issues as legacy compatibility still sitting on core runtime paths, repo-wide warning suppression for upstream qm-qua deprecations, tracked generated/build artifacts in the repository, fragmented documentation authority across canonical/supporting/historical and package-local compatibility docs, and a low-quality outlier module in qubox/experiments/config_builder.py with mojibake and duplicate imports. No new immediate hardware-safety bug was identified in this pass; the remaining problems are primarily maintainability and repository-hygiene debt.

## Context

Read-only follow-up review after the prior architecture hardening, warning cleanup, and deprecation-removal work. The goal was to identify what still feels messy or noisy in the live repository, with emphasis on structural noise rather than already-fixed safety issues.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
