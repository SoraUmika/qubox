# qubox_v2_legacy — Codebase Architecture Survey

> **Historical document (2026-03-07).** This surveys the `qubox_v2_legacy`
> codebase which has since been fully eliminated and merged into `qubox`.
> For the current architecture, see [API Reference](../API_REFERENCE.md)
> and [Architecture — Package Map](../site_docs/architecture/package-map.md).

> **Generated:** 2026-03-07  
> **Type:** Read-only structural reconnaissance  
> **Scope:** Full `qubox_v2_legacy/` package (183 Python files across 20 packages)

---

## Table of Contents

1. [A1. Repository Subsystem Map](#a1-repository-subsystem-map)
2. [A2. Dependency Analysis](#a2-dependency-analysis)
3. [A3. Architectural Smells](#a3-architectural-smells)
4. [A4. Suggested Target Layering](#a4-suggested-target-layering)
5. [A5. Experiment Flow Discussion](#a5-experiment-flow-discussion)
6. [B. Graphical Outputs Index](#b-graphical-outputs-index)
7. [Dependency Heat Ranking](#dependency-heat-ranking)
8. [Cycle Report](#cycle-report)
9. [Proposed Future Package Map](#proposed-future-package-map)
10. [Specific Questions Answered](#specific-questions-answered)
11. [Suggested Next Actions](#suggested-next-actions)
12. [Appendix: Tooling & Reproduction](#appendix-tooling--reproduction)

---

## A1. Repository Subsystem Map

### Package Inventory

| Package | Files | Apparent Responsibility | Layer |
|---------|------:|------------------------|-------|
| **core** | 17 | Config models, protocols, errors, logging, experiment context, bindings, persistence | 0 — Foundation |
| **pulses** | 8 | Waveform specs, pulse lifecycle, PulseOperationManager, registry | 1 — Primitives |
| **gates** | 23 | Gate algebra: models (unitary/Kraus), hardware implementations, noise, caching, Liouville algebra | 2 — Primitives |
| **hardware** | 6 | OPX+/Octave control: ConfigEngine, HardwareController, ProgramRunner, QueueManager | 3 — Infrastructure |
| **devices** | 4 | External instrument management (DeviceManager, DeviceHandle, DeviceSpec) | 3 — Infrastructure |
| **compile** | 11 | Gate compilation via ansatz optimization (GPU-accelerated) | 4 — Compilation |
| **simulation** | 5 | cQED Hamiltonian + Lindblad solver (QuTiP-based) | 4 — Simulation |
| **programs** | 28 | QUA program factories, measurement macros, builders per experiment type, circuit compiler | 5 — Program Construction |
| **calibration** | 11 | Calibration store, orchestrator, patch rules, mixer calibration, history, Pydantic models | 6 — Calibration |
| **analysis** | 16 | Fitting, metrics, cQED attributes, pulse analysis, plotting, post-processing, output containers | 6 — Analysis |
| **optimization** | 4 | Smooth + stochastic optimization wrappers (CMA-ES, skopt) | 7 — Optimization |
| **experiments** | 30 | Experiment base classes, session management, concrete experiments (spectroscopy, time-domain, cavity, tomography, calibration) | 8 — Orchestration |
| **autotune** | 2 | Automated calibration workflows (post-cavity autotune) | 9 — Automation |
| **verification** | 4 | Persistence verification, schema checks, waveform regression | 9 — QA |
| **gui** | 2 | PyQt5-based program GUI | 10 — UI |
| **tools** | 3 | Waveform generators | 10 — Utilities |
| **examples** | 3 | Demo scripts (circuit architecture, session startup) | 11 — Docs |
| **tests** | 5 | Unit tests (calibration, parameter resolution, workflow safety) | 11 — Tests |
| **compat** | 0 | Empty — reserved for backward-compatibility shims | 11 — Legacy |
| **migration** | 1 | Empty init — reserved for migration tooling | 11 — Legacy |

### Inferred Layering

The codebase intends a clean bottom-up layering:

```
Layer 0:  core (protocols, config, errors, logging, types)
Layer 1:  pulses (waveform primitives)
Layer 2:  gates (gate algebra, noise models)
Layer 3:  hardware, devices (OPX+ control, external instruments)
Layer 4:  compile, simulation (gate compilation, cQED solver)
Layer 5:  programs (QUA program factories, macros)
Layer 6:  calibration, analysis (data stores, fitting, metrics)
Layer 7:  optimization (parameter optimization)
Layer 8:  experiments (orchestration, session, concrete experiments)
Layer 9:  autotune, verification (automation, QA)
Layer 10: gui, tools (UI, waveform generators)
Layer 11: examples, tests, compat, migration
```

**Verdict:** The layering intention is sound. The implementation violates it significantly, as detailed in Section A2.

---

## A2. Dependency Analysis

### Package-Level Dependency Edges (51 total)

See: [`docs/architecture/package_dependency_graph.svg`](architecture/package_dependency_graph.svg)

#### Dependency Direction Summary

| Source Package | Depends On |
|---------------|------------|
| **core** (L0) | analysis ⚠, experiments ⚠, hardware ⚠, programs ⚠, pulses |
| **pulses** (L1) | analysis ⚠, core, tools |
| **gates** (L2) | analysis ⚠, core |
| **hardware** (L3) | analysis ⚠, calibration ⚠, core, programs |
| **devices** (L3) | core |
| **compile** (L4) | gates |
| **programs** (L5) | analysis, core, experiments ⚠, gates, pulses, tools |
| **calibration** (L6) | analysis, core, hardware, programs |
| **analysis** (L6) | calibration, core, experiments ⚠ |
| **experiments** (L8) | analysis, calibration, core, devices, hardware, programs, pulses, tools |
| **autotune** (L9) | experiments, programs |
| **verification** (L9) | core, pulses |
| **gui** (L10) | — (not analyzed, likely imports pulses/programs) |
| **tools** (L10) | core, pulses |
| **examples** (L11) | core, programs, pulses, verification |
| **tests** (L11) | analysis, calibration, experiments, programs |

⚠ = suspiciously upward import (lower layer depends on higher layer)

### Central Hub Modules

Ranked by total degree (in + out edges at package level):

| Rank | Package | In-Degree | Out-Degree | Total | Role |
|------|---------|-----------|------------|-------|------|
| 1 | **core** | 11 | 5 | **16** | Foundation — imported by almost everything, but also imports upward |
| 2 | **experiments** | 5 | 8 | **13** | Top-level orchestrator — expected high fan-out |
| 3 | **programs** | 7 | 6 | **13** | Program factories — center of the build pipeline |
| 4 | **analysis** | 8 | 3 | **11** | Heavily imported Output/cQED_attributes permeate everything |
| 5 | **pulses** | 6 | 3 | **9** | Waveform layer — many consumers |

### Bidirectional (Mutual) Dependencies

These are the most dangerous structural couplings — packages that import each other:

| Pair | Severity | Assessment |
|------|----------|------------|
| **core ↔ analysis** | 🔴 Critical | `core.bindings` imports `analysis.cQED_attributes`. Inverted — core should never depend on analysis. |
| **core ↔ experiments** | 🔴 Critical | `core.preflight` and `core.artifacts` import `experiments.session.SessionManager`. Inverted — foundation depends on orchestration. |
| **core ↔ hardware** | 🔴 Critical | `core.artifacts` imports `hardware.program_runner.RunResult`. Type should live in core. |
| **core ↔ programs** | 🔴 Critical | `core.measurement_config` imports `programs.macros.measure.measureMacro`. |
| **core ↔ pulses** | 🟡 Moderate | `core.schemas` imports `pulses.spec_models.VALID_SHAPES`. |
| **analysis ↔ calibration** | 🟡 Moderate | `analysis.fitting` imports `experiments.result.FitResult` (transitive). Mutual analysis↔calibration imports. |
| **analysis ↔ experiments** | 🟡 Moderate | `analysis.fitting` → `experiments.result.FitResult`. |
| **hardware ↔ calibration** | 🟡 Moderate | `controller.py` imports `calibration.mixer_calibration` for mixer cal workflow. |
| **programs ↔ experiments** | 🟡 Moderate | `programs.circuit_execution/compiler` imports `experiments.result.ProgramBuildResult`. |
| **pulses ↔ analysis** | 🟡 Moderate | `pulses.manager/registry` imports `analysis.pulseOp` and `analysis.algorithms`. |

### Layer Violations (16 detected)

| Severity | From (Layer) | To (Layer) | Gap | Specific Files |
|----------|-------------|------------|-----|----------------|
| 🔴 ERROR | core (0) | analysis (6) | +6 | `bindings.py` → `cQED_attributes` |
| 🔴 ERROR | core (0) | experiments (8) | +8 | `preflight.py`, `artifacts.py` → `SessionManager` |
| 🔴 ERROR | core (0) | hardware (3) | +3 | `artifacts.py` → `RunResult` |
| 🔴 ERROR | core (0) | programs (5) | +5 | `measurement_config.py` → `measureMacro` |
| 🔴 ERROR | pulses (1) | analysis (6) | +5 | `manager.py`, `registry.py` → `PulseOp` |
| 🔴 ERROR | pulses (1) | tools (10) | +9 | `manager.py` → `tools.waveforms` |
| 🔴 ERROR | gates (2) | analysis (6) | +4 | `gates` → `analysis` |
| 🔴 ERROR | hardware (3) | analysis (6) | +3 | `program_runner.py` → `analysis.output.Output` |
| 🔴 ERROR | hardware (3) | calibration (6) | +3 | `controller.py` → `mixer_calibration` |
| 🔴 ERROR | programs (5) | experiments (8) | +3 | `circuit_execution.py`, `circuit_compiler.py` → `ProgramBuildResult` |
| 🔴 ERROR | programs (5) | tools (10) | +5 | Multiple builders use `tools.waveforms` |
| 🟡 WARN | core (0) | pulses (1) | +1 | `schemas.py` → `VALID_SHAPES` |
| 🟡 WARN | hardware (3) | programs (5) | +2 | `program_runner` uses program types |
| 🟡 WARN | programs (5) | analysis (6) | +1 | Builders use analysis utilities |
| 🟡 WARN | analysis (6) | experiments (8) | +2 | `fitting.py` → `FitResult` |
| 🟡 WARN | experiments (8) | tools (10) | +2 | experiments use waveform tools |

---

## A3. Architectural Smells

### Smell 1: `core/` Is Not Actually Core — It Reaches Upward 

The `core` package (Layer 0) has **5 upward imports** into layers 1–8. A true foundation layer should be imported by everything and import nothing above it.

**Specific violations:**
- `core/bindings.py` → `analysis.cQED_attributes` — binds core's channel-binding API to a legacy analysis attributes class
- `core/artifacts.py` → `experiments.session.SessionManager` and `hardware.program_runner.RunResult`
- `core/preflight.py` → `experiments.session.SessionManager`
- `core/measurement_config.py` → `programs.macros.measure.measureMacro`
- `core/schemas.py` → `pulses.spec_models.VALID_SHAPES`

**Root cause:** Several data types (`RunResult`, `ProgramBuildResult`, `FitResult`, `cQED_attributes`, `Output`, `PulseOp`) were originally defined in higher-layer packages but are needed everywhere. Rather than moving the types down to `core/`, the imports were added upward — sometimes hidden behind `TYPE_CHECKING` guards or lazy imports.

### Smell 2: `analysis` Is a God Package

The `analysis` package (16 files) is imported by **8 other packages**, making it the most-imported non-core package. It contains:
- Output container (`Output`, a dict subclass)
- cQED parameter attributes (`cQED_attributes`)
- Fitting and algorithm libraries
- Physics plotting
- Post-processing and post-selection
- Pulse analysis (`PulseOp`, waveform FFT)

Several of these (especially `Output`, `cQED_attributes`, `PulseOp`) should live in `core/` since they are used across all layers.

### Smell 3: `experiments.result` Owns Types That Don't Belong There

`ProgramBuildResult`, `FitResult`, `AnalysisResult`, and `SimulationResult` are defined in `experiments/result.py`, but are imported by `programs/`, `analysis/`, and `hardware/`. These are cross-cutting data types that should live in a lower layer (e.g., `core/results.py`).

### Smell 4: Bidirectional Core ↔ Analysis Coupling

`core.bindings` imports `analysis.cQED_attributes` to create `FrequencyPlan.from_attributes()`. Meanwhile, `analysis` imports from `core`. This creates a hard mutual dependency at the most foundational level.

### Smell 5: Hardware Embeds Calibration Logic

`hardware/controller.py` imports `calibration.mixer_calibration` to perform mixer calibration — an operational concern that should be orchestrated by the calibration layer, not embedded in the hardware controller.

### Smell 6: Pulses Depend on Analysis

`pulses/manager.py` and `pulses/pulse_registry.py` import `analysis.pulseOp.PulseOp` and `analysis.algorithms.compute_waveform_fft`. These analysis utilities are really pulse-level tools and should live in `pulses/` or `core/`.

### Smell 7: Two Competing Session/Context Objects

The codebase has both `ExperimentRunner` (legacy, in `experiments/base.py`) and `SessionManager` (modern, in `experiments/session.py`). Both compose the same set of objects (`HardwareController`, `ProgramRunner`, `PulseOperationManager`, `DeviceManager`). `ExperimentBase._ctx` accepts either. This dual-track design adds confusion and duplication.

### Smell 8: 481 Package-Level Cycles

The dependency graph contains **481 cycles** at the package level (37 of length ≤ 3). This is extraordinarily high for a 20-package codebase and indicates systemic tangling rather than isolated issues.

**Fundamental length-2 cycles (direct mutual imports):**
- `analysis ↔ calibration`
- `analysis ↔ core`
- `analysis ↔ experiments`
- `calibration ↔ hardware`
- `core ↔ analysis`
- `core ↔ experiments`
- `core ↔ hardware`
- `core ↔ programs`
- `core ↔ pulses`
- `experiments ↔ programs`
- `pulses ↔ tools`

---

## A4. Suggested Target Layering

### Ideal Dependency Direction

```
                            ┌──────────────┐
                            │  notebooks   │  (external consumers)
                            │  autotune    │
                            │  gui         │
                            └──────┬───────┘
                                   │
                            ┌──────▼───────┐
                            │ experiments  │  Layer 8: Orchestration
                            └──────┬───────┘
                                   │
                 ┌─────────────────┼─────────────────┐
                 │                 │                  │
          ┌──────▼──────┐  ┌──────▼──────┐  ┌───────▼──────┐
          │ calibration │  │  programs   │  │ optimization │  Layer 5–7
          └──────┬──────┘  └──────┬──────┘  └──────────────┘
                 │                │
       ┌─────────┼────────────────┤
       │         │                │
┌──────▼──────┐  │         ┌──────▼──────┐
│  analysis   │  │         │   compile   │   Layer 4–6
└──────┬──────┘  │         └──────┬──────┘
       │         │                │
       │    ┌────▼─────┐   ┌─────▼──────┐
       │    │ hardware │   │ simulation │    Layer 3–4
       │    │ devices  │   └────────────┘
       │    └────┬─────┘
       │         │
       │    ┌────▼─────┐
       │    │  pulses   │                   Layer 1
       │    │  gates    │
       │    └────┬─────┘
       │         │
       └─────────┤
                 │
          ┌──────▼──────┐
          │    core     │                   Layer 0
          └─────────────┘
```

**Rules:**
- Arrows point **downward only** (higher layers depend on lower layers).
- `core` imports **nothing** from above.
- `analysis` and `calibration` are peers that may share types through `core`.
- `experiments` is the integration layer — it may import from any lower layer.

### Edge Classification

| Edge | Verdict | Action Required |
|------|---------|-----------------|
| experiments → programs, calibration, analysis, hardware, pulses, devices | ✅ Acceptable | None |
| programs → core, pulses, gates, tools | ✅ Acceptable | None |
| calibration → core, analysis | ✅ Acceptable | None |
| hardware → core | ✅ Acceptable | None |
| gates → core | ✅ Acceptable | None |
| core → analysis | 🔴 **Must fix** | Move `cQED_attributes` and `Output` into core |
| core → experiments | 🔴 **Must fix** | Move `SessionManager` type hints behind TYPE_CHECKING only; move `RunResult`, `ProgramBuildResult` to core |
| core → hardware | 🔴 **Must fix** | Move `RunResult` to core |
| core → programs | 🔴 **Must fix** | Move `measureMacro` type hint to core or use Protocol |
| pulses → analysis | 🔴 **Must fix** | Move `PulseOp` and `compute_waveform_fft` to pulses |
| hardware → calibration | 🟡 Refactor | Extract mixer calibration orchestration to calibration layer |
| programs → experiments | 🟡 Refactor | Move `ProgramBuildResult` to core |
| analysis → experiments | 🟡 Refactor | Move `FitResult` to core |

---

## A5. Experiment Flow Discussion

See: [`docs/architecture/experiment_flow.svg`](architecture/experiment_flow.svg)

### How Experiments Connect to the System

The typical experiment lifecycle flows as follows:

```
1. Notebook / Script
   │
   ├── SessionManager.from_sample(sample_dir, ...)
   │    ├── Reads hardware.json, calibration.json, pulse_specs.json, cqed_params.json
   │    ├── Creates ExperimentContext (frozen identity passport)
   │    ├── Opens ConfigEngine → HardwareController → QuantumMachinesManager
   │    ├── Creates ProgramRunner
   │    ├── Creates PulseOperationManager + PulseRegistry
   │    ├── Creates CalibrationStore + CalibrationOrchestrator
   │    └── Creates DeviceManager (optional, for external LOs etc.)
   │
   ├── exp = SomeExperiment(session)     # e.g., QubitSpectroscopy, PowerRabi
   │
   ├── exp.run(n_avg=1000, ...)
   │    ├── exp.build_program() → ProgramBuildResult
   │    │    └── Calls programs.builders.*.build_*() to construct QUA program
   │    │         └── Uses programs.macros.measure.measureMacro
   │    │         └── Uses pulses.PulseOperationManager for waveform config
   │    │
   │    ├── exp.burn_pulses()  →  writes waveforms into QM config
   │    ├── ProgramRunner.run_program(prog, n_total)
   │    │    └── Submits to OPX+ via QuantumMachinesManager
   │    │    └── Returns RunResult (output dict + metadata)
   │    │
   │    └── exp.process(raw_output) → AnalysisResult
   │         └── Calls analysis.fitting, analysis.metrics
   │         └── Returns fitted parameters, metrics, plot data
   │
   └── exp.analyze(result, update_calibration=True)
        └── CalibrationOrchestrator.run_analysis_patch_cycle()
             ├── Builds a Patch from analysis results
             ├── Applies patch to CalibrationStore
             └── Persists calibration.json and Output artifacts
```

### Key Observations About the Flow

1. **SessionManager is the god object.** It composes HardwareController, ProgramRunner, PulseOperationManager, CalibrationStore, CalibrationOrchestrator, DeviceManager, and PulseRegistry. It is the single point of entry for all experiment operations.

2. **Programs are built by experiment-specific builders** in `programs/builders/`. Each builder is a factory function that returns a QUA program plus metadata (`ProgramBuildResult`). The builders use macros (especially `measureMacro`) extensively.

3. **Calibration is tightly coupled to the session.** The `CalibrationOrchestrator` holds a back-reference to `SessionManager`, creating a bidirectional dependency between the session layer and the calibration layer.

4. **Analysis is pulled in at every level.** The `analysis.output.Output` container (a dict subclass) is used for result storage across hardware, programs, and experiments. The `cQED_attributes` class (a parameter dictionary) is used for frequency planning and builder configuration.

5. **Notebook-driven workflow is strong.** The `HardwareDefinition` builder in `core/` lets notebooks define hardware configuration interactively, and `SessionManager.from_sample()` provides a clean entry point. This is a well-designed pattern.

6. **The flow path `experiment → build → run → process → analyze → calibrate` is clear** in intent, but the dependency arrows between these steps are tangled — programs import experiment types, analysis imports experiment types, calibration imports analysis types, etc.

---

## B. Graphical Outputs Index

| Diagram | File | Description |
|---------|------|-------------|
| B1. Package Dependency Graph | [`package_dependency_graph.svg`](architecture/package_dependency_graph.svg) | All 20 packages with dependency edges, cycle highlighting, layer violations |
| B2. Workflow Dependency Graph | [`workflow_dependency_graph.svg`](architecture/workflow_dependency_graph.svg) | Focused on 9 core scientific packages only |
| B3. Class Relationships | [`class_relationships.svg`](architecture/class_relationships.svg) | UML-style diagram of ~25 key classes showing composition |
| B4. Experiment Flow | [`experiment_flow.svg`](architecture/experiment_flow.svg) | Control/data flow through experiment lifecycle |

Machine-readable data:

| File | Contents |
|------|----------|
| [`package_dependencies.json`](architecture/package_dependencies.json) | Package-level adjacency list + file counts + external deps |
| [`centrality_metrics.json`](architecture/centrality_metrics.json) | Package centrality + top-imported/importing module rankings |
| [`cycle_report.json`](architecture/cycle_report.json) | All 481 cycles + 16 layer violations |
| [`module_edges.json`](architecture/module_edges.json) | Full module-level edge list (for custom analysis) |

---

## Dependency Heat Ranking

### Top 15 Most-Imported Modules (In-Degree)

| Rank | Module | Import Count | Assessment |
|------|--------|-------------|------------|
| 1 | `core.bindings` | **54** | 🔴 Massive hub — channel bindings are needed everywhere |
| 2 | `programs.macros.measure` | **31** | 🟡 Key macro — all measurement programs import it |
| 3 | `hardware.program_runner` | **27** | 🟡 RunResult + ProgramRunner used widely |
| 4 | `experiments.result` | **20** | 🔴 Contains types that should be in core |
| 5 | `programs` (init) | **20** | 🟡 Package-level re-exports |
| 6 | `analysis` (init) | **17** | 🟡 Package-level re-exports |
| 7 | `analysis.output` | **16** | 🔴 Output dict used across all layers |
| 8 | `experiments.experiment_base` | **16** | 🟡 Expected — all experiments inherit from it |
| 9 | `analysis.analysis_tools` | **13** | Analysis utility functions |
| 10 | `core.logging` | **13** | ✅ Expected — logging is foundational |
| 11 | `gates.contexts` | **13** | ModelContext/NoiseConfig used by all gate types |
| 12 | `programs.measurement` | **12** | Measurement program factories |
| 13 | `core.persistence_policy` | **11** | ✅ Expected — used for JSON serialization |
| 14 | `core.errors` | **11** | ✅ Expected — error types are foundational |
| 15 | `qubox_v2_legacy` (root init) | **10** | Package-level logger access |

### Top 15 Most-Importing Modules (Out-Degree)

| Rank | Module | Import Count | Assessment |
|------|--------|-------------|------------|
| 1 | `experiments.session` | **27** | 🔴 God module — composes everything |
| 2 | `experiments.calibration.gates` | **18** | Complex calibration experiment |
| 3 | `experiments.calibration.readout` | **16** | Complex calibration experiment |
| 4 | `experiments.experiment_base` | **15** | Base class needs many imports |
| 5 | `programs.builders.cavity` | **14** | Complex builder |
| 6 | `programs.builders.time_domain` | **13** | Complex builder |
| 7 | `experiments.base` | **12** | Legacy ExperimentRunner (duplicate of session) |
| 8 | `experiments.time_domain.rabi` | **12** | Complex experiment |
| 9 | `programs.circuit_compiler` | **11** | Compilation orchestration |
| 10 | `calibration.orchestrator` | **10** | Calibration workflow orchestration |

---

## Cycle Report

### Fundamental Bidirectional Pairs (Length-2 Cycles)

| Pair | Primary Violation |
|------|-------------------|
| `core ↔ analysis` | `core.bindings` → `analysis.cQED_attributes` |
| `core ↔ experiments` | `core.preflight`, `core.artifacts` → `experiments.session` |
| `core ↔ hardware` | `core.artifacts` → `hardware.program_runner.RunResult` |
| `core ↔ programs` | `core.measurement_config` → `programs.macros.measure` |
| `core ↔ pulses` | `core.schemas` → `pulses.spec_models.VALID_SHAPES` |
| `analysis ↔ calibration` | mutual imports for fitting + calibration data |
| `analysis ↔ experiments` | `analysis.fitting` → `experiments.result.FitResult` |
| `hardware ↔ calibration` | `hardware.controller` → `calibration.mixer_calibration` |
| `programs ↔ experiments` | `programs.circuit_*` → `experiments.result.ProgramBuildResult` |
| `pulses ↔ analysis` | `pulses.manager/registry` → `analysis.pulseOp` |
| `pulses ↔ tools` | `pulses.manager` → `tools.waveforms` |

### Cycle Classification

| Cycle Type | Count | Severity |
|------------|------:|----------|
| **Involving `core`** | ~100+ | 🔴 Dangerous — poisons the entire dependency tree |
| **analysis ↔ calibration ↔ programs** | ~150+ | 🟡 Problematic — tight coupling of data flow layers |
| **experiments ↔ programs** | ~50+ | 🟡 Fixable — just move `ProgramBuildResult` to core |
| **pulses ↔ tools** | ~10 | 🟢 Minor — `tools.waveforms` is a utility |

### Assessment

The cycle explosion is caused by a small number of **misplaced types**. Because `core` imports upward, and `core` is imported by everything, every package that touches `core` becomes part of every cycle. Fixing the 5 upward imports from `core/` would eliminate the majority of cycles.

---

## Proposed Future Package Map

### Clean Target Architecture

```
qubox_v2_legacy/
├── core/                  # Layer 0: ZERO upward imports
│   ├── types.py           # Enums, type aliases, constants
│   ├── errors.py          # All error types
│   ├── logging.py         # Logger configuration
│   ├── protocols.py       # Protocol interfaces
│   ├── config.py          # Pydantic config models
│   ├── results.py         # ← MOVE HERE: RunResult, ProgramBuildResult,
│   │                      #   FitResult, AnalysisResult, SimulationResult
│   ├── output.py          # ← MOVE HERE from analysis: Output, OutputArray
│   ├── attributes.py      # ← MOVE HERE from analysis: cQED_attributes
│   ├── bindings.py        # Channel bindings (drop analysis import)
│   ├── persistence.py     # Persistence policy
│   ├── schemas.py         # JSON schema validation (drop pulses import)
│   ├── experiment_context.py
│   ├── session_state.py
│   ├── hardware_definition.py
│   └── measurement_config.py  # (drop programs import, use Protocol)
│
├── pulses/                # Layer 1: depends only on core
│   ├── models.py
│   ├── waveforms.py       # ← MOVE HERE from tools: waveform generators
│   ├── pulse_op.py        # ← MOVE HERE from analysis: PulseOp
│   ├── algorithms.py      # ← MOVE HERE from analysis: compute_waveform_fft
│   ├── manager.py
│   ├── registry.py
│   └── factory.py
│
├── gates/                 # Layer 2: depends on core, pulses
│   └── (unchanged — cleanly organized)
│
├── hardware/              # Layer 3: depends on core
│   ├── config_engine.py
│   ├── controller.py      # ← REMOVE calibration import
│   ├── program_runner.py  # ← REMOVE analysis import
│   └── queue_manager.py
│
├── devices/               # Layer 3: depends on core
│   └── (unchanged)
│
├── compile/               # Layer 4: depends on core, gates
│   └── (unchanged)
│
├── simulation/            # Layer 4: depends on core, gates
│   └── (unchanged)
│
├── programs/              # Layer 5: depends on core, pulses, gates
│   ├── builders/          # ← REMOVE experiments import
│   ├── macros/
│   └── circuit_*.py
│
├── calibration/           # Layer 6: depends on core, analysis, hardware
│   ├── mixer_calibration.py  # ← MOVE orchestration here from controller
│   └── (rest unchanged)
│
├── analysis/              # Layer 6: depends on core (only)
│   ├── fitting.py         # ← REMOVE experiments import
│   ├── plotting.py
│   └── (rest lighter after moving Output, cQED_attributes, PulseOp up)
│
├── experiments/           # Layer 8: depends on all lower layers
│   ├── session.py         # SessionManager (only session object)
│   ├── experiment_base.py
│   └── (concrete experiments unchanged)
│
└── (autotune, verification, gui, tools, examples, tests — unchanged)
```

### Key Moves Required

| What | From | To | Impact |
|------|------|----|--------|
| `RunResult`, `ProgramBuildResult`, `FitResult`, `AnalysisResult`, `SimulationResult` | `experiments.result` / `hardware.program_runner` | `core.results` | Breaks 5+ cycles |
| `Output`, `OutputArray` | `analysis.output` | `core.output` | Breaks 3+ cycles |
| `cQED_attributes` | `analysis.cQED_attributes` | `core.attributes` | Breaks core↔analysis cycle |
| `PulseOp` | `analysis.pulseOp` | `pulses.pulse_op` | Breaks pulses↔analysis cycle |
| `compute_waveform_fft` | `analysis.algorithms` | `pulses.algorithms` | Breaks pulses↔analysis cycle |
| Waveform generators | `tools.waveforms` | `pulses.waveforms` | Breaks pulses↔tools cycle |
| Mixer calibration orchestration | `hardware.controller` (inline) | `calibration.mixer_calibration` | Breaks hardware↔calibration cycle |
| `ExperimentRunner` | `experiments.base` | Deprecate / merge into SessionManager | Reduces duplication |

---

## Specific Questions Answered

### 1. What are the major architectural layers of qubox as it currently exists?

There are 12 layers (0–11) as documented in Section A1. The main scientific stack is:
- **core** (foundation) → **pulses/gates** (primitives) → **hardware/devices** (control) → **programs** (QUA factories) → **calibration/analysis** (data) → **experiments** (orchestration)

### 2. Is the current dependency direction mostly sensible, or is it tangled?

**It is significantly tangled.** The intended layering is sensible, but the implementation has 51 package-level edges of which **16 are layer violations** and **11 are bidirectional cycles**. The root cause is misplaced types: a handful of widely-used data classes (`RunResult`, `Output`, `cQED_attributes`, `ProgramBuildResult`) were defined in upper layers but are needed at every level.

### 3. Which modules are the biggest coupling hotspots?

1. **`core.bindings`** — 54 imports into it; also imports upward into `analysis`
2. **`experiments.session`** — 27 outward imports; god module composing everything
3. **`programs.macros.measure`** — 31 imports into it; a critical shared utility
4. **`analysis.output`** — 16 imports into it from all layers
5. **`experiments.result`** — 20 imports into it; contains types used 3 layers below

### 4. Are experiments cleanly separated from hardware, calibration, and analysis?

**No.** Experiments depend on all three (which is acceptable — orchestration layers should). However, the **reverse** is also true: hardware imports calibration, analysis imports experiments, programs import experiments. The separation is violated in both directions.

### 5. Is there evidence that notebooks or scripts are driving architecture in an unhealthy way?

**Partially.** The `HardwareDefinition` builder in `core/` is specifically designed for notebook-first workflows and is well-architected. However, the `ExperimentRunner` (in `experiments/base.py`) appears to be a legacy context manager that duplicates `SessionManager` and may have originated from notebook usage patterns. The dual-track design (SessionManager vs. ExperimentRunner) adds confusion.

### 6. What are the top five structural risks in the current codebase?

1. **`core/` imports upward into 5 higher-layer packages** — poisons the entire dependency tree with cycles
2. **481 package-level cycles** — makes safe refactoring extremely difficult
3. **SessionManager is a god object** (27 outward imports, composes 7+ subsystems) — single point of fragility
4. **Shared types are in the wrong packages** (RunResult, Output, ProgramBuildResult, etc.) — forces cross-layer imports
5. **hardware ↔ calibration bidirectional coupling** — mixer calibration logic is embedded in the hardware controller, making it impossible to modify calibration without touching hardware

### 7. What would the ideal target dependency structure look like?

See Section A4 and the proposed package map in the "Proposed Future Package Map" section. The key principle: **all shared data types must live in `core/`**, and dependency arrows must flow **exclusively downward** from higher layers to lower layers.

---

## Suggested Next Actions

### Priority 1: Move Shared Types to `core/` (High Impact, Moderate Effort)

Create `core/results.py` and move `RunResult`, `ProgramBuildResult`, `FitResult`, `AnalysisResult`, `SimulationResult` there. Create `core/output.py` and move `Output`/`OutputArray` there. This single refactor eliminates the majority of cycles.

**Estimated cycle reduction:** ~300+ of the 481 cycles eliminated.

### Priority 2: Break `core`'s Upward Imports (High Impact, Low Effort)

Fix the 5 specific imports in `core/` that reach into higher layers:
- `core/bindings.py`: Move `cQED_attributes` to `core/attributes.py`
- `core/artifacts.py`: Import from `core/results.py` instead
- `core/preflight.py`: Use Protocol or `TYPE_CHECKING` properly
- `core/measurement_config.py`: Use Protocol for measure macro
- `core/schemas.py`: Inline `VALID_SHAPES` or move to core

### Priority 3: Merge ExperimentRunner into SessionManager

Consolidate the two session objects. `ExperimentRunner` appears to be the legacy version; `SessionManager` is the modern one with calibration store support.

### Priority 4: Extract Mixer Calibration from Hardware Controller

Move the mixer calibration orchestration logic from `hardware/controller.py` into `calibration/mixer_calibration.py`. The controller should expose a low-level calibration primitive; the calibration layer should handle the workflow.

### Priority 5: Move `PulseOp` to Pulses Package

`analysis.pulseOp.PulseOp` is a pulse analysis utility, not a general analysis tool. Moving it to `pulses/pulse_op.py` eliminates the pulses↔analysis cycle.

---

## Appendix: Tooling & Reproduction

### Scripts Created

| Script | Purpose | Run Command |
|--------|---------|-------------|
| `tools/analyze_imports.py` | AST-based import analysis, cycle detection, centrality metrics | `python tools/analyze_imports.py` |
| `tools/generate_codebase_graphs.py` | SVG diagram generation from analysis JSON | `python tools/generate_codebase_graphs.py` |

### Output Files

| Path | Type | Purpose |
|------|------|---------|
| `docs/codebase_graph_survey.md` | Markdown | This report |
| `docs/architecture/package_dependency_graph.svg` | SVG | Full package dependency graph |
| `docs/architecture/workflow_dependency_graph.svg` | SVG | Focused scientific workflow graph |
| `docs/architecture/class_relationships.svg` | SVG | Key class UML-style diagram |
| `docs/architecture/experiment_flow.svg` | SVG | Experiment lifecycle flow |
| `docs/architecture/package_dependencies.json` | JSON | Package-level adjacency list |
| `docs/architecture/centrality_metrics.json` | JSON | Centrality rankings |
| `docs/architecture/cycle_report.json` | JSON | All cycles + layer violations |
| `docs/architecture/module_edges.json` | JSON | Full module-level edge list |

### External Dependencies Detected (60 packages)

The codebase depends on: numpy, scipy, matplotlib, plotly, qm (Quantum Machines SDK), qutip, pydantic, pandas, PyQt5, jax, cupy, skopt, qcodes, grpclib, octave_sdk, instrumentserver, tqdm, yaml, and others.

### Methodology

1. All 183 `.py` files under `qubox_v2_legacy/` were parsed using Python's `ast` module
2. Import statements (both absolute and relative) were resolved to dotted module names
3. Module-level imports were aggregated to package-level dependency edges
4. Cycles were detected using DFS-based enumeration (up to length 10)
5. Centrality was computed as in-degree + out-degree at both module and package levels
6. Layer violations were identified by comparing source/target layer numbers
7. SVG diagrams were generated using raw SVG markup (no external tools required)
