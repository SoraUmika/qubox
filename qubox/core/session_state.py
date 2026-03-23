# qubox_v2/core/session_state.py
"""Immutable runtime snapshot of session configuration.

SessionState is constructed once during SessionManager.open() and provides
a frozen, hashable view of all source-of-truth configuration. Experiments
should depend on SessionState rather than reading raw files.

This module is additive — SessionManager continues to work without it.
SessionState is opt-in for new code that benefits from reproducibility
guarantees.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SchemaInfo:
    """Schema version and source path for a single config file."""
    file_type: str
    path: str
    version: str | int
    size_bytes: int


@dataclass(frozen=True)
class SessionState:
    """Immutable runtime snapshot of session configuration.

    All fields are frozen at construction time. No mutations are allowed.

    Attributes
    ----------
    hardware : dict
        Parsed hardware.json contents.
    pulse_specs : dict
        Parsed pulse_specs.json (or pulse_definitions from pulses.json).
    calibration : dict
        Parsed calibration.json contents.
    cqed_params : dict
        Parsed cqed_params.json contents.
    schemas : tuple[SchemaInfo, ...]
        Schema version info for all loaded files.
    build_hash : str
        SHA-256 hash (first 12 hex chars) of all source-of-truth file contents.
    build_timestamp : str
        ISO 8601 timestamp of when the state was constructed.
    git_commit : str | None
        Git HEAD commit hash if available.
    """
    hardware: dict = field(default_factory=dict)
    pulse_specs: dict = field(default_factory=dict)
    calibration: dict = field(default_factory=dict)
    cqed_params: dict = field(default_factory=dict)
    schemas: tuple[SchemaInfo, ...] = ()
    build_hash: str = ""
    build_timestamp: str = ""
    git_commit: str | None = None
    sample_id: str | None = None
    cooldown_id: str | None = None
    wiring_rev: str | None = None

    @classmethod
    def from_config_dir(
        cls,
        config_dir: str | Path,
        *,
        sample_config_dir: str | Path | None = None,
        sample_id: str | None = None,
        cooldown_id: str | None = None,
        wiring_rev: str | None = None,
    ) -> SessionState:
        """Construct SessionState by reading all config files from a directory.

        Parameters
        ----------
        config_dir : str | Path
            Path to the config directory (e.g., ``cooldown/config/``).
        sample_config_dir : str | Path | None
            Optional sample-level config directory. In context mode,
            sample-level files (hardware.json, pulse_specs.json,
            cqed_params.json) live here rather than in the cooldown
            config dir.

        Returns
        -------
        SessionState
            Frozen snapshot of all configuration.

        Raises
        ------
        FileNotFoundError
            If required files (hardware.json, calibration.json) are missing.
        """
        config_dir = Path(config_dir)
        sample_dir = Path(sample_config_dir) if sample_config_dir is not None else None
        schemas = []
        hash_inputs = []

        # --- Hardware (required) ---
        hw_path = config_dir / "hardware.json"
        if not hw_path.exists() and sample_dir is not None:
            hw_path = sample_dir / "hardware.json"
        if not hw_path.exists():
            raise FileNotFoundError(f"Required file missing: {hw_path}")
        hw_raw = hw_path.read_bytes()
        hardware = json.loads(hw_raw)
        hash_inputs.append(hw_raw)
        schemas.append(SchemaInfo(
            file_type="hardware",
            path=str(hw_path),
            version=hardware.get("version", 1),
            size_bytes=len(hw_raw),
        ))

        # --- Calibration (required) ---
        cal_path = config_dir / "calibration.json"
        if not cal_path.exists():
            raise FileNotFoundError(f"Required file missing: {cal_path}")
        cal_raw = cal_path.read_bytes()
        calibration = json.loads(cal_raw)
        hash_inputs.append(cal_raw)
        schemas.append(SchemaInfo(
            file_type="calibration",
            path=str(cal_path),
            version=calibration.get("version", "1.0.0"),
            size_bytes=len(cal_raw),
        ))

        # --- Pulse specs (optional — may be pulse_specs.json or pulses.json) ---
        pulse_specs = {}
        ps_path = config_dir / "pulse_specs.json"
        if not ps_path.exists() and sample_dir is not None:
            ps_path = sample_dir / "pulse_specs.json"
        if not ps_path.exists():
            ps_path = config_dir / "pulses.json"
        if ps_path.exists():
            ps_raw = ps_path.read_bytes()
            pulse_specs = json.loads(ps_raw)
            hash_inputs.append(ps_raw)
            schemas.append(SchemaInfo(
                file_type="pulse_specs" if "pulse_specs" in ps_path.name else "pulses",
                path=str(ps_path),
                version=pulse_specs.get("schema_version", pulse_specs.get("_schema_version", 1)),
                size_bytes=len(ps_raw),
            ))

        # --- cQED params (optional, legacy) ---
        cqed_params = {}
        cqed_path = config_dir / "cqed_params.json"
        if not cqed_path.exists() and sample_dir is not None:
            cqed_path = sample_dir / "cqed_params.json"
        if cqed_path.exists():
            cqed_raw = cqed_path.read_bytes()
            cqed_params = json.loads(cqed_raw)
            # Not included in build hash — legacy, not source of truth

        # --- Build hash ---
        hasher = hashlib.sha256()
        for raw in hash_inputs:
            hasher.update(raw)
        build_hash = hasher.hexdigest()[:12]

        # --- Git commit ---
        git_commit = _resolve_git_commit(config_dir)

        return cls(
            hardware=hardware,
            pulse_specs=pulse_specs,
            calibration=calibration,
            cqed_params=cqed_params,
            schemas=tuple(schemas),
            build_hash=build_hash,
            build_timestamp=datetime.now().isoformat(),
            git_commit=git_commit,
            sample_id=sample_id,
            cooldown_id=cooldown_id,
            wiring_rev=wiring_rev,
        )

    def summary(self) -> str:
        """Return a human-readable summary of the session state."""
        lines = [
            f"SessionState (build_hash={self.build_hash})",
            f"  timestamp: {self.build_timestamp}",
            f"  git_commit: {self.git_commit or 'unknown'}",
            f"  sample_id: {self.sample_id or '(legacy)'}",
            f"  cooldown_id: {self.cooldown_id or '(legacy)'}",
            f"  wiring_rev: {self.wiring_rev or '(unknown)'}",
            f"  schemas:",
        ]
        for s in self.schemas:
            lines.append(f"    {s.file_type}: v{s.version} ({s.size_bytes} bytes) — {s.path}")

        hw_elements = list(self.hardware.get("elements", {}).keys())
        lines.append(f"  hardware elements: {hw_elements}")

        cal_sections = [k for k, v in self.calibration.items()
                        if isinstance(v, dict) and v and k not in ("version", "created", "last_modified")]
        lines.append(f"  calibration sections: {cal_sections}")

        n_specs = len(self.pulse_specs.get("specs", self.pulse_specs.get("pulse_definitions", {})))
        lines.append(f"  pulse specs: {n_specs} definitions")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict for artifact storage."""
        return {
            "build_hash": self.build_hash,
            "build_timestamp": self.build_timestamp,
            "git_commit": self.git_commit,
            "sample_id": self.sample_id,
            "cooldown_id": self.cooldown_id,
            "wiring_rev": self.wiring_rev,
            "schemas": [
                {"file_type": s.file_type, "path": s.path,
                 "version": s.version, "size_bytes": s.size_bytes}
                for s in self.schemas
            ],
            "hardware_elements": list(self.hardware.get("elements", {}).keys()),
            "calibration_version": self.calibration.get("version"),
            "pulse_spec_count": len(
                self.pulse_specs.get("specs",
                                     self.pulse_specs.get("pulse_definitions", {}))
            ),
        }


def _resolve_git_commit(near_path: Path) -> str | None:
    """Attempt to read HEAD commit from nearest git repo."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=str(near_path.parent if near_path.is_file() else near_path),
        )
        if result.returncode == 0:
            return result.stdout.strip()[:12]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None
