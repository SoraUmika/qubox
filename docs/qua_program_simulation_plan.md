# QUA Program Simulation Support + First-Class Program Build Abstraction

> **Version:** 1.0.0 · **Date:** 2026-02-26 · **Status:** Design proposal (pre-implementation)
> **Scope:** First-class build/simulate pipeline for all `qubox_v2` experiments
> **Dependencies:** v2.1 roleless types (`DriveTarget`, `ReadoutHandle`, `FrequencyPlan`, `*Config`)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Workflow & Limitations](#2-current-workflow--limitations)
3. [Legacy Review: `qubox_legacy/program_manager`](#3-legacy-review-qubox_legacyprogram_manager)
4. [Proposed Architecture: Build / Run / Simulate Separation](#4-proposed-architecture-build--run--simulate-separation)
5. [Proposed Types: `ProgramBuildResult`, `QuboxSimulationConfig`, `SimulationResult`](#5-proposed-types)
6. [Readout & measureMacro in Simulation Context](#6-readout--measuremacro-in-simulation-context)
7. [Examples (Pseudo-Code)](#7-examples-pseudo-code)
8. [Rollout Plan & Risk Assessment](#8-rollout-plan--risk-assessment)

---

## 1. Executive Summary

### 1.1 Problem

Today, every experiment's `run()` method is a monolith that resolves parameters,
applies side effects (frequency mutations, measureMacro configuration), builds a
QUA program, and executes it — all in one inseparable call.  There is **no way to
obtain a QUA program from an experiment without executing it on hardware**.

`ProgramRunner.simulate()` at `qubox_v2/hardware/program_runner.py:362-389`
already exists and works.  It takes a pre-built QUA program, calls
`qmm.simulate(cfg, program, SimulationConfig)`, and returns relabeled
`SimulatorSamples` with built-in plotting.  But nobody can give it a program
without running the experiment first.

The `build_program()` method is defined in the `Experiment` protocol
(`core/protocols.py:91`) and stubbed in `ExperimentBase`
(`experiments/experiment_base.py:420`), but it raises `NotImplementedError`
and **no experiment subclass implements it**.

### 1.2 Design Goal

Introduce a **build step** that cleanly separates parameter resolution and QUA
program construction from execution.  This enables:

1. **Simulation without hardware execution** — visualize pulse sequences, verify
   timing, debug control flow.
2. **Program inspection and serialization** — export QUA scripts for offline
   debugging.
3. **Reproducibility through provenance logging** — record resolved bindings,
   frequencies, and parameters alongside every program.
4. **Compatibility with v2.1 roleless types** — frozen `DriveTarget`,
   `ReadoutHandle`, `FrequencyPlan`, and per-experiment `*Config` dataclasses
   from `experiments/configs.py`.

### 1.3 Key Constraint

`run()` must remain callable with its current signatures.  All 15+ experiment
classes and their notebook call-sites continue to work identically.  The refactor
is **internal** — `simulate()` is additive.

---

## 2. Current Workflow & Limitations

### 2.1 The `run()` Monolith Pattern

Every experiment follows the same inline pattern.  Taking `PowerRabi.run()` at
`experiments/time_domain/rabi.py:138-180` as the canonical example:

```python
def run(self, max_gain, dg=1e-3, op="ge_ref_r180", length=None,
        truncate_clks=None, n_avg=1000):
    # ── Phase 1: Parameter resolution ──
    attr = self.attr
    gains = np.arange(-max_gain, max_gain + 1e-12, dg, dtype=float)
    pulse_info = self.pulse_mgr.get_pulseOp_by_element_op(attr.qb_el, op)
    if not length:
        length = pulse_info.length
    pulse_clock_len = round(length / 4)

    # ── Phase 2: Side effects (frequency mutations on live hardware) ──
    self.set_standard_frequencies()

    # ── Phase 3: QUA program construction ──
    prog = cQED_programs.power_rabi(
        pulse_clock_len, gains, attr.qb_therm_clks,
        op, truncate_clks, n_avg,
        qb_el=attr.qb_el, bindings=self._bindings_or_none,
    )

    # ── Phase 4: Execute + post-process ──
    result = self.run_program(prog, n_total=n_avg, processors=[...])
    self.save_output(result.output, "powerRabi")
    return result
```

Phases 1-3 are **extractable**.  Phase 4 is what `simulate()` replaces.

### 2.2 Side Effect Inventory

Experiments mutate hardware state before building programs:

| Side Effect | Source | Affected Experiments |
|---|---|---|
| `self.hw.set_element_fq(el, freq)` | `set_standard_frequencies()` (`experiment_base.py:285-304`) | T1, T2Ramsey, T2Echo, PowerRabi, TemporalRabi, Chevrons, QubitSpec, cavity experiments |
| `measureMacro.using_defaults()` context | Individual `run()` methods | ResonatorSpectroscopy, ResonatorPowerSpectroscopy |
| Custom `set_element_fq()` with detuning | `T2Ramsey.run()` (`coherence.py:50-51`) | T2Ramsey, ResidualPhotonRamsey |

For simulation, these side effects **must still happen** — the QM config used by
`qmm.simulate()` must reflect the same frequency state that a real execution
would use.

### 2.3 Existing `ProgramRunner.simulate()`

At `hardware/program_runner.py:362-389`:

```python
def simulate(self, program, *, duration=4000, plot=True, plot_params=None,
             controllers=("con1",), t_begin=None, t_end=None, compiler_options=None):
    cfg = self.config.build_qm_config()
    sim_config = SimulationConfig(duration=int(int(duration) / 4))
    job = self._qmm.simulate(cfg, program, sim_config, compiler_options=compiler_options)
    sim_raw = job.get_simulated_samples()
    sim_labeled = self._relabel_simulator_samples(sim_raw)
    if plot:
        self._plot_sim_custom(sim_labeled, ...)
    return sim_labeled
```

This already does everything needed at the runner level.  The gap is **between the
experiment and the runner** — there is no path from experiment parameters to a
built program without executing.

### 2.4 Build Protocol Exists But Is Unused

```python
# core/protocols.py:80-93
class Experiment(Protocol):
    """Contract for a single experiment type."""
    def build_program(self, **params: Any) -> Any: ...   # ← line 91
    def run(self, **params: Any) -> Any: ...
    def process(self, raw_output: Any, **params: Any) -> Any: ...

# experiments/experiment_base.py:420-422
def build_program(self, **params: Any) -> Any:
    raise NotImplementedError(
        f"{self.name}.build_program() not implemented"
    )
```

No experiment overrides `build_program()`.  The protocol anticipated this need but
it was never realized.

### 2.5 Execution Path

```
experiment.run(**params)
  └→ self.run_program(prog, n_total=...)          # experiment_base.py:375
       └→ runner = getattr(self._ctx, "runner")    # experiment_base.py:381
            └→ ProgramRunner.run_program(prog, ...) # program_runner.py:153
                 ├→ cfg_snapshot = self.config.build_qm_config()
                 ├→ job = self.hw.qm.execute(qua_prog)
                 ├→ result_handles.fetch_all()
                 └→ return RunResult(mode=HARDWARE, output=out, ...)
```

### 2.6 Program Builder Functions

All ~40 builder functions in `programs/builders/` are **pure QUA program
factories**.  They accept parameters and return a QUA `program` object.  They do
not care whether the program will be executed or simulated.

| Module | Functions | Example Signature |
|---|---|---|
| `builders/time_domain.py` | 10 | `power_rabi(qb_clock_len, gains, therm, pulse, trunc, n_avg, *, qb_el, bindings)` |
| `builders/spectroscopy.py` | 6 | `resonator_spectroscopy(if_frequencies, depletion_clks, n_avg, *, ro_el, bindings)` |
| `builders/readout.py` | 8 | `iq_blobs(ro_el, qb_el, r180, therm, n_runs, *, bindings)` |
| `builders/calibration.py` | 5 | `randomized_benchmarking(...)` |
| `builders/cavity.py` | 11 | `storage_spectroscopy(qb_el, st_el, disp, sel_r180, ...)` |
| `builders/tomography.py` | 2 | `qubit_state_tomography(...)` |

**No changes to builder functions are needed for simulation support.**

---

## 3. Legacy Review: `qubox_legacy/program_manager`

### 3.1 Legacy Simulation Entry Point

**File:** `qubox_legacy/program_manager.py:1352-1404`

```python
def simulate(self, program, *, duration=4000, plot=True, plot_params=None,
             controllers=("con1",), t_begin=None, t_end=None, compiler_options=None):
    cfg = self.qm_config or self.build_qm_config()
    pp = deepcopy(_DEFAULT_PLOT_PARAMS)
    if plot_params:
        pp.update(plot_params)

    sim_config = SimulationConfig(duration=int(int(duration) / 4))
    job = self._qmm.simulate(cfg, program, sim_config, compiler_options=compiler_options)
    sim_raw = job.get_simulated_samples()
    sim_labeled = self._relabel_simulator_samples(sim_raw)

    if plot:
        self._plot_sim_custom(sim_labeled, plot_params=pp, controllers=controllers,
                              t_begin=t_begin, t_end=t_end)
    return sim_labeled
```

### 3.2 QM SDK API Calls

| Call | Purpose | Returns |
|---|---|---|
| `SimulationConfig(duration=N)` | Configure sim duration in clock cycles (ns/4) | `SimulationConfig` |
| `qmm.simulate(cfg, program, sim_config)` | Run QUA program in QM simulator | `SimulationJob` |
| `job.get_simulated_samples()` | Fetch simulated waveforms | `SimulatorSamples` |

**QM SDK imports:**
```python
from qm import QuantumMachinesManager, SimulationConfig, generate_qua_script
from qm.simulate import SimulatorControllerSamples, SimulatorSamples
```

### 3.3 Sample Relabeling

`_relabel_simulator_samples()` (`program_manager.py:680-701`) maps raw port-based
keys (`"1-1"`, `"1-2"`) to human-readable element:channel names (`"qubit:I"`,
`"readout:Q"`) using `octave_links` metadata from the hardware config.

```
Raw key  "1-1"  →  octave_links lookup  →  "qubit:I"
Raw key  "1-2"  →  octave_links lookup  →  "qubit:Q"
Raw key  "1-3"  →  octave_links lookup  →  "readout:I"
```

### 3.4 Visualization

`_plot_sim_custom()` (`program_manager.py:1217-1349`):
- Matplotlib GridSpec with 2 subplots (main plot + legend panel)
- Analog waveforms on left y-axis (volts)
- Digital signals on right y-axis (twinx) as step plots
- Configurable time unit (ns/us/ms), channel filtering, time windowing

**Default plot parameters** (`program_manager.py:67-77`):
```python
_DEFAULT_PLOT_PARAMS = {
    "which": "both",        # "analog", "digital", or "both"
    "channels": None,       # list of channel names (None = all)
    "time_unit": "ns",      # "ns", "us", or "ms"
    "xlim": None,
    "ylim": None,
    "digital_ylim": None,
    "title": None,
    "legend": True,
    "grid": True,
}
```

### 3.5 Legacy ↔ v2 Mapping

| Legacy (`QuaProgramManager`) | v2 (`ProgramRunner`) | Status |
|---|---|---|
| `simulate()` at 1352-1404 | `simulate()` at 362-389 | ✅ Already ported |
| `_relabel_simulator_samples()` at 680-701 | `_relabel_simulator_samples()` at 442-457 | ✅ Already ported |
| `_plot_sim_custom()` at 1217-1349 | `_plot_sim_custom()` at 460-568 | ✅ Already ported |
| `_build_ao_aliases_from_config()` at 634-665 | `_build_ao_aliases_from_config()` at 399-427 | ✅ Already ported |
| N/A | `ExperimentBase.simulate()` | ❌ **Missing — this plan** |
| N/A | `ProgramBuildResult` type | ❌ **Missing — this plan** |

### 3.6 Legacy Pitfalls to Avoid

1. **Factor-of-4 confusion** — QM's `SimulationConfig.duration` is in clock
   cycles (4 ns each).  The legacy code divides ns by 4 inline
   (`int(int(duration) / 4)`).  We should centralize this in a typed config.

2. **No provenance** — the legacy `simulate()` returns raw `SimulatorSamples`
   with no record of which program, parameters, or frequencies were used.

3. **Config staleness** — `self.qm_config or self.build_qm_config()` could
   use a stale config if frequencies were changed after the last `open_qm()`.
   The v2 `ProgramRunner.simulate()` already calls `build_qm_config()` fresh.

4. **No build abstraction** — users had to manually call a builder function,
   set up measureMacro, and pass the program to `simulate()`.  This is exactly
   the gap we close.

---

## 4. Proposed Architecture: Build / Run / Simulate Separation

### 4.1 High-Level Flow

```
                    ┌─────────────────────┐
                    │  user params / cfg   │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │   build_program()   │  ← ExperimentBase (applies frequencies)
                    │     └→ _build_impl()│  ← Subclass override point
                    └─────────┬───────────┘
                              │
                     ProgramBuildResult
                     (frozen snapshot)
                              │
                  ┌───────────┼───────────┐
                  │                       │
         ┌────────▼────────┐    ┌─────────▼─────────┐
         │     run()       │    │   simulate()      │
         │  execute on HW  │    │  QM sim engine    │
         └────────┬────────┘    └─────────┬─────────┘
                  │                       │
            RunResult              SimulationResult
```

### 4.2 Design Decision: Experiment-Level Methods

`simulate()` lives on `ExperimentBase`, **not** on `SessionManager`.

**Justification:**

1. **Parameter coupling** — each experiment's `simulate()` needs the same
   parameters as its `run()`.  Putting `simulate()` on the session would
   require forwarding arbitrary kwargs or a clumsy two-step.

2. **Symmetry** — `run()` is on the experiment.  `simulate()` is its
   simulation analog.  Users expect `rabi.simulate(...)` to mirror
   `rabi.run(...)`.

3. **Session remains the lifecycle manager** — the session owns `ProgramRunner`
   and the hardware connection.  The experiment's `simulate()` delegates to
   `runner.simulate()` for the actual work.

A thin `session.simulate_program(prog)` convenience is added for ad-hoc QUA
program simulation not tied to any experiment.

### 4.3 Override Pattern: `_build_impl()` vs `build_program()`

```python
class ExperimentBase:

    def build_program(self, **params) -> ProgramBuildResult:
        """Public entry point.  Calls _build_impl(), then applies frequencies."""
        build = self._build_impl(**params)
        for element, freq in build.resolved_frequencies.items():
            self.hw.set_element_fq(element, freq)
        return build

    def _build_impl(self, **params) -> ProgramBuildResult:
        """Subclass override point.  Must NOT apply side effects."""
        raise NotImplementedError(
            f"{self.name}._build_impl() not implemented. "
            "Migrate the build portion of run() to _build_impl()."
        )
```

**Why two methods?**

- `build_program()` is the **public, base-class-controlled** method that
  enforces invariants (frequency application, provenance timestamping).
- `_build_impl()` is the **subclass override point** that handles experiment-
  specific parameter resolution and QUA program construction.  It must not call
  `set_standard_frequencies()` or `run_program()`.

### 4.4 Helper: `_resolve_readout_frequency()`

Extracted from `set_standard_frequencies()` (`experiment_base.py:285-304`) as a
**pure resolver** that returns the frequency without applying it:

```python
def _resolve_readout_frequency(self) -> float:
    """Resolve readout frequency: bindings → measureMacro → attributes."""
    b = self._bindings_or_none
    if b is not None and b.readout is not None:
        ro_fq = getattr(b.readout, "drive_frequency", None)
        if isinstance(ro_fq, (int, float)) and np.isfinite(ro_fq):
            return float(ro_fq)
    mm = self.measure_macro
    ro_fq = getattr(mm, "_drive_frequency", None)
    if isinstance(ro_fq, (int, float)) and np.isfinite(ro_fq):
        return float(ro_fq)
    return float(self.attr.ro_fq)
```

Similarly, `_resolve_qubit_frequency()` wraps the existing
`get_qubit_frequency()` logic.  Subclasses call these in `_build_impl()` and
place the results in `ProgramBuildResult.resolved_frequencies`.

### 4.5 Refactored `run()`

Each experiment's `run()` becomes:

```python
def run(self, ...) -> RunResult:
    build = self.build_program(...)
    result = self.run_program(
        build.program, n_total=build.n_total,
        processors=build.processors, **build.run_program_kwargs,
    )
    result.metadata = {
        **(result.metadata or {}),
        "build_provenance": {
            "experiment": build.experiment_name,
            "builder": build.builder_function,
            "params": build.params,
            "frequencies": build.resolved_frequencies,
            "timestamp": build.timestamp,
        },
    }
    self.save_output(result.output, "<tag>")
    return result
```

### 4.6 `simulate()` on `ExperimentBase`

```python
def simulate(self, sim_config=None, **params) -> SimulationResult:
    """Build the QUA program, then simulate it."""
    if sim_config is None:
        sim_config = QuboxSimulationConfig()

    build = self.build_program(**params)

    runner = getattr(self._ctx, "runner", None)
    if runner is None:
        raise RuntimeError("No ProgramRunner available. Call session.open() first.")

    sim_samples = runner.simulate(
        build.program,
        duration=sim_config.duration_ns,
        plot=sim_config.plot,
        plot_params=sim_config.plot_params,
        controllers=sim_config.controllers,
        t_begin=sim_config.t_begin,
        t_end=sim_config.t_end,
        compiler_options=sim_config.compiler_options,
    )

    return SimulationResult(
        samples=sim_samples,
        build=build,
        config_snapshot=runner.config.build_qm_config(),
        sim_config=sim_config,
        duration_ns=sim_config.duration_ns,
    )
```

---

## 5. Proposed Types

### 5.1 `ProgramBuildResult`

**Location:** `qubox_v2/experiments/result.py` (alongside existing `RunResult`,
`AnalysisResult`)

```python
@dataclass(frozen=True)
class ProgramBuildResult:
    """Immutable snapshot produced by ExperimentBase.build_program().

    Contains everything needed to execute OR simulate a QUA program,
    plus provenance metadata for reproducibility.
    """

    # ── Core payload ──
    program: Any
        # The QUA program object (qm.qua._Program).

    n_total: int
        # Total shot count for progress tracking and result shaping.

    processors: list[Callable]
        # Post-processing pipeline to apply to raw output.

    # ── Provenance ──
    experiment_name: str
        # Fully qualified experiment class name (e.g. "PowerRabi").

    params: dict[str, Any]
        # Frozen copy of resolved parameters used to build the program.
        # Post-resolution values (arrays materialized, frequencies computed).

    resolved_frequencies: dict[str, float]
        # {element_name: frequency_hz} — exact frequencies that were set
        # (or would be set) before program execution.

    bindings_snapshot: dict[str, Any] | None
        # Serializable snapshot of ExperimentBindings state.

    # ── Optional metadata ──
    builder_function: str | None = None
        # Name of the cQED_programs.* function that built the program.

    sweep_axes: dict[str, Any] | None = None
        # {axis_name: array_or_description} for each swept parameter.
        # E.g. {"gains": np.array([...]), "delays": np.array([...])}

    measure_macro_state: dict[str, Any] | None = None
        # Snapshot of measureMacro configuration at build time (active_element,
        # active_op, weight_len, etc.)

    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
        # ISO-8601 build time.

    run_program_kwargs: dict[str, Any] = field(default_factory=dict)
        # Additional kwargs to forward to run_program().
```

**Design choices:**

- **Frozen** — once built, the program and its provenance are immutable.
  Prevents accidental mutation between build and execute/simulate.
- **`processors` included** — both `run()` and `simulate()` (when
  `process_in_sim=True`) can apply identical transforms.
- **`resolved_frequencies`** captures what `set_standard_frequencies()` would
  apply, enabling simulation to replay exact config mutations.
- **`sweep_axes`** — optional metadata ("this program swept gains from −0.5 to
  0.5 in 1000 steps") for debugging and provenance.

### 5.2 `QuboxSimulationConfig`

**Location:** `qubox_v2/hardware/program_runner.py` (near existing `RunResult`,
`_DEFAULT_PLOT_PARAMS`)

```python
@dataclass
class QuboxSimulationConfig:
    """qubox-specific wrapper around QM's SimulationConfig.

    Provides sensible defaults and centralizes the ns → clock-cycle
    conversion that is scattered in legacy code.
    """

    duration_ns: int = 4000
        # Simulation duration in nanoseconds.

    plot: bool = True
        # Auto-plot simulated waveforms.

    plot_params: dict[str, Any] | None = None
        # Override keys: which, channels, time_unit, xlim, ylim,
        # digital_ylim, title, legend, grid.

    controllers: tuple[str, ...] = ("con1",)
        # Controller names to include in plots.

    t_begin: float | None = None
        # Plot time window start (in time_unit).

    t_end: float | None = None
        # Plot time window end (in time_unit).

    compiler_options: Any = None
        # Forwarded to qmm.simulate().

    def to_qm_sim_config(self) -> "SimulationConfig":
        """Convert to QM SDK's SimulationConfig (clock cycles = ns/4)."""
        from qm import SimulationConfig
        return SimulationConfig(duration=int(self.duration_ns // 4))
```

**Why wrap?**  QM's `SimulationConfig` takes duration in clock cycles (ns/4).
The legacy code has `int(int(duration) / 4)` inline in two places.
Centralizing this prevents off-by-4× errors.

### 5.3 `SimulationResult`

**Location:** `qubox_v2/experiments/result.py`

```python
@dataclass
class SimulationResult:
    """Result of simulating a QUA program.

    Carries simulated waveform samples and the full provenance chain
    back to the build step.
    """

    samples: Any
        # Relabeled SimulatorSamples.
        # Dict[controller_name → SimulatorControllerSamples].
        # Keys are element:I / element:Q after relabeling.

    build: ProgramBuildResult
        # The build result that produced the simulated program.
        # Provides full provenance chain.

    config_snapshot: dict[str, Any]
        # QM config dict used for simulation (deep copy at sim time).

    sim_config: QuboxSimulationConfig
        # Simulation parameters used.

    duration_ns: int
        # Actual simulation duration in ns.

    def analog_channels(self) -> dict[str, np.ndarray]:
        """Flatten all analog channels across controllers."""
        out = {}
        for ctrl, con in self.samples.items():
            for name, arr in con.analog.items():
                out[f"{ctrl}:{name}"] = np.asarray(arr)
        return out

    def digital_channels(self) -> dict[str, np.ndarray]:
        """Flatten all digital channels across controllers."""
        out = {}
        for ctrl, con in self.samples.items():
            for name, arr in con.digital.items():
                out[f"{ctrl}:{name}"] = np.asarray(arr)
        return out
```

### 5.4 Relationship to Existing `RunResult`

```python
# Existing (hardware/program_runner.py:60-65) — unchanged
@dataclass
class RunResult:
    mode: ExecMode          # HARDWARE or SIMULATE
    output: Any             # Output dict-like with fetched results
    sim_samples: Any = None # For simulations (populated when mode=SIMULATE)
    metadata: dict = None   # Job metadata + build provenance (new in this plan)
```

`RunResult` keeps its current shape.  The `metadata` field gains a
`"build_provenance"` sub-dict when the refactored `run()` is used.
`SimulationResult` is a **new, separate type** for the simulation path — it
carries richer provenance than `RunResult` and does not try to shoehorn
waveform data into the `output` field.

---

## 6. Readout & measureMacro in Simulation Context

### 6.1 How measureMacro Works During Build

Builder functions in `programs/builders/` call `measureMacro.measure()` inside
`with program()` blocks to emit QUA `measure()` statements.  Before calling a
builder, some experiments set up a context:

```python
# experiments/spectroscopy/resonator.py:33-42 (ResonatorSpectroscopy.run)
ro_info = self.pulse_mgr.get_pulseOp_by_element_op(attr.ro_el, readout_op)
mm = measureMacro
weight_len = int(ro_info.length) if ro_info.length else None
with mm.using_defaults(pulse_op=ro_info, active_op=readout_op, weight_len=weight_len):
    prog = cQED_programs.resonator_spectroscopy(...)
    result = self.run_program(prog, ...)
```

The `using_defaults()` context manager temporarily sets measureMacro state that
the builder reads during QUA program construction.

### 6.2 Simulation Needs Identical Context

For simulation, the QUA program is compiled by the QM simulator including all
`measure()` statements.  The simulator generates output waveforms for all
elements including readout pulses.

The critical point: `measureMacro` must be configured (via `using_defaults()`)
before the builder function is called, **identically for both run and simulate
paths**.  The `build_program()` architecture ensures this because the same
`_build_impl()` is used by both paths.

### 6.3 Strategy Per Experiment Category

**Category A — no measureMacro context needed** (~10 experiments):
PowerRabi, TemporalRabi, T1, T2Echo, QubitSpectroscopy, ResonatorSpectroscopyX180,
Chevrons, StorageSpectroscopy.

These inherit `simulate()` from `ExperimentBase` unchanged.  `_build_impl()`
is straightforward.

**Category B — measureMacro context needed** (~4 experiments):
ResonatorSpectroscopy, ResonatorPowerSpectroscopy.

These override both `run()` and `simulate()` to wrap the call in
`measureMacro.using_defaults(...)`:

```python
class ResonatorSpectroscopy(ExperimentBase):

    def _setup_measure_context(self, readout_op):
        """Return the measureMacro context manager for this experiment."""
        ro_info = self.pulse_mgr.get_pulseOp_by_element_op(self.attr.ro_el, readout_op)
        weight_len = int(ro_info.length) if ro_info.length else None
        return measureMacro.using_defaults(
            pulse_op=ro_info, active_op=readout_op, weight_len=weight_len,
        )

    def run(self, readout_op, rf_begin=8605e6, rf_end=8620e6, df=50e3, n_avg=1000):
        with self._setup_measure_context(readout_op):
            build = self.build_program(readout_op=readout_op, ...)
            result = self.run_program(build.program, ...)
        return result

    def simulate(self, sim_config=None, **params):
        readout_op = params.get("readout_op", "readout")
        with self._setup_measure_context(readout_op):
            return super().simulate(sim_config, **params)
```

### 6.4 Future: `emit_measurement()` Eliminates the Problem

At `programs/macros/measure.py:2042-2113`, `emit_measurement()` is a pure
function taking `ReadoutHandle`.  When builders migrate from
`measureMacro.measure()` to `emit_measurement(ReadoutHandle, ...)`, the
`using_defaults()` context managers in `run()` and `simulate()` become
unnecessary.  This simplifies both paths simultaneously.

---

## 7. Examples (Pseudo-Code)

### 7.1 PowerRabi: Full Refactored Implementation

```python
class PowerRabi(ExperimentBase):
    """Qubit Rabi oscillations vs amplitude/gain."""

    def _build_impl(
        self,
        max_gain: float = 0.5,
        dg: float = 1e-3,
        op: str = "ge_ref_r180",
        length: int | None = None,
        truncate_clks: int | None = None,
        n_avg: int = 1000,
    ) -> ProgramBuildResult:
        attr = self.attr
        gains = np.arange(-max_gain, max_gain + 1e-12, dg, dtype=float)

        pulse_info = self.pulse_mgr.get_pulseOp_by_element_op(attr.qb_el, op)
        if not length:
            length = pulse_info.length
        I_wf, Q_wf = pulse_info.I_wf, pulse_info.Q_wf
        peak_amp = max(np.abs(I_wf).max(), np.abs(Q_wf).max())
        if peak_amp * max_gain > MAX_AMPLITUDE:
            raise ValueError(...)

        pulse_clock_len = round(length / 4)

        # Resolve frequencies (do NOT apply — base class handles that)
        ro_fq = self._resolve_readout_frequency()
        qb_fq = self.get_qubit_frequency()

        prog = cQED_programs.power_rabi(
            pulse_clock_len, gains, attr.qb_therm_clks,
            op, truncate_clks, n_avg,
            qb_el=attr.qb_el,
            bindings=self._bindings_or_none,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=[pp.proc_default, pp.proc_attach("gains", gains)],
            experiment_name="PowerRabi",
            params={"max_gain": max_gain, "dg": dg, "op": op,
                    "length": length, "truncate_clks": truncate_clks, "n_avg": n_avg},
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.power_rabi",
            sweep_axes={"gains": gains},
        )

    def run(self, max_gain, dg=1e-3, op="ge_ref_r180", length=None,
            truncate_clks=None, n_avg=1000) -> RunResult:
        build = self.build_program(
            max_gain=max_gain, dg=dg, op=op,
            length=length, truncate_clks=truncate_clks, n_avg=n_avg,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=build.processors,
        )
        self._run_params = {"op": op}
        self.save_output(result.output, "powerRabi")
        return result
```

### 7.2 Notebook: Simulate a Power Rabi

```python
from qubox_v2.hardware.program_runner import QuboxSimulationConfig

rabi = PowerRabi(session)

# ── Simulate with defaults (4000 ns, auto-plot) ──
sim = rabi.simulate(max_gain=0.5, dg=1e-3, n_avg=1000)
# → Displays matplotlib plot of analog/digital waveforms

# ── Simulate with custom duration, no auto-plot ──
sim = rabi.simulate(
    sim_config=QuboxSimulationConfig(duration_ns=10_000, plot=False),
    max_gain=0.5, dg=1e-3, n_avg=1000,
)

# ── Inspect provenance ──
print(sim.build.resolved_frequencies)
# {'readout': 8612000000.0, 'qubit': 6234000000.0}

print(sim.build.sweep_axes)
# {'gains': array([-0.5, -0.499, ..., 0.499, 0.5])}

print(sim.build.builder_function)
# 'cQED_programs.power_rabi'

# ── Access raw waveform data ──
channels = sim.analog_channels()
for name, data in channels.items():
    print(f"{name}: {len(data)} samples, range [{data.min():.4f}, {data.max():.4f}] V")
```

### 7.3 Build-Only: Inspect Without Simulating

```python
rabi = PowerRabi(session)
build = rabi.build_program(max_gain=0.5, dg=1e-3, n_avg=1000)

# Serialize QUA script for offline debugging
session.runner.serialize_program(build.program, path="debug/", filename="power_rabi.py")

# Inspect resolved metadata
print(build.params)
print(build.resolved_frequencies)
print(build.n_total)
```

### 7.4 Ad-Hoc Program Simulation (Session-Level)

```python
# For programs built manually, not through an experiment class
from qm.qua import program, declare, fixed, for_, play, measure

with program() as test_prog:
    # ... custom QUA statements ...
    pass

sim_samples = session.simulate_program(
    test_prog,
    sim_config=QuboxSimulationConfig(duration_ns=2000, plot=True),
)
```

### 7.5 T2 Ramsey with Custom Detuning

```python
class T2Ramsey(ExperimentBase):

    def _build_impl(self, qb_detune, delay_end, dt, r90="x90",
                     n_avg=1000) -> ProgramBuildResult:
        attr = self.attr
        delay_clks = create_clks_array(4, delay_end, dt, time_per_clk=4)

        # Resolve base qubit frequency, then apply detuning
        qb_fq_base = self.get_qubit_frequency()
        qb_fq_detuned = qb_fq_base + qb_detune
        ro_fq = self._resolve_readout_frequency()

        prog = cQED_programs.T2_ramsey(
            r90, delay_clks, attr.qb_therm_clks, n_avg,
            qb_el=attr.qb_el, bindings=self._bindings_or_none,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=[pp.proc_default,
                        pp.proc_attach("delays", delay_clks * 4)],
            experiment_name="T2Ramsey",
            params={"qb_detune": qb_detune, "delay_end": delay_end, "dt": dt,
                    "r90": r90, "n_avg": n_avg},
            resolved_frequencies={
                attr.ro_el: ro_fq,
                attr.qb_el: qb_fq_detuned,  # ← detuned frequency
            },
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.T2_ramsey",
            sweep_axes={"delays": delay_clks * 4},
        )
```

### 7.6 Future: v2.1 Config-Based Build (Phase 3)

```python
from qubox_v2.experiments.configs import PowerRabiConfig
from dataclasses import replace

cfg = PowerRabiConfig(max_gain=0.4, n_avg=2000)
qb = session.qubit()       # DriveTarget
ro = session.readout()     # ReadoutHandle

# Config-based build
build = rabi.build_program(config=cfg, drive=qb, readout=ro)

# Config-based simulate
sim = rabi.simulate(config=cfg, drive=qb, readout=ro)

# Parameter sweep
for gain in [0.1, 0.2, 0.3]:
    sim = rabi.simulate(config=replace(cfg, max_gain=gain), drive=qb, readout=ro)
```

---

## 8. Rollout Plan & Risk Assessment

### 8.1 Phase 0: Foundation (No Experiment Changes)

**Goal:** Ship types and base infrastructure without touching any experiment.

| Deliverable | File | Description |
|---|---|---|
| `ProgramBuildResult` | `experiments/result.py` | Frozen dataclass with all provenance fields |
| `SimulationResult` | `experiments/result.py` | Dataclass with samples + build provenance |
| `QuboxSimulationConfig` | `hardware/program_runner.py` | Config wrapper with ns/4 conversion |
| `_resolve_readout_frequency()` | `experiments/experiment_base.py` | Pure frequency resolver |
| `_resolve_qubit_frequency()` | `experiments/experiment_base.py` | Pure frequency resolver |
| `_serialize_bindings()` | `experiments/experiment_base.py` | Bindings serialization helper |
| `build_program()` refactored | `experiments/experiment_base.py` | Calls `_build_impl()` + applies frequencies |
| `simulate()` added | `experiments/experiment_base.py` | Calls `build_program()` + runner.simulate() |
| `simulate_program()` | `experiments/session.py` | Session-level convenience for ad-hoc programs |
| Protocol updated | `core/protocols.py` | Add `simulate()`, update `build_program()` return type |

**Risk:** Zero.  No existing behavior changes.  `_build_impl()` still raises
`NotImplementedError` for all experiments.

**Done criteria:** Types constructable and serializable.
`ExperimentBase.simulate()` raises `NotImplementedError` (via `_build_impl`)
with a clear migration message.

### 8.2 Phase 1: Pilot — 4 Canonical Experiments

**Goal:** Prove the pattern on the simplest experiments.

| Experiment | File | Complexity | measureMacro? |
|---|---|---|---|
| `PowerRabi` | `time_domain/rabi.py` | Low | No |
| `T1Relaxation` | `time_domain/relaxation.py` | Low | No |
| `QubitSpectroscopy` | `spectroscopy/qubit.py` | Low | No |
| `ResonatorSpectroscopy` | `spectroscopy/resonator.py` | Medium | Yes (`using_defaults`) |

**Per experiment:**
1. Implement `_build_impl()` with full provenance
2. Refactor `run()` to delegate to `build_program()`
3. Override `simulate()` where measureMacro context is needed
4. Integration test: `build_program()` returns valid `ProgramBuildResult`
5. Regression test: `run()` behavior identical before/after

**Done criteria:** All 4 experiments support `exp.build_program(...)` and
`exp.simulate(...)`.  Existing `run()` tests pass unchanged.

### 8.3 Phase 2: Broad Migration — All Standard Experiments

**Batch 2a — Low complexity, no measureMacro:**
- TemporalRabi, T2Echo, ResonatorSpectroscopyX180
- TimeRabiChevron, PowerRabiChevron, RamseyChevron
- StorageSpectroscopy, ReadoutTrace

**Batch 2b — Medium complexity:**
- T2Ramsey (custom qubit detuning)
- ResidualPhotonRamsey
- ResonatorPowerSpectroscopy (measureMacro context)

**Batch 2c — Cavity and calibration:**
- Cavity experiments (FockStatePrepare, WignerTomography, etc.)
- Readout calibration experiments (IQBlobs, Butterfly, etc.)
- Gate calibration experiments (AllXY, RB, DRAG)

**Skip until Phase 3:**
- ReadoutFrequencyOptimization (multi-program loop — see §8.5)

### 8.4 Phase 3: Advanced Features & v2.1 Integration

1. **Provenance persistence** — `ProgramBuildResult` summary logged to artifact
   store alongside experiment output.
2. **Config-based build** — accept `*Config` dataclass + v2.1 primitives:
   ```python
   build = rabi.build_program(config=PowerRabiConfig(...), drive=qb, readout=ro)
   ```
3. **`emit_measurement()` migration** — as builders switch from
   `measureMacro.measure()` to `emit_measurement(ReadoutHandle)`, remove
   measureMacro context overrides in `simulate()` and `run()`.
4. **Multi-program experiments** — `build_programs()` for
   ReadoutFrequencyOptimization and similar loop-based experiments.
5. **Simulation comparison tools** — diff two `SimulationResult` objects
   to compare waveforms (verify calibration changes).

### 8.5 Multi-Program Experiments

`ReadoutFrequencyOptimization` runs multiple QUA programs in a loop (one per
IF frequency).  `build_program()` cannot return a single program.

**Options:**
1. **Skip** — `build_program()` raises `NotImplementedError`.  Document that
   loop-based experiments do not support single-shot simulation.
2. **Return first iteration** with metadata indicating it is 1 of N.
3. **`build_programs()`** variant returning `list[ProgramBuildResult]`.

**Recommendation:** Option 1 for Phase 0-2.  Option 3 in Phase 3 if needed.

### 8.6 Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| measureMacro context not set up correctly in simulate path | Medium | High (wrong QUA program) | Phase 1 tests ResonatorSpectroscopy.  Regression tests compare run() output before/after. |
| Frequency side effects order-dependent | Low | Medium (wrong IF in sim) | `build_program()` applies frequencies atomically from `resolved_frequencies` dict. |
| Multi-program experiments cannot use `build_program()` | Certain | Low (rare use case) | Explicitly skip in Phase 0-2.  Document limitation.  Phase 3 adds `build_programs()`. |
| `run()` regression after refactor | Low | High | Per-experiment regression test: compare output dict keys and value shapes old vs new. |
| QM config stale after frequency mutation | Medium | Medium (sim uses wrong config) | `ProgramRunner.simulate()` calls `build_qm_config()` fresh.  `build_program()` applies freqs before sim reads config. |
| v2.1 Config dataclasses not yet wired | Low | Low | Phase 3 feature.  Existing dataclasses in `configs.py` are additive. |
| Simulation accidentally touches hardware | Very Low | High (unsafe) | `simulate()` delegates only to `ProgramRunner.simulate()` which calls `qmm.simulate()`, never `qm.execute()`. |

### 8.7 Testing Strategy

**Unit tests (Phase 0):**
- `ProgramBuildResult` construction, frozen immutability, field access
- `QuboxSimulationConfig.to_qm_sim_config()` clock conversion (ns → ns/4)
- `SimulationResult` construction and helper methods

**Integration tests (Phase 1+):**
- Per experiment: `build_program()` returns populated `ProgramBuildResult`
- `simulate()` with mock `qmm.simulate()` returning synthetic `SimulatorSamples`
- Regression: `run()` output keys and shapes match pre-refactor golden snapshot

**End-to-end tests (Phase 2+):**
- On QM simulator: `exp.simulate(...)` returns non-empty analog channels
- Provenance round-trip: `build.params` reconstructs identical build

---

## Appendix: File Modification Summary

| File | Change | Phase |
|---|---|---|
| `qubox_v2/experiments/result.py` | Add `ProgramBuildResult`, `SimulationResult` | 0 |
| `qubox_v2/hardware/program_runner.py` | Add `QuboxSimulationConfig` | 0 |
| `qubox_v2/experiments/experiment_base.py` | Refactor `build_program()`, add `simulate()`, `_build_impl()`, resolvers | 0 |
| `qubox_v2/experiments/session.py` | Add `simulate_program()` | 0 |
| `qubox_v2/core/protocols.py` | Update `Experiment` protocol with `simulate()` | 0 |
| `qubox_v2/experiments/time_domain/rabi.py` | `PowerRabi._build_impl()` + refactor `run()` | 1 |
| `qubox_v2/experiments/time_domain/relaxation.py` | `T1Relaxation._build_impl()` + refactor `run()` | 1 |
| `qubox_v2/experiments/spectroscopy/resonator.py` | `ResonatorSpectroscopy._build_impl()` + override `simulate()` | 1 |
| `qubox_v2/experiments/spectroscopy/qubit.py` | `QubitSpectroscopy._build_impl()` + refactor `run()` | 1 |
| `qubox_v2/experiments/time_domain/coherence.py` | T2Ramsey, T2Echo, ResidualPhotonRamsey | 2 |
| `qubox_v2/experiments/time_domain/chevron.py` | Chevron classes | 2 |
| `qubox_v2/experiments/cavity/storage.py` | StorageSpectroscopy | 2 |
| `qubox_v2/experiments/cavity/fock.py` | Cavity experiments | 2c |
| `qubox_v2/experiments/calibration/*.py` | Calibration experiments | 2c |
| `qubox_v2/experiments/configs.py` | Wire as `build_program(config=...)` input | 3 |
