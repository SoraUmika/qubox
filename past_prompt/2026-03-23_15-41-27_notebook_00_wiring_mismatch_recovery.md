# Prompt Log

**Date:** 2026-03-23 15:41:27
**Task:** notebook_00_wiring_mismatch_recovery
**Target files:** notebooks/00_hardware_defintion.ipynb,qubox/devices/device_manager.py,tests/test_schemas.py,docs/CHANGELOG.md

## Original Request

User reported that notebooks/00_hardware_defintion.ipynb no longer ran after hardware-definition changes and showed a ContextMismatchError due to a stale calibration wiring revision. Investigate the failure, preserve calibration safety, make the notebook runnable again, and validate the fix. After notebook recovery exposed a second runtime failure in DeviceManager when reading schema-versioned devices.json, fix that loader bug and verify notebook execution.

## Response / Changes Made

Updated notebooks/00_hardware_defintion.ipynb so session bootstrap handles wiring-revision ContextMismatchError by backing up the stale cooldown calibration.json, removing it, and retrying the session open against the current hardware definition. Fixed qubox/devices/device_manager.py to load schema-versioned devices.json files by ignoring metadata entries, accepting flat or wrapped device maps, and preserving schema_version on save. Added regression tests in tests/test_schemas.py and validated with targeted pytest plus a notebook rerun through session open, preflight, and the reporting cell.

## Context

Root cause chain: hardware.json changed, wiring revision changed, strict calibration-store validation correctly rejected the stale cooldown calibration. Notebook recovery needed to be explicit and local rather than weakening global safety checks. That retry then exposed a second bug where DeviceManager treated top-level schema_version metadata as a device spec. Validation included targeted pytest and rerunning notebook 00 after restarting the kernel.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
