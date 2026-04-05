---
name: calibration-experiment-audit
description: "Audit calibration and experiment logic in the qubox codebase. Use when: tracing experiment lifecycle (run/analyze/patch/apply), auditing calibration pipelines, checking FitResult propagation, verifying patch rule correctness, reviewing experiment subclass implementations, inspecting cQED parameter flow, diagnosing stale calibration data, or validating experiment-to-analysis data handoff."
argument-hint: "Name the experiment or calibration flow to audit"
---

# Calibration & Experiment Audit

## Purpose

Trace the full lifecycle from experiment construction → data acquisition → analysis → fit evaluation → patch building → state application. Detect silent failures, contract violations, and data flow gaps.

## Procedure

### 1. Identify the Experiment

Locate the class in `qubox/legacy/experiments/`. Read `__init__`, `run()`, `analyze()`. Map base class and dependencies (hardware elements, pulse ops, analysis tools).

### 2. Trace the Data Flow

```
ExperimentRunner.__init__() → ConfigBuilder → PulseOperationManager → HardwareController
experiment.run() → ProgramRunner → RunResult
CalibrationOrchestrator.run_experiment() → Artifact
CalibrationOrchestrator.analyze() → Output with fit/metrics → FitResult.success evaluation → CalibrationResult
CalibrationOrchestrator.build_patch() → patch_rules → Patch
CalibrationOrchestrator.apply_patch() → pre-patch snapshot → mutate → rollback on failure
```

At each stage verify: types match signatures, errors are handled (not swallowed), metadata flows through.

### 3. FitResult Contract

- `analyze()` produces `Output` with `.fit` attribute
- `fit.success is False` → `quality["passed"] = False`
- Fit params extracted only after success check
- `r_squared` compared against 0.5 threshold

### 4. Patch Rule Validation

Find matching rules in `calibration/patch_rules.py` → `default_patch_rules()`. Verify: transforms are correct, units/scaling/naming match session state keys, target path exists.

### 5. Cross-Experiment Consistency

For related experiments (e.g., resonator → qubit spectroscopy → Rabi): verify dependency chain respected, upstream results consumed (not re-derived), parameter naming consistent.

## Output

Structured audit report: lifecycle trace with ✓/✗, FitResult contract status, patch rule table, data flow issues, recommendations.
