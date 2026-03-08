"""Reusable prompt templates exposed by the MCP server."""
from __future__ import annotations

from typing import Any


def register_prompts(mcp: Any) -> None:
    @mcp.prompt(title="Trace gate usage")
    def trace_gate_usage_prompt(gate_name: str) -> str:
        return (
            f"Trace the implementation and usage of the gate '{gate_name}'. "
            "Use repository search, symbol lookup, and notebook archaeology. "
            "Summarize likely breakpoints for refactors, notebook compatibility risks, and any calibration or waveform conventions involved."
        )

    @mcp.prompt(title="Compare calibrations")
    def compare_calibrations_prompt(path_a: str, path_b: str, focus_keys: str = "chi, chi2, Kerr, pulse references") -> str:
        return (
            f"Compare calibration/config JSON files at {path_a} and {path_b}. "
            f"Focus on {focus_keys}. Highlight changed keys, likely physical meaning, and any downstream experiment or notebook impact."
        )

    @mcp.prompt(title="Notebook archaeology")
    def notebook_archaeology_prompt(path: str, topic: str) -> str:
        return (
            f"Inspect notebook {path}. Find cells related to '{topic}', preserve execution order, and summarize the workflow, "
            "dependencies, experiment entrypoints, and legacy API assumptions."
        )
