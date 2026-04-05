"""Public pre-flight validation surface.

The implementation lives in :mod:`qubox.core.preflight`; this module exists to
preserve the stable import path used by notebooks and advanced workflows.
"""
from __future__ import annotations

from .core.preflight import preflight_check

__all__ = ["preflight_check"]
