from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from qubox_lab_mcp.config import ServerConfig
from qubox_lab_mcp.policies.path_policy import PathPolicy
from qubox_lab_mcp.policies.safety_policy import SafetyPolicy
from qubox_lab_mcp.adapters.notebook_adapter import NotebookAdapter


class NotebookAdapterTests(unittest.TestCase):
    def test_reads_and_finds_cells(self) -> None:
        with tempfile.TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            nb_path = root / "demo.ipynb"
            nb_path.write_text(
                json.dumps(
                    {
                        "cells": [
                            {"cell_type": "markdown", "source": ["# Title\n", "Workflow"]},
                            {"cell_type": "code", "execution_count": 1, "source": ["import numpy as np\n", "run_wigner()\n"]},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            adapter = NotebookAdapter(PathPolicy(ServerConfig(allowed_roots=[root])), SafetyPolicy(ServerConfig(allowed_roots=[root])))
            summary = adapter.read_notebook("demo.ipynb")
            self.assertEqual(summary.cell_count, 2)
            self.assertIn("Title", summary.headings)
            hits = adapter.find_cells("demo.ipynb", "wigner")
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].index, 2)


if __name__ == "__main__":
    unittest.main()
