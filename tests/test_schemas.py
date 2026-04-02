from __future__ import annotations

import json

from qubox.devices.device_manager import DeviceManager, DeviceSpec
from qubox.core.hardware_definition import HardwareDefinition
from qubox.schemas import validate_schema


def test_validate_devices_schema_accepts_flat_runtime_map(tmp_path):
    result = validate_schema(
        tmp_path / "devices.json",
        "devices",
        data={
            "sa124b": {
                "driver": "instrumentserver:Instrument",
                "backend": "instrumentserver",
                "connect": {"host": "127.0.0.1", "port": 1234},
                "settings": {},
                "enabled": True,
            }
        },
    )

    assert result.valid is True
    assert result.errors == []


def test_validate_devices_schema_accepts_wrapped_device_map(tmp_path):
    result = validate_schema(
        tmp_path / "devices.json",
        "devices",
        data={
            "schema_version": 1,
            "devices": {
                "sa124b": {
                    "driver": "instrumentserver:Instrument",
                    "backend": "instrumentserver",
                    "connect": {"host": "127.0.0.1", "port": 1234},
                    "settings": {},
                    "enabled": True,
                }
            },
        },
    )

    assert result.valid is True
    assert result.errors == []


def test_hardware_definition_emits_version_and_default_operations(tmp_path):
    hw = HardwareDefinition(controller="con1", octave="oct1")
    hw.add_readout(
        "resonator",
        rf_out=1,
        rf_in=1,
        lo_frequency=8.8e9,
        frequency=8.75e9,
    )
    hw.add_control(
        "transmon",
        rf_out=3,
        lo_frequency=6.2e9,
        frequency=6.15e9,
    )

    payload = hw.to_hardware_dict()

    assert payload["version"] == 1
    assert payload["elements"]["resonator"]["operations"] == {
        "const": "const_pulse",
        "zero": "zero_pulse",
    }
    assert payload["elements"]["transmon"]["operations"] == {
        "const": "const_pulse",
        "zero": "zero_pulse",
    }
    assert payload["__qubox"]["bindings"]["outputs"]["resonator"]["operations"] == {
        "const": "const_pulse",
        "zero": "zero_pulse",
    }

    result = validate_schema(tmp_path / "hardware.json", "hardware", data=payload)

    assert result.valid is True
    assert "File 'hardware.json' has no 'version' field, assuming v1" not in result.warnings
    assert "Element 'resonator' missing 'const' operation" not in result.warnings
    assert "Element 'resonator' missing 'zero' operation" not in result.warnings
    assert "Element 'transmon' missing 'const' operation" not in result.warnings
    assert "Element 'transmon' missing 'zero' operation" not in result.warnings


def test_hardware_definition_devices_include_schema_version(tmp_path):
    hw = HardwareDefinition(controller="con1", octave="oct1")
    hw.set_instrument_server("127.0.0.1", 50183)
    hw.add_device("sa124b", instrument_name="sa124b_20234880", settings={})

    payload = hw.to_devices_dict()

    assert payload["schema_version"] == 1
    assert "sa124b" in payload

    result = validate_schema(tmp_path / "devices.json", "devices", data=payload)

    assert result.valid is True
    assert result.warnings == []


def test_device_manager_loads_schema_versioned_flat_device_map(tmp_path):
    config_path = tmp_path / "devices.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sa124b": {
                    "driver": "instrumentserver:Instrument",
                    "backend": "instrumentserver",
                    "connect": {"host": "127.0.0.1", "port": 50183},
                    "settings": {},
                    "enabled": True,
                },
            }
        ),
        encoding="utf-8",
    )

    manager = DeviceManager(config_path)

    assert list(manager.specs) == ["sa124b"]


def test_device_manager_save_preserves_schema_version(tmp_path):
    config_path = tmp_path / "devices.json"
    manager = DeviceManager(config_path)
    manager.specs["sa124b"] = DeviceSpec(
        name="sa124b",
        driver="instrumentserver:Instrument",
        backend="instrumentserver",
        connect={"host": "127.0.0.1", "port": 50183},
        settings={},
        enabled=True,
    )

    manager.save()

    payload = json.loads(config_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert "sa124b" in payload