AGENTS.md — qubox Agent Configuration

This repository controls real quantum hardware. Physical correctness and compiled-program
fidelity are never optional. Read this document before making any change.


1. Quick-Start Decision Tree
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
  │     Create: a new numbered notebook under notebooks/ before adding experiment steps
  │     Apply: §6 QUA Protocol, §7 Trust Gates, §8 Change Protocol, §9 Docs Sync
  │
  ├─► DOCS-ONLY CHANGE
  │     Read: API_REFERENCE.md, docs/CHANGELOG.md
  │     Apply: §9 Docs Sync Rules
  │
  ├─► NOTEBOOK / EXAMPLE WORK
  │     Read: README.md, API_REFERENCE.md, the specific notebook(s)
  │     Follow: numbered notebook sequencing rules in §9.1
  │     Apply: §8 Change Protocol, §9 Docs Sync
  │     Watch: apply §15 Hang & Loop Recovery if any cell exceeds its timeout budget
  │
  ├─► REFACTOR
  │     Read: README.md, API_REFERENCE.md, affected modules
  │     Apply: §2 Priority (backward compat = high), §8 Change Protocol
  │     Test: unit tests + standard experiments if pulse path touched
  │
  ├─► EXPERIMENT MIGRATION (legacy → qubox)
  │     Read: README.md, API_REFERENCE.md, standard_experiments.md,
  │           §14 Legacy Reference Codebase
  │     Reference: legacy experiment code + post_cavity_experiment_legacy.ipynb (§14)
  │     Apply: §6 QUA Protocol, §7 Trust Gates, §8 Change Protocol, §9 Docs Sync
  │     Validate: migrated experiment must match legacy behavior before shipping
  │
  └─► BUG FIX
        Read: affected module(s), relevant test(s)
        Apply: §8 Change Protocol (scope: minimal), §9 Docs Sync if user-visible

2. Priority Hierarchy
When two policies conflict, the higher-numbered priority wins.

Physical correctness / hardware safety — Compiled program behavior must match intent. A mismatch is never silently acceptable. Real hardware time is expensive; incorrect programs waste it.
Backward compatibility — Do not rename or remove public APIs without explicit user approval. Existing notebooks and user workflows must not silently break.
Documentation consistency — If user-visible behavior changes, docs change in the same task. Stale docs are a form of silent breakage.
Minimal change scope — The smallest correct change wins. No unrelated cleanup. No speculative refactoring.
Reproducibility — Changes must be explainable, inspectable, and re-runnable. Validation results must be logged or reported.
Code clarity — Prefer readable, structurally consistent code over clever abstraction.


3. Startup Checklist
Complete these before writing any code or documentation:

 Read README.md — understand project purpose, architecture, and entry points.
 Read API_REFERENCE.md — if the task touches public API.
 Read standard_experiments.md — if the task touches QUA compilation, pulse sequences, or experiment structure.
 Read limitations/qua_related_limitations.md — if it exists and the task is QUA-related.
 Read the relevant notebook(s) — if the task affects usage examples or notebooks.
 Identify whether the task belongs in a new numbered notebook under notebooks/.
 If the work is experiment execution or a new experiment type, start from the required prior numbered notebooks before adding a new one.
 Confirm Python version (3.12.13 preferred; 3.11.8 on ECE-SHANKAR-07 only). See §4.
 Confirm QM API version is 1.2.6. Do not assume other versions.
 If simulator validation is required: confirm hosted server accessibility (see §4).
 Understand the existing code structure before proposing new abstractions.
 If the task is an experiment migration: read the legacy reference experiment (§14) and post_cavity_experiment_legacy.ipynb to understand expected behavior.
 If running or executing any notebook cell: apply the timeout budgets from §15 before execution begins. Do not start a cell without a plan for what to do if it hangs.


4. Environment & Backend
Python
VersionStatus3.12.13Required (installed default)3.11.8Fallback — ECE-SHANKAR-07 only (hardware access machine)Any otherForbidden unless user explicitly authorizes
Do not silently change the Python version. If the installed version differs, report it.
If a lab package, notebook, or experiment works under the known-good Python 3.11.8 install but fails under 3.12.x, treat the 3.11.8 environment as the package reference backup before changing qubox code. First inspect the package name, version, and import location from E:\Program Files\Python311\python.exe, then mirror the required install into the active 3.12.x environment and report the dependency gap explicitly.
Hardware Stack

