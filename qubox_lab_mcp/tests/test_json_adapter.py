from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qubox_lab_mcp.adapters.json_adapter import JsonAdapter
from qubox_lab_mcp.config import ServerConfig
from qubox_lab_mcp.policies.path_policy import PathPolicy
from qubox_lab_mcp.policies.safety_policy import SafetyPolicy


class JsonAdapterTests(unittest.TestCase):
    def test_compare_json_files_detects_changed_keys(self) -> None:
        with tempfile.TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            a = root / "a.json"
            b = root / "b.json"
            a.write_text(json.dumps({"chi": 1.0, "nested": {"kerr": 2.0}}), encoding="utf-8")
            b.write_text(json.dumps({"chi": 1.5, "nested": {"kerr": 2.0}, "pulse": "ref_r180"}), encoding="utf-8")
            adapter = JsonAdapter(PathPolicy(ServerConfig(allowed_roots=[root])), SafetyPolicy(ServerConfig(allowed_roots=[root])))
            diff = adapter.compare_json_files("a.json", "b.json")
            paths = {entry.path for entry in diff.changes}
            self.assertIn("chi", paths)
            self.assertIn("pulse", paths)


if __name__ == "__main__":
    unittest.main()
