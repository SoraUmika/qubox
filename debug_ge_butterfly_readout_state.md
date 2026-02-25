# GE → Butterfly readout-state mismatch debug report

## Scope
- Investigated GE (`ReadoutGEDiscrimination`) → Butterfly (`ReadoutButterflyMeasurement`) mismatch and rotated-weight usage.
- Constraint honored: no default behavior changes; only debug-gated instrumentation and minimal bug fix.

## Root cause(s)
1. **Deterministic signature-hash mismatch bug (confirmed)**
   - GE writes signature with `fidelity_definition="assignment_fidelity_balanced_accuracy_percent"`.
   - Butterfly recomputes signature from `measureMacro._ro_disc_params["fidelity_definition"]`.
   - `measureMacro._update_readout_discrimination(...)` did not persist `fidelity_definition`, so Butterfly saw `None`.
   - Result: hash mismatch even when element/op/pulse/weights/angle/threshold match.

2. **Strict-mode rotated-weight persistence ambiguity (likely secondary contributor)**
   - GE logs: `Strict mode: rotated weight/macro updates emitted as patch intent`.
   - In strict mode, rotated weights may not be regenerated inline unless patch is applied.
   - Butterfly can still bind `rot_*` labels, but those label definitions may be stale relative to latest GE angle.

3. **Artifact persistence prevents full offline shot-level replay for this run**
   - Runtime `.npz` for the failing run contains only `acceptance_rate`, `average_tries`.
   - Shot-level arrays (`I1/Q1/...`) were dropped by persistence policy, so artifact-only M1 replay is not possible post hoc.

## Reproduction steps
1. Run GE discrimination (Notebook Cell 68) with:
   - `update_measure_macro=True`, `apply_rotated_weights=True`, `persist=True`.
2. Run Butterfly measurement (Notebook Cell 70) with:
   - `update_measure_macro=True`, `use_stored_config=True`.
3. Observe logs:
   - `Butterfly measureMacro sync applied ... weights=['rot_cos','rot_sin','rot_m_sin']`
   - `Butterfly readout state mismatch: GE hash=..., butterfly hash=...`
   - `Skipping stored post-select config ... (hash_mismatch)`
   - fallback to `policy='BLOBS'`.

## Evidence
- Failing run hashes:
  - GE hash: `a2ffa3daf42c0470`
  - Butterfly hash: `44e218e1234507f1`
- Hash reconstruction check (offline from artifacts):
  - Recomputed GE canonical hash = `a2ffa3daf42c0470` (exact match)
  - Recomputed with only `fidelity_definition=None` = `44e218e1234507f1` (exact Butterfly hash)
  - Therefore mismatch field is concretely `fidelity_definition`.
- Performance mismatch from run artifacts/logs:
  - GE reference fidelity: `0.6976` (fraction)
  - Butterfly `F`: `0.5775`
  - Delta: `~0.1202` (12.02%)
- Persistence evidence:
  - runtime artifact `butterflyMeasurement_20260225_140017.npz` keys: only `acceptance_rate`, `average_tries`
  - calibration run file reports dropped fields including `metrics.S1_g`, `metrics.S1_e`.

## BLOBS frame check
- `PostSelectionConfig.from_discrimination_results(...)` uses **rotated** centers (`rot_mu_g/e`) as `Ig/Qg/Ie/Qe`.
- QUA `sequenceMacros.post_select(..., policy='BLOBS')` compares passed `I,Q` directly to those centers.
- Butterfly builder uses `I0,Q0` from `measureMacro.measure(...)` for BLOBS acceptance.
- Therefore frame consistency is expected **if** `measureMacro` is using the same rotated demod weights at compile time.

## Code changes made (minimal)
1. **Bug fix (minimal, default-safe):**
   - `qubox_v2/programs/macros/measure.py`
   - Added `fidelity_definition` field to `_ro_disc_params` and persist it in `_update_readout_discrimination(...)`.
   - Effect: removes false GE/BF hash mismatch caused solely by missing field.

2. **Debug-only instrumentation (no default behavior change):**
   - `qubox_v2/experiments/calibration/readout.py`
   - Added `debug: bool=False` to GE and Butterfly `run(...)`.
   - GE debug: logs full GE signature dict.
   - Butterfly debug:
     - logs GE signature dict, Butterfly signature dict, and field-by-field diff,
     - logs compile preflight (element/op/pulse/active outputs),
     - verifies integration-weight existence in QM config,
     - logs short weight checksums (`first3`, `sum`, `len`) for each active weight label,
     - logs BLOBS policy/frame details.
    - Added strict-mode warning-only guard:
       - warns when GE requested `apply_rotated_weights=True` in strict mode (patch intent pending) and Butterfly is about to run with `rot_*` labels.
       - warning includes concrete next step: apply orchestrator patch + rerun GE→Butterfly.
   - Added debug-only runtime snapshot writer in Butterfly to persist shot-level arrays for offline replay on future debug runs.
       - path: `artifacts/debug_snapshots/butterfly_debug_<timestamp>.npz`
       - companion metadata includes runtime discriminator params (`threshold`, `angle`, `fidelity_definition`, active output labels).

## Example debug output after fix (hashes match)
```text
GE signature dict: {"element":"resonator","operation":"readout","pulse":"readout_pulse",...,
                              "fidelity_definition":"assignment_fidelity_balanced_accuracy_percent",
                              "hash":"a2ffa3daf42c0470"}
Butterfly signature dict: {"element":"resonator","operation":"readout","pulse":"readout_pulse",...,
                                        "fidelity_definition":"assignment_fidelity_balanced_accuracy_percent",
                                        "hash":"a2ffa3daf42c0470"}
GE vs Butterfly signature field diff: {}
readout_state_match=True
Butterfly compile weight label 'rot_cos': mapped_weight=rot_cos_w_resonator in_mapping=True checksum={..."exists": true,...}
Butterfly compile weight label 'rot_sin': mapped_weight=rot_sin_w_resonator in_mapping=True checksum={..."exists": true,...}
Butterfly compile weight label 'rot_m_sin': mapped_weight=rot_m_sin_w_resonator in_mapping=True checksum={..."exists": true,...}
```

## Recommended minimal fix options
1. **Keep implemented fix** (recommended)
   - Persist `fidelity_definition` in measureMacro discrimination state.
   - This addresses the concrete false hash mismatch root cause.

2. **For strict mode, ensure rotated-weight patch is actually applied before Butterfly**
   - Either apply orchestrator patch between GE and BF, or add explicit warning/guard when `apply_rotated_weights=True` but strict-mode patch not committed.
   - Minimal and behavior-preserving as a warning-only path.

3. **Enable debug run when validating regressions**
   - Run GE/BF once with `debug=True`.
   - Use generated debug logs + `butterfly_debug_*.npz` to perform exact offline M1 replay and disambiguate:
     - runtime path issue vs genuine readout drift.

## Regression-test checklist
1. GE then Butterfly with `debug=True`.
2. Confirm `readout_state_match=True` and hashes equal.
3. Confirm compile preflight reports active weights `rot_cos/rot_sin/rot_m_sin` with expected checksums.
4. Replay offline M1 from debug snapshot and compare with reported Butterfly `F`.
5. Validate no changes in default behavior when `debug=False`.
