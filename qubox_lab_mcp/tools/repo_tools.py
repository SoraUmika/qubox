"""Repository and code archaeology MCP tools."""
from __future__ import annotations

from typing import Any

from ..models.results import ComparisonSummary
from ..services import ServiceContainer


def register_repo_tools(mcp: Any, services: ServiceContainer) -> None:
    @mcp.tool()
    def read_file(path: str, start_line: int | None = None, end_line: int | None = None):
        """Safely read a text file snippet within allowed roots."""
        return services.filesystem.read_file(path, start_line=start_line, end_line=end_line)

    @mcp.tool()
    def search_repo(query: str, include_globs: list[str] | None = None, exclude_globs: list[str] | None = None):
        """Search code and text across allowed repository roots."""
        return services.filesystem.search_repo(query, include_globs=include_globs, exclude_globs=exclude_globs)

    @mcp.tool()
    def find_symbol(symbol_name: str):
        """Best-effort Python symbol lookup for functions, classes, and assigned names."""
        return services.python_index.find_symbol(symbol_name)

    @mcp.tool()
    def trace_references(symbol_name: str):
        """Trace best-effort symbol references across Python, notebooks, markdown, and JSON."""
        return services.python_index.trace_references(symbol_name)

    @mcp.tool()
    def list_directory(path: str, recursive: bool = False):
        """List a directory within allowed roots. Recursive listings are capped."""
        return services.filesystem.list_directory(path, recursive=recursive)

    @mcp.tool()
    def compare_python_implementations(path_a: str, path_b: str):
        """Compare module outlines for two Python implementations."""
        outline_a = services.python_index.extract_module_outline(path_a)
        outline_b = services.python_index.extract_module_outline(path_b)
        keys_a = set(outline_a)
        keys_b = set(outline_b)
        changed = []
        for key in sorted(keys_a & keys_b):
            if outline_a[key][0] != outline_b[key][0]:
                changed.append(key)
        return ComparisonSummary(
            path_a=services.path_policy.display_path(services.path_policy.resolve_path(path_a, must_exist=True, allow_directory=False)),
            path_b=services.path_policy.display_path(services.path_policy.resolve_path(path_b, must_exist=True, allow_directory=False)),
            shared_symbols=sorted(keys_a & keys_b),
            only_in_a=sorted(keys_a - keys_b),
            only_in_b=sorted(keys_b - keys_a),
            changed_signatures=changed,
        )

    @mcp.tool()
    def trace_gate_usage(gate_name: str):
        """Trace mentions of a gate name across code, notebooks, and docs."""
        query = gate_name.strip()
        return services.filesystem.search_repo(query, include_globs=["**/*.py", "**/*.ipynb", "**/*.md", "**/*.json"])

    @mcp.tool()
    def extract_experiment_entrypoints():
        """Find likely experiment entrypoints such as notebooks, scripts, and session bootstrap sites."""
        notebook_hits = services.filesystem.search_repo("SessionManager", include_globs=["**/*.ipynb", "**/*.py"])
        main_hits = services.filesystem.search_repo("__main__", include_globs=["**/*.py"])
        return {
            "session_manager_hits": notebook_hits.matches[:50],
            "main_blocks": main_hits.matches[:50],
        }

    @mcp.tool()
    def summarize_waveform_conventions(path: str):
        """Summarize likely waveform-related conventions from a source file."""
        snippet = services.filesystem.read_file(path, start_line=1, end_line=services.config.limits.max_read_lines)
        keywords = ["waveform", "amplitude", "sigma", "drag", "displacement", "theta", "duration"]
        relevant_lines = [line for line in snippet.content.splitlines() if any(key in line.lower() for key in keywords)]
        return {
            "path": snippet.path,
            "relevant_lines": relevant_lines[:80],
            "notes": [
                "This is a heuristic source summary, not a semantic proof.",
                "Use `trace_references()` or `find_symbol()` for follow-up archaeology.",
            ],
        }
