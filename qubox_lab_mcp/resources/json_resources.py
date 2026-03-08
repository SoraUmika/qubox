"""JSON and calibration-oriented MCP resources."""
from __future__ import annotations

from typing import Any

from ..services import ServiceContainer


def register_json_resources(mcp: Any, services: ServiceContainer) -> None:
    @mcp.resource("json://file/{path}")
    def json_resource(path: str):
        """Read a JSON file as a resource."""
        return services.json.load_json(path)
