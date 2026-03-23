"""qubox.calibration.orchestrator — calibration execution and patch lifecycle.

Migrated from ``qubox_v2_legacy.calibration.orchestrator``.
qubox_v2_legacy imports removed; QUA-specific ops (measureMacro sync) are
kept as lazy runtime-only imports so this module can be loaded without
connecting to hardware.

Flow::

    orch = CalibrationOrchestrator(session)
    artifact       = orch.run_experiment(exp)
    cal_result     = orch.analyze(exp, artifact)
    patch          = orch.build_patch(cal_result)
    preview        = orch.apply_patch(patch, dry_run=True)   # safe preview
    apply_result   = orch.apply_patch(patch, dry_run=False)  # commit

Or the convenience wrapper::

    result = orch.run_analysis_patch_cycle(exp, apply=True)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.persistence import sanitize_mapping_for_json, split_output_for_persistence
from .contracts import Artifact, CalibrationResult, Patch
from .patch_rules import default_patch_rules

_logger = logging.getLogger(__name__)


@dataclass
class _SimpleRunResult:
    """Minimal stand-in for a RunResult when replaying from an Artifact."""

    output: dict[str, Any]
    metadata: dict[str, Any]
    mode: str = "hardware"
    sim_samples: None = None


class CalibrationOrchestrator:
    """Owns experiment execution, artifact persistence, and patch lifecycle.

    Parameters
    ----------
    session
        A session object that exposes:
        ``calibration`` (CalibrationStore), ``experiment_path`` (Path),
        ``pulse_mgr`` (POM), ``context_snapshot()`` (ctx), ``save_pulses()``,
        ``burn_pulses(include_volatile=...)``, ``bindings`` (optional).
    patch_rules : dict, optional
        Override specific rule lists; keys are ``CalibrationResult.kind`` strings.
    """

    def __init__(self, session: Any, *, patch_rules: dict[str, list[Any]] | None = None):
        self.session = session
        self._applied_patches: list[str] = []
        rules = default_patch_rules(session)
        if patch_rules:
            for kind, kind_rules in patch_rules.items():
                rules[kind] = list(kind_rules)
        self.patch_rules = rules

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def run_experiment(self, exp: Any, **run_kwargs: Any) -> Artifact:
        """Execute *exp* and return an :class:`~qubox.calibration.contracts.Artifact`."""
        result = exp.run(**run_kwargs)
        return self._artifact_from_result(exp.__class__.__name__, result)

    # ------------------------------------------------------------------
    # Analyze
    # ------------------------------------------------------------------
    def analyze(self, exp: Any, artifact: Artifact, **analyze_kwargs: Any) -> CalibrationResult:
        """Call ``exp.analyze`` and wrap the output in a :class:`CalibrationResult`."""
        pseudo_result = _SimpleRunResult(
            output=dict(artifact.data),
            metadata=dict(artifact.meta),
        )
        analyze_kwargs = dict(analyze_kwargs or {})
        update_calibration = bool(analyze_kwargs.pop("update_calibration", True))

        out = exp.analyze(pseudo_result, update_calibration=update_calibration, **analyze_kwargs)
        out_metadata = dict(getattr(out, "metadata", {}) or {})
        kind = str(out_metadata.get("calibration_kind") or exp.__class__.__name__)

        quality: dict[str, Any] = {}
        fit = getattr(out, "fit", None)
        if fit is not None:
            quality["r_squared"] = getattr(fit, "r_squared", None)
            fit_success = getattr(fit, "success", None)
            if fit_success is False:
                quality["passed"] = False
                quality["failure_reason"] = getattr(fit, "reason", None) or "fit did not converge"
                return CalibrationResult(
                    kind=kind,
                    params=dict(getattr(out, "metrics", {}) or {}),
                    uncertainties=dict(getattr(fit, "uncertainties", {}) or {}),
                    quality=quality,
                    evidence={"artifact_id": artifact.artifact_id, "analysis_metadata": out_metadata},
                )

        r_sq = quality.get("r_squared")
        quality["passed"] = not (r_sq is not None and r_sq < 0.5)
        if not quality["passed"]:
            quality["failure_reason"] = f"r_squared={r_sq:.3f} < 0.5"

        return CalibrationResult(
            kind=kind,
            params=dict(getattr(out, "metrics", {}) or {}),
            uncertainties=dict(getattr(getattr(out, "fit", None), "uncertainties", {}) or {}),
            quality=quality,
            evidence={"artifact_id": artifact.artifact_id, "analysis_metadata": out_metadata},
        )

    # ------------------------------------------------------------------
    # Build patch
    # ------------------------------------------------------------------
    def build_patch(self, result: CalibrationResult) -> Patch:
        """Apply all matching rules to *result* and aggregate into one Patch."""
        patch = Patch(
            reason=f"Auto-generated patch for {result.kind}",
            provenance={
                "kind": result.kind,
                "timestamp": datetime.now().isoformat(),
                "quality": result.quality,
                "evidence": result.evidence,
            },
        )
        for rule in self.patch_rules.get(result.kind, []):
            generated = rule(result)
            if generated is None:
                continue
            for op in generated.updates:
                patch.updates.append(op)
        return patch

    # ------------------------------------------------------------------
    # Apply patch
    # ------------------------------------------------------------------
    def apply_patch(self, patch: Patch, dry_run: bool = True) -> dict[str, Any]:
        """Apply (or preview) a calibration patch.

        Parameters
        ----------
        patch : Patch
            Collection of :class:`~qubox.calibration.contracts.UpdateOp` items.
        dry_run : bool
            Default ``True`` (safe preview).  Pass ``False`` to commit.

        Returns
        -------
        dict
            ``{"dry_run": bool, "n_updates": int, "preview": list, "sync_ok": bool}``
        """
        preview: list[dict[str, Any]] = [
            {"op": u.op, "payload": u.payload} for u in patch.updates
        ]

        if dry_run:
            return {"dry_run": True, "n_updates": len(patch.updates), "preview": preview, "sync_ok": True}

        # Snapshot for rollback
        snapshot = self.session.calibration.create_in_memory_snapshot()
        try:
            self._apply_updates(patch)
        except Exception as exc:
            _logger.error(
                "Patch apply failed mid-way — rolling back CalibrationStore. Error: %s", exc, exc_info=True,
            )
            self.session.calibration.restore_in_memory_snapshot(snapshot)
            raise RuntimeError(f"Transactional patch apply failed and was rolled back: {exc}") from exc

        self.session.calibration.save()
        self.session.save_pulses()

        sync_ok = True
        # Optional: sync measureMacro (hardware-specific, lazy import)
        try:
            from qubox.programs.macros.measure import measureMacro  # type: ignore[import]
            ro_el = getattr(self.session.context_snapshot(), "ro_el", None)
            if ro_el is not None:
                measureMacro.sync_from_calibration(self.session.calibration, ro_el)
        except ImportError:
            pass
        except Exception as exc:
            _logger.warning("measureMacro sync_from_calibration failed: %s", exc)
            sync_ok = False

        try:
            bindings = getattr(self.session, "bindings", None)
            if bindings is not None:
                bindings.readout.sync_from_calibration(self.session.calibration)
        except Exception as exc:
            _logger.warning("ReadoutBinding sync_from_calibration failed: %s", exc)
            sync_ok = False

        tag = getattr(patch, "reason", None) or f"patch_{len(self._applied_patches)}"
        self._applied_patches.append(tag)

        return {"dry_run": False, "n_updates": len(patch.updates), "preview": preview, "sync_ok": sync_ok}

    # ------------------------------------------------------------------
    # Convenience cycle
    # ------------------------------------------------------------------
    def run_analysis_patch_cycle(
        self,
        exp: Any,
        *,
        run_kwargs: dict[str, Any] | None = None,
        analyze_kwargs: dict[str, Any] | None = None,
        persist_artifact: bool = True,
        apply: bool = False,
    ) -> dict[str, Any]:
        """Run full orchestration and return patch preview.

        Returns
        -------
        dict
            Keys: ``artifact``, ``artifact_path``, ``calibration_result``,
            ``patch``, ``dry_run``, ``apply_result``.
        """
        run_kwargs = dict(run_kwargs or {})
        analyze_kwargs = dict(analyze_kwargs or {})

        artifact = self.run_experiment(exp, **run_kwargs)
        artifact_path: str | None = None
        if persist_artifact:
            artifact_path = str(self.persist_artifact(artifact))

        calibration_result = self.analyze(exp, artifact, **analyze_kwargs)
        patch = self.build_patch(calibration_result)
        dry_run = self.apply_patch(patch, dry_run=True)

        if apply and not calibration_result.passed:
            _logger.warning(
                "Skipping patch application: calibration_result.passed=False for kind=%r "
                "(reason: %s). Dry-run preview still available.",
                calibration_result.kind,
                calibration_result.quality.get("failure_reason", "unknown"),
            )
            apply_result = None
        else:
            apply_result = self.apply_patch(patch, dry_run=False) if apply else None

        return {
            "artifact": artifact,
            "artifact_path": artifact_path,
            "calibration_result": calibration_result,
            "patch": patch,
            "dry_run": dry_run,
            "apply_result": apply_result,
        }

    def list_applied_patches(self) -> list[str]:
        """Return list of patch tags applied during this session."""
        return list(self._applied_patches)

    # ------------------------------------------------------------------
    # Artifact persistence
    # ------------------------------------------------------------------
    def persist_artifact(self, artifact: Artifact) -> Path:
        """Save artifact arrays and metadata to disk under experiment_path/artifacts/."""
        root = Path(self.session.experiment_path) / "artifacts" / "runtime"
        root.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        data_path = root / f"{artifact.name}_{ts}.npz"
        meta_path = root / f"{artifact.name}_{ts}.meta.json"

        arrays, meta, dropped = split_output_for_persistence(artifact.data)
        if dropped:
            meta["_persistence"] = {
                "raw_data_policy": "drop_shot_level_arrays",
                "dropped_fields": dropped,
            }
        meta["artifact_meta"] = artifact.meta
        meta["artifact_id"] = artifact.artifact_id

        ctx = getattr(self.session, "context", None)
        if ctx is not None and hasattr(ctx, "to_dict"):
            meta["experiment_context"] = ctx.to_dict()

        import numpy as np
        np.savez_compressed(data_path, **arrays)

        payload, dropped_meta = sanitize_mapping_for_json(meta)
        if dropped_meta:
            payload.setdefault("_persistence", {})["dropped_fields_meta"] = dropped_meta
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        return data_path

    # ------------------------------------------------------------------
    # Internal: apply individual update ops
    # ------------------------------------------------------------------
    def _apply_updates(self, patch: Patch) -> None:
        for update in patch.updates:
            op = update.op
            payload = update.payload

            if op == "SetCalibration":
                self._set_calibration_path(str(payload["path"]), payload.get("value"))

            elif op == "SetPulseParam":
                self._set_pulse_param(str(payload["pulse_name"]), str(payload["field"]), payload.get("value"))

            elif op == "SetMeasureWeights":
                self._apply_measure_weights(payload)

            elif op == "PersistMeasureConfig":
                self._apply_persist_measure_config(payload)

            elif op == "SetMeasureDiscrimination":
                self._apply_measure_discrimination(payload)

            elif op == "SetMeasureQuality":
                self._apply_measure_quality(payload)

            elif op == "TriggerPulseRecompile":
                include_volatile = bool(payload.get("include_volatile", True))
                self.session.burn_pulses(include_volatile=include_volatile)

    def _apply_measure_weights(self, payload: dict[str, Any]) -> None:
        try:
            from qubox.programs.macros.measure import measureMacro  # type: ignore[import]
        except ImportError:
            _logger.warning("SetMeasureWeights: measureMacro not available — skipping")
            return
        element = str(payload.get("element", getattr(self.session.context_snapshot(), "ro_el", "rr")))
        operation = str(payload.get("operation", "readout"))
        weights = payload.get("weights")
        info = self.session.pulse_mgr.get_pulseOp_by_element_op(element, operation, strict=False)
        if info is not None and weights is not None:
            if isinstance(weights, dict):
                pulse = info.pulse
                for label, value in weights.items():
                    if isinstance(value, dict):
                        cos = value.get("cos")
                        sin = value.get("sin")
                        if cos is not None and sin is not None:
                            self.session.pulse_mgr.add_int_weight_segments(label, cos, sin, persist=False)
                    elif isinstance(value, (list, tuple)) and len(value) == 2:
                        self.session.pulse_mgr.add_int_weight_segments(label, value[0], value[1], persist=False)
                    self.session.pulse_mgr.append_integration_weight_mapping(
                        pulse, label, label, override=True,
                    )
                return
            measureMacro.set_pulse_op(info, active_op=operation, weights=weights, weight_len=info.length)

    def _apply_persist_measure_config(self, payload: dict[str, Any]) -> None:
        try:
            from qubox.programs.macros.measure import measureMacro  # type: ignore[import]
        except ImportError:
            _logger.warning("PersistMeasureConfig: measureMacro not available — skipping")
            return
        dst = Path(payload.get("path") or (self.session.experiment_path / "config" / "measureConfig.json"))
        dst.parent.mkdir(parents=True, exist_ok=True)
        measureMacro.save_json(str(dst))

    def _apply_measure_discrimination(self, payload: dict[str, Any]) -> None:
        try:
            from qubox.programs.macros.measure import measureMacro  # type: ignore[import]
        except ImportError:
            _logger.warning("SetMeasureDiscrimination: measureMacro not available — skipping")
            return
        measureMacro._update_readout_discrimination(payload)

    def _apply_measure_quality(self, payload: dict[str, Any]) -> None:
        try:
            from qubox.programs.macros.measure import measureMacro  # type: ignore[import]
        except ImportError:
            _logger.warning("SetMeasureQuality: measureMacro not available — skipping")
            return
        measureMacro._update_readout_quality(payload)

    def _set_calibration_path(self, dotted_path: str, value: Any) -> None:
        parts = dotted_path.split(".")
        dispatch = {
            "frequencies":          ("set_frequencies",   2),
            "coherence":            ("set_coherence",      2),
            "pulse_calibrations":   ("set_pulse_calibration", 2),
            "discrimination":       ("set_discrimination", 2),
            "readout_quality":      ("set_readout_quality", 2),
            "cqed_params":          ("set_cqed_params",   2),
        }
        if len(parts) >= 3 and parts[0] in dispatch:
            method_name, _ = dispatch[parts[0]]
            element_or_key = parts[1]
            field_name = parts[2]
            getattr(self.session.calibration, method_name)(element_or_key, **{field_name: value})
            return

        # Fallback: generic dict update + reload
        raw = self.session.calibration.to_dict()
        cursor = raw
        for key in parts[:-1]:
            if key not in cursor or not isinstance(cursor[key], dict):
                cursor[key] = {}
            cursor = cursor[key]
        cursor[parts[-1]] = value
        self.session.calibration.reload_from_dict(raw)

    def _set_pulse_param(self, pulse_name: str, field: str, value: Any) -> None:
        cal = self.session.calibration.get_pulse_calibration(pulse_name)
        old = cal.model_dump() if cal is not None else {"pulse_name": pulse_name}
        old[field] = value
        self.session.calibration.set_pulse_calibration(pulse_name, **old)

    def _artifact_from_result(self, name: str, run_result: Any) -> Artifact:
        out = getattr(run_result, "output", {})
        data = dict(out) if isinstance(out, dict) else (out if isinstance(out, dict) else {})
        try:
            data = dict(out)
        except (TypeError, ValueError):
            data = {}
        meta = dict(getattr(run_result, "metadata", {}) or {})
        meta.setdefault("timestamp", datetime.now().isoformat())
        return Artifact(name=name, data=data, raw=None, meta=meta)
