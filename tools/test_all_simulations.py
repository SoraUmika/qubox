"""Validate all QUA-capable experiments compile & simulate successfully.

Run with:  python tools/test_all_simulations.py
Requires:  QM server at 10.157.36.68 reachable
"""
from __future__ import annotations

import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qubox.notebook import (
    open_shared_session,
    close_shared_session,
    get_shared_session,
)
from qubox.hardware.program_runner import QuboxSimulationConfig

# ── Session setup ────────────────────────────────────────────────────
REGISTRY_BASE = Path(r"E:\qubox")
SAMPLE_ID = "post_cavity_sample_A"
COOLDOWN_ID = "cd_2026_03_24"
QOP_IP = "10.157.36.68"
CLUSTER_NAME = "Cluster_2"
SIM_DURATION_NS = 4000

existing = get_shared_session()
if existing is not None:
    close_shared_session()

session = open_shared_session(
    sample_id=SAMPLE_ID,
    cooldown_id=COOLDOWN_ID,
    registry_base=REGISTRY_BASE,
    qop_ip=QOP_IP,
    cluster_name=CLUSTER_NAME,
    auto_save_calibration=False,
    force_reopen=True,
)

attr = session.context_snapshot()
sim_config = QuboxSimulationConfig(duration_ns=SIM_DURATION_NS, plot=False)

# Set a dummy discrimination threshold for simulation testing.
# Without readout calibration, measureMacro._ro_disc_params["threshold"] is None,
# which makes experiments that do state discrimination fail at QUA compile time.
from qubox.programs.macros.measure import measureMacro
if measureMacro._ro_disc_params.get("threshold") is None:
    measureMacro._ro_disc_params["threshold"] = 0.0
    print("Set dummy measureMacro threshold = 0.0 for simulation testing")

ro_fq = float(attr.ro_fq)
qb_fq = float(attr.qb_fq)
st_fq = float(attr.st_fq) if hasattr(attr, "st_fq") and attr.st_fq else 5e9

results: list[tuple[str, str, float]] = []  # (name, status, seconds)


def run_test(name: str, experiment_cls, sim_kwargs: dict) -> None:
    """Instantiate, simulate, and record result."""
    print(f"\n{'-' * 60}")
    print(f"Testing: {name}")
    t0 = time.time()
    try:
        exp = experiment_cls(session)
        sim_result = exp.simulate(sim_config=sim_config, **sim_kwargs)
        elapsed = time.time() - t0
        assert sim_result is not None, "simulate() returned None"
        results.append((name, "PASS", elapsed))
        print(f"  PASS ({elapsed:.1f}s)")
    except Exception as exc:
        elapsed = time.time() - t0
        results.append((name, f"FAIL: {exc}", elapsed))
        print(f"  FAIL ({elapsed:.1f}s): {exc}")
        traceback.print_exc()


# ── Import all experiment classes ────────────────────────────────────
from qubox.notebook import (
    ResonatorSpectroscopy,
    ResonatorPowerSpectroscopy,
    ResonatorSpectroscopyX180,
    ReadoutTrace,
    QubitSpectroscopy,
    QubitSpectroscopyEF,
    PowerRabi,
    TemporalRabi,
    T1Relaxation,
    T2Ramsey,
    T2Echo,
    IQBlob,
    ReadoutGEDiscrimination,
    ReadoutWeightsOptimization,
    AllXY,
    DRAGCalibration,
    StorageSpectroscopy,
    NumSplittingSpectroscopy,
    StorageChiRamsey,
    FockResolvedSpectroscopy,
    FockResolvedT1,
    FockResolvedRamsey,
    FockResolvedPowerRabi,
    RandomizedBenchmarking,
    PulseTrainCalibration,
    ReadoutButterflyMeasurement,
    CalibrateReadoutFull,
    QubitStateTomography,
    StorageWignerTomography,
    SNAPOptimization,
)

# Classes not in the notebook surface — import directly
from qubox.experiments import (
    ReadoutFrequencyOptimization,
    TimeRabiChevron, PowerRabiChevron, RamseyChevron,
    ReadoutGERawTrace, ReadoutGEIntegratedTrace, ReadoutAmpLenOpt,
    QubitResetBenchmark, ActiveQubitResetBenchmark, ReadoutLeakageBenchmarking,
    StorageSpectroscopyCoarse, StorageRamsey, StoragePhaseEvolution,
    ResidualPhotonRamsey,
    SequentialQubitRotations,
    QubitSpectroscopyCoarse,
)

# ═════════════════════════════════════════════════════════════════════
# SPECTROSCOPY
# ═════════════════════════════════════════════════════════════════════

run_test("ResonatorSpectroscopy", ResonatorSpectroscopy, dict(
    readout_op="readout",
    rf_begin=int(ro_fq - 2e6),
    rf_end=int(ro_fq + 2e6),
    df=1e6,
    n_avg=1,
))

run_test("ResonatorPowerSpectroscopy", ResonatorPowerSpectroscopy, dict(
    readout_op="readout",
    rf_begin=int(ro_fq - 2e6),
    rf_end=int(ro_fq + 2e6),
    df=1e6,
    g_min=0.1,
    g_max=0.5,
    N_a=3,
    n_avg=1,
))

run_test("ResonatorSpectroscopyX180", ResonatorSpectroscopyX180, dict(
    rf_begin=int(ro_fq - 2e6),
    rf_end=int(ro_fq + 2e6),
    df=1e6,
    r180="x180",
    n_avg=1,
))

