#!/usr/bin/env python
"""
Validate the 20 standard experiments via QM simulator.

For each experiment:
  1. Instantiate the canonical experiment class via Session
  2. Call build_program() with minimal parameters (n_avg=1, small sweeps)
  3. Simulate via qmm.simulate() (no hardware execution)
  4. Check that the compiled QUA program produces non-trivial waveforms

Usage:
    python tools/validate_standard_experiments_simulation.py

Requires: Python 3.11+, qm SDK, network access to QM hosted server (10.157.36.68).
"""
from __future__ import annotations

import sys
import json
import time
import traceback
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
QOP_IP = "10.157.36.68"
CLUSTER_NAME = "Cluster_2"
SAMPLE_ID = "post_cavity_sample_A"
COOLDOWN_ID = "cd_2026_03_02"
REGISTRY_BASE = Path(__file__).resolve().parent.parent  # E:\qubox
SIM_DURATION_NS = 10_000  # 10 µs default; some experiments may need more

# Default thermalization wait (clock cycles, 1 clk = 4 ns)
DEFAULT_QB_THERM = 250    # 1 µs
DEFAULT_RO_THERM = 2500   # 10 µs
DEFAULT_ST_THERM = 250    # 1 µs


@dataclass
class ValidationResult:
    template: str
    status: str  # "PASS", "FAIL", "SKIP", "ERROR"
    compile_time_s: float = 0.0
    sim_duration_ns: int = 0
    sample_source: str = "samples"
    message: str = ""
    has_analog_output: bool = False
    has_digital_output: bool = False
    qua_script_lines: int = 0


def _event_duration_ns(event: dict[str, Any]) -> int:
    duration = int(event.get("duration", 0) or 0)
    if duration > 0:
        return duration
    length = int(event.get("length", 0) or 0)
    if length > 0:
        return length
    samples = event.get("samples")
    if samples is not None:
        return max(1, len(samples))
    return 1


def _dense_port_activity(
    events: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    duration_ns: int,
    dtype: type[np.float64] | type[np.bool_],
) -> np.ndarray:
    max_end = max(
        (
            int(event.get("timestamp", 0) or 0) + _event_duration_ns(event)
            for event in events
        ),
        default=0,
    )
    length = max(int(duration_ns), max_end, 1)
    samples = np.zeros(length, dtype=dtype)
    for event in events:
        start = max(0, int(event.get("timestamp", 0) or 0))
        stop = min(length, start + _event_duration_ns(event))
        if stop <= start:
            stop = min(length, start + 1)
        if np.issubdtype(dtype, np.bool_):
            samples[start:stop] = True
        else:
            samples[start:stop] += 1.0
    return samples


def _dense_waveform_activity(
    waveforms: list[Any] | tuple[Any, ...],
    *,
    duration_ns: int,
    dtype: type[np.float64] | type[np.bool_],
) -> np.ndarray:
    max_end = max((int(getattr(waveform, "ends_at", 0) or 0) for waveform in waveforms), default=0)
    length = max(int(duration_ns), max_end, 1)
    samples = np.zeros(length, dtype=dtype)
    for waveform in waveforms:
        start = max(0, int(getattr(waveform, "timestamp", 0) or 0))
        stop = min(length, int(getattr(waveform, "ends_at", start + 1) or (start + 1)))
        if stop <= start:
            stop = min(length, start + 1)
        if np.issubdtype(dtype, np.bool_):
            samples[start:stop] = True
        else:
            samples[start:stop] += 1.0
    return samples


def _build_waveform_report_samples(job: Any, *, duration_ns: int):
    from qm.simulate import SimulatorControllerSamples, SimulatorSamples

    report = None
    if hasattr(job, "get_simulated_waveform_report"):
        report = job.get_simulated_waveform_report()
    if report is None:
        return None

    simulator_samples: dict[str, SimulatorControllerSamples] = {}
    for controller_name, controller_report in report.report_by_controllers().items():
        port_report = controller_report.get_report_by_output_ports()
        analog = {
            port: _dense_waveform_activity(waveforms, duration_ns=duration_ns, dtype=np.float64)
            for port, waveforms in port_report.flat_analog_out.items()
            if waveforms
        }
        digital = {
            port: _dense_waveform_activity(waveforms, duration_ns=duration_ns, dtype=np.bool_)
            for port, waveforms in port_report.flat_digital_out.items()
            if waveforms
        }
        simulator_samples[controller_name] = SimulatorControllerSamples(analog=analog, digital=digital)

    if not simulator_samples:
        return None

    return SimulatorSamples(simulator_samples)


