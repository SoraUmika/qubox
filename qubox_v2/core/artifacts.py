"""qubox_v2.core.artifacts
===========================
Experiment artifact persistence — config snapshots, calibration summaries,
and run metadata.

Provides functions for saving a complete snapshot of the system state
before an experiment run, and for collecting post-run summaries.

Usage::

    from qubox_v2.core.artifacts import save_config_snapshot, save_run_summary

    # Before experiment
    save_config_snapshot(session, tag="pre_T1")

    # After experiment
    save_run_summary(session, result, tag="T1_run1")
"""
from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from .persistence_policy import sanitize_mapping_for_json

if TYPE_CHECKING:
    from ..experiments.session import SessionManager
    from ..hardware.program_runner import RunResult

_logger = logging.getLogger(__name__)


def _json_serialiser(obj: Any) -> Any:
    """Default JSON serialiser for numpy types and paths."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.complexfloating):
        return {"re": float(obj.real), "im": float(obj.imag)}
    if isinstance(obj, complex):
        return {"re": obj.real, "im": obj.imag}
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    return str(obj)


def save_config_snapshot(
    session: "SessionManager",
    *,
    tag: str = "",
    dest_dir: Path | str | None = None,
) -> Path:
    """Save a JSON snapshot of the current QM config + pulse registry state.

    The snapshot includes:
    - QM hardware config (elements, controllers, waveforms)
    - PulseOperationManager element-op mappings
    - cQED attributes summary
    - Timestamp and tag

    Parameters
    ----------
    session : SessionManager
        An active session.
    tag : str
        Optional label to include in the filename.
    dest_dir : Path, optional
        Directory to save to.  Defaults to ``<experiment_path>/artifacts/``.

    Returns
    -------
    Path
        Path to the written snapshot JSON.
    """
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"config_snapshot_{tag}_{ts}" if tag else f"config_snapshot_{ts}"

    target = Path(dest_dir) if dest_dir else session.experiment_path / "artifacts"
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{stem}.json"

    snapshot: dict[str, Any] = {
        "timestamp": ts,
        "tag": tag,
        "experiment_path": str(session.experiment_path),
    }

    # QM config summary (element names + operations only — not full waveforms)
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
        _logger.warning("Could not capture element config: %s", exc)

    # POM element-op mapping
    try:
        pom = session.pulse_mgr
        pom_map = {}
        for store_name, store in [("permanent", pom._perm), ("volatile", pom._volatile)]:
            pom_map[store_name] = {
                el: dict(ops) for el, ops in store.el_ops.items()
            }
        snapshot["pulse_op_mappings"] = pom_map
    except Exception as exc:
        snapshot["pulse_op_mappings_error"] = str(exc)

    # Attributes summary
    try:
        attr = session.attributes
        attr_dict = {}
        for field in ("qb_el", "ro_el", "st_el", "qb_fq", "ro_fq", "st_fq",
                       "qb_lo", "ro_lo", "st_lo",
                       "b_coherent_amp", "b_coherent_len", "b_alpha",
                       "fock_fqs"):
            if hasattr(attr, field):
                val = getattr(attr, field)
                attr_dict[field] = val
        snapshot["attributes"] = attr_dict
    except Exception as exc:
        snapshot["attributes_error"] = str(exc)

    # Calibration store metadata
    try:
        cal = session.calibration
        snapshot["calibration"] = {
            "path": str(cal._path),
            "exists": cal._path.exists(),
            "n_entries": len(cal._data) if hasattr(cal, "_data") else "unknown",
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
        json.dump(payload, f, indent=2, default=_json_serialiser)

    _logger.info("Config snapshot saved to %s", path)
    return path


def save_run_summary(
    session: "SessionManager",
    result: "RunResult | None" = None,
    *,
    tag: str = "",
    dest_dir: Path | str | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Save a JSON summary of an experiment run.

    Parameters
    ----------
    session : SessionManager
        An active session (used for path resolution).
    result : RunResult, optional
        The experiment run result.  If provided, metadata is extracted.
    tag : str
        Optional label to include in the filename.
    dest_dir : Path, optional
        Defaults to ``<experiment_path>/artifacts/``.
    extra : dict, optional
        Additional key-value pairs to include in the summary.

    Returns
    -------
    Path
        Path to the written summary JSON.
    """
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = f"run_summary_{tag}_{ts}" if tag else f"run_summary_{ts}"

    target = Path(dest_dir) if dest_dir else session.experiment_path / "artifacts"
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
            # Output keys
            out = getattr(result, "output", None)
            if out is not None:
                if hasattr(out, "keys"):
                    summary["result"]["output_keys"] = list(out.keys())
                elif isinstance(out, dict):
                    summary["result"]["output_keys"] = list(out.keys())
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
        json.dump(payload, f, indent=2, default=_json_serialiser)

    _logger.info("Run summary saved to %s", path)
    return path
