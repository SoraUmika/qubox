---
name: prompt-logging
description: >
  Use this skill after completing any task to log the prompt and response. Every agent
  interaction must be logged for auditability and reproducibility. Trigger at the end of
  every task, always — even for small changes.
---

# Prompt Logging

## Usage

**Preferred:** `python tools/log_prompt.py --task "<name>" --prompt "<request>" --response "<summary>" --files "<changed files>"`

**Manual fallback:** Create `past_prompt/YYYY-MM-DD_HH-MM-SS_<task_name>.md` with: date, task summary, original request, changes made, files modified, validation performed.

## Rules

- Never overwrite prior logs — each run gets its own file
- Task names: short, hyphen-separated, lowercase (e.g., `fix-iq-blob-timing`)
- Do not create subdirectories inside `past_prompt/`
