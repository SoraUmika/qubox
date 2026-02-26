# Architectural Audit & Design Proposal: `|f⟩` Support in `qubox_v2`

> **Status**: Design proposal — not yet implemented.
> **Scope**: Extend the cQED experiment framework from implicit two-level (`|g⟩`, `|e⟩`) transmon support to full `|f⟩` (third transmon level) support.

---

## Table of Contents

- [A. Current-State Audit](#a-current-state-audit)
- [B. Hidden Two-Level Assumptions](#b-hidden-two-level-assumptions)
- [C. Proposed Target Design](#c-proposed-target-design)
- [D. Migration Strategy](#d-migration-strategy)
- [E. Implementation Roadmap](#e-implementation-roadmap)
- [F. Risks and Tradeoffs](#f-risks-and-tradeoffs)
- [Appendix: Three Plans Compared](#appendix-three-plans-compared)

---

## A. Current-State Audit

### A.1 Codebase Architecture Overview

The `qubox_v2` framework is a layered superconducting qubit experiment platform built on top of **Quantum Machines OPX** (QUA language). The key modules relevant to this audit are:

| Layer | Module | Role |
|-------|--------|------|
| Hardware Abstraction | `pulses/manager.py` | `PulseOperationManager` — pulse/waveform/integration-weight registration, perm/volatile stores |
| Hardware Abstraction | `tools/generators.py` | `register_qubit_rotation()`, `register_rotations_from_ref_iq()` — rotation pulse construction |
| Macros | `programs/macros/measure.py` | `measureMacro` — measurement, IQ rotation, discrimination, posterior model |
| Macros | `programs/macros/sequence.py` | `sequenceMacros` — state preparation, active reset, post-selection |
| QUA Program Builders | `programs/builders/spectroscopy.py` | Spectroscopy QUA programs (qubit, resonator, ef) |
| QUA Program Builders | `programs/builders/readout.py` | IQ blobs, raw/integrated traces, butterfly measurement, reset benchmark |
| QUA Program Builders | `programs/builders/time_domain.py` | Rabi, Ramsey, echo, T1 programs |
| Calibration Models | `calibration/models.py` | Pydantic models: `DiscriminationParams`, `ReadoutQuality`, `PulseCalibration`, `ElementFrequencies`, etc. |
| Calibration Store | `calibration/store.py` | `CalibrationStore` — JSON-backed typed persistence |
| Calibration Engine | `calibration/orchestrator.py` | `CalibrationOrchestrator` — experiment → artifact → patch pipeline |
| Analysis | `analysis/analysis_tools.py` | `two_state_discriminator()`, posterior model builders |
| Analysis | `analysis/post_selection.py` | `PostSelectionConfig`, `TargetState` literal |
| Core | `core/session_state.py` | `SessionState` — immutable config snapshot |
| Core | `core/schemas.py` | Schema versioning and migration registry |

### A.2 How the Two-Level Model Pervades the System

The system is built around an **implicit g/e binary model at every layer**. This manifests as:

1. **Boolean state variables**: `measureMacro.measure()` returns `state` declared as QUA `bool`, discriminated by a single scalar threshold (`state = I > threshold`). (`measure.py` ~L1838)

2. **Binary discrimination parameters**: `DiscriminationParams` stores `mu_g`, `mu_e`, `sigma_g`, `sigma_e`, a single `threshold`, and optionally a 2×2 `confusion_matrix`. (`calibration/models.py:28–46`)

3. **Binary readout quality**: `ReadoutQuality` stores `t01`, `t10` (two transition rates), 2×2 confusion matrix. (`calibration/models.py:49–67`)

4. **Binary posterior model**: `compute_posterior_weights()` returns `(w_g, w_e)` only. `compute_posterior_state_weight()` raises on any target other than `"g"` or `"e"`. (`measure.py:516`, `measure.py:641`)

5. **Binary state preparation**: `sequenceMacros.prepare_state()` accepts only `target_state ∈ {"g", "e"}` and raises `ValueError` otherwise. (`sequence.py:203`)

6. **Binary post-selection**: `sequenceMacros.post_select()` and `PostSelectionConfig` implement g/e-only acceptance policies. The type itself is `TargetState = Literal["g", "e"]`. (`post_selection.py:8`, `sequence.py:464`)

7. **Binary conditional reset**: `conditional_reset_ground()` and `conditional_reset_excited()` use `I > threshold` to decide whether to apply a single pi pulse. (`sequence.py`)

8. **Binary readout builders**: `iq_blobs()` saves `Ig, Qg, Ie, Qe` only. `readout_ge_raw_trace()` and `readout_ge_integrated_trace()` have "ge" baked into function names. `readout_butterfly_measurement()` has exactly two branches: target `|g⟩` and target `|e⟩`. (`readout.py:10–476`)

9. **Binary pulse naming**: `register_rotations_from_ref_iq()` has a hard-coded table of rotation names `{x180, x90, xn90, y180, y90, yn90}` with no transition suffix. (`generators.py:184–192`)

10. **Binary calibration records**: `PulseCalibration` stores one `pulse_name` per entry with no `transition` dimension. `PulseTrainResult` defaults to `rotation_pulse="x180"`. (`calibration/models.py:128–146`, `models.py:224`)

### A.3 What Already Works for `|f⟩`

Several components are already transition-agnostic or have partial `|f⟩` awareness:

| Component | Status | Details |
|-----------|--------|---------|
| `qubit_spectroscopy_ef()` | **Already exists** | Prepares `\|e⟩` via ge π-pulse, sweeps ef IF. (`spectroscopy.py:179`) |
| `qubit_spectroscopy()` | Transition-agnostic | Takes `sat_pulse` + frequency array as params |
| `temporal_rabi()`, `power_rabi()` | Transition-agnostic | Take generic `pulse` name parameter |
| `T1_relaxation()`, `T2_ramsey()`, `T2_echo()` | Transition-agnostic | Take `r180`/`r90` as params — usable for ef |
| `PulseOperationManager` | Fully agnostic | Registers `(element, op_name)` pairs with arbitrary string names |
| `register_qubit_rotation()` | Agnostic | Takes arbitrary `name` — can already be `"ef_x180"` |
| `register_rotations_from_ref_iq()` | Has `prefix` param | `prefix="ef_"` would produce `"ef_x180"` etc. |
| `ElementFrequencies` | Partial | Has `anharmonicity` (α = ω_ge − ω_ef) and `fock_freqs` placeholder |
| `MultiStateCalibration` | Exists | Has `state_labels: list[str]` and `affine_matrix` for arbitrary N-state |
| `FockSQRCalibration` | Exists | Per-Fock-number calibration records |

---

## B. Hidden Two-Level Assumptions

### B.1 CRITICAL — Hard-coded binary constraints (must change for `|f⟩`)

| # | File | Location | Assumption | Impact |
|---|------|----------|-----------|--------|
| B1.1 | `programs/macros/measure.py` | ~L1838 | `state = declare(bool)` — state is a QUA boolean | Cannot represent 3 states in QUA |
| B1.2 | `programs/macros/measure.py` | ~L1838 | `assign(state, I > threshold)` — single scalar threshold | 3-state needs 2 thresholds or GMM classifier |
| B1.3 | `programs/macros/measure.py` | L148–161 | `_ro_disc_params` stores only `rot_mu_g`, `rot_mu_e`, `sigma_g`, `sigma_e`, one `threshold` | No `mu_f`, `sigma_f`, second threshold |
| B1.4 | `programs/macros/measure.py` | L516 | `compute_posterior_weights()` returns `(w_g, w_e)` tuple | No `w_f` computed |
| B1.5 | `programs/macros/measure.py` | L641, L676 | `compute_posterior_state_weight()` raises if `ts not in ("g","e")` | Cannot query P(f\|S) |
| B1.6 | `programs/macros/sequence.py` | L203 | `prepare_state()`: `if ts not in ("g","e"): raise ValueError` | Cannot prepare `\|f⟩` |
| B1.7 | `programs/macros/sequence.py` | L464 | `post_select()` limits `target_state` to `"g"` or `"e"` | Cannot post-select on `\|f⟩` |
| B1.8 | `programs/macros/sequence.py` | various | `conditional_reset_ground()` / `conditional_reset_excited()` use binary `I > threshold` | No 3-state conditional reset |
| B1.9 | `analysis/post_selection.py` | L8 | `TargetState = Literal["g", "e"]` | Type alias excludes `"f"` |
| B1.10 | `analysis/post_selection.py` | L227–250 | `post_select_indices()` validates against `("g", "e")` | Rejects `"f"` |
| B1.11 | `analysis/post_selection.py` | L288–374 | All discrimination policies (ZSCORE, AFFINE, HYSTERESIS, BLOBS) are binary | No 3-class classification |
| B1.12 | `calibration/models.py` | L28–46 | `DiscriminationParams`: `mu_g`, `mu_e`, `sigma_g`, `sigma_e` — no `mu_f`, `sigma_f` | Cannot store 3-state calibration |
| B1.13 | `calibration/models.py` | L49–67 | `ReadoutQuality`: `t01`, `t10` only; 2×2 confusion matrix | No `t02`, `t12`, `t20`, `t21`; need 3×3 |
| B1.14 | `analysis/analysis_tools.py` | ~L345 | `two_state_discriminator()` accepts only `(Ig, Qg, Ie, Qe)` | No third state input |
| B1.15 | `programs/builders/readout.py` | L10–42 | `iq_blobs()` saves only `Ig`, `Qg`, `Ie`, `Qe` streams | No `If`, `Qf` |
| B1.16 | `programs/builders/readout.py` | L323–476 | `readout_butterfly_measurement()` has exactly 2 branches (target g, target e) | No f branch |
| B1.17 | `programs/builders/readout.py` | L489 | `readout_leakage_benchmarking()`: `state = declare(bool)` | Binary state output |
| B1.18 | `programs/builders/readout.py` | L529–602 | `qubit_reset_benchmark()`: binary state, binary conditional reset | Cannot reset from `\|f⟩` |

### B.2 MODERATE — Naming/schema limitations (should change)

| # | File | Location | Assumption | Impact |
|---|------|----------|-----------|--------|
| B2.1 | `tools/generators.py` | L184–192 | `THETA_PHI` dict has `{"x180", "x90", ...}` with no transition prefix | ge vs ef rotations collide if both registered |
| B2.2 | `tools/generators.py` | L7 | `register_qubit_rotation()`, `name` is freeform but all examples/defaults use unprefixed names | No convention enforcement for `"ef_x180"` |
| B2.3 | `calibration/models.py` | L128–146 | `PulseCalibration.pulse_name: str` — single name per entry, no `transition` field | Need per-transition calibration records |
| B2.4 | `calibration/models.py` | L198 | `CalibrationData.pulse_calibrations: dict[str, PulseCalibration]` keyed by name | No transition dimension in key schema |
| B2.5 | `calibration/models.py` | L98–100 | `ElementFrequencies`: `qubit_freq`, `anharmonicity` — no explicit `ef_freq` field | ef freq must be computed as `qb_freq + anharmonicity` |
| B2.6 | `calibration/models.py` | L216–227 | `PulseTrainResult.rotation_pulse = "x180"` — hardcoded default | Assumes ge pulse |
| B2.7 | `programs/builders/readout.py` | L45, L85 | `readout_ge_raw_trace`, `readout_ge_integrated_trace` — "ge" baked into function names | Confusing when reused for ef/gef readout |
| B2.8 | `programs/macros/measure.py` | L163–176 | `_ro_quality_params`: `eta_g`, `eta_e` only | No `eta_f` |

### B.3 LOW — Already supports `|f⟩` or is transition-agnostic

| # | File | Status |
|---|------|--------|
| B3.1 | `programs/builders/spectroscopy.py:179` | `qubit_spectroscopy_ef()` already exists |
| B3.2 | `programs/builders/spectroscopy.py:139` | `qubit_spectroscopy()` is transition-agnostic |
| B3.3 | `programs/builders/time_domain.py` | `temporal_rabi()`, `power_rabi()`, `T1_relaxation()`, `T2_ramsey()`, `T2_echo()` all take generic pulse name params |
| B3.4 | `pulses/manager.py` | `PulseOperationManager` is fully transition-agnostic |
| B3.5 | `tools/generators.py:7` | `register_qubit_rotation()` accepts arbitrary `name` string |
| B3.6 | `tools/generators.py:132` | `register_rotations_from_ref_iq()` has `prefix` parameter |
| B3.7 | `calibration/models.py:245` | `MultiStateCalibration` has `state_labels: list[str]` (N-state ready) |
| B3.8 | `calibration/models.py:100` | `ElementFrequencies.fock_freqs: list[float]` placeholder exists |
| B3.9 | `calibration/orchestrator.py` | `CalibrationOrchestrator` is experiment-agnostic |

---

## C. Proposed Target Design

### C.1 State Model Extension

**Current:** `state ∈ {g, e}`, represented as `bool`.

**Proposed:** `state ∈ {g, e, f}`, represented as `int` (0=g, 1=e, 2=f).

In QUA programs, 3-state discrimination via two thresholds on the rotated I axis:

```python
# 3-state discrimination (two thresholds, optimal rotation angle)
state = declare(int)

with if_(I_rot < threshold_ge):
    assign(state, 0)   # g
with elif_(I_rot < threshold_ef):
    assign(state, 1)   # e
with else_():
    assign(state, 2)   # f
```

**Backward compatibility**: Keep the existing `bool` path as the default. Add a `num_states=2` parameter to `measureMacro.measure()` that switches to `int` when `num_states=3`. All consumers of `state` that only care about g/e continue to work unchanged.

### C.2 Pulse Naming Convention

**Recommended convention** using the `prefix` mechanism already in `register_rotations_from_ref_iq()`:

| Transition | Pulse name | Generated via |
|-----------|-----------|--------------|
| g↔e | `ge_x180`, `ge_x90`, `ge_y90`, ... | `prefix="ge_"` |
| e↔f | `ef_x180`, `ef_x90`, `ef_y90`, ... | `prefix="ef_"` |

**Backward compatibility policy:**

- **Short term**: Keep unprefixed names (`x180`, `x90`, etc.) as aliases for `ge_x180`, etc. Both map to the same pulse in `PulseOperationManager`.
- **Medium term**: Emit deprecation warnings when unprefixed names are used. Notebooks and experiment calls shift to prefixed names.
- **Long term**: Remove unprefixed aliases (optional; they are harmless if left in place).

The `PulseOperationManager` already supports arbitrary operation names per element, so no structural change is needed in the pulse management layer.

**Naming convention for calibration targets:**

```
Calibration pulse name:     ge_ref_r180,  ef_ref_r180
Derived rotation names:     ge_x180,      ef_x180
                            ge_x90,       ef_x90
                            ge_y180,      ef_y180
                            ... etc.
```

This convention scales naturally to higher transitions if ever needed (`fh_x180` etc.).

### C.3 Discrimination Parameters Schema

**Extend `DiscriminationParams`** additively (all new fields optional, backward-compatible):

```python
class DiscriminationParams(BaseModel):
    # --- Existing g/e fields (unchanged) ---
    threshold: float           # ge threshold on rotated I axis
    angle: float               # IQ rotation angle
    mu_g: list[float]          # [I, Q] centroid for |g⟩
    mu_e: list[float]          # [I, Q] centroid for |e⟩
    sigma_g: float
    sigma_e: float
    fidelity: float | None = None
    confusion_matrix: list[list[float]] | None = None  # 2×2 or 3×3
    n_shots: int | None = None
    integration_time_ns: int | None = None
    demod_weights: list[str] | None = None
    state_prep_ops: list[str] | None = None

    # --- NEW f-state fields (all Optional for backward compat) ---
    mu_f: list[float] | None = None       # [I, Q] centroid for |f⟩
    sigma_f: float | None = None
    threshold_ef: float | None = None     # second threshold (on rotated I)
    angle_ef: float | None = None         # ef rotation angle (if different from ge)
    fidelity_ge: float | None = None      # per-pair fidelity
    fidelity_ef: float | None = None      # per-pair fidelity
    num_states: int = 2                   # 2 or 3
```

**Extend `ReadoutQuality`**:

```python
class ReadoutQuality(BaseModel):
    # --- Existing (unchanged) ---
    alpha: float | None = None
    beta: float | None = None
    F: float | None = None
    Q: float | None = None
    V: float | None = None
    t01: float | None = None
    t10: float | None = None
    confusion_matrix: list[list[float]] | None = None  # 2×2 or 3×3

    # --- NEW ---
    t02: float | None = None     # g→f transition probability
    t12: float | None = None     # e→f transition probability
    t20: float | None = None     # f→g transition probability
    t21: float | None = None     # f→e transition probability
    num_states: int = 2
```

### C.4 Calibration Data Model

`CalibrationData.pulse_calibrations` currently uses `dict[str, PulseCalibration]` keyed by pulse name. For transition-aware calibration:

**Recommended approach (minimal schema change):** Key by transition-prefixed pulse name:

```json
{
  "pulse_calibrations": {
    "ge_ref_r180": {
      "pulse_name": "ge_ref_r180",
      "element": "qubit",
      "transition": "ge",
      "amplitude": 0.32,
      "length": 40,
      "sigma": 6.67,
      "drag_coeff": 0.5,
      "anharmonicity": -200e6
    },
    "ef_ref_r180": {
      "pulse_name": "ef_ref_r180",
      "element": "qubit",
      "transition": "ef",
      "amplitude": 0.28,
      "length": 48,
      "sigma": 8.0,
      "drag_coeff": 0.3,
      "anharmonicity": -200e6
    }
  }
}
```

Add `transition` field to `PulseCalibration`:

```python
class PulseCalibration(BaseModel):
    pulse_name: str
    element: str | None = None
    transition: str | None = None      # NEW — "ge" or "ef", optional
    amplitude: float | None = None
    length: int | None = None
    sigma: float | None = None
    drag_coeff: float | None = None
    detuning: float | None = None
    phase_offset: float | None = None
    timestamp: str | None = None
```

Similarly, extend `PulseTrainResult`:

```python
class PulseTrainResult(BaseModel):
    element: str
    amp_err: float
    phase_err: float
    delta: float = 0.0
    zeta: float = 0.0
    rotation_pulse: str = "x180"
    transition: str | None = None      # NEW
    N_values: list[int] = []
    timestamp: str | None = None
```

Add explicit `ef_freq` to `ElementFrequencies`:

```python
class ElementFrequencies(BaseModel):
    # --- Existing ---
    lo_freq: float | None = None
    if_freq: float | None = None
    rf_freq: float | None = None
    qubit_freq: float | None = None
    anharmonicity: float | None = None
    fock_freqs: list[float] | None = None
    chi: float | None = None
    # ...

    # --- NEW ---
    ef_freq: float | None = None       # |e⟩↔|f⟩ frequency (Hz)
    ef_if_freq: float | None = None    # ef intermediate frequency (Hz)
```

### C.5 Measurement Macro Extension

The core change is in `measureMacro.measure()`:

```python
@classmethod
def measure(cls, ..., num_states: int = 2, state=None, ...):
    if num_states == 2:
        # === Existing binary path (entirely unchanged) ===
        state_var = declare(bool) if state is None else state
        assign(state_var, I > cls._ro_disc_params["threshold"])
    elif num_states == 3:
        # === NEW 3-state path ===
        state_var = declare(int) if state is None else state
        with if_(I_rot < cls._ro_disc_params["threshold"]):
            assign(state_var, 0)    # g
        with elif_(I_rot < cls._ro_disc_params["threshold_ef"]):
            assign(state_var, 1)    # e
        with else_():
            assign(state_var, 2)    # f
```

Extend `_ro_disc_params` setter/sync to accept the three new keys when `num_states=3`:

```python
_ro_disc_params = {
    # existing
    "threshold": ...,
    "angle": ...,
    "fidelity": ...,
    "rot_mu_g": ..., "rot_mu_e": ...,
    "unrot_mu_g": ..., "unrot_mu_e": ...,
    "sigma_g": ..., "sigma_e": ...,
    # new (only populated when 3-state calibration exists)
    "threshold_ef": ...,
    "rot_mu_f": ..., "unrot_mu_f": ...,
    "sigma_f": ...,
    "num_states": 2,   # or 3
}
```

Extend `compute_posterior_weights()`:

```python
@classmethod
def compute_posterior_weights(cls, I, Q, num_states=2):
    if num_states == 2:
        # existing (w_g, w_e) path
        ...
    elif num_states == 3:
        # 3-component Gaussian mixture posterior
        # returns (w_g, w_e, w_f)
        ...
```

### C.6 State Preparation & Reset

Extend `sequenceMacros.prepare_state()` to accept `"f"`:

```python
@classmethod
def prepare_state(cls, target_state, ..., r180="x180", ef_r180="ef_x180", ...):
    ts = target_state.lower().strip()
    if ts not in ("g", "e", "f"):
        raise ValueError(f"target_state must be 'g', 'e', or 'f', got {ts!r}")

    if ts == "g":
        # existing: do nothing (or active reset to ground)
        ...
    elif ts == "e":
        # existing: apply r180 (ge pi pulse)
        play(r180, qb_el)
        ...
    elif ts == "f":
        # NEW: apply ge pi, then ef pi
        play(r180, qb_el)       # g → e
        align()
        play(ef_r180, qb_el)    # e → f
        align()
```

Add `conditional_reset_3state()`:

```python
@classmethod
def conditional_reset_3state(cls, state_var, r180_ge, r180_ef, qb_el):
    """Active reset from any of {g, e, f} to |g⟩ using measured int state."""
    with if_(state_var == 2):       # in |f⟩
        play(r180_ef, qb_el)       # f → e
        align()
        play(r180_ge, qb_el)       # e → g
    with elif_(state_var == 1):     # in |e⟩
        play(r180_ge, qb_el)       # e → g
    # state == 0: already in |g⟩, do nothing
```

Extend `post_select()` for `"f"` target:

```python
@classmethod
def post_select(cls, accept, I, Q, target_state, policy, **kwargs):
    ts = target_state.lower().strip()
    if ts not in ("g", "e", "f"):
        raise ValueError(...)
    # For 3-state policies, use int comparison instead of threshold
    ...
```

### C.7 Analysis: Three-State Discriminator

Add `three_state_discriminator()` alongside the existing `two_state_discriminator()`:

```python
def three_state_discriminator(
    Ig, Qg,     # IQ data with qubit prepared in |g⟩
    Ie, Qe,     # IQ data with qubit prepared in |e⟩
    If, Qf,     # IQ data with qubit prepared in |f⟩
    b_print=True,
    b_plot=True,
):
    """
    Three-state single-shot readout discrimination.

    1. Find optimal IQ rotation angle that maximizes separation along I axis.
    2. Fit 3-component 1D Gaussian mixture on rotated I data.
    3. Compute two optimal thresholds (ge and ef boundaries).
    4. Build 3×3 confusion matrix.
    5. Return DiscriminationParams with num_states=3.
    """
    ...
```

Returns:

```python
{
    "angle": float,              # optimal IQ rotation angle
    "threshold": float,          # ge boundary
    "threshold_ef": float,       # ef boundary
    "fidelity": float,           # overall assignment fidelity
    "fidelity_ge": float,        # ge pair fidelity
    "fidelity_ef": float,        # ef pair fidelity
    "confusion_matrix": 3x3,
    "mu_g": [I, Q],
    "mu_e": [I, Q],
    "mu_f": [I, Q],
    "sigma_g": float,
    "sigma_e": float,
    "sigma_f": float,
    "num_states": 3,
}
```

### C.8 Readout Builder Extensions

New `iq_blobs_gef()` builder:

```python
def iq_blobs_gef(
    ro_el, qb_el,
    r180_ge, r180_ef,
    qb_therm_clks, n_runs,
):
    """IQ blob acquisition for g, e, and f states."""
    # Three loops:
    #   1. Measure |g⟩ (no prep) → save Ig, Qg
    #   2. Prepare |e⟩ via r180_ge, measure → save Ie, Qe
    #   3. Prepare |f⟩ via r180_ge + r180_ef, measure → save If, Qf
    ...
```

Similarly: `readout_butterfly_measurement_gef()` with three branches (g, e, f).

### C.9 Experiment API Design

For experiments that are inherently transition-specific (Rabi, Ramsey, T1, etc.), the approach is **parameterization, not duplication**.

**Current** (already works, no changes needed):

```python
# ge Rabi
rabi_prog = temporal_rabi(
    qb_el="qubit",
    pulse="ge_x180",
    ...
)

# ef Rabi
rabi_prog = temporal_rabi(
    qb_el="qubit",
    pulse="ef_x180",
    ...
)
```

The builder functions are already transition-agnostic because they accept arbitrary pulse name strings. **No changes needed** at the builder layer.

**Experiment classes** (higher-level wrappers) should accept a `transition="ge"` parameter that selects which calibrated pulse set and frequency to use:

```python
class PowerRabi(ExperimentBase):
    def __init__(self, session, *, transition="ge", **kwargs):
        self.transition = transition
        # Select pulse set based on transition:
        self.pulse_name = f"{transition}_ref_r180"
        ...
```

**Notebook usage after migration:**

```python
# ge calibration (default, backward-compatible)
rabi = PowerRabi(session)
rabi.run()

# ef calibration (new)
rabi_ef = PowerRabi(session, transition="ef")
rabi_ef.run()
```

### C.10 Spectroscopy Workflow for ef

The existing `qubit_spectroscopy_ef()` already demonstrates the pattern:

1. Set qubit element frequency to ge IF
2. Apply ge π-pulse to prepare `|e⟩`
3. Switch qubit element frequency to ef IF
4. Apply saturation pulse at probed ef frequency
5. Read out

This should be promoted from an ad-hoc builder to a first-class experiment that:

- Stores its result as `ef_freq` in `ElementFrequencies`
- Feeds into the ef pulse calibration pipeline
- Has a prerequisite check that ge π-pulse is calibrated

```python
class QubitSpectroscopyEF(ExperimentBase):
    """
    Prerequisite: calibrated ge_ref_r180 pulse.
    Output: ef_freq patched into calibration store.
    """
    ...
```

---

## D. Migration Strategy

### Stage 1: Foundation (Additive, No Breaking Changes)

**Goal:** Lay data model groundwork. Nothing breaks.

1. Add optional `mu_f`, `sigma_f`, `threshold_ef`, `angle_ef`, `fidelity_ge`, `fidelity_ef`, `num_states` fields to `DiscriminationParams`
2. Add optional `t02`, `t12`, `t20`, `t21`, `num_states` fields to `ReadoutQuality`
3. Add `transition` field to `PulseCalibration` and `PulseTrainResult`
4. Add `ef_freq`, `ef_if_freq` fields to `ElementFrequencies`
5. Extend `TargetState = Literal["g", "e", "f"]` in `post_selection.py`
6. Implement `three_state_discriminator()` in `analysis_tools.py`
7. Bump calibration schema version (v4 → v5) with migration that adds new optional fields

**Risk:** Zero. All new fields are `Optional` with defaults matching current 2-state behavior.

### Stage 2: Core Macro Extension

**Goal:** Enable 3-state measurement and state prep in QUA programs.

1. Add `num_states` parameter to `measureMacro.measure()` (default=2, preserving existing behavior)
2. Extend `_ro_disc_params` sync to load 3-state parameters when available
3. Extend `prepare_state()` to accept `"f"` with configurable `ef_r180` pulse name parameter
4. Add `conditional_reset_3state()` to `sequenceMacros`
5. Extend `compute_posterior_weights()` for 3-component model
6. Extend `post_select()` to accept `"f"` target state, add 3-state post-selection policies

**Risk:** Low. All extensions use keyword arguments with defaults that reproduce current behavior. `num_states=2` remains default everywhere.

### Stage 3: Pulse Naming Convention

**Goal:** Establish transition-aware naming as the canonical convention.

1. Adopt `prefix="ge_"` / `prefix="ef_"` convention in `register_rotations_from_ref_iq()`
2. Register backward-compat aliases: `x180` → `ge_x180`, etc. (both map to same pulse in POM)
3. Update calibration routines to store transition-prefixed pulse names
4. Add schema migration for `calibration.json` to prefix existing pulse names with `ge_`
5. Update `qubit_spectroscopy_ef()` to use `ge_x180` (or accept param)

**Risk:** Low-medium. The POM wildcard mechanism makes aliases cheap. Existing code continues to work via aliases. Notebooks need updating over time.

### Stage 4: New Readout Builders & Experiments

**Goal:** Full 3-state readout and calibration pipeline.

1. Add `iq_blobs_gef()` builder
2. Add `readout_butterfly_measurement_gef()` builder (3 branches)
3. Add `readout_core_efficiency_calibration_gef()` builder
4. Create `IQBlobGEF` experiment class wrapping `iq_blobs_gef()` + `three_state_discriminator()`
5. Create `QubitSpectroscopyEF` experiment class
6. Create ef-specific calibration experiment wrappers (PowerRabi with ef defaults, DRAG ef, etc.)
7. Update notebooks with ef examples

**Risk:** Medium. New code, requires testing with real hardware.

---

## E. Implementation Roadmap

### Phase 1: Data Model & Analysis (no QUA changes)

- [ ] Extend `DiscriminationParams` with `mu_f`, `sigma_f`, `threshold_ef`, `angle_ef`, `fidelity_ge`, `fidelity_ef`, `num_states`
- [ ] Extend `ReadoutQuality` with `t02`, `t12`, `t20`, `t21`, `num_states`
- [ ] Add `transition` to `PulseCalibration` and `PulseTrainResult`
- [ ] Add `ef_freq`, `ef_if_freq` to `ElementFrequencies`
- [ ] Extend `TargetState` literal to include `"f"`
- [ ] Implement `three_state_discriminator()` in `analysis_tools.py`
- [ ] Extend `PostSelectionConfig` for 3-state policies
- [ ] Add schema migration v4 → v5
- [ ] Bump calibration schema version

### Phase 2: Measurement & Macro Extension

- [ ] Add `num_states` kwarg to `measureMacro.measure()` (default=2)
- [ ] Implement 3-state threshold discrimination logic in QUA
- [ ] Extend `_ro_disc_params` setter/sync for 3-state params
- [ ] Extend `compute_posterior_weights()` for 3 states
- [ ] Extend `prepare_state()` for `"f"` target
- [ ] Add `conditional_reset_3state()`
- [ ] Extend `post_select()` for `"f"` target

### Phase 3: Naming & Calibration

- [ ] Adopt transition prefix convention (`ge_`, `ef_`) in `register_rotations_from_ref_iq()`
- [ ] Register backward-compat aliases (`x180` → `ge_x180`)
- [ ] Create schema migration for existing `calibration.json` files
- [ ] Update `CalibrationStore` getter/setter methods
- [ ] Update experiment classes to accept/pass `transition` parameter

### Phase 4: New Builders & Experiments

- [ ] `iq_blobs_gef()` builder
- [ ] `readout_butterfly_measurement_gef()` builder
- [ ] `readout_core_efficiency_calibration_gef()` builder
- [ ] `IQBlobGEF` experiment class
- [ ] `QubitSpectroscopyEF` experiment class
- [ ] ef-specific Rabi, DRAG, Ramsey experiment wrappers
- [ ] Update notebooks with ef calibration examples

---

## F. Risks and Tradeoffs

### Risk 1: QUA `int` vs `bool` State Variable

**Impact**: Changing `state` from `bool` to `int` affects every downstream consumer. QUA's `bool` type is more efficient for FPGA branching; `int` comparisons use more FPGA resources.

**Mitigation**: Keep `bool` as default for 2-state mode. Only allocate `int` state when `num_states=3` is explicitly requested. All boolean-returning APIs remain unchanged. The `with if_` / `with elif_` structure compiles to efficient FPGA conditional blocks.

### Risk 2: Readout Fidelity for 3-State Discrimination

**Impact**: Distinguishing `|f⟩` from `|e⟩` in dispersive readout may have very low fidelity depending on the χ/κ regime. If `χ_ef ≈ χ_ge`, the `|f⟩` blob overlaps with `|e⟩` and 3-state discrimination becomes unreliable.

**Mitigation**: `DiscriminationParams.num_states` makes the mode explicit. The `three_state_discriminator()` must report per-pair fidelities and a 3×3 confusion matrix. Experiments should check `fidelity_ef` before enabling 3-state readout. Stage the rollout: support `|f⟩` in **control** first (Stages 1–3), add 3-state **readout** later (Stage 4) only when the hardware regime supports it.

### Risk 3: Pulse Name Collision During Migration

**Impact**: If users have existing calibrations with unprefixed `x180` that is implicitly ge, and new code registers `ef_x180`, the two coexist. But if some code path tries to register `ge_x180` that duplicates existing `x180`, conflicts arise.

**Mitigation**: In Stage 3, `ge_x180` is registered as the canonical name and `x180` is registered as an alias (both map to the same pulse in POM). `PulseOperationManager` already supports multiple op names mapping to the same pulse. The alias is implemented as an additional `el_ops` entry, not a copy.

### Risk 4: Calibration Schema Migration

**Impact**: Existing `calibration.json` files need the new optional fields. Schema migration must be lossless.

**Mitigation**: All new fields are `Optional` with defaults. The schema migration registry (`core/schemas.py`) already supports versioned migration chains. Migration from v4 → v5 only adds the new optional fields (no existing field is removed or renamed). Pydantic's `model_validate()` with `extra="allow"` handles forward-compatible loading.

### Risk 5: Scope Creep Toward `|h⟩` and Beyond

**Impact**: If the design hard-codes `num_states=3`, a future 4th level requires another refactor.

**Mitigation**: The core design choices are N-level ready:
- `int` state variable works for any N
- `N×N` confusion matrix generalizes naturally
- Threshold-based discrimination needs `(N−1)` thresholds — works for any N
- `transition` string field on calibration records is freeform
- Pulse naming convention (`ge_`, `ef_`, `fh_`) scales arbitrarily

The only 3-specific items are: (a) the `"f"` string literal in `prepare_state()` and `post_select()` — straightforward to extend to 4+ levels; (b) the triple reset sequence in `conditional_reset_3state()` — a natural generalization exists for N levels (apply π-pulses from highest level down).

### Risk 6: ef Pulse Calibration Prerequisites

**Impact**: Every ef calibration experiment requires a pre-calibrated ge π-pulse to prepare `|e⟩`. If the ge pulse drifts, ef calibrations become unreliable.

**Mitigation**: The `CalibrationOrchestrator` should enforce prerequisite checks. An ef experiment should verify that a recent, valid ge calibration exists before running. This is an orchestration policy, not a framework limitation.

---

## Appendix: Three Plans Compared

| Aspect | Plan A: Minimal Intervention | Plan B: Recommended Balanced | Plan C: Clean-Slate Ideal |
|--------|------------------------------|------------------------------|---------------------------|
| **State model** | Keep `bool`, run separate `ef_` experiments manually | `int` with `num_states` kwarg, default 2 | Generic `N`-level `StateVector` class |
| **Discrimination** | Separate `ef_discriminator()` function, store results ad-hoc | Extended `DiscriminationParams` with `num_states` | `NStateDiscriminator` class with pluggable classifiers (GMM, SVM) |
| **Pulse names** | Manual prefixes by user convention | Convention via `prefix` kwarg, aliases for backward compat | `TransitionPulseRegistry` object with transition-aware lookup |
| **State prep** | Manual ef sequences in notebooks | `prepare_state("f")` with `ef_r180` parameter | `prepare_state(level=2)` with auto-sequencing from any level to any level |
| **Schema changes** | None | Additive optional fields + schema migration | Full schema redesign with nested `transitions` dict |
| **Breaking changes** | Zero | Zero | Significant (calibration JSON, experiment APIs) |
| **Implementation scope** | Small (1–2 weeks of work) | Medium (3–4 phases) | Large (full rewrite of calibration + macro layers) |
| **Future-proof** | Low (same work needed again for `\|h⟩`) | Good (through ~4 levels with minimal additional work) | Excellent (arbitrary N-level) |
| **Pragmatism** | High (fastest path to running ef experiments) | High (clean design, no breakage, staged rollout) | Low (high effort, high breakage risk) |

**Recommendation: Plan B (Balanced)**

It delivers full `|f⟩` support with zero breaking changes, leverages existing extension points (`prefix`, freeform pulse names, optional Pydantic fields), and the `num_states` pattern generalizes naturally to `|h⟩` if ever needed. The staged rollout (Phases 1–4) allows each phase to be validated on hardware before proceeding.
