"""Filesystem adapter for safe read-only operations."""
from __future__ import annotations

import fnmatch
import itertools
import re
from pathlib import Path

from ..config import ServerConfig
from ..errors import LimitExceededError
from ..models.results import DirectoryEntry, FileSnippet, SearchMatch, SearchResult
from ..policies.path_policy import PathPolicy
from ..policies.safety_policy import SafetyPolicy


class FilesystemAdapter:
    def __init__(self, config: ServerConfig, path_policy: PathPolicy, safety_policy: SafetyPolicy) -> None:
        self.config = config
        self.path_policy = path_policy
        self.safety_policy = safety_policy

    def read_file(self, path: str, start_line: int | None = None, end_line: int | None = None) -> FileSnippet:
        resolved = self.path_policy.resolve_path(path, must_exist=True, allow_directory=False)
        self.safety_policy.ensure_size_allowed(resolved)
        self.safety_policy.reject_binary(resolved)

        text = resolved.read_text(encoding="utf-8")
        text = self.safety_policy.redact_text(text)
        lines = text.splitlines()
        total_lines = len(lines)
        start = max(start_line or 1, 1)
        end = min(end_line or min(total_lines, start + self.config.limits.max_read_lines - 1), total_lines)
        if end - start + 1 > self.config.limits.max_read_lines:
            end = start + self.config.limits.max_read_lines - 1
        selected = lines[start - 1:end]
        numbered = "\n".join(f"{idx}: {line}" for idx, line in enumerate(selected, start=start))
        return FileSnippet(
            path=self.path_policy.display_path(resolved),
            start_line=start,
            end_line=end,
            total_lines=total_lines,
            content=numbered,
            truncated=start > 1 or end < total_lines,
        )

    def list_directory(self, path: str, recursive: bool = False) -> list[DirectoryEntry]:
        resolved = self.path_policy.resolve_path(path, must_exist=True, allow_directory=True)
        if not resolved.is_dir():
            raise LimitExceededError("Path is not a directory", path=str(resolved))

        if recursive:
            entries = list(itertools.islice(self._walk_directory_entries(resolved), self.config.limits.max_list_entries + 1))
        else:
            children = sorted(resolved.iterdir(), key=lambda child: (not child.is_dir(), child.name.lower()))
            entries = [self._entry_from_path(child) for child in children[: self.config.limits.max_list_entries + 1]]

        if len(entries) > self.config.limits.max_list_entries:
            entries = entries[: self.config.limits.max_list_entries]
        return entries

    def search_repo(
        self,
        query: str,
        include_globs: list[str] | None = None,
        exclude_globs: list[str] | None = None,
        *,
        case_sensitive: bool = False,
        regex: bool = False,
    ) -> SearchResult:
        include_globs = include_globs or ["**/*"]
        exclude_globs = exclude_globs or []
        if not query.strip():
            raise LimitExceededError("Search query must not be empty")

        flags = 0 if case_sensitive else re.IGNORECASE
        matcher = re.compile(query if regex else re.escape(query), flags)
        matches: list[SearchMatch] = []
        total_matches = 0

        for file_path in self.iter_text_files(include_globs=include_globs, exclude_globs=exclude_globs):
            try:
                text = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            text = self.safety_policy.redact_text(text)
            file_hits = 0
            for line_no, line in enumerate(text.splitlines(), start=1):
                line_match = matcher.search(line)
                if not line_match:
                    continue
                total_matches += 1
                file_hits += 1
                if len(matches) < self.config.limits.max_search_results:
                    matches.append(
                        SearchMatch(
                            path=self.path_policy.display_path(file_path),
                            line=line_no,
                            column=line_match.start() + 1,
                            preview=line.strip(),
                        )
                    )
                if file_hits >= self.config.limits.max_matches_per_file:
                    break
            if total_matches >= self.config.limits.max_search_results:
                break

        return SearchResult(query=query, total_matches=total_matches, truncated=total_matches >= self.config.limits.max_search_results, matches=matches)

    def iter_text_files(
        self,
        *,
        include_globs: list[str] | None = None,
        exclude_globs: list[str] | None = None,
    ) -> list[Path]:
        include_globs = include_globs or ["**/*"]
        exclude_globs = exclude_globs or []
        results: list[Path] = []
        for root in self.config.allowed_roots:
            for file_path in root.rglob("*"):
                if len(results) >= self.config.limits.max_walk_files:
                    return results
                if not file_path.is_file():
                    continue
                rel = self.path_policy.display_path(file_path)
                if not any(fnmatch.fnmatch(rel, pattern) for pattern in include_globs):
                    continue
                if any(fnmatch.fnmatch(rel, pattern) for pattern in exclude_globs):
                    continue
                if any(part in self.config.excluded_names for part in file_path.parts):
                    continue
                try:
                    self.safety_policy.reject_binary(file_path)
                except Exception:
                    continue
                results.append(file_path)
        return results

    def _walk_directory_entries(self, root: Path) -> list[DirectoryEntry]:
        entries: list[DirectoryEntry] = []
        for item in root.rglob("*"):
            if any(part in self.config.excluded_names for part in item.parts):
                continue
            entries.append(self._entry_from_path(item))
        return entries

    def _entry_from_path(self, path: Path) -> DirectoryEntry:
        size = path.stat().st_size if path.is_file() else None
        return DirectoryEntry(
            path=self.path_policy.display_path(path),
            name=path.name,
            entry_type="directory" if path.is_dir() else "file",
            size_bytes=size,
        )