Backend: Quantum Machines OPX+ + Octave
QUA / QM API: version 1.2.6 — do not assume compatibility with other versions
Architecture ref: qubox/legacy/docs/ARCHITECTURE.md

Hosted Server
pythonhost         = "10.157.36.68"
cluster_name = "Cluster_2"
Use this configuration for simulator validation and real execution. Do not silently substitute a different host or cluster. If the server is unreachable, report that clearly and fall back to best available path.
Reference Documentation
ResourceURLQM General Docshttps://docs.quantum-machines.co/1.2.6/Simulator APIhttps://docs.quantum-machines.co/1.2.6/docs/API_references/simulator_api/Octave APIhttps://docs.quantum-machines.co/1.2.6/docs/API_references/qm_octave/OPX+ / QM APIhttps://docs.quantum-machines.co/1.2.6/docs/API_references/qm_api/QUA Tutorialshttps://github.com/qua-platform/qua-libs/tree/main/Tutorials

5. Prompt Logging Policy
Every agent task must be logged for auditability and reproducibility.
File location: past_prompt/
Naming: past_prompt/YYYY-MM-DD_HH-MM-SS_<short_task_name>.md
Each log must contain:

Original prompt / request
Produced response or summary of changes
Target files modified
Task context (why, constraints, assumptions)

Rules:

Never overwrite a prior log. Each run gets its own file.
If a prompt is revised multiple times, each meaningful revision is a separate file.
Use tools/log_prompt.py to generate logs automatically.


6. QUA Compilation & Validation Protocol

The compiled QUA program is the source of truth. Written code is intent. Compiled behavior is reality. When they differ, reality wins — and the discrepancy must be reported.

Validation Steps (required for any QUA-touching change)

Compile — Run the QUA program builder. Compilation must complete in < 1 minute. If it exceeds 1 minute, report it and apply §15 hang recovery.
Simulate — Run through the hosted QM simulator (host = "10.157.36.68", cluster_name = "Cluster_2"). Simulation must complete within the budget defined in §15. If it does not, interrupt, report, and do not proceed to hardware.
Verify — Inspect the simulated output for:

Correct pulse ordering and timing
Correct control flow (loops, conditionals, sweeps)
Correct measurement placement
Correct frame / phase updates
Multi-element alignment behavior



Validation Shortcuts (for quick structural checks)

Set n_avg = 1 unless averaging is what is being tested.
Shorten idle periods (thermal relaxation waits, etc.) to the minimum needed to verify structure.
Simulate only up to the end of the pulse sequence (state prep → experiment body → measurement).
For long-wait experiments (e.g., T1 with 1000+ clock cycle delays): shorten the wait artificially for simulation; verify structure, not duration.

Reporting Requirements

If compiled behavior does not match intent: report the discrepancy explicitly.
If a mismatch cannot be fixed (hardware limitation, compilation artifact): document it in limitations/qua_related_limitations.md.
Never silently accept a mismatch between intended and compiled behavior.

Tools

tools/validate_qua.py — command-line validation helper. Use --quick for fast structural checks.


7. Standard Experiments (Trust Gates)
standard_experiments.md defines reference pulse protocols that act as trust gates for compilation logic.
Rule: If your change touches pulse-sequence generation, compilation, scheduling, or QUA translation — run the relevant standard experiments and verify they still pass.

Failure = do not ship without explanation and explicit user approval.
If a standard experiment becomes invalid from a legitimate change: update standard_experiments.md, explain why, and get user acknowledgment.
Passing standard experiments does not prove total correctness, but failing them is a red flag that must not be ignored.


8. Change Protocol
Scope

Make the smallest correct change that fully addresses the task.
Do not perform unrelated cleanup.
Do not introduce new abstractions unless there is repeated structure that clearly justifies them.
Extend existing patterns before creating new ones.

Backward Compatibility

Do not rename or remove public API elements without explicit user approval.
If a breaking change is necessary:

Update API_REFERENCE.md with the change and migration path.
Update docs/CHANGELOG.md.
Update affected notebooks and examples.



Testing
Every change must have at least one of:

 Unit test in tests/
 Validation script run and result reported
 Simulator check completed (§6)
 Standard experiment verified (§7)

Known Limitations

Document explicitly in limitations/qua_related_limitations.md.
Never hide a limitation by silently working around it.


