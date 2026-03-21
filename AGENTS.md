# AGENTS.md — qubox Agent Configuration

> **This repository controls real quantum hardware. Physical correctness and compiled-program
> fidelity are never optional. Read this document before making any change.**

---

## 1. Quick-Start Decision Tree

```
START
  │
  ├─ What is the task?
  │
  ├─► CODE CHANGE (non-QUA)
  │     Read: README.md, API_REFERENCE.md
  │     Apply: §2 Priority, §3 Checklist, §8 Change Protocol, §9 Docs Sync
  │
  ├─► QUA / COMPILATION / PULSE-SEQUENCE WORK
  │     Read: README.md, standard_experiments.md,
  │           limitations/qua_related_limitations.md (if exists)
  │     Apply: §6 QUA Protocol, §7 Trust Gates, §8 Change Protocol
  │     Validate: compile → simulate → verify (§6)
  │
  ├─► NEW EXPERIMENT
  │     Read: README.md, API_REFERENCE.md, standard_experiments.md,
  │           qubox/experiments/ (existing pattern), relevant notebooks
  │     Apply: §6 QUA Protocol, §7 Trust Gates, §8 Change Protocol, §9 Docs Sync
  │
  ├─► DOCS-ONLY CHANGE
  │     Read: API_REFERENCE.md, docs/CHANGELOG.md
  │     Apply: §9 Docs Sync Rules
  │
  ├─► NOTEBOOK / EXAMPLE WORK
  │     Read: README.md, API_REFERENCE.md, the specific notebook(s)
  │     Apply: §8 Change Protocol, §9 Docs Sync
  │
  ├─► REFACTOR
  │     Read: README.md, API_REFERENCE.md, affected modules
  │     Apply: §2 Priority (backward compat = high), §8 Change Protocol
  │     Test: unit tests + standard experiments if pulse path touched
  │
  └─► BUG FIX
        Read: affected module(s), relevant test(s)
        Apply: §8 Change Protocol (scope: minimal), §9 Docs Sync if user-visible
```

---

## 2. Priority Hierarchy

When two policies conflict, the higher-numbered priority wins.

1. **Physical correctness / hardware safety** — Compiled program behavior must match intent. A mismatch is never silently acceptable. Real hardware time is expensive; incorrect programs waste it.
2. **Backward compatibility** — Do not rename or remove public APIs without explicit user approval. Existing notebooks and user workflows must not silently break.
3. **Documentation consistency** — If user-visible behavior changes, docs change in the same task. Stale docs are a form of silent breakage.
4. **Minimal change scope** — The smallest correct change wins. No unrelated cleanup. No speculative refactoring.
5. **Reproducibility** — Changes must be explainable, inspectable, and re-runnable. Validation results must be logged or reported.
6. **Code clarity** — Prefer readable, structurally consistent code over clever abstraction.

---

## 3. Startup Checklist

Complete these before writing any code or documentation:

- [ ] Read `README.md` — understand project purpose, architecture, and entry points.
- [ ] Read `API_REFERENCE.md` — if the task touches public API.
- [ ] Read `standard_experiments.md` — if the task touches QUA compilation, pulse sequences, or experiment structure.
- [ ] Read `limitations/qua_related_limitations.md` — if it exists and the task is QUA-related.
- [ ] Read the relevant notebook(s) — if the task affects usage examples or notebooks.
- [ ] Confirm Python version (3.12.13 preferred; 3.11.8 on ECE-SHANKAR-07 only). See §4.
- [ ] Confirm QM API version is 1.2.6. Do not assume other versions.
- [ ] If simulator validation is required: confirm hosted server accessibility (see §4).
- [ ] Understand the existing code structure before proposing new abstractions.

---

## 4. Environment & Backend

### Python

| Version | Status |
|---|---|
| **3.12.10** | **Required (installed default)** |
| 3.11.8 | Fallback — ECE-SHANKAR-07 only (hardware access machine) |
| Any other | **Forbidden** unless user explicitly authorizes |

Do not silently change the Python version. If the installed version differs, report it.

### Hardware Stack

- **Backend:** Quantum Machines OPX+ + Octave
- **QUA / QM API:** version `1.2.6` — do not assume compatibility with other versions
- **Architecture ref:** `qubox/legacy/docs/ARCHITECTURE.md`

