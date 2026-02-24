# qubox_v2/devices/__init__.py
"""External device management (SignalCore, OctoDac, etc.) and sample registry."""
from .device_manager import DeviceSpec, DeviceHandle, DeviceManager, DeviceError
from .sample_registry import SampleRegistry, SampleInfo, SAMPLE_LEVEL_FILES, COOLDOWN_LEVEL_FILES
from .context_resolver import ContextResolver

# Backward compatibility aliases
DeviceRegistry = SampleRegistry
DeviceInfo = SampleInfo

__all__ = [
    "DeviceSpec", "DeviceHandle", "DeviceManager", "DeviceError",
    "SampleRegistry", "SampleInfo", "SAMPLE_LEVEL_FILES", "COOLDOWN_LEVEL_FILES",
    "DeviceRegistry", "DeviceInfo",  # backward compat aliases
    "ContextResolver",
]
