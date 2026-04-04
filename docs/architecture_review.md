# Comprehensive Structural Survey — qubox_v2

> **Historical document (2026-03-02).** This surveys the `qubox_v2_legacy`
> codebase which has since been fully eliminated and merged into `qubox`.
> For the current architecture, see [API Reference](../API_REFERENCE.md)
> and [Architecture — Package Map](../site_docs/architecture/package-map.md).

**Date**: 2026-03-02  
**Scope**: Full read-only analysis of the `qubox_v2_legacy` repository  
**Version**: qubox_v2_legacy 2.0.0

---

## Table of Contents

1. [High-Level Architecture Overview](#1-high-level-architecture-overview)
2. [Experiment Lifecycle Breakdown](#2-experiment-lifecycle-breakdown)
3. [Data Flow Analysis](#3-data-flow-analysis)
4. [Analysis and Fitting Architecture](#4-analysis-and-fitting-architecture)
5. [Calibration and Patch Logic Review](#5-calibration-and-patch-logic-review)
6. [Bug Risk Assessment (Ranked)](#6-bug-risk-assessment-ranked)
7. [Architectural Inconveniences](#7-architectural-inconveniences)
8. [Consistency Audit](#8-consistency-audit)
9. [Strategic Recommendations](#9-strategic-recommendations)

---

## 1. High-Level Architecture Overview

### 1.1 Directory Structure Map

```
qubox_v2_legacy/
├── core/                  # Foundation: config models, identity, bindings, persistence, errors, logging
├── hardware/              # QM connection, config engine, program runner, queue manager
├── devices/               # External instrument management, sample registry, context resolver
├── pulses/                # Pulse factory, operation manager, registry, waveform generators
├── programs/              # QUA program builders, macros (measureMacro, sequenceMacros), circuit runner
│   ├── builders/          # Stateless factory functions per experiment category
│   └── macros/            # Stateful QUA statement helpers
├── experiments/           # Experiment classes, session manager, result types
│   ├── calibration/       # Gate calibration, readout optimization, reset benchmarks
│   ├── cavity/            # Fock-state, storage experiments
│   ├── spectroscopy/      # Qubit and resonator spectroscopy
│   ├── time_domain/       # Rabi, T1, T2, chevrons
│   ├── tomography/        # Qubit/Fock/Wigner state tomography
│   └── spa/               # SPA flux optimization
├── analysis/              # Fitting engine, models, post-processing, IQ discrimination, metrics
├── calibration/           # CalibrationStore (JSON persistence), orchestrator, patch rules, contracts
├── gates/                 # Gate algebra: models (unitary), hardware (OPX pulse gen), noise, caching
│   ├── models/            # Pure mathematical gate representations
│   └── hardware/          # OPX+-specific gate implementations
├── compile/               # Gate sequence optimization: ansatz, evaluators, structure search, GPU
├── simulation/            # QuTiP-based cQED simulation: Hamiltonian, drives, solver
├── optimization/          # General-purpose optimizers: scipy, CMA-ES, SPSA, Adam, Bayesian
├── autotune/              # Autonomous calibration pipelines
├── verification/          # Schema checks, waveform regression, persistence verification
├── tools/                 # Waveform generators, utility scripts
├── gui/                   # PyQt5 live experiment runner (optional)
├── migration/             # Schema migration entry point (references tools/ scripts)
├── compat/                # Backward compatibility (empty)
├── examples/              # Session startup demo
├── tests/                 # Unit tests (~25 test cases total)
└── docs/                  # Internal architecture/API reference
```

### 1.2 Module Dependency Graph (Logical)

```
Layer 0: core (errors, types, logging, utils, config, persistence_policy)
    ↓
Layer 1: core (experiment_context, session_state, schemas, protocols, bindings, hardware_definition)
    ↓
Layer 2: hardware (config_engine, controller, program_runner, queue_manager)
         devices  (device_manager, sample_registry, context_resolver)
         pulses   (factory, manager, registry, waveforms, integration_weights)
    ↓
Layer 3: programs (builders/*, macros/measure, macros/sequence, circuit_runner, gate_tuning)
    ↓
Layer 4: experiments (experiment_base, session, result, configs, config_builder)
         experiments/* (all experiment implementations)
    ↓
Layer 5: analysis (output, fitting, models, cQED_models, algorithms, analysis_tools, post_process, metrics)
         calibration (store, orchestrator, patch_rules, contracts, models, transitions, history)
    ↓
Layer 6: gates (models/*, hardware/*, gate, sequence, fidelity, noise, cache, liouville)
         compile (ansatz, evaluators, objectives, optimizers, structure_search, templates, gpu_*)
         simulation (cQED, hamiltonian_builder, drive_builder, solver)
    ↓
Layer 7: optimization (smooth_opt, stochastic_opt, bayesian)
         autotune (run_post_cavity_autotune_v1_1)
         verification (schema_checks, waveform_regression, persistence_verifier)
         gui, tools, examples
```

**Notable cross-layer dependencies:**
- `core/bindings.py` references `analysis/cQED_attributes` (guarded by `TYPE_CHECKING`)
- `core/artifacts.py` references `experiments/session` (guarded by `TYPE_CHECKING`)
- `calibration/orchestrator.py` directly imports `programs/macros/measure` (measureMacro singleton)
- `autotune` module directly mutates both `cQED_attributes` and `CalibrationStore` — a dual write path

### 1.3 Core Abstractions

| Abstraction | Module | Role |
|---|---|---|
| `ExperimentContext` | `core/experiment_context` | Frozen identity: sample, cooldown, wiring rev, config hash |
| `SessionState` | `core/session_state` | Frozen config snapshot with build-hash provenance |
| `HardwareConfig` | `core/config` | Pydantic v2 model for `hardware.json` |
| `ExperimentBindings` | `core/bindings` | Named channel binding collection: qubit + readout + storage |
| `ChannelRef` | `core/bindings` | Stable physical hardware port identity |
| `ReadoutHandle` | `core/bindings` | Immutable measurement handle (v2.1 API) |
| `FrequencyPlan` | `core/bindings` | Immutable frequency plan; atomic `apply(hw)` |
| `ExperimentBase` | `experiments/experiment_base` | Abstract base: `_build_impl()` → `build_program()` → `run()` → `analyze()` |
| `SessionManager` | `experiments/session` | Central service container: hardware + runner + pulses + calibration |
| `ProgramBuildResult` | `experiments/result` | Frozen build provenance snapshot |
| `RunResult` | `hardware/program_runner` | Raw execution result (output + mode + metadata) |
| `AnalysisResult` | `experiments/result` | Processed data + fits + metrics |
| `Output` | `analysis/output` | `dict` subclass — universal data container |
| `CalibrationStore` | `calibration/store` | JSON-backed typed persistence with atomic writes |
| `CalibrationData` | `calibration/models` | Pydantic root model for `calibration.json` |
| `CalibrationOrchestrator` | `calibration/orchestrator` | run→analyze→patch→apply lifecycle manager |
| `Patch` / `UpdateOp` | `calibration/contracts` | Ordered mutation list + op dispatch |
| `PulseOperationManager` | `pulses/manager` | Dual-store pulse/waveform/weight registry (2490 lines) |
| `PulseFactory` | `pulses/factory` | Declarative pulse spec → waveform compiler |
| `ConfigEngine` | `hardware/config_engine` | 5-layer config merge system |
| `HardwareController` | `hardware/controller` | QM connection lifecycle + frequency/LO control |
| `ProgramRunner` | `hardware/program_runner` | QUA program execution and simulation |
| `measureMacro` | `programs/macros/measure` | Measurement singleton — state, weights, discrimination |
| `GateModel` / `GateHardware` | `gates/` | Pure math + OPX pulse generation (composition pattern) |
| `circuitQED` | `simulation/cQED` | QuTiP cavity-transmon simulator |

### 1.4 Control Flow Between Modules

```
User (Notebook)
  → SessionManager.open(config_dir)
      → ConfigEngine.load_hardware() → HardwareConfig
      → PulseFactory.register_all(PulseOperationManager)
      → ConfigEngine.merge_pulses(POM) → QM config dict
      → HardwareController.open_qm(config)
      → CalibrationStore(calibration.json)
      → cQED_attributes.load()
  → Experiment(ctx=session)
      → experiment.run(**params)
          → ExperimentBase.build_program()
              → resolve_param() / resolve_override_or_attr()
              → builders.some_experiment() → QUA program
          → ProgramRunner.run_program(prog, n_total, processors)
              → QM execute → fetch → proc pipeline → Output
          → RunResult
      → experiment.analyze(result, update_calibration=False)
          → Signal processing (project, normalize, demod)
          → generalized_fit() → FitResult
          → AnalysisResult
      → [optional] guarded_calibration_commit()
          → CalibrationStore.set_*()
          → CalibrationStore.save() (atomic JSON write)
  → ArtifactManager.save_*(...)
```

---

## 2. Experiment Lifecycle Breakdown

### 2.1 Step-by-Step Lifecycle (Canonical Single-Program Experiment)

#### Step 1: Instantiation

```python
exp = T1Relaxation(ctx=session_manager)
```

The constructor (`ExperimentBase.__init__`) stores only a reference to `_ctx`. No hardware interaction, no parameter resolution. Experiments are **stateless singletons** scoped to a session context.

#### Step 2: Parameter Resolution

Inside `build_program()` → `_build_impl()`:

```python
# 4-level priority chain:
resolve_param("delay_max", override=user_value, default=40_000)
# Priority: explicit override → CalibrationStore value → default → error

# 2-level fallback:
resolve_override_or_attr("qb_el", override=user_value)
# Priority: explicit override → cQED_attributes fallback
```

Parameter sources are recorded in `_param_provenance` for debugging.

#### Step 3: Hardware Configuration Access

Experiments access hardware through `self._ctx` (SessionManager) properties:
- `self.hw` → `HardwareController` — live element frequency/LO control
- `self.attr` → `cQED_attributes` — element names, frequencies, coherence times
- `self.pulse_mgr` → `PulseOperationManager` — pulse definitions
- `self.calibration_store` → `CalibrationStore` — typed calibration data
- `self.device_manager` → `DeviceManager` — external instruments (optional)

#### Step 4: Pulse Program Construction

```python
# Inside _build_impl():
from qubox_v2_legacy.programs import api as cQED_programs

prog = cQED_programs.t1_relaxation(
    qb_el=self.attr.qb_el,
    delays=delay_array,
    n_avg=n_avg,
    # ... other params
)
```

Builder functions in `programs/builders/*.py` construct QUA programs using the QM SDK's `program()` context manager, `declare()`, `for_()`, `play()`, `measure()`, `stream_processing()`.

#### Step 5: Execution

```python
# ExperimentBase.build_program() creates ProgramBuildResult, then:
result = self.run_program(prog, n_total, processors=build_result.processors)
```

`ProgramRunner.run_program()`:
1. Calls `ConfigEngine.build_qm_config()` to merge all layers
2. Opens/re-uses the QM connection
3. Submits the QUA program via `qm.execute()`
4. Monitors progress via `IterationHandle` with a `tqdm` progress bar
5. Fetches results and applies the processor pipeline to produce an `Output`
6. Returns `RunResult(mode, output, metadata)`

#### Step 6: Raw Data Collection

Data arrives as named streams in `Output` (a `dict` subclass):
- Raw IQ pairs: `I`, `Q` (or `Ig`, `Qg`, `Ie`, `Qe` for discrimination)
- Sweep axes: `delays`, `frequencies`, `gains`
- Status signals: `n`, `iteration`

#### Step 7: Post-Processing

The **processor pipeline** (registered during `build_program()`) transforms `Output` in-place:

1. `proc_default` → Combines `I + 1jQ` → complex `S`, computes `Phases`, `uPhases`, deletes raw I/Q keys
2. `qubit_proc` → Applies affine normalization: `S` → `States` using calibrated g/e centroids
3. `ro_state_correct_proc` → Applies $\Lambda^{-1}$ confusion matrix correction
4. `proc_magnitude` → Computes `|S|` for spectroscopy experiments
5. `proc_attach(key, val)` → Attaches sweep axes to output

#### Step 8: Analysis

```python
analysis = exp.analyze(result, update_calibration=False)
```

Typical analysis flow:
1. Extract processed data: `S = output.extract("S")`
2. Apply domain-specific transforms: `project_complex_to_line_real(S)` for time-domain
3. Construct initial guess: heuristic-based (e.g., `T1 ≈ data_span/3`)
4. Fit model: `fit_and_wrap(x, y, T1_relaxation_model, p0)` → `FitResult`
5. Extract metrics: `T1_us = fit.params["T1"] * 1e6`
6. Return `AnalysisResult.from_run(result, fit=fit, metrics=metrics_dict)`

#### Step 9: Calibration Update (Optional)

```python
# Two-phase commit via guarded_calibration_commit():
self.guarded_calibration_commit(
    analysis=analysis,
    run_result=result,
    calibration_tag="t1_relaxation",
    require_fit=True,
    min_r2=0.5,
    required_metrics={"T1_us": (0.1, 1000.0)},
    apply_update=lambda: self.calibration_store.set_coherence(
        self.attr.qb_el, T1=fit.params["T1"]
    ),
)
```

Phase 1: Always persists the experiment artifact.  
Phase 2: Validates quality gates (fit succeeded, R² threshold, metric bounds) → conditionally applies the calibration update via the `apply_update` callable.

In **strict mode** (`allow_inline_mutations=False`), mutations are deferred as `proposed_patch_ops` in metadata for later replay by `CalibrationOrchestrator`.

#### Step 10: Artifact Persistence

```python
ArtifactManager(experiment_path, build_hash).save_artifact("t1_result", data)
Output.save(path)  # → .npz (arrays) + .meta.json (scalars)
```

`ArtifactManager` uses the `SessionState.build_hash` (SHA-256 of config files) as the storage key, ensuring reproducibility across sessions.

### 2.2 Flow Diagram (Pseudocode)

```
INSTANTIATE:
    exp = SomeExperiment(session_manager)

BUILD:
    build_result = exp.build_program(**user_params)
        params = resolve_param(key, override, default) for each knob
        qua_prog = cQED_programs.builder_fn(elements, sweeps, n_avg, ...)
        hw.set_element_fq(el, resolved_freq) for each element
        return ProgramBuildResult(prog, processors, frequencies, provenance)

RUN:
    run_result = exp.run_program(prog, n_total, processors)
        config_dict = config_engine.build_qm_config()
        job = qm.execute(prog)
        wait_for_completion(job, n_total)
        raw_output = job.result_handles.fetch_all()
        for proc in processors:
            proc(raw_output)
        return RunResult(output=raw_output)

ANALYZE:
    analysis = exp.analyze(run_result, update_calibration)
        data = extract_and_transform(run_result.output)
        fit = fit_and_wrap(x, y, model, p0)
        metrics = compute_metrics(fit)
        if update_calibration:
            guarded_calibration_commit(analysis, fit, metrics)
        return AnalysisResult(data, fit, metrics)

PERSIST:
    artifact_manager.save_artifact(name, data)
    output.save(path)
```

### 2.3 Non-Canonical Experiments

**8 experiments (~28%) bypass the canonical lifecycle:**

| Experiment | Deviation |
|---|---|
| `QubitSpectroscopyCoarse` | Multi-LO segment loop; `_build_impl()` raises `NotImplementedError` |
| `ReadoutFrequencyOptimization` | Multi-program fidelity sweep |
| `CalibrateReadoutFull` | Multi-stage pipeline; `run()` returns `dict` not `RunResult` |
| `ReadoutAmpLenOpt` | 2D sweep orchestrator; `run()` returns `Output` |
| `RandomizedBenchmarking` | Batched Clifford sequence programs |
| `PulseTrainCalibration` | Multi-prep tomography orchestration |
| `SPAFluxOptimization` / `SPAFluxOptimization2` | DC/pump parameter sweeps with per-point runs |

These experiments construct their own `Output` objects ad-hoc, losing the provenance guarantees of `ProgramBuildResult`. There is no common interface for multi-program experiments — each re-invents its own orchestration loop.

---

## 3. Data Flow Analysis

### 3.1 IQ Data Origin and Transformation Pipeline

```
QUA program (OPX+ hardware)
  ↓ raw demodulated I/Q streams per element
ProgramRunner collects into Output dict
  ↓
proc_default (post_process.py)
  ↓ S = I + 1jQ, Phases = angle(S), uPhases = unwrap(Phases)
  ↓ original I/Q keys DELETED from Output
  ↓
[Spectroscopy path]:
  proc_magnitude → |S| = sqrt(I² + Q²)
  ↓
[Time-domain path]:
  project_complex_to_line_real(S) → PCA projection onto principal axis
  ↓
[Discrimination path]:
  two_state_discriminator(Sg, Se) →
    estimate_intrinsic_sigmas_mog() → EM-based 2-component Gaussian mixture on optimal axis
    optimal_threshold_empirical() → sweep-based threshold on rotated I
    ↓ angle, threshold, fidelity_matrix, affine_normalizer
  ↓
  qubit_proc → affine normalization: S → States ∈ [-1, +1]
  ↓
  ro_state_correct_proc → Λ⁻¹ confusion matrix correction → corrected P_e
```

### 3.2 Metrics Extraction

Metrics are extracted from `FitResult.params` within each experiment's `analyze()` method:

| Experiment | Key Metrics | Source |
|---|---|---|
| `ResonatorSpectroscopy` | `f0`, `kappa` | `resonator_spec_model` fit |
| `QubitSpectroscopy` | `f0`, `gamma` | `qubit_spec_model` fit |
| `TemporalRabi` / `PowerRabi` | `f_Rabi`, `g_pi`, `T_decay` | `temporal_rabi_model` / `power_rabi_model` fit |
| `T1Relaxation` | `T1`, `T1_us` | `T1_relaxation_model` fit |
| `T2Ramsey` | `T2`, `T2_star_us`, `f_det` | `T2_ramsey_model` fit |
| `ReadoutGEDiscrimination` | `fidelity`, `angle`, `threshold` | `two_state_discriminator` statistical analysis |
| `ReadoutButterflyMeasurement` | `F`, `Q`, `V`, `t01`, `t10` | `butterfly_metrics` statistical analysis |
| `StorageChiRamsey` | `chi`, `nbar` | `chi_ramsey_model` fit |

### 3.3 Storage of Fitted Parameters

Fitted parameters are stored at three levels:

1. **`AnalysisResult.fits`** — in-memory `dict[str, FitResult]` with full parameter values, uncertainties, R², and residuals
2. **`CalibrationStore`** (`calibration.json`) — persistent typed storage via patch rules or `guarded_calibration_commit`
3. **`cQED_attributes`** (`cqed_params.json`) — legacy in-memory snapshot; directly mutated by some experiments and the autotune module

### 3.4 Calibration JSON Update Propagation

```
FitResult.params["T1"]
  → guarded_calibration_commit(apply_update=lambda: store.set_coherence(el, T1=value))
    → CalibrationStore._data.cqed_params[alias].T1 = value
    → CalibrationStore._touch() → auto_save → _atomic_write()
      → tempfile.mkstemp() → json.dump() → os.replace()
        → calibration.json on disk
```

Alternatively, via the orchestrator:
```
CalibrationResult(params={"T1": value})
  → T1Rule.__call__(result) → Patch([UpdateOp("SetCalibration", path="cqed_params.transmon.T1", value=...)])
    → orchestrator.apply_patch() → _set_calibration_path()
      → CalibrationStore.set_coherence(...)
      → CalibrationStore.save()
```

### 3.5 Data Ownership Ambiguities

| Concern | Detail |
|---|---|
| **Dual state stores** | `cQED_attributes` (in-memory, from `cqed_params.json`) and `CalibrationStore` (JSON-backed, from `calibration.json`) both hold frequencies, coherence times, and pulse parameters. They can diverge if one is updated without the other. |
| **`measureMacro` singleton state** | Discrimination parameters (angle, threshold, fidelity matrix) live in class-level variables on `measureMacro`. These are also stored in `CalibrationStore.discrimination`. Synchronization is manual via `sync_from_calibration()`. |
| **Mutable `Output`** | `Output` is a mutable `dict` subclass. Processors modify it in-place (including deleting keys). If a reference is shared, downstream consumers see mutations from upstream processors. |
| **Hidden dependency on import order** | `qubox_v2_legacy/__init__.py` calls `configure_global_logging(level="INFO")` at import time — a global side effect that affects all loggers before any user configuration. |

---

## 4. Analysis and Fitting Architecture

### 4.1 Model Selection

Models are **manually selected** per experiment — there is no auto-model-selection mechanism. Each experiment's `analyze()` method calls `generalized_fit()` (or `fit_and_wrap()`) with a hardcoded model function passed as a first-class callable.

**Available model catalogues:**

| Module | Models | Domain |
|---|---|---|
| `analysis/models.py` | `lorentzian`, `gaussian`, `voigt`, `linear`, `exponential`, `polynomial` | Generic |
| `analysis/cQED_models.py` | `resonator_spec`, `qubit_spec`, `temporal_rabi`, `power_rabi`, `T1_relaxation`, `T2_ramsey`, `T2_echo`, `chi_ramsey`, `kerr_ramsey`, `num_splitting`, `rb_survival`, `qubit_pulse_train`, `coherent_population`, `poisson_with_offset` | cQED physics |
| `analysis/pulse_train_models.py` | `model_base`, `model_with_zeta`, `model_with_zeta_and_relax` | Pulse-train tomography |

### 4.2 Initial Guess Determination

Each fitting callsite constructs `p0` heuristically:

| Experiment Type | p0 Strategy |
|---|---|
| Spectroscopy | `f0 ≈ freq[argmin(S)]`, `A ≈ max−min`, `offset ≈ mean` |
| Rabi | `g_pi ≈ gain at minimum`, `A ≈ (max−min)/2` |
| T1/T2 | `T ≈ data_span/3`, `A ≈ signal range`, `offset ≈ mean` |
| Chi-Ramsey | `chi` from FFT peak detection |
| Pulse-train | `[0, 0, 0]` (small error assumption) |

The `generalized_fit` retry mechanism generates perturbations when the initial guess fails: midpoint of bounds, random jitter at `scale=0.5`, up to 8 retries with deduplication.

### 4.3 Silent Fitting Failure Points

1. **`generalized_fit()` returns `(None, None)` on total failure** — no exception raised. All callers must explicitly check for `None`.

2. **`fit_and_wrap()` returns `FitResult(params={}, metadata={"failed": True})`** — downstream code checking `fit.params["key"]` will raise `KeyError`.

3. **`calibration_algorithms.fit_number_splitting()` and `fit_chi_ramsey()`** silently return initial guesses on fit failure — no warning, no flag. The returned values are indistinguishable from successful fits without checking R².

4. **`T2_ramsey_model` uses `np.abs(T2) + 1e-15`** — silently prevents division-by-zero but allows the optimizer to explore physically meaningless negative-T2 solutions, potentially converging to wrong parameter values.

5. **`display_fock_populations` assumes `global_opt=True` always succeeds** — if `generalized_fit` returns `None`, accessing `pois_fit_res[0]` would raise `TypeError`.

6. **`proc_default` catches demodulation exceptions and prints a warning but continues** — downstream code may find missing keys in `Output`.

### 4.4 Model Assumption Enforcement

Model assumptions are **not systematically enforced**:

- No automatic checking that fitted parameters are physically plausible (e.g., negative T1, frequencies outside IF bandwidth)
- Bounds are set ad-hoc per callsite — there is no centralized parameter-bounds registry
- The stretched exponential exponent `n` in `T2_ramsey_model` / `T2_echo_model` is a free parameter with no upper bound, allowing unphysical fits

### 4.5 Duplication in Fitting/Model Logic

| Duplicated Item | Location 1 | Location 2 |
|---|---|---|
| Lorentzian resonance model | `models.lorentzian_model` | `cQED_models.resonator_spec_model` |
| Exponential decay model | `models.exponential_model` | `cQED_models.T1_relaxation_model` |
| Poisson+offset model | `cQED_models.poisson_with_offset_model` | Inline in `cQED_plottings.display_fock_populations` |
| Pulse-train fitting | `calibration_algorithms.fit_pulse_train` (simple Levenberg-Marquardt) | `pulse_train_models.fit_pulse_train_model` (DE+LS global) |
| `scipy.optimize.minimize` wrapper | `compile/optimizers.py` (multi-restart + early stop) | `optimization/smooth_opt.py` (thin wrapper) |

---

## 5. Calibration and Patch Logic Review

### 5.1 Parameter Resolution Hierarchy

The `CalibrationStore` resolves parameters through a 3-level hierarchy:

1. **`cqed_params` dict** (primary) — checked first via alias-resolved key
2. **Legacy `frequencies` / `coherence` dicts** — fallback when `cqed_params` has no entry
3. **`alias_index`** — translates human names (e.g., `"transmon"`) to physical channel IDs before any lookup

At the experiment level, `resolve_param()` adds two more levels atop the store:

4. **Explicit override** (user-supplied argument) — highest priority
5. **CalibrationStore value** — next priority
6. **Default value** — lowest priority
7. **Error** — if none found and no default

### 5.2 JSON Read/Write Safety

**Atomic writes**: `CalibrationStore._atomic_write()` uses `tempfile.mkstemp()` in the same directory, then `os.replace()` — atomic on both POSIX and Windows NTFS (same volume). Failure cleanup is handled via `BaseException` exception handler.

**Serialization safety**:
- `sanitize_mapping_for_json()` strips oversized arrays (>8192 elements) and raw-shot data
- `exclude_none=True` prevents null pollution
- `allow_nan=False` is used by the mixer calibration DB
- **Risk**: `default=str` in `json.dump` silently stringifies any un-serializable type, potentially producing valid JSON with wrong data types on reload

**No file locking**: There is no advisory file lock (`fcntl.flock` / `msvcrt.locking`). Two concurrent processes writing the same `calibration.json` won't corrupt the file (last-writer-wins via `os.replace`), but one write will be silently overwritten.

### 5.3 Inconsistent State Risks

| Risk | Severity | Detail |
|---|---|---|
| **Partial patch application** | Medium | `apply_patch()` iterates ops sequentially. If an op raises mid-iteration, preceding ops have already mutated in-memory state but `save()` hasn't run. No rollback mechanism exists. |
| **In-memory ↔ disk drift** | Medium | `CalibrationStore` loads once on init and operates on in-memory `_data`. External file modifications are invisible until `reload()` is called. |
| **`measureMacro` sync failure** | Low | Post-patch sync calls are wrapped in try/except. Failures are logged but execution continues — CalibrationStore is committed but live runtime state may be stale. |
| **History snapshot skips migration** | Low | `history.load_snapshot()` doesn't run `_migrate_legacy_to_cqed_params()`, so loading old v5.0.0 snapshots would have empty `cqed_params`. |
| **Generic fallback in `_set_calibration_path`** | Low | For unrecognized dotted paths, raw dict mutation bypasses Pydantic type validation. |

### 5.4 Race Condition Scenarios

| Scenario | Impact |
|---|---|
| Long-running notebook session + external process writing calibration | In-memory store becomes stale; `auto_save=True` mitigates writes but not reads |
| Two notebooks sharing the same `calibration.json` | Last-writer-wins; no merge strategy |
| Cooldown mismatch on load | Warn-only (never raises) — stale calibrations could be silently applied to a new cooldown |

### 5.5 Patch Rule System

Each rule is a `@dataclass` callable mapping `CalibrationResult.kind` → `Patch`:

| Rule | Triggered by | Key Behavior |
|---|---|---|
| `PiAmpRule` | `"pi_amp"` | Reads current ref amplitude, multiplies by fitted `g_pi`, patches both store and live pulse |
| `T1Rule` | `"t1"` | Writes `T1`, `T1_us`, `qb_therm_clks`; has **unit heuristic** (if T1 > 1e-3, assumes nanoseconds) |
| `T2RamseyRule` | `"t2_ramsey"` | Writes `T2_ramsey`, `T2_star_us`, optional corrected qubit frequency |
| `FrequencyRule` | configurable | General-purpose spectroscopy rule (instantiated per element) |
| `DragAlphaRule` | `"drag_alpha"` | Patches DRAG coefficient on target reference pulse only |
| `DiscriminationRule` | `"ReadoutGEDiscrimination"` | Patches angle, threshold, fidelity, sigma, centroids |
| `WeightRegistrationRule` | any | Promotes `proposed_patch_ops` from metadata into real ops |
| `PulseTrainRule` | `"pulse_train"` | Patches corrected amplitude + phase offset on reference pulse |

**Quality gating**: The orchestrator only applies patches when `CalibrationResult.passed == True` (which itself requires `quality["passed"]` and optionally `r_squared >= 0.5`).

---

## 6. Bug Risk Assessment (Ranked)

### HIGH RISK

#### H1. Silent Fitting Failures Propagate as Valid Calibration Updates

**Description**: `generalized_fit()` returns `(None, None)` on failure without raising an exception. Several callsites in `calibration_algorithms.py` (`fit_number_splitting`, `fit_chi_ramsey`) silently return their initial guesses when the fit fails, with no warning flag. If these values are subsequently used for calibration patches, incorrect parameters will be committed to `calibration.json`.

**Why it is dangerous**: Incorrect chi, T1, or frequency values written to calibration will corrupt all subsequent experiments until manually detected and corrected. The failure is invisible at the commit point.

**Where it occurs**: `analysis/calibration_algorithms.py` (lines in `fit_number_splitting`, `fit_chi_ramsey`), `analysis/fitting.py` (`generalized_fit` return path).

**Suggested mitigation**: All fitting functions should return a typed result object with an explicit `success` flag. `CalibrationStore` setters should require a `FitResult` source with R² above a minimum threshold.

---

#### H2. measureMacro Singleton — Global Mutable State Without Thread Safety

**Description**: `measureMacro` in `programs/macros/measure.py` uses class-level mutable variables for all discrimination parameters, weights, and demod configuration. There is no instance creation — all state is shared globally.

**Why it is dangerous**: Two experiments cannot configure different readout parameters simultaneously. Any exception during `push_settings()`/`restore_settings()` can leave the stack in a corrupted state. The `analyze()` method of `ReadoutGEDiscrimination` mutates `measureMacro` as a side effect, meaning the analysis of one experiment modifies the runtime configuration of all subsequent measurements.

**Where it occurs**: `programs/macros/measure.py` (entire module), `experiments/calibration/readout.py` (`ReadoutGEDiscrimination.analyze()`).

**Suggested mitigation**: Refactor `measureMacro` to an instance-based design. The v2.1 `ReadoutHandle` and `emit_measurement()` API is the correct replacement — complete the migration.

---

#### H3. Dual State Stores (cQED_attributes + CalibrationStore) Can Diverge

**Description**: Frequencies, coherence times, and pulse parameters exist simultaneously in `cQED_attributes` (in-memory, from `cqed_params.json`) and `CalibrationStore` (JSON-backed, from `calibration.json`). The autotune module directly mutates `cQED_attributes` via `setattr(attr, key, value)`, bypassing CalibrationStore's typed API.

**Why it is dangerous**: Experiments use `self.attr` (cQED_attributes) for element names and frequency lookups, while calibration patches write to `CalibrationStore`. If the two stores diverge, an experiment may read stale parameters from one store while the other has updated values.

**Where it occurs**: `autotune/run_post_cavity_autotune_v1_1.py` (`_apply_attr_patch`), `experiments/experiment_base.py` (uses `self.attr`), `calibration/store.py` (writes to separate JSON).

**Suggested mitigation**: Eliminate the dual-store pattern. Make `CalibrationStore` the single source of truth and have `cQED_attributes` be a read-only projection of it.

---

#### H4. T1Rule Unit Heuristic — Threshold-Based Unit Guessing

**Description**: `T1Rule` in `calibration/patch_rules.py` uses the heuristic: if `T1 > 1e-3`, assume the value is in nanoseconds and multiply by 1e-9. This is fragile — a T1 of exactly 1 ms (1e-3 s) sits on the boundary.

**Why it is dangerous**: Results from experiments reporting T1 in seconds could be misinterpreted. The threshold is arbitrary and undocumented at the call sites. A microsecond-range T1 value (e.g., 1.5 × 10⁻³ from a short-lived element) would be incorrectly scaled down by 10⁹.

**Where it occurs**: `calibration/patch_rules.py` (T1Rule).

**Suggested mitigation**: Require units to be explicitly declared in `CalibrationResult.params` (e.g., `{"T1": {"value": 15.2, "unit": "us"}}`). Eliminate all heuristic unit conversion.

---

#### H5. Partial Patch Application Without Rollback

**Description**: `CalibrationOrchestrator.apply_patch()` iterates `UpdateOp` sequentially. If an op raises mid-iteration, preceding ops have already mutated in-memory `CalibrationStore` state, but `save()` hasn't run. There is no transaction or rollback mechanism.

**Why it is dangerous**: An exception during a multi-op patch (e.g., setting discrimination + weight registration + pulse recompile) leaves the in-memory store in an inconsistent state. Subsequent experiment reads see partially applied changes.

**Where it occurs**: `calibration/orchestrator.py` (`apply_patch` method).

**Suggested mitigation**: Implement a snapshot-restore mechanism: take a `model_dump()` snapshot before patch application, restore on any exception.

---

### MEDIUM RISK

#### M1. Confusion Between IF/LO/RF Frequencies Across Layers

**Description**: Multiple frequency-setting APIs coexist:
- `HardwareController.set_element_fq(el, rf_freq)` → computes IF = RF − LO
- `ConfigEngine.hw_set_element_intermediate_frequency(el, if_freq)` → sets IF directly
- `FrequencyPlan.apply(hw)` → sets IFs atomically
- Some experiments call `set_standard_frequencies()` directly from `cQED_attributes`

**Why it is dangerous**: Passing an IF frequency where an RF frequency is expected (or vice versa) silently produces wrong results. The ±500 MHz IF validation in `set_element_fq` catches some errors, but passing an RF frequency to `hw_set_element_intermediate_frequency` would not be validated.

**Where it occurs**: `hardware/controller.py`, `hardware/config_engine.py`, `core/bindings.py`, `experiments/*` (frequency-setting code in `_build_impl`).

**Suggested mitigation**: Introduce typed frequency wrappers (`RFFrequency`, `IFFrequency`, `LOFrequency`) that prevent accidental type confusion.

---

#### M2. Unit Convention Fragmentation (Hz vs rad/s)

**Description**: The simulation module uses angular frequency (rad/s, ℏ=1) while all other modules use Hz. There is no centralized unit conversion utility.

**Why it is dangerous**: Every boundary between simulation and the rest of the system requires a manual `* 2π` or `/ (2π)` conversion. A missing or double conversion would produce incorrect simulation results that might not be immediately obvious.

**Where it occurs**: `simulation/cQED.py` (rad/s), `gates/contexts.py` (Hz), `calibration/` (Hz), `autotune/` (Hz).

**Suggested mitigation**: Add explicit unit annotations or conversion functions. Consider a `Frequency` type that tracks its unit.

---

#### M3. `fock_resolved_power_rabi` QUA Variable Shadowing

**Description**: In `programs/builders/cavity.py`, `fock_resolved_power_rabi` declares `f = declare(int)` as a QUA variable, then reuses `f` as a Python loop variable in `for (f, disp_pulse) in zip(fock_ifs, disp_n_list)`. The Python integer from `zip` shadows the QUA `int` variable. `update_frequency` then receives the Python int rather than the QUA variable.

**Why it is dangerous**: This may work correctly if `update_frequency` accepts Python integers (which get implicitly converted), but the semantic mismatch is confusing and could break if the QUA SDK tightens type checking.

**Where it occurs**: `programs/builders/cavity.py` (`fock_resolved_power_rabi`).

**Suggested mitigation**: Rename the QUA variable to avoid name collision (e.g., `f_qua = declare(int)`).

---

#### M4. `storage_wigner_tomography` Operator Precedence Bug

**Description**: The line `c, s = ratio.real / norm, ratio.imag / norm if norm else (0.0, 0.0)` in `programs/builders/cavity.py` has a Python operator precedence issue. Due to how Python parses conditional expressions, this evaluates as `c = ratio.real / norm` and `s = (ratio.imag / norm if norm else (0.0, 0.0))`. The `if norm` guard only protects `s`, not `c`.

**Why it is dangerous**: A zero `norm` causes a division-by-zero for `c`, producing `inf` or `nan` in the displacement waveform.

**Where it occurs**: `programs/builders/cavity.py` (`storage_wigner_tomography`).

**Suggested mitigation**: Add parentheses: `c, s = (ratio.real / norm, ratio.imag / norm) if norm else (0.0, 0.0)`.

---

#### M5. `ProcessPoolExecutor` + Lambda Serialization in Structure Search

**Description**: `compile/structure_search.py` uses `ProcessPoolExecutor` for parallel beam search. `TemplateFactory` stores a `make` callable, which may be a lambda. Python's `pickle` cannot serialize lambdas.

**Why it is dangerous**: This is a latent bug — code works in single-process mode but fails at runtime when `parallel=True` is used with factory objects containing lambdas.

**Where it occurs**: `compile/structure_search.py` (beam search parallel evaluation).

**Suggested mitigation**: Require `make` functions to be module-level named functions, or use `cloudpickle` for serialization.

---

#### M6. Alias Resolution Substring Matching

**Description**: `CalibrationStore._infer_cqed_alias()` uses substring matching: names containing `"rr"` map to `"resonator"`. Short element names could trigger false positives (e.g., `"mirror"` contains `"rr"`).

**Where it occurs**: `calibration/store.py` (`_infer_cqed_alias`).

**Suggested mitigation**: Use word-boundary or exact-match patterns instead of substring search.

---

#### M7. Dual GPU Backends Without Mutual Exclusion

**Description**: `compile/gpu_accelerators.py` (JAX) and `compile/gpu_utils.py` (CuPy) can both be activated simultaneously. JAX monkey-patches evaluator functions while CuPy provides transfer wrappers.

**Why it is dangerous**: If both are active, JAX-patched functions may receive CuPy arrays (or vice versa), causing type errors or silent numerical errors.

**Where it occurs**: `compile/gpu_accelerators.py`, `compile/gpu_utils.py`.

**Suggested mitigation**: Add a mutex or runtime check that prevents both backends from being active simultaneously.

---

### LOW RISK

#### L1. `ConnectionError` Shadows Python Built-in

**Description**: `core/errors.py` defines `ConnectionError(QuboxError)` which shadows `builtins.ConnectionError`.

**Where**: `core/errors.py`. **Mitigation**: Rename to `HardwareConnectionError`.

---

#### L2. Global Logging Side Effect on Import

**Description**: `qubox_v2_legacy/__init__.py` calls `configure_global_logging(level="INFO")` at import time.

**Why**: Could surprise library consumers who have their own logging setup. **Mitigation**: Defer to explicit initialization.

---

#### L3. `default=str` in `json.dump` Silently Stringifies Unknown Types

**Description**: Several `json.dump` calls use `default=str`, which converts any un-serializable type to a string rather than raising.

**Where**: `calibration/store.py`, `core/artifacts.py`. **Mitigation**: Use a strict default handler that raises on unknown types.

---

#### L4. `DisplacementModel` LRU Cache Unbounded Growth

**Description**: `@functools.lru_cache` on matrix exponential keyed by `(alpha, n_max)`. Since `alpha` is a continuous complex value, cache hit rate is near zero in optimization loops, causing unbounded memory growth.

**Where**: `gates/models/displacement.py`. **Mitigation**: Use `maxsize` parameter or switch to a parameterized cache.

---

#### L5. `skopt_bo` Export is Dead Code

**Description**: `optimization/__init__.py` exports `skopt_bo` but the actual function is `bayesian_optimize`. This will raise `ImportError` at runtime.

**Where**: `optimization/__init__.py`. **Mitigation**: Fix the export name.

---

#### L6. Mixer Calibration DB Sanitization Masks Failures

**Description**: `_sanitize_calibration_db_file()` in `HardwareController` replaces NaN/Inf with 0.0 silently.

**Where**: `hardware/controller.py`. **Mitigation**: Log a warning when NaN/Inf is encountered.

---

#### L7. `randomized_benchmarking` Sentinel Collision Risk

**Description**: Auto-sentinel logic `if sentinel_gate is None: sentinel_gate = len(gate_list)` means the sentinel depends on gate list length, potentially colliding with valid gate indices.

**Where**: `programs/builders/calibration.py`. **Mitigation**: Use a dedicated sentinel value well outside the gate index range.

---

## 7. Architectural Inconveniences

### 7.1 Redundant Code

| Item | Locations | Impact |
|---|---|---|
| Lorentzian model | `models.py` + `cQED_models.py` | Divergent parameter names (`fwhm` vs `kappa`) |
| Exponential decay | `models.py` + `cQED_models.py` | Maintenance burden |
| Poisson model | `cQED_models.py` + inline in `cQED_plottings.py` | Inline copy misses bug fixes |
| Pulse-train fitting | `calibration_algorithms.py` + `pulse_train_models.py` | Two complexity levels, unclear which to use when |
| `scipy.optimize.minimize` wrapper | `compile/optimizers.py` + `optimization/smooth_opt.py` | Same library, different interfaces |
| `PulseOperationManager` + `PulseRegistry` | `pulses/manager.py` + `pulses/pulse_registry.py` | Parallel implementations with different reserved-name semantics |

### 7.2 Unintuitive Flow

| Issue | Detail |
|---|---|
| **Three measurement APIs** | `measureMacro.measure()`, `measure_with_binding()`, `emit_measurement()` coexist in the same codebase. Most builders use the singleton, while a few use the newer binding-based APIs. No clear migration path is enforced. |
| **Multi-program experiments bypass lifecycle** | 8 experiments raise `NotImplementedError` from `_build_impl()` and implement entirely custom run loops. The base class provides no framework for multi-program orchestration. |
| **ConfigEngine 5-layer merge** | The layered merge (hardware_base → extras → pulse_overlay → element_ops_overlay → runtime_overrides) is powerful but opaque. Debugging which layer overrides which requires understanding the merge order. |
| **Artifact persistence split** | Data is split between `.npz` (arrays) and `.meta.json` (scalars) by the persistence policy. The `dropped` fields are tracked in `_persistence` metadata. Reconstructing original data requires understanding both files plus the drop policy. |

### 7.3 Unclear Responsibilities

| Module | Issue |
|---|---|
| `analysis/analysis_tools.py` | "Swiss army knife" with 1011 lines covering IQ transforms, normalization, discrimination, posterior models, serialization, and probability computation. Should be split into focused modules. |
| `programs/macros/measure.py` | `measureMacro` is a measurement emitter, a discrimination parameter store, a weight manager, a post-selection policy holder, and a JSON persistence system. Too many responsibilities for a single class. |
| `experiments/session.py` | `SessionManager` (~1235 lines) is the service container for everything: hardware, pulses, calibration, devices, orchestrator. It's the "god object" of the system. |

### 7.4 Tight Coupling

| Coupling | Detail |
|---|---|
| `CalibrationOrchestrator` ↔ `measureMacro` | Orchestrator directly imports and mutates the measurement singleton during patch application |
| `autotune` ↔ `cQED_attributes` | Autotune mutates attributes via `setattr`, bypassing the calibration store |
| `ExperimentBase` ↔ `SessionManager` | Experiments access 7+ services through `self._ctx` property delegation |
| `core/bindings.py` ↔ `analysis/cQED_attributes` | Bindings layer imports cQED_attributes for backward compatibility |

### 7.5 Refactoring Opportunities

1. **Split `measureMacro`** into: (a) `MeasurementConfig` (parameters), (b) `MeasurementEmitter` (QUA code gen), (c) `DiscriminationState` (threshold/centroids)
2. **Introduce `MultiProgramExperiment` base class** with first-class support for multi-program loops, provenance chaining, and result aggregation
3. **Unify optimization stacks** — one optimizer module shared by `compile` and `optimization`
4. **Merge model catalogues** — one model per physics concept, parameterized by naming convention
5. **Extract `analysis_tools.py`** into `iq_processing.py`, `discrimination.py`, `posterior_models.py`, `serialization.py`

---

## 8. Consistency Audit

### 8.1 Do All Experiments Follow run → analyze → patch?

**No.** Three patterns exist:

| Pattern | Experiments | Fraction |
|---|---|---|
| Canonical (`build_program` → `run` → `analyze` → optional `guarded_calibration_commit`) | ~20 experiments | ~72% |
| Custom multi-program loop (bypasses `_build_impl`) | 8 experiments | ~28% |
| Configuration-only wrapper (delegates to another experiment) | `CalibrationReadoutFull` | ~3% |

The canonical pattern is well-defined and consistent. The multi-program experiments have ad-hoc implementations with no shared framework.

### 8.2 Do All Experiments Respect Calibration Override Rules?

**Mostly.** The `resolve_param()` 4-level chain and `resolve_override_or_attr()` 2-level chain are used consistently across canonical experiments. However:

- Different experiments use different resolution methods for the same parameter (e.g., `qb_therm_clks` uses `resolve_param()` in some and `resolve_override_or_attr()` in others)
- Multi-program experiments may resolve parameters outside the `build_program()` framework, bypassing provenance recording

### 8.3 Are Naming Conventions Consistent?

**Partially.**

| Convention | Consistency |
|---|---|
| Element names (`qb_el`, `ro_el`, `st_el`) | ✅ Consistent across all experiments |
| Frequency fields (`ro_fq`, `qb_fq`, `st_fq`) | ✅ Consistent |
| Pulse names (`ge_ref_r180`, `ef_ref_r90`, etc.) | ✅ Enforced by `transitions.py` canonical grammar |
| Model function names | ❌ Mixed: `T1_relaxation_model` vs `lorentzian_model` (underscore vs no-underscore prefix) |
| Result keys | ❌ Mixed: `"T1_us"` vs `"T2_star_us"` vs `"fidelity"` (no prefix convention for metrics) |
| Module naming | ❌ Mixed: `cQED_models.py` (camelCase prefix) vs `pulse_train_models.py` (snake_case) |
| Calibration kind strings | ❌ Mixed: `"t1"`, `"t2_ramsey"` (lowercase) vs `"ReadoutGEDiscrimination"` (PascalCase) |

### 8.4 Is Metric Reporting Uniform?

**No.** Each experiment defines its own metrics dict with ad-hoc keys:

| Experiment | Metric Keys Example |
|---|---|
| `T1Relaxation` | `{"T1_us": float, "offset": float}` |
| `T2Ramsey` | `{"T2_star_us": float, "f_det_MHz": float}` |
| `ResonatorSpectroscopy` | `{"f0_MHz": float, "kappa_kHz": float}` |
| `ReadoutGEDiscrimination` | `{"fidelity": float, "angle_deg": float, "threshold": float}` |
| `ReadoutButterflyMeasurement` | `{"F": float, "Q": float, "V": float}` |

There is no `MetricSpec` or typed metric registry. Units are encoded in key names (e.g., `_us`, `_MHz`, `_kHz`) rather than as structured metadata.

---

## 9. Strategic Recommendations

### 9.1 Structural Refactors

1. **Unify state stores**: Eliminate `cQED_attributes` as a separate entity. Make `CalibrationStore` the single source of truth, with `cQED_attributes` being a read-only view that refreshes from `CalibrationStore` on access. This eliminates the dual-store divergence risk (H3).

2. **Instance-based measurement**: Complete the migration from `measureMacro` singleton to instance-based `ReadoutHandle` + `emit_measurement()`. Add a deprecation layer that logs usage of the singleton API. Target: all builders use the new API within one release cycle.

3. **Multi-program experiment framework**: Introduce `MultiProgramExperiment(ExperimentBase)` with:
   - `build_programs()` → `list[ProgramBuildResult]`
   - `run_sequence(programs)` → `list[RunResult]`
   - `aggregate_results(results)` → `RunResult`
   - Migrate the 8 non-canonical experiments to this framework.

4. **Split analysis_tools.py**: Extract into focused modules: `iq_transforms.py`, `discrimination.py`, `posterior_models.py`, `normalization.py`.

5. **Consolidate optimization**: Create a single `qubox_v2_legacy.optim` module that both `compile` and general users consume. Eliminate the duplicate `scipy.optimize.minimize` wrappers.

6. **Merge pulse infrastructure**: Deprecate `PulseOperationManager` in favor of `PulseRegistry`. Provide an adapter for backward compatibility during migration.

### 9.2 API Improvements

1. **Typed fitting results**: Replace `(None, None)` return with a `FitOutcome` sum type:
   ```python
   @dataclass
   class FitSuccess:
       params: dict[str, float]
       covariance: np.ndarray
       r_squared: float
   
   @dataclass
   class FitFailure:
       reason: str
       last_params: dict[str, float] | None
   
   FitOutcome = FitSuccess | FitFailure
   ```

2. **Typed frequency wrappers**: `RFFrequency`, `IFFrequency`, `LOFrequency` newtype wrappers that prevent confusion between frequency types at the type level.

3. **Typed metric reporting**: Introduce `Metric(name, value, unit, source_experiment)` and a `MetricRegistry` that enforces consistent naming and unit conventions.

4. **Calibration units contract**: Require all calibration values to carry explicit units. Eliminate heuristic unit conversion (T1Rule).

5. **Session-scoped measurement config**: Replace the singleton `measureMacro` with a `MeasurementConfig` instance owned by `SessionManager`, passed explicitly to builders.

### 9.3 Validation Layers

1. **Pre-commit calibration validation**: Before `CalibrationStore.save()`, validate that all values are physically plausible (frequencies within hardware IF bandwidth, T1/T2 positive, amplitudes ≤ `MAX_AMPLITUDE`, etc.).

2. **Post-fit plausibility checks**: After `fit_and_wrap()`, automatically flag parameters outside expected physical ranges. This should be a configurable `FitValidator` that experiments can customize.

3. **Frequency-type guards**: Add runtime checks in `set_element_fq()` and `hw_set_element_intermediate_frequency()` that detect when a value is likely the wrong frequency type (e.g., IF > 500 MHz → probably RF).

4. **Patch preview and dry-run**: Make dry-run the default for `CalibrationOrchestrator.apply_patch()`. Require explicit confirmation for production patches.

5. **Cross-store consistency check**: Add a `verify_consistency()` method that compares `cQED_attributes`, `CalibrationStore`, and `measureMacro` for divergent values. Run automatically after each calibration update.

### 9.4 Testing Strategy Improvements

The current test suite covers only **calibration parameter plumbing** (~25 test cases). The following areas have zero coverage and should be prioritized:

| Priority | Area | Suggested Tests |
|---|---|---|
| **P0** | Fitting engine | Test `generalized_fit()` and `fit_and_wrap()` with known functions, ensure failure returns are correct, test retry mechanism |
| **P0** | CalibrationStore | Round-trip JSON load/save, migration, atomic write under concurrent access, alias resolution |
| **P0** | Patch rules | Test each rule with mock `CalibrationResult`, verify correct `UpdateOp` generation |
| **P1** | Gate models | Verify unitarity of all gate models, test known special cases (identity, Pauli gates), Kraus operator CPTP property |
| **P1** | Compile evaluators | Test `compose_unitary()` against known gate sequences, verify fidelity computation |
| **P1** | Post-processing | Test `proc_default`, `qubit_proc`, `ro_state_correct_proc` with synthetic IQ data |
| **P2** | Simulation | Test Hamiltonian construction, verify drives match analytical forms, solver convergence |
| **P2** | PulseFactory | Verify waveform shapes against analytical expectations, test constraint enforcement |
| **P3** | Integration | End-to-end test: build → simulate → analyze for one canonical experiment |

**Infrastructure needs:**
- Add `pytest` configuration to `pyproject.toml`
- Set up CI/CD (GitHub Actions) with the test suite
- Add property-based testing (`hypothesis`) for numerical components
- Add snapshot testing for waveform regression

### 9.5 Schema Hardening Suggestions

1. **Schema version registry**: Create a centralized `SCHEMA_VERSIONS.md` documenting all schema families (hardware, calibration, pulse_specs, measureConfig, devices) with their version history and migration paths.

2. **Strict schema validation on load**: Replace the current `default=str` JSON serialization with a strict handler that rejects unknown types. Add schema validation via Pydantic on every `json.load()`.

3. **Calibration file locking**: Implement advisory file locking for `calibration.json` to prevent silent overwrites in multi-process scenarios. Use `filelock` library for cross-platform support.

4. **Immutable calibration snapshots**: After a calibration is committed, write an immutable `.snapshot.json` alongside the mutable `calibration.json`. This provides point-in-time recovery without relying on the `history.py` snapshot mechanism.

5. **Schema migration tests**: For each registered migration in `core/schemas.py`, add a test that loads a fixture file of the old version and verifies the migrated output matches the expected new version.

---

## Appendix: Documentation vs. Implementation Discrepancies

| Documented Claim | Actual Implementation |
|---|---|
| "No waveform auto-generation is permitted" (README Step 3) | Autotune module implicitly depends on pre-registered pulses. No enforcement mechanism prevents waveform generation outside the prescribed flow. |
| 9-layer architecture model (docs/ARCHITECTURE.md) | Layering is not strictly enforced. Calibration code imports from experiments. Autotune bypasses several layers. |
| Schema v5.1.0 (docs) | CalibrationStore supports v5.0.0 and v5.1.0 but some documentation references differ. Cross-referencing with the `_SUPPORTED_CALIBRATION_VERSIONS` set is needed to confirm. |
| SessionState build hash = SHA-256 of config files | Autotune uses its own `_snapshot_hash()` over parameter state — different concept, same terminology. |
| Root ARCHITECTURE.md and API_REFERENCE.md | **Stubs** that redirect to README.md; actual content is in `qubox_v2_legacy/docs/`. |
| Migration module documentation | References `SCHEMA_VERSIONING.md` and `PULSE_SPEC_SCHEMA.md` which do not exist in the repository. |

---

*This report was generated by automated structural analysis of the complete qubox_v2_legacy repository. All findings are based on static code reading — no code was executed or modified.*
