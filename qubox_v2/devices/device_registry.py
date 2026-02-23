# qubox_v2/devices/device_registry.py
"""Device and cooldown directory management.

The :class:`DeviceRegistry` manages a structured filesystem layout where
each physical device has its own directory containing device-level config
(hardware, wiring, cqed_params) and per-cooldown subdirectories containing
cooldown-scoped calibrations, pulses, and measurement config.

Layout::

    <base>/devices/<device_id>/
        device.json
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

# Files that live at the device level (shared across cooldowns)
DEVICE_LEVEL_FILES = frozenset({
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
class DeviceInfo:
    """Metadata about a physical device."""

    device_id: str
    description: str = ""
    sample_info: dict[str, Any] = field(default_factory=dict)
    element_map: dict[str, str] = field(default_factory=dict)
    created: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "description": self.description,
            "sample_info": self.sample_info,
            "element_map": self.element_map,
            "created": self.created,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DeviceInfo:
        return cls(
            device_id=str(d.get("device_id", "")),
            description=str(d.get("description", "")),
            sample_info=dict(d.get("sample_info", {})),
            element_map=dict(d.get("element_map", {})),
            created=str(d.get("created", "")),
        )


class DeviceRegistry:
    """Manage device and cooldown directory trees.

    Parameters
    ----------
    base_path : Path
        Root directory containing the ``devices/`` folder.
    """

    def __init__(self, base_path: str | Path) -> None:
        self._base = Path(base_path)
        self._devices_root = self._base / "devices"

    @property
    def base_path(self) -> Path:
        return self._base

    # ------------------------------------------------------------------
    # Device operations
    # ------------------------------------------------------------------
    def device_path(self, device_id: str) -> Path:
        """Return the directory path for a device."""
        return self._devices_root / device_id

    def device_exists(self, device_id: str) -> bool:
        return (self._devices_root / device_id / "device.json").exists()

    def list_devices(self) -> list[str]:
        """Return sorted list of device IDs."""
        if not self._devices_root.exists():
            return []
        return sorted(
            d.name for d in self._devices_root.iterdir()
            if d.is_dir() and (d / "device.json").exists()
        )

    def load_device_info(self, device_id: str) -> DeviceInfo:
        """Load device metadata from device.json."""
        info_path = self._devices_root / device_id / "device.json"
        if not info_path.exists():
            raise FileNotFoundError(f"Device '{device_id}' not found at {info_path}")
        raw = json.loads(info_path.read_text(encoding="utf-8"))
        return DeviceInfo.from_dict(raw)

    def create_device(
        self,
        device_id: str,
        *,
        description: str = "",
        hardware_source: str | Path | None = None,
        config_source: str | Path | None = None,
        sample_info: dict[str, Any] | None = None,
        element_map: dict[str, str] | None = None,
    ) -> Path:
        """Create a new device directory with config files.

        Parameters
        ----------
        device_id : str
            Unique identifier for the device.
        description : str
            Human-readable description.
        hardware_source : Path, optional
            Path to an existing hardware.json to copy into the device.
        config_source : Path, optional
            Path to a directory containing device-level config files
            to copy (hardware.json, devices.json, cqed_params.json, etc.).
        sample_info : dict, optional
            Arbitrary sample metadata.
        element_map : dict, optional
            Mapping of logical element names to physical element names.

        Returns
        -------
        Path
            Path to the created device directory.
        """
        dev_dir = self._devices_root / device_id
        config_dir = dev_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Write device.json
        info = DeviceInfo(
            device_id=device_id,
            description=description,
            sample_info=sample_info or {},
            element_map=element_map or {},
            created=datetime.now().isoformat(),
        )
        (dev_dir / "device.json").write_text(
            json.dumps(info.to_dict(), indent=2), encoding="utf-8",
        )

        # Copy config files from source directory
        if config_source is not None:
            src = Path(config_source)
            for fname in DEVICE_LEVEL_FILES:
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

        _logger.info("Created device '%s' at %s", device_id, dev_dir)
        return dev_dir

    # ------------------------------------------------------------------
    # Cooldown operations
    # ------------------------------------------------------------------
    def cooldown_path(self, device_id: str, cooldown_id: str) -> Path:
        """Return the directory path for a cooldown."""
        return self._devices_root / device_id / "cooldowns" / cooldown_id

    def list_cooldowns(self, device_id: str) -> list[str]:
        """Return sorted list of cooldown IDs for a device."""
        cd_root = self._devices_root / device_id / "cooldowns"
        if not cd_root.exists():
            return []
        return sorted(
            d.name for d in cd_root.iterdir()
            if d.is_dir() and (d / "config").exists()
        )

    def cooldown_exists(self, device_id: str, cooldown_id: str) -> bool:
        cd_dir = self.cooldown_path(device_id, cooldown_id)
        return (cd_dir / "config").exists()

    def create_cooldown(
        self,
        device_id: str,
        cooldown_id: str,
        *,
        seed_from: str | Path | None = None,
    ) -> Path:
        """Create a new cooldown directory.

        Parameters
        ----------
        device_id : str
            The parent device.
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
        if not self.device_exists(device_id):
            raise FileNotFoundError(
                f"Device '{device_id}' does not exist. Create it first."
            )

        cd_dir = self.cooldown_path(device_id, cooldown_id)
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
            device_id, cooldown_id, cd_dir,
        )
        return cd_dir

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------
    def resolve_config_paths(
        self, device_id: str, cooldown_id: str,
    ) -> dict[str, Path]:
        """Resolve config file paths for a device+cooldown combination.

        Device-level files come from ``<device>/config/``.
        Cooldown-level files come from ``<cooldown>/config/``.

        Returns
        -------
        dict[str, Path]
            Mapping of filename → resolved path. Only files that
            exist on disk are included.
        """
        dev_cfg = self.device_path(device_id) / "config"
        cd_cfg = self.cooldown_path(device_id, cooldown_id) / "config"

        paths: dict[str, Path] = {}
        for fname in DEVICE_LEVEL_FILES:
            p = dev_cfg / fname
            if p.exists():
                paths[fname] = p
        for fname in COOLDOWN_LEVEL_FILES:
            p = cd_cfg / fname
            if p.exists():
                paths[fname] = p

        return paths
