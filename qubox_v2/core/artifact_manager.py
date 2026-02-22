# qubox_v2/core/artifact_manager.py
"""Build-hash keyed artifact storage.

ArtifactManager organises per-session artifacts under a directory keyed by
the SessionState build_hash. This ensures artifacts are reproducibly
associated with the exact source-of-truth configuration that produced them.

See docs/ARTIFACT_POLICY.md for the full specification.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .persistence_policy import sanitize_mapping_for_json

_logger = logging.getLogger(__name__)


def _json_default(obj: Any) -> Any:
    """Fallback serialiser for artifact JSON."""
    import numpy as np
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.complexfloating, complex)):
        return {"re": float(obj.real), "im": float(obj.imag)}
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


class ArtifactManager:
    """Manage build-hash keyed artifacts for a session.

    Storage layout::

        <experiment_path>/artifacts/<build_hash>/
            session_state.json
            generated_config.json
            reports/
                legacy_parity_*.md

    Parameters
    ----------
    experiment_path : Path
        Root experiment directory (e.g. ``seq_1_device/``).
    build_hash : str
        SHA-256 prefix from SessionState.build_hash.
    """

    def __init__(self, experiment_path: str | Path, build_hash: str):
        self.experiment_path = Path(experiment_path)
        self.build_hash = build_hash
        self.root = self.experiment_path / "artifacts" / build_hash
        self.root.mkdir(parents=True, exist_ok=True)
        _logger.debug("ArtifactManager initialized: %s", self.root)

    @property
    def reports_dir(self) -> Path:
        """Directory for reports."""
        d = self.root / "reports"
        d.mkdir(exist_ok=True)
        return d

    def save_session_state(self, state_dict: dict[str, Any]) -> Path:
        """Save a SessionState snapshot.

        Parameters
        ----------
        state_dict : dict
            Output of ``SessionState.to_dict()``.

        Returns
        -------
        Path
            Path to the written JSON file.
        """
        path = self.root / "session_state.json"
        self._write_json(path, state_dict)
        _logger.info("Session state saved: %s", path)
        return path

    def save_generated_config(self, config: dict[str, Any]) -> Path:
        """Save a generated QM config dict.

        Parameters
        ----------
        config : dict
            The compiled QM config (elements, controllers, waveforms, etc.).

        Returns
        -------
        Path
            Path to the written JSON file.
        """
        path = self.root / "generated_config.json"
        self._write_json(path, config)
        _logger.info("Generated config saved: %s", path)
        return path

    def save_report(self, name: str, content: str, *, ext: str = ".md") -> Path:
        """Save a text report.

        Parameters
        ----------
        name : str
            Report name (without extension).
        content : str
            Report body text.
        ext : str
            File extension (default ``.md``).

        Returns
        -------
        Path
            Path to the written file.
        """
        path = self.reports_dir / f"{name}{ext}"
        path.write_text(content, encoding="utf-8")
        _logger.info("Report saved: %s", path)
        return path

    def save_artifact(self, name: str, data: dict[str, Any]) -> Path:
        """Save an arbitrary JSON artifact.

        Parameters
        ----------
        name : str
            Artifact name (without ``.json`` extension).
        data : dict
            JSON-serialisable data.

        Returns
        -------
        Path
            Path to the written file.
        """
        path = self.root / f"{name}.json"
        self._write_json(path, data)
        _logger.info("Artifact saved: %s", path)
        return path

    def list_artifacts(self) -> list[Path]:
        """List all artifacts under this build hash.

        Returns
        -------
        list[Path]
            Sorted list of artifact file paths.
        """
        if not self.root.exists():
            return []
        return sorted(self.root.rglob("*") if self.root.is_dir() else [])

    def _write_json(self, path: Path, data: dict) -> None:
        """Write JSON with consistent formatting."""
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
# Artifact cleanup
# ---------------------------------------------------------------------------

def cleanup_artifacts(
    experiment_path: str | Path,
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
        Number of recent artifact dirs to keep.
    current_hash : str | None
        If provided, this build-hash directory is always kept.

    Returns
    -------
    list[Path]
        List of removed directories.
    """
    import shutil

    artifacts_dir = Path(experiment_path) / "artifacts"
    if not artifacts_dir.exists():
        return []

    # Find build-hash directories (12-char hex dirs)
    hash_dirs = []
    for d in artifacts_dir.iterdir():
        if d.is_dir() and len(d.name) <= 12 and _looks_like_hash(d.name):
            hash_dirs.append(d)

    # Sort by modification time (newest first)
    hash_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)

    removed = []
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
    """Check if a directory name looks like a hex hash prefix."""
    return all(c in "0123456789abcdef" for c in name.lower())