### Hosted Server

```python
host         = "10.157.36.68"
cluster_name = "Cluster_2"
```

Use this configuration for simulator validation and real execution. Do not silently substitute a different host or cluster. If the server is unreachable, report that clearly and fall back to best available path.

### Reference Documentation

| Resource | URL |
|---|---|
| QM General Docs | https://docs.quantum-machines.co/1.2.6/ |
| Simulator API | https://docs.quantum-machines.co/1.2.6/docs/API_references/simulator_api/ |
| Octave API | https://docs.quantum-machines.co/1.2.6/docs/API_references/qm_octave/ |
| OPX+ / QM API | https://docs.quantum-machines.co/1.2.6/docs/API_references/qm_api/ |
| QUA Tutorials | https://github.com/qua-platform/qua-libs/tree/main/Tutorials |

---

## 5. Prompt Logging Policy

Every agent task must be logged for auditability and reproducibility.

**File location:** `past_prompt/`
**Naming:** `past_prompt/YYYY-MM-DD_HH-MM-SS_<short_task_name>.md`

Each log must contain:
- Original prompt / request
- Produced response or summary of changes
- Target files modified
- Task context (why, constraints, assumptions)

**Rules:**
- Never overwrite a prior log. Each run gets its own file.
- If a prompt is revised multiple times, each meaningful revision is a separate file.
- Use `tools/log_prompt.py` to generate logs automatically.

---

## 6. QUA Compilation & Validation Protocol

> **The compiled QUA program is the source of truth. Written code is intent. Compiled behavior is reality. When they differ, reality wins — and the discrepancy must be reported.**

### Validation Steps (required for any QUA-touching change)

1. **Compile** — Run the QUA program builder. Compilation must complete in **< 1 minute**. If it exceeds 1 minute, report it.
2. **Simulate** — Run through the hosted QM simulator (`host = "10.157.36.68"`, `cluster_name = "Cluster_2"`).
3. **Verify** — Inspect the simulated output for:
   - Correct pulse ordering and timing
   - Correct control flow (loops, conditionals, sweeps)
   - Correct measurement placement
   - Correct frame / phase updates
   - Multi-element alignment behavior

### Validation Shortcuts (for quick structural checks)

- Set `n_avg = 1` unless averaging is what is being tested.
- Shorten idle periods (thermal relaxation waits, etc.) to the minimum needed to verify structure.
- Simulate only up to the end of the pulse sequence (state prep → experiment body → measurement).
- For long-wait experiments (e.g., T1 with 1000+ clock cycle delays): shorten the wait artificially for simulation; verify structure, not duration.

### Reporting Requirements

- If compiled behavior does not match intent: report the discrepancy explicitly.
- If a mismatch cannot be fixed (hardware limitation, compilation artifact): document it in `limitations/qua_related_limitations.md`.
- **Never silently accept a mismatch between intended and compiled behavior.**

### Tools

- `tools/validate_qua.py` — command-line validation helper. Use `--quick` for fast structural checks.

---

## 7. Standard Experiments (Trust Gates)

`standard_experiments.md` defines reference pulse protocols that act as trust gates for compilation logic.

**Rule:** If your change touches pulse-sequence generation, compilation, scheduling, or QUA translation — run the relevant standard experiments and verify they still pass.

- Failure = do not ship without explanation and explicit user approval.
- If a standard experiment becomes invalid from a legitimate change: update `standard_experiments.md`, explain why, and get user acknowledgment.
- Passing standard experiments does not prove total correctness, but failing them is a red flag that must not be ignored.

---

## 8. Change Protocol

### Scope
- Make the **smallest correct change** that fully addresses the task.
- Do not perform unrelated cleanup.
- Do not introduce new abstractions unless there is repeated structure that clearly justifies them.
- Extend existing patterns before creating new ones.

### Backward Compatibility
- Do not rename or remove public API elements without explicit user approval.
- If a breaking change is necessary:
  1. Update `API_REFERENCE.md` with the change and migration path.
  2. Update `docs/CHANGELOG.md`.
  3. Update affected notebooks and examples.

### Testing
Every change must have at least one of:
- [ ] Unit test in `tests/`
- [ ] Validation script run and result reported
- [ ] Simulator check completed (§6)
- [ ] Standard experiment verified (§7)

