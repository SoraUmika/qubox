from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

from qubox.core.device_metadata import DeviceMetadata


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_tool_module(filename: str):
    path = REPO_ROOT / "tools" / filename
    module_name = f"_tool_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("filename", "temp_dir_name"),
    [
        ("validate_circuit_runner_serialization.py", ".tmp_serialization_validation"),
        ("validate_gate_tuning_visualization.py", ".tmp_gate_tuning_validation"),
    ],
)
def test_validation_tools_build_device_metadata_context(filename: str, temp_dir_name: str) -> None:
    module = _load_tool_module(filename)

    session = module._load_local_session(
        repo_root=REPO_ROOT,
        sample_id="post_cavity_sample_A",
        cooldown_id="cd_2025_02_22",
    )
    ctx = session.context_snapshot()

    assert isinstance(ctx, DeviceMetadata)
    assert ctx.qb_el == "transmon"
    assert ctx.ro_el == "resonator"
    assert ctx.qb_fq is not None
    assert ctx.ro_fq is not None
    assert session.bindings.readout.drive_frequency == pytest.approx(ctx.ro_fq)

    shutil.rmtree(REPO_ROOT / temp_dir_name, ignore_errors=True)
