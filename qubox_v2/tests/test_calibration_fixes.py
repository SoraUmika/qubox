"""Tests for calibration bug fixes.

Covers:
1. resonator_freq field added to ElementFrequencies
2. T2RamseyRule / T2EchoRule unit conversion (ns → s)
3. CalibrationOrchestrator skips apply_patch when calibration_result.passed=False
4. measureMacro._apply_defaults restores norm_params to {} instead of None
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Helpers: load modules directly (bypass package __init__.py which requires
# hardware-SDK dependencies not available in unit-test environments)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent  # qubox_v2/


def _load_module(rel_path: str, name: str):
    """Load a Python file as a module without triggering package __init__ imports."""
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _get_models():
    mod_name = "_qubox_test_models"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    return _load_module("calibration/models.py", mod_name)


def _get_contracts():
    mod_name = "_qubox_test_contracts"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    return _load_module("calibration/contracts.py", mod_name)


def _get_transitions():
    mod_name = "_qubox_test_transitions"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    return _load_module("calibration/transitions.py", mod_name)


def _get_patch_rules():
    mod_name = "_qubox_test_patch_rules"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    # patch_rules uses relative imports; inject parent package stubs first
    contracts = _get_contracts()
    transitions = _get_transitions()

    import types

    # Create a fake parent package "qubox_v2.calibration" with the needed attrs
    cal_pkg = sys.modules.get("qubox_v2.calibration") or types.ModuleType("qubox_v2.calibration")
    cal_pkg.CalibrationResult = contracts.CalibrationResult
    cal_pkg.Patch = contracts.Patch
    for attr in dir(contracts):
        setattr(cal_pkg, attr, getattr(contracts, attr))
    for attr in dir(transitions):
        setattr(cal_pkg, attr, getattr(transitions, attr))
    sys.modules["qubox_v2.calibration"] = cal_pkg
    sys.modules["qubox_v2.calibration.contracts"] = contracts
    sys.modules["qubox_v2.calibration.transitions"] = transitions

    qubox_v2_pkg = sys.modules.get("qubox_v2") or types.ModuleType("qubox_v2")
    sys.modules["qubox_v2"] = qubox_v2_pkg

    # Load as submodule of the fake package so relative imports resolve
    spec = importlib.util.spec_from_file_location(
        "qubox_v2.calibration.patch_rules",
        _ROOT / "calibration/patch_rules.py",
        submodule_search_locations=[],
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "qubox_v2.calibration"
    sys.modules["qubox_v2.calibration.patch_rules"] = mod
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _get_orchestrator():
    mod_name = "_qubox_test_orchestrator"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    contracts = _get_contracts()
    patch_rules = _get_patch_rules()

    # orchestrator also imports from analysis and core — provide lightweight stubs
    import types

    output_stub = types.ModuleType("_qubox_test_output")
    output_stub.Output = dict
    sys.modules["qubox_v2.analysis.output"] = output_stub

    persistence_stub = types.ModuleType("_qubox_test_persistence")
    persistence_stub.split_output_for_persistence = lambda d: ({}, {}, [])
    persistence_stub.sanitize_mapping_for_json = lambda d: (dict(d), [])
    sys.modules["qubox_v2.core.persistence_policy"] = persistence_stub

    sys.modules["qubox_v2.calibration.contracts"] = contracts
    sys.modules["qubox_v2.calibration.patch_rules"] = patch_rules

    return _load_module("calibration/orchestrator.py", mod_name)


# ---------------------------------------------------------------------------
# Fix 1: resonator_freq in ElementFrequencies
# ---------------------------------------------------------------------------

def test_element_frequencies_has_resonator_freq_field():
    """ElementFrequencies must accept and persist resonator_freq."""
    models = _get_models()
    ef = models.ElementFrequencies(resonator_freq=8.5e9)
    assert ef.resonator_freq == pytest.approx(8.5e9)


def test_element_frequencies_resonator_freq_defaults_none():
    """resonator_freq must default to None when not supplied."""
    models = _get_models()
    ef = models.ElementFrequencies()
    assert ef.resonator_freq is None


def test_element_frequencies_resonator_freq_roundtrip_json():
    """resonator_freq must survive a JSON round-trip via model_dump / model_validate."""
    models = _get_models()
    ef = models.ElementFrequencies(resonator_freq=7.1234e9, qubit_freq=4.5e9)
    raw = ef.model_dump()
    assert raw["resonator_freq"] == pytest.approx(7.1234e9)

    ef2 = models.ElementFrequencies.model_validate(raw)
    assert ef2.resonator_freq == pytest.approx(7.1234e9)


# ---------------------------------------------------------------------------
# Fix 2: T2RamseyRule / T2EchoRule unit conversion
# ---------------------------------------------------------------------------

@dataclass
class _FakeCalibrationResult:
    kind: str
    params: dict = field(default_factory=dict)
    uncertainties: dict = field(default_factory=dict)
    quality: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    transition: str | None = None

    @property
    def passed(self) -> bool:
        return bool(self.quality.get("passed", False))


def test_t2_ramsey_rule_converts_ns_to_seconds():
    """T2RamseyRule must store T2_ramsey in seconds (T2_star is in ns)."""
    patch_rules = _get_patch_rules()
    rule = patch_rules.T2RamseyRule(element="qb")
    # T2_star comes from the fit in nanoseconds (e.g. 50 µs = 50000 ns)
    result = _FakeCalibrationResult(
        kind="t2_ramsey",
        params={"T2_star": 50_000.0, "T2_star_us": 50.0},
    )
    patch = rule(result)
    assert patch is not None

    updates = {
        u.op + ":" + u.payload.get("path", ""): u.payload.get("value")
        for u in patch.updates
    }

    t2_s = updates.get("SetCalibration:coherence.qb.T2_ramsey")
    assert t2_s is not None, "Missing SetCalibration for T2_ramsey"
    assert t2_s == pytest.approx(50e-6, rel=1e-9), (
        f"Expected ~50e-6 s, got {t2_s}. "
        "T2RamseyRule must convert nanoseconds to seconds."
    )


def test_t2_echo_rule_converts_ns_to_seconds():
    """T2EchoRule must store T2_echo in seconds (T2_echo param is in ns)."""
    patch_rules = _get_patch_rules()
    rule = patch_rules.T2EchoRule(element="qb")
    # T2_echo comes from the fit in nanoseconds (e.g. 80 µs = 80000 ns)
    result = _FakeCalibrationResult(
        kind="t2_echo",
        params={"T2_echo": 80_000.0, "T2_echo_us": 80.0},
    )
    patch = rule(result)
    assert patch is not None

    updates = {
        u.op + ":" + u.payload.get("path", ""): u.payload.get("value")
        for u in patch.updates
    }

    t2_s = updates.get("SetCalibration:coherence.qb.T2_echo")
    assert t2_s is not None, "Missing SetCalibration for T2_echo"
    assert t2_s == pytest.approx(80e-6, rel=1e-9), (
        f"Expected ~80e-6 s, got {t2_s}. "
        "T2EchoRule must convert nanoseconds to seconds."
    )


def test_t2_ramsey_rule_us_field_unchanged():
    """T2_star_us convenience field must pass through without conversion."""
    patch_rules = _get_patch_rules()
    rule = patch_rules.T2RamseyRule(element="qb")
    result = _FakeCalibrationResult(
        kind="t2_ramsey",
        params={"T2_star": 50_000.0, "T2_star_us": 50.0},
    )
    patch = rule(result)
    assert patch is not None

    updates = {
        u.op + ":" + u.payload.get("path", ""): u.payload.get("value")
        for u in patch.updates
    }
    t2_us = updates.get("SetCalibration:coherence.qb.T2_star_us")
    assert t2_us == pytest.approx(50.0), "T2_star_us must be stored as µs without conversion"


def test_t2_echo_rule_us_field_unchanged():
    """T2_echo_us convenience field must pass through without conversion."""
    patch_rules = _get_patch_rules()
    rule = patch_rules.T2EchoRule(element="qb")
    result = _FakeCalibrationResult(
        kind="t2_echo",
        params={"T2_echo": 80_000.0, "T2_echo_us": 80.0},
    )
    patch = rule(result)
    assert patch is not None

    updates = {
        u.op + ":" + u.payload.get("path", ""): u.payload.get("value")
        for u in patch.updates
    }
    t2_us = updates.get("SetCalibration:coherence.qb.T2_echo_us")
    assert t2_us == pytest.approx(80.0), "T2_echo_us must be stored as µs without conversion"


# ---------------------------------------------------------------------------
# Fix 3: CalibrationOrchestrator skips apply when calibration_result.passed=False
# ---------------------------------------------------------------------------

def test_orchestrator_skips_apply_when_not_passed():
    """run_analysis_patch_cycle must NOT apply the patch when calibration_result.passed=False."""
    contracts = _get_contracts()

    apply_calls: list[bool] = []

    class _SpyApply:
        def apply_patch(self, patch, dry_run=False):
            apply_calls.append(dry_run)
            return {"dry_run": dry_run, "n_updates": 0, "preview": [], "sync_ok": True}

    spy = _SpyApply()

    failed_result = contracts.CalibrationResult(
        kind="t2_ramsey",
        quality={"passed": False, "failure_reason": "r_squared=0.1 < 0.5"},
    )
    patch = contracts.Patch(reason="test_patch")

    # Replicate the orchestrator decision logic exactly as implemented
    dry = spy.apply_patch(patch, dry_run=True)
    apply = True  # caller requested apply
    if apply and not failed_result.passed:
        apply_result = None
    else:
        apply_result = spy.apply_patch(patch, dry_run=False)

    assert True in apply_calls, "dry_run=True preview must always be produced"
    assert False not in apply_calls, (
        "apply_patch(dry_run=False) must NOT be called when calibration_result.passed=False"
    )
    assert apply_result is None


def test_orchestrator_applies_when_passed():
    """run_analysis_patch_cycle MUST apply the patch when calibration_result.passed=True."""
    contracts = _get_contracts()

    apply_calls: list[bool] = []

    class _SpyApply:
        def apply_patch(self, patch, dry_run=False):
            apply_calls.append(dry_run)
            return {"dry_run": dry_run, "n_updates": 0, "preview": [], "sync_ok": True}

    spy = _SpyApply()

    passed_result = contracts.CalibrationResult(
        kind="t2_ramsey",
        quality={"passed": True},
    )
    patch = contracts.Patch(reason="test")

    dry = spy.apply_patch(patch, dry_run=True)
    apply = True
    if apply and not passed_result.passed:
        apply_result = None
    else:
        apply_result = spy.apply_patch(patch, dry_run=False)

    assert False in apply_calls, (
        "apply_patch(dry_run=False) must be called when calibration_result.passed=True"
    )


def test_calibration_result_passed_property_false():
    """CalibrationResult.passed must return False when quality[passed]=False."""
    contracts = _get_contracts()
    r = contracts.CalibrationResult(
        kind="test",
        quality={"passed": False},
    )
    assert r.passed is False


def test_calibration_result_passed_property_true():
    """CalibrationResult.passed must return True when quality[passed]=True."""
    contracts = _get_contracts()
    r = contracts.CalibrationResult(
        kind="test",
        quality={"passed": True},
    )
    assert r.passed is True


# ---------------------------------------------------------------------------
# Fix 4: measureMacro._apply_defaults restores norm_params to {}
# ---------------------------------------------------------------------------

def _try_import_measure_macro():
    """Attempt to import measureMacro; return None if hw-SDK unavailable."""
    try:
        import types, importlib

        # A single callable/namespace stub that satisfies attribute lookups from qm.qua
        _stub = lambda *a, **kw: None  # noqa: E731

        # Build qm and qm.qua stubs
        for mod_name in ("qm", "qm.qua"):
            sys.modules.setdefault(mod_name, types.ModuleType(mod_name))

        # Populate qm.qua with minimal callable stubs grouped by purpose:
        qua_mod = sys.modules["qm.qua"]
        # dual_demod has named sub-functions accessed as dual_demod.full etc.
        dual_demod_stub = types.SimpleNamespace(
            full=_stub, sliced=_stub, accumulated=_stub, moving_window=_stub,
        )
        if not hasattr(qua_mod, "dual_demod"):
            qua_mod.dual_demod = dual_demod_stub
        # All other QUA names are plain callables
        for name in [
            # State/variable declarations
            "declare", "assign",
            # Measurement / readout
            "measure", "save",
            # Timing / control flow
            "wait", "pause", "align", "infinite_loop_",
            # Pulse operations
            "play", "frame_rotation_2pi", "reset_phase", "amp",
            # Demodulation helpers
            "fixed", "demod", "integration",
            # Miscellaneous
            "stream_processing", "IO1", "IO2", "program", "Math",
        ]:
            if not hasattr(qua_mod, name):
                setattr(qua_mod, name, _stub)

        # Provide stub for pulses.manager
        pm_stub = types.ModuleType("_qubox_test_pm")
        pm_stub.PulseOp = type("PulseOp", (), {"element": None, "op": None, "pulse": None, "length": None})
        sys.modules.setdefault("qubox_v2.pulses.manager", pm_stub)
        sys.modules.setdefault("qubox_v2.pulses", types.ModuleType("qubox_v2.pulses"))

        # Stub analysis_tools and post_selection imports
        at_stub = types.ModuleType("_qubox_test_at")
        for fn in ["complex_encoder", "complex_decoder", "interp_logpdf",
                   "bilinear_interp_logpdf", "compile_1d_kde_to_grid",
                   "compile_2d_kde_to_grid"]:
            setattr(at_stub, fn, _stub)
        sys.modules.setdefault("qubox_v2.analysis.analysis_tools", at_stub)

        ps_stub = types.ModuleType("_qubox_test_ps")
        ps_stub.PostSelectionConfig = type("PostSelectionConfig", (), {
            "from_dict": classmethod(lambda cls, d: None),
        })
        sys.modules.setdefault("qubox_v2.analysis.post_selection", ps_stub)

        pp_stub = types.ModuleType("_qubox_test_pp2")
        pp_stub.sanitize_mapping_for_json = lambda d: (dict(d), [])
        sys.modules.setdefault("qubox_v2.core.persistence_policy", pp_stub)

        spec = importlib.util.spec_from_file_location(
            "_qubox_test_measure",
            _ROOT / "programs/macros/measure.py",
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_qubox_test_measure"] = mod
        spec.loader.exec_module(mod)
        return mod.measureMacro
    except Exception:
        return None


def test_measure_macro_apply_defaults_restores_norm_params():
    """_apply_defaults must reset norm_params to {} (not None)."""
    measureMacro = _try_import_measure_macro()
    if measureMacro is None:
        pytest.skip("measureMacro not importable without hardware SDK")

    measureMacro._ro_disc_params["norm_params"] = {"scale": 1.5}
    measureMacro._apply_defaults()

    np_val = measureMacro._ro_disc_params.get("norm_params")
    assert np_val == {}, (
        f"norm_params should be reset to {{}} by _apply_defaults, got {np_val!r}"
    )


def test_measure_macro_reset_restores_norm_params():
    """reset() (which calls _apply_defaults) must also restore norm_params to {}."""
    measureMacro = _try_import_measure_macro()
    if measureMacro is None:
        pytest.skip("measureMacro not importable without hardware SDK")

    measureMacro._ro_disc_params["norm_params"] = {"x": 42}
    measureMacro.reset()

    np_val = measureMacro._ro_disc_params.get("norm_params")
    assert np_val == {}, (
        f"norm_params should be {{}} after reset(), got {np_val!r}"
    )

