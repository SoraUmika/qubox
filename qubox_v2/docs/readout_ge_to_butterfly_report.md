# Readout GE Discrimination → Butterfly Measurement: Full Workflow Report

**Date**: 2026-02-25
**Scope**: Complete workflow from `ReadoutGEDiscrimination` through
`ReadoutButterflyMeasurement`, including legacy comparison and inconsistency analysis.
**Status**: Analysis document (no code changes).

---

## Table of Contents

1. [File Map and Call Graphs](#1-file-map-and-call-graphs)
2. [Hardware-Level Experimental Sequences](#2-hardware-level-experimental-sequences)
3. [Physics Intent](#3-physics-intent)
4. [Mathematics and Code Locations](#4-mathematics-and-code-locations)
5. [Data Products and Interfaces](#5-data-products-and-interfaces)
6. [Legacy Comparison](#6-legacy-comparison)
7. [Inconsistencies and Root Causes](#7-inconsistencies-and-root-causes)
8. [Open Questions / Missing Information](#8-open-questions--missing-information)

---

## 1. File Map and Call Graphs

### 1.1 File Inventory

| File | Role |
|------|------|
| `qubox_v2/experiments/calibration/readout.py` | Experiment classes: `ReadoutGEDiscrimination`, `ReadoutButterflyMeasurement`, `CalibrateReadoutFull` |
| `qubox_v2/programs/builders/readout.py` | QUA program factories: `iq_blobs()`, `readout_butterfly_measurement()` |
| `qubox_v2/programs/macros/measure.py` | `measureMacro` singleton: QUA readout code generation, discrimination/quality state |
| `qubox_v2/programs/macros/sequence.py` | `sequenceMacros`: `post_select()`, `conditional_reset_ground()`, `conditional_reset_excited()` |
| `qubox_v2/analysis/analysis_tools.py` | `two_state_discriminator()`: IQ blob analysis, rotation, thresholding |
| `qubox_v2/analysis/algorithms.py` | `estimate_intrinsic_sigmas_mog()`, `optimal_threshold_empirical()` |
| `qubox_v2/analysis/metrics.py` | `butterfly_metrics()`: F, Q, V, confusion/transition matrices |
| `qubox_v2/calibration/orchestrator.py` | `CalibrationOrchestrator.apply_patch()`: patch commit + sync |
| `qubox_v2/calibration/models.py` | `DiscriminationParams`, `ReadoutQuality`: typed calibration models |
| `qubox_v2/calibration/store.py` | `CalibrationStore`: canonical persistence layer |

### 1.2 ReadoutGEDiscrimination Call Graph

```
ReadoutGEDiscrimination.run()                          [readout.py:354]
  ├── ExperimentBase.set_standard_frequencies()         [experiment_base.py]
  ├── measureMacro.set_pulse_op(unrotated_weights)      [measure.py]
  ├── session.burn_pulses()                             [session.py]
  ├── builders.iq_blobs(qb_el, r180, n_runs, ...)      [builders/readout.py:10]
  │     └── (QUA) per iteration:
  │           ├── measure |g⟩ → save(Ig, Qg)
  │           ├── wait(qb_therm_clks)
  │           ├── play(r180, qb_el) [prep |e⟩]
  │           └── measure |e⟩ → save(Ie, Qe)
  └── ProgramRunner.run_program(prog, n_total)          [program_runner.py]

ReadoutGEDiscrimination.analyze()                      [readout.py:487]
  ├── two_state_discriminator(Ig, Qg, Ie, Qe)          [analysis_tools.py:345]
  │     ├── estimate_intrinsic_sigmas_mog(Sg, Se)       [algorithms.py:372]
  │     │     ├── compute axis = (mu_e - mu_g) / |delta|
  │     │     ├── project to 1D along axis
  │     │     └── EM: fit 2-component 1D Gaussian mixture
  │     ├── rotate blobs: S_rot = S * conj(axis)
  │     └── optimal_threshold_empirical(Ig_rot, Ie_rot) [algorithms.py:604]
  │           └── sweep candidate thresholds → min misclass
  ├── _build_rotated_weights()                          [readout.py:747]
  │     ├── C = cos(-angle), S = sin(-angle)
  │     ├── build rot_cos, rot_sin, rot_m_sin segments
  │     └── POM.add_int_weight_segments(...)
  ├── _apply_rotated_measure_macro()                    [readout.py:817]
  │     └── measureMacro.set_pulse_op(rotated weights)
  ├── _apply_discrimination_measure_macro()             [readout.py:866]
  │     ├── measureMacro._update_readout_discrimination(payload)
  │     ├── stamp qbx_readout_state hash                [readout.py:914]
  │     └── optional: PostSelectionConfig.from_discrimination_results()
  └── optional: guarded_calibration_commit()            [experiment_base.py]
```

### 1.3 ReadoutButterflyMeasurement Call Graph

```
ReadoutButterflyMeasurement.run()                      [readout.py:1601]
  ├── threshold sync: if None → sync_from_calibration() [readout.py:1624]
  ├── qbx_readout_state hash comparison                 [readout.py:1647]
  │     └── _current_readout_state_signature()           [readout.py:1772]
  ├── post-selection fallback chain:                     [readout.py:1665]
  │     ├── 1. explicit prep_policy param
  │     ├── 2. use_stored_config + hash match → mm.get_post_select_config()
  │     ├── 3. blob params from GE → BLOBS(k_blob=2.0)
  │     └── 4. threshold fallback → THRESHOLD policy
  ├── _pick_weight_triplet()                             [readout.py:1799]
  ├── builders.readout_butterfly_measurement(            [builders/readout.py:323]
  │       qb_el, r180, policy, kwargs, MAX_TRIALS, n_shots)
  │     └── (QUA) per shot:
  │           ├── Branch A (target |g⟩):
  │           │     while not accepted:
  │           │       M0 → M1 → M2 (gapless)
  │           │       post_select(M0, target="g")
  │           │       if rejected: conditional_reset_ground(...)
  │           ├── Branch B (target |e⟩):
  │           │     play(r180) [prep |e⟩]
  │           │     while not accepted:
  │           │       M0 → M1 → M2 (gapless)
  │           │       post_select(M0, target="e")
  │           │       if rejected: conditional_reset_excited(...)
  │           └── save states(n_shots, 2, 3), IQ, acceptance
  └── ProgramRunner.run_program(prog, n_total)

ReadoutButterflyMeasurement.analyze()                  [readout.py:1880]
  ├── extract states array → shape (n_shots, 2, 3)
  ├── compute P(m=1) per (branch, measurement):
  │     ├── m1_g = states[:, 0, 1]  (M1 from |g⟩-branch)
  │     ├── m1_e = states[:, 1, 1]  (M1 from |e⟩-branch)
  │     ├── m2_g = states[:, 0, 2]  (M2 from |g⟩-branch)
  │     └── m2_e = states[:, 1, 2]  (M2 from |e⟩-branch)
  ├── butterfly_metrics(m1_g, m1_e, m2_g, m2_e)        [metrics.py:116]
  │     ├── confusion matrix Λ_M from M1
  │     ├── F = 1 - 0.5*(a0 + a1)
  │     ├── V = (1-a1) - a0
  │     ├── invert Λ_M → transition matrix T
  │     ├── t01, t10 from T
  │     └── Q = 1 - 0.5*(t01 + t10)
  ├── optional: T1 decay correction                     [readout.py:2050]
  └── metadata["proposed_patch_ops"] with SetMeasureQuality
```

### 1.4 CalibrateReadoutFull Pipeline

```
CalibrateReadoutFull.run(readoutConfig)                [readout.py:2259]
  ├── Step 1: ReadoutWeightsOptimization.run()          (optional)
  │     └── registers optimized weights in POM
  ├── Step 2: ReadoutGEDiscrimination.run()
  │     ├── .analyze(update_calibration=True)
  │     └── rotated weights registered, macro updated
  ├── Step 3: ReadoutButterflyMeasurement.run()
  │     └── .analyze() → proposed_patch_ops
  └── Step 4: return combined result
```

---

## 2. Hardware-Level Experimental Sequences

### 2.1 GE Discrimination: IQ Blob Acquisition

The QUA program `iq_blobs()` (`builders/readout.py:10-42`) executes:

```
  Time ──────────────────────────────────────────────────────────────────►

  |g⟩ PREP (thermal)           |e⟩ PREP (pi-pulse)
  ┌──────────────────┐         ┌──────────────────────────────┐
  │                  │         │                              │
  │  Readout pulse   │  wait   │  play(r180)  align  Readout  │  wait
  │  ───────────►    │ (therm) │  ───────►         ───────►   │ (therm)
  │  demod: I_g, Q_g │ clks    │         demod: I_e, Q_e      │ clks
  │                  │         │                              │
  └──────────────────┘         └──────────────────────────────┘
       M_ground                     M_excited

  Repeated n_runs times. Stream processing:
    I_g, Q_g → buffer(n_runs) → save
    I_e, Q_e → buffer(n_runs) → save
```

**Key hardware parameters:**
- Readout element: `attr.ro_el` (typically `"resonator"`)
- Readout operation: configured via `measureMacro.set_pulse_op()`
- Integration weights: initially unrotated (cos/sin/m_sin triplet)
- Demodulation: `dual_demod.full` (full integration over pulse length)
- p-pulse: `r180` (default `"x180"`, mapped to `ref_r180`-derived waveform)
- Thermalization: `qb_therm_clks` clock cycles (4 ns each)

### 2.2 Butterfly Measurement: Triple-Measurement Protocol

The QUA program `readout_butterfly_measurement()` (`builders/readout.py:323-476`) executes:

```
  Time ──────────────────────────────────────────────────────────────────►

  BRANCH A: Target |g⟩ (no prep)
  ┌─────────────────────────────────────────────────────────────────────┐
  │  M0 (project)     M1 (measure)     M2 (verify)                    │
  │  ───────────►     ───────────►     ───────────►                    │
  │  I0, Q0, m0       I1, Q1, m1       I2, Q2, m2                     │
  │       │                                                             │
  │       └─ post_select(I0, Q0, target="g", policy)                   │
  │            ├─ accepted → save all, next shot                       │
  │            └─ rejected → conditional_reset_ground(I0, thr, r180)   │
  │                          └─ retry (up to M0_MAX_TRIALS)            │
  └─────────────────────────────────────────────────────────────────────┘

  BRANCH B: Target |e⟩ (pi-pulse prep)
  ┌─────────────────────────────────────────────────────────────────────┐
  │  play(r180)  align                                                  │
  │  ───────►                                                           │
  │                                                                     │
  │  M0 (project)     M1 (measure)     M2 (verify)                    │
  │  ───────────►     ───────────►     ───────────►                    │
  │  I0, Q0, m0       I1, Q1, m1       I2, Q2, m2                     │
  │       │                                                             │
  │       └─ post_select(I0, Q0, target="e", policy)                   │
  │            ├─ accepted → save all, next shot                       │
  │            └─ rejected → conditional_reset_excited(I0, thr, r180)  │
  │                          └─ retry (up to M0_MAX_TRIALS)            │
  └─────────────────────────────────────────────────────────────────────┘

  Per shot: Branch A then Branch B, wait(wait_between_shots)
  Repeated n_shots times.

  Output shape: states[n_shots, 2_branches, 3_measurements]
```

**Measurement roles:**
- **M0** — Projective state preparation. Post-selected to confirm the qubit
  is in the intended state (|g⟩ or |e⟩) before the measurement-under-test.
- **M1** — The measurement being characterized. Its outcomes feed into
  fidelity (F), visibility (V), and the confusion matrix Λ_M.
- **M2** — Post-measurement verification. Compared with M1 to assess QND-ness
  (whether M1 disturbed the state).

**Post-selection details:**
- Uses `sequenceMacros.post_select()` on M0's IQ point.
- Policy is resolved by `ReadoutButterflyMeasurement.run()` before the QUA program
  is built. Supported policies: `BLOBS`, `THRESHOLD`, `ZSCORE`, `AFFINE`, `HYSTERESIS`.
- On rejection, a corrective conditional reset is applied:
  - Branch A (`target="g"`): `conditional_reset_ground(I0, threshold, r180, qb_el)`
    — if I0 > threshold (looks excited), plays r180 to flip back.
  - Branch B (`target="e"`): `conditional_reset_excited(I0, threshold, r180, qb_el)`
    — if I0 < threshold (looks ground), plays r180 to flip.
- Maximum retries: `M0_MAX_TRIALS` (default 16 in `ReadoutConfig`, 1000 in legacy).

**Three measurements are gapless:** M0, M1, M2 are consecutive `measureMacro.measure()`
calls with no intervening wait or alignment. This means:
- M0 projects the state.
- M1 occurs immediately after M0 — the qubit is in the post-M0 state.
- M2 occurs immediately after M1 — the qubit is in the post-M1 state.

### 2.3 Integration Weight Convention

GE Discrimination computes rotated weights at `readout.py:747-816`:

Given discrimination `angle` (the complex argument of the axis separating |g⟩ and |e⟩
in the IQ plane):

```
C = cos(-angle)
S = sin(-angle)

rot_cos   = (C, -S)    # cosine component of rotated demodulation
rot_sin   = (S,  C)    # sine component of rotated demodulation
rot_m_sin = (-S, -C)   # minus-sine component (needed for dual_demod)
```

These are registered as integration weight segments in the PulseOperationManager:
- `{prefix}rot_cos_w_{element}` → `(C * ones, -S * ones)` segments
- `{prefix}rot_sin_w_{element}` → `(S * ones, C * ones)` segments
- `{prefix}rot_m_sin_w_{element}` → `(-S * ones, -C * ones)` segments

After rotation, the first demodulated output (I) is a 1D projection along the
optimal discrimination axis, enabling scalar thresholding: `state = (I > threshold)`.

---

## 3. Physics Intent

### 3.1 What GE Discrimination Estimates

**Goal:** Find the optimal single-shot readout discriminator that classifies the
qubit as |g⟩ or |e⟩ from a single integrated IQ measurement.

**Physical model:** When measured, the qubit-cavity system produces IQ points
clustered around two centroids in the IQ plane — one for |g⟩ and one for |e⟩.
The separation is set by the dispersive shift χ and the readout pulse parameters.
Thermal fluctuations, amplifier noise, and T1 decay during readout broaden each
cluster into approximately Gaussian distributions.

**What is estimated:**
1. **Discrimination axis** — the optimal 1D projection direction that maximizes
   separation between the two clusters.
2. **Threshold** — the 1D decision boundary along the projected axis.
3. **Fidelity** — the balanced classification accuracy: `(P(g|g) + P(e|e)) / 2`.
4. **Rotated integration weights** — hardware-level demodulation rotation that
   aligns the discrimination axis with the I-quadrature, enabling real-time
   thresholding in QUA.

**Assumptions:**
- The qubit is well-thermalized to |g⟩ before the ground-state measurement.
- The π-pulse prepares a high-fidelity |e⟩ state (π-pulse error contributes
  to the measured infidelity but is not separated out).
- Each cluster is approximately Gaussian (the MoG estimator accommodates
  overlap from T1-decay misassignment).
- Readout is in the linear dispersive regime.

### 3.2 What Butterfly Measurement Estimates

**Goal:** Characterize the full measurement operator — not just classification
accuracy, but also back-action and QND-ness.

**Physical model:** An ideal projective measurement of a qubit in the computational
basis should:
1. Correctly identify the state with high **fidelity** (F).
2. Leave the state unchanged after measurement — **quantum non-demolition** (QND).
3. Have high **visibility** (V) — the measurement outcomes for |g⟩ and |e⟩ are
   well-separated.

In practice, T1 decay during readout, measurement-induced transitions, and
residual photon populations cause deviations from ideal behavior.

**What is estimated:**
1. **Fidelity F** = 1 - (a0 + a1)/2 where a0 = P(M1=e | prep g), a1 = P(M1=g | prep e).
   This is the probability that M1 correctly identifies the prepared state.
2. **Visibility V** = (1-a1) - a0. The difference in conditional probabilities
   that M1 reports |e⟩ given actual |e⟩ vs actual |g⟩.
3. **QND-ness Q** = 1 - (t01 + t10)/2. The probability that the state is unchanged
   after M1, quantified by comparing M1 and M2 outcomes.
4. **Transition probabilities** t01 = P(M2=e | M1=g), t10 = P(M2=g | M1=e).
   These are extracted by inverting the measurement confusion matrix.
5. **Confusion matrix Λ_M** and **transition matrix T** — full characterization
   of measurement errors and back-action.

**Assumptions:**
- M0 post-selection successfully prepares the intended state (|g⟩ or |e⟩).
  The quality of this preparation depends on the post-selection policy.
- The three measurements (M0, M1, M2) use identical readout parameters.
- T1 decay between M1 and M2 is negligible or corrected for.
- The measurement operator is memoryless (M2's error rates equal M1's).

### 3.3 Role of M0 Post-Selection

M0 is the heralding measurement. Its purpose is to project the qubit into a
known state before M1 characterizes the measurement. Without M0, the butterfly
protocol would conflate state-preparation errors (e.g., π-pulse infidelity)
with measurement errors.

The post-selection policy on M0 determines how aggressively ambiguous shots
are rejected:
- **Stricter policy (smaller k_blob)** → higher prep fidelity, lower acceptance rate.
- **Looser policy (larger k_blob)** → more data, but M1/M2 analysis may include
  shots where the qubit was not in the intended state.

---

## 4. Mathematics and Code Locations

### 4.1 IQ Blob Rotation and Discrimination

**Step 1 — Compute discrimination axis** (`algorithms.py:427-433`):

Given raw IQ samples S_g and S_e (complex):

```
δ = mean(S_e) - mean(S_g)
axis = δ / |δ|                     # unit complex vector
```

**Step 2 — Project to 1D** (`algorithms.py:436-446`):

```
S_g_rot = Re(S_g · conj(axis))    # project along axis
S_e_rot = Re(S_e · conj(axis))
```

**Step 3 — Fit 2-component Gaussian mixture** (`algorithms.py:449-527`):

The EM algorithm on the 1D projections yields:
- μ_g, μ_e: cluster centers along the axis
- σ_g, σ_e: intrinsic widths (deconvolved from overlap)
- π_g, π_e: mixing weights (accounts for T1-decay misassignment)
- ε_up: P(actual e-component | prepared g) — upward misassignment
- ε_down: P(actual g-component | prepared e) — downward misassignment

**Step 4 — Optimal threshold** (`algorithms.py:604-675`):

Sweep all midpoints between sorted 1D samples; minimize total misclassification:

```
threshold* = argmin_t [ w_g · P(I_g > t) + w_e · P(I_e < t) ]
```

**Step 5 — Fidelity** (`analysis_tools.py:570-590`):

```
gg = count(I_g_rot < threshold) / N_g      # P(classify g | true g)
ee = count(I_e_rot > threshold) / N_e      # P(classify e | true e)
fidelity = 100.0 · (gg + ee) / 2.0         # balanced accuracy in PERCENT
```

**Step 6 — Rotation angle** (`analysis_tools.py:548`):

```
angle = -arg(axis)                          # negative of complex argument
```

This is the angle used to construct rotated integration weights (Section 2.3).

### 4.2 Rotated Weight Construction

At `readout.py:768-810`, given `angle` from discrimination:

```
C = cos(-angle)
S = sin(-angle)

weight_length = integration_length (from readout pulse)

rot_cos_segments   = { cosine: [(C, weight_length)],  sine: [(-S, weight_length)] }
rot_sin_segments   = { cosine: [(S, weight_length)],  sine: [(C, weight_length)]  }
rot_m_sin_segments = { cosine: [(-S, weight_length)], sine: [(-C, weight_length)] }
```

These are registered via `POM.add_int_weight_segments()` and bound to the
readout pulse via `measureMacro.set_pulse_op()`.

After this, the QUA `measure()` demodulates with dual_demod using these rotated
weights, producing:

```
I_rot = ∫ [C · cos(ωt) - S · sin(ωt)] · signal(t) dt    ≈ Re(S · e^{j·angle})
Q_rot = ∫ [S · cos(ωt) + C · sin(ωt)] · signal(t) dt    ≈ Im(S · e^{j·angle})
```

The I_rot output is the optimal 1D projection for scalar thresholding.

### 4.3 Butterfly Metrics

At `metrics.py:116-273`, given binary state vectors from M1 and M2:

```
m1_g[i] ∈ {0, 1}    # M1 outcome for shot i, branch A (intended |g⟩)
m1_e[i] ∈ {0, 1}    # M1 outcome for shot i, branch B (intended |e⟩)
m2_g[i] ∈ {0, 1}    # M2 outcome for shot i, branch A
m2_e[i] ∈ {0, 1}    # M2 outcome for shot i, branch B
```

**Confusion matrix from M1** (the measurement-under-test):

```
a0 = mean(m1_g)          # P(M1 reports e | state is g)  — false positive rate
a1 = mean(1 - m1_e)      # P(M1 reports g | state is e)  — false negative rate

        ┌              ┐
Λ_M  =  │ 1-a0    a0   │     rows: true state (0=g, 1=e)
        │  a1    1-a1   │     cols: measured state (0=g, 1=e)
        └              ┘
```

**Fidelity, Visibility:**

```
F = clip(1.0 - 0.5·(a0 + a1), 0, 1)      # balanced accuracy, FRACTION [0,1]
V = (1 - a1) - a0                          # visibility
```

**Post-measurement transition matrix** (`metrics.py:190-230`):

The transition matrix T describes back-action. If Λ_M is invertible:

```
Λ_M^{-1} exists ⟹ we can solve for T

M2 conditional on M1:
  P(m2 | m1, prep) = Σ_s T[m2, s] · P(s | m1, prep)

where P(s | m1, prep) = Λ_M^{-1} [m1, s] · prior[s | prep]
```

The code constructs per-branch M1→M2 conditional tables and inverts Λ_M
to extract:

```
t01 = P(state flipped g→e between M1 and M2)
t10 = P(state flipped e→g between M1 and M2)
```

**QND-ness:**

```
Q = clip(1.0 - 0.5·(t01 + t10), 0, 1)
```

### 4.4 T1 Decay Correction

At `readout.py:2050-2085`, the butterfly analysis optionally corrects for
T1 relaxation between M1 and M2:

```
readout_duration_ns = measureMacro.active_length()     # pulse length in ns
readout_duration_clks = readout_duration_ns / 4        # convert to clocks
T1_s = calibration_store.get_coherence(element).T1     # T1 in seconds

t_readout_s = readout_duration_ns * 1e-9
decay_factor = exp(-t_readout_s / T1_s)

# Corrected transition probabilities:
t10_corrected = t10 - (1 - decay_factor) · P(e post-M1)
```

This correction accounts for the finite probability that a qubit in |e⟩ decays
to |g⟩ during the M2 readout pulse, artificially inflating t10.

### 4.5 Post-Selection Decision Rules

At `readout.py:1665-1722`, the post-selection policy is resolved:

```
Fallback chain (first match wins):
  1. Explicit prep_policy parameter → use directly
  2. use_stored_config=True AND qbx_readout_state hash matches
       → mm.get_post_select_config()
  3. Blob parameters available from GE discrimination
       → PostSelectionConfig(policy="BLOBS", k_blob=2.0, ...)
  4. Threshold available
       → PostSelectionConfig(policy="THRESHOLD", threshold=thr)
```

**BLOBS policy** constructs circular acceptance regions:
- Center: rotated centroid (rot_mu_g or rot_mu_e)
- Radius: k_blob × sigma (k_blob default = 2.0 in qubox_v2, 3.0 in legacy)
- A shot is accepted if the M0 IQ point falls within the target-state blob.

**THRESHOLD policy** uses scalar comparison:
- Branch A (target g): accept if I0 < threshold
- Branch B (target e): accept if I0 > threshold

### 4.6 Real-Time State Discrimination in QUA

At `measure.py:1647-1651`, inside the QUA program:

```python
assign(state, target_vars[0] > cls._ro_disc_params["threshold"])
```

This is a QUA-level real-time comparison: `state = (I_rot > threshold)`.
The value `True` (1) means |e⟩, `False` (0) means |g⟩.

---

## 5. Data Products and Interfaces

### 5.1 GE Discrimination Outputs

**AnalysisResult.metrics** (populated at `readout.py:580-620`):

| Key | Type | Unit | Description |
|-----|------|------|-------------|
| `angle` | float | radians | Discrimination angle (= -arg(axis)) |
| `threshold` | float | a.u. | 1D decision boundary along rotated axis |
| `fidelity` | float | **percent** (0-100) | Balanced accuracy = 100·(gg+ee)/2 |
| `gg` | float | fraction | P(classify g \| true g) |
| `ge` | float | fraction | P(classify e \| true g) |
| `eg` | float | fraction | P(classify g \| true e) |
| `ee` | float | fraction | P(classify e \| true e) |
| `rot_mu_g` | complex | a.u. | Rotated g-centroid |
| `rot_mu_e` | complex | a.u. | Rotated e-centroid |
| `sigma_g` | float | a.u. | Gaussian width of g-cluster |
| `sigma_e` | float | a.u. | Gaussian width of e-cluster |
| `SNR` | float | dB | Signal-to-noise ratio |

**Side effects on measureMacro** (via `_apply_discrimination_measure_macro()`):

| Field | Storage | Description |
|-------|---------|-------------|
| `_ro_disc_params["threshold"]` | measureConfig.json | Scalar threshold |
| `_ro_disc_params["angle"]` | measureConfig.json | Rotation angle |
| `_ro_disc_params["fidelity"]` | measureConfig.json | GE fidelity (percent) |
| `_ro_disc_params["rot_mu_g"]` | measureConfig.json | Rotated g-centroid |
| `_ro_disc_params["rot_mu_e"]` | measureConfig.json | Rotated e-centroid |
| `_ro_disc_params["sigma_g"]` | measureConfig.json | g-width |
| `_ro_disc_params["sigma_e"]` | measureConfig.json | e-width |
| `_ro_disc_params["qbx_readout_state"]` | runtime only | Hash dict for Butterfly validation |

**Side effects on CalibrationStore** (via `guarded_calibration_commit()`):

| Field | Storage | Description |
|-------|---------|-------------|
| `discrimination.{element}.threshold` | calibration.json | Scalar threshold |
| `discrimination.{element}.angle` | calibration.json | Rotation angle |
| `discrimination.{element}.fidelity` | calibration.json | GE fidelity (percent) |
| `discrimination.{element}.mu_g` | calibration.json | [Re, Im] of g-centroid |
| `discrimination.{element}.mu_e` | calibration.json | [Re, Im] of e-centroid |
| `discrimination.{element}.sigma_g` | calibration.json | g-width |
| `discrimination.{element}.sigma_e` | calibration.json | e-width |

**Side effects on PulseOperationManager:**

Rotated integration weights registered:
- `{prefix}rot_cos_w_{element}`
- `{prefix}rot_sin_w_{element}`
- `{prefix}rot_m_sin_w_{element}`

### 5.2 Butterfly Measurement Outputs

**AnalysisResult.metrics** (populated at `readout.py:1990-2060`):

| Key | Type | Unit | Description |
|-----|------|------|-------------|
| `F` | float | **fraction** (0-1) | Measurement fidelity |
| `Q` | float | fraction (0-1) | QND-ness |
| `V` | float | fraction (-1 to 1) | Visibility |
| `t01` | float | fraction | P(g→e transition between M1, M2) |
| `t10` | float | fraction | P(e→g transition between M1, M2) |
| `confusion_matrix` | 2×2 array | — | Λ_M from M1 |
| `transition_matrix` | 2×2 array | — | T from M1→M2 |
| `Lambda_M_valid` | bool | — | Whether Λ_M was invertible |
| `acceptance_rate` | array [2] | fraction | Post-selection acceptance per branch |
| `average_tries` | array [2] | count | Average retries per branch |
| `fidelity_delta_GE_minus_F` | float | fraction | GE fidelity - F (for consistency check) |

**AnalysisResult.metadata["proposed_patch_ops"]:**

```python
[
    {
        "op": "SetMeasureQuality",
        "payload": {
            "F": float, "Q": float, "V": float,
            "t01": float, "t10": float,
            "confusion_matrix": [[...], [...]],
        }
    }
]
```

**Side effects on CalibrationStore** (via orchestrator patch):

| Field | Storage | Description |
|-------|---------|-------------|
| `readout_quality.{element}.F` | calibration.json | Fidelity |
| `readout_quality.{element}.Q` | calibration.json | QND-ness |
| `readout_quality.{element}.V` | calibration.json | Visibility |
| `readout_quality.{element}.t01` | calibration.json | g→e transition |
| `readout_quality.{element}.t10` | calibration.json | e→g transition |
| `readout_quality.{element}.confusion_matrix` | calibration.json | Λ_M |

### 5.3 State Handoff: GE → Butterfly

The critical coupling between GE Discrimination and Butterfly is:

| Datum | Written by GE at | Read by Butterfly at | Storage |
|-------|-------------------|----------------------|---------|
| Threshold | `readout.py:890` | `readout.py:1624` | `mm._ro_disc_params` |
| Rotated weights | `readout.py:795-810` | `readout.py:1806` | POM weight store |
| Discrimination angle | `readout.py:893` | (implicit via weights) | `mm._ro_disc_params` |
| Blob centroids | `readout.py:898-899` | `readout.py:1695` | `mm._ro_disc_params` |
| Blob sigmas | `readout.py:901-902` | `readout.py:1697-1698` | `mm._ro_disc_params` |
| `qbx_readout_state` hash | `readout.py:914` | `readout.py:1652` | `mm._ro_disc_params` (runtime only) |
| PostSelectionConfig | `readout.py:920-924` | `readout.py:1673` | `mm._post_select_config` |

**Invariant:** Butterfly must use the same threshold and rotated weights that GE
produced. If `sync_from_calibration()` runs between GE and Butterfly (e.g., after
an orchestrator patch commit), the `qbx_readout_state` hash is preserved (BUG-R3 fix)
to maintain the consistency check.

---

## 6. Legacy Comparison

### 6.1 Side-by-Side: GE Discrimination

| Aspect | Legacy (`cQED_Experiment`) | qubox_v2 (`ReadoutGEDiscrimination`) |
|--------|---------------------------|--------------------------------------|
| **QUA program** | `iq_blobs()` (same builder) | `iq_blobs()` (same builder) |
| **Analysis function** | `two_state_discriminator()` (same) | `two_state_discriminator()` (same) |
| **Macro mutation** | Direct: `mm._update_readout_discrimination(out)` | Via `_apply_discrimination_measure_macro()`, deprecated warning on direct call |
| **Weight registration** | Same `_build_rotated_weights()` logic | Same logic, registered in POM |
| **Calibration write** | Direct `CalibrationStore.set_discrimination()` | Via `guarded_calibration_commit()` with validation gates |
| **PostSelection auto** | `auto_update_postsel=True, blob_k_g=3.0` | `PostSelectionConfig.from_discrimination_results(k_blob=2.0)` |
| **Persistence** | `mm.save_json()` called inline | Routed through `PersistMeasureConfig` patch op |
| **Hash stamping** | Not present | `qbx_readout_state` hash stamped at `readout.py:914` |
| **Burn weights** | `session.burn_pulses()` called after | `burn_rot_weights=True` param controls |
| **Fidelity scale** | Percent (0-100) | Percent (0-100) |

### 6.2 Side-by-Side: Butterfly Measurement

| Aspect | Legacy (`cQED_Experiment`) | qubox_v2 (`ReadoutButterflyMeasurement`) |
|--------|---------------------------|------------------------------------------|
| **QUA program** | `readout_butterfly_measurement()` (same builder) | `readout_butterfly_measurement()` (same builder) |
| **Analysis function** | `butterfly_metrics()` (same) | `butterfly_metrics()` (same) |
| **Macro mutation** | Direct: `mm._update_readout_quality(out)` | Via `SetMeasureQuality` proposed patch ops |
| **Post-selection default** | `blob_k_g=3.0` (in `calibrate_readout_full`) | `k_blob=2.0` (in `ReadoutConfig` and fallback) |
| **M0_MAX_TRIALS** | 1000 (in `calibrate_readout_full`) | 16 (in `ReadoutConfig`) |
| **Hash check** | Not present | Compares `qbx_readout_state` with current signature |
| **T1 correction** | Available but separate | Integrated into `analyze()` at `readout.py:2050` |
| **F scale** | Fraction (0-1) | Fraction (0-1) |
| **Burn between GE/Butterfly** | Explicit `burn_pulses()` call | Via `burn_rot_weights=True` in GE `run()` |
| **Calibration write** | Direct `set_readout_quality()` | Via orchestrator patch with `SetMeasureQuality` |

### 6.3 Side-by-Side: CalibrateReadoutFull Pipeline

| Step | Legacy (`calibrate_readout_full`) | qubox_v2 (`CalibrateReadoutFull`) |
|------|----------------------------------|-----------------------------------|
| **1. Weight opt** | `readout_weights_optimization()` | `ReadoutWeightsOptimization.run()` |
| **2. GE disc** | `readout_ge_discrimination(auto_update_postsel=True, blob_k_g=3.0)` | `ReadoutGEDiscrimination.run(ge_update_measure_macro=True)` |
| **2a. Burn** | Explicit `burn_pulses()` between GE and Butterfly | Via `burn_rot_weights=True` in GE `.run()` |
| **3. Butterfly** | `readout_butterfly_measurement(use_stored_config=True, M0_MAX_TRIALS=1000)` | `ReadoutButterflyMeasurement.run()` |
| **3a. Convergence** | Single iteration (no convergence loop) | Optional convergence loop with `fidelity_tolerance` |
| **4. Post** | IQ normalization extraction + persistence | Patch ops routed via orchestrator |
| **Defaults** | `blob_k_g=3.0`, `M0_MAX_TRIALS=1000`, `n_shots=50000` | `blob_k_g=2.0`, `M0_MAX_TRIALS=16`, `n_shots=50000` |

### 6.4 Artifact Schema Comparison

**GE Discrimination artifacts:**

| Artifact | Legacy | qubox_v2 |
|----------|--------|----------|
| Raw IQ data | `.npz` with `I_g, Q_g, I_e, Q_e` | Same `.npz` format |
| Metadata | `.meta.json` with `_run_params` | Same `.meta.json` format |
| Calibration | Direct store write | `artifacts/calibration_runs/{tag}_{ts}.json` + store write |
| measureConfig | `measureConfig.json` inline save | Deferred to `PersistMeasureConfig` patch |

**Butterfly artifacts:**

| Artifact | Legacy | qubox_v2 |
|----------|--------|----------|
| Raw states | `.npz` with `states(n,2,3)` | Same `.npz` format |
| Raw IQ | `.npz` with `I0-I2, Q0-Q2` | Same `.npz` format |
| Metrics | Direct store write | `proposed_patch_ops` in metadata |
| measureConfig | `measureConfig.json` inline save | Via orchestrator patch |

---

## 7. Inconsistencies and Root Causes

### INC-1: Fidelity Scale Mismatch (GE vs Butterfly)

**What:** GE Discrimination reports fidelity in **percent** (0-100) at
`analysis_tools.py:577`: `fidelity = 100.0 * (gg + ee) / 2.0`.
Butterfly reports F as a **fraction** (0-1) at `metrics.py:169`:
`F = clip(1.0 - 0.5*(a0 + a1), 0, 1)`.

**Where the inconsistency surfaces:** Butterfly `analyze()` computes a
consistency check at `readout.py:2035-2042`:
```python
ge_fidelity = mm._ro_disc_params.get("fidelity", None)
if ge_fidelity is not None:
    ge_fidelity_frac = ge_fidelity / 100.0  # convert percent → fraction
    metrics["fidelity_delta_GE_minus_F"] = ge_fidelity_frac - F
```

**Root cause:** Historical convention from `two_state_discriminator` which has
always returned percent. Butterfly follows the standard physics convention of [0,1].

**Impact:** Low — the conversion is handled correctly at the comparison point.
However, `DiscriminationParams.fidelity` in CalibrationStore stores the percent
value, which could confuse consumers expecting a fraction.

**How to verify:** `assert 0 < cal.get_discrimination(el).fidelity <= 100`
confirms percent scale. `assert 0 < cal.get_readout_quality(el).F <= 1`
confirms fraction scale.

### INC-2: Post-Selection Tightness Default (blob_k_g)

**What:** qubox_v2 uses `k_blob=2.0` (at `readout.py:1707` and `ReadoutConfig.blob_k_g`).
Legacy `calibrate_readout_full` uses `blob_k_g=3.0` (at `legacy_experiment.py:~2955`).

**Where it matters:** Tighter post-selection (k=2.0) rejects ~4.6% of Gaussian
shots vs ~0.3% for k=3.0. For the same dataset, the qubox_v2 butterfly:
- Has higher effective state-preparation fidelity (fewer misclassified shots pass M0).
- Reports higher F and Q.
- Has lower acceptance rate (more retries needed).
- Is more sensitive to non-Gaussianity in the IQ distribution.

**Root cause:** Deliberate tightening in qubox_v2, but not documented in the
codebase or CHANGELOG as an intentional change.

**How to verify:** Compare `readoutConfig.blob_k_g` against legacy default.
Run butterfly with both k=2.0 and k=3.0 on the same GE data and compare F, Q.

### INC-3: M0_MAX_TRIALS Default (16 vs 1000)

**What:** qubox_v2 `ReadoutConfig.M0_MAX_TRIALS` defaults to 16.
Legacy `calibrate_readout_full` uses `M0_MAX_TRIALS=1000`.

**Where it matters:** With only 16 retries and k_blob=2.0, shots in the
rejection region may exhaust retries and be saved as "last attempt" (not
necessarily accepted). These un-accepted shots contaminate the butterfly
statistics.

**Root cause:** The qubox_v2 default was likely chosen to keep QUA program
execution time bounded. Legacy's 1000 retries is effectively "retry until
accepted" for any reasonable noise level.

**How to verify:** Check `acceptance_rate` in butterfly analysis output.
If significantly below 1.0, retry exhaustion is occurring.

### INC-4: `qbx_readout_state` Hash Not Validated After Calibration Commit

**What:** The `qbx_readout_state` hash is set by GE Discrimination
(`readout.py:914`) and checked by Butterfly (`readout.py:1647-1663`).
After `sync_from_calibration()`, the hash is now preserved (BUG-R3 fix), but
the hash check only triggers a **warning**, not an error, on mismatch
(`readout.py:1658`).

**Where it matters:** If the user re-runs GE discrimination (updating the
hash), then runs an unrelated calibration (triggering sync), then runs
butterfly — the hash may appear stale even though the readout config is
actually current.

**Root cause:** The hash is a runtime-only field (not in CalibrationStore)
that tracks "has the readout config changed since GE ran." The sync
mechanism preserves it, but lacks a mechanism to update it when the config
genuinely changes through a sync.

**How to verify:** Run GE → commit calibration → sync → check
`mm._ro_disc_params["qbx_readout_state"]` is preserved.

### INC-5: `_update_readout_quality` Dead Code Restoration Completeness

**What:** BUG-R2 restored the dead code for `t01`, `t10`, `eta_g`, `eta_e`
in `_update_readout_quality()` (`measure.py:442-452`). However, the
`_update_readout_quality()` method is deprecated — the recommended path is
`SetMeasureQuality` patch ops via the orchestrator.

**Where it matters:** The `SetMeasureQuality` patch handler in
`orchestrator.py` calls `_update_readout_quality()` to update the macro.
The restored code ensures t01/t10 propagate immediately. But the orchestrator's
post-patch `sync_from_calibration()` also reads t01/t10 from CalibrationStore,
creating a double-write to `_ro_quality_params`.

**Root cause:** The sync mechanism was designed before the BUG-R2 fix. Now
both the direct update and the sync write the same values, which is harmless
but redundant.

**How to verify:** Set a breakpoint in `_update_readout_quality` and
`sync_from_calibration` after a butterfly patch commit; confirm both write
the same t01/t10 values.

### INC-6: Confusion Matrix Convention Ambiguity

**What:** The confusion matrix Λ_M is defined differently in comments vs code:
- `butterfly_metrics()` at `metrics.py:155-165` defines rows as true state,
  columns as measured state.
- The `DiscriminationParams.confusion_matrix` in CalibrationStore uses the
  same convention.
- But the readout builder's `readout_butterfly_measurement` QUA program
  produces states indexed as `states[shot, branch, measurement]` where
  branch 0 = prepared g, branch 1 = prepared e.

The matrix orientation is consistent, but nowhere in the code is the
convention explicitly documented as a docstring on the `confusion_matrix`
field of `ReadoutQuality` or `DiscriminationParams`.

**Root cause:** Missing documentation.

**How to verify:** Confirm `confusion_matrix[0,0]` represents P(measure g | true g)
by tracing through `butterfly_metrics` at `metrics.py:155-165`.

### INC-7: Butterfly Does Not Validate Weight Consistency

**What:** Butterfly reads the threshold and blob params from `measureMacro` but
does **not** verify that the integration weights in the POM match those produced
by GE discrimination. If a user manually modifies weights between GE and
Butterfly, the butterfly uses the new weights without warning.

**Where:** `_pick_weight_triplet()` at `readout.py:1799-1813` selects weights
from the current POM state. No comparison against GE's registered weights.

**Root cause:** The `qbx_readout_state` hash includes discrimination params
but does not include a checksum of the integration weights themselves.

**How to verify:** After GE, manually modify a weight via
`pom.modify_integration_weights()`, then run Butterfly. No warning is emitted.

---

## 8. Open Questions / Missing Information

### Q1: Post-Selection Policy Propagation to QUA

The `post_select()` function in `sequenceMacros` is the QUA-level implementation
of the acceptance criterion. The exact QUA code for each policy type (BLOBS,
THRESHOLD, ZSCORE, AFFINE, HYSTERESIS) was not fully traced in this analysis.
The IQ comparison is done in QUA fixed-point arithmetic, which has limited
dynamic range. Questions:
- Are there numerical precision issues with the blob-radius comparison in QUA
  fixed-point?
- Does the BLOBS policy use a true circular region or an axis-aligned rectangle
  approximation?

### Q2: T1 Decay Correction Interaction with Post-Selection

The T1 decay correction in Butterfly `analyze()` accounts for decay *during*
the readout pulse. But M0 post-selection already rejects shots where the qubit
decayed before M0. If the qubit decays *between* M0 and M1 (during the gapless
transition), does the correction account for this? The three measurements are
gapless in QUA, so the inter-measurement time is effectively zero plus the
readout pulse length. Clarification needed on whether the correction applies
to M1→M2 time, M0→M1 time, or both.

### Q3: `eta_g` and `eta_e` Computation

The `_ro_quality_params` dict includes `eta_g` and `eta_e` fields, and the
restored BUG-R2 code reads them from the butterfly output. However,
`butterfly_metrics()` in `metrics.py` does not compute or return `eta_g`/`eta_e`.
These must come from a different analysis path (possibly the
`readout_core_efficiency_calibration` QUA program, which evaluates dual core
membership). The data flow for these fields is unclear.

### Q4: `affine_n` in Quality Params

The `_ro_quality_params` dict includes `affine_n` — a per-Fock-number affine
correction. This is populated by the butterfly's `_update_readout_quality` but
`butterfly_metrics()` does not compute it. It likely comes from a multi-state
(ge0/ge1/...) discrimination calibration. The provenance of this field in the
butterfly context is unclear.

### Q5: Legacy IQ Normalization Step

Legacy `calibrate_readout_full()` includes an IQ normalization extraction step
(step 4) that is absent from qubox_v2's `CalibrateReadoutFull`. This
normalization may affect downstream experiments that rely on absolute IQ
magnitudes. It is unclear whether this omission is intentional or an oversight.

### Q6: `readout_core_efficiency_calibration` Usage

The QUA program `readout_core_efficiency_calibration()` in
`builders/readout.py:196-320` performs dual post-selection (evaluating both
g-core and e-core membership on each shot) without retry logic. This appears
to be a standalone calibration for post-selection core efficiencies. Its
relationship to the GE→Butterfly pipeline is unclear — it may be a precursor
to the BLOBS policy but is not called by `CalibrateReadoutFull`.

### Q7: Convergence Loop in CalibrateReadoutFull

qubox_v2's `CalibrateReadoutFull` supports an optional convergence loop
(`max_iterations`, `fidelity_tolerance` in `ReadoutConfig`). The convergence
criterion and what is re-run on each iteration (just butterfly? GE + butterfly?)
needs clarification. Legacy has no convergence loop.

---

*End of report. This document is analysis-only; no code was modified.*
