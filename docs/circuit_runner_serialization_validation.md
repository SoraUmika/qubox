# Circuit Runner Serialization Validation

Validation method: QUA serialization comparison (legacy vs new CircuitRunner), simulator-only compile flow (no hardware execution).

## Environment

- `qop_ip`: `10.157.36.68` (target cluster information provided)
- `cluster_name`: `Cluster_2` (target cluster information provided)
- Execution mode: **No hardware runs** (program build + serialization only)

## Power Rabi

- Sweep configuration: gains=-0.15..0.15 step 0.05
- n_avg / n_samples: 64
- Legacy serialized QUA: [docs/circuit_serialized/power_rabi_legacy.py](docs/circuit_serialized/power_rabi_legacy.py)
- CircuitRunner serialized QUA: [docs/circuit_serialized/power_rabi_circuit.py](docs/circuit_serialized/power_rabi_circuit.py)
- Serialized comparison result: **Functionally equivalent with timing notes**
- Timing / ordering notes:
  - Serialized scripts differ only in non-semantic metadata (generation timestamp header).
- Final verdict: **PASS**

## T1

- Sweep configuration: wait_cycles=2..20 step 2
- n_avg / n_samples: 64
- Legacy serialized QUA: [docs/circuit_serialized/t1_legacy.py](docs/circuit_serialized/t1_legacy.py)
- CircuitRunner serialized QUA: [docs/circuit_serialized/t1_circuit.py](docs/circuit_serialized/t1_circuit.py)
- Serialized comparison result: **Functionally equivalent with timing notes**
- Timing / ordering notes:
  - Serialized scripts differ only in non-semantic metadata (generation timestamp header).
- Final verdict: **PASS**

## Readout GE discrimination

- Sweep configuration: single-point acquisition, no sweep
- n_avg / n_samples: 2048
- Legacy serialized QUA: [docs/circuit_serialized/readout_ge_discrimination_legacy.py](docs/circuit_serialized/readout_ge_discrimination_legacy.py)
- CircuitRunner serialized QUA: [docs/circuit_serialized/readout_ge_discrimination_circuit.py](docs/circuit_serialized/readout_ge_discrimination_circuit.py)
- Serialized comparison result: **Functionally equivalent with timing notes**
- Timing / ordering notes:
  - Serialized scripts differ only in non-semantic metadata (generation timestamp header).
- Final verdict: **PASS**

## Butterfly measurement

- Sweep configuration: single-point acquisition, policy=THRESHOLD
- n_avg / n_samples: 2048
- Legacy serialized QUA: [docs/circuit_serialized/butterfly_legacy.py](docs/circuit_serialized/butterfly_legacy.py)
- CircuitRunner serialized QUA: [docs/circuit_serialized/butterfly_circuit.py](docs/circuit_serialized/butterfly_circuit.py)
- Serialized comparison result: **Functionally equivalent with timing notes**
- Timing / ordering notes:
  - Serialized scripts differ only in non-semantic metadata (generation timestamp header).
- Final verdict: **PASS**

## Overall verdict

**PASS**

Any `Behaviorally different` result requires investigation before hardware execution.
