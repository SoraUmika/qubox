from __future__ import annotations

import importlib
import sys
import types
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest


class _FakeExpr:
    def __init__(self, text: str):
        self.text = text

    def __repr__(self) -> str:
        return self.text

    def __str__(self) -> str:
        return self.text

    def __and__(self, other):
        return _FakeExpr(f"({self.text}&{other})")

    def __or__(self, other):
        return _FakeExpr(f"({self.text}|{other})")

    def __invert__(self):
        return _FakeExpr(f"(~{self.text})")

    def __add__(self, other):
        return _FakeExpr(f"({self.text}+{other})")

    def __sub__(self, other):
        return _FakeExpr(f"({self.text}-{other})")

    def __mul__(self, other):
        return _FakeExpr(f"({self.text}*{other})")

    def __gt__(self, other):
        return _FakeExpr(f"({self.text}>{other})")

    def __lt__(self, other):
        return _FakeExpr(f"({self.text}<{other})")


class _FakeVar(_FakeExpr):
    counter = 0

    def __init__(self, prefix: str = "v"):
        _FakeVar.counter += 1
        super().__init__(f"{prefix}{_FakeVar.counter}")

    def _binary(self, op: str, other):
        return _FakeExpr(f"({self.text}{op}{other})")

    def __gt__(self, other):
        return self._binary(">", other)

    def __lt__(self, other):
        return self._binary("<", other)

    def __eq__(self, other):  # type: ignore[override]
        return self._binary("==", other)

    def __add__(self, other):
        return self._binary("+", other)

    def __radd__(self, other):
        return _FakeExpr(f"({other}+{self.text})")

    def __sub__(self, other):
        return self._binary("-", other)

    def __mul__(self, other):
        return self._binary("*", other)


class _FakeStream:
    def __init__(self, name: str = "stream"):
        self.name = name

    def boolean_to_int(self):
        return self

    def buffer(self, *_args, **_kwargs):
        return self

    def average(self):
        return self

    def save(self, *_args, **_kwargs):
        return None

    def save_all(self, *_args, **_kwargs):
        return None


class _FakeContext:
    def __init__(self, value=None):
        self.value = value if value is not None else self

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeProgram:
    pass


def _stub_callable(*_args, **_kwargs):
    return None


