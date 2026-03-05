# Parameter Flow Map — cQED Calibration Dependencies

## Calibration Dependency Chain

```
Resonator Spectroscopy
  └─→ resonator_frequency, resonator_kappa
       │
       ▼
Qubit Spectroscopy
  └─→ qubit_frequency, anharmonicity
       │
       ▼
Rabi Oscillation
  └─→ pi_pulse_amplitude, pi_pulse_duration
       │
       ├──→ Readout Optimization
       │      └─→ readout_amplitude, readout_duration, threshold
       │
       ├──→ T1 Relaxation
       │      └─→ T1
       │
       ▼
Ramsey Experiment
  └─→ qubit_frequency (refined), T2_star
       │
       ▼
Echo Experiment
  └─→ T2_echo
       │
       ▼
Gate Calibration
  └─→ gate_fidelity, DRAG_alpha, DRAG_delta
```

## Key Parameters by Experiment

| Experiment | Produces | Consumes |
|-----------|----------|----------|
| Resonator Spectroscopy | `resonator_frequency`, `resonator_kappa` | (none) |
| Qubit Spectroscopy | `qubit_frequency`, `anharmonicity` | `resonator_frequency` |
| Rabi | `pi_pulse_amplitude`, `pi_pulse_duration` | `qubit_frequency` |
| Ramsey | `qubit_frequency` (refined), `T2_star` | `pi_pulse_amplitude` |
| T1 Relaxation | `T1` | `pi_pulse_amplitude` |
| Echo | `T2_echo` | `pi_pulse_amplitude` |
| Readout Optimization | `readout_amplitude`, `readout_duration`, `threshold` | `pi_pulse_amplitude` |
| Gate Calibration | `gate_fidelity`, `DRAG_alpha` | All of the above |

## Session State Key Conventions

Parameters are stored in session state under structured paths:
- `qubit.{qubit_id}.frequency` → qubit frequency in Hz
- `qubit.{qubit_id}.anharmonicity` → anharmonicity in Hz
- `qubit.{qubit_id}.T1` → relaxation time in ns
- `qubit.{qubit_id}.T2_star` → dephasing time in ns
- `resonator.{resonator_id}.frequency` → resonator frequency in Hz
- `readout.{qubit_id}.amplitude` → readout amplitude (V)
- `readout.{qubit_id}.threshold` → classification threshold
- `pulse.{qubit_id}.pi.amplitude` → pi pulse amplitude (V)
- `pulse.{qubit_id}.pi.duration` → pi pulse duration (ns)
