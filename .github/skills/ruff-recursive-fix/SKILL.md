---
name: ruff-recursive-fix
description: "Run ruff linter iteratively to fix all lint issues in the qubox codebase. Use when: running ruff checks, fixing lint errors, enforcing code style, cleaning up imports, running autofix, or any request like 'lint the code', 'fix ruff errors', 'clean up style', 'run ruff', or 'format code'."
argument-hint: "Target path to lint (e.g., 'qubox/', 'qubox_tools/', 'tests/'). Empty = whole repo."
---

# Ruff Recursive Fix Skill

## When to Use

- Running lint checks across the codebase
- Fixing ruff errors after a refactor
- Cleaning up imports, formatting, or style issues
- Enforcing the project's 120-char line length
- Any request mentioning "ruff", "lint", "format", or "style"

## Project Ruff Configuration

qubox uses ruff configured in `pyproject.toml`:
- **Line length**: 120 characters
- **Target**: Python 3.12
- Read `pyproject.toml` `[tool.ruff]` section before starting to know the exact rule set

## Procedure

### Step 1 — Baseline Analysis

```bash
# Full project with config from pyproject.toml
ruff check qubox/ qubox_tools/ tests/

# Specific folder
ruff check qubox/legacy/experiments/

# Count findings by rule
ruff check qubox/ --statistics
```

Classify findings:
- **Autofixable safe** — ruff can fix without behavioral change
- **Autofixable unsafe** — ruff can fix but may change behavior
- **Manual** — requires human judgment

If no findings, stop.

### Step 2 — Safe Autofix Pass

```bash
# Apply safe fixes only
ruff check qubox/ --fix

# Format after fixing
ruff format qubox/

# Re-check for remaining issues
ruff check qubox/
```

Review the diff after each fix pass for semantic correctness.

### Step 3 — Unsafe Autofix Pass

Only run if findings remain and the change is appropriate:

```bash
# Apply unsafe fixes (review carefully)
ruff check qubox/ --fix --unsafe-fixes

# Format
ruff format qubox/

# Re-check
ruff check qubox/
```

Review each unsafe fix carefully — these may change behavior.

### Step 4 — Manual Remediation

For remaining findings:

1. Fix directly in code when there is a clear, safe correction
2. Keep edits minimal and local
3. Run `ruff format` on changed files
4. Re-run `ruff check`

### Step 5 — Suppression Decision

Use `# noqa: <RULE>` only when ALL of these are true:

- The rule conflicts with required behavior (e.g., QUA API patterns, hardware API conventions)
- Refactoring would be disproportionate to the value
- The suppression is narrow (single line, explicit rule code)

Add a brief reason comment for non-obvious suppressions:
```python
from qm.qua import *  # noqa: F403 — QUA star import is intentional per QM convention
```

### Step 6 — Recursive Loop

Repeat steps 2–5 until one of:
- `ruff check` returns clean
- Remaining findings require architectural decisions (present to user)
- Remaining findings are intentionally suppressed with rationale

### Step 7 — Report

```markdown
## Ruff Fix Report

| Metric | Value |
|--------|-------|
| Scope | qubox/, qubox_tools/, tests/ |
| Iterations | N |
| Safe fixes applied | N |
| Unsafe fixes applied | N |
| Manual fixes | N |
| Suppressions added | N |
| Remaining (user decision) | N |

### Suppressions
| File | Line | Rule | Reason |
|------|------|------|--------|

### Remaining Issues (need user decision)
| File | Line | Rule | Options |
|------|------|------|---------|
```

## Rules

- Always read `pyproject.toml` `[tool.ruff]` first to know the configured rules
- Run `ruff format` after every fix pass (formatting + linting are separate concerns)
- Never suppress without an explicit reason
- If multiple valid solutions exist, ask the user before choosing
- Preserve `from __future__ import annotations` in every module (never remove)
