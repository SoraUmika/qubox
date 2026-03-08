"""Experiment run directory summarization."""
from __future__ import annotations

from pathlib import Path

from ..config import ServerConfig
from ..models.results import DirectoryEntry, RunDirectorySummary
from ..policies.path_policy import PathPolicy


class RunAdapter:
    def __init__(self, config: ServerConfig, path_policy: PathPolicy) -> None:
        self.config = config
        self.path_policy = path_policy

    def summarize_run_directory(self, path: str) -> RunDirectorySummary:
        resolved = self.path_policy.resolve_path(path, must_exist=True, allow_directory=True)
        if not resolved.is_dir():
            raise ValueError("Run summary expects a directory path")
        total_files = 0
        figures: list[str] = []
        results: list[str] = []
        notebooks: list[str] = []
        logs: list[str] = []
        for item in resolved.rglob("*"):
            if any(part in self.config.excluded_names for part in item.parts):
                continue
            if not item.is_file():
                continue
            total_files += 1
            rel = self.path_policy.display_path(item)
            suffix = item.suffix.lower()
            if suffix in self.config.figure_extensions:
                figures.append(rel)
            if suffix in self.config.result_extensions:
                results.append(rel)
            if suffix == ".ipynb":
                notebooks.append(rel)
            if suffix in {".log", ".out", ".err", ".txt"}:
                logs.append(rel)
            if total_files >= self.config.limits.max_walk_files:
                break
        top_level_entries = [
            DirectoryEntry(
                path=self.path_policy.display_path(child),
                name=child.name,
                entry_type="directory" if child.is_dir() else "file",
                size_bytes=child.stat().st_size if child.is_file() else None,
            )
            for child in sorted(resolved.iterdir(), key=lambda child: (not child.is_dir(), child.name.lower()))[:25]
        ]
        return RunDirectorySummary(
            path=self.path_policy.display_path(resolved),
            total_files=total_files,
            figure_files=figures[:100],
            result_files=results[:150],
            notebooks=notebooks[:50],
            logs=logs[:50],
            top_level_entries=top_level_entries,
        )

    def list_generated_figures(self, path: str) -> list[str]:
        return self.summarize_run_directory(path).figure_files

    def find_result_files(self, path: str) -> list[str]:
        return self.summarize_run_directory(path).result_files
