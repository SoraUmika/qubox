"""Build the post_cavity_experiment_context.ipynb notebook programmatically."""
import json
import os

OUTPUT = r"e:\qubox\notebooks\post_cavity_experiment_context.ipynb"


def make_cell(cell_type, source_str):
    lines = source_str.split("\n")
    source = []
    for i, line in enumerate(lines):
        if i < len(lines) - 1:
            source.append(line + "\n")
        else:
            source.append(line)
    cell = {"cell_type": cell_type, "metadata": {}, "source": source}
    if cell_type == "code":
        cell["outputs"] = []
        cell["execution_count"] = None
    return cell


cells = []

# ── 1 Title ──────────────────────────────────────────────
cells.append(make_cell("markdown", """\
# Post-Cavity Experiment — Context Mode

Comprehensive characterization using the **qubox_v2 v4** context-mode API
with explicit device + cooldown scoping.

**Sections:**
1. Device Registry & Cooldown Setup
2. Session Initialization (Context Mode)
3. OPX/Octave Mixer Calibration
4. Readout Characterization
5. Qubit Characterization
6. Pulse Calibration
7. Readout Calibration
8. SPA Benchmarking
9. Storage Cavity
10. Quantum State Tomography
11. Session Verification & Summary
12. Context Mismatch Protection Demo
13. Utility: Continuous-Wave Output

All calibrations are automatically scoped to the active `device_id + cooldown_id`.
Stale-calibration reuse across cooldowns is prevented by compatibility checks."""))

# ── 2 Imports ────────────────────────────────────────────
cells.append(make_cell("code", """\
import sys
import numpy as np

# Ensure qubox_v2 is importable from the notebooks/ directory
sys.path.insert(0, r"E:\\qubox")

from pathlib import Path
from qualang_tools.units import unit

from qubox_v2.experiments.session import SessionManager
from qubox_v2.experiments import (
    # Spectroscopy
    ResonatorSpectroscopy,
    ResonatorPowerSpectroscopy,
    ResonatorSpectroscopyX180,
    ReadoutTrace,
    QubitSpectroscopy,
    QubitSpectroscopyEF,
    # Time domain
    PowerRabi,
    TemporalRabi,
    T1Relaxation,
    T2Ramsey,
    T2Echo,
    # Calibration
    IQBlob,
    ReadoutGEDiscrimination,
    ReadoutWeightsOptimization,
    ReadoutButterflyMeasurement,
    CalibrateReadoutFull,
    AllXY,
    DRAGCalibration,
    QubitPulseTrain,
    RandomizedBenchmarking,
    # Cavity / Fock
    StorageSpectroscopy,
    NumSplittingSpectroscopy,
    StorageChiRamsey,
    FockResolvedSpectroscopy,
    FockResolvedT1,
    FockResolvedRamsey,
    FockResolvedPowerRabi,
    # Tomography
    QubitStateTomography,
    StorageWignerTomography,
    SNAPOptimization,
    # SPA
    SPAFluxOptimization,
    SPAPumpFrequencyOptimization,
)
from qubox_v2.experiments.calibration import ReadoutConfig
from qubox_v2.calibration import CalibrationOrchestrator
from qubox_v2.devices import DeviceRegistry, DeviceInfo

u = unit()"""))

# ── 3 Registry heading ──────────────────────────────────
cells.append(make_cell("markdown", """\
## 1. Device Registry & Cooldown Setup

Create a device in the registry from existing `seq_1_device` config files,
then create a cooldown for today's session.

**Directory layout created:**
```
devices/<device_id>/
  device.json
  config/  (hardware.json, cqed_params.json, devices.json, pulse_specs.json)
  cooldowns/<cooldown_id>/
    config/  (calibration.json, pulses.json, measureConfig.json)
    data/
    artifacts/
```"""))

# ── 4 Registry init ─────────────────────────────────────
cells.append(make_cell("code", """\
# Registry root — where the devices/ directory tree lives
REGISTRY_BASE = Path(r"E:\\qubox")

registry = DeviceRegistry(REGISTRY_BASE)
print(f"Registry base: {registry.base_path}")
print(f"Existing devices: {registry.list_devices()}")"""))

# ── 5 Create device ─────────────────────────────────────
cells.append(make_cell("code", """\
DEVICE_ID = "post_cavity_sample_A"

if not registry.device_exists(DEVICE_ID):
    dev_path = registry.create_device(
        DEVICE_ID,
        description="Transmon qubit A — 3D cavity sample",
        config_source=Path(r"E:\\qubox\\seq_1_device\\config"),
        sample_info={"chip": "Q1-2025A", "fridge": "BlueFors-LD400"},
    )
    print(f"Created device at: {dev_path}")
else:
    print(f"Device '{DEVICE_ID}' already exists")

info = registry.load_device_info(DEVICE_ID)
print(f"Device: {info.device_id} — {info.description}")"""))

# ── 6 Create cooldown ───────────────────────────────────
cells.append(make_cell("code", """\
COOLDOWN_ID = "cd_2025_02_22"

if not registry.cooldown_exists(DEVICE_ID, COOLDOWN_ID):
    cd_path = registry.create_cooldown(
        DEVICE_ID, COOLDOWN_ID,
        seed_from=Path(r"E:\\qubox\\seq_1_device\\config"),
    )
    print(f"Created cooldown at: {cd_path}")
else:
    print(f"Cooldown '{COOLDOWN_ID}' already exists")

print(f"Cooldowns for {DEVICE_ID}: {registry.list_cooldowns(DEVICE_ID)}")"""))

# ── 7 Session heading ───────────────────────────────────
cells.append(make_cell("markdown", """\
## 2. Session Initialization (Context Mode)

Open a `SessionManager` using `device_id` + `cooldown_id` instead of
a raw `experiment_path`. The session automatically resolves:
- **Device-level** files: `hardware.json`, `cqed_params.json`, `devices.json`, `pulse_specs.json`
- **Cooldown-level** files: `calibration.json`, `pulses.json`, `measureConfig.json`

Compatibility checks verify that the calibration context matches the device
and wiring revision. Mismatches raise `ContextMismatchError` (or log warnings)."""))

# ── 8 Open session ──────────────────────────────────────
cells.append(make_cell("code", """\
session = SessionManager(
    device_id=DEVICE_ID,
    cooldown_id=COOLDOWN_ID,
    registry_base=REGISTRY_BASE,
    qop_ip="10.157.36.68",
    cluster_name="Cluster_2",
    auto_save_calibration=True,
)

# Verify context is populated
ctx = session.context
print(f"Device ID:      {ctx.device_id}")
print(f"Cooldown ID:    {ctx.cooldown_id}")
print(f"Wiring Rev:     {ctx.wiring_rev}")
print(f"Config Hash:    {ctx.config_hash}")
print(f"Schema Version: {ctx.schema_version}")
print(f"Experiment Path: {session.experiment_path}")"""))

# ── 9 QM open + context verify ──────────────────────────
cells.append(make_cell("code", """\
# Open QM connection and build element table
session.open()

attr = session.attributes
print(f"Resonator: {attr.ro_fq / 1e9:.4f} GHz")
print(f"Qubit:     {attr.qb_fq / 1e9:.4f} GHz")
print(f"Storage:   {attr.st_fq / 1e9:.4f} GHz")

# Verify calibration context is stamped
cal_ctx = session.calibration.data.context
if cal_ctx:
    print(f"\\nCalibration bound to device:   {cal_ctx.device_id}")
    print(f"Calibration bound to cooldown: {cal_ctx.cooldown_id}")
    print(f"Calibration wiring rev:        {cal_ctx.wiring_rev}")
else:
    print("\\nNo context block in calibration (legacy v3 file — will be stamped on first save)")

# Uncomment to run in simulation mode:
# session.hw.set_exec_mode("simulate")"""))

# ── 10 Snapshot + preflight heading ─────────────────────
cells.append(make_cell("markdown", """\
### 2.1 Session Snapshot + Preflight + Readout Override

Unified setup block for reproducibility and runtime readout configuration."""))

