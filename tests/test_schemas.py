from __future__ import annotations

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