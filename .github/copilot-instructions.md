# qubox — GitHub Copilot Instructions

## Project Overview

qubox is a Python cQED experiment framework targeting Quantum Machines hardware (OPX+ + Octave,
QUA API v1.2.6). It compiles high-level experiment definitions into QUA programs and runs them
on real quantum hardware or the QM simulator. **Physical correctness is non-negotiable.**

**Read `AGENTS.md` before making any change.** It is the master policy document.

## Python

- **Required:** Python 3.12.13 (fallback: 3.11.8 on ECE-SHANKAR-07 only)
- **Forbidden:** all other Python versions
- Style: PEP 8, ruff linter, 120-char line length
- `from __future__ import annotations` in every module
- Pydantic v2 for data models; frozen dataclasses for identity objects
- Imports: stdlib → third-party → local

## QUA Validation Rule

> **The compiled QUA program is the source of truth, not the written code.**

Every QUA-touching change must be validated:

1. Compile (must finish in < 1 minute)
2. Simulate on hosted server: `host="10.157.36.68"`, `cluster_name="Cluster_2"`
3. Verify: pulse ordering, timing, control flow, measurements
4. Mismatches → report explicitly; never silently accept

Shortcuts for validation: `n_avg=1`, shorten idle periods, simulate minimum duration.
Unresolvable mismatches → document in `limitations/qua_related_limitations.md`.

## Standard Experiments

`standard_experiments.md` defines trust gates. If a change touches pulse-sequence generation,
compilation, scheduling, or QUA translation: verify relevant standard experiments still pass.
Failure = do not ship without explanation and user approval.

## Documentation Sync

These updates happen **in the same task** as the code change — not later:

- `API_REFERENCE.md` — any public API change
- `docs/CHANGELOG.md` — all notable changes (append-only)
- Affected notebooks — if usage pattern changes

A code change that breaks a notebook without acknowledgment is incomplete work.

## Backward Compatibility

- Do not rename or remove public APIs without explicit user approval.
- Breaking changes require `API_REFERENCE.md` update + `docs/CHANGELOG.md` entry + notebook fixes.

## Architecture

```text
qubox/              Main package (public API)
qubox/legacy/       Former qubox_v2_legacy — experiment classes, QUA programs
qubox/compat/       notebook.py — sole import surface for notebooks
qubox_tools/        Analysis, fitting, plotting
tools/              Agent and developer utilities
past_prompt/        Prompt logs (append-only)
limitations/        Known QUA/hardware limitations
```

## Key Rules

- Do not import from `qubox_v2_legacy` — use `qubox.legacy.*` instead.
- Do not assume QM API compatibility beyond version 1.2.6.
- Do not scatter temp scripts outside `tools/`.
- Log every completed task to `past_prompt/YYYY-MM-DD_HH-MM-SS_<task>.md`.
- Make the smallest correct change. No unrelated cleanup.
