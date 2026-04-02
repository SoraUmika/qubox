# Time-Domain Experiments

Rabi oscillations, relaxation, coherence, and chevron measurements.

## Power Rabi

Sweep drive amplitude to calibrate $\pi$ pulse amplitude.

```python
result = session.exp.qubit.power_rabi(
    a_min=0.0, a_max=0.5, da=0.005, n_avg=1000
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `a_min` | `float` | Minimum amplitude |
| `a_max` | `float` | Maximum amplitude |
| `da` | `float` | Amplitude step |
| `n_avg` | `int` | Averages |

**Extracts:** $\pi$ pulse amplitude, $\pi/2$ pulse amplitude

**Notebook:** `05_qubit_spectroscopy_pulse_calibration.ipynb`

---

## Time Rabi

Sweep drive duration at fixed amplitude.

```python
result = session.exp.qubit.time_rabi(
    t_min=4, t_max=200, dt=4, n_avg=1000
)
```

**Extracts:** $\pi$ pulse duration

---

## T1 (Energy Relaxation)

Measure the qubit energy relaxation time.

```python
result = session.exp.qubit.t1(
    t_min=100, t_max=50000, n_points=100, n_avg=2000
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `t_min` | `int` | Minimum wait time (ns) |
| `t_max` | `int` | Maximum wait time (ns) |
| `n_points` | `int` | Number of time points |
| `n_avg` | `int` | Averages |

**Extracts:** $T_1$ relaxation time

**Notebook:** `06_coherence_experiments.ipynb`

---

## T2 Ramsey (Dephasing)

Ramsey fringe experiment to measure $T_2^*$.

```python
result = session.exp.qubit.t2_ramsey(
    t_min=100, t_max=20000, n_points=100,
    detuning=0.5e6, n_avg=2000
)
```

**Extracts:** $T_2^*$ dephasing time, frequency detuning

---

## T2 Echo (Hahn Echo)

Spin echo experiment for $T_{2E}$ measurement.

```python
result = session.exp.qubit.t2_echo(
    t_min=100, t_max=50000, n_points=100, n_avg=2000
)
```

**Extracts:** $T_{2E}$ echo time

---

## Chevron

2D sweep of drive frequency and amplitude/duration for qubit characterization.

```python
result = session.exp.qubit.chevron(
    f_min=4.8e9, f_max=4.9e9, df=0.5e6,
    t_min=4, t_max=200, dt=4,
    n_avg=500
)
```

**Extracts:** Resonance conditions, coupling strengths

**Notebook:** `12_chevron_experiments.ipynb`

---

## Sideband Transitions

Probe sideband transitions in the qubit-cavity system.

```python
result = session.exp.qubit.sideband_transition(
    f_min=4.0e9, f_max=5.0e9, df=0.5e6,
    drive_element="sideband",
    n_avg=1000
)
```

**Notebook:** `10_sideband_transitions.ipynb`

---

## Coherence 2D Pump Sweeps

Two-dimensional pump frequency/power sweeps for coherence characterization.

**Notebook:** `11_coherence_2d_pump_sweeps.ipynb`
