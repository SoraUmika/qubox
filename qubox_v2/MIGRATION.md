# qubox_v2 Migration Guide (v2 → v3)

> This document describes what changed in the v3 architecture refactoring,
> what moved where, and how to update existing code.

---

## 1. Quick Migration (Zero Effort)

Add one line at the top of your legacy notebooks:

```python
import qubox_v2.compat.legacy
```

All old `qubox.*` imports will work transparently (with deprecation warnings).
No other changes needed.

---

## 2. What's New in v3

### New Layers

| Layer | Module | Description |
|-------|--------|-------------|
| L1 | `calibration/` | JSON-backed typed calibration persistence with Pydantic v2 |
| — | `calibration/store.py` | `CalibrationStore` — get/set/snapshot/restore |
| — | `calibration/models.py` | `QubitCalibration`, `ReadoutCalibration`, etc. |
| — | `calibration/history.py` | Timestamped calibration snapshots |

### New Pulse Infrastructure

| Module | Description |
|--------|-------------|
| `pulses/pulse_registry.py` | `PulseRegistry` — simplified facade over `PulseOperationManager` |
| `pulses/integration_weights.py` | `IntegrationWeightManager` — extracted from POM |
| `pulses/waveforms.py` | Waveform factory functions (`gaussian`, `drag`, `flat_top`, etc.) |

### New Experiment Infrastructure

| Module | Description |
|--------|-------------|
| `experiments/experiment_base.py` | `ExperimentBase` — ABC for modular experiment classes |
| `experiments/session.py` | `SessionManager` — service container replacing god-object wiring |
| `experiments/result.py` | `AnalysisResult`, `FitResult` dataclasses |

### New Experiment Classes

Experiments are now individual classes instead of methods on the 5,200-line `cQED_Experiment`:

| Subdirectory | Classes |
|--------------|---------|
| `experiments/spectroscopy/` | `ResonatorSpectroscopy`, `ResonatorPowerSpectroscopy`, `QubitSpectroscopy`, `QubitSpectroscopyEF` |
| `experiments/time_domain/` | `TemporalRabi`, `PowerRabi`, `RabiChevron`, `RamseyChevron`, `T1Relaxation`, `T2Ramsey`, `T2Echo` |
| `experiments/calibration/` | `AllXY`, `DRAGCalibration`, `RandomizedBenchmarking`, `ReadoutDiscrimination`, `ReadoutButterfly`, `WeightsOptimization`, `ActiveReset`, `LeakageBenchmarking` |
| `experiments/cavity/` | `StorageSpectroscopy`, `NumSplitting`, `ChiRamsey`, `FockResolvedSpectroscopy`, `FockResolvedRamsey` |
| `experiments/tomography/` | `QubitStateTomography`, `FockStateTomography`, `WignerTomography`, `SNAPOptimization` |
| `experiments/spa/` | `SPAFluxOptimization`, `SPAPumpFreqOptimization` |

### Program Category Modules

The 2,898-line `cQED_programs.py` monolith is now accessible via category modules:

| Module | What it re-exports |
|--------|--------------------|
| `programs/spectroscopy.py` | `resonator_spectroscopy`, `qubit_spectroscopy`, etc. |
| `programs/time_domain.py` | `temporal_rabi`, `T1_relaxation`, `T2_ramsey`, etc. |
| `programs/calibration.py` | `all_xy`, `randomized_benchmarking`, etc. |
| `programs/readout.py` | `iq_blobs`, `readout_butterfly_measurement`, etc. |
| `programs/cavity.py` | `storage_chi_ramsey`, `fock_resolved_spectroscopy`, etc. |
| `programs/tomography.py` | `qubit_state_tomography`, etc. |

> **Note:** These are re-export facades. `cQED_programs.py` is preserved as-is.
> Both import styles work:
> ```python
> from qubox_v2.programs.spectroscopy import resonator_spectroscopy  # v3 style
> from qubox_v2.programs.cQED_programs import resonator_spectroscopy  # still works
> ```

### Shared Types

| Module | Exports |
|--------|---------|
| `core/types.py` | `ExecMode`, `DemodMode`, `PulseType`, `WaveformType` enums |

---

## 3. What Was Preserved (Unchanged)

These files are unchanged from v2 and remain fully functional:

- `core/` — config, errors, protocols, utils, logging
- `hardware/` — config_engine, controller, program_runner, queue_manager
- `devices/` — device_manager
- `pulses/manager.py` — PulseOperationManager (2,362 lines)
- `pulses/models.py` — WaveformSpec, PulseSpec, ResourceStore
- `programs/cQED_programs.py` — all 40+ QUA program factories
- `programs/macros/` — measureMacro, sequenceMacros
- `experiments/base.py` — ExperimentRunner
- `experiments/legacy_experiment.py` — cQED_Experiment
- `experiments/config_builder.py` — ConfigBuilder
- `experiments/gates_legacy.py` — legacy gate dataclasses
- `analysis/` — all analysis modules
- `simulation/` — QuTiP simulation
- `gates/` — gate abstraction framework
- `compile/` — gate-sequence compilation
- `optimization/` — optimisation routines
- `tools/` — waveform generators
- `gui/` — program GUI

---

## 4. Import Path Changes

### Programs

```python
# v2 (still works)
from qubox_v2.programs.cQED_programs import resonator_spectroscopy

# v3 (preferred)
from qubox_v2.programs.spectroscopy import resonator_spectroscopy
```

### Experiments (new v3 classes)

```python
# v2 (legacy monolith)
from qubox_v2.experiments.legacy_experiment import cQED_Experiment
exp = cQED_Experiment("./path")
exp.resonator_spectroscopy(...)

# v3 (modular classes)
from qubox_v2.experiments.session import SessionManager
from qubox_v2.experiments.spectroscopy import ResonatorSpectroscopy

with SessionManager("./path", qop_ip="10.0.0.1") as session:
    spec = ResonatorSpectroscopy(session)
    result = spec.run(...)
    analysis = spec.analyze(result)
```

### Pulse Registration

```python
# v2 (POM directly)
from qubox_v2.pulses.manager import PulseOperationManager
pom = PulseOperationManager(config_engine)
pom.register("x180", ...)

# v3 (PulseRegistry facade)
from qubox_v2.pulses import PulseRegistry
registry = PulseRegistry(pom)
registry.register("x180", ...)
```

### Calibration (new)

```python
from qubox_v2.calibration import CalibrationStore

store = CalibrationStore("./cal_data")
store.set("qubit_freq", 5.55e9)
store.save_snapshot("baseline")
```

---

## 5. Backward-Compatibility Shim Details

The `compat/` module intercepts `qubox.*` imports via `sys.meta_path`:

| Old Import | Redirects To |
|------------|-------------|
| `qubox.program_manager` | `qubox_v2.hardware` |
| `qubox.device_manager` | `qubox_v2.devices.device_manager` |
| `qubox.pulse_manager` | `qubox_v2.pulses.manager` |
| `qubox.cQED_programs` | `qubox_v2.programs.cQED_programs` |
| `qubox.cQED_experiments` | `qubox_v2.experiments.legacy_experiment` |
| `qubox.config_builder` | `qubox_v2.experiments.config_builder` |
| `qubox.gates_legacy` | `qubox_v2.experiments.gates_legacy` |
| `qubox.logging_config` | `qubox_v2.core.logging` |
| `qubox.analysis.*` | `qubox_v2.analysis.*` |
| `qubox.simulation.*` | `qubox_v2.simulation.*` |
| `qubox.compile.*` | `qubox_v2.compile.*` |
| `qubox.calibration.*` | `qubox_v2.calibration.*` |
| `qubox.programs.*` | `qubox_v2.programs.*` |
| `qubox.experiments.*` | `qubox_v2.experiments.*` |

---

## 6. Recommended Migration Path

1. **Start with the shim** — `import qubox_v2.compat.legacy` at the top of notebooks
2. **Update imports** — Replace `qubox.*` with `qubox_v2.*` as you touch files
3. **Adopt SessionManager** — For new experiments, use `SessionManager` + experiment classes
4. **Use program categories** — Import from `programs.spectroscopy` etc. instead of the monolith
5. **Add calibration** — Use `CalibrationStore` for calibration data persistence
6. **Phase out legacy** — Eventually remove the compat shim and `cQED_Experiment` usage

---

*Generated for qubox_v2 v3.0.0 — Quantum Circuits Group*
