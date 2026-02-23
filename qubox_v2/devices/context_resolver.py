# qubox_v2/devices/context_resolver.py
"""Resolve an ExperimentContext from device registry paths.

The :class:`ContextResolver` bridges the :class:`DeviceRegistry` and
:class:`ExperimentContext` frozen dataclass: given a device_id and
cooldown_id it validates that the device and cooldown exist, computes
the wiring revision from hardware.json, and assembles the context.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..core.experiment_context import ExperimentContext
from ..core.logging import get_logger

_logger = get_logger(__name__)


class ContextResolver:
    """Resolve device + cooldown into an :class:`ExperimentContext`.

    Parameters
    ----------
    registry : DeviceRegistry
        The device registry to query for paths.
    """

    def __init__(self, registry: Any) -> None:
        self._registry = registry

    def resolve(
        self,
        device_id: str,
        cooldown_id: str,
    ) -> ExperimentContext:
        """Build an ExperimentContext from a device and cooldown.

        Parameters
        ----------
        device_id : str
            Must exist in the registry.
        cooldown_id : str
            Must exist under the device.

        Returns
        -------
        ExperimentContext

        Raises
        ------
        FileNotFoundError
            If the device or cooldown does not exist.
        """
        if not self._registry.device_exists(device_id):
            raise FileNotFoundError(
                f"Device '{device_id}' not found in registry at "
                f"{self._registry.base_path}"
            )
        if not self._registry.cooldown_exists(device_id, cooldown_id):
            raise FileNotFoundError(
                f"Cooldown '{cooldown_id}' not found for device '{device_id}'"
            )

        # Compute wiring revision from hardware.json
        paths = self._registry.resolve_config_paths(device_id, cooldown_id)
        hw_path = paths.get("hardware.json")
        wiring_rev = ""
        if hw_path is not None and hw_path.exists():
            wiring_rev = ExperimentContext.compute_wiring_rev(hw_path)

        # Compute config hash from all resolved config files
        config_hash = self._compute_config_hash(paths)

        # Read calibration schema version if calibration file exists
        schema_version = "4.0.0"
        cal_path = paths.get("calibration.json")
        if cal_path is not None and cal_path.exists():
            try:
                cal_data = json.loads(cal_path.read_text(encoding="utf-8"))
                schema_version = str(cal_data.get("version", "4.0.0"))
            except (json.JSONDecodeError, OSError):
                pass

        ctx = ExperimentContext(
            device_id=device_id,
            cooldown_id=cooldown_id,
            wiring_rev=wiring_rev,
            schema_version=schema_version,
            config_hash=config_hash,
        )
        _logger.info(
            "Resolved context: device=%s cooldown=%s wiring=%s",
            device_id, cooldown_id, wiring_rev,
        )
        return ctx

    def resolve_legacy(self, experiment_path: Path) -> ExperimentContext | None:
        """Attempt to build a minimal context from a legacy experiment directory.

        Returns None if hardware.json is not found.
        """
        config_dir = experiment_path / "config"
        if not config_dir.exists():
            config_dir = experiment_path

        hw_path = config_dir / "hardware.json"
        if not hw_path.exists():
            return None

        wiring_rev = ExperimentContext.compute_wiring_rev(hw_path)

        # Derive a device_id from directory name
        device_id = experiment_path.name

        return ExperimentContext(
            device_id=device_id,
            cooldown_id="legacy",
            wiring_rev=wiring_rev,
            schema_version="4.0.0",
            config_hash="",
        )

    @staticmethod
    def _compute_config_hash(paths: dict[str, Path]) -> str:
        """SHA-256 first 12 hex chars over sorted config file contents."""
        h = hashlib.sha256()
        for name in sorted(paths.keys()):
            p = paths[name]
            if p.exists():
                h.update(name.encode())
                h.update(p.read_bytes())
        return h.hexdigest()[:12]
