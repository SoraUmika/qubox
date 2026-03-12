# AGENTS.md

## Project Purpose

This repository contains the **qubox API** (main implementation folder: `qubox_v2`), a framework intended to make **cQED experimental design, execution, analysis, and extension easier, clearer, and more reproducible**.

Its long-term goal is to provide a stable, hardware-aware, and user-friendly abstraction layer for:

- defining cQED experiments,
- constructing pulse sequences and higher-level protocols,
- compiling them into backend-specific programs,
- running them on supported hardware or simulator backends,
- collecting and organizing results,
- and analyzing those results in a reproducible and physically meaningful way.

The guiding philosophy of this repository is to keep the **user-facing experiment interface simple and expressive** while ensuring that **backend behavior remains physically faithful, operationally correct, and easy to inspect**.

---

## Startup Policy

Before making changes, an agent must first gather project context.

### Requirements
- Read `README.md` first.
- If the task is API-related, also inspect `API_REFERENCE.md`.
- If the task touches QUA compilation, experiment structure, or validation, also inspect:
  - `standard_experiments.md`
  - `limitations/qua_related_limitations.md` if it exists
- If the task affects notebooks, examples, or usage flows, inspect the relevant notebook(s) under the notebook folder before modifying code.
- Prefer understanding the existing repository structure before introducing new abstractions, files, or workflows.

### General Working Principle
- Prefer minimal, clear, and structurally consistent changes.
- Do not introduce large architectural rewrites unless the task explicitly calls for them.
- Preserve compatibility with the existing supported Quantum Machines stack unless the user explicitly requests a migration.

---

## Prompt Logging Policy

All prompt requests and prompt-generated results must be logged for traceability.

### Requirements
- Every prompt question/request and every corresponding prompt result/response must be saved under the `past_prompt/` folder.
- Each saved record must include an **explicit date and time** in its filename or metadata.
- Timestamps should be precise enough to distinguish multiple prompt runs on the same day.
- The saved record should make clear:
  - the original prompt/request,
  - the produced result/response,
  - and, when relevant, the task context or target files.
- Do not overwrite prior prompt logs unless the task explicitly calls for replacement; preserve history by default.

### Guidance
- Prefer stable, readable naming conventions such as:
  - `past_prompt/YYYY-MM-DD_HH-MM-SS_<short_task_name>.md`
  - or an equivalent structured format already used by the repository
- If a prompt is revised multiple times, each meaningful revision should be logged separately.
- Prompt logs should be organized so that past agent interactions can be audited later.

### Goal
This policy exists to ensure reproducibility, auditability, and historical traceability of agent-assisted development work.

---

## Python Version Policy

For stability and reproducibility, all development and execution environments should use **Python 3.12.13**.

### Requirements
- Before performing environment-dependent work, check whether **Python 3.12.x** is available on the system.
- When actually connecting to hardware, Python **3.11.8** may be used as a fallback, since hardware access is only available when the system name is `ECE-SHANKAR-07`.
- If Python 3.12.x is not available, create and use a **virtual environment** based on that version, if possible.
- Avoid using other Python versions unless:
  - the user explicitly requests it, or
  - there is a documented project-wide exception.

### Notes
- Environment changes should be kept minimal and justified.
- If a different Python version is required by a dependency or external tool, clearly document the reason.
- Do not silently change the Python version policy.

---

## Hardware and Backend Scope

The qubox API currently primarily supports **Quantum Machines** hardware and software.

### Supported Stack
- **Quantum Machines QUA / QM API version:** `1.2.6`
- **Primary hardware target:** **OPX+ + Octave**

All implementation, experiment generation, validation, and documentation work should remain consistent with this supported stack unless the user explicitly requests an upgrade or migration.

### Official References
- General Quantum Machines documentation:  
  `https://docs.quantum-machines.co/1.2.6/`
- QUA Simulator API:  
  `https://docs.quantum-machines.co/1.2.6/docs/API_references/simulator_api/`
- Octave API:  
  `https://docs.quantum-machines.co/1.2.6/docs/API_references/qm_octave/`
- OPX+ / QM API:  
  `https://docs.quantum-machines.co/1.2.6/docs/API_references/qm_api/`
- General tutorials:  
  `https://github.com/qua-platform/qua-libs/tree/main/Tutorials`

### Scope Expectations
- Do not assume compatibility with other QM versions unless verified.
- Do not assume compatibility with non-QM hardware unless the abstraction is explicitly backend-agnostic and the task requests such support.
- If adding abstractions intended for future backend portability, keep current QM backend behavior correct first.

---

## Core Repository Philosophy

Agents working in this repository should preserve the following high-level design goals:

- **high-level experiment simplicity**
- **backend-faithful compiled behavior**
- **clear and inspectable pulse-sequence logic**
- **reproducibility**
- **documentation consistency**
- **extensibility toward future cQED experiments**
- **practical usability for experimental physicists**

This repository is not just a code library; it is intended to support real experimental workflows. Readability, reproducibility, and physical correctness matter more than clever abstraction for its own sake.

---

## QUA Program Validation Policy

For any new experiment, audit, refactor, or feature that produces or modifies a **QUA program**, the resulting **compiled program** must be treated as the source of truth for execution behavior.

### Requirements
- Do **not** assume that written QUA code and actual compiled behavior are identical.
- Any experiment that compiles to QUA must be validated carefully to ensure that the generated program behaves as intended.
- When checking, auditing, or developing a QUA-based experiment, the program should be run through the **Quantum Machines supported simulator API** whenever feasible.
- Validation should focus on whether the compiled and simulated behavior matches the intended:
  - pulse sequence,
  - timing,
  - control flow,
  - measurements,
  - and overall experimental logic.

### Hosted Quantum Machines Server Preference
- If a hosted Quantum Machines server is available, prefer using the hosted server for simulator-based validation and, when explicitly appropriate for the task, real experiment execution.
- Use the following hosted server settings:
  - `host = "10.157.36.68"`
  - `cluster_name = "Cluster_2"`
- When simulator validation is possible on the hosted server, prefer that path over purely local assumptions.
- When real execution is requested or required for the audit, use the same hosted configuration unless the task explicitly specifies a different target.
- If the hosted server is unavailable, inaccessible, misconfigured, or inconsistent with the requested task, report that clearly and fall back to the best available validation path.
- Do not silently substitute a different host or cluster unless the user explicitly requests it or the repository already defines an approved override.

### Simulation and Compilation Guidance
- Be aware that some QUA programs may introduce **hardware-limited latency** or other backend-specific behavior not obvious from the written source.
- If such latency or backend behavior is observed and cannot be reasonably removed or corrected, it must be documented in:
  - `limitations/qua_related_limitations.md`
- Compilation and simulation cost must be taken into account during validation.
- As a general target, **QUA compilation time should remain below 1 minute**. If compilation exceeds 1 minute, report it clearly.
- For experiments that mainly sweep linear variables or repeat the same sequence many times through averaging, use reduced settings for validation whenever possible.
- In particular, for quick validation of repeated experiments:
  - set `n_avg = 1` unless averaging itself is the object of the test,
  - reduce unnecessarily long idle periods when they are not the feature being validated,
  - and simulate only the minimum duration needed to verify the sequence.

- Refer to `standard_experiments.md` for the set of standard reference protocols that should pass for intended operations whenever applicable.

### Long-Wait and Relaxation Experiments
- Some experiments include long delays, such as thermal relaxation waits, often on the order of **1000+ clock cycles** or longer.
- For validation through the simulator API, these waits may be shortened artificially when the purpose is only to verify program structure, ordering, and timing logic rather than the exact physical wait duration.
- A good rule of thumb is to estimate the total pulse-sequence duration from:
  - state preparation,
  - experiment body,
  - to measurement,
  and simulate only up to that timespan.

### Reporting Expectations
- If the compiled program does not perfectly match the intended high-level design, report the discrepancy clearly.
- If simulator behavior, backend constraints, or compilation artifacts prevent a perfect match, do **not** ignore it; document the issue explicitly.

### Goal
The purpose of this policy is to ensure that high-level experiment definitions in qubox remain faithful to the actual backend behavior seen by the Quantum Machines stack.

Perfect agreement may not always be achievable due to backend constraints, compilation artifacts, or hardware-related timing behavior. When this occurs, the mismatch must be clearly reported rather than silently accepted.

---

## Standard Experiment / Trust Protocol Policy

The file `standard_experiments.md` defines standard reference experiments that act as trust gates for agent-generated compilation logic.

### Requirements
- If a task introduces or modifies pulse-sequence generation, experiment compilation, scheduling logic, or QUA translation behavior, the agent should consider whether the relevant standard experiments still pass.
- These standard experiments are meant to be simple but structurally representative.
- Passing them does **not** prove total correctness, but failure to pass them should be treated as a warning sign that compilation behavior may not be trustworthy.
- If a standard experiment becomes invalid because of a legitimate architectural change, update `standard_experiments.md` accordingly and explain why.

---

## Tooling Policy

Agents may use utilities located in the `tools/` folder when they help complete the task more effectively.

### Requirements
- Reuse existing tools when appropriate.
- Modify existing tools if:
  - the current version is outdated,
  - it no longer applies to the present codebase,
  - or improving it would substantially simplify or strengthen the task.
