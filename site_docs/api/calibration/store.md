# CalibrationStore

JSON-backed, versioned parameter store with snapshot history.

## Overview

`CalibrationStore` is the central repository for all calibrated device parameters.
It persists to a JSON file and maintains a history of snapshots for auditability.

## Usage

```python
from qubox.calibration import CalibrationStore

# Load from file
store = CalibrationStore.load("samples/sampleA/cooldown/cd_2026_03/calibration.json")

# Access core parameters
store.cqed_params.qubit_freq      # float (Hz)
store.cqed_params.rr_freq         # float (Hz)
store.cqed_params.anharmonicity   # float (Hz)

# Access pulse calibrations
pi_pulse = store.get_pulse_calibration("x180")
pi_pulse.amp       # float
pi_pulse.duration  # int (ns)
pi_pulse.drag      # float (DRAG coefficient)

# Access readout calibration
readout = store.readout_calibration
readout.frequency  # float (Hz)
readout.threshold  # float
readout.rotation   # float (rad)
```

## Core API

| Method | Description |
|--------|-------------|
| `CalibrationStore.load(path)` | Load store from JSON file |
| `store.save()` | Save current state to file |
| `store.commit(patch, reason)` | Apply patch and save snapshot |
| `store.get_pulse_calibration(name)` | Get pulse parameters by name |
| `store.set_pulse_calibration(name, cal)` | Set pulse parameters |
| `store.snapshot()` | Create immutable snapshot of current state |
| `store.history` | List of historical snapshots |

## Data Models

### CQEDParams

```python
class CQEDParams(BaseModel):
    qubit_freq: float           # Qubit GE frequency (Hz)
    rr_freq: float              # Resonator frequency (Hz)
    anharmonicity: float        # Anharmonicity α (Hz)
    ef_freq: float | None       # EF transition frequency (Hz)
    chi: float | None           # Dispersive shift (Hz)
    t1: float | None            # T1 relaxation time (s)
    t2_ramsey: float | None     # T2* dephasing time (s)
    t2_echo: float | None       # T2E echo time (s)
    thermalization_time: int    # Wait time between shots (ns)
```

### PulseCalibration

```python
class PulseCalibration(BaseModel):
    amp: float                  # Pulse amplitude
    duration: int               # Duration (ns)
    drag: float = 0.0           # DRAG coefficient
    waveform: str = "gaussian"  # Waveform type
```

### ReadoutCalibration

```python
class ReadoutCalibration(BaseModel):
    frequency: float            # Readout frequency (Hz)
    amplitude: float            # Readout amplitude
    duration: int               # Readout duration (ns)
    threshold: float            # Discrimination threshold
    rotation: float             # IQ rotation angle (rad)
    fidelity: float | None      # Assignment fidelity
```

## Snapshot History

Every `commit()` creates an immutable snapshot:

```python
# List all snapshots
for snap in store.history:
    print(f"{snap.timestamp}: {snap.reason}")

# Load a specific snapshot
old_state = store.load_snapshot(snap.id)
```

## File Format

```json
{
    "version": "3.0.0",
    "cqed_params": {
        "qubit_freq": 4850000000.0,
        "rr_freq": 7200000000.0,
        "anharmonicity": -220000000.0
    },
    "pulses": {
        "x180": {"amp": 0.312, "duration": 40, "drag": 0.5},
        "x90": {"amp": 0.156, "duration": 40, "drag": 0.5}
    },
    "readout": {
        "frequency": 7200000000.0,
        "threshold": 0.0023
    },
    "metadata": {
        "last_updated": "2026-03-31T12:00:00Z"
    }
}
```
