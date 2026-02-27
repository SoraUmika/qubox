"""Tests for three calibration bug fixes:
1. resonator_freq field in ElementFrequencies model
2. T2Ramsey/T2Echo unit conversion (ns → s) in patch rules
3. CalibrationOrchestrator skips apply when calibration_result.passed is False
"""
from __future__ import annotations

import importlib.util
import sys
import os
import types
from pathlib import Path

_ROOT = str(Path(__file__).parent.parent.parent.parent)


def _load_module(rel_path: str, name: str):
    """Load a single .py file as a module without triggering package __init__."""
    path = os.path.normpath(os.path.join(_ROOT, rel_path))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _ensure_calibration_modules():
    """Load only the calibration sub-modules needed for the tests."""
    # Minimal stubs so that inter-module imports don't blow up
    # without requiring the full qubox_v2 package to be installed.

    # contracts (no external deps)
    if "qubox_v2.calibration.contracts" not in sys.modules:
        _load_module("qubox_v2/calibration/contracts.py", "qubox_v2.calibration.contracts")

    # transitions (no heavy deps)
    if "qubox_v2.calibration.transitions" not in sys.modules:
        _load_module("qubox_v2/calibration/transitions.py", "qubox_v2.calibration.transitions")

    # models (pydantic + numpy)
    if "qubox_v2.calibration.models" not in sys.modules:
        _load_module("qubox_v2/calibration/models.py", "qubox_v2.calibration.models")

    # patch_rules depends on contracts + transitions
    if "qubox_v2.calibration.patch_rules" not in sys.modules:
        _load_module("qubox_v2/calibration/patch_rules.py", "qubox_v2.calibration.patch_rules")


_ensure_calibration_modules()


# ---------------------------------------------------------------------------
# Fix 1: resonator_freq in ElementFrequencies
# ---------------------------------------------------------------------------
def test_element_frequencies_has_resonator_freq_field():
    from qubox_v2.calibration.models import ElementFrequencies
    ef = ElementFrequencies(resonator_freq=7.1e9)
    assert ef.resonator_freq == 7.1e9


def test_element_frequencies_resonator_freq_default_none():
    from qubox_v2.calibration.models import ElementFrequencies
    ef = ElementFrequencies()
    assert ef.resonator_freq is None


def test_element_frequencies_round_trips_resonator_freq():
    from qubox_v2.calibration.models import ElementFrequencies
    ef = ElementFrequencies(resonator_freq=8.5e9, qubit_freq=5.0e9)
    data = ef.model_dump()
    ef2 = ElementFrequencies(**{k: v for k, v in data.items() if v is not None})
    assert ef2.resonator_freq == 8.5e9


# ---------------------------------------------------------------------------
# Fix 2: T2RamseyRule and T2EchoRule convert ns → seconds
# ---------------------------------------------------------------------------
def test_t2_ramsey_rule_converts_ns_to_seconds():
    from qubox_v2.calibration.patch_rules import T2RamseyRule
    from qubox_v2.calibration.contracts import CalibrationResult

    rule = T2RamseyRule(element="qb")
    result = CalibrationResult(
        kind="t2_ramsey",
        params={"T2_star": 50000.0, "T2_star_us": 50.0},  # 50 µs = 50000 ns
    )
    patch = rule(result)
    assert patch is not None
    ops = {op.payload["path"]: op.payload["value"] for op in patch.updates}
    # T2_ramsey field must be in seconds
    t2_s = ops["coherence.qb.T2_ramsey"]
    assert abs(t2_s - 50e-6) < 1e-12, f"Expected 50e-6 s, got {t2_s}"
    # T2_star_us is stored as-is (microseconds convenience field)
    assert ops["coherence.qb.T2_star_us"] == 50.0


def test_t2_echo_rule_converts_ns_to_seconds():
    from qubox_v2.calibration.patch_rules import T2EchoRule
    from qubox_v2.calibration.contracts import CalibrationResult

    rule = T2EchoRule(element="qb")
    result = CalibrationResult(
        kind="t2_echo",
        params={"T2_echo": 120000.0, "T2_echo_us": 120.0},  # 120 µs = 120000 ns
    )
    patch = rule(result)
    assert patch is not None
    ops = {op.payload["path"]: op.payload["value"] for op in patch.updates}
    t2_s = ops["coherence.qb.T2_echo"]
    assert abs(t2_s - 120e-6) < 1e-12, f"Expected 120e-6 s, got {t2_s}"
    assert ops["coherence.qb.T2_echo_us"] == 120.0


