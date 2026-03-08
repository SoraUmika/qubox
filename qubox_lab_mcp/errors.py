"""Structured errors for the qubox MCP server."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class QuboxMcpError(Exception):
    """Base exception carrying a stable error code and metadata."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class PathAccessError(QuboxMcpError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(code="path_access_denied", message=message, details=details)


class BinaryFileError(QuboxMcpError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(code="binary_file_rejected", message=message, details=details)


class ParsingError(QuboxMcpError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(code="parse_failure", message=message, details=details)


class LimitExceededError(QuboxMcpError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(code="limit_exceeded", message=message, details=details)


class ValidationError(QuboxMcpError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(code="validation_error", message=message, details=details)
