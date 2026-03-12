# qubox_v2 — Architectural and API Audit Report

**Prepared by**: Claude Sonnet 4.6
**Date**: 2026-03-12
**Repository**: `e:/repo/qubox`
**Version audited**: qubox_v2 v2.1.0
**Scope**: Read-only architectural and API review

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [High-Level Architectural Assessment](#2-high-level-architectural-assessment)
3. [Public API Consistency Review](#3-public-api-consistency-review)
4. [Experiment / Pulse / Compilation Design Review](#4-experiment--pulse--compilation-design-review)
5. [Calibration / Configuration Review](#5-calibration--configuration-review)
6. [Documentation / Notebook Drift Review](#6-documentation--notebook-drift-review)
7. [Validation / Testing Risk Review](#7-validation--testing-risk-review)
8. [Ranked Problems](#8-ranked-problems)
9. [Strategic Recommendations](#9-strategic-recommendations)
10. [Suggested Next Refactor Targets](#10-suggested-next-refactor-targets)
11. [Final Verdict](#11-final-verdict)

---

## 1. Executive Summary

`qubox_v2` is an ambitious and largely well-designed cQED experiment orchestration framework targeting Quantum Machines OPX+ hardware. The architecture shows clear evidence of iterative improvement: a layered module structure, explicit ownership boundaries, a good separation between experiment lifecycle stages, and solid calibration persistence infrastructure.

The v2.1.0 refactoring addressed several serious safety gaps — silent fit failures, non-transactional calibration commits, heuristic unit conversions — and these improvements are genuine strengths. The Gate → Protocol → Circuit → Backend layer added in the most recent cycle is a notable step forward.

However, the codebase carries significant accumulated technical debt in specific areas:

- **A globally mutable singleton (`measureMacro`) sits at the center of every experiment's measurement path.** This is the single most dangerous design pattern in the codebase.
- **Two separate stores (`cQED_attributes` and `CalibrationStore`) hold overlapping data**, and their reconciliation is complex, implicit, and fragile.
- **No experimental validation of the Standard Compilation Trust Protocol (SCTP)** exists in the test suite, despite the `standard_experiments.md` policy requiring it.
- **Wildcard QUA imports (`from qm.qua import *`)** in all 14 builder files make the codebase opaque to static analysis and IDE tools.
- **Small but systematic code duplication** (helper functions copied across experiment files) signals missing base-class consolidation.

The core experiment loop — `SessionManager → ExperimentBase._build_impl() → ProgramBuildResult → run_program()` — is clean and should be preserved. The principal design investment needed is in disciplining the calibration/parameter resolution path and eliminating the global singleton.

**Overall health**: **Moderate.** The architecture is sound and improving, but several latent risks could cause correctness bugs in real lab workflows.

---

## 2. High-Level Architectural Assessment

### 2.1 Actual Module Structure

The repository's main package is `qubox_v2/` and contains:

```
core/           — config models, bindings, experiment identity, persistence policy, errors
hardware/       — ConfigEngine, HardwareController, ProgramRunner, QueueManager
devices/        — DeviceManager, SampleRegistry, ContextResolver
pulses/         — PulseOperationManager, PulseFactory, PulseRegistry
programs/       — QUA program builders, macros (measureMacro, sequenceMacros), circuit IR
  builders/     — 8 builder modules (stateless factory functions)
  macros/       — measureMacro (singleton), sequenceMacros (singleton)
experiments/    — ExperimentRunner, ExperimentBase, SessionManager, result types
  calibration/  — IQBlob, AllXY, DRAGCalibration, RB, readout calibration experiments
  cavity/       — Fock-resolved, storage spectroscopy experiments
  time_domain/  — Rabi, T1, T2, Chevron experiments
  spectroscopy/ — ResonatorSpectroscopy, QubitSpectroscopy experiments
  tomography/   — State, Fock, Wigner tomography experiments
  spa/          — SPA flux experiments
analysis/       — Output, fitting, models, post-processing, IQ tools, cQED_attributes
calibration/    — CalibrationStore (JSON), CalibrationOrchestrator, patch rules
gates/          — Gate algebra: pure math models + OPX hardware implementations
compile/        — Gate sequence optimization (ansatz, GPU, structure search)
simulation/     — QuTiP-based cQED simulation
```

### 2.2 Layer Architecture

The intended 9-layer dependency model (from `API_REFERENCE.md`) is broadly followed, with a few exceptions noted in §3. The core lifecycle flow is:

```
Notebook
  → SessionManager.open()          [infrastructure wiring]
  → ExperimentBase._build_impl()   [pure program construction]
  → ProgramRunner.run_program()    [QUA execution]
  → analyze() / plot()             [offline analysis]
  → CalibrationOrchestrator        [guarded parameter persistence]
```

This flow is clean and physically meaningful.

### 2.3 Genuine Architectural Strengths

1. **`ProgramBuildResult` as a frozen provenance snapshot.** Every program build records its resolved parameters, frequencies, sweep axes, and bindings in an immutable dataclass. This is excellent for reproducibility and debugging.

2. **`CalibrationStore` with atomic writes and schema versioning.** Atomic temp-file + `os.replace` writes, Pydantic v2 validation, version detection, and `create_in_memory_snapshot()` / `restore_in_memory_snapshot()` for rollback are all genuinely good engineering.

3. **Transactional `apply_patch()` with rollback (v2.1).** The `dry_run=True` default and the pre/post snapshot pattern mean calibration patches are safe by default.

4. **`ExperimentBase._build_impl()` / `build_program()` / `run()` separation.** Experiments declare their logic in `_build_impl()` (pure, no hardware side effects), frequencies are applied by the base class, and `run()` delegates. This is a clean and physically appropriate contract.

5. **Gate → Protocol → Circuit → Backend architecture (v2.4).** `RamseyProtocol`, `EchoProtocol`, and `CircuitRunnerV2` with golden-file tests represent a well-designed intent layer. The `ParameterSource` precedence chain is explicit. The IQ-only measurement contract is enforced.

6. **Context-mode session scoping.** The `sample_id` + `cooldown_id` + wiring hash identity model prevents accidentally loading calibrations from a different cooldown or sample.

7. **`FitResult.success` contract (v2.1).** Downstream calibration code now checks `success` before consuming `params`. Silent fit failures no longer silently corrupt calibration data.

---

## 3. Public API Consistency Review

### 3.1 Entry-Point Duplication: Two Base Classes

There are two experiment infrastructure classes:

- `ExperimentRunner` ([experiments/base.py](qubox_v2/experiments/base.py)) — "lightweight," wraps QM connection, POM, DeviceManager.
- `ExperimentBase` ([experiments/experiment_base.py](qubox_v2/experiments/experiment_base.py)) — "modular experiment types," takes a context object (`cQED_Experiment` or `ExperimentRunner`).

`ExperimentBase` accesses its context through attribute fallback chains:

```python
# From experiment_base.py:197-203
pm = getattr(self._ctx, "pulseOpMngr",
             getattr(self._ctx, "pulse_mgr", None))
```

```python
# From experiment_base.py:207-215
h = getattr(self._ctx, "quaProgMngr",
            getattr(self._ctx, "hw", None))
```

The dual naming (`.pulseOpMngr` vs `.pulse_mgr`, `.quaProgMngr` vs `.hw`) betrays a legacy compatibility shim for a `cQED_Experiment` object that no longer exists in the codebase (the `__init__.py` states "Legacy monolithic experiment interfaces have been removed"). These fallback chains are now dead code paths that add noise and confusion.

**Verdict**: Definite inconsistency. The `getattr` fallbacks for legacy attribute names should be cleaned up since the legacy context is gone.

### 3.2 `experiments/configs.py` Exists but Is Not Used

`experiments/configs.py` defines frozen parameter dataclasses (`PowerRabiConfig`, `TemporalRabiConfig`, etc.) with the docstring:

```python
# From configs.py:
result = rabi.run(cfg, drive=qb, readout=ro)
```

But `PowerRabi.run()` has the signature:

```python
def run(self, max_gain: float, dg: float = 1e-3, op: str = "ge_ref_r180", ...) -> RunResult:
```

It does not accept a `Config` object. **The `configs.py` module is completely decoupled from the experiment implementations it documents.** No experiment class actually uses these config dataclasses. This is wasted infrastructure that creates a false expectation of a cleaner API.

**Verdict**: Definite inconsistency. Either wire up the configs or remove them.

### 3.3 Naming Collision: `CalibrateReadoutFull` vs `CalibrationReadoutFull`

Both are exported from `experiments/__init__.py`. Two nearly identical names for what appear to be different classes in `experiments/calibration/readout.py`. Any physicist typing at a Jupyter prompt will be confused.

**Verdict**: Definite inconsistency. One should be deprecated or renamed.

### 3.4 `_resolve_qb_therm_clks` Copied Across 5 Files

The helper function:

```python
def _resolve_qb_therm_clks(exp: ExperimentBase, value: int | None, owner: str) -> int:
    return int(exp.resolve_override_or_attr(
        value=value, attr_name="qb_therm_clks", owner=owner, cast=int,
    ))
```

is defined identically in:
- `experiments/time_domain/rabi.py`
- `experiments/time_domain/coherence.py`
- `experiments/time_domain/relaxation.py`
- `experiments/spectroscopy/qubit.py`
- `experiments/spectroscopy/resonator.py`

This is unnecessary duplication. It belongs in `ExperimentBase` as a `get_therm_clks("qb")` call (which itself already exists and delegates to `resolve_param`). The `get_therm_clks()` method exists at `experiment_base.py:523-551` but is not being used by these files.

**Verdict**: Probable design weakness. Easy to fix.

### 3.5 `PowerRabi` Silent Fallback from `CircuitRunner` to Legacy Builder

```python
# From rabi.py:260-288:
if use_circuit_runner:
    try:
        circuit, sweep = make_power_rabi_circuit(...)
        compiled = CircuitRunner(self._ctx).compile(circuit, sweep=sweep)
        prog = compiled.program
        builder_function = "CircuitRunner.power_rabi"
    except Exception:
        prog = cQED_programs.power_rabi(...)
```

If `CircuitRunner` fails for any reason — import error, compile error, incorrect calibration — the experiment silently falls back to the legacy builder **without notifying the user**. The user sees the same `ProgramBuildResult` but `builder_function` changes, which is only visible in logs. This pattern hides failures and makes it impossible to confidently test the CircuitRunner path.

**Verdict**: Definite inconsistency. A silent broad `except Exception` is always a red flag in experiment execution code.

### 3.6 `save_output()` Has Two Different Implementations

- `ExperimentRunner.save_output()` ([experiments/base.py:188-228](qubox_v2/experiments/base.py)) — saves `.npz` + `.meta.json` with context snapshot.
- `ExperimentBase.save_output()` ([experiments/experiment_base.py:634-654](qubox_v2/experiments/experiment_base.py)) — tries `orchestrator.persist_artifact()`, then falls back to `self._ctx.save_output()`.

These two save paths have different behaviors: different file formats, different metadata structures, and different failure modes. A user calling `experiment.save_output()` gets a different result depending on which base class path is active.

**Verdict**: Probable design weakness.

### 3.7 `simulate()` on `ExperimentBase` Lacks Parity with `run()` in Subclasses

`ExperimentBase.simulate()` is properly implemented in the base class and calls `build_program()` then `runner.simulate()`. However, most experiment classes override `run()` and add domain-specific logic (e.g., `self.save_output()`, `self._run_params = {...}`), but do not override `simulate()`. The `simulate()` path therefore skips save, provenance tracking, and parameter annotation that `run()` provides. This is semantically correct but inconsistently documented.

---

## 4. Experiment / Pulse / Compilation Design Review

### 4.1 The `measureMacro` Global Singleton Problem

The `measureMacro` class in `programs/macros/measure.py` uses class-level state:

```python
class measureMacro:
    _pulse_op: PulseOp | None = None
    _active_op: str | None = None
    _demod_fn = dual_demod.full
    _demod_args = ()
    _ro_disc_params = { "threshold": None, "angle": None, ... }
    _state_stack: list[tuple[str, dict]] = []
    _drive_frequency = None
    ...
```

This is a Python class used as a namespace, not a class intended to be instantiated. All state is shared globally at the process level. This means:

1. If two experiments are constructed or run in sequence (or, theoretically, concurrently), they share all measurement configuration — threshold, angle, weights, demodulation function.
2. There is no per-session or per-experiment isolation of measurement configuration.
3. The v2.1 `MeasurementConfig` frozen dataclass was introduced as a safer alternative, but the singleton is still used in 10 files including `experiment_base.py`, `orchestrator.py`, and multiple builders.
4. `ExperimentBase.get_confusion_matrix()` has the macro singleton as its third-priority fallback, meaning calibration data can bleed from one experiment run to the next.

The `sequenceMacros` object in `programs/macros/sequence.py` follows the same class-as-namespace singleton pattern.

**This is the highest-priority design problem in the codebase.** A measurement threshold configured for a T1 experiment remains in the singleton when a T2 experiment starts unless explicitly re-configured. In a real lab session with multiple experiments, this is a correctness hazard.

**Verdict**: Definite design weakness. High risk.

### 4.2 `from qm.qua import *` Wildcard Imports in 14 Files

All 8 program builder modules, both macro modules, `config_builder.py`, and the canonical notebook all use:

```python
from qm.qua import *
```

This pattern:
- Imports hundreds of QUA symbols into the module namespace
- Makes it impossible for any IDE, linter, or static checker to verify which QUA functions are being called
- Prevents `__all__` enforcement
- Makes it hard to audit which QUA primitives (`play`, `wait`, `align`, `measure`, `update_frequency`, `frame_rotation_2pi`) are actually being used by each builder
- Blocks any future effort to mock or stub QUA primitives for offline testing

The builder modules do not need QUA's entire namespace. The used primitives are a small, known set.

**Verdict**: Definite design weakness. Low severity for correctness, high severity for maintainability.

### 4.3 `programs/builders/` vs `programs/circuit_compiler.py` — Two Compilation Paths

There are currently two ways to generate a QUA program:
1. **Direct builder functions** — `cQED_programs.temporal_rabi(pulse, pulse_clks, ...)` — stateless functions that call QUA primitives directly.
2. **Circuit compiler path** — `CircuitRunnerV2(session).compile(circuit)` — lowers `Gate` IR to QUA via `circuit_compiler.py`.

Path 1 is used by all 26 experiment classes (after their recent migration to `_build_impl()`). Path 2 is only used by `PowerRabi` (optionally, with silent fallback) and in the protocol examples. The circuit compiler path is more principled — it has parameter provenance tracking, golden-file tests, and a clean IR — but it covers only a small fraction of experiments.

The survey note in `docs/SURVEY.md` explicitly identified this as a gap: "There is no intermediate protocol layer between physics intent and QUA emission." The `circuit_protocols.py` layer (`RamseyProtocol`, `EchoProtocol`) exists but is not connected to `T2Ramsey` or `T2Echo` experiment classes, which still use the direct builder path.

**Verdict**: Speculative future risk now, but will become a definite inconsistency if the circuit path is intended to be the canonical path going forward.

### 4.4 Measurement Loop Order Inconsistency

Looking at `temporal_rabi` in `programs/builders/time_domain.py`:

```python
with for_(n, 0, n < n_avg, n + 1):       # averaging outer loop
    with for_(*from_array(pulse_clk, pulse_clks)):  # sweep inner loop
        play(...)
        align(...)
        emit_measurement_spec(...)
        wait(int(qb_therm_clks))
        save(I, I_st); save(Q, Q_st)
    save(n, n_st)
```

The thermalization wait is **inside the sweep loop**, meaning the qubit thermalizes between every sweep point. This is correct physics (qubit needs to cool between shots), but the placement means the *thermalization* happens between sweep points, not between averaging repetitions. For sweep experiments where the sweep variable is a wait time, this nesting is intentional. For sweep experiments where it's a frequency or amplitude, the positioning still achieves the right physics but may not match naive expectations about nesting.

More importantly: **there is no documentation in the builders about which loop is inner vs outer and why.** A physicist implementing a new experiment could easily reverse the nesting and get incorrect averaging behavior.

**Verdict**: Probable design weakness. Documentation gap.

### 4.5 `cQED_attributes` — A Remnant of the Legacy Architecture

`analysis/cQED_attributes.py` is a flat Python `@dataclass` holding:
- Element names (`ro_el`, `qb_el`, `st_el`)
- Frequencies (`ro_fq`, `qb_fq`, `st_fq`)
- Coupling parameters (`ro_chi`, `anharmonicity`, `st_chi`, etc.)
- Coherence times (`qb_T1_relax`, `qb_T2_ramsey`, etc.)
- Pulse amplitude fields (`ge_r180_amp`, `ge_rlen`, etc.)

This is called a "context snapshot" but is effectively a second calibration store. `CalibrationStore` has typed models for all of the same data. The `verify_consistency(store)` method added in v2.1 acknowledges the dual-truth problem but does not solve it.

Experiments access physics parameters via `self.attr` (which comes from `cqed_params.json`, a JSON representation of `cQED_attributes`) AND via `self.calibration_store` (which comes from `calibration.json`). The resolution order in `get_readout_frequency()` is:
1. `CalibrationStore.get_frequencies(ro_el).resonator_freq`
2. `CalibrationStore.get_frequencies(ro_el).if_freq + lo_freq`
3. Raises `ValueError`

The attributes object (`self.attr`) is not consulted for frequency in this path — the transition to `CalibrationStore` primacy is partially complete. However, `self.attr.ro_el`, `self.attr.qb_el`, and `self.attr.st_el` (element names) are still the canonical source for element names throughout the codebase. This mixture means neither `cqed_params.json` nor `calibration.json` is fully authoritative.

**Verdict**: Definite design weakness. This is the root of the dual-truth problem documented in `docs/architecture_review.md`.

---

## 5. Calibration / Configuration Review

### 5.1 `CalibrationStore` Data Model Consolidation (In Progress)

In v2.1, `set_frequencies()` now delegates to `set_cqed_params()`, and `get_frequencies()` checks `cqed_params` first. This is the right direction — consolidating all calibration data into the `cqed_params` sub-schema. However:

- The old `frequencies` dict still exists in `CalibrationData` (for backward compat via `_dual_lookup`).
- The old `coherence` dict still exists alongside the `cqed_params` field.
- `_infer_cqed_alias()` uses string-matching heuristics (`"resonator"`, `"readout"`, `"rr"` → alias `"resonator"`) which will fail silently for non-standard element naming conventions.

The migration is in progress but not complete. Users who write to `CalibrationStore.set_frequencies("resonator_element_001", ...)` will get different behavior depending on whether the key matches the heuristic.

**Verdict**: Definite inconsistency. The alias inference heuristic is fragile.

### 5.2 `CalibrationStore` Supported Versions: v5.0.0 and v5.1.0 Only

```python
_SUPPORTED_CALIBRATION_VERSIONS = {"5.0.0", "5.1.0"}
```

Versions below 5.0.0 are not supported and will raise `ValueError`. Users who have calibration files from earlier versions (v3.x, v4.x) must migrate. The migration path is documented in `API_REFERENCE.md` but not in a migration script. `_migrate_legacy_to_cqed_params()` handles only `5.0.0 → 5.1.0` upgrades, not older versions.

**Verdict**: Known limitation, well-documented.

### 5.3 Calibration Patch Rules Use `session.calibration` Directly

`PiAmpRule.__call__()` in `calibration/patch_rules.py` accesses `self.session.calibration.get_pulse_calibration(target_op)`. This means patch rules have a direct dependency on the live `CalibrationStore` via the session, not a pure function of the `CalibrationResult` they receive. This makes patch rules harder to test (they need a real or mocked session) and creates an implicit ordering dependency.

**Verdict**: Probable design weakness.

### 5.4 `autotune` Module Bypasses the Standard Calibration Pipeline

`autotune/run_post_cavity_autotune_v1_1.py` directly mutates both `cQED_attributes` and `CalibrationStore` — a dual-write path noted in the architecture review. The autotune module can bypass the human-approval model required by the orchestrator's `dry_run=True` default.

**Verdict**: Probable design weakness. High risk for autonomous lab workflows.

### 5.5 Calibration Confidence Score and Timestamp Not Tracked Per Parameter

`FitRecord` tracks a fit history per experiment, but individual calibrated parameters (e.g., `qubit_freq`, `pi_length`) don't carry a timestamp, r-squared, or confidence score. This means you cannot answer "when was this parameter last calibrated and how good was the fit?" from the calibration JSON alone.

**Verdict**: Missing feature. Long-term maintainability risk.

---

## 6. Documentation / Notebook Drift Review

### 6.1 `API_REFERENCE.md` is Authoritative but Extremely Large

`API_REFERENCE.md` is over 70,000 tokens — approximately 200-300 printed pages. It covers 28 sections and 3 appendices. While thorough, this density creates its own maintenance risk: updating code without updating the corresponding section becomes easier to miss. The document self-declares as "Governing Document" and has a CHANGELOG section at the top, which is good.

The document is current through v2.1.0 and appears to accurately reflect the `SessionManager`, `ExperimentBase`, `ProgramBuildResult`, and `CalibrationOrchestrator` APIs as implemented. The binding-driven API (§24) and roleless primitives (§25) reflect the current `core/bindings.py` module.

**One notable gap**: Section 28 ("Gate → Protocol → Circuit Architecture") was added in v2.4 per the changelog but the implementation (`RamseyProtocol`, `EchoProtocol`) is in `programs/circuit_protocols.py`. The experiments `T2Ramsey` and `T2Echo` in `experiments/time_domain/coherence.py` do **not** use `RamseyProtocol` — they still call `cQED_programs.T2_ramsey()`. This is a gap between what the docs describe as the canonical path and what experiment classes actually do.

### 6.2 `experiments/configs.py` Docstring Documents Non-Existent API

As noted in §3.2, `experiments/configs.py` contains:

```python
# Usage:
cfg = PowerRabiConfig(max_gain=0.4, n_avg=2000)
result = rabi.run(cfg, drive=qb, readout=ro)
```

`PowerRabi.run()` does not accept a `Config` object and does not have `drive` or `readout` parameters. The docstring documents a proposed future API that was never implemented. This is a direct documentation–implementation mismatch that will confuse any physicist reading the source.

**Verdict**: Definite documentation mismatch.

### 6.3 Builder Docstrings Reference Old Parameter Names

In `programs/builders/time_domain.py`, the `temporal_rabi` function docstring lists:

```
ro_el             : Readout resonator element
qb_el             : Qubit element
qb_gain           : Gain for the qubit drive pulse
```

But the function signature is `temporal_rabi(pulse, pulse_clks, pulse_gain, qb_therm_clks, n_avg, *, qb_el=None, bindings=None)` — no `ro_el` parameter (it's resolved from `bindings` or `measureMacro`), and `pulse_gain` vs `qb_gain`. The docstring was not updated when the function signature changed.

This pattern is common in the builder files, which inherited docstrings from before the binding-driven refactor.

**Verdict**: Definite documentation drift.

### 6.4 Notebook Status Unknown from Static Reading

Two notebooks exist: `notebooks/post_cavity_experiment_context.ipynb` and `notebooks/post_cavity_experiment_quantum_circuit.ipynb`. The context notebook is referenced in `API_REFERENCE.md` §1-§9 as the canonical usage example. Given that v2.0 introduced `ChannelRef` / `OutputBinding` / `ExperimentBindings` and v2.1 introduced `MeasurementConfig` and `MultiProgramExperiment`, any notebook written before these versions may contain outdated patterns.

Without executing the notebooks, it is impossible to confirm they run correctly against v2.1. The AGENTS.md policy states notebooks should be updated when major API changes are made, but no notebook update is listed in the CHANGELOG.

**Verdict**: Unknown — probable notebook drift. Verification required.

### 6.5 `ARCHITECTURE.md` in `qubox_v2/docs/` Not Listed in AGENTS.md Requirements

`qubox_v2/docs/ARCHITECTURE.md` exists alongside `API_REFERENCE.md` but is not mentioned in `AGENTS.md`'s startup policy. This suggests it may drift independently.

---

## 7. Validation / Testing Risk Review

### 7.1 Standard Experiments Not Implemented in Test Suite

`standard_experiments.md` defines the **Standard Compilation Trust Protocol (SCTP)** as a mandatory gate check:

> "Before trusting an agent's QUA compilation workflow, the following minimum set should pass: (1) SCTP, (2) Pure Qubit Delay Test, (3) Small Sweep Test."

There is **no test file anywhere in the repository that implements or runs any of these standard experiments.** The test files that exist are:

- `qubox_v2/tests/test_calibration_cqed_params.py` — unit tests for CalibrationStore
- `qubox_v2/tests/test_calibration_fixes.py` — unit tests for calibration logic
- `qubox_v2/tests/test_parameter_resolution_policy.py` — unit tests for parameter resolution
- `qubox_v2/tests/test_workflow_safety_refactor.py` — 32 tests for v2.1 safety features
- `tests/gate_architecture/test_gate_architecture.py` — 17 tests for the circuit compiler

None of these run a QUA program through the QM simulator. The SCTP policy is aspirational documentation without corresponding executable validation.

**Verdict**: Critical gap. The framework's stated trust validation policy is entirely unenforced.

### 7.2 No Tests for Experiment Classes

There are ~26 experiment classes (`TemporalRabi`, `PowerRabi`, `T1Relaxation`, `T2Ramsey`, `QubitSpectroscopy`, `StorageSpectroscopy`, etc.) and zero unit or integration tests for any of them. `_build_impl()` logic — including parameter resolution, program construction, and processor wiring — is completely untested. Any refactor of the base class or builder functions could silently break experiment behavior.

**Verdict**: Critical gap.

### 7.3 No Tests for Program Builders

The 8 builder modules in `programs/builders/` produce QUA programs. None of their outputs are tested. There are no assertions about pulse ordering, wait positions, alignment calls, or measurement placement.

**Verdict**: Critical gap. The "builders are stateless factory functions" design principle makes them easily testable, yet they have zero tests.

### 7.4 Gate Architecture Tests Are Strong

In contrast to the above gaps, `tests/gate_architecture/test_gate_architecture.py` has 17 tests with golden files, a full fake-session fixture (offline, no real QM dependency), and covers the circuit compiler, display, measurement schema validation, and cluster safety. This is a genuine strength and demonstrates what good test infrastructure looks like for this codebase.

**Verdict**: Strength. Should serve as the template for other test areas.

### 7.5 Testing Isolated from Hardware by Design — But Simulation Gap Remains

The gate architecture tests use a `FakePulseManager` and stub QM objects. This is the right approach for CI testing. However, the `AGENTS.md` policy requires QM simulator validation for compilation correctness. There is no automated path to run simulator-backed tests, even when a QM server is available. This must be manual today.

**Verdict**: Known gap. Important for long-term trust in the compilation pipeline.

---

## 8. Ranked Problems

### Problem 1 — `measureMacro` Global Singleton (CRITICAL)

**What**: `measureMacro` is a class that acts as a global namespace for all measurement state: demodulation function, integration weights, discrimination threshold, rotation angle, drive frequency, IQ normalization parameters, state stack. All state is class-level (not instance-level), making it a process-wide global.

**Why it matters**: In any lab session running multiple experiments sequentially, the measurement configuration from one experiment persists into the next unless explicitly re-set. This is an invisible, silent correctness hazard. In the worst case, a `T1Relaxation` run with a misconfigured threshold contaminates subsequent `T2Ramsey` data.

**Risk**: Incorrect experiment results that are difficult to reproduce or trace. The `_state_stack` in the singleton provides some isolation, but only if callers consistently push/pop, which is not enforced.

**Fix needed**: Replace the global singleton with a per-session `MeasurementConfig` instance (the frozen dataclass added in v2.1 is the right direction). Propagate it as a parameter through the experiment chain. Deprecate the singleton class.

---

### Problem 2 — No Test Coverage for Experiment Classes or Builders (CRITICAL)

**What**: Zero tests for 26 experiment classes and 8 builder modules.

**Why it matters**: Any refactoring of `ExperimentBase`, `ProgramBuildResult`, or a builder function could silently break experiment behavior with no safety net. The codebase has been actively refactored (v2.0, v2.1) and will continue to be. Without tests, each refactor is done blind.

**Risk**: Regressions in pulse ordering, parameter resolution, processor wiring, or output format that are only detected when running on real hardware — potentially after days of failed lab sessions.

**Fix needed**: Offline unit tests for `_build_impl()` methods using the `FakePulseManager` / stub pattern already demonstrated in `tests/gate_architecture/conftest.py`. At minimum: parameter resolution tests and program structure tests.

---

### Problem 3 — SCTP and Standard Experiments Not Validated (HIGH)

**What**: `standard_experiments.md` mandates simulator-backed validation of pulse ordering, timing, alignment, and measurement placement. No such validation exists.

**Why it matters**: The `AGENTS.md` policy explicitly states: "Any experiment that compiles to QUA must be validated carefully." This policy is declared but not enforced by any tooling.

**Risk**: A compilation bug (wrong loop nesting, missing `align()`, incorrect measurement placement) could go undetected until real hardware experiments produce wrong data.

**Fix needed**: A validation script that constructs the SCTP sequence using the qubox API, compiles it, and runs it through the QM simulator. Even with `n_avg=1` and 3-point sweep, this would provide a meaningful trust gate.

---

### Problem 4 — Dual Calibration Truth (`cQED_attributes` + `CalibrationStore`) (HIGH)

**What**: Physical parameters (frequencies, coherence times, element names) exist in two stores with complex resolution order. `verify_consistency()` detects drift but cannot resolve it.

**Why it matters**: Users and experiments must know which store is authoritative for which parameter. Currently, element names come from `cqed_params.json` (`cQED_attributes`), frequencies come from `calibration.json` (`CalibrationStore`), and the resolution chain is documented only in code comments.

**Risk**: A parameter updated in `CalibrationStore` silently fails to propagate to `cQED_attributes` (or vice versa), causing experiments to run with stale values.

**Fix needed**: Designate `CalibrationStore` as the sole source of truth for all parameters. Remove `cQED_attributes` for calibration data (keep only for element name mapping). Or vice versa — but pick one.

---

### Problem 5 — `from qm.qua import *` Wildcard Imports (MODERATE)

**What**: All 8 builder modules use `from qm.qua import *`.

**Why it matters**: Namespace pollution blocks static analysis, IDE completion, and automated testing. It also means any function name collision between QUA and Python builtins goes undetected.

**Risk**: Low for correctness today, but significantly impedes future testability and refactoring safety.

**Fix needed**: Replace with explicit imports. The used QUA primitives are a small, known set: `program`, `declare`, `declare_stream`, `play`, `wait`, `align`, `measure`, `save`, `update_frequency`, `frame_rotation_2pi`, `for_`, `stream_processing`, etc.

---

### Problem 6 — `experiments/configs.py` Documents Unimplemented API (MODERATE)

**What**: Config dataclasses exist but no experiment uses them.

**Why it matters**: A physicist reading `configs.py` will try to call `rabi.run(cfg, ...)` and get a `TypeError`. The documentation actively misleads users.

**Risk**: User confusion and wasted debugging time.

**Fix needed**: Either wire up configs to `run()` or delete `configs.py`.

---

### Problem 7 — Silent Exception Swallow in `PowerRabi._build_impl()` (MODERATE)

**What**: `use_circuit_runner=True` path does `except Exception: prog = cQED_programs.power_rabi(...)`.

**Why it matters**: If `CircuitRunner` fails due to a genuine bug, the experiment silently produces a result through the legacy path. The user has no way to know which compilation path was taken or that an error occurred.

**Risk**: Silent regression if `CircuitRunner` is supposed to be the canonical path.

**Fix needed**: Log the exception explicitly. Consider removing the silent fallback and letting the error propagate, or making `use_circuit_runner=False` the default with an explicit opt-in.

---

### Problem 8 — `_resolve_qb_therm_clks` Duplicated in 5 Files (LOW)

**What**: Identical helper function in 5 experiment files.

**Why it matters**: If the resolution logic changes (e.g., parameter path changes in `CalibrationStore`), it must be updated in 5 places. The base-class method `get_therm_clks()` exists and is identical but not used.

**Fix needed**: Replace all 5 with `self.get_therm_clks("qb")` calls.

---

### Problem 9 — Builder Docstrings Describe Old Signatures (LOW)

**What**: Several builder functions have docstrings referencing parameters that no longer exist (e.g., `ro_el` removed after binding refactor).

**Why it matters**: Developer confusion, outdated API understanding.

**Fix needed**: Systematic docstring update pass across `programs/builders/`.

---

### Problem 10 — Test Location Inconsistency (LOW)

**What**: `tests/gate_architecture/` lives outside `qubox_v2/tests/`. One test tree for the package, another at repo root.

**Why it matters**: Testing infrastructure is fragmented. CI configuration likely needs two separate test roots.

**Fix needed**: Consolidate under `qubox_v2/tests/` with a shared conftest.

---

## 9. Strategic Recommendations

### Short-Term Improvements (1–2 weeks)

1. **Replace the 5 duplicated `_resolve_qb_therm_clks` helpers** with calls to `self.get_therm_clks("qb")`. This is a mechanical, low-risk change.

2. **Fix the `PowerRabi` silent exception fallback**: Either remove the broad `except Exception` and let failures propagate, or at minimum log the full exception at WARNING level so users know which path ran.

3. **Delete or wire up `experiments/configs.py`**: If the config-dataclass pattern is the intended future API, implement it in one experiment class as a prototype. If not, delete the file before it misleads more users.

4. **Fix `CalibrateReadoutFull` vs `CalibrationReadoutFull` naming**: Deprecate one and document the migration.

5. **Update builder docstrings** that reference `ro_el` or other removed parameters.

6. **Add offline tests for 3–5 experiment classes** using the `FakePulseManager` pattern from `tests/gate_architecture/conftest.py`. Start with `T1Relaxation`, `PowerRabi`, and `QubitSpectroscopy` as they are the most frequently used.

### Medium-Term Refactors (1–3 months)

1. **Implement the SCTP validation script**: Build the Standard Compilation Trust Protocol using qubox API, compile to QUA, and run through the QM simulator with `n_avg=1` and 3-point sweep. Make this runnable as an agent trust check.

2. **Replace wildcard QUA imports** in all builder modules with explicit imports. This is tedious but mechanical and makes the codebase statically analyzable.

3. **Complete the `cQED_attributes` → `CalibrationStore` migration**: Element names (`ro_el`, `qb_el`, `st_el`) are the last major fields that still live in `cQED_attributes` without a `CalibrationStore` equivalent. Define a canonical `ElementNames` record in `CalibrationData` and migrate element names there. This completes the single-source-of-truth goal.

4. **Remove the legacy context accessor fallbacks** in `ExperimentBase`: The `getattr(self._ctx, "pulseOpMngr", getattr(self._ctx, "pulse_mgr", None))` patterns are dead code. Clean them up.

5. **Wire `RamseyProtocol` and `EchoProtocol` to `T2Ramsey` and `T2Echo` experiment classes**: Make the circuit compiler path the canonical path for at least these two experiments. This validates the circuit architecture end-to-end in a real experiment context.

### Long-Term Architectural Direction

1. **Phase out `measureMacro` singleton**: The `MeasurementConfig` frozen dataclass (v2.1) is the right replacement. The path is:
   - Phase A: Pass `MeasurementConfig` as a parameter into builder functions (alongside `bindings`).
   - Phase B: Have `SessionManager` create a `MeasurementConfig` from `CalibrationStore` on `open()`.
   - Phase C: Remove the singleton. All measurement configuration is session-scoped.

2. **Unify the two compilation paths**: Choose whether the circuit compiler (`CircuitRunnerV2`) or the direct builder functions are the canonical path for new experiments. The circuit path is more principled (parameter provenance, golden-file tests, display). Extend it to cover more experiment types.

3. **Mandate simulator-backed validation in CI**: Even a few key experiments (SCTP, T1, PowerRabi) compiled and simulated in CI would dramatically improve confidence in the compilation pipeline. The QM simulator API supports this without physical hardware.

4. **Add per-parameter calibration timestamps and confidence scores**: Extend `CQEDParams` in `calibration/models.py` with optional `_fit_r2` and `_last_calibrated` fields per physics parameter. This enables labs to audit "when was my qubit frequency last calibrated and how good was the fit?"

5. **Clarify the role of `compile/`**: The `compile/` module (ansatz, GPU accelerators, structure_search) is a gate sequence optimizer for quantum optimal control — a very different scope from the experiment orchestration core. It should either be clearly documented as an optional advanced module, or placed in a separate sub-package to signal its independence from the experiment flow.

---

## 10. Suggested Next Refactor Targets

In priority order, if one wants to improve the codebase:

1. **`programs/macros/measure.py`** — The singleton must become a session-scoped object. This is the highest-leverage change for correctness.

2. **`experiments/experiment_base.py`** — Clean up legacy fallback chains, add `get_therm_clks` delegation, ensure consistent `save_output()`.

3. **`programs/builders/time_domain.py`** + other builder modules — Replace wildcard imports; fix docstrings; add tests.

4. **`analysis/cQED_attributes.py`** — Define the final scope of this class: element names only (no physics values). Deprecate physics fields.

5. **`experiments/configs.py`** — Implement or delete.

6. **`qubox_v2/tests/`** — Expand test coverage to include at least 3 experiment classes and the SCTP trust protocol.

---

## 11. Final Verdict

### Is the current API design healthy?

**Partially.** The experiment lifecycle architecture (`_build_impl()` → `ProgramBuildResult` → `run_program()`) is clean and physically faithful. The calibration infrastructure (`CalibrationStore`, transactional patches, `FitResult.success`) is solid. The circuit compiler layer is well-designed.

However, the `measureMacro` singleton is a genuine correctness hazard for real lab workflows, and the dual calibration-truth problem creates subtle drift risks. These are not cosmetic concerns — they are design patterns that will cause incorrect data if not addressed.

### Is it good enough for long-term growth?

**Conditionally.** If the `measureMacro` singleton is replaced with session-scoped measurement configuration, and the calibration truth is consolidated, the architecture is extensible and maintainable. If not addressed, these problems will compound as more experiments are added.

The near-zero test coverage for experiment classes and builders is the other serious long-term risk. The gate architecture tests demonstrate that offline testing of this codebase is achievable. Expanding that coverage is necessary before the framework can be trusted for autonomous calibration workflows.

### What should be fixed first?

1. **Implement the SCTP validation script** — even one successful simulator run of the canonical trust protocol would meaningfully raise confidence in the compilation pipeline.
2. **Add offline tests for 3–5 experiment classes** — use the existing conftest pattern.
3. **Begin `measureMacro` migration** — start by passing `MeasurementConfig` alongside `bindings` in one experiment, as proof of concept.
4. **Consolidate the calibration truth** — complete the `cQED_attributes → CalibrationStore` migration for element names.

The codebase is not in crisis. It is a framework under active, thoughtful development, with good engineering practices in many areas. The issues identified here are fixable without architectural surgery. The most important single action is implementing the SCTP validator — it creates a trust gate that catches many other problems automatically.

---

*Report generated from static read-only inspection of source files, documentation, and tests. No code was modified during this audit.*