# ── 11 Snapshot + preflight code ────────────────────────
cells.append(make_cell("code", """\
from qubox_v2.core.session_state import SessionState
from qubox_v2.core.artifact_manager import ArtifactManager
from qubox_v2.core.preflight import preflight_check
from qubox_v2.core.artifacts import save_config_snapshot
from qubox_v2.core.schemas import validate_config_dir

# Orchestrator used by calibration preview/commit cells
orch = CalibrationOrchestrator(session)

config_dir = Path(session.experiment_path) / "config"
ss = SessionState.from_config_dir(
    config_dir,
    device_id=DEVICE_ID,
    cooldown_id=COOLDOWN_ID,
    wiring_rev=ctx.wiring_rev,
)
am = ArtifactManager(session.experiment_path, ss.build_hash)
am.save_session_state(ss.to_dict())
print(ss.summary())
print(f"\\nArtifacts root: {am.root}")

# Preflight validation
report = preflight_check(session)
if report["all_ok"]:
    print("All preflight checks PASSED.")
else:
    print("PREFLIGHT FAILURES:")
    for err in report["errors"]:
        print(f"  - {err}")

if report["warnings"]:
    print("Warnings:")
    for w in report["warnings"]:
        print(f"  - {w}")

snapshot_path = save_config_snapshot(session, tag="session_open")
print(f"\\nConfig snapshot saved to: {snapshot_path}")

schema_results = validate_config_dir(config_dir)
print("\\nSchema validation:")
for r in schema_results:
    status = "PASS" if r.valid else "FAIL"
    print(f"  {status} v={r.version}")
    for e in r.errors:
        print(f"    ERROR: {e}")
    for w in r.warnings:
        print(f"    WARN: {w}")

# Runtime readout override
READOUT_OVERRIDE_ELEMENT = attr.ro_el
READOUT_OVERRIDE_OP = "readout"
READOUT_OVERRIDE_WEIGHTS = None
READOUT_OVERRIDE_DEMOD = "dual_demod.full"
READOUT_OVERRIDE_THRESHOLD = None
READOUT_OVERRIDE_WEIGHT_LEN = None

override_info = session.override_readout_operation(
    element=READOUT_OVERRIDE_ELEMENT,
    operation=READOUT_OVERRIDE_OP,
    weights=READOUT_OVERRIDE_WEIGHTS,
    demod=READOUT_OVERRIDE_DEMOD,
    threshold=READOUT_OVERRIDE_THRESHOLD,
    weight_len=READOUT_OVERRIDE_WEIGHT_LEN,
    apply_to_attributes=True,
    persist_measure_config=True,
    drive_frequency=attr.ro_fq,
)

print("\\nRuntime readout override applied:")
print(f"  element:            {override_info['element']}")
print(f"  operation:          {override_info['operation']}")
print(f"  pulse:              {override_info['pulse']}")
print(f"  attributes.ro_el:   {override_info['attributes_ro_el']}")
print(f"  QM mapping:         {override_info['qm_config_entry']}")
print(f"  measureConfig path: {override_info['measure_config_path']}")"""))

# ── 12 Mixer heading ────────────────────────────────────
cells.append(make_cell("markdown", """\
## 3. OPX/Octave Mixer Calibration

Calibrate IQ mixer offsets (DC offset, gain imbalance, phase imbalance) for
each element. Run this before any measurements to ensure clean signal generation."""))

# ── 13 Manual cal controls heading ──────────────────────
cells.append(make_cell("markdown", """\
### 3.0 Manual Calibration UX Controls

Configure logging, scan bounds/grid, SA settings, and sideband objective for manual IQ calibration."""))

# ── 14 Manual cal controls code ─────────────────────────
cells.append(make_cell("code", """\
# -------- Notebook-level UX toggles --------
QUIET_QM_LOGS = True
LIVE_PLOTS = True
LIVE_PLOT_EVERY = 1

# -------- Scan bounds / grid --------
DC_COARSE_RANGE = 0.10
DC_COARSE_N = 11
DC_FINE_RANGE = 0.02
DC_FINE_N = 11

IQ_GAIN_RANGE = 0.10
IQ_PHASE_RANGE = 0.20
IQ_COARSE_N = 11
IQ_FINE_GAIN_RANGE = 0.02
IQ_FINE_PHASE_RANGE = 0.04
IQ_FINE_N = 11

MIN_MAXITER = 60
MIN_XTOL = 1e-4

# -------- Spectrum analyzer settings --------
SA_SPAN_HZ = 2e6
SA_RBW = 10e3
SA_VBW = 10e3
SA_LEVEL_DBM = 0.0
SA_AVG = 1
SA_SETTLE_S = 0.0
SA_EXTRA_CONFIG = {}

# -------- Sideband targeting objective --------
SIDEBAND = "lsb"
OBJECTIVE_MODE = "weighted_sum"
W_CARRIER = 1.0
W_IMAGE = 1.0
W_TARGET = 1.0

print("Manual calibration controls set.")"""))

# ── 15 Mixer cal code ───────────────────────────────────
cells.append(make_cell("code", """\
hw = session.hw

elements = [attr.ro_el, attr.qb_el, attr.st_el]
el_los = hw.get_element_lo(elements)
el_ifs = [hw.calculate_el_if_fq(el, fq)
          for el, fq in zip(elements, [attr.ro_fq, attr.qb_fq, attr.st_fq])]

print("Mixer calibration targets:")
for el, lo, if_fq in zip(elements, el_los, el_ifs):
    print(f"  {el:20s}  LO={lo/1e9:.4f} GHz  IF={if_fq/1e6:.2f} MHz")

# --- Manual IQ mixer calibration via SA124B ---
from qubox_v2.calibration import MixerCalibrationConfig, SAMeasurementHelper

cfg = MixerCalibrationConfig(
    sa_span_hz=SA_SPAN_HZ, sa_rbw=SA_RBW, sa_vbw=SA_VBW,
    sa_level=SA_LEVEL_DBM, sa_avg=SA_AVG, sa_settle=SA_SETTLE_S,
    sa_extra_config=SA_EXTRA_CONFIG,
    dc_coarse_range=DC_COARSE_RANGE, dc_coarse_n=DC_COARSE_N,
    dc_fine_range=DC_FINE_RANGE, dc_fine_n=DC_FINE_N,
    iq_gain_range=IQ_GAIN_RANGE, iq_phase_range=IQ_PHASE_RANGE,
    iq_coarse_n=IQ_COARSE_N,
    iq_fine_range_gain=IQ_FINE_GAIN_RANGE,
    iq_fine_range_phase=IQ_FINE_PHASE_RANGE,
    iq_fine_n=IQ_FINE_N,
    minimizer_maxiter=MIN_MAXITER, minimizer_xtol=MIN_XTOL,
    quiet_qm_logs=QUIET_QM_LOGS, live_plot=LIVE_PLOTS,
    live_plot_every=LIVE_PLOT_EVERY,
    sideband=SIDEBAND, objective_mode=OBJECTIVE_MODE,
    w_carrier=W_CARRIER, w_image=W_IMAGE, w_target=W_TARGET,
)

target_el = "qubit"
idx = elements.index(target_el)
target_lo = float(el_los[idx])
target_if = float(el_ifs[idx])

sa_dev = session.devices.get("sa124b")
sa_helper = SAMeasurementHelper(sa_dev, cfg)
before = sa_helper.measure_tones(target_lo, target_if)

result = hw.calibrate_element(
    el=target_el, method="manual_minimizer",
    mixer_cal_config=cfg, save_to_db=False,
)

after = sa_helper.measure_tones(target_lo, target_if)

print("\\nManual calibration complete.")

metrics_rows = [
    ("Target sideband power (dBm)", before["P_des_dBm"], after["P_des_dBm"], after["P_des_dBm"] - before["P_des_dBm"]),
    ("LO leakage power (dBm)", before["P_LO_dBm"], after["P_LO_dBm"], after["P_LO_dBm"] - before["P_LO_dBm"]),
    ("Image sideband power (dBm)", before["P_img_dBm"], after["P_img_dBm"], after["P_img_dBm"] - before["P_img_dBm"]),
    ("Target/LO (dBc)", before["LO_leak_dBc"], after["LO_leak_dBc"], after["LO_leak_dBc"] - before["LO_leak_dBc"]),
    ("Target/Image (dBc)", before["IRR_dBc"], after["IRR_dBc"], after["IRR_dBc"] - before["IRR_dBc"]),
]

print("\\nMixer calibration metrics (before -> after):")
print(f"{'Metric':32s} {'Before':>10s} {'After':>10s} {'Delta':>10s}")
for name, b, a, d in metrics_rows:
    print(f"{name:32s} {b:10.2f} {a:10.2f} {d:10.2f}")

import matplotlib.pyplot as plt
labels = [r[0] for r in metrics_rows]
before_vals = [r[1] for r in metrics_rows]
after_vals = [r[2] for r in metrics_rows]

x = np.arange(len(labels))
w = 0.38
fig, ax = plt.subplots(figsize=(10, 4.5))
ax.bar(x - w/2, before_vals, width=w, label="Before")
ax.bar(x + w/2, after_vals, width=w, label="After")
ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=20, ha="right")
ax.set_title("Mixer Calibration Metrics: Before vs After")
ax.grid(axis="y", alpha=0.3)
ax.legend()
plt.tight_layout()
plt.show()"""))

# ── 16 Readout heading ──────────────────────────────────
cells.append(make_cell("markdown", "## 4. Readout Characterization"))

# ── 17 Readout trace heading ────────────────────────────
cells.append(make_cell("markdown", """\
### 4.1 Readout Trace

Acquire raw ADC traces to verify readout signal level and timing."""))

# ── 18 Readout trace code ───────────────────────────────
cells.append(make_cell("code", """\
trace = ReadoutTrace(session)
result = trace.run(attr.ro_fq, n_avg=10000)

analysis = trace.analyze(result)
trace.plot(analysis)
print(analysis.metrics)"""))

# ── 19 Res spec heading ─────────────────────────────────
cells.append(make_cell("markdown", """\
### 4.2 Resonator Spectroscopy

Sweep readout frequency to locate resonator resonance."""))

# ── 20 Res spec code ────────────────────────────────────
cells.append(make_cell("code", """\
spec = ResonatorSpectroscopy(session)
res_cycle = orch.run_analysis_patch_cycle(
    spec,
    run_kwargs={
        "readout_op": "readout",
        "rf_begin": 8560 * u.MHz,
        "rf_end": 8640 * u.MHz,
        "df": 200 * u.kHz,
        "n_avg": 10000,
    },
    analyze_kwargs={"update_calibration": True},
    apply=False,
    persist_artifact=True,
)

res_result = orch._run_result_from_artifact(res_cycle["artifact"])
res_analysis = spec.analyze(res_result, update_calibration=False)
spec.plot(res_analysis)
print(f"f0 = {res_cycle['calibration_result'].params.get('f0_MHz', float('nan')):.4f} MHz")
print(f"kappa = {res_cycle['calibration_result'].params.get('kappa', float('nan')) / 1e3:.1f} kHz")
print("Patch preview:")
for item in res_cycle["dry_run"]["preview"]:
    print(" ", item)

# Commit only after review:
# orch.apply_patch(res_cycle["patch"], dry_run=False)"""))

# ── 21 Res power spec heading ───────────────────────────
cells.append(make_cell("markdown", """\
### 4.3 Resonator Power Spectroscopy

2D sweep of readout frequency vs gain to find optimal readout power."""))

# ── 22 Res power spec code ──────────────────────────────
cells.append(make_cell("code", """\
pspec = ResonatorPowerSpectroscopy(session)
result = pspec.run(
    "readout",
    rf_begin=8590 * u.MHz,
    rf_end=8600 * u.MHz,
    df=50 * u.kHz,
    g_min=0.01,
    g_max=1.9,
    N_a=20,
    n_avg=5000,
)

analysis = pspec.analyze(result)
pspec.plot(analysis)
print(f"Optimal gain: {analysis.metrics.get('optimal_gain', 'N/A')}")
print(f"Optimal freq: {analysis.metrics.get('optimal_freq', 'N/A')}")"""))

# ── 23 Res x180 heading ─────────────────────────────────
cells.append(make_cell("markdown", """\
### 4.4 Resonator Spectroscopy with X180

Measure resonator with ground and excited qubit states to extract dispersive shift chi."""))

# ── 24 Res x180 code ────────────────────────────────────
cells.append(make_cell("code", """\
spec_x180 = ResonatorSpectroscopyX180(session)
result = spec_x180.run(
    rf_begin=8560 * u.MHz,
    rf_end=8640 * u.MHz,
    df=200 * u.kHz,
    n_avg=10000,
)

analysis = spec_x180.analyze(result, update_calibration=True)
spec_x180.plot(analysis)
print(f"f0_g = {analysis.metrics.get('f0_g', 0) / 1e6:.4f} MHz")
print(f"f0_e = {analysis.metrics.get('f0_e', 0) / 1e6:.4f} MHz")
print(f"chi = {analysis.metrics.get('chi', 0) / 1e3:.1f} kHz")"""))

# ── 25 Qubit heading ────────────────────────────────────
cells.append(make_cell("markdown", "## 5. Qubit Characterization"))

# ── 26 Qubit spec heading ───────────────────────────────
cells.append(make_cell("markdown", """\
### 5.1 Qubit Spectroscopy

Sweep qubit drive frequency to locate the qubit transition.
Updates qubit frequency in the cooldown-scoped calibration store."""))

# ── 27 Qubit spec code ──────────────────────────────────
cells.append(make_cell("code", """\
qb_spec = QubitSpectroscopy(session)
qb_cycle = orch.run_analysis_patch_cycle(
    qb_spec,
    run_kwargs={
        "pulse": "saturation",
        "rf_begin": 6130 * u.MHz,
        "rf_end": 6170 * u.MHz,
        "df": 500 * u.kHz,
        "qb_gain": 1.0,
        "qb_len": 1000,
        "n_avg": 1000,
    },
    analyze_kwargs={"update_calibration": True},
    apply=False,
    persist_artifact=True,
)

qb_result = orch._run_result_from_artifact(qb_cycle["artifact"])
qb_analysis = qb_spec.analyze(qb_result, update_calibration=False)
qb_spec.plot(qb_analysis)
print(f"f0 = {qb_cycle['calibration_result'].params['f0_MHz']:.4f} MHz")
print("Patch preview:")
for item in qb_cycle["dry_run"]["preview"]:
    print(" ", item)

# Commit only after review:
# orch.apply_patch(qb_cycle["patch"], dry_run=False)"""))

# ── 28 Power Rabi heading ───────────────────────────────
cells.append(make_cell("markdown", """\
### 5.2 Power Rabi

Sweep qubit drive amplitude to calibrate the pi pulse gain.
Updates `ref_r180` amplitude and derived primitives (cooldown-scoped)."""))

# ── 29 Power Rabi code ──────────────────────────────────
cells.append(make_cell("code", """\
import importlib
import qubox_v2.calibration.orchestrator as orch_mod
importlib.reload(orch_mod)

orch = orch_mod.CalibrationOrchestrator(session)
rabi = PowerRabi(session)
rabi_cycle = orch.run_analysis_patch_cycle(
    rabi,
    run_kwargs={
        "max_gain": 1.2,
        "dg": 0.04,
        "op": "ref_r180",
        "n_avg": 5000,
    },
    analyze_kwargs={
        "update_calibration": True,
        "p0": [0.0001, 1, 0],
    },
    apply=False,
    persist_artifact=True,
)

rabi_result = orch._run_result_from_artifact(rabi_cycle["artifact"])
rabi_analysis = rabi.analyze(rabi_result, update_calibration=False, p0=[0.0001, 1, 0])
rabi.plot(rabi_analysis)
rabi_g_pi = float(rabi_cycle["calibration_result"].params.get("g_pi", 1.0))
print(f"g_pi (ref_r180) = {rabi_g_pi:.6f}")
print("Patch preview:")
for item in rabi_cycle["dry_run"]["preview"]:
    print(" ", item)

# Commit only after review:
# orch.apply_patch(rabi_cycle["patch"], dry_run=False)"""))

# ── 30 Temporal Rabi heading ────────────────────────────
cells.append(make_cell("markdown", """\
### 5.3 Temporal Rabi

Sweep pulse duration at fixed amplitude to measure Rabi frequency."""))

# ── 31 Temporal Rabi code ───────────────────────────────
cells.append(make_cell("code", """\
trabi = TemporalRabi(session)
result = trabi.run(
    pulse="const_x180",
    pulse_len_begin=16,
    pulse_len_end=500,
    dt=4,
    n_avg=5000,
)

analysis = trabi.analyze(result)
trabi.plot(analysis)
print(f"f_Rabi = {analysis.metrics.get('f_Rabi', 'N/A')} Hz")
print(f"pi_length = {analysis.metrics.get('pi_length', 'N/A')} ns")"""))

# ── 32 T1 heading ───────────────────────────────────────
cells.append(make_cell("markdown", """\
### 5.4 T1 Relaxation

Measure energy relaxation time after a pi pulse.
Stores T1 result in the cooldown-scoped calibration."""))

# ── 33 T1 code ──────────────────────────────────────────
cells.append(make_cell("code", """\
t1 = T1Relaxation(session)
t1_cycle = orch.run_analysis_patch_cycle(
    t1,
    run_kwargs={
        "delay_end": 50 * u.us,
        "dt": 500,
        "n_avg": 2000,
    },
    analyze_kwargs={
        "update_calibration": True,
        "p0": [0, 10, 0],
        "p0_time_unit": "us",
        "derive_qb_therm_clks": True,
        "clock_period_ns": 4.0,
    },
    apply=False,
    persist_artifact=True,
)

t1_result = orch._run_result_from_artifact(t1_cycle["artifact"])
t1_analysis = t1.analyze(t1_result, update_calibration=False, p0=[0, 10, 0], p0_time_unit="us")
t1.plot(t1_analysis)
print(f"T1 = {t1_cycle['calibration_result'].params.get('T1_us', float('nan')):.2f} us")
print(f"qb_therm_clks (proposed) = {t1_cycle['calibration_result'].params.get('qb_therm_clks', 'N/A')}")
print("Patch preview:")
for item in t1_cycle["dry_run"]["preview"]:
    print(" ", item)

# Commit only after review:
# orch.apply_patch(t1_cycle["patch"], dry_run=False)"""))

# ── 34 T2 Ramsey heading ────────────────────────────────
cells.append(make_cell("markdown", """\
### 5.5 T2 Ramsey

Ramsey interferometry with intentional detuning to measure T2*.
Applies frequency correction if configured (cooldown-scoped)."""))

# ── 35 T2 Ramsey code ───────────────────────────────────
cells.append(make_cell("code", """\
t2r = T2Ramsey(session)
qb_det_MHz = 0.2
t2r_cycle = orch.run_analysis_patch_cycle(
    t2r,
    run_kwargs={
        "qb_detune": int(qb_det_MHz * 1e6),
        "delay_end": 40 * u.us,
        "dt": 100,
        "n_avg": 4000,
        "qb_detune_MHz": qb_det_MHz,
    },
    analyze_kwargs={
        "update_calibration": True,
        "p0": [0, 20, 1.0, qb_det_MHz, 0.0, 0],
        "p0_time_unit": "us",
        "p0_freq_unit": "MHz",
        "apply_frequency_correction": False,
        "freq_correction_sign": -1.0,
    },
    apply=False,
    persist_artifact=True,
)

t2r_result = orch._run_result_from_artifact(t2r_cycle["artifact"])
t2r_analysis = t2r.analyze(
    t2r_result,
    update_calibration=False,
    p0=[0, 20, 1.0, qb_det_MHz, 0.0, 0],
    p0_time_unit="us",
    p0_freq_unit="MHz",
)
t2r.plot(t2r_analysis)
print(f"T2* = {t2r_cycle['calibration_result'].params.get('T2_star_us', float('nan')):.2f} us")
print(f"f_det = {t2r_cycle['calibration_result'].params.get('f_det_MHz', float('nan')):.4f} MHz")
print("Patch preview:")
for item in t2r_cycle["dry_run"]["preview"]:
    print(" ", item)

# Commit only after review:
# orch.apply_patch(t2r_cycle["patch"], dry_run=False)"""))

