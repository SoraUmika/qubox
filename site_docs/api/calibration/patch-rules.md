# Patch Rules

Named rules that map experiment `FitResult` into `CalibrationStore` updates.

## Available Rules

| Rule Name | Experiment Source | Updates |
|-----------|-----------------|---------|
| `PiAmpRule` | Power Rabi | `x180.amp`, `x90.amp` |
| `FrequencyRule` | Qubit Spectroscopy | `cqed_params.qubit_freq` |
| `EFFrequencyRule` | EF Spectroscopy | `cqed_params.ef_freq` |
| `ResonatorFrequencyRule` | Resonator Spectroscopy | `cqed_params.rr_freq` |
| `T1Rule` | T1 Measurement | `cqed_params.t1` |
| `T2RamseyRule` | T2 Ramsey | `cqed_params.t2_ramsey` |
| `T2EchoRule` | T2 Echo | `cqed_params.t2_echo` |
| `DragRule` | DRAG Calibration | `x180.drag`, `x90.drag` |
| `ReadoutFrequencyRule` | Readout Optimization | `readout.frequency` |
| `ReadoutThresholdRule` | IQ Blob | `readout.threshold`, `readout.rotation` |
| `ChiRule` | Dispersive Shift | `cqed_params.chi` |

## Rule Structure

Every patch rule implements the same interface:

```python
class PatchRule:
    name: str                      # Unique rule identifier
    required_fit_params: list[str] # FitResult params this rule needs

    def evaluate(self, fit_result: FitResult) -> Patch | None:
        """
        Return a Patch if fit_result is valid, None if rejected.
        """
        if not fit_result.success:
            return None

        value = fit_result.params[self.required_fit_params[0]]
        return Patch(ops=[
            UpdateOp(field=self.target_field, value=value)
        ])
```

## Patch and UpdateOp

```python
from qubox.calibration import Patch, UpdateOp

patch = Patch(ops=[
    UpdateOp(field="cqed_params.qubit_freq", value=4.85e9),
    UpdateOp(field="x180.amp", value=0.312),
])
```

| `UpdateOp` Field | Type | Description |
|-----------------|------|-------------|
| `field` | `str` | Dot-separated path into CalibrationStore |
| `value` | `Any` | New value to set |
| `old_value` | `Any \| None` | Previous value (set during evaluation) |

## Custom Rules

Create domain-specific rules by subclassing `PatchRule`:

```python
from qubox.calibration.patch_rules import PatchRule

class MyCustomRule(PatchRule):
    name = "my_custom_rule"
    required_fit_params = ["center_freq", "linewidth"]

    def evaluate(self, fit_result):
        if not fit_result.success:
            return None
        if fit_result.params["linewidth"] > 1e6:
            return None  # Reject: linewidth too broad

        return Patch(ops=[
            UpdateOp(
                field="cqed_params.qubit_freq",
                value=fit_result.params["center_freq"]
            ),
        ])
```

## Validation Guards

Rules can enforce physical bounds:

```python
class FrequencyRule(PatchRule):
    FREQ_MIN = 3.0e9   # 3 GHz
    FREQ_MAX = 8.0e9   # 8 GHz

    def evaluate(self, fit_result):
        freq = fit_result.params["center_freq"]
        if not (self.FREQ_MIN <= freq <= self.FREQ_MAX):
            return None  # Out of physical range
        ...
```