def _install_sdk_stubs() -> None:
    if "qm" in sys.modules and "qm.qua" in sys.modules:
        return

    pkg_root = Path(__file__).resolve().parents[2]

    qm_mod = types.ModuleType("qm")
    qua_mod = types.ModuleType("qm.qua")
    loops_mod = types.ModuleType("qualang_tools.loops")
    units_mod = types.ModuleType("qualang_tools.units")
    qualang_tools_mod = types.ModuleType("qualang_tools")

    def _program():
        return _FakeContext(_FakeProgram())

    def _declare(*_args, **_kwargs):
        return _FakeVar()

    def _declare_stream(*_args, **_kwargs):
        return _FakeStream()

    def _context(*_args, **_kwargs):
        return _FakeContext()

    def _amp(_value):
        return 1

    qua_mod.program = _program
    qua_mod.declare = _declare
    qua_mod.declare_stream = _declare_stream
    qua_mod.save = _stub_callable
    qua_mod.stream_processing = _context
    qua_mod.for_ = _context
    qua_mod.for_each_ = _context
    qua_mod.while_ = _context
    qua_mod.if_ = _context
    qua_mod.elif_ = _context
    qua_mod.else_ = _context
    qua_mod.switch_ = _context
    qua_mod.case_ = _context
    qua_mod.play = _stub_callable
    qua_mod.wait = _stub_callable
    qua_mod.update_frequency = _stub_callable
    qua_mod.measure = _stub_callable
    qua_mod.align = _stub_callable
    qua_mod.frame_rotation_2pi = _stub_callable
    qua_mod.reset_phase = _stub_callable
    qua_mod.reset_frame = _stub_callable
    qua_mod.pause = _stub_callable
    qua_mod.infinite_loop_ = _context
    qua_mod.assign = _stub_callable
    qua_mod.amp = _amp
    qua_mod.fixed = object()
    qua_mod.IO1 = object()
    qua_mod.IO2 = object()
    qua_mod.Math = types.SimpleNamespace(
        ln=lambda x: x,
        sin2pi=lambda x: x,
        cos2pi=lambda x: x,
    )
    qua_mod.dual_demod = types.SimpleNamespace(
        full=_stub_callable,
        sliced=_stub_callable,
        accumulated=_stub_callable,
        moving_window=_stub_callable,
    )
    qua_mod.demod = types.SimpleNamespace(sliced=_stub_callable)
    qua_mod.integration = types.SimpleNamespace()
    qua_mod.__all__ = [
        "program",
        "declare",
        "declare_stream",
        "save",
        "stream_processing",
        "for_",
        "for_each_",
        "while_",
        "if_",
        "elif_",
        "else_",
        "switch_",
        "case_",
        "play",
        "wait",
        "update_frequency",
        "measure",
        "align",
        "frame_rotation_2pi",
        "reset_phase",
        "reset_frame",
        "pause",
        "infinite_loop_",
        "assign",
        "amp",
        "fixed",
        "IO1",
        "IO2",
        "Math",
        "dual_demod",
        "demod",
        "integration",
    ]

    qm_mod.generate_qua_script = lambda *_args, **_kwargs: "<stubbed qua script>"
    qm_mod.qua = qua_mod

    loops_mod.from_array = lambda *_args, **_kwargs: (None, None, None)
    qualang_tools_mod.loops = loops_mod
    units_mod.unit = lambda *_args, **_kwargs: None
    qualang_tools_mod.units = units_mod

    sys.modules["qm"] = qm_mod
    sys.modules["qm.qua"] = qua_mod
    sys.modules["qualang_tools"] = qualang_tools_mod
    sys.modules["qualang_tools.loops"] = loops_mod
    sys.modules["qualang_tools.units"] = units_mod

    # Stub heavy transitive dependencies that the test environment may lack
    for stub_name in [
        "qubox_tools",
        "qubox_tools.algorithms",
        "qubox_tools.algorithms.transforms",
        "qubox_tools.algorithms.core",
        "qubox_tools.algorithms.metrics",
        "qubox_tools.algorithms.readout_analysis",
    ]:
        if stub_name not in sys.modules:
            stub = types.ModuleType(stub_name)
            for attr in [
                "complex_encoder", "complex_decoder", "interp_logpdf",
                "bilinear_interp_logpdf", "compile_1d_kde_to_grid",
                "compile_2d_kde_to_grid", "classify_iq_point",
                "assign_fidelity_optimal_threshold", "compute_readout_fidelity",
                "compute_waveform_fft", "gaussianity_score",
                "derive_measure_outcome_from_raw",
                "derive_measure_outcome_from_classified",
                "classify_iq_blob_pair", "pair_classify_and_derive",
            ]:
                setattr(stub, attr, _stub_callable)
            if stub_name == "qubox_tools":
                stub.__path__ = [str(pkg_root / "qubox_tools")]
            elif stub_name.startswith("qubox_tools.algorithms"):
                stub.__path__ = [str(pkg_root / "qubox_tools" / "algorithms")]
            sys.modules[stub_name] = stub

    # Pre-register qubox as a minimal package to bypass heavy __init__.py
    if "qubox" not in sys.modules:
        qubox_pkg = types.ModuleType("qubox")
        qubox_pkg.__path__ = [str(pkg_root / "qubox")]
        sys.modules["qubox"] = qubox_pkg
    for subpkg_path in [
        "core", "calibration", "programs", "experiments", "gates",
        "gates/hardware", "pulses", "tools", "programs/macros",
        "programs/gate_lowerers", "programs/builders",
    ]:
        dotted = "qubox." + subpkg_path.replace("/", ".")
        if dotted not in sys.modules:
            sub = types.ModuleType(dotted)
            sub.__path__ = [str(pkg_root / "qubox" / subpkg_path)]
            sys.modules[dotted] = sub


def _reload_gate_modules():
    for name in [
        "qubox.programs.circuit_display",
        "qubox.programs.circuit_execution",
        "qubox.programs.circuit_compiler",
        "qubox.programs.circuit_postprocess",
        "qubox.programs.circuit_protocols",
        "qubox.programs.circuit_runner",
    ]:
        sys.modules.pop(name, None)
    circuit_runner = importlib.import_module("qubox.programs.circuit_runner")
    circuit_display = importlib.import_module("qubox.programs.circuit_display")
    circuit_execution = importlib.import_module("qubox.programs.circuit_execution")
    circuit_compiler = importlib.import_module("qubox.programs.circuit_compiler")
    circuit_postprocess = importlib.import_module("qubox.programs.circuit_postprocess")
    circuit_protocols = importlib.import_module("qubox.programs.circuit_protocols")
    return SimpleNamespace(
        circuit_runner=circuit_runner,
        circuit_display=circuit_display,
        circuit_execution=circuit_execution,
        circuit_compiler=circuit_compiler,
        circuit_postprocess=circuit_postprocess,
        circuit_protocols=circuit_protocols,
    )


def _fake_emit_measurement_spec(
    _spec,
    *,
    targets=None,
    with_state=False,
    state=None,
    **_kwargs,
):
    if with_state:
        return tuple(targets or []) + ((state,) if state is not None else tuple())
    return tuple(targets or [])


@pytest.fixture(scope="session")
def gate_arch_modules():
    _install_sdk_stubs()
    modules = _reload_gate_modules()
    modules.circuit_compiler.emit_measurement_spec = _fake_emit_measurement_spec
    return modules


class FakeHW:
    def __init__(self):
        self._lo = {"qubit": 6.0e9, "readout": 8.0e9, "storage": 7.0e9}
        self.elements = {name: {"LO": freq, "IF": 50e6} for name, freq in self._lo.items()}
        self.qm = object()
        self.run_calls: list[dict[str, object]] = []

    def get_element_lo(self, element: str) -> float:
        return float(self._lo[element])

    def set_element_fq(self, element: str, freq: float) -> None:
        self.elements.setdefault(element, {})
        self.elements[element]["RF"] = float(freq)

    def run_program(self, program, *, n_total=1, processors=(), **kwargs):
        self.run_calls.append(
            {
                "program": program,
                "n_total": int(n_total),
                "processors": tuple(processors),
                "kwargs": dict(kwargs),
            }
        )
        return SimpleNamespace(mode="hardware", output={"I": [0.0], "Q": [0.0]}, metadata={"n_total": int(n_total)})


