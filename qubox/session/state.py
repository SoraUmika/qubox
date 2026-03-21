"""qubox.session.state — reproducible session state snapshot.

Migrated from ``qubox_v2_legacy.core.session_state``.
No external dependencies beyond the standard library.

:class:`SessionState` is an immutable snapshot of the config files in a
session directory.  Its ``build_hash`` is a 12-character SHA-256 prefix of
all the config file contents combined, giving a reproducible key for
associating artifacts with the exact source of truth that produced them.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SessionState:
    """Immutable snapshot of a session's config directory.

    Parameters
    ----------
    config_dir : str
        Absolute path to the config directory.
    hardware_config : dict
        Parsed hardware.json.
    calibration_data : dict
        Parsed calibration.json.
    pulse_specs : dict
        Parsed pulse_specs.json (may be empty if file absent).
    cqed_params : dict
        Parsed cqed_params.json (may be empty if file absent).
    build_hash : str
        First 12 hex characters of SHA-256 of all config file contents
        (hardware + calibration + pulse_specs + cqed_params).
    git_commit : str
        Short git commit hash at session creation, or empty string.
    """

    config_dir: str
    hardware_config: dict
    calibration_data: dict
    pulse_specs: dict
    cqed_params: dict
    build_hash: str
    git_commit: str = ""

    @classmethod
    def from_config_dir(cls, config_dir: str | Path) -> "SessionState":
        """Load and snapshot all config files in *config_dir*.

        Parameters
        ----------
        config_dir : str | Path
            Directory containing ``hardware.json``, ``calibration.json``,
            and optionally ``pulse_specs.json`` and ``cqed_params.json``.

        Raises
        ------
        FileNotFoundError
            If ``hardware.json`` or ``calibration.json`` do not exist.
        """
        d = Path(config_dir)

        def _load(name: str, required: bool = True) -> dict:
            p = d / name
            if not p.exists():
                if required:
                    raise FileNotFoundError(
                        f"Required config file not found: {p}"
                    )
                return {}
            return json.loads(p.read_bytes())

        hardware = _load("hardware.json", required=True)
        calibration = _load("calibration.json", required=True)
        pulse_specs = _load("pulse_specs.json", required=False)
        cqed_params = _load("cqed_params.json", required=False)

        build_hash = cls._compute_build_hash(hardware, calibration, pulse_specs, cqed_params)
        git_commit = cls._resolve_git_commit(d)

        return cls(
            config_dir=str(d.resolve()),
            hardware_config=hardware,
            calibration_data=calibration,
            pulse_specs=pulse_specs,
            cqed_params=cqed_params,
            build_hash=build_hash,
            git_commit=git_commit,
        )

    @staticmethod
    def _compute_build_hash(
        hardware: dict,
        calibration: dict,
        pulse_specs: dict,
        cqed_params: dict,
    ) -> str:
        """SHA-256 of all config files combined; first 12 hex chars."""
        parts = [
            json.dumps(hardware, sort_keys=True, separators=(",", ":")),
            json.dumps(calibration, sort_keys=True, separators=(",", ":")),
            json.dumps(pulse_specs, sort_keys=True, separators=(",", ":")),
            json.dumps(cqed_params, sort_keys=True, separators=(",", ":")),
        ]
        combined = "\n".join(parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:12]

    @staticmethod
    def _resolve_git_commit(config_dir: Path) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                cwd=str(config_dir),
                timeout=3,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    def summary(self) -> str:
        """Return a human-readable summary."""
        lines = [
            "SessionState",
            f"  config_dir:  {self.config_dir}",
            f"  build_hash:  {self.build_hash}",
            f"  git_commit:  {self.git_commit or '(unknown)'}",
            f"  hardware:    {len(self.hardware_config.get('elements', {}))} elements",
            f"  calibration: version={self.calibration_data.get('version', '?')}",
            f"  pulse_specs: {len(self.pulse_specs.get('specs', {}))} specs"
            if self.pulse_specs else "  pulse_specs: (absent)",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_dir": self.config_dir,
            "hardware_config": self.hardware_config,
            "calibration_data": self.calibration_data,
            "pulse_specs": self.pulse_specs,
            "cqed_params": self.cqed_params,
            "build_hash": self.build_hash,
            "git_commit": self.git_commit,
        }
