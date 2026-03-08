"""Notebook parsing and summarization helpers."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..errors import ParsingError
from ..models.results import NotebookCellSummary, NotebookSummary
from ..policies.path_policy import PathPolicy
from ..policies.safety_policy import SafetyPolicy


class NotebookAdapter:
    def __init__(self, path_policy: PathPolicy, safety_policy: SafetyPolicy) -> None:
        self.path_policy = path_policy
        self.safety_policy = safety_policy

    def load_notebook(self, path: str) -> tuple[Path, dict[str, Any]]:
        resolved = self.path_policy.resolve_path(path, must_exist=True, allow_directory=False)
        if resolved.suffix.lower() != ".ipynb":
            raise ParsingError("Unsupported notebook type", path=str(resolved))
        self.safety_policy.ensure_size_allowed(resolved)
        try:
            data = json.loads(resolved.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ParsingError("Failed to parse notebook JSON", path=str(resolved), error=str(exc)) from exc
        if not isinstance(data, dict) or "cells" not in data:
            raise ParsingError("Notebook JSON missing 'cells'", path=str(resolved))
        return resolved, data

    def read_notebook(self, path: str, include_source: bool = False) -> NotebookSummary:
        resolved, data = self.load_notebook(path)
        headings: list[str] = []
        imports: set[str] = set()
        cells: list[NotebookCellSummary] = []
        code_cells = 0
        markdown_cells = 0

        for idx, cell in enumerate(data.get("cells", []), start=1):
            cell_type = str(cell.get("cell_type", "unknown"))
            source = self._source_text(cell)
            preview = self._preview(source)
            if cell_type == "markdown":
                markdown_cells += 1
                headings.extend(self._extract_headings(source))
            elif cell_type == "code":
                code_cells += 1
                imports.update(self._extract_imports(source))
            cells.append(
                NotebookCellSummary(
                    index=idx,
                    cell_type=cell_type,
                    execution_count=cell.get("execution_count"),
                    preview=preview,
                    source=source if include_source else None,
                )
            )

        return NotebookSummary(
            path=self.path_policy.display_path(resolved),
            cell_count=len(cells),
            code_cells=code_cells,
            markdown_cells=markdown_cells,
            headings=headings[:50],
            imports=sorted(imports)[:100],
            cells=cells[: self.safety_policy.config.limits.max_notebook_cells],
        )

    def find_cells(self, path: str, pattern: str) -> list[NotebookCellSummary]:
        _, data = self.load_notebook(path)
        regex = re.compile(pattern, re.IGNORECASE)
        results: list[NotebookCellSummary] = []
        for idx, cell in enumerate(data.get("cells", []), start=1):
            source = self._source_text(cell)
            if regex.search(source):
                results.append(
                    NotebookCellSummary(
                        index=idx,
                        cell_type=str(cell.get("cell_type", "unknown")),
                        execution_count=cell.get("execution_count"),
                        preview=self._preview(source),
                        source=source,
                    )
                )
        return results

    def extract_cell(self, path: str, cell_index: int) -> NotebookCellSummary:
        _, data = self.load_notebook(path)
        cells = data.get("cells", [])
        if cell_index < 1 or cell_index > len(cells):
            raise ParsingError("Notebook cell index out of range", cell_index=cell_index, total_cells=len(cells))
        cell = cells[cell_index - 1]
        source = self._source_text(cell)
        return NotebookCellSummary(
            index=cell_index,
            cell_type=str(cell.get("cell_type", "unknown")),
            execution_count=cell.get("execution_count"),
            preview=self._preview(source),
            source=source,
        )

    def summarize_workflow(self, path: str) -> dict[str, Any]:
        summary = self.read_notebook(path, include_source=True)
        experiment_mentions: list[str] = []
        workflow_steps: list[str] = []
        for cell in summary.cells:
            source = cell.source or ""
            if cell.cell_type == "markdown":
                workflow_steps.extend(self._extract_headings(source))
            elif cell.cell_type == "code":
                experiment_mentions.extend(re.findall(r"\b([A-Z][A-Za-z0-9_]+)\s*\(", source))
        return {
            "path": summary.path,
            "cell_count": summary.cell_count,
            "headings": summary.headings,
            "imports": summary.imports,
            "workflow_steps": workflow_steps[:30],
            "experiment_mentions": sorted({name for name in experiment_mentions if len(name) > 2})[:50],
            "notes": [
                f"Notebook has {summary.code_cells} code cells and {summary.markdown_cells} markdown cells.",
                "Execution order is represented by cell index and execution_count when present.",
            ],
        }

    @staticmethod
    def _source_text(cell: dict[str, Any]) -> str:
        source = cell.get("source", [])
        if isinstance(source, list):
            return "".join(source)
        return str(source)

    @staticmethod
    def _preview(text: str) -> str:
        compact = " ".join(line.strip() for line in text.splitlines() if line.strip())
        return compact[:240]

    @staticmethod
    def _extract_headings(text: str) -> list[str]:
        return [line.lstrip("# ").strip() for line in text.splitlines() if line.strip().startswith("#")]

    @staticmethod
    def _extract_imports(text: str) -> list[str]:
        imports: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("import "):
                imports.extend(part.strip() for part in line[7:].split(","))
            elif line.startswith("from "):
                imports.append(line.split()[1])
        return imports