- Prefer improving shared tooling over duplicating one-off logic when the tool is likely to be reused.

### Guidance
- Keep tools general-purpose when possible.
- Avoid creating narrow one-use utilities unless the task clearly justifies it.
- If a tool becomes part of the regular workflow, ensure its usage is discoverable and documented.

---

## API and Documentation Consistency

The file `API_REFERENCE.md` is the canonical reference for public API usage.

### Requirements
- Refer to `API_REFERENCE.md` when using or modifying the API.
- Any change to the public API must be reflected in `API_REFERENCE.md`.
- Any notable repository change should also update `docs/CHANGELOG.md`.
- Documentation changes should be made in the same task whenever practical, so code and docs remain synchronized.

### This Includes
- new public classes,
- new functions,
- renamed parameters,
- removed features,
- changed behavior,
- changed defaults,
- backend support changes,
- and workflow changes visible to users.

### Documentation Principle
If a user-visible behavior changes, the corresponding documentation should change in the same task unless there is a strong reason not to.

---

## Notebook and Example Policy

The notebook folder contains usage examples and workflow demonstrations.

### Requirements
- If a major change is made to the API, user workflow, experiment structure, or core abstractions, inspect the relevant notebook(s) and update them as needed.
- Notebooks should remain aligned with the current public usage model of the repository.
- If an old notebook no longer represents best practice, either:
  - update it,
  - clearly relabel it as legacy / archival,
  - or replace it with a better example.

### Notes
- Notebooks are part of the practical user interface of the repository.
- A code change that breaks notebooks without acknowledgment is considered incomplete work.
- Prefer notebooks that demonstrate intended usage clearly rather than exposing unnecessary internal complexity.

---

## Testing and Validation Expectations

Agents should prefer changes that are testable and inspectable.

### Requirements
- When modifying experiment logic, pulse compilation, or API behavior, check whether the change should be accompanied by:
  - a unit test,
  - a validation script,
  - a simulator check,
  - or an update to a standard experiment.
- If a change introduces a known limitation or unresolved discrepancy, document it explicitly rather than hiding it.
- Avoid making changes that cannot be explained, inspected, or reproduced.

### General Principle
A successful change is not just one that “runs,” but one that can be explained and validated.

---

## Backward Compatibility Guidance

When modifying existing interfaces, prefer preserving backward compatibility unless the task explicitly requires breaking changes.

### Requirements
- Do not rename or remove public APIs casually.
- If a breaking change is necessary:
  - document it in `API_REFERENCE.md`,
  - record it in `docs/CHANGELOG.md`,
  - and update affected notebooks/examples.
- If a legacy path is being deprecated, prefer a clear migration path where practical.

---

## Change Scope Guidance

Agents should prefer the smallest correct change that fully addresses the task.

### Requirements
- Do not perform unrelated cleanup unless it materially improves the requested work.
- Do not introduce large new abstractions unless they are justified by repeated structure or long-term maintainability.
- Do not rewrite working subsystems only for stylistic reasons.

### Preferred Behavior
- Understand existing conventions first.
- Extend existing patterns where reasonable.
- Refactor only when it clearly improves correctness, maintainability, or usability.

---

## File and Repository Hygiene

### Requirements
- Keep new files placed in logically appropriate directories.
- Avoid scattering experimental scripts, temporary utilities, or ad hoc notes in unrelated parts of the repository.
- If creating a new policy, limitation, or reference document, place it in a location consistent with the existing repository structure.

### Guidance
- Repository structure should remain understandable to a new contributor.
- File names should be descriptive and stable.

---

## Reporting and Transparency Expectations

When an agent finishes a substantial task, it should be able to explain:

- what was changed,
- why it was changed,
- what assumptions were made,
- what validation was performed,
- what remains uncertain,
- and what limitations were discovered.

### Requirements
- Do not silently ignore mismatches between intended behavior and compiled behavior.
- Do not silently leave broken notebooks, stale docs, or failed trust protocols if they were affected by the change.
- Be explicit about what was verified versus what was only assumed.

---

## Working Expectations for Agents

When making changes in this repository, agents should aim to preserve:

- API clarity,
- hardware realism,
- reproducibility,
- documentation accuracy,
- compatibility with the supported Quantum Machines stack,
- usability for experimental workflows,
- and long-term maintainability.

Agents should prefer changes that make the system:

- easier to maintain,
- easier to extend to new cQED experiments,
- easier to validate with simulator-backed checks,
- and less likely to drift from actual hardware behavior.

The best changes in this repository are those that improve both **user simplicity** and **backend correctness**.