"""qubox.preflight — pre-flight session validation.

Adapted to duck-type the session object so it works with both the qubox
:class:`~qubox.session.Session` (with ``__getattr__`` forwarding) and the
legacy ``SessionManager`` directly.

Usage::

    from qubox.preflight import preflight_check

    report = preflight_check(session)
    if not report["all_ok"]:
        for err in report["errors"]:
            print("PREFLIGHT FAIL:", err)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

_BASELINE_OPS = ("const",)


def preflight_check(
    session: Any,
    *,
    require_elements: list[str] | None = None,
    require_ops: dict[str, list[str]] | None = None,
    check_readout_weights: bool = True,
    check_calibration_file: bool = True,
    verbose: bool = True,
    auto_map_elements: bool = True,
) -> dict[str, Any]:
    """Run comprehensive pre-flight validation of *session*.

    Parameters
    ----------
    session
        An already-opened session (qubox Session or legacy SessionManager).
    require_elements : list[str], optional
        Elements that MUST exist in the QM config.  If None, uses
        ``[qb_el, ro_el]`` from the session context.
    require_ops : dict[str, list[str]], optional
        Additional ``{element: [op_names]}`` that must be registered.
    check_readout_weights : bool
        Verify that readout integration weights are present.
    check_calibration_file : bool
        Verify that the calibration JSON is readable.
    verbose : bool
        Log each check result at INFO/ERROR/WARNING level.

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
        hw = session.hardware
        if getattr(hw, "qm", None) is None:
            _fail("qm_connection", "QM not opened — call session.open() first")
        else:
            _ok("qm_connection")
    except Exception as exc:
        _fail("qm_connection", str(exc))

    # ---- 2. Resolve context snapshot ----
    ctx_snap = getattr(session, "context_snapshot", None)
    attr = ctx_snap() if callable(ctx_snap) else getattr(session, "attributes", None)
    default_ro_el = getattr(attr, "ro_el", None)
    default_qb_el = getattr(attr, "qb_el", None)

    if require_elements is None:
        required_els = [e for e in (default_qb_el, default_ro_el) if e]
    else:
        required_els = list(require_elements)

    # ---- 3. Elements present ----
    try:
        hw_elements = set(session.hardware.elements.keys())
    except Exception:
        hw_elements = set()

    def _resolve_element_alias(name: str) -> tuple[str | None, str | None]:
        if name in hw_elements:
            return name, None
        nlow = str(name).lower()
        if nlow == "readout":
            if default_ro_el and default_ro_el in hw_elements:
                return default_ro_el, f"requested '{name}' mapped to attributes.ro_el='{default_ro_el}'"
            if "resonator" in hw_elements:
                return "resonator", "requested 'readout' mapped to existing element 'resonator'"
        return None, None

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
                suggestion = f" Try element '{default_ro_el}'."
            _fail(tag, f"Element '{el}' not found in QM config. Available: {sorted(hw_elements)}.{suggestion}")

    # ---- 4. Baseline ops ----
    try:
        pom = session.pulse_mgr
        rops = require_ops or {}
        for el in required_els:
            resolved_el = resolved_elements.get(el, el)
            if resolved_el not in hw_elements:
                continue
            for op in set(list(_BASELINE_OPS) + rops.get(el, [])):
                tag = f"op_{resolved_el}_{op}"
                info = pom.get_pulseOp_by_element_op(resolved_el, op, strict=False)
                if info is not None:
                    _ok(tag)
                else:
                    _fail(tag, f"Operation '{op}' not mapped for element '{resolved_el}'")
    except Exception as exc:
        _warn("baseline_ops", f"Could not verify baseline ops: {exc}")

    # ---- 5. Readout weights ----
    if check_readout_weights:
        tag = "readout_weights"
        try:
            ro_el = getattr(attr, "ro_el", "readout") if attr else "readout"
            pom = session.pulse_mgr
            pinfo = pom.get_pulseOp_by_element_op(ro_el, "readout", strict=False)
            if pinfo is not None:
                _ok(tag, f"(element={ro_el!r}, op='readout')")
            else:
                _warn(tag, f"No pulse mapping for ({ro_el!r}, 'readout'). Run readout calibration.")
        except Exception as exc:
            _warn(tag, f"Could not verify readout weights: {exc}")

    # ---- 6. Calibration file ----
    if check_calibration_file:
        tag = "calibration_file"
        try:
            import json
            cal_path = session.calibration._path
            if cal_path.exists():
                with open(cal_path, "r", encoding="utf-8") as f:
                    json.load(f)
                _ok(tag, str(cal_path))
            else:
                _warn(tag, f"Calibration file does not exist yet: {cal_path}")
        except Exception as exc:
            _fail(tag, f"Calibration file unreadable: {exc}")

    # ---- 7. Experiment path writable ----
    tag = "experiment_path"
    try:
        test_file = Path(session.experiment_path) / ".preflight_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        _ok(tag)
    except Exception as exc:
        _fail(tag, f"Cannot write to experiment path: {exc}")

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
