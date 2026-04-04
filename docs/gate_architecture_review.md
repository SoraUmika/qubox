# Gate → Protocol → Circuit → Backend Architecture — Review Memo

> **Historical document (2025-01).** This reviews the gate/circuit architecture
> that has since been narrowed. `qubox.gates` now contains only runtime
> hardware gate implementations; the gate-model, fidelity, noise, and
> gate-sequence layers described here were removed. See
> [API Reference §2](../API_REFERENCE.md) for the current package layout.

**Date**: 2025-01  
**Scope**: Documentation & review only.  No code refactoring.

---

## 1. Module Inventory

| Module | Lines | Responsibility |
|--------|------:|----------------|
| `programs/circuit_runner.py` | 1 058 | Canonical IR types (`Gate`, `QuantumCircuit`, `ParameterSource`, `MeasurementSchema`, etc.), legacy `CircuitRunner`, `compile_v2` bridge, factory helpers |
| `programs/circuit_compiler.py` | 1 160 | `CircuitRunnerV2.compile()` — lowers intent gates to QUA programs.  Parameter resolution, frequency management, gate lowering dispatch, resolution report |
| `programs/circuit_protocols.py` | 249 | Pure protocol builders: `RamseyProtocol`, `EchoProtocol`, `ActiveResetProtocol` + convenience `make_*_circuit()` wrappers |
| `programs/circuit_display.py` | 384 | `circuit_to_diagram_text()` (text) and `draw_circuit()` (matplotlib) |
| `programs/circuit_execution.py` | ~160 | Cluster-guarded execution: `run_compiled_circuit()`, `SAFE_OPX_CLUSTER = "Cluster_1"` |
| `programs/circuit_postprocess.py` | ~60 | `build_state_derivation_processor()` — post-run IQ → state derivation |
| `programs/measurement.py` | ~220 | `StateRule`, `derive_state()`, `MeasureSpec`, `emit_measurement_spec()` |
| `examples/circuit_architecture_demo.py` | ~45 | Demo entry point: build, display, compile Ramsey/Echo without hardware |
| `tests/gate_architecture/` | — | 17 tests + 6 golden files + fixture conftest (467 lines) |

---

## 2. Public API Entry Points

### 2.1 IR Types (all in `qubox_v2_legacy.programs.circuit_runner`)

| Type | Kind | Key Fields |
|------|------|------------|
| `Gate` | `@dataclass(frozen=True)` | `name`, `target`, `params`, `duration_clks`, `tags`, `instance_name`, `condition`, `metadata` |
| `QuantumCircuit` | `@dataclass(frozen=True)` | `name`, `gates`, `metadata`, `measurement_schema`, `blocks` |
| `ParameterSource` | `@dataclass(frozen=True)` | `calibration`, `override`, `attr_fallback`, `default`, `required` |
| `CalibrationReference` | `@dataclass(frozen=True)` | `namespace`, `key`, `field` |
| `GateCondition` | `@dataclass(frozen=True)` | `measurement_key`, `source`, `comparator`, `value` |
| `ConditionalGate` | `@dataclass(frozen=True)` | `gate`, `condition` — helper, not a second IR node |
| `CircuitBlock` | `@dataclass(frozen=True)` | `label`, `start`, `stop`, `block_type`, `lanes`, `metadata` |
| `StreamSpec` | `@dataclass(frozen=True)` | `name`, `qua_type`, `shape`, `aggregate` |
| `MeasurementRecord` | `@dataclass(frozen=True)` | `key`, `kind`, `operation`, `with_state`, `streams`, `state_rule`, `derived_state_name` |
| `MeasurementSchema` | `@dataclass(frozen=True)` | `records` — with `validate()` and `to_payload()` |
| `IntentGate` | alias | `= Gate` |
| `Circuit` | alias | `= QuantumCircuit` |

### 2.2 Protocols (`qubox_v2_legacy.programs.circuit_protocols`)

| Class / Function | Produces |
|------------------|----------|
| `RamseyProtocol(qubit, readout, tau_clks, …).build()` | X90 → Idle(τ) → X90 → MeasureIQ |
| `EchoProtocol(qubit, readout, tau_clks, …).build()` | X90 → Idle(τ/2) → X180 → Idle(τ/2) → X90 → MeasureIQ |
| `ActiveResetProtocol(qubit, readout, …).build()` | MeasureIQ (analysis-only default; `enable_real_time_branching=True` adds conditional gate that correctly fails at compile time) |
| `make_ramsey_circuit(**kw)` | Shorthand → `RamseyProtocol(**kw).build()` |
| `make_echo_circuit(**kw)` | Shorthand → `EchoProtocol(**kw).build()` |
| `make_active_reset_circuit(**kw)` | Shorthand → `ActiveResetProtocol(**kw).build()` |

### 2.3 Compiler (`qubox_v2_legacy.programs.circuit_compiler`)