9. Documentation Sync Rules

If user-visible behavior changes, documentation changes in the same task.

"Documentation" means:

API_REFERENCE.md — canonical public API reference
docs/CHANGELOG.md — append-only change log
Relevant notebooks under notebooks/

9.1 Notebook Experiment Workflow

Calibration and experiment execution flows are split across separate notebooks under notebooks/.
Any later agent task that needs to perform an experiment, or introduce a new experiment type, must create a new notebook instead of appending more workflow to an existing all-in-one notebook.
Notebook filenames must use a zero-padded sequence prefix followed by the purpose, for example 00_hardware_defintion.ipynb.
Standard experiment notebooks are intended to be run sequentially. Start from the lowest-numbered prerequisite notebook and then proceed forward.
Every new cooldown or experiment campaign starts with 00_hardware_defintion.ipynb, which initializes hardware and establishes the shared session context.
notebooks/post_cavity_experiment_context.ipynb remains the source notebook for extracting the split workflow, but future experiment work should land in numbered notebooks.

Documentation sync is required when:

New public class or function is added
Parameter is renamed or removed
Default value changes
Feature is removed or deprecated
Behavior changes (even subtly)
Backend support changes
Workflow changes visible to users

Notebook rule: A code change that breaks a notebook without acknowledgment is incomplete work. Either update the notebook, mark it as legacy, or replace it.

10. Tooling Policy

Tools live in tools/. Do not scatter utilities elsewhere.
Reuse before duplicating. Check tools/ for existing scripts before writing new ones.
Improve shared tools rather than creating parallel one-off scripts.
If a tool becomes part of regular workflow: add a usage note to tools/ or mention it in README.md.
Keep tools general-purpose. Avoid narrow one-use scripts unless the task clearly requires it.

Key Tools
ToolPurposetools/validate_qua.pyCompile + simulate a QUA program against the hosted servertools/log_prompt.pyLog agent prompts to past_prompt/tools/validate_standard_experiments_simulation.pyRun standard experiments against simulator

11. File & Repo Hygiene

Place new files in logically appropriate directories (not the repo root).
No scattered temporary scripts or ad-hoc notes in unrelated directories.
Filenames must be descriptive and stable — avoid temp_, new_, test2_ prefixes.
The repository must remain navigable to a new contributor who has never seen it.

Directory Guide
DirectoryContentsqubox/Main package — public API and modern implementationqubox_tools/Analysis, fitting, plotting utilitiesqubox_lab_mcp/Lab MCP servertools/Agent and developer utilitiesnotebooks/Usage examples, numbered sequential experiment notebooks, and workflow demospast_prompt/Agent prompt logs (append-only)docs/CHANGELOG and extended documentationtests/Unit and integration testslimitations/Known QUA/hardware limitations.github/skills/GitHub Copilot / agent skill files.skills/Claude Code skill files

12. Completion Report Template
Fill in and output this report at the end of every substantial task:
markdown## Task Completion Report
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

### Notebook Execution Health  ← NEW
- [ ] No cells exceeded their §15 timeout budget
- [ ] Any hang or loop detected: described below with recovery action taken
- Hang/loop details (if any): ...

### What Remains Uncertain
- ...

### Limitations Discovered
- ...

13. Design Philosophy Reference
ValueMeaningUser simplicityExperiment definitions should read like physics, not boilerplate. Expose only what the user needs to configure.Backend fidelityThe compiled QUA program must match intent. Discrepancies are bugs, not acceptable approximations.InspectabilityPulse sequences, timing, and control flow must be readable and simulatable. Black-box behavior is not acceptable.ReproducibilityEvery experiment run must be re-runnable with the same result from the same config. Log everything.Documentation consistencyCode and docs must stay in sync. Stale documentation is a form of technical debt that breaks real experiments.ExtensibilityNew cQED experiments should slot in without rewriting existing infrastructure. Follow existing class patterns.Practical usabilityThe primary users are experimental physicists, not software engineers. Clarity and correctness over elegance.

This repository supports real experimental workflows. Readability, reproducibility, and
physical correctness matter more than clever abstraction. When in doubt, be explicit.


14. Legacy Reference Codebase & Experiment Migration

The legacy codebase is the behavioral ground truth for experiment migration. Experiments
defined there have been validated on real hardware and usually produce the correct behavior.
The goal is to incrementally migrate each experiment into qubox while preserving that behavior.

