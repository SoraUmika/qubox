---
name: repo-onboarding
description: >
  Use this skill at the very start of any new task or conversation about the qubox repository.
  Trigger on: first message in a conversation, "help me with qubox", "what is this repo",
  "how does this work", "where is X", "explain the architecture", or any indication the agent
  needs to understand the project before acting. Do not make changes until onboarding is complete.
---

# Repository Onboarding Skill

## When to Use

- First message in any new conversation about qubox
- Any request to explain the repository architecture
- Any request to locate a file, class, or concept
- Before starting any non-trivial task in an unfamiliar part of the repo
- When switching from one area of the repo to a very different one

## Read These Files in Order

1. **`AGENTS.md`** — Master policy document. Read every section. Do not skip.
2. **`README.md`** — Project overview, quickstart, architecture summary.
3. **`API_REFERENCE.md`** — Public API. Read if the task involves user-facing code.
4. **`standard_experiments.md`** — Trust-gate protocols. Read if the task involves QUA or experiments.

Do not make changes until you have read at least files 1 and 2.

## Project Architecture Summary

qubox is a cQED experiment orchestration framework for Quantum Machines hardware.

### Key Directories

| Directory | Contents |
| --- | --- |
| `qubox/` | Main package — public API, experiments, calibration, hardware, QUA programs |
| `qubox/backends/qm/` | QM-specific backend: runtime, lowering, adapter layer |
| `qubox/calibration/` | CalibrationStore, CalibrationOrchestrator, patch rules |
| `qubox/session/` | Session, ExperimentContext, SessionState |
| `qubox/experiments/` | ExperimentLibrary, templates, workflows, concrete experiment classes |
| `qubox/programs/` | QUA program builders, macros, circuit compiler |
| `qubox/hardware/` | Hardware abstraction (config engine, controller, program runner) |
| `qubox/notebook/` | Notebook-facing import surface: experiment classes, calibration, session helpers |
| `qubox_tools/` | Analysis toolkit — fitting, plotting, algorithms, optimization |
| `qubox_lab_mcp/` | Lab MCP server |
| `tools/` | Developer & agent utilities (validation, demos, logging) |
| `notebooks/` | 28 sequential experiment notebooks |
| `past_prompt/` | Agent prompt logs (append-only) |
| `docs/` | CHANGELOG and extended documentation |
| `tests/` | Unit and integration tests |
| `limitations/` | Known QUA/hardware limitations |
| `.github/skills/` | Agent skill files (8 skills — see listing below) |

### Key Files

| File | Purpose |
| --- | --- |
| `AGENTS.md` | Master agent policy — read first |
| `API_REFERENCE.md` | Canonical public API reference |
| `standard_experiments.md` | Trust-gate QUA protocols |
| `limitations/qua_related_limitations.md` | Known hardware/compilation mismatches |
| `docs/CHANGELOG.md` | Append-only change log |
| `qubox/notebook/__init__.py` | Primary import surface for notebooks |

### User-Facing Workflow

```python
# Notebook usage (all imports via qubox.notebook)
from qubox.notebook import (
    CalibrationStore, CalibrationOrchestrator,
    QubitSpectroscopy, T1Relaxation, ...
)

# Modern API
from qubox.session import Session
session = Session.open(sample_id="...", cooldown_id="...")
result = session.exp.qubit.spectroscopy(frequencies=..., n_avg=100)
```

### Package Boundaries

- `qubox/` contains all experiment classes, QUA program builders, and hardware
  control code directly (not in a legacy sublayer).
- `qubox.notebook` re-exports experiment classes as the primary notebook import surface.
- Do not import from `qubox_v2_legacy` or `qubox.legacy` — those packages have been eliminated.

## Python Version and Hardware

| Item | Value |
| --- | --- |
| Python version | 3.12.10 via the workspace `.venv` or a global 3.12.10 interpreter (fallback: 3.11.8 on ECE-SHANKAR-07) |
| QM API version | 1.2.6 |
| Hardware | OPX+ + Octave |
| Hosted server | host=10.157.36.68, cluster_name=Cluster_2 |
| Linter | ruff, 120-char line length |

## Rules

- Do not make changes until onboarding is complete (files 1 and 2 read minimum).
- Do not assume the architecture from memory — read the current code.
- Do not introduce changes inconsistent with the policies in `AGENTS.md`.
- If the task is QUA-related: also use the **qua-validation** skill.
- If the task creates or modifies public API: also use the **docs-sync** skill.
- If migrating legacy → qubox: also use the **legacy-migration** skill.
