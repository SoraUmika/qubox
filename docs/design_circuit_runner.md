# Design Survey: Gate/Circuit Abstraction + Generic QUA Circuit Runner (Design-Only)

## 1) Scope and goals

This document proposes a **design-only** architecture for adding a reusable gate/circuit layer and a generic QUA circuit runner to `qubox_v2`, without replacing the current experiment API immediately.

Primary goals:
- Keep compatibility with `ExperimentBase`, `ProgramBuildResult`, `ProgramRunner`, `CalibrationOrchestrator`, and existing analysis contracts.
- Enable a single abstraction path for gate-sequence experiments (Rabi/T1/T2, readout protocols, pulse-train style workflows).
- Preserve calibration/orchestration behavior (patch preview/apply, artifact persistence, strict context mode).

Non-goals:
- No immediate rewrite of existing builders under `qubox_v2/programs/builders/*`.
- No change to persisted schema in this phase.
- No changes to user-facing notebook APIs until migration stages are complete.

---

## 2) Current-state map (as-is flow)

## 2.1 Build/Run architecture today

Current path in `qubox_v2`:

1. `SessionManager` wires infrastructure (`ConfigEngine`, `HardwareController`, `ProgramRunner`, `CalibrationStore`, devices, bindings).
2. Experiment subclass (`ExperimentBase`) implements `_build_impl(...) -> ProgramBuildResult`.
3. `_build_impl` calls `qubox_v2.programs.api` function (e.g., `power_rabi`, `T1_relaxation`, `readout_butterfly_measurement`) to construct QUA.
4. `build_program()` returns immutable `ProgramBuildResult` with:
   - QUA program
   - processors
   - resolved frequencies
   - builder provenance
   - sweep axes metadata
5. `run()` delegates to `run_program(...)` via `ProgramRunner` and returns `RunResult`.
6. `analyze()` creates `AnalysisResult` (fit/metrics/metadata), optionally emitting patch intents in metadata.
7. `CalibrationOrchestrator` optionally executes run → analysis → patch preview/apply lifecycle.

Key strengths already present:
- Strong provenance object (`ProgramBuildResult`).
- Clean post-processing contract (`RunResult`/`AnalysisResult`).
- Safe patch workflow via orchestrator.
- Session-level strict context + calibration aliasing.

## 2.2 Representative experiment paths

### A) Power Rabi
- Experiment: `experiments/time_domain/rabi.py::PowerRabi`
- Builder call: `cQED_programs.power_rabi(...)`
- QUA implementation: `programs/builders/time_domain.py::power_rabi(...)`
- Sweep axis: gain list attached in processors and `sweep_axes`
- Analysis extracts `g_pi` and may emit calibration patch intent for pulse amplitude.

### B) T1
- Experiment: `experiments/time_domain/relaxation.py::T1Relaxation`
- Builder call: `cQED_programs.T1_relaxation(...)`
- QUA implementation: `programs/builders/time_domain.py::T1_relaxation(...)`
- Sweep axis: delay clocks mapped to ns (`delays`)
- Analysis fits exponential decay and may emit coherence patch intents.

### C) Readout discrimination + butterfly
- GE discrimination experiment: `experiments/calibration/readout.py::ReadoutGEDiscrimination`
  - program: `cQED_programs.iq_blobs(...)`
  - derives angle/threshold/fidelity and optional rotated-weight intents.
- Butterfly experiment: `experiments/calibration/readout.py::ReadoutButterflyMeasurement`
  - program: `cQED_programs.readout_butterfly_measurement(...)`
  - relies on active `measureMacro` readout state and post-selection policy.

Important observation:
- `measureMacro` is still a central mutable dependency for many builders.
- A future generic runner must either (a) encapsulate `measureMacro` state transitions, or (b) route through a binding-aware pure measurement emission API.

---

## 3) Proposed abstractions

## 3.1 `Gate`

A lightweight operation primitive suitable for circuit composition and compilation.

