---
name: research-artifact-builder
description: "Generate research documentation artifacts from qubox codebase and experiment results. Use when: writing README updates, generating API documentation, creating CHANGELOG entries, building Overleaf-ready LaTeX writeups, producing experiment summary reports, updating ARCHITECTURE.md, generating test case reports, or creating notebook documentation from experiment data."
argument-hint: "Describe the artifact to generate (e.g., 'API docs for calibration module', 'LaTeX summary of Rabi results')"
---

# Research Artifact Builder

## Artifact Types

| Artifact | Source | Target | Template |
|----------|--------|--------|----------|
| API docs | Source code signatures + docstrings | `API_REFERENCE.md` | [api-entry.md](./assets/api-entry.md) |
| Module summary | Module structure + public API | README or `docs/` | [module-summary.md](./assets/module-summary.md) |
| CHANGELOG | Git diff / change description | `docs/CHANGELOG.md` (append-only) | [changelog-entry.md](./assets/changelog-entry.md) |
| LaTeX writeup | Experiment class + fit results + plots | Overleaf-ready `.tex` | [experiment-writeup.tex](./assets/experiment-writeup.tex) |
| Test report | Pytest output | Structured summary | — |

## Procedure

1. **Identify scope:** Which modules changed, what artifact(s) needed.
2. **Extract:** Read source → signatures, types, docstrings, fit results as applicable.
3. **Generate:** Use the appropriate template. For CHANGELOG: follow [Keep a Changelog](https://keepachangelog.com/) format (Added/Changed/Fixed/Deprecated/Security).
4. **Validate:** All documented names exist in code, types match, cross-references valid.

## LaTeX Specifics

Structure: Introduction → Methods (QUA program, pulse sequence) → Results (fit params ± uncertainties, plots) → Discussion.
Use `siunitx` for units, figure placeholders with captions, parameter tables.

## Rules

- CHANGELOG is append-only
- Verify all public names in docs exist in code
- LaTeX must be compilable standalone
