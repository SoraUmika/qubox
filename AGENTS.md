# AGENTS.md — qubox Agent Configuration

**This repository controls real quantum hardware. Physical correctness is non-negotiable.**

---

## §1. Task Routing

| Task Type | Read First | Key Sections |
|-----------|-----------|-------------|
| Code change (non-QUA) | README, API_REFERENCE | §2, §8, §9 |
| QUA / compilation / pulses | README, standard_experiments, limitations/ | §6, §7, §8 |
| New experiment | README, API_REFERENCE, standard_experiments, existing experiments | §6–§9 |
| Docs-only | API_REFERENCE, CHANGELOG | §9 |
| Notebook work | README, the notebook(s), §15 hang budgets | §8, §9, §15 |
| Refactor | README, API_REFERENCE, affected modules | §2, §8 |
| Legacy migration | README, API_REFERENCE, §14 legacy ref | §6–§9, §14 |
| Bug fix | Affected module(s), test(s) | §8, §9 |

---

## §2. Priority Hierarchy (highest wins)

1. **Physical correctness / hardware safety** — compiled behavior must match intent
2. **Backward compatibility** — no public API removal without explicit approval
3. **Documentation consistency** — user-visible changes = docs changes in same task
4. **Minimal change scope** — smallest correct change, no unrelated cleanup
5. **Reproducibility** — explainable, inspectable, re-runnable
6. **Code clarity** — readable over clever

---

## §4. Environment

| Item | Value |
|------|-------|
| Python | **3.12.10** required; all others forbidden unless user authorizes |
| QM API | 1.2.6 — do not assume other versions |
| Hardware | OPX+ + Octave |
| Server | `host="10.157.36.68"`, `cluster_name="Cluster_2"` |
| Style | PEP 8, ruff, 120-char lines, `from __future__ import annotations` |
| Models | Pydantic v2; frozen dataclasses for identity objects |

