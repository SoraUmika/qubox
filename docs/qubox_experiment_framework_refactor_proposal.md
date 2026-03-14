# qubox Experiment Framework: Architectural Review and Refactor Proposal

Date: 2026-03-13

## Scope and Audit Basis

This review is based on the current `qubox_v2` codebase, with emphasis on the
actual runtime path rather than only the advertised API. The audit focused on:

- `experiments/session.py`, `experiments/experiment_base.py`, and
  representative experiment classes across spectroscopy, time-domain,
  calibration, and cavity modules
- `programs/builders/*`, `programs/macros/*`, `programs/circuit_runner.py`,
  and `programs/circuit_compiler.py`
- `hardware/*`, `pulses/*`, `calibration/*`, `analysis/*`, and `core/*`
- user workflow notebooks in `notebooks/`
- public documentation in `API_REFERENCE.md` and `standard_experiments.md`

The goal of this document is not to propose a generic software architecture. It
is to propose a better qubox architecture for real cQED work on Quantum
Machines hardware.

## Executive Summary

The current repository already contains most of the capabilities needed for a
serious cQED platform:

- sample and cooldown aware session management
- a large catalog of experiment classes
- a QM / QUA bridge that can build and run real programs
- calibration storage and patch orchestration
- a newer gate / circuit compiler direction
- artifact and reproducibility utilities

The main problem is not missing features. The main problem is architectural
overlap.

Today the codebase exposes several partially competing mental models:

1. An experiment-class model built around `SessionManager`,
   `ExperimentBase`, and direct QUA builders
2. A notebook-first configuration and cooldown workflow
3. A newer roleless API with `DriveTarget`, `ReadoutHandle`,
   `MeasurementConfig`, and binding-driven resolution
4. A newer gate -> protocol -> circuit compiler stack that is promising but
   not yet the dominant production path

For a new experimentalist, the friction comes from having too many valid
"entry points" and not enough obvious defaults.

The most defensible target architecture is:

- `Session` as the runtime entry point
- experiment templates as the main user-facing API
- `Sequence` or `QuantumCircuit` as the body IR for ordered control protocols
- sweeps and acquisition as first-class orthogonal concepts
- calibration-backed operation references, not waveform-owning gates
- one canonical QM backend adapter and compiler path
- one artifact contract and one analysis pipeline contract

The key recommendation is to **not** make `QuantumCircuit` the only top-level
abstraction. It should be important, but it should sit below the experiment
template layer, not above everything else.

## Current Architecture Overview

### Session and Runtime Context

The practical entry point is `qubox_v2.experiments.session.SessionManager`.
This object does much more than simple session bookkeeping:

- resolves sample and cooldown paths through the sample registry
- loads hardware, device, pulse, calibration, and measurement config files
- constructs `ConfigEngine`, `HardwareController`, `ProgramRunner`,
  `QueueManager`, `PulseOperationManager`, `PulseRegistry`,
  `CalibrationStore`, `DeviceManager`, and `CalibrationOrchestrator`
- acts as a factory for higher-level helpers such as target handles and
  circuit-facing objects

This is a strong foundation for reproducibility. Sample and cooldown scoping is
the right direction for lab work.

The friction is startup complexity. A user who wants to run one Ramsey scan is
implicitly required to understand a large amount of session infrastructure.
There is also documentation drift: older docs still suggest a legacy
path-oriented session flow, while the current code effectively enforces strict
sample / cooldown context mode.

### How Experiments Are Defined Today

Experiments are mostly implemented as concrete `ExperimentBase` subclasses under
domain-specific folders such as:

- `experiments/spectroscopy`
- `experiments/time_domain`
- `experiments/calibration`
- `experiments/cavity`
- `experiments/tomography`

The common pattern is:

1. constructor stores experiment parameters
2. `_build_impl()` creates a QUA program or a multi-program plan
3. `run()` builds, executes, and saves output
4. `analyze()` performs experiment-specific fitting
5. `plot()` renders experiment-specific plots

