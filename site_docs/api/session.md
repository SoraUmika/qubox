# Session

`Session` is the primary user entry point for qubox. It manages the hardware connection,
calibration store, experiment templates, and the full experiment lifecycle.

## Creating a Session

```python
from qubox import Session

session = Session.open(
    sample_id="sampleA",
    cooldown_id="cd_2026_03",
    registry_base="./samples",
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `sample_id` | `str` | Sample identifier used for data and calibration lookup |
| `cooldown_id` | `str` | Cooldown folder name |
| `registry_base` | `str \| Path` | Root directory for sample data |
| `qop_ip` | `str` | IP address of the QM OPX+ server |
| `cluster_name` | `str` | QM cluster name |

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `session.store` | `CalibrationStore` | Live calibration store |
| `session.config` | `dict` | Current QM hardware config |
| `session.state` | `SessionState` | Immutable runtime snapshot |
| `session.exp` | `ExperimentLibrary` | Template experiment access |
| `session.ops` | `OperationLibrary` | Operation library |
| `session.metadata` | `DeviceMetadata` | Frozen device parameters |
| `session.qm` | `QuantumMachine` | Active QM connection |
| `session.qmm` | `QuantumMachinesManager` | QM manager instance |

## Running Experiments

### Template-Based (Recommended)

```python
# Experiments are organized by domain
result = session.exp.qubit.spectroscopy(
    f_min=4.5e9, f_max=5.5e9, df=0.5e6,
    n_avg=1000,
)

result = session.exp.qubit.power_rabi(
    a_min=0.0, a_max=0.5, da=0.005,
    n_avg=500,
)
```

### Direct Instantiation

```python
from qubox.experiments import QubitSpectroscopy

exp = QubitSpectroscopy(session=session, f_min=4.5e9, f_max=5.5e9, df=0.5e6)
result = exp.run(n_avg=1000)
analysis = exp.analyze(result)
```

## Experiment Domains

| Accessor | Domain | Examples |
|----------|--------|----------|
| `session.exp.qubit` | Qubit experiments | `spectroscopy`, `power_rabi`, `t1`, `t2_ramsey` |
| `session.exp.resonator` | Resonator experiments | `spectroscopy`, `power_chevron` |
| `session.exp.readout` | Readout experiments | `trace`, `iq_blobs`, `butterfly` |
| `session.exp.calibration` | Calibration | `all_xy`, `drag`, `rb` |
| `session.exp.storage` | Cavity / storage | `spectroscopy`, `chi_ramsey`, `fock_resolved` |
| `session.exp.tomography` | Tomography | `qubit_state`, `wigner` |
| `session.exp.reset` | Active reset | `active` |

## Session Lifecycle

```python
# Open session (connects to hardware)
session = Session.open(...)

# Work with experiments...
result = session.exp.qubit.spectroscopy(...)

# Close session (releases hardware)
session.close()
```

!!! tip "Context Manager"
    ```python
    with Session.open(...) as session:
        result = session.exp.qubit.spectroscopy(...)
    # Automatically closes
    ```

## DeviceMetadata Access

`session.metadata` returns a `DeviceMetadata` frozen dataclass that provides clean property access
to calibrated device parameters:

```python
meta = session.metadata
meta.qubit_freq_hz         # float — qubit frequency
meta.resonator_freq_hz     # float — resonator frequency
meta.pi_amp                # float — pi pulse amplitude
meta.ef_freq_hz            # float — EF transition frequency
meta.qubit_lo_freq         # float — qubit LO frequency
```

!!! warning "Deprecation"
    Direct attribute forwarding via `session.<attr>` (e.g., `session.qubit_freq`) is deprecated.
    Use `session.metadata.<attr>` instead.
