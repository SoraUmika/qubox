"""Repository-oriented MCP resources."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..services import ServiceContainer


def register_repo_resources(mcp: Any, services: ServiceContainer) -> None:
    @mcp.resource("qubox://config")
    def server_config_resource():
        """Get server roots and safety limits."""
        return {
            "allowed_roots": [str(root) for root in services.config.allowed_roots],
            "excluded_names": sorted(services.config.excluded_names),
            "limits": asdict(services.config.limits),
        }

    @mcp.resource("qubox://survey")
    def workspace_survey_resource():
        """Get a compact survey of common qubox research locations."""
        sample_dirs = []
        try:
            sample_dirs = [entry.path for entry in services.filesystem.list_directory("samples", recursive=False)]
        except Exception:
            sample_dirs = []
        return {
            "repo_root": str(services.config.primary_root),
            "notebook_dirs": [entry.path for entry in services.filesystem.list_directory("notebooks", recursive=False)] if (services.config.primary_root / "notebooks").exists() else [],
            "sample_dirs": sample_dirs,
            "notes": [
                "Source code primarily lives under qubox/ (public API) and qubox_v2_legacy/ (runtime backend).",
                "Context-mode sample configs live under samples/<sample_id>/config.",
                "Cooldown-specific calibration and artifact data live under samples/<sample_id>/cooldowns/<cooldown_id>/.",
            ],
        }

    @mcp.resource("repo://file/{path}")
    def repo_file_resource(path: str):
        """Read a repository text file as a resource."""
        snippet = services.filesystem.read_file(path)
        return {
            "path": snippet.path,
            "start_line": snippet.start_line,
            "end_line": snippet.end_line,
            "content": snippet.content,
            "truncated": snippet.truncated,
        }
