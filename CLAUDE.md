<context>
qubox is a Python framework for circuit-QED (cQED) experimental design, execution, analysis,
and extension targeting Quantum Machines hardware (OPX+ + Octave, QUA API v1.2.6). It compiles
high-level experiment descriptions into QUA programs, runs them on real hardware or the QM
simulator, and collects results. Physical correctness and compiled-program fidelity are
non-negotiable — this controls real quantum hardware.
</context>

## Read First

Before making any change: read `AGENTS.md` completely. Every policy is there. This file
supplements it with Claude-specific memory and banned patterns.

## Memory

Retain these facts across turns:

| Fact | Value |
| --- | --- |
| Python version | **3.12.10** via the workspace `.venv` or a global 3.12.10 interpreter |
| QM API version | 1.2.6 |
| Hardware | OPX+ + Octave |
| Hosted server host | `10.157.36.68` |
| Hosted server cluster | `Cluster_2` |
| Legacy runtime location | **Removed** — legacy code eliminated; experiments live in `qubox/experiments/` |
| Legacy reference codebase | `C:\Users\jl82323\Box\...\JJL_Experiments` (read-only) |
| Legacy reference notebook | `post_cavity_experiment_legacy.ipynb` (in legacy codebase) |
| Notebook import surface | `qubox.notebook` |
| Canonical API reference | `API_REFERENCE.md` |
| Trust gates | `standard_experiments.md` |
| Limitation log | `limitations/qua_related_limitations.md` |
| Prompt logs | `past_prompt/YYYY-MM-DD_HH-MM-SS_<task>.md` |
| Linter | ruff, 120-char line length |
| Data models | Pydantic v2; frozen dataclasses for identity objects |

## Startup Checklist

- [ ] Read `AGENTS.md` (§1 Decision Tree → route to right sections)
- [ ] Read `README.md`
- [ ] Read `API_REFERENCE.md` if task is API-related
- [ ] Read `standard_experiments.md` if task touches QUA/compilation/pulse sequences
- [ ] Read `limitations/qua_related_limitations.md` if it exists and task is QUA-related
- [ ] Read relevant notebooks if task affects usage examples
- [ ] If migrating an experiment: read legacy reference codebase and `post_cavity_experiment_legacy.ipynb` (§14)
- [ ] Confirm Python version is **3.12.10** (see AGENTS.md §4)

## Section Map (AGENTS.md)

| Need | Go to |
| --- | --- |
| Which files to read for this task | §1 Decision Tree |
| Conflicting policies | §2 Priority Hierarchy |
| What to do before starting | §3 Startup Checklist |
| Python version / server config | §4 Environment |
| How to log prompts | §5 Prompt Logging |
| How to validate QUA | §6 QUA Protocol |
| Standard experiment trust gates | §7 Trust Gates |
| Scope / backward compat / testing | §8 Change Protocol |
| What docs to update and when | §9 Docs Sync |
| Tool reuse policy | §10 Tooling |
| Where to put new files | §11 File Hygiene |
| End-of-task report | §12 Completion Report |
| Legacy codebase & migration | §14 Legacy Reference |

## Code Style

- `from __future__ import annotations` in every module
- Imports: stdlib → third-party → local (relative within package)
- Type hints on all public functions and methods
- Docstrings on all public classes and methods
- Pydantic v2 for data models; frozen dataclasses for identity objects
- Ruff linter; 120-char line length

## QUA Validation (summary)

1. Compile the program (must finish in < 1 minute)
2. Simulate on hosted server (`host="10.157.36.68"`, `cluster_name="Cluster_2"`)
3. Verify: pulse ordering, timing, control flow, measurements, alignment
4. Shortcuts: `n_avg=1`, shorten idle waits, minimum simulation duration
5. Mismatches → report; do not silently accept

Use `tools/validate_qua.py --quick` for fast structural checks.

## Documentation Sync

Any change to user-visible behavior, public API, or workflow must update in the same task:

- `API_REFERENCE.md` — public API changes
- `docs/CHANGELOG.md` — all notable changes (append-only)
- Affected notebooks — if usage pattern changes

## Banned Patterns

Never do any of the following:

- **Silently accept a mismatch** between written QUA intent and compiled behavior
- **Use a Python version** other than 3.12.x without explicit user approval
- **Substitute a different QM server** without reporting it (do not guess `localhost` or other hosts)
- **Skip docs updates** when user-visible behavior changes
- **Rename or remove a public API** without explicit user approval
- **Assume QM API compatibility** beyond version 1.2.6
- **Leave a broken notebook** unacknowledged after a code change
- **Create files in wrong directories** (no scattered scripts, no temp files at repo root)
- **Overwrite a prior prompt log** — each run gets its own file
- **Import from `qubox_v2_legacy` or `qubox.legacy`** — those packages no longer exist
- **Introduce new abstractions** without justification from repeated structure
- **Run destructive git operations** (force push, reset --hard, branch -D) without explicit user request

## Architecture Quick Reference

```
qubox/              Main package — public API, experiments, calibration, hardware, QUA programs
qubox/notebook/     Notebook-facing import surface (~65 essentials + ~45 advanced symbols)
qubox_tools/        Analysis toolkit — fitting, plotting, algorithms, optimization
qubox_lab_mcp/      Lab MCP server
tools/              Developer & agent utilities (validation, demos, logging)
notebooks/          28 sequential experiment notebooks (must stay current)
tests/              Pytest test suite
docs/               CHANGELOG, architecture docs, design reviews
samples/            Sample & cooldown data directories
past_prompt/        Prompt logs (append-only)
limitations/        Known QUA/hardware limitations
.skills/            Claude Code skill files
.github/skills/     GitHub Copilot skill files
```

## Completion Report

End every substantial task with the template from `AGENTS.md §12`. Include:

- What changed, why, and what was assumed
- Validation performed (compile / simulate / standard experiments / unit tests / docs)
- What remains uncertain
- Limitations discovered
