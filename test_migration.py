"""Post-migration import verification for the qubox legacy elimination."""
import sys
import traceback

results = []

def check(label, fn):
    try:
        fn()
        results.append(("OK", label))
        print(f"  OK  {label}")
    except Exception as e:
        results.append(("FAIL", label, str(e)))
        print(f"  FAIL {label}: {e}")
        traceback.print_exc()

print(f"Python: {sys.version}")
print()

# --- Core package ---
check("import qubox", lambda: __import__("qubox"))
check("core.errors", lambda: (
    __import__("qubox.core.errors", fromlist=["QuboxError", "ConfigError", "ContextMismatchError"])
))
check("core.types merged enums", lambda: (
    exec("""
from qubox.core.types import ExecMode, PulseType
assert hasattr(ExecMode, 'HARDWARE')
assert hasattr(ExecMode, 'RUN')
assert hasattr(PulseType, 'CONSTANT')
assert hasattr(PulseType, 'CONTROL')
""")
))

# --- Hardware ---
check("hardware imports", lambda: (
    __import__("qubox.hardware", fromlist=["ConfigEngine", "HardwareController", "ProgramRunner", "QueueManager"])
))

# --- Programs ---
check("programs.macros.measure", lambda: (
    __import__("qubox.programs.macros.measure", fromlist=["measureMacro"])
))

# --- Experiments ---
check("experiments (spectroscopy)", lambda: (
    __import__("qubox.experiments", fromlist=["QubitSpectroscopy", "ResonatorSpectroscopy"])
))
check("experiments (time_domain)", lambda: (
    __import__("qubox.experiments", fromlist=["PowerRabi", "T1Relaxation", "T2Ramsey", "T2Echo"])
))
check("experiments (cavity)", lambda: (
    __import__("qubox.experiments", fromlist=["StorageSpectroscopy", "NumSplittingSpectroscopy"])
))
check("experiments (tomography)", lambda: (
    __import__("qubox.experiments", fromlist=["QubitStateTomography", "StorageWignerTomography"])
))
check("experiments.result", lambda: (
    __import__("qubox.experiments.result", fromlist=["RunResult", "AnalysisResult", "ProgramBuildResult"])
))
check("experiments.session", lambda: (
    __import__("qubox.experiments.session", fromlist=["SessionManager"])
))

# --- Session ---
check("session.session (Session class)", lambda: (
    __import__("qubox.session.session", fromlist=["Session"])
))

# --- Calibration ---
check("calibration (store + mixer)", lambda: (
    __import__("qubox.calibration", fromlist=["CalibrationStore", "MixerCalibrationConfig"])
))

# --- Devices ---
check("devices (manager + resolver)", lambda: (
    __import__("qubox.devices", fromlist=["DeviceManager", "ContextResolver", "SampleRegistry"])
))

# --- Notebook import surface ---
check("notebook (full surface)", lambda: (
    exec("""
from qubox.notebook import (
    QubitSpectroscopy, PowerRabi, measureMacro, RunResult,
    CalibrationStore, SampleRegistry, HardwareDefinition,
    readout_mod, gates_mod
)
""")
))

# --- Gates ---
check("gates.contexts", lambda: (
    __import__("qubox.gates.contexts", fromlist=["ModelContext", "NoiseConfig"])
))
check("gates.cache", lambda: (
    __import__("qubox.gates.cache", fromlist=["ModelCache"])
))

# --- Compile ---
check("compile.api", lambda: (
    __import__("qubox.compile.api", fromlist=["compile_api"])
))

# --- Verification ---
check("verification.waveform_regression", lambda: (
    __import__("qubox.verification.waveform_regression", fromlist=["run_all_checks"])
))

# --- Analysis ---
check("analysis (cQED_attributes)", lambda: (
    __import__("qubox.analysis.cQED_attributes", fromlist=["cQED_attributes"])
))

# --- Summary ---
print()
ok_count = sum(1 for r in results if r[0] == "OK")
fail_count = sum(1 for r in results if r[0] == "FAIL")
print(f"Results: {ok_count} OK, {fail_count} FAIL out of {len(results)} checks")
if fail_count:
    print("\nFailed checks:")
    for r in results:
        if r[0] == "FAIL":
            print(f"  - {r[1]}: {r[2]}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
