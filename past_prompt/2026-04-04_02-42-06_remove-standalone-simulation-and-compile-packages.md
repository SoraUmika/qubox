# Prompt Log

**Date:** 2026-04-04 02:42:06
**Task:** remove-standalone-simulation-and-compile-packages
**Target files:** README.md, API_REFERENCE.md, docs/CHANGELOG.md, docs/architecture_audit.md, docs/architecture/ARCHITECTURE_AUDIT.md, site_docs/api/gates.md, site_docs/architecture/package-map.md, test_migration.py, pyproject.toml, qubox.egg-info/requires.txt, qubox.egg-info/SOURCES.txt, qubox/compile, qubox/simulation

## Original Request

Remove the non-hardware simulation and standalone compile surfaces from qubox, for example the simulation and compile packages under qubox, while keeping the QM-hosted hardware-program simulation path because that stays in qubox. Clean up the repo so those numerical-simulation APIs are no longer part of qubox and can move to cqed_sim instead.

## Response / Changes Made

Removed the dormant qubox.compile and qubox.simulation package trees, deleted their optional dependency metadata, updated current docs and the migration import check to reflect the new runtime boundary, and preserved the QM-hosted simulation path used for compiled-program validation. Validation confirmed that qubox still imports, QuboxSimulationConfig still imports, and qubox.compile / qubox.simulation no longer resolve as packages.

## Context

This was a breaking-scope cleanup, not a QUA behavior change. The retained simulation surface is the QM-hosted program simulation path in qubox.hardware.program_runner. Historical architecture audit documents were annotated rather than fully rewritten, while current docs and package metadata were updated directly.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
