---
name: research-artifact-builder
description: "Generate research documentation artifacts from qubox codebase and experiment results. Use when: writing README updates, generating API documentation, creating CHANGELOG entries, building Overleaf-ready LaTeX writeups, producing experiment summary reports, updating ARCHITECTURE.md, generating test case reports, or creating notebook documentation from experiment data."
argument-hint: "Describe the artifact to generate (e.g., 'API docs for calibration module', 'LaTeX summary of Rabi results')"
---

# Research Artifact Builder

## Purpose

Generate structured documentation artifacts from the qubox codebase — README updates, API docs, changelogs, architecture docs, experiment reports, and LaTeX-ready research writeups. Ensures documentation stays synchronized with code changes.

## When to Use

- After completing a refactor or feature addition
- When preparing experiment results for publication or group meeting
- When updating API_REFERENCE.md or ARCHITECTURE.md after code changes
- When generating CHANGELOG.md entries for a release
- When creating Overleaf-ready LaTeX sections from experiment data
- When building a test case report from pytest output

## Procedure

### For README / API Documentation Updates

#### Step 1 — Identify Changes
1. Determine which modules changed (from git diff or user description)
2. Read the current documentation files that need updating
3. Read the source code of changed modules to extract new/modified APIs

#### Step 2 — Extract API Signatures
For each changed public class/function:
1. Read the source file
2. Extract: name, parameters (with types), return type, docstring
3. Note any breaking changes vs. previous documentation

#### Step 3 — Generate Documentation
Use the appropriate template from [templates](./assets/):

- **API entry**: [api-entry.md](./assets/api-entry.md)
- **Module summary**: [module-summary.md](./assets/module-summary.md)
- **CHANGELOG entry**: [changelog-entry.md](./assets/changelog-entry.md)

#### Step 4 — Validate
1. Verify all public names in documentation exist in code
2. Verify parameter types match source
3. Ensure cross-references (links to other docs) are valid

---

### For LaTeX / Overleaf Research Writeups

#### Step 1 — Gather Data
1. Identify the experiment(s) to document
2. Read experiment class source for methodology
3. Collect fit results, parameters, plots from analysis output
4. Read any existing notebook analysis

#### Step 2 — Structure the Writeup
Follow the [LaTeX template](./assets/experiment-writeup.tex):

1. **Introduction**: Experiment purpose, system parameters
2. **Methods**: QUA program structure, pulse sequence, measurement protocol
3. **Results**: Fit parameters with uncertainties, plots, comparison to theory
4. **Discussion**: Quality assessment, limitations, next steps

#### Step 3 — Generate LaTeX
Produce compilable LaTeX using the template. Include:
- Proper SI units via `siunitx`
- Figure placeholders with captions
- Table of fit parameters with uncertainties
- References to qubox module/class names

---

### For CHANGELOG Entries

#### Step 1 — Classify Changes
Categorize each change as:
- **Added**: New features, modules, experiments
- **Changed**: Modified behavior, API changes
- **Fixed**: Bug fixes, contract violations resolved
- **Deprecated**: Features marked for removal
- **Security**: Vulnerability fixes

#### Step 2 — Write Entry
Follow [Keep a Changelog](https://keepachangelog.com/) format:
```markdown
## [version] - YYYY-MM-DD

### Added
- Description of new feature (#issue)

### Fixed
- Description of bug fix (#issue)
```

Append to `docs/CHANGELOG.md` (append-only policy).

## Input Format

Provide one of:
- A description of what changed and what documentation to update
- An experiment name and results to document
- A version number for CHANGELOG generation

## Output Format

Depends on artifact type:
- **Markdown**: Ready to paste into target `.md` file
- **LaTeX**: Compilable `.tex` content with `\section{}` structure
- **CHANGELOG**: Formatted entry to append to `docs/CHANGELOG.md`

## Resources

- [API Entry Template](./assets/api-entry.md)
- [Module Summary Template](./assets/module-summary.md)
- [CHANGELOG Entry Template](./assets/changelog-entry.md)
- [LaTeX Experiment Writeup Template](./assets/experiment-writeup.tex)
