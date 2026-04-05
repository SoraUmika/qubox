<context>
qubox is a Python cQED experiment framework for Quantum Machines hardware (OPX+ + Octave,
QUA API v1.2.6). Compiles experiment descriptions → QUA programs → runs on hardware/simulator.
Physical correctness is non-negotiable.
</context>

## Read First

`AGENTS.md` is the master policy. This file adds Claude-specific memory and banned patterns.

## Memory

| Fact | Value |
| --- | --- |
| Python | **3.12.10** (`.venv` or global) |
| QM API | 1.2.6 |
| Hardware | OPX+ + Octave |
| Server | `10.157.36.68` / `Cluster_2` |
| Import surfaces | `qubox`, `qubox.notebook`, `qubox.notebook.advanced` |
| API reference | `API_REFERENCE.md` |
| Trust gates | `standard_experiments.md` |
| Limitations | `limitations/qua_related_limitations.md` |
| Prompt logs | `past_prompt/YYYY-MM-DD_HH-MM-SS_<task>.md` |
| Style | ruff, 120-char, `from __future__ import annotations` |
| Models | Pydantic v2; frozen dataclasses for identity |
| Legacy ref | `C:\Users\jl82323\Box\...\JJL_Experiments` (read-only) |

## Code Style

- `from __future__ import annotations` in every module
- Imports: stdlib → third-party → local (relative within package)
- Type hints on public functions; docstrings on public classes/methods
- Pydantic v2 for data models; frozen dataclasses for identity objects

## Banned Patterns

- Silently accept compiled-vs-intended QUA mismatch
- Use Python != 3.12.x without approval
- Substitute a different QM server
- Skip docs updates for user-visible changes
- Remove public API without approval
- Import from `qubox_v2_legacy` or `qubox.legacy` (don't exist)
- Create files in wrong directories or at repo root
- Overwrite prior prompt logs
- Run destructive git ops without explicit request

## Architecture

```
qubox/              Main package — experiments, calibration, hardware, QUA programs
qubox/notebook/     Notebook import surface
qubox_tools/        Analysis — fitting, plotting, algorithms
qubox_lab_mcp/      Lab MCP server
tools/              Validation, logging utilities
notebooks/          28 sequential experiment notebooks
tests/              Pytest suite
```

## Completion

End every substantial task with the template from `AGENTS.md §12`.
