# qubox_v2/core/config.py
"""
Pydantic v2 models for typed, validated hardware configuration.

Replaces raw-dict manipulation with structured objects that catch
key typos and type errors at load time.  Every model round-trips
through JSON / dict for QM compatibility.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------
class AnalogPort(BaseModel):
    offset: float = 0.0

class ControllerConfig(BaseModel):
    """One OPX+ controller (e.g. 'con1')."""
    analog_outputs: Dict[int, AnalogPort] = Field(default_factory=dict)
    digital_outputs: Dict[int, dict] = Field(default_factory=dict)
    analog_inputs: Dict[int, AnalogPort] = Field(default_factory=dict)

    @field_validator("analog_outputs", "digital_outputs", "analog_inputs", mode="before")
    @classmethod
    def coerce_int_keys(cls, v):
        if isinstance(v, dict):
            return {int(k): val for k, val in v.items()}
        return v


# ---------------------------------------------------------------------------
# Octave
# ---------------------------------------------------------------------------
class OctaveRFOutput(BaseModel):
    LO_frequency: float
    LO_source: Literal["internal", "external"] = "internal"
    output_mode: str = "always_on"
    gain: float = 0.0

class OctaveRFInput(BaseModel):
    RF_source: str = "RF_in"
    LO_frequency: Optional[float] = None

class OctaveConfig(BaseModel):
    """One Octave unit (e.g. 'oct1')."""
    RF_outputs: Dict[int, OctaveRFOutput] = Field(default_factory=dict)
    RF_inputs: Dict[int, OctaveRFInput] = Field(default_factory=dict)
    connectivity: str = "con1"

    @field_validator("RF_outputs", "RF_inputs", mode="before")
    @classmethod
    def coerce_int_keys(cls, v):
        if isinstance(v, dict):
            return {int(k): val for k, val in v.items()}
        return v


# ---------------------------------------------------------------------------
# Element
# ---------------------------------------------------------------------------
class ElementConfig(BaseModel):
    """One QM element (e.g. 'resonator', 'qubit', 'storage')."""
    RF_inputs: Dict[str, Any] = Field(default_factory=dict)
    RF_outputs: Optional[Dict[str, Any]] = None
    intermediate_frequency: float = 0.0
    digitalInputs: Optional[Dict[str, Any]] = None
    time_of_flight: Optional[int] = None
    operations: Dict[str, str] = Field(default_factory=dict)
    type: Optional[str] = None


# ---------------------------------------------------------------------------
# __qubox extras
# ---------------------------------------------------------------------------
class ExternalLOEntry(BaseModel):
    """Maps an octave RF output to an external LO device + port."""
    device: str
    lo_port: str  # e.g. "LO2"

class OctaveLink(BaseModel):
    """Maps octave RF port → controller analog outputs (for simulator relabeling)."""
    octave: str
    rf_out: int
    controller: str
    ao_i: int
    ao_q: int

class QuboxExtras(BaseModel):
    """The __qubox section of hardware.json."""
    external_lo_map: Dict[str, Union[ExternalLOEntry, str]] = Field(default_factory=dict)
    octave_links: List[OctaveLink] = Field(default_factory=list)
    bindings: Dict[str, Any] = Field(default_factory=dict)
    aliases: Dict[str, Any] = Field(default_factory=dict)
    binding_bundle: Dict[str, Any] = Field(default_factory=dict)
    alias_map: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}

    @field_validator("external_lo_map", mode="before")
    @classmethod
    def normalize_lo_map(cls, v):
        """Accept both legacy string and dict formats."""
        out = {}
        for key, val in (v or {}).items():
            if isinstance(val, str):
                out[key] = ExternalLOEntry(device=val, lo_port="")
            elif isinstance(val, dict):
                out[key] = ExternalLOEntry(**val)
            else:
                out[key] = val
        return out


# ---------------------------------------------------------------------------
# Top-level Hardware Config
# ---------------------------------------------------------------------------
class HardwareConfig(BaseModel):
    """
    Complete typed representation of hardware.json.

    Usage:
        cfg = HardwareConfig.from_json("config/hardware.json")
        cfg.controllers["con1"].analog_outputs[1].offset = -0.002
        cfg.save_json("config/hardware.json")
        qm_dict = cfg.to_qm_dict()
    """
    version: int = 1
    controllers: Dict[str, ControllerConfig] = Field(default_factory=dict)
    octaves: Dict[str, OctaveConfig] = Field(default_factory=dict)
    elements: Dict[str, ElementConfig] = Field(default_factory=dict)
    qubox_extras: Optional[QuboxExtras] = Field(default=None, alias="__qubox")

    model_config = {"populate_by_name": True, "extra": "allow"}

    # --- I/O helpers ---
    @classmethod
    def from_json(cls, path: str | Path) -> HardwareConfig:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return cls.model_validate(raw)

    @classmethod
    def from_dict(cls, d: dict) -> HardwareConfig:
        return cls.model_validate(d)

    def save_json(self, path: str | Path) -> None:
        Path(path).write_text(
            self.model_dump_json(indent=2, by_alias=True, exclude_none=True),
            encoding="utf-8",
        )

    def to_qm_dict(self) -> dict:
        """
        Export to the raw dict format expected by QuantumMachinesManager.open_qm().
        Strips __qubox extras (QM doesn't understand them).
        """
        d = self.model_dump(by_alias=True, exclude_none=True)
        d.pop("__qubox", None)
        return d

    def get_qubox_extras(self) -> QuboxExtras:
        """Return the __qubox section (or empty defaults)."""
        return self.qubox_extras if self.qubox_extras is not None else QuboxExtras()
