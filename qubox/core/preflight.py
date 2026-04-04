"""qubox_v2.core.preflight
===========================
Pre-flight validation for experiment sessions.

Call ``preflight_check(session)`` after ``session.open()`` and before
running experiments to catch common configuration problems early.

Example::

    with SessionManager("./cooldown", qop_ip="10.0.0.1") as session:
        report = preflight_check(session)
        if not report["all_ok"]:
            for err in report["errors"]:
                print("PREFLIGHT FAIL:", err)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..experiments.session import SessionManager

_logger = logging.getLogger(__name__)

# Elements that every qubox setup should have
_BASELINE_ELEMENTS = ()  # v2.0.0: no hardcoded element requirements; validated via bindings
# Operations every element should have at minimum
_BASELINE_OPS = ("const",)


def preflight_check(
    session: "SessionManager",
    *,
    require_elements: list[str] | None = None,
    require_ops: dict[str, list[str]] | None = None,
    check_readout_weights: bool = True,
    check_calibration_file: bool = True,
    verbose: bool = True,
    auto_map_elements: bool = True,
) -> dict[str, Any]:
    """Run a comprehensive pre-flight validation of *session*.

    Parameters
    ----------
    session : SessionManager
        An already-opened session.
    require_elements : list[str], optional
        Elements that MUST exist in the QM config.  Defaults to
        ``["qubit", "readout"]``.
    require_ops : dict[str, list[str]], optional
        Mapping of ``{element: [op_names]}`` that must be registered in
        the PulseOperationManager.
    check_readout_weights : bool
        Verify that readout integration weights are present.
    check_calibration_file : bool
        Verify that the calibration JSON is readable.
    verbose : bool
        Log each check result at INFO level.

    Returns
    -------
    dict
        ``{"all_ok": bool, "errors": [...], "warnings": [...], "checks": {...}}``
    """
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, bool] = {}

    def _ok(name: str, msg: str = "") -> None:
        checks[name] = True
        if verbose:
            _logger.info("  [PASS] %s %s", name, msg)

    def _fail(name: str, msg: str) -> None:
        checks[name] = False
        errors.append(f"{name}: {msg}")
        if verbose:
            _logger.error("  [FAIL] %s — %s", name, msg)

    def _warn(name: str, msg: str) -> None:
        warnings.append(f"{name}: {msg}")
        if verbose:
            _logger.warning("  [WARN] %s — %s", name, msg)

    _logger.info("=== Preflight Check ===")

    # ---- 1. QM connection ----
    try:
        if session.hardware.qm is None:
            _fail("qm_connection", "QM not opened — call session.open() first")
        else:
            _ok("qm_connection")
    except Exception as exc:
        _fail("qm_connection", str(exc))

    # ---- 2. Elements in config ----
    snapshot = getattr(session, "context_snapshot", None)
    attr = snapshot() if callable(snapshot) else getattr(session, "attributes", None)
    default_ro_el = getattr(attr, "ro_el", None)
    default_qb_el = getattr(attr, "qb_el", None)

    if require_elements is None:
        required_els = [e for e in (default_qb_el, default_ro_el, *_BASELINE_ELEMENTS) if e]
    else:
        required_els = list(require_elements)

    def _resolve_element_alias(name: str) -> tuple[str | None, str | None]:
        if name in hw_elements:
            return name, None
        nlow = str(name).lower()
        if nlow == "readout":
            if default_ro_el and default_ro_el in hw_elements:
                return default_ro_el, (
                    f"requested '{name}' mapped to attributes.ro_el='{default_ro_el}'"
                )
            if "resonator" in hw_elements:
                return "resonator", "requested 'readout' mapped to existing element 'resonator'"
        return None, None

    hw_elements = set(session.hardware.elements.keys())
    resolved_elements: dict[str, str] = {}
    for el in required_els:
        tag = f"element_{el}"
        if el in hw_elements:
            resolved_elements[el] = el
            _ok(tag)
            continue

        mapped, note = _resolve_element_alias(el)
        if mapped is not None and auto_map_elements:
            resolved_elements[el] = mapped
            _warn(tag, f"{note}. Available: {sorted(hw_elements)}")
        else:
            suggestion = ""
            if default_ro_el and str(el).lower() == "readout":
                suggestion = f" Try element '{default_ro_el}' from cqed_params.json (ro_el)."
            _fail(tag, f"Element '{el}' not found in QM config. Available: {sorted(hw_elements)}.{suggestion}")

    # ---- 3. Baseline ops ----
    pom = session.pulse_mgr
    rops = require_ops or {}
    # Always check baseline ops for standard elements
    for el in required_els:
        resolved_el = resolved_elements.get(el, el)
        if resolved_el not in hw_elements:
            continue
        base_ops = list(_BASELINE_OPS)
        extra_ops = rops.get(el, [])
        for op in set(base_ops + extra_ops):
            tag = f"op_{resolved_el}_{op}"
            info = pom.get_pulseOp_by_element_op(resolved_el, op, strict=False)
            if info is not None:
                _ok(tag)
            else:
                _fail(tag, f"Operation '{op}' not mapped for element '{resolved_el}'")

    # ---- 4. Readout weights ----
    if check_readout_weights:
        tag = "readout_weights"
        try:
            ctx = session.context_snapshot() if callable(getattr(session, "context_snapshot", None)) else attr
            ro_el = ctx.ro_el if hasattr(ctx, "ro_el") else "readout"
            ro_op = "readout"
            pinfo = pom.get_pulseOp_by_element_op(ro_el, ro_op, strict=False)
            if pinfo is not None:
                _ok(tag, f"(element={ro_el!r}, op={ro_op!r})")
            else:
                _warn(tag, f"No pulse mapping for ({ro_el!r}, {ro_op!r}). "
                           "Run readout calibration to populate.")
        except Exception as exc:
            _warn(tag, f"Could not verify readout weights: {exc}")

    # ---- 5. Calibration files ----
    if check_calibration_file:
        tag = "calibration_file"
        try:
            cal_path = session.calibration._path
            if cal_path.exists():
                import json
                with open(cal_path, "r", encoding="utf-8") as f:
                    json.load(f)
                _ok(tag, str(cal_path))
            else:
                _warn(tag, f"Calibration file does not exist yet: {cal_path}")
        except Exception as exc:
            _fail(tag, f"Calibration file unreadable: {exc}")

    # ---- 6. Experiment path writable ----
    tag = "experiment_path"
    try:
        test_file = session.experiment_path / ".preflight_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        _ok(tag)
    except Exception as exc:
        _fail(tag, f"Cannot write to experiment path: {exc}")

    # ---- 7. measureConfig present ----
    tag = "measure_config"
    mc_path = session._resolve_path("measureConfig.json", required=False)
    if mc_path is not None and mc_path.exists():
        _ok(tag, str(mc_path))
    else:
        _warn(tag, "No measureConfig.json found — explicit readout defaults will be inferred")

    # ---- 8. Bindings validation ----
    tag = "bindings"
    try:
        from .bindings import validate_binding
        bindings_obj = session.bindings
        issues: list[str] = []
        issues.extend(validate_binding(bindings_obj.qubit))
        issues.extend(validate_binding(bindings_obj.readout))
        if bindings_obj.storage is not None:
            issues.extend(validate_binding(bindings_obj.storage))
        if issues:
            for issue in issues:
                _warn(tag, issue)
        else:
            _ok(tag, "ExperimentBindings validated")
    except Exception as exc:
        _warn(tag, f"Could not validate bindings: {exc}")

    # ---- Summary ----
    all_ok = len(errors) == 0
    _logger.info(
        "=== Preflight %s (%d checks, %d errors, %d warnings) ===",
        "PASSED" if all_ok else "FAILED",
        len(checks), len(errors), len(warnings),
    )
    return {
        "all_ok": all_ok,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }
