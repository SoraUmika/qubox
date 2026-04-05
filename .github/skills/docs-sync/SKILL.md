---
name: docs-sync
description: >
  Use this skill whenever making any change that affects user-visible behavior, public APIs,
  or workflows. This includes new classes, renamed parameters, removed features, changed
  defaults, new experiments, and workflow changes. Even if the user does not mention
  documentation, use this skill to ensure docs stay in sync with every code change.
---

# Documentation Sync

## Trigger Conditions

Any of: new public class/function, renamed/removed parameter, changed default, removed/deprecated feature, changed behavior, new experiment, backend change, workflow change.

## Required Updates

| Change Type | Update |
| --- | --- |
| New public class/function | `API_REFERENCE.md` + `docs/CHANGELOG.md` |
| Renamed/removed parameter | `API_REFERENCE.md` + `docs/CHANGELOG.md` + affected notebooks |
| Changed default/behavior | `API_REFERENCE.md` + `docs/CHANGELOG.md` |
| Removed feature | `API_REFERENCE.md` + `docs/CHANGELOG.md` (breaking) + notebooks |
| New experiment | `API_REFERENCE.md` + `docs/CHANGELOG.md` + consider new notebook |

## Procedure

1. **API_REFERENCE.md** — Update signature, params, return type, description. Add new section if needed. Follow existing format.
2. **docs/CHANGELOG.md** — Append entry at top: `- [added|changed|fixed|removed] Description`. Never delete existing entries.
3. **Notebooks** — Check affected notebooks under `notebooks/`. Update broken cells or acknowledge they need update.

## Rules

- Docs update happens **in the same task** as code change — not later
- `docs/CHANGELOG.md` is append-only
- A code change that breaks a notebook without acknowledgment is incomplete work
- No dangling references to removed classes/parameters in docs
