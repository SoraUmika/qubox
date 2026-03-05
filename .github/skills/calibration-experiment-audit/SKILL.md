---
name: calibration-experiment-audit
description: "Audit calibration and experiment logic in the qubox codebase. Use when: tracing experiment lifecycle (run/analyze/patch/apply), auditing calibration pipelines, checking FitResult propagation, verifying patch rule correctness, reviewing experiment subclass implementations, inspecting cQED parameter flow, diagnosing stale calibration data, or validating experiment-to-analysis data handoff."
argument-hint: "Name the experiment or calibration flow to audit"
---

# Calibration & Experiment Audit

## Purpose

Trace and verify the full lifecycle of experiments and calibration flows in qubox_v2 — from experiment construction through data acquisition, analysis, fit evaluation, patch building, and state application. Detects silent failures, contract violations, and data flow gaps.

## When to Use

- Auditing a specific experiment class (e.g., Rabi, Ramsey, readout calibration)
- Verifying the CalibrationOrchestrator pipeline for a new experiment type
- Debugging why calibration results seem stale or incorrect
- Checking that a new experiment subclass correctly implements the base contract
- Reviewing cQED parameter propagation from fit → patch → session state

## Procedure

### Step 1 — Identify the Experiment

1. Locate the experiment class file in `qubox_v2/experiments/`
2. Read its class definition, `__init__`, `run()`, and `analyze()` methods
3. Identify which base class it inherits from (`ExperimentRunner`, `cQED_Experiment`, etc.)
4. Map its dependencies: which hardware elements, pulse operations, and analysis tools it uses

### Step 2 — Trace the Data Flow

Follow data through the full pipeline:

```
ExperimentRunner.__init__()
    → ConfigBuilder builds QUA config
    → PulseOperationManager registers pulses
    → HardwareController connects
    
experiment.run(**kwargs)
    → ProgramRunner executes QUA program
    → Returns RunResult with raw data
    
CalibrationOrchestrator.run_experiment(exp)
    → Wraps run() result as Artifact
    
CalibrationOrchestrator.analyze(exp, artifact)
    → exp.analyze(pseudo_result) → Output with fit, metrics, metadata
    → Evaluates FitResult.success
    → Builds CalibrationResult with quality dict
    
CalibrationOrchestrator.build_patch(result)
    → Applies patch_rules to CalibrationResult.params
    → Returns Patch object
    
CalibrationOrchestrator.apply_patch(patch)
    → Captures pre-patch snapshot
    → Mutates session state
    → Rollback on failure
```

For each stage, verify:
- [ ] Data types match expected signatures
- [ ] Error conditions are handled (not silently swallowed)
- [ ] Metadata flows through (calibration_kind, artifact_id)

### Step 3 — FitResult Contract Audit

Check the experiment's `analyze()` method:

1. Does it produce an `Output` with a `.fit` attribute?
2. If `fit.success is False`, does the downstream code set `quality["passed"] = False`?
3. Are fit parameters (e.g., frequency, T1, T2) extracted only after success check?
4. Is `r_squared` computed and compared against the 0.5 threshold?

Reference: [Contract Checklist](./references/audit-checklist.md)

### Step 4 — Patch Rule Validation

For the experiment's calibration kind:

1. Find the matching rules in `calibration/patch_rules.py` → `default_patch_rules()`
2. Verify each rule transforms `CalibrationResult.params` correctly
3. Check units, scaling, and naming conventions match session state keys
4. Confirm that the patch target path in session state exists

### Step 5 — Cross-Experiment Consistency

If auditing multiple related experiments (e.g., resonator spectroscopy → qubit spectroscopy → Rabi):

1. Verify the calibration dependency chain is respected
2. Check that upstream calibration results are consumed (not re-derived)
3. Confirm parameter naming is consistent across the chain

### Step 6 — Generate Audit Report

```markdown
## Experiment Audit: [ExperimentClassName]

### Lifecycle Trace
[Data flow diagram with ✓/✗ at each stage]

### FitResult Contract
- success propagation: [PASS/FAIL]
- r_squared threshold: [PASS/FAIL/N/A]
- stale parameter risk: [NONE/LOW/HIGH]

### Patch Rules
| Param | Rule | Target Key | Status |
|-------|------|------------|--------|

### Data Flow Issues
[List of gaps, type mismatches, or silent failures]

### Recommendations
[Ordered fixes]
```

## Input Format

Provide one of:
- An experiment class name (e.g., `Rabi`, `ReadoutCalibration`)
- A calibration flow description
- A specific failure symptom to diagnose

## Output Format

Structured markdown audit report as shown in Step 6.

## Resources

- [Audit Checklist](./references/audit-checklist.md) — Per-experiment verification items
- [Parameter Flow Map](./references/parameter-flow.md) — cQED parameter dependencies
