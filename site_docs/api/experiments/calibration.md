# Calibration Experiments

Pulse calibration, readout optimization, and benchmarking experiments.

## IQ Blob Calibration

Characterize the readout by collecting IQ shots for ground and excited states.

```python
result = session.exp.calibration.iq_blob(n_avg=5000)
```

**Extracts:** IQ centers, rotation angle, readout fidelity, threshold

**Notebook:** `16_readout_calibration.ipynb`

---

## AllXY

Run the AllXY pulse sequence to diagnose systematic errors.

```python
result = session.exp.calibration.allxy(n_avg=1000)
```

**Extracts:** Pulse error diagnosis (amplitude, DRAG, detuning, leakage)

---

## DRAG Calibration

Optimize DRAG ($\alpha$) parameter to minimize leakage to $|f\rangle$.

```python
result = session.exp.calibration.drag_calibration(
    alpha_min=-2.0, alpha_max=2.0, n_points=41, n_avg=1000
)
```

**Extracts:** Optimal DRAG coefficient ($\alpha$)

**Notebook:** `14_gate_calibration_benchmarking.ipynb`

---

## Randomized Benchmarking (RB)

Clifford-based randomized benchmarking for gate fidelity estimation.

```python
result = session.exp.calibration.rb(
    depths=[1, 2, 4, 8, 16, 32, 64, 128],
    n_random=30, n_avg=500
)
```

**Extracts:** Error per Clifford (EPC), average gate fidelity

**Notebook:** `14_gate_calibration_benchmarking.ipynb`

---

## Readout Optimization

Optimize readout parameters (frequency, amplitude, duration).

```python
result = session.exp.calibration.readout_optimization(
    f_min=7.15e9, f_max=7.25e9, df=0.1e6,
    n_avg=2000
)
```

**Extracts:** Optimal readout frequency, SNR

---

## Readout Bayesian Optimization

Use Bayesian optimization for multi-parameter readout tuning.

```python
result = session.exp.calibration.bayesian_readout(
    n_iterations=50, n_avg=1000
)
```

**Notebook:** `17_readout_bayesian_optimization.ipynb`

---

## Active Reset Benchmarking

Characterize and benchmark active qubit reset protocols.

```python
result = session.exp.calibration.active_reset_benchmark(
    n_avg=2000, reset_rounds=3
)
```

**Notebook:** `18_active_reset_benchmarking.ipynb`

---

## Readout Leakage Benchmarking

Measure readout-induced leakage to $|f\rangle$.

**Notebook:** `20_readout_leakage_benchmarking.ipynb`
