# Plotting

Publication-quality visualizations for cQED data.

## Common Plots (`qubox_tools.plotting.common`)

### 2D Heatmap

```python
from qubox_tools.plotting.common import plot_heatmap

fig = plot_heatmap(
    x=frequencies,
    y=amplitudes,
    z=data_2d,
    xlabel="Frequency (GHz)",
    ylabel="Amplitude",
    title="Spectroscopy Chevron",
    colorbar_label="Signal (V)",
    cmap="RdBu_r",
)
```

## cQED Plots (`qubox_tools.plotting.cqed`)

### IQ Scatter

```python
from qubox_tools.plotting.cqed import plot_iq_scatter

fig = plot_iq_scatter(
    I_ground, Q_ground,
    I_excited, Q_excited,
    threshold_line=True,
    rotation_angle=0.42,
)
```

### Bloch Sphere

```python
from qubox_tools.plotting.cqed import plot_bloch_sphere

fig = plot_bloch_sphere(
    bloch_vector=[0.5, 0.3, 0.8],
    title="Qubit State",
)
```

### Chevron Plot

```python
from qubox_tools.plotting.cqed import plot_chevron

fig = plot_chevron(
    frequencies=freq_axis,
    times=time_axis,
    data=chevron_data,
    qubit_freq=4.85e9,
)
```

### Tomography Visualization

```python
from qubox_tools.plotting.cqed import (
    plot_wigner,
    plot_density_matrix,
    plot_state_histogram,
)

# Wigner function
fig = plot_wigner(wigner_data, alpha_range=(-3, 3))

# Density matrix bar plot
fig = plot_density_matrix(rho, basis_labels=["g", "e", "f"])

# State population histogram
fig = plot_state_histogram(populations, state_labels=["0", "1", "2"])
```

## Integration with Experiments

Experiment `analyze()` methods use these plotting functions internally. You can also
call them directly for custom visualization of saved data:

```python
from qubox_tools.data.containers import Output
from qubox_tools.plotting.cqed import plot_iq_scatter

data = Output.load("results/iq_blob_001.npz")
fig = plot_iq_scatter(data.get("I_g"), data.get("Q_g"),
                      data.get("I_e"), data.get("Q_e"))
```