This model works and is readable once the user knows the codebase. It also
maps well to common cQED tasks where each named experiment has established
physics meaning.

The problem is that many experiment classes contain a mix of concerns:

- physics intent
- parameter resolution
- QUA program assembly
- hardware quirks
- fit logic
- plotting
- artifact saving

That makes the surface area large and extension cost high.

### How Pulse Sequences and Protocols Are Represented

The main production representation is still direct QUA builder code.

Representative builders live in:

- `programs/builders/spectroscopy.py`
- `programs/builders/time_domain.py`
- `programs/measurement.py`
- `programs/macros/sequence.py`

Protocol fragments such as Ramsey echo blocks, tomography, state preparation,
and reset logic are represented as reusable QUA macros or helper functions.

This is effective for QM fidelity because the builder code remains close to the
backend. It is also one reason the system has strong physics coverage already.

The downside is that the protocol layer is still too QUA-shaped. A user often
needs to think in terms of builder internals before they can extend the system.

### Quantum Machines Bridge and Compilation Path

There are currently two circuit-related architectures:

1. `programs/circuit_runner.py`
2. `programs/circuit_compiler.py`

The older `CircuitRunner` path defines useful IR objects, but in production it
mostly dispatches by circuit name back into legacy builders rather than truly
lowering a generic sequence to QUA.

The newer `CircuitRunnerV2` path is more promising. It can lower operation-like
objects such as measurement, idle, frame update, play, and qubit rotation into
QUA while generating resolution metadata.

The problem is adoption. The newer compiler path is only partially integrated.
Most real experiment classes still compile through legacy builders, and some
codepaths silently fall back from "circuit mode" to legacy mode.

That means the repository currently has a design direction, but not yet one
canonical compiler path.

### Calibration Logic

Calibration is one of the stronger parts of the codebase.

`CalibrationStore` provides a typed JSON-backed store for:

- cQED parameters
- readout calibration
- pulse calibration
- fit history
- aliases and schema versioning

`CalibrationOrchestrator` already supports a serious flow:

- run experiment
- analyze fit
- propose patch
- dry run or apply patch
- persist artifacts
- roll back on failure

This is exactly the kind of workflow a lab platform should support.

The architectural issue is not missing calibration features. It is split source
of truth. Runtime state is still spread across multiple surfaces:

- `CalibrationStore`
- `analysis/cQED_attributes.py`
- `measureMacro`
- session runtime JSON
- pulse JSON and pulse spec JSON

As long as those surfaces all remain independently meaningful, users cannot
trust that "the calibration" lives in one place.

### Analysis

Analysis is mixed between shared utilities and per-experiment implementations.

The repository already has:

- common fit result objects
- fit wrappers and reusable models
- experiment result dataclasses
- plotting helpers

But in practice analysis is still largely decentralized. Each experiment owns
its own analysis and plotting flow, often with different conventions. Large
calibration files contain both orchestration logic and substantial analysis
logic.

This is workable for a small team with local knowledge, but not ideal for a
platform meant to scale to new users and new experiment families.

### Results, Metadata, and Artifacts

Result persistence exists, but it is fragmented.

Current storage paths include:

- `.npz` output files and `.meta.json` files under cooldown data folders
- calibration artifacts under runtime artifact directories
- optional build metadata via `ArtifactManager` and `SessionState`
- config snapshots and summaries via `core/artifacts.py`

The codebase clearly values traceability and reproducibility. That is the right
direction. The issue is that there is not one default artifact contract for all
runs.

## Current Pain Points

### Usability Pain Points

From the perspective of an experimental physicist, the current friction points
are:

1. The user-facing story is unclear. There are experiment classes, notebook
   flows, typed config objects, target handles, gate abstractions, and circuit
   abstractions, but not one clearly dominant path.
