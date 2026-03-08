"""Decomposition and gate artifact MCP tools."""
from __future__ import annotations

from typing import Any

from ..services import ServiceContainer


def register_decomposition_tools(mcp: Any, services: ServiceContainer) -> None:
    @mcp.tool()
    def load_decomposition(path: str):
        """Load a decomposition-style JSON artifact and normalize the step list."""
        return services.decomposition.load_decomposition(path)

    @mcp.tool()
    def summarize_gate_sequence(path: str):
        """Summarize the ordered gate sequence from a decomposition artifact."""
        return services.decomposition.summarize_gate_sequence(path)

    @mcp.tool()
    def flag_parameter_issues(path: str):
        """Flag suspicious or malformed gate parameters in a decomposition artifact."""
        return services.decomposition.flag_parameter_issues(path)

    @mcp.tool()
    def estimate_sequence_metadata(path: str):
        """Estimate counts, targets, and simple metadata for a gate sequence."""
        return services.decomposition.estimate_sequence_metadata(path)
