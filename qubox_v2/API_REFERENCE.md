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
6. [Recipes](#6-recipes)
7. [Design Principles](#7-design-principles)

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

Typed, versioned calibration data with JSON persistence and snapshot history.

**Constructor:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str \| Path` | *(required)* | Path to calibration JSON file. Created with defaults if it does not exist. |
| `auto_save` | `bool` | `False` | If `True`, every mutating method automatically writes to disk. |

**Persistence behaviour:**

- On construction, if `path` does not exist the file is created immediately
  with default `CalibrationData` (version 3.0.0). The parent directory is
  created automatically (`parents=True`).
- All disk writes use **atomic write** (temp file + `os.replace`) so a crash
  mid-write never leaves a corrupt JSON file.
- With `auto_save=False` (the default), call `store.save()` explicitly or
  rely on `SessionManager` context-manager cleanup (`with SessionManager(...) as s:`
  calls `s.calibration.save()` on exit).
- With `auto_save=True`, every `set_*()` call writes to disk immediately.

```python
from qubox_v2.calibration import CalibrationStore

# Path used by SessionManager: <experiment_path>/config/calibration.json
store = CalibrationStore("./experiment/config/calibration.json", auto_save=False)

# Readout discrimination
store.set_discrimination("resonator", threshold=0.003, angle=1.23,
                         mu_g=[0.0, 0.0], mu_e=[0.01, 0.0],
                         sigma_g=0.001, sigma_e=0.001, fidelity=0.97)
disc = store.get_discrimination("resonator")  # -> DiscriminationParams

# Readout quality (butterfly measurement)
store.set_readout_quality("resonator", F=0.95, Q=0.98, V=0.90)
rq = store.get_readout_quality("resonator")   # -> ReadoutQuality

# Element frequencies
store.set_frequencies("qubit", lo_freq=5.5e9, if_freq=50e6,
                      qubit_freq=5.55e9, chi=-1.5e6)
freqs = store.get_frequencies("qubit")        # -> ElementFrequencies

# Coherence times
store.set_coherence("qubit", T1=25e-6, T2_ramsey=12e-6, T2_echo=30e-6)
coh = store.get_coherence("qubit")            # -> CoherenceParams

# Pulse calibrations
store.set_pulse_calibration("x180", amplitude=0.45, element="qubit",
                            drag_coeff=0.3)
pcal = store.get_pulse_calibration("x180")    # -> PulseCalibration

# Pulse-train error analysis
store.set_pulse_train_result("qubit", pt_result)
pt = store.get_pulse_train_result("qubit")    # -> PulseTrainResult

# Fock SQR calibrations
store.set_fock_sqr_calibrations("qubit", [cal_n0, cal_n1])
sqr = store.get_fock_sqr_calibrations("qubit")# -> list[FockSQRCalibration]

# Multi-state affine correction
store.set_multi_state_calibration("resonator", ms_cal)
ms = store.get_multi_state_calibration("resonator") # -> MultiStateCalibration

# Fit history
from qubox_v2.calibration import FitRecord
store.store_fit(FitRecord(experiment="T1", model_name="T1_relaxation_model",
                          params={"A": 0.5, "T1": 25e-6, "offset": 0.01}))
last = store.get_latest_fit("T1")             # -> FitRecord | None
hist = store.get_fit_history("T1")            # -> list[FitRecord]

# Persistence & snapshots
store.save()                                  # Write to JSON (atomic)
snap = store.snapshot("pre_optimization")     # Timestamped backup
store.reload()                                # Reload from disk

# Diagnostic summary
print(store.summary())
# CalibrationStore: ./experiment/config/calibration.json
#   file exists: True
#   auto_save:   False
#   version:     3.0.0
#   created:     2025-02-20T14:30:00
#   modified:    2025-02-20T15:45:00
#
#   discrimination: 1 entries [resonator]
#   frequencies: 2 entries [qubit, storage]
#   coherence: 1 entries [qubit]
#   ...
```

#### `calibration.models` — Pydantic v2 Calibration Models

| Model | Fields | Description |
|-------|--------|-------------|
| `DiscriminationParams` | `threshold`, `angle`, `mu_g`, `mu_e`, `sigma_g`, `sigma_e`, `fidelity`, `confusion_matrix` | Single-shot readout state discrimination |
| `ReadoutQuality` | `F`, `Q`, `V`, `alpha`, `beta`, `confusion_matrix`, `affine_n` | Butterfly measurement metrics |
| `ElementFrequencies` | `lo_freq`, `if_freq`, `qubit_freq`, `anharmonicity`, `fock_freqs`, `chi`, `chi2`, `chi3`, `kappa`, `kerr` | Calibrated element frequencies |
| `CoherenceParams` | `T1`, `T2_ramsey`, `T2_echo`, `timestamp` | Coherence time measurements |
| `PulseCalibration` | `pulse_name`, `element`, `amplitude`, `length`, `sigma`, `drag_coeff`, `detuning` | Calibrated pulse parameters |
| `FitRecord` | `experiment`, `model_name`, `params`, `uncertainties`, `reduced_chi2`, `metadata` | Generic fit result with history |
| `PulseTrainResult` | `element`, `amp_err`, `phase_err`, `delta`, `zeta`, `rotation_pulse`, `N_values` | Pulse-train tomography errors |
| `FockSQRCalibration` | `fock_number`, `model_type`, `params`, `fidelity` | Per-Fock SQR gate calibration |
| `MultiStateCalibration` | `element`, `alpha_values`, `affine_matrix`, `offset_vector`, `state_labels` | Multi-state affine IQ correction |
| `CalibrationData` | (root container) | Aggregates all models, keyed by element |

```python
from qubox_v2.calibration.models import PulseTrainResult, FockSQRCalibration

pt = PulseTrainResult(element="qubit", amp_err=0.01, phase_err=-0.003)
sqr = FockSQRCalibration(fock_number=1, model_type="power_rabi",
                          params={"g_pi": 0.45})
```

#### `calibration.algorithms` (NEW in v3)

Calibration analysis routines that accept experimental data, perform fitting,
and return typed models ready for storage.

```python
from qubox_v2.calibration import (
    fit_pulse_train,
    compute_corrected_knobs,
    fit_multi_alpha_affine,
    apply_affine_correction,
    fit_number_splitting,
    fit_chi_ramsey,
    fit_fock_sqr,
    optimize_fock_sqr_iterative,
    optimize_fock_sqr_spsa,
)
```

| Function | Input | Returns | Description |
|----------|-------|---------|-------------|
| `fit_pulse_train` | `N_values`, `I_data`, `Q_data` | `PulseTrainResult` | Fit pulse-train tomography → amp_err, phase_err, delta |
| `compute_corrected_knobs` | `PulseTrainResult`, `amplitude` | `dict` | Compute corrected amplitude/phase from pulse-train fit |
| `fit_multi_alpha_affine` | `S_measured`, `S_ideal` dicts | `MultiStateCalibration` | Fit affine IQ correction from multi-state calibration |
| `apply_affine_correction` | `S`, `MultiStateCalibration` | `ndarray` | Apply fitted affine correction to raw IQ data |
| `fit_number_splitting` | `peak_frequencies` | `dict` | Extract chi, chi2, chi3 from number-split peak positions |
| `fit_chi_ramsey` | `times`, `signal` | `dict` | Fit chi-Ramsey collapse-and-revival data |
| `fit_fock_sqr` | `gains`, `signal`, `fock_number` | `FockSQRCalibration` | Fit single Fock-resolved SQR power Rabi curve |
| `optimize_fock_sqr_iterative` | `gains`, `signals_per_fock` | `list[FockSQRCalibration]` | Iteratively fit SQR calibrations for each Fock number |
| `optimize_fock_sqr_spsa` | `cost_function`, `x0` | `FockSQRCalibration` | SPSA optimizer for noisy experimental cost functions |

#### `calibration.history`

```python
from qubox_v2.calibration.history import CalibrationHistory

history = CalibrationHistory("./cal_history")
history.record(qubit_cal, tag="post_cooldown")
history.list_entries()
```

---

#### Calibration Audit — Which Experiments Update What

All calibration writes are gated by `analyze(result, update_calibration=True)`.
No experiment calls `store.save()` directly — saving is handled by `SessionManager.close()`
or `auto_save=True`.

| Experiment | Store Method | Fields Updated |
|------------|-------------|----------------|
| `ResonatorSpectroscopy` | `set_frequencies(ro_el, ...)` | `lo_freq`, `if_freq` |
| `ResonatorSpectroscopyX180` | `set_frequencies(ro_el, ...)` | `chi` |
| `ReadoutFrequencyOptimization` | `set_frequencies(ro_el, ...)` | `lo_freq`, `if_freq` |
| `QubitSpectroscopy` | `set_frequencies(qb_el, ...)` | `qubit_freq` |
| `QubitSpectroscopyCoarse` | `set_frequencies(qb_el, ...)` | `qubit_freq` |
| `StorageSpectroscopy` | `set_frequencies(st_el, ...)` | `qubit_freq`, `kappa` |
| `StorageChiRamsey` | `set_frequencies(st_el, ...)` | `chi` |
| `TemporalRabi` | `set_pulse_calibration("x180", ...)` | `pi_length` |
| `PowerRabi` | `set_pulse_calibration("x180", ...)` | `amplitude` |
| `DRAGCalibration` | `set_pulse_calibration("x180", ...)` | `drag_coeff` |
| `T1Relaxation` | `set_coherence(qb_el, ...)` | `T1` |
| `T2Ramsey` | `set_coherence(qb_el, ...)` | `T2_ramsey` |
| `T2Echo` | `set_coherence(qb_el, ...)` | `T2_echo` |
| `ReadoutGEDiscrimination` | `set_discrimination(ro_el, ...)` | `angle`, `threshold`, `fidelity` |
| `ReadoutButterflyMeasurement` | `set_readout_quality(ro_el, ...)` | `F`, `Q`, `V` |

**Experiments that measure but do not persist** (no `update_calibration` path):

| Experiment | What it measures | Why not persisted |
|------------|-----------------|-------------------|
| `QubitSpectroscopyEF` | `f_ef`, `gamma` | E-F transition not tracked in CalibrationData |
| `ResonatorPowerSpectroscopy` | `optimal_gain`, `optimal_freq` | 2-D exploration, not a single calibration |
| `AllXY` | `gate_error` | Diagnostic only, no stored field |
| `RandomizedBenchmarking` | `avg_gate_fidelity`, `error_per_gate` | Diagnostic only |
| `FockResolvedT1` | `T1_fock_0`, `T1_fock_1`, ... | Per-Fock T1 not in CalibrationData schema |
| `FockResolvedPowerRabi` | `g_pi_fock_0`, `g_pi_fock_1`, ... | Per-Fock gains managed via FockSQRCalibration |
| `StorageWignerTomography` | `W_min`, `W_max`, `negativity` | Diagnostic only |
| `QubitStateTomography` | `sx`, `sy`, `sz`, `purity` | Diagnostic only |

---

### 3.3 hardware/

The **QPM split** — the 2 052-line `QuaProgramManager` is decomposed into
four focused classes.

#### `hardware.ConfigEngine`

```python
engine = ConfigEngine(hardware_path="hardware.json")

qm_config = engine.build_qm_config()    # Full QM-compatible dict
engine.patch_hardware("elements.qubit.intermediate_frequency", 50e6)
engine.merge_pulses(pom)                 # Accepts PulseOperationManager
engine.save_hardware("hardware_out.json")
```

**Config layering:** `hardware_base → pulse_overlay → element_ops_overlay → runtime_overrides → build_qm_config()`

#### `hardware.HardwareController`

```python
from qm import QuantumMachinesManager

qmm = QuantumMachinesManager(host="10.0.0.1", cluster_name="Cluster_1")
hw = HardwareController(qmm=qmm, config_engine=engine)
qm = hw.open_qm()

# LO management (with external LO routing for OctaveLOSource.LO1–LO5)
hw.set_element_lo("qubit", 5.5e9)       # Updates Octave or external LO
hw.set_element_fq("qubit", 5.55e9)      # Adjusts IF to hit target freq
hw.set_octave_output("qubit", "on")     # RFOutputMode
hw.init_config(output_mode=RFOutputMode.on)

lo = hw.get_element_lo("qubit")         # Returns frequency
```

**External LO routing:**
- Reads `qubox_extras.external_los` from config
- Maps `OctaveLOSource.LO1–LO5` to physical SignalCore devices
- Automatically routes `set_element_lo()` to correct device

#### `hardware.ProgramRunner`

```python
runner = ProgramRunner(qmm=qmm, controller=hw, config_engine=engine)

# Run on hardware
result: RunResult = runner.run_program(program, n_total=1000)
print(result.output)                     # Fetched data

# Execution mode
runner.set_exec_mode(ExecMode.SIMULATE)
sim = runner.run_program(program)
```

**`ExecMode` enum:** `HARDWARE`, `SIMULATE`
**`RunResult` dataclass:** `mode`, `output`, `sim_samples`, `metadata`

#### `hardware.QueueManager`

```python
queue = QueueManager(runner=runner)

# Batch submission with progress bar
results = queue.run_many(programs, labels=["spec", "rabi", "T1"])

# Fine-grained control
pending = queue.submit(program)
```

---

### 3.4 devices/

#### `devices.DeviceManager`

Manages external instruments (SignalCore LOs, OctoDac, SPA pump, etc.)
via QCoDeS or InstrumentServer backends.

```python
dm = DeviceManager("devices.json")

# Load and connect
dm.instantiate_all()                    # Connect to all configured devices

# Access a device
lo = dm.get("signal_core_1")           # Returns device instance
dm.apply("signal_core_1", frequency=6e9, power=10)

# Ramp with safety limits
dm.ramp("octodac_ch1", param="voltage", to=0.5, step=0.01)

# Snapshot all device states
snap = dm.snapshot()
```

---

### 3.5 pulses/

#### `pulses.PulseOperationManager`

The 2 362-line pulse manager with dual permanent/volatile stores.

```python
# Load from JSON (typical)
pom = PulseOperationManager.from_json("pulses.json")

# Or create empty
pom = PulseOperationManager()

# Add waveforms and pulses
pom.add_waveform("gauss_wf", "arbitrary", samples)
pom.add_pulse("x180_pulse", "control", length=40, I_wf="gauss_wf", Q_wf="zero_wf")
pom.set_element_operation("qubit", "x180", "x180_pulse")

# Burn to hardware config via ConfigEngine
config_engine.merge_pulses(pom, include_volatile=True)

# Save / load
pom.save_json("pulses.json")
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

registry = PulseRegistry()

# Add control pulses with a clean API
registry.add_control_pulse("qubit", "x180",
                           I_wf=gauss_samples, length=40)

# Add measurement pulse
registry.add_measurement_pulse("resonator", "readout",
                               length=1000, amplitude=0.1)

# Burn to config via ConfigEngine
config_engine.merge_pulses(registry, include_volatile=True)
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

**Constructor parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `experiment_path` | `str \| Path` | *(required)* | Root directory. Config, data, and calibration live here. |
| `qop_ip` | `str \| None` | `None` | OPX+ IP / hostname. Resolved from `hardware.json` if `None`. |
| `cluster_name` | `str \| None` | `None` | QM cluster identifier. |
| `load_devices` | `bool \| list[str]` | `True` | `True` = all devices, `False` = none, `list` = named subset. |
| `oct_cal_path` | `str \| Path \| None` | `None` | Octave calibration DB path. Defaults to `experiment_path`. |
| `auto_save_calibration` | `bool` | `False` | If `True`, `CalibrationStore` auto-saves on every mutation. |

**Expected directory structure:**

```
<experiment_path>/
├── config/
│   ├── hardware.json          # QM hardware configuration
│   ├── pulses.json            # Pulse definitions
│   ├── calibration.json       # CalibrationStore (auto-created)
│   ├── cqed_params.json       # cQED_attributes (auto-created)
│   └── devices.json           # External instruments (optional)
├── data/                      # Experiment output files (auto-created)
└── octave_cal/                # Octave calibration DB (optional)
```

**Owned components (attributes):**

| Attribute | Type | Description |
|-----------|------|-------------|
| `config_engine` | `ConfigEngine` | Hardware config builder |
| `hardware` / `hw` | `HardwareController` | LO routing, Octave, QM connection |
| `runner` | `ProgramRunner` | Program execution |
| `queue` | `QueueManager` | Batch job submission |
| `pulse_mgr` | `PulseOperationManager` | Full pulse manager |
| `pulses` | `PulseRegistry` | Simplified pulse facade |
| `calibration` | `CalibrationStore` | Typed calibration persistence |
| `devices` | `DeviceManager` | External instruments |
| `attributes` / `attr` | `cQED_attributes` | Typed experiment parameters |

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

#### Experiment `analyze()` / `plot()` Protocol

All experiment classes implement the unified three-step protocol:

```python
exp = ExperimentClass(session)
result = exp.run(...)                                    # Execute on hardware
analysis = exp.analyze(result, update_calibration=True)  # Fit + extract metrics
exp.plot(analysis)                                       # Visualize
```

**`analyze(result, *, update_calibration=False, **kw) -> AnalysisResult`**
- Extracts data from `result.output` (e.g., `S`, `frequencies`, `delays`)
- Fits physics models via `fit_and_wrap()` where applicable
- Returns `AnalysisResult` with `.fit`, `.metrics`, `.data`
- If `update_calibration=True`, persists results to `CalibrationStore`

**`plot(analysis, *, ax=None, **kwargs) -> fig`**
- Accepts optional `ax` kwarg for embedding in multi-panel figures
- Returns `matplotlib.figure.Figure`
- Shows data points, fit curves, and key metrics in legend/title

**`AnalysisResult` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `data` | `dict` | Raw data from the experiment output |
| `fit` | `FitResult \| None` | Primary fit result |
| `fits` | `dict[str, FitResult]` | Named fit results (e.g., per-Fock) |
| `metrics` | `dict[str, Any]` | Extracted parameters (f0, T1, chi, ...) |

**`FitResult` fields:**

| Field | Type | Description |
|-------|------|-------------|
| `model_name` | `str` | Name of the fitted model |
| `params` | `dict[str, float]` | Best-fit parameters (keys match model arg names) |
| `uncertainties` | `dict[str, float]` | Parameter uncertainties |
| `r_squared` | `float` | Goodness of fit |
| `residuals` | `np.ndarray` | Fit residuals |
| `metadata` | `dict[str, Any]` | Extra metadata (e.g., `{"equation": "..."}`) |

#### `analysis.fitting.fit_and_wrap()` (NEW in v3)

Bridge between `generalized_fit()` and the typed `FitResult`:

```python
from qubox_v2.analysis.fitting import fit_and_wrap

fit = fit_and_wrap(x_data, y_data, model_function, p0, model_name="T1")
# fit.params = {"A": ..., "T1": ..., "offset": ...}
# Keys extracted from model function signature
```

#### `analysis.fitting.build_fit_legend()` (NEW in v3)

Generates a multi-line legend string with the model equation and fitted parameter values.
Used by all `plot()` methods for consistent equation display on figures.

```python
from qubox_v2.analysis.fitting import build_fit_legend

legend_text = build_fit_legend(fit_result)
# Returns e.g.:
# "$y = \text{offset} + A\,e^{-t/T_1}$"
# "A = 0.5123"
# "T1 = 2.531e+04"
# "offset = 0.01234"

# Used in plot methods:
ax.plot(x_fit, y_fit, "r-", label=build_fit_legend(analysis.fit))
ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=10)
```

#### Unit conventions for auto_p0

All `analyze()` methods construct automatic initial guesses (`auto_p0`) using the
native units of the data. Since delays are stored in **nanoseconds** (ns) via
`delay_clks * 4`, frequency parameters must be in **1/ns = GHz**:

| Parameter | Unit | Example |
|-----------|------|---------|
| `delays`, `T1`, `T2` | ns | 10000 (= 10 us) |
| `f_det`, `chi` | 1/ns (GHz) | 0.0002 (= 200 kHz) |
| `gains`, `A`, `offset` | (unitless) | 0.5 |

Users can override auto_p0 by passing explicit `p0=` to `analyze()`.

**Per-experiment metrics reference:**

| Experiment | Model | Key metrics |
|------------|-------|-------------|
| `ResonatorSpectroscopy` | `resonator_spec_model` | `f0`, `kappa` |
| `QubitSpectroscopy` | `qubit_spec_model` | `f0`, `gamma` |
| `PowerRabi` | `power_rabi_model` | `g_pi` |
| `TemporalRabi` | `temporal_rabi_model` | `f_Rabi`, `T_decay`, `pi_length` |
| `T1Relaxation` | `T1_relaxation_model` | `T1` |
| `T2Ramsey` | `T2_ramsey_model` | `T2`, `f_det` |
| `T2Echo` | `T2_echo_model` | `T2_echo` |
| `AllXY` | (ideal pattern) | `gate_error` |
| `DRAGCalibration` | (zero-crossing) | `optimal_alpha` |
| `RandomizedBenchmarking` | `rb_survival_model` | `p`, `avg_gate_fidelity`, `error_per_gate` |
| `IQBlob` | `two_state_discriminator` | `fidelity`, `angle`, `threshold` |
| `ReadoutButterflyMeasurement` | `butterfly_metrics` | `F`, `Q`, `V` |
| `StorageSpectroscopy` | `resonator_spec_model` | `f_storage`, `kappa` |
| `StorageChiRamsey` | `chi_ramsey_model` | `chi`, `nbar`, `T2_eff` |
| `FockResolvedT1` | `T1_relaxation_model` (per-Fock) | `T1_fock_0`, `T1_fock_1`, ... |
| `FockResolvedPowerRabi` | `power_rabi_model` (per-Fock) | `g_pi_fock_0`, `g_pi_fock_1`, ... |
| `QubitStateTomography` | (Bloch vector) | `sx`, `sy`, `sz`, `purity` |
| `StorageWignerTomography` | (parity -> W) | `W_min`, `W_max`, `negativity` |
| `SPAFluxOptimization` | (peak search) | `best_dc`, `best_freq` |
| `SPAPumpFrequencyOptimization` | (argmax) | `best_pump_power`, `best_pump_detuning`, `best_metric` |

#### Experiment class hierarchy (NEW in v3)

| Subdirectory | Classes |
|--------------|---------|
| `spectroscopy/` | `ResonatorSpectroscopy`, `ResonatorPowerSpectroscopy`, `ResonatorSpectroscopyX180`, `ReadoutTrace`, `ReadoutFrequencyOptimization`, `QubitSpectroscopy`, `QubitSpectroscopyCoarse`, `QubitSpectroscopyEF` |
| `time_domain/` | `TemporalRabi`, `PowerRabi`, `T1Relaxation`, `T2Ramsey`, `T2Echo`, `ResidualPhotonRamsey` |
| `calibration/` | `AllXY`, `DRAGCalibration`, `QubitPulseTrain`, `QubitPulseTrainLegacy`, `RandomizedBenchmarking`, `IQBlob`, `ReadoutGERawTrace`, `ReadoutGEIntegratedTrace`, `ReadoutGEDiscrimination`, `ReadoutWeightsOptimization`, `ReadoutButterflyMeasurement`, `CalibrateReadoutFull`, `ReadoutAmpLenOpt` |
| `cavity/` | `StorageSpectroscopy`, `StorageSpectroscopyCoarse`, `NumSplittingSpectroscopy`, `StorageRamsey`, `StorageChiRamsey`, `StoragePhaseEvolution`, `FockResolvedSpectroscopy`, `FockResolvedT1`, `FockResolvedRamsey`, `FockResolvedPowerRabi` |
| `tomography/` | `QubitStateTomography`, `FockResolvedStateTomography`, `StorageWignerTomography`, `SNAPOptimization` |
| `spa/` | `SPAFluxOptimization`, `SPAFluxOptimization2`, `SPAPumpFrequencyOptimization` |

#### Experiment `run()` Parameter Reference

Full parameter signatures for every experiment class, organized by subdirectory.
All experiments share the protocol: `exp = Class(session); result = exp.run(...); analysis = exp.analyze(result)`.

##### spectroscopy/

**`ResonatorSpectroscopy.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `readout_op` | `str` | *(required)* | Readout operation name |
| `rf_begin` | `float` | `8605e6` | Start frequency (Hz) |
| `rf_end` | `float` | `8620e6` | End frequency (Hz) |
| `df` | `float` | `50e3` | Frequency step (Hz) |
| `n_avg` | `int` | `1000` | Averages |

Calibration: `set_frequencies(ro_el, lo_freq=..., if_freq=...)` | Metrics: `f0`, `kappa`

**`ResonatorPowerSpectroscopy.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `readout_op` | `str` | *(required)* | Readout operation name |
| `rf_begin` | `float` | *(required)* | Start frequency (Hz) |
| `rf_end` | `float` | *(required)* | End frequency (Hz) |
| `df` | `float` | *(required)* | Frequency step (Hz) |
| `g_min` | `float` | `1e-3` | Min readout gain |
| `g_max` | `float` | `0.5` | Max readout gain |
| `N_a` | `int` | `50` | Gain steps |
| `n_avg` | `int` | `1000` | Averages |

Calibration: none | Metrics: `optimal_gain`, `optimal_freq`

**`ResonatorSpectroscopyX180.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rf_begin` | `float` | *(required)* | Start frequency (Hz) |
| `rf_end` | `float` | *(required)* | End frequency (Hz) |
| `df` | `float` | *(required)* | Frequency step (Hz) |
| `r180` | `str` | `"x180"` | Pi pulse operation name |
| `n_avg` | `int` | `1000` | Averages |

Calibration: `set_frequencies(ro_el, chi=...)` | Metrics: `f0_g`, `f0_e`, `chi`

**`ReadoutFrequencyOptimization.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rf_begin` | `float` | *(required)* | Start frequency (Hz) |
| `rf_end` | `float` | *(required)* | End frequency (Hz) |
| `df` | `float` | *(required)* | Frequency step (Hz) |
| `ro_op` | `str \| None` | `None` | Readout op override |
| `r180` | `str` | `"x180"` | Pi pulse name |
| `n_runs` | `int` | `1000` | Shots per frequency |

Calibration: `set_frequencies(ro_el, lo_freq=..., if_freq=...)` | Metrics: `best_fidelity`, `best_freq`

**`QubitSpectroscopy.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pulse` | `str` | *(required)* | Qubit drive pulse name |
| `rf_begin` | `float` | *(required)* | Start frequency (Hz) |
| `rf_end` | `float` | *(required)* | End frequency (Hz) |
| `df` | `float` | *(required)* | Frequency step (Hz) |
| `qb_gain` | `float` | *(required)* | Qubit drive gain |
| `qb_len` | `int` | *(required)* | Drive pulse length (ns) |
| `n_avg` | `int` | `1000` | Averages |

Calibration: `set_frequencies(qb_el, qubit_freq=...)` | Metrics: `f0`, `gamma`

**`QubitSpectroscopyCoarse.run()`** — same as `QubitSpectroscopy` but uses multi-LO segments for wide sweeps.

**`QubitSpectroscopyEF.run()`** — same signature as `QubitSpectroscopy`. No calibration update. Metrics: `f_ef`, `gamma`.

##### time_domain/

**`TemporalRabi.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pulse` | `str` | *(required)* | Drive pulse name |
| `pulse_len_begin` | `int` | *(required)* | Start duration (ns, multiple of 4) |
| `pulse_len_end` | `int` | *(required)* | End duration (ns) |
| `dt` | `int` | `4` | Duration step (ns) |
| `pulse_gain` | `float` | `1.0` | Pulse gain scaling |
| `n_avg` | `int` | `1000` | Averages |

Calibration: `set_pulse_calibration("x180", pi_length=...)` | Metrics: `f_Rabi`, `T_decay`, `pi_length`

**`PowerRabi.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_gain` | `float` | *(required)* | Maximum gain to sweep |
| `dg` | `float` | `1e-3` | Gain step |
| `op` | `str` | `"x180"` | Pulse operation name |
| `length` | `int \| None` | `None` | Override pulse length (ns) |
| `truncate_clks` | `int \| None` | `None` | Truncation in clock cycles |
| `n_avg` | `int` | `1000` | Averages |

Calibration: `set_pulse_calibration("x180", amplitude=...)` | Metrics: `g_pi`

**`T1Relaxation.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `delay_end` | `int` | *(required)* | Max delay (clock cycles) |
| `dt` | `int` | *(required)* | Delay step (clock cycles) |
| `delay_begin` | `int` | `4` | Min delay (clock cycles) |
| `r180` | `str` | `"x180"` | Pi pulse name |
| `n_avg` | `int` | `1000` | Averages |

Calibration: `set_coherence(qb_el, T1=...)` | Metrics: `T1`

**`T2Ramsey.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `qb_detune` | `int` | *(required)* | Detuning (Hz) |
| `delay_end` | `int` | *(required)* | Max delay (clock cycles) |
| `dt` | `int` | *(required)* | Delay step (clock cycles) |
| `delay_begin` | `int` | `4` | Min delay (clock cycles) |
| `r90` | `str` | `"x90"` | Half-pi pulse name |
| `n_avg` | `int` | `1000` | Averages |

Calibration: `set_coherence(qb_el, T2_ramsey=...)` | Metrics: `T2_star`, `f_det`

**`T2Echo.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `delay_end` | `int` | *(required)* | Max delay (clock cycles) |
| `dt` | `int` | *(required)* | Delay step (clock cycles) |
| `delay_begin` | `int` | `8` | Min delay (clock cycles) |
| `r180` | `str` | `"x180"` | Pi pulse name |
| `r90` | `str` | `"x90"` | Half-pi pulse name |
| `n_avg` | `int` | `1000` | Averages |

Calibration: `set_coherence(qb_el, T2_echo=...)` | Metrics: `T2_echo`

**`ResidualPhotonRamsey.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `t_R_begin` | `int` | *(required)* | Start Ramsey time (clock cycles) |
| `t_R_end` | `int` | *(required)* | End Ramsey time (clock cycles) |
| `dt` | `int` | *(required)* | Step (clock cycles) |
| `test_ro_op` | `str` | *(required)* | Test readout operation |
| `qb_detuning` | `int` | `0` | Qubit detuning (Hz) |
| `t_relax` | `int` | `40` | Relaxation time (ns) |
| `t_buffer` | `int` | `400` | Buffer time (ns) |
| `r90` | `str` | `"x90"` | Half-pi pulse |
| `r180` | `str` | `"x180"` | Pi pulse |
| `prep_e` | `bool` | `False` | Prepare excited state |
| `test_ro_amp` | `float` | `1.0` | Test readout amplitude |
| `measure_ro_op` | `str` | `"readout_long"` | Measurement readout op |
| `n_avg` | `int` | `1000` | Averages |

Calibration: none | Metrics: `T2`

##### calibration/

**`AllXY.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `gate_indices` | `list[int] \| None` | `None` | Subset of 21 AllXY sequences (all if None) |
| `prefix` | `str` | `""` | Gate name prefix |
| `qb_detuning` | `int` | `0` | Detuning offset (Hz) |
| `n_avg` | `int` | `1000` | Averages |

Calibration: none | Metrics: `gate_error`

**`DRAGCalibration.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `amps` | `ndarray \| list[float]` | *(required)* | DRAG amplitude sweep |
| `n_avg` | `int` | `1000` | Averages |
| `x180` | `str` | `"x180"` | X180 pulse name |
| `x90` | `str` | `"x90"` | X90 pulse name |
| `y180` | `str` | `"y180"` | Y180 pulse name |
| `y90` | `str` | `"y90"` | Y90 pulse name |

Calibration: `set_pulse_calibration("x180", drag_coeff=...)` | Metrics: `optimal_alpha`

**`RandomizedBenchmarking.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `m_list` | `list[int]` | *(required)* | Clifford depths |
| `num_sequence` | `int` | *(required)* | Sequences per depth |
| `n_avg` | `int` | `1000` | Averages |
| `interleave_op` | `str \| None` | `None` | Gate to interleave |
| `primitives_by_id` | `dict \| None` | `None` | Custom primitive mapping |
| `primitive_prefix` | `str` | `""` | Primitive name prefix |
| `max_sequences_per_compile` | `int` | `10` | Batch size |
| `guard_clks` | `int` | `18` | Idle guard cycles |

Calibration: none | Metrics: `p`, `avg_gate_fidelity`, `error_per_gate`

**`QubitPulseTrain.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `N_values` | `list[int] \| ndarray` | *(required)* | Pulse repetition counts |
| `reference_pulse` | `str` | `"x90"` | Reference pulse |
| `rotation_pulse` | `str` | `"x180"` | Rotation pulse |
| `run_reference` | `bool` | `False` | Include zero-amplitude reference |
| `n_avg` | `int` | `1000` | Averages |

Calibration: none | Metrics: `I_std`, `Q_std`, `amp_err`

**`IQBlob.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `r180` | `str` | `"x180"` | Pi pulse name |
| `n_runs` | `int` | `1000` | Shots |

Calibration: none | Metrics: `fidelity`, `angle`, `threshold`, `confusion_matrix`

**`ReadoutGEDiscrimination.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `measure_op` | `str` | *(required)* | Measure operation name |
| `drive_frequency` | `float` | *(required)* | Readout drive frequency (Hz) |
| `r180` | `str` | `"x180"` | Pi pulse |
| `gain` | `float` | `1.0` | Readout gain |
| `n_samples` | `int` | `10_000` | Shots |
| `blob_k_g` | `float` | `2.0` | Ground blob k-sigma |
| `blob_k_e` | `float \| None` | `None` | Excited blob k-sigma |

Calibration: `set_discrimination(ro_el, angle=..., threshold=..., fidelity=...)` | Metrics: `fidelity`, `angle`, `threshold`, `gg`, `ge`, `eg`, `ee`

**`ReadoutButterflyMeasurement.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prep_policy` | `str \| None` | `None` | Post-selection policy |
| `prep_kwargs` | `dict \| None` | `None` | Policy kwargs |
| `r180` | `str` | `"x180"` | Pi pulse |
| `n_samples` | `int` | `10_000` | Shots |
| `M0_MAX_TRIALS` | `int` | `16` | Max post-selection retries |

Calibration: `set_readout_quality(ro_el, F=..., Q=..., V=...)` | Metrics: `F`, `Q`, `V`

**`CalibrateReadoutFull.run()`** — pipeline running `ReadoutWeightsOptimization` + `ReadoutGEDiscrimination` + `ReadoutButterflyMeasurement` in sequence. Returns `dict` of sub-results.

**`ReadoutAmpLenOpt.run()`** — 2-D sweep of readout amplitude x length. Returns `Output` with `fidelity_matrix`. Metrics: `best_length`, `best_gain`, `best_fidelity`.

##### cavity/

**`StorageSpectroscopy.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `disp` | `str` | *(required)* | Displacement pulse name |
| `rf_begin` | `float` | *(required)* | Start frequency (Hz) |
| `rf_end` | `float` | *(required)* | End frequency (Hz) |
| `df` | `float` | *(required)* | Frequency step (Hz) |
| `storage_therm_time` | `int` | *(required)* | Thermalization time (clock cycles) |
| `sel_r180` | `str` | `"sel_x180"` | Selective pi pulse |
| `n_avg` | `int` | `1000` | Averages |

Calibration: `set_frequencies(st_el, qubit_freq=..., kappa=...)` | Metrics: `f_storage`, `kappa`

**`StorageSpectroscopyCoarse.run()`** — multi-LO wide sweep variant. Same analyze/calibration as `StorageSpectroscopy`.

**`NumSplittingSpectroscopy.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rf_centers` | `list[float] \| ndarray` | *(required)* | Peak center frequencies (Hz) |
| `rf_spans` | `list[float] \| ndarray` | *(required)* | Span around each center (Hz) |
| `df` | `float` | *(required)* | Frequency step (Hz) |
| `sel_r180` | `str` | `"sel_x180"` | Selective pi pulse |
| `state_prep` | `Any` | `None` | State preparation |
| `n_avg` | `int` | `1000` | Averages |

Calibration: none | Metrics: `n_peaks`

**`StorageRamsey.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `delay_ticks` | `ndarray \| list[int]` | *(required)* | Delay sweep (clock cycles) |
| `st_detune` | `int` | `0` | Storage detuning (Hz) |
| `disp_pulse` | `str` | `"const_alpha"` | Displacement pulse |
| `sel_r180` | `str` | `"sel_x180"` | Selective pi pulse |
| `n_avg` | `int` | `200` | Averages |

Calibration: none | Metrics: `T2_storage`

**`StorageChiRamsey.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fock_fq` | `float` | *(required)* | Fock transition frequency (Hz) |
| `delay_ticks` | `ndarray \| list[int]` | *(required)* | Delay sweep (clock cycles) |
| `disp_pulse` | `str` | `"const_alpha"` | Displacement pulse |
| `x90_pulse` | `str` | `"x90"` | Half-pi pulse |
| `n_avg` | `int` | `200` | Averages |

Calibration: `set_frequencies(st_el, chi=...)` | Metrics: `chi`, `nbar`, `T2_eff`

**`FockResolvedSpectroscopy.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `probe_fqs` | `list[float] \| ndarray` | *(required)* | Probe frequencies |
| `state_prep` | `Any` | `None` | State preparation |
| `sel_r180` | `str` | `"sel_x180"` | Selective pi pulse |
| `calibrate_ref_r180_S` | `bool` | `True` | Calibrate reference |
| `n_avg` | `int` | `100` | Averages |

Calibration: none | Metrics: `n_fock` or `n_points`

**`FockResolvedT1.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fock_fqs` | `list[float] \| ndarray` | *(required)* | Fock transition frequencies |
| `fock_disps` | `list[str]` | *(required)* | Displacement names per Fock |
| `delay_end` | `int` | *(required)* | Max delay (clock cycles) |
| `dt` | `int` | *(required)* | Delay step (clock cycles) |
| `delay_begin` | `int` | `4` | Min delay |
| `sel_r180` | `str` | `"sel_x180"` | Selective pi pulse |
| `n_avg` | `int` | `1000` | Averages |

Calibration: none | Metrics: `T1_fock_0`, `T1_fock_1`, ...

**`FockResolvedRamsey.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fock_fqs` | `list[float] \| ndarray` | *(required)* | Fock frequencies |
| `detunings` | `list[float] \| ndarray` | *(required)* | Detuning sweep |
| `disps` | `list[str]` | *(required)* | Displacement names |
| `delay_end` | `int` | *(required)* | Max delay |
| `dt` | `int` | *(required)* | Delay step |
| `delay_begin` | `int` | `4` | Min delay |
| `sel_r90` | `str` | `"sel_x90"` | Selective 90 pulse |
| `n_avg` | `int` | `1000` | Averages |

Calibration: none | Metrics: `T2_fock_0`, `T2_fock_1`, ...

**`FockResolvedPowerRabi.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fock_fqs` | `list[float] \| ndarray` | *(required)* | Fock frequencies |
| `gains` | `list[float] \| ndarray` | *(required)* | Gain sweep |
| `sel_qb_pulse` | `str` | *(required)* | Selective qubit pulse |
| `disp_n_list` | `list[str]` | *(required)* | Displacement list per Fock |
| `n_avg` | `int` | `1000` | Averages |

Calibration: none | Metrics: `g_pi_fock_0`, `g_pi_fock_1`, ...

##### tomography/

**`QubitStateTomography.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `state_prep` | `Callable \| list` | *(required)* | State preparation |
| `n_avg` | `int` | *(required)* | Averages |
| `x90_pulse` | `str` | `"x90"` | X90 pulse (keyword-only) |
| `yn90_pulse` | `str` | `"yn90"` | Y-90 pulse (keyword-only) |
| `therm_clks` | `int \| None` | `None` | Thermalization (keyword-only) |

Calibration: none | Metrics: `sx`, `sy`, `sz`, `purity`

**`FockResolvedStateTomography.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `fock_fqs` | `list[float] \| ndarray` | *(required)* | Fock frequencies |
| `state_prep` | `Callable \| list` | *(required)* | State preparation |
| `sel_r180` | `str` | `"sel_x180"` | Selective pi (keyword-only) |
| `rxp90` | `str` | `"x90"` | X90 pulse (keyword-only) |
| `rym90` | `str` | `"yn90"` | Y-90 pulse (keyword-only) |
| `n_avg` | `int` | `1000` | Averages (keyword-only) |

Calibration: none | Metrics: `n_fock`, `fock_pops`

**`StorageWignerTomography.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `gates` | `list` | *(required)* | Gate sequence for state prep |
| `x_vals` | `ndarray \| list` | *(required)* | Phase-space x grid |
| `p_vals` | `ndarray \| list` | *(required)* | Phase-space p grid |
| `base_alpha` | `float` | `10.0` | Displacement magnitude scale |
| `r90_pulse` | `str` | `"x90"` | Half-pi pulse |
| `n_avg` | `int` | `200` | Averages |

Calibration: none | Metrics: `W_min`, `W_max`, `negativity`

##### spa/

**`SPAFluxOptimization.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dc_list` | `list[float] \| ndarray` | *(required)* | DC bias voltages |
| `sample_fqs` | `list[float] \| ndarray` | *(required)* | Probe frequencies |
| `n_avg` | `int` | *(required)* | Averages |
| `odc_name` | `str` | `"octodac_bf"` | OctoDac device name (keyword-only) |
| `odc_param` | `str` | `"voltage5"` | OctoDac parameter (keyword-only) |
| `step` | `float` | `0.005` | Voltage ramp step (keyword-only) |
| `delay_s` | `float` | `0.1` | Settle delay in seconds (keyword-only) |

Calibration: none | Metrics: `best_dc`, `best_freq`, `peak_magnitude`

**`SPAPumpFrequencyOptimization.run()`**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `readout_op` | `str` | *(required)* | Readout operation |
| `drive_frequency` | `float` | *(required)* | Drive frequency (Hz) |
| `pump_powers` | `list[float] \| ndarray` | *(required)* | Pump power sweep |
| `pump_detunings` | `list[float] \| ndarray` | *(required)* | Pump detuning sweep |
| `r180` | `str` | `"x180"` | Pi pulse |
| `samples_per_run` | `int` | `25_000` | Shots per point |
| `metric` | `str` | `"assignment_fidelity"` | Optimization metric name |

Calibration: none | Metrics: `best_pump_power`, `best_pump_detuning`, `best_metric`

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
| `fitting.py` | `generalized_fit`, `fit_and_wrap`, `build_fit_legend` — curve fitting with typed results |
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
from qm import QuantumMachinesManager
from qubox_v2.hardware import ConfigEngine, HardwareController, ProgramRunner

engine = ConfigEngine(hardware_path="hardware.json")
qmm = QuantumMachinesManager(host="10.0.0.1", cluster_name="Cluster_1")
hw = HardwareController(qmm=qmm, config_engine=engine)
runner = ProgramRunner(qmm=qmm, controller=hw, config_engine=engine)

# Open QM and set LO
hw.open_qm()
hw.set_element_lo("qubit", 5.5e9)

# Run
result = runner.run_program(my_program)

hw.close()
```

### D. Batch experiments with queue

```python
from qubox_v2.hardware import QueueManager

queue = QueueManager(runner=runner)
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

## 6. Recipes

### A. Verify calibration persistence

```python
from qubox_v2.experiments.session import SessionManager

with SessionManager("./seq_1_device", qop_ip="10.0.0.1") as session:
    # Check file exists and inspect contents
    print(session.calibration.summary())

    # Verify a round-trip: write → save → reload → read
    session.calibration.set_coherence("qubit", T1=25e3)
    session.calibration.save()
    session.calibration.reload()
    coh = session.calibration.get_coherence("qubit")
    assert coh is not None and abs(coh.T1 - 25e3) < 1e-6
    print("Calibration persistence OK")
```

### B. End-to-end qubit characterization with calibration

```python
from qubox_v2.experiments.session import SessionManager
from qubox_v2.experiments.spectroscopy import ResonatorSpectroscopy, QubitSpectroscopy
from qubox_v2.experiments.time_domain import PowerRabi, T1Relaxation, T2Ramsey
from qubox_v2.experiments.calibration import ReadoutGEDiscrimination

with SessionManager("./seq_1_device", qop_ip="10.0.0.1") as session:
    # 1. Resonator spectroscopy → calibrate readout frequency
    res = ResonatorSpectroscopy(session)
    r = res.run(readout_op="readout")
    a = res.analyze(r, update_calibration=True)
    res.plot(a)

    # 2. Qubit spectroscopy → calibrate qubit frequency
    qb = QubitSpectroscopy(session)
    r = qb.run(pulse="saturation", rf_begin=5.2e9, rf_end=5.3e9, df=100e3,
               qb_gain=0.1, qb_len=10000)
    a = qb.analyze(r, update_calibration=True)
    qb.plot(a)

    # 3. Power Rabi → calibrate pi pulse gain
    rabi = PowerRabi(session)
    r = rabi.run(max_gain=0.5, dg=1e-3)
    a = rabi.analyze(r, update_calibration=True)
    rabi.plot(a)
    print(f"g_pi = {a.metrics['g_pi']:.4f}")

    # 4. T1 → calibrate coherence
    t1 = T1Relaxation(session)
    r = t1.run(delay_end=50000, dt=200)
    a = t1.analyze(r, update_calibration=True)
    print(f"T1 = {a.metrics['T1']:.0f} ns")

    # 5. Readout discrimination → calibrate threshold/angle
    disc = ReadoutGEDiscrimination(session)
    r = disc.run(measure_op="readout", drive_frequency=8.61e9, n_samples=10000)
    a = disc.analyze(r, update_calibration=True)
    print(f"Fidelity = {a.metrics['fidelity']:.1f}%")

    # All calibrations saved automatically on context manager exit
    print(session.calibration.summary())
```

### C. Inspect calibration without hardware

```python
from qubox_v2.calibration import CalibrationStore

store = CalibrationStore("./seq_1_device/config/calibration.json")
print(store.summary())

# Read specific sections
freqs = store.get_frequencies("qubit")
if freqs:
    print(f"Qubit freq: {freqs.qubit_freq / 1e9:.6f} GHz")
    print(f"LO freq:    {freqs.lo_freq / 1e9:.6f} GHz")
    print(f"IF freq:    {freqs.if_freq / 1e6:.3f} MHz")

coh = store.get_coherence("qubit")
if coh:
    print(f"T1: {coh.T1:.0f} ns = {coh.T1 / 1e3:.1f} us")
    if coh.T2_ramsey:
        print(f"T2*: {coh.T2_ramsey:.0f} ns = {coh.T2_ramsey / 1e3:.1f} us")

disc = store.get_discrimination("resonator")
if disc:
    print(f"Discrimination fidelity: {disc.fidelity:.1f}%")
    print(f"Threshold: {disc.threshold:.6f}")
```

### D. Create a calibration snapshot before optimization

```python
with SessionManager("./seq_1_device", qop_ip="10.0.0.1") as session:
    # Snapshot current state
    snap_path = session.calibration.snapshot("pre_optimization")
    print(f"Snapshot saved to: {snap_path}")

    # ... run optimization experiments ...

    # If something goes wrong, restore
    # from qubox_v2.calibration import CalibrationStore
    # session.calibration = CalibrationStore(snap_path)
```

---

## 7. Design Principles

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
