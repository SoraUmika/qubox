# Prompt Log

**Date:** 2026-03-21 21:24:30
**Task:** devices-schema-validation-compatibility-fix
**Target files:** qubox/schemas.py, qubox/legacy/core/schemas.py, tests/test_schemas.py, docs/CHANGELOG.md

## Original Request

run check validation check on 00_hardware_defintiion.ipynb, fix any errors,then write 01_mixer_calibrations.ipynb and ensure it runs

## Response / Changes Made

Updated schema validation so devices.json accepts the flat top-level device map used by the runtime and by HardwareDefinition. This removed the false sample-level validation failure in notebooks/00_hardware_defintion.ipynb. Added targeted tests and re-ran the notebook validation cell successfully.

## Context

Discovered while replaying notebook 00: devices.json loaded correctly at runtime but failed schema validation because the checker still required a wrapped top-level devices key.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
