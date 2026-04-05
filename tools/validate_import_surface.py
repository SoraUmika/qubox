"""Post-migration import verification for the live qubox package surface."""
from __future__ import annotations

import sys
import traceback

results: list[tuple[str, str] | tuple[str, str, str]] = []


def check(label: str, fn) -> None:
    try:
        fn()
        results.append(("OK", label))
        print(f"  OK  {label}")
    except Exception as exc:
        results.append(("FAIL", label, str(exc)))
        print(f"  FAIL {label}: {exc}")
        traceback.print_exc()


print(f"Python: {sys.version}")
print()

# --- Core package ---
check("import qubox", lambda: __import__("qubox"))
check(
    "core.errors",
    lambda: __import__("qubox.core.errors", fromlist=["QuboxError", "ConfigError", "ContextMismatchError"]),
)
check(
    "core.types merged enums",
    lambda: exec(
        """
from qubox.core.types import ExecMode, PulseType
assert hasattr(ExecMode, 'HARDWARE')
assert hasattr(ExecMode, 'RUN')
assert hasattr(PulseType, 'CONSTANT')
assert hasattr(PulseType, 'CONTROL')
"""
    ),
)

# --- Hardware ---
check(
    "hardware imports",
    lambda: __import__("qubox.hardware", fromlist=["ConfigEngine", "HardwareController", "ProgramRunner", "QueueManager"]),
)

# --- Programs ---
check(
    "programs.macros.measure",
    lambda: __import__("qubox.programs.macros.measure", fromlist=["measureMacro"]),
)

# --- Experiments ---
check(
    "experiments (spectroscopy)",
    lambda: __import__("qubox.experiments", fromlist=["QubitSpectroscopy", "ResonatorSpectroscopy"]),
)
check(
    "experiments (time_domain)",
    lambda: __import__("qubox.experiments", fromlist=["PowerRabi", "T1Relaxation", "T2Ramsey", "T2Echo"]),
)
check(
    "experiments (cavity)",
    lambda: __import__("qubox.experiments", fromlist=["StorageSpectroscopy", "NumSplittingSpectroscopy"]),
)
check(
    "experiments (tomography)",
    lambda: __import__("qubox.experiments", fromlist=["QubitStateTomography", "StorageWignerTomography"]),
)
check(
    "experiments.result",
    lambda: __import__("qubox.experiments.result", fromlist=["RunResult", "AnalysisResult", "ProgramBuildResult"]),
)
check(
    "experiments.session",
    lambda: __import__("qubox.experiments.session", fromlist=["SessionManager"]),
)

# --- Session ---
check("session.session (Session class)", lambda: __import__("qubox.session.session", fromlist=["Session"]))

# --- Calibration ---
check(
    "calibration (store + mixer)",
    lambda: __import__("qubox.calibration", fromlist=["CalibrationStore", "MixerCalibrationConfig"]),
)

# --- Devices ---
check(
    "devices (manager + resolver)",
    lambda: __import__("qubox.devices", fromlist=["DeviceManager", "ContextResolver", "SampleRegistry"]),
)

# --- Notebook import surface ---
check(
    "notebook (current surfaces)",
    lambda: exec(
        """
from qubox.notebook import (
    QubitSpectroscopy, PowerRabi, RunResult,
    CalibrationOrchestrator, HardwareDefinition, QuboxSimulationConfig
)
from qubox.notebook.advanced import CalibrationStore, SampleRegistry
"""
    ),
)

# --- Gates ---
check(
    "gates.hardware",
    lambda: __import__(
        "qubox.gates",
        fromlist=["QubitRotationHardware", "DisplacementHardware", "SQRHardware", "SNAPHardware"],
    ),
)

# --- Verification ---
check(
    "verification.waveform_regression",
    lambda: __import__("qubox.verification.waveform_regression", fromlist=["run_all_checks"]),
)

# --- Core metadata replacement ---
check("core.device_metadata", lambda: __import__("qubox.core.device_metadata", fromlist=["DeviceMetadata"]))

# --- Summary ---
print()
ok_count = sum(1 for result in results if result[0] == "OK")
fail_count = sum(1 for result in results if result[0] == "FAIL")
print(f"Results: {ok_count} OK, {fail_count} FAIL out of {len(results)} checks")
if fail_count:
    print("\nFailed checks:")
    for result in results:
        if result[0] == "FAIL":
            print(f"  - {result[1]}: {result[2]}")
    sys.exit(1)

print("ALL CHECKS PASSED")