# ── 36 T2 Echo heading ──────────────────────────────────
cells.append(make_cell("markdown", """\
### 5.6 T2 Echo

Hahn echo measurement for T2_echo (removing low-frequency dephasing)."""))

# ── 37 T2 Echo code ─────────────────────────────────────
cells.append(make_cell("code", """\
t2e = T2Echo(session)
t2e_cycle = orch.run_analysis_patch_cycle(
    t2e,
    run_kwargs={
        "delay_end": 40 * u.us,
        "dt": 100,
        "n_avg": 4000,
    },
    analyze_kwargs={
        "update_calibration": True,
        "p0": [-1, 40, 1.0, 0],
        "p0_time_unit": "us",
    },
    apply=False,
    persist_artifact=True,
)

t2e_result = orch._run_result_from_artifact(t2e_cycle["artifact"])
t2e_analysis = t2e.analyze(t2e_result, update_calibration=False, p0=[-1, 40, 1.0, 0], p0_time_unit="us")
t2e.plot(t2e_analysis)
print(f"T2_echo = {t2e_cycle['calibration_result'].params.get('T2_echo_us', float('nan')):.2f} us")
print("Patch preview:")
for item in t2e_cycle["dry_run"]["preview"]:
    print(" ", item)

# Commit only after review:
# orch.apply_patch(t2e_cycle["patch"], dry_run=False)"""))

# ── 38 Primitive update heading ──────────────────────────
cells.append(make_cell("markdown", """\
### 5.7 Primitive Pulse Waveform Update

Apply the Power Rabi calibration (`g_pi`) to the reference pulse and regenerate
all qubit rotation waveforms."""))

# ── 39 Primitive update code ────────────────────────────
cells.append(make_cell("code", """\
# Commit PowerRabi patch after manual preview approval
print("PowerRabi patch preview:")
for item in rabi_cycle["dry_run"]["preview"]:
    print(" ", item)

# Uncomment to commit the previewed patch:
# rabi_apply = orch.apply_patch(rabi_cycle["patch"], dry_run=False)
# print(rabi_apply)

primitive_ops = ["x180", "y180", "x90", "xn90", "y90", "yn90"]
primitive_amps = {}
for op_name in primitive_ops:
    pcal = session.calibration.get_pulse_calibration(op_name)
    primitive_amps[op_name] = getattr(pcal, "amplitude", None)

print("Primitive amplitudes (current store):")
for op_name in primitive_ops:
    print(f"  {op_name:5s} -> {primitive_amps[op_name]}")"""))

# ── 40 Pulse cal heading ────────────────────────────────
cells.append(make_cell("markdown", "## 6. Pulse Calibration"))

# ── 41 DRAG heading ─────────────────────────────────────
cells.append(make_cell("markdown", """\
### 6.1 DRAG Calibration

Sweep DRAG coefficient to minimize leakage to the second excited state.
Stores DRAG alpha in the cooldown-scoped calibration."""))

# ── 42 DRAG code ────────────────────────────────────────
cells.append(make_cell("code", """\
drag = DRAGCalibration(session)
drag_cycle = orch.run_analysis_patch_cycle(
    drag,
    run_kwargs={
        "amps": np.linspace(-0.5, 0.5, 20),
        "n_avg": 5000,
        "base_alpha": 1.0,
    },
    analyze_kwargs={
        "update_calibration": True,
        "propagate_drag_to_primitives": True,
    },
    apply=False,
    persist_artifact=True,
)

drag_result = orch._run_result_from_artifact(drag_cycle["artifact"])
drag_analysis = drag.analyze(drag_result, update_calibration=False)
drag.plot(drag_analysis)
print(f"Optimal alpha = {drag_cycle['calibration_result'].params.get('optimal_alpha', 'N/A')}")
print("Patch preview:")
for item in drag_cycle["dry_run"]["preview"]:
    print(" ", item)

# Commit only after quality review:
# orch.apply_patch(drag_cycle["patch"], dry_run=False)"""))

# ── 43 DRAG commit heading ──────────────────────────────
cells.append(make_cell("markdown", """\
### 6.1b DRAG Calibration Commit

Wrap the DRAG calibration result in a `CalibrationStateMachine` lifecycle
and commit via `CalibrationPatch` if the fit quality passes validation."""))

# ── 44 DRAG commit code ─────────────────────────────────
cells.append(make_cell("code", """\
from qubox_v2.calibration.state_machine import (
    CalibrationStateMachine, CalibrationState,
    CalibrationPatch, PatchValidation,
)

sm_drag = CalibrationStateMachine(experiment="drag_calibration")
sm_drag.transition(CalibrationState.CONFIGURED)
sm_drag.transition(CalibrationState.ACQUIRING)
sm_drag.transition(CalibrationState.ACQUIRED)
sm_drag.transition(CalibrationState.ANALYZING)

optimal_alpha = drag_analysis.metrics.get("optimal_alpha", None)

drag_cal = session.calibration.get_pulse_calibration("ref_r180")
old_drag = drag_cal.drag_coeff if (drag_cal and drag_cal.drag_coeff is not None) else 0.0

drag_patch = CalibrationPatch(experiment="drag_calibration")
drag_patch.add_change(
    path="pulse_calibrations.ref_r180.drag_coeff",
    old_value=float(old_drag),
    new_value=float(optimal_alpha) if optimal_alpha is not None else None,
)

alpha_valid = optimal_alpha is not None and np.isfinite(optimal_alpha)
bounds_ok = alpha_valid and abs(optimal_alpha) < 5.0

drag_patch.validation = PatchValidation(
    passed=alpha_valid and bounds_ok,
    checks={"alpha_finite": alpha_valid, "alpha_bounds": bounds_ok},
    reasons=[] if (alpha_valid and bounds_ok) else
            [f"optimal_alpha={optimal_alpha} out of range or invalid"],
)
drag_patch.metadata = {"optimal_alpha": optimal_alpha}
sm_drag.patch = drag_patch

sm_drag.transition(CalibrationState.ANALYZED)
sm_drag.transition(CalibrationState.PENDING_APPROVAL)

print(drag_patch.summary())

if drag_patch.is_approved():
    sm_drag.transition(CalibrationState.COMMITTING)
    sm_drag.transition(CalibrationState.COMMITTED)
    print(f"\\nDRAG commit recorded: alpha = {optimal_alpha:.4f}")
    am.save_artifact("drag_calibration_patch", drag_patch.to_dict())
else:
    am.save_artifact("drag_calibration_candidate", drag_patch.to_dict())
    print("\\nDRAG calibration NOT committed. Candidate saved as artifact.")"""))

# ── 45 Pulse train heading ──────────────────────────────
cells.append(make_cell("markdown", """\
### 6.2 Qubit Pulse Train

Repeated gate applications to measure amplitude and phase errors."""))

# ── 46 Pulse train code ─────────────────────────────────
cells.append(make_cell("code", """\
ptrain = QubitPulseTrain(session)
result = ptrain.run(
    N_values=list(range(1, 51)),
    rotation_pulse="x180",
    n_avg=5000,
)

analysis = ptrain.analyze(result)
ptrain.plot(analysis)
print(analysis.metrics)"""))

# ── 47 AllXY heading ────────────────────────────────────
cells.append(make_cell("markdown", """\
### 6.3 AllXY

21-point gate error diagnostic. Ideal result is the stepped staircase pattern."""))

# ── 48 AllXY code ───────────────────────────────────────
cells.append(make_cell("code", """\
from qubox_v2.programs.macros.measure import measureMacro

allxy = AllXY(session)
result = allxy.run(n_avg=5000)
analysis = allxy.analyze(result)
allxy.plot(analysis)

print(f"Gate error = {analysis.metrics.get('gate_error', float('nan')):.4f}")
print(f"Observable = {analysis.metrics.get('observable', 'unknown')}")
print(f"State map  = {analysis.metrics.get('state_mapping', {})}")
print(f"Confusion correction used = {analysis.metrics.get('used_confusion_correction', False)}")
print(f"Confusion matrix present  = {measureMacro._ro_quality_params.get('confusion_matrix') is not None}")"""))

# ── 49 Confusion check ──────────────────────────────────
cells.append(make_cell("code", """\
from qubox_v2.programs.macros.measure import measureMacro
confusion = measureMacro._ro_quality_params.get("confusion_matrix", None)
confusion"""))

# ── 50 RB heading ───────────────────────────────────────
cells.append(make_cell("markdown", """\
### 6.4 Randomized Benchmarking

Single-qubit Clifford RB for average gate fidelity."""))

