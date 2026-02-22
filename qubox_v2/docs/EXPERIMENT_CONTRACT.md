# Experiment Contract

**Version**: 1.0.0
**Date**: 2026-02-21
**Status**: Governing Document

---

## 1. Required Interface

Every experiment class must inherit from `ExperimentBase` and implement:

```python
class MyExperiment(ExperimentBase):
    def run(self, **params) -> RunResult:
        """Execute hardware acquisition. Returns raw data."""
        ...

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        """Process raw data into fitted parameters and metrics."""
        ...

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        """Visualize analysis results."""
        ...
```

### 1.1 `run()` Contract

- Must return a `RunResult` from `self.run_program()`.
- Must not modify `calibration.json`.
- Must not create hidden pulse operations. All required pulses must be registered before `run()` or passed as parameters.
- Must call `self.set_standard_frequencies()` if the experiment depends on calibrated element frequencies.
- Must document all parameters with types and defaults.
- Hardware state changes (frequency sets, gain changes) are allowed within `run()` but must not persist beyond the call unless the experiment's explicit purpose is to configure hardware.

### 1.2 `analyze()` Contract

- Must accept a `RunResult` and return an `AnalysisResult`.
- Must be **idempotent**: calling `analyze(result)` twice produces the same `AnalysisResult`.
- Must not execute hardware operations.
- Must populate `metrics` dict with all extracted scalar quantities.
- Must populate `fit` or `fits` if curve fitting was performed.
- If `update_calibration=True`, must use `self.guarded_calibration_commit()` with appropriate validation gates.
- Must never silently swallow fit failures. If fitting fails, set `metadata["diagnostics"]` with the reason and return partial metrics.

### 1.3 `plot()` Contract

- Must accept an `AnalysisResult` and optional `matplotlib.axes.Axes`.
- Must create its own figure if `ax=None`.
- Must not modify the analysis result.
- Must not execute hardware operations.
- Must call `plt.tight_layout()` and `plt.show()` for standalone figures.
- Must return the figure object for programmatic use.

---

## 2. Return Data Formats

### 2.1 RunResult

Produced by `ProgramRunner.run_program()`:

```python
@dataclass
class RunResult:
    output: Output              # Dict-like access to stream processing results
    metadata: dict[str, Any]    # {n_avg, execution_time, program_hash, ...}
    success: bool
```

**Output key naming conventions** (must match legacy):

| Key Pattern | Meaning | Example |
|------------|---------|---------|
| `I`, `Q` | Demodulated in-phase/quadrature | Single-point readout |
| `I1`, `Q1`, `I2`, `Q2` | Multi-readout channels | DRAG calibration |
| `II`, `IQ`, `QI`, `QQ` | Dual-demod 4-channel | Sliced integration |
| `S` | Complex signal `I + jQ` | Post-processed default |
| `g_trace`, `e_trace` | Ground/excited state traces | Weight optimization |
| `iteration` | Progress counter stream | Averaging loop index |
| `gains`, `frequencies`, `delays` | Sweep axis arrays | Rabi, spectroscopy, T1 |

### 2.2 AnalysisResult

```python
@dataclass
class AnalysisResult:
    data: dict[str, Any]        # Processed arrays (from RunResult.output)
    fit: FitResult | None       # Primary curve fit
    fits: dict[str, FitResult]  # Named collection for multi-fit
    metrics: dict[str, Any]     # Scalar quantities
    source: RunResult | None    # Back-reference
    metadata: dict[str, Any]    # Freeform metadata
```

**Metrics naming conventions:**

| Key | Type | Experiment |
|-----|------|-----------|
| `f0` | float (Hz) | ResonatorSpectroscopy |
| `kappa` | float (Hz) | ResonatorSpectroscopy |
| `g_pi` | float | PowerRabi |
| `T1` | float (ns) | T1Relaxation |
| `T2_star` | float (ns) | T2Ramsey |
| `T2_echo` | float (ns) | T2Echo |
| `fidelity` | float (0-1) | ReadoutGEDiscrimination |
| `threshold` | float | ReadoutGEDiscrimination |
| `angle` | float (rad) | ReadoutGEDiscrimination |
| `F` | float (0-1) | ReadoutButterflyMeasurement |
| `Q` | float (0-1) | ReadoutButterflyMeasurement |
| `V` | float | ReadoutButterflyMeasurement |
| `optimal_alpha` | float | DRAGCalibration |
| `gate_error` | float | AllXY |
| `trace_length` | int | ReadoutWeightsOptimization |
| `ge_diff_norm_max` | float | ReadoutWeightsOptimization |

---

## 3. Element and Operation Validation

### 3.1 Required Elements

Every experiment must validate that its required elements exist before program construction:

```python
# In run():
attr = self.attr
assert attr.qb_el in self.hw.get_available_elements()
assert attr.ro_el in self.hw.get_available_elements()
```

### 3.2 Required Operations

Experiments must not assume operations exist. Check via `PulseOperationManager`:

