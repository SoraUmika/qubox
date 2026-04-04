#!/usr/bin/env python3
"""
analyze_imports.py — Static import-graph analysis for the qubox codebase.

Walks every .py file under qubox/, uses the AST to extract import
statements, then builds a directed graph of module-level and package-level
dependencies.  Produces:

  1. JSON adjacency list   (docs/architecture/package_dependencies.json)
  2. Cycle report          (docs/architecture/cycle_report.json)
  3. Centrality metrics    (docs/architecture/centrality_metrics.json)

Run from the repo root:

    python tools/analyze_imports.py
"""
from __future__ import annotations

import ast
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "qubox"
OUT_DIR = REPO_ROOT / "docs" / "architecture"

# Packages to treat as top-level subsystems
SUBSYSTEM_PACKAGES = [
    "core", "hardware", "devices", "pulses", "programs", "experiments",
    "gates", "compile", "simulation", "analysis", "calibration",
    "optimization", "autotune", "verification", "gui", "tools",
    "examples", "tests", "compat", "migration",
]

# ---------------------------------------------------------------------------
# AST-based import extraction
# ---------------------------------------------------------------------------

def _collect_python_files(root: Path) -> list[Path]:
    """Return all .py files under *root*, skipping __pycache__ and tmp files."""
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__" and d != ".pytest_cache"]
        for fn in filenames:
            if fn.endswith(".py") and not fn.startswith("tmpclaude"):
                result.append(Path(dirpath) / fn)
    return sorted(result)


def _module_name(filepath: Path) -> str:
    """Convert a file path to a dotted module name relative to the repo root."""
    rel = filepath.relative_to(REPO_ROOT)
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _extract_imports(filepath: Path) -> list[str]:
    """Return a list of imported module names from a .py file."""
    try:
        source = filepath.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                # Resolve relative imports
                if node.level > 0:
                    # Relative import — resolve against current package
                    module_parts = _module_name(filepath).split(".")
                    # Go up `level` packages
                    base_parts = module_parts[:-(node.level)]
                    if node.module:
                        full = ".".join(base_parts) + "." + node.module
                    else:
                        full = ".".join(base_parts)
                    imports.append(full)
                else:
                    imports.append(node.module)
            elif node.level > 0:
                # from . import something
                module_parts = _module_name(filepath).split(".")
                base_parts = module_parts[:-(node.level)]
                imports.append(".".join(base_parts))
    return imports


def _to_subsystem(module_name: str) -> str | None:
    """Map a dotted module name to its qubox subsystem, or None."""
    if not module_name.startswith("qubox."):
        return None
    parts = module_name.split(".")
    if len(parts) < 2:
        return "qubox"
    subsys = parts[1]
    if subsys in SUBSYSTEM_PACKAGES:
        return subsys
    return None


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_module_graph() -> dict[str, dict]:
    """Build module-level and package-level dependency graphs.
    
    Returns dict with keys:
        module_edges: list of (src_module, dst_module)
        package_edges: list of (src_pkg, dst_pkg)
        module_to_pkg: dict mapping module -> pkg
        file_count_per_pkg: dict
        external_deps: set of external package names
    """
    py_files = _collect_python_files(PACKAGE_ROOT)
    
    module_edges: list[tuple[str, str]] = []
    package_edges_set: set[tuple[str, str]] = set()
    module_to_pkg: dict[str, str] = {}
    file_count: dict[str, int] = defaultdict(int)
    external_deps: set[str] = set()
    
    for fp in py_files:
        src_mod = _module_name(fp)
        src_pkg = _to_subsystem(src_mod)
        if src_pkg:
            module_to_pkg[src_mod] = src_pkg
            file_count[src_pkg] += 1
        
        for imp in _extract_imports(fp):
            dst_pkg = _to_subsystem(imp)
            
            if imp.startswith("qubox."):
                module_edges.append((src_mod, imp))
                if src_pkg and dst_pkg and src_pkg != dst_pkg:
                    package_edges_set.add((src_pkg, dst_pkg))
            elif not imp.startswith("qubox"):
                # External dependency
                top = imp.split(".")[0]
                external_deps.add(top)
    
    return {
        "module_edges": module_edges,
        "package_edges": sorted(package_edges_set),
        "module_to_pkg": module_to_pkg,
        "file_count_per_pkg": dict(file_count),
        "external_deps": sorted(external_deps),
    }


