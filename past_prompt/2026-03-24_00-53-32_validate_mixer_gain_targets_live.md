# Prompt Log

**Date:** 2026-03-24 00:53:32
**Task:** validate_mixer_gain_targets_live
**Target files:** notebooks/00_hardware_defintion.ipynb,notebooks/01_mixer_calibrations.ipynb,samples/post_cavity_sample_A/config/hardware.json,docs/CHANGELOG.md

## Original Request

User asked to run the notebook 00 to notebook 01 flow end-to-end, ensure notebook 01 sees the updated gains from notebook 00, run the auto mixer calibration, and verify that the CW post-check target powers land near -30 dBm for all outputs except resonator, which should remain near -40 dBm.

## Response / Changes Made

Configured both notebooks on the workspace .venv kernel, reran notebook 00 through the hardware-definition cell, persisted the sample hardware definition from notebook 00, then ran notebook 01 auto mixer calibration twice. The first live run showed storage_gf and resonator_gf were too hot, so their gains were reduced from 12.0/14.0 dB to 6.5/7.5 dB in notebook 00, notebook 01, and the sample hardware.json. After persisting from notebook 00 again and rerunning notebook 01 auto calibration, the CW post-check reached: resonator_gf -29.86 dBm, storage -30.25 dBm, storage_gf -29.78 dBm, resonator -40.48 dBm, transmon -29.95 dBm. Auto calibration controller summary reported status=ok for all elements.

## Context

The live verification showed that notebook 00 and notebook 01 were structurally wired correctly, but the first gain plan overshot the GF outputs. The validated steady-state gains are resonator -10.0 dB, transmon 3.0 dB, storage 0.0 dB, storage_gf 6.5 dB, and resonator_gf 7.5 dB. A temporary notebook 00 persistence cell was inserted only for execution and then removed once the sample config had been written from notebook 00.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
