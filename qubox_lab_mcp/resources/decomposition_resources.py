"""Decomposition-oriented MCP resources."""
from __future__ import annotations

from typing import Any

from ..services import ServiceContainer


def register_decomposition_resources(mcp: Any, services: ServiceContainer) -> None:
    @mcp.resource("decomposition://file/{path}")
    def decomposition_resource(path: str):
        """Read a normalized decomposition artifact."""
        return services.decomposition.load_decomposition(path)
