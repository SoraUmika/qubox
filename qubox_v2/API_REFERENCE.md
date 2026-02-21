# qubox_v2 — API Reference & Architecture Guide

> **Version 3.0.0** · Modular architecture refactoring
> Target: Python ≥ 3.10 · QM OPX+ / Octave (SDK 1.x) · Pydantic v2

---

## Table of Contents

1. [Package Overview](#1-package-overview)
2. [Directory Layout](#2-directory-layout)
3. [Layer-by-Layer Reference](#3-layer-by-layer-reference)
   - [3.1 core/](#31-core)
   - [3.2 calibration/ (NEW)](#32-calibration)
   - [3.3 hardware/](#33-hardware)
   - [3.4 devices/](#34-devices)
   - [3.5 pulses/](#35-pulses)
   - [3.6 programs/](#36-programs)
   - [3.7 experiments/](#37-experiments)
   - [3.8 analysis/](#38-analysis)
   - [3.9 simulation/](#39-simulation)
   - [3.10 gates/](#310-gates)
   - [3.11 compile/](#311-compile)
   - [3.12 optimization/](#312-optimization)
   - [3.13 tools/](#313-tools)
   - [3.14 gui/](#314-gui)
   - [3.15 compat/](#315-compat)
4. [Migration Guide](#4-migration-guide)
5. [Quick-Start Examples](#5-quick-start-examples)
6. [Design Principles](#6-design-principles)

---

## 1. Package Overview

`qubox_v2` is a restructured, modular Python package for controlling
superconducting circuit QED experiments on the Quantum Machines (QM)
OPX+ platform.  It replaces the earlier flat `qubox` package which
had grown to ~70 files with several >2 000-line monolithic classes.

### Key improvements over `qubox`

| Area | Before (`qubox`) | After (`qubox_v2` v3) |
|------|-------------------|-----------------------|
| **Config** | Raw `dict` ↔ JSON | Pydantic v2 typed models |
| **Hardware** | `QuaProgramManager` (2 052 lines) | 4 focused classes: `ConfigEngine`, `HardwareController`, `ProgramRunner`, `QueueManager` |
| **Experiments** | `cQED_Experiment` (5 197 lines) | `ExperimentBase` ABC + per-experiment classes + `SessionManager` |
| **Calibration** | Ad-hoc per-experiment | `CalibrationStore` (JSON-backed, typed, with snapshots) |
| **Pulses** | `PulseOperationManager` only | `PulseRegistry` facade + `IntegrationWeightManager` + waveform factories |
| **Programs** | Monolithic `cQED_programs.py` | Category modules (spectroscopy, time_domain, calibration, readout, cavity, tomography) |
| **Results** | Raw dicts | `RunResult` + `AnalysisResult` + `FitResult` dataclasses |
| **Errors** | Bare `Exception` / `print` | `QuboxError` hierarchy |
| **Logging** | Ad-hoc per-file | Unified `core.logging` |
| **Interfaces** | Implicit duck typing | `typing.Protocol` contracts |
| **Packaging** | `setup.py` | Modern `pyproject.toml` with optional extras |
| **Compatibility** | — | `compat.legacy` import shim |

---

## 2. Directory Layout

```
qubox_v2/
├── __init__.py              # Package root (v3.0.0), auto-configures logging
├── pyproject.toml           # Modern packaging (pip install -e .)
│
├── core/                    # ── Layer 0: Shared foundations ──
│   ├── __init__.py          # Re-exports errors, logging, config, protocols, utils
│   ├── config.py            # Pydantic v2 models: HardwareConfig, ControllerConfig, …
│   ├── errors.py            # QuboxError → ConfigError, ConnectionError, JobError, …
│   ├── logging.py           # configure_global_logging(), get_logger(), context managers
│   ├── protocols.py         # @runtime_checkable Protocol interfaces
│   ├── types.py             # Shared enums: ExecMode, DemodMode, PulseType, WaveformType
│   └── utils.py             # Shared helpers: deep_merge, json_dump, with_retries, …
│
├── calibration/             # ── Layer 1: Calibration persistence (NEW) ──
│   ├── __init__.py          # Re-exports CalibrationStore, models
│   ├── models.py            # Pydantic v2 models (QubitCalibration, ReadoutCalibration, …)
│   ├── store.py             # CalibrationStore: JSON-backed typed storage with snapshots
│   └── history.py           # Timestamped calibration snapshots
│
├── hardware/                # ── Layer 2: QM hardware interaction ──
│   ├── __init__.py          # Re-exports all hardware classes
│   ├── config_engine.py     # ConfigEngine: JSON ↔ QM config dict builder
│   ├── controller.py        # HardwareController: connection, LO routing, Octave
│   ├── program_runner.py    # ProgramRunner: run, simulate, ExecMode, RunResult
│   └── queue_manager.py     # QueueManager: submit, batch, progress bars
│
├── devices/                 # ── Layer 3: External instruments ──
│   ├── __init__.py
│   └── device_manager.py    # DeviceManager, DeviceSpec, DeviceHandle (QCoDeS, InstrumentServer)
│
├── pulses/                  # ── Layer 4: Pulse operation management ──
│   ├── __init__.py          # Exports PulseOperationManager, PulseRegistry
│   ├── manager.py           # PulseOperationManager (2 362 lines, dual perm/volatile stores)
│   ├── models.py            # WaveformSpec, PulseSpec, ResourceStore dataclasses
│   ├── pulse_registry.py    # PulseRegistry: simplified facade over POM (NEW)
│   ├── integration_weights.py # IntegrationWeightManager (NEW)
│   └── waveforms.py         # Waveform factory functions (NEW)
│
├── programs/                # ── Layer 5: QUA program factories ──
│   ├── __init__.py          # Re-exports all + category sub-modules
│   ├── cQED_programs.py     # All QUA program generators (monolith, preserved)
│   ├── spectroscopy.py      # Category: resonator/qubit/storage spectroscopy (NEW)
│   ├── time_domain.py       # Category: Rabi, T1, T2, chevrons (NEW)
│   ├── calibration.py       # Category: AllXY, DRAG, RB (NEW)
│   ├── readout.py           # Category: IQ blobs, butterfly, discrimination (NEW)
│   ├── cavity.py            # Category: Wigner, chi Ramsey, Fock-resolved (NEW)
│   ├── tomography.py        # Category: qubit/Fock state tomography (NEW)
│   └── macros/
│       ├── __init__.py
│       ├── measure.py       # measureMacro: readout + demod + streaming
│       └── sequence.py      # sequenceMacros: gate sequence execution
│
├── experiments/             # ── Layer 6: Experiment orchestration ──
│   ├── __init__.py          # Exports all experiment classes
│   ├── base.py              # ExperimentRunner: generic experiment base class
│   ├── experiment_base.py   # ExperimentBase: modular experiment ABC (NEW)
│   ├── session.py           # SessionManager: service container (NEW)
│   ├── result.py            # AnalysisResult, FitResult dataclasses (NEW)
│   ├── config_builder.py    # ConfigBuilder: fluent hardware config construction
│   ├── gates_legacy.py      # Legacy gate dataclasses (Gate, Displacement, SNAP, Measure)
│   ├── legacy_experiment.py # cQED_Experiment: full legacy experiment class (preserved)
│   ├── spectroscopy/        # ResonatorSpectroscopy, QubitSpectroscopy, … (NEW)
│   ├── time_domain/         # TemporalRabi, PowerRabi, T1, T2Ramsey, T2Echo, … (NEW)
│   ├── calibration/         # AllXY, DRAGCalibration, RB, ReadoutDiscrimination, … (NEW)
│   ├── cavity/              # StorageSpectroscopy, FockResolved, ChiRamsey, … (NEW)
│   ├── tomography/          # QubitStateTomography, WignerTomography, … (NEW)
│   └── spa/                 # SPAFluxOptimization, SPAPumpFreqOptimization (NEW)
│
├── analysis/                # ── Layer 7: Data analysis & fitting ──
│   ├── __init__.py
│   ├── algorithms.py        # PeakObjective, lock_to_peak, scout_windows, …
│   ├── analysis_tools.py    # two_state_discriminator, IQ normalisation, probabilities
│   ├── cQED_attributes.py   # cQED_attributes: typed experiment parameters
│   ├── cQED_models.py       # Physics models (Jaynes-Cummings, transmon, …)
│   ├── cQED_plottings.py    # Standard cQED visualisation helpers
│   ├── fitting.py           # Curve fitting (Lorentzian, Rabi, T1, T2, …)
│   ├── metrics.py           # butterfly_metrics, fidelity metrics
│   ├── models.py            # Data model base classes
│   ├── output.py            # Output dict wrapper
│   ├── plotting.py          # Generic matplotlib helpers
│   ├── post_process.py      # proc_default, standard post-processing pipelines
│   ├── post_selection.py    # PostSelectionConfig, heralded measurement filtering
│   └── pulseOp.py           # PulseOp: waveform ↔ FFT analysis utilities
│
├── simulation/              # ── Layer 7: QuTiP / Hamiltonian simulation ──
│   ├── __init__.py
│   ├── cQED.py              # cQED_Simulation: full system simulation
│   ├── drive_builder.py     # Drive Hamiltonian construction
│   ├── hamiltonian_builder.py  # Static Hamiltonian builder (transmon + cavity)
│   └── solver.py            # Time-domain ODE solver wrappers
│
├── gates/                   # ── Layer 8: Gate abstraction framework ──
│   ├── __init__.py          # Exports Gate, GateModel, GateHardware, GateSequence
│   ├── gate.py              # Gate: model ↔ hardware bridge
│   ├── model_base.py        # GateModel ABC
│   ├── hardware_base.py     # GateHardware ABC
│   ├── sequence.py          # GateSequence: ordered gate composition
│   ├── fidelity.py          # Fidelity metrics (process, average gate)
│   ├── noise.py             # Noise channel modelling
│   ├── liouville.py         # Liouville superoperator utilities
│   ├── free_evolution.py    # Free-evolution (idle) gate
│   ├── cache.py             # Gate result caching
│   ├── contexts.py          # Gate execution contexts
│   ├── hash_utils.py        # Deterministic hashing for gate parameters
│   ├── models/              # Concrete gate models
│   │   ├── common.py, displacement.py, qubit_rotation.py, snap.py, sqr.py
│   └── hardware/            # Hardware implementations
│       ├── displacement.py, qubit_rotation.py, snap.py, sqr.py
│
├── compile/                 # ── Layer 9: Gate-sequence → pulse compilation ──
│   ├── __init__.py
│   ├── api.py               # High-level compile() entry point
│   ├── ansatz.py            # Ansatz parametrisations
│   ├── evaluators.py        # Cost-function evaluators
│   ├── gpu_accelerators.py  # GPU-accelerated batch evaluation
│   ├── gpu_utils.py         # CuPy / CUDA helpers
│   ├── objectives.py        # Optimisation objectives (fidelity, leakage, …)
│   ├── optimizers.py        # Optimiser wrappers (scipy, custom)
│   ├── param_space.py       # Parameter space definitions
│   ├── structure_search.py  # Gate-sequence structure search
│   └── templates.py         # Pre-built compilation templates
│
├── optimization/            # ── Smooth & stochastic optimisation ──
│   ├── __init__.py
│   ├── optimization.py      # Core optimisation loop
│   ├── smooth_opt.py        # Gradient-based smooth optimisation
│   └── stochastic_opt.py    # Stochastic / evolutionary optimisation
│
├── tools/                   # ── Waveform generators & utilities ──
│   ├── __init__.py
│   ├── generators.py        # Pulse envelope generators
│   └── waveforms.py         # Waveform construction helpers
│
├── gui/                     # ── Interactive GUI (optional, PyQt5) ──
│   ├── __init__.py
│   └── program_gui.py       # ProgramRunnerGUI: live parameter sweep + plotting
│
└── compat/                  # ── Backward compatibility ──
    ├── __init__.py          # Import shim: installs sys.meta_path finder
    └── legacy.py            # Convenience entry: `import qubox_v2.compat.legacy`
```

**Total: ~120 Python files across 16 sub-packages.**

---

## 3. Layer-by-Layer Reference

### 3.1 core/

The **foundation layer** — every other package depends on `core/` but
`core/` depends on nothing else in `qubox_v2`.

#### `core.errors`

```python
class QuboxError(Exception): ...      # Base for all qubox errors
class ConfigError(QuboxError): ...    # Bad/missing configuration
class ConnectionError(QuboxError): ...# Hardware connection failure
class JobError(QuboxError): ...       # QM job failure
class DeviceError(QuboxError): ...    # External device error
class PulseError(QuboxError): ...     # Pulse definition error
class CalibrationError(QuboxError):...# Calibration failure
```

#### `core.config` — Pydantic v2 Models

```python
class HardwareConfig(BaseModel):
    """Top-level hardware configuration (replaces raw dict).

    Load / save:
        cfg = HardwareConfig.from_json("hardware.json")
        cfg.save_json("hardware_out.json")
        qm_dict = cfg.to_qm_dict()   # ready for QuantumMachinesManager
    """
    version: str
    controllers: dict[str, ControllerConfig]
    octaves: dict[str, OctaveConfig]
    elements: dict[str, ElementConfig]
    qubox_extras: QuboxExtras          # external LOs, octave links, …

class ControllerConfig(BaseModel):
    analog_outputs: dict[int, AnalogOutput]
    digital_outputs: dict[int, DigitalOutput]
    analog_inputs: dict[int, AnalogInput]

class OctaveConfig(BaseModel):
    connectivity: str
    RF_outputs: dict[int, OctaveRFOutput]
    RF_inputs: dict[int, OctaveRFInput]

class QuboxExtras(BaseModel):
    external_los: dict[str, ExternalLOEntry]
    octave_links: dict[str, OctaveLink]
```

#### `core.protocols` — Interface Contracts

```python
@runtime_checkable
class HardwareControllerP(Protocol):
    def open_qm(self) -> Any: ...
    def close(self) -> None: ...
    def apply_changes(self) -> None: ...

@runtime_checkable
class ProgramRunnerP(Protocol):
    def run_program(self, program, *, mode, **kw) -> RunResult: ...
    def simulate(self, program, *, duration, **kw) -> Any: ...

@runtime_checkable
class ConfigEngineP(Protocol):
    def build_qm_config(self) -> dict: ...
    def patch_hardware(self, path, value) -> None: ...

@runtime_checkable
class Experiment(Protocol):
    def run(self, program, **kw) -> RunResult: ...
    def close(self) -> None: ...
```

#### `core.logging`

```python
configure_global_logging(level="INFO")  # Sets up qubox + qm loggers
logger = get_logger(__name__)           # Returns qubox.module logger

with temporarily_set_levels([logger], logging.DEBUG):
    ...  # Verbose for this block only

with temporarily_disable([noisy_logger]):
    ...  # Silence specific loggers
```

#### `core.utils`

| Function | Description |
|----------|-------------|
| `deep_merge(base, overlay)` | Recursive dict merge |
| `json_dump(obj, path)` | JSON serialise with numpy support |
| `numeric_keys_to_ints(d)` | Convert `"1"` → `1` in dict keys |
| `with_retries(fn, n, delay)` | Retry with exponential backoff |
| `require(condition, msg)` | Assert-like with custom error |

---

### 3.2 calibration/ (NEW)

JSON-backed typed calibration persistence with snapshot history.

#### `calibration.CalibrationStore`

```python
from qubox_v2.calibration import CalibrationStore

store = CalibrationStore("./calibration_data")

# Store typed calibration values
store.set("qubit_freq", 5.55e9)
store.set("readout_fidelity", 0.97)
store.set("T1", 25e-6)

# Retrieve with type safety
freq = store.get("qubit_freq")           # Returns float
all_data = store.snapshot()              # Full state dict

# History / snapshots
store.save_snapshot("after_cooldown")
store.list_snapshots()
store.restore_snapshot("after_cooldown")
```

#### `calibration.models` — Pydantic v2 Calibration Models

```python
from qubox_v2.calibration.models import QubitCalibration, ReadoutCalibration

qubit_cal = QubitCalibration(
    frequency=5.55e9,
    anharmonicity=-220e6,
    T1=25e-6,
    T2_ramsey=12e-6,
    pi_amplitude=0.45,
    pi_length=40,
)
qubit_cal.save_json("qubit_cal.json")
```

#### `calibration.history`

```python
from qubox_v2.calibration.history import CalibrationHistory

history = CalibrationHistory("./cal_history")
history.record(qubit_cal, tag="post_cooldown")
history.list_entries()
```

---

### 3.3 hardware/

The **QPM split** — the 2 052-line `QuaProgramManager` is decomposed into
four focused classes.

#### `hardware.ConfigEngine`

```python
engine = ConfigEngine(hardware_json="hardware.json", pulse_json="pulses.json")

qm_config = engine.build_qm_config()    # Full QM-compatible dict
engine.patch_hardware("elements.qubit.intermediate_frequency", 50e6)
engine.merge_pulses(pulse_dict)
engine.save_hardware("hardware_out.json")
```

**Config layering:** `hardware_base → pulse_overlay → element_ops_overlay → runtime_overrides → build_qm_config()`

#### `hardware.HardwareController`

```python
hw = HardwareController(config_engine=engine, qop_ip="10.0.0.1")
qm = hw.open_qm()

# LO management (with external LO routing for OctaveLOSource.LO1–LO5)
hw.set_element_lo("qubit", 5.5e9)       # Updates Octave or external LO
hw.set_element_fq("qubit", 5.55e9)      # Adjusts IF to hit target freq
hw.set_octave_gain("qubit", 10)          # dBm
hw.calibrate_element("qubit")            # Octave mixer calibration

lo, src = hw.get_element_lo("qubit")     # Returns (freq, "internal"|device_name)
```

**External LO routing:**
- Reads `qubox_extras.external_los` from config
- Maps `OctaveLOSource.LO1–LO5` to physical SignalCore devices
- Automatically routes `set_element_lo()` to correct device

#### `hardware.ProgramRunner`

```python
runner = ProgramRunner(controller=hw)

# Run on hardware
result: RunResult = runner.run_program(program, mode=ExecMode.RUN, n_avg=1000)
print(result.I, result.Q)                # Fetched data

# Simulate
sim = runner.simulate(program, duration=10_000, plot=True)
```

**`ExecMode` enum:** `RUN`, `SIMULATE`, `CONTINUOUS_WAVE`  
**`RunResult` dataclass:** `job`, `data`, `I`, `Q`, `timestamps`, `duration`

#### `hardware.QueueManager`

```python
queue = QueueManager(controller=hw)

# Batch submission with progress bar
results = queue.run_many(programs, labels=["spec", "rabi", "T1"])

# Fine-grained control
job_id = queue.submit(program)
queue.count()
queue.pending_jobs()
```

---

### 3.4 devices/

#### `devices.DeviceManager`

Manages external instruments (SignalCore LOs, OctoDac, SPA pump, etc.)
via QCoDeS or InstrumentServer backends.

```python
dm = DeviceManager("devices.json", autoload=True)

# Access a device
lo = dm["signal_core_1"]                 # DeviceHandle
lo.set("frequency", 6e9)
lo.set("power", 10)

# Ramp with safety limits
dm.ramp("octodac_ch1", target=0.5, rate=0.01)

# Snapshot all device states
snap = dm.snapshot()
dm.close_all()
```

---

### 3.5 pulses/

#### `pulses.PulseOperationManager`

The 2 362-line pulse manager with dual permanent/volatile stores.

```python
pom = PulseOperationManager(config_engine)

# Register a pulse
pom.register("pi_pulse", element="qubit", type="gaussian",
             amplitude=0.5, sigma=20, length=100)

# Volatile (session-only) pulses
pom.register_volatile("temp_pulse", ...)

# Burn to hardware config
pom.burn(include_volatile=True)

# Save / load
pom.save("pulses.json")
pom.load("pulses.json")
```

#### `pulses.models`

```python
@dataclass
class WaveformSpec:
    name: str
    samples: np.ndarray | list[float]
    wf_type: str = "arbitrary"

@dataclass
class PulseSpec:
    name: str
    element: str
    length: int
    waveforms: dict[str, WaveformSpec]
    digital_marker: str | None = None

class ResourceStore:
    """In-memory pulse/waveform/digital-marker store."""
    def add(self, name, spec): ...
    def get(self, name): ...
    def remove(self, name): ...
    def keys(self) -> list[str]: ...
```

#### `pulses.PulseRegistry` (NEW)

Simplified facade over `PulseOperationManager` for common operations.

```python
from qubox_v2.pulses import PulseRegistry

registry = PulseRegistry(pulse_op_manager)

# Register pulses with a clean API
registry.register("x180", element="qubit", type="gaussian",
                   amplitude=0.45, sigma=10, length=40)

# Volatile (session-only) pulses
registry.register_volatile("temp_probe", ...)

# Query
registry.list_pulses()
registry.get("x180")

# Burn all to hardware config
registry.burn()
```

#### `pulses.IntegrationWeightManager` (NEW)

```python
from qubox_v2.pulses.integration_weights import IntegrationWeightManager

iwm = IntegrationWeightManager(config_engine)
iwm.set_optimal_weights("readout", cos_weights, sin_weights)
iwm.set_constant_weights("readout", length=1000)
```

#### `pulses.waveforms` (NEW)

```python
from qubox_v2.pulses.waveforms import gaussian, drag, flat_top, cosine

wf = gaussian(amplitude=0.5, sigma=10, length=40)
wf = drag(amplitude=0.5, sigma=10, length=40, delta=-220e6, alpha=0.5)
wf = flat_top(amplitude=0.3, rise=8, flat=100, fall=8)
```

---

### 3.6 programs/

QUA program factories — pure functions that build `qua.program` objects.
Now organized into category modules for cleaner imports (v3).

```python
# Category-based import (preferred in v3)
from qubox_v2.programs.spectroscopy import resonator_spectroscopy, qubit_spectroscopy
from qubox_v2.programs.time_domain import temporal_rabi, T1_relaxation, T2_ramsey
from qubox_v2.programs.calibration import all_xy, randomized_benchmarking
from qubox_v2.programs.readout import iq_blobs, readout_butterfly_measurement
from qubox_v2.programs.cavity import storage_chi_ramsey, fock_resolved_spectroscopy
from qubox_v2.programs.tomography import qubit_state_tomography

# Legacy flat import (still works)
from qubox_v2.programs.cQED_programs import resonator_spectroscopy  # 40+ factories
```

**Category modules** (re-export facades over `cQED_programs.py`):

| Module | Programs |
|--------|----------|
| `spectroscopy` | `readout_trace`, `resonator_spectroscopy`, `resonator_power_spectroscopy`, `resonator_spectroscopy_x180`, `qubit_spectroscopy`, `qubit_spectroscopy_ef`, `storage_spectroscopy`, `num_splitting_spectroscopy` |
| `time_domain` | `temporal_rabi`, `power_rabi`, `time_rabi_chevron`, `power_rabi_chevron`, `ramsey_chevron`, `T1_relaxation`, `T2_ramsey`, `T2_echo`, `ac_stark_shift`, `residual_photon_ramsey` |
| `calibration` | `all_xy`, `randomized_benchmarking`, `drag_calibration_YALE`, `drag_calibration_GOOGLE`, `sequential_qb_rotations`, `qubit_pulse_train`, `qubit_pulse_train_legacy` |
| `readout` | `iq_blobs`, `readout_ge_raw_trace`, `readout_ge_integrated_trace`, `readout_core_efficiency_calibration`, `readout_butterfly_measurement`, `readout_leakage_benchmarking`, `qubit_reset_benchmark`, `active_qubit_reset_benchmark` |
| `cavity` | `storage_wigner_tomography`, `storage_chi_ramsey`, `storage_ramsey`, `phase_evolution_prog`, `fock_resolved_spectroscopy`, `fock_resolved_T1_relaxation`, `fock_resolved_power_rabi`, `fock_resolved_qb_ramsey`, `sel_r180_calibration0`, `SPA_flux_optimization`, `continuous_wave` |
| `tomography` | `qubit_state_tomography`, `fock_resolved_state_tomography`, `sequential_simulation` |

**Macros:**

```python
from qubox_v2.programs.macros import measureMacro, sequenceMacros

# measureMacro: handles readout, demod, streaming
# sequenceMacros: applies gate sequences inside QUA
```

---

### 3.7 experiments/

#### `experiments.SessionManager` (NEW in v3)

Central service container that replaces the god-object wiring of `cQED_Experiment`.

```python
from qubox_v2.experiments.session import SessionManager

with SessionManager("./cooldown_2025", qop_ip="10.0.0.1") as session:
    # Access all services
    session.config_engine    # ConfigEngine
    session.hardware         # HardwareController
    session.runner           # ProgramRunner
    session.queue            # QueueManager
    session.pulse_mgr        # PulseOperationManager
    session.pulses           # PulseRegistry (simplified facade)
    session.calibration      # CalibrationStore
    session.devices          # DeviceManager

    # Run an experiment class
    from qubox_v2.experiments.spectroscopy import ResonatorSpectroscopy
    spec = ResonatorSpectroscopy(session)
    result = spec.run(freq_start=6.8e9, freq_stop=7.2e9, n_avg=1000)
    analysis = spec.analyze(result)
    spec.plot(analysis)
```

#### `experiments.ExperimentBase` (NEW in v3)

Abstract base class for modular experiment classes.

```python
from qubox_v2.experiments.experiment_base import ExperimentBase

class MyExperiment(ExperimentBase):
    def build_program(self, **params) -> qua.program:
        ...  # Build QUA program
    def run(self, **params) -> RunResult:
        ...  # Execute on hardware
    def analyze(self, result, **kw) -> AnalysisResult:
        ...  # Fit and extract metrics
    def plot(self, result, **kw):
        ...  # Visualize
```

#### `experiments.result` (NEW in v3)

```python
from qubox_v2.experiments.result import RunResult, AnalysisResult, FitResult

# RunResult — from hardware.program_runner (re-exported)
# FitResult — model_name, params, uncertainties, r_squared, residuals
# AnalysisResult — data, fit, fits, metrics, source RunResult, metadata
analysis = AnalysisResult.from_run(run_result, fit=fit_result, metrics={"fidelity": 0.99})
```

#### Experiment class hierarchy (NEW in v3)

| Subdirectory | Classes |
|--------------|---------|
| `spectroscopy/` | `ResonatorSpectroscopy`, `ResonatorPowerSpectroscopy`, `QubitSpectroscopy`, `QubitSpectroscopyEF` |
| `time_domain/` | `TemporalRabi`, `PowerRabi`, `RabiChevron`, `RamseyChevron`, `T1Relaxation`, `T2Ramsey`, `T2Echo` |
| `calibration/` | `AllXY`, `DRAGCalibration`, `RandomizedBenchmarking`, `ReadoutDiscrimination`, `ReadoutButterfly`, `WeightsOptimization`, `ActiveReset`, `LeakageBenchmarking` |
| `cavity/` | `StorageSpectroscopy`, `NumSplitting`, `ChiRamsey`, `FockResolvedSpectroscopy`, `FockResolvedRamsey` |
| `tomography/` | `QubitStateTomography`, `FockStateTomography`, `WignerTomography`, `SNAPOptimization` |
| `spa/` | `SPAFluxOptimization`, `SPAPumpFreqOptimization` |

#### `experiments.ExperimentRunner`

Clean base class extracted from the legacy monolith (v2).

```python
from qubox_v2.experiments import ExperimentRunner

with ExperimentRunner("./my_experiment") as exp:
    exp.register_pulse("pi", element="qubit", ...)
    exp.burn_pulses()

    result = exp.run(my_program)
    exp.save_output(result.data, tag="spectroscopy")
```

#### `experiments.legacy_experiment` — `cQED_Experiment`

The full 5 197-line legacy class, preserved with updated imports.
Contains 60+ experiment methods (see legacy docs).

---

### 3.8 analysis/

Data analysis, fitting, models, and visualisation.

| Module | Key Exports |
|--------|-------------|
| `output.py` | `Output` — dict-like data container |
| `fitting.py` | Lorentzian, Rabi, T1, T2, exponential fits |
| `algorithms.py` | `PeakObjective`, `lock_to_peak_3pt`, `scout_windows`, `refine_around` |
| `analysis_tools.py` | `two_state_discriminator`, `apply_norm_IQ`, `compute_probabilities` |
| `cQED_attributes.py` | `cQED_attributes` — typed experiment parameters |
| `cQED_models.py` | Physics models (Jaynes-Cummings, dispersive shift, …) |
| `cQED_plottings.py` | Standard cQED figure templates |
| `metrics.py` | `butterfly_metrics`, fidelity calculations |
| `post_process.py` | `proc_default` — standard data post-processing |
| `post_selection.py` | `PostSelectionConfig` — heralded measurement filtering |
| `pulseOp.py` | `PulseOp` — waveform ↔ FFT analysis |
| `plotting.py` | Generic matplotlib utilities |

---

### 3.9 simulation/

QuTiP-based Hamiltonian simulation of the cQED system.

```python
from qubox_v2.simulation.cQED import cQED_Simulation

sim = cQED_Simulation(
    N_qubit=3, N_cavity=10,
    omega_q=5.5e9, omega_c=7.0e9,
    chi=-1.5e6, kappa=50e3,
)
result = sim.run(tlist, gates=[...])
sim.plot_populations()
```

| Module | Description |
|--------|-------------|
| `cQED.py` | `cQED_Simulation` — full system simulation |
| `hamiltonian_builder.py` | Builds static H₀ (transmon + cavity) |
| `drive_builder.py` | Constructs time-dependent drive terms |
| `solver.py` | `mesolve` / `sesolve` wrappers with progress |

---

### 3.10 gates/

Model ↔ hardware gate abstraction with composable sequences.

```python
from qubox_v2.gates import Gate, GateSequence
from qubox_v2.gates.models.displacement import DisplacementModel
from qubox_v2.gates.hardware.displacement import DisplacementHardware

# Create a gate with both model and hardware
disp = Gate(
    model=DisplacementModel(alpha=1.0+0.5j),
    hardware=DisplacementHardware(element="storage", ...)
)

# Compose a sequence
seq = GateSequence([disp, snap_gate, measure_gate])
fidelity = seq.compute_fidelity(target_state)
```

**Available gates:** Displacement, SNAP, Qubit Rotation, SQR (selective qubit rotation),
Free Evolution.

---

### 3.11 compile/

Numerical gate-sequence → pulse compilation / optimisation.

```python
from qubox_v2.compile.api import compile_sequence

result = compile_sequence(
    target_unitary=U_target,
    gate_types=["displacement", "snap"],
    max_depth=6,
    optimizer="scipy-COBYLA",
)
print(result.fidelity, result.parameters)
```

| Module | Description |
|--------|-------------|
| `api.py` | `compile_sequence()` — high-level entry point |
| `ansatz.py` | Gate-sequence ansatz parametrisations |
| `evaluators.py` | Cost-function evaluators |
| `objectives.py` | Fidelity, leakage, smoothness objectives |
| `optimizers.py` | scipy, custom optimiser wrappers |
| `param_space.py` | Bounded parameter space definitions |
| `structure_search.py` | Automated gate-sequence structure search |
| `templates.py` | Pre-built compilation templates |
| `gpu_accelerators.py` | CuPy batch evaluation for GPU |
| `gpu_utils.py` | CUDA / CuPy helpers |

---

### 3.12 optimization/

General-purpose optimisation routines used by `compile/` and experiments.

| Module | Description |
|--------|-------------|
| `optimization.py` | Core optimisation loop with callbacks |
| `smooth_opt.py` | Gradient-based (L-BFGS-B, etc.) |
| `stochastic_opt.py` | Evolutionary / stochastic methods |

---

### 3.13 tools/

Waveform generators and numerical utilities.

| Module | Description |
|--------|-------------|
| `generators.py` | Gaussian, DRAG, flat-top, cosine envelopes |
| `waveforms.py` | Waveform construction, sampling, interpolation |

---

### 3.14 gui/

Optional interactive GUI (requires PyQt5 + pyqtgraph).

```python
from qubox_v2.gui.program_gui import ProgramRunnerGUI

gui = ProgramRunnerGUI(experiment_callable, param_specs={...})
gui.show()   # Opens live-update parameter sweep window
```

---

### 3.15 compat/

Backward-compatibility shim for legacy `qubox.*` imports.

```python
# Add once at the top of old notebooks:
import qubox_v2.compat.legacy

# Then old imports work transparently:
from qubox.program_manager import QuaProgramManager  # → qubox_v2.hardware
from qubox.cQED_experiments import cQED_Experiment    # → qubox_v2.experiments.legacy_experiment
```

**Redirect map:**

| Old import | New target |
|------------|-----------|
| `qubox.program_manager` | `qubox_v2.hardware` |
| `qubox.device_manager` | `qubox_v2.devices.device_manager` |
| `qubox.pulse_manager` | `qubox_v2.pulses.manager` |
| `qubox.cQED_experiments` | `qubox_v2.experiments.legacy_experiment` |
| `qubox.cQED_programs` | `qubox_v2.programs.cQED_programs` |
| `qubox.config_builder` | `qubox_v2.experiments.config_builder` |
| `qubox.gates_legacy` | `qubox_v2.experiments.gates_legacy` |
| `qubox.logging_config` | `qubox_v2.core.logging` |
| `qubox.analysis.*` | `qubox_v2.analysis.*` |
| `qubox.simulation.*` | `qubox_v2.simulation.*` |
| `qubox.compile.*` | `qubox_v2.compile.*` |
| `qubox.calibration.*` | `qubox_v2.calibration.*` |
| `qubox.programs.spectroscopy` | `qubox_v2.programs.spectroscopy` |
| `qubox.programs.time_domain` | `qubox_v2.programs.time_domain` |
| `qubox.programs.calibration` | `qubox_v2.programs.calibration` |
| `qubox.programs.readout` | `qubox_v2.programs.readout` |
| `qubox.programs.cavity` | `qubox_v2.programs.cavity` |
| `qubox.programs.tomography` | `qubox_v2.programs.tomography` |
| `qubox.experiments.session` | `qubox_v2.experiments.session` |
| `qubox.experiments.result` | `qubox_v2.experiments.result` |

---

## 4. Migration Guide

### Step 1 — Use the compatibility shim (zero-effort)

```python
import qubox_v2.compat.legacy
# All existing code works unchanged (with deprecation warnings)
```

### Step 2 — Update imports incrementally

Replace old flat imports:

```python
# OLD
from qubox.program_manager import QuaProgramManager
from qubox.cQED_experiments import cQED_Experiment
from qubox.pulse_manager import PulseOperationManager

# NEW
from qubox_v2.hardware import ConfigEngine, HardwareController, ProgramRunner
from qubox_v2.experiments.legacy_experiment import cQED_Experiment
from qubox_v2.pulses.manager import PulseOperationManager
```

### Step 3 — Use `SessionManager` + experiment classes (v3, recommended)

```python
from qubox_v2.experiments.session import SessionManager
from qubox_v2.experiments.spectroscopy import ResonatorSpectroscopy

with SessionManager("./cooldown_2025", qop_ip="10.0.0.1") as session:
    spec = ResonatorSpectroscopy(session)
    result = spec.run(freq_start=6.8e9, freq_stop=7.2e9, n_avg=1000)
    analysis = spec.analyze(result)
    spec.plot(analysis)
```

### Step 4 — Or use `ExperimentRunner` (v2 style)

```python
from qubox_v2.experiments import ExperimentRunner

class MyNewExperiment(ExperimentRunner):
    def run_spectroscopy(self, freqs, **kw):
        from qubox_v2.programs.spectroscopy import resonator_spectroscopy
        prog = resonator_spectroscopy(freqs, ...)
        return self.run(prog, **kw)
```

### Step 5 — Use typed config

```python
from qubox_v2.core.config import HardwareConfig

cfg = HardwareConfig.from_json("hardware.json")
cfg.elements["qubit"].intermediate_frequency = 50e6
cfg.save_json("hardware_updated.json")
```

---

## 5. Quick-Start Examples

### A. SessionManager + experiment classes (v3 recommended)

```python
from qubox_v2.experiments.session import SessionManager
from qubox_v2.experiments.time_domain import TemporalRabi, T1Relaxation

with SessionManager("./cooldown_2025", qop_ip="10.0.0.1") as session:
    # Run a Rabi experiment
    rabi = TemporalRabi(session)
    result = rabi.run(pulse="x180", t_start=16, t_stop=400, dt=4, n_avg=2000)
    analysis = rabi.analyze(result)
    rabi.plot(analysis)

    # Follow up with T1
    t1 = T1Relaxation(session)
    result = t1.run(delay_max=50_000, n_avg=5000)
    analysis = t1.analyze(result)
    print(f"T1 = {analysis.fit.params['T1']*1e6:.1f} us")
```

### B. Connect and run with ExperimentRunner (v2 style)

```python
from qubox_v2.experiments import ExperimentRunner

with ExperimentRunner("./experiments/cooldown_2025") as exp:
    # Register a pi pulse
    exp.register_pulse("x180", element="qubit",
                       type="gaussian", amplitude=0.45,
                       sigma=10, length=40)
    exp.burn_pulses()

    # Run a program
    from qubox_v2.programs.cQED_programs import T1_relaxation_prog
    prog = T1_relaxation_prog(delay_max=50_000, n_avg=5000)
    result = exp.run(prog)

    # Save
    exp.save_output(result.data, tag="T1")
```

### C. Use the hardware layer directly

```python
from qubox_v2.hardware import ConfigEngine, HardwareController, ProgramRunner

engine = ConfigEngine(hardware_json="hardware.json")
hw = HardwareController(config_engine=engine, qop_ip="10.0.0.1")
runner = ProgramRunner(controller=hw)

# Set external LO frequency
hw.set_element_lo("qubit", 5.5e9)

# Run
result = runner.run_program(my_program, mode="run")

hw.close()
```

### D. Batch experiments with queue

```python
from qubox_v2.hardware import QueueManager

queue = QueueManager(controller=hw)
results = queue.run_many(
    [prog1, prog2, prog3],
    labels=["spec", "rabi", "T1"],
)
for label, result in zip(["spec", "rabi", "T1"], results):
    print(f"{label}: {result.duration:.1f}s")
```

### E. Gate compilation

```python
from qubox_v2.compile.api import compile_sequence
import numpy as np

# Target: |0⟩ → |1⟩ Fock state
result = compile_sequence(
    target_unitary=np.array([[0, 1], [1, 0]]),  # simplified
    gate_types=["displacement", "snap"],
    max_depth=4,
)
print(f"Fidelity: {result.fidelity:.6f}")
print(f"Gates: {result.parameters}")
```

---

## 6. Design Principles

1. **Single Responsibility** — Each class does one thing well.
   ConfigEngine builds configs; HardwareController manages connections;
   ProgramRunner executes programs.

2. **Dependency Inversion** — Upper layers depend on `Protocol`
   interfaces, not concrete classes.  Swap implementations for testing.

3. **Layered Architecture** — `core → hardware → devices → pulses →
   programs → experiments`.  No circular imports.

4. **Typed Configuration** — Pydantic v2 models catch errors at
   load time, not at hardware-submission time.

5. **Error Hierarchy** — `QuboxError` subclasses give callers
   fine-grained `try/except` control.

6. **Backward Compatibility** — The `compat` shim lets legacy code
   run unchanged while migration proceeds incrementally.

7. **Composable Gates** — Model (physics) and Hardware (pulses)
   are separate concerns combined through the `Gate` bridge.

8. **Progressive Disclosure** — `SessionManager` hides complexity
   for common workflows; power users access lower layers directly.

9. **Calibration Persistence** — `CalibrationStore` provides typed,
   JSON-backed storage with snapshot history for reproducibility.

10. **Structured Results** — `RunResult`, `AnalysisResult`, and
    `FitResult` provide consistent, typed containers for experiment data.

---

*Generated for qubox_v2 v3.0.0 — Quantum Circuits Group*
