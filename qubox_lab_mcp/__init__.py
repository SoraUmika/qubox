"""Read-mostly MCP server for qubox research workflows."""

from .config import ServerConfig, load_server_config

__all__ = ["ServerConfig", "load_server_config"]
