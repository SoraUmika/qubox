# Roleless Experiments v2: Revised Design Plan

**Version:** 2.0.0
**Date:** 2026-02-26
**Status:** Design proposal (pre-implementation)
**Scope:** Remove fixed `qubit/readout/storage` role assumptions; typed config objects; explicit bindings; pure frequency plans

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Core Types & API Primitives](#2-core-types--api-primitives)
3. [Readout Strategy](#3-readout-strategy)
4. [Frequency Strategy](#4-frequency-strategy)
5. [Experiment Requirements Table](#5-experiment-requirements-table)
6. [Before / After Examples](#6-before--after-examples)
7. [Migration Plan](#7-migration-plan)
8. [Risks & Mitigations](#8-risks--mitigations)

---

## 1. Executive Summary

### 1.1 Problem recap

Today every experiment class hard-codes assumptions about three named
roles -- `qubit`, `readout`, and `storage` -- accessed through
`self.attr.qb_el`, `self.attr.ro_el`, and `self.attr.st_el`. The API is
brittle, non-portable, and opaque. The v1 roleless plan addressed the
role coupling but introduced three new problems:

1. **Kwargs explosion** -- `run()` signatures grew to 10+ keyword
   arguments for channel names, frequencies, thermalization clocks, and
   pulse ops, making the API harder to use than the implicit version.
2. **Role reintroduction via bundles** -- `QubitBundle` and
   `CavityBundle` baked role names (`drive_el`, `storage_el`) back into
   the type system, just at a different level.
3. **Mutable global state preserved** -- `FrequencyScope` still mutated
   QM hardware IF frequencies as a side effect, and `measureMacro`
   remained the authoritative source of readout DSP state.

### 1.2 Design principles (v2)

This revised plan follows six corrective principles:

| # | Principle | Concrete rule |
|---|-----------|---------------|
| 1 | **Typed config objects, not kwargs** | Each experiment defines a frozen dataclass `*Config` holding all physics parameters. `run()` accepts at most one config object plus binding primitives. |
| 2 | **Generic binding primitives** | Experiments accept `DriveTarget` and `ReadoutHandle` -- generic types with no role vocabulary. User-facing bundles (`QubitSetup`, `CavitySetup`) are ergonomic *factories* that produce these primitives; experiments never type-check for bundles. |
| 3 | **Split ReadoutBinding from ReadoutCal** | Physical wiring identity (`ReadoutBinding`) is separated from tunable calibration artifacts (`ReadoutCal`). `ReadoutHandle = ReadoutBinding + ReadoutCalRef`. |
| 4 | **Pure FrequencyPlan, no mutable scope** | Frequency configuration is a pure, computed `FrequencyPlan` resolved once at `run()` entry. No global QM state mutation during resolution; mutations happen exactly once at program execution time. |
| 5 | **Loud backward compatibility** | No silent `None` fallbacks that silently read from `self.attr`. A `compat_mode=True` flag enables legacy resolution with explicit `DeprecationWarning` on every use. Missing required bindings *raise immediately*. |
| 6 | **measureMacro has a defined end-state** | A canonical `emit_measurement()` function replaces the singleton. Migration is staged with done-criteria: zero remaining `measureMacro.measure()` callsites in builders. |

### 1.3 Design philosophy alignment

Per `qubox_v2/docs/ARCHITECTURE.md`:

- **Explicit Over Implicit** -- config objects and binding parameters
  make every dependency visible in the function signature.
- **Immutable Snapshots** -- `ReadoutCal`, `FrequencyPlan`, and
  `*Config` are frozen dataclasses; no hidden mutation.
- **No Hidden Experiment-Side Mutation** -- frequency plan is resolved
  once and applied atomically; no mid-experiment `set_element_fq` calls
  scattered through business logic.
- **Notebook-First Workflow** -- ergonomic factories (`session.qubit()`,
  `session.readout()`) keep notebook code concise while the underlying
  primitives remain generic.

---

## 2. Core Types & API Primitives

### 2.1 Generic binding primitives (experiment-facing)

These are the types that experiment `run()` methods accept. They carry
**no role vocabulary** -- no field named `qubit` or `storage`.

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class DriveTarget:
    """A single control output channel for driving."""
    element: str              # QM element name (ephemeral at runtime)
    lo_freq: float            # LO frequency (Hz)
    rf_freq: float            # Target RF frequency (Hz)
    therm_clks: int = 250_000 # Thermalization wait (clock cycles)

    @property
    def if_freq(self) -> float:
        return self.rf_freq - self.lo_freq


@dataclass(frozen=True)
class ReadoutHandle:
    """Everything needed to measure one readout channel.

    Combines physical identity (ReadoutBinding) with calibration
    artifact reference (ReadoutCal). Both are frozen/immutable.
    """
    binding: "ReadoutBinding"   # Physical wiring (from core.bindings)
    cal: "ReadoutCal"           # Calibration artifacts (thresholds, weights)
    element: str                # QM element name (ephemeral at runtime)
    operation: str              # Pulse operation (e.g. "readout")

    @property
    def drive_frequency(self) -> float:
        return self.cal.drive_frequency

    @property
    def physical_id(self) -> str:
        return self.binding.physical_id
```

**Key design decisions:**

- `DriveTarget` is not called `QubitDrive` or `StorageDrive`. It is the
  same type for qubit, storage, pump, or any other control line.
- `ReadoutHandle` is not called `ResonatorHandle`. It works for any
  readout channel.
- Experiments type-check for `DriveTarget` and `ReadoutHandle`, never
  for `QubitSetup` or `CavitySetup`.

### 2.2 ReadoutCal -- calibration artifact type

Separated from `ReadoutBinding` (physical wiring):

```python
@dataclass(frozen=True)
class ReadoutCal:
    """Immutable snapshot of readout calibration state.

    Contains all tunable parameters that change during calibration
    (thresholds, weights, confusion matrices). Physical wiring identity
    is NOT here -- it lives in ReadoutBinding.
    """
    drive_frequency: float                  # RF frequency (Hz)

    # Demodulation
    demod_method: str = "dual_demod.full"
    weight_keys: tuple[str, ...] = ("cos", "sin", "minus_sin")
    weight_length: int | None = None

    # Discrimination (set by ReadoutGEDiscrimination)
    threshold: float | None = None
    rotation_angle: float | None = None

    # Quality metrics (set by ReadoutButterflyMeasurement)
    confusion_matrix: tuple[tuple[float, ...], ...] | None = None
    fidelity: float | None = None
    transition_rates: dict[str, float] | None = None

    # Post-selection
    post_select_threshold: float | None = None
    post_select_max_retries: int = 3

    @classmethod
    def from_calibration_store(
        cls, store: "CalibrationStore", channel_id: str, *, drive_freq: float,
    ) -> "ReadoutCal":
        """Construct from persisted calibration data.

        Parameters
        ----------
        store : CalibrationStore
        channel_id : str
            Physical channel ID (e.g. "oct1:RF_in:1") or alias.
        drive_freq : float
            RF drive frequency in Hz.
        """
        disc = store.get_discrimination(channel_id)
        qual = store.get_readout_quality(channel_id)
        return cls(
            drive_frequency=drive_freq,
            threshold=getattr(disc, "threshold", None),
            rotation_angle=getattr(disc, "angle", None),
            confusion_matrix=getattr(qual, "confusion_matrix", None),
            fidelity=getattr(qual, "fidelity", None),
        )

    def with_discrimination(
        self, *, threshold: float, rotation_angle: float,
    ) -> "ReadoutCal":
        """Return a new ReadoutCal with updated discrimination params."""
        from dataclasses import replace
        return replace(self, threshold=threshold, rotation_angle=rotation_angle)
```

### 2.3 Per-experiment typed config objects

Each experiment defines a frozen dataclass holding **all physics
parameters** (sweep ranges, pulse names, averaging counts). The `run()`
signature stays compact.

**Naming convention:** `<ExperimentName>Config`.

```python
@dataclass(frozen=True)
class PowerRabiConfig:
    """Physics parameters for a power Rabi experiment."""
    op: str = "ge_ref_r180"
    max_gain: float = 0.5
    dg: float = 1e-3
    n_avg: int = 1000
    length: int | None = None          # Pulse length override (ns)
    truncate_clks: int | None = None

@dataclass(frozen=True)
class T1RelaxationConfig:
    """Physics parameters for a T1 relaxation experiment."""
    r180: str = "x180"
    delay_begin: int = 4
    delay_end: int = 50_000   # ns
    dt: int = 500             # ns
    n_avg: int = 2000

@dataclass(frozen=True)
class T2RamseyConfig:
    """Physics parameters for a T2 Ramsey experiment."""
    r90: str = "x90"
    qb_detune_MHz: float = 0.2
    delay_begin: int = 4
    delay_end: int = 40_000   # ns
    dt: int = 100
    n_avg: int = 4000

@dataclass(frozen=True)
class ResonatorSpectroscopyConfig:
    """Physics parameters for resonator spectroscopy."""
    readout_op: str = "readout"
    rf_begin: float = 8.5e9
    rf_end: float = 8.7e9
    df: float = 100e3
    n_avg: int = 1000

@dataclass(frozen=True)
class StorageSpectroscopyConfig:
    """Physics parameters for storage cavity spectroscopy."""
    disp: str = "const_alpha"
    sel_r180: str = "sel_x180"
    rf_begin: float = 5.0e9
    rf_end: float = 5.5e9
    df: float = 200e3
    storage_therm_clks: int = 500_000
    n_avg: int = 50
```

### 2.4 Canonical `run()` signature pattern

Every experiment follows a consistent pattern:

```python
def run(
    self,
    cfg: <ExperimentName>Config,
    *,
    drive: DriveTarget,                    # primary drive channel
    readout: ReadoutHandle,                # readout channel
    # additional channels only if the experiment physically needs them:
    # aux_drive: DriveTarget | None = None  (e.g. storage, pump)
) -> RunResult:
```

The signature has at most 4-5 parameters:

1. `cfg` -- typed config object (all physics params)
2. `drive` -- primary control channel
3. `readout` -- readout channel
4. Optional additional drives (cavity experiments add `storage: DriveTarget`)
5. No frequencies, no thermalization clocks, no element names as loose kwargs

### 2.5 User-facing ergonomic factories (session helpers)

These are **convenience constructors**, not types that experiments
accept. They produce `DriveTarget` and `ReadoutHandle` instances.

```python
# On SessionManager:

class SessionManager:
    def drive_target(
        self, alias: str, *, rf_freq: float | None = None,
        therm_clks: int | None = None,
    ) -> DriveTarget:
        """Construct a DriveTarget from a named alias.

        Resolves element name, LO frequency, and RF frequency from the
        hardware config and calibration store.
        """
        binding = self._resolve_output_binding(alias)
        element = binding.element_name or alias
        lo = binding.lo_frequency
        freq = rf_freq or self._calibrated_freq(alias)
        therm = therm_clks or self._therm_clks(alias)
        return DriveTarget(element=element, lo_freq=lo, rf_freq=freq, therm_clks=therm)

    def readout_handle(
        self, alias: str = "resonator", operation: str = "readout",
    ) -> ReadoutHandle:
        """Construct a ReadoutHandle from a named alias.

        Resolves physical binding from hardware config and calibration
        artifacts from CalibrationStore.
        """
        rb = self._resolve_readout_binding(alias)
        element = rb.element_name or alias
        cal = ReadoutCal.from_calibration_store(
            self.calibration, rb.physical_id,
            drive_freq=self._calibrated_freq(alias, field="readout_freq"),
        )
        return ReadoutHandle(binding=rb, cal=cal, element=element, operation=operation)

    # Ergonomic shortcuts for common patterns:
    def qubit(self, alias: str = "qubit", **kw) -> DriveTarget:
        """Shortcut for drive_target(alias)."""
        return self.drive_target(alias, **kw)

    def storage(self, alias: str = "storage", **kw) -> DriveTarget:
        """Shortcut for drive_target(alias)."""
        return self.drive_target(alias, **kw)

    def readout(self, alias: str = "resonator", **kw) -> ReadoutHandle:
        """Shortcut for readout_handle(alias)."""
        return self.readout_handle(alias, **kw)
```

**Usage in a notebook:**

```python
qb = session.qubit()          # -> DriveTarget
ro = session.readout()         # -> ReadoutHandle
st = session.storage()         # -> DriveTarget

# These are plain DriveTarget / ReadoutHandle -- no role vocabulary
```

### 2.6 Relationship to existing ExperimentBindings

The existing `ExperimentBindings` (with fixed `qubit`, `readout`,
`storage` fields) remains as an **internal adapter** during migration.
It is not part of the new public API.

```
User-facing (new):          Internal (existing):
  DriveTarget      <----->   OutputBinding + element name
  ReadoutHandle    <----->   ReadoutBinding + ReadoutCal
  session.qubit()  <----->   bindings.qubit
```

The `ConfigBuilder.ephemeral_names()` mechanism continues to work
internally. New code passes `DriveTarget.element` directly.

---

## 3. Readout Strategy

### 3.1 The ReadoutBinding / ReadoutCal split

**Problem:** The v1 plan's `ReadoutHandle` combined physical wiring
identity with calibration artifacts in one frozen dataclass. This
means calibration routines (GE discrimination, butterfly measurement)
need to return an entirely new handle when only the threshold changes.

**Solution:** Split into two layers:

| Type | Contents | Mutability | Keyed by |
|------|----------|------------|----------|
| `ReadoutBinding` | Physical wiring: `ChannelRef` for drive output + acquire input, LO frequencies, time-of-flight | Frozen, never changes | `physical_id` (canonical channel ID) |
| `ReadoutCal` | Calibration artifacts: threshold, rotation angle, confusion matrix, weights, drive frequency | Frozen (new instance on update) | `physical_id` via CalibrationStore |
| `ReadoutHandle` | `ReadoutBinding` + `ReadoutCal` + ephemeral element name + operation | Frozen | Composed at session level |

**Calibration flow:**

```
ReadoutGEDiscrimination.analyze()
    |
    v
Returns AnalysisResult with metrics:
    metrics["threshold"] = -1.89e-5
    metrics["rotation_angle"] = 0.397
    |
    v
CalibrationStore.set_discrimination(physical_id, ...)
    |
    v
User constructs new ReadoutHandle for subsequent experiments:
    updated_ro = session.readout()   # re-reads from CalibrationStore
```

No global `measureMacro` state mutation. No mutable fields on existing
objects. State flows forward through new instances.

### 3.2 emit_measurement() -- the canonical measurement function

Replaces `measureMacro.measure()` in all builder code:

```python
def emit_measurement(
    readout: ReadoutHandle,
    *,
    targets: list | None = None,
    state: "QUA_bool_var | None" = None,
    gain: float | None = None,
    timestamp_stream: "QUA_stream | None" = None,
    adc_stream: "QUA_stream | None" = None,
) -> tuple:
    """Emit a QUA measure() statement using a ReadoutHandle.

    This is the canonical replacement for measureMacro.measure().
    It is a pure function -- it reads from the ReadoutHandle and
    emits QUA statements. It has no class-level state.

    Parameters
    ----------
    readout : ReadoutHandle
        Immutable readout channel configuration.
    targets : list, optional
        [I, Q] QUA variables to receive demodulated results.
    state : QUA variable, optional
        Boolean variable for state discrimination.
    gain : float, optional
        Override readout gain.
    """
    element = readout.element
    op = readout.operation
    cal = readout.cal

    # Build demod output tuple from ReadoutCal weight keys
    outputs = _build_demod_outputs(cal, targets)

    pulse = op if gain is None else op * amp(gain)
    measure(pulse, element, None, *outputs,
            timestamp_stream=timestamp_stream, adc_stream=adc_stream)

    if state is not None and cal.threshold is not None:
        I_var = targets[0] if targets else None
        if I_var is not None:
            if cal.rotation_angle is not None:
                # Apply IQ rotation before thresholding
                _apply_iq_rotation(cal.rotation_angle, targets)
            assign(state, I_var > cal.threshold)

    return targets if targets else ()
```

### 3.3 measureMacro migration end-state

**Staged migration:**

| Stage | Scope | Callsite count | Criteria |
|-------|-------|---------------|----------|
| **S0 (now)** | `emit_measurement()` exists alongside `measureMacro.measure()` | 0 / 348 migrated | Function defined, tested with ReadoutHandle |
| **S1** | All builder functions call `emit_measurement()` when `ReadoutHandle` is available, fall back to `measureMacro.measure()` otherwise | ~200 / 348 migrated | Every builder with `bindings` param uses new path |
| **S2** | `measureMacro.measure()` becomes a thin wrapper around `emit_measurement()`, constructing a `ReadoutHandle` from its class-level state | 348 / 348 migrated (via wrapper) | `measureMacro.measure()` delegates; no independent implementation |
| **S3** | `measureMacro` class removed; `emit_measurement()` is the only API | 0 remaining | No import of `measureMacro` in any builder or experiment |

**Definition of "done":** Zero `measureMacro.measure()` calls in
`programs/builders/*.py` and `programs/macros/sequence.py`. The
`measureMacro` class may persist as a deprecated compat shim in
`programs/macros/measure.py` for external consumers.

### 3.4 ReadoutGEDiscrimination / ReadoutButterflyMeasurement migration

These experiments currently mutate `measureMacro._ro_disc_params` and
`measureMacro._ro_quality_params`. In the new model:

```python
class ReadoutGEDiscrimination(ExperimentBase):
    def run(
        self,
        cfg: GEDiscriminationConfig,
        *,
        qubit: DriveTarget,
        readout: ReadoutHandle,
    ) -> RunResult:
        # Uses readout.element, readout.operation
        # No measureMacro state needed
        ...

    def analyze(
        self, result: RunResult, *, update_calibration: bool = False,
    ) -> AnalysisResult:
        # Returns AnalysisResult with metrics:
        #   metrics["threshold"], metrics["rotation_angle"]
        #   metrics["fidelity"], metrics["mu_g"], metrics["mu_e"]
        # If update_calibration:
        #   self.calibration_store.set_discrimination(physical_id, ...)
        # Returns updated ReadoutCal in metadata:
        #   metadata["updated_readout_cal"] = cal.with_discrimination(...)
        ...
```

**Key change:** `analyze()` returns an updated `ReadoutCal` in
`metadata["updated_readout_cal"]`. The user passes this to subsequent
experiments by constructing a new `ReadoutHandle`. No global singleton
state mutation.

---

## 4. Frequency Strategy

### 4.1 Pure FrequencyPlan

Replaces both `set_standard_frequencies()` and the mutable
`FrequencyScope` from v1.

```python
@dataclass(frozen=True)
class ElementFreq:
    """Resolved frequency for one element."""
    element: str
    rf_freq: float    # Target RF frequency (Hz)
    lo_freq: float    # LO frequency (Hz)
    if_freq: float    # Intermediate frequency (Hz) = rf - lo
    source: str       # Provenance: "explicit", "calibration", "sample_default"

@dataclass(frozen=True)
class FrequencyPlan:
    """Pure, immutable frequency configuration for one experiment run.

    Computed once at run() entry. Applied atomically before program execution.
    Recorded in RunResult metadata for reproducibility.
    """
    entries: tuple[ElementFreq, ...]

    def get(self, element: str) -> ElementFreq:
        for e in self.entries:
            if e.element == element:
                return e
        raise KeyError(f"No frequency entry for element '{element}'")

    def to_metadata(self) -> dict:
        """Serialize for RunResult provenance."""
        return {
            e.element: {
                "rf_freq": e.rf_freq,
                "lo_freq": e.lo_freq,
                "if_freq": e.if_freq,
                "source": e.source,
            }
            for e in self.entries
        }

    def apply(self, hw) -> None:
        """Set IF frequencies on QM hardware. Called once, atomically."""
        for e in self.entries:
            hw.qm.set_intermediate_frequency(e.element, int(e.if_freq))
```

### 4.2 Resolution order

When building a `FrequencyPlan`, frequencies resolve in this order
(first match wins):

1. **Explicit override** -- value passed directly in config or
   `DriveTarget.rf_freq`
2. **CalibrationStore** -- `store.get_frequencies(channel_id).qubit_freq`
3. **Sample defaults** -- `cqed_params.json` values (via `self.attr`)

The resolution is **loud**: if a frequency comes from step 3 and
`compat_mode` is not enabled, emit a `DeprecationWarning`:

```python
def _resolve_drive_freq(
    drive: DriveTarget | None,
    *,
    cal_store: CalibrationStore | None,
    attr: cQED_attributes,
    attr_field: str,
    compat_mode: bool,
) -> ElementFreq:
    if drive is not None:
        return ElementFreq(
            element=drive.element, rf_freq=drive.rf_freq,
            lo_freq=drive.lo_freq, if_freq=drive.if_freq,
            source="explicit",
        )
    if not compat_mode:
        raise ValueError(
            "drive target is required. Pass a DriveTarget explicitly "
            "or enable compat_mode=True for legacy fallback."
        )
    warnings.warn(
        f"Resolving drive frequency from legacy self.attr.{attr_field}. "
        "Pass an explicit DriveTarget to suppress this warning.",
        DeprecationWarning, stacklevel=4,
    )
    rf = float(getattr(attr, attr_field))
    lo = ...  # resolve from hardware config
    return ElementFreq(
        element=getattr(attr, ...),
        rf_freq=rf, lo_freq=lo, if_freq=rf - lo,
        source="sample_default",
    )
```

### 4.3 FrequencyPlan in the experiment lifecycle

```
run() entry:
    1. Build FrequencyPlan from DriveTarget + ReadoutHandle + config overrides
    2. Validate: all IF frequencies within MAX_IF_BANDWIDTH
    3. Apply: freq_plan.apply(self.hw)   # one atomic call
    4. Build QUA program (uses element names from DriveTarget/ReadoutHandle)
    5. Execute program
    6. Record freq_plan in RunResult metadata

No snapshot/restore needed:
    - FrequencyPlan replaces the old pattern entirely
    - Next experiment builds its own FrequencyPlan from scratch
    - No stale IF state because each run() starts with explicit apply()
```

### 4.4 Freshness checks

When resolving from CalibrationStore (step 2 in resolution order), check
the calibration timestamp against a session-level staleness threshold:

```python
MAX_CALIBRATION_AGE_HOURS = 24  # configurable per session

freq_entry = cal_store.get_frequencies(channel_id)
if freq_entry is not None and freq_entry.timestamp is not None:
    age = datetime.now() - freq_entry.timestamp
    if age > timedelta(hours=MAX_CALIBRATION_AGE_HOURS):
        warnings.warn(
            f"Calibrated frequency for '{channel_id}' is "
            f"{age.total_seconds()/3600:.1f}h old. "
            "Consider re-running frequency calibration.",
            UserWarning, stacklevel=3,
        )
```

### 4.5 No global state mutation during resolution

The critical difference from v1's `FrequencyScope`:

| v1 FrequencyScope | v2 FrequencyPlan |
|---|---|
| Snapshots current IF frequencies | No snapshot needed |
| Mutates QM state during resolution | Pure computation; no side effects |
| Restores on `__exit__` | Nothing to restore |
| Can leak if exception between snapshot and restore | No leak possible |
| `set_standard_frequencies()` mutates state | `FrequencyPlan.apply()` is an atomic batch |

---

## 5. Experiment Requirements Table

### 5.1 Element requirement categories

| Category | Channels needed | Config type |
|---|---|---|
| **D+R** | 1 drive + readout | `*Config` + `drive: DriveTarget` + `readout: ReadoutHandle` |
| **R** | readout only | `*Config` + `readout: ReadoutHandle` |
| **D+R (sweep)** | 1 drive (freq sweep) + readout | `*Config` + `drive: DriveTarget` + `readout: ReadoutHandle` |
| **D+S+R** | drive + storage + readout | `*Config` + `drive: DriveTarget` + `storage: DriveTarget` + `readout: ReadoutHandle` |

### 5.2 Per-experiment requirements

| Experiment | Category | `run()` signature (new) |
|---|---|---|
| **Spectroscopy** | | |
| `ResonatorSpectroscopy` | R | `run(cfg, *, readout)` |
| `ResonatorPowerSpectroscopy` | R | `run(cfg, *, readout)` |
| `ResonatorSpectroscopyX180` | D+R | `run(cfg, *, drive, readout)` |
| `ReadoutTrace` | R | `run(cfg, *, readout)` |
| `QubitSpectroscopy` | D+R (sweep) | `run(cfg, *, drive, readout)` |
| **Time Domain** | | |
| `PowerRabi` | D+R | `run(cfg, *, drive, readout)` |
| `TemporalRabi` | D+R | `run(cfg, *, drive, readout)` |
| `T1Relaxation` | D+R | `run(cfg, *, drive, readout)` |
| `T2Ramsey` | D+R | `run(cfg, *, drive, readout)` |
| `T2Echo` | D+R | `run(cfg, *, drive, readout)` |
| `TimeRabiChevron` | D+R (sweep) | `run(cfg, *, drive, readout)` |
| `PowerRabiChevron` | D+R (sweep) | `run(cfg, *, drive, readout)` |
| **Calibration** | | |
| `AllXY` | D+R | `run(cfg, *, drive, readout)` |
| `DRAGCalibration` | D+R | `run(cfg, *, drive, readout)` |
| `RandomizedBenchmarking` | D+R | `run(cfg, *, drive, readout)` |
| `PulseTrainCalibration` | D+R | `run(cfg, *, drive, readout)` |
| `IQBlob` | D+R | `run(cfg, *, drive, readout)` |
| `ReadoutGEDiscrimination` | D+R | `run(cfg, *, drive, readout)` |
| `ReadoutButterflyMeasurement` | D+R | `run(cfg, *, drive, readout)` |
| `ReadoutWeightsOptimization` | D+R | `run(cfg, *, drive, readout)` |
| `CalibrateReadoutFull` | D+R | `run(cfg, *, drive, readout)` |
| **Cavity / Fock** | | |
| `StorageSpectroscopy` | D+S+R | `run(cfg, *, drive, storage, readout)` |
| `NumSplittingSpectroscopy` | D+S+R | `run(cfg, *, drive, storage, readout)` |
| `StorageChiRamsey` | D+S+R | `run(cfg, *, drive, storage, readout)` |
| `StorageRamsey` | D+S+R | `run(cfg, *, drive, storage, readout)` |
| `FockResolvedSpectroscopy` | D+S+R | `run(cfg, *, drive, storage, readout)` |
| `FockResolvedT1` | D+S+R | `run(cfg, *, drive, storage, readout)` |
| `FockResolvedRamsey` | D+S+R | `run(cfg, *, drive, storage, readout)` |
| `FockResolvedPowerRabi` | D+S+R | `run(cfg, *, drive, storage, readout)` |
| **Tomography** | | |
| `QubitStateTomography` | D+R | `run(cfg, *, drive, readout)` |
| `StorageWignerTomography` | D+S+R | `run(cfg, *, drive, storage, readout)` |
| `SNAPOptimization` | D+S+R | `run(cfg, *, drive, storage, readout)` |
| **SPA** | | |
| `SPAFluxOptimization` | R | `run(cfg, *, readout)` |
| `SPAPumpFrequencyOptimization` | D+R | `run(cfg, *, drive, readout)` |

### 5.3 Pattern observations

1. **All experiments need `readout: ReadoutHandle`.**
2. **~70% need exactly `drive: DriveTarget` + `readout: ReadoutHandle`.**
   The most common pattern is D+R. The config object absorbs all
   physics parameters (sweep ranges, pulse names, averaging).
3. **~25% need an additional `storage: DriveTarget`.**
   These are cavity/Fock experiments. The storage channel is just
   another `DriveTarget` -- no special type.
4. **No experiment needs more than 3 channel arguments.**
5. **Frequency sweep experiments** absorb sweep ranges into their
   config objects. The `DriveTarget` provides the base frequency; the
   sweep range is in the config.

---

## 6. Before / After Examples

### 6.1 PowerRabi

**Before (current):**

```python
rabi = PowerRabi(session)
result = rabi.run(max_gain=0.5, dg=0.01, op="ge_ref_r180", n_avg=4000)
# Internally:
#   attr = self.attr
#   self.set_standard_frequencies()              # global state mutation
#   prog = cQED_programs.power_rabi(
#       ..., qb_el=attr.qb_el,                  # hidden dependency
#       bindings=self._bindings_or_none,         # optional binding
#   )
```

**After (v2):**

```python
# Notebook setup (once):
qb = session.qubit()        # -> DriveTarget
ro = session.readout()       # -> ReadoutHandle

# Run:
rabi = PowerRabi(session)
result = rabi.run(
    PowerRabiConfig(op="ge_ref_r180", max_gain=0.5, dg=0.01, n_avg=4000),
    drive=qb,
    readout=ro,
)
```

**Internal implementation:**

```python
class PowerRabi(ExperimentBase):
    def run(
        self,
        cfg: PowerRabiConfig,
        *,
        drive: DriveTarget,
        readout: ReadoutHandle,
    ) -> RunResult:
        gains = np.arange(-cfg.max_gain, cfg.max_gain + 1e-12, cfg.dg)

        pulse_info = self.pulse_mgr.get_pulseOp_by_element_op(
            drive.element, cfg.op,
        )
        length = cfg.length or pulse_info.length
        peak_amp = max(np.abs(pulse_info.I_wf).max(),
                       np.abs(pulse_info.Q_wf).max())
        if peak_amp * cfg.max_gain > MAX_AMPLITUDE:
            raise ValueError(...)

        freq_plan = FrequencyPlan(entries=(
            ElementFreq(drive.element, drive.rf_freq, drive.lo_freq,
                        drive.if_freq, source="explicit"),
            ElementFreq(readout.element, readout.drive_frequency,
                        readout.binding.drive_out.lo_frequency,
                        readout.drive_frequency - readout.binding.drive_out.lo_frequency,
                        source="explicit"),
        ))
        freq_plan.apply(self.hw)

        prog = build_power_rabi(
            op=cfg.op,
            pulse_clock_len=round(length / 4),
            gains=gains,
            therm_clks=drive.therm_clks,
            truncate_clks=cfg.truncate_clks,
            n_avg=cfg.n_avg,
            drive_el=drive.element,
            readout=readout,
        )
        result = self.run_program(prog, n_total=cfg.n_avg, ...)
        result.metadata["frequency_plan"] = freq_plan.to_metadata()
        return result
```

### 6.2 T1Relaxation

**Before:**

```python
t1 = T1Relaxation(session)
result = t1.run(delay_end=50*u.us, dt=500, n_avg=2000)
# Internally uses: attr.qb_el, attr.qb_therm_clks, set_standard_frequencies()
```

**After:**

```python
t1 = T1Relaxation(session)
result = t1.run(
    T1RelaxationConfig(delay_end=50_000, dt=500, n_avg=2000),
    drive=session.qubit(),
    readout=session.readout(),
)
```

### 6.3 T2Ramsey

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
#   self.hw.set_element_fq(attr.ro_el, measureMacro._drive_frequency)  # singleton!
```

**After:**

```python
qb = session.qubit()
ro = session.readout()

t2r = T2Ramsey(session)
result = t2r.run(
    T2RamseyConfig(qb_detune_MHz=0.2, delay_end=40_000, dt=100, n_avg=4000),
    drive=qb,
    readout=ro,
)
```

**Internal implementation (T2Ramsey-specific frequency handling):**

```python
class T2Ramsey(ExperimentBase):
    def run(
        self,
        cfg: T2RamseyConfig,
        *,
        drive: DriveTarget,
        readout: ReadoutHandle,
    ) -> RunResult:
        qb_detune = int(cfg.qb_detune_MHz * 1e6)
        if abs(qb_detune) > ConfigSettings.MAX_IF_BANDWIDTH:
            raise ValueError("qb_detune exceeds maximum IF bandwidth")

        delay_clks = create_clks_array(cfg.delay_begin, cfg.delay_end, cfg.dt)

        # Detuned frequency: explicit, not reading from self.attr
        detuned_rf = drive.rf_freq + qb_detune

        freq_plan = FrequencyPlan(entries=(
            ElementFreq(drive.element, detuned_rf, drive.lo_freq,
                        detuned_rf - drive.lo_freq, source="explicit"),
            ElementFreq(readout.element, readout.drive_frequency,
                        readout.binding.drive_out.lo_frequency,
                        readout.drive_frequency - readout.binding.drive_out.lo_frequency,
                        source="explicit"),
        ))
        freq_plan.apply(self.hw)

        prog = cQED_programs.T2_ramsey(
            cfg.r90, delay_clks, drive.therm_clks, cfg.n_avg,
            qb_el=drive.element,
            readout=readout,
        )
        result = self.run_program(prog, n_total=cfg.n_avg, ...)
        result.metadata["frequency_plan"] = freq_plan.to_metadata()
        result.metadata["qb_detune_Hz"] = qb_detune
        return result
```

**Key change:** The readout frequency comes from
`readout.drive_frequency` (an immutable field on `ReadoutCal`), not
from `measureMacro._drive_frequency` (a global singleton field).

### 6.4 ReadoutGEDiscrimination

**Before:**

```python
ge = ReadoutGEDiscrimination(session)
result = ge.run(
    "readout", attr.ro_fq, r180="x180", n_samples=50000,
    update_measure_macro=True, apply_rotated_weights=True, persist=True,
)
# Internally: mutates measureMacro._ro_disc_params
```

**After:**

```python
ge = ReadoutGEDiscrimination(session)
result = ge.run(
    GEDiscriminationConfig(r180="x180", n_samples=50000),
    drive=session.qubit(),
    readout=session.readout(),
)
analysis = ge.analyze(result, update_calibration=True)

# Get updated ReadoutCal for subsequent experiments:
updated_cal = analysis.metadata["updated_readout_cal"]
updated_ro = ReadoutHandle(
    binding=ro.binding,
    cal=updated_cal,
    element=ro.element,
    operation=ro.operation,
)
# Use updated_ro for subsequent experiments
```

**Key change:** No global state mutation. `analyze()` returns an updated
`ReadoutCal` that the user explicitly passes forward. Calibration is
persisted to `CalibrationStore` when `update_calibration=True`.

### 6.5 StorageSpectroscopy

**Before:**

```python
st_spec = StorageSpectroscopy(session)
result = st_spec.run(
    disp="const_alpha", rf_begin=5200*u.MHz, rf_end=5280*u.MHz,
    df=200*u.kHz, storage_therm_time=500, n_avg=50,
)
# Internally: attr.qb_el, attr.st_el, hw.get_element_lo(attr.st_el)
```

**After:**

```python
st_spec = StorageSpectroscopy(session)
result = st_spec.run(
    StorageSpectroscopyConfig(
        disp="const_alpha", rf_begin=5200e6, rf_end=5280e6,
        df=200e3, storage_therm_clks=500_000, n_avg=50,
    ),
    drive=session.qubit(),
    storage=session.storage(),
    readout=session.readout(),
)
```

**The `storage` parameter is just a `DriveTarget`** -- the same type as
`drive`. No `CavityBundle`, no role-specific type.

### 6.6 Full notebook session example

```python
# === Session setup ===
session = SessionManager("./cooldown", qop_ip="10.0.0.1")
session.open()

# Construct channel handles (once)
qb = session.qubit()        # DriveTarget for qubit
ro = session.readout()       # ReadoutHandle for resonator
st = session.storage()       # DriveTarget for storage cavity

# === Resonator spectroscopy ===
res_spec = ResonatorSpectroscopy(session)
result = res_spec.run(
    ResonatorSpectroscopyConfig(rf_begin=8.5e9, rf_end=8.7e9, df=100e3),
    readout=ro,
)
analysis = res_spec.analyze(result, update_calibration=True)

# === Power Rabi ===
rabi = PowerRabi(session)
result = rabi.run(
    PowerRabiConfig(op="ge_ref_r180", max_gain=0.5, dg=0.01, n_avg=4000),
    drive=qb, readout=ro,
)
analysis = rabi.analyze(result, update_calibration=True)

# === T1 ===
t1 = T1Relaxation(session)
result = t1.run(
    T1RelaxationConfig(delay_end=50_000, dt=500, n_avg=2000),
    drive=qb, readout=ro,
)
analysis = t1.analyze(result, update_calibration=True)

# === Readout calibration ===
ge = ReadoutGEDiscrimination(session)
result = ge.run(
    GEDiscriminationConfig(r180="x180", n_samples=50000),
    drive=qb, readout=ro,
)
analysis = ge.analyze(result, update_calibration=True)

# Re-fetch readout handle with updated calibration
ro = session.readout()  # picks up new threshold from CalibrationStore

# === T2 Ramsey (with updated readout calibration) ===
t2r = T2Ramsey(session)
result = t2r.run(
    T2RamseyConfig(qb_detune_MHz=0.2, delay_end=40_000, dt=100, n_avg=4000),
    drive=qb, readout=ro,
)
analysis = t2r.analyze(result, update_calibration=True)

# === Cavity experiment ===
st_spec = StorageSpectroscopy(session)
result = st_spec.run(
    StorageSpectroscopyConfig(
        disp="const_alpha", rf_begin=5200e6, rf_end=5280e6,
        df=200e3, n_avg=50,
    ),
    drive=qb, storage=st, readout=ro,
)
```

---

## 7. Migration Plan

### 7.1 Phases

#### Phase 0: Infrastructure types (no experiment changes)

| Step | Deliverable | Test |
|------|-------------|------|
| P0.1 | `DriveTarget` frozen dataclass | Unit tests: construction, if_freq property |
| P0.2 | `ReadoutCal` frozen dataclass with `from_calibration_store()` and `with_discrimination()` | Unit tests: construction from store, immutable update |
| P0.3 | `ReadoutHandle` frozen dataclass | Unit tests: physical_id, drive_frequency |
| P0.4 | `FrequencyPlan` and `ElementFreq` frozen dataclasses | Unit tests: construction, apply(), to_metadata() |
| P0.5 | `emit_measurement()` free function | Unit tests: QUA statement emission with ReadoutHandle |
| P0.6 | `session.drive_target()`, `session.readout_handle()` factories | Integration tests: resolve from hardware.json + CalibrationStore |
| P0.7 | `session.qubit()`, `session.storage()`, `session.readout()` shortcuts | Integration tests: ergonomic aliases |

**Backward compat: 100%.** No existing code changes.

#### Phase 1: Config objects + experiment signatures (per-experiment)

For each experiment class:

1. Define `*Config` frozen dataclass with all physics parameters
2. Add new `run()` overload accepting `(cfg, *, drive, readout, ...)`
3. Old `run()` signature delegates to new one with `compat_mode=True`
4. Build `FrequencyPlan` at `run()` entry
5. Pass `ReadoutHandle` to builder
6. Record `frequency_plan` in `RunResult.metadata`

**Migration order:**

| Order | Experiments | Rationale |
|---|---|---|
| 1 | `PowerRabi`, `TemporalRabi`, `T1Relaxation` | Simplest (D+R, no frequency override) |
| 2 | `T2Ramsey`, `T2Echo` | Frequency detuning handling |
| 3 | `ResonatorSpectroscopy`, `QubitSpectroscopy` | Frequency sweep patterns |
| 4 | `AllXY`, `DRAGCalibration`, `RandomizedBenchmarking` | Gate calibration |
| 5 | `IQBlob`, `ReadoutGEDiscrimination`, `ReadoutButterflyMeasurement` | Readout calibration (requires ReadoutCal split) |
| 6 | `CalibrateReadoutFull`, `ReadoutWeightsOptimization` | Full readout pipeline |
| 7 | `StorageSpectroscopy`, `StorageChiRamsey`, `StorageRamsey` | Cavity (D+S+R) |
| 8 | `FockResolved*`, `NumSplitting*` | Multi-Fock cavity |
| 9 | `QubitStateTomography`, `StorageWignerTomography` | Tomography |
| 10 | SPA experiments | Specialized |

**Backward compat: 100%.** Old-style `run()` calls still work via
delegation with `compat_mode=True` and `DeprecationWarning`.

#### Phase 2: Builder migration to emit_measurement()

For each builder function in `programs/builders/*.py`:

1. When `ReadoutHandle` is passed, call `emit_measurement(readout, ...)`
   instead of `measureMacro.measure(...)`
2. When `ReadoutHandle` is not passed (compat path), fall back to
   `measureMacro.measure(...)` with deprecation warning

| Builder file | Functions | Status |
|---|---|---|
| `time_domain.py` | 14 functions | All have `bindings` param; add `readout: ReadoutHandle \| None` |
| `spectroscopy.py` | 5 functions | All have `bindings` param; add `readout: ReadoutHandle \| None` |
| `calibration.py` | 6 functions | All have `bindings` param; add `readout: ReadoutHandle \| None` |
| `readout.py` | 8 functions | All have `bindings` param; add `readout: ReadoutHandle \| None` |
| `cavity.py` | 11 functions | All have `bindings` param; add `readout: ReadoutHandle \| None` |
| `tomography.py` | 2 functions | All have `bindings` param; add `readout: ReadoutHandle \| None` |

**Backward compat: 100%.** `readout=None` falls back to `measureMacro`.

#### Phase 3: measureMacro wrapper stage

1. `measureMacro.measure()` internally constructs a `ReadoutHandle` from
   its class-level state and delegates to `emit_measurement()`
2. No more independent implementation in `measureMacro.measure()`
3. Emit `DeprecationWarning` on every `measureMacro.measure()` call

**Backward compat: 100%.** All existing callsites work via wrapper.

#### Phase 4: Cleanup and removal

1. Remove old-style `run()` overloads (kwargs versions)
2. Remove `compat_mode` flag; require explicit `DriveTarget` / `ReadoutHandle`
3. Remove `self.attr.qb_el` / `self.attr.ro_el` reads from experiment classes
4. Remove `set_standard_frequencies()` from `ExperimentBase`
5. Remove `measureMacro` class (keep as import alias pointing to
   `emit_measurement` with final deprecation warning)
6. Remove `ReadoutConfig` hardcoded defaults (`ro_el="resonator"`)
7. Remove `_resolve_element_alias()` fallback logic from `preflight.py`

### 7.2 Backward compatibility policy

**No silent fallbacks.** All compatibility mechanisms are **loud**:

```python
def run(self, cfg=None, *, drive=None, readout=None,
        # Legacy kwargs (compat only):
        **legacy_kw):
    if cfg is None and legacy_kw:
        # Legacy path: construct config from kwargs
        warnings.warn(
            f"{self.name}.run(): Positional/keyword parameters are deprecated. "
            f"Use {self.name}Config(...) and pass drive/readout explicitly. "
            "This will be removed in v3.0.0.",
            DeprecationWarning, stacklevel=2,
        )
        cfg = self._build_compat_config(**legacy_kw)
    if drive is None:
        if not getattr(self, '_compat_mode', False):
            raise ValueError(
                f"{self.name}.run() requires 'drive: DriveTarget'. "
                "Pass session.qubit() or construct a DriveTarget explicitly."
            )
        warnings.warn(
            f"{self.name}.run(): Resolving drive from session attributes. "
            "Pass a DriveTarget explicitly to suppress this warning.",
            DeprecationWarning, stacklevel=2,
        )
        drive = self._compat_drive_target()
    ...
```

**Compat mode activation:**

```python
class ExperimentBase:
    def __init__(self, ctx, *, compat_mode: bool | None = None):
        self._ctx = ctx
        # Auto-detect: if session was opened with legacy set_roles(),
        # enable compat mode with a warning
        if compat_mode is None:
            compat_mode = getattr(ctx, '_legacy_roles_active', False)
            if compat_mode:
                warnings.warn(
                    "Legacy role-based session detected. Experiments will use "
                    "compat_mode=True. Migrate to session.qubit() / "
                    "session.readout() to suppress this warning.",
                    DeprecationWarning, stacklevel=2,
                )
        self._compat_mode = compat_mode
```

**Removal timeline:** Compat mode is deprecated in v2.1.0, removed in
v3.0.0. Each deprecation warning includes the target version.

### 7.3 Testing strategy

| Level | What | How |
|---|---|---|
| **Unit** | Config dataclasses, DriveTarget, ReadoutHandle, ReadoutCal, FrequencyPlan | Standard pytest; no hardware dependency |
| **Unit** | `emit_measurement()` | Mock QUA context; verify statement emission |
| **Integration** | New `run()` signatures produce identical QUA programs as old signatures | Build both programs, compare AST or serialized form |
| **Integration** | `session.qubit()` / `session.readout()` resolve correctly from hardware.json | Test with `samples/post_cavity_sample_A` config |
| **Notebook regression** | Full notebook with both old and new calling conventions | Run with `APPLY=False` orchestrator mode |
| **Compat mode** | Legacy notebooks emit DeprecationWarning but produce correct results | Capture warnings; verify identical outputs |

---

## 8. Risks & Mitigations

### 8.1 Risk matrix

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| **Config object proliferation** -- 35+ experiment-specific config types | Medium | High | Shared base fields via mixin or inheritance (`SweepConfigMixin` with `rf_begin/rf_end/df`). Config objects are simple frozen dataclasses, not heavy classes. |
| **User adoption friction** -- new API is more verbose for simple cases | Medium | Medium | `session.qubit()` / `session.readout()` shortcuts reduce to 2-3 extra tokens vs. current API. Config objects have sensible defaults. |
| **measureMacro removal breaks external consumer code** | High | Medium | Long deprecation runway (v2.0 → v3.0). `measureMacro.measure()` wrapper stays indefinitely as a deprecated import. |
| **ReadoutCal staleness** -- user holds stale handle across calibration update | Medium | Medium | `session.readout()` always reads fresh from CalibrationStore. Document "re-fetch after calibration" pattern in all examples. |
| **FrequencyPlan atomicity** -- `apply()` partially fails | Low | Low | `apply()` is a simple loop over `set_intermediate_frequency()` calls. If one fails, the QM API itself will raise. No partial state to clean up. |
| **Migration duration** -- 35+ experiments to migrate | High | High | Incremental migration (Phase 1-2 are independent per-experiment). Compat mode allows mixed old/new code. Each experiment is a standalone PR. |
| **Builder `readout` parameter threading** -- 46 builders need new param | Medium | High | Mechanical change: add `readout: ReadoutHandle | None = None`, add `if readout: emit_measurement(readout, ...) else: measureMacro.measure(...)`. Can be partially automated. |

### 8.2 Open questions

1. **Should `*Config` types use Pydantic BaseModel or frozen dataclass?**
   Argument for Pydantic: validation, serialization, schema generation.
   Argument for dataclass: lighter, matches existing binding types.
   **Recommendation:** Frozen dataclass with a `validate()` classmethod
   that raises `ValueError` on invalid combinations. This matches the
   existing pattern in `core/bindings.py`.

2. **Should `DriveTarget` include pulse operation names?**
   Pulse names are experiment-specific (e.g., `x180` for Rabi, `sel_x180`
   for cavity). They belong in the config object, not the channel target.
   **Recommendation:** Keep pulse names in `*Config` only.

3. **How to handle `transition` (ge/ef) in config objects?**
   Proposal: experiments that support ef transition accept
   `transition: str = "ge"` in their config, which selects the
   appropriate frequency and pulse mappings.

4. **Should `session.qubit()` cache the DriveTarget?**
   Pro: avoids repeated CalibrationStore lookups. Con: stale after
   frequency recalibration. **Recommendation:** No caching. The factory
   always reads fresh state. CalibrationStore lookups are O(1) dict
   access.

5. **Multi-qubit experiments?**
   The design scales naturally: `drive_1: DriveTarget`, `drive_2: DriveTarget`.
   The config object holds parameters specific to the multi-qubit protocol.
   Out of scope for this plan but the architecture supports it.

---

*End of plan.*
