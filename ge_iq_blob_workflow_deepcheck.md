# GE -> IQ_blob workflow deep check (before/after overrides)

Date: 2026-02-25
Notebook: `notebooks/post_cavity_experiment_context.ipynb`

## What was checked

1. **PulseOperationManager weights before/after GE override**
2. **measureMacro state before/after GE analyze**
3. **IQ_blob discriminator angle using direct `builders.iq_blobs()` run**
4. **Compile-time config vs POM consistency**
5. **A/B compile tests with manual rot_* coefficient changes**

## Key observations

### A) Before/after override in GE workflow

From the deep trace cell:

- **Before GE run**: `measureMacro` active outputs were rotated labels (`rot_cos/rot_sin/rot_m_sin`) with prior rot coefficients.
- **After GE run but before analyze**: outputs switched to base labels (`cos/sin/minus_sin`) as expected for blob acquisition.
- **After GE analyze**: outputs switched back to rotated labels and `ro_disc_params.angle/hash` updated to the latest GE values.

So the GE state transition itself is working as coded.

### B) POM coefficients are updated

After GE analyze, POM `rot_*` first-segment coefficients changed and matched the latest GE angle-driven values.

### C) Config overlay sync

After patching `_build_rotated_weights` to call `config_engine.merge_pulses(...)`, built config now matches POM at GE time:

- `cfg.integration_weights['rot_*']` == `POM rot_*`

So stale **config overlay** (from earlier runs) was fixed.

### D) IQ_blob still shows non-zero angle

Despite the above, direct `iq_blobs()` runs still produce non-zero fitted angle (about `-0.9 rad`) instead of ~0.

### E) Manual compile-time A/B tests

Changing `rot_*` coefficients and forcing `merge_pulses` before compile changes the result only slightly (small angle delta), not enough to explain expected alignment.

This means the mismatch is no longer explained by stale POM/config values alone.

## Diagnosis (current)

The requested checks confirm:

- GE override updates **do** happen in POM.
- measureMacro state update to rotated labels **does** happen.
- Built config can be made consistent with POM.

But GE->IQ_blob angle remains far from 0, indicating an additional issue in the runtime measurement chain, likely one of:

1. demod/integration-weight convention mismatch in how `dual_demod.full` combines channels versus assumed rotation formula,
2. effective readout path not using the expected quadrature combination for angle comparison,
3. live-QM configuration lifecycle nuances beyond POM/config overlay sync.

## Practical next step

Run a focused demod-convention validation against the exact QUA demod expression used by `measureMacro.measure(...)` and derive the required rot formula from measured `(Ig,Qg,Ie,Qe)` to close the remaining ~0.9 rad offset.
