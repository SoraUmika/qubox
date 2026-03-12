# Standard Experiments

## Purpose

This document defines a small set of **standard reference experiments / pulse-sequence protocols** that an agent should be able to implement, compile, simulate, and inspect before its QUA compilation workflow is considered trustworthy.

These are **not** meant to be full physics validations or calibration-quality benchmarks. Their purpose is to verify that the agent can correctly translate a high-level experimental design into a compiled QUA program whose behavior still matches intent.

In particular, these standard experiments are meant to test:

- pulse ordering,
- pulse timing,
- explicit waits,
- align behavior,
- frame / phase updates,
- multi-element coordination,
- measurement placement,
- loop structure,
- sweep structure,
- and simulator-visible compiled behavior.

Passing these experiments does **not** prove full correctness for all future experiments, but it establishes a minimum level of trust in the compilation process.

---

## General Validation Policy

For any standard experiment defined in this document:

- The **compiled QUA program** must be treated as the source of truth for execution behavior.
- The written pulse sequence alone is not sufficient evidence of correctness.
- The experiment should be run through the **Quantum Machines simulator API** whenever feasible.
- Validation should focus on whether the compiled and simulated behavior matches the intended:
  - pulse order,
  - timing,
  - control flow,
  - measurement position,
  - and overall experiment logic.

If the compiled behavior differs from the intended high-level design because of backend constraints, compiler behavior, or hardware-limited latency, the discrepancy must be explicitly reported.

If unresolved QUA-related limitations are found, document them in:

- `limitations/qua_related_limitations.md`

---

## Validation Cost Control

To keep trust checks fast and practical:

- use `n_avg = 1` unless averaging behavior itself is under test,
- use a very small sweep,
- shorten long waits when the exact wait duration is not the feature being tested,
- and simulate only up to the approximate full pulse-sequence duration.

For long thermal-relaxation or idle-wait experiments, the simulator check may use artificially shortened waits as long as the purpose is only to validate sequence structure, ordering, alignment, and control logic.

As a general target, compilation time should remain below **1 minute**. If compilation exceeds this, report it.

---

# Standard Compilation Trust Protocol

## Purpose

This is the primary standard experiment that an agent should pass before its QUA compilation process is trusted for broader experimental work.

This protocol is intentionally simple from a physics standpoint, but structurally rich enough to reveal many common scheduling and compilation mistakes.

---

## Protocol Name

**Standard Compilation Trust Protocol (SCTP)**

---

## High-Level Structure

The protocol should include:

1. alignment of relevant elements,
2. explicit idle wait,
3. qubit preparation pulse,
4. explicit inter-pulse delay,
5. a second control pulse,
6. optional frame / phase update,
7. a second qubit pulse,
8. final alignment,
9. measurement,
10. result save,
11. averaging loop support,
12. and a small 1D sweep.

This protocol is meant to exercise both single-sequence execution and looped / swept execution.

---

## Relevant Elements

When available, the protocol should involve the following elements:

- qubit drive element,
- resonator readout element,
- cavity / storage drive element.

If the repository currently does not support one of these robustly, the protocol may be adapted, but the intended multi-element nature should be preserved whenever possible.

---

## Canonical Reference Sequence

A recommended canonical sequence is:

1. `align(qubit, cavity, resonator)`
2. `wait(t_init)`
3. `play(qubit_x90)`
4. `wait(t_gap_1)`
5. `play(cavity_displacement)` or other distinct secondary control pulse
6. optionally apply `frame_rotation(phase_test)` or equivalent
7. `play(qubit_x90_probe)` or another distinct qubit pulse
8. `align(qubit, resonator)`
9. `measure(readout)`
10. `save(result)`

This logical order must remain preserved in the compiled program.

---

## Recommended Concrete Version

### Protocol: Qubit Pulse -> Delay -> Cavity Pulse -> Delay -> Qubit Pulse -> Readout

### Logical Flow

1. align qubit / cavity / resonator
2. wait `t_init`
3. play qubit `x90`
4. wait `t_delay`
5. play cavity displacement pulse
6. wait `t_gap_2`
7. optionally apply a frame update
8. play second qubit `x90`
9. align qubit and resonator
10. measure resonator readout
11. save IQ or equivalent measurement outputs

---

## Why This Is a Good Trust Test

This sequence checks:

- multi-element scheduling,
- explicit waits,
- repeated qubit operations,
- possible frame handling,
- alignment before measurement,
- measurement placement,
- sweep compatibility,
- averaging-loop compatibility,
- and simulator-visible timing correctness.

It is much more informative than a trivial single-pulse-plus-measurement test.

---

## Averaging Requirements

The protocol must support averaging through `n_avg`.

For validation and trust testing:

- use `n_avg = 1`

unless averaging behavior itself is the specific thing being audited.

This keeps simulation fast while still validating loop structure.

---

## Sweep Requirements

The protocol must support a small 1D sweep.

### Recommended sweep variables

Choose exactly one of the following:

- wait duration,
- qubit pulse amplitude,
- cavity displacement amplitude,
- frame phase,
- readout detuning.

### Best default choices

The most useful default sweep variables are usually:

- wait duration, or
- qubit pulse amplitude.

### Sweep size

Use only a very small sweep for trust validation, for example:

- 3 to 5 points.

### Purpose of the sweep

This checks whether:

- parameter updates are compiled correctly,
- loop nesting is correct,
- timing remains sensible across sweep points,
- and the experiment structure survives beyond a single fixed sequence.

---

## Acceptance Criteria

