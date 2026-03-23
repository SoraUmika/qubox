# Prompt Log

**Date:** 2026-03-21 20:56:05
**Task:** sequential-notebook-workflow-bootstrap
**Target files:** AGENTS.md, docs/CHANGELOG.md, notebooks/00_hardware_defintion.ipynb

## Original Request

modify AGENTS.md to set this changes: I have decided to perform differnet experiemtns.calibration process in a seperate notebook, so for any later agent tasks taht erquires to perform an experiment, or a new experiment type, it shall create  a new notebook in notebooks, , there should be standard experiments that is meant to be perform sequentially, so we shall start thoese first, so for example, we will always start initalizing the hardware for every new expeiremtns/cooldown, so we will define 00_hardware_defintion.ipynb , note the filename format {XX_Purpose} ,  currently notebooks/post_cavity_experiments.context.ipynb contains all the relevant experimetns, apply the relevant changes for AGENTS.md and then apply me the first notebook

## Response / Changes Made

Updated AGENTS.md with a numbered notebook workflow for sequential experiment execution, appended a CHANGELOG entry, and created notebooks/00_hardware_defintion.ipynb by extracting the shared hardware-definition, sample or cooldown setup, session-open, and preflight bootstrap flow from the existing post_cavity_experiment_context notebook.

## Context

Workflow documentation change only; no QUA program or runtime source code changed. Notebook JSON validity was checked with PowerShell ConvertFrom-Json, and VS Code reported no errors for AGENTS.md or the new notebook.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
