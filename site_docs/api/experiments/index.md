# Experiments

qubox ships 40+ experiment classes organized by physics domain. Every experiment follows
the `ExperimentBase` lifecycle: `configure → build_program → run → analyze`.

## Experiment Domains

| Domain | Description | Page |
|--------|-------------|------|
| **Spectroscopy** | Frequency-domain characterization | [Spectroscopy](spectroscopy.md) |
| **Time Domain** | Rabi, relaxation, coherence | [Time Domain](time-domain.md) |
| **Calibration** | Pulse calibration, benchmarking | [Calibration](calibration.md) |
| **Cavity / Storage** | Storage mode, dispersive, Fock | [Cavity](cavity.md) |
| **Tomography** | State reconstruction | [Tomography](tomography.md) |
| **SPA** | Parametric amplifier optimization | [SPA](spa.md) |

## Common Interface

All experiments inherit from `ExperimentBase` and follow this lifecycle:

```python
from qubox.experiments import PowerRabi

# Create experiment
exp = PowerRabi(session=session, a_min=0.0, a_max=0.5, da=0.005)

# Run on hardware
result = exp.run(n_avg=1000)

# Analyze results
analysis = exp.analyze(result)
print(analysis.fit_result)
```

### ExperimentBase Methods

| Method | Description |
|--------|-------------|
| `configure(**kwargs)` | Validate parameters, resolve from CalibrationStore |
| `build_program()` | Generate QUA program |
| `run(n_avg, ...)` | Execute on hardware, return raw data |
| `analyze(result)` | Fit data, produce FitResult + plots |

### Result Types

| Type | Description |
|------|-------------|
| `RunResult` | Raw data from hardware execution |
| `AnalysisResult` | Contains `FitResult`, plots, extracted parameters |
| `FitResult` | Fit parameters, uncertainties, `success` flag |
| `ProgramBuildResult` | Compiled QUA program + metadata |

## Template Access (Recommended)

Instead of importing experiment classes directly, use the session's experiment library:

```python
# Domain.experiment_name(kwargs)
result = session.exp.qubit.spectroscopy(f_min=4.5e9, f_max=5.5e9, df=0.5e6)
result = session.exp.qubit.power_rabi(a_min=0.0, a_max=0.5, da=0.005)
result = session.exp.resonator.spectroscopy(f_min=7.0e9, f_max=7.4e9)
result = session.exp.calibration.iq_blob(n_avg=5000)
```

## Custom Experiments

Extend `ExperimentBase` to create custom experiments:

```python
from qubox.experiments import ExperimentBase

class MyExperiment(ExperimentBase):
    def configure(self, **kwargs):
        self.param = kwargs.get("param", 1.0)

    def build_program(self):
        # Return QUA program
        ...

    def analyze(self, result):
        # Return AnalysisResult
        ...
```
