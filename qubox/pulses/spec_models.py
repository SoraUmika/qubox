"""Pydantic models for declarative pulse specifications.

These models define the schema for ``pulse_specs.json``. They are used
for validation during load and for generating specs during migration.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Constraint model
# ---------------------------------------------------------------------------

class PulseConstraints(BaseModel):
    """Post-generation constraints applied to waveform arrays."""
    max_amplitude: float = 0.45
    normalize_area: bool = False
    pad_to_multiple_of: int = 4
    clip: bool = True


# ---------------------------------------------------------------------------
# Shape-specific parameter models
# ---------------------------------------------------------------------------

class ConstantParams(BaseModel):
    amplitude_I: float = 0.0
    amplitude_Q: float = 0.0
    length: int

    @field_validator("length")
    @classmethod
    def length_positive(cls, v: int) -> int:
        if v < 4:
            raise ValueError(f"length must be >= 4, got {v}")
        return v


class ZeroParams(BaseModel):
    length: int = 16


class DragGaussianParams(BaseModel):
    amplitude: float
    length: int
    sigma: float
    drag_coeff: float = 0.0
    anharmonicity: float = 0.0
    detuning: float = 0.0
    subtracted: bool = True


class DragCosineParams(BaseModel):
    amplitude: float
    length: int
    alpha: float = 0.0
    anharmonicity: float = 0.0
    detuning: float = 0.0


class KaiserParams(BaseModel):
    amplitude: float
    length: int
    beta: float
    detuning: float = 0.0
    alpha: float = 0.0
    anharmonicity: float = 0.0


class SlepianParams(BaseModel):
    amplitude: float
    length: int
    NW: float
    detuning: float = 0.0
    alpha: float = 0.0
    anharmonicity: float = 0.0


class FlattopParams(BaseModel):
    """Common params for all flat-top shapes."""
    amplitude: float
    flat_length: int
    rise_fall_length: int


class CLEARParams(BaseModel):
    t_duration: int
    t_kick: int | list[int]
    A_steady: float
    A_rise_hi: float
    A_rise_lo: float
    A_fall_lo: float
    A_fall_hi: float


class RotationDerivedParams(BaseModel):
    reference_spec: str
    theta: float = 3.141592653589793  # pi
    phi: float = 0.0
    d_lambda: float = 0.0
    d_alpha: float = 0.0
    d_omega: float = 0.0


class ArbitraryBlobParams(BaseModel):
    """Transitional format for non-declarative waveforms."""
    I_samples_b64: str = ""
    Q_samples_b64: str = ""
    length: int = 16


# ---------------------------------------------------------------------------
# Measurement metadata
# ---------------------------------------------------------------------------

class MeasurementMetadata(BaseModel):
    """Additional metadata for measurement-type pulses."""
    pulse_type: Literal["measurement"] = "measurement"
    digital_marker: str = "ON"
    int_weights_mapping: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Spec entry
# ---------------------------------------------------------------------------

VALID_SHAPES = {
    "constant", "zero", "drag_gaussian", "drag_cosine",
    "kaiser", "slepian",
    "flattop_gaussian", "flattop_cosine", "flattop_tanh", "flattop_blackman",
    "clear", "rotation_derived", "arbitrary_blob",
}


class PulseSpecEntry(BaseModel):
    """A single pulse specification."""

    model_config = ConfigDict(extra="allow")

    shape: str
    element: str
    op: str
    transition: str | None = None  # "ge" or "ef"; None treated as "ge"
    params: dict[str, Any] = Field(default_factory=dict)
    constraints: PulseConstraints | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("shape")
    @classmethod
    def shape_valid(cls, v: str) -> str:
        if v not in VALID_SHAPES:
            raise ValueError(
                f"Unknown shape '{v}'. Valid shapes: {sorted(VALID_SHAPES)}"
            )
        return v


# ---------------------------------------------------------------------------
# Integration weight models
# ---------------------------------------------------------------------------

class ConstantWeightDef(BaseModel):
    type: Literal["constant"] = "constant"
    cosine: float = 1.0
    sine: float = 0.0
    length: int = 400


class SegmentedWeightDef(BaseModel):
    type: Literal["segmented"] = "segmented"
    cosine_segments: list[list[float]] = Field(default_factory=list)
    sine_segments: list[list[float]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level file model
# ---------------------------------------------------------------------------

class PulseSpecFile(BaseModel):
    """Root model for ``pulse_specs.json``."""

    schema_version: int = 1
    specs: dict[str, PulseSpecEntry] = Field(default_factory=dict)
    integration_weights: dict[str, dict[str, Any]] = Field(default_factory=dict)
    element_operations: dict[str, dict[str, str]] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def version_supported(cls, v: int) -> int:
        if v not in (1,):
            raise ValueError(f"Unsupported schema_version {v}. Supported: [1]")
        return v

    def validate_completeness(self, required_elements: list[str] | None = None) -> list[str]:
        """Check that all required elements have const and zero specs.

        Returns list of warnings (empty = all good).
        """
        warnings_list = []
        elements_in_specs = set()
        for name, spec in self.specs.items():
            elements_in_specs.add(spec.element)

        check_elements = required_elements or list(elements_in_specs)

        for el in check_elements:
            el_ops = {s.op for s in self.specs.values() if s.element == el}
            if "const" not in el_ops:
                warnings_list.append(f"Element '{el}' missing 'const' operation spec")
            if "zero" not in el_ops:
                warnings_list.append(f"Element '{el}' missing 'zero' operation spec")

        return warnings_list
