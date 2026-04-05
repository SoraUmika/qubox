# qubox — GitHub Copilot Instructions

**Read `AGENTS.md` before making any change.** It is the master policy document.

## Environment

- **Python 3.12.10** required (`.venv` or global); all others forbidden
- QM API 1.2.6, OPX+ + Octave, server `10.157.36.68` / `Cluster_2`
- Style: PEP 8, ruff, 120-char lines, `from __future__ import annotations`
- Pydantic v2 for models; frozen dataclasses for identity objects
- Imports: stdlib → third-party → local

## QUA Validation

Compile (<1 min) → simulate on hosted server → verify pulses/timing/control flow.
Shortcuts: `n_avg=1`, shorten waits. Mismatches → report, never silently accept.
Unfixable → `limitations/qua_related_limitations.md`.

## Docs & Compatibility

- Same-task updates: `API_REFERENCE.md`, `docs/CHANGELOG.md`, affected notebooks
- No public API removal without approval
- `standard_experiments.md` = trust gates for QUA changes

## Architecture

```
qubox/              Main package — experiments, calibration, hardware, QUA programs
qubox/notebook/     Notebook import surface
qubox_tools/        Analysis — fitting, plotting, algorithms
tools/              Developer utilities (validation, logging)
notebooks/          28 sequential experiment notebooks
tests/              Pytest suite
```

## Rules

- Import from `qubox`, `qubox.notebook`, or concrete `qubox.*` — never `qubox_v2_legacy`/`qubox.legacy`
- No temp scripts outside `tools/`; log tasks to `past_prompt/`
- Smallest correct change; no unrelated cleanup
- Legacy ref (read-only): `C:\Users\jl82323\Box\...\JJL_Experiments` — see `AGENTS.md §14`
