"""Tests for the workflow safety refactoring (P0.1–P2.1).

Covers:
- P0.1: FitResult.success contract, orchestrator guard
- P0.2: Transactional apply_patch with rollback
- P0.3: T1Rule heuristic removal, T2 explicit-unit deprecation
- P1.1: cQED_attributes.verify_consistency / from_calibration_store
- P1.2: MeasurementConfig frozen dataclass
- P2.1: MultiProgramExperiment base class
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers – load modules directly from .py files, bypassing the package
# __init__.py which pulls in heavy hardware-SDK dependencies.
#
# The approach mirrors test_calibration_fixes.py:  plain-name modules for
# files without relative imports, and proper dotted-name loading with
# __package__ for files that use ``from ..`` / ``from .`` imports.
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent  # qubox_v2/


def _load_module(rel_path: str, name: str):
    """Load a Python file as a module – no relative-import support needed."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_as_submodule(rel_path: str, dotted_name: str):
    """Load a .py file as a submodule of the qubox_v2 fake package tree.

    This sets ``__package__`` so that relative imports resolve via the
    stubs previously injected into ``sys.modules``.
    """
    if dotted_name in sys.modules:
        return sys.modules[dotted_name]
    spec = importlib.util.spec_from_file_location(
        dotted_name,
        _ROOT / rel_path,
        submodule_search_locations=[],
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = dotted_name.rsplit(".", 1)[0]
    sys.modules[dotted_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Fake package tree + lightweight stubs ──
def _ensure_stubs():
    """Inject minimal stub packages so that relative imports resolve."""
    # Top-level package stubs
    for pkg in (
        "qubox_v2",
        "qubox_v2.core",
        "qubox_v2.analysis",
        "qubox_v2.calibration",
        "qubox_v2.experiments",
        "qubox_v2.hardware",
        "qubox_v2.programs",
        "qubox_v2.programs.macros",
        "qubox_v2.programs.macros.measure",
        "qubox_v2.pulses",
        "qubox_v2.devices",
    ):
        if pkg not in sys.modules:
            m = types.ModuleType(pkg)
            m.__path__ = [str(_ROOT / pkg.replace("qubox_v2.", "").replace(".", "/"))]
            sys.modules[pkg] = m

    # core.logging
    if "qubox_v2.core.logging" not in sys.modules:
        import logging as _sl
        s = types.ModuleType("qubox_v2.core.logging")
        s.get_logger = _sl.getLogger
        s.configure_global_logging = lambda *a, **kw: None
        sys.modules["qubox_v2.core.logging"] = s

    # core.persistence_policy
    if "qubox_v2.core.persistence_policy" not in sys.modules:
        s = types.ModuleType("qubox_v2.core.persistence_policy")
        s.sanitize_mapping_for_json = lambda d: (dict(d), [])
        s.split_output_for_persistence = lambda d: ({}, {}, [])
        sys.modules["qubox_v2.core.persistence_policy"] = s

    # core.errors
    if "qubox_v2.core.errors" not in sys.modules:
        s = types.ModuleType("qubox_v2.core.errors")

        class ContextMismatchError(Exception):
            pass

        s.ContextMismatchError = ContextMismatchError
        sys.modules["qubox_v2.core.errors"] = s

    # hardware.program_runner  (RunResult used in experiments/result.py)
    if "qubox_v2.hardware.program_runner" not in sys.modules:
        s = types.ModuleType("qubox_v2.hardware.program_runner")

        @dataclass
        class RunResult:
            mode: str = "hardware"
            output: Any = None
            sim_samples: Any = None
            metadata: dict = field(default_factory=dict)

        s.RunResult = RunResult
        s.ExecMode = types.SimpleNamespace(HARDWARE="hardware", SIMULATION="simulation")
        s.ProgramRunner = None
        sys.modules["qubox_v2.hardware.program_runner"] = s

    # analysis.output (used by orchestrator)
    if "qubox_v2.analysis.output" not in sys.modules:
        s = types.ModuleType("qubox_v2.analysis.output")
        s.Output = dict
        sys.modules["qubox_v2.analysis.output"] = s

    # analysis.analysis_tools (used by cQED_attributes)
    if "qubox_v2.analysis.analysis_tools" not in sys.modules:
        s = types.ModuleType("qubox_v2.analysis.analysis_tools")
        s.complex_encoder = lambda d: d
        s.complex_decoder = lambda d: d
        sys.modules["qubox_v2.analysis.analysis_tools"] = s


_ensure_stubs()


# ── Module getters (in dependency order) ──
def _get_models():
    return _load_module("calibration/models.py", "_wsr_models")


def _get_contracts():
    return _load_module("calibration/contracts.py", "_wsr_contracts")


def _get_transitions():
    return _load_module("calibration/transitions.py", "_wsr_transitions")


def _get_store():
    # store.py uses relative imports → needs real submodule names
    models = _get_models()
    transitions = _get_transitions()
    # Inject into the qubox_v2 namespace so relative imports work
    sys.modules["qubox_v2.calibration.models"] = models
    sys.modules["qubox_v2.calibration.transitions"] = transitions
    return _load_as_submodule("calibration/store.py", "qubox_v2.calibration.store")


def _get_result():
    # result.py uses: from ..hardware.program_runner import RunResult
    return _load_as_submodule("experiments/result.py", "qubox_v2.experiments.result")


def _get_fitting():
    # fitting.py has no top-level relative imports, but calls
    # from ..experiments.result import FitResult lazily inside fit_and_wrap.
    _get_result()  # ensure result module is loadable
    return _load_as_submodule("analysis/fitting.py", "qubox_v2.analysis.fitting")


def _get_cqed_models():
    return _load_module("analysis/cQED_models.py", "_wsr_cqed_models")


def _get_calibration_algorithms():
    cqed_models = _get_cqed_models()
    fitting = _get_fitting()
    models = _get_models()
    # Inject into qubox_v2 namespace for relative imports
    sys.modules["qubox_v2.analysis.cQED_models"] = cqed_models
    sys.modules["qubox_v2.analysis.fitting"] = fitting
    sys.modules["qubox_v2.calibration.models"] = models
    return _load_as_submodule(
        "analysis/calibration_algorithms.py",
        "qubox_v2.analysis.calibration_algorithms",
    )


def _get_patch_rules():
    contracts = _get_contracts()
    transitions = _get_transitions()
    sys.modules["qubox_v2.calibration.contracts"] = contracts
    sys.modules["qubox_v2.calibration.transitions"] = transitions
    return _load_as_submodule(
        "calibration/patch_rules.py",
        "qubox_v2.calibration.patch_rules",
    )


def _get_orchestrator():
    _get_contracts()
    _get_patch_rules()
    # Orchestrator also needs store loaded for transactional tests
    _get_store()
    return _load_as_submodule(
        "calibration/orchestrator.py",
        "qubox_v2.calibration.orchestrator",
    )


def _get_cqed_attributes():
    return _load_as_submodule(
        "analysis/cQED_attributes.py",
        "qubox_v2.analysis.cQED_attributes",
    )


def _get_measurement_config():
    return _load_module("core/measurement_config.py", "_wsr_meas_config")


# ============================================================================
# P0.1 — FitResult.success contract
# ============================================================================
class TestFitResultContract:
    """P0.1: FitResult must carry ``success`` / ``reason`` fields."""

    def test_fit_result_has_success_field(self):
        mod = _get_result()
        fr = mod.FitResult(model_name="test", params={"a": 1.0})
        assert hasattr(fr, "success")
        assert fr.success is True

    def test_fit_result_failure_path(self):
        mod = _get_result()
        fr = mod.FitResult(
            model_name="test",
            params={},
            success=False,
            reason="curve_fit did not converge",
        )
        assert fr.success is False
        assert "converge" in fr.reason

    def test_fit_result_has_reason_field(self):
        mod = _get_result()
        fr = mod.FitResult(model_name="test", params={"a": 1.0})
        assert fr.reason is None

    def test_backward_compat_no_success_kwarg(self):
        """Old code that doesn't pass success= should still work (default True)."""
        mod = _get_result()
        fr = mod.FitResult(model_name="test", params={"a": 1.0})
        assert fr.success is True
        assert fr.reason is None


# ============================================================================
# P0.1 — fit_and_wrap success / failure
# ============================================================================
class TestFitAndWrapContract:
    """P0.1: fit_and_wrap must set success=False on failure."""

    def test_fit_and_wrap_success(self):
        mod = _get_fitting()
        xdata = np.array([1.0, 2.0, 3.0, 4.0])
        ydata = 2.0 * xdata + 1.0

        def linear(x, a, b):
            return a * x + b

        result = mod.fit_and_wrap(xdata, ydata, linear, [1.0, 0.0])
        assert result.success is True
        assert result.reason is None
        assert "a" in result.params

    def test_fit_and_wrap_failure(self):
        mod = _get_fitting()
        xdata = np.array([0.0, 0.0, 0.0])
        ydata = np.array([0.0, 0.0, 0.0])

        def bad_model(x, a, b, c, d, e):
            return a * np.exp(b * x * c) + d * np.sin(e * x)

        result = mod.fit_and_wrap(xdata, ydata, bad_model, [0, 0, 0, 0, 0])
        assert result.success is False
        assert result.reason is not None
        assert result.params == {}


# ============================================================================
# P0.1 — calibration_algorithms warnings
# ============================================================================
class TestCalibrationAlgorithmsWarnings:
    """P0.1: fit_number_splitting should flag failure."""

    def test_fit_number_splitting_success_flag_on_good_data(self):
        mod = _get_calibration_algorithms()
        freqs = np.array([4.5e9, 4.501e9, 4.502e9, 4.503e9])
        result = mod.fit_number_splitting(freqs)
        assert result.get("_fit_success") is True

    def test_fit_number_splitting_warns_on_failure(self):
        mod = _get_calibration_algorithms()
        with pytest.warns(RuntimeWarning, match="fit_number_splitting"):
            result = mod.fit_number_splitting(
                peak_frequencies=np.array([0.0, 0.0, 0.0]),
                fock_numbers=np.array([0, 1, 2]),
            )
        assert result["_fit_success"] is False


# ============================================================================
# P0.2 — Transactional apply_patch
# ============================================================================
class TestTransactionalPatch:
    """P0.2: apply_patch must default to dry_run=True and be transactional."""

    def _make_store(self, tmp_path):
        cal_path = tmp_path / "calibration.json"
        cal_path.write_text(json.dumps({
            "version": "5.1.0",
            "created": "2024-01-01T00:00:00",
            "cqed_params": {
                "transmon": {"qubit_freq": 4.5e9, "T1": 50e-6},
            },
        }))
        store_mod = _get_store()
        return store_mod.CalibrationStore(str(cal_path))

    def _make_orchestrator(self, store, tmp_path):
        class _MockSession:
            calibration = store
            experiment_path = tmp_path

            def context_snapshot(self):
                return types.SimpleNamespace(ro_el="rr")

            def save_pulses(self):
                pass

            def burn_pulses(self, **kw):
                pass

            pulse_mgr = types.SimpleNamespace(
                get_pulseOp_by_element_op=lambda *a, **kw: None,
            )

        orch_mod = _get_orchestrator()
        return orch_mod.CalibrationOrchestrator(_MockSession(), patch_rules={})

    def test_dry_run_is_default(self, tmp_path):
        """apply_patch must default to dry_run=True."""
        store = self._make_store(tmp_path)
        orch = self._make_orchestrator(store, tmp_path)
        contracts = _get_contracts()

        patch = contracts.Patch(reason="test")
        patch.add("SetCalibration", path="cqed_params.transmon.qubit_freq", value=5.0e9)

        result = orch.apply_patch(patch)  # no dry_run= kwarg
        assert result["dry_run"] is True
        cqed = store.get_cqed_params("transmon")
        assert cqed.qubit_freq == pytest.approx(4.5e9)

    def test_explicit_apply(self, tmp_path):
        """apply_patch(dry_run=False) must mutate the store."""
        store = self._make_store(tmp_path)
        orch = self._make_orchestrator(store, tmp_path)
        contracts = _get_contracts()

        patch = contracts.Patch(reason="test")
        patch.add("SetCalibration", path="cqed_params.transmon.qubit_freq", value=5.0e9)

        result = orch.apply_patch(patch, dry_run=False)
        assert result["dry_run"] is False
        cqed = store.get_cqed_params("transmon")
        assert cqed.qubit_freq == pytest.approx(5.0e9)

    def test_rollback_on_failure(self, tmp_path):
        """Mid-op failure must roll back to pre-patch state."""
        store = self._make_store(tmp_path)
        orch = self._make_orchestrator(store, tmp_path)
        contracts = _get_contracts()

        original_freq = store.get_cqed_params("transmon").qubit_freq

        # Monkey-patch _set_calibration_path to fail on the 2nd call
        call_count = [0]
        real_set = orch._set_calibration_path

        def _failing_set(path, value):
            call_count[0] += 1
            if call_count[0] > 1:
                raise RuntimeError("Simulated mid-op failure")
            return real_set(path, value)

        orch._set_calibration_path = _failing_set

        patch = contracts.Patch(reason="will_fail")
        patch.add("SetCalibration", path="cqed_params.transmon.qubit_freq", value=5.5e9)
        patch.add("SetCalibration", path="cqed_params.transmon.T1", value=999.0)

        with pytest.raises(RuntimeError, match="rolled back"):
            orch.apply_patch(patch, dry_run=False)

        cqed = store.get_cqed_params("transmon")
        assert cqed.qubit_freq == pytest.approx(original_freq)

    def test_snapshot_restore_roundtrip(self, tmp_path):
        """CalibrationStore snapshot/restore must preserve state."""
        store = self._make_store(tmp_path)
        snap = store.create_in_memory_snapshot()
        assert isinstance(snap, dict)
        assert snap["cqed_params"]["transmon"]["qubit_freq"] == pytest.approx(4.5e9)

        store.set_cqed_params("transmon", qubit_freq=6.0e9)
        assert store.get_cqed_params("transmon").qubit_freq == pytest.approx(6.0e9)

        store.restore_in_memory_snapshot(snap)
        assert store.get_cqed_params("transmon").qubit_freq == pytest.approx(4.5e9)


# ============================================================================
# P0.3 — T1Rule heuristic removal
# ============================================================================
@dataclass
class _FakeCR:
    """Minimal CalibrationResult duck-type for patch-rule tests."""
    kind: str
    params: dict = field(default_factory=dict)
    uncertainties: dict = field(default_factory=dict)
    quality: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    transition: str | None = None

    @property
    def passed(self) -> bool:
        return bool(self.quality.get("passed", False))


class TestT1RuleHeuristicRemoval:
    """P0.3: T1Rule must no longer silently convert units."""

    def test_t1_s_key_preferred(self):
        rule = _get_patch_rules().T1Rule(alias="transmon")
        patch = rule(_FakeCR(kind="t1", params={"T1_s": 50e-6}))
        vals = {u.payload.get("path"): u.payload.get("value") for u in patch.updates}
        assert vals["cqed_params.transmon.T1"] == pytest.approx(50e-6)

    def test_t1_ns_key_converted(self):
        rule = _get_patch_rules().T1Rule(alias="transmon")
        patch = rule(_FakeCR(kind="t1", params={"T1_ns": 50_000.0}))
        vals = {u.payload.get("path"): u.payload.get("value") for u in patch.updates}
        assert vals["cqed_params.transmon.T1"] == pytest.approx(50e-6)

    def test_bare_t1_large_value_ignored(self):
        """Bare 'T1' key no longer accepted — must use T1_s or T1_ns."""
        rule = _get_patch_rules().T1Rule(alias="transmon")
        patch = rule(_FakeCR(kind="t1", params={"T1": 50_000.0}))
        # No recognized key → no patch produced
        assert patch is None

    def test_bare_t1_small_value_ignored(self):
        """Bare 'T1' key no longer accepted — must use T1_s or T1_ns."""
        rule = _get_patch_rules().T1Rule(alias="transmon")
        patch = rule(_FakeCR(kind="t1", params={"T1": 50e-6}))
        assert patch is None


# ============================================================================
# P0.3 — T2 explicit-unit deprecation
# ============================================================================
class TestT2ExplicitUnits:
    """P0.3: T2 rules should prefer explicit-unit keys and deprecate bare keys."""

    def test_t2_ramsey_explicit_seconds(self):
        rule = _get_patch_rules().T2RamseyRule(alias="transmon")
        patch = rule(_FakeCR(kind="t2_ramsey", params={"T2_star_s": 50e-6}))
        vals = {u.payload.get("path"): u.payload.get("value") for u in patch.updates}
        assert vals["cqed_params.transmon.T2_ramsey"] == pytest.approx(50e-6)

    def test_t2_ramsey_bare_key_ignored(self):
        """Bare 'T2_star' key no longer accepted — must use T2_star_s or T2_star_ns."""
        rule = _get_patch_rules().T2RamseyRule(alias="transmon")
        patch = rule(_FakeCR(kind="t2_ramsey", params={"T2_star": 50_000.0}))
        assert patch is None

    def test_t2_echo_explicit_seconds(self):
        rule = _get_patch_rules().T2EchoRule(alias="transmon")
        patch = rule(_FakeCR(kind="t2_echo", params={"T2_echo_s": 80e-6}))
        vals = {u.payload.get("path"): u.payload.get("value") for u in patch.updates}
        assert vals["cqed_params.transmon.T2_echo"] == pytest.approx(80e-6)

    def test_t2_echo_bare_key_ignored(self):
        """Bare 'T2_echo' key no longer accepted — must use T2_echo_s or T2_echo_ns."""
        rule = _get_patch_rules().T2EchoRule(alias="transmon")
        patch = rule(_FakeCR(kind="t2_echo", params={"T2_echo": 80_000.0}))
        assert patch is None

    def test_t2_ramsey_ns_key(self):
        rule = _get_patch_rules().T2RamseyRule(alias="transmon")
        patch = rule(_FakeCR(kind="t2_ramsey", params={"T2_star_ns": 50_000.0}))
        vals = {u.payload.get("path"): u.payload.get("value") for u in patch.updates}
        assert vals["cqed_params.transmon.T2_ramsey"] == pytest.approx(50e-6)


# ============================================================================
# P1.1 — cQED_attributes.verify_consistency
# ============================================================================
class TestVerifyConsistency:
    """P1.1: cQED_attributes ↔ CalibrationStore consistency check."""

    def _make_store(self, tmp_path, cqed_params=None):
        cal_path = tmp_path / "cal.json"
        cal_path.write_text(json.dumps({
            "version": "5.1.0",
            "created": "2024-01-01T00:00:00",
            "cqed_params": cqed_params or {},
        }))
        return _get_store().CalibrationStore(str(cal_path))

    def test_consistent_returns_empty(self, tmp_path):
        store = self._make_store(tmp_path, {
            "transmon": {"qubit_freq": 4.5e9, "T1": 50e-6},
            "resonator": {"resonator_freq": 8.5e9},
        })
        mod = _get_cqed_attributes()
        attr = mod.cQED_attributes(
            qb_fq=4.5e9,
            ro_fq=8.5e9,
            qb_T1_relax=50e-6,
        )
        mismatches = attr.verify_consistency(store)
        assert mismatches == []

    def test_divergent_flags_mismatch(self, tmp_path):
        store = self._make_store(tmp_path, {
            "transmon": {"qubit_freq": 4.5e9},
        })
        mod = _get_cqed_attributes()
        attr = mod.cQED_attributes(qb_fq=5.0e9)
        mismatches = attr.verify_consistency(store)
        assert len(mismatches) == 1
        assert "qb_fq" in mismatches[0]

    def test_raise_on_mismatch_flag(self, tmp_path):
        store = self._make_store(tmp_path, {
            "transmon": {"qubit_freq": 4.5e9},
        })
        mod = _get_cqed_attributes()
        attr = mod.cQED_attributes(qb_fq=5.0e9)
        with pytest.raises(ValueError, match="mismatch"):
            attr.verify_consistency(store, raise_on_mismatch=True)

    def test_from_calibration_store(self, tmp_path):
        store = self._make_store(tmp_path, {
            "transmon": {"qubit_freq": 4.5e9, "T1": 50e-6, "anharmonicity": -200e6},
            "resonator": {"resonator_freq": 8.5e9, "kappa": 1e6},
            "storage": {"storage_freq": 6.0e9, "chi": -1e6, "chi2": 50.0},
        })
        mod = _get_cqed_attributes()
        attr = mod.cQED_attributes.from_calibration_store(
            store, ro_el="rr", qb_el="qb", st_el="st",
        )
        assert attr.qb_fq == pytest.approx(4.5e9)
        assert attr.ro_fq == pytest.approx(8.5e9)
        assert attr.st_fq == pytest.approx(6.0e9)
        assert attr.qb_T1_relax == pytest.approx(50e-6)
        assert attr.anharmonicity == pytest.approx(-200e6)
        assert attr.ro_kappa == pytest.approx(1e6)
        assert attr.st_chi == pytest.approx(-1e6)


# ============================================================================
# P1.2 — MeasurementConfig
# ============================================================================
class TestMeasurementConfig:
    """P1.2: Frozen MeasurementConfig dataclass."""

    def test_frozen(self):
        mod = _get_measurement_config()
        cfg = mod.MeasurementConfig(threshold=0.5, angle=1.2)
        with pytest.raises(AttributeError):
            cfg.threshold = 0.9  # type: ignore[misc]

    def test_from_calibration_store(self, tmp_path):
        cal_path = tmp_path / "cal.json"
        cal_path.write_text(json.dumps({
            "version": "5.1.0",
            "created": "2024-01-01T00:00:00",
            "discrimination": {
                "rr": {
                    "threshold": 0.45,
                    "angle": 1.1,
                    "fidelity": 0.97,
                    "mu_g": [0.0, 0.0],
                    "mu_e": [1.0, 0.0],
                    "sigma_g": 0.1,
                    "sigma_e": 0.1,
                }
            },
            "readout_quality": {
                "rr": {"F": 0.98, "Q": 0.95}
            },
        }))
        store = _get_store().CalibrationStore(str(cal_path))
        mod = _get_measurement_config()
        cfg = mod.MeasurementConfig.from_calibration_store(store, element="rr")
        assert cfg.threshold == pytest.approx(0.45)
        assert cfg.angle == pytest.approx(1.1)
        assert cfg.fidelity == pytest.approx(0.97)
        assert cfg.F == pytest.approx(0.98)
        assert cfg.Q == pytest.approx(0.95)
        assert cfg.source == "calibration_store"

    def test_from_measure_macro_snapshot(self):
        mod = _get_measurement_config()
        snapshot = {
            "ro_disc_params": {
                "threshold": 0.3,
                "angle": 0.8,
                "norm_params": {"scale": 1.5},
            },
            "ro_quality_params": {"F": 0.92},
        }
        cfg = mod.MeasurementConfig.from_measure_macro_snapshot(snapshot)
        assert cfg.threshold == pytest.approx(0.3)
        assert cfg.norm_params == {"scale": 1.5}
        assert cfg.F == pytest.approx(0.92)
        assert cfg.source == "measure_macro"

    def test_to_dict(self):
        mod = _get_measurement_config()
        cfg = mod.MeasurementConfig(
            threshold=0.5,
            angle=1.0,
            rot_mu_g=complex(0.1, 0.2),
            element="rr",
        )
        d = cfg.to_dict()
        assert d["threshold"] == pytest.approx(0.5)
        assert d["rot_mu_g"] == [pytest.approx(0.1), pytest.approx(0.2)]


# ============================================================================
# P2.1 — MultiProgramExperiment base class
# ============================================================================
class TestMultiProgramExperiment:
    """P2.1: MultiProgramExperiment base class."""

    def _load_module(self):
        eb_name = "qubox_v2.experiments.experiment_base"
        stub = types.ModuleType(eb_name)

        class _StubExperimentBase:
            def __init__(self, ctx=None):
                self._ctx = ctx

            @property
            def name(self):
                return type(self).__name__

            @property
            def hw(self):
                return self._ctx

        stub.ExperimentBase = _StubExperimentBase
        sys.modules[eb_name] = stub
        sys.modules.pop("qubox_v2.experiments.multi_program", None)

        return _load_as_submodule(
            "experiments/multi_program.py",
            "qubox_v2.experiments.multi_program",
        )

    def test_build_programs_must_be_overridden(self):
        mod = self._load_module()

        class Bare(mod.MultiProgramExperiment):
            pass

        exp = Bare(ctx=None)
        with pytest.raises(NotImplementedError):
            exp.build_programs()

    def test_multi_program_result_structure(self):
        mod = self._load_module()
        r = mod.MultiProgramResult()
        assert r.individual_results == []
        assert r.merged is None
        assert r.builds == []

    def test_run_all_happy_path(self):
        mod = self._load_module()
        result_mod = _get_result()
        hw_stub = sys.modules["qubox_v2.hardware.program_runner"]

        run_calls = []

        class _MockHW:
            def run_program(self, program, *, n_total=1, processors=(), **kw):
                run_calls.append(program)
                return hw_stub.RunResult(mode="hardware", output={"I": [1, 2, 3]})

            def set_element_frequency(self, el, freq):
                pass

        class MyMulti(mod.MultiProgramExperiment):
            def build_programs(self, *, n=2, **kw):
                return [
                    result_mod.ProgramBuildResult(program=f"prog_{i}", n_total=100)
                    for i in range(n)
                ]

        exp = MyMulti(ctx=_MockHW())
        result = exp.run_all(n=3)
        assert len(result.individual_results) == 3
        assert len(result.builds) == 3
        assert len(run_calls) == 3
        assert result.metadata["n_programs"] == 3
