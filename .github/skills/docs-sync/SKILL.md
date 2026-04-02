---
name: docs-sync
description: >
  Use this skill whenever making any change that affects user-visible behavior, public APIs,
  or workflows. This includes new classes, renamed parameters, removed features, changed
  defaults, new experiments, and workflow changes. Even if the user does not mention
  documentation, use this skill to ensure docs stay in sync with every code change.
---

# Documentation Sync Skill

## When to Use

Trigger this skill whenever any of the following is true:

- A new public class or function is added
- A parameter is renamed, removed, or has its default changed
- A feature is removed or deprecated
- Experiment behavior changes (even subtly)
- A new experiment type is added
- Backend support changes
- The user-facing workflow changes
- A notebook cell would produce different output after this change
- `API_REFERENCE.md` is more than one task out of date

## How to Use

### Step 1 — Identify What Changed

Determine the category of change:

| Change Type | Required Doc Updates |
| --- | --- |
| New public class | `API_REFERENCE.md` (add entry), `docs/CHANGELOG.md` |
| New public function | `API_REFERENCE.md` (add entry), `docs/CHANGELOG.md` |
| Renamed parameter | `API_REFERENCE.md` (update signature), `docs/CHANGELOG.md`, affected notebooks |
| Removed parameter | `API_REFERENCE.md` (remove or deprecation note), `docs/CHANGELOG.md`, affected notebooks |
| Changed default | `API_REFERENCE.md` (update), `docs/CHANGELOG.md` |
| Removed feature | `API_REFERENCE.md` (remove), `docs/CHANGELOG.md` (breaking change note), affected notebooks |
| New experiment | `API_REFERENCE.md` (add), `docs/CHANGELOG.md`, consider new notebook example |
| Changed behavior | `API_REFERENCE.md` (update), `docs/CHANGELOG.md` |
| Backend change | `API_REFERENCE.md` (update), `docs/CHANGELOG.md` |

### Step 2 — Update API_REFERENCE.md

- Open `API_REFERENCE.md`.
- Find the relevant section for the class/function/experiment.
- Update the signature, parameters, return type, and description.
- Add a new section if the class/function/experiment is new.
- Follow the existing format exactly — do not change the document structure.

### Step 3 — Update docs/CHANGELOG.md

- Open `docs/CHANGELOG.md`.
- **Append** a new entry at the top of the most recent version section.
- Format: `- [type] Short description of change.` where type is one of:
  `added`, `changed`, `deprecated`, `removed`, `fixed`, `security`
- Do not rewrite or delete existing changelog entries.
- If no version section exists for today: add one with today's date.

### Step 4 — Check Notebooks

- Identify notebooks under `notebooks/` that use the changed API.
- Open each affected notebook.
- Verify that every cell that calls the changed API still produces correct output.
- If a cell would break: update it.
- If a notebook becomes significantly out of date: either update it fully or mark it as
  `[LEGACY]` in the title cell.

A notebook that breaks without acknowledgment is incomplete work.

### Step 5 — Verify Consistency

After updating all docs:

- [ ] `API_REFERENCE.md` reflects the current public API accurately
- [ ] `docs/CHANGELOG.md` has an entry for this change
- [ ] All affected notebooks are updated or acknowledged
- [ ] No documentation references a class, function, or parameter that no longer exists
- [ ] No code change was left undocumented

## Reference Files

| File | Role |
| --- | --- |
| `API_REFERENCE.md` | Canonical public API reference — update for every API change |
| `docs/CHANGELOG.md` | Append-only change log — add an entry for every notable change |
| `notebooks/` | Usage examples — check and update if affected |

## Rules

- Documentation updates happen **in the same task** as the code change. Not in a follow-up.
- `docs/CHANGELOG.md` is append-only. Never delete or rewrite prior entries.
- A code change that breaks a notebook without acknowledgment is incomplete work.
- If updating notebooks is out of scope for the current task: explicitly state that the
  notebooks are not yet updated and why, and file a follow-up task.
- Do not leave `API_REFERENCE.md` pointing to classes or parameters that no longer exist.