# ---------------------------------------------------------------------------
# Cycle detection (Tarjan-style DFS)
# ---------------------------------------------------------------------------

def find_cycles(edges: list[tuple[str, str]]) -> list[list[str]]:
    """Find all elementary cycles in a directed graph (Johnson's algorithm simplified)."""
    # Build adjacency list
    adj: dict[str, set[str]] = defaultdict(set)
    nodes: set[str] = set()
    for u, v in edges:
        adj[u].add(v)
        nodes.add(u)
        nodes.add(v)
    
    # Use simple DFS-based cycle detection
    cycles: list[list[str]] = []
    visited: set[str] = set()
    stack: list[str] = []
    on_stack: set[str] = set()
    
    def _dfs(node: str, target: str, depth: int = 0):
        if depth > 10:  # Limit cycle length
            return
        stack.append(node)
        on_stack.add(node)
        
        for neighbor in adj.get(node, set()):
            if neighbor == target and len(stack) > 1:
                cycles.append(list(stack))
            elif neighbor not in on_stack and neighbor not in visited:
                _dfs(neighbor, target, depth + 1)
        
        on_stack.remove(node)
        stack.pop()
    
    for node in sorted(nodes):
        _dfs(node, node)
        visited.add(node)
    
    # Deduplicate cycles (canonical form: start with min element)
    unique: list[tuple[str, ...]] = []
    for cycle in cycles:
        min_idx = cycle.index(min(cycle))
        canonical = tuple(cycle[min_idx:] + cycle[:min_idx])
        if canonical not in unique:
            unique.append(canonical)
    
    return [list(c) for c in unique]


# ---------------------------------------------------------------------------
# Centrality computation (no networkx needed)
# ---------------------------------------------------------------------------

def compute_centrality(edges: list[tuple[str, str]]) -> dict[str, dict]:
    """Compute in-degree, out-degree, and simple betweenness proxy."""
    in_deg: dict[str, int] = defaultdict(int)
    out_deg: dict[str, int] = defaultdict(int)
    nodes: set[str] = set()
    
    for u, v in edges:
        out_deg[u] += 1
        in_deg[v] += 1
        nodes.add(u)
        nodes.add(v)
    
    metrics = {}
    for n in sorted(nodes):
        metrics[n] = {
            "in_degree": in_deg.get(n, 0),
            "out_degree": out_deg.get(n, 0),
            "total_degree": in_deg.get(n, 0) + out_deg.get(n, 0),
        }
    return metrics


# ---------------------------------------------------------------------------
# Cross-layer violation detection
# ---------------------------------------------------------------------------

# Ideal layering: lower number = lower layer = should not depend on higher
LAYER_ORDER = {
    "core": 0,
    "pulses": 1,
    "gates": 2,
    "hardware": 3,
    "devices": 3,
    "compile": 4,
    "simulation": 4,
    "programs": 5,
    "calibration": 6,
    "analysis": 6,
    "optimization": 7,
    "experiments": 8,
    "autotune": 9,
    "verification": 9,
    "gui": 10,
    "tools": 10,
    "examples": 11,
    "tests": 11,
    "compat": 11,
    "migration": 11,
}

def detect_layer_violations(edges: list[tuple[str, str]]) -> list[dict]:
    """Detect edges where a lower-layer package depends on a higher-layer one."""
    violations = []
    for src, dst in edges:
        src_layer = LAYER_ORDER.get(src)
        dst_layer = LAYER_ORDER.get(dst)
        if src_layer is not None and dst_layer is not None:
            if src_layer < dst_layer:
                violations.append({
                    "from": src,
                    "to": dst,
                    "from_layer": src_layer,
                    "to_layer": dst_layer,
                    "severity": "warning" if (dst_layer - src_layer) <= 2 else "error",
                })
    return violations


# ---------------------------------------------------------------------------
# Module-level detail: which specific modules are most imported
# ---------------------------------------------------------------------------