```python
pulseOp = self.pulse_mgr.get_pulseOp_by_element_op(element, op_name)
if pulseOp is None:
    raise RuntimeError(
        f"No pulse registered for ({element!r}, {op_name!r}). "
        "Register the operation before running this experiment."
    )
```

### 3.3 Minimum Element Operations

Every element must have at least:

| Operation | Purpose |
|-----------|---------|
| `const` | Constant-amplitude drive (used by spectroscopy) |
| `zero` | Zero-amplitude placeholder (used by idle/wait periods) |

For qubit elements, additionally:

| Operation | Purpose |
|-----------|---------|
| `x180` | Pi rotation around X |
| `x90` | Pi/2 rotation around X |
| `y180` | Pi rotation around Y |
| `y90` | Pi/2 rotation around Y |

These must be registered before running calibration experiments that reference them.

---

## 4. State Preparation Rules

### 4.1 General Rule

**State preparation is notebook-driven.** Experiments must not generate internal state-prep sequences unless explicitly parameterized.

### 4.2 Fock-Resolved Experiments

Fock-resolved experiments (`FockResolvedT1`, `FockResolvedRamsey`, `FockResolvedPowerRabi`) must:

1. Accept `state_prep` as an explicit parameter (a QUA callable or None).
2. Accept `fock_disps` as an explicit list of displacement operation names.
3. Validate that all displacement operations exist before program construction using `validate_displacement_ops()`.
4. Raise `RuntimeError` with remediation instructions if operations are missing.

```python
# Correct usage (notebook):
from qubox_v2.tools.generators import ensure_displacement_ops

ensure_displacement_ops(session.pulse_mgr, element="storage", n_max=3)
session.burn_pulses()

result = fock_t1.run(
    fock_fqs=fock_fqs,
    fock_disps=["disp_n0", "disp_n1", "disp_n2"],
    state_prep=my_prep_function,  # user-defined
)
```

### 4.3 What Experiments Must Not Do

- Generate QUA `play()` calls for state preparation unless the `state_prep` parameter is provided.
- Auto-create displacement or rotation pulses internally.
- Assume a specific initial state (ground, excited, Fock) without the user explicitly preparing it.

---

## 5. Analysis Separation

### 5.1 Principle

Analysis must be **separable** from acquisition. Given a `RunResult`, `analyze()` must produce the same `AnalysisResult` regardless of:

- Whether the hardware is still connected.
- Whether other experiments have run since.
- How many times `analyze()` is called.

### 5.2 Implications

- `analyze()` must not call `self.hw` for any measurement operation.
- `analyze()` may read `self.attr` for context (element names, frequencies) but must not modify it.
- `analyze()` may read `self.pulse_mgr` for weight mappings but must not modify pulse definitions (except for weight registration in `ReadoutWeightsOptimization`, which is an explicit side effect documented in the method).

### 5.3 Side Effects in analyze()

The following side effects are **permitted** in `analyze()`:

| Experiment | Side Effect | Justification |
|-----------|------------|---------------|
| `ReadoutWeightsOptimization` | Register optimized integration weights in POM | The entire purpose is to compute and register weights |
| `ReadoutGEDiscrimination` | Update rotated integration weights in POM | Rotated weights derived from discrimination angle |

All other side effects in `analyze()` require explicit documentation and justification.

---

## 6. Registration Requirements

### 6.1 Module Registration

Every experiment class must be:

1. Defined in the appropriate subpackage under `experiments/`.
2. Exported in the subpackage's `__init__.py`.
3. Re-exported in `experiments/__init__.py`.
4. Listed in `experiments/__init__.__all__`.

### 6.2 Naming Conventions

| Convention | Example | Rule |
|-----------|---------|------|
| Class name | `ReadoutGEDiscrimination` | PascalCase, descriptive |
| Module file | `readout.py` | lowercase, grouped by domain |
| Metric keys | `ge_diff_norm_max` | snake_case |
| Output keys | `g_trace`, `I1` | Legacy naming preserved exactly |
| Pulse ops | `x180`, `disp_n0` | Legacy naming preserved exactly |

---

## 7. Error Handling

### 7.1 Fail-Fast

Experiments must fail fast with actionable error messages:

```python
# Good: specific, actionable
raise RuntimeError(
    f"No pulse registered for (element='storage', op='disp_n0'). "
    "Run ensure_displacement_ops() before this experiment. "
    "See notebook Section 8.4b."
)

# Bad: generic
raise ValueError("Missing pulse")
```

### 7.2 Graceful Degradation in analyze()

If analysis partially succeeds (e.g., one of two fits fails), return the partial result with diagnostics:

```python
if fit_failed:
    metadata["diagnostics"] = f"Fit failed: {error_msg}"
    _logger.warning("Fit failed for %s: %s", self.__class__.__name__, error_msg)
    # Return partial metrics (what we could compute)
    return AnalysisResult.from_run(result, metrics=partial_metrics, metadata=metadata)
```

### 7.3 Never Silently Return None

`run()` must always return `RunResult`. `analyze()` must always return `AnalysisResult`. If something goes wrong, raise or return with diagnostics — never return `None`.