The Standard Compilation Trust Protocol is considered passed only if all of the following are satisfied.

### 1. Compilation succeeds

- The QUA program compiles without error.

### 2. Simulation succeeds

- The compiled program runs through the Quantum Machines simulator API.

### 3. Pulse ordering is preserved

- The simulated schedule shows the intended order of pulses and waits.
- No silent reordering should change the meaning of the sequence.

### 4. Explicit waits are preserved within backend constraints

- Waits should appear in the intended places.
- If the backend introduces unavoidable latency or timing shifts, this must be reported.

### 5. Measurement placement is correct

- Measurement must occur only after the intended control sequence.
- It must not overlap incorrectly with prior control pulses unless that is explicitly intended.

### 6. Total sequence duration is sensible

- The simulated runtime should be consistent with the intended sum of:
  - pulse durations,
  - waits,
  - alignments,
  - and measurement duration.

### 7. Sweep structure is correct

- The small 1D sweep compiles and simulates correctly.
- The number of sweep points matches expectation.

### 8. Averaging structure is correct

- The protocol supports averaging.
- The validation path works correctly with `n_avg = 1`.

### 9. Frame / phase behavior is either verified or explicitly marked unverified

- If frame operations are part of the abstraction, they should be exercised here.
- If not yet supported or not yet reliable, this limitation must be stated explicitly.

### 10. Any discrepancy is documented

- Any mismatch between intended high-level sequence and compiled behavior must be reported clearly.
- Unresolved issues must be documented in `limitations/qua_related_limitations.md`.

---

## What This Protocol Is Good At Catching

This protocol is particularly useful for detecting:

- missing `align()` calls,
- incorrect wait insertion,
- unexpected compiler-induced latency,
- wrong pulse order,
- broken frame update handling,
- measurement placed too early,
- broken sweep wiring,
- broken averaging-loop structure,
- and miscompiled multi-element timing.

---

## What This Protocol Does Not Prove

Passing this protocol does **not** prove:

- correct physics calibration,
- correct pulse amplitude calibration,
- correct DRAG tuning,
- correct readout discrimination,
- correct resonator calibration,
- correct hardware wiring,
- correct long-run experiment performance,
- or correctness of all advanced protocols.

It only proves that the agent can successfully implement and validate a basic but representative compiled pulse sequence.

---

# Additional Standard Experiments

The following additional experiments are recommended as secondary trust checks.

These are not necessarily required in the first pass, but they are valuable for building confidence in the compilation pipeline.

---

## Standard Experiment 2: Pure Qubit Delay Test

### Purpose

This tests whether a simple single-element qubit sequence with explicit waits is compiled correctly.

### Sequence

1. align qubit and resonator
2. play qubit `x90`
3. wait `t_delay`
4. play qubit `x90`
5. align qubit and resonator
6. measure readout

### What it tests

- simple pulse ordering,
- explicit wait preservation,
- repeated operation scheduling on one element,
- and measurement placement after control.

### Notes

This is simpler than the main SCTP and is useful as a quick sanity check.

---

## Standard Experiment 3: Multi-Element Align Test

### Purpose

This tests whether alignment across multiple elements behaves as intended.

### Sequence

1. play qubit pulse
2. play cavity pulse
3. align qubit, cavity, and resonator
4. measure readout

### What it tests

- multi-element timeline coordination,
- whether control branches rejoin properly,
- and whether measurement starts only after intended alignment.

---

## Standard Experiment 4: Frame Update Test

### Purpose

This checks whether explicit frame or phase updates survive compilation correctly.

### Sequence

1. play qubit `x90`
2. apply frame rotation / phase shift
3. play second qubit pulse
4. measure readout

### What it tests

- whether frame updates are preserved,
- whether subsequent pulses inherit the intended phase behavior,
- and whether the abstraction matches compiled behavior.

### Notes

If frame support is not yet mature in the repository, this experiment should still exist as a declared validation target, even if marked partially supported.

---

## Standard Experiment 5: Small Sweep Test

### Purpose

This checks whether simple parameter sweeps compile and execute correctly.

### Sequence

Use a simple pulse sequence, for example:

1. play qubit pulse
2. wait or vary pulse amplitude
3. measure readout

Run this over a very small 1D sweep.

### What it tests

- loop nesting,
- parameter updates,
- sweep indexing,
- and whether per-point timing remains sensible.

---

# Recommended Minimum Passing Set

Before trusting an agent’s QUA compilation workflow, the following minimum set should pass:

1. **Standard Compilation Trust Protocol (SCTP)**
2. **Pure Qubit Delay Test**
3. **Small Sweep Test**

If multi-element support is central to the task, also require:

4. **Multi-Element Align Test**

If frame handling is used in the abstraction, also require:

5. **Frame Update Test**

---

# Reporting Expectations

For each standard experiment that is implemented and checked, the agent should report:

- whether compilation succeeded,
- whether simulation succeeded,
- approximate total simulated sequence duration,
- whether pulse ordering matched intent,
- whether waits appeared correctly,
- whether measurement occurred at the intended point,
- whether sweep behavior was correct,
- and whether any backend-induced discrepancy was observed.

Any unresolved limitation should be documented explicitly rather than silently ignored.

---

# Recommended Practical Default

If only one standard experiment is used as the primary trust gate, the recommended default is:

**`x90 -> wait -> cavity displacement -> wait -> x90 -> measure`**

This is the best default because it is:

- simple,
- easy to inspect,
- multi-element,
- timing-sensitive,
- and representative of real cQED control structure.

---