# ── 51 RB code ──────────────────────────────────────────
cells.append(make_cell("code", """\
rb = RandomizedBenchmarking(session)
result = rb.run(
    m_list=[1, 5, 10, 20, 50, 100, 200],
    num_sequence=20,
    n_avg=1000,
)

analysis = rb.analyze(result, p0=[0.99, 0.5, 0.5])
rb.plot(analysis)
print(f"p = {analysis.metrics.get('p', 'N/A')}")
print(f"Avg gate fidelity = {analysis.metrics.get('avg_gate_fidelity', 'N/A')}")
print(f"Error per gate = {analysis.metrics.get('error_per_gate', 'N/A')}")"""))

# ── 52 Readout cal heading ──────────────────────────────
cells.append(make_cell("markdown", "## 7. Readout Calibration"))

# ── 53 IQ blob heading ──────────────────────────────────
cells.append(make_cell("markdown", """\
### 7.1 IQ Blob

Acquire IQ blobs for ground and excited states."""))

# ── 54 IQ blob code ─────────────────────────────────────
cells.append(make_cell("code", """\
iq = IQBlob(session)
result = iq.run("x180", n_runs=5000)

analysis = iq.analyze(result)
iq.plot(analysis)
print(f"Readout fidelity = {analysis.metrics.get('fidelity', 0):.2%}")"""))

# ── 55 Weights heading ──────────────────────────────────
cells.append(make_cell("markdown", """\
### 7.2 Readout Weight Optimization

Optimize integration weights using time-sliced g/e readout traces."""))

# ── 56 Weights code ─────────────────────────────────────
cells.append(make_cell("code", """\
wopt = ReadoutWeightsOptimization(session)
result = wopt.run(
    ro_op="readout",
    drive_frequency=attr.ro_fq,
    cos_w_key="cos",
    sin_w_key="sin",
    m_sin_w_key="minus_sin",
    num_div=1,
    r180="x180",
    n_avg=200_000,
    persist=True,
    set_measure_macro=True,
)

analysis = wopt.analyze(result)
wopt.plot(analysis)

print(f"trace_length     = {analysis.metrics.get('trace_length', 'N/A')}")
print(f"ge_diff_norm_max = {analysis.metrics.get('ge_diff_norm_max', 'N/A'):.4f}")
print(f"opt_cos_key      = {analysis.metrics.get('opt_cos_key', 'N/A')}")
print(f"opt_sin_key      = {analysis.metrics.get('opt_sin_key', 'N/A')}")
print(f"opt_m_sin_key    = {analysis.metrics.get('opt_m_sin_key', 'N/A')}")"""))

# ── 57 GE disc heading ──────────────────────────────────
cells.append(make_cell("markdown", """\
### 7.3 GE Discrimination

Full discrimination analysis — rotation angle, threshold, confusion matrix.
Stores weights/threshold/confusion in the cooldown-scoped calibration."""))

# ── 58 GE disc code ─────────────────────────────────────
cells.append(make_cell("code", """\
from qubox_v2.experiments.calibration.readout import ReadoutGEDiscrimination

ge = ReadoutGEDiscrimination(session)
result = ge.run(
    "readout",
    attr.ro_fq,
    r180="x180",
    n_samples=50000,
    update_measure_macro=True,
    apply_rotated_weights=True,
    persist=True,
)

analysis = ge.analyze(result, update_calibration=True)
ge.plot(analysis, show_rotated=True, interactive=False)
print(f"Fidelity = {analysis.metrics.get('fidelity', 0):.2f}%")
print(f"Angle = {analysis.metrics.get('angle', 0):.3f} rad")
print(f"Threshold = {analysis.metrics.get('threshold', 0):.4f}")

rp = getattr(ge, "_run_params", {})
print("\\nResolved readout_ge mapping:")
print(f"  element_readout: {attr.ro_el}")
print(f"  operation:       {rp.get('measure_op')}")
print(f"  pulse key:       {getattr(rp.get('pulse_info', None), 'pulse', None)}")
print(f"  base weights:    cos={rp.get('base_cos_name')}, sin={rp.get('base_sin_name')}, m_sin={rp.get('base_m_sin_name')}")

if "gaussianity_g" in analysis.metrics:
    print(f"Gaussianity (g) = {analysis.metrics['gaussianity_g']:.3f}")
    print(f"Gaussianity (e) = {analysis.metrics['gaussianity_e']:.3f}")
if "cv_fidelity" in analysis.metrics:
    print(f"Cross-validated fidelity = {analysis.metrics['cv_fidelity']:.2%}")"""))

# ── 59 Butterfly heading ────────────────────────────────
cells.append(make_cell("markdown", """\
### 7.4 Butterfly Measurement

Two successive measurements to quantify QND fidelity, F, Q, and V."""))

# ── 60 Butterfly code ───────────────────────────────────
cells.append(make_cell("code", """\
from qubox_v2.experiments.calibration.readout import ReadoutButterflyMeasurement

bfly = ReadoutButterflyMeasurement(session)
result = bfly.run(r180="x180", update_measure_macro=True, n_samples=50000)

analysis = bfly.analyze(result, update_calibration=True)
bfly.plot(analysis, show_histogram=True, show_discriminator=True)
print(f"F = {analysis.metrics.get('F', 0):.2%}")
print(f"Q = {analysis.metrics.get('Q', 0):.2%}")
print(f"V = {analysis.metrics.get('V', 0):.4f}")

if "t01" in analysis.metrics:
    print(f"t01 = {analysis.metrics['t01']:.4f}")
    print(f"t10 = {analysis.metrics['t10']:.4f}")
if "Lambda_M_valid" in analysis.metrics:
    print(f"Lambda_M_valid = {analysis.metrics['Lambda_M_valid']}")"""))

# ── 61 Full readout heading ─────────────────────────────
cells.append(make_cell("markdown", """\
### 7.5 Full Readout Calibration Pipeline

Run the full state machine pipeline with explicit staged patch review and commit.
Stores all readout quality params in the cooldown-scoped calibration."""))

# ── 62 Full readout code ────────────────────────────────
cells.append(make_cell("code", """\
import importlib
import qubox_v2.experiments.calibration.readout as readout_mod
importlib.reload(readout_mod)

from qubox_v2.experiments.calibration.readout import (
    CalibrationReadoutFull,
    ReadoutConfig,
    ReadoutGEDiscrimination,
    ReadoutButterflyMeasurement,
    ReadoutWeightsOptimization,
    CalibrateReadoutFull,
)
from qubox_v2.programs.macros.measure import measureMacro

LEGACY_BLOB_K = 3.0
LEGACY_M0_MAX_TRIALS = 1000

readoutConfig = ReadoutConfig(
    measure_op="readout",
    drive_frequency=attr.ro_fq,
    ro_el=attr.ro_el,
    r180="x180",
    n_avg_weights=200_000,
    n_samples=50_000,
    n_shots_butterfly=50_000,
    skip_weights_optimization=False,
    persist_weights=True,
    update_weights=True,
    update_threshold=True,
    rotation_method="optimal",
    weight_extraction_method="legacy_ge_diff_norm",
    histogram_fitting="two_state_discriminator",
    threshold_extraction="legacy_discriminator",
    overwrite_policy="override",
    blob_k_g=LEGACY_BLOB_K,
    blob_k_e=LEGACY_BLOB_K,
    M0_MAX_TRIALS=LEGACY_M0_MAX_TRIALS,
    save_to_config=True,
    save_calibration_json=True,
    save_calibration_db=False,
    save_measure_config=True,
    save_session_state=False,
    display_analysis=False,
    ge_kwargs={
        "auto_update_postsel": True,
        "apply_rotated_weights": True,
        "persist": True,
    },
    bfly_kwargs={
        "update_measure_macro": True,
        "show_analysis": False,
    },
)

cal = CalibrationReadoutFull(session)
ro_pipeline_result = cal.run(readoutConfig=readoutConfig)
ro_pipeline_analysis = cal.analyze(ro_pipeline_result, update_calibration=True)

ge_stage = ro_pipeline_analysis.metadata.get("ge_analysis")
bfly_stage = ro_pipeline_analysis.metadata.get("bfly_analysis")

ge_fid_frac = float(ro_pipeline_analysis.metrics.get("ge_fidelity", float("nan")))
if ge_fid_frac > 1.0 and np.isfinite(ge_fid_frac):
    ge_fid_frac = ge_fid_frac / 100.0
ge_fid_pct = ge_fid_frac * 100.0 if np.isfinite(ge_fid_frac) else float("nan")

bfly_F = float(ro_pipeline_analysis.metrics.get("bfly_F", float("nan")))
ge_minus_F = ge_fid_frac - bfly_F if (np.isfinite(ge_fid_frac) and np.isfinite(bfly_F)) else float("nan")

weights_mode = "optimized" if not readoutConfig.skip_weights_optimization else "base"
print("Readout calibration pipeline complete.")
print(f"Weight mode = {weights_mode}")
print(f"GE fidelity = {ge_fid_pct:.2f}%  ({ge_fid_frac:.4f} frac)")
print(f"GE angle    = {ro_pipeline_analysis.metrics.get('ge_angle', 0):.6f} rad")
print(f"GE thr      = {ro_pipeline_analysis.metrics.get('ge_threshold', 0):.6g}")
print(f"F = {ro_pipeline_analysis.metrics.get('bfly_F', 0):.4f}, Q = {ro_pipeline_analysis.metrics.get('bfly_Q', 0):.4f}, V = {ro_pipeline_analysis.metrics.get('bfly_V', 0):.4f}")
print(f"GE/100 - F  = {ge_minus_F:.4f}")
print(f"Lambda_M_valid = {ro_pipeline_analysis.metrics.get('bfly_Lambda_M_valid', None)}")
print(f"acceptance_rate = {ro_pipeline_analysis.metrics.get('bfly_acceptance_rate', float('nan'))}")
print(f"average_tries   = {ro_pipeline_analysis.metrics.get('bfly_average_tries', float('nan'))}")
print(f"measureMacro confusion loaded: {measureMacro._ro_quality_params.get('confusion_matrix') is not None}")

if bfly_stage is not None:
    cm = bfly_stage.metrics.get("confusion_matrix", None)
    tm = bfly_stage.metrics.get("transition_matrix", None)
else:
    cm = None
    tm = None

if cm is not None:
    print("\\nButterfly confusion matrix Lambda_M:")
    try:
        print(cm.to_markdown(floatfmt=".4f"))
    except Exception:
        print(cm)
if tm is not None:
    print("\\nButterfly transition matrix T:")
    try:
        print(tm.to_markdown(floatfmt=".4f"))
    except Exception:
        print(tm)

ro_pipeline_summary = {
    "readoutConfig": readoutConfig,
    "result": ro_pipeline_result,
    "analysis": ro_pipeline_analysis,
    "parity": {
        "ge_fidelity_frac": ge_fid_frac,
        "F": bfly_F,
        "ge_minus_F": ge_minus_F,
    },
}"""))

# ── 63 Readout artifacts heading ────────────────────────
cells.append(make_cell("markdown", """\
### 7.6 Readout Calibration Artifacts

Save all readout calibration metrics and state machine histories as
session artifacts. Validates persistence to cooldown-scoped paths."""))

# ── 64 Readout artifacts code ───────────────────────────
cells.append(make_cell("code", """\
import importlib
from pathlib import Path
import qubox_v2.experiments.calibration.gates as gates_mod
importlib.reload(gates_mod)
from qubox_v2.experiments.calibration.gates import AllXY
from qubox_v2.programs.macros.measure import measureMacro

# Persist readout + pulse calibration artifacts (cooldown-scoped)
session.calibration.save()
session.save_pulses()
measure_cfg_path = Path(session.experiment_path) / "config" / "measureConfig.json"
measure_cfg_path.parent.mkdir(parents=True, exist_ok=True)
measureMacro.save_json(str(measure_cfg_path))

# Reload measureMacro from disk to validate persistence path
measureMacro.load_json(str(measure_cfg_path))

# Run ALLXY as post-readout sanity check
allxy = AllXY(session)
allxy_result = allxy.run(n_avg=5000)
allxy_analysis = allxy.analyze(allxy_result)
allxy.plot(allxy_analysis)

cm = measureMacro._ro_quality_params.get("confusion_matrix", None)
tm = measureMacro._ro_quality_params.get("transition_matrix", None)

print("=== Calibration Summary ===")
print(f"g_pi (ref_r180): {float(globals().get('rabi_g_pi', float('nan'))):.6f}")

primitive_ops = ["x180", "y180", "x90", "xn90", "y90", "yn90"]
print("Primitive pulse amplitudes:")
for op_name in primitive_ops:
    pcal = session.calibration.get_pulse_calibration(op_name)
    print(f"  {op_name:5s}: {getattr(pcal, 'amplitude', None)}")

if "ro_pipeline_summary" in globals():
    disc = ro_pipeline_summary.get("discrimination", {})
    bfly_s = ro_pipeline_summary.get("butterfly", {})
    print(f"Blob centers: mu_g={disc.get('rot_mu_g')}, mu_e={disc.get('rot_mu_e')}")
    print(f"Rotation angle: {disc.get('angle')}")
    print(f"F={bfly_s.get('F')}, Q={bfly_s.get('Q')}, V={bfly_s.get('V')}")

print("Confusion matrix:")
print(cm)
print("Transition matrix:")
print(tm)
print(f"ALLXY observable: {allxy_analysis.metrics.get('observable')}")
print(f"ALLXY correction applied: {allxy_analysis.metrics.get('used_confusion_correction')}")
print(f"ALLXY state mapping: {allxy_analysis.metrics.get('state_mapping')}")
print("Final mapping: +1 -> |g>, -1 -> |e>")
print(f"measureConfig persisted to: {measure_cfg_path}")"""))

# ── 65 SPA heading ──────────────────────────────────────
cells.append(make_cell("markdown", "## 8. SPA Benchmarking"))

# ── 66 SPA flux heading ─────────────────────────────────
cells.append(make_cell("markdown", """\
### 8.1 SPA Flux Optimization

Sweep DC flux bias with SPA-enhanced readout to find optimal flux point."""))

# ── 67 SPA flux code ────────────────────────────────────
cells.append(make_cell("code", """\
spa_flux = SPAFluxOptimization(session)
result = spa_flux.run(
    dc_list=np.linspace(-0.5, 0.5, 51),
    sample_fqs=np.linspace(8.5e9, 8.7e9, 21),
    n_avg=1000,
)

analysis = spa_flux.analyze(result)
spa_flux.plot(analysis)
print(f"Best DC = {analysis.metrics.get('best_dc', 'N/A'):.4f} V")
print(f"Best freq = {analysis.metrics.get('best_freq', 0) / 1e6:.2f} MHz")"""))

# ── 68 SPA pump heading ─────────────────────────────────
cells.append(make_cell("markdown", """\
### 8.2 SPA Pump Frequency Optimization

2D sweep of pump power and detuning to optimize SPA readout fidelity."""))

# ── 69 SPA pump code ────────────────────────────────────
cells.append(make_cell("code", """\
spa_pump = SPAPumpFrequencyOptimization(session)
# result = spa_pump.run(
#     readout_op="readout",
#     drive_frequency=attr.qb_fq,
#     pump_powers=np.linspace(0.1, 1.0, 10),
#     pump_detunings=np.linspace(-5e6, 5e6, 21),
#     r180="x180",
#     samples_per_run=25000,
# )
# analysis = spa_pump.analyze(result)
# spa_pump.plot(analysis)
# print(f"Best pump power = {analysis.metrics.get('best_pump_power', 'N/A')}")
# print(f"Best pump detuning = {analysis.metrics.get('best_pump_detuning', 'N/A')}")"""))

# ── 70 Storage heading ──────────────────────────────────
cells.append(make_cell("markdown", "## 9. Storage Cavity"))

# ── 71 Storage spec heading ─────────────────────────────
cells.append(make_cell("markdown", """\
### 9.1 Storage Spectroscopy

Sweep storage cavity frequency to locate resonance."""))

# ── 72 Storage spec code ────────────────────────────────
cells.append(make_cell("code", """\
st_spec = StorageSpectroscopy(session)
result = st_spec.run(
    disp="const_alpha",
    rf_begin=5200 * u.MHz,
    rf_end=5280 * u.MHz,
    df=200 * u.kHz,
    storage_therm_time=500,
    n_avg=50,
)

analysis = st_spec.analyze(result, update_calibration=True)
st_spec.plot(analysis)
print(f"f_storage = {analysis.metrics['f_storage'] / 1e6:.4f} MHz")
print(f"kappa = {analysis.metrics['kappa'] / 1e3:.1f} kHz")"""))

# ── 73 Storage spec orch heading ────────────────────────
cells.append(make_cell("markdown", """\
### 9.1b Storage Spectroscopy (Orchestrator Pipeline)

Run via the Artifact -> CalibrationResult -> Patch -> Orchestrator flow."""))

# ── 74 Storage spec orch code ───────────────────────────
cells.append(make_cell("code", """\
st_spec = StorageSpectroscopy(session)
st_center = float(getattr(attr, "st_fq", attr.qb_fq))
st_cycle = orch.run_analysis_patch_cycle(
    st_spec,
    run_kwargs={
        "disp": "const_alpha",
        "rf_begin": (st_center - 5 * u.MHz),
        "rf_end": (st_center + 5 * u.MHz),
        "df": 200 * u.kHz,
        "storage_therm_time": int(getattr(attr, "qb_therm_clks", 0)),
        "sel_r180": "sel_x180",
        "n_avg": 1000,
    },
    analyze_kwargs={"update_calibration": True},
    apply=False,
    persist_artifact=True,
)

st_result = orch._run_result_from_artifact(st_cycle["artifact"])
st_analysis = st_spec.analyze(st_result, update_calibration=False)
st_spec.plot(st_analysis)
print(f"storage f0 = {st_cycle['calibration_result'].params.get('f_storage_MHz', float('nan')):.4f} MHz")
print("Patch preview:")
for item in st_cycle["dry_run"]["preview"]:
    print(" ", item)

# Commit only after review:
# orch.apply_patch(st_cycle["patch"], dry_run=False)"""))

# ── 75 Num split heading ────────────────────────────────
cells.append(make_cell("markdown", """\
### 9.2 Number Splitting Spectroscopy

Resolve photon-number-dependent qubit frequency shifts."""))

