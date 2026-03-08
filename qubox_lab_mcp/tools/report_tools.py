"""Higher-level report helpers for research refactors and analysis."""
from __future__ import annotations

from typing import Any

from ..services import ServiceContainer


def register_report_tools(mcp: Any, services: ServiceContainer) -> None:
    @mcp.tool()
    def generate_refactor_report(symbol_name: str):
        """Generate a concise archaeology report around a symbol or convention."""
        definitions = services.python_index.find_symbol(symbol_name)
        references = services.python_index.trace_references(symbol_name)
        return {
            "symbol": symbol_name,
            "definitions": definitions,
            "reference_count": references.total_matches,
            "references": references.matches[:50],
            "notes": [
                "This is a static report generated from read-only repository inspection.",
                "Notebook compatibility still needs human review for semantic behavior changes.",
            ],
        }