2. The startup path is heavy relative to simple experimental goals.
3. Common experiment families still require knowledge of backend-shaped helper
   modules.
4. The public docs advertise abstractions that are only partially adopted in
   production.
5. Discoverability is weak because the repository does not currently guide the
   user from "I want to run qubit spectroscopy" to one obvious API.

### Coupling and Extension Risks

The codebase has several strongly coupled hotspots:

- `experiments/session.py`
- `experiments/experiment_base.py`
- `programs/macros/measure.py`
- `pulses/manager.py`
- `experiments/calibration/readout.py`

These modules are not large by accident. They are large because they each own
multiple responsibilities that should eventually be separated.

Specific architectural risks:

1. Measurement behavior is too centralized in a large global singleton-like
   macro object.
2. Circuit compilation exists in multiple partially overlapping forms.
3. Calibration truth is duplicated.
4. Persistence is duplicated.
5. Typed config surfaces exist but are not consistently enforced or adopted.

### What Is Already Intuitive

Not everything needs replacement. The following parts are good and should be
preserved:

- sample / cooldown scoping
- experiment names that reflect physics intent
- typed calibration storage with schema versioning
- patch-based calibration updates with dry-run support
- the idea of backend-faithful simulation and trust validation
- the roleless target direction for future extensibility

## Design Goals

The target architecture should optimize for the following:

1. One obvious top-level path for common experiment work
2. Strong separation between physics intent and hardware lowering
3. First-class support for sweep-heavy cQED experiments
4. Explicit calibration awareness without making every user think about pulse
   JSON files
5. Easy inspection of what will be sent to hardware
6. Simple extension for new experiment families
7. QM correctness first, future backend support second
8. Clear artifact, metadata, and analysis contracts
9. Gradual migration with coexistence of legacy experiments

## Proposed Target Architecture

### Core Principle

Use a layered design where each layer has one job:

```text
User API
  -> Experiment Template / Workflow
     -> Sequence Body + Sweep Plan + Acquisition Spec
        -> Calibration Resolver / Operation Library
           -> Backend Compiler / Adapter
              -> Execution Runtime
                 -> Result Bundle + Analysis Pipeline + Artifact Store
```

### Recommended Main Concepts

#### 1. Session

Keep a session object as the lab-runtime anchor.

Responsibilities:

- load sample and cooldown context
- expose device and target resolution
- expose calibration and measurement context
- provide backend runner access
- save artifacts through one artifact manager

The session should not be responsible for detailed experiment construction.

#### 2. ExperimentTemplate

This should be the main user-facing abstraction for standard experiments.

Responsibilities:

- declare physics intent
- define required targets and parameters
- provide default sweep plans and acquisition schemas
- select an analysis pipeline
- optionally emit a sequence body

Examples:

- `QubitSpectroscopy`
- `ResonatorSpectroscopy`
- `PowerRabi`
- `Ramsey`
- `T1`
- `ReadoutGEDiscrimination`
- `ActiveReset`

#### 3. Workflow

Use workflows for multi-stage calibrations and tune-ups that are not naturally
"one program, one fit".

Examples:

- full readout calibration
- mixer calibration
- gate tune-up
- cavity calibration chains

A workflow can run multiple experiment templates in order, collect results, and
propose calibration patches.

#### 4. Sequence

Use `Sequence` as the ordered control body abstraction. `QuantumCircuit` can be
kept as an alias or compatibility layer if desired, but `Sequence` is the
clearer term for cQED work because not all meaningful operations are gates.

Responsibilities:

- ordered operations
- block composition
- repeat blocks
- conditional blocks when backend supports them
- optional measurement and reset operations

This layer should model time-ordered physics intent, not backend waveforms.

#### 5. Operation Library

Use an operation library instead of letting gates own waveforms.

Operations should reference calibrated semantic operations such as:

