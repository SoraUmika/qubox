# Prompt Log

**Date:** 2026-04-04 02:56:14
**Task:** remove-gate-model-stack-and-scan-noncore-packages
**Target files:** qubox/programs/builders/simulation.py, qubox/programs/builders/cavity.py, qubox/gates/__init__.py, qubox/gates, README.md, API_REFERENCE.md, docs/CHANGELOG.md, site_docs/api/gates.md, site_docs/architecture/package-map.md, docs/architecture_audit.md, docs/architecture/ARCHITECTURE_AUDIT.md, test_migration.py, qubox/analysis, qubox/optimization, qubox.egg-info/SOURCES.txt

## Original Request

Similarly, gates also have a lot of stuff like this. Let's remove it, then look into the codebase for anything that is not part of the core.

## Response / Changes Made

Removed the non-core gate-model stack from qubox.gates, leaving only the runtime hardware implementations and hardware base. Updated the two builder modules that still referenced the old Gate wrapper, refreshed current docs and package metadata, removed the empty qubox.analysis and qubox.optimization tombstone directories during the wider non-core scan, and validated that the repo smoke-check passes with 18/18 OK while qubox.gates.gate, qubox.gates.models, qubox.analysis, and qubox.optimization no longer resolve.

## Context

This cleanup kept the active QUA/runtime path intact. The retained gate layer is the hardware implementation path used by control.realizer and programs.circuit_compiler. The wider scan found additional non-core candidates that were not removed in this pass: qubox.gui, qubox.migration, qubox.examples, qubox.verification, qubox.autotune, and qubox.operations. Historical audit docs were annotated rather than fully rewritten.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