| Class / Method | Return Type |
|---------------|-------------|
| `CircuitRunnerV2(session).compile(circuit, n_shots=None)` | `ProgramBuildResult` (from `experiments.result`) |

Legacy bridge in `CircuitRunner`:

| Method | Route |
|--------|-------|
| `CircuitRunner.compile_v2(circuit, *, n_shots=None)` | Delegates to `CircuitRunnerV2(session).compile()` |
| `CircuitRunner.compile_program(circuit, *, n_shots=None)` | Alias for `compile_v2()` |

### 2.4 Display (`qubox_v2_legacy.programs.circuit_display`)

| Function | Return |
|----------|--------|
| `circuit_to_diagram_text(circuit, *, cell_width=20)` | `str` — ASCII diagram with lanes, blocks, analysis, branches, schema |
| `draw_circuit(circuit, figsize=None, save_path=None, include_gate_names=False)` | `matplotlib.Figure` |

`QuantumCircuit` delegates via:
- `.to_diagram_text(cell_width=20)` → `circuit_to_diagram_text`
- `.draw(…)` / `.display(…)` / `.draw_logical(…)` → `draw_circuit`

### 2.5 Execution (`qubox_v2_legacy.programs.circuit_execution`)

| Function | Default | Notes |
|----------|---------|-------|
| `run_compiled_circuit(session, circuit, cluster="Cluster_1", run_on_opx=False, …)` | dry-run | Returns `CompiledCircuitExecution` |

Safety guardrails:
- Only `Cluster_1` accepted; `Cluster_2` → immediate `ValueError`.
- Default `run_on_opx=False` — compile + diagram only.
- Ambiguous cluster → `RuntimeError`.

### 2.6 Post-Processing

| Function / Module | Purpose |
|-------------------|---------|
| `build_state_derivation_processor(schema, resolved_rules)` (`circuit_postprocess`) | Returns `Callable` that maps `{key.I, key.Q}` → `{key.state}` via `derive_state()` |
| `derive_state(iq, rule)` (`measurement`) | NumPy vectorised I-threshold with optional rotation |
| `StateRule(kind, threshold, sense, rotation_angle, metadata)` (`measurement`) | Post-processing rule dataclass |

---

## 3. Design Assessment

### 3.1 Strengths

1. **Single IR, no split**.  `Gate` and `QuantumCircuit` are the sole intent
   representation.  The `IntentGate = Gate` / `Circuit = QuantumCircuit`
   aliases avoid a second IR.

2. **Measurement honesty**.  `compile_v2` emits IQ acquisition only at
   QUA-program time; state derivation is explicitly deferred to
   `build_state_derivation_processor` and attached to
   `ProgramBuildResult.processors`.  `MeasurementSchema.validate()` rejects
   `with_state=True` claims because compilation never produces real-time state.

3. **Parameter precedence is explicit**.  `ParameterSource` documents the
   four-tier resolution order: override → calibration → cQED_attributes → default.
   The compiler's `_resolve_param()` faithfully implements this chain.

4. **Protocol purity**.  `RamseyProtocol.build()` et al. are zero-side-effect
   factories that return fully-formed `QuantumCircuit` objects.

5. **Cluster safety**.  Hard-coded `SAFE_OPX_CLUSTER = "Cluster_1"` with
   zero tolerance for mismatch.

6. **Display honesty**.  Analysis-only blocks render with `[analysis-only]`
   annotations.  Conditional gates that _cannot_ compile to real-time QUA
   branches are documented honestly in the diagram and the compilation
   raises immediately when attempted.

7. **Golden-file tests**.  Six golden files lock the diagram text, circuit
   text, resolution report, and measurement schema, preventing silent drift.

### 3.2 Observations & Potential Improvements

