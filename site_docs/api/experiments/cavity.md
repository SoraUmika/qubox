# Cavity & Storage Experiments

Experiments for storage cavity characterization, Fock-state-resolved spectroscopy,
and quantum state preparation in the cavity mode.

## Storage Cavity Characterization

Sweep-based spectroscopy of the storage cavity mode.

```python
result = session.exp.cavity.storage_spectroscopy(
    f_min=5.0e9, f_max=6.0e9, df=0.5e6, n_avg=1000
)
```

**Extracts:** Storage cavity frequency ($f_s$), linewidth ($\kappa_s$)

**Notebook:** `21_storage_cavity_characterization.ipynb`

---

## Chi Ramsey

Ramsey experiment conditioned on photon number in the storage cavity
to extract the dispersive shift $\chi$.

```python
result = session.exp.cavity.chi_ramsey(
    t_min=100, t_max=10000, n_points=50, n_avg=2000
)
```

**Extracts:** Dispersive shift ($\chi$) per photon number

---

## Fock-Resolved Spectroscopy

Qubit spectroscopy resolved by photon number in the cavity.

```python
result = session.exp.cavity.fock_resolved_spectroscopy(
    f_min=4.7e9, f_max=4.9e9, df=0.1e6,
    n_photons=[0, 1, 2, 3],
    n_avg=2000
)
```

**Extracts:** Photon-number-dependent qubit frequencies ($f_{01}^{(n)}$)

**Notebook:** `22_fock_resolved_experiments.ipynb`

---

## Quantum State Preparation

Prepare and verify Fock states and superpositions in the cavity.

```python
result = session.exp.cavity.state_preparation(
    target_state="fock_1",
    verification_method="wigner",
    n_avg=5000
)
```

**Notebook:** `23_quantum_state_preparation.ipynb`

---

## Free Evolution Tomography

Monitor free evolution of a prepared cavity state over time.

**Notebook:** `24_free_evolution_tomography.ipynb`

---

## Cluster State Evolution

Prepare and measure cluster-state-like entangled states.

**Notebook:** `27_cluster_state_evolution.ipynb`
