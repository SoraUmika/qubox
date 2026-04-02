# Hardware

Configuration engine, hardware controller, and program runner.

## ConfigEngine

Manages the QM hardware configuration dictionary:

```python
from qubox.hardware import ConfigEngine

engine = ConfigEngine.from_file("config.json")

# Inspect elements
engine.list_elements()       # ['transmon', 'resonator', 'flux']
engine.get_element("transmon")

# Patch configuration
engine.set_frequency("transmon", 4.85e9)
engine.set_amplitude("transmon", "x180", 0.312)

# Export for QM
config = engine.to_qm_config()
```

### Key Methods

| Method | Description |
|--------|-------------|
| `from_file(path)` | Load config from JSON |
| `to_qm_config()` | Export as QM-compatible config dict |
| `list_elements()` | List all defined elements |
| `get_element(name)` | Get element configuration |
| `set_frequency(element, freq)` | Update element frequency |
| `set_amplitude(element, pulse, amp)` | Update pulse amplitude |
| `add_element(name, config)` | Add a new element |
| `save(path)` | Save config to file |

## HardwareController

Live control of hardware elements:

```python
from qubox.hardware import HardwareController

ctrl = HardwareController(qm=session.qm)

# Live parameter updates (takes effect immediately)
ctrl.set_frequency("transmon", 4.85e9)
ctrl.set_dc_offset("flux", 0.1)
ctrl.set_output_gain("resonator", -10)
```

## ProgramRunner

Execute QUA programs on hardware or simulator:

```python
from qubox.hardware import ProgramRunner

runner = ProgramRunner(qm=session.qm)

# Execute
job = runner.execute(qua_program)
result = runner.wait_for_results(job, timeout=60)

# Simulate
from qm import SimulationConfig

sim_config = SimulationConfig(duration=10000)
sim_result = runner.simulate(qua_program, sim_config)
```

### Execution API

| Method | Description |
|--------|-------------|
| `execute(program)` | Submit program to OPX+ |
| `simulate(program, config)` | Run on QM simulator |
| `wait_for_results(job, timeout)` | Block until results ready |
| `get_running_job()` | Check for active hardware job |
| `halt_job(job)` | Stop a running job |

## QueueManager

Manages the QM job queue:

```python
from qubox.hardware import QueueManager

qm_mgr = QueueManager(qmm=session.qmm)
qm_mgr.list_pending()
qm_mgr.clear_queue()
```

## Connection Setup

```python
from qm import QuantumMachinesManager

qmm = QuantumMachinesManager(
    host="10.157.36.68",
    cluster_name="Cluster_2",
)
qm = qmm.open_qm(config)
```

!!! warning "Server Availability"
    Always verify server reachability before attempting connection.
    A connection attempt against an unreachable host will hang indefinitely.
