---
name: repo-onboarding
description: >
  Use this skill at the very start of any new task or conversation about the qubox repository.
  Trigger on: first message in a conversation, "help me with qubox", "what is this repo",
  "how does this work", "where is X", "explain the architecture", or any indication the agent
  needs to understand the project before acting. Do not make changes until onboarding is complete.
---

# Repository Onboarding

## Required Reading (in order)

1. **`AGENTS.md`** — Master policy. Read every section. Do not skip.
2. **`README.md`** — Project overview and architecture.
3. **`API_REFERENCE.md`** — If task involves user-facing code.
4. **`standard_experiments.md`** — If task involves QUA or experiments.

Do not make changes until at least files 1 and 2 are read.

## Quick Facts

| Item | Value |
| --- | --- |
| Python | 3.12.10 (`.venv` or global) |
| QM API | 1.2.6; Hardware: OPX+ + Octave |
| Server | `10.157.36.68` / `Cluster_2` |
| Import surfaces | `qubox`, `qubox.notebook`, `qubox.notebook.advanced` |
| Banned imports | `qubox_v2_legacy`, `qubox.legacy` (don't exist) |

## Key Directories

| Directory | Contents |
| --- | --- |
| `qubox/` | Main package — experiments, calibration, hardware, QUA programs |
| `qubox/notebook/` | Notebook import surface |
| `qubox_tools/` | Analysis — fitting, plotting, algorithms |
| `tools/` | Developer utilities (validation, logging) |
| `notebooks/` | 28 sequential experiment notebooks |
| `tests/` | Pytest suite |

## Rules

- Do not make changes until onboarding reading is done
- QUA-related → also use **qua-validation** skill
- Public API changes → also use **docs-sync** skill
- Legacy migration → also use **legacy-migration** skill
