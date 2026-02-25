# GE → IQ Blob Rotated-Weight Consistency Check

Date: 2026-02-25
Notebook: `notebooks/post_cavity_experiment_context.ipynb`

## What was run

1. `ReadoutGEDiscrimination.run(..., apply_rotated_weights=True, update_measure_macro=True, persist=True, debug=True)`
2. Immediate direct IQ blob acquisition via `qubox_v2.programs.builders.readout.iq_blobs(...)`
3. `two_state_discriminator(Ig, Qg, Ie, Qe)` on the acquired IQ blob data

## Debug preflight (before iq_blobs compile/run)

- Active element/op: `resonator/readout`
- Active outputs: `[['rot_cos', 'rot_sin'], ['rot_m_sin', 'rot_cos']]`
- Bound labels include rotated triplet: `True`
- Label mapping:
  - `rot_cos -> rot_cos`
  - `rot_sin -> rot_sin`
  - `rot_m_sin -> rot_m_sin`

Weight checksums (first segment amplitudes):
- `rot_cos`: `c0=0.9161871594`, `s0=0.4007506567`
- `rot_sin`: `c0=-0.4007506567`, `s0=0.9161871594`
- `rot_m_sin`: `c0=0.4007506567`, `s0=-0.9161871594`

## Measured consistency result

GE discrimination result (same run):
- `angle_ge = 0.3729689338 rad`
- `threshold_ge = -1.0039508028e-05`
- `fidelity_ge = 73.385%`

IQ blob discriminator (immediately after GE):
- `angle_blob = -0.8550408100 rad`
- `|angle_blob|` distance to `{0, π, 2π}` = `0.8550408100 rad`
- Pass criterion `|angle_blob| < 0.05` (with π-equivalence): **FAIL**
- `threshold_blob = -3.7887985826e-05`
- `fidelity_blob = 75.39%`

## Diagnosis

`angle_blob` is significantly non-zero, so rotated-frame alignment is not being achieved in the IQ blob run.

Initial failure mode was **stale rotated weight definitions caused by store-shadowing**.

Why this pointed to stale weights (not sign error) in the first failing run:
- Labels are correctly rotated (`rot_cos/rot_sin/rot_m_sin`) and bound at runtime.
- But the actual `rot_*` coefficients correspond to an *older* angle (~0.4123 rad), not the current `angle_ge=0.3730 rad`.
- Additional sign/convention probe (re-rotating IQ data by ±`angle_ge`) did **not** bring fitted angle near zero.

So the dominant issue is not “wrong sign” and not “wrong label triplet”; it is that the numeric weight payload behind those labels is not refreshed to the latest GE angle before iq_blobs compile/run.

## Follow-up after fix (same day)

### `two_state_discriminator` semantic check

Confirmed from source that `two_state_discriminator(Ig,Qg,Ie,Qe)` computes `axis` directly from the **original** complex IQ data (`Sg = Ig + iQg`, `Se = Ie + iQe`) and reports:

- `angle = -arg(axis)`

The function then computes rotated arrays (`S*_rot`) for thresholding metrics, but the reported `angle` is based on the original data axis.

### Stale-coefficient root cause and fix

Root cause: `PulseOperationManager.get_integration_weights()` resolves volatile weights first. GE could refresh only persistent `rot_*` weights (`persist=True`), leaving stale volatile `rot_*` definitions to shadow reads/compile preflight.

Fix implemented in `ReadoutGEDiscrimination._build_rotated_weights()`:

- Always refresh runtime volatile `rot_*` definitions.
- Additionally refresh persistent `rot_*` definitions when `persist=True`.

Post-fix validation:

- Expected-from-base coefficients now exactly match actual `rot_cos/rot_sin/rot_m_sin` values for the latest GE angle.

### Current status

- **Stale rot coefficients: fixed**.
- `angle_blob` is still significantly non-zero in the immediate GE→iq_blobs check, so a **separate issue** remains (likely demod/sign/channel convention path), not stale coefficient persistence.

## Recommended next check/fix

- Ensure rotated weight creation in GE path **overrides existing `rot_*` definitions in-place** (instead of keeping prior values).
- Re-run this same GE→IQ blob check and verify:
  - `rot_*` checksums match current `cos(-angle_ge), sin(-angle_ge)`
  - `angle_blob` is near `0` (or `π` by convention)