class FakeConfigEngine:
    def __init__(self, pulse_mgr):
        self.pulse_mgr = pulse_mgr
        self._base = {
            "version": 1,
            "controllers": {
                "con1": {
                    "analog_outputs": {
                        1: {"offset": 0.0},
                        2: {"offset": 0.0},
                        3: {"offset": 0.0},
                        4: {"offset": 0.0},
                        5: {"offset": 0.0},
                        6: {"offset": 0.0},
                    },
                    "digital_outputs": {1: {}, 2: {}, 3: {}},
                    "analog_inputs": {
                        1: {"offset": 0.0, "gain_db": 0},
                        2: {"offset": 0.0, "gain_db": 0},
                    },
                }
            },
            "elements": {
                "qubit": {
                    "mixInputs": {"I": ("con1", 1), "Q": ("con1", 2), "lo_frequency": 6.0e9, "mixer": "mixer_q"},
                    "intermediate_frequency": 50e6,
                    "operations": {},
                },
                "readout": {
                    "mixInputs": {"I": ("con1", 3), "Q": ("con1", 4), "lo_frequency": 8.0e9, "mixer": "mixer_ro"},
                    "intermediate_frequency": 50e6,
                    "operations": {},
                    "outputs": {"out1": ("con1", 1), "out2": ("con1", 2)},
                    "time_of_flight": 24,
                    "smearing": 0,
                },
                "storage": {
                    "mixInputs": {"I": ("con1", 5), "Q": ("con1", 6), "lo_frequency": 7.0e9, "mixer": "mixer_st"},
                    "intermediate_frequency": 50e6,
                    "operations": {},
                },
            },
            "mixers": {
                "mixer_q": [{"intermediate_frequency": 50e6, "lo_frequency": 6.0e9, "correction": [1.0, 0.0, 0.0, 1.0]}],
                "mixer_ro": [{"intermediate_frequency": 50e6, "lo_frequency": 8.0e9, "correction": [1.0, 0.0, 0.0, 1.0]}],
                "mixer_st": [{"intermediate_frequency": 50e6, "lo_frequency": 7.0e9, "correction": [1.0, 0.0, 0.0, 1.0]}],
            },
            "waveforms": {},
            "digital_waveforms": {},
            "pulses": {},
            "integration_weights": {},
        }

    def build_qm_config(self):
        cfg = deepcopy(self._base)
        self.pulse_mgr.burn_to_config(cfg, include_volatile=True)
        return cfg


@pytest.fixture
def fake_session(tmp_path, gate_arch_modules):
    from qubox.core.device_metadata import DeviceMetadata
    from qubox.calibration.store_models import PulseCalibration
    from qubox.calibration.store import CalibrationStore
    from qubox.pulses.manager import PulseOperationManager

    pulse_mgr = PulseOperationManager(elements=["qubit", "readout", "storage"])
    pulse_mgr.create_control_pulse(
        "qubit",
        "x90",
        length=16,
        I_samples=[0.1] * 16,
        Q_samples=[0.0] * 16,
        persist=True,
        override=True,
    )
    pulse_mgr.create_control_pulse(
        "qubit",
        "x180",
        length=16,
        I_samples=[0.2] * 16,
        Q_samples=[0.0] * 16,
        persist=True,
        override=True,
    )
    pulse_mgr._perm.el_ops.setdefault("readout", {})["readout"] = pulse_mgr.READOUT_PULSE_NAME

    calibration = CalibrationStore(tmp_path / "calibration.json")
    calibration.set_cqed_params("transmon", qubit_freq=6.05e9)
    calibration.set_cqed_params("resonator", resonator_freq=8.10e9)
    calibration.set_cqed_params("storage", storage_freq=7.10e9)
    calibration.set_discrimination(
        "readout",
        threshold=0.015,
        angle=0.25,
        mu_g=[-0.1, 0.0],
        mu_e=[0.1, 0.0],
        sigma_g=0.02,
        sigma_e=0.02,
        fidelity=0.98,
    )
    calibration.set_pulse_calibration(
        "ge_ref_r180",
        PulseCalibration(
            pulse_name="ge_ref_r180",
            amplitude=0.22,
            length=32,
            sigma=8,
            drag_coeff=0.4,
        ),
    )
    calibration.save()

    attr = DeviceMetadata(
        qb_el="qubit",
        ro_el="readout",
        st_el="storage",
        _calibration=calibration,
    )

    return SimpleNamespace(
        calibration=calibration,
        pulse_mgr=pulse_mgr,
        hw=FakeHW(),
        config_engine=FakeConfigEngine(pulse_mgr),
        bindings=None,
        cluster_name="Cluster_1",
        context_snapshot=lambda: attr,
    )