# ── 76 Num split code ───────────────────────────────────
cells.append(make_cell("code", """\
from qm.qua import wait

def prep_vacuum():
    \"\"\"Explicit no-op preparation for notebook-driven workflows.\"\"\"
    wait(1)

nsplit = NumSplittingSpectroscopy(session)
result = nsplit.run(
    rf_centers=[attr.qb_fq],
    rf_spans=[10 * u.MHz],
    df=100 * u.kHz,
    state_prep=prep_vacuum,
    n_avg=500,
)

analysis = nsplit.analyze(result)
nsplit.plot(analysis)
print(analysis.metrics)"""))

# ── 77 Chi Ramsey heading ───────────────────────────────
cells.append(make_cell("markdown", """\
### 9.3 Storage Chi Ramsey

Measure dispersive coupling chi via Ramsey interferometry."""))

# ── 78 Chi Ramsey code ──────────────────────────────────
cells.append(make_cell("code", """\
chi_ramsey = StorageChiRamsey(session)
result = chi_ramsey.run(
    fock_fq=attr.qb_fq,
    delay_ticks=np.arange(4, 2000, 10),
    disp_pulse="const_alpha",
    x90_pulse="x90",
    n_avg=20,
)

analysis = chi_ramsey.analyze(result, update_calibration=True,
                              p0=[0.5, 0.5, 35000, 0.1, 0.0028, 400])
chi_ramsey.plot(analysis)
print(f"chi = {analysis.metrics.get('chi', 0) / 1e3:.1f} kHz")
print(f"nbar = {analysis.metrics.get('nbar', 0):.2f}")"""))

# ── 79 Fock spec heading ────────────────────────────────
cells.append(make_cell("markdown", """\
### 9.4 Fock-Resolved Spectroscopy

Probe qubit spectroscopy conditioned on Fock number."""))

# ── 80 Fock spec code ───────────────────────────────────
cells.append(make_cell("code", """\
fock_spec = FockResolvedSpectroscopy(session)
result = fock_spec.run(
    probe_fqs=np.linspace(attr.qb_fq - 5e6, attr.qb_fq + 5e6, 101),
    state_prep=prep_vacuum,
    n_avg=20,
)

analysis = fock_spec.analyze(result)
fock_spec.plot(analysis)
print(analysis.metrics)"""))

# ── 81 Disp pulses heading ──────────────────────────────
cells.append(make_cell("markdown", """\
### 9.4b Register Displacement Pulses for Fock-Resolved Experiments

**REQUIRED** before running Fock-resolved T1, Ramsey, or Power Rabi."""))

# ── 82 Disp pulses code ─────────────────────────────────
cells.append(make_cell("code", """\
from qubox_v2.tools.generators import ensure_displacement_ops

n_fock = 3

disp_ref = session.get_displacement_reference()
coherent_amp = disp_ref.get("coherent_amp", None)
coherent_len = disp_ref.get("coherent_len", None)
b_alpha = disp_ref.get("b_alpha", None)

created = ensure_displacement_ops(
    session.pulse_mgr,
    element=attr.st_el,
    n_max=n_fock,
    coherent_amp=coherent_amp,
    coherent_len=coherent_len,
    b_alpha=b_alpha,
)

session.burn_pulses()

print(f"Displacement refs: amp={coherent_amp}, len={coherent_len}, alpha={b_alpha}")
print(f"Registered {len(created)} displacement ops on '{attr.st_el}':")
for name, (I, Q) in created.items():
    print(f"  {name}: len={len(I)}, max_I={I.max():.4f}, max_Q={Q.max():.4f}")"""))

# ── 83 Fock T1 heading ──────────────────────────────────
cells.append(make_cell("markdown", """\
### 9.5 Fock-Resolved T1

Measure T1 in individual Fock manifolds."""))

# ── 84 Fock T1 code ─────────────────────────────────────
cells.append(make_cell("code", """\
fock_t1 = FockResolvedT1(session)

n_fock = 2
fock_fqs = attr.get_fock_frequencies(n_fock)
result = fock_t1.run(
     fock_fqs=fock_fqs,
     fock_disps=["disp_n0", "disp_n1"],
     delay_end=40000,
     dt=200,
     n_avg=20,
)
analysis = fock_t1.analyze(result)
fock_t1.plot(analysis)
for key, val in analysis.metrics.items():
     if key.startswith("T1_fock_"):
         print(f"{key} = {val / 1e3:.2f} us")"""))

# ── 85 Fock Ramsey heading ──────────────────────────────
cells.append(make_cell("markdown", """\
### 9.6 Fock-Resolved Ramsey

Measure T2 in individual Fock manifolds."""))

# ── 86 Fock Ramsey code ─────────────────────────────────
cells.append(make_cell("code", """\
fock_ramsey = FockResolvedRamsey(session)

n_fock = 2
fock_fqs = attr.get_fock_frequencies(n_fock)
result = fock_ramsey.run(
     fock_fqs=fock_fqs,
     detunings=[0.2e6],
     disps=["disp_n0", "disp_n1"],
     delay_end=40000,
     dt=100,
     n_avg=20,
)
analysis = fock_ramsey.analyze(result)
fock_ramsey.plot(analysis)
print(analysis.metrics)"""))

# ── 87 Fock Rabi heading ────────────────────────────────
cells.append(make_cell("markdown", """\
### 9.7 Fock-Resolved Power Rabi

Calibrate selective pi pulses per Fock manifold."""))

# ── 88 Fock Rabi code ───────────────────────────────────
cells.append(make_cell("code", """\
fock_rabi = FockResolvedPowerRabi(session)
# fock_fqs = [...]  # From NumSplittingSpectroscopy results
# result = fock_rabi.run(
#     fock_fqs=fock_fqs,
#     gains=np.linspace(0, 1.5, 50),
#     sel_qb_pulse="sel_x180",
#     disp_n_list=["disp_n0", "disp_n1", "disp_n2"],
#     n_avg=2000,
# )
# analysis = fock_rabi.analyze(result)
# fock_rabi.plot(analysis)
# for key, val in analysis.metrics.items():
#     if key.startswith("g_pi_fock_"):
#         print(f"{key} = {val:.4f}")"""))

# ── 89 Tomo heading ─────────────────────────────────────
cells.append(make_cell("markdown", "## 10. Quantum State Tomography"))

# ── 90 Qubit tomo heading ───────────────────────────────
cells.append(make_cell("markdown", """\
### 10.1 Qubit State Tomography

Three-axis measurement to reconstruct the qubit Bloch vector."""))

# ── 91 Qubit tomo code ──────────────────────────────────
cells.append(make_cell("code", """\
from qm.qua import *

def prep_x_plus():
    \"\"\"Prepare |+x> state.\"\"\"
    play("x90", attr.qb_el)

tomo = QubitStateTomography(session)
result = tomo.run(
    state_prep=prep_x_plus,
    n_avg=10000,
)

analysis = tomo.analyze(result)
tomo.plot(analysis)
print(f"sx = {analysis.metrics.get('sx', 0):.3f}")
print(f"sy = {analysis.metrics.get('sy', 0):.3f}")
print(f"sz = {analysis.metrics.get('sz', 0):.3f}")
print(f"Purity = {analysis.metrics.get('purity', 0):.3f}")"""))

# ── 92 Wigner heading ───────────────────────────────────
cells.append(make_cell("markdown", """\
### 10.2 Wigner Tomography

Reconstruct the Wigner function of the storage cavity state."""))

# ── 93 Wigner code ──────────────────────────────────────
cells.append(make_cell("code", """\
wigner = StorageWignerTomography(session)
# result = wigner.run(
#     gates=[...],
#     x_vals=np.linspace(-3, 3, 41),
#     p_vals=np.linspace(-3, 3, 41),
#     n_avg=500,
# )
# analysis = wigner.analyze(result)
# wigner.plot(analysis)
# print(f"W_min = {analysis.metrics.get('W_min', 0):.3f}")
# print(f"W_max = {analysis.metrics.get('W_max', 0):.3f}")
# print(f"Negativity = {analysis.metrics.get('negativity', 0):.3f}")"""))

# ── 94 SNAP heading ─────────────────────────────────────
cells.append(make_cell("markdown", """\
### 10.3 SNAP Optimization

Optimize SNAP gate angles using Fock-resolved state tomography."""))

# ── 95 SNAP code ────────────────────────────────────────
cells.append(make_cell("code", """\
snap = SNAPOptimization(session)
# result = snap.run(
#     snap_gate=...,
#     disp1_gate=...,
#     fock_probe_fqs=[...],
#     n_avg=500,
# )
# analysis = snap.analyze(result)
# snap.plot(analysis)
# print(analysis.metrics)"""))

# ── 96 Verification heading ─────────────────────────────
cells.append(make_cell("markdown", "## 11. Session Verification & Summary"))

# ── 97 Waveform check heading ───────────────────────────
cells.append(make_cell("markdown", """\
### 11.1 Waveform Regression Check

Verify that PulseFactory produces deterministic, correct waveforms."""))

# ── 98 Waveform check code ──────────────────────────────
cells.append(make_cell("code", """\
from qubox_v2.verification.waveform_regression import run_all_checks

wf_results = run_all_checks()
passed = sum(1 for r in wf_results if r.passed)
total = len(wf_results)
print(f"Waveform regression: {passed}/{total} passed")

for r in wf_results:
    if not r.passed:
        print(r)

if passed == total:
    print("All waveform regression checks PASSED.")
else:
    print(f"WARNING: {total - passed} waveform regression check(s) failed.")"""))

