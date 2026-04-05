---
name: security-review
description: "Review qubox codebase for security issues specific to quantum hardware control software. Use when: auditing network connections to QM hardware, checking for exposed server addresses or credentials, reviewing hardware control flow safety, inspecting session state integrity, or any request like 'security review', 'check for secrets', 'audit connections', or 'is the code secure'."
argument-hint: "Scope to review (e.g., 'qubox/backends/', 'notebooks/', 'full codebase')"
---

# Security Review

## Context

qubox controls real quantum hardware. Primary risks: hardware safety (incorrect control signals), network exposure (server addresses/credentials), data integrity (calibration corruption), session state (stale/corrupted state → incorrect experiments).

## Scan Areas

1. **Secrets & exposure** — Search for hardcoded passwords, tokens, API keys, IP addresses in non-config files. Server addresses (`10.157.36.68`) are acceptable in `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, and `qubox/legacy/configuration/`.
2. **Hardware safety** — Pulse amplitude/frequency bounds validation, connection lifecycle (open/use/close), error propagation (not silently caught), orphaned job prevention (`qm.get_running_job()`).
3. **Data integrity** — Atomic writes in CalibrationStore, rollback support in `apply_patch()`, input validation before compilation, no pickle for untrusted data.
4. **Network** — No TLS bypass, connection timeouts set, correct server address used.

## Severity Guide

| Severity | Example |
|----------|---------|
| CRITICAL | Unbounded amplitude, exposed passwords, hardware damage risk |
| HIGH | Missing rollback, disabled TLS, data integrity risk |
| MEDIUM | Missing timeouts, broad exception catch |
| LOW | Verbose error messages, missing input validation |

## Rules

- Never auto-apply patches — present for human review
- Include file path and line number for every finding
- Hardware safety findings are always CRITICAL or HIGH
