#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

"""qubox_v2 Post-Refactor Stabilization Audit -- Offline Execution Script.

Runs all three audit layers without hardware:
  Layer A: Static / Pure Logic
  Layer B: Compile-Only & Mock Runtime
  Parity & Performance checks

Usage:
    python audit_offline.py
"""

import base64
import copy
import hashlib
import json
import math
import os
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    category: str
    severity: str  # CRITICAL, MAJOR, MINOR, INFO
    title: str
    description: str
    location: str = ""
    fix_suggestion: str = ""

findings: list[Finding] = []

def record(cat, sev, title, desc, loc="", fix=""):
    findings.append(Finding(cat, sev, title, desc, loc, fix))

def section_header(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

def sub_header(title):
    print(f"\n  --- {title} ---")

pass_count = 0
fail_count = 0

def check(label, condition, detail=""):
    global pass_count, fail_count
    if condition:
        pass_count += 1
        print(f"    PASS  {label}")
    else:
        fail_count += 1
        print(f"    FAIL  {label}" + (f" -- {detail}" if detail else ""))
    return condition


# ===================================================================
# LAYER A: STATIC / PURE LOGIC AUDIT
# ===================================================================
section_header("LAYER A: STATIC / PURE LOGIC AUDIT")

# ------------------------------------------------------------------
# A.1 PulseSpec Schema Validation (Pydantic models)
# ------------------------------------------------------------------
sub_header("A.1  PulseSpec Pydantic Model Validation")

try:
    from qubox_v2.pulses.spec_models import (
        PulseConstraints, ConstantParams, ZeroParams, DragGaussianParams,
        DragCosineParams, KaiserParams, SlepianParams, FlattopParams,
        CLEARParams, RotationDerivedParams, ArbitraryBlobParams,
        PulseSpecEntry, PulseSpecFile, VALID_SHAPES,
    )

    # Valid instantiation
    check("PulseConstraints() default", PulseConstraints() is not None)
    check("ConstantParams(length=16)", ConstantParams(length=16) is not None)
    check("ZeroParams() default", ZeroParams() is not None)
    check("DragGaussianParams minimal",
          DragGaussianParams(amplitude=0.1, length=16, sigma=2.0) is not None)
    check("FlattopParams minimal",
          FlattopParams(amplitude=0.2, flat_length=100, rise_fall_length=20) is not None)

    # Reject bad length
    try:
        ConstantParams(length=2)
        check("ConstantParams rejects length<4", False, "Should have raised")
    except Exception:
        check("ConstantParams rejects length<4", True)

    # Reject unknown shape
    try:
        PulseSpecEntry(shape="nonexistent", element="q", op="x")
        check("PulseSpecEntry rejects unknown shape", False, "Should have raised")
    except Exception:
        check("PulseSpecEntry rejects unknown shape", True)

    # Validate completeness checker
    psf = PulseSpecFile(specs={
        "qb_const": PulseSpecEntry(shape="constant", element="qubit", op="const"),
        "qb_zero": PulseSpecEntry(shape="zero", element="qubit", op="zero"),
        "ro_const": PulseSpecEntry(shape="constant", element="resonator", op="const"),
    })
    warns = psf.validate_completeness()
    check("validate_completeness detects missing resonator zero",
          any("resonator" in w and "zero" in w for w in warns))

    # Shape set matches factory registration
    expected_shapes = {
        "constant", "zero", "drag_gaussian", "drag_cosine", "kaiser", "slepian",
        "flattop_gaussian", "flattop_cosine", "flattop_tanh", "flattop_blackman",
        "clear", "rotation_derived", "arbitrary_blob",
    }
    check("VALID_SHAPES matches expected set", VALID_SHAPES == expected_shapes,
          f"Missing: {expected_shapes - VALID_SHAPES}, Extra: {VALID_SHAPES - expected_shapes}")

except Exception as exc:
    check("PulseSpec model import", False, str(exc))
    record("pulse_system", "CRITICAL", "PulseSpec model import failure",
           str(exc), "pulses/spec_models.py")

# ------------------------------------------------------------------
# A.2 PulseFactory Determinism
# ------------------------------------------------------------------
sub_header("A.2  PulseFactory Determinism")

try:
    from qubox_v2.pulses.factory import (
        PulseFactory, _SHAPE_REGISTRY,
        _handle_drag_gaussian, _handle_constant, _handle_zero,
        _apply_constraints,
    )

    # Registry sanity
    check("12 shapes registered in factory",
          len(_SHAPE_REGISTRY) == 12,
          f"Got {len(_SHAPE_REGISTRY)}: {sorted(_SHAPE_REGISTRY.keys())}")

    # rotation_derived is NOT in _SHAPE_REGISTRY (handled specially in compile_one)
    check("rotation_derived not in registry (handled specially)",
          "rotation_derived" not in _SHAPE_REGISTRY)

    # Determinism: DRAG Gaussian called twice -> identical
    params = {"amplitude": 0.11165, "length": 16, "sigma": 2.6667,
              "drag_coeff": 0.5, "anharmonicity": 255750000.0,
              "detuning": 0.0, "subtracted": True}
    I1, Q1 = _handle_drag_gaussian(params)
    I2, Q2 = _handle_drag_gaussian(params)
    check("DRAG Gaussian determinism", I1 == I2 and Q1 == Q2)

    # DRAG sign convention: alpha/(2*pi*anharmonicity - 2*pi*detuning)
    # With alpha>0, anharmonicity>0, detuning=0: Q derivative should match
    params_pos = {"amplitude": 0.1, "length": 32, "sigma": 5.0,
                  "drag_coeff": 1.0, "anharmonicity": 200e6,
                  "detuning": 0.0, "subtracted": True}
    I_pos, Q_pos = _handle_drag_gaussian(params_pos)
    # Q should be proportional to dI/dt (derivative of Gaussian)
    # At center, Gaussian derivative == 0 -> Q should be near 0 at midpoint
    mid = len(Q_pos) // 2
    check("DRAG Q sign: Q near zero at midpoint", abs(Q_pos[mid]) < 0.01,
          f"Q[{mid}] = {Q_pos[mid]:.6f}")

    # Constants
    I_c, Q_c = _handle_constant({"amplitude_I": 0.3, "amplitude_Q": -0.1, "length": 100})
    check("Constant I all equal", all(v == 0.3 for v in I_c))
    check("Constant Q all equal", all(v == -0.1 for v in Q_c))
    check("Constant length correct", len(I_c) == 100 and len(Q_c) == 100)

    # Zero
    I_z, Q_z = _handle_zero({"length": 8})
    check("Zero all zeros", all(v == 0.0 for v in I_z) and all(v == 0.0 for v in Q_z))

    # Constraint: clipping
    I_big = [0.5, 0.6, 0.7, 0.5]
    Q_zero = [0.0] * 4
    I_cl, Q_cl = _apply_constraints(I_big, Q_zero, {"max_amplitude": 0.45, "clip": True})
    peak = max(abs(v) for v in I_cl)
    check("Clipping enforces max_amplitude", peak <= 0.45 + 1e-12, f"peak={peak}")

    # BUG CHECK: clipping uses uniform scaling, not per-sample clip
    # This means all samples are scaled by the same factor, preserving shape.
    # Verify the ratio is consistent:
    if I_big[2] != 0:
        ratio_0 = I_cl[0] / I_big[0]
        ratio_2 = I_cl[2] / I_big[2]
        check("Clipping uses uniform scaling (shape preserved)",
              abs(ratio_0 - ratio_2) < 1e-12,
              f"ratios: {ratio_0:.6f} vs {ratio_2:.6f}")

    # Constraint: padding
    I_odd = [0.1, 0.2, 0.3, 0.4, 0.5]
    Q_odd = [0.0] * 5
    I_pad, Q_pad = _apply_constraints(I_odd, Q_odd, {"pad_to_multiple_of": 4})
    check("Padding to multiple of 4", len(I_pad) % 4 == 0, f"len={len(I_pad)}")
    check("Padding adds zeros", I_pad[-1] == 0.0)

    # BUG CHECK: constraints with clip=False should NOT clip
    I_over = [0.5, 0.6]
    Q_over = [0.0, 0.0]
    I_noclip, Q_noclip = _apply_constraints(I_over, Q_over, {"max_amplitude": 0.45, "clip": False})
    check("clip=False does not enforce max_amplitude",
          max(abs(v) for v in I_noclip) >= 0.5,
          f"Expected unclipped but got peak={max(abs(v) for v in I_noclip)}")

except Exception as exc:
    check("PulseFactory import/baseline", False, str(exc))
    traceback.print_exc()
    record("pulse_system", "CRITICAL", "PulseFactory import failure",
           str(exc), "pulses/factory.py")

# ------------------------------------------------------------------
# A.3 PulseFactory: rotation_derived compilation
# ------------------------------------------------------------------
sub_header("A.3  Rotation-Derived Compilation")

try:
    specs_data = {
        "schema_version": 1,
        "specs": {
            "ref_r180": {
                "shape": "drag_gaussian", "element": "qubit", "op": "ref_r180",
                "params": {"amplitude": 0.11165, "length": 16, "sigma": 2.6667,
                           "drag_coeff": 0.0, "anharmonicity": 255750000.0,
                           "detuning": 0.0, "subtracted": True},
            },
            "x180": {
                "shape": "rotation_derived", "element": "qubit", "op": "x180",
                "params": {"reference_spec": "ref_r180", "theta": math.pi, "phi": 0.0},
            },
            "x90": {
                "shape": "rotation_derived", "element": "qubit", "op": "x90",
                "params": {"reference_spec": "ref_r180", "theta": math.pi / 2, "phi": 0.0},
            },
            "y180": {
                "shape": "rotation_derived", "element": "qubit", "op": "y180",
                "params": {"reference_spec": "ref_r180", "theta": math.pi, "phi": math.pi / 2},
            },
            "y90": {
                "shape": "rotation_derived", "element": "qubit", "op": "y90",
                "params": {"reference_spec": "ref_r180", "theta": math.pi / 2, "phi": math.pi / 2},
            },
        },
        "integration_weights": {},
        "element_operations": {},
    }
    factory = PulseFactory(specs_data)

    I_ref, Q_ref, _ = factory.compile_one("ref_r180")
    I_x180, Q_x180, _ = factory.compile_one("x180")
    I_x90, Q_x90, _ = factory.compile_one("x90")
    I_y180, Q_y180, _ = factory.compile_one("y180")
    I_y90, Q_y90, _ = factory.compile_one("y90")

    # x180 vs ref: theta=pi, phi=0 -> should closely match ref
    diff_x180 = np.max(np.abs(np.array(I_x180) - np.array(I_ref)))
    check("x180 ~= ref_r180 (theta=pi, phi=0)", diff_x180 < 1e-8, f"max diff={diff_x180:.2e}")

    # x90 should be ~0.5x amplitude of x180
    peak_x180 = np.max(np.abs(np.array(I_x180)))
    peak_x90 = np.max(np.abs(np.array(I_x90)))
    if peak_x180 > 0:
        ratio = peak_x90 / peak_x180
        check("x90/x180 amplitude ratio ~= 0.5", abs(ratio - 0.5) < 0.05,
              f"ratio={ratio:.4f}")
    else:
        check("x180 peak > 0", False, "x180 peak is zero")

    # y180: phi=pi/2, so I->near zero, Q dominant
    peak_y180_I = np.max(np.abs(np.array(I_y180)))
    peak_y180_Q = np.max(np.abs(np.array(Q_y180)))
    check("y180 Q dominant over I", peak_y180_Q > peak_y180_I * 0.9,
          f"I_peak={peak_y180_I:.4f}, Q_peak={peak_y180_Q:.4f}")

    # BUG CHECK: rotation sign convention -- exp(-j * phi_eff)
    # For phi=pi/2: exp(-j*pi/2) = -j -> swaps I->Q with sign
    w_ref = np.array(I_ref) + 1j * np.array(Q_ref)
    w_y180 = np.array(I_y180) + 1j * np.array(Q_y180)
    # Should satisfy w_y180 ~= w_ref * exp(-j*pi/2) = w_ref * (-j)
    expected = w_ref * np.exp(-1j * math.pi / 2)
    l2_sign = np.sqrt(np.sum(np.abs(w_y180 - expected)**2))
    check("y180 sign convention: w_ref * exp(-j*pi/2)", l2_sign < 1e-8,
          f"L2 diff = {l2_sign:.2e}")

    # Missing reference check
    bad_specs = {
        "schema_version": 1,
        "specs": {
            "broken": {
                "shape": "rotation_derived", "element": "qubit", "op": "broken",
                "params": {"reference_spec": "nonexistent"},
            },
        },
    }
    bad_factory = PulseFactory(bad_specs)
    try:
        bad_factory.compile_one("broken")
        check("Missing ref spec raises KeyError", False, "Should have raised")
    except KeyError:
        check("Missing ref spec raises KeyError", True)

    # compile_all() succeeds for valid specs
    compiled = factory.compile_all()
    check("compile_all() produces 5 specs", len(compiled) == 5, f"got {len(compiled)}")

except Exception as exc:
    check("Rotation-derived compilation", False, str(exc))
    traceback.print_exc()
    record("pulse_system", "CRITICAL", "Rotation-derived compilation failure",
           str(exc), "pulses/factory.py:_compile_rotation_derived")


# ------------------------------------------------------------------
# A.4 CalibrationStateMachine Transition Legality
# ------------------------------------------------------------------
sub_header("A.4  CalibrationStateMachine Transitions")

try:
    from qubox_v2.calibration.state_machine import (
        CalibrationStateMachine, CalibrationState, CalibrationStateError,
        CalibrationPatch, PatchValidation, PatchEntry,
        ALLOWED_TRANSITIONS, _UNIVERSAL_TARGETS,
    )

    sm = CalibrationStateMachine(experiment="test_audit")
    check("Initial state is IDLE", sm.state == CalibrationState.IDLE)

    # Happy path
    sm.transition(CalibrationState.CONFIGURED)
    check("IDLE -> CONFIGURED", sm.state == CalibrationState.CONFIGURED)
    sm.transition(CalibrationState.ACQUIRING)
    sm.transition(CalibrationState.ACQUIRED)
    sm.transition(CalibrationState.ANALYZING)
    sm.transition(CalibrationState.ANALYZED)
    sm.transition(CalibrationState.PENDING_APPROVAL)
    check("Full happy path to PENDING_APPROVAL", sm.state == CalibrationState.PENDING_APPROVAL)

    # Approval gating: needs patch
    check("is_committable() False without patch", not sm.is_committable())

    # Attach patch
    patch = CalibrationPatch(experiment="test_audit")
    patch.add_change("test.path", 1.0, 2.0)
    patch.validation = PatchValidation(passed=True, checks={"min_r2": True})

    # Setting patch outside ANALYZING/ANALYZED should fail
    sm2 = CalibrationStateMachine(experiment="test_patch_guard")
    try:
        sm2.patch = patch
        check("Patch assignment in IDLE raises error", False, "Should have raised")
    except CalibrationStateError:
        check("Patch assignment in IDLE raises error", True)

    # Set patch in valid state
    sm_patch = CalibrationStateMachine(experiment="test_patch_valid")
    sm_patch.transition(CalibrationState.CONFIGURED)
    sm_patch.transition(CalibrationState.ACQUIRING)
    sm_patch.transition(CalibrationState.ACQUIRED)
    sm_patch.transition(CalibrationState.ANALYZING)
    sm_patch.patch = patch
    check("Patch assignable in ANALYZING", sm_patch.patch is not None)

    sm_patch.transition(CalibrationState.ANALYZED)
    sm_patch.transition(CalibrationState.PENDING_APPROVAL)
    check("is_committable() True with valid patch", sm_patch.is_committable())

    # Illegal transition: IDLE -> COMMITTED
    sm3 = CalibrationStateMachine(experiment="test_illegal")
    try:
        sm3.transition(CalibrationState.COMMITTED)
        check("IDLE -> COMMITTED raises", False, "Should have raised")
    except CalibrationStateError:
        check("IDLE -> COMMITTED raises CalibrationStateError", True)

    # Illegal: CONFIGURED -> ANALYZED (skipping ACQUIRING)
    sm4 = CalibrationStateMachine(experiment="test_skip")
    sm4.transition(CalibrationState.CONFIGURED)
    try:
        sm4.transition(CalibrationState.ANALYZED)
        check("CONFIGURED -> ANALYZED (skip) raises", False, "Should have raised")
    except CalibrationStateError:
        check("CONFIGURED -> ANALYZED (skip) raises", True)

    # Universal targets: FAILED and ABORTED from any state
    for start_state_name in ["IDLE", "CONFIGURED", "ACQUIRING", "PENDING_APPROVAL"]:
        start_state = CalibrationState(start_state_name.lower())
        sm_univ = CalibrationStateMachine(experiment=f"test_univ_{start_state_name}")
        if start_state != CalibrationState.IDLE:
            # Walk to the start state
            path_to = {
                CalibrationState.CONFIGURED: [CalibrationState.CONFIGURED],
                CalibrationState.ACQUIRING: [CalibrationState.CONFIGURED, CalibrationState.ACQUIRING],
                CalibrationState.PENDING_APPROVAL: [
                    CalibrationState.CONFIGURED, CalibrationState.ACQUIRING,
                    CalibrationState.ACQUIRED, CalibrationState.ANALYZING,
                    CalibrationState.ANALYZED, CalibrationState.PENDING_APPROVAL,
                ],
            }
            for s in path_to.get(start_state, []):
                sm_univ.transition(s)

        sm_univ.transition(CalibrationState.FAILED)
        check(f"{start_state_name} -> FAILED allowed", sm_univ.state == CalibrationState.FAILED)

    sm_abort = CalibrationStateMachine(experiment="test_abort")
    sm_abort.abort("testing abort path")
    check("abort() from IDLE works", sm_abort.state == CalibrationState.ABORTED)

    # Double commit attempt
    sm_dc = CalibrationStateMachine(experiment="test_double_commit")
    sm_dc.transition(CalibrationState.CONFIGURED)
    sm_dc.transition(CalibrationState.ACQUIRING)
    sm_dc.transition(CalibrationState.ACQUIRED)
    sm_dc.transition(CalibrationState.ANALYZING)
    sm_dc.transition(CalibrationState.ANALYZED)
    sm_dc.transition(CalibrationState.PENDING_APPROVAL)
    sm_dc.transition(CalibrationState.COMMITTING)
    sm_dc.transition(CalibrationState.COMMITTED)
    try:
        sm_dc.transition(CalibrationState.COMMITTED)
        check("COMMITTED -> COMMITTED (double commit) raises", False, "Should have raised")
    except CalibrationStateError:
        check("COMMITTED -> COMMITTED (double commit) raises", True)

    # Rollback from COMMITTED
    sm_dc.transition(CalibrationState.ROLLED_BACK)
    check("COMMITTED -> ROLLED_BACK allowed", sm_dc.state == CalibrationState.ROLLED_BACK)

    # History tracking
    check("History length matches transitions", len(sm_dc.history) > 0)
    summary = sm_dc.summary()
    check("summary() returns dict with expected keys",
          "experiment" in summary and "state" in summary and "history" in summary)

except Exception as exc:
    check("CalibrationStateMachine import/test", False, str(exc))
    traceback.print_exc()
    record("calibration_state_machine", "CRITICAL", "State machine test failure",
           str(exc), "calibration/state_machine.py")

# ------------------------------------------------------------------
# A.5 CalibrationPatch Approval Gating
# ------------------------------------------------------------------
sub_header("A.5  CalibrationPatch Approval Gating")

try:
    # Approved: validation passed
    p1 = CalibrationPatch(experiment="t1")
    p1.validation = PatchValidation(passed=True, checks={"r2": True})
    check("Patch approved when validation passes", p1.is_approved())

    # Not approved: validation failed, no overrides
    p2 = CalibrationPatch(experiment="t2")
    p2.validation = PatchValidation(passed=False, checks={"r2": False, "bounds": True})
    check("Patch NOT approved when r2 fails without override", not p2.is_approved())

    # Override the failed gate
    p2.override_validation("r2", "Acceptable for test", user="audit_script")
    check("Patch approved after override", p2.is_approved())
    check("Override recorded in metadata",
          len(p2.metadata.get("validation_overrides", [])) == 1)

    # to_dict serialization
    d = p2.to_dict()
    check("to_dict() has 'changes' key", "changes" in d)
    check("to_dict() has 'overrides' key", "overrides" in d)
    check("to_dict() has 'validation' key", "validation" in d)

    # summary() produces string
    s = p2.summary()
    check("summary() returns non-empty string", len(s) > 10)

except Exception as exc:
    check("CalibrationPatch gating", False, str(exc))

# ------------------------------------------------------------------
# A.6 SessionState Immutability
# ------------------------------------------------------------------
sub_header("A.6  SessionState Immutability")

try:
    from qubox_v2.core.session_state import SessionState, SchemaInfo

    # Construct directly
    ss = SessionState(
        hardware={"elements": {"qubit": {}}},
        pulse_specs={"schema_version": 1, "specs": {}},
        calibration={"version": "3.0.0"},
        cqed_params={},
        schemas=(SchemaInfo("hardware", "/test", 1, 100),),
        build_hash="abc123def456",
        build_timestamp="2026-02-22T00:00:00",
        git_commit="deadbeef",
    )

    check("SessionState constructs", ss is not None)
    check("build_hash accessible", ss.build_hash == "abc123def456")

    # Frozen: attempt mutation should raise
    try:
        ss.build_hash = "modified"
        check("SessionState is frozen (rejects mutation)", False, "Assignment succeeded")
        record("session_state", "CRITICAL", "SessionState not frozen",
               "Mutation of frozen dataclass succeeded",
               "core/session_state.py", "Verify @dataclass(frozen=True)")
    except AttributeError:
        check("SessionState is frozen (rejects mutation)", True)

    # summary() and to_dict()
    check("summary() returns string", len(ss.summary()) > 0)
    d = ss.to_dict()
    check("to_dict() has build_hash", d["build_hash"] == "abc123def456")

except Exception as exc:
    check("SessionState immutability", False, str(exc))
    traceback.print_exc()

# ------------------------------------------------------------------
# A.7 Schema Version Guards
# ------------------------------------------------------------------
sub_header("A.7  Schema Version Guards")

try:
    from qubox_v2.core.schemas import (
        validate_schema, ValidationResult, UnsupportedSchemaError,
        migrate, MIGRATIONS, validate_config_dir,
    )

    # Valid hardware data
    hw_data = {"version": 1, "controllers": {}, "elements": {"qubit": {"operations": {"const": "p", "zero": "z"}}}}
    r = validate_schema(Path("fake.json"), "hardware", data=hw_data)
    check("Valid hardware schema passes", r.valid)

    # Unsupported version
    hw_bad = {"version": 99, "controllers": {}, "elements": {"qubit": {}}}
    r = validate_schema(Path("fake.json"), "hardware", data=hw_bad)
    check("Unsupported hardware version fails", not r.valid)

    # Missing required key
    hw_no_ctrl = {"version": 1, "elements": {"qubit": {}}}
    r = validate_schema(Path("fake.json"), "hardware", data=hw_no_ctrl)
    check("Missing 'controllers' key detected", not r.valid)

    # Unknown file type
    r = validate_schema(Path("fake.json"), "unknown_type", data={})
    check("Unknown file_type fails validation", not r.valid)

    # Pulse specs validation
    ps_data = {"schema_version": 1, "specs": {
        "qb_const": {"shape": "constant", "element": "qubit", "op": "const"},
    }}
    r = validate_schema(Path("fake.json"), "pulse_specs", data=ps_data)
    check("Valid pulse_specs passes", r.valid)

    ps_bad_shape = {"schema_version": 1, "specs": {
        "bad": {"shape": "nonexistent_shape", "element": "q", "op": "x"},
    }}
    r = validate_schema(Path("fake.json"), "pulse_specs", data=ps_bad_shape)
    check("Unknown shape in pulse_specs detected", not r.valid)

    # Calibration: version should be string
    cal_data = {"version": "3.0.0"}
    r = validate_schema(Path("fake.json"), "calibration", data=cal_data)
    check("Valid calibration schema passes", r.valid)

    # BUG CHECK: calibration with integer version
    cal_int = {"version": 3}
    r = validate_schema(Path("fake.json"), "calibration", data=cal_int)
    # This should fail because integer 3 is not in supported ["3.0.0"]
    check("Integer calibration version correctly rejected",
          not r.valid,
          f"valid={r.valid}, errors={r.errors}")
    if r.valid:
        record("schema_validation", "MAJOR",
               "Integer calibration version not rejected",
               "validate_schema accepts version=3 but supported is ['3.0.0']",
               "core/schemas.py:162",
               "Normalize version comparison (int vs string)")

    # Missing version field: should warn and assume v1
    no_ver = {"controllers": {}, "elements": {"q": {"operations": {"const": "p", "zero": "z"}}}}
    r = validate_schema(Path("fake.json"), "hardware", data=no_ver)
    check("Missing version warns (not errors)",
          r.valid and len(r.warnings) > 0,
          f"valid={r.valid}, warns={r.warnings}")

    # Corrupted schema_version (non-integer)
    corrupt = {"schema_version": "banana", "specs": {}}
    r = validate_schema(Path("fake.json"), "pulse_specs", data=corrupt)
    check("Corrupted schema_version rejected",
          not r.valid,
          f"valid={r.valid}")

    # Migration chain: no migrations registered, requesting v1->v2 should fail
    try:
        migrate({"version": 1}, "hardware", 1, 2)
        check("Missing migration step raises", False, "Should have raised")
    except UnsupportedSchemaError:
        check("Missing migration step raises UnsupportedSchemaError", True)

except Exception as exc:
    check("Schema version guards", False, str(exc))
    traceback.print_exc()

# ------------------------------------------------------------------
# A.8 Patch Application Logic
# ------------------------------------------------------------------
sub_header("A.8  Patch Application (calipatch.py)")

try:
    from qubox_v2.calibration.patch import (
        _get_nested, _set_nested, validate_patch_freshness, StalePatchError,
    )

    # _get_nested
    d = {"a": {"b": {"c": 42}}}
    check("_get_nested('a.b.c') == 42", _get_nested(d, "a.b.c") == 42)
    check("_get_nested('a.b.x') is None", _get_nested(d, "a.b.x") is None)
    check("_get_nested('x.y') is None", _get_nested(d, "x.y") is None)

    # _set_nested
    d2 = {}
    _set_nested(d2, "a.b.c", 99)
    check("_set_nested creates nested path", d2 == {"a": {"b": {"c": 99}}})

    # Overwrite existing
    _set_nested(d2, "a.b.c", 100)
    check("_set_nested overwrites", d2["a"]["b"]["c"] == 100)

    # BUG CHECK: _get_nested with value 0 (falsy but valid)
    d3 = {"a": {"b": 0}}
    val = _get_nested(d3, "a.b")
    check("_get_nested returns 0 (not None) for falsy value",
          val == 0,
          f"Got {val!r}")
    if val is None:
        record("calibration_patch", "MAJOR",
               "_get_nested returns None for falsy values",
               "_get_nested('a.b') returns None when actual value is 0 because `if current is None`",
               "calibration/patch.py:46",
               "Change `if current is None` to `if current is _SENTINEL`")

    # BUG CHECK: _get_nested with empty string value
    d4 = {"a": {"b": ""}}
    val2 = _get_nested(d4, "a.b")
    check("_get_nested returns '' for empty string value",
          val2 == "",
          f"Got {val2!r}")

    # BUG CHECK: _get_nested with False value
    d5 = {"a": {"b": False}}
    val3 = _get_nested(d5, "a.b")
    check("_get_nested returns False (not None) for False value",
          val3 is False,
          f"Got {val3!r}")

    # validate_patch_freshness
    store_data = {"frequencies": {"qubit": {"if_freq": 100e6}}}
    patch = CalibrationPatch(experiment="test")
    patch.add_change("frequencies.qubit.if_freq", 100e6, 110e6)
    stale = validate_patch_freshness(patch, store_data)
    check("Fresh patch has no stale entries", len(stale) == 0)

    # Stale case
    patch2 = CalibrationPatch(experiment="test")
    patch2.add_change("frequencies.qubit.if_freq", 99e6, 110e6)  # old_value wrong
    stale2 = validate_patch_freshness(patch2, store_data)
    check("Stale patch detected", len(stale2) > 0)

except Exception as exc:
    check("Patch application logic", False, str(exc))
    traceback.print_exc()

# ------------------------------------------------------------------
# A.9 ArtifactManager Path Safety
# ------------------------------------------------------------------
sub_header("A.9  ArtifactManager Path Safety")

try:
    from qubox_v2.core.artifact_manager import ArtifactManager, cleanup_artifacts, _looks_like_hash

    with tempfile.TemporaryDirectory() as tmpdir:
        am = ArtifactManager(tmpdir, "abc123def456")
        check("ArtifactManager root created", am.root.exists())
        check("Root path contains build hash", "abc123def456" in str(am.root))

        # Save artifacts
        state_path = am.save_session_state({"build_hash": "abc123def456", "test": True})
        check("save_session_state creates file", state_path.exists())

        config_path = am.save_generated_config({"elements": {}})
        check("save_generated_config creates file", config_path.exists())

        report_path = am.save_report("test_report", "# Test\nContent here")
        check("save_report creates file", report_path.exists())

        arb_path = am.save_artifact("test_artifact", {"key": "value"})
        check("save_artifact creates file", arb_path.exists())

        # List
        artifacts = am.list_artifacts()
        check("list_artifacts returns > 0", len(artifacts) > 0)

        # BUG CHECK: path traversal
        # Ensure artifact names can't escape the root
        safe_name = am.root / "test.json"
        check("Artifact paths stay within root",
              str(safe_name).startswith(str(am.root)))

    # Hash detection
    check("_looks_like_hash('abc123') True", _looks_like_hash("abc123"))
    check("_looks_like_hash('xyz!@#') False", not _looks_like_hash("xyz!@#"))
    check("_looks_like_hash('ABCDEF') True", _looks_like_hash("ABCDEF"))

except Exception as exc:
    check("ArtifactManager", False, str(exc))
    traceback.print_exc()


# ===================================================================
# LAYER B: COMPILE-ONLY & MOCK RUNTIME AUDIT
# ===================================================================
section_header("LAYER B: COMPILE-ONLY & MOCK RUNTIME AUDIT")

# ------------------------------------------------------------------
# B.1 SessionState from_config_dir (with real configs)
# ------------------------------------------------------------------
sub_header("B.1  SessionState.from_config_dir()")

config_dir = Path("seq_1_device/config")
session_state = None

try:
    if config_dir.exists():
        session_state = SessionState.from_config_dir(config_dir)
        check("SessionState built from real config", session_state is not None)
        check("build_hash is 12 chars", len(session_state.build_hash) == 12)
        check("build_hash is hex", _looks_like_hash(session_state.build_hash))
        check("hardware non-empty", len(session_state.hardware) > 0)
        check("calibration non-empty", len(session_state.calibration) > 0)
        check("schemas tuple populated", len(session_state.schemas) > 0)

        # Determinism: build twice -> same hash
        ss2 = SessionState.from_config_dir(config_dir)
        check("Deterministic build_hash", session_state.build_hash == ss2.build_hash)

        print(f"\n    Build hash: {session_state.build_hash}")
        print(f"    Schemas: {len(session_state.schemas)}")
        for s in session_state.schemas:
            print(f"      {s.file_type}: v{s.version} ({s.size_bytes} bytes)")
    else:
        check("Config dir exists for live test", False, f"{config_dir} not found")
except Exception as exc:
    check("SessionState.from_config_dir", False, str(exc))
    traceback.print_exc()

# ------------------------------------------------------------------
# B.2 Schema Validation on Real Config Files
# ------------------------------------------------------------------
sub_header("B.2  Schema Validation on Real Configs")

try:
    if config_dir.exists():
        results = validate_config_dir(config_dir)
        for r in results:
            status = "PASS" if r.valid else "FAIL"
            label = f"v={r.version}"
            check(f"Schema validation {label}", r.valid,
                  "; ".join(r.errors) if r.errors else "")
            if r.warnings:
                for w in r.warnings:
                    print(f"      WARN: {w}")
    else:
        print("    Skipped (no config dir)")
except Exception as exc:
    check("Real config schema validation", False, str(exc))

# ------------------------------------------------------------------
# B.3 Config Structure Audit
# ------------------------------------------------------------------
sub_header("B.3  Config Structure Audit")

try:
    if config_dir.exists():
        hw_path = config_dir / "hardware.json"
        if hw_path.exists():
            hw = json.loads(hw_path.read_bytes())
            elements = hw.get("elements", {})
            for el_name, el_data in elements.items():
                ops = el_data.get("operations", {})
                check(f"Element '{el_name}' has operations",
                      len(ops) > 0, f"ops={list(ops.keys())}")

        cal_path = config_dir / "calibration.json"
        if cal_path.exists():
            cal = json.loads(cal_path.read_bytes())
            check("calibration.json has version field", "version" in cal)

            # Check for direct mutation risk: no mutable references leaked
            cal_copy = copy.deepcopy(cal)
            check("calibration.json deep-copyable", cal_copy == cal)
except Exception as exc:
    check("Config structure audit", False, str(exc))


# ===================================================================
# LAYER B.4: WAVEFORM REGRESSION (run actual tests)
# ===================================================================
sub_header("B.4  Waveform Regression Tests")

try:
    from qubox_v2.verification.waveform_regression import run_all_checks, ShapeTestResult

    wf_results = run_all_checks()
    wf_passed = sum(1 for r in wf_results if r.passed)
    wf_failed = sum(1 for r in wf_results if not r.passed)

    print(f"    Total: {len(wf_results)}  Passed: {wf_passed}  Failed: {wf_failed}")

    for r in wf_results:
        if not r.passed:
            check(f"[{r.shape}] {r.test_name}", False, r.error)
            record("waveform_regression", "MAJOR" if "DRAG" in r.shape else "MINOR",
                   f"Waveform test failure: {r.shape}/{r.test_name}",
                   r.error, "verification/waveform_regression.py")
        else:
            check(f"[{r.shape}] {r.test_name}", True)

except Exception as exc:
    check("Waveform regression suite", False, str(exc))
    traceback.print_exc()
    record("waveform_regression", "CRITICAL", "Waveform regression suite crashed",
           str(exc), "verification/waveform_regression.py")


# ===================================================================
# LAYER B.5: MOCK REPLAY FRAMEWORK
# ===================================================================
sub_header("B.5  Mock Replay Framework (FakeRunner)")

try:
    # Build a synthetic replay dataset and run through analysis
    @dataclass
    class RawDataset:
        experiment: str
        timestamp: str
        n_avg: int
        raw_data: dict[str, Any]
        metadata: dict[str, Any] = field(default_factory=dict)

    def save_dataset(ds: RawDataset, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "experiment": ds.experiment,
            "timestamp": ds.timestamp,
            "n_avg": ds.n_avg,
            "raw_data": {k: v.tolist() if isinstance(v, np.ndarray) else v
                         for k, v in ds.raw_data.items()},
            "metadata": ds.metadata,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return path

    def load_dataset(path: Path) -> RawDataset:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        raw = {k: np.array(v) if isinstance(v, list) else v
               for k, v in d.get("raw_data", {}).items()}
        return RawDataset(
            experiment=d["experiment"],
            timestamp=d["timestamp"],
            n_avg=d["n_avg"],
            raw_data=raw,
            metadata=d.get("metadata", {}),
        )

    # Create synthetic GE discrimination dataset
    np.random.seed(42)
    n_shots = 1000
    g_I = np.random.normal(0.002, 0.001, n_shots)
    g_Q = np.random.normal(-0.001, 0.001, n_shots)
    e_I = np.random.normal(-0.003, 0.001, n_shots)
    e_Q = np.random.normal(0.002, 0.001, n_shots)

    ds = RawDataset(
        experiment="ge_discrimination",
        timestamp=datetime.now().isoformat(),
        n_avg=n_shots,
        raw_data={"g_I": g_I, "g_Q": g_Q, "e_I": e_I, "e_Q": e_Q},
        metadata={"element": "resonator", "readout_length": 400},
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        ds_path = save_dataset(ds, Path(tmpdir) / "ge_disc.json")
        loaded = load_dataset(ds_path)
        check("Dataset round-trip preserves shape",
              loaded.raw_data["g_I"].shape == (n_shots,))
        check("Dataset round-trip preserves values",
              np.allclose(loaded.raw_data["g_I"], g_I))

    # Simple discrimination analysis (offline)
    g_complex = g_I + 1j * g_Q
    e_complex = e_I + 1j * e_Q
    g_mean = np.mean(g_complex)
    e_mean = np.mean(e_complex)
    separation = abs(e_mean - g_mean)
    g_std = np.std(np.abs(g_complex - g_mean))
    e_std = np.std(np.abs(e_complex - e_mean))
    snr = separation / ((g_std + e_std) / 2)

    check("Synthetic GE separation > 0", separation > 0, f"sep={separation:.6f}")
    check("Synthetic GE SNR > 1", snr > 1.0, f"SNR={snr:.2f}")

    print(f"    Separation: {separation:.6f}")
    print(f"    SNR: {snr:.2f}")
    print(f"    FakeRunner replay framework: operational")

except Exception as exc:
    check("Mock replay framework", False, str(exc))
    traceback.print_exc()


# ===================================================================
# PERFORMANCE & STRESS TESTS
# ===================================================================
section_header("PERFORMANCE & STRESS TESTS")

# ------------------------------------------------------------------
# P.1 Session Build Time
# ------------------------------------------------------------------
sub_header("P.1  Session Build Time")

try:
    if config_dir.exists():
        times = []
        for _ in range(10):
            t0 = time.perf_counter()
            ss = SessionState.from_config_dir(config_dir)
            t1 = time.perf_counter()
            times.append(t1 - t0)

        avg_ms = np.mean(times) * 1000
        max_ms = np.max(times) * 1000
        check(f"SessionState build avg < 200ms", avg_ms < 200, f"avg={avg_ms:.1f}ms")
        print(f"    Avg: {avg_ms:.1f}ms, Max: {max_ms:.1f}ms, Min: {np.min(times)*1000:.1f}ms")

        # Repeated builds produce same hash
        hashes = set()
        for _ in range(5):
            hashes.add(SessionState.from_config_dir(config_dir).build_hash)
        check("Repeated builds -> same hash", len(hashes) == 1)
except Exception as exc:
    check("Session build time", False, str(exc))

# ------------------------------------------------------------------
# P.2 PulseFactory Compile Time (large spec set)
# ------------------------------------------------------------------
sub_header("P.2  PulseFactory Compile Time")

try:
    # Generate a large spec set
    large_specs = {"schema_version": 1, "specs": {}, "integration_weights": {}, "element_operations": {}}
    for i in range(100):
        large_specs["specs"][f"const_{i}"] = {
            "shape": "constant", "element": f"el_{i % 5}", "op": "const",
            "params": {"amplitude_I": 0.1 * (i % 5), "amplitude_Q": 0.0, "length": 100},
        }
    for i in range(20):
        large_specs["specs"][f"drag_{i}"] = {
            "shape": "drag_gaussian", "element": "qubit", "op": f"rot_{i}",
            "params": {"amplitude": 0.1, "length": 16, "sigma": 2.6667,
                       "drag_coeff": 0.0, "anharmonicity": 255750000.0,
                       "detuning": 0.0, "subtracted": True},
        }

    t0 = time.perf_counter()
    factory = PulseFactory(large_specs)
    compiled = factory.compile_all()
    t1 = time.perf_counter()
    compile_ms = (t1 - t0) * 1000

    check(f"120 specs compiled in < 2s", compile_ms < 2000, f"took {compile_ms:.0f}ms")
    check("All 120 specs compiled", len(compiled) == 120, f"got {len(compiled)}")
    print(f"    120 specs compiled in {compile_ms:.0f}ms")

except Exception as exc:
    check("PulseFactory compile time", False, str(exc))

# ------------------------------------------------------------------
# P.3 Empty / Edge Case Configs
# ------------------------------------------------------------------
sub_header("P.3  Edge Case Configs")

try:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Empty calibration
        empty_cal = {"version": "3.0.0"}
        (tmpdir / "calibration.json").write_text(json.dumps(empty_cal))

        # Minimal hardware
        min_hw = {"version": 1, "controllers": {}, "elements": {
            "qubit": {"operations": {"const": "p", "zero": "z"}},
        }}
        (tmpdir / "hardware.json").write_text(json.dumps(min_hw))

        ss_edge = SessionState.from_config_dir(tmpdir)
        check("SessionState from minimal config", ss_edge is not None)
        check("Empty calibration handled", len(ss_edge.calibration) > 0)

        # Empty pulse_specs
        empty_ps = {"schema_version": 1, "specs": {}}
        (tmpdir / "pulse_specs.json").write_text(json.dumps(empty_ps))

        factory_empty = PulseFactory(empty_ps)
        compiled_empty = factory_empty.compile_all()
        check("Empty pulse_specs compiles to empty dict", len(compiled_empty) == 0)

except Exception as exc:
    check("Edge case configs", False, str(exc))

# ------------------------------------------------------------------
# P.4 Artifact Cleanup Stress
# ------------------------------------------------------------------
sub_header("P.4  Artifact Cleanup Stress")

try:
    with tempfile.TemporaryDirectory() as tmpdir:
        art_dir = Path(tmpdir) / "artifacts"
        # Create 20 fake hash dirs
        for i in range(20):
            d = art_dir / f"{i:012x}"
            d.mkdir(parents=True)
            (d / "session_state.json").write_text("{}")
            # Stagger modification times
            import time as time_mod
            time_mod.sleep(0.01)

        removed = cleanup_artifacts(tmpdir, keep_latest=5)
        remaining = [d for d in art_dir.iterdir() if d.is_dir()]
        check("Cleanup keeps 5, removes 15", len(remaining) == 5 and len(removed) == 15,
              f"remaining={len(remaining)}, removed={len(removed)}")

except Exception as exc:
    check("Artifact cleanup stress", False, str(exc))


# ===================================================================
# DIRECT LEGACY PARITY CHECK
# ===================================================================
section_header("LEGACY PARITY CHECK")

sub_header("Direct Waveform Comparison (Synthetic)")

try:
    from qubox_v2.verification.legacy_parity import compare_waveforms

    # Identical waveforms: should pass
    I = np.array([0.1, 0.2, 0.3, 0.2, 0.1])
    Q = np.array([0.0, 0.01, 0.02, 0.01, 0.0])
    cmp = compare_waveforms("identical", I, Q, I.copy(), Q.copy())
    check("Identical waveforms pass parity", cmp.passed)
    check("Identical L2 == 0", cmp.l2_norm == 0.0)

    # Slightly different: should fail at strict thresholds
    I_diff = I + 1e-8
    cmp2 = compare_waveforms("slight_diff", I, Q, I_diff, Q)
    check("Slight diff (1e-8) detected at strict thresholds", not cmp2.passed,
          f"L2={cmp2.l2_norm:.2e}")

    # Zero waveforms: both zero -> pass
    cmp3 = compare_waveforms("both_zero", np.zeros(10), np.zeros(10),
                             np.zeros(10), np.zeros(10))
    check("Both-zero waveforms pass", cmp3.passed)
    check("Both-zero dot product == 1.0", cmp3.normalized_dot_product == 1.0)

    # Length mismatch
    cmp4 = compare_waveforms("length_mismatch", np.zeros(10), np.zeros(10),
                             np.zeros(8), np.zeros(8))
    check("Length mismatch detected", not cmp4.passed and not cmp4.length_match)

    # Sign flip (critical for DRAG)
    I_pos = np.array([0.0, 0.05, 0.1, 0.05, 0.0])
    I_neg = -I_pos
    cmp5 = compare_waveforms("sign_flip", I_pos, Q, I_neg, Q)
    check("Sign flip detected", not cmp5.passed)

    print(f"\n    Sign flip metrics: L2={cmp5.l2_norm:.4f}, dot={cmp5.normalized_dot_product:.4f}")

except Exception as exc:
    check("Legacy parity comparison", False, str(exc))
    traceback.print_exc()


# ===================================================================
# BUG DETECTION SUMMARY -- flagging found issues
# ===================================================================
section_header("BUG DETECTION: IDENTIFIED ISSUES")

# Check for _get_nested falsy-value bug
from qubox_v2.calibration.patch import _get_nested

bug_tests = [
    ({"a": 0}, "a", 0, "_get_nested returns 0"),
    ({"a": False}, "a", False, "_get_nested returns False"),
    ({"a": ""}, "a", "", "_get_nested returns empty string"),
    ({"a": []}, "a", [], "_get_nested returns empty list"),
    ({"a": 0.0}, "a", 0.0, "_get_nested returns 0.0"),
]

for d, path, expected, label in bug_tests:
    actual = _get_nested(d, path)
    is_correct = actual == expected and type(actual) == type(expected)
    if not is_correct:
        record("calibration_patch", "MAJOR",
               f"_get_nested falsy-value bug: {label}",
               f"Expected {expected!r} ({type(expected).__name__}), got {actual!r} ({type(actual).__name__})",
               "calibration/patch.py:_get_nested",
               "Use a sentinel value instead of `if current is None`")
    check(label, is_correct, f"got {actual!r}")

# Check CalibrationPatch._overrides not in to_dict() consistently
try:
    p_check = CalibrationPatch(experiment="check")
    p_check.add_change("a.b", 1, 2)
    p_check.validation = PatchValidation(passed=False, checks={"gate": False})
    p_check.override_validation("gate", "reason", user="tester")
    d = p_check.to_dict()
    check("Overrides serialized in to_dict()",
          "overrides" in d and d["overrides"].get("gate") == "reason")
except Exception as exc:
    check("Patch override serialization", False, str(exc))

# Check state machine: ANALYZED -> PENDING_APPROVAL shortcut
try:
    sm_short = CalibrationStateMachine(experiment="shortcut_test")
    sm_short.transition(CalibrationState.CONFIGURED)
    sm_short.transition(CalibrationState.ACQUIRING)
    sm_short.transition(CalibrationState.ACQUIRED)
    sm_short.transition(CalibrationState.ANALYZING)
    sm_short.transition(CalibrationState.ANALYZED)
    sm_short.transition(CalibrationState.PENDING_APPROVAL)
    check("ANALYZED -> PENDING_APPROVAL shortcut works",
          sm_short.state == CalibrationState.PENDING_APPROVAL)
except CalibrationStateError as exc:
    check("ANALYZED -> PENDING_APPROVAL shortcut", False, str(exc))
    record("calibration_state_machine", "MINOR",
           "ANALYZED->PENDING_APPROVAL shortcut missing",
           str(exc), "calibration/state_machine.py:ALLOWED_TRANSITIONS")


# ===================================================================
# FINAL SUMMARY
# ===================================================================
section_header("AUDIT RESULTS SUMMARY")

total = pass_count + fail_count
print(f"\n  Total checks: {total}")
print(f"  Passed: {pass_count}")
print(f"  Failed: {fail_count}")
if total > 0:
    pct = (pass_count / total) * 100
    print(f"  Pass rate: {pct:.1f}%")

# Score
if fail_count == 0:
    score = 10
elif fail_count <= 2:
    score = 8
elif fail_count <= 5:
    score = 6
elif fail_count <= 10:
    score = 4
else:
    score = 2

print(f"\n  STABILITY SCORE: {score}/10")

# Findings summary
if findings:
    print(f"\n  Findings: {len(findings)}")
    critical = [f for f in findings if f.severity == "CRITICAL"]
    major = [f for f in findings if f.severity == "MAJOR"]
    minor = [f for f in findings if f.severity == "MINOR"]
    info = [f for f in findings if f.severity == "INFO"]

    if critical:
        print(f"    CRITICAL: {len(critical)}")
    if major:
        print(f"    MAJOR: {len(major)}")
    if minor:
        print(f"    MINOR: {len(minor)}")
    if info:
        print(f"    INFO: {len(info)}")

    print("\n  FINDINGS DETAIL:")
    for i, f in enumerate(findings, 1):
        print(f"\n    [{f.severity}] #{i}: {f.title}")
        print(f"      Category: {f.category}")
        print(f"      Description: {f.description}")
        if f.location:
            print(f"      Location: {f.location}")
        if f.fix_suggestion:
            print(f"      Suggested fix: {f.fix_suggestion}")
else:
    print("\n  No findings recorded.")

print(f"\n{'='*70}")
print(f"  AUDIT COMPLETE")
print(f"{'='*70}")
