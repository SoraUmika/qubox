"""qubox.artifacts — build-hash keyed artifact storage and config snapshots.

Consolidates artifact management and storage utilities.

Public API
----------
ArtifactManager
    Organises per-session artifacts under a directory keyed by build_hash.
save_config_snapshot
    Save a snapshot of the current QM config + pulse registry state.
save_run_summary
    Save a post-run metadata summary.
cleanup_artifacts
    Remove old build-hash artifact directories, keeping the most recent.
"""
from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any

from .core.persistence import sanitize_mapping_for_json

_logger = logging.getLogger(__name__)


def _json_default(obj: Any) -> Any:
    """Fallback JSON serialiser for numpy types and paths."""
    try:
        import numpy as np
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.complexfloating, complex)):
            return {"re": float(obj.real), "im": float(obj.imag)}
    except ImportError:
        if isinstance(obj, complex):
            return {"re": obj.real, "im": obj.imag}
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    return str(obj)


# ---------------------------------------------------------------------------
# ArtifactManager
# ---------------------------------------------------------------------------

class ArtifactManager:
    """Manage build-hash keyed artifacts for a session.

    Storage layout::

        <experiment_path>/artifacts/<build_hash>/
            session_state.json
            generated_config.json
            reports/
                <name>.md

    Parameters
    ----------
    experiment_path : str | Path
        Root experiment directory.
    build_hash : str
        SHA-256 prefix from :attr:`SessionState.build_hash`.
    """

    def __init__(self, experiment_path: str | Path, build_hash: str) -> None:
        self.experiment_path = Path(experiment_path)
        self.build_hash = build_hash
        self.root = self.experiment_path / "artifacts" / build_hash
        self.root.mkdir(parents=True, exist_ok=True)
        _logger.debug("ArtifactManager initialized: %s", self.root)

    @property
    def reports_dir(self) -> Path:
        d = self.root / "reports"
        d.mkdir(exist_ok=True)
        return d

    def save_session_state(self, state_dict: dict[str, Any]) -> Path:
        """Save a :class:`~qubox.core.session_state.SessionState` snapshot."""
        path = self.root / "session_state.json"
        self._write_json(path, state_dict)
        _logger.info("Session state saved: %s", path)
        return path

    def save_generated_config(self, config: dict[str, Any]) -> Path:
        """Save a compiled QM config dict."""
        path = self.root / "generated_config.json"
        self._write_json(path, config)
        _logger.info("Generated config saved: %s", path)
        return path

    def save_report(self, name: str, content: str, *, ext: str = ".md") -> Path:
        """Save a text report to the reports subdirectory."""
        path = self.reports_dir / f"{name}{ext}"
        path.write_text(content, encoding="utf-8")
        _logger.info("Report saved: %s", path)
        return path

    def save_artifact(self, name: str, data: dict[str, Any]) -> Path:
        """Save an arbitrary JSON artifact (without ``.json`` extension in *name*)."""
        path = self.root / f"{name}.json"
        self._write_json(path, data)
        _logger.info("Artifact saved: %s", path)
        return path

    def list_artifacts(self) -> list[Path]:
        """List all artifact files under this build hash, sorted."""
        if not self.root.exists():
            return []
        return sorted(p for p in self.root.rglob("*") if p.is_file())

    def _write_json(self, path: Path, data: dict) -> None:
        payload, dropped = sanitize_mapping_for_json(data)
        if dropped:
            payload["_persistence"] = {
                "raw_data_policy": "drop_shot_level_arrays",
                "dropped_fields": dropped,
            }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=_json_default, ensure_ascii=False)
            f.write("\n")


# ---------------------------------------------------------------------------
# Config snapshot
# ---------------------------------------------------------------------------

