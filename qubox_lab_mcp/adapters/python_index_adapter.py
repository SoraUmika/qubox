"""Best-effort Python symbol indexing for repository archaeology."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable

from ..models.results import SearchResult, SymbolMatch
from .filesystem_adapter import FilesystemAdapter


class PythonIndexAdapter:
    def __init__(self, filesystem: FilesystemAdapter) -> None:
        self.filesystem = filesystem

    def find_symbol(self, symbol_name: str) -> list[SymbolMatch]:
        matches: list[SymbolMatch] = []
        for path in self._python_files():
            try:
                source = path.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except (UnicodeDecodeError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol_name:
                    matches.append(
                        SymbolMatch(
                            symbol=symbol_name,
                            kind=self._kind(node),
                            path=self.filesystem.path_policy.display_path(path),
                            line=node.lineno,
                            signature=self._signature(source, node),
                            context=ast.get_docstring(node),
                        )
                    )
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == symbol_name:
                            matches.append(
                                SymbolMatch(
                                    symbol=symbol_name,
                                    kind="variable",
                                    path=self.filesystem.path_policy.display_path(path),
                                    line=node.lineno,
                                    signature=target.id,
                                )
                            )
        return matches

    def trace_references(self, symbol_name: str) -> SearchResult:
        boundary = rf"\b{re.escape(symbol_name)}\b"
        return self.filesystem.search_repo(boundary, include_globs=["**/*.py", "**/*.ipynb", "**/*.md", "**/*.json"], regex=True)

    def extract_module_outline(self, path: str) -> dict[str, tuple[str, int]]:
        resolved = self.filesystem.path_policy.resolve_path(path, must_exist=True, allow_directory=False)
        source = resolved.read_text(encoding="utf-8")
        tree = ast.parse(source)
        outline: dict[str, tuple[str, int]] = {}
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                outline[f"class:{node.name}"] = (self._signature(source, node), node.lineno)
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        outline[f"method:{node.name}.{sub.name}"] = (self._signature(source, sub), sub.lineno)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                outline[f"function:{node.name}"] = (self._signature(source, node), node.lineno)
        return outline

    def _python_files(self) -> Iterable[Path]:
        return self.filesystem.iter_text_files(include_globs=["**/*.py"], exclude_globs=[])

    @staticmethod
    def _kind(node: ast.AST) -> str:
        if isinstance(node, ast.ClassDef):
            return "class"
        if isinstance(node, ast.AsyncFunctionDef):
            return "async_function"
        return "function"

    @staticmethod
    def _signature(source: str, node: ast.AST) -> str:
        try:
            return ast.get_source_segment(source, node).splitlines()[0].strip()
        except Exception:
            if hasattr(node, "name"):
                return str(getattr(node, "name"))
            return "<unknown>"
