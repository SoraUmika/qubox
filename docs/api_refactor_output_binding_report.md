# Binding-Driven API Redesign: Remove Element Definitions + Readout/measureMacro Refactor

> **Version**: 1.0 — 2026-02-26
> **Scope**: qubox_v2 v1.8.0
> **Status**: Proposal — awaiting review

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Proposed Binding Model (Target Architecture)](#2-proposed-binding-model-target-architecture)
3. [Readout / measureMacro Redesign Options + Recommendation](#3-readout--measuremacro-redesign-options--recommendation)
4. [Codebase Coupling Survey (Ranked)](#4-codebase-coupling-survey-ranked)
5. [Calibration & Artifact Schema Changes](#5-calibration--artifact-schema-changes)
6. [Migration Plan with Phases](#6-migration-plan-with-phases)
7. [Appendix A: Before vs After API Examples](#7-appendix-a-before-vs-after-api-examples)
8. [Appendix B: Glossary](#8-appendix-b-glossary)

---

## 1. Executive Summary

The current qubox_v2 architecture relies on **named "elements"** defined in `hardware.json` (e.g., `"qubit"`, `"resonator"`, `"storage"`) that are implicitly referenced throughout experiments, program builders, macros, calibration storage, and session management. This coupling creates several problems:

- **Hidden assumptions**: Experiments silently break when element names change or differ across samples.
- **Reuse friction**: Moving an experiment to a new device requires renaming elements in `hardware.json` or patching string references.
- **Readout is a global singleton**: `measureMacro` is a class-level singleton keyed to a single active readout element, making multi-readout or multi-qubit experiments fragile.
- **Calibration data is keyed by mutable aliases**: Renaming elements orphans calibration records.

This report proposes a **binding-driven architecture** where:

1. Physical channels (controller ports, Octave RF outputs/inputs, ADC ports) are the stable identity layer.
2. Human-friendly aliases map to physical channels, not to QM element definitions.
3. Experiments receive explicit binding objects — no experiment assumes a globally-defined element name exists.
4. `measureMacro` is refactored to accept a `ReadoutBinding` instead of relying on a global readout element.
5. Calibration data is keyed by **physical channel ID**, with alias pointers for convenience.

**Recommended readout design**: Option A — `measureMacro` becomes binding-based (see §3).

---

## 2. Proposed Binding Model (Target Architecture)

### 2.1 Core Concepts

```
┌─────────────────────────────────────────────────────────┐
│                  Physical Layer                          │
│  ChannelRef: stable identity for a physical port         │
│  e.g. ("con1", "analog_out", 3) or ("oct1", "RF_out", 1)│
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                  Binding Layer                            │
│  OutputBinding: ChannelRef + IF freq + gain + pulse_ops  │
│  InputBinding:  ChannelRef + time_of_flight + weights    │
│  ReadoutBinding: OutputBinding + InputBinding (paired)    │
│  AliasMap: str → ChannelRef (user-friendly names)        │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                  Experiment Layer                         │
│  ExperimentBindings: named collection of bindings        │
│  Passed explicitly to every experiment                   │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Type Definitions

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class ChannelRef:
    """Stable physical identity for a hardware port.

    Examples:
        ChannelRef("con1", "analog_out", 3)
        ChannelRef("oct1", "RF_out", 1)
        ChannelRef("con1", "analog_in", 1)
    """
    device: str          # controller or octave name
    port_type: str       # "analog_out", "analog_in", "RF_out", "RF_in", "digital_out"
    port_number: int

    @property
    def canonical_id(self) -> str:
        """Stable string key for calibration/artifact storage."""
        return f"{self.device}:{self.port_type}:{self.port_number}"


@dataclass
class OutputBinding:
    """A bound control output channel."""
    channel: ChannelRef
    intermediate_frequency: float = 0.0
    lo_frequency: float | None = None
    gain: float | None = None
    digital_inputs: dict[str, ChannelRef] = field(default_factory=dict)

    # Pulse operations registered for this output
    operations: dict[str, str] = field(default_factory=dict)  # op_name -> pulse_name


@dataclass
class InputBinding:
    """A bound acquisition input channel."""
    channel: ChannelRef
    lo_frequency: float | None = None
    time_of_flight: int = 24
    smearing: int = 0

    # Integration weight identifiers
    weight_keys: list[list[str]] = field(
        default_factory=lambda: [["cos", "sin"], ["minus_sin", "cos"]]
    )
    weight_length: int | None = None


@dataclass
class ReadoutBinding:
    """Paired output + input for readout/measurement.

    Encapsulates everything measureMacro needs: the drive output,
    the acquisition input, and all DSP configuration.
    """
    drive_out: OutputBinding
    acquire_in: InputBinding

    # PulseOp currently bound for measurement
    pulse_op: "PulseOp | None" = None
    active_op: str | None = None     # QUA operation handle

    # Demod configuration
    demod_weight_sets: list[list[str]] = field(
        default_factory=lambda: [["cos", "sin"], ["minus_sin", "cos"]]
    )

    # Discrimination / DSP state (replaces measureMacro class-level state)
    discrimination: dict = field(default_factory=dict)
    quality: dict = field(default_factory=dict)
    drive_frequency: float | None = None

    @property
    def physical_id(self) -> str:
        """Canonical key for calibration storage."""
        return self.acquire_in.channel.canonical_id


@dataclass
class ExperimentBindings:
    """Collection of bindings passed to an experiment.

    Replaces the implicit assumption that element names like
    "qubit", "resonator", "storage" exist in hardware.json.
    """
    qubit: OutputBinding
    readout: ReadoutBinding
    storage: OutputBinding | None = None

    # Additional named bindings for multi-element experiments
    extras: dict[str, OutputBinding | ReadoutBinding] = field(default_factory=dict)


# Alias layer
AliasMap = dict[str, ChannelRef]   # e.g. {"qubit": ChannelRef("oct1","RF_out",2)}
```

### 2.3 Key Rules

1. **No experiment imports or references a global element name string.** Element-like names exist only as keys in `ExperimentBindings` — they are structural roles, not global identifiers.

2. **QM config elements are constructed at runtime from bindings.** At the compilation boundary (before handing a QUA program to `ProgramRunner`), a `ConfigBuilder` synthesizes the required QM elements dict from the active bindings.

3. **Calibration is keyed by `ChannelRef.canonical_id`**, not by alias. A mapping layer lets users look up calibration by alias for convenience, but the storage key is always the physical port identity.

4. **`measureMacro` receives `ReadoutBinding`** instead of looking up a global element name. All DSP state (discrimination, weights, thresholds) lives on the `ReadoutBinding` instance, not on class-level singletons.

### 2.4 ConfigBuilder: Binding → QM Element

```python
class ConfigBuilder:
    """Synthesize QM config element dicts from bindings at compile time."""

    @staticmethod
    def build_element(
        name: str,
        binding: OutputBinding | ReadoutBinding,
        pulse_registry: PulseRegistry,
    ) -> dict:
        """Build a single QM element definition from a binding.

        This is the ONLY place where QM "element" dicts are created.
        The name is ephemeral — used only for the QM config dict.
        """
        if isinstance(binding, ReadoutBinding):
            return ConfigBuilder._build_readout_element(name, binding, pulse_registry)
        return ConfigBuilder._build_control_element(name, binding, pulse_registry)

    @staticmethod
    def build_config(bindings: ExperimentBindings, pulse_registry) -> dict:
        """Build a full QM config from an ExperimentBindings bundle."""
        elements = {}
        elements["__qb"] = ConfigBuilder.build_element("__qb", bindings.qubit, pulse_registry)
        elements["__ro"] = ConfigBuilder.build_element("__ro", bindings.readout, pulse_registry)
        if bindings.storage:
            elements["__st"] = ConfigBuilder.build_element("__st", bindings.storage, pulse_registry)
        for k, b in bindings.extras.items():
            elements[f"__ext_{k}"] = ConfigBuilder.build_element(f"__ext_{k}", b, pulse_registry)
        # Merge with base hardware config (controllers, octaves)
        # ...
        return {"elements": elements, ...}
```

The `__qb`, `__ro` prefixes are internal implementation details. Users never see or reference these names. The experiment code uses the binding objects directly, and the builders receive ephemeral element names from the `ConfigBuilder`.

---

## 3. Readout / measureMacro Redesign Options + Recommendation

### 3.0 Current State

`measureMacro` is a **class-level singleton** (not instantiable — raises `TypeError` on `__new__`). All state is stored as class attributes:

- `_pulse_op` / `_active_op` — bound element + operation
- `_demod_weight_sets` — integration weight names
- `_ro_disc_params` — discrimination thresholds, mu/sigma, fidelity
- `_ro_quality_params` — butterfly metrics, confusion matrix, affine corrections
- `_drive_frequency`, `_gain`, `_post_select_config`

The `.measure()` method calls `cls.active_element()` (which reads `_pulse_op.element`) and `cls.active_op()` to emit the QUA `measure()` statement.

**348 callsites** reference `measureMacro` across the codebase.

---

### 3.1 Option A: measureMacro Becomes Binding-Based (Recommended)

#### What the user passes

Every experiment that does readout receives a `ReadoutBinding` (either directly or via `ExperimentBindings`). The `ReadoutBinding` carries all measurement state.

#### How QUA building changes

```python
# BEFORE (current)
measureMacro.set_pulse_op(ro_pulse_op, active_op="readout")
measureMacro.set_IQ_mod(("cos","sin"), ("minus_sin","cos"))
# ... inside QUA program:
I, Q = measureMacro.measure()

# AFTER (Option A)
ro_binding = bindings.readout  # ReadoutBinding instance
# ... inside QUA program:
I, Q = measure_with_binding(ro_binding, targets=[I_var, Q_var])
```

Where `measure_with_binding` is a free function (or a method on a non-singleton `MeasurementEngine`):

```python
def measure_with_binding(
    ro: ReadoutBinding,
    *,
    element_name: str,    # ephemeral name from ConfigBuilder
    targets: list = None,
    with_state: bool = False,
    gain=None,
    timestamp_stream=None,
    adc_stream=None,
):
    """Emit a QUA measure() statement using a ReadoutBinding."""
    op_handle = ro.active_op or ro.pulse_op.op
    eff_gain = gain if gain is not None else ro.drive_out.gain
    pulse = op_handle if eff_gain is None else op_handle * amp(eff_gain)

    outputs = _build_demod_outputs(ro.demod_weight_sets, targets)
    measure(pulse, element_name, None, *outputs,
            timestamp_stream=timestamp_stream, adc_stream=adc_stream)
    align()
```

#### Where DSP config lives

| Concern | Location |
|---------|----------|
| Integration weights / demod | `ReadoutBinding.demod_weight_sets` + `InputBinding.weight_keys` |
| IQ rotation angle | `ReadoutBinding.discrimination["angle"]` |
| Discrimination model, thresholds | `ReadoutBinding.discrimination` dict |
| Confusion matrix, transition rates | `ReadoutBinding.quality` dict |
| Clipping / post-selection | `ReadoutBinding` can carry a `PostSelectionConfig` |

#### How calibration pipelines work without element keys

```python
# Patching after GE Discrimination:
cal_store.set_discrimination(
    channel_id=ro_binding.physical_id,    # e.g. "con1:analog_in:1"
    threshold=result["threshold"],
    angle=result["angle"],
    ...
)

# Syncing back to binding:
ro_binding.discrimination = cal_store.get_discrimination(ro_binding.physical_id).to_dict()
```

The `CalibrationOrchestrator` patch rules reference `ReadoutBinding.physical_id` instead of an element name string.

#### Silent mis-binding prevention

- `ReadoutBinding` pairs an `OutputBinding` (drive) with an `InputBinding` (acquire). The constructor can validate that the output and input are on compatible hardware (same Octave port group, correct controller routing).
- `ChannelRef.canonical_id` is immutable and derived from physical wiring — it cannot accidentally point to the wrong ADC.
- A `validate_binding()` function checks that the Octave RF output → RF input → controller ADC routing chain is consistent with `hardware.json`'s `octave_links`.

#### Pros
- Cleanest API: experiments state exactly what they need, no hidden globals.
- Supports multi-readout naturally (each readout has its own binding with its own DSP state).
- `ReadoutBinding` is serializable — snapshot/restore becomes trivial.
- Eliminates the singleton anti-pattern.

#### Cons
- Most invasive: 348 `measureMacro` callsites need updating.
- Program builders need a new parameter signature.
- Requires careful backward-compatibility shimming during migration.

---

### 3.2 Option B: Runtime Element at Compilation Boundary

#### What the user passes

The user still constructs a `ReadoutBinding`, but the actual `measureMacro` internals are unchanged. A `CompilationAdapter` translates bindings into ephemeral QM element names at compile time and configures `measureMacro` accordingly.

```python
# User code
bindings = ExperimentBindings(qubit=qb_binding, readout=ro_binding)

# At compile boundary
with CompilationAdapter(bindings) as ctx:
    # measureMacro is auto-configured with the correct element name
    prog = power_rabi(
        qb_el=ctx.qubit_element_name,     # ephemeral, e.g. "__qb"
        ...
    )
    result = runner.execute(prog, ctx.compiled_config)
```

#### How `measureMacro` behaves

`measureMacro` remains a singleton but is configured by `CompilationAdapter` at entry:

```python
class CompilationAdapter:
    def __enter__(self):
        measureMacro.push_settings()
        measureMacro.set_pulse_op(
            self.readout.pulse_op,
            active_op=self.readout.active_op,
            weights=self.readout.demod_weight_sets,
        )
        # inject discrimination state
        measureMacro._ro_disc_params = dict(self.readout.discrimination)
        measureMacro._ro_quality_params = dict(self.readout.quality)
        return self

    def __exit__(self, *exc):
        measureMacro.restore_settings()
```

#### Where DSP config lives

Same as Option A — on the `ReadoutBinding`. But it's copied into `measureMacro` class attributes at compile time.

#### Calibration without element keys

Same physical-ID keying as Option A. The `CompilationAdapter` translates.

#### Silent mis-binding prevention

Same as Option A at the binding construction layer.

#### Pros
- **Minimal program builder changes**: builders still call `measureMacro.measure()` with the same API.
- Faster migration — only the experiment entry point and calibration storage change.

#### Cons
- `measureMacro` remains a singleton: multi-readout in a single QUA program is still awkward (requires push/pop around each measurement).
- `CompilationAdapter` context manager adds a layer of indirection.
- "Half-way" solution that preserves the global mutable state pattern.

---

### 3.3 Option C: Measurement Contract / Acquisition Pipeline

#### What the user passes

A `MeasurementContract` that describes *what* the experiment needs from readout, without specifying *how*:

```python
@dataclass
class MeasurementContract:
    """Declarative specification of what an experiment needs from readout."""
    needs_iq: bool = True
    needs_state: bool = False
    needs_raw_adc: bool = False
    num_outputs: int = 2
    weight_set: str = "base"
    post_selection: PostSelectionConfig | None = None

contract = MeasurementContract(needs_iq=True, needs_state=True)
```

A separate `AcquisitionPipeline` resolves the contract against a `ReadoutBinding`:

```python
pipeline = AcquisitionPipeline(contract, ro_binding)
# Inside QUA:
result = pipeline.execute()   # returns MeasurementResult with I, Q, state
```

#### Calibration without element keys

Same physical-ID keying.

#### Pros
- Most future-proof: decouples experiment intent from hardware details.
- Natural fit for multi-mode acquisition (IQ + raw ADC + state simultaneously).

#### Cons
- Highest abstraction cost — significant new code for the pipeline layer.
- Over-engineered for the current single-readout use case.
- Harder to debug: another layer between experiments and QUA.

---

### 3.4 Recommendation: Option A

**Option A (binding-based `measureMacro`)** is the recommended approach because:

1. It directly solves the root problem (global mutable singleton keyed to element names).
2. It naturally supports multi-readout without push/pop hacks.
3. The `ReadoutBinding` is a self-contained, serializable unit of measurement configuration — clean for persistence, snapshots, and testing.
4. While 348 callsites is significant, the migration can be automated (see §6) and done incrementally.

Option B is acceptable as a **transitional step** (Phase 1-2 of migration), but should not be the long-term target.

### 3.5 Parts of the Codebase That Must Change

| Component | What changes | Effort |
|-----------|-------------|--------|
| `programs/macros/measure.py` | Replace class-level singleton with `measure_with_binding()` free function; keep shim for `measureMacro` during transition | High |
| `programs/macros/sequence.py` | Accept `ReadoutBinding` + ephemeral element name instead of `qb_el` defaults | Medium |
| `programs/builders/*.py` | Add `ReadoutBinding` parameter; derive `element_name` from ConfigBuilder | Medium |
| `experiments/base.py` | Base class constructs `ExperimentBindings` from session attributes | Medium |
| `experiments/session.py` | `override_readout_operation()` returns a `ReadoutBinding`; new `build_bindings()` method | Medium |
| `calibration/store.py` | Dual-keying (physical ID + alias) — see §5 | Medium |
| `calibration/orchestrator.py` | Patch rules reference `ReadoutBinding.physical_id` | Medium |
| `core/preflight.py` | Validate bindings instead of element-name lookups | Low |
| `pulses/pulse_registry.py` | Remove `_RESERVED_OPS` tied to "readout" string; make readout pulse a normal pulse | Low |
| `analysis/cQED_attributes.py` | Derive `ro_el`/`qb_el` from bindings; keep as compat aliases | Low |

### 3.6 Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Breaking existing notebooks | Adapter layer (§6 Phase 0) auto-converts old sessions to bindings |
| Performance regression from added indirection | Bindings are dataclasses — no runtime overhead beyond attribute access |
| Multi-readout ordering bugs | `ReadoutBinding` carries its own DSP state; no shared mutable globals |
| Calibration data loss during migration | Migration script copies records from old (element-name) keys to new (physical-ID) keys; old keys kept as aliases |
| 348 measureMacro callsites | Automated codemod + staged rollout (builders first, then experiments) |

---

## 4. Codebase Coupling Survey (Ranked)

### 4.1 Ranked Impact List

Items ranked from **highest risk** (most callsites, most assumptions, hardest to fix) to **lowest risk**.

---

#### Rank 1: `measureMacro` Singleton — 348 references

**Files**: `programs/macros/measure.py` (definition), `programs/builders/*.py` (37+38+16+13+17 callsites), `programs/macros/sequence.py` (10 callsites), `experiments/calibration/readout.py` (63 callsites), `experiments/legacy_experiment.py` (75+ callsites)

**What breaks**: Every program builder calls `measureMacro.measure()`, `measureMacro.active_element()`, or `measureMacro.active_op()`. These assume a single global readout element is configured via `set_pulse_op()`.

**Minimal refactor**:
- Introduce `measure_with_binding(ro: ReadoutBinding, element_name: str, ...)` as a drop-in alongside `measureMacro.measure()`.
- Add a compat shim: `measureMacro.measure()` internally constructs a `ReadoutBinding` from its class-level state and delegates.
- Migrate builders one at a time to the new signature.

---

#### Rank 2: `cQED_attributes` — `ro_el`, `qb_el`, `st_el` — 648+ indirect accesses

**Files**: `analysis/cQED_attributes.py` (definition), `experiments/legacy_experiment.py` (all `attr.ro_el`, `attr.qb_el` accesses), `experiments/base.py` (frequency/LO lookups), `experiments/session.py` (attribute setting)

**What breaks**: Every experiment reads element names from `attr.ro_el` / `attr.qb_el` and passes them to builders. This is the primary propagation path of element name strings.

**Minimal refactor**:
- `cQED_attributes` gains a `.bindings` property that returns an `ExperimentBindings` constructed from the current `ro_el`/`qb_el`/`st_el` + hardware config.
- Experiments are migrated to read from `self.bindings` instead of `attr.ro_el`.
- The old `ro_el`/`qb_el` properties remain for backward compat, derived from bindings.

---

#### Rank 3: `ReadoutConfig` — Hardcoded `"resonator"` and `"readout"` defaults

**File**: `experiments/calibration/readout_config.py:79-91`

```python
ro_op: str = "readout"         # HARDCODED
ro_el: str = "resonator"       # HARDCODED
cos_weight_key: str = "cos"    # HARDCODED
sin_weight_key: str = "sin"    # HARDCODED
m_sin_weight_key: str = "minus_sin"  # HARDCODED
```

**What breaks**: Any readout calibration call that doesn't override these defaults uses `"resonator"` as the element name and `"readout"` as the operation.

**Minimal refactor**:
- Remove defaults. Require explicit construction or derive from `ReadoutBinding`.
- Add factory method: `ReadoutConfig.from_binding(ro: ReadoutBinding) -> ReadoutConfig`.

---

#### Rank 4: `sequenceMacros` — Hardcoded `qb_el="qubit"`, `st_el="storage"`

**File**: `programs/macros/sequence.py` — 7 function signatures with defaults

**What breaks**: Any call to `prepare_state()`, `qubit_state_tomography()`, `num_splitting_spectroscopy()`, etc. that omits the element argument silently uses `"qubit"` or `"storage"`.

**Minimal refactor**:
- Change defaults to `None`; resolve from `ExperimentBindings` at call time.
- Alternatively, make element name a required parameter with no default.

---

#### Rank 5: `PulseRegistry` — Reserved `"readout"` operation

**File**: `pulses/pulse_registry.py:34-36, 86-89`

```python
_RESERVED_OPS = frozenset({"readout"})
# Global wildcard mapping:
self._perm.el_ops["*"] = {"const": ..., "readout": "readout_pulse"}
```

**What breaks**: Every QM element automatically gets a `"readout"` operation mapped to `"readout_pulse"`. This is the hidden mechanism that makes `measure("readout", ...)` work without explicit registration.

**Minimal refactor**:
- Remove the `"*"` wildcard for `"readout"`.
- Readout pulse registration happens explicitly in `ReadoutBinding` → `ConfigBuilder` flow.
- Keep `"const"` as universal default (it's genuinely universal).

---

#### Rank 6: `core/preflight.py` — Element alias fallback chain

**File**: `core/preflight.py:108-119, 162`

```python
if "resonator" in hw_elements: return "resonator", ...
ro_el = session.attributes.ro_el if hasattr(...) else "readout"
```

**What breaks**: Preflight validation hard-codes the assumption that a readout element exists under `"resonator"` or `"readout"`.

**Minimal refactor**:
- Preflight checks bindings for completeness instead of looking up element names.
- `preflight_check(session)` → `preflight_check(session, bindings: ExperimentBindings)`.

---

#### Rank 7: `CalibrationStore` — Element-name-keyed dictionaries

**File**: `calibration/store.py`, `calibration/models.py`

All calibration data is keyed by element name strings:
```python
discrimination: dict[str, DiscriminationParams]    # "resonator" -> ...
frequencies: dict[str, ElementFrequencies]          # "qubit" -> ...
coherence: dict[str, CoherenceParams]               # "qubit" -> ...
```

**What breaks**: Renaming an element in `hardware.json` orphans all calibration data. Cross-device comparison requires manual key translation.

**Minimal refactor**: See §5 for detailed schema changes.

---

#### Rank 8: `CalibrationOrchestrator` — Dotted path routing uses element names

**File**: `calibration/orchestrator.py`

Patch operations use paths like `"frequencies.qubit.rf_freq"`, `"discrimination.resonator.threshold"`.

**What breaks**: If the element key in the calibration store changes, all patch rules break.

**Minimal refactor**:
- Patch paths become `"frequencies.<channel_id>.rf_freq"`.
- Patch rules receive `ReadoutBinding.physical_id` or `OutputBinding.channel.canonical_id` instead of element name strings.

---

#### Rank 9: `experiments/session.py` — `override_readout_operation()`

**File**: `experiments/session.py:550-618`

Sets `self.attributes.ro_el = element` and pushes into `measureMacro`.

**What breaks**: This is the primary runtime override point for readout configuration.

**Minimal refactor**:
- Replace with `build_readout_binding(channel: ChannelRef, ...) -> ReadoutBinding`.
- Keep `override_readout_operation()` as a compat wrapper that internally creates a binding.

---

#### Rank 10: `PulseOperationManager` — Readout constants

**File**: `pulses/manager.py:72-80`

```python
READOUT_PULSE_NAME = "readout_pulse"
READOUT_IW_COS_NAME = "readout_cosine_weights"
```

**What breaks**: These are referenced during QM config generation to wire up readout weights.

**Minimal refactor**: These constants become configurable properties of `ReadoutBinding` rather than global constants.

---

#### Rank 11: `experiments/calibration/readout.py` — Readout GE / Butterfly

**File**: `experiments/calibration/readout.py` — 63+ measureMacro callsites

`ReadoutGEDiscrimination` and `ReadoutButterflyMeasurement` both heavily use `measureMacro._ro_disc_params` and `measureMacro.active_element()`.

**What breaks**: These experiments assume a single global readout binding.

**Minimal refactor**:
- Accept `ReadoutBinding` in constructor.
- Read/write discrimination state on the binding, not on the singleton.

---

#### Rank 12: `migration/pulses_converter.py` — Hardcoded `"resonator"` mapping

**File**: `migration/pulses_converter.py:447-462`

Migration logic maps legacy pulse definitions to `"resonator"` element.

**What breaks**: Only relevant for legacy migration; low ongoing risk.

**Minimal refactor**: No change needed — this is a one-time migration tool.

---

## 5. Calibration & Artifact Schema Changes

### 5.1 Current Schema (v4.0.0)

```python
# All keyed by element name (str):
CalibrationData:
    discrimination:  {"resonator": DiscriminationParams, ...}
    readout_quality: {"resonator": ReadoutQuality, ...}
    frequencies:     {"qubit": ElementFrequencies, ...}
    coherence:       {"qubit": CoherenceParams, ...}
```

### 5.2 Proposed Schema (v5.0.0)

```python
class CalibrationData(BaseModel):
    version: str = "5.0.0"

    # PRIMARY KEY: physical channel ID (ChannelRef.canonical_id)
    # e.g. "con1:analog_in:1" or "oct1:RF_out:2"
    discrimination:  dict[str, DiscriminationParams] = {}
    readout_quality: dict[str, ReadoutQuality] = {}
    frequencies:     dict[str, ElementFrequencies] = {}
    coherence:       dict[str, CoherenceParams] = {}
    pulse_calibrations: dict[str, PulseCalibration] = {}

    # ALIAS INDEX: maps human-friendly names to physical IDs
    # e.g. {"resonator": "con1:analog_in:1", "qubit": "oct1:RF_out:2"}
    alias_index: dict[str, str] = {}

    # REVERSE INDEX: physical_id -> [aliases]
    # Auto-derived, not stored (computed on load)
```

### 5.3 Accessors with Dual Lookup

```python
class CalibrationStore:
    def get_discrimination(self, key: str) -> DiscriminationParams | None:
        """Look up by physical_id first, then try alias_index."""
        if key in self._data.discrimination:
            return self._data.discrimination[key]
        # Try alias resolution
        physical_id = self._data.alias_index.get(key)
        if physical_id:
            return self._data.discrimination.get(physical_id)
        return None

    def set_discrimination(self, key: str, params: DiscriminationParams, **kw):
        """Always store under physical_id. Resolve aliases if needed."""
        physical_id = self._resolve_key(key)
        self._data.discrimination[physical_id] = params
        self._touch()

    def _resolve_key(self, key: str) -> str:
        """If key is an alias, return the physical_id. Otherwise return key as-is."""
        return self._data.alias_index.get(key, key)

    def register_alias(self, alias: str, physical_id: str):
        """Map a human-friendly name to a physical channel ID."""
        self._data.alias_index[alias] = physical_id
```

### 5.4 Artifact Storage Update

Current artifact path: `artifacts/<build_hash>/`

Proposed: artifacts continue to use build-hash keying (which already captures the full config snapshot). The `SessionState` snapshot includes the `alias_index` so that artifact provenance can resolve channel IDs to aliases at the time of capture.

### 5.5 Preventing Accidental Misapplication

| Concern | Solution |
|---------|----------|
| Patch applied to wrong channel | Patch rules receive `ReadoutBinding.physical_id` — a stable, derived value |
| Alias renamed after calibration | Alias index updated; physical-ID keys are unchanged |
| Two aliases point to same physical port | Allowed — `alias_index` is a many-to-one mapping. CalibrationStore resolves to the same physical record |
| Stale alias in old notebook | Lookup falls back to physical-ID; alias miss produces a clear warning |

---

## 6. Migration Plan with Phases

### Phase 0: Introduce Binding Objects + Adapter Layer

**Goal**: Old notebooks continue to work unchanged. New binding types are available but optional.

**Steps**:
1. Add `ChannelRef`, `OutputBinding`, `InputBinding`, `ReadoutBinding`, `ExperimentBindings` to `qubox_v2/core/bindings.py`.
2. Add `AliasMap` loader that reads `hardware.json` element definitions and produces bindings:
   ```python
   def bindings_from_hardware_config(
       hw: HardwareConfig,
       attr: cQED_attributes,
   ) -> ExperimentBindings:
       """Backward-compatible: derive bindings from existing element definitions."""
   ```
3. Add `ConfigBuilder` that can synthesize QM element dicts from bindings (inverse of step 2).
4. `SessionManager` gains a `.bindings` property that lazily constructs `ExperimentBindings` from its current hardware config + attributes. No experiments are modified yet.
5. `CalibrationStore` gets `alias_index` support (§5) but continues accepting element-name keys transparently.
6. Add `validate_binding()` utility that checks hardware routing consistency.

**Backward compat**: 100%. Nothing changes for existing users.

---

### Phase 1: Update Subset of Experiments to Accept Explicit Bindings

**Goal**: Demonstrate the new API on key experiments. Both old and new calling conventions work.

**Steps**:
1. Update program builders to accept an optional `bindings: ExperimentBindings | None` parameter alongside existing element-name parameters:
   ```python
   def power_rabi(
       qb_el: str | None = None,
       ...,
       bindings: ExperimentBindings | None = None,
   ):
       if bindings is not None:
           qb_el = bindings.qubit.element_name  # ephemeral
       ...
   ```
2. Start with these experiments (high-value, representative):
   - `ResonatorSpectroscopy`
   - `QubitSpectroscopy`
   - `PowerRabi`
   - `T1Relaxation`
   - `T2Ramsey`
3. Update `ExperimentBase` to pass `self.bindings` to builders when available.
4. Update `ReadoutConfig` to add `from_binding()` factory.
5. Write integration tests that run the same experiment with both old-style (element names) and new-style (bindings) calling conventions and verify identical QUA programs.

**Backward compat**: 100%. Old-style calls still work; `bindings=None` falls back to element names.

---

### Phase 2: Refactor measureMacro and Readout Pipelines

**Goal**: `measureMacro` gains binding-aware methods. ReadoutGEDiscrimination and ReadoutButterflyMeasurement work with bindings.

**Steps**:
1. Add `measure_with_binding()` free function in `programs/macros/measure.py`.
2. Add compat shim inside `measureMacro.measure()` that delegates to `measure_with_binding()` when a binding is available.
3. Move DSP state (`_ro_disc_params`, `_ro_quality_params`) to `ReadoutBinding` instances.
4. `measureMacro.sync_from_calibration(cal_store, element)` → `ReadoutBinding.sync_from_calibration(cal_store)` (using `self.physical_id`).
5. Update `ReadoutGEDiscrimination` to accept `ReadoutBinding`.
6. Update `ReadoutButterflyMeasurement` to accept `ReadoutBinding`.
7. Update `CalibrationOrchestrator` patch rules (`SetMeasureDiscrimination`, `SetMeasureQuality`) to write to binding instead of singleton.
8. Update `sequence.py` macros — replace default `qb_el="qubit"` with `qb_el: str | None = None` + binding resolution.

**Backward compat**: `measureMacro` singleton API still works but logs a deprecation warning when used without bindings.

---

### Phase 3: Deprecate / Remove Element-Name Assumptions

**Goal**: Element names are fully ephemeral. All experiments use bindings.

**Steps**:
1. Migrate remaining experiments (cavity, tomography, SPA) to bindings.
2. Migrate `legacy_experiment.py` (75+ callsites).
3. Remove `_BASELINE_ELEMENTS = ("qubit",)` from `preflight.py`.
4. Remove `_RESERVED_OPS = frozenset({"readout"})` from `pulse_registry.py`.
5. Remove the `"*"` wildcard readout mapping.
6. `cQED_attributes.ro_el` / `qb_el` become derived properties from bindings (not stored directly).
7. `CalibrationStore` v5 becomes the default; migration script converts v4 data.
8. Remove element-name fallback logic from `preflight.py`, `session.py`, `readout_config.py`.
9. `measureMacro` singleton is removed; `measure_with_binding()` is the only API.

**Backward compat**: Adapter layer warnings become errors. Old notebooks can run with an `import qubox_v2.compat.legacy_bindings` shim that synthesizes bindings from element names.

---

## 7. Appendix A: Before vs After API Examples

### A.1 Qubit Spectroscopy

**Before**:
```python
session = SessionManager("./cooldown", qop_ip="10.0.0.1")
session.open()

attr = session.attributes
spec = QubitSpectroscopy(
    session,
    sat_pulse="saturation",
    if_frequencies=np.arange(-200e6, 200e6, 0.5e6),
    qb_gain=0.1,
    qb_len=10_000,
)
spec.run()
```
Internally calls `qubit_spectroscopy(qb_el=attr.qb_el, ...)` which uses the element name from `cqed_params.json`.

**After**:
```python
session = SessionManager("./cooldown", qop_ip="10.0.0.1")
session.open()

bindings = session.bindings   # auto-derived from hardware.json + cqed_params.json
spec = QubitSpectroscopy(
    session,
    bindings=bindings,
    sat_pulse="saturation",
    if_frequencies=np.arange(-200e6, 200e6, 0.5e6),
    qb_gain=0.1,
    qb_len=10_000,
)
spec.run()
```
Internally calls `qubit_spectroscopy(bindings=bindings, ...)`. The qubit element name is resolved at compile time from `bindings.qubit`.

---

### A.2 Power Rabi

**Before**:
```python
rabi = PowerRabi(
    session,
    pulse="x180",
    gains=np.linspace(0, 0.5, 100),
    qb_clock_len=4,
)
rabi.run()
```
Reads `attr.qb_el` to get `"qubit"`, passes to `power_rabi(qb_el="qubit", ...)`.

**After**:
```python
rabi = PowerRabi(
    session,
    bindings=session.bindings,
    pulse="x180",
    gains=np.linspace(0, 0.5, 100),
    qb_clock_len=4,
)
rabi.run()
```
`power_rabi(bindings=session.bindings, ...)` — qubit element constructed at compile time.

---

### A.3 T1 Relaxation

**Before**:
```python
t1 = T1Relaxation(
    session,
    r180="x180",
    wait_times=np.logspace(2, 5, 50),
)
t1.run()
# Calibration patched to: cal_store.set_coherence("qubit", T1=result)
```

**After**:
```python
t1 = T1Relaxation(
    session,
    bindings=session.bindings,
    r180="x180",
    wait_times=np.logspace(2, 5, 50),
)
t1.run()
# Calibration patched to: cal_store.set_coherence("oct1:RF_out:2", T1=result)
# (where "oct1:RF_out:2" is bindings.qubit.channel.canonical_id)
```

---

### A.4 Ramsey

**Before**:
```python
ramsey = T2Ramsey(
    session,
    r90="x90",
    wait_times=np.logspace(1, 5, 100),
)
ramsey.run()
```

**After**:
```python
ramsey = T2Ramsey(
    session,
    bindings=session.bindings,
    r90="x90",
    wait_times=np.logspace(1, 5, 100),
)
ramsey.run()
```

---

### A.5 Mixer Calibration (Readout Frequency Optimization)

**Before**:
```python
ro_opt = ReadoutFrequencyOptimization(
    session,
    if_frequencies=np.arange(-300e6, 300e6, 1e6),
)
ro_opt.run()
# Internally: resonator_spectroscopy(ro_el=attr.ro_el, ...)
```

**After**:
```python
ro_opt = ReadoutFrequencyOptimization(
    session,
    bindings=session.bindings,
    if_frequencies=np.arange(-300e6, 300e6, 1e6),
)
ro_opt.run()
# Internally: resonator_spectroscopy(bindings=session.bindings, ...)
# Uses bindings.readout.drive_out for the resonator sweep
```

---

### A.6 Readout GE Discrimination

**Before**:
```python
ge = ReadoutGEDiscrimination(
    session,
    n_samples=250_000,
    ro_el="resonator",        # HARDCODED or from attr
    r180="x180",
)
ge.run()
# Writes: measureMacro._ro_disc_params["threshold"] = ...
# Patches: cal_store.set_discrimination("resonator", ...)
```

**After**:
```python
ge = ReadoutGEDiscrimination(
    session,
    bindings=session.bindings,
    n_samples=250_000,
    r180="x180",
)
ge.run()
# Writes: bindings.readout.discrimination["threshold"] = ...
# Patches: cal_store.set_discrimination("con1:analog_in:1", ...)
# measureMacro compat shim syncs if still in use
```

---

### A.7 Readout Butterfly Measurement

**Before**:
```python
bfly = ReadoutButterflyMeasurement(
    session,
    n_shots=50_000,
    r180="x180",
)
bfly.run()
# Reads: measureMacro._ro_disc_params (threshold, angle)
# Writes: measureMacro._ro_quality_params (confusion_matrix, t01, t10)
# Patches: cal_store.set_readout_quality("resonator", ...)
```

**After**:
```python
bfly = ReadoutButterflyMeasurement(
    session,
    bindings=session.bindings,
    n_shots=50_000,
    r180="x180",
)
bfly.run()
# Reads: bindings.readout.discrimination (threshold, angle)
# Writes: bindings.readout.quality (confusion_matrix, t01, t10)
# Patches: cal_store.set_readout_quality("con1:analog_in:1", ...)
```

---

## 8. Appendix B: Glossary

| Term | Definition |
|------|-----------|
| **ChannelRef** | Immutable identifier for a physical hardware port: `(device, port_type, port_number)` |
| **canonical_id** | String representation of a `ChannelRef`, e.g. `"con1:analog_out:3"`. Used as the primary key for calibration storage |
| **OutputBinding** | A bound control output: `ChannelRef` + IF freq + LO freq + gain + operations |
| **InputBinding** | A bound acquisition input: `ChannelRef` + ToF + integration weights |
| **ReadoutBinding** | Paired `OutputBinding` + `InputBinding` for a complete readout channel, plus all DSP state (discrimination, quality) |
| **ExperimentBindings** | Named collection of bindings (`qubit`, `readout`, `storage`, etc.) passed to experiments |
| **AliasMap** | `dict[str, ChannelRef]` mapping human-friendly names to physical ports |
| **alias_index** | Stored in `CalibrationData` — maps alias strings to `canonical_id` strings |
| **ConfigBuilder** | Synthesizes QM config element dicts from bindings at compile time |
| **measure_with_binding** | Replacement for `measureMacro.measure()` that takes a `ReadoutBinding` |
| **CompilationAdapter** | (Phase 1 compat) Context manager that configures `measureMacro` from bindings |
| **physical_id** | Shorthand for `ChannelRef.canonical_id` on a `ReadoutBinding` |
