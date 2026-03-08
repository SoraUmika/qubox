"""Content safety helpers for read-mostly server operations."""
from __future__ import annotations

import re
from pathlib import Path

from ..config import ServerConfig
from ..errors import BinaryFileError, LimitExceededError

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(token|secret|password|passwd|api[_-]?key|access[_-]?key|private[_-]?key)\s*[:=]\s*([\"']?)([^\s\"']+)(\2)"
)


class SafetyPolicy:
    def __init__(self, config: ServerConfig) -> None:
        self.config = config

    def ensure_size_allowed(self, path: Path) -> None:
        size = path.stat().st_size
        if size > self.config.limits.max_file_bytes:
            raise LimitExceededError(
                "File exceeds configured size limit",
                path=str(path),
                size_bytes=size,
                max_file_bytes=self.config.limits.max_file_bytes,
            )

    def reject_binary(self, path: Path) -> None:
        suffix = path.suffix.lower()
        if suffix and suffix not in self.config.text_extensions:
            sample = path.read_bytes()[:4096]
            if b"\x00" in sample:
                raise BinaryFileError("Binary file access is not allowed", path=str(path))
            try:
                sample.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise BinaryFileError("Unsupported binary or non-UTF-8 file", path=str(path)) from exc
            return

        sample = path.read_bytes()[:4096]
        if b"\x00" in sample:
            raise BinaryFileError("Binary file access is not allowed", path=str(path))

    def redact_text(self, text: str) -> str:
        def repl(match: re.Match[str]) -> str:
            prefix = match.group(1)
            value = match.group(3)
            return match.group(0).replace(value, "***REDACTED***") if value else match.group(0)

        return _SECRET_ASSIGNMENT.sub(repl, text)

    def trim_text(self, text: str, *, max_chars: int | None = None) -> tuple[str, bool]:
        limit = max_chars or self.config.limits.max_resource_chars
        if len(text) <= limit:
            return text, False
        return text[:limit] + "\n...<truncated>...", True
