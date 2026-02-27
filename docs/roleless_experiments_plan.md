# Roleless Experiments: Design Plan & Migration Report

**Version:** 1.0.0
**Date:** 2026-02-26
**Status:** Design proposal (pre-implementation)
**Scope:** Remove fixed `qubit/readout/storage` role assumptions from experiment classes

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture & Problem Statement](#2-current-architecture--problem-statement)
3. [General Refactor Rule](#3-general-refactor-rule)
4. [Readout Handling Plan](#4-readout-handling-plan)
5. [Frequency Management Plan](#5-frequency-management-plan)
6. [Experiment Requirements Survey](#6-experiment-requirements-survey)
7. [Before / After Examples](#7-before--after-examples)
8. [Migration Plan](#8-migration-plan)
9. [Risks & Open Questions](#9-risks--open-questions)
10. [Appendix: Full Experiment Element Matrix](#appendix-full-experiment-element-matrix)

---

## 1. Executive Summary

Today every experiment class hard-codes assumptions about the existence of
three named roles -- `qubit`, `readout`, and `storage` -- accessed through
`self.attr.qb_el`, `self.attr.ro_el`, and `self.attr.st_el`. This makes
the API brittle (element names are strings baked deep inside classes),
non-portable (adding a second qubit means duplicating experiment code), and
opaque (the user cannot tell from the `run()` signature which hardware
channels are actually required).

This plan proposes a **roleless experiment API** where:

- The user **explicitly passes** the elements (or structured channel
  bundles) each experiment needs via `run()` keyword arguments.
- Experiments **never** reach into `self.attr` for element names or
  frequencies inside `run()` -- all physics parameters flow through the
  function signature.
- A thin **alias layer** (`ExperimentSetup` / session helpers) keeps
  common workflows concise by letting users define named aliases once
  and reuse them.
- **measureMacro** is replaced with a per-call `ReadoutHandle` that
  carries the readout element, operation, weights, and discrimination
  state without global singleton state.
- **Frequency management** becomes explicit: experiments declare which
  elements they will drive and at what frequencies, with validation
  and reproducibility guarantees.

The refactor is **incremental**: a compatibility adapter lets all
existing notebook code continue working unchanged while new code
migrates to the explicit API one experiment at a time.

---

## 2. Current Architecture & Problem Statement

### 2.1 How roles are wired today

```
HardwareDefinition.set_roles(qubit="qubit", readout="resonator", storage="storage")
          |
          v
    cqed_params.json  --->  cQED_attributes dataclass
      qb_el = "qubit"         .qb_el  .ro_el  .st_el
      ro_el = "resonator"     .qb_fq  .ro_fq  .st_fq
      st_el = "storage"       .qb_therm_clks  ...
          |
          v
    ExperimentBase.__init__(session)
      self.attr  -->  all experiments grab element names / frequencies here
```

**Concrete coupling points inside experiment classes:**

| Access pattern | Files affected | Count |
|---|---|---|
| `self.attr.qb_el` | All time-domain, spectroscopy, cavity, calibration | ~40 |
| `self.attr.ro_el` | Spectroscopy, readout calibration, resonator | ~15 |
| `self.attr.st_el` | All cavity/Fock experiments | ~12 |
| `self.attr.qb_fq` / `.ro_fq` / `.st_fq` | Frequency setup | ~25 |
| `self.attr.qb_therm_clks` | Thermalization waits | ~20 |
| `measureMacro._drive_frequency` | `T2Ramsey`, `set_standard_frequencies` | ~5 |
| `self.get_qubit_frequency()` | Uses `self.attr.qb_el` internally | ~8 |
| `self.set_standard_frequencies()` | Uses `self.attr.ro_el` + `self.attr.qb_el` | ~15 |

### 2.2 ExperimentBindings (v2.0.0)

The Phase 1 binding refactor introduced `ExperimentBindings` with
hard-coded role fields:

```python
@dataclass
class ExperimentBindings:
    qubit: OutputBinding
    readout: ReadoutBinding
    storage: OutputBinding | None = None
    extras: dict[str, OutputBinding | ReadoutBinding] = field(default_factory=dict)
```

This was a step forward (physical channel identity vs. string names) but
kept the role vocabulary encoded in the type itself.

### 2.3 What's wrong

1. **Inflexible naming**: Cannot represent "second qubit" or "pump cavity"
   without abusing `extras`.
2. **Implicit dependencies**: A user calling `T1Relaxation(session).run()`
   cannot tell from the signature that the experiment needs a qubit
   element and a readout element. They only discover this at runtime if
   `self.attr.qb_el` is `None`.
3. **Global singleton readout**: `measureMacro` is a class-level singleton.
   Switching readout configuration between calls requires careful
   context manager nesting and risks state leakage.
4. **Frequency entanglement**: `set_standard_frequencies()` hard-codes
   which elements get their frequencies set and in what order. Adding a
   new element type requires editing `ExperimentBase`.

---

## 3. General Refactor Rule

### 3.1 Core principle

> **Every experiment's `run()` method receives all hardware channel
> identifiers and physics parameters it needs through its keyword
> arguments. It never reads element names or frequencies from
> `self.attr`.**

### 3.2 Naming conventions for element parameters

Use **semantic role names** scoped to the experiment's physics, not
global role names. The vocabulary is small:

| Parameter name | Type | Semantics |
|---|---|---|
| `target_el` | `str` | The element being driven / measured (general single-element experiments) |
| `drive_el` | `str` | Control drive element (when ambiguity with readout exists) |
| `readout` | `ReadoutHandle` | Readout channel bundle (element + operation + weights + discrimination) |
| `probe_el` | `str` | Element used for spectroscopy probing |
| `storage_el` | `str` | Storage cavity element |
| `aux_el` | `str` | Auxiliary element (second qubit, pump, etc.) |

For experiments that are inherently about a specific physics concept
(e.g. "qubit T1"), the parameter name should reflect the actual role:

```python
def run(self, *, qubit: str, readout: ReadoutHandle, ...) -> RunResult:
```

This is **not** the same as the current design. Today `qubit` is a
hidden dependency read from `self.attr`; in the new design it is an
explicit parameter that the caller supplies.

### 3.3 Structured channel bundles

For experiments needing multiple related channels, accept a structured
bundle rather than N separate string parameters:

```python
@dataclass(frozen=True)
class QubitBundle:
    """Everything needed to perform single-qubit experiments."""
    drive_el: str                 # QM element name for qubit drive
    drive_freq: float             # Qubit transition frequency (Hz)
    readout: ReadoutHandle        # Readout channel bundle
    therm_clks: int = 250000      # Thermalization wait (clock cycles)

@dataclass(frozen=True)
class CavityBundle:
    """Extension for cavity experiments."""
    qubit: QubitBundle
    storage_el: str               # QM element name for storage cavity drive
    storage_freq: float           # Storage transition frequency (Hz)
    storage_therm_clks: int = 500000
```

Bundles are **optional convenience** -- every experiment also accepts
the raw element strings directly. The bundle just groups them for common
workflows.

### 3.4 Session-level alias factory

Users define aliases once at session start and reuse them:

```python
# Setup (once per session, analogous to today's set_roles)
qb = session.qubit_bundle(
    drive_el="qubit",
    readout_el="resonator",
    readout_op="readout",
)

# Usage (concise, explicit)
t1 = T1Relaxation(session)
result = t1.run(qubit=qb, delay_end=50*u.us, dt=500, n_avg=2000)

# Or fully explicit (no alias):
result = t1.run(
    qubit="qubit",
    readout=session.readout_handle("resonator", "readout"),
    qubit_freq=6.15e9,
    therm_clks=250000,
    delay_end=50*u.us,
    dt=500,
    n_avg=2000,
)
```

### 3.5 How defaults work

Experiments MAY provide defaults derived from the session context, but
**only** when the parameter is not supplied by the caller:

```python
def run(self, *, qubit: str | QubitBundle | None = None, ...) -> RunResult:
    if qubit is None:
        qubit = self._default_qubit_bundle()   # reads self.attr as fallback
    # From here on, only use `qubit`, never self.attr.qb_el
```

This preserves backward compatibility while making the dependency
explicit. When `qubit=None`, the experiment falls back to session
defaults. When `qubit="my_qubit_2"`, the experiment uses exactly what
was passed.

### 3.6 Validation contract

Every experiment validates its inputs at the top of `run()`:

```python
if qubit_el is None:
    raise ValueError(
        f"{self.name}.run() requires 'qubit_el'. Pass it explicitly "
        f"or ensure session attributes define a default qubit element."
    )
```

No silent fallbacks to `None`. No element name guessing.

---

## 4. Readout Handling Plan

### 4.1 Options considered

| Option | Description | Pros | Cons |
|---|---|---|---|
| **A: Session-level contract** | measureMacro stays, configured once per session | Minimal code change | Global state, can't run two readouts simultaneously |
| **B: Binding-driven ReadoutHandle** | Replace measureMacro with per-call handles | Clean, testable, composable | Large migration surface |
| **C: Hybrid** | ReadoutHandle for new code, measureMacro adapter for legacy | Incremental migration | Two code paths during transition |

### 4.2 Recommendation: Option C (Hybrid) with B as target

**Phase 1 (immediate):** Introduce `ReadoutHandle` as a frozen dataclass
that carries all readout configuration for a single measurement call.

```python
@dataclass(frozen=True)
class ReadoutHandle:
    """Immutable readout channel configuration for a single experiment call."""

    element: str                          # QM element name (e.g. "resonator")
    operation: str                        # Pulse operation (e.g. "readout")
    drive_frequency: float                # RF drive frequency (Hz)

    # Demodulation
    demod_method: str = "dual_demod.full"
    weight_keys: tuple[str, ...] = ("cos", "sin", "minus_sin")
    weight_length: int | None = None

    # Discrimination (optional)
    threshold: float | None = None
    rotation_angle: float | None = None

    # Post-selection (optional)
    post_select_config: dict | None = None

    # Quality metrics (optional, for confusion correction)
    confusion_matrix: np.ndarray | None = None
    transition_matrix: list | None = None
```

**Phase 2 (migration):** Builders accept `ReadoutHandle` and call a
new `emit_measurement(handle, ...)` function instead of
`measureMacro.measure(...)`.

```python
# In builder code:
def T1_relaxation(r180, delay_clks, therm_clks, n_avg, *,
                  qubit_el: str, readout: ReadoutHandle):
    with program() as prog:
        ...
        emit_measurement(readout, targets=[I, Q])
        ...
```

**Phase 3 (deprecation):** `measureMacro.measure()` becomes a thin
wrapper that constructs a `ReadoutHandle` from its internal state and
delegates.

### 4.3 ReadoutHandle construction helpers

```python
# From session (preferred -- uses persisted calibration state)
ro = session.readout_handle(
    element="resonator",
    operation="readout",
)  # auto-fills drive_frequency, threshold, weights from calibration store

# Explicit override
ro = ReadoutHandle(
    element="resonator",
    operation="readout",
    drive_frequency=8.596e9,
    threshold=-1.89e-5,
    rotation_angle=0.397,
)

# From measureMacro (backward compat bridge)
ro = ReadoutHandle.from_measure_macro()
```

### 4.4 How ReadoutHandle flows through the stack

```
Notebook:
  ro = session.readout_handle("resonator", "readout")
  t1 = T1Relaxation(session)
  t1.run(qubit="qubit", readout=ro, ...)
      |
      v
Experiment class (T1Relaxation.run):
  self._resolve_readout(readout)   # validate, set IF frequency
  prog = build_T1_program(qubit_el=qubit, readout=ro, ...)
      |
      v
Builder (programs/builders/time_domain.py):
  emit_measurement(readout, targets=[I, Q], state=state)
      |
      v
emit_measurement():
  measure(readout.operation, readout.element, None,
          demod.full(readout.weight_keys[0], I, ...),
          demod.full(readout.weight_keys[1], Q, ...))
  if readout.threshold is not None:
      assign(state, I > readout.threshold)
```

### 4.5 measureMacro compatibility bridge

During migration, `measureMacro.measure()` continues to work.
Experiments that have been migrated use `ReadoutHandle` directly;
experiments that haven't been migrated yet still call `measureMacro`.

The bridge is:

```python
class measureMacro:
    @classmethod
    def as_readout_handle(cls) -> ReadoutHandle:
        """Snapshot current singleton state into an immutable ReadoutHandle."""
        return ReadoutHandle(
            element=cls.active_element(),
            operation=cls._active_op,
            drive_frequency=cls._drive_frequency,
            demod_method=cls._demod_fn,
            threshold=cls._ro_disc_params.get("threshold"),
            rotation_angle=cls._ro_disc_params.get("angle"),
            confusion_matrix=cls._ro_quality_params.get("confusion_matrix"),
            ...
        )
```

---

## 5. Frequency Management Plan

### 5.1 Current state

Frequencies are set through a chain of implicit steps:

1. `session.open()` loads `cqed_params.json` -> `attr.qb_fq`, `attr.ro_fq`, `attr.st_fq`
2. `session.refresh_attribute_frequencies_from_calibration()` overwrites
   attrs from CalibrationStore
3. `experiment.set_standard_frequencies()` calls
   `hw.set_element_fq(attr.qb_el, ...)` and
   `hw.set_element_fq(attr.ro_el, ...)`
4. Some experiments further override with
   `hw.set_element_fq(attr.qb_el, qb_base_fq + qb_detune)`
5. Builders receive `if_frequencies` arrays already computed relative
   to the LO

**Problems:**

- Steps 1-3 are implicit -- the user doesn't see which frequencies
  get set or when.
- Step 4 mutates global QM hardware state as a side effect of
  `run()`.
- There's no snapshot/restore: if a Ramsey experiment detunes the
  qubit, the next experiment inherits that detuned frequency unless
  it explicitly resets.

### 5.2 Proposed model

#### 5.2.1 Frequencies as explicit run() parameters

Every experiment that needs to set element frequencies accepts them
as `run()` keyword arguments:

```python
def run(self, *, qubit_freq: float | None = None, readout_freq: float | None = None, ...):
```

When `None`, the experiment resolves from (in order):
1. The `ReadoutHandle.drive_frequency` / `QubitBundle.drive_freq`
2. CalibrationStore `frequencies.<element>.qubit_freq`
3. Session attributes (`attr.qb_fq`)

This resolution is performed once at the top of `run()` and the
resolved value is stored in `self._run_params` for provenance.

#### 5.2.2 Frequency context manager

To prevent state leakage between experiments, introduce a frequency
context manager that snapshots and restores IF frequencies:

```python
class FrequencyScope:
    """Snapshot element IF frequencies before an experiment and restore after."""

    def __init__(self, hw, elements: list[str]):
        self.hw = hw
        self.elements = elements
        self._snapshot: dict[str, int] = {}

    def __enter__(self):
        for el in self.elements:
            self._snapshot[el] = self.hw.get_element_if(el)
        return self

    def __exit__(self, *exc):
        for el, if_val in self._snapshot.items():
            self.hw.qm.set_intermediate_frequency(el, if_val)
```

Usage in experiments:

```python
def run(self, *, qubit: str, qubit_freq: float, ...):
    with FrequencyScope(self.hw, [qubit]):
        self.hw.set_element_fq(qubit, qubit_freq)
        prog = ...
        return self.run_program(prog, ...)
    # frequencies restored automatically
```

#### 5.2.3 IF frequency computation

The existing `create_if_frequencies()` helper works well but takes
element names to look up LO frequencies. In the new model, pass the
LO frequency explicitly:

```python
# Before:
if_freqs = create_if_frequencies(attr.qb_el, rf_begin, rf_end, df, lo_freq=lo_qb)

# After:
lo_qb = self.hw.get_element_lo(qubit_el)  # or from ReadoutHandle
if_freqs = create_if_frequencies(qubit_el, rf_begin, rf_end, df, lo_freq=lo_qb)
```

No change to the helper itself -- only the call site changes from
`attr.qb_el` to the explicit `qubit_el` parameter.

#### 5.2.4 Reproducibility: frequency provenance in RunResult

Every `RunResult` records which frequencies were active:

```python
result.metadata["frequency_state"] = {
    "qubit": {"element": "qubit", "rf_freq": 6.15e9, "lo_freq": 6.2e9, "if_freq": -50e6},
    "readout": {"element": "resonator", "rf_freq": 8.596e9, "lo_freq": 8.8e9, "if_freq": -204e6},
}
```

This is a metadata annotation, not a behavioral change.

### 5.3 Stale frequency prevention

Two mechanisms:

1. **FrequencyScope** (section 5.2.2) restores IF frequencies after
   each experiment call, preventing accidental inheritance.

2. **CalibrationStore freshness check**: When resolving default
   frequencies, compare `CalibrationStore.last_modified` against
   session start time. If calibrations were updated by a prior
   experiment in the same session, use the updated value (not the
   stale `attr` value).

---

## 6. Experiment Requirements Survey

### 6.1 Element requirement categories

| Category | Elements needed | Pattern |
|---|---|---|
| **Q** (qubit-only) | qubit drive + readout | Single drive element + measurement |
| **R** (readout-only) | readout | Readout-only measurement |
| **QR** (qubit + explicit readout) | qubit drive + readout (both explicit) | Readout frequency matters (e.g. spectroscopy) |
| **QS** (qubit + storage) | qubit + storage + readout | Cavity experiments |
| **QRS** (qubit + readout + storage) | qubit + readout + storage (all explicit) | Full 3-element experiments |
| **M** (measurement-only) | readout | Only measurement, no drive |

### 6.2 Per-experiment requirements table

| Experiment | Category | Drive element(s) | Readout | Freq params needed | Pulse params needed |
|---|---|---|---|---|---|
| **Spectroscopy** | | | | | |
| `ResonatorSpectroscopy` | R | -- | readout (sweep) | `rf_begin`, `rf_end`, `df` | `readout_op` |
| `ResonatorPowerSpectroscopy` | R | -- | readout (sweep) | `rf_begin`, `rf_end`, `df` | `readout_op`, gain sweep |
| `ResonatorSpectroscopyX180` | QR | qubit | readout (sweep) | `rf_begin`, `rf_end`, `df` | `x180` |
| `ReadoutTrace` | M | -- | readout | `readout_freq` | -- |
| `QubitSpectroscopy` | Q | qubit (sweep) | readout | `rf_begin`, `rf_end`, `df` | `pulse`, `qb_gain`, `qb_len` |
| **Time Domain** | | | | | |
| `PowerRabi` | Q | qubit | readout | `qubit_freq` (implicit) | `op`, `max_gain`, `dg` |
| `TemporalRabi` | Q | qubit | readout | `qubit_freq` (implicit) | `pulse`, `pulse_gain`, duration range |
| `T1Relaxation` | Q | qubit | readout | `qubit_freq` (implicit) | `r180`, delay range |
| `T2Ramsey` | QR | qubit | readout | `qubit_freq` + `qb_detune` | `r90`, delay range |
| `T2Echo` | Q | qubit | readout | `qubit_freq` (implicit) | `r90`, `r180`, delay range |
| `TimeRabiChevron` | QR | qubit (freq sweep) | readout | `rf_begin`, `rf_end`, `df` | `pulse`, duration range |
| `PowerRabiChevron` | QR | qubit (freq sweep) | readout | `rf_begin`, `rf_end`, `df` | `op`, gain range |
| **Calibration** | | | | | |
| `AllXY` | Q | qubit | readout | `qubit_freq` (implicit) | rotation sequence |
| `DRAGCalibration` | Q | qubit | readout | `qubit_freq` (implicit) | `x180`, `x90`, `y180`, `y90`, alpha sweep |
| `RandomizedBenchmarking` | Q | qubit | readout | `qubit_freq` (implicit) | Clifford primitives |
| `PulseTrainCalibration` | Q | qubit | readout | `qubit_freq` (implicit) | `arb_rot`, prep functions |
| `IQBlob` | Q | qubit | readout | both freq (implicit) | `r180` |
| `ReadoutGEDiscrimination` | QR | qubit | readout | `readout_freq` | `r180`, readout op |
| `ReadoutButterflyMeasurement` | QR | qubit | readout | `readout_freq` | `r180`, readout op |
| `ReadoutWeightsOptimization` | QR | qubit | readout | `readout_freq` | `r180`, readout op |
| `CalibrateReadoutFull` | QR | qubit | readout | `readout_freq` | `r180`, readout op |
| **Cavity / Fock** | | | | | |
| `StorageSpectroscopy` | QS | qubit, storage (sweep) | readout | `rf_begin`, `rf_end`, `df` | `disp`, `sel_r180` |
| `NumSplittingSpectroscopy` | QS | qubit (sweep), storage | readout | `rf_centers`, `rf_spans` | `sel_r180`, `state_prep` |
| `StorageChiRamsey` | QRS | qubit, storage | readout | `fock_fq`, delay sweep | `disp_pulse`, `x90_pulse` |
| `StorageRamsey` | QRS | qubit, storage | readout | storage freq, delay sweep | `disp_pulse`, `sel_r180` |
| `FockResolvedSpectroscopy` | QS | qubit (sweep per Fock) | readout | `probe_fqs`, `fock_ifs` | `sel_r180`, `state_prep` |
| `FockResolvedT1` | QS | qubit, storage | readout | `fock_fqs`, delay sweep | `fock_disps`, `sel_r180` |
| `FockResolvedRamsey` | QS | qubit, storage | readout | `fock_fqs`, detunings | `disps`, `sel_r90` |
| `FockResolvedPowerRabi` | QS | qubit, storage | readout | `fock_ifs`, gain sweep | `disp_n_list`, `sel_qb_pulse` |
| **Tomography** | | | | | |
| `QubitStateTomography` | Q | qubit | readout | `qubit_freq` (implicit) | `x90`, `yn90`, `state_prep` |
| `StorageWignerTomography` | QRS | qubit, storage | readout | storage freq | `prep_gates`, `base_disp`, `x90_pulse` |
| `SNAPOptimization` | QRS | qubit, storage | readout | `fock_probe_fqs` | `snap_gate`, `disp_gate` |
| **SPA** | | | | | |
| `SPAFluxOptimization` | R | -- | readout | `sample_fqs`, DC sweep | -- |
| `SPAPumpFrequencyOptimization` | QR | qubit | readout | pump freq sweep | `r180`, readout op |

### 6.3 Observations

1. **All experiments need readout.** Even "qubit-only" experiments like
   `PowerRabi` read out through the resonator. Today this is implicit
   via `measureMacro`; in the new model it must be explicit via
   `ReadoutHandle`.

2. **Most qubit experiments need only `qubit_el` + `readout`.**
   The `QubitBundle` covers ~70% of experiments.

3. **Cavity experiments always need `qubit_el` + `storage_el` + `readout`.**
   The `CavityBundle` covers these.

4. **Frequency sweep experiments** (`*Spectroscopy`, `*Chevron`) always
   pass sweep ranges explicitly -- they already have `rf_begin`/`rf_end`
   parameters and don't rely on implicit frequency state.

5. **Thermalization clocks** appear in every builder but vary per
   element. They should attach to the channel bundle, not be global
   `attr` fields.

---

## 7. Before / After Examples

### 7.1 PowerRabi

**Before (current):**

```python
rabi = PowerRabi(session)
result = rabi.run(
    max_gain=1.2,
    dg=0.04,
    op="ref_r180",
    n_avg=4000,
)
# Internally:
#   attr = self.attr
#   self.set_standard_frequencies()           # sets qb + ro freqs from attr
#   prog = cQED_programs.power_rabi(
#       op, gains, attr.qb_therm_clks, n_avg,
#       qb_el=attr.qb_el,                    # <-- hidden dependency
#       bindings=self._bindings_or_none,
#   )
```

**After (roleless):**

```python
rabi = PowerRabi(session)
result = rabi.run(
    max_gain=1.2,
    dg=0.04,
    op="ref_r180",
    n_avg=4000,
    # Explicit channel specification:
    qubit="qubit",                            # or QubitBundle
    readout=session.readout_handle("resonator", "readout"),
    qubit_freq=6.15e9,                        # or None -> resolve from calibration
    therm_clks=250000,                        # or None -> resolve from session
)

# With alias (same behavior, concise):
qb = session.qubit_bundle("qubit", "resonator", "readout")
result = rabi.run(qubit=qb, max_gain=1.2, dg=0.04, op="ref_r180", n_avg=4000)
```

**Internal implementation:**

```python
class PowerRabi(ExperimentBase):
    def run(self, *, op: str, max_gain: float, dg: float, n_avg: int = 1000,
            qubit: str | QubitBundle | None = None,
            readout: ReadoutHandle | None = None,
            qubit_freq: float | None = None,
            therm_clks: int | None = None,
            ) -> RunResult:

        qubit_el, readout_h, qb_freq, therm = self._resolve_qubit_params(
            qubit=qubit, readout=readout,
            qubit_freq=qubit_freq, therm_clks=therm_clks,
        )
        gains = np.arange(0, max_gain + dg / 2, dg)

        with FrequencyScope(self.hw, [qubit_el, readout_h.element]):
            self.hw.set_element_fq(qubit_el, qb_freq)
            self.hw.set_element_fq(readout_h.element, readout_h.drive_frequency)

            prog = build_power_rabi(
                op=op, gains=gains, therm_clks=therm,
                n_avg=n_avg, qubit_el=qubit_el, readout=readout_h,
            )
            return self.run_program(prog, n_total=n_avg, ...)
```

### 7.2 T1Relaxation

**Before:**

```python
t1 = T1Relaxation(session)
result = t1.run(delay_end=50*u.us, dt=500, n_avg=2000)
# Internally uses: attr.qb_el, attr.qb_therm_clks, set_standard_frequencies()
```

**After:**

```python
t1 = T1Relaxation(session)

# Concise (session defaults):
result = t1.run(delay_end=50*u.us, dt=500, n_avg=2000)

# Explicit:
result = t1.run(
    delay_end=50*u.us, dt=500, n_avg=2000,
    qubit="qubit",
    readout=session.readout_handle("resonator", "readout"),
    r180="x180",
)
```

### 7.3 T2Ramsey

**Before (notebook cell 41):**

```python
t2r = T2Ramsey(session)
result = t2r.run(
    qb_detune=int(0.2 * 1e6),
    delay_end=40 * u.us,
    dt=100,
    n_avg=4000,
    qb_detune_MHz=0.2,
)
# Internally:
#   qb_base_fq = self.get_qubit_frequency()
#   self.hw.set_element_fq(attr.qb_el, qb_base_fq + qb_detune)
#   self.hw.set_element_fq(attr.ro_el, measureMacro._drive_frequency)  # <-- singleton!
```

**After:**

```python
t2r = T2Ramsey(session)
result = t2r.run(
    qb_detune_MHz=0.2,
    delay_end=40 * u.us,
    dt=100,
    n_avg=4000,
    qubit="qubit",
    readout=session.readout_handle("resonator", "readout"),
    qubit_freq=6.15e9,     # base frequency; detuning added internally
)

# Concise (session defaults + calibration store freq):
result = t2r.run(qb_detune_MHz=0.2, delay_end=40*u.us, dt=100, n_avg=4000)
```

**Key change:** The readout frequency no longer comes from
`measureMacro._drive_frequency` (a global singleton field). It comes
from `readout.drive_frequency` (an immutable field on the
`ReadoutHandle` passed to `run()`).

### 7.4 ReadoutGEDiscrimination

**Before:**

```python
ge = ReadoutGEDiscrimination(session)
result = ge.run(
    "readout",
    attr.ro_fq,
    r180="x180",
    n_samples=50000,
    update_measure_macro=True,
    apply_rotated_weights=True,
    persist=True,
)
# Internally: uses attr.ro_el, attr.qb_el, measureMacro state mutation
```

**After:**

```python
ge = ReadoutGEDiscrimination(session)
result = ge.run(
    readout=session.readout_handle("resonator", "readout"),
    qubit="qubit",
    r180="x180",
    n_samples=50000,
    persist=True,
)
# analyze() returns updated ReadoutHandle with new threshold/angle:
analysis = ge.analyze(result, update_calibration=True)
updated_ro = analysis.metadata["updated_readout_handle"]
# Use updated_ro for subsequent experiments
```

**Key change:** Instead of mutating `measureMacro` class state
(`update_measure_macro=True`), the analysis returns an updated
`ReadoutHandle` that the user can pass to subsequent experiments.
State flows forward explicitly, not through a global singleton.

### 7.5 StorageSpectroscopy (Cavity workflow)

**Before:**

```python
st_spec = StorageSpectroscopy(session)
result = st_spec.run(
    disp="const_alpha",
    rf_begin=5200 * u.MHz,
    rf_end=5280 * u.MHz,
    df=200 * u.kHz,
    storage_therm_time=500,
    n_avg=50,
)
# Internally:
#   lo_freq = self.hw.get_element_lo(attr.st_el)      # <-- attr.st_el
#   prog = cQED_programs.storage_spectroscopy(
#       attr.qb_el, attr.st_el, disp, sel_r180,       # <-- hardcoded roles
#       if_freqs, storage_therm_time, n_avg,
#   )
```

**After:**

```python
st_spec = StorageSpectroscopy(session)
result = st_spec.run(
    disp="const_alpha",
    rf_begin=5200 * u.MHz,
    rf_end=5280 * u.MHz,
    df=200 * u.kHz,
    storage_therm_time=500,
    n_avg=50,
    # Explicit channels:
    qubit="qubit",
    storage="storage",
    readout=session.readout_handle("resonator", "readout"),
    sel_r180="sel_x180",
)

# Or with CavityBundle:
cav = session.cavity_bundle("qubit", "storage", "resonator", "readout")
result = st_spec.run(cavity=cav, disp="const_alpha",
                     rf_begin=5200*u.MHz, rf_end=5280*u.MHz,
                     df=200*u.kHz, n_avg=50)
```

---

## 8. Migration Plan

### 8.1 Phases

#### Phase 0: Infrastructure (no experiment changes)

- [ ] Implement `ReadoutHandle` dataclass
- [ ] Implement `FrequencyScope` context manager
- [ ] Implement `QubitBundle` and `CavityBundle` dataclasses
- [ ] Add `session.readout_handle()`, `session.qubit_bundle()`,
      `session.cavity_bundle()` factory methods
- [ ] Add `measureMacro.as_readout_handle()` bridge method
- [ ] Add `ExperimentBase._resolve_qubit_params()` helper
- [ ] Add `ExperimentBase._resolve_cavity_params()` helper
- [ ] Add `emit_measurement(readout_handle, ...)` builder function

#### Phase 1: Builder migration

- [ ] Update all builder functions to accept `ReadoutHandle` instead
      of calling `measureMacro.measure()` directly
- [ ] Each builder gets a `readout: ReadoutHandle | None = None`
      parameter; when None, falls back to `measureMacro` (compat)
- [ ] Add `qubit_el` / `storage_el` explicit parameters to all builders
      that don't already have them

#### Phase 2: Experiment class migration (incremental, per-class)

For each experiment class:

1. Add new keyword parameters to `run()` (`qubit`, `readout`,
   `qubit_freq`, `therm_clks`, etc.)
2. Add `_resolve_*_params()` call at top of `run()`
3. Replace all `self.attr.qb_el` / `self.attr.ro_el` / etc. reads
   with resolved local variables
4. Wrap frequency-setting code in `FrequencyScope`
5. Pass `ReadoutHandle` to builder instead of relying on `measureMacro`
6. Update docstrings

**Migration order (by dependency):**

| Order | Experiments | Rationale |
|---|---|---|
| 1 | `T1Relaxation`, `PowerRabi`, `TemporalRabi` | Simplest (single qubit + readout) |
| 2 | `T2Ramsey`, `T2Echo` | Add frequency override handling |
| 3 | `ResonatorSpectroscopy`, `QubitSpectroscopy` | Frequency sweep patterns |
| 4 | `AllXY`, `DRAGCalibration`, `RandomizedBenchmarking` | Gate calibration |
| 5 | `IQBlob`, `ReadoutGEDiscrimination`, `ReadoutButterflyMeasurement` | Readout calibration |
| 6 | `CalibrateReadoutFull`, `ReadoutWeightsOptimization` | Full readout pipeline |
| 7 | `StorageSpectroscopy`, `StorageChiRamsey` | Cavity experiments |
| 8 | `FockResolved*`, `NumSplitting*` | Multi-Fock cavity |
| 9 | `QubitStateTomography`, `StorageWignerTomography` | Tomography |
| 10 | SPA experiments | Specialized |

#### Phase 3: Notebook migration

- [ ] Update `post_cavity_experiment_context.ipynb` to use
      `session.qubit_bundle()` / `session.readout_handle()` idiom
- [ ] Verify all cells pass with explicit parameters
- [ ] Update session initialization to use new factory methods

#### Phase 4: Deprecation & cleanup

- [ ] Mark `self.attr.qb_el` / `self.attr.ro_el` / `self.attr.st_el`
      usage in experiments as deprecated
- [ ] Mark `measureMacro.measure()` direct calls in builders as deprecated
- [ ] Mark `ExperimentBindings` role fields (`qubit`, `readout`,
      `storage`) as deprecated in favor of generic `channels` dict
- [ ] Remove `set_standard_frequencies()` from `ExperimentBase`
      (replaced by `FrequencyScope` + explicit frequency params)
- [ ] Remove deprecated code paths after all notebooks / tests are migrated

### 8.2 Backward compatibility guarantee

During Phases 1-3, **all existing code continues to work without changes.**

The compatibility mechanism:

```python
def run(self, *, qubit: str | QubitBundle | None = None, ...):
    if qubit is None:
        # Legacy path: resolve from self.attr (backward compat)
        qubit_el = self.attr.qb_el
        therm = self.attr.qb_therm_clks
        qb_freq = self.get_qubit_frequency()
    elif isinstance(qubit, str):
        qubit_el = qubit
        therm = therm_clks or self.get_therm_clks("qb")
        qb_freq = qubit_freq or self.get_calibrated_frequency(qubit_el)
    elif isinstance(qubit, QubitBundle):
        qubit_el = qubit.drive_el
        therm = qubit.therm_clks
        qb_freq = qubit.drive_freq
    ...
```

### 8.3 Testing strategy

- **Unit tests**: Each experiment tested with explicit parameters
  (no session) using a mock `ReadoutHandle` and element names.
- **Integration tests**: Run against simulation backend with both
  legacy (no explicit params) and new (explicit params) modes.
- **Notebook regression**: Run full notebook with `APPLY=False`
  orchestrator mode to verify analysis outputs are identical.

---

## 9. Risks & Open Questions

### 9.1 Risks

| Risk | Severity | Mitigation |
|---|---|---|
| API surface explosion (too many kwargs on `run()`) | Medium | Bundle types (`QubitBundle`) reduce parameter count; `None` defaults preserve concise usage |
| measureMacro removal breaks third-party code | High | Phase 3 bridge pattern; `measureMacro.measure()` stays as a thin wrapper indefinitely |
| Frequency scope overhead (snapshot/restore per call) | Low | `get_intermediate_frequency()` + `set_intermediate_frequency()` are fast QM API calls |
| Bundle proliferation (QubitBundle, CavityBundle, ...) | Medium | Keep to 3 bundles max (Qubit, Cavity, Readout); use raw strings for anything else |
| Stale ReadoutHandle (threshold changes mid-session) | Medium | `ReadoutHandle.from_calibration(store, element)` always reads latest; warn if handle age > N experiments |

### 9.2 Open questions

1. **Should `ReadoutHandle` be truly immutable (frozen dataclass)?**
   Pro: prevents accidental mutation. Con: readout calibration
   experiments need to produce updated handles (solved by returning
   new instances from `analyze()`).

2. **Should bundles include pulse operation names (e.g. `r180="x180"`)?**
   Pulse names are experiment-specific, not channel-specific. Current
   recommendation: keep pulse names as separate `run()` parameters,
   not part of the bundle.

3. **How to handle `transition` (ge/ef) in a roleless world?**
   Transition is a physics concept about which energy levels are
   addressed. Proposal: transition-specific experiments accept a
   `transition: str = "ge"` parameter that selects frequency/pulse
   mappings.

4. **Should `ExperimentBindings` be removed or generalized?**
   Proposal: generalize to `ChannelMap = dict[str, OutputBinding | ReadoutBinding]`
   with no fixed role keys. This is Phase 4 work.

5. **Multi-qubit experiments?**
   The bundle approach scales: `qubit_1: QubitBundle`, `qubit_2: QubitBundle`.
   Out of scope for this plan but the architecture supports it.

---

## Appendix: Full Experiment Element Matrix

Summary of every experiment class, its internal element access patterns,
and what the roleless signature should look like.

| Class | Current accesses | Roleless `run()` params |
|---|---|---|
| `ResonatorSpectroscopy` | `attr.ro_el`, `get_readout_lo()` | `readout: ReadoutHandle, rf_begin, rf_end, df` |
| `ResonatorPowerSpectroscopy` | `attr.ro_el`, `get_readout_lo()` | `readout: ReadoutHandle, rf_begin, rf_end, df, g_min, g_max` |
| `ResonatorSpectroscopyX180` | `attr.ro_el`, `attr.qb_el` | `qubit: str, readout: ReadoutHandle, rf_begin, rf_end, df` |
| `ReadoutTrace` | `attr.ro_fq`, `measureMacro` | `readout: ReadoutHandle` |
| `QubitSpectroscopy` | `attr.qb_el`, `get_qubit_lo()` | `qubit: str, readout: ReadoutHandle, rf_begin, rf_end, df` |
| `PowerRabi` | `attr.qb_el`, `attr.qb_therm_clks` | `qubit: str\|QubitBundle, readout: ReadoutHandle, op, max_gain, dg` |
| `TemporalRabi` | `attr.qb_el`, `attr.qb_therm_clks` | `qubit: str\|QubitBundle, readout: ReadoutHandle, pulse, duration_range` |
| `T1Relaxation` | `attr.qb_el`, `attr.qb_therm_clks` | `qubit: str\|QubitBundle, readout: ReadoutHandle, r180, delay_range` |
| `T2Ramsey` | `attr.qb_el`, `attr.ro_el`, `measureMacro._drive_frequency` | `qubit: str\|QubitBundle, readout: ReadoutHandle, qb_detune, delay_range` |
| `T2Echo` | `attr.qb_el`, `attr.qb_therm_clks` | `qubit: str\|QubitBundle, readout: ReadoutHandle, r90, r180, delay_range` |
| `TimeRabiChevron` | `attr.qb_el`, `get_qubit_lo()` | `qubit: str, readout: ReadoutHandle, rf_begin, rf_end, df, pulse, duration_range` |
| `PowerRabiChevron` | `attr.qb_el`, `get_qubit_lo()` | `qubit: str, readout: ReadoutHandle, rf_begin, rf_end, df, op, gain_range` |
| `AllXY` | `attr.qb_el`, `attr.qb_therm_clks` | `qubit: str\|QubitBundle, readout: ReadoutHandle` |
| `DRAGCalibration` | `attr.qb_el`, `attr.qb_therm_clks` | `qubit: str\|QubitBundle, readout: ReadoutHandle, amps, x180, y180, x90, y90` |
| `RandomizedBenchmarking` | `attr.qb_el`, `attr.qb_therm_clks` | `qubit: str\|QubitBundle, readout: ReadoutHandle, m_list, num_sequence` |
| `PulseTrainCalibration` | `attr.qb_el` | `qubit: str\|QubitBundle, readout: ReadoutHandle, arb_rot, prep_defs, N_values` |
| `IQBlob` | `attr.qb_el`, `attr.ro_el` | `qubit: str, readout: ReadoutHandle, r180, n_runs` |
| `ReadoutGEDiscrimination` | `attr.qb_el`, `attr.ro_el`, `measureMacro` mutation | `qubit: str, readout: ReadoutHandle, r180, n_samples` |
| `ReadoutButterflyMeasurement` | `attr.qb_el`, `attr.ro_el`, `measureMacro` mutation | `qubit: str, readout: ReadoutHandle, r180, n_samples, prep_policy` |
| `ReadoutWeightsOptimization` | `attr.ro_el`, `measureMacro` mutation | `readout: ReadoutHandle, qubit: str, r180, n_avg` |
| `CalibrateReadoutFull` | `attr.qb_el`, `attr.ro_el`, `measureMacro` mutation | `qubit: str, readout: ReadoutHandle, readoutConfig` |
| `StorageSpectroscopy` | `attr.qb_el`, `attr.st_el` | `qubit: str, storage: str, readout: ReadoutHandle, disp, rf_begin, rf_end, df` |
| `NumSplittingSpectroscopy` | `attr.qb_el`, `attr.st_el` | `qubit: str, storage: str, readout: ReadoutHandle, sel_r180, rf_centers, state_prep` |
| `StorageChiRamsey` | `attr.qb_el`, `attr.st_el`, `attr.ro_el` | `qubit: str, storage: str, readout: ReadoutHandle, disp_pulse, x90_pulse, delay_ticks` |
| `StorageRamsey` | `attr.qb_el`, `attr.st_el`, `attr.ro_el` | `qubit: str, storage: str, readout: ReadoutHandle, disp_pulse, sel_r180, delay_ticks` |
| `FockResolvedT1` | `attr.qb_el`, `attr.st_el` | `qubit: str, storage: str, readout: ReadoutHandle, fock_disps, fock_fqs, sel_r180` |
| `FockResolvedRamsey` | `attr.qb_el`, `attr.st_el` | `qubit: str, storage: str, readout: ReadoutHandle, fock_fqs, detunings, disps, sel_r90` |
| `FockResolvedPowerRabi` | `attr.qb_el`, `attr.st_el` | `qubit: str, storage: str, readout: ReadoutHandle, disp_n_list, fock_ifs, sel_qb_pulse` |
| `FockResolvedSpectroscopy` | `attr.qb_el` | `qubit: str, readout: ReadoutHandle, probe_fqs, fock_ifs, sel_r180, state_prep` |
| `QubitStateTomography` | `attr.qb_el`, `attr.qb_therm_clks` | `qubit: str\|QubitBundle, readout: ReadoutHandle, state_prep, x90, yn90` |
| `StorageWignerTomography` | `attr.qb_el`, `attr.st_el`, `attr.ro_el` | `qubit: str, storage: str, readout: ReadoutHandle, prep_gates, base_disp, x90_pulse` |
| `SNAPOptimization` | `attr.qb_el`, `attr.st_el`, `attr.ro_el` | `qubit: str, storage: str, readout: ReadoutHandle, snap_gate, disp_gate, fock_probe_fqs` |
| `SPAFluxOptimization` | `attr.ro_el` | `readout: ReadoutHandle, dc_list, sample_fqs` |
| `SPAPumpFrequencyOptimization` | `attr.qb_el`, `attr.ro_el` | `qubit: str, readout: ReadoutHandle, pump_powers, pump_detunings` |

---

*End of plan.*
