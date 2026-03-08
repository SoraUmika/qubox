# Audit Checklist — Per-Experiment Verification

## For Every Experiment Class

### Construction
- [ ] Inherits from `ExperimentRunner` or documented base
- [ ] Calls `super().__init__()` with correct arguments
- [ ] Registers pulses through `PulseOperationManager`
- [ ] Does NOT hardcode hardware addresses or QUA element names

### run() Method
- [ ] Returns a `RunResult` (or compatible) object
- [ ] Does not mutate session state directly
- [ ] Handles hardware communication errors (ConnectionError)
- [ ] Respects `ExecMode` (simulation vs. real hardware)

### analyze() Method
- [ ] Accepts `RunResult` and returns `Output`
- [ ] Performs fit using `analysis/fitting.py` utilities
- [ ] Sets `Output.fit` with a proper `FitResult` object
- [ ] If fit fails: `FitResult.success = False` with reason
- [ ] Computes `r_squared` when applicable
- [ ] Does NOT silently return stale parameters on failure
- [ ] Populates `Output.metadata["calibration_kind"]`

### CalibrationOrchestrator Integration
- [ ] Experiment kind has matching entry in `patch_rules.py`
- [ ] Patch rules correctly map fit params → session state keys
- [ ] `build_patch()` produces a valid `Patch` object
- [ ] `apply_patch()` is idempotent (applying same patch twice is safe)

## Red Flags

- `analyze()` returns hardcoded values instead of fit results
- Missing `calibration_kind` in metadata → orchestrator can't route
- Direct session state mutation outside orchestrator
- Fit result used without checking `.success`
- Exception caught and silently ignored in run/analyze