def save_config_snapshot(
    session: Any,
    *,
    tag: str = "",
    dest_dir: "Path | str | None" = None,
) -> Path:
    """Save a JSON snapshot of the current QM config + pulse registry state.

    The snapshot includes elements, operations, POM element-op mappings,
    context attributes, and calibration metadata.  Best-effort: individual
    sections that fail are recorded as error strings rather than aborting.

    Parameters
    ----------
    session
        An active session exposing the standard qubox session surface.
    tag : str
        Optional label included in the filename.
    dest_dir : Path, optional
        Destination directory.  Defaults to ``<experiment_path>/artifacts/``.

    Returns
    -------
    Path
        Path to the written snapshot JSON.
    """
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"config_snapshot_{tag}_{ts}" if tag else f"config_snapshot_{ts}"

    target = Path(dest_dir) if dest_dir else Path(session.experiment_path) / "artifacts"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{stem}.json"

    snapshot: dict[str, Any] = {
        "timestamp": ts,
        "tag": tag,
        "experiment_path": str(session.experiment_path),
    }

    try:
        cfg = session.config_engine.build_qm_config()
        element_summary = {}
        for el_name, el_data in (cfg.get("elements") or {}).items():
            ops = list((el_data.get("operations") or {}).keys())
            element_summary[el_name] = {
                "operations": ops,
                "intermediate_frequency": el_data.get("intermediate_frequency"),
            }
        snapshot["elements"] = element_summary
    except Exception as exc:
        snapshot["elements_error"] = str(exc)

    try:
        pom = session.pulse_mgr
        pom_map = {}
        for store_name, store in [("permanent", pom._perm), ("volatile", pom._volatile)]:
            pom_map[store_name] = {el: dict(ops) for el, ops in store.el_ops.items()}
        snapshot["pulse_op_mappings"] = pom_map
    except Exception as exc:
        snapshot["pulse_op_mappings_error"] = str(exc)

    try:
        ctx_snap = getattr(session, "context_snapshot", None)
        attr = ctx_snap() if callable(ctx_snap) else getattr(session, "attributes", None)
        if attr is not None:
            attr_dict = {}
            for f in ("qb_el", "ro_el", "st_el", "qb_fq", "ro_fq", "st_fq",
                      "qb_lo", "ro_lo", "st_lo",
                      "b_coherent_amp", "b_coherent_len", "b_alpha", "fock_fqs"):
                if hasattr(attr, f):
                    attr_dict[f] = getattr(attr, f)
            snapshot["context_snapshot"] = attr_dict
    except Exception as exc:
        snapshot["context_snapshot_error"] = str(exc)

    try:
        cal = session.calibration
        snapshot["calibration"] = {
            "path": str(cal._path),
            "exists": cal._path.exists(),
        }
    except Exception as exc:
        snapshot["calibration_error"] = str(exc)

    payload, dropped = sanitize_mapping_for_json(snapshot)
    if dropped:
        payload["_persistence"] = {
            "raw_data_policy": "drop_shot_level_arrays",
            "dropped_fields": dropped,
        }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=_json_default)
    _logger.info("Config snapshot saved to %s", path)
    return path


# ---------------------------------------------------------------------------
# Run summary
# ---------------------------------------------------------------------------

def save_run_summary(
    session: Any,
    result: Any = None,
    *,
    tag: str = "",
    dest_dir: "Path | str | None" = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Save a JSON summary of an experiment run.

    Parameters
    ----------
    session
        Active session (used for path resolution).
    result
        Experiment run result (RunResult or ExperimentResult).
    tag : str
        Optional label included in the filename.
    dest_dir : Path, optional
        Defaults to ``<experiment_path>/artifacts/``.
    extra : dict, optional
        Additional key-value pairs to include.

    Returns
    -------
    Path
        Path to the written summary JSON.
    """
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"run_summary_{tag}_{ts}" if tag else f"run_summary_{ts}"

    target = Path(dest_dir) if dest_dir else Path(session.experiment_path) / "artifacts"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{stem}.json"

    summary: dict[str, Any] = {
        "timestamp": ts,
        "tag": tag,
        "experiment_path": str(session.experiment_path),
    }

    if result is not None:
        try:
            summary["result"] = {
                "success": getattr(result, "success", None),
                "n_avg": getattr(result, "n_avg", None),
                "execution_time_s": getattr(result, "execution_time", None),
            }
            out = getattr(result, "output", None)
            if out is not None:
                try:
                    summary["result"]["output_keys"] = list(out.keys())
                except AttributeError:
                    pass
        except Exception as exc:
            summary["result_error"] = str(exc)

    if extra:
        summary["extra"] = extra

    payload, dropped = sanitize_mapping_for_json(summary)
    if dropped:
        payload["_persistence"] = {
            "raw_data_policy": "drop_shot_level_arrays",
            "dropped_fields": dropped,
        }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=_json_default)
    _logger.info("Run summary saved to %s", path)
    return path


# ---------------------------------------------------------------------------
# Artifact cleanup
# ---------------------------------------------------------------------------

def cleanup_artifacts(
    experiment_path: "str | Path",
    *,
    keep_latest: int = 10,
    current_hash: str | None = None,
) -> list[Path]:
    """Remove old build-hash artifact directories, keeping the most recent.

    Parameters
    ----------
    experiment_path : str | Path
        Root experiment directory.
    keep_latest : int
        Number of recent artifact directories to keep.
    current_hash : str, optional
        This build-hash directory is always kept, even if beyond *keep_latest*.

    Returns
    -------
    list[Path]
        Directories that were removed.
    """
    import shutil

    artifacts_dir = Path(experiment_path) / "artifacts"
    if not artifacts_dir.exists():
        return []

    hash_dirs = [
        d for d in artifacts_dir.iterdir()
        if d.is_dir() and len(d.name) <= 12 and _looks_like_hash(d.name)
    ]
    hash_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)

    removed: list[Path] = []
    for d in hash_dirs[keep_latest:]:
        if current_hash and d.name == current_hash:
            continue
        try:
            shutil.rmtree(d)
            removed.append(d)
            _logger.info("Cleaned up artifact dir: %s", d)
        except OSError as exc:
            _logger.warning("Failed to remove %s: %s", d, exc)
    return removed


def _looks_like_hash(name: str) -> bool:
    return all(c in "0123456789abcdef" for c in name.lower())
