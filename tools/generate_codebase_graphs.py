#!/usr/bin/env python3
"""
generate_codebase_graphs.py — Generate architecture diagrams for qubox.

Reads the JSON outputs from analyze_imports.py and produces four SVG
diagrams directly (no Graphviz binary needed):

  B1. docs/architecture/package_dependency_graph.svg
  B2. docs/architecture/workflow_dependency_graph.svg
  B3. docs/architecture/class_relationships.svg
  B4. docs/architecture/experiment_flow.svg

Run from the repo root:

    python tools/generate_codebase_graphs.py
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "docs" / "architecture"
OUT_DIR = DATA_DIR

# ===================================================================
# SVG Helper Utilities
# ===================================================================

def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _svg_header(width: int, height: int, *, title: str = "") -> str:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="Segoe UI, Helvetica, Arial, sans-serif">\n'
        f'  <style>\n'
        f'    text {{ font-size: 13px; fill: #222; }}\n'
        f'    .title {{ font-size: 18px; font-weight: bold; fill: #111; }}\n'
        f'    .subtitle {{ font-size: 12px; fill: #666; }}\n'
        f'    .node-label {{ font-size: 12px; fill: #fff; font-weight: 600; text-anchor: middle; dominant-baseline: central; }}\n'
        f'    .node-label-dark {{ font-size: 12px; fill: #222; font-weight: 600; text-anchor: middle; dominant-baseline: central; }}\n'
        f'    .small-label {{ font-size: 10px; fill: #555; text-anchor: middle; dominant-baseline: central; }}\n'
        f'    .edge {{ stroke-width: 1.5; fill: none; }}\n'
        f'    .edge-cycle {{ stroke-width: 2; fill: none; stroke-dasharray: 6,3; }}\n'
        f'    .metric {{ font-size: 10px; fill: #888; text-anchor: middle; }}\n'
        f'  </style>\n'
        f'  <defs>\n'
        f'    <marker id="arrow" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="8" markerHeight="6" orient="auto">\n'
        f'      <path d="M0,0 L10,3 L0,6 Z" fill="#555"/>\n'
        f'    </marker>\n'
        f'    <marker id="arrow-red" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="8" markerHeight="6" orient="auto">\n'
        f'      <path d="M0,0 L10,3 L0,6 Z" fill="#d32f2f"/>\n'
        f'    </marker>\n'
        f'    <marker id="arrow-orange" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="8" markerHeight="6" orient="auto">\n'
        f'      <path d="M0,0 L10,3 L0,6 Z" fill="#e65100"/>\n'
        f'    </marker>\n'
        f'    <marker id="arrow-green" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="8" markerHeight="6" orient="auto">\n'
        f'      <path d="M0,0 L10,3 L0,6 Z" fill="#2e7d32"/>\n'
        f'    </marker>\n'
        f'    <marker id="arrow-blue" viewBox="0 0 10 6" refX="10" refY="3" markerWidth="8" markerHeight="6" orient="auto">\n'
        f'      <path d="M0,0 L10,3 L0,6 Z" fill="#1565c0"/>\n'
        f'    </marker>\n'
        f'    <filter id="shadow" x="-4%" y="-4%" width="108%" height="108%">\n'
        f'      <feDropShadow dx="1" dy="1" stdDeviation="2" flood-opacity="0.15"/>\n'
        f'    </filter>\n'
        f'  </defs>\n'
    )


def _svg_footer() -> str:
    return '</svg>\n'


def _rect(x, y, w, h, *, rx=6, fill="#4a90d9", stroke="#2a5fa0", stroke_width=1.5, opacity=1.0, shadow=True):
    filt = ' filter="url(#shadow)"' if shadow else ''
    return (
        f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}" '
        f'opacity="{opacity}"{filt}/>\n'
    )


def _text(x, y, label, *, cls="node-label", extra=""):
    return f'  <text x="{x}" y="{y}" class="{cls}" {extra}>{_escape(label)}</text>\n'


def _line(x1, y1, x2, y2, *, color="#555", marker="arrow", cls="edge", extra=""):
    return (
        f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{color}" class="{cls}" marker-end="url(#{marker})" {extra}/>\n'
    )


def _curved_edge(x1, y1, x2, y2, *, color="#555", marker="arrow", cls="edge", curve=30):
    """Quadratic Bezier curve between two points."""
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    # Perpendicular offset
    dx, dy = x2 - x1, y2 - y1
    ln = max(math.sqrt(dx*dx + dy*dy), 1)
    nx, ny = -dy/ln * curve, dx/ln * curve
    cx, cy = mx + nx, my + ny
    return (
        f'  <path d="M{x1},{y1} Q{cx},{cy} {x2},{y2}" '
        f'stroke="{color}" class="{cls}" marker-end="url(#{marker})"/>\n'
    )


# ===================================================================
# B1: Package Dependency Graph
# ===================================================================

# Color palette for packages
PKG_COLORS = {
    "core":          ("#37474f", "#263238"),    # dark gray
    "pulses":        ("#7b1fa2", "#4a148c"),    # purple
    "gates":         ("#6a1b9a", "#4a148c"),    # deep purple
    "hardware":      ("#1565c0", "#0d47a1"),    # blue
    "devices":       ("#0277bd", "#01579b"),    # light blue
    "compile":       ("#00695c", "#004d40"),    # teal
    "simulation":    ("#2e7d32", "#1b5e20"),    # green
    "programs":      ("#e65100", "#bf360c"),    # orange
    "calibration":   ("#c62828", "#b71c1c"),    # red
    "analysis":      ("#ad1457", "#880e4f"),    # pink
    "optimization":  ("#4e342e", "#3e2723"),    # brown
    "experiments":   ("#f57f17", "#e65100"),    # amber
    "autotune":      ("#827717", "#6b6e00"),    # lime-dark
    "verification":  ("#546e7a", "#37474f"),    # blue-gray
    "gui":           ("#455a64", "#263238"),     # gray
    "tools":         ("#616161", "#424242"),     # gray
    "examples":      ("#78909c", "#546e7a"),    # light gray
    "tests":         ("#90a4ae", "#78909c"),     # lightest gray
    "compat":        ("#bdbdbd", "#9e9e9e"),
    "migration":     ("#bdbdbd", "#9e9e9e"),
}

# Layered layout positions (x, y)
PKG_POSITIONS = {
    # Layer 0: Foundation
    "core":          (400, 80),
    # Layer 1: Basic primitives
    "pulses":        (180, 180),
    # Layer 2: Gate algebra
    "gates":         (620, 180),
    # Layer 3: Hardware + Devices
    "hardware":      (180, 300),
    "devices":       (400, 300),
    # Layer 4: Compile + Simulation
    "compile":       (620, 300),
    "simulation":    (800, 300),
    # Layer 5: Programs
    "programs":      (400, 420),
    # Layer 6: Calibration + Analysis
    "calibration":   (180, 540),
    "analysis":      (620, 540),
    # Layer 7: Optimization
    "optimization":  (800, 420),
    # Layer 8: Experiments
    "experiments":   (400, 660),
    # Layer 9: High-level automation
    "autotune":      (180, 760),
    "verification":  (620, 760),
    # Layer 10: UI + utilities
    "gui":           (800, 660),
    "tools":         (800, 540),
    # Layer 11: Examples/tests
    "examples":      (180, 860),
    "tests":         (400, 860),
}

def generate_package_dependency_graph():
    """B1: Full package-level dependency graph."""

    with open(DATA_DIR / "package_dependencies.json") as f:
        data = json.load(f)
    with open(DATA_DIR / "centrality_metrics.json") as f:
        centrality = json.load(f)
    with open(DATA_DIR / "cycle_report.json") as f:
        cycle_data = json.load(f)

    edges = data["package_edges"]
    file_counts = data["file_count_per_pkg"]
    pkg_cent = centrality["package_centrality"]

    # Identify cycle edges (length-2 cycles = bidirectional)
    edge_set = set(tuple(e) for e in edges)
    cycle_edges = set()
    for a, b in edges:
        if (b, a) in edge_set:
            cycle_edges.add((a, b))
            cycle_edges.add((b, a))

    # Layer violation edges
    LAYER_ORDER = {
        "core": 0, "pulses": 1, "gates": 2, "hardware": 3, "devices": 3,
        "compile": 4, "simulation": 4, "programs": 5, "calibration": 6,
        "analysis": 6, "optimization": 7, "experiments": 8, "autotune": 9,
        "verification": 9, "gui": 10, "tools": 10, "examples": 11, "tests": 11,
    }
    violation_edges = set()
    for a, b in edges:
        la, lb = LAYER_ORDER.get(a, 99), LAYER_ORDER.get(b, 99)
        if la < lb and (lb - la) >= 3:
            violation_edges.add((a, b))

    W, H = 1000, 960
    node_w, node_h = 120, 40

    svg = _svg_header(W, H, title="Package Dependency Graph")
    svg += _text(W//2, 30, "qubox — Package Dependency Graph", cls="title", extra='text-anchor="middle"')
    svg += _text(W//2, 50, "Node size ~ total degree • Red dashed = bidirectional edge • Orange = layer violation (≥3 levels)", cls="subtitle", extra='text-anchor="middle"')

    # Draw edges first (under nodes)
    for src, dst in edges:
        if src not in PKG_POSITIONS or dst not in PKG_POSITIONS:
            continue
        sx, sy = PKG_POSITIONS[src]
        dx, dy = PKG_POSITIONS[dst]

        # Compute line endpoints to stop at node boundary
        angle = math.atan2(dy - sy, dx - sx)
        sx2 = sx + math.cos(angle) * (node_w / 2 + 2)
        sy2 = sy + math.sin(angle) * (node_h / 2 + 2)
        dx2 = dx - math.cos(angle) * (node_w / 2 + 8)
        dy2 = dy - math.sin(angle) * (node_h / 2 + 8)

        if (src, dst) in cycle_edges:
            color = "#d32f2f"
            marker = "arrow-red"
            cls = "edge-cycle"
            curve = 20
        elif (src, dst) in violation_edges:
            color = "#e65100"
            marker = "arrow-orange"
            cls = "edge"
            curve = 0
        else:
            color = "#777"
            marker = "arrow"
            cls = "edge"
            curve = 0

        if (src, dst) in cycle_edges:
            svg += _curved_edge(sx2, sy2, dx2, dy2, color=color, marker=marker, cls=cls, curve=curve)
        else:
            svg += _line(sx2, sy2, dx2, dy2, color=color, marker=marker, cls=cls)

    # Draw nodes
    for pkg, (cx, cy) in PKG_POSITIONS.items():
        fill, stroke = PKG_COLORS.get(pkg, ("#999", "#777"))
        td = pkg_cent.get(pkg, {}).get("total_degree", 0)
        # Scale node slightly by degree
        w = node_w + td * 2
        h = node_h + td * 1
        x = cx - w / 2
        y = cy - h / 2
        svg += _rect(x, y, w, h, fill=fill, stroke=stroke)
        svg += _text(cx, cy - 2, pkg, cls="node-label")
        fc = file_counts.get(pkg, 0)
        svg += _text(cx, cy + 12, f"{fc} files • deg {td}", cls="small-label", extra='fill="#ddd"')

    # Legend
    lx, ly = 20, H - 80
    svg += _rect(lx, ly, 200, 70, fill="#fafafa", stroke="#ccc", shadow=False, rx=4)
    svg += _text(lx + 10, ly + 16, "Legend:", cls="small-label", extra='text-anchor="start" font-weight="bold" fill="#333"')
    svg += f'  <line x1="{lx+10}" y1="{ly+32}" x2="{lx+50}" y2="{ly+32}" stroke="#777" stroke-width="1.5" marker-end="url(#arrow)"/>\n'
    svg += _text(lx + 60, ly + 33, "normal import", cls="small-label", extra='text-anchor="start"')
    svg += f'  <line x1="{lx+10}" y1="{ly+48}" x2="{lx+50}" y2="{ly+48}" stroke="#d32f2f" stroke-width="2" stroke-dasharray="6,3" marker-end="url(#arrow-red)"/>\n'
    svg += _text(lx + 60, ly + 49, "bidirectional (cycle)", cls="small-label", extra='text-anchor="start"')
    svg += f'  <line x1="{lx+10}" y1="{ly+63}" x2="{lx+50}" y2="{ly+63}" stroke="#e65100" stroke-width="1.5" marker-end="url(#arrow-orange)"/>\n'
    svg += _text(lx + 60, ly + 64, "layer violation (≥3)", cls="small-label", extra='text-anchor="start"')

    svg += _svg_footer()

    out_path = OUT_DIR / "package_dependency_graph.svg"
    out_path.write_text(svg, encoding="utf-8")
    print(f"  Written: {out_path}")


# ===================================================================
# B2: Workflow Dependency Graph (focused scientific layers)
# ===================================================================

def generate_workflow_dependency_graph():
    """B2: Focused graph for scientific workflow layers."""

    with open(DATA_DIR / "package_dependencies.json") as f:
        data = json.load(f)

    all_edges = data["package_edges"]
    focus = {"experiments", "programs", "gates", "pulses", "calibration", "analysis", "hardware", "simulation", "core"}
    edges = [(a, b) for a, b in all_edges if a in focus and b in focus]

    # Positions in a layered flow layout
    positions = {
        "core":          (400, 80),
        "pulses":        (200, 200),
        "gates":         (600, 200),
        "hardware":      (200, 340),
        "simulation":    (600, 340),
        "programs":      (400, 340),
        "calibration":   (200, 480),
        "analysis":      (600, 480),
        "experiments":   (400, 580),
    }

    edge_set = set(tuple(e) for e in edges)
    bidi = {(a, b) for a, b in edges if (b, a) in edge_set}

    W, H = 820, 680
    node_w, node_h = 130, 42

    svg = _svg_header(W, H)
    svg += _text(W//2, 30, "qubox — Scientific Workflow Dependencies", cls="title", extra='text-anchor="middle"')
    svg += _text(W//2, 50, "Core scientific layers only • Red dashed = bidirectional coupling", cls="subtitle", extra='text-anchor="middle"')

    # Edges
    for src, dst in edges:
        sx, sy = positions[src]
        dx, dy = positions[dst]
        angle = math.atan2(dy - sy, dx - sx)
        sx2 = sx + math.cos(angle) * (node_w / 2 + 2)
        sy2 = sy + math.sin(angle) * (node_h / 2 + 2)
        dx2 = dx - math.cos(angle) * (node_w / 2 + 8)
        dy2 = dy - math.sin(angle) * (node_h / 2 + 8)

        if (src, dst) in bidi:
            svg += _curved_edge(sx2, sy2, dx2, dy2, color="#d32f2f", marker="arrow-red", cls="edge-cycle", curve=22)
        else:
            svg += _line(sx2, sy2, dx2, dy2, color="#555", marker="arrow")

    # Nodes
    for pkg, (cx, cy) in positions.items():
        fill, stroke = PKG_COLORS.get(pkg, ("#999", "#777"))
        x, y = cx - node_w / 2, cy - node_h / 2
        svg += _rect(x, y, node_w, node_h, fill=fill, stroke=stroke)
        svg += _text(cx, cy, pkg, cls="node-label")

    # Layer annotations
    layers = [
        (80, "Layer 0: Foundation"),
        (200, "Layer 1-2: Primitives"),
        (340, "Layer 3-5: Infrastructure"),
        (480, "Layer 6: Calibration / Analysis"),
        (580, "Layer 8: Experiments"),
    ]
    for ly, label in layers:
        svg += _text(790, ly, label, cls="small-label", extra='text-anchor="end" fill="#aaa"')

    svg += _svg_footer()
    out_path = OUT_DIR / "workflow_dependency_graph.svg"
    out_path.write_text(svg, encoding="utf-8")
    print(f"  Written: {out_path}")


# ===================================================================
# B3: Class Relationships (UML-style)
# ===================================================================

def generate_class_relationships():
    """B3: Key class relationships diagram."""

    # Class definitions: (name, package, type, key_attributes)
    classes = [
        # Core
        ("ExperimentContext", "core", "frozen dataclass", ["sample_id", "cooldown_id", "wiring_rev"]),
        ("SessionState", "core", "frozen dataclass", ["hardware", "pulse_specs", "calibration", "build_hash"]),
        ("HardwareDefinition", "core", "builder", ["_elements", "_devices", "_aliases"]),
        # Protocols
        ("«protocol»\nHardwareController", "core", "protocol", ["set_element_lo()", "get_element_if()"]),
        ("«protocol»\nProgramRunner", "core", "protocol", ["run_program()", "simulate()"]),
        ("«protocol»\nExperiment", "core", "protocol", ["build_program()", "run()", "process()"]),

        # Hardware
        ("HardwareController", "hardware", "class", ["_qmm", "config", "qm"]),
        ("ProgramRunner", "hardware", "class", ["hw", "config", "job"]),
        ("ConfigEngine", "hardware", "class", ["_cfg_dict"]),

        # Experiments
        ("ExperimentBase", "experiments", "class", ["_ctx", "_last_build"]),
        ("ExperimentRunner", "experiments", "class", ["hw", "runner", "pulse_mgr"]),
        ("SessionManager", "experiments", "class", ["hw", "runner", "pulse_mgr", "calibration", "orchestrator"]),

        # Programs
        ("ProgramBuildResult", "experiments", "frozen dataclass", ["program", "n_total", "processors"]),

        # Pulses
        ("PulseOperationManager", "pulses", "class", ["_perm", "_volatile", "elements"]),

        # Gates
        ("Gate", "gates", "dataclass", ["model: GateModel", "hw: GateHardware"]),
        ("GateModel", "gates", "ABC", ["gate_type", "unitary()", "kraus()"]),
        ("GateHardware", "gates", "ABC", ["build()", "play()"]),

        # Calibration
        ("CalibrationStore", "calibration", "class", ["_data: CalibrationData"]),
        ("CalibrationOrchestrator", "calibration", "class", ["session", "patch_rules"]),
        ("CalibrationData", "calibration", "pydantic", ["context", "cqed_params", "frequencies"]),

        # Analysis
        ("Output", "analysis", "dict subclass", ["save()", "load()", "extract()"]),
        ("cQED_attributes", "analysis", "class", ["parameter dict"]),

        # Devices
        ("DeviceManager", "devices", "class", ["specs", "handles"]),

        # Simulation
        ("Solver", "simulation", "class", ["hamiltonian", "c_ops"]),
    ]

    # Composition / dependency relationships
    # (from_class, to_class, relationship_type, label)
    relationships = [
        ("SessionManager", "HardwareController", "composition", "hw"),
        ("SessionManager", "ProgramRunner", "composition", "runner"),
        ("SessionManager", "PulseOperationManager", "composition", "pulse_mgr"),
        ("SessionManager", "CalibrationStore", "composition", "calibration"),
        ("SessionManager", "CalibrationOrchestrator", "composition", "orchestrator"),
        ("SessionManager", "DeviceManager", "composition", "devices"),
        ("ExperimentRunner", "HardwareController", "composition", "hw"),
        ("ExperimentRunner", "ProgramRunner", "composition", "runner"),
        ("ExperimentRunner", "PulseOperationManager", "composition", "pulse_mgr"),
        ("ExperimentRunner", "DeviceManager", "composition", "device_manager"),
        ("ExperimentBase", "SessionManager", "dependency", "_ctx"),
        ("CalibrationOrchestrator", "SessionManager", "dependency", "session"),
        ("ProgramRunner", "HardwareController", "composition", "hw"),
        ("ProgramRunner", "ConfigEngine", "composition", "config"),
        ("HardwareController", "ConfigEngine", "composition", "config"),
        ("Gate", "GateModel", "composition", "model"),
        ("Gate", "GateHardware", "composition", "hw"),
        ("CalibrationStore", "CalibrationData", "composition", "_data"),
    ]

    # Layout classes by package grouping
    groups = {
        "experiments\n(Orchestration)": [
            ("SessionManager", 120, 80),
            ("ExperimentRunner", 120, 160),
            ("ExperimentBase", 120, 240),
            ("ProgramBuildResult", 120, 320),
        ],
        "hardware\n(Control)": [
            ("HardwareController", 380, 80),
            ("ProgramRunner", 380, 160),
            ("ConfigEngine", 380, 240),
        ],
        "pulses / gates": [
            ("PulseOperationManager", 620, 80),
            ("Gate", 620, 160),
            ("GateModel", 620, 240),
            ("GateHardware", 620, 320),
        ],
        "calibration\n+ analysis": [
            ("CalibrationOrchestrator", 380, 380),
            ("CalibrationStore", 380, 460),
            ("CalibrationData", 380, 540),
            ("Output", 620, 460),
            ("cQED_attributes", 620, 540),
        ],
        "core + devices": [
            ("ExperimentContext", 120, 460),
            ("SessionState", 120, 540),
            ("HardwareDefinition", 120, 620),
            ("DeviceManager", 380, 620),
        ],
    }

    # Flatten positions
    positions: dict[str, tuple[int, int]] = {}
    group_bounds: dict[str, tuple[int, int, int, int]] = {}
    for gname, items in groups.items():
        xs = [x for _, x, _ in items]
        ys = [y for _, _, y in items]
        group_bounds[gname] = (min(xs) - 80, min(ys) - 30, max(xs) + 80, max(ys) + 30)
        for cname, x, y in items:
            positions[cname] = (x, y)

    W, H = 800, 720
    box_w, box_h = 140, 50

    svg = _svg_header(W, H)
    svg += _text(W//2, 24, "qubox — Key Class Relationships", cls="title", extra='text-anchor="middle"')

    # Group backgrounds
    group_colors = ["#e3f2fd", "#fff3e0", "#f3e5f5", "#e8f5e9", "#fce4ec"]
    for i, (gname, (gx1, gy1, gx2, gy2)) in enumerate(group_bounds.items()):
        color = group_colors[i % len(group_colors)]
        svg += _rect(gx1, gy1, gx2 - gx1 + box_w, gy2 - gy1 + box_h, rx=10, fill=color, stroke="#bbb", stroke_width=1, shadow=False)
        svg += _text(gx1 + 5, gy1 + 12, gname.split("\n")[0], cls="small-label", extra='text-anchor="start" fill="#555" font-weight="bold"')

    # Draw relationships (edges)
    for src, dst, rel_type, label in relationships:
        if src not in positions or dst not in positions:
            continue
        sx, sy = positions[src]
        dx, dy = positions[dst]

        angle = math.atan2(dy - sy, dx - sx)
        sx2 = sx + math.cos(angle) * (box_w / 2 + 2)
        sy2 = sy + math.sin(angle) * (box_h / 2 + 2)
        dx2 = dx - math.cos(angle) * (box_w / 2 + 8)
        dy2 = dy - math.sin(angle) * (box_h / 2 + 8)

        if rel_type == "composition":
            svg += _line(sx2, sy2, dx2, dy2, color="#1565c0", marker="arrow-blue")
        elif rel_type == "inheritance":
            svg += _line(sx2, sy2, dx2, dy2, color="#2e7d32", marker="arrow-green")
        else:  # dependency
            svg += f'  <line x1="{sx2}" y1="{sy2}" x2="{dx2}" y2="{dy2}" stroke="#888" stroke-dasharray="5,3" stroke-width="1" marker-end="url(#arrow)"/>\n'

    # Draw class boxes
    for cname, (cx, cy) in positions.items():
        x, y = cx - box_w / 2, cy - box_h / 2
        # Find the class data
        cls_data = None
        for c in classes:
            if c[0] == cname:
                cls_data = c
                break

        if cls_data:
            _, pkg, ctype, attrs = cls_data
            fill, stroke = PKG_COLORS.get(pkg, ("#666", "#444"))
            if ctype in ("frozen dataclass", "dataclass", "pydantic"):
                fill = "#5c6bc0"
                stroke = "#3949ab"
            elif ctype == "ABC":
                fill = "#8e24aa"
                stroke = "#6a1b9a"
            elif ctype == "protocol":
                fill = "#00897b"
                stroke = "#00695c"
        else:
            fill, stroke = "#666", "#444"

        svg += _rect(x, y, box_w, box_h, fill=fill, stroke=stroke, rx=4)
        svg += _text(cx, cy - 4, cname, cls="node-label", extra=f'font-size="10px"')
        if cls_data:
            svg += _text(cx, cy + 12, f"«{cls_data[2]}»", cls="small-label", extra='fill="#ddd" font-size="9px"')

    # Legend
    lx, ly = 10, H - 52
    svg += _rect(lx, ly, 300, 45, fill="#fafafa", stroke="#ccc", shadow=False, rx=4)
    svg += f'  <line x1="{lx+10}" y1="{ly+15}" x2="{lx+40}" y2="{ly+15}" stroke="#1565c0" stroke-width="1.5" marker-end="url(#arrow-blue)"/>\n'
    svg += _text(lx + 50, ly + 16, "composition (has-a)", cls="small-label", extra='text-anchor="start"')
    svg += f'  <line x1="{lx+10}" y1="{ly+33}" x2="{lx+40}" y2="{ly+33}" stroke="#888" stroke-dasharray="5,3" stroke-width="1" marker-end="url(#arrow)"/>\n'
    svg += _text(lx + 50, ly + 34, "dependency (uses)", cls="small-label", extra='text-anchor="start"')
    svg += _rect(lx + 180, ly + 6, 15, 15, fill="#5c6bc0", stroke="#3949ab", rx=2, shadow=False)
    svg += _text(lx + 200, ly + 15, "dataclass", cls="small-label", extra='text-anchor="start"')
    svg += _rect(lx + 180, ly + 26, 15, 15, fill="#8e24aa", stroke="#6a1b9a", rx=2, shadow=False)
    svg += _text(lx + 200, ly + 35, "abstract base", cls="small-label", extra='text-anchor="start"')

    svg += _svg_footer()
    out_path = OUT_DIR / "class_relationships.svg"
    out_path.write_text(svg, encoding="utf-8")
    print(f"  Written: {out_path}")


# ===================================================================
# B4: Experiment Flow Diagram
# ===================================================================

def generate_experiment_flow():
    """B4: Control/data flow through the experiment lifecycle."""

    # Flow steps
    steps = [
        ("User / Notebook", "#78909c", 100),
        ("SessionManager.open()", "#37474f", 190),
        ("HardwareController\n+ ConfigEngine", "#1565c0", 280),
        ("PulseOperationManager\n(burn pulses to QM config)", "#7b1fa2", 370),
        ("ExperimentBase._build_impl()\n→ ProgramBuildResult", "#e65100", 460),
        ("ProgramRunner.run_program()\n→ RunResult", "#1565c0", 550),
        ("ExperimentBase.process()\n→ AnalysisResult", "#ad1457", 640),
        ("CalibrationOrchestrator\n→ Patch → CalibrationStore", "#c62828", 730),
        ("Output.save()\n→ JSON artifacts", "#2e7d32", 820),
    ]

    # Side connections (data/control sidebranches)
    side_branches = [
        (280, "DeviceManager\n(external instruments)", "left", "#0277bd"),
        (370, "PulseRegistry\n(pulse_specs.json)", "right", "#7b1fa2"),
        (460, "programs.builders.*\n(QUA program factories)", "right", "#e65100"),
        (550, "QuantumMachinesManager\n(OPX+ / Octave)", "left", "#1565c0"),
        (640, "analysis.fitting\nanalysis.metrics", "right", "#ad1457"),
        (730, "calibration.json\nhardware.json", "left", "#c62828"),
    ]

    W, H = 860, 920
    box_w, box_h = 300, 50
    cx = 400

    svg = _svg_header(W, H)
    svg += _text(W//2, 30, "qubox — Experiment Lifecycle Flow", cls="title", extra='text-anchor="middle"')
    svg += _text(W//2, 50, "Control flow (top→bottom) • Side branches show key dependencies", cls="subtitle", extra='text-anchor="middle"')

    # Main flow boxes + arrows
    for i, (label, color, y) in enumerate(steps):
        x = cx - box_w / 2
        svg += _rect(x, y - box_h/2, box_w, box_h, fill=color, stroke=color, rx=6)
        lines = label.split("\n")
        if len(lines) == 1:
            svg += _text(cx, y, lines[0], cls="node-label", extra='font-size="11px"')
        else:
            svg += _text(cx, y - 8, lines[0], cls="node-label", extra='font-size="11px"')
            svg += _text(cx, y + 8, lines[1], cls="node-label", extra='font-size="10px" fill="#ddd"')

        # Arrow to next step
        if i < len(steps) - 1:
            next_y = steps[i + 1][2]
            svg += _line(cx, y + box_h/2, cx, next_y - box_h/2 - 6, color="#444", marker="arrow")

    # Side branches
    side_box_w, side_box_h = 180, 40
    for main_y, label, side, color in side_branches:
        if side == "left":
            bx = cx - box_w/2 - side_box_w - 30
            svg += _rect(bx, main_y - side_box_h/2, side_box_w, side_box_h, fill="#fff", stroke=color, rx=4, shadow=False)
            lines = label.split("\n")
            tcx = bx + side_box_w / 2
            if len(lines) == 1:
                svg += _text(tcx, main_y, lines[0], cls="node-label-dark", extra='font-size="10px"')
            else:
                svg += _text(tcx, main_y - 7, lines[0], cls="node-label-dark", extra='font-size="10px"')
                svg += _text(tcx, main_y + 7, lines[1], cls="small-label", extra='font-size="9px"')
            # Connecting line
            svg += f'  <line x1="{bx + side_box_w}" y1="{main_y}" x2="{cx - box_w/2}" y2="{main_y}" stroke="{color}" stroke-dasharray="4,3" stroke-width="1"/>\n'
        else:
            bx = cx + box_w/2 + 30
            svg += _rect(bx, main_y - side_box_h/2, side_box_w, side_box_h, fill="#fff", stroke=color, rx=4, shadow=False)
            lines = label.split("\n")
            tcx = bx + side_box_w / 2
            if len(lines) == 1:
                svg += _text(tcx, main_y, lines[0], cls="node-label-dark", extra='font-size="10px"')
            else:
                svg += _text(tcx, main_y - 7, lines[0], cls="node-label-dark", extra='font-size="10px"')
                svg += _text(tcx, main_y + 7, lines[1], cls="small-label", extra='font-size="9px"')
            svg += f'  <line x1="{cx + box_w/2}" y1="{main_y}" x2="{bx}" y2="{main_y}" stroke="{color}" stroke-dasharray="4,3" stroke-width="1"/>\n'

    # Footer note
    svg += _text(W//2, H - 20, "Each step feeds into the next • Side dependencies show composition / data flow", cls="small-label")

    svg += _svg_footer()
    out_path = OUT_DIR / "experiment_flow.svg"
    out_path.write_text(svg, encoding="utf-8")
    print(f"  Written: {out_path}")


# ===================================================================
# Main
# ===================================================================

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating architecture diagrams...")
    print()

    generate_package_dependency_graph()
    generate_workflow_dependency_graph()
    generate_class_relationships()
    generate_experiment_flow()

    print()
    print("All diagrams generated in docs/architecture/")


if __name__ == "__main__":
    main()