- `X90(qubit)`
- `X180(qubit)`
- `RamseyPrep(qubit)`
- `Displace(storage, amp, phase)`
- `Measure(readout_handle, mode="iq")`
- `Reset(qubit, mode="active")`

Each operation resolves through calibration into concrete backend play / align /
measure instructions.

#### 6. SweepPlan

Sweeps should be first-class and orthogonal to sequences.

They should represent:

- swept parameters
- dimensions and axes
- mapping from user parameters to operation parameters or acquisition settings
- averaging and repeat policy

This is essential because many cQED experiments are fundamentally sweep-driven
rather than circuit-driven.

#### 7. AcquisitionSpec

Acquisition should be explicit and independent from the sequence body.

It should describe:

- what is measured
- whether the result is IQ, state discrimination, populations, or traces
- integration weights or resolved measurement configuration
- buffering and stream processing expectations

This separates "how to probe" from "what pulse sequence to run".

#### 8. Backend Adapter

Keep backend-specific lowering in `backends/qm/`.

Responsibilities:

- resolve calibrated operations
- lower sequences, sweeps, and acquisition to QUA
- validate backend support for features such as real-time branching
- emit inspection objects and compiled program metadata

Do not let experiment templates import QUA directly.

#### 9. AnalysisPipeline

Move toward reusable analysis pipelines instead of embedding fit logic in every
experiment class.

A pipeline should define:

- expected input channels
- preprocessing
- fit model selection
- quality metrics
- patch proposal hooks when relevant
- plotting helpers

#### 10. ResultBundle

Unify output around one result object with:

- raw data
- coordinate axes
- resolved experiment spec
- resolved calibration snapshot
- compiler report
- analysis outputs
- artifact paths

This becomes the default object returned by runs.

## cQED-Specific Design Requirements

The architecture must explicitly support cQED realities rather than pretending
all experiments are digital circuits.

### Multi-Element Systems

The model must support multiple physical elements with different roles:

- qubit
- resonator
- storage cavity
- higher transitions such as `ef`
- flux and control lines when present

Operations should target typed physical handles, not generic labels only.

### Calibration-Aware Control

Operations must resolve through calibration data. Users should call semantic
operations, not manually manage waveform objects for standard work.

Examples:

- `ops.x90("q0")` should use the current calibrated pulse definition
- `ops.measure("rr0", mode="ge")` should resolve the current readout
  discriminator and integration weights

### Active Reset and Feedback

The model must represent:

- real-time branch-capable active reset
- discriminator-driven reset criteria
- loop-until-ground or bounded retry semantics

This belongs in protocol or workflow layers with explicit backend capability
checks.

### Spectroscopy and Sweep-Heavy Work

Spectroscopy does not naturally fit a pure gate-only model. It needs:

- sweep axes over frequency, amplitude, duration, and sometimes power
- simple repeated probe patterns
- explicit acquisition configuration
- convenient plotting of linecuts and heatmaps

That is why sweeps and acquisition should not be hidden inside gate objects.

### Primitive Operations and Composed Protocols

The system should support both:

- reusable primitive operations such as rotations, waits, measurements, and
  displacements
- experiment-specific composed blocks such as Ramsey bodies, echo blocks,
  active reset loops, and cavity preparation sequences

### Inspection

Users must be able to inspect:

- resolved sequence structure
- applied calibrations
- compiled QUA summary
- expected timeline or pulse schedule visualization

Inspection must be treated as a first-class feature, not a debugging afterthought.

## Circuit and Gate Abstraction Analysis

### Should QuantumCircuit Be the Main Entry Point?

Not universally.

A circuit abstraction is useful for:

- custom coherent control sequences
- gate calibration bodies
- repeated control motifs
- tomography-like pulse ordering
- active reset or feedback blocks with explicit sequencing

It is less natural as the top-level abstraction for:

- coarse or fine spectroscopy
- wide parameter scans
- multi-stage calibrations
- experiment families that are primarily "sequence + sweep + analysis"