Legacy Location
C:\Users\jl82323\Box\Shyam Shankar Quantum Circuits Group\Users\Users_JianJun\JJL_Experiments
Key Reference Notebook

post_cavity_experiment_legacy.ipynb — demonstrates how experiments are defined and run
in the legacy codebase. This is the primary reference for understanding experiment execution
flow, parameter setup, and expected behavior.

Migration Strategy
The migration from legacy to qubox is incremental — one experiment at a time:

Study the legacy implementation — Read the experiment definition in the legacy codebase
and post_cavity_experiment_legacy.ipynb. Understand the pulse sequence, parameters,
measurement protocol, and expected output.
Implement in qubox — Translate the experiment into qubox's framework (qubox/experiments/),
following existing class patterns and the public API conventions in API_REFERENCE.md.
Validate behavioral equivalence — The migrated experiment must produce the same QUA
program structure, pulse ordering, and measurement behavior as the legacy version:

Compile and simulate (§6 QUA Protocol)
Compare simulated output against legacy behavior
Run standard experiment trust gates (§7) if applicable


Create a numbered notebook — Add a new notebook under notebooks/ that demonstrates
the migrated experiment, following the sequential numbering convention (§9.1).
Document the migration — Update docs/CHANGELOG.md and API_REFERENCE.md if new
public API surfaces are added.

Rules

Legacy behavior is the reference. If the migrated experiment behaves differently from
the legacy version, that discrepancy must be reported and justified — not silently accepted.
Do not modify the legacy codebase. It is read-only reference material.
One experiment per migration task. Keep the scope small and verifiable.
Preserve parameter names and semantics where possible, so users familiar with the legacy
code can transition smoothly.
If the legacy experiment has a known defect, document it in limitations/ and implement
the corrected version in qubox with a clear explanation of what changed and why.


15. Notebook Hang & Infinite-Loop Recovery

A notebook cell that does not finish is not a minor nuisance — it may be holding open a
hardware connection, blocking a shared server resource, or producing silently wrong
intermediate state. Treat every hang as a real incident and respond systematically.

15.1 Timeout Budgets by Cell Type
Before executing any notebook cell, identify its type and apply the corresponding budget.
If the cell does not complete within its budget, it is a hang — apply §15.2 immediately.
Cell TypeWarn AfterHard Interrupt AfterNotesImport / environment setup30 s60 sNetwork imports (e.g. QM package init) can be slow; still cap themHardware connection (QuantumMachinesManager, Octave init)30 s90 sServer unreachable is a common cause; see §15.3QUA compilation (compile, get_config)45 s120 sAlso required by §6 to complete in < 1 minSimulator execution60 s180 sUse --quick / reduced params first (§6 shortcuts)Single measurement / data acquisition sweep2 min10 minReduce n_avg, sweep range, or wait times first (§15.4)Long averaging run (production n_avg)—No auto-kill; warn every 5 minUser-initiated long runs are expected; report progress, do not interruptData processing / fitting / plotting30 s120 sShould never be slow; if it is, report it
Warn = emit a visible message noting elapsed time and expected budget.
Hard interrupt = stop kernel execution (equivalent to Jupyter "interrupt kernel"), then follow §15.2.
15.2 Recovery Decision Tree
When a hang or timeout is detected:
HANG DETECTED
  │
  ├─ Is this a hardware connection cell?
  │     → §15.3 Connection Hang Protocol
  │
  ├─ Is this a QUA compilation cell?
  │     → Interrupt. Report elapsed time and compilation inputs.
  │       Try reducing program complexity (n_avg=1, shorter wait).
  │       If still hanging after second attempt: document in limitations/qua_related_limitations.md.
  │       Do NOT proceed to hardware execution.
  │
  ├─ Is this a simulator execution cell?
  │     → Interrupt. Apply §6 shortcuts (n_avg=1, shorten waits).
  │       Retry once. If second attempt also hangs: report to user, stop.
  │       Do NOT proceed to hardware execution if simulator cannot complete.
  │
  ├─ Is this a measurement / data acquisition cell?
  │     → §15.4 Measurement Hang Protocol
  │
  ├─ Is this a data processing / plotting cell?
  │     → Interrupt. Inspect input data for unexpected size or shape.
  │       Report the anomaly. Do not retry blindly.
  │
  └─ Unknown cell type or cause?
        → Interrupt. Do not retry.
          Report: cell index, elapsed time, last known kernel state.
          Stop the notebook. Await user instruction.