def _build_waveform_metadata_samples(job: Any, *, duration_ns: int):
    from qm.simulate import SimulatorControllerSamples, SimulatorSamples

    analog_report = job.simulated_analog_waveforms() or {}
    digital_report = job.simulated_digital_waveforms() or {}

    if isinstance(analog_report, dict) and isinstance(analog_report.get("waveforms"), dict):
        analog_report = analog_report["waveforms"]
    if isinstance(digital_report, dict) and isinstance(digital_report.get("waveforms"), dict):
        digital_report = digital_report["waveforms"]

    analog_controllers = (analog_report.get("controllers") or {})
    digital_controllers = (digital_report.get("controllers") or {})
    controller_names = sorted(set(analog_controllers) | set(digital_controllers))
    if not controller_names:
        return None

    simulator_samples: dict[str, SimulatorControllerSamples] = {}
    for controller_name in controller_names:
        analog_ports = ((analog_controllers.get(controller_name) or {}).get("ports") or {})
        digital_ports = ((digital_controllers.get(controller_name) or {}).get("ports") or {})
        analog = {
            port: _dense_port_activity(events, duration_ns=duration_ns, dtype=np.float64)
            for port, events in analog_ports.items()
            if events
        }
        digital = {
            port: _dense_port_activity(events, duration_ns=duration_ns, dtype=np.bool_)
            for port, events in digital_ports.items()
            if events
        }
        simulator_samples[controller_name] = SimulatorControllerSamples(analog=analog, digital=digital)

    return SimulatorSamples(simulator_samples)


# ---------------------------------------------------------------------------
# Pulse registration helpers
# ---------------------------------------------------------------------------
def inject_calibration_data(session):
    """Populate calibration store with minimal frequencies and thresholds.

    The cd_2026_03_02 cooldown has no calibrated frequencies in its
    cqed_params.  We inject physical-ish values so that experiments
    that call get_readout_frequency() etc. can resolve.
    """
    cal = session.calibration
    attr = session.context_snapshot()
    qb_el = attr.qb_el
    ro_el = attr.ro_el
    st_el = attr.st_el

    # --- Element frequencies (from cqed_params.json & prior calibration) ---
    cal.set_frequencies(ro_el, resonator_freq=8.596e9)
    cal.set_frequencies(qb_el, qubit_freq=6.15e9)
    cal.set_frequencies(st_el, storage_freq=5.35e9)

    # --- Thermalization clocks ---
    cal.set_cqed_params(qb_el, qb_therm_clks=DEFAULT_QB_THERM)
    cal.set_cqed_params(ro_el, ro_therm_clks=DEFAULT_RO_THERM)
    cal.set_cqed_params(st_el, st_therm_clks=DEFAULT_ST_THERM)

    # --- Readout discrimination threshold (needed for with_state=True) ---
    cal.set_discrimination(
        ro_el,
        threshold=0.0,
        angle=0.0,
        mu_g=[-0.1, 0.0],
        mu_e=[0.1, 0.0],
        sigma_g=0.02,
        sigma_e=0.02,
        fidelity=1.0,
    )

    readout_binding = getattr(getattr(session, "bindings", None), "readout", None)
    if readout_binding is not None and hasattr(readout_binding, "sync_from_calibration"):
        readout_binding.sync_from_calibration(cal)

    print("[INIT] Injected calibration frequencies & stored readout discrimination")


