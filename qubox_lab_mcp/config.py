"""Configuration for the qubox MCP server."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class ServerLimits:
    max_file_bytes: int = 16_000_000
    max_read_lines: int = 400
    max_list_entries: int = 200
    max_search_results: int = 100
    max_matches_per_file: int = 20
    max_resource_chars: int = 120_000
    max_notebook_cells: int = 400
    max_cell_chars: int = 12_000
    max_diff_entries: int = 200
    max_walk_files: int = 5_000


@dataclass(slots=True)
class ServerConfig:
    allowed_roots: list[Path]
    excluded_names: set[str] = field(
        default_factory=lambda: {
            ".git",
            ".venv",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "node_modules",
        }
    )
    text_extensions: set[str] = field(
        default_factory=lambda: {
            ".py",
            ".md",
            ".txt",
            ".json",
            ".toml",
            ".yaml",
            ".yml",
            ".ini",
            ".cfg",
            ".ipynb",
            ".csv",
            ".tsv",
            ".rst",
        }
    )
    figure_extensions: set[str] = field(
        default_factory=lambda: {".png", ".pdf", ".svg", ".jpg", ".jpeg", ".gif"}
    )
    result_extensions: set[str] = field(
        default_factory=lambda: {".json", ".csv", ".tsv", ".npz", ".npy", ".h5", ".hdf5", ".txt", ".log", ".ipynb"}
    )
    secret_key_markers: tuple[str, ...] = (
        "token",
        "secret",
        "password",
        "passwd",
        "api_key",
        "apikey",
        "access_key",
        "private_key",
    )
    limits: ServerLimits = field(default_factory=ServerLimits)

    @property
    def primary_root(self) -> Path:
        return self.allowed_roots[0]


def _parse_roots(value: str | None, default_root: Path) -> list[Path]:
    if not value:
        return [default_root.resolve()]
    roots = []
    for item in value.replace(";", os.pathsep).split(os.pathsep):
        item = item.strip()
        if not item:
            continue
        roots.append(Path(item).expanduser().resolve())
    return roots or [default_root.resolve()]


def load_server_config(base_dir: str | Path | None = None) -> ServerConfig:
    root = Path(base_dir or Path.cwd()).resolve()
    allowed_roots = _parse_roots(os.getenv("QUBOX_MCP_ROOTS"), root)
    limits = ServerLimits(
        max_file_bytes=int(os.getenv("QUBOX_MCP_MAX_FILE_BYTES", "16000000")),
        max_read_lines=int(os.getenv("QUBOX_MCP_MAX_READ_LINES", "400")),
        max_list_entries=int(os.getenv("QUBOX_MCP_MAX_LIST_ENTRIES", "200")),
        max_search_results=int(os.getenv("QUBOX_MCP_MAX_SEARCH_RESULTS", "100")),
        max_matches_per_file=int(os.getenv("QUBOX_MCP_MAX_MATCHES_PER_FILE", "20")),
        max_resource_chars=int(os.getenv("QUBOX_MCP_MAX_RESOURCE_CHARS", "120000")),
        max_notebook_cells=int(os.getenv("QUBOX_MCP_MAX_NOTEBOOK_CELLS", "400")),
        max_cell_chars=int(os.getenv("QUBOX_MCP_MAX_CELL_CHARS", "12000")),
        max_diff_entries=int(os.getenv("QUBOX_MCP_MAX_DIFF_ENTRIES", "200")),
        max_walk_files=int(os.getenv("QUBOX_MCP_MAX_WALK_FILES", "5000")),
    )
    return ServerConfig(allowed_roots=allowed_roots, limits=limits)