| # | Area | Observation | Impact | Suggested Action |
|---|------|-------------|--------|------------------|
| 1 | **Module size** | `circuit_runner.py` (1 058 lines) holds both IR types and the entire legacy `CircuitRunner` with 5 compile paths plus pulse visualization.  `circuit_compiler.py` (1 160 lines) is similarly dense. | Readability | Future: split IR types into `circuit_ir.py`, keep legacy runner and V2 compiler in separate files.  No action now. |
| 2 | **`_UNSET` sentinel** | Defined in `circuit_runner.py` and imported by `circuit_compiler.py`.  It is a module-private name but used cross-module. | Minor API hygiene | Consider promoting to `UNSET` or moving to a shared constants file in the future. |
| 3 | **Target aliasing** | `_resolve_target()` in `CircuitRunnerV2` maps `"qubit"` → `attr.qb_el`, `"readout"` → `attr.ro_el`, etc.  This map is inline and undocumented. | Discoverability | Document the canonical alias table in the README section below. |
| 4 | **`compile_program` vs `compile_v2`** | Two names for the same bridge on `CircuitRunner`.  `compile_program` is an alias for `compile_v2`.  | Naming | Recommend deprecating one.  No action now. |
| 5 | **Real-time branching** | `ActiveResetProtocol(enable_real_time_branching=True)` builds a circuit with a `ConditionalGate` referencing derived state, then the compiler correctly raises `RuntimeError`. | Correctness | Correct behavior per "IQ-only" design.  A future real-time branch path would need a separate gate type (e.g. `measure_and_branch`) that emits QUA `if_()` with a threshold variable. |
| 6 | **Frequency resolution fallback chain** | `_base_frequency_for()` tries calibration → attributes.  `_lo_frequency_for()` tries hardware → bindings.  Failure modes produce clear `ValueError`s. | Correct | No action. |
| 7 | **Test location** | Tests live under `e:\qubox\tests\gate_architecture\`, outside the `qubox_v2_legacy/tests/` tree. | Project layout consistency | Acceptable for isolation.  Consider merging into `qubox_v2_legacy/tests/` if the project standardizes on a single test root. |
| 8 | **`MeasurementSchema.validate()` is explicit-call** | Schema validation is invoked manually by the compiler, not enforced at construction time (`__post_init__`). | Flexibility | Correct choice — allows building partial schemas during protocol construction before final validate. |

### 3.3 Naming Consistency Check

| Design Doc Name | Actual Code Name | Match? |
|----------------|-----------------|--------|
| `IntentGate` | `Gate` + alias `IntentGate = Gate` | ✓ |
| `Circuit` | `QuantumCircuit` + alias `Circuit = QuantumCircuit` | ✓ |
| `CircuitRunnerV2.compile()` | `CircuitRunnerV2.compile(circuit, n_shots=None)` | ✓ |
| `CircuitRunner.compile_v2()` | exists as bridge method | ✓ |
| `RamseyProtocol`, `EchoProtocol`, `ActiveResetProtocol` | class names match | ✓ |
| `run_compiled_circuit()` | function name matches | ✓ |
| `derive_state()` | in `measurement.py`, matches | ✓ |
| `StateRule` | `@dataclass(frozen=True)` in `measurement.py` | ✓ |

All names in `architecture_design.md` match their implementations.

---

## 4. Test Coverage Summary

**File**: `tests/gate_architecture/test_gate_architecture.py` (399 lines, 17 tests)

| Test Name | What It Verifies |
|-----------|-----------------|
| `test_single_qubit_rotation_override_beats_calibration_and_policy_selection` | ParameterSource override takes precedence; drag/gaussian/square policies produce distinct waveforms |
| `test_derive_state_supports_rotation_and_sense` | `derive_state()` with rotation_angle and both `greater`/`less` senses |
| `test_measurement_schema_validate_accepts_iq_outputs_and_namespaced_streams` | Valid IQ schema validates; `output_name` is `<key>.<stream>` |
| `test_measurement_schema_validate_rejects_missing_q_stream` | Missing Q stream → `ValueError` |
| `test_measurement_schema_validate_rejects_false_state_claim` | `with_state=True` without state_rule → `ValueError` |
| `test_ramsey_protocol_compilation_sequence_schema_and_diagram` | Ramsey gate sequence, trace ops, stream names, schema correctness |
| `test_echo_protocol_compilation_sequence` | Echo gate sequence and trace ops |
| `test_active_reset_defaults_to_analysis_only` | Analysis-only mode: no real-time branch, derives state post-run |
| `test_active_reset_post_processing_derives_state_after_run` | Processor maps IQ → boolean state correctly |
| `test_active_reset_real_time_branching_fails_loudly` | `enable_real_time_branching=True` → `RuntimeError` at compile time |
| `test_frequency_resolution_records_base_plan_and_update_order` | Frequency resolution chain, detune, update_frequency trace entry |
| `test_display_plot_groups_protocol_block` | Matplotlib figure has expected patches |
| `test_cluster1_runner_dry_run_is_default` | Default = dry-run, no hardware calls |
| `test_cluster1_runner_rejects_any_other_cluster` | Cluster_2 → `ValueError` |
| `test_cluster1_runner_requires_unambiguous_cluster_for_hardware_run` | Missing cluster_name → `RuntimeError` |
| `test_cluster1_runner_executes_only_when_explicit` | `run_on_opx=True` → actual execution |
| Golden-file tests (×5) | Lock circuit text, diagram, resolution report, measurement schema, analysis snapshot against checked-in golden files |

**Conftest** (467 lines): provides `fake_session` with stub QM/QUA fakes, a
`FakePulseManager`, and fake calibration data — fully offline, no imports
from `qm.qua` at fixture level.

---

## 5. Conclusion

The implementation faithfully follows `architecture_design.md`.  All naming
matches, the IQ-only measurement contract is enforced, and the safety rails
(Cluster_1 only, dry-run default, real-time branch rejection) work as
designed.  The golden-file test suite provides regression protection for the
full compile → display → schema pipeline.

No code changes recommended at this time.  The observations in §3.2 are
informational items for future consideration.