def register_simulation_pulses(session):
    """Register minimal gate pulses needed for simulation.

    The sample's pulses.json only contains const, zero, and readout.
    We register simple flat-pulse (constant-amplitude) versions of the
    standard gate operations so experiments can build QUA programs.
    """
    from qubox.core.pulse_op import PulseOp
    from qubox.tools.generators import ensure_displacement_ops

    pm = session.pulse_mgr
    attr = session.context_snapshot()
    qb_el = attr.qb_el   # "transmon"
    ro_el = attr.ro_el    # "resonator"
    st_el = attr.st_el    # "storage"

    # --- Qubit gate pulses (constant amplitude, 40 ns) ---
    gate_len = 40  # clock cycles
    amp = 0.25

    qubit_ops = {
        "r0": 0.0,
        "x180": amp,
        "x90": amp / 2,
        "y180": amp,
        "y90": amp / 2,
        "yn90": amp / 2,
        "ge_x180": amp,
        "ge_x90": amp / 2,
        "ge_y180": amp,
        "ge_y90": amp / 2,
        "ge_ref_r180": amp,
    }

    for op_name, op_amp in qubit_ops.items():
        p = PulseOp(
            element=qb_el,
            op=op_name,
            type="control",
            length=gate_len,
            I_wf=op_amp,
            Q_wf=0.0,
        )
        pm.register_pulse_op(p, override=True, persist=False)

    # --- Number-selective π pulse for cavity experiments ---
    sel_ops = {"sel_x180": amp}
    for op_name, op_amp in sel_ops.items():
        p = PulseOp(
            element=qb_el,
            op=op_name,
            type="control",
            length=gate_len * 4,  # Longer selective pulse
            I_wf=op_amp,
            Q_wf=0.0,
        )
        pm.register_pulse_op(p, override=True, persist=False)

    # --- Storage displacement pulses (disp_n0, disp_n1, etc.) ---
    ensure_displacement_ops(
        pm,
        element=st_el,
        n_max=3,
        coherent_amp=0.2,
        coherent_len=100,
        override=True,
        persist=False,
    )

    # --- Also register generic "disp0" alias for StorageSpectroscopy ---
    p = PulseOp(
        element=st_el,
        op="disp0",
        type="control",
        length=gate_len,
        I_wf=0.1,
        Q_wf=0.0,
    )
    pm.register_pulse_op(p, override=True, persist=False)

    # --- Merge volatile (temp) pulses into config ---
    session.config_engine.merge_pulses(pm, include_volatile=True)

    # --- Bind the explicit readout state used by modern builders ---
    readout_pop = PulseOp(
        element=ro_el,
        op="readout",
        type="measurement",
        length=1000,
    )
    readout_binding = session.bindings.readout
    readout_binding.pulse_op = readout_pop
    readout_binding.active_op = "readout"
    readout_binding.sync_from_calibration(session.calibration, lookup_keys=(ro_el,))
    ro_freqs = session.calibration.get_frequencies(ro_el)
    if ro_freqs is not None and getattr(ro_freqs, "resonator_freq", None) is not None:
        readout_binding.drive_frequency = float(ro_freqs.resonator_freq)

    print(f"[INIT] Registered {len(qubit_ops)} qubit gate ops, "
          f"{len(sel_ops)} selective ops, 2 displacement ops")
    print(f"[INIT] Readout binding configured for {ro_el}:readout via calibration-backed sync")


# ---------------------------------------------------------------------------
# Session setup
# ---------------------------------------------------------------------------
def create_session():
    """Create and open a Session connected to the hosted QM server."""
    from qubox import Session

    print(f"[INIT] Creating Session for {SAMPLE_ID}/{COOLDOWN_ID}...")
    print(f"[INIT] QOP: {QOP_IP}, Cluster: {CLUSTER_NAME}")
    session = Session.open(
        sample_id=SAMPLE_ID,
        cooldown_id=COOLDOWN_ID,
        registry_base=REGISTRY_BASE,
        simulation_mode=True,
        connect=False,
        qop_ip=QOP_IP,
        cluster_name=CLUSTER_NAME,
        load_devices=False,
    )
    # External LOs are not needed for simulation.
    session.devices.specs.clear()
    session.connect()
    print("[INIT] Session opened successfully.")

    # Inject calibration data and register simulation pulses
    inject_calibration_data(session)
    register_simulation_pulses(session)

    return session