So the right answer is:

- yes, keep a circuit or sequence abstraction
- no, do not force every experiment through it as the only user-facing model

### What Should Count as a Gate?

Use "gate" narrowly.

A `QuantumGate` should mean a meaningful calibrated control operation that is
close to a unitary or named control primitive, for example:

- `X90`
- `X180`
- `Y90`
- `VirtualZ`
- `Displacement`
- `SNAP`
- `SQR`

Do not overload the word "gate" to include every time-ordered operation.

### Should Measurement Be a Gate?

No. Measurement should be an `Acquire` or `Measure` operation, not a gate.

It can appear inside a sequence, but it is semantically different:

- it resolves discriminator and integration configuration
- it may emit IQ or classified states
- it interacts with stream processing and sometimes feedback

Treating it as a gate makes the model less clear.

### Do Spectroscopy Experiments Fit Naturally into a Circuit Model?

Only partially.

They often have a trivial sequence body but a rich sweep definition. If the
top-level API is forced to be circuit-centric, spectroscopy becomes awkward and
users will end up encoding sweep semantics in unnatural places.

The better model is:

- simple sequence body
- explicit sweep plan
- explicit acquisition
- experiment template that binds them together

### How Should Parameter Sweeps Be Represented?

Sweeps should be explicit objects. They should not be encoded as pseudo-gates
or hidden in compiler metadata.

Represent:

- axis name
- target parameter path
- values or generators
- nesting order
- averaging policy
- optional adaptive policy later

### How Should Calibration-Aware Gates Behave?

Operations should reference calibrated definitions, not contain permanent
waveforms.

Recommended behavior:

- the operation stores semantic intent and user overrides
- the calibration layer resolves the canonical pulse or operation recipe
- the backend compiler lowers the resolved recipe into QUA

This keeps calibration updates centralized.

### Should Gates Own Waveforms?

No for standard operations.

Waveform ownership inside gates leads to duplication and calibration drift. A
custom low-level escape hatch can still exist for expert workflows, but it
should be explicit and uncommon.

### How to Support Reusable Primitives and Custom Sequences

Use both:

- a standard operation library for common calibrated primitives
- a composable sequence builder for custom protocols

That gives new users a small friendly surface and advanced users an escape hatch
without forcing everything into backend-specific code.

## Proposed User-Facing API Style

The top-level API should feel experiment-first, with a clear path to custom
sequences.

### Qubit Spectroscopy

```python
from qubox_v2 import Session

session = Session.open(sample_id="sampleA", cooldown_id="cd2026_03_13")

result = session.exp.qubit.spectroscopy(
    qubit="q0",
    readout="rr0",
    freq=session.sweep.linspace(-30e6, 30e6, 241, center="q0.ge"),
    drive_amp=0.02,
    n_avg=200,
)

result.plot()
result.fit.summary()
```

### Power Rabi

```python
result = session.exp.qubit.power_rabi(
    qubit="q0",
    readout="rr0",
    amplitude=session.sweep.linspace(0.0, 0.25, 101),
    pulse="x180",
    n_avg=500,
)

pi_amp = result.analysis["pi_amp"]
```

### Ramsey

```python
result = session.exp.qubit.ramsey(
    qubit="q0",
    readout="rr0",
    delay=session.sweep.geomspace(16, 20_000, 81, unit="ns"),
    detuning=0.5e6,
    prep="x90",
    final="x90",
    n_avg=1000,
)
```

### Active Reset

```python
result = session.exp.reset.active(
    qubit="q0",
    readout="rr0",
    threshold="calibrated",
    max_attempts=5,
    verify=True,
    n_avg=200,
)
```

### Custom Composed Sequence

