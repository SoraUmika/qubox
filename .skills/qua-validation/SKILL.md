---
name: qua-validation
description: >
  Use this skill whenever writing, modifying, auditing, or reviewing QUA programs or any code
  that compiles to QUA. This includes pulse-sequence generation, experiment compilation,
  scheduling logic, QUA translation, and any work touching the Quantum Machines backend.
  Always use this skill if the task involves the words "QUA", "compile", "pulse", "sequence",
  "experiment", "OPX", "Octave", or "simulator".
---

# QUA Compilation & Validation Skill

## When to Use

- Writing a new QUA program or experiment class
- Modifying existing pulse-sequence generation or scheduling logic
- Auditing compiled behavior against intended behavior
- Reviewing any code path that eventually calls `qm.qua` or the QM API
- Debugging timing, alignment, measurement placement, or control-flow issues
- Any task that mentions: QUA, compile, pulse, sequence, OPX, Octave, simulator

## How to Use

### Step 1 — Read References

Read these files before starting:

- `standard_experiments.md` — trust-gate protocols; understand what baseline behavior looks like
- `limitations/qua_related_limitations.md` — known mismatches and hardware constraints
- `API_REFERENCE.md` — public experiment API

### Step 2 — Write or Modify

Make your change. Follow existing class patterns in `qubox/experiments/` and
`qubox/legacy/experiments/`. Do not introduce new abstractions without justification.

### Step 3 — Compile

Run the QUA program builder. Target: **< 1 minute compilation time**.

```python
# Minimal compilation check
from qubox.session import Session
session = Session.open(sample_id="test", cooldown_id="test", connect=False)
experiment = MyExperiment(session.legacy_session)
build = experiment.build_plan(...)
print("Compiled OK:", build)
```

If compilation exceeds 1 minute, report it before proceeding.

### Step 4 — Simulate

Connect to the hosted QM server and run the simulator:

```python
from qm import QuantumMachinesManager, SimulationConfig

host         = "10.157.36.68"
cluster_name = "Cluster_2"

qmm = QuantumMachinesManager(host=host, cluster_name=cluster_name)
simulation_config = SimulationConfig(duration=2000)  # clock cycles; adjust as needed

# n_avg=1 for quick validation; shorten any idle periods
job = qmm.simulate(config, program, simulation_config)
samples = job.get_simulated_samples()
```

Use `tools/validate_qua.py --quick` for fast structural validation.

### Step 5 — Verify

Inspect the simulated output for:

- [ ] Correct pulse ordering (right pulses at right times on right elements)
- [ ] Correct timing (no unexpected gaps or overlaps)
- [ ] Correct control flow (loops, conditionals, sweeps execute correctly)
- [ ] Correct measurement placement (readout after state preparation)
- [ ] Correct frame / phase updates (appear at expected points)
- [ ] Multi-element alignment (simultaneous pulses are aligned)

### Step 6 — Report or Document

- If compiled behavior matches intent: check all boxes above and proceed.
- If there is a mismatch:
  - Report it explicitly. Do not silently accept it.
  - If it can be fixed: fix it, re-validate.
  - If it cannot be fixed (hardware limitation, API constraint): document it in
    `limitations/qua_related_limitations.md` with the experiment name, QUA version, and description.

## Reference Files

| File | When to Read |
| --- | --- |
| `standard_experiments.md` | Always — understand baseline behavior |
| `limitations/qua_related_limitations.md` | Before starting — know existing constraints |
| `API_REFERENCE.md` | When touching public experiment API |
| `qubox/legacy/experiments/` | When following existing experiment patterns |
| `qubox/legacy/programs/` | When working with QUA program builders |

## Hosted Server Config

```python
host         = "10.157.36.68"
cluster_name = "Cluster_2"
```

Never substitute a different server without reporting it. If the server is unreachable,
report that and fall back to best available path.

## Validation Shortcuts

| Shortcut | When to Use |
| --- | --- |
| `n_avg=1` | Any structural validation (not testing averaging) |
| Shorten idle waits | When verifying structure, not physical wait duration |
| Minimum simulation duration | Simulate only through end of pulse sequence |
| Omit calibration sweeps | When only validating a single sequence variant |

## Standard Experiment Trust Gates

After any QUA-touching change, verify that relevant standard experiments in
`standard_experiments.md` still pass. If they fail:

- Do not ship without explanation.
- Get explicit user approval.
- If the failure is justified by a legitimate change: update `standard_experiments.md`.

## Pre-Submission Checklist

Before marking QUA work as done:

- [ ] Compilation completes in < 1 minute
- [ ] Simulator run completed on hosted server (10.157.36.68 / Cluster_2)
- [ ] Pulse ordering verified in simulation output
- [ ] Timing verified in simulation output
- [ ] Control flow verified in simulation output
- [ ] Measurements verified in simulation output
- [ ] Standard experiments checked
- [ ] Mismatches reported or documented in limitations/
- [ ] `limitations/qua_related_limitations.md` updated if needed
