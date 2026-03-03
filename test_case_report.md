# Gate Architecture Test Case Report

## Scope

This report covers the hardened Gate -> Protocol -> Circuit -> Backend feature area:

- intent gates and protocol builders
- `compile_v2` lowering and resolution reporting
- honest circuit display
- measurement schema invariants
- post-run state derivation
- Cluster_1-only guarded execution

Primary test file:

- `tests/gate_architecture/test_gate_architecture.py`

Supporting fixture/stub file:

- `tests/gate_architecture/conftest.py`

## Summary

| Category | Passed | Skipped | Notes |
| --- | ---: | ---: | --- |
| Parameter resolution and pulse policy | 1 | 0 | Override precedence and waveform policy selection |
| Post-processing helpers | 2 | 0 | `derive_state()` and post-run processor behavior |
| Measurement schema validation | 3 | 0 | Accept and reject representative schema shapes |
| Protocol compilation and display | 6 | 0 | Ramsey, Echo, Active Reset, frequency ordering, matplotlib grouping |
| Cluster guard | 4 | 0 | Dry-run default, Cluster_2 hard-fail, ambiguity checks, explicit execution |
| Golden snapshots | 6 | 0 | Circuit text, diagrams, resolution reports, schema, hardened active-reset snapshot |
| Total feature-area tests | 22 | 0 | `pytest tests/gate_architecture/test_gate_architecture.py -q` |

Full repository regression at the end of this hardening pass:

| Suite | Passed | Skipped | Command |
| --- | ---: | ---: | --- |
| Full repository | 79 | 3 | `pytest -q` |

## Test Inventory

| Test | File | Purpose | Verifies |
| --- | --- | --- | --- |
| `test_single_qubit_rotation_override_beats_calibration_and_policy_selection` | `tests/gate_architecture/test_gate_architecture.py` | Check logical qubit rotation parameter precedence and implementation policy routing. | Override amplitude beats calibration and drag/gaussian/square waveform selection stays policy-driven. |
| `test_derive_state_supports_rotation_and_sense` | `tests/gate_architecture/test_gate_architecture.py` | Validate raw helper behavior for IQ-to-state conversion. | `derive_state()` handles threshold sense and IQ rotation deterministically. |
| `test_measurement_schema_validate_accepts_iq_outputs_and_namespaced_streams` | `tests/gate_architecture/test_gate_architecture.py` | Confirm valid IQ schemas pass validation. | IQ schema validates and exposes deterministic namespaced output names such as `m0.I`. |
| `test_measurement_schema_validate_rejects_missing_q_stream` | `tests/gate_architecture/test_gate_architecture.py` | Reject incomplete IQ schemas. | `MeasurementSchema.validate()` fails when a required IQ stream is missing. |
| `test_measurement_schema_validate_rejects_false_state_claim` | `tests/gate_architecture/test_gate_architecture.py` | Reject dishonest schema declarations. | A record cannot claim produced state output without an actual bool stream. |
| `test_ramsey_protocol_compilation_sequence_schema_and_diagram` | `tests/gate_architecture/test_gate_architecture.py` | Validate the canonical Ramsey builder end to end. | Gate order, instruction trace, namespaced stream outputs, and diagram metadata all match the intended IQ-only contract. |
| `test_echo_protocol_compilation_sequence` | `tests/gate_architecture/test_gate_architecture.py` | Validate the canonical Echo builder end to end. | Echo emits the exact gate and lowering order expected by the protocol definition. |
| `test_active_reset_defaults_to_analysis_only` | `tests/gate_architecture/test_gate_architecture.py` | Verify the hardened default active-reset contract. | Active reset compiles as IQ-only plus post-processing metadata, emits no fake runtime branch, and labels analysis-only behavior explicitly in the display. |
| `test_active_reset_post_processing_derives_state_after_run` | `tests/gate_architecture/test_gate_architecture.py` | Verify that state derivation moved out of compilation. | The processor attached to `ProgramBuildResult.processors` derives `active_reset_m0.state` from IQ after the run. |
| `test_active_reset_real_time_branching_fails_loudly` | `tests/gate_architecture/test_gate_architecture.py` | Guard against misleading runtime-branch behavior. | Real-time branch intent is still visible in the circuit display, but `compile_v2` raises explicitly because derived-state branching is not lowered silently. |
| `test_frequency_resolution_records_base_plan_and_update_order` | `tests/gate_architecture/test_gate_architecture.py` | Validate resolved frequency reporting and trace ordering. | Base RF plan lands in `ProgramBuildResult.resolved_frequencies` and IF update happens before playback. |
| `test_display_plot_groups_protocol_block` | `tests/gate_architecture/test_gate_architecture.py` | Smoke-test the matplotlib display path. | Protocol blocks and gate boxes render together without collapsing the structural grouping metadata. |
| `test_cluster1_runner_dry_run_is_default` | `tests/gate_architecture/test_gate_architecture.py` | Verify the safe default execution path. | `run_compiled_circuit()` defaults to compile/display only and does not call hardware. |
| `test_cluster1_runner_rejects_any_other_cluster` | `tests/gate_architecture/test_gate_architecture.py` | Enforce the Cluster_1-only safety guard. | Any explicit `cluster=\"Cluster_2\"` request hard-fails immediately and does not reach hardware. |
| `test_cluster1_runner_requires_unambiguous_cluster_for_hardware_run` | `tests/gate_architecture/test_gate_architecture.py` | Prevent unsafe cluster guessing. | Hardware execution aborts when the session does not expose a single unambiguous cluster binding. |
| `test_cluster1_runner_executes_only_when_explicit` | `tests/gate_architecture/test_gate_architecture.py` | Verify opt-in hardware execution semantics. | Hardware run only happens with `run_on_opx=True`, and the compiled processor chain is forwarded to the runner. |
| `test_ramsey_circuit_text_matches_golden` | `tests/gate_architecture/test_gate_architecture.py` | Lock the stable circuit text representation. | Ramsey intent text remains deterministic across refactors. |
| `test_ramsey_diagram_matches_golden` | `tests/gate_architecture/test_gate_architecture.py` | Lock the stable text diagram representation. | Ramsey diagram text remains deterministic, including the measurement schema footer. |
| `test_ramsey_resolution_report_matches_golden` | `tests/gate_architecture/test_gate_architecture.py` | Lock resolved parameter provenance. | Ramsey resolution report remains deterministic, including namespaced measurement outputs in the trace. |
| `test_ramsey_measurement_schema_matches_golden` | `tests/gate_architecture/test_gate_architecture.py` | Lock schema serialization details. | Measurement schema payload remains deterministic, including derived output fields and namespaced stream outputs. |
| `test_active_reset_real_time_circuit_text_matches_golden` | `tests/gate_architecture/test_gate_architecture.py` | Lock the IR-side representation of requested runtime branching. | The real-time-requested active-reset circuit still serializes structurally even though compilation rejects it. |
| `test_active_reset_analysis_snapshot_matches_golden` | `tests/gate_architecture/test_gate_architecture.py` | Lock the hardened analysis-only active-reset surface. | Combined diagram text, measurement schema, instruction trace, resolution report, and post-processing plan remain deterministic. |

## How To Run

Feature-area suite:

```powershell
pytest tests/gate_architecture/test_gate_architecture.py -q
```

Full repository regression suite:

```powershell
pytest -q
```
