# Prompt Log

**Date:** 2026-03-21 21:05:49
**Task:** explicit-hardware-definition-notebook-controls
**Target files:** qubox/compat/notebook.py, tests/test_qubox_public_api.py, API_REFERENCE.md, docs/CHANGELOG.md, notebooks/00_hardware_defintion.ipynb

## Original Request

qubox should be define such that i can actually define all the hardawre, in particular i am talking about hardware port bindings and LO, IF setttings, external devices etc , currently its using some default value , but iw ant you to have an cell in the hardware definition to expcitly allow the user to change it

## Response / Changes Made

Exposed HardwareDefinition on qubox.compat.notebook, added an explicit editable hardware-definition section to notebooks/00_hardware_defintion.ipynb for bindings, LO/IF, aliases, ADC offsets, external LO routing, and devices, and updated API_REFERENCE.md, docs/CHANGELOG.md, and the compat surface test accordingly.

## Context

Validated with pytest on Python 3.12.10 and a direct HardwareDefinition builder smoke test. Notebook diagnostics are clean. The VS Code notebook kernel auto-selected Python 3.14.3, so authoritative validation was done in the repo-configured 3.12 environment instead of executing notebook cells in-kernel.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
