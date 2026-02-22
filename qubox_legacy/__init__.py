# qubox/__init__.py
from .logging_config import configure_global_logging, get_logger

# Configure once on import (you can pick a default level here)
configure_global_logging(level="INFO")

__all__ = [
    "configure_global_logging",
    "get_logger",
    # ... your other public symbols
]
