# Gate-Protocol-Circuit Architecture

## Scope

This design adds a gate-driven circuit pipeline without replacing legacy builders.

- Legacy `programs/builders/*` flows remain intact.
- `measureMacro` remains available and is still the lowering path for measurement.
- `SessionState` hashing and artifact layout are unchanged.
- The canonical intent IR stays in `qubox_v2/programs/circuit_runner.py`.

## Canonical IR

The canonical intent representation is still:

- `IntentGate = Gate`
- `Circuit = QuantumCircuit`

Key IR types in `qubox_v2/programs/circuit_runner.py`:

- `Gate`
  - canonical intent gate
  - supports targets, logical params, tags, stable names, optional runtime `condition`, and metadata
- `ParameterSource`
  - parameter precedence contract:
    - `override`
    - calibration lookup via `CalibrationReference`
    - `cQED_attributes` fallback
    - `default`
    - error
- `GateCondition`
  - explicit runtime branch intent attached to a gate
- `ConditionalGate`
  - helper that wraps an existing `Gate`; it is not a second IR
- `QuantumCircuit`
  - ordered gate list
  - structural protocol blocks
  - explicit measurement schema
  - stable text and display output
- `CircuitBlock`
  - structural grouping for protocol blocks
  - carries display-relevant metadata such as `analysis_only` versus `real_time_branching_requested`

## Measurement Schema

Measurement schema is attached to the circuit and lives in `qubox_v2/programs/circuit_runner.py`.

- `StreamSpec`
  - local stream name such as `I` or `Q`
  - QUA type
  - shape
  - aggregation
- `MeasurementRecord`
  - record key
  - kind
  - operation
  - local stream definitions
  - optional `StateRule`
  - optional `derived_state_name`
  - computed output names:
    - IQ streams are emitted as `<measure_key>.I` and `<measure_key>.Q`
    - derived state is addressed as `<measure_key>.<derived_state_name>`
- `MeasurementSchema`
  - ordered collection of `MeasurementRecord`
  - stable text/payload rendering
  - `validate()` enforces:
    - non-empty unique record keys
    - required IQ streams for IQ measurement
    - unique local stream names per record
    - unique emitted output names across the schema
    - valid shape and aggregation declarations
    - no claimed state output unless a real bool stream exists
    - no derived-state name without a `StateRule`

## IQ Acquisition Versus State Derivation

The hard contract is now:

- compilation emits IQ acquisition only
- compilation records state-derivation metadata only
- analysis/post-processing applies `derive_state()`

`StateRule` and `derive_state()` live in `qubox_v2/programs/measurement.py`.

`compile_v2` does not perform IQ-to-state conversion inside QUA lowering.

Instead, `qubox_v2/programs/circuit_compiler.py`:

- resolves `StateRule` parameters during compilation for provenance
- records those resolved values in the resolution report
- attaches a post-processing processor via `ProgramBuildResult.processors`

The post-processing helper lives in `qubox_v2/programs/circuit_postprocess.py`.

That processor:

- consumes emitted IQ outputs such as `active_reset_m0.I` and `active_reset_m0.Q`
- applies `derive_state()`
- writes derived boolean output such as `active_reset_m0.state`

## Protocol Layer

Pure protocol builders live in `qubox_v2/programs/circuit_protocols.py`.

- `RamseyProtocol`
  - `X90 -> Idle(tau) -> X90 -> MeasureIQ`
- `EchoProtocol`
  - `X90 -> Idle(tau/2) -> X180 -> Idle(tau/2) -> X90 -> MeasureIQ`
- `ActiveResetProtocol`
  - always emits IQ measurement plus a `StateRule`
  - `enable_real_time_branching=False`
    - analysis-only mode
    - structural block metadata carries explicit analysis steps
    - display shows `MeasureIQ -> derive_state(...) -> external/next-shot conditional action`
  - `enable_real_time_branching=True`
    - emits an explicit conditional gate in the IR
    - display marks the block as real-time branch requested
    - `compile_v2` raises a loud error unless a true QUA branch implementation exists

Protocols do not emit QUA and do not touch hardware or macros.

## Display Layer

Display code lives in `qubox_v2/programs/circuit_display.py`.