Key rule: Never retry a hung cell more than once without changing something. Identical inputs produce identical hangs.
15.3 Connection Hang Protocol
Hardware and server connection cells are the most common hang source.
Step 1 — Verify server reachability before connecting:
pythonimport subprocess
result = subprocess.run(
    ["ping", "-n", "1", "-w", "2000", "10.157.36.68"],  # Windows
    capture_output=True, text=True
)
reachable = result.returncode == 0
If unreachable: stop immediately. Report that the hosted server at 10.157.36.68 is not responding. Do not attempt to open a QuantumMachinesManager connection against an unreachable host — this will hang indefinitely.
Step 2 — If reachable but connection still hangs:

Interrupt the cell.
Check whether a prior notebook session left an open QM connection (stale handles are a common cause).
If a stale handle is suspected: restart the kernel cleanly, re-run only the hardware definition notebook (00_hardware_defintion.ipynb) from the top, and report what was found.

Step 3 — If connection succeeds but Octave init hangs:

Interrupt. Report which Octave initialization step stalled (LO configuration, mixer calibration, etc.).
Do not proceed with pulse execution if Octave is not fully initialized.

15.4 Measurement Hang Protocol
A measurement loop that runs longer than its hard-interrupt budget, or that produces no new data for > 2 minutes, is presumed hung.
Diagnosis checklist (run mentally before interrupting):

Is n_avg unreasonably large for a structural check? → Reduce to 1 and retry.
Is a sweep range (frequency, amplitude, time) extremely wide? → Narrow it.
Is there a long thermal relaxation wait (wait, reset_qubit) inside the loop? → Apply §6 shortcut: shorten the wait for validation purposes.
Is the loop variable being updated correctly, or is it recalculating the same point? → This is a logic bug; interrupt and fix.

After interrupting a measurement cell:

Check whether the QM job is still running on the hardware side (qm.get_running_job()). If a job is still active on the OPX+, it must be explicitly halted before restarting — do not leave orphaned hardware jobs.
Report the last sweep index or iteration count reached, if obtainable.
Log the hang in the §12 Completion Report under "Notebook Execution Health."

15.5 Infinite-Loop Detection
Not all infinite loops are obvious. Watch for these signals:
SignalLikely CauseCell runs > 2× its hard-interrupt budget with no outputLoop with no progress or exit conditionKernel CPU at 100%, no data appearingPython-side infinite loop (not hardware)Cell produces output at constant rate indefinitelyLoop exit condition never triggeredCell produces no output at all for > hard-interrupt budgetBlocked on I/O, network, or hardware wait
For any of these: interrupt immediately, do not wait to see if it resolves. Report the signal type and the cell contents. A loop that has no exit condition is a code bug — fix it before retrying.
15.6 Post-Hang State Cleanup
After any interrupted cell, the notebook kernel may be in a partially initialized state. Before continuing:

 Confirm no hardware job is still running (qm.get_running_job() returns None or the job has ended).
 Confirm QM connection object is still valid — if in doubt, close and reopen it.
 Confirm all shared state variables (config dicts, qubit parameters, frequency offsets) are still correctly set — a mid-cell interrupt may have left them partially updated.
 If any shared state is uncertain: re-run from 00_hardware_defintion.ipynb rather than assuming the state is clean.

Do not proceed to the next cell if shared state is uncertain. A clean re-run from a known-good checkpoint is always safer than continuing on potentially corrupted state.
15.7 Logging Hangs
Every hang must be logged, even if it resolved cleanly.
In the §12 Completion Report: fill in the "Notebook Execution Health" block.
If the hang is reproducible or unexplained: create an entry in limitations/qua_related_limitations.md:
markdown## Notebook Hang: <notebook_name>, Cell <index>

**Date observed:** YYYY-MM-DD
**Cell type:** <connection | compilation | simulation | measurement | processing>
**Elapsed before interrupt:** <time>
**Inputs / parameters at time of hang:**
- n_avg: ...
- sweep range: ...
- wait time: ...
**Recovery action taken:** <describe>
**Root cause (if known):** <describe or "unknown">
**Workaround:** <describe>
Documented hangs are actionable. Undocumented hangs recur.