"""Calibration and config JSON MCP tools."""
from __future__ import annotations

from typing import Any

from ..services import ServiceContainer


def register_json_tools(mcp: Any, services: ServiceContainer) -> None:
    @mcp.tool()
    def load_json(path: str):
        """Load a JSON file under allowed roots."""
        return services.json.load_json(path)

    @mcp.tool()
    def compare_json_files(path_a: str, path_b: str):
        """Compare two JSON files and return a structured diff."""
        return services.json.compare_json_files(path_a, path_b, max_entries=services.config.limits.max_diff_entries)

    @mcp.tool()
    def summarize_calibration(path: str):
        """Summarize a calibration or cQED parameter JSON file."""
        return services.json.summarize_calibration(path)

    @mcp.tool()
    def validate_json_schema(path: str, schema_path: str | None = None):
        """Validate JSON against a supplied schema or a lightweight builtin heuristic."""
        return services.json.validate_json_schema(path, schema_path=schema_path)