```python
seq = session.sequence()
seq.add(session.ops.x90("q0"))
seq.add(session.ops.wait("q0", 200))
seq.add(session.ops.virtual_z("q0", phase=0.25))
seq.add(session.ops.x90("q0"))
seq.add(session.ops.measure("rr0", mode="iq"))

result = session.exp.custom(
    sequence=seq,
    sweep=session.sweep.param("wait.duration").values([100, 200, 400, 800]),
    analysis="ramsey_like",
    n_avg=500,
)
```

### Two-Dimensional Sweep

```python
result = session.exp.custom(
    sequence=seq,
    sweep=session.sweep.grid(
        session.sweep.param("drive.frequency").linspace(-10e6, 10e6, 101),
        session.sweep.param("drive.amplitude").linspace(0.0, 0.20, 41),
    ),
    acquire=session.acquire.iq("rr0"),
    n_avg=100,
)
```

### Calibration Workflow

```python
workflow = session.workflow.readout.full(
    qubit="q0",
    readout="rr0",
    update_store=False,
)

report = workflow.run()
report.review()
report.apply()
```

This API is concise, readable, and still leaves room for backend-specific
inspection under the hood.

## Proposed Directory and Module Layout

The exact naming can vary, but the structure should separate experiment intent
from backend lowering.

```text
qubox_v2/
  session/
    session.py
    context.py
    registry.py
    artifacts.py

  experiments/
    templates/
      spectroscopy.py
      rabi.py
      coherence.py
      relaxation.py
      cavity.py
      readout.py
      reset.py
    workflows/
      readout_calibration.py
      gate_calibration.py
      mixer_calibration.py
    custom/
      custom_experiment.py

  sequence/
    sequence.py
    block.py
    control_flow.py
    sweep.py
    acquisition.py
    inspection.py

  operations/
    primitives.py
    cavity.py
    measurement.py
    reset.py
    library.py

  calibration/
    store.py
    resolver.py
    measurement.py
    workflows.py
    patch_rules.py

  backends/
    base/
      compiler.py
      runtime.py
      capabilities.py
    qm/
      compiler.py
      lowering.py
      measurement.py
      runtime.py
      inspect.py
      simulator.py

  analysis/
    pipelines/
      spectroscopy.py
      rabi.py
      ramsey.py
      t1.py
      readout.py
    fitting/
    plotting/
    report.py

  data/
    result_bundle.py
    coordinates.py
    artifacts.py
    schemas.py

  devices/
    targets.py
    hardware_definition.py
    frequency_plan.py

  compat/
    legacy_experiments.py
    legacy_measurement.py
    legacy_cqed_attributes.py
```

Important policy decisions:

1. New code should enter through `experiments/templates`, `workflows`,
   `sequence`, and `operations`.
2. QM-specific code should stay under `backends/qm/`.
3. Legacy experiment classes should be preserved temporarily under a clearly
   marked compatibility layer.

## Documentation Strategy

The documentation needs a more explicit learning path.

### Core Documentation

Add or fix:

1. A root `README.md` that answers:
   - what qubox is
   - who it is for
   - what the primary workflow is
   - where to start
2. A "Getting Started" guide that walks through:
   - opening a session
   - selecting a device target
   - running a standard experiment
   - inspecting results
3. A "Concepts" section that explains:
   - session
   - experiment template
   - sequence
   - sweep
   - acquisition
   - calibration store
   - backend adapter

### Tutorials

Add tutorials that map directly to experimental goals:

1. Run your first resonator spectroscopy
2. Run qubit spectroscopy and update frequency
3. Calibrate pi amplitude with power Rabi
4. Run Ramsey and interpret detuning
5. Build a custom sequence with standard operations
6. Run a full readout calibration workflow
7. Inspect the compiled QM program and pulse schedule

### API Reference

The API reference should describe only the supported public path for new users.
If compatibility APIs remain, they should be marked as such.

It should cover:

- session entry points
- standard experiment templates
- workflow entry points
- sequence builder
- operation library
- sweep and acquisition APIs
- result bundle and analysis access
- backend inspection hooks

### Calibration Documentation

