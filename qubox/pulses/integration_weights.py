"""Integration weight management for readout pulses.

Extracted from PulseOperationManager to provide focused,
single-responsibility weight lifecycle management.
"""
from __future__ import annotations

from typing import Any

from ..core.logging import get_logger

_logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Default weight names (canonical readout)
# ---------------------------------------------------------------------------
READOUT_COS_WEIGHT = "readout_cosine_weights"
READOUT_SIN_WEIGHT = "readout_sine_weights"
READOUT_MINUS_WEIGHT = "readout_minus_weights"

_RESERVED_WEIGHT_NAMES = frozenset({
    READOUT_COS_WEIGHT,
    READOUT_SIN_WEIGHT,
    READOUT_MINUS_WEIGHT,
})


class IntegrationWeightManager:
    """Manages integration weights for readout demodulation.

    Weights are stored as QM-compatible dicts::

        {"cosine": [(amp, length_cc), ...], "sine": [(amp, length_cc), ...]}

    The manager initializes default weights for the canonical readout pulse.
    Reserved weight names can only be updated via :meth:`update`, not
    created/overwritten via :meth:`add`.
    """

    def __init__(self, readout_length: int = 1000) -> None:
        self._weights: dict[str, dict[str, list[tuple[float, int]]]] = {}
        self._init_defaults(readout_length)

    def _init_defaults(self, length: int) -> None:
        self._weights[READOUT_COS_WEIGHT] = {
            "cosine": [(1.0, length)],
            "sine": [(0.0, length)],
        }
        self._weights[READOUT_SIN_WEIGHT] = {
            "cosine": [(0.0, length)],
            "sine": [(1.0, length)],
        }
        self._weights[READOUT_MINUS_WEIGHT] = {
            "cosine": [(0.0, length)],
            "sine": [(-1.0, length)],
        }

    # ------------------------------------------------------------------
    # Add / update / remove
    # ------------------------------------------------------------------
    def add(
        self,
        name: str,
        cosine: list[tuple[float, int]],
        sine: list[tuple[float, int]],
    ) -> None:
        """Add a new integration weight.

        Cannot overwrite reserved weight names; use :meth:`update` instead.
        """
        if name in _RESERVED_WEIGHT_NAMES:
            raise ValueError(
                f"Weight '{name}' is reserved. Use update() to modify it."
            )
        self._validate_segments(cosine, "cosine")
        self._validate_segments(sine, "sine")
        self._weights[name] = {
            "cosine": list(cosine),
            "sine": list(sine),
        }

    def add_simple(
        self,
        name: str,
        cos_val: float,
        sin_val: float,
        length: int,
    ) -> None:
        """Add a single-segment integration weight (convenience)."""
        self.add(name, cosine=[(cos_val, length)], sine=[(sin_val, length)])

    def update(
        self,
        name: str,
        *,
        cosine: list[tuple[float, int]] | None = None,
        sine: list[tuple[float, int]] | None = None,
    ) -> None:
        """Update an existing integration weight (including reserved ones)."""
        if name not in self._weights:
            raise KeyError(f"Weight '{name}' not found.")
        if cosine is not None:
            self._validate_segments(cosine, "cosine")
            self._weights[name]["cosine"] = list(cosine)
        if sine is not None:
            self._validate_segments(sine, "sine")
            self._weights[name]["sine"] = list(sine)

    def remove(self, name: str) -> None:
        """Remove a non-reserved integration weight."""
        if name in _RESERVED_WEIGHT_NAMES:
            raise ValueError(f"Cannot remove reserved weight '{name}'.")
        if name not in self._weights:
            raise KeyError(f"Weight '{name}' not found.")
        del self._weights[name]

    def get(self, name: str) -> dict[str, list[tuple[float, int]]]:
        """Get weight definition by name."""
        if name not in self._weights:
            raise KeyError(f"Weight '{name}' not found.")
        return self._weights[name]

    def exists(self, name: str) -> bool:
        return name in self._weights

    def list_weights(self) -> list[str]:
        return list(self._weights.keys())

    # ------------------------------------------------------------------
    # Default triplet for measurement pulses
    # ------------------------------------------------------------------
    def default_triplet(
        self, length: int, *, suffix: str = ""
    ) -> dict[str, str]:
        """Create or get the standard cos/sin/minus_sin weight triplet.

        If ``suffix`` is provided, creates length-specific weights like
        ``cos_1000_weights``.  Otherwise returns the canonical names.
        """
        if not suffix:
            return {
                "cos": READOUT_COS_WEIGHT,
                "sin": READOUT_SIN_WEIGHT,
                "minus_sin": READOUT_MINUS_WEIGHT,
            }

        names = {
            "cos": f"cos_{suffix}_weights",
            "sin": f"sin_{suffix}_weights",
            "minus_sin": f"minus_sin_{suffix}_weights",
        }

        for label, name in names.items():
            if name not in self._weights:
                if label == "cos":
                    self._weights[name] = {"cosine": [(1.0, length)], "sine": [(0.0, length)]}
                elif label == "sin":
                    self._weights[name] = {"cosine": [(0.0, length)], "sine": [(1.0, length)]}
                else:
                    self._weights[name] = {"cosine": [(0.0, length)], "sine": [(-1.0, length)]}

        return names

    # ------------------------------------------------------------------
    # Merge into config
    # ------------------------------------------------------------------
    def merge_into(self, cfg: dict[str, Any]) -> None:
        """Merge all weights into a QM config dict."""
        cfg.setdefault("integration_weights", {}).update(self._weights)

    def as_dict(self) -> dict[str, dict]:
        return dict(self._weights)

    def load_from_dict(self, d: dict[str, dict]) -> None:
        self._weights.update(d)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_segments(
        segments: list[tuple[float, int]], label: str
    ) -> None:
        if not isinstance(segments, list):
            raise TypeError(f"{label} must be a list of (amplitude, length) tuples.")
        for i, seg in enumerate(segments):
            if not isinstance(seg, (list, tuple)) or len(seg) != 2:
                raise ValueError(f"{label}[{i}] must be a (amplitude, length) tuple.")
            amp, length = seg
            if not isinstance(amp, (int, float)):
                raise ValueError(f"{label}[{i}] amplitude must be numeric.")
            if not isinstance(length, int) or length <= 0:
                raise ValueError(f"{label}[{i}] length must be a positive integer.")