- `QuantumCircuit.to_diagram_text()`
  - always available
  - shows gate order, lane rows, protocol block rows, warnings, measurement schema, and explicit analysis/branch sections
- `QuantumCircuit.draw()` / `display()`
  - matplotlib timeline view
  - protocol blocks are structural, not cosmetic
  - analysis-only blocks are visually marked differently from ordinary protocol blocks
  - conditional gates are rendered with explicit branch intent

Display honesty rules:

- analysis-only logic is shown as post-run analysis, not as a QUA branch
- real-time branch requests are shown as requested branches, not silently lowered

## Compiler / Runner v2

The lowering path lives in `qubox_v2/programs/circuit_compiler.py`.

Entry points:

- `CircuitRunnerV2.compile(circuit, *, n_shots=None) -> ProgramBuildResult`
- `CircuitRunner.compile_v2(...)`
- `CircuitRunner.compile_program(...)`

Compiler responsibilities:

- walk gates in order
- validate measurement schema before lowering
- resolve parameters and provenance
- resolve base frequencies and emit IF updates when needed
- lower:
  - `idle` / `wait`
  - `frame_update`
  - `play_pulse`
  - `qubit_rotation`
  - `displacement`
  - `sqr`
  - `measure_iq`
- emit stream processing using explicit namespaced measurement outputs
- attach post-processing processors for derived-state analysis

Real-time branching contract:

- conditions on raw QUA measurement variables may still be lowered if supported
- conditions on post-processed derived state are rejected explicitly
- there is no silent no-op lowering

## Output Contract

`CircuitRunnerV2.compile()` returns a standard `ProgramBuildResult` with:

- `program`
- `n_total`
- `processors`
  - includes post-run state derivation when `StateRule` is present
- `resolved_frequencies`
- `resolved_parameter_sources`
- `measure_macro_state`
- `metadata`
  - `circuit_text`
  - `diagram_text`
  - `measurement_schema`
  - `display_blocks`
  - `resolution_report`
  - `resolution_report_text`
  - `instruction_trace`
  - `post_processing`
  - `compiler_warnings`

Instruction trace semantics:

- trace contains only QUA-time behavior
- analysis-only `derive_state` does not appear in the instruction trace

## Cluster Selection Audit

### Legacy experiment paths

Legacy experiment execution is unchanged.

Cluster selection for legacy paths occurs where QM connections are constructed:

- `qubox_v2/experiments/session.py`
  - `Session(...)` builds `QuantumMachinesManager(host=..., cluster_name=cluster_name, ...)`
- `qubox_v2/hardware/qua_program_manager.py`
  - `QuaProgramManager(...)` builds `QuantumMachinesManager(host=qop_ip, cluster_name=cluster_name)`

After construction, legacy runs continue through:

- `ExperimentBase.run_program()` in `qubox_v2/experiments/experiment_base.py`
- `ProgramRunner.run_program()` in `qubox_v2/hardware/program_runner.py`

This hardening work does not modify those legacy cluster defaults or flows.

### New circuit execution path

The new guarded runner lives in `qubox_v2/programs/circuit_execution.py`.

Entry point:

- `run_compiled_circuit(session, circuit, cluster="Cluster_1", run_on_opx=False, ...)`

Guard behavior:

- only `Cluster_1` is accepted
- `Cluster_2` is rejected immediately
- default mode is compile/display only
- hardware execution requires `run_on_opx=True`
- ambiguous or mismatched session cluster bindings abort
- the helper does not open a QM or change global session defaults

Cluster selection for the new path is therefore local to `circuit_execution.py`.

## Example

`qubox_v2/examples/circuit_architecture_demo.py` demonstrates Ramsey and Echo circuit build/display/compile flows. It remains dry-run by default.

## Test Surface

Primary coverage lives under `tests/gate_architecture/`.

The suite covers:

- parameter precedence and pulse implementation selection
- measurement schema validation
- Ramsey and Echo compilation
- active-reset analysis-only versus requested real-time branch behavior
- post-run state derivation processors
- honest text/matplotlib display behavior
- namespaced measurement outputs and golden snapshots
- Cluster_1-only execution guard behavior
