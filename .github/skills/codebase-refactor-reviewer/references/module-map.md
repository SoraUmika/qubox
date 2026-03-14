# Module Map — qubox Architecture Boundaries

## Core Modules

| Module | Responsibility | Key Classes | Depends On |
|--------|---------------|-------------|------------|
| `core/` | Session identity, config, persistence, schemas | `ExperimentContext`, `SessionState`, `PersistencePolicy` | (none — leaf module) |
| `hardware/` | OPX+ / Octave abstraction | `ConfigEngine`, `HardwareController`, `ProgramRunner` | `core/` |
| `pulses/` | Pulse generation & registry | `PulseOperationManager`, `PulseRegistry`, `PulseFactory` | `core/` |
| `devices/` | External instrument management | `DeviceManager`, `ContextResolver`, `SampleRegistry` | `core/` |

## Experiment Layer

| Module | Responsibility | Key Classes | Depends On |
|--------|---------------|-------------|------------|
| `experiments/` | Experiment base + 30+ physics subclasses | `ExperimentRunner`, `ConfigBuilder` | `core/`, `hardware/`, `pulses/`, `devices/`, `analysis/` |
| `experiments/time_domain/` | Rabi, coherence, chevron, relaxation | Domain-specific runners | `experiments/base` |
| `experiments/spectroscopy/` | Qubit & resonator spectroscopy | Domain-specific runners | `experiments/base` |
| `experiments/cavity/` | Storage, Fock state experiments | Domain-specific runners | `experiments/base` |
| `experiments/tomography/` | Wigner, qubit, Fock tomography | Domain-specific runners | `experiments/base` |
| `experiments/calibration/` | Readout, reset, gate calibration | Domain-specific runners | `experiments/base` |

## Analysis & Calibration

| Module | Responsibility | Key Classes | Depends On |
|--------|---------------|-------------|------------|
| `analysis/` | Fitting, metrics, models, plotting | `Output`, `FitResult`, `cQED_attributes` | `core/` |
| `calibration/` | Orchestration pipeline | `CalibrationOrchestrator`, `Patch`, `CalibrationResult` | `core/`, `analysis/` |

## Advanced

| Module | Responsibility | Depends On |
|--------|---------------|------------|
| `compile/` | Ansatz optimization, GPU | `core/` |
| `gates/` | Gate system architecture | `core/`, `pulses/` |
| `simulation/` | QuTiP quantum simulation | `core/` |

## Dependency Rules

1. `core/` has NO inward dependencies — it is the leaf
2. `hardware/`, `pulses/`, `devices/` depend only on `core/`
3. `analysis/` depends only on `core/`
4. `calibration/` depends on `core/` + `analysis/`
5. `experiments/` may depend on everything except `compile/` and `simulation/`
6. `compile/` and `simulation/` are isolated advanced modules
