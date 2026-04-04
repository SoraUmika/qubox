# Prompt Log

**Date:** 2026-04-04 02:29:38
**Task:** docs-and-runtime-architecture-reconciliation
**Target files:** AGENTS.md, .github/copilot-instructions.md, API_REFERENCE.md, docs/CHANGELOG.md

## Original Request

Apply three prompt-driven tasks to the live qubox repository on main: (1) produce an execution-ready refactor order and architecture summary without code changes, (2) design a declarative experiment-spec layer for QMRuntime without implementation, and (3) perform a docs-only reconciliation pass and apply straightforward doc fixes if safe. Read the governing docs and the listed live code files first, separate verified current facts from hypotheses, preserve QUA correctness constraints, and log the task when complete.

## Response / Changes Made

Verified the live session, runtime, control, measurement, and calibration architecture against the current tree; confirmed the hosted standard-experiment simulator trust gate is green; identified that explicit readout ownership is already complete and that conditional AcquireInstruction lowering remains the active QM limitation; and then applied a docs-only reconciliation patch. The patch updated AGENTS.md to point at current architecture references, fixed .github/copilot-instructions.md to stop directing agents toward a nonexistent qubox.legacy package, rewrote API_REFERENCE.md from the live export and package surfaces, and added a changelog entry for the documentation sync.

## Context

Task combined architecture review, QMRuntime design analysis, and docs reconciliation. No runtime code was changed. Validation consisted of direct file inspection, symbol searches, export-surface verification, and markdown/error checks on the edited docs. Existing markdown-style warnings remain in long-standing docs, but the new API reference and updated Copilot instructions are clean.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