### Known Limitations
- Document explicitly in `limitations/qua_related_limitations.md`.
- Never hide a limitation by silently working around it.

---

## 9. Documentation Sync Rules

> **If user-visible behavior changes, documentation changes in the same task.**

"Documentation" means:
- `API_REFERENCE.md` — canonical public API reference
- `docs/CHANGELOG.md` — append-only change log
- Relevant notebooks under `notebooks/`

Documentation sync is **required** when:
- New public class or function is added
- Parameter is renamed or removed
- Default value changes
- Feature is removed or deprecated
- Behavior changes (even subtly)
- Backend support changes
- Workflow changes visible to users

**Notebook rule:** A code change that breaks a notebook without acknowledgment is incomplete work. Either update the notebook, mark it as legacy, or replace it.

---

## 10. Tooling Policy

- Tools live in `tools/`. Do not scatter utilities elsewhere.
- **Reuse before duplicating.** Check `tools/` for existing scripts before writing new ones.
- **Improve shared tools** rather than creating parallel one-off scripts.
- If a tool becomes part of regular workflow: add a usage note to `tools/` or mention it in `README.md`.
- Keep tools general-purpose. Avoid narrow one-use scripts unless the task clearly requires it.

### Key Tools

| Tool | Purpose |
|---|---|
| `tools/validate_qua.py` | Compile + simulate a QUA program against the hosted server |
| `tools/log_prompt.py` | Log agent prompts to `past_prompt/` |
| `tools/validate_standard_experiments_simulation.py` | Run standard experiments against simulator |

---

## 11. File & Repo Hygiene

- Place new files in logically appropriate directories (not the repo root).
- No scattered temporary scripts or ad-hoc notes in unrelated directories.
- Filenames must be descriptive and stable — avoid `temp_`, `new_`, `test2_` prefixes.
- The repository must remain navigable to a new contributor who has never seen it.

### Directory Guide

| Directory | Contents |
|---|---|
| `qubox/` | Main package — public API and modern implementation |
| `qubox/legacy/` | Full copy of former `qubox_v2_legacy` — do not delete without confirming notebook deps are migrated |
| `qubox_tools/` | Analysis, fitting, plotting utilities |
| `qubox_lab_mcp/` | Lab MCP server |
| `tools/` | Agent and developer utilities |
| `notebooks/` | Usage examples and workflow demos |
| `past_prompt/` | Agent prompt logs (append-only) |
| `docs/` | CHANGELOG and extended documentation |
| `tests/` | Unit and integration tests |
| `limitations/` | Known QUA/hardware limitations |
| `.github/skills/` | GitHub Copilot / agent skill files |
| `.skills/` | Claude Code skill files |

---

## 12. Completion Report Template

Fill in and output this report at the end of every substantial task:

```markdown
## Task Completion Report
**Date:** YYYY-MM-DD HH:MM
**Task:** <one-line summary>

### Changes Made
- ...

### Why
- ...

### Assumptions
- ...

### Validation Performed
- [ ] Compiled successfully
- [ ] Simulator check passed (host: 10.157.36.68, cluster: Cluster_2)
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)

### What Remains Uncertain
- ...

### Limitations Discovered
- ...
```

---

## 13. Design Philosophy Reference

| Value | Meaning |
|---|---|
| **User simplicity** | Experiment definitions should read like physics, not boilerplate. Expose only what the user needs to configure. |
| **Backend fidelity** | The compiled QUA program must match intent. Discrepancies are bugs, not acceptable approximations. |
| **Inspectability** | Pulse sequences, timing, and control flow must be readable and simulatable. Black-box behavior is not acceptable. |
| **Reproducibility** | Every experiment run must be re-runnable with the same result from the same config. Log everything. |
| **Documentation consistency** | Code and docs must stay in sync. Stale documentation is a form of technical debt that breaks real experiments. |
| **Extensibility** | New cQED experiments should slot in without rewriting existing infrastructure. Follow existing class patterns. |
| **Practical usability** | The primary users are experimental physicists, not software engineers. Clarity and correctness over elegance. |

> **This repository supports real experimental workflows. Readability, reproducibility, and
> physical correctness matter more than clever abstraction. When in doubt, be explicit.**