```python
@dataclass(frozen=True)
class Gate:
    name: str                     # e.g., "x180", "wait", "measure", "update_frequency"
    target: str | tuple[str, ...] # element alias(es)
    params: dict[str, Any] = field(default_factory=dict)
    duration_clks: int | None = None
    tags: tuple[str, ...] = ()
```

Design notes:
- `name` references either pulse operation names (`x180`) or virtual/meta operations (`align`, `wait`, `measure`).
- `target` uses alias-level names first, resolved via bindings at compile time.
- `params` carries op-specific values (`amp`, `frequency`, `policy`, etc.).

## 3.2 `QuantumCircuit`

An immutable sequence container for gate-level intent.

```python
@dataclass(frozen=True)
class QuantumCircuit:
    gates: tuple[Gate, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def append(self, gate: Gate) -> "QuantumCircuit": ...
    def extend(self, gates: Iterable[Gate]) -> "QuantumCircuit": ...
```

Design notes:
- Immutable-by-default to improve reproducibility and cacheability.
- Stores provenance metadata (experiment name, build labels, notes).

## 3.3 `SweepSpec`

A declarative sweep descriptor for 1D/2D parameter scans.

```python
@dataclass(frozen=True)
class SweepAxis:
    key: str                      # e.g., "gain", "delay_clks", "detune_hz"
    values: np.ndarray
    target_gate: str | None = None
    param_name: str | None = None

@dataclass(frozen=True)
class SweepSpec:
    axes: tuple[SweepAxis, ...]
    averaging: int
    shot_order: str = "axis-major"  # or "shot-major"
```

Design notes:
- Explicitly models axes that are currently spread across loops/processors.
- Supports mapping to legacy `sweep_axes` in `ProgramBuildResult`.

## 3.4 `QuantumCircuitRunner`

A generic compiler+executor facade that integrates with existing runtime.

```python
class QuantumCircuitRunner:
    def build(
        self,
        circuit: QuantumCircuit,
        sweep: SweepSpec | None,
        *,
        session: SessionManager,
        processors: tuple[Callable, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> ProgramBuildResult: ...

    def run(self, build: ProgramBuildResult, *, session: SessionManager, **run_kw) -> RunResult: ...

    def simulate(self, build: ProgramBuildResult, *, session: SessionManager, sim_cfg=None) -> SimulationResult: ...
```

Design notes:
- Returns `ProgramBuildResult` to remain native with current experiment and simulation flows.
- Does not replace `ProgramRunner`; it compiles circuit intent into a QUA `program` and delegates run/sim to existing infrastructure.

---

## 4) Compilation strategy options

## 4.1 Strategy A: Direct gate→QUA lowering

Approach:
- `QuantumCircuitRunner` walks circuit gates and emits QUA immediately.

Pros:
- Fastest to deliver.
- Minimal architecture overhead.
- Easier parity with existing builder functions.

Cons:
- Limited optimization opportunities.
- Harder to target non-QUA backends later.
- Less inspectable intermediate representation for debugging/analysis.

Best use:
- Initial prototype and migration bridge for current experiments.

## 4.2 Strategy B: Gate→IR→QUA two-stage lowering

Approach:
- Convert `QuantumCircuit` into a normalized IR (timing events, resolved targets, measurement intents), then lower IR to QUA.

Pros:
- Better validation and static checks (timing conflicts, unsupported ops).
- Backend flexibility (future simulator/compiler targets).
- Easier optimization passes (gate fusion, align/wait normalization).

Cons:
- More upfront design cost.
- Requires IR schema/versioning discipline.

Best use:
- Medium-term architecture once first set of experiments is on circuit path.

## 4.3 Recommendation

Use a phased hybrid:
- **Phase P1:** direct lowering only, but define a stable internal `LoweringContext` and typed gate taxonomy now.
- **Phase P2:** insert a minimal IR boundary without changing public `QuantumCircuitRunner` API.
- **Phase P3:** move validations/optimizations into IR passes.

