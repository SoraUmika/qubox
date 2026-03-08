"""Notebook-oriented MCP resources."""
from __future__ import annotations

from typing import Any

from ..services import ServiceContainer


def register_notebook_resources(mcp: Any, services: ServiceContainer) -> None:
    @mcp.resource("notebook://file/{path}")
    def notebook_resource(path: str):
        """Read a notebook summary resource."""
        return services.notebook.read_notebook(path)
