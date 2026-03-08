"""Experiment artifact MCP resources."""
from __future__ import annotations

from typing import Any

from ..services import ServiceContainer


def register_run_resources(mcp: Any, services: ServiceContainer) -> None:
    @mcp.resource("run://summary/{path}")
    def run_summary_resource(path: str):
        """Read a run-directory summary resource."""
        return services.run.summarize_run_directory(path)
