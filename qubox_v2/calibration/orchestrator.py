from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .contracts import Artifact, CalibrationResult, Patch
from .patch_rules import default_patch_rules
from ..analysis.output import Output
from ..core.persistence_policy import split_output_for_persistence, sanitize_mapping_for_json

_logger = logging.getLogger(__name__)


class CalibrationOrchestrator:
    """Owns execution persistence and state mutation application.

    Flow:
      run_experiment -> Artifact
      persist_artifact
      analyze -> CalibrationResult
      build_patch -> Patch
      apply_patch

        Convenience:
            run_analysis_patch_cycle -> execute full flow in one call
    """

    def __init__(self, session, *, patch_rules: dict[str, list[Any]] | None = None):
        self.session = session
        self._applied_patches: list[str] = []
        rules = default_patch_rules(session)
        if patch_rules:
            for kind, kind_rules in patch_rules.items():
                rules[kind] = list(kind_rules)
        self.patch_rules = rules

    def run_experiment(self, exp, **run_kwargs: Any) -> Artifact:
        result = exp.run(**run_kwargs)
        return self._artifact_from_result(exp.__class__.__name__, result)

    def analyze(self, exp, artifact: Artifact, **analyze_kwargs: Any) -> CalibrationResult:
        pseudo_result = self._run_result_from_artifact(artifact)
        analyze_kwargs = dict(analyze_kwargs or {})
        update_calibration = bool(analyze_kwargs.pop("update_calibration", True))
        out = exp.analyze(
            pseudo_result,
            update_calibration=update_calibration,
            **analyze_kwargs,
        )
        out_metadata = dict(getattr(out, "metadata", {}) or {})
        kind = str(out_metadata.get("calibration_kind") or exp.__class__.__name__)

        quality = {}
        if getattr(out, "fit", None) is not None:
            fit = out.fit
            quality["r_squared"] = getattr(fit, "r_squared", None)
        r_sq = quality.get("r_squared")
        if r_sq is not None and r_sq < 0.5:
            quality["passed"] = False
            quality["failure_reason"] = f"r_squared={r_sq:.3f} < 0.5"
        else:
            quality["passed"] = True

        return CalibrationResult(
            kind=kind,
            params=dict(getattr(out, "metrics", {}) or {}),
            uncertainties=dict(getattr(getattr(out, "fit", None), "uncertainties", {}) or {}),
            quality=quality,
            evidence={
                "artifact_id": artifact.artifact_id,
                "analysis_metadata": out_metadata,
            },
        )

    def build_patch(self, result: CalibrationResult) -> Patch:
        patch = Patch(
            reason=f"Auto-generated patch for {result.kind}",
            provenance={
                "kind": result.kind,
                "timestamp": datetime.now().isoformat(),
                "quality": result.quality,
                "evidence": result.evidence,
            },
        )

        rules = self.patch_rules.get(result.kind, [])
        for rule in rules:
            generated = rule(result)
            if generated is None:
                continue
            for op in generated.updates:
                patch.updates.append(op)
        return patch

    def run_analysis_patch_cycle(
        self,
        exp,
        *,
        run_kwargs: dict[str, Any] | None = None,
        analyze_kwargs: dict[str, Any] | None = None,
        persist_artifact: bool = True,
        apply: bool = False,
    ) -> dict[str, Any]:
        """Run full orchestration and return patch preview.

        Parameters
        ----------
        exp
            Experiment instance (subclass of ExperimentBase).
        run_kwargs
            Keyword arguments passed to exp.run(...).
        analyze_kwargs
            Keyword arguments passed to exp.analyze(...).
        persist_artifact
            Persist artifact to disk before analysis.
        apply
            If True, apply generated patch after creating dry-run preview.

        Returns
        -------
        dict
            {
              "artifact": Artifact,
              "artifact_path": str | None,
              "calibration_result": CalibrationResult,
              "patch": Patch,
              "dry_run": dict,
              "apply_result": dict | None,
            }
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
        apply_result = self.apply_patch(patch, dry_run=False) if apply else None

        return {
            "artifact": artifact,
            "artifact_path": artifact_path,
            "calibration_result": calibration_result,
            "patch": patch,
            "dry_run": dry_run,
            "apply_result": apply_result,
        }

    def apply_patch(self, patch: Patch, dry_run: bool = False) -> dict[str, Any]:
        preview: list[dict[str, Any]] = []

        for update in patch.updates:
            op = update.op
            payload = update.payload
            preview.append({"op": op, "payload": payload})

            if dry_run:
                continue

            if op == "SetCalibration":
                path = str(payload["path"])
                value = payload.get("value")
                self._set_calibration_path(path, value)

            elif op == "SetPulseParam":
                pulse_name = str(payload["pulse_name"])
                field = str(payload["field"])
                value = payload.get("value")
                self._set_pulse_param(pulse_name, field, value)

            elif op == "SetMeasureWeights":
                from ..programs.macros.measure import measureMacro
                element = str(payload.get("element", self.session.attributes.ro_el))
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
                                    self.session.pulse_mgr.add_int_weight_segments(
                                        label,
                                        cos,
                                        sin,
                                        persist=False,
                                    )
                            elif isinstance(value, (list, tuple)) and len(value) == 2:
                                self.session.pulse_mgr.add_int_weight_segments(
                                    label,
                                    value[0],
                                    value[1],
                                    persist=False,
                                )
                            self.session.pulse_mgr.append_integration_weight_mapping(
                                pulse,
                                label,
                                label,
                                override=True,
                            )
                        continue
                    measureMacro.set_pulse_op(info, active_op=operation, weights=weights, weight_len=info.length)

            elif op == "PersistMeasureConfig":
                from ..programs.macros.measure import measureMacro
                dst = Path(payload.get("path") or (self.session.experiment_path / "config" / "measureConfig.json"))
                dst.parent.mkdir(parents=True, exist_ok=True)
                measureMacro.save_json(str(dst))

            elif op == "SetMeasureDiscrimination":
                from ..programs.macros.measure import measureMacro
                measureMacro._update_readout_discrimination(payload)

            elif op == "SetMeasureQuality":
                from ..programs.macros.measure import measureMacro
                measureMacro._update_readout_quality(payload)

            elif op == "TriggerPulseRecompile":
                include_volatile = bool(payload.get("include_volatile", True))
                self.session.burn_pulses(include_volatile=include_volatile)

        if not dry_run:
            self.session.calibration.save()
            self.session.save_pulses()

            sync_ok = True
            try:
                self.session.refresh_attribute_frequencies_from_calibration(persist=True)
            except Exception as exc:
                _logger.warning("refresh_attribute_frequencies_from_calibration failed: %s", exc, exc_info=True)
                sync_ok = False

            # Sync measureMacro from CalibrationStore after every commit
            # so discrimination/quality params stay in sync.
            try:
                from ..programs.macros.measure import measureMacro
                ro_el = getattr(self.session.attributes, "ro_el", None)
                if ro_el is not None:
                    measureMacro.sync_from_calibration(self.session.calibration, ro_el)
            except Exception as exc:
                _logger.warning("measureMacro sync_from_calibration failed: %s", exc, exc_info=True)
                sync_ok = False

            # Sync bindings from CalibrationStore (binding-driven API)
            try:
                bindings = getattr(self.session, "bindings", None)
                if bindings is not None:
                    bindings.readout.sync_from_calibration(self.session.calibration)
            except Exception as exc:
                _logger.warning("ReadoutBinding sync_from_calibration failed: %s", exc, exc_info=True)
                sync_ok = False

            tag = getattr(patch, "reason", None) or f"patch_{len(self._applied_patches)}"
            self._applied_patches.append(tag)

        return {
            "dry_run": dry_run,
            "n_updates": len(patch.updates),
            "preview": preview,
            "sync_ok": sync_ok if not dry_run else True,
        }

    def list_applied_patches(self) -> list[str]:
        """Return list of patch tags applied during this session."""
        return list(self._applied_patches)

    def persist_artifact(self, artifact: Artifact) -> Path:
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

        # Stamp experiment context if available
        ctx = getattr(self.session, "context", None)
        if ctx is not None:
            meta["experiment_context"] = ctx.to_dict()

        import numpy as np

        np.savez_compressed(data_path, **arrays)
        payload, dropped_meta = sanitize_mapping_for_json(meta)
        if dropped_meta:
            payload.setdefault("_persistence", {})["dropped_fields_meta"] = dropped_meta

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        return data_path

    def _artifact_from_result(self, name: str, run_result: Any) -> Artifact:
        out = getattr(run_result, "output", {})
        data = dict(out) if isinstance(out, (dict, Output)) else dict(out)
        meta = dict(getattr(run_result, "metadata", {}) or {})
        meta.setdefault("timestamp", datetime.now().isoformat())
        return Artifact(name=name, data=data, raw=None, meta=meta)

    def _run_result_from_artifact(self, artifact: Artifact):
        from ..hardware.program_runner import RunResult
        return RunResult(
            mode="hardware",
            output=Output(artifact.data),
            sim_samples=None,
            metadata=dict(artifact.meta),
        )

    def _set_calibration_path(self, dotted_path: str, value: Any) -> None:
        # Map common root categories to store mutators for explicit typing.
        parts = dotted_path.split(".")
        if len(parts) >= 3 and parts[0] == "frequencies":
            element, field = parts[1], parts[2]
            self.session.calibration.set_frequencies(element, **{field: value})
            return
        if len(parts) >= 3 and parts[0] == "coherence":
            element, field = parts[1], parts[2]
            self.session.calibration.set_coherence(element, **{field: value})
            return
        if len(parts) >= 3 and parts[0] == "pulse_calibrations":
            pulse_name, field = parts[1], parts[2]
            self.session.calibration.set_pulse_calibration(pulse_name, **{field: value})
            return
        if len(parts) >= 3 and parts[0] == "discrimination":
            element, field = parts[1], parts[2]
            self.session.calibration.set_discrimination(element, **{field: value})
            return
        if len(parts) >= 3 and parts[0] == "readout_quality":
            element, field = parts[1], parts[2]
            self.session.calibration.set_readout_quality(element, **{field: value})
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