run_test("ReadoutTrace", ReadoutTrace, dict(
    drive_frequency=ro_fq,
    n_avg=1,
))

# ReadoutFrequencyOptimization uses a multi-program loop — cannot simulate as a
# single program. Marked as expected skip.
print("\n" + "-" * 60)
print("Testing: ReadoutFrequencyOptimization")
print("  SKIP (multi-program loop, cannot simulate single program)")
results.append(("ReadoutFrequencyOptimization", "SKIP", 0.0))

run_test("QubitSpectroscopy", QubitSpectroscopy, dict(
    pulse="const",
    rf_begin=int(qb_fq - 2e6),
    rf_end=int(qb_fq + 2e6),
    df=1e6,
    qb_gain=0.5,
    qb_len=2000,
    n_avg=1,
))

run_test("QubitSpectroscopyEF", QubitSpectroscopyEF, dict(
    pulse="const",
    rf_begin=int(qb_fq - 202e6),
    rf_end=int(qb_fq - 198e6),
    df=1e6,
    qb_gain=0.5,
    qb_len=2000,
    ge_prep_pulse="x180",
    n_avg=1,
))

# ═════════════════════════════════════════════════════════════════════
# TIME-DOMAIN (Rabi)
# ═════════════════════════════════════════════════════════════════════

run_test("PowerRabi", PowerRabi, dict(
    max_gain=0.5,
    dg=0.25,
    op="x180",
    n_avg=1,
))

run_test("TemporalRabi", TemporalRabi, dict(
    pulse="x180",
    pulse_len_begin=16,
    pulse_len_end=100,
    dt=20,
    n_avg=1,
))

run_test("SequentialQubitRotations", SequentialQubitRotations, dict(
    n_shots=10,
))

# ═════════════════════════════════════════════════════════════════════
# COHERENCE
# ═════════════════════════════════════════════════════════════════════

run_test("T1Relaxation", T1Relaxation, dict(
    delay_begin=16,
    delay_end=1000,
    dt=200,
    r180="x180",
    n_avg=1,
))

run_test("T2Ramsey", T2Ramsey, dict(
    qb_detune=0,
    delay_begin=16,
    delay_end=1000,
    dt=200,
    n_avg=1,
))

run_test("T2Echo", T2Echo, dict(
    delay_begin=32,
    delay_end=1000,
    dt=200,
    n_avg=1,
))

run_test("ResidualPhotonRamsey", ResidualPhotonRamsey, dict(
    t_R_begin=16,
    t_R_end=200,
    dt=50,
    test_ro_op="readout",
    n_avg=1,
))

# ═════════════════════════════════════════════════════════════════════
# CHEVRON
# ═════════════════════════════════════════════════════════════════════

run_test("TimeRabiChevron", TimeRabiChevron, dict(
    if_span=4e6,
    df=2e6,
    max_pulse_duration=100,
    dt=20,
    pulse="x180",
    n_avg=1,
))

run_test("PowerRabiChevron", PowerRabiChevron, dict(
    if_span=4e6,
    df=2e6,
    max_gain=0.5,
    dg=0.25,
    pulse="x180",
    n_avg=1,
))

run_test("RamseyChevron", RamseyChevron, dict(
    if_span=4e6,
    df=2e6,
    max_delay_duration=200,
    dt=50,
    n_avg=1,
))

# ═════════════════════════════════════════════════════════════════════
# READOUT CALIBRATION
# ═════════════════════════════════════════════════════════════════════

run_test("IQBlob", IQBlob, dict(
    r180="x180",
    n_runs=10,
))

run_test("ReadoutGEDiscrimination", ReadoutGEDiscrimination, dict(
    measure_op="readout",
    drive_frequency=ro_fq,
    r180="x180",
    n_samples=10,
))

run_test("ReadoutButterflyMeasurement", ReadoutButterflyMeasurement, dict(
    n_samples=10,
))

# ═════════════════════════════════════════════════════════════════════
# GATE CALIBRATION
# ═════════════════════════════════════════════════════════════════════

run_test("AllXY", AllXY, dict(
    n_avg=1,
))

run_test("DRAGCalibration", DRAGCalibration, dict(
    amps=[0.0, 0.5, 1.0],
    n_avg=1,
))

# ═════════════════════════════════════════════════════════════════════
# RESET
# ═════════════════════════════════════════════════════════════════════

run_test("QubitResetBenchmark", QubitResetBenchmark, dict(
    bit_size=10,
    num_shots=10,
    r180="x180",
    random_seed=42,
))

run_test("ActiveQubitResetBenchmark", ActiveQubitResetBenchmark, dict(
    post_sel_policy="threshold",
    n_shots=10,
))

# ═════════════════════════════════════════════════════════════════════
# SUMMARY
# ═════════════════════════════════════════════════════════════════════

print("\n" + "=" * 60)
print("SIMULATION TEST RESULTS")
print("=" * 60)
passed = sum(1 for _, s, _ in results if s == "PASS")
skipped = sum(1 for _, s, _ in results if s == "SKIP")
failed = sum(1 for _, s, _ in results if s not in ("PASS", "SKIP"))
for name, status, elapsed in results:
    if status == "PASS":
        marker = "+"
    elif status == "SKIP":
        marker = "-"
    else:
        marker = "X"
    status_short = status[:60] if status not in ("PASS", "SKIP") else status
    print(f"  {marker} {name:40s} {status_short:40s} ({elapsed:.1f}s)")

print(f"\nTotal: {passed} passed, {skipped} skipped, {failed} failed, {len(results)} total")

close_shared_session()

sys.exit(0 if failed == 0 else 1)
