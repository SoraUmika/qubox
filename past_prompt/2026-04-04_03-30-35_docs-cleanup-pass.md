# Prompt Log: Documentation Cleanup Pass

**Date:** 2026-04-04 03:30
**Task:** Docs-only cleanup to make repository documentation clearer, internally consistent, and aligned with the live codebase.

---

## Original Prompt

User requested a comprehensive docs-only cleanup pass for the qubox repository with specific deliverables:

1. README cleaned up — structured, navigable, accurate package layout
2. API_REFERENCE.md cleaned — remove stale "corrections versus older docs" framing, tighten notes/limitations
3. Architecture mapping docs — consistent descriptions, identify canonical vs supporting vs historical
4. AGENTS.md — fix stale architecture pointers, update directory guide
5. Historical docs — label obsolete docs with banners pointing to canonical references

Required outputs: updated canonical docs, AGENTS.md alignment, doc classification summary
(canonical / supporting / historical), contradictions resolved, CHANGELOG entry, prompt log.

---

## Changes Made

### Canonical Docs Updated

| File | Change |
|------|--------|
| `README.md` | Complete rewrite — packages table, quick start, import surfaces table, repo layout tree, documentation map (canonical / supporting / historical) |
| `API_REFERENCE.md` | 3 targeted edits: replaced "Important corrections vs older docs" section, removed stale qubox.legacy note in §6.2, consolidated §11 Notes & Limitations |
| `AGENTS.md` | 2 edits: §4 architecture refs → API_REFERENCE.md + package-map.md; §11 directory guide updated with more precise descriptions and `samples/` |
| `CLAUDE.md` | Architecture Quick Reference updated for consistency |
| `.github/copilot-instructions.md` | Architecture section updated for consistency |
| `site_docs/architecture/package-map.md` | Tightened removed-packages scope-boundary note |

### Historical Docs Labeled (11 total)

All received a historical banner pointing to canonical replacements:

- `docs/qubox_architecture.md` — also fixed stale Backend Policy referencing qubox_v2_legacy
- `docs/qubox_refactor_verification.md`
- `docs/qubox_tools_analysis_split.md`
- `docs/qubox_migration_guide.md`
- `docs/qubox_experiment_framework_refactor_proposal.md`
- `docs/architecture_review.md`
- `docs/gate_architecture_review.md`
- `docs/codebase_graph_survey.md`
- `SURVEY.md`
- `notebooks/migration_plan.md`
- `notebooks/COMPILATION_VERIFICATION_REPORT.md`

### Stale References Fixed

| File | Fix |
|------|-----|
| `.github/skills/experiment-design/SKILL.md` | `qubox.legacy.programs.*` → `qubox.programs.*` |
| `.github/skills/repo-onboarding/SKILL.md` | Removed qubox/legacy/ dir entry, added qubox/programs/ and qubox/hardware/, replaced "Legacy Bridge" section with "Package Boundaries", updated descriptions |
| `.github/skills/codebase-refactor-reviewer/references/test-map.md` | Fixed test paths from `qubox_v2_legacy/tests/` to `qubox/tests/` |
| `.github/WORKFLOW_BLUEPRINT.md` | Removed `qubox_v2_legacy\` from directory tree |

### CHANGELOG Entry

Added entry under `2026-04-04 — Documentation Cleanup Pass` in `docs/CHANGELOG.md`.

---

## Contradictions Resolved

1. **AGENTS.md §4** pointed to `docs/qubox_architecture.md` as canonical architecture ref — but that doc is a historical 2026-03-13 facade-era sketch. → Fixed to point to `API_REFERENCE.md` and `site_docs/architecture/package-map.md`.
2. **API_REFERENCE.md §2** had an "Important corrections versus older documentation" section referencing `qubox_v2_legacy`, `qubox.legacy`, `qubox.compile`, `qubox.simulation` — all removed packages. → Replaced with neutral "Notes on the live layout".
3. **API_REFERENCE.md §6.2** still said "this is not a removed qubox.legacy layer" — redundant since qubox.legacy is long gone. → Removed.
4. **Skill files** still referenced `qubox.legacy.programs.*` and `qubox_v2_legacy/tests/` — packages that no longer exist. → Fixed to current paths.
5. **WORKFLOW_BLUEPRINT.md** directory tree still showed `qubox_v2_legacy\` as a top-level directory. → Removed and noted.
6. **README.md** had verbose "scope boundary" text explaining the qubox.compile/qubox.simulation removal — confusing for new readers. → Replaced with clean documentation map.

---

## Unresolved Ambiguities

1. `qubox/gui/` and `qubox/migration/` are empty directory stubs (no `__init__.py`). Could be deleted but that's a code change outside docs scope.
2. `LEGACY_ELIMINATION_REPORT.md` at repo root is historical but was not labeled (it self-documents as "COMPLETE" and describes the qubox.legacy → qubox merger). Its status is clear from its content.
3. Some historical docs in `docs/` (e.g., `measureMacro_refactoring_plan.md`, `codebase_refactor_plan.md`) contain qubox.legacy references but are already clearly scoped to completed refactors. Not labeled this pass.

---

## Target Files Modified

22 files total — see CHANGELOG entry for full list.

---

## Task Context

- **Why:** After legacy elimination and multiple refactors, the docs had accumulated stale references, contradictory architecture pointers, and an unclear hierarchy of canonical vs historical documents.
- **Constraints:** Docs-only — no code changes. Preserve historical content for auditability; label rather than delete.
- **Assumptions:** The live package tree at time of audit is the ground truth. `API_REFERENCE.md` and `site_docs/architecture/package-map.md` are the canonical architecture references.