# ---------------------------------------------------------------------------
# Per-experiment build + simulate
# ---------------------------------------------------------------------------
def simulate_program(session, program, duration_ns: int = SIM_DURATION_NS):
    """Simulate a QUA program and return (sim_samples, compile_time, sample_source)."""
    from qm import SimulationConfig
    from qm.exceptions import QMSimulationError

    t0 = time.time()
    cfg = session.config_engine.build_qm_config()
    sim_config = SimulationConfig(duration=max(1, int(duration_ns) // 4))
    job = session.runner._qmm.simulate(cfg, program, sim_config)

    pull_delays_s = (0.0, 0.25, 0.75)
    last_error: QMSimulationError | None = None
    for delay_s in pull_delays_s:
        if delay_s:
            time.sleep(delay_s)
        try:
            sim_samples = job.get_simulated_samples()
            elapsed = time.time() - t0
            return sim_samples, elapsed, "samples"
        except QMSimulationError as exc:
            last_error = exc

    fallback_samples = _build_waveform_report_samples(job, duration_ns=duration_ns)
    if fallback_samples is None:
        fallback_samples = _build_waveform_metadata_samples(job, duration_ns=duration_ns)
    if fallback_samples is not None:
        elapsed = time.time() - t0
        return fallback_samples, elapsed, "waveform_report"

    if last_error is not None:
        raise last_error
    raise RuntimeError("Simulation sample retrieval failed without a recoverable waveform-report fallback.")


def check_sim_output(sim_samples) -> tuple[bool, bool]:
    """Return (has_analog, has_digital) from simulated samples."""
    has_analog = False
    has_digital = False
    for ctrl_name, ctrl_samples in sim_samples.items():
        analog = getattr(ctrl_samples, "analog", {}) or {}
        digital = getattr(ctrl_samples, "digital", {}) or {}
        for ch_name, data in analog.items():
            arr = np.asarray(data)
            if np.any(arr != 0):
                has_analog = True
                break
        for ch_name, data in digital.items():
            arr = np.asarray(data)
            if np.any(arr != 0):
                has_digital = True
                break
    return has_analog, has_digital


def get_qua_script(program) -> str:
    """Generate the QUA script text from a program object."""
    try:
        from qm import generate_qua_script
        return generate_qua_script(program)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Experiment definitions — each returns (build, sim_duration_ns)
# Uses correct import paths from qubox.experiments
# ---------------------------------------------------------------------------

def build_readout_trace(session):
    from qubox.experiments import ReadoutTrace
    exp = ReadoutTrace(session)
    attr = exp.attr
    build = exp.build_program(
        drive_frequency=attr.ro_fq or 8.75e9,
        ro_therm_clks=DEFAULT_RO_THERM,
        n_avg=1,
    )
    return build, 5_000


def build_resonator_spectroscopy(session):
    from qubox.experiments import ResonatorSpectroscopy
    exp = ResonatorSpectroscopy(session)
    attr = exp.attr
    lo_ro = exp.get_readout_lo()
    center = attr.ro_fq or (lo_ro - 50e6)
    build = exp.build_program(
        readout_op="readout",
        rf_begin=center - 2e6,
        rf_end=center + 2e6,
        df=1e6,
        n_avg=1,
        ro_therm_clks=DEFAULT_RO_THERM,
    )
    return build, 5_000


def build_resonator_power_spectroscopy(session):
    from qubox.experiments import ResonatorPowerSpectroscopy
    exp = ResonatorPowerSpectroscopy(session)
    attr = exp.attr
    lo_ro = exp.get_readout_lo()
    center = attr.ro_fq or (lo_ro - 50e6)
    build = exp.build_program(
        readout_op="readout",
        rf_begin=center - 1e6,
        rf_end=center + 1e6,
        df=1e6,
        g_min=0.01,
        g_max=0.1,
        N_a=3,
        n_avg=1,
        ro_therm_clks=DEFAULT_RO_THERM,
    )
    return build, 10_000


def build_qubit_spectroscopy(session):
    from qubox.experiments import QubitSpectroscopy
    exp = QubitSpectroscopy(session)
    attr = exp.attr
    lo_qb = exp.get_qubit_lo()
    center = attr.qb_fq or (lo_qb - 50e6)
    build = exp.build_program(
        pulse="x180",
        rf_begin=center - 2e6,
        rf_end=center + 2e6,
        df=1e6,
        qb_gain=0.1,
        qb_len=16,
        n_avg=1,
        qb_therm_clks=DEFAULT_QB_THERM,
    )
    return build, 5_000


def build_temporal_rabi(session):
    from qubox.experiments import TemporalRabi
    exp = TemporalRabi(session)
    build = exp.build_program(
        pulse="x180",
        pulse_len_begin=16,
        pulse_len_end=80,
        dt=16,
        pulse_gain=1.0,
        n_avg=1,
        qb_therm_clks=DEFAULT_QB_THERM,
    )
    return build, 5_000


def build_power_rabi(session):
    from qubox.experiments import PowerRabi
    exp = PowerRabi(session)
    build = exp.build_program(
        max_gain=0.5,
        dg=0.1,
        op="x180",
        n_avg=1,
        qb_therm_clks=DEFAULT_QB_THERM,
        use_circuit_runner=False,
    )
    return build, 5_000


def build_time_rabi_chevron(session):
    from qubox.experiments import TimeRabiChevron
    exp = TimeRabiChevron(session)
    build = exp.build_program(
        if_span=4e6,
        df=2e6,
        max_pulse_duration=80,
        dt=16,
        pulse="x180",
        pulse_gain=1.0,
        n_avg=1,
        qb_therm_clks=DEFAULT_QB_THERM,
    )
    return build, 10_000


def build_power_rabi_chevron(session):
    from qubox.experiments import PowerRabiChevron
    exp = PowerRabiChevron(session)
    build = exp.build_program(
        if_span=4e6,
        df=2e6,
        max_gain=0.5,
        dg=0.1,
        pulse="x180",
        pulse_duration=40,
        n_avg=1,
        qb_therm_clks=DEFAULT_QB_THERM,
    )
    return build, 10_000


def build_t1_relaxation(session):
    from qubox.experiments import T1Relaxation
    exp = T1Relaxation(session)
    # Note: T1Relaxation resolves qb_therm_clks internally from calibration
    build = exp.build_program(
        delay_end=208,
        dt=48,
        delay_begin=16,
        r180="x180",
        n_avg=1,
        use_circuit_runner=False,
    )
    return build, 5_000


def build_t2_ramsey(session):
    from qubox.experiments import T2Ramsey
    exp = T2Ramsey(session)
    build = exp.build_program(
        qb_detune=0,
        delay_end=208,
        dt=48,
        delay_begin=16,
        r90="x90",
        n_avg=1,
        qb_therm_clks=DEFAULT_QB_THERM,
    )
    return build, 5_000


def build_t2_echo(session):
    from qubox.experiments import T2Echo
    exp = T2Echo(session)
    build = exp.build_program(
        delay_end=224,
        dt=64,
        delay_begin=32,
        r180="x180",
        r90="x90",
        n_avg=1,
        qb_therm_clks=DEFAULT_QB_THERM,
    )
    return build, 5_000


def build_iq_blobs(session):
    from qubox.experiments import IQBlob
    exp = IQBlob(session)
    build = exp.build_program(
        r180="x180",
        n_runs=10,
        qb_therm_clks=DEFAULT_QB_THERM,
    )
    return build, 5_000


def build_all_xy(session):
    from qubox.experiments import AllXY
    exp = AllXY(session)
    build = exp.build_program(
        n_avg=1,
        qb_therm_clks=DEFAULT_QB_THERM,
    )
    return build, 10_000


def build_drag_calibration(session):
    from qubox.experiments import DRAGCalibration
    exp = DRAGCalibration(session)
    amps = np.linspace(-0.5, 0.5, 5)
    build = exp.build_program(
        amps=amps,
        n_avg=1,
        qb_therm_clks=DEFAULT_QB_THERM,
    )
    return build, 10_000


def build_readout_butterfly(session):
    from qubox.experiments import ReadoutButterflyMeasurement
    exp = ReadoutButterflyMeasurement(session)
    build = exp.build_program(
        prep_policy="threshold",
        prep_kwargs={"threshold": 0.0},
        r180="x180",
        n_samples=10,
        M0_MAX_TRIALS=2,
    )
    return build, 10_000


def build_qubit_state_tomography(session):
    from qubox.experiments import QubitStateTomography
    from qm import qua

    def state_prep():
        qua.play("x180", "transmon")

    exp = QubitStateTomography(session)
    build = exp.build_program(
        state_prep=state_prep,
        n_avg=1,
        therm_clks=DEFAULT_QB_THERM,
    )
    return build, 5_000


def build_storage_spectroscopy(session):
    from qubox.experiments import StorageSpectroscopy
    exp = StorageSpectroscopy(session)
    attr = exp.attr
    lo_st = session.hardware.get_element_lo(attr.st_el)
    center = attr.st_fq or (lo_st - 50e6)
    build = exp.build_program(
        disp="disp0",
        rf_begin=center - 1e6,
        rf_end=center + 1e6,
        df=1e6,
        storage_therm_time=DEFAULT_ST_THERM,
        n_avg=1,
    )
    return build, 5_000


def build_storage_t1_decay(session):
    from qubox.experiments import FockResolvedT1
    exp = FockResolvedT1(session)
    attr = exp.attr
    fock_fqs = getattr(attr, "fock_fqs", None)
    if fock_fqs is None:
        fock_fqs = [attr.qb_fq or 6.15e9]
    build = exp.build_program(
        fock_fqs=fock_fqs[:1],
        delay_end=208,
        dt=48,
        delay_begin=16,
        sel_r180="sel_x180",
        n_avg=1,
        st_therm_clks=DEFAULT_ST_THERM,
    )
    return build, 5_000


def build_num_splitting(session):
    from qubox.experiments import NumSplittingSpectroscopy
    from qm import qua

    def state_prep():
        qua.wait(4)

    exp = NumSplittingSpectroscopy(session)
    attr = exp.attr
    qb_fq = attr.qb_fq or 6.15e9
    build = exp.build_program(
        rf_centers=[qb_fq],
        rf_spans=[2e6],
        df=1e6,
        sel_r180="sel_x180",
        state_prep=state_prep,
        n_avg=1,
        st_therm_clks=DEFAULT_ST_THERM,
    )
    return build, 5_000


def build_wigner_tomography(session):
    from qubox.experiments import StorageWignerTomography
    from qm import qua

    def state_prep():
        qua.play("const", "storage")

    exp = StorageWignerTomography(session)
    x_vals = np.linspace(-1, 1, 3)
    p_vals = np.linspace(-1, 1, 3)
    build = exp.build_program(
        gates=[state_prep],
        x_vals=x_vals,
        p_vals=p_vals,
        base_alpha=10.0,
        r90_pulse="x90",
        n_avg=1,
        qb_therm_clks=DEFAULT_QB_THERM,
        parity_wait_clks=250,
        st_therm_clks=DEFAULT_ST_THERM,
        base_disp="disp_n0",
    )
    return build, 20_000


# ---------------------------------------------------------------------------
# All experiments registry
# ---------------------------------------------------------------------------
EXPERIMENTS = [
    ("readout.trace", build_readout_trace),
    ("resonator.spectroscopy", build_resonator_spectroscopy),
    ("resonator.power_spectroscopy", build_resonator_power_spectroscopy),
    ("qubit.spectroscopy", build_qubit_spectroscopy),
    ("qubit.temporal_rabi", build_temporal_rabi),
    ("qubit.power_rabi", build_power_rabi),
    ("qubit.time_rabi_chevron", build_time_rabi_chevron),
    ("qubit.power_rabi_chevron", build_power_rabi_chevron),
    ("qubit.t1", build_t1_relaxation),
    ("qubit.ramsey", build_t2_ramsey),
    ("qubit.echo", build_t2_echo),
    ("readout.iq_blobs", build_iq_blobs),
    ("calibration.all_xy", build_all_xy),
    ("calibration.drag", build_drag_calibration),
    ("readout.butterfly", build_readout_butterfly),
    ("tomography.qubit_state", build_qubit_state_tomography),
    ("storage.spectroscopy", build_storage_spectroscopy),
    ("storage.t1_decay", build_storage_t1_decay),
    ("storage.num_splitting", build_num_splitting),
    ("tomography.wigner", build_wigner_tomography),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    results: list[ValidationResult] = []
    session = None

    try:
        session = create_session()
    except Exception as exc:
        print(f"[FATAL] Cannot create SessionManager: {exc}")
        traceback.print_exc()
        sys.exit(1)

    print(f"\n{'=' * 80}")
    print(f"  Standard Experiments QM Simulation Validation")
    print(f"  {len(EXPERIMENTS)} experiments to validate")
    print(f"{'=' * 80}\n")

    for template_key, build_fn in EXPERIMENTS:
        print(f"[TEST] {template_key} ... ", end="", flush=True)
        result = ValidationResult(template=template_key, status="SKIP")

        try:
            # Step 1: build program
            t_build_start = time.time()
            build, sim_dur = build_fn(session)
            t_build_end = time.time()
            build_time = t_build_end - t_build_start

            program = build.program
            if program is None:
                result.status = "FAIL"
                result.message = "build_program() returned None program"
                results.append(result)
                print("FAIL (no program)")
                continue

            # Step 2: generate QUA script for inspection
            qua_script = get_qua_script(program)
            result.qua_script_lines = len(qua_script.splitlines()) if qua_script else 0

            # Step 3: simulate
            sim_samples, sim_time, sample_source = simulate_program(session, program, duration_ns=sim_dur)
            result.compile_time_s = build_time + sim_time
            result.sim_duration_ns = sim_dur
            result.sample_source = sample_source

            # Step 4: check output
            has_analog, has_digital = check_sim_output(sim_samples)
            result.has_analog_output = has_analog
            result.has_digital_output = has_digital

            if has_analog or has_digital:
                result.status = "PASS"
                result.message = (
                    f"analog={'Y' if has_analog else 'N'}, "
                    f"digital={'Y' if has_digital else 'N'}, "
                    f"QUA lines={result.qua_script_lines}, "
                    f"time={result.compile_time_s:.2f}s, "
                    f"source={result.sample_source}"
                )
                print(f"PASS ({result.message})")
            else:
                result.status = "FAIL"
                result.message = (
                    f"No non-zero analog or digital output. "
                    f"QUA lines={result.qua_script_lines}, "
                    f"sim_dur={sim_dur}ns, "
                    f"source={result.sample_source}"
                )
                print(f"FAIL ({result.message})")

        except Exception as exc:
            result.status = "ERROR"
            result.message = f"{type(exc).__name__}: {exc}"
            results.append(result)
            print(f"ERROR ({result.message})")
            traceback.print_exc()
            continue

        results.append(result)

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    print(f"\n{'=' * 80}")
    print("  SIMULATION VALIDATION SUMMARY")
    print(f"{'=' * 80}")
    n_pass = sum(1 for r in results if r.status == "PASS")
    n_fail = sum(1 for r in results if r.status == "FAIL")
    n_error = sum(1 for r in results if r.status == "ERROR")
    n_skip = sum(1 for r in results if r.status == "SKIP")
    print(f"  PASS: {n_pass}  FAIL: {n_fail}  ERROR: {n_error}  SKIP: {n_skip}")
    print(f"  Total: {len(results)} / {len(EXPERIMENTS)}")
    print()

    for r in results:
        icon = {"PASS": "+", "FAIL": "x", "ERROR": "!", "SKIP": "-"}.get(r.status, "?")
        print(f"  [{icon}] {r.template:<30} {r.status:>5}  {r.message}")

    print()

    # Write JSON report
    report_path = REGISTRY_BASE / "tools" / "simulation_validation_report.json"
    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "qop_ip": QOP_IP,
        "cluster": CLUSTER_NAME,
        "sample_id": SAMPLE_ID,
        "cooldown_id": COOLDOWN_ID,
        "total": len(EXPERIMENTS),
        "passed": n_pass,
        "failed": n_fail,
        "errors": n_error,
        "skipped": n_skip,
        "results": [
            {
                "template": r.template,
                "status": r.status,
                "compile_time_s": round(r.compile_time_s, 3),
                "sim_duration_ns": r.sim_duration_ns,
                "sample_source": r.sample_source,
                "has_analog_output": r.has_analog_output,
                "has_digital_output": r.has_digital_output,
                "qua_script_lines": r.qua_script_lines,
                "message": r.message,
            }
            for r in results
        ],
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
    print(f"  Report saved to: {report_path}")

    if n_fail > 0 or n_error > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