This keeps the first delivery small while avoiding design dead-ends.

---

## 5) Integration with existing experiment system

## 5.1 Keep `ExperimentBase` as outer contract

Experiments continue to provide:
- `run(...) -> RunResult`
- `analyze(...) -> AnalysisResult`
- `plot(...)`

Only `_build_impl` changes for migrated experiments:
- Build a `QuantumCircuit` + `SweepSpec`
- Call `QuantumCircuitRunner.build(...)`
- Return resulting `ProgramBuildResult`

## 5.2 Preserve orchestrator lifecycle

No changes required in `CalibrationOrchestrator` API:
- It already consumes experiment `run` + `analyze` outputs.
- Patch generation/apply remains metadata-driven from `AnalysisResult`.
- Artifact persistence remains run-output based.

## 5.3 Frequency/bindings/readout integration

A circuit compile context should include:
- session bindings snapshot
- resolved frequencies (readout/qubit/storage/extras)
- readout state source (bindings + calibration)
- measure config token/hash for reproducibility

For readout ops, avoid hidden global mutations where possible:
- preferred: binding-aware emission API semantics
- transitional: scoped `measureMacro` context wrappers (push/restore) around build

## 5.4 Migration envelope

- Existing `qubox_v2.programs.api` builders remain valid.
- Circuit runner can initially call builder helpers internally for complex macros.
- Each migrated experiment can keep old analysis code unchanged.

---

## 6) Proposed migration plan

## Stage 0: Foundations
- Add data classes/interfaces only (`Gate`, `QuantumCircuit`, `SweepSpec`, runner stub).
- Add serialization for circuit metadata into `ProgramBuildResult.params/metadata`.

## Stage 1: Pilot experiments (low-risk)
- Migrate `PowerRabi` and `T1Relaxation` build paths to circuit runner.
- Validate output parity on sweep axes and processor outputs.

## Stage 2: Readout-sensitive path
- Migrate `ReadoutGEDiscrimination` builder path with explicit readout gate semantics.
- Migrate `ReadoutButterflyMeasurement` with explicit post-selection gate/model.
- Ensure strict-mode patch-pending behavior remains preserved in metadata.

## Stage 3: Broader adoption
- Migrate additional time-domain and spectroscopy experiments.
- Introduce IR layer if/when needed.

## Stage 4: Optional deprecation
- Mark duplicate legacy builder entry points as internal once migration coverage is sufficient.

---

## 7) Pseudocode examples (requested)

## 7.1 Power Rabi (circuit-style)

```python
circuit = QuantumCircuit(gates=(
    Gate("play", target="qubit", params={"op": "x180", "amp": Param("gain")}),
    Gate("align", target=("qubit", "readout")),
    Gate("measure", target="readout", params={"acquire": ["I", "Q"]}),
    Gate("wait", target="qubit", params={"clks": Attr("qb_therm_clks")}),
))

sweep = SweepSpec(
    axes=(SweepAxis(key="gain", values=np.arange(-max_gain, max_gain + dg, dg), target_gate="play", param_name="amp"),),
    averaging=n_avg,
)

build = circuit_runner.build(circuit, sweep, session=session, processors=(proc_default, proc_attach("gains", gains)))
result = circuit_runner.run(build, session=session)
analysis = power_rabi_analyze(result)
```

## 7.2 T1 (circuit-style)

```python
circuit = QuantumCircuit(gates=(
    Gate("play", target="qubit", params={"op": "x180"}),
    Gate("wait", target="qubit", params={"clks": Param("delay_clks")}),
    Gate("align", target=("qubit", "readout")),
    Gate("measure", target="readout", params={"acquire": ["I", "Q"]}),
    Gate("wait", target="qubit", params={"clks": Attr("qb_therm_clks")}),
))

sweep = SweepSpec(
    axes=(SweepAxis(key="delay_clks", values=delay_clks),),
    averaging=n_avg,
)

build = circuit_runner.build(circuit, sweep, session=session, processors=(proc_default, proc_attach("delays", delay_clks * 4)))
result = circuit_runner.run(build, session=session)
analysis = t1_analyze(result)
```

