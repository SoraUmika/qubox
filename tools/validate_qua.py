"""validate_qua.py — QUA program compilation and simulation validator.

Connects to the hosted Quantum Machines server, compiles a QUA program,
optionally simulates it, and reports results.  Exits 0 on success, 1 on failure.

Usage
-----
    python tools/validate_qua.py <program_file.py> [options]

The program file must define a callable named `build_program(config)` that
returns a QUA program (the result of a `program()` context manager), and a
callable named `build_config()` that returns the QM hardware config dict.

Quick-validation example
------------------------
    python tools/validate_qua.py tools/example_program.py --quick

Dry-run (compile only, no simulation)
--------------------------------------
    python tools/validate_qua.py tools/example_program.py --dry-run

Custom server
-------------
    python tools/validate_qua.py tools/example_program.py \\
        --host 10.157.36.68 --cluster Cluster_2
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_HOST         = "10.157.36.68"
DEFAULT_CLUSTER      = "Cluster_2"
DEFAULT_DURATION     = 2000   # simulation duration in clock cycles
QUICK_DURATION       = 500    # --quick flag simulation duration
COMPILE_TIME_TARGET  = 60.0   # seconds; report if exceeded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_module(path: Path) -> Any:
    """Import a Python file as a module."""
    spec = importlib.util.spec_from_file_location("_qua_program", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def _check_server(host: str, cluster: str, timeout: float = 10.0) -> bool:
    """Return True if the QM server is reachable."""
    try:
        from qm import QuantumMachinesManager  # type: ignore[import]
        qmm = QuantumMachinesManager(host=host, cluster_name=cluster, timeout=timeout)
        _ = qmm.version()
        return True
    except Exception as exc:
        print(f"[ERROR] Cannot reach QM server at {host} / {cluster}: {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------

def validate(
    program_file: Path,
    *,
    host: str = DEFAULT_HOST,
    cluster: str = DEFAULT_CLUSTER,
    duration: int = DEFAULT_DURATION,
    dry_run: bool = False,
    n_avg: int = 1,
    verbose: bool = True,
) -> bool:
    """Compile and (optionally) simulate a QUA program.

    Parameters
    ----------
    program_file
        Path to a Python file that exposes ``build_config()`` and
        ``build_program(config)``.
    host
        QM server hostname.
    cluster
        QM cluster name.
    duration
        Simulation duration in clock cycles.
    dry_run
        If True, only compile — do not simulate.
    n_avg
        Number of averages (use 1 for structural validation).
    verbose
        Print progress messages.

    Returns
    -------
    bool
        True on success.
    """
    if verbose:
        print(f"[INFO] Loading program file: {program_file}")

    if not program_file.exists():
        print(f"[ERROR] File not found: {program_file}", file=sys.stderr)
        return False

    # ── Load module ──────────────────────────────────────────────────────────
    try:
        module = _load_module(program_file)
    except Exception as exc:
        print(f"[ERROR] Failed to import {program_file}: {exc}", file=sys.stderr)
        return False

    if not hasattr(module, "build_config"):
        print("[ERROR] Program file must define build_config()", file=sys.stderr)
        return False
    if not hasattr(module, "build_program"):
        print("[ERROR] Program file must define build_program(config)", file=sys.stderr)
        return False

    # ── Build config and program ─────────────────────────────────────────────
    try:
        config = module.build_config()
    except Exception as exc:
        print(f"[ERROR] build_config() raised: {exc}", file=sys.stderr)
        return False

    try:
        t0 = time.perf_counter()
        program = module.build_program(config, n_avg=n_avg)
        compile_time = time.perf_counter() - t0
    except TypeError:
        # build_program may not accept n_avg
        try:
            t0 = time.perf_counter()
            program = module.build_program(config)
            compile_time = time.perf_counter() - t0
        except Exception as exc:
            print(f"[ERROR] build_program() raised: {exc}", file=sys.stderr)
            return False
    except Exception as exc:
        print(f"[ERROR] build_program() raised: {exc}", file=sys.stderr)
        return False

    if verbose:
        status = "OK" if compile_time < COMPILE_TIME_TARGET else "SLOW"
        print(f"[{status}] Program built in {compile_time:.2f}s "
              f"(target: < {COMPILE_TIME_TARGET:.0f}s)")

    if compile_time >= COMPILE_TIME_TARGET:
        print(f"[WARN] Compilation exceeded {COMPILE_TIME_TARGET:.0f}s target. "
              "Report this.", file=sys.stderr)

    if dry_run:
        if verbose:
            print("[INFO] --dry-run: skipping simulation.")
        return True

    # ── Check server reachability ────────────────────────────────────────────
    if verbose:
        print(f"[INFO] Connecting to QM server: {host} / {cluster}")

    if not _check_server(host, cluster):
        return False

    # ── Simulate ─────────────────────────────────────────────────────────────
    try:
        from qm import QuantumMachinesManager, SimulationConfig  # type: ignore[import]
        qmm = QuantumMachinesManager(host=host, cluster_name=cluster)

        sim_config = SimulationConfig(duration=duration)

        if verbose:
            print(f"[INFO] Simulating for {duration} clock cycles ...")

        t0 = time.perf_counter()
        job = qmm.simulate(config, program, sim_config)
        sim_time = time.perf_counter() - t0

        samples = job.get_simulated_samples()
        analog_channels = getattr(samples, "analog", {})
        digital_channels = getattr(samples, "digital", {})

        if verbose:
            print(f"[OK]   Simulation completed in {sim_time:.2f}s")
            print(f"       Analog channels  : {sorted(analog_channels.keys())}")
            print(f"       Digital channels : {sorted(digital_channels.keys())}")

        return True

    except ImportError:
        print("[ERROR] qm package not installed. Install qm-qua to run simulation.",
              file=sys.stderr)
        return False
    except Exception as exc:
        print(f"[ERROR] Simulation failed: {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile and simulate a QUA program against the hosted QM server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "program_file",
        type=Path,
        help="Python file defining build_config() and build_program(config).",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"QM server hostname. Default: {DEFAULT_HOST}",
    )
    parser.add_argument(
        "--cluster",
        default=DEFAULT_CLUSTER,
        help=f"QM cluster name. Default: {DEFAULT_CLUSTER}",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION,
        help=f"Simulation duration in clock cycles. Default: {DEFAULT_DURATION}",
    )
    parser.add_argument(
        "--n-avg",
        type=int,
        default=1,
        dest="n_avg",
        help="Number of averages for the compiled program. Default: 1",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help=f"Fast structural check: n_avg=1, duration={QUICK_DURATION} clock cycles.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compile only — do not simulate.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output (errors still shown).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    duration = QUICK_DURATION if args.quick else args.duration
    n_avg    = 1 if args.quick else args.n_avg

    success = validate(
        program_file=args.program_file,
        host=args.host,
        cluster=args.cluster,
        duration=duration,
        dry_run=args.dry_run,
        n_avg=n_avg,
        verbose=not args.quiet,
    )

    if success:
        print("[PASS] Validation complete.")
        return 0
    else:
        print("[FAIL] Validation failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
