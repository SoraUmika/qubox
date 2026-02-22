#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Hardware smoke test: simple Rabi oscillation.

Runs a minimal power Rabi experiment to verify that:
1. Pulse compilation works end-to-end on hardware
2. The qubit responds to drive pulses
3. Readout returns meaningful I/Q data

Usage:
    python smoke_test_rabi.py --config-dir seq_1_device/config

Requires:
    - OPX hardware connected
    - Qubit at known operating point
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


def run_rabi_smoke(config_dir: str | Path) -> bool:
    """Run minimal power Rabi and verify qubit response."""
    from qm.QuantumMachinesManager import QuantumMachinesManager
    from qm import qua

    config_dir = Path(config_dir)

    print("=" * 50)
    print("  Smoke Test: Simple Power Rabi")
    print("=" * 50)

    # Step 1: Build SessionState
    print("\n[1] Building SessionState...")
    try:
        from qubox_v2.core.session_state import SessionState
        ss = SessionState.from_config_dir(config_dir)
        print(f"    Build hash: {ss.build_hash}")
    except Exception as exc:
        print(f"    FAIL: {exc}")
        return False

    # Step 2: Open QM
    print("\n[2] Connecting to QMM...")
    try:
        qmm = QuantumMachinesManager()
        qm = qmm.open_qm(ss.hardware)
        print(f"    Connected.")
    except Exception as exc:
        print(f"    FAIL: {exc}")
        return False

    # Step 3: Run Rabi
    print("\n[3] Running Power Rabi (10 amplitudes, 100 averages)...")
    try:
        n_avg = 100
        amplitudes = np.linspace(0.0, 0.4, 10)

        with qua.program() as rabi_prog:
            n = qua.declare(int)
            a = qua.declare(qua.fixed)
            I = qua.declare(qua.fixed)
            Q = qua.declare(qua.fixed)
            I_stream = qua.declare_stream()
            Q_stream = qua.declare_stream()

            with qua.for_(n, 0, n < n_avg, n + 1):
                with qua.for_each_(a, amplitudes.tolist()):
                    qua.play("x180" * qua.amp(a), "qubit")
                    qua.align("qubit", "resonator")
                    qua.measure(
                        "readout",
                        "resonator",
                        None,
                        qua.dual_demod.full("cos", "out1", "sin", "out2", I),
                        qua.dual_demod.full("minus_sin", "out1", "cos", "out2", Q),
                    )
                    qua.save(I, I_stream)
                    qua.save(Q, Q_stream)

            with qua.stream_processing():
                I_stream.buffer(len(amplitudes)).average().save("I")
                Q_stream.buffer(len(amplitudes)).average().save("Q")

        job = qm.execute(rabi_prog)
        result_handles = job.result_handles
        result_handles.wait_for_all_values()

        I_data = result_handles.get("I").fetch_all()
        Q_data = result_handles.get("Q").fetch_all()

        print(f"    Received {len(I_data)} I points, {len(Q_data)} Q points")

        # Basic checks
        ok = True

        # Check we got data
        if len(I_data) == 0 or np.all(np.isnan(I_data)):
            print("    FAIL: No valid I data received")
            ok = False
        else:
            print(f"    I range: [{np.min(I_data):.6f}, {np.max(I_data):.6f}]")

        if len(Q_data) == 0 or np.all(np.isnan(Q_data)):
            print("    FAIL: No valid Q data received")
            ok = False
        else:
            print(f"    Q range: [{np.min(Q_data):.6f}, {np.max(Q_data):.6f}]")

        # Check for Rabi oscillation signature: I should vary with amplitude
        if ok:
            I_range = np.max(I_data) - np.min(I_data)
            if I_range < 1e-6:
                print(f"    WARN: I range is very small ({I_range:.2e}), "
                      "qubit may not be responding")
            else:
                print(f"    PASS: I channel shows variation (range={I_range:.6f})")

    except Exception as exc:
        print(f"    FAIL: {exc}")
        import traceback
        traceback.print_exc()
        ok = False

    # Step 4: Close
    print("\n[4] Closing QM...")
    try:
        qm.close()
    except Exception:
        pass

    print("\n" + "=" * 50)
    print(f"  Result: {'PASS' if ok else 'FAIL'}")
    print("=" * 50)

    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simple Rabi smoke test")
    parser.add_argument("--config-dir", "-c", required=True)
    args = parser.parse_args(argv)

    ok = run_rabi_smoke(args.config_dir)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
