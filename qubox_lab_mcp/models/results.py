"""Structured result models used by tools and resources."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DirectoryEntry:
    path: str
    name: str
    entry_type: str
    size_bytes: int | None = None


@dataclass(slots=True)
class FileSnippet:
    path: str
    start_line: int
    end_line: int
    total_lines: int
    content: str
    truncated: bool = False


@dataclass(slots=True)
class SearchMatch:
    path: str
    line: int
    column: int
    preview: str


@dataclass(slots=True)
class SearchResult:
    query: str
    total_matches: int
    truncated: bool
    matches: list[SearchMatch] = field(default_factory=list)


@dataclass(slots=True)
class SymbolMatch:
    symbol: str
    kind: str
    path: str
    line: int
    signature: str | None = None
    context: str | None = None


@dataclass(slots=True)
class NotebookCellSummary:
    index: int
    cell_type: str
    execution_count: int | None
    preview: str
    source: str | None = None


@dataclass(slots=True)
class NotebookSummary:
    path: str
    cell_count: int
    code_cells: int
    markdown_cells: int
    headings: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    cells: list[NotebookCellSummary] = field(default_factory=list)


@dataclass(slots=True)
class JsonDiffEntry:
    path: str
    change_type: str
    left: Any = None
    right: Any = None


@dataclass(slots=True)
class JsonDiffResult:
    path_a: str
    path_b: str
    total_changes: int
    truncated: bool
    changes: list[JsonDiffEntry] = field(default_factory=list)


@dataclass(slots=True)
class ValidationIssue:
    path: str
    message: str
    severity: str = "error"


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    schema_source: str | None
    issues: list[ValidationIssue] = field(default_factory=list)


@dataclass(slots=True)
class GateStep:
    index: int
    gate_type: str
    target: str | None
    params: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SequenceMetadata:
    path: str
    total_steps: int
    gate_types: dict[str, int]
    targets: list[str]
    parameter_keys: list[str]
    estimated_depth: int
    suspicious_steps: list[int] = field(default_factory=list)


@dataclass(slots=True)
class RunDirectorySummary:
    path: str
    total_files: int
    figure_files: list[str] = field(default_factory=list)
    result_files: list[str] = field(default_factory=list)
    notebooks: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    top_level_entries: list[DirectoryEntry] = field(default_factory=list)


@dataclass(slots=True)
class ComparisonSummary:
    path_a: str
    path_b: str
    shared_symbols: list[str] = field(default_factory=list)
    only_in_a: list[str] = field(default_factory=list)
    only_in_b: list[str] = field(default_factory=list)
    changed_signatures: list[str] = field(default_factory=list)
