---
name: ruff-recursive-fix
description: "Run ruff linter iteratively to fix all lint issues in the qubox codebase. Use when: running ruff checks, fixing lint errors, enforcing code style, cleaning up imports, running autofix, or any request like 'lint the code', 'fix ruff errors', 'clean up style', 'run ruff', or 'format code'."
argument-hint: "Target path to lint (e.g., 'qubox/', 'qubox_tools/', 'tests/'). Empty = whole repo."
---

# Ruff Recursive Fix

## Setup

Read `pyproject.toml` `[tool.ruff]` section first to know configured rules. Line length: 120, target: Python 3.12.

## Procedure

1. **Baseline:** `ruff check <target> --statistics` — classify: autofixable safe, unsafe, manual.
2. **Safe autofix:** `ruff check <target> --fix` → `ruff format <target>` → re-check. Review diff.
3. **Unsafe autofix** (if needed): `ruff check <target> --fix --unsafe-fixes` → format → re-check. Review carefully.
4. **Manual fixes:** Fix remaining issues directly. Keep edits minimal.
5. **Suppression:** Use `# noqa: <RULE>` only when rule conflicts with required behavior and refactoring is disproportionate. Always include reason comment.
6. **Loop:** Repeat 2–5 until clean or remaining issues need user decision.

## Rules

- Run `ruff format` after every fix pass
- Never suppress without explicit reason
- Preserve `from __future__ import annotations` (never remove)
- If multiple valid solutions exist, ask user before choosing
