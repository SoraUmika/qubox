---
name: qua-validation
description: >
  Use this skill whenever writing, modifying, auditing, or reviewing QUA programs or any code
  that compiles to QUA. This includes pulse-sequence generation, experiment compilation,
  scheduling logic, QUA translation, and any work touching the Quantum Machines backend.
  Always use this skill if the task involves the words "QUA", "compile", "pulse", "sequence",
  "experiment", "OPX", "Octave", or "simulator".
---

# QUA Validation

## Prereqs

Read before starting: `standard_experiments.md`, `limitations/qua_related_limitations.md`, `API_REFERENCE.md`.

## Protocol

1. **Compile** — Must finish in < 1 min. Use `tools/validate_qua.py --quick` for structural checks.
2. **Simulate** — On hosted server (`10.157.36.68` / `Cluster_2`). Use `n_avg=1`, shorten idle waits.
3. **Verify** — Check: pulse ordering, timing, control flow, measurement placement, frame/phase updates, multi-element alignment.
4. **Trust gates** — Verify relevant standard experiments (`standard_experiments.md`) still pass. Failure = do not ship without user approval.
5. **Report** — Mismatches: report explicitly. Unfixable → `limitations/qua_related_limitations.md`.

## Checklist

- [ ] Compilation < 1 min
- [ ] Simulator run completed on hosted server
- [ ] Pulse ordering, timing, control flow, measurements verified
- [ ] Standard experiments checked
- [ ] Mismatches documented in `limitations/` if needed