Calibration docs should explicitly answer:

- where calibration lives
- how it is resolved into operations
- how readout configuration is selected
- how patch proposals are reviewed and applied
- what the source of truth is

### Backend Documentation

QM-specific docs should explain:

- what is lowered to QUA
- what is resolved from calibration at compile time
- which features rely on backend real-time branching
- how simulator-backed validation works
- known limitations

The repository should also add the currently missing
`limitations/qua_related_limitations.md` once validated backend limitations are
collected.

## Migration Roadmap

### Quick Wins

1. Add a root `README.md`.
2. Make `SessionManager` documentation match the actual required
   sample / cooldown constructor.
3. Declare one official top-level API for new users and mark everything else as
   compatibility or advanced.
4. Stop silent fallback from circuit-oriented paths to legacy builders.
5. Either adopt `experiments/configs.py` in real production flows or remove it
   from the advertised primary API.
6. Create an executable trust suite from `standard_experiments.md`.
7. Unify default run artifact saving behind one result bundle contract.

These changes provide immediate clarity without large rewrites.

### Medium-Term Structural Changes

1. Introduce `ExperimentTemplate`, `Workflow`, `Sequence`, `SweepPlan`, and
   `AcquisitionSpec`.
2. Wrap `measureMacro` behind a session-owned measurement runtime, then route
   all new code through that wrapper.
3. Make `CalibrationStore` the only accepted calibration truth for new code.
4. Port a small representative set of experiments first:
   - qubit spectroscopy
   - resonator spectroscopy
   - power Rabi
   - Ramsey
   - GE discrimination
   - active reset
5. Move multi-stage calibration flows into dedicated workflow modules.
6. Consolidate pulse operation resolution into one canonical operation library.

### Long-Term Redesign

1. Retire the old `CircuitRunner.compile(...)` dispatch path.
2. Promote one compiler path for all sequence-shaped experiments.
3. Reduce `cQED_attributes` to a compatibility snapshot generated from
   `CalibrationStore`.
4. Replace ad hoc measurement state with one measurement configuration model.
5. Keep backend extension possible, but do not weaken QM correctness in pursuit
   of abstract generality.

## Risks and Tradeoffs

1. If the architecture becomes too circuit-centric, spectroscopy and
   calibration workflows will become awkward.
2. If backend abstraction is pushed too early, QM faithfulness may degrade.
3. If measurement refactoring is too abrupt, mature readout workflows may break.
4. If compatibility layers stay forever, the refactor will not actually improve
   usability.
5. If typed config objects become mandatory too early, notebook iteration may
   feel slower for exploratory users.

The migration should therefore be progressive, not revolutionary.

## Final Recommendations

1. Preserve the sample / cooldown session model and the calibration store
   foundation.
2. Make experiment templates, not raw circuit objects, the primary API for
   common lab work.
3. Keep `QuantumCircuit` or `Sequence` as the ordered protocol abstraction for
   custom and sequence-shaped experiments.
4. Treat sweeps and acquisition as first-class objects rather than hidden
   circuit metadata.
5. Resolve operations through calibration instead of letting gates own
   waveforms.
6. Replace the global measurement singleton with a session-owned runtime path
   for all new code.
7. Consolidate to one compiler path and one artifact contract.
8. Turn `standard_experiments.md` into an executable simulator-backed trust
   suite before expanding abstractions further.

## Bottom Line

The repository should not start its next phase by inventing one more
abstraction. It should start by choosing which of the existing good ideas become
canonical.

The best target is:

- `Session` for runtime context
- experiment templates for standard physics workflows
- sequences for custom ordered control
- sweeps and acquisition as explicit orthogonal objects
- calibration-backed operation resolution
- one QM backend adapter
- one result and analysis contract

That architecture matches real cQED work more naturally than a pure
circuit-first model, and it gives new lab members a clearer path from
"I want to run experiment X" to "I know which API to use."
