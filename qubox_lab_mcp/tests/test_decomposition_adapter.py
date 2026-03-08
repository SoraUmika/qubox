from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qubox_lab_mcp.adapters.decomposition_adapter import DecompositionAdapter
from qubox_lab_mcp.adapters.json_adapter import JsonAdapter
from qubox_lab_mcp.config import ServerConfig
from qubox_lab_mcp.policies.path_policy import PathPolicy
from qubox_lab_mcp.policies.safety_policy import SafetyPolicy


class DecompositionAdapterTests(unittest.TestCase):
    def test_flags_suspicious_theta(self) -> None:
        with tempfile.TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            artifact = root / "decomp.json"
            artifact.write_text(
                json.dumps(
                    {
                        "sequence": [
                            {"type": "SQR", "target": "transmon", "params": {"theta": 4.0}},
                            {"type": "SNAP", "target": "storage", "params": {"theta": 0.1}},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            config = ServerConfig(allowed_roots=[root])
            adapter = DecompositionAdapter(JsonAdapter(PathPolicy(config), SafetyPolicy(config)))
            issues = adapter.flag_parameter_issues("decomp.json")
            self.assertTrue(any("theta" in issue.path for issue in issues))
            meta = adapter.estimate_sequence_metadata("decomp.json")
            self.assertEqual(meta.total_steps, 2)
            self.assertEqual(meta.gate_types["SQR"], 1)


if __name__ == "__main__":
    unittest.main()
