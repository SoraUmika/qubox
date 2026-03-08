"""JSON loading, diffing, summarization, and lightweight schema validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..errors import ParsingError
from ..models.results import JsonDiffEntry, JsonDiffResult, ValidationIssue, ValidationResult
from ..policies.path_policy import PathPolicy
from ..policies.safety_policy import SafetyPolicy


class JsonAdapter:
    def __init__(self, path_policy: PathPolicy, safety_policy: SafetyPolicy) -> None:
        self.path_policy = path_policy
        self.safety_policy = safety_policy

    def load_json(self, path: str) -> dict[str, Any] | list[Any]:
        resolved = self.path_policy.resolve_path(path, must_exist=True, allow_directory=False)
        self.safety_policy.ensure_size_allowed(resolved)
        try:
            return json.loads(resolved.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ParsingError("Malformed JSON", path=str(resolved), error=str(exc)) from exc

    def compare_json_files(self, path_a: str, path_b: str, max_entries: int = 200) -> JsonDiffResult:
        left = self.load_json(path_a)
        right = self.load_json(path_b)
        changes: list[JsonDiffEntry] = []
        self._diff_values(left, right, path="", out=changes, max_entries=max_entries)
        return JsonDiffResult(
            path_a=self.path_policy.display_path(self.path_policy.resolve_path(path_a, must_exist=True, allow_directory=False)),
            path_b=self.path_policy.display_path(self.path_policy.resolve_path(path_b, must_exist=True, allow_directory=False)),
            total_changes=len(changes),
            truncated=len(changes) >= max_entries,
            changes=changes[:max_entries],
        )

    def summarize_calibration(self, path: str) -> dict[str, Any]:
        data = self.load_json(path)
        if not isinstance(data, dict):
            raise ParsingError("Calibration summary expects a JSON object", path=path)
        cqed = data.get("cqed_params", {})
        pulse_calibrations = data.get("pulse_calibrations", {})
        frequencies = data.get("frequencies", {})
        summary_keys = [
            "chi",
            "chi2",
            "kerr",
            "Kerr",
            "resonator_freq",
            "qubit_freq",
        ]
        highlights = self._collect_interesting_scalars(data, summary_keys)
        return {
            "path": self.path_policy.display_path(self.path_policy.resolve_path(path, must_exist=True, allow_directory=False)),
            "version": data.get("version") or data.get("schema_version"),
            "context": data.get("context"),
            "cqed_params_keys": sorted(cqed.keys()) if isinstance(cqed, dict) else [],
            "pulse_calibration_count": len(pulse_calibrations) if isinstance(pulse_calibrations, dict) else 0,
            "frequency_keys": sorted(frequencies.keys()) if isinstance(frequencies, dict) else [],
            "highlights": highlights,
        }

    def validate_json_schema(self, path: str, schema_path: str | None = None) -> ValidationResult:
        instance = self.load_json(path)
        schema_source = None
        if schema_path:
            schema = self.load_json(schema_path)
            schema_source = self.path_policy.display_path(self.path_policy.resolve_path(schema_path, must_exist=True, allow_directory=False))
            issues = self._validate_against_schema(instance, schema, path="$")
            return ValidationResult(valid=not issues, schema_source=schema_source, issues=issues)

        issues = self._heuristic_validate(path, instance)
        return ValidationResult(valid=not issues, schema_source="heuristic", issues=issues)

    def _diff_values(self, left: Any, right: Any, *, path: str, out: list[JsonDiffEntry], max_entries: int) -> None:
        if len(out) >= max_entries:
            return
        if type(left) is not type(right):
            out.append(JsonDiffEntry(path=path or "$", change_type="type_changed", left=left, right=right))
            return
        if isinstance(left, dict):
            keys = set(left) | set(right)
            for key in sorted(keys):
                if len(out) >= max_entries:
                    return
                child_path = f"{path}.{key}" if path else key
                if key not in left:
                    out.append(JsonDiffEntry(path=child_path, change_type="added", right=right[key]))
                elif key not in right:
                    out.append(JsonDiffEntry(path=child_path, change_type="removed", left=left[key]))
                else:
                    self._diff_values(left[key], right[key], path=child_path, out=out, max_entries=max_entries)
            return
        if isinstance(left, list):
            if left != right:
                max_len = max(len(left), len(right))
                for idx in range(max_len):
                    if len(out) >= max_entries:
                        return
                    child_path = f"{path}[{idx}]"
                    if idx >= len(left):
                        out.append(JsonDiffEntry(path=child_path, change_type="added", right=right[idx]))
                    elif idx >= len(right):
                        out.append(JsonDiffEntry(path=child_path, change_type="removed", left=left[idx]))
                    else:
                        self._diff_values(left[idx], right[idx], path=child_path, out=out, max_entries=max_entries)
            return
        if left != right:
            out.append(JsonDiffEntry(path=path or "$", change_type="changed", left=left, right=right))

    def _collect_interesting_scalars(self, data: Any, keys_of_interest: list[str], prefix: str = "") -> dict[str, Any]:
        found: dict[str, Any] = {}
        if isinstance(data, dict):
            for key, value in data.items():
                child_prefix = f"{prefix}.{key}" if prefix else key
                if key in keys_of_interest and not isinstance(value, (dict, list)):
                    found[child_prefix] = value
                found.update(self._collect_interesting_scalars(value, keys_of_interest, child_prefix))
        elif isinstance(data, list):
            for idx, item in enumerate(data):
                found.update(self._collect_interesting_scalars(item, keys_of_interest, f"{prefix}[{idx}]"))
        return found

    def _validate_against_schema(self, instance: Any, schema: Any, *, path: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if not isinstance(schema, dict):
            return issues
        schema_type = schema.get("type")
        if schema_type and not self._matches_type(instance, schema_type):
            issues.append(ValidationIssue(path=path, message=f"Expected type {schema_type}, got {type(instance).__name__}"))
            return issues

        if schema_type == "object":
            required = schema.get("required", [])
            properties = schema.get("properties", {})
            if isinstance(instance, dict):
                for key in required:
                    if key not in instance:
                        issues.append(ValidationIssue(path=f"{path}.{key}", message="Missing required key"))
                for key, subschema in properties.items():
                    if key in instance:
                        issues.extend(self._validate_against_schema(instance[key], subschema, path=f"{path}.{key}"))
        elif schema_type == "array" and isinstance(instance, list) and "items" in schema:
            for idx, item in enumerate(instance):
                issues.extend(self._validate_against_schema(item, schema["items"], path=f"{path}[{idx}]"))
        return issues

    @staticmethod
    def _matches_type(value: Any, schema_type: str) -> bool:
        mapping = {
            "object": dict,
            "array": list,
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "null": type(None),
        }
        expected = mapping.get(schema_type)
        return isinstance(value, expected) if expected else True

    def _heuristic_validate(self, path: str, instance: Any) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        file_name = Path(path).name.lower()
        if not isinstance(instance, dict):
            issues.append(ValidationIssue(path="$", message="Top-level JSON value should be an object for qubox configs"))
            return issues
        if file_name == "calibration.json":
            for key in ("version", "cqed_params", "pulse_calibrations"):
                if key not in instance:
                    issues.append(ValidationIssue(path=f"$.{key}", message="Missing expected calibration key", severity="warning"))
        if file_name == "hardware.json" and "elements" not in instance:
            issues.append(ValidationIssue(path="$.elements", message="Missing expected hardware elements mapping", severity="warning"))
        return issues
