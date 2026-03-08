"""Helpers for decomposition and gate-sequence JSON artifacts."""
from __future__ import annotations

from dataclasses import asdict
import math
from typing import Any

from ..errors import ParsingError
from ..models.results import GateStep, SequenceMetadata, ValidationIssue
from .json_adapter import JsonAdapter

_SEQUENCE_KEYS = ("gates", "sequence", "steps", "operations", "ops")
_TYPE_KEYS = ("type", "gate", "op", "name")
_TARGET_KEYS = ("target", "targets", "element", "qubit", "mode")
_PARAM_KEYS = ("params", "parameters", "kwargs")


class DecompositionAdapter:
    def __init__(self, json_adapter: JsonAdapter) -> None:
        self.json_adapter = json_adapter

    def load_decomposition(self, path: str) -> dict[str, Any]:
        data = self.json_adapter.load_json(path)
        if not isinstance(data, dict):
            raise ParsingError("Decomposition artifact must be a JSON object", path=path)
        sequence = self._extract_sequence(data)
        return {
            "path": self.json_adapter.path_policy.display_path(self.json_adapter.path_policy.resolve_path(path, must_exist=True, allow_directory=False)),
            "top_level_keys": sorted(data.keys()),
            "sequence_length": len(sequence),
            "steps": [asdict(step) for step in sequence],
        }

    def summarize_gate_sequence(self, path: str) -> dict[str, Any]:
        sequence = self._extract_sequence(self.json_adapter.load_json(path))
        return {
            "path": self.json_adapter.path_policy.display_path(self.json_adapter.path_policy.resolve_path(path, must_exist=True, allow_directory=False)),
            "ordered_gates": [
                {
                    "index": step.index,
                    "gate_type": step.gate_type,
                    "target": step.target,
                    "params": step.params,
                }
                for step in sequence
            ],
            "summary": asdict(self.estimate_sequence_metadata(path)),
        }

    def flag_parameter_issues(self, path: str) -> list[ValidationIssue]:
        sequence = self._extract_sequence(self.json_adapter.load_json(path))
        issues: list[ValidationIssue] = []
        for step in sequence:
            if step.gate_type.lower() in {"sqr", "snap", "qubitrotation", "qubit_rotation"}:
                theta = step.params.get("theta")
                if isinstance(theta, (int, float)) and abs(theta) > math.pi + 1e-9:
                    issues.append(ValidationIssue(path=f"step[{step.index}].theta", message=f"Suspicious theta={theta} > pi", severity="warning"))
            if not step.gate_type or step.gate_type == "unknown":
                issues.append(ValidationIssue(path=f"step[{step.index}]", message="Missing gate type"))
            if not step.target:
                issues.append(ValidationIssue(path=f"step[{step.index}]", message="Missing target", severity="warning"))
            if any(key.endswith("vector") for key in step.params):
                for key, value in step.params.items():
                    if key.endswith("vector") and not isinstance(value, list):
                        issues.append(ValidationIssue(path=f"step[{step.index}].{key}", message="Parameter vector must be a list"))
        return issues

    def estimate_sequence_metadata(self, path: str) -> SequenceMetadata:
        sequence = self._extract_sequence(self.json_adapter.load_json(path))
        gate_types: dict[str, int] = {}
        targets: set[str] = set()
        parameter_keys: set[str] = set()
        suspicious_steps: list[int] = []
        for step in sequence:
            gate_types[step.gate_type] = gate_types.get(step.gate_type, 0) + 1
            if step.target:
                targets.add(str(step.target))
            parameter_keys.update(step.params.keys())
            theta = step.params.get("theta")
            if isinstance(theta, (int, float)) and abs(theta) > math.pi + 1e-9:
                suspicious_steps.append(step.index)
        return SequenceMetadata(
            path=self.json_adapter.path_policy.display_path(self.json_adapter.path_policy.resolve_path(path, must_exist=True, allow_directory=False)),
            total_steps=len(sequence),
            gate_types=gate_types,
            targets=sorted(targets),
            parameter_keys=sorted(parameter_keys),
            estimated_depth=len(sequence),
            suspicious_steps=suspicious_steps,
        )

    def _extract_sequence(self, data: Any) -> list[GateStep]:
        if isinstance(data, dict):
            for key in _SEQUENCE_KEYS:
                value = data.get(key)
                if isinstance(value, list):
                    return [self._normalize_step(idx, item) for idx, item in enumerate(value)]
        raise ParsingError("Could not locate a supported gate sequence list in JSON artifact")

    def _normalize_step(self, index: int, raw: Any) -> GateStep:
        if not isinstance(raw, dict):
            return GateStep(index=index, gate_type="unknown", target=None, raw={"value": raw})
        gate_type = next((str(raw[key]) for key in _TYPE_KEYS if key in raw and raw[key] is not None), "unknown")
        target_value = next((raw[key] for key in _TARGET_KEYS if key in raw and raw[key] is not None), None)
        target = ",".join(map(str, target_value)) if isinstance(target_value, list) else (str(target_value) if target_value is not None else None)
        params = next((raw[key] for key in _PARAM_KEYS if isinstance(raw.get(key), dict)), None)
        if params is None:
            params = {k: v for k, v in raw.items() if k not in {*_TYPE_KEYS, *_TARGET_KEYS, *_PARAM_KEYS}}
        return GateStep(index=index, gate_type=gate_type, target=target, params=params, raw=raw)
