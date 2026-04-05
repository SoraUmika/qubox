# Agent Config Compaction
**Date:** 2026-04-05 15:39
**Task:** Compact AGENTS.md, CLAUDE.md, copilot-instructions.md, and all 12 skill files for reduced agent token consumption.

## Request
Clean up AGENTS.md, CLAUDE.md and .skills MEMORY etc, so that they are more compact for agentic usage.

## Changes Made
- **AGENTS.md**: ~600 → 148 lines (75% reduction). Compressed all sections: routing table, environment, QUA protocol, trust gates, change protocol, docs sync, tooling, file hygiene, completion report, design values, legacy migration, notebook hang recovery.
- **CLAUDE.md**: ~160 → 49 lines (69% reduction). Removed redundant section map, startup checklist, architecture details already in AGENTS.md.
- **.github/copilot-instructions.md**: ~120 → 30 lines (75% reduction). Removed verbose project overview, kept environment table and key rules.
- **12 skill files** compacted from ~1830 total lines to ~328 total lines (82% reduction):
  - prompt-logging: 95 → 15, qua-validation: 165 → 24, docs-sync: 105 → 28
  - legacy-migration: 180 → 24, repo-onboarding: 125 → 37, ruff-recursive-fix: 155 → 20
  - pytest-coverage: 135 → 17, security-review: 175 → 24, research-artifact-builder: 165 → 26
  - calibration-experiment-audit: 185 → 32, codebase-refactor-reviewer: 160 → 35, experiment-design: 155 → 46
- **3 instruction files** (~30 lines each) assessed and left as-is — already compact.

## Files Modified
AGENTS.md, CLAUDE.md, .github/copilot-instructions.md, .github/skills/*/SKILL.md (12 files)

## Validation
- All files verified as well-formed markdown with YAML frontmatter intact
- No content-bearing information removed — only redundancy, verbose templates, and AGENTS.md duplication
- Total reduction: ~2710 → ~555 lines across all files (~80% reduction)
