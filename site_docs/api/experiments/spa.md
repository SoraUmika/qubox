# SPA Experiments

Superconducting Parametric Amplifier (SPA) optimization experiments.

## Flux Sweep

Sweep the flux bias to find the SPA operating point.

```python
result = session.exp.spa.flux_sweep(
    flux_min=-0.5, flux_max=0.5, n_points=101,
    n_avg=500
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `flux_min` | `float` | Minimum flux bias (V) |
| `flux_max` | `float` | Maximum flux bias (V) |
| `n_points` | `int` | Number of flux points |
| `n_avg` | `int` | Averages |

**Extracts:** Optimal flux bias point, gain-vs-flux profile

**Notebook:** `19_spa_optimization.ipynb`

---

## Pump Optimization

Optimize the SPA pump frequency and power for maximum gain.

```python
result = session.exp.spa.pump_optimization(
    f_pump_min=11.0e9, f_pump_max=12.0e9, df=5e6,
    p_pump_min=-20, p_pump_max=0, n_powers=21,
    n_avg=500
)
```

**Extracts:** Optimal pump frequency, optimal pump power, gain profile

**Notebook:** `19_spa_optimization.ipynb`

---

## Gain Characterization

Measure amplifier gain as a function of signal frequency.

```python
result = session.exp.spa.gain_vs_signal(
    f_signal_min=6.5e9, f_signal_max=7.5e9, df=1e6,
    n_avg=1000
)
```

**Extracts:** Gain bandwidth, 3dB bandwidth, gain ripple
