#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Hardware smoke test: readout / GE discrimination.

Verifies that readout returns distinguishable ground and excited state
distributions. This validates integration weights, readout pulse compilation,
and the full measurement chain.

Usage:
    python smoke_test_readout.py --config-dir seq_1_device/config

Requires:
    - OPX hardware connected
    - Qubit at known operating point
    - Pi-pulse calibrated (x180 operation available)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


def run_readout_smoke(config_dir: str | Path) -> bool:
    """Run GE discrimination and verify readout fidelity."""
    from qm.QuantumMachinesManager import QuantumMachinesManager
    from qm import qua

    config_dir = Path(config_dir)

    print("=" * 50)
    print("  Smoke Test: Readout / GE Discrimination")
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

    # Step 3: Run GE discrimination
    print("\n[3] Running GE discrimination (500 shots each)...")
    n_shots = 500
    ok = True

    try:
        with qua.program() as ge_prog:
            n = qua.declare(int)
            I_g = qua.declare(qua.fixed)
            Q_g = qua.declare(qua.fixed)
            I_e = qua.declare(qua.fixed)
            Q_e = qua.declare(qua.fixed)

            I_g_stream = qua.declare_stream()
            Q_g_stream = qua.declare_stream()
            I_e_stream = qua.declare_stream()
            Q_e_stream = qua.declare_stream()

            with qua.for_(n, 0, n < n_shots, n + 1):
                # Ground state: measure without pi pulse
                qua.align("qubit", "resonator")
                qua.measure(
                    "readout", "resonator", None,
                    qua.dual_demod.full("cos", "out1", "sin", "out2", I_g),
                    qua.dual_demod.full("minus_sin", "out1", "cos", "out2", Q_g),
                )
                qua.save(I_g, I_g_stream)
                qua.save(Q_g, Q_g_stream)
                qua.wait(250000 // 4, "resonator")  # Cooldown ~250us

                # Excited state: pi pulse then measure
                qua.play("x180", "qubit")
                qua.align("qubit", "resonator")
                qua.measure(
                    "readout", "resonator", None,
                    qua.dual_demod.full("cos", "out1", "sin", "out2", I_e),
                    qua.dual_demod.full("minus_sin", "out1", "cos", "out2", Q_e),
                )
                qua.save(I_e, I_e_stream)
                qua.save(Q_e, Q_e_stream)
                qua.wait(250000 // 4, "resonator")  # Cooldown

            with qua.stream_processing():
                I_g_stream.save_all("I_g")
                Q_g_stream.save_all("Q_g")
                I_e_stream.save_all("I_e")
                Q_e_stream.save_all("Q_e")

        job = qm.execute(ge_prog)
        result_handles = job.result_handles
        result_handles.wait_for_all_values()

        I_g_data = result_handles.get("I_g").fetch_all()
        Q_g_data = result_handles.get("Q_g").fetch_all()
        I_e_data = result_handles.get("I_e").fetch_all()
        Q_e_data = result_handles.get("Q_e").fetch_all()

        print(f"    Received {len(I_g_data)} ground / {len(I_e_data)} excited shots")

        # Compute discrimination metrics
        g_complex = I_g_data + 1j * Q_g_data
        e_complex = I_e_data + 1j * Q_e_data
        g_mean = np.mean(g_complex)
        e_mean = np.mean(e_complex)
        separation = abs(e_mean - g_mean)
        g_std = np.std(np.abs(g_complex - g_mean))
        e_std = np.std(np.abs(e_complex - e_mean))
        snr = separation / ((g_std + e_std) / 2) if (g_std + e_std) > 0 else 0

        print(f"\n    Ground mean: ({np.real(g_mean):.6f}, {np.imag(g_mean):.6f})")
        print(f"    Excited mean: ({np.real(e_mean):.6f}, {np.imag(e_mean):.6f})")
        print(f"    Separation: {separation:.6f}")
        print(f"    SNR: {snr:.2f}")

        # Simple threshold discrimination
        threshold_angle = np.angle(e_mean - g_mean)
        g_rotated = np.real(g_complex * np.exp(-1j * threshold_angle))
        e_rotated = np.real(e_complex * np.exp(-1j * threshold_angle))
        threshold = (np.mean(g_rotated) + np.mean(e_rotated)) / 2

        g_correct = np.sum(g_rotated < threshold)
        e_correct = np.sum(e_rotated >= threshold)
        fidelity = (g_correct + e_correct) / (2 * n_shots)

        print(f"    Fidelity: {fidelity:.2%}")

        # Acceptance criteria
        if snr < 1.0:
            print("    FAIL: SNR < 1.0 -- states are not well-separated")
            ok = False
        else:
            print("    PASS: SNR > 1.0")

        if fidelity < 0.7:
            print("    FAIL: Fidelity < 70% -- readout needs optimization")
            ok = False
        elif fidelity < 0.9:
            print("    WARN: Fidelity < 90% -- acceptable but could be improved")
        else:
            print("    PASS: Fidelity > 90%")

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
    parser = argparse.ArgumentParser(description="Readout smoke test")
    parser.add_argument("--config-dir", "-c", required=True)
    args = parser.parse_args(argv)

    ok = run_readout_smoke(args.config_dir)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
