# Prompt Log

**Date:** 2026-03-23 15:48:07
**Task:** mixer_calibration_gain_retune
**Target files:** notebooks/00_hardware_defintion.ipynb,notebooks/01_mixer_calibrations.ipynb,samples/post_cavity_sample_A/config/hardware.json,docs/CHANGELOG.md

## Original Request

User asked to initialize notebook 00 hardware definition and modify mixer gains so notebook 01 auto mixer SA validation reports about -30 dBm target power for all calibrated elements except resonator, which should remain near -40 dBm on purpose.

## Response / Changes Made

Updated notebooks/00_hardware_defintion.ipynb to set default gains matching the desired CW validation power plan, updated notebooks/01_mixer_calibrations.ipynb to apply the same per-element auto-calibration gain overrides by default, and aligned samples/post_cavity_sample_A/config/hardware.json so fresh session bootstrap picks up the same gains from disk. Added a changelog entry documenting the retuning.

## Context

The current auto SA validation report showed resonator_gf, storage_gf, and transmon below the desired CW target power. The fix keeps resonator at -10 dB gain to stay near -40 dBm while raising transmon to 3 dB, storage_gf to 12 dB, and resonator_gf to 14 dB so notebook 01 targets approximately -30 dBm after notebook 00 initialization or a fresh session reopen.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