**Reference docs:** [QM Docs](https://docs.quantum-machines.co/1.2.6/) · [Simulator API](https://docs.quantum-machines.co/1.2.6/docs/API_references/simulator_api/) · [Octave API](https://docs.quantum-machines.co/1.2.6/docs/API_references/qm_octave/) · [OPX+ API](https://docs.quantum-machines.co/1.2.6/docs/API_references/qm_api/)

Do not silently change the Python version or substitute a different server.

---

## §5. Prompt Logging

Log every task to `past_prompt/YYYY-MM-DD_HH-MM-SS_<task>.md`. Use `tools/log_prompt.py`.
Never overwrite prior logs. Each run gets its own file.

---

## §6. QUA Validation Protocol

> Compiled QUA behavior is the source of truth. Mismatches must be reported, never silently accepted.

**Required for any QUA-touching change:**

1. **Compile** — must finish in < 1 min
2. **Simulate** — on hosted server (§4); use `tools/validate_qua.py --quick`
3. **Verify** — pulse ordering, timing, control flow, measurements, alignment

**Shortcuts:** `n_avg=1`, shorten idle waits, minimum simulation duration.

**Mismatches:** report explicitly. Unfixable → document in `limitations/qua_related_limitations.md`.

---

## §7. Standard Experiments (Trust Gates)

`standard_experiments.md` defines trust-gate protocols. If your change touches pulse-sequence
generation, compilation, scheduling, or QUA translation: verify relevant standard experiments
still pass. Failure = do not ship without explanation and user approval.

---

## §8. Change Protocol

### Scope

- Make the smallest correct change that fully addresses the task.
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

## §9. Documentation Sync

> User-visible behavior change = docs change in the same task.

Update these when public API, defaults, behavior, or workflow changes:
- `API_REFERENCE.md` — public API reference
- `docs/CHANGELOG.md` — append-only change log
- Affected `notebooks/` — if usage pattern changes

### §9.1 Notebook Rules
- Notebooks use zero-padded sequential numbering (e.g., `00_hardware_defintion.ipynb`)
- New experiments → new notebook (don't append to existing ones)
- Run sequentially from lowest prerequisite; every campaign starts with `00_hardware_defintion.ipynb`
- A code change that breaks a notebook without acknowledgment is incomplete work

---

## §10. Tooling

Tools live in `tools/`. Reuse before creating new ones.

| Tool | Purpose |
|------|---------|
| `tools/validate_qua.py` | Compile + simulate QUA against hosted server |
| `tools/log_prompt.py` | Log agent prompts to `past_prompt/` |
| `tools/validate_standard_experiments_simulation.py` | Run standard experiments against simulator |

---

## §11. File Hygiene

| Directory | Contents |
|-----------|----------|
| `qubox/` | Main package — public API, experiments, calibration, hardware, QUA programs |
| `qubox_tools/` | Analysis toolkit — fitting, plotting, algorithms, optimization |
| `qubox_lab_mcp/` | Lab MCP server |
| `tools/` | Agent and developer utilities |
| `notebooks/` | Numbered sequential experiment notebooks |
| `tests/` | Unit and integration tests |
| `docs/` | CHANGELOG, architecture docs |
| `samples/` | Sample and cooldown data |
| `past_prompt/` | Agent prompt logs (append-only) |
| `limitations/` | Known QUA/hardware limitations |
| `.github/skills/` | GitHub Copilot agent skill files |

No scattered temp scripts, no files at repo root, descriptive filenames only.

---

## §12. Completion Report

End every substantial task with:

```markdown
## Task Completion Report
**Date:** YYYY-MM-DD HH:MM  |  **Task:** <one-line summary>
### Changes Made — ...
### Validation — [ ] Compiled  [ ] Simulated  [ ] Standard exps  [ ] Tests  [ ] Docs
### Assumptions — ...
### What Remains Uncertain — ...
### Limitations Discovered — ...
```

---

## §13. Design Values

User simplicity · Backend fidelity · Inspectability · Reproducibility · Documentation consistency · Extensibility · Practical usability for experimental physicists.

---

## §14. Legacy Reference & Migration

Legacy codebase at `C:\Users\jl82323\Box\Shyam Shankar Quantum Circuits Group\Users\Users_JianJun\JJL_Experiments` is the behavioral ground truth (read-only). Reference notebook: `post_cavity_experiment_legacy.ipynb`.

**Migration:** One experiment at a time: study legacy → implement in qubox → validate equivalence (§6) → create numbered notebook → update docs. Legacy behavior is the reference; discrepancies must be reported. Do not modify the legacy codebase.

---

## §15. Notebook Hang Recovery

### Timeout Budgets

| Cell Type | Warn | Hard Interrupt |
|-----------|------|----------------|
| Import / env setup | 30s | 60s |
| Hardware connection | 30s | 90s |
| QUA compilation | 45s | 120s |
| Simulator execution | 60s | 180s |
| Measurement sweep | 2min | 10min |
| Long averaging (production) | warn every 5min | do not auto-kill |
| Data processing / plotting | 30s | 120s |

### Recovery Rules

1. **Never retry a hung cell without changing inputs.** Identical inputs = identical hang.
2. **Connection hangs:** Ping `10.157.36.68` first. Unreachable → stop. Stale handle → restart kernel + re-run `00_hardware_defintion.ipynb`.
3. **Compilation/simulation hangs:** Interrupt, reduce complexity (`n_avg=1`, shorter waits), retry once. Still hanging → document in `limitations/`.
4. **Measurement hangs:** Check `n_avg`, sweep range, wait times. After interrupt, verify no orphaned hardware job (`qm.get_running_job()`).
5. **Post-hang:** Confirm no running hardware job, QM connection valid, shared state correct. If uncertain → clean re-run from `00_hardware_defintion.ipynb`.
6. **Log every hang** in §12 report and `limitations/qua_related_limitations.md` if reproducible.