## 7.3 Readout discrimination + butterfly (circuit-style)

```python
# GE discrimination circuit
ge_circuit = QuantumCircuit(gates=(
    Gate("measure", target="readout", params={"label": "g_blob"}),
    Gate("play", target="qubit", params={"op": "x180"}),
    Gate("align", target=("qubit", "readout")),
    Gate("measure", target="readout", params={"label": "e_blob"}),
))

ge_build = circuit_runner.build(ge_circuit, SweepSpec(axes=(), averaging=n_samples), session=session)
ge_result = circuit_runner.run(ge_build, session=session)
ge_analysis = ge_discrimination_analyze(ge_result)  # emits angle/threshold + patch intents

# Butterfly circuit, explicitly consuming post-select policy from GE analysis
bfly_circuit = QuantumCircuit(gates=(
    Gate("branch_start", target="qubit", params={"state": "g"}),
    Gate("triple_measure_with_retry", target=("qubit", "readout"), params={
        "r180": "x180",
        "policy": ge_analysis.metadata.get("recommended_policy", "THRESHOLD"),
        "policy_kwargs": ge_analysis.metadata.get("policy_kwargs", {}),
        "max_trials": M0_MAX_TRIALS,
    }),
    Gate("branch_start", target="qubit", params={"state": "e"}),
    Gate("triple_measure_with_retry", target=("qubit", "readout"), params={...}),
))

bfly_build = circuit_runner.build(bfly_circuit, SweepSpec(axes=(), averaging=n_samples), session=session)
bfly_result = circuit_runner.run(bfly_build, session=session)
bfly_analysis = butterfly_analyze(bfly_result)
```

---

## 8) Risks and open questions

## 8.1 Main risks

1. **measureMacro coupling risk**
   - Many builders and readout flows rely on mutable singleton state.
   - Risk of hidden state drift between GE and butterfly unless compile context is explicit.

2. **Parity risk in nested loops**
   - Existing QUA builders manually control stream buffer layout.
   - Circuit lowering must preserve shape/order exactly to avoid downstream analysis breakage.

3. **Calibration patch intent drift**
   - Analysis metadata currently encodes patch ops with experiment-specific assumptions.
   - Migration must keep these intents stable for orchestrator rules.

4. **Over-generalization risk**
   - A too-abstract gate model can become harder to reason about than current explicit builders.

## 8.2 Open questions

1. Should readout/post-selection be represented as first-class gate types or as measurement gate params with policy plugins?
2. Should sweep nesting order be fixed globally or declared per experiment (`axis-major` vs `shot-major`)?
3. What is the minimum IR needed to justify introducing it (validation only vs optimization)?
4. How should we version circuit metadata persisted in artifacts for long-term reproducibility?

---

## 9) Prototype-first recommendation

Recommended first prototype:
- Implement only enough circuit runner capability to express current `PowerRabi` and `T1` paths.
- Keep lowerer direct-to-QUA.
- Preserve `ProgramBuildResult` contract exactly.
- Add parity checks for:
  - sweep axes
    - output key names (`I`, `Q`, `iteration`, attached axes)
  - analysis metric equivalence for baseline datasets.

Then proceed to GE + butterfly migration with explicit readout compile context and state signature handling.

Success criteria for prototype:
- No API break for notebook-level experiment usage.
- Existing orchestrator flow unchanged.
- Equivalent analysis outputs for pilot experiments within expected statistical tolerance.

---

## 10) Summary

A generic gate/circuit runner is compatible with the current `qubox_v2` architecture if introduced as an internal compilation layer under existing `ExperimentBase` contracts. The safest path is phased adoption: direct lowering first for simple time-domain experiments, followed by readout-sensitive workflows, and only then optional IR insertion for validation/optimization. This approach delivers immediate reuse benefits while preserving calibration governance, provenance, and notebook stability.