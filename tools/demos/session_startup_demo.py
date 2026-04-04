"""End-to-end session startup demo.

Demonstrates the dry startup path without opening a hardware connection:

1. Schema validation of config files
2. SessionState construction
3. PulseFactory compilation from pulse specs
4. ArtifactManager setup
5. Verification checks

Usage
-----

    python tools/demos/session_startup_demo.py --config-dir seq_1_device/config
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_logger = logging.getLogger(__name__)


def run_demo(config_dir: str | Path, *, verbose: bool = False) -> bool:
    """Run the full session-startup demo and report whether all checks passed."""

    config_dir = Path(config_dir)
    all_ok = True

    print("=" * 60)
    print("  qubox Session Startup Demo")
    print("=" * 60)
    print(f"  Config directory: {config_dir}")
    print()

    print("Step 1: Schema Validation")
    print("-" * 40)
    try:
        from qubox.schemas import validate_config_dir

        results = validate_config_dir(config_dir)
        for result in results:
            status = "PASS" if result.valid else "FAIL"
            print(f"  {status} version={result.version}")
            if result.errors:
                for error in result.errors:
                    print(f"       ERROR: {error}")
            if result.warnings:
                for warning in result.warnings:
                    print(f"       WARN:  {warning}")

        if any(not result.valid for result in results):
            print("  ** Schema validation FAILED **")
            all_ok = False
        else:
            print("  All schemas valid.")
    except Exception as exc:
        print(f"  Schema validation error: {exc}")
        all_ok = False
    print()

    print("Step 2: SessionState Construction")
    print("-" * 40)
    session_state = None
    try:
        from qubox.core.session_state import SessionState

        session_state = SessionState.from_config_dir(config_dir)
        print(session_state.summary())
    except FileNotFoundError as exc:
        print(f"  Required file missing: {exc}")
        all_ok = False
    except Exception as exc:
        print(f"  SessionState construction error: {exc}")
        all_ok = False
    print()

    print("Step 3: PulseFactory Compilation")
    print("-" * 40)
    compiled = None
    if session_state and session_state.pulse_specs.get("specs"):
        try:
            from qubox.pulses.factory import PulseFactory

            factory = PulseFactory(session_state.pulse_specs)
            compiled = factory.compile_all()
            print(f"  Compiled {len(compiled)} pulse specs:")
            for name, (i_waveform, q_waveform, meta) in compiled.items():
                shape = meta.get("shape", "?")
                length = meta.get("length", len(i_waveform))
                print(f"    {name}: shape={shape}, length={length}")
        except Exception as exc:
            print(f"  PulseFactory error: {exc}")
            all_ok = False
    else:
        print("  No pulse_specs.json found or no specs defined.")
        print("  (This is expected if the sample still uses pulses.json only.)")
    print()

    print("Step 4: ArtifactManager Setup")
    print("-" * 40)
    if session_state:
        try:
            from qubox.core.artifact_manager import ArtifactManager

            experiment_path = config_dir.parent
            artifact_manager = ArtifactManager(experiment_path, session_state.build_hash)
            print(f"  Artifact root: {artifact_manager.root}")

            state_path = artifact_manager.save_session_state(session_state.to_dict())
            print(f"  Session state saved: {state_path}")

            artifacts = artifact_manager.list_artifacts()
            print(f"  Total artifacts: {len(artifacts)}")
        except Exception as exc:
            print(f"  ArtifactManager error: {exc}")
            all_ok = False
    else:
        print("  Skipped (no SessionState)")
    print()

    print("Step 5: Verification Checks")
    print("-" * 40)
    try:
        from qubox.verification.schema_checks import check_spec_models

        model_result = check_spec_models()
        status = "PASS" if model_result.valid else "FAIL"
        print(f"  Pydantic models: {status}")
        if model_result.errors:
            for error in model_result.errors:
                print(f"    ERROR: {error}")
    except Exception as exc:
        print(f"  Model check error: {exc}")
        all_ok = False

    try:
        from qubox.verification.waveform_regression import run_all_checks

        waveform_results = run_all_checks()
        passed = sum(1 for result in waveform_results if result.passed)
        failed = sum(1 for result in waveform_results if not result.passed)
        print(f"  Waveform regression: {passed} passed, {failed} failed")
        if failed > 0:
            for result in waveform_results:
                if not result.passed:
                    print(f"    FAIL: [{result.shape}] {result.test_name} - {result.error}")
            all_ok = False
    except Exception as exc:
        print(f"  Waveform regression error: {exc}")
        all_ok = False
    print()

    print("=" * 60)
    if all_ok:
        print("  RESULT: ALL STEPS PASSED")
    else:
        print("  RESULT: SOME STEPS FAILED (see above)")
    print("=" * 60)

    return all_ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="qubox session startup demo")
    parser.add_argument("--config-dir", "-c", required=True, help="Path to config directory")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    ok = run_demo(args.config_dir, verbose=args.verbose)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
