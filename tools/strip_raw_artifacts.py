from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qubox.core.persistence import sanitize_mapping_for_json


def sanitize_json_file(
    path: str | Path,
    *,
    in_place: bool = True,
    backup: bool = True,
) -> tuple[Path, dict[str, Any]]:
    src = Path(path)
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object at root: {src}")

    sanitized, dropped = sanitize_mapping_for_json(data)
    if dropped:
        sanitized["_persistence"] = {
            "raw_data_policy": "drop_shot_level_arrays",
            "dropped_fields": dropped,
            "migration": "strip_raw_artifacts",
        }

    if in_place:
        if backup:
            backup_path = src.with_suffix(src.suffix + ".bak")
            backup_path.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        dst = src
    else:
        dst = src.with_name(src.stem + "_sanitized" + src.suffix)

    with open(dst, "w", encoding="utf-8") as f:
        json.dump(sanitized, f, indent=2, default=str)
        f.write("\n")

    return dst, dropped


def sanitize_tree(
    root: str | Path,
    *,
    include_globs: tuple[str, ...] = (
        "artifacts/**/*.json",
        "config/calibration*.json",
        "config/measureConfig.json",
        "config/calibration_db.json",
    ),
    backup: bool = True,
) -> dict[str, Any]:
    base = Path(root)
    summary: dict[str, Any] = {"processed": 0, "changed": 0, "files": []}

    seen: set[Path] = set()
    for pattern in include_globs:
        for path in base.glob(pattern):
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            summary["processed"] += 1
            dst, dropped = sanitize_json_file(path, in_place=True, backup=backup)
            changed = bool(dropped)
            if changed:
                summary["changed"] += 1
            summary["files"].append(
                {
                    "path": str(dst),
                    "changed": changed,
                    "dropped_field_count": len(dropped),
                }
            )

    return summary
