# Spectroscopy Experiments

Frequency-domain characterization experiments for qubits and resonators.

## Resonator Spectroscopy

Sweep the readout frequency to find the resonator resonance.

```python
result = session.exp.resonator.spectroscopy(
    f_min=7.0e9, f_max=7.4e9, df=0.1e6, n_avg=1000
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `f_min` | `float` | Start frequency (Hz) |
| `f_max` | `float` | Stop frequency (Hz) |
| `df` | `float` | Frequency step (Hz) |
| `n_avg` | `int` | Number of averages |

**Extracts:** Resonator frequency ($f_r$), loaded quality factor ($Q_L$)

**Notebook:** `03_resonator_spectroscopy.ipynb`

---

## Resonator Power Chevron

2D sweep of readout frequency vs. power to map the resonator response.

```python
result = session.exp.resonator.power_chevron(
    f_min=7.1e9, f_max=7.3e9, df=0.2e6,
    a_min=-30, a_max=0, n_powers=31,
    n_avg=500
)
```

**Extracts:** Power-dependent resonator shift, optimal readout power

**Notebook:** `04_resonator_power_chevron.ipynb`

---

## Qubit Spectroscopy

Sweep the drive frequency to find the qubit $ |g\rangle \leftrightarrow |e\rangle $ transition.

```python
result = session.exp.qubit.spectroscopy(
    f_min=4.5e9, f_max=5.5e9, df=0.5e6, n_avg=1000
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `f_min` | `float` | Start frequency (Hz) |
| `f_max` | `float` | Stop frequency (Hz) |
| `df` | `float` | Frequency step (Hz) |
| `n_avg` | `int` | Number of averages |
| `saturation_amp` | `float` | Drive amplitude (optional) |
| `saturation_len` | `int` | Drive duration in ns (optional) |

**Extracts:** Qubit frequency ($f_{01}$)

**Notebook:** `05_qubit_spectroscopy_pulse_calibration.ipynb`

---

## EF Spectroscopy

Find the $ |e\rangle \leftrightarrow |f\rangle $ transition for qutrit work.

```python
result = session.exp.qubit.ef_spectroscopy(
    f_min=4.2e9, f_max=4.7e9, df=0.5e6, n_avg=1000
)
```

**Extracts:** EF transition frequency ($f_{12}$), anharmonicity ($\alpha = f_{12} - f_{01}$)

**Notebook:** `09_qutrit_spectroscopy_calibration.ipynb`

---

## CW Diagnostics

Continuous-wave spectroscopy for rapid diagnostics:

```python
result = session.exp.qubit.cw_spectroscopy(
    f_min=4.0e9, f_max=6.0e9, df=1e6, n_avg=100
)
```

**Notebook:** `07_cw_diagnostics.ipynb`

---

## Dispersive Shift

Measure the dispersive shift $2\chi$ between qubit and resonator:

```python
result = session.exp.cavity.dispersive_shift(
    f_min=7.1e9, f_max=7.3e9, df=0.05e6, n_avg=2000
)
```

**Extracts:** Dispersive shift ($2\chi$), qubit-state-dependent resonator frequencies

**Notebook:** `13_dispersive_shift_measurement.ipynb`
