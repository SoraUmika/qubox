#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Hardware smoke test: constant pulse output.

Plays a constant pulse on each element and verifies it executes without error.
This is the most basic hardware acceptance test -- if this fails, nothing else
will work.

Usage:
    python smoke_test_const_pulse.py --config-dir seq_1_device/config

Requires:
    - OPX hardware connected
    - QMM accessible
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def run_const_smoke(config_dir: str | Path) -> bool:
    """Play constant pulses on all elements and verify execution."""
    import time
    from qm.QuantumMachinesManager import QuantumMachinesManager
    from qm import qua

    config_dir = Path(config_dir)
    all_ok = True

    print("=" * 50)
    print("  Smoke Test: Constant Pulse")
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
        print(f"    Connected. QM ID: {qm.id}")
    except Exception as exc:
        print(f"    FAIL: {exc}")
        return False

    # Step 3: Play constant pulse on each element
    print("\n[3] Playing constant pulses...")
    elements = list(ss.hardware.get("elements", {}).keys())

    for element in elements:
        print(f"\n    Element: {element}")
        try:
            with qua.program() as smoke_prog:
                with qua.infinite_loop_():
                    qua.play("const", element)
                    qua.wait(1000, element)

            # Execute for a short time
            job = qm.execute(smoke_prog)

            time.sleep(0.5)
            job.halt()

            # Check for errors
            execution_report = job.execution_report()
            if execution_report.has_errors():
                print(f"      FAIL: Execution errors: {execution_report.errors()}")
                all_ok = False
            else:
                print(f"      PASS: Constant pulse played without error")

        except KeyError:
            print(f"      SKIP: Element '{element}' has no 'const' operation")
        except Exception as exc:
            print(f"      FAIL: {exc}")
            all_ok = False

    # Step 4: Close QM
    print("\n[4] Closing QM...")
    try:
        qm.close()
        print("    Done.")
    except Exception:
        pass

    print("\n" + "=" * 50)
    print(f"  Result: {'ALL PASS' if all_ok else 'SOME FAILURES'}")
    print("=" * 50)

    return all_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Constant pulse smoke test")
    parser.add_argument("--config-dir", "-c", required=True)
    args = parser.parse_args(argv)

    ok = run_const_smoke(args.config_dir)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
