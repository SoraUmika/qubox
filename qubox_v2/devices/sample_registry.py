# qubox_v2/devices/sample_registry.py
"""Sample and cooldown directory management.

The :class:`SampleRegistry` manages a structured filesystem layout where
each physical sample has its own directory containing sample-level config
(hardware, wiring, cqed_params) and per-cooldown subdirectories containing
cooldown-scoped calibrations, pulses, and measurement config.

Layout::

    <base>/samples/<sample_id>/
        sample.json
        config/  (hardware.json, devices.json, cqed_params.json, pulse_specs.json)
        cooldowns/<cooldown_id>/
            config/  (calibration.json, pulses.json, measureConfig.json)
            data/
            artifacts/
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..core.logging import get_logger

_logger = get_logger(__name__)

# Files that live at the sample level (shared across cooldowns)
SAMPLE_LEVEL_FILES = frozenset({
    "hardware.json",
    "devices.json",
    "cqed_params.json",
    "pulse_specs.json",
})

# Files that are cooldown-scoped
COOLDOWN_LEVEL_FILES = frozenset({
    "calibration.json",
    "pulses.json",
    "measureConfig.json",
    "session_runtime.json",
})


@dataclass
class SampleInfo:
    """Metadata about a physical sample."""

    sample_id: str
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    element_map: dict[str, str] = field(default_factory=dict)
    created: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "description": self.description,
            "metadata": self.metadata,
            "element_map": self.element_map,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SampleInfo:
        return cls(
            sample_id=str(d.get("sample_id", "")),
            description=str(d.get("description", "")),
            metadata=dict(d.get("metadata", {})),
            element_map=dict(d.get("element_map", {})),
            created=str(d.get("created", "")),
        )


class SampleRegistry:
    """Manage sample and cooldown directory trees.

    Parameters
    ----------
    base_path : Path
        Root directory containing the ``samples/`` folder.
    """

    def __init__(self, base_path: str | Path) -> None:
        self._base = Path(base_path)
        self._samples_root = self._base / "samples"

    @property
    def base_path(self) -> Path:
        return self._base

    # ------------------------------------------------------------------
    # Sample operations
    # ------------------------------------------------------------------
    def sample_path(self, sample_id: str) -> Path:
        """Return the directory path for a sample."""
        return self._samples_root / sample_id

    def sample_exists(self, sample_id: str) -> bool:
        sample_dir = self._samples_root / sample_id
        return (sample_dir / "sample.json").exists()

    def list_samples(self) -> list[str]:
        """Return sorted list of sample IDs."""
        if not self._samples_root.exists():
            return []
        return sorted(
            d.name for d in self._samples_root.iterdir()
            if d.is_dir() and (d / "sample.json").exists()
        )

    def load_sample_info(self, sample_id: str) -> SampleInfo:
        """Load sample metadata from sample.json."""
        sample_dir = self._samples_root / sample_id
        info_path = sample_dir / "sample.json"
        if not info_path.exists():
            raise FileNotFoundError(f"Sample '{sample_id}' not found at {sample_dir}")
        raw = json.loads(info_path.read_text(encoding="utf-8"))
        return SampleInfo.from_dict(raw)

    def create_sample(
        self,
        sample_id: str,
        *,
        description: str = "",
        hardware_source: str | Path | None = None,
        config_source: str | Path | None = None,
        metadata: dict[str, Any] | None = None,
        element_map: dict[str, str] | None = None,
    ) -> Path:
        """Create a new sample directory with config files.

        Parameters
        ----------
        sample_id : str
            Unique identifier for the sample.
        description : str
            Human-readable description.
        hardware_source : Path, optional
            Path to an existing hardware.json to copy into the sample.
        config_source : Path, optional
            Path to a directory containing sample-level config files
            to copy (hardware.json, devices.json, cqed_params.json, etc.).
        metadata : dict, optional
            Arbitrary sample metadata.
        element_map : dict, optional
            Mapping of logical element names to physical element names.

        Returns
        -------
        Path
            Path to the created sample directory.
        """
        sample_dir = self._samples_root / sample_id
        config_dir = sample_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Write sample.json
        info = SampleInfo(
            sample_id=sample_id,
            description=description,
            metadata=metadata or {},
            element_map=element_map or {},
            created=datetime.now().isoformat(),
        )
        (sample_dir / "sample.json").write_text(
            json.dumps(info.to_dict(), indent=2), encoding="utf-8",
        )

        # Copy config files from source directory
        if config_source is not None:
            src = Path(config_source)
            for fname in SAMPLE_LEVEL_FILES:
                src_file = src / fname
                if src_file.exists():
                    shutil.copy2(src_file, config_dir / fname)
                    _logger.info("Copied %s → %s", src_file, config_dir / fname)

        # Override hardware.json from explicit source
        if hardware_source is not None:
            hw_src = Path(hardware_source)
            if hw_src.exists():
                shutil.copy2(hw_src, config_dir / "hardware.json")
                _logger.info("Copied hardware.json from %s", hw_src)

        _logger.info("Created sample '%s' at %s", sample_id, sample_dir)
        return sample_dir

    # ------------------------------------------------------------------
    # Cooldown operations
    # ------------------------------------------------------------------
    def cooldown_path(self, sample_id: str, cooldown_id: str) -> Path:
        """Return the directory path for a cooldown."""
        return self._samples_root / sample_id / "cooldowns" / cooldown_id

    def list_cooldowns(self, sample_id: str) -> list[str]:
        """Return sorted list of cooldown IDs for a sample."""
        cd_root = self._samples_root / sample_id / "cooldowns"
        if not cd_root.exists():
            return []
        return sorted(
            d.name for d in cd_root.iterdir()
            if d.is_dir() and (d / "config").exists()
        )

    def cooldown_exists(self, sample_id: str, cooldown_id: str) -> bool:
        cd_dir = self.cooldown_path(sample_id, cooldown_id)
        return (cd_dir / "config").exists()

    def create_cooldown(
        self,
        sample_id: str,
        cooldown_id: str,
        *,
        seed_from: str | Path | None = None,
    ) -> Path:
        """Create a new cooldown directory.

        Parameters
        ----------
        sample_id : str
            The parent sample.
        cooldown_id : str
            Unique identifier for this cooldown cycle.
        seed_from : Path, optional
            Path to a directory containing cooldown-level config files
            to copy as initial state (calibration.json, pulses.json, etc.).

        Returns
        -------
        Path
            Path to the created cooldown directory.
        """
        if not self.sample_exists(sample_id):
            raise FileNotFoundError(
                f"Sample '{sample_id}' does not exist. Create it first."
            )

        cd_dir = self.cooldown_path(sample_id, cooldown_id)
        config_dir = cd_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (cd_dir / "data").mkdir(exist_ok=True)
        (cd_dir / "artifacts").mkdir(exist_ok=True)

        # Copy seed config files
        if seed_from is not None:
            src = Path(seed_from)
            for fname in COOLDOWN_LEVEL_FILES:
                src_file = src / fname
                if src_file.exists():
                    shutil.copy2(src_file, config_dir / fname)
                    _logger.info("Seeded %s → %s", src_file, config_dir / fname)

        _logger.info(
            "Created cooldown '%s/%s' at %s",
            sample_id, cooldown_id, cd_dir,
        )
        return cd_dir

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------
    def resolve_config_paths(
        self, sample_id: str, cooldown_id: str,
    ) -> dict[str, Path]:
        """Resolve config file paths for a sample+cooldown combination.

        Sample-level files come from ``<sample>/config/``.
        Cooldown-level files come from ``<cooldown>/config/``.

        Returns
        -------
        dict[str, Path]
            Mapping of filename → resolved path. Only files that
            exist on disk are included.
        """
        sample_cfg = self.sample_path(sample_id) / "config"
        cd_cfg = self.cooldown_path(sample_id, cooldown_id) / "config"

        paths: dict[str, Path] = {}
        for fname in SAMPLE_LEVEL_FILES:
            p = sample_cfg / fname
            if p.exists():
                paths[fname] = p
        for fname in COOLDOWN_LEVEL_FILES:
            p = cd_cfg / fname
            if p.exists():
                paths[fname] = p

        return paths
