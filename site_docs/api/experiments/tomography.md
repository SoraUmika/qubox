# Tomography Experiments

Quantum state reconstruction and verification.

## Qubit State Tomography

Full single-qubit state tomography via Pauli measurements.

```python
result = session.exp.tomography.state_tomography(
    preparation="x90",
    n_avg=5000
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `preparation` | `str` | Preparation pulse sequence name |
| `n_avg` | `int` | Averages per measurement basis |

**Extracts:** Bloch vector components ($\langle X \rangle$, $\langle Y \rangle$, $\langle Z \rangle$), state fidelity

**Notebook:** `15_qubit_state_tomography.ipynb`

---

## Wigner Tomography

Reconstruct the Wigner function of a cavity state via displaced parity measurements.

```python
result = session.exp.tomography.wigner(
    alpha_max=3.0,
    n_points=41,
    n_avg=5000
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `alpha_max` | `float` | Maximum displacement amplitude |
| `n_points` | `int` | Grid resolution per axis |
| `n_avg` | `int` | Averages per displacement point |

**Extracts:** $W(\alpha)$ on a 2D grid, state purity, photon number distribution

---

## SNAP Gate Verification

Apply SNAP (Selective Number-dependent Arbitrary Phase) gates and verify
the resulting state.

```python
result = session.exp.tomography.snap_verify(
    phases=[0, 3.14, 0, 0],  # Phase per Fock state
    verification="wigner",
    n_avg=5000
)
```

**Extracts:** Post-SNAP Wigner function, gate fidelity estimate

---

## SQR Calibration Verification

Context-aware Selective Qubit Rotation (SQR) gate calibration and verification.

**Notebook:** `25_context_aware_sqr_calibration.ipynb`
