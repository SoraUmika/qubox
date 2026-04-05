"""Entry point for the qubox read-mostly MCP server."""
from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from typing import Any

from .config import ServerConfig, load_server_config
from .prompts import register_prompts
from .resources.decomposition_resources import register_decomposition_resources
from .resources.json_resources import register_json_resources
from .resources.notebook_resources import register_notebook_resources
from .resources.repo_resources import register_repo_resources
from .resources.run_resources import register_run_resources
from .services import build_services
from .tools.decomposition_tools import register_decomposition_tools
from .tools.json_tools import register_json_tools
from .tools.notebook_tools import register_notebook_tools
from .tools.repo_tools import register_repo_tools
from .tools.report_tools import register_report_tools
from .tools.run_tools import register_run_tools


def build_server(config: ServerConfig | None = None) -> Any:
    try:
        FastMCP = importlib.import_module("mcp.server.fastmcp").FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "The 'mcp' package is required to run qubox_lab_mcp. Install it with 'pip install \"mcp[cli]\"'."
        ) from exc

    config = config or load_server_config(Path.cwd())
    services = build_services(config)
    mcp = FastMCP(
        name="qubox_lab_mcp",
        instructions=(
            "Read-mostly MCP server for local qubox/cQED research workflows. "
            "Use resources for contextual artifacts and tools for structured inspection. "
            "Do not expect live hardware control or write actions."
        ),
        json_response=True,
    )

    register_repo_resources(mcp, services)
    register_notebook_resources(mcp, services)
    register_json_resources(mcp, services)
    register_decomposition_resources(mcp, services)
    register_run_resources(mcp, services)

    register_repo_tools(mcp, services)
    register_notebook_tools(mcp, services)
    register_json_tools(mcp, services)
    register_decomposition_tools(mcp, services)
    register_run_tools(mcp, services)
    register_report_tools(mcp, services)
    register_prompts(mcp)
    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the qubox read-mostly MCP server")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--root", action="append", default=None, help="Allowed root directory. Repeat for multiple roots.")
    args = parser.parse_args()

    config = load_server_config(Path.cwd())
    if args.root:
        config.allowed_roots = [Path(item).expanduser().resolve() for item in args.root]

    mcp = build_server(config)
    if args.transport == "streamable-http":
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        if args.host != "127.0.0.1":
            import logging
            logging.getLogger("qubox_lab_mcp").warning(
                "MCP HTTP server listening on %s:%d — ensure this is a trusted network.",
                args.host, args.port,
            )
        mcp.run(transport="streamable-http")
        return
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
