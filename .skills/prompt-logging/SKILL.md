---
name: prompt-logging
description: >
  Use this skill after completing any task to log the prompt and response. Every agent
  interaction must be logged for auditability and reproducibility. Trigger at the end of
  every task, always — even for small changes.
---

# Prompt Logging Skill

## When to Use

- At the end of every completed task
- After any agent-generated code change
- After any documentation update
- After any QUA validation run
- After any refactor, bug fix, or new feature

## How to Use

### Option A — Use the Helper Script (preferred)

```bash
python tools/log_prompt.py \
  --task "short_task_name" \
  --prompt "The original user request..." \
  --response "Summary of what was done..." \
  --files "qubox/experiments/foo.py, API_REFERENCE.md"
```

The script generates the timestamped file automatically and never overwrites prior logs.

### Option B — Manual

1. Determine the timestamp: `YYYY-MM-DD_HH-MM-SS` (use the time the task was completed)
2. Determine the task name: short, hyphen-separated, lowercase (e.g., `add-t2-ramsey-experiment`)
3. Create the file: `past_prompt/YYYY-MM-DD_HH-MM-SS_<task_name>.md`
4. Fill in the template below.

## Log File Template

```markdown
# Prompt Log

**Date:** YYYY-MM-DD HH:MM:SS
**Task:** <short one-line description>
**Target files:** <comma-separated list of files changed>

## Original Request

<paste the original user prompt here>

## Response / Changes Made

<summary of what was done>

## Context

<relevant background: why this change was made, what constraints applied>

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated
```

## File Naming Convention

```
past_prompt/YYYY-MM-DD_HH-MM-SS_<short_task_name>.md
```

Examples:

```
past_prompt/2026-03-20_14-35-22_add-t2-ramsey-experiment.md
past_prompt/2026-03-20_09-12-00_fix-iq-blob-timing.md
past_prompt/2026-03-19_22-45-11_update-api-reference-calibration.md
```

## Rules

- **Never overwrite a prior log.** Each task run gets its own file.
- If a filename collision occurs: the helper script appends `_2`, `_3`, etc.
- If a prompt is revised multiple times: each meaningful revision is a separate log file.
- Log files are append-only historical records — never edit them after creation.
- The `past_prompt/` directory must remain organized and navigable for audit.

## Storage Location

```
past_prompt/          ← all logs live here, flat directory
```

Do not create subdirectories inside `past_prompt/`.
