---
name: codebase-refactor-reviewer
description: "Review and audit code refactors in the qubox codebase. Use when: reviewing pull requests, inspecting refactor safety, auditing architecture changes, checking for regressions, verifying contract compliance (FitResult.success, patch transactionality), reviewing module boundaries, or validating that refactors preserve experiment lifecycle semantics."
argument-hint: "Describe the refactor or point to changed files/modules"
---

# Codebase Refactor Reviewer

## Purpose

Verify refactors preserve behavioral contracts. Focus: experiment lifecycle, calibration pipeline, hardware safety.

## Contract Checklist

| Contract | Key Check |
|----------|-----------|
| FitResult.success | `analyze()` → `Output.fit.success` → quality gate → param extraction gated on success |
| Patch transactionality | Pre-snapshot → mutate → rollback on failure; no partial application |
| Experiment lifecycle | `__init__` → `run()` → `analyze()` order preserved; no silent state mutations |
| ExperimentContext | Frozen after construction — no field assignment post-init |
| Persistence | `split_output_for_persistence` for all Output serialization; no raw numpy to JSON |
| Module boundaries | No circular imports, no cross-boundary private access |
| QUA compilation | Same compiled output before/after; verify with `tools/validate_qua.py --quick` |

## Procedure

1. **Scope:** Identify all changed files. Classify: structural (moved/renamed), behavioral (logic), interface (signature), cosmetic.
2. **Contract audit:** For each contract-bearing file, verify each contract above.
3. **Dependency impact:** For changed public APIs, search all call sites for breakage. Check `__init__.py` re-exports.
4. **Regression check:** Confirm existing tests still pass. If tests changed, verify strictly stronger.
5. **AGENTS.md compliance:** Minimal change scope, no unrelated cleanup, docs updated if API changed.

## Risk Assessment

| Risk Level | Criteria |
|------------|----------|
| CRITICAL | Persistence format, hardware control flow, patch application without rollback |
| HIGH | Calibration/experiment lifecycle behavioral changes, untested contract paths |
| MEDIUM | Interface changes with updated call sites, new code paths with tests |
| LOW | Cosmetic, imports, type annotations only |

## Rules

- Never approve breaking a contract without explicit user approval
- "Tests pass" is necessary but not sufficient — contracts are the primary check
- Flag any silent behavior change even if tests pass