# ── 99 Session summary heading ──────────────────────────
cells.append(make_cell("markdown", """\
### 11.2 Session Summary & Artifact Finalization

Print context, build hash, all calibrations committed, and save the
final session report. All artifacts are written to cooldown-scoped paths."""))

# ── 100 Session summary code ────────────────────────────
cells.append(make_cell("code", """\
import datetime

print("=" * 60)
print("  SESSION SUMMARY (Context Mode)")
print("=" * 60)
print(f"  Device ID:      {ctx.device_id}")
print(f"  Cooldown ID:    {ctx.cooldown_id}")
print(f"  Wiring Rev:     {ctx.wiring_rev}")
print(f"  Config Hash:    {ctx.config_hash}")
print(f"  Build hash:     {ss.build_hash}")
print(f"  Git commit:     {ss.git_commit or 'unknown'}")
print(f"  Timestamp:      {ss.build_timestamp}")
print(f"  Experiment Path: {session.experiment_path}")
print()

# Calibration file location
print(f"  Calibration file: {session.calibration.path}")
print(f"  Calibration version: {session.calibration.data.version}")
cal_ctx = session.calibration.data.context
if cal_ctx:
    print(f"  Calibration device_id:   {cal_ctx.device_id}")
    print(f"  Calibration cooldown_id: {cal_ctx.cooldown_id}")
    print(f"  Calibration wiring_rev:  {cal_ctx.wiring_rev}")
print()

# Collect calibration state machines
all_sms = []
for name in ["sm_rabi", "sm_drag", "sm_readout"]:
    try:
        sm_obj = eval(name)
        info = sm_obj.summary()
        all_sms.append(info)
        state_str = info["state"]
        committed = state_str == "committed"
        print(f"  {info['experiment']:20s}  {state_str:20s}  "
              f"{'COMMITTED' if committed else 'not committed'}")
    except NameError:
        pass

# Waveform regression
print(f"\\n  Waveform regression:  {passed}/{total} passed")

# Schema validation
n_valid = sum(1 for r in schema_results if r.valid)
print(f"  Schema validation:    {n_valid}/{len(schema_results)} passed")

print()

# Save session summary report
report_lines = [
    f"# Session Report (Context Mode)",
    f"",
    f"- Device ID: {ctx.device_id}",
    f"- Cooldown ID: {ctx.cooldown_id}",
    f"- Wiring Rev: {ctx.wiring_rev}",
    f"- Config Hash: {ctx.config_hash}",
    f"- Build hash: {ss.build_hash}",
    f"- Git commit: {ss.git_commit or 'unknown'}",
    f"- Timestamp:  {ss.build_timestamp}",
    f"- Report generated: {datetime.datetime.now().isoformat()}",
    f"",
    f"## Calibration State Machines",
    f"",
]
for info in all_sms:
    report_lines.append(f"- **{info['experiment']}**: {info['state']} "
                        f"({info['transitions']} transitions, "
                        f"has_patch={info['has_patch']})")
report_lines += [
    f"",
    f"## Verification",
    f"",
    f"- Waveform regression: {passed}/{total} passed",
    f"- Schema validation: {n_valid}/{len(schema_results)} passed",
]

am.save_report("session_summary", "\\n".join(report_lines))

# List all artifacts
print("Artifacts:")
for artifact in am.list_artifacts():
    if artifact.is_file():
        print(f"  {artifact.relative_to(am.root)}")

print()
print("=" * 60)
from qubox_v2.core.artifact_manager import cleanup_artifacts
removed = cleanup_artifacts(str(session.experiment_path), keep_latest=5, current_hash=ss.build_hash)
if removed:
    print(f"  Cleaned up {len(removed)} old artifact directories.")
print("  Done.")"""))

# ── 101 Context mismatch heading ────────────────────────
cells.append(make_cell("markdown", """\
## 12. Context Mismatch Protection Demo

If you try to load calibration from a different device or with a mismatched
wiring revision, the system raises `ContextMismatchError` (in strict mode)
or logs a warning (in non-strict mode)."""))

# ── 102 Context mismatch code ───────────────────────────
cells.append(make_cell("code", """\
from qubox_v2.core.errors import ContextMismatchError
from qubox_v2.core.experiment_context import ExperimentContext
from qubox_v2.calibration.store import CalibrationStore

# Simulate a mismatched context
wrong_ctx = ExperimentContext(
    device_id="different_device",
    cooldown_id=COOLDOWN_ID,
    wiring_rev="00000000",
)

try:
    bad_store = CalibrationStore(
        session.calibration.path,
        context=wrong_ctx,
        strict_context=True,
    )
except ContextMismatchError as e:
    print(f"BLOCKED: Context mismatch detected!\\n  {e}")
else:
    print("No mismatch (calibration file may not have a context block yet)")

print(f"\\nActive context:  device={ctx.device_id}, cooldown={ctx.cooldown_id}")
print(f"Wrong context:   device={wrong_ctx.device_id}, cooldown={wrong_ctx.cooldown_id}")"""))

# ── 103 CW heading ──────────────────────────────────────
cells.append(make_cell("markdown", """\
## 13. Utility: Continuous-Wave Output

Drive a target element continuously for diagnostics such as
spectrum analyser alignment or mixer leakage checks."""))

# ── 104 CW code ─────────────────────────────────────────
cells.append(make_cell("code", """\
from qubox_v2.programs import cQED_programs

target_element = attr.qb_el
cw_pulse = "const_x180"
cw_gain = 0.5
truncate_clks = 250

cw_prog = cQED_programs.continuous_wave(
    target_el=target_element,
    pulse=cw_pulse,
    gain=cw_gain,
    truncate_clks=truncate_clks,
)

print(f"Starting CW output on '{target_element}'")
print(f"  pulse      = {cw_pulse}")
print(f"  gain       = {cw_gain}")
print(f"  truncate   = {truncate_clks} clks ({truncate_clks * 4} ns)")
print(f"  This program runs in an INFINITE LOOP.")
print(f"  To stop:  job.halt()")

job = session.hw.qm.execute(cw_prog)
print(f"\\nJob started: {job.id}")
print("Run 'job.halt()' in the next cell to stop.")"""))

# ── 105 CW halt code ────────────────────────────────────
cells.append(make_cell("code", """\
# --- Stop CW output ---
job.halt()
print("CW output halted.")"""))

# ── 106 Close heading ───────────────────────────────────
cells.append(make_cell("markdown", "## 14. Close Session"))

# ── 107 Close code ──────────────────────────────────────
cells.append(make_cell("code", """\
session.close()
print("Session closed.")
print(f"All calibrations saved to cooldown-scoped path: {session.experiment_path}")"""))

# ── 108 Final summary markdown ──────────────────────────
cells.append(make_cell("markdown", """\
---

## Summary

All experiment classes follow the unified `run() -> analyze() -> plot()` protocol:

```python
exp = ExperimentClass(session)
result = exp.run(...)
analysis = exp.analyze(result, update_calibration=True)
exp.plot(analysis)
print(analysis.metrics)
```

### Context Mode vs Legacy Mode

| Feature | Context Mode (this notebook) | Legacy Mode |
|---------|-----|------|
| Session init | `SessionManager(device_id=..., cooldown_id=...)` | `SessionManager("./seq_1_device")` |
| Calibration scoping | Per-cooldown directory | Single flat directory |
| Stale-cal protection | `ContextMismatchError` on device/wiring mismatch | None |
| Config paths | Device-level + cooldown-level separation | All in one `config/` |
| Artifact paths | `cooldowns/<id>/artifacts/` | `artifacts/` |
| `session.context` | `ExperimentContext(device_id, cooldown_id, ...)` | `None` |

### Switching Cooldowns

To start a new cooldown with the same device:

```python
registry.create_cooldown("post_cavity_sample_A", "cd_2025_03_15")
session = SessionManager(
    device_id="post_cavity_sample_A",
    cooldown_id="cd_2025_03_15",
    registry_base=Path("E:/qubox"),
    qop_ip="10.157.36.68",
)
session.open()
# Fresh calibrations — no risk of stale data from previous cooldown
```

### Architecture Integration

| Component | Where | Purpose |
|---|---|---|
| `DeviceRegistry` | Section 1 | Device + cooldown directory management |
| `ExperimentContext` | Section 2 | Immutable context identity (device + cooldown + wiring) |
| `CalibrationContext` | Section 2 | Context block stamped in calibration.json |
| `ContextMismatchError` | Section 12 | Prevents stale-calibration reuse |
| `SessionState` | Section 2.1 | Immutable config snapshot with SHA-256 build hash |
| `CalibrationOrchestrator` | All cal sections | Artifact -> Patch -> Commit lifecycle |
| `CalibrationStateMachine` | Section 6.1b | Lifecycle enforcement for calibration commits |
| `ArtifactManager` | Section 11.2 | Build-hash keyed artifact storage |"""))


# ── Assemble notebook ───────────────────────────────────
nb = {
    "nbformat": 4,
    "nbformat_minor": 2,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.11.0",
        },
    },
    "cells": cells,
}

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

print(f"Notebook written: {OUTPUT}")
print(f"Total cells: {len(cells)}")
code_cells = sum(1 for c in cells if c["cell_type"] == "code")
md_cells = sum(1 for c in cells if c["cell_type"] == "markdown")
print(f"  Code cells: {code_cells}")
print(f"  Markdown cells: {md_cells}")
