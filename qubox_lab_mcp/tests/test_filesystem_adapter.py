from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qubox_lab_mcp.adapters.filesystem_adapter import FilesystemAdapter
from qubox_lab_mcp.config import ServerConfig
from qubox_lab_mcp.errors import BinaryFileError
from qubox_lab_mcp.policies.path_policy import PathPolicy
from qubox_lab_mcp.policies.safety_policy import SafetyPolicy


class FilesystemAdapterTests(unittest.TestCase):
    def test_read_file_respects_line_bounds(self) -> None:
        with tempfile.TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            file_path = root / "code.py"
            file_path.write_text("a\nb\nc\nd\n", encoding="utf-8")
            config = ServerConfig(allowed_roots=[root])
            adapter = FilesystemAdapter(config, PathPolicy(config), SafetyPolicy(config))
            snippet = adapter.read_file("code.py", start_line=2, end_line=3)
            self.assertEqual(snippet.start_line, 2)
            self.assertIn("2: b", snippet.content)
            self.assertIn("3: c", snippet.content)
            self.assertNotIn("1: a", snippet.content)

    def test_binary_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            file_path = root / "data.bin"
            file_path.write_bytes(b"\x00\x01\x02")
            config = ServerConfig(allowed_roots=[root])
            adapter = FilesystemAdapter(config, PathPolicy(config), SafetyPolicy(config))
            with self.assertRaises(BinaryFileError):
                adapter.read_file("data.bin")


if __name__ == "__main__":
    unittest.main()
