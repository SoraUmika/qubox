---
name: security-review
description: "Review qubox codebase for security issues specific to quantum hardware control software. Use when: auditing network connections to QM hardware, checking for exposed server addresses or credentials, reviewing hardware control flow safety, inspecting session state integrity, or any request like 'security review', 'check for secrets', 'audit connections', or 'is the code secure'."
argument-hint: "Scope to review (e.g., 'qubox/backends/', 'notebooks/', 'full codebase')"
---

# Security Review Skill

## When to Use

- Auditing code that connects to the QM hosted server (10.157.36.68)
- Checking for hardcoded credentials, API keys, or server addresses in committed code
- Reviewing hardware control flow for safety (preventing accidental hardware damage)
- Inspecting session state integrity and data persistence security
- Before deploying or sharing notebooks externally
- Any request mentioning "security", "credentials", "secrets", or "audit"

## Context

qubox controls real quantum hardware (OPX+ + Octave). Security concerns are different
from typical web applications — the primary risks are:

1. **Hardware safety** — Incorrect control signals can damage equipment
2. **Network exposure** — Server addresses and connection details in committed code
3. **Data integrity** — Calibration data corruption or unauthorized modification
4. **Session state** — Stale or corrupted session state leading to incorrect experiments

## Procedure

### Step 1 — Scope Resolution

Determine what to scan:
- If a path was provided, scan only that scope
- If no path, scan: `qubox/`, `qubox_tools/`, `qubox_lab_mcp/`, `notebooks/`, `tools/`
- Identify connection-related code (QM API calls, network connections)

### Step 2 — Secrets & Exposure Scan

Search ALL files for:

```
# Patterns to grep for
- IP addresses (especially 10.157.36.68 in non-config files)
- Hardcoded passwords, tokens, API keys
- Connection strings with credentials embedded
- Private keys or certificates
- .env files with secrets
```

**Acceptable locations** for server addresses:
- `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md` (documentation)
- `qubox/legacy/configuration/` (hardware config — expected)
- Notebook cells that explicitly set up connections

**Unacceptable locations**:
- Test files with real server addresses (should use mocks)
- Utility scripts with hardcoded credentials
- Any file with passwords or tokens

### Step 3 — Hardware Safety Review

For code that sends commands to the OPX+:

1. **Pulse amplitude bounds** — Are amplitudes validated before sending to hardware?
2. **Frequency bounds** — Are frequency values checked against hardware limits?
3. **Connection lifecycle** — Are QM connections properly opened, used, and closed?
4. **Error handling** — Do hardware errors propagate correctly (not silently caught)?
5. **Job management** — Are orphaned hardware jobs prevented? (`qm.get_running_job()`)

### Step 4 — Data Integrity Review

For calibration and session persistence:

1. **Atomic writes** — Does `CalibrationStore` use atomic write patterns (temp file + rename)?
2. **Rollback support** — Can `apply_patch()` revert on failure?
3. **Input validation** — Are experiment parameters validated before compilation?
4. **Deserialization safety** — Is pickle avoided for untrusted data? (Prefer JSON/Pydantic)

### Step 5 — Network Security

1. **No TLS bypass** — Check that certificate validation is not disabled
2. **Connection timeouts** — Are timeouts set on QM connections? (Prevents indefinite hangs)
3. **Server validation** — Is the correct server address used? (Not substituted silently)

### Step 6 — Generate Report

```markdown
## Security Review: [scope]

### Summary
| Severity | Count |
|----------|-------|
| CRITICAL | N |
| HIGH     | N |
| MEDIUM   | N |
| LOW      | N |

### Findings

#### [SEVERITY] Finding Title
- **File**: `path/to/file.py` line N
- **Issue**: Description
- **Risk**: What could go wrong
- **Fix**: Concrete remediation

### Secrets Scan
- [ ] No hardcoded credentials found
- [ ] Server addresses only in expected locations
- [ ] No .env files with secrets committed

### Hardware Safety
- [ ] Amplitude bounds checked
- [ ] Frequency bounds checked
- [ ] Connection lifecycle correct
- [ ] Error handling adequate
```

## Severity Guide

| Severity | Meaning | Example |
|----------|---------|---------|
| CRITICAL | Hardware damage risk or credential exposure | Unbounded amplitude, exposed passwords |
| HIGH | Data integrity risk or connection safety | Missing rollback, disabled TLS |
| MEDIUM | Best practice violation with real risk | Missing timeouts, broad exception catch |
| LOW | Hardening opportunity | Verbose error messages, missing input validation |

## Rules

- Never auto-apply patches — present for human review
- Include file path and line number for every finding
- If the codebase is clean, say so clearly
- Hardware safety findings are always CRITICAL or HIGH — equipment is expensive
