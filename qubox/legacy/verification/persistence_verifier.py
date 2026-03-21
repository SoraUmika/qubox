from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from ..core.persistence_policy import split_output_for_persistence, sanitize_mapping_for_json


DEFAULT_JSON_GLOBS = (
    "artifacts/**/*.json",
    "config/calibration*.json",
    "config/measureConfig.json",
    "config/calibration_db.json",
    "config/session_runtime.json",
)


def _json_policy_issues(path: Path) -> dict[str, Any] | None:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        return {"reason": "root_not_object"}

    _, dropped = sanitize_mapping_for_json(payload)
    if not dropped:
        return None
    return {
        "dropped_field_count": len(dropped),
        "sample_fields": sorted(dropped.keys())[:8],
    }


def scan_json(root: Path) -> dict[str, Any]:
    seen: set[Path] = set()
    issues: list[dict[str, Any]] = []
    scanned = 0

    for pattern in DEFAULT_JSON_GLOBS:
        for path in root.glob(pattern):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            scanned += 1
            try:
                issue = _json_policy_issues(path)
            except Exception as exc:
                issues.append({"path": str(path), "reason": f"read_error: {exc}"})
                continue
            if issue is not None:
                issues.append({"path": str(path), **issue})

    return {
        "scanned": scanned,
        "issue_count": len(issues),
        "issues": issues,
    }


def _npz_policy_projection(path: Path) -> dict[str, Any]:
    with np.load(path, allow_pickle=True) as zf:
        data = {k: zf[k] for k in zf.files}

    arrays, _, dropped = split_output_for_persistence(data)
    original_bytes = int(path.stat().st_size)
    kept_array_bytes = int(sum(v.nbytes for v in arrays.values()))
    dropped_array_bytes = int(
        sum(v.nbytes for k, v in data.items() if isinstance(v, np.ndarray) and k not in arrays)
    )

    return {
        "path": str(path),
        "original_bytes": original_bytes,
        "kept_array_bytes": kept_array_bytes,
        "dropped_array_bytes": dropped_array_bytes,
        "array_keys_total": len(data),
        "array_keys_kept": len(arrays),
        "dropped_field_count": len(dropped),
        "sample_dropped_fields": sorted(dropped.keys())[:8],
        "reduction_fraction_vs_original": 1.0 - (kept_array_bytes / max(original_bytes, 1)),
    }


def scan_latest_butterfly(root: Path, limit: int = 10) -> dict[str, Any]:
    files = sorted(
        (root / "data").glob("butterflyMeasurement*.npz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    selected = files[: max(1, int(limit))]

    rows: list[dict[str, Any]] = []
    for path in selected:
        try:
            rows.append(_npz_policy_projection(path))
        except Exception as exc:
            rows.append({"path": str(path), "error": str(exc)})

    valid = [r for r in rows if "error" not in r]
    if not valid:
        return {"scanned": len(rows), "found": len(files), "rows": rows}

    avg_original = sum(r["original_bytes"] for r in valid) / len(valid)
    avg_kept = sum(r["kept_array_bytes"] for r in valid) / len(valid)

    return {
        "found": len(files),
        "scanned": len(rows),
        "avg_original_bytes": avg_original,
        "avg_kept_array_bytes": avg_kept,
        "avg_reduction_fraction": 1.0 - (avg_kept / max(avg_original, 1.0)),
        "rows": rows,
    }


def verify(root: Path, *, butterfly_limit: int = 10) -> dict[str, Any]:
    json_report = scan_json(root)
    butterfly_report = scan_latest_butterfly(root, limit=butterfly_limit)

    json_ok = json_report["issue_count"] == 0
    butterfly_ok = butterfly_report.get("found", 0) > 0

    return {
        "root": str(root),
        "status": "PASS" if json_ok else "FAIL",
        "checks": {
            "json_policy_clean": json_ok,
            "butterfly_files_found": butterfly_ok,
        },
        "json": json_report,
        "butterfly": butterfly_report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify persistence policy compliance")
    parser.add_argument("root", type=Path, help="Experiment root (e.g. seq_1_device)")
    parser.add_argument("--butterfly-limit", type=int, default=10)
    parser.add_argument("--out", type=Path, default=None, help="Optional JSON report output path")
    args = parser.parse_args()

    report = verify(args.root, butterfly_limit=args.butterfly_limit)
    text = json.dumps(report, indent=2)
    print(text)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