def top_imported_modules(module_edges: list[tuple[str, str]], n: int = 15) -> list[tuple[str, int]]:
    """Top N modules by import count (in-degree at module level)."""
    counts: dict[str, int] = defaultdict(int)
    for _, dst in module_edges:
        counts[dst] += 1
    return sorted(counts.items(), key=lambda x: -x[1])[:n]


def top_importing_modules(module_edges: list[tuple[str, str]], n: int = 15) -> list[tuple[str, int]]:
    """Top N modules that import the most other modules (out-degree)."""
    counts: dict[str, int] = defaultdict(int)
    for src, _ in module_edges:
        counts[src] += 1
    return sorted(counts.items(), key=lambda x: -x[1])[:n]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("qubox Import Analysis")
    print("=" * 60)
    
    graph = build_module_graph()
    
    # --- Package-level analysis ---
    pkg_edges = graph["package_edges"]
    pkg_centrality = compute_centrality(pkg_edges)
    pkg_cycles = find_cycles(pkg_edges)
    layer_violations = detect_layer_violations(pkg_edges)
    
    # --- Module-level stats ---
    mod_edges = graph["module_edges"]
    top_imported = top_imported_modules(mod_edges)
    top_importing = top_importing_modules(mod_edges)
    
    # --- Print summary ---
    print(f"\nFiles analyzed per package:")
    for pkg, count in sorted(graph["file_count_per_pkg"].items()):
        print(f"  {pkg:20s}  {count} files")
    
    print(f"\nPackage-level edges ({len(pkg_edges)}):")
    for src, dst in pkg_edges:
        print(f"  {src:20s} -> {dst}")
    
    print(f"\nPackage centrality (sorted by total degree):")
    for pkg, m in sorted(pkg_centrality.items(), key=lambda x: -x[1]["total_degree"]):
        print(f"  {pkg:20s}  in={m['in_degree']:2d}  out={m['out_degree']:2d}  total={m['total_degree']:2d}")
    
    print(f"\nPackage-level cycles ({len(pkg_cycles)}):")
    for c in pkg_cycles:
        print(f"  {' -> '.join(c)} -> {c[0]}")
    
    print(f"\nLayer violations ({len(layer_violations)}):")
    for v in layer_violations:
        print(f"  [{v['severity'].upper():7s}] {v['from']} (layer {v['from_layer']}) -> {v['to']} (layer {v['to_layer']})")
    
    print(f"\nTop 15 most-imported modules:")
    for mod, count in top_imported:
        print(f"  {count:3d} imports <- {mod}")
    
    print(f"\nTop 15 modules importing the most:")
    for mod, count in top_importing:
        print(f"  {count:3d} imports -> from {mod}")
    
    print(f"\nExternal dependencies ({len(graph['external_deps'])}):")
    print(f"  {', '.join(graph['external_deps'])}")
    
    # --- Save JSON outputs ---
    with open(OUT_DIR / "package_dependencies.json", "w") as f:
        json.dump({
            "package_edges": pkg_edges,
            "file_count_per_pkg": graph["file_count_per_pkg"],
            "external_deps": graph["external_deps"],
        }, f, indent=2)
    
    with open(OUT_DIR / "cycle_report.json", "w") as f:
        json.dump({
            "package_cycles": [list(c) for c in pkg_cycles],
            "layer_violations": layer_violations,
        }, f, indent=2)
    
    with open(OUT_DIR / "centrality_metrics.json", "w") as f:
        json.dump({
            "package_centrality": pkg_centrality,
            "top_imported_modules": [[m, c] for m, c in top_imported],
            "top_importing_modules": [[m, c] for m, c in top_importing],
        }, f, indent=2)
    
    # --- Save module-level edges for the graph generator ---
    with open(OUT_DIR / "module_edges.json", "w") as f:
        json.dump({
            "module_edges": mod_edges,
            "module_to_pkg": graph["module_to_pkg"],
        }, f, indent=2)
    
    print(f"\nOutputs saved to {OUT_DIR}/")
    print("  package_dependencies.json")
    print("  cycle_report.json")
    print("  centrality_metrics.json")
    print("  module_edges.json")


if __name__ == "__main__":
    main()
