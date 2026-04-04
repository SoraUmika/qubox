# Prompt Log

**Date:** 2026-04-03 00:59:01
**Task:** plan-measurement-refactor
**Target files:** past_prompt

## Original Request

I am considrign doing a major refactoring on the measure itself, please look up quanutm machines qua website (for api reference) to see hwo it works, and then come up with a plan so that it fits to our codebase nicely.

## Response / Changes Made

Researched the Quantum Machines QUA 1.2.6 measurement API and the current qubox measurement stack, then produced a repository-fit refactor plan centered on an explicit measurement IR, calibration-backed readout ownership, and measureMacro as a temporary compatibility layer. No source modules were changed.

## Context

Task was planning-only. The repo already has explicit ReadoutHandle and emit_measurement paths in most builders, but session and calibration flows still own measureMacro state and advanced QUA modes like sliced demod still bypass the abstraction.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
