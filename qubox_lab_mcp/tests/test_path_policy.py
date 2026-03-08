from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from qubox_lab_mcp.config import ServerConfig
from qubox_lab_mcp.errors import PathAccessError
from qubox_lab_mcp.policies.path_policy import PathPolicy


class PathPolicyTests(unittest.TestCase):
    def test_rejects_path_outside_allowed_root(self) -> None:
        with tempfile.TemporaryDirectory() as root_dir, tempfile.TemporaryDirectory() as other_dir:
            policy = PathPolicy(ServerConfig(allowed_roots=[Path(root_dir)]))
            outside = Path(other_dir) / "secret.txt"
            outside.write_text("x", encoding="utf-8")
            with self.assertRaises(PathAccessError):
                policy.resolve_path(str(outside), must_exist=True, allow_directory=False)

    def test_resolves_relative_path_inside_root(self) -> None:
        with tempfile.TemporaryDirectory() as root_dir:
            root = Path(root_dir)
            file_path = root / "notes.txt"
            file_path.write_text("hello", encoding="utf-8")
            policy = PathPolicy(ServerConfig(allowed_roots=[root]))
            resolved = policy.resolve_path("notes.txt", must_exist=True, allow_directory=False)
            self.assertEqual(resolved, file_path.resolve())


if __name__ == "__main__":
    unittest.main()
