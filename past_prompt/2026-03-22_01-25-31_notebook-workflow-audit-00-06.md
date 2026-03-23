# Prompt Log

**Date:** 2026-03-22 01:25:31
**Task:** notebook-workflow-audit-00-06
**Target files:** notebooks/report.md

## Original Request

Please perform a deep, end-to-end analysis of notebooks `00` through `06` in the notebooks folder.

Your goals are:

1. **Execution flow**
   - Determine how each notebook is intended to be run.
   - Identify dependencies between notebooks, including shared state, imported modules, generated artifacts, calibration files, and any assumptions carried from earlier notebooks.
   - Clarify the expected user workflow from notebook `00` to notebook `06`.

2. **Experiment structure**
   - For each notebook, explain what experiments are being performed and their purpose.
   - Describe how experimental parameters are defined, modified, and passed into acquisition/analysis routines.
   - Point out any places where execution is fragile, implicit, or dependent on hidden context.

3. **Data extraction and processing**
   - Trace how raw data is acquired, stored, loaded, and transformed.
   - Identify where IQ data, projected data, fitted quantities, and summary metrics are produced.
   - Explain exactly how analysis outputs are generated from the raw or intermediate data.

4. **Calibration workflow**
   - Analyze how calibrations are performed across notebooks `00` to `06`.
   - Identify what is being calibrated in each step, what inputs and outputs are used, and how calibration results propagate forward.
   - Note any inconsistencies, duplicated logic, unclear conventions, or risks of stale calibration values being reused.

5. **Code quality and notebook usability**
   - Evaluate whether the notebooks are clean, understandable, and runnable by a user with minimal manual intervention.
   - Flag unnecessary complexity, redundant flags, hard-coded assumptions, notebook-order dependence, and places where the workflow could break.
   - Suggest concrete improvements to make the notebook sequence more robust, reproducible, and user-friendly.

6. **Deliverable**
   - Write a file named `report.md` in the same notebooks folder.
   - The report should be well structured and include:
     - an overview of the full workflow,
     - a notebook-by-notebook breakdown,
     - a dataflow/calibrationflow summary,
     - key problems found,
     - and prioritized recommendations for cleanup and improvement.

Important:
- Base the analysis on the actual code and notebook contents, not assumptions.
- Be explicit about uncertainties or places where behavior is ambiguous.
- Treat this as a real workflow audit for experimental readiness and maintainability.

## Response / Changes Made

Created notebooks/report.md with a deep workflow audit covering notebooks 00 through 06. The report documents execution order, cross-notebook dependencies, runtime/session/bootstrap behavior, experiment-by-experiment dataflow, calibration propagation, fragility points, key problems, and prioritized recommendations for cleanup. Validated the generated markdown file after normalizing repeated subsection headings.

## Context

Read notebooks 00 through 06 plus supporting session, calibration, registry, and experiment runtime code to ground the audit in actual behavior.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
