# Algorithms

Signal processing, peak finding, post-processing, and data transforms.

## Peak Finding (`qubox_tools.algorithms.core`)

```python
from qubox_tools.algorithms.core import find_peaks, estimate_threshold

# Find spectroscopy peaks
peaks = find_peaks(
    x_data=frequencies,
    y_data=amplitude,
    prominence=0.1,
    min_distance=1e6,  # Hz
)
# peaks = [{'index': 42, 'frequency': 4.85e9, 'amplitude': 0.95}, ...]

# Estimate discrimination threshold
threshold = estimate_threshold(I_ground, I_excited)
```

## Post-Processing (`qubox_tools.algorithms.post_process`)

```python
from qubox_tools.algorithms.post_process import (
    demodulate, readout_error_correction
)

# Software demodulation
demod_data = demodulate(raw_adc, freq_if=50e6, sample_rate=1e9)

# Readout error mitigation
corrected = readout_error_correction(
    raw_counts, confusion_matrix=[[0.98, 0.02], [0.03, 0.97]]
)
```

## Transforms (`qubox_tools.algorithms.transforms`)

IQ data manipulation:

```python
from qubox_tools.algorithms.transforms import (
    iq_to_amplitude_phase,
    rotate_iq,
    project_iq,
    compute_snr,
)

# IQ → amplitude + phase
amp, phase = iq_to_amplitude_phase(I, Q)

# Rotate IQ plane
I_rot, Q_rot = rotate_iq(I, Q, angle=0.42)  # radians

# Project onto discrimination axis
projected = project_iq(I, Q, angle=0.42)

# Signal-to-noise ratio
snr = compute_snr(I_ground, Q_ground, I_excited, Q_excited)
```

## Post-Selection (`qubox_tools.algorithms.post_selection`)

5 post-selection policies for conditional data filtering:

```python
from qubox_tools.algorithms.post_selection import PostSelectionConfig

config = PostSelectionConfig(
    policy="threshold",       # or "gaussian", "boundary", "heralded", "custom"
    threshold=0.003,
    axis="I",
)

mask = config.apply(I_data, Q_data)
filtered_I = I_data[mask]
```

| Policy | Description |
|--------|-------------|
| `"threshold"` | Simple threshold on one quadrature |
| `"gaussian"` | Gaussian mixture model classification |
| `"boundary"` | Linear boundary in IQ plane |
| `"heralded"` | Post-select on herald measurement |
| `"custom"` | User-provided filter function |

## Metrics (`qubox_tools.algorithms.metrics`)

Statistical analysis tools:

```python
from qubox_tools.algorithms.metrics import (
    wilson_confidence_interval,
    gaussianity_score,
    assignment_fidelity,
)

# Wilson score confidence interval
ci = wilson_confidence_interval(n_success=980, n_total=1000, confidence=0.95)

# Check Gaussianity of IQ distribution
score = gaussianity_score(I_data, Q_data)

# Readout assignment fidelity
fidelity = assignment_fidelity(I_ground, Q_ground, I_excited, Q_excited)
```
