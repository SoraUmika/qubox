# Fitting

Robust model fitting with retry strategies and global optimization fallback.

## generalized_fit()

The primary fitting interface:

```python
from qubox_tools.fitting.routines import generalized_fit

fit = generalized_fit(
    x_data=frequencies,
    y_data=amplitude,
    model="lorentzian",
    p0=None,         # Auto-estimate initial params
    bounds=None,     # Auto-set physical bounds
    method="leastsq",
)

print(fit.params)     # {'center': 4.85e9, 'width': 2e6, 'amp': 0.8}
print(fit.success)    # True
print(fit.r_squared)  # 0.998
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `x_data` | `np.ndarray` | required | Independent variable |
| `y_data` | `np.ndarray` | required | Dependent variable |
| `model` | `str \| callable` | required | Model name or function |
| `p0` | `dict \| None` | `None` | Initial parameter guesses |
| `bounds` | `dict \| None` | `None` | Parameter bounds |
| `method` | `str` | `"leastsq"` | Fitting method |
| `retry` | `bool` | `True` | Enable retry with global optimizer |
| `max_retries` | `int` | `3` | Maximum retry attempts |

### Return: FitResult

| Field | Type | Description |
|-------|------|-------------|
| `params` | `dict[str, float]` | Fitted parameter values |
| `uncertainties` | `dict[str, float]` | Parameter uncertainties |
| `success` | `bool` | Whether the fit converged |
| `r_squared` | `float` | Goodness of fit |
| `residuals` | `np.ndarray` | Fit residuals |
| `model_name` | `str` | Name of the model used |

## Built-in Models

### Standard Models (`qubox_tools.fitting.models`)

| Model | Function | Parameters |
|-------|----------|-----------|
| Lorentzian | $\frac{A \gamma^2}{(x - x_0)^2 + \gamma^2} + B$ | `center`, `width`, `amp`, `offset` |
| Gaussian | $A \exp\left(-\frac{(x-x_0)^2}{2\sigma^2}\right) + B$ | `center`, `sigma`, `amp`, `offset` |
| Voigt | Convolution of Lorentzian and Gaussian | `center`, `sigma`, `gamma`, `amp` |
| Exponential decay | $A e^{-x/\tau} + B$ | `amplitude`, `tau`, `offset` |
| Damped cosine | $A e^{-x/\tau} \cos(2\pi f x + \phi) + B$ | `amplitude`, `tau`, `freq`, `phase`, `offset` |
| Sine | $A \sin(2\pi f x + \phi) + B$ | `amplitude`, `freq`, `phase`, `offset` |
| Linear | $mx + b$ | `slope`, `intercept` |
| Polynomial | $\sum a_n x^n$ | `coefficients` |
| Double Lorentzian | Sum of two Lorentzians | 8 parameters |
| Fano | Fano resonance lineshape | `center`, `width`, `q`, `amp` |

### cQED Models (`qubox_tools.fitting.cqed`)

| Model | Use Case |
|-------|----------|
| `rabi_model` | Rabi oscillation fitting |
| `t1_model` | Exponential T1 decay |
| `t2_ramsey_model` | Ramsey fringe with detuning |
| `t2_echo_model` | Echo decay |
| `dispersive_readout_model` | Dispersive readout response |

## Calibration Bridge (`qubox_tools.fitting.calibration`)

Bridge between fit results and the CalibrationStore:

```python
from qubox_tools.fitting.calibration import fit_to_calibration

# Convert FitResult → CalibrationStore update
cal_update = fit_to_calibration(fit_result, rule="pi_amp")
```