# ---------------------------------------------------------------------------
# Fix 3: CalibrationOrchestrator skips apply when calibration_result.passed is False
# ---------------------------------------------------------------------------
def _load_orchestrator():
    """Load orchestrator with minimal stubs for heavy dependencies."""
    # Provide a stub for analysis.output
    if "qubox_v2.analysis" not in sys.modules:
        analysis_stub = types.ModuleType("qubox_v2.analysis")
        sys.modules["qubox_v2.analysis"] = analysis_stub
    if "qubox_v2.analysis.output" not in sys.modules:
        output_stub = types.ModuleType("qubox_v2.analysis.output")
        output_stub.Output = dict
        sys.modules["qubox_v2.analysis.output"] = output_stub

    # Provide stub for hardware.program_runner
    if "qubox_v2.hardware" not in sys.modules:
        hw_stub = types.ModuleType("qubox_v2.hardware")
        sys.modules["qubox_v2.hardware"] = hw_stub
    if "qubox_v2.hardware.program_runner" not in sys.modules:
        pr_stub = types.ModuleType("qubox_v2.hardware.program_runner")

        class _RunResult:
            def __init__(self, mode, output, sim_samples, metadata):
                self.mode = mode
                self.output = output
                self.sim_samples = sim_samples
                self.metadata = metadata
        pr_stub.RunResult = _RunResult
        sys.modules["qubox_v2.hardware.program_runner"] = pr_stub

    # Provide stub for core.persistence_policy
    if "qubox_v2.core" not in sys.modules:
        core_stub = types.ModuleType("qubox_v2.core")
        sys.modules["qubox_v2.core"] = core_stub
    if "qubox_v2.core.persistence_policy" not in sys.modules:
        pp_stub = types.ModuleType("qubox_v2.core.persistence_policy")
        pp_stub.split_output_for_persistence = lambda data: ({}, {}, [])
        pp_stub.sanitize_mapping_for_json = lambda m: (m, [])
        sys.modules["qubox_v2.core.persistence_policy"] = pp_stub

    if "qubox_v2.calibration.orchestrator" not in sys.modules:
        _load_module(
            "qubox_v2/calibration/orchestrator.py",
            "qubox_v2.calibration.orchestrator",
        )
    return sys.modules["qubox_v2.calibration.orchestrator"]


def test_orchestrator_skips_apply_when_calibration_fails():
    """When calibration_result.passed is False, apply_patch must not be called
    with dry_run=False even if apply=True is requested."""
    from unittest.mock import MagicMock, patch as mock_patch
    from qubox_v2.calibration.contracts import CalibrationResult, Patch
    orch_mod = _load_orchestrator()
    CalibrationOrchestrator = orch_mod.CalibrationOrchestrator

    session = MagicMock()
    session.attributes.ro_el = "rr"
    session.attributes.qb_el = "qb"
    session.attributes.st_el = "st"
    orch = CalibrationOrchestrator(session, patch_rules={})

    failing_result = CalibrationResult(
        kind="t1",
        params={"T1_s": 1e-5},
        quality={"passed": False, "failure_reason": "r_squared=0.1 < 0.5"},
    )
    assert not failing_result.passed

    empty_patch = Patch(reason="test")

    exp = MagicMock()
    with (
        mock_patch.object(orch, "run_experiment", return_value=MagicMock()),
        mock_patch.object(orch, "persist_artifact", return_value="/tmp/fake"),
        mock_patch.object(orch, "analyze", return_value=failing_result),
        mock_patch.object(orch, "build_patch", return_value=empty_patch),
        mock_patch.object(orch, "apply_patch", return_value={"dry_run": True, "n_updates": 0, "preview": [], "sync_ok": True}) as mock_apply,
    ):
        outcome = orch.run_analysis_patch_cycle(exp, apply=True, persist_artifact=True)

    # apply_patch should have been called exactly once (dry_run=True only)
    assert mock_apply.call_count == 1, f"apply_patch called {mock_apply.call_count} times, expected 1 (dry-run only)"
    _, kwargs = mock_apply.call_args
    assert kwargs.get("dry_run", True) is True, "The only apply_patch call must be dry_run=True"
    assert outcome["apply_result"] is None


def test_orchestrator_applies_when_calibration_passes():
    """When calibration_result.passed is True, apply_patch is called with dry_run=False."""
    from unittest.mock import MagicMock, patch as mock_patch
    from qubox_v2.calibration.contracts import CalibrationResult, Patch
    orch_mod = _load_orchestrator()
    CalibrationOrchestrator = orch_mod.CalibrationOrchestrator

    session = MagicMock()
    session.attributes.ro_el = "rr"
    session.attributes.qb_el = "qb"
    session.attributes.st_el = "st"
    orch = CalibrationOrchestrator(session, patch_rules={})

    passing_result = CalibrationResult(
        kind="t1",
        params={"T1_s": 1e-5},
        quality={"passed": True},
    )
    assert passing_result.passed

    empty_patch = Patch(reason="test")
    apply_result_val = {"dry_run": False, "n_updates": 0, "preview": [], "sync_ok": True}

    exp = MagicMock()
    with (
        mock_patch.object(orch, "run_experiment", return_value=MagicMock()),
        mock_patch.object(orch, "persist_artifact", return_value="/tmp/fake"),
        mock_patch.object(orch, "analyze", return_value=passing_result),
        mock_patch.object(orch, "build_patch", return_value=empty_patch),
        mock_patch.object(orch, "apply_patch", side_effect=[
            {"dry_run": True, "n_updates": 0, "preview": [], "sync_ok": True},
            apply_result_val,
        ]) as mock_apply,
    ):
        outcome = orch.run_analysis_patch_cycle(exp, apply=True, persist_artifact=True)

    assert mock_apply.call_count == 2
    assert outcome["apply_result"] is apply_result_val


if __name__ == "__main__":
    import traceback
    tests = [
        test_element_frequencies_has_resonator_freq_field,
        test_element_frequencies_resonator_freq_default_none,
        test_element_frequencies_round_trips_resonator_freq,
        test_t2_ramsey_rule_converts_ns_to_seconds,
        test_t2_echo_rule_converts_ns_to_seconds,
        test_orchestrator_skips_apply_when_calibration_fails,
        test_orchestrator_applies_when_calibration_passes,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(failed)

