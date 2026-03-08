---
name: codebase-refactor-reviewer
description: "Review and audit code refactors in the qubox codebase. Use when: reviewing pull requests, inspecting refactor safety, auditing architecture changes, checking for regressions, verifying contract compliance (FitResult.success, patch transactionality), reviewing module boundaries, or validating that refactors preserve experiment lifecycle semantics."
argument-hint: "Describe the refactor or point to changed files/modules"
---

# Codebase Refactor Reviewer

## Purpose

Systematically review code refactors in the qubox_v2 codebase to ensure correctness, contract compliance, and architectural consistency. Produces a structured review report with risk assessment.

## When to Use

- Before merging any refactor branch
- After restructuring module boundaries (e.g., moving code between experiments/, calibration/, core/)
- When changing base classes (ExperimentRunner, CalibrationOrchestrator)
- When modifying Pydantic models, frozen dataclasses, or persistence logic
- When touching hardware abstraction or pulse pipeline code

## Procedure

### Step 1 — Scope the Change

1. Identify all changed files (use git diff or file list provided by user)
2. Classify each change: **structural** (moved/renamed), **behavioral** (logic change), **interface** (signature change), **cosmetic** (formatting only)
3. Map changed files to [architecture modules](./references/module-map.md)

### Step 2 — Contract Compliance Check

For each changed file, verify these invariants:

- [ ] **FitResult.success contract**: Any code touching `CalibrationResult` or fit analysis must propagate `quality["passed"] = False` on fit failure. Never silently pass stale params.
- [ ] **ExperimentContext immutability**: No code assigns to fields of a frozen `ExperimentContext` after construction.
- [ ] **Patch transactionality**: `CalibrationOrchestrator.apply_patch` must support rollback. No partial state mutations.
- [ ] **Persistence policy**: `split_output_for_persistence` is used for all Output serialization; raw numpy arrays never written directly to JSON.
- [ ] **Import hygiene**: Relative imports within qubox_v2; no circular dependencies introduced.

### Step 3 — Dependency Impact Analysis

1. For each changed public API (class, function, constant), search for all call sites
2. Flag any call site that now receives different types, different defaults, or missing arguments
3. Check that `__init__.py` re-exports are updated if public names moved

### Step 4 — Test Coverage Check

1. List all test files relevant to changed modules (see [test mapping](./references/test-map.md))
2. Verify existing tests still pass conceptually (flag tests that reference removed/renamed symbols)
3. Identify untested paths introduced by the refactor
4. Recommend specific test additions with expected inputs/outputs

### Step 5 — Risk Assessment

Classify overall risk:

| Risk Level | Criteria |
|------------|----------|
| **LOW** | Cosmetic only; no behavioral change; all tests pass |
| **MEDIUM** | Interface changes with updated call sites; new code paths with tests |
| **HIGH** | Behavioral changes to calibration/experiment lifecycle; contract modifications; untested paths |
| **CRITICAL** | Changes to persistence format; hardware control flow; patch application logic without rollback |

### Step 6 — Generate Report

Produce a structured markdown report with these sections:

```markdown
## Refactor Review: [title]

### Summary
[1-2 sentence description of what changed and why]

### Changed Files
| File | Change Type | Risk |
|------|-------------|------|

### Contract Compliance
[Checklist results from Step 2]

### Breaking Changes
[List any API breaks, with migration guidance]

### Test Gaps
[Untested paths, recommended additions]

### Risk Assessment: [LOW/MEDIUM/HIGH/CRITICAL]
[Justification]

### Recommendations
[Ordered list of actions before merge]
```

## Input Format

Provide one of:
- A list of changed files or a branch name to diff
- A description of the refactor intent
- A specific module or class to audit

## Output Format

Structured markdown report as shown in Step 6. Always includes risk level and actionable recommendations.

## Resources

- [Module Map](./references/module-map.md) — Architecture module boundaries
- [Test Map](./references/test-map.md) — Module-to-test file mapping
- [Contract Checklist](./references/contract-checklist.md) — Full invariant checklist
