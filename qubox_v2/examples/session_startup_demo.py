# qubox_v2/examples/session_startup_demo.py
"""End-to-end session startup demo.

Demonstrates the new declarative architecture flow:

1. Schema validation of all config files
2. SessionState construction (immutable snapshot + build hash)
3. PulseFactory compilation from pulse_specs.json
4. ArtifactManager setup (build-hash keyed)
5. CalibrationStateMachine lifecycle
6. Verification checks

This script runs in "dry" mode — no hardware connection required.
It exercises all new modules against the config directory.

Usage
-----
::

    python -m qubox_v2.examples.session_startup_demo \\
        --config-dir seq_1_device/config

Or from a notebook::

    from qubox_v2.examples.session_startup_demo import run_demo
    run_demo("seq_1_device/config")
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_logger = logging.getLogger(__name__)


def run_demo(config_dir: str | Path, *, verbose: bool = False) -> bool:
    """Run the full session startup demo.

    Parameters
    ----------
    config_dir : str | Path
        Path to the config directory.
    verbose : bool
        Enable debug logging.

    Returns
    -------
    bool
        True if all steps passed.
    """
    config_dir = Path(config_dir)
    all_ok = True

    print("=" * 60)
    print("  qubox_v2 Session Startup Demo")
    print("=" * 60)
    print(f"  Config directory: {config_dir}")
    print()

    # ---------------------------------------------------------------
    # Step 1: Schema Validation
    # ---------------------------------------------------------------
    print("Step 1: Schema Validation")
    print("-" * 40)

    try:
        from ..core.schemas import validate_config_dir
        results = validate_config_dir(config_dir)

        for r in results:
            status = "PASS" if r.valid else "FAIL"
            print(f"  {status} version={r.version}")
            if r.errors:
                for e in r.errors:
                    print(f"       ERROR: {e}")
            if r.warnings:
                for w in r.warnings:
                    print(f"       WARN:  {w}")

        if any(not r.valid for r in results):
            print("  ** Schema validation FAILED **")
            all_ok = False
        else:
            print("  All schemas valid.")
    except Exception as exc:
        print(f"  Schema validation error: {exc}")
        all_ok = False

    print()

    # ---------------------------------------------------------------
    # Step 2: SessionState Construction
    # ---------------------------------------------------------------
    print("Step 2: SessionState Construction")
    print("-" * 40)

    session_state = None
    try:
        from ..core.session_state import SessionState
        session_state = SessionState.from_config_dir(config_dir)
        print(session_state.summary())
    except FileNotFoundError as exc:
        print(f"  Required file missing: {exc}")
        all_ok = False
    except Exception as exc:
        print(f"  SessionState construction error: {exc}")
        all_ok = False

    print()

    # ---------------------------------------------------------------
    # Step 3: PulseFactory Compilation
    # ---------------------------------------------------------------
    print("Step 3: PulseFactory Compilation")
    print("-" * 40)

    compiled = None
    if session_state and session_state.pulse_specs.get("specs"):
        try:
            from ..pulses.factory import PulseFactory
            factory = PulseFactory(session_state.pulse_specs)
            compiled = factory.compile_all()
            print(f"  Compiled {len(compiled)} pulse specs:")
            for name, (I_wf, Q_wf, meta) in compiled.items():
                shape = meta.get("shape", "?")
                length = meta.get("length", len(I_wf))
                print(f"    {name}: shape={shape}, length={length}")
        except Exception as exc:
            print(f"  PulseFactory error: {exc}")
            all_ok = False
    else:
        print("  No pulse_specs.json found or no specs defined.")
        print("  (This is expected if still using legacy pulses.json)")

    print()

    # ---------------------------------------------------------------
    # Step 4: ArtifactManager Setup
    # ---------------------------------------------------------------
    print("Step 4: ArtifactManager Setup")
    print("-" * 40)

    if session_state:
        try:
            from ..core.artifact_manager import ArtifactManager
            experiment_path = config_dir.parent
            am = ArtifactManager(experiment_path, session_state.build_hash)
            print(f"  Artifact root: {am.root}")

            # Save session state artifact
            state_path = am.save_session_state(session_state.to_dict())
            print(f"  Session state saved: {state_path}")

            # List existing artifacts
            artifacts = am.list_artifacts()
            print(f"  Total artifacts: {len(artifacts)}")
        except Exception as exc:
            print(f"  ArtifactManager error: {exc}")
            all_ok = False
    else:
        print("  Skipped (no SessionState)")

    print()

    # ---------------------------------------------------------------
    # Step 5: CalibrationStateMachine Demo
    # ---------------------------------------------------------------
    print("Step 5: CalibrationStateMachine Lifecycle")
    print("-" * 40)

    try:
        from ..calibration.state_machine import (
            CalibrationStateMachine,
            CalibrationState,
            CalibrationPatch,
            PatchValidation,
        )

        sm = CalibrationStateMachine(experiment="demo_power_rabi")
        print(f"  Initial state: {sm.state.value}")

        # Walk through a typical lifecycle
        transitions = [
            CalibrationState.CONFIGURED,
            CalibrationState.ACQUIRING,
            CalibrationState.ACQUIRED,
            CalibrationState.ANALYZING,
        ]

        for target in transitions:
            sm.transition(target)
            print(f"  → {sm.state.value}")

        # Create and attach a patch
        patch = CalibrationPatch(experiment="demo_power_rabi")
        patch.add_change(
            path="pulse_calibrations.qubit.x180.amplitude",
            old_value=0.11165,
            new_value=0.11234,
            dtype="float",
        )
        patch.validation = PatchValidation(
            passed=True,
            checks={"min_r2": True, "bounds_check": True},
        )
        sm.patch = patch

        sm.transition(CalibrationState.ANALYZED)
        print(f"  → {sm.state.value}")

        sm.transition(CalibrationState.PENDING_APPROVAL)
        print(f"  → {sm.state.value}")
        print(f"  Committable: {sm.is_committable()}")

        # Show patch summary
        print()
        print("  Patch Summary:")
        for line in patch.summary().split("\n"):
            print(f"    {line}")

        print()
        print(f"  State machine summary:")
        summary = sm.summary()
        print(f"    Transitions: {summary['transitions']}")
        print(f"    Has patch: {summary['has_patch']}")

    except Exception as exc:
        print(f"  StateMachine error: {exc}")
        all_ok = False

    print()

    # ---------------------------------------------------------------
    # Step 6: Verification Checks
    # ---------------------------------------------------------------
    print("Step 6: Verification Checks")
    print("-" * 40)

    # Schema model checks
    try:
        from ..verification.schema_checks import check_spec_models
        model_result = check_spec_models()
        status = "PASS" if model_result.valid else "FAIL"
        print(f"  Pydantic models: {status}")
        if model_result.errors:
            for e in model_result.errors:
                print(f"    ERROR: {e}")
    except Exception as exc:
        print(f"  Model check error: {exc}")
        all_ok = False

    # Waveform regression (if scipy available)
    try:
        from ..verification.waveform_regression import run_all_checks
        wf_results = run_all_checks()
        passed = sum(1 for r in wf_results if r.passed)
        failed = sum(1 for r in wf_results if not r.passed)
        print(f"  Waveform regression: {passed} passed, {failed} failed")
        if failed > 0:
            for r in wf_results:
                if not r.passed:
                    print(f"    FAIL: [{r.shape}] {r.test_name} — {r.error}")
            all_ok = False
    except Exception as exc:
        print(f"  Waveform regression error: {exc}")
        all_ok = False

    print()

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("=" * 60)
    if all_ok:
        print("  RESULT: ALL STEPS PASSED")
    else:
        print("  RESULT: SOME STEPS FAILED (see above)")
    print("=" * 60)

    return all_ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="qubox_v2 session startup demo")
    parser.add_argument(
        "--config-dir", "-c",
        required=True,
        help="Path to config directory",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
    )
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    ok = run_demo(args.config_dir, verbose=args.verbose)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
