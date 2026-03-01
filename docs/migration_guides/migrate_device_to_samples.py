"""Migrate on-disk data from legacy devices/ layout to samples/ layout.

Performs:
1. Copy ``<base>/devices/`` -> ``<base>/samples/``
2. For each sample directory in ``samples/*/``:
   - Rename ``device.json`` -> ``sample.json``
   - Update JSON keys: ``device_id`` -> ``sample_id``, ``sample_info`` -> ``metadata``
   - Scan ``cooldowns/*/config/calibration.json`` for ``context.device_id`` -> ``context.sample_id``
3. Validate migrated tree (file counts match, JSON parses OK)
4. Print summary

Usage::

    python tools/migrate_device_to_samples.py [--base E:\\qubox] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def migrate_device_json(src_path: Path, dst_path: Path, *, dry_run: bool = False) -> dict:
    """Migrate device.json -> sample.json with key renames."""
    with open(src_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Rename keys
    migrated = {}
    migrated["sample_id"] = data.pop("device_id", data.pop("sample_id", ""))
    migrated["description"] = data.pop("description", "")
    migrated["metadata"] = data.pop("sample_info", data.pop("metadata", {}))
    migrated["element_map"] = data.pop("element_map", {})
    migrated["created"] = data.pop("created", "")
    # Preserve any extra keys
    migrated.update(data)

    if not dry_run:
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dst_path, "w", encoding="utf-8") as f:
            json.dump(migrated, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return migrated


def migrate_calibration_json(cal_path: Path, *, dry_run: bool = False) -> bool:
    """Migrate context.device_id -> context.sample_id in calibration.json."""
    if not cal_path.exists():
        return False

    with open(cal_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    changed = False
    context = data.get("context")
    if isinstance(context, dict):
        if "device_id" in context and "sample_id" not in context:
            context["sample_id"] = context.pop("device_id")
            changed = True

    if changed and not dry_run:
        with open(cal_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return changed


def count_files(directory: Path) -> int:
    """Recursively count files in a directory."""
    return sum(1 for p in directory.rglob("*") if p.is_file())


def migrate(base: Path, *, dry_run: bool = False) -> dict:
    """Run the full migration."""
    src_root = base / "devices"
    dst_root = base / "samples"

    if not src_root.exists():
        print(f"ERROR: Source directory not found: {src_root}")
        sys.exit(1)

    if dst_root.exists():
        print(f"WARNING: Destination already exists: {dst_root}")
        print("  Migration may have already been run. Proceeding anyway.")

    summary = {
        "samples_migrated": [],
        "device_jsons_migrated": [],
        "calibrations_updated": [],
        "src_file_count": 0,
        "dst_file_count": 0,
        "errors": [],
    }

    # Count source files
    summary["src_file_count"] = count_files(src_root)
    print(f"Source: {src_root} ({summary['src_file_count']} files)")

    # Step 1: Copy tree
    if not dry_run:
        if not dst_root.exists():
            shutil.copytree(src_root, dst_root)
            print(f"Copied {src_root} -> {dst_root}")
        else:
            print(f"Destination exists, skipping copytree: {dst_root}")
    else:
        print(f"[DRY RUN] Would copy {src_root} -> {dst_root}")

    # Step 2: For each sample directory
    sample_dirs = sorted(p for p in (dst_root if not dry_run else src_root).iterdir() if p.is_dir())
    for sample_dir in sample_dirs:
        sample_name = sample_dir.name
        print(f"\nProcessing sample: {sample_name}")
        summary["samples_migrated"].append(sample_name)

        # 2a: Rename device.json -> sample.json
        device_json = sample_dir / "device.json"
        sample_json = sample_dir / "sample.json"

        if device_json.exists():
            target_dir = dst_root / sample_name if dry_run else sample_dir
            target_sample_json = target_dir / "sample.json"

            migrated = migrate_device_json(device_json, target_sample_json, dry_run=dry_run)
            print(f"  device.json -> sample.json: sample_id={migrated.get('sample_id')}")
            summary["device_jsons_migrated"].append(sample_name)

            # Remove old device.json (in the destination)
            if not dry_run and device_json.exists():
                device_json.unlink()
                print(f"  Removed old device.json")
        elif sample_json.exists():
            print(f"  sample.json already exists (already migrated?)")
        else:
            summary["errors"].append(f"No device.json or sample.json in {sample_dir}")
            print(f"  WARNING: No device.json or sample.json found")

        # 2b: Scan cooldowns for calibration.json
        cooldowns_dir = sample_dir / "cooldowns"
        if cooldowns_dir.exists():
            for cd_dir in sorted(cooldowns_dir.iterdir()):
                if not cd_dir.is_dir():
                    continue
                cal_path = cd_dir / "config" / "calibration.json"
                if cal_path.exists():
                    changed = migrate_calibration_json(cal_path, dry_run=dry_run)
                    if changed:
                        print(f"  Migrated context in: {cd_dir.name}/config/calibration.json")
                        summary["calibrations_updated"].append(str(cal_path))
                    else:
                        print(f"  No context migration needed: {cd_dir.name}/config/calibration.json")

    # Step 3: Validate
    if not dry_run and dst_root.exists():
        summary["dst_file_count"] = count_files(dst_root)
        # We removed device.json files and created sample.json files, so count should be same
        diff = summary["dst_file_count"] - summary["src_file_count"]
        print(f"\nFile count: src={summary['src_file_count']}, dst={summary['dst_file_count']}, diff={diff}")
        if diff != 0:
            print(f"  NOTE: File count differs by {diff} (expected 0 if all device.json->sample.json)")

        # Validate all sample.json files parse correctly
        for sample_dir in sorted(dst_root.iterdir()):
            if not sample_dir.is_dir():
                continue
            sj = sample_dir / "sample.json"
            if sj.exists():
                try:
                    with open(sj, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    sid = data.get("sample_id", "MISSING")
                    print(f"  Validated: {sample_dir.name}/sample.json -> sample_id={sid}")
                except Exception as e:
                    summary["errors"].append(f"Parse error in {sj}: {e}")
                    print(f"  ERROR: {sj}: {e}")

    # Summary
    print(f"\n{'='*60}")
    print("Migration Summary")
    print(f"{'='*60}")
    print(f"  Samples migrated: {len(summary['samples_migrated'])}")
    print(f"  device.json -> sample.json: {len(summary['device_jsons_migrated'])}")
    print(f"  calibration.json context updates: {len(summary['calibrations_updated'])}")
    print(f"  Errors: {len(summary['errors'])}")
    if summary["errors"]:
        for err in summary["errors"]:
            print(f"    - {err}")
    print(f"  Dry run: {dry_run}")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate devices/ -> samples/ directory layout")
    parser.add_argument("--base", type=str, default=r"E:\qubox", help="Registry base directory")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without making changes")
    args = parser.parse_args()

    migrate(Path(args.base), dry_run=args.dry_run)
