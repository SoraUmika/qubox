"""Notebook archaeology MCP tools."""
from __future__ import annotations

from typing import Any

from ..services import ServiceContainer


def register_notebook_tools(mcp: Any, services: ServiceContainer) -> None:
    @mcp.tool()
    def read_notebook(path: str):
        """Read and summarize a notebook, preserving cell order and types."""
        return services.notebook.read_notebook(path)

    @mcp.tool()
    def find_notebook_cells(path: str, pattern: str):
        """Find notebook cells whose source matches the supplied regex pattern."""
        return services.notebook.find_cells(path, pattern)

    @mcp.tool()
    def extract_notebook_cell(path: str, cell_index: int):
        """Extract a single notebook cell by 1-based index."""
        return services.notebook.extract_cell(path, cell_index)

    @mcp.tool()
    def summarize_notebook_workflow(path: str):
        """Summarize headings, imports, and likely workflow stages in a notebook."""
        return services.notebook.summarize_workflow(path)
