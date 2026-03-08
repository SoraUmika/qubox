"""Experiment artifact directory MCP tools."""
from __future__ import annotations

from typing import Any

from ..services import ServiceContainer


def register_run_tools(mcp: Any, services: ServiceContainer) -> None:
    @mcp.tool()
    def summarize_run_directory(path: str):
        """Summarize the contents of an experiment output directory."""
        return services.run.summarize_run_directory(path)

    @mcp.tool()
    def list_generated_figures(path: str):
        """List figure files under a run directory."""
        return services.run.list_generated_figures(path)

    @mcp.tool()
    def find_result_files(path: str):
        """Find likely result files under a run directory."""
        return services.run.find_result_files(path)
