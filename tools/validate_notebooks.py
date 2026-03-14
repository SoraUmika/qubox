"""Validate notebook cells that do not require the QM hardware stack.

This script supports two validation modes:

- conservative mode: stop at a hardware-gated boundary detected heuristically
- sequential mode: execute the first N code cells in order and stop on failure
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


HARDWARE_MARKERS = (
    "qualang_tools",
    "from qm import",
    "import qm",
    "octave_sdk",
    "qubox_v2_legacy.experiments",
    "qubox_v2_legacy.experiments.session",
    "from qubox import Session",
)


def _cell_source(cell: dict) -> str:
    return "".join(cell.get("source", []))


def validate_notebook(path: Path) -> tuple[list[int], int | None]:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    state: dict[str, object] = {"__name__": "__main__"}
    executed: list[int] = []
    boundary: int | None = None

    for idx, cell in enumerate(notebook.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue

        source = _cell_source(cell)
        if any(marker in source for marker in HARDWARE_MARKERS):
            boundary = idx
            break

        exec(compile(source, f"{path}:cell_{idx}", "exec"), state)
        executed.append(idx)

    return executed, boundary


def execute_first_code_cells(path: Path, max_code_cells: int) -> tuple[list[int], str | None]:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    state: dict[str, object] = {"__name__": "__main__"}
    executed: list[int] = []
    failure: str | None = None
    code_count = 0

    for idx, cell in enumerate(notebook.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        if code_count >= max_code_cells:
            break

        source = _cell_source(cell)
        try:
            exec(compile(source, f"{path}:cell_{idx}", "exec"), state)
            executed.append(idx)
            code_count += 1
        except Exception as exc:  # pragma: no cover - CLI validation path
            failure = f"cell {idx}: {type(exc).__name__}: {exc}"
            break

    return executed, failure


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("notebooks", nargs="+", type=Path)
    parser.add_argument(
        "--max-code-cells",
        type=int,
        default=None,
        help="Execute the first N code cells sequentially instead of using the conservative boundary mode.",
    )
    args = parser.parse_args()

    for notebook in args.notebooks:
        if args.max_code_cells is None:
            executed, boundary = validate_notebook(notebook)
            boundary_text = "none" if boundary is None else str(boundary)
            print(f"{notebook}: executed={executed} boundary={boundary_text}")
        else:
            executed, failure = execute_first_code_cells(notebook, args.max_code_cells)
            failure_text = "none" if failure is None else failure
            print(
                f"{notebook}: executed={executed} "
                f"max_code_cells={args.max_code_cells} failure={failure_text}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
