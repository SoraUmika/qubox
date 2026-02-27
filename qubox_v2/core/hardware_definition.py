# qubox_v2/core/hardware_definition.py
"""Notebook-first hardware definition.

Lets users define all hardware elements, LO/IF frequencies, and wiring
in the notebook.  ``HardwareDefinition`` generates the full
``hardware.json`` (controllers, octaves, elements, __qubox, octave_links)
and seeds ``cqed_params.json`` (element names + initial frequencies).

Usage::

    from qubox_v2.core.hardware_definition import HardwareDefinition

    hw = HardwareDefinition(controller="con1", octave="oct1")
    hw.add_readout("resonator", rf_out=1, rf_in=1, lo_frequency=8.8e9, ...)
    hw.add_control("qubit", rf_out=3, lo_frequency=6.2e9, ...)
    hw.set_roles(qubit="qubit", readout="resonator", storage="storage")

    # Pass to SessionManager — hardware.json is auto-generated
    session = SessionManager.from_sample(..., hardware=hw, ...)

On subsequent sessions, the persisted ``hardware.json`` is loaded
automatically and no ``HardwareDefinition`` is needed.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .errors import ConfigError

_logger = logging.getLogger(__name__)

# Default digital input timing (standard OPX switch gate)
_DEFAULT_DI_DELAY = 57
_DEFAULT_DI_BUFFER = 18


# ---------------------------------------------------------------------------
# Internal element representation
# ---------------------------------------------------------------------------
@dataclass
class _ElementDef:
    """Internal description of one hardware element."""

    name: str
    kind: Literal["control", "readout"]
    rf_out: int
    rf_in: int | None = None
    lo_frequency: float = 0.0
    lo_source: Literal["internal", "external"] = "internal"
    frequency: float | None = None
    intermediate_frequency: float = -50e6
    gain: float = 0.0
    time_of_flight: int | None = None
    digital_inputs: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    # Each entry: (port_number, delay, buffer)


# ---------------------------------------------------------------------------
# Public builder
# ---------------------------------------------------------------------------
class HardwareDefinition:
    """Notebook-friendly builder for hardware.json + cqed_params.json.

    Parameters
    ----------
    controller : str
        OPX+ controller name (e.g. ``"con1"``).
    octave : str
        Octave unit name (e.g. ``"oct1"``).
    """

    def __init__(self, controller: str = "con1", octave: str = "oct1") -> None:
        self._controller = controller
        self._octave = octave
        self._elements: dict[str, _ElementDef] = {}
        self._external_los: dict[int, dict[str, str]] = {}
        self._roles: dict[str, str] = {}
        self._adc_offsets: dict[int, float] = {}

    # ------------------------------------------------------------------
    # Builder methods
    # ------------------------------------------------------------------
    def add_readout(
        self,
        name: str,
        *,
        rf_out: int,
        rf_in: int,
        lo_frequency: float,
        frequency: float | None = None,
        intermediate_frequency: float = -50e6,
        gain: float = 0.0,
        time_of_flight: int = 280,
        digital_inputs: dict[str, int | tuple[int, int, int]] | None = None,
        lo_source: Literal["internal", "external"] = "internal",
    ) -> "HardwareDefinition":
        """Add a readout element (paired drive output + acquisition input).

        Parameters
        ----------
        name : str
            Human-friendly element name (e.g. ``"resonator"``).
        rf_out : int
            Octave RF output port (1-5) for the drive path.
        rf_in : int
            Octave RF input port for the acquisition return path.
        lo_frequency : float
            LO frequency in Hz.
        frequency : float, optional
            Absolute RF frequency in Hz.  If provided, the IF is computed
            as ``frequency - lo_frequency``.  If *None*,
            ``intermediate_frequency`` is used directly.
        intermediate_frequency : float
            Default IF when *frequency* is not given (default -50 MHz).
        gain : float
            Octave output gain in dB.
        time_of_flight : int
            Time-of-flight in ns (default 280).
        digital_inputs : dict, optional
            Digital input mapping.  Values are either a bare port number
            ``int`` (uses default delay=57, buffer=18) or a tuple
            ``(port, delay, buffer)`` for full control.
        lo_source : str
            ``"internal"`` or ``"external"`` LO source.
        """
        if name in self._elements:
            raise ConfigError(f"Element '{name}' already defined.")
        self._elements[name] = _ElementDef(
            name=name,
            kind="readout",
            rf_out=rf_out,
            rf_in=rf_in,
            lo_frequency=lo_frequency,
            lo_source=lo_source,
            frequency=frequency,
            intermediate_frequency=intermediate_frequency,
            gain=gain,
            time_of_flight=time_of_flight,
            digital_inputs=_normalize_digital_inputs(digital_inputs),
        )
        return self

    def add_control(
        self,
        name: str,
        *,
        rf_out: int,
        lo_frequency: float,
        frequency: float | None = None,
        intermediate_frequency: float = -50e6,
        gain: float = 0.0,
        digital_inputs: dict[str, int | tuple[int, int, int]] | None = None,
        lo_source: Literal["internal", "external"] = "internal",
    ) -> "HardwareDefinition":
        """Add a control-only element (drive output, no acquisition).

        Parameters
        ----------
        name : str
            Human-friendly element name (e.g. ``"qubit"``).
        rf_out : int
            Octave RF output port (1-5).
        lo_frequency : float
            LO frequency in Hz.
        frequency : float, optional
            Absolute RF frequency in Hz.  IF = frequency - lo_frequency.
        intermediate_frequency : float
            Default IF when *frequency* is not given (default -50 MHz).
        gain : float
            Octave output gain in dB.
        digital_inputs : dict, optional
            Digital input mapping. See :meth:`add_readout`.
        lo_source : str
            ``"internal"`` or ``"external"`` LO source.
        """
        if name in self._elements:
            raise ConfigError(f"Element '{name}' already defined.")
        self._elements[name] = _ElementDef(
            name=name,
            kind="control",
            rf_out=rf_out,
            lo_frequency=lo_frequency,
            lo_source=lo_source,
            frequency=frequency,
            intermediate_frequency=intermediate_frequency,
            gain=gain,
            digital_inputs=_normalize_digital_inputs(digital_inputs),
        )
        return self

    def set_external_lo(
        self, rf_out: int, *, device: str, lo_port: str
    ) -> "HardwareDefinition":
        """Register an external LO device for an RF output port.

        Parameters
        ----------
        rf_out : int
            Octave RF output port that uses this external LO.
        device : str
            Device name in the DeviceManager (e.g. ``"octave_external_lo2"``).
        lo_port : str
            LO port identifier (e.g. ``"LO2"``).
        """
        self._external_los[rf_out] = {"device": device, "lo_port": lo_port}
        return self

    def set_roles(
        self,
        *,
        qubit: str,
        readout: str,
        storage: str | None = None,
    ) -> "HardwareDefinition":
        """Assign element names to experiment roles.

        Parameters
        ----------
        qubit : str
            Element name to use as the qubit drive channel.
        readout : str
            Element name to use as the readout channel.
        storage : str, optional
            Element name to use as the storage cavity channel.
        """
        self._roles = {"qubit": qubit, "readout": readout}
        if storage is not None:
            self._roles["storage"] = storage
        return self

    def set_adc_offsets(
        self, offsets: dict[int, float]
    ) -> "HardwareDefinition":
        """Set ADC analog input DC offsets.

        Parameters
        ----------
        offsets : dict[int, float]
            Mapping of analog input port number to offset in volts.
        """
        self._adc_offsets = dict(offsets)
        return self

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate(self) -> list[str]:
        """Validate the hardware definition.

        Returns
        -------
        list[str]
            Error messages.  Empty list means the definition is valid.
        """
        errors: list[str] = []

        # 1. Required roles
        if "qubit" not in self._roles:
            errors.append("Role 'qubit' is required. Call set_roles().")
        if "readout" not in self._roles:
            errors.append("Role 'readout' is required. Call set_roles().")

        # 2. Role elements must exist
        for role, name in self._roles.items():
            if name and name not in self._elements:
                errors.append(
                    f"Role '{role}' references unknown element '{name}'."
                )

        # 3. Readout element must have rf_in
        readout_name = self._roles.get("readout")
        if readout_name and readout_name in self._elements:
            el = self._elements[readout_name]
            if el.kind != "readout" or el.rf_in is None:
                errors.append(
                    f"Readout element '{readout_name}' must be added "
                    "with add_readout() including rf_in."
                )

        # 4. RF output port conflicts
        port_users: dict[int, list[str]] = {}
        for el in self._elements.values():
            port_users.setdefault(el.rf_out, []).append(el.name)
        for port, users in port_users.items():
            if len(users) > 1:
                errors.append(
                    f"RF output port {port} used by multiple elements: {users}."
                )

        # 5. RF output port range (OPX+ Octave: 1-5)
        for el in self._elements.values():
            if not (1 <= el.rf_out <= 5):
                errors.append(
                    f"Element '{el.name}': rf_out={el.rf_out} outside range 1-5."
                )

        # 6. IF frequency range (OPX+ limit: +/- 400 MHz)
        for el in self._elements.values():
            if_freq = self._compute_if(el)
            if abs(if_freq) > 400e6:
                errors.append(
                    f"Element '{el.name}': IF={if_freq / 1e6:.1f} MHz "
                    "exceeds OPX+ limit of +/- 400 MHz."
                )

        # 7. External LO consistency
        for rf_out, lo_info in self._external_los.items():
            found = False
            for el in self._elements.values():
                if el.rf_out == rf_out:
                    found = True
                    if el.lo_source != "external":
                        errors.append(
                            f"External LO configured for rf_out={rf_out} but "
                            f"element '{el.name}' has lo_source='{el.lo_source}'."
                        )
            if not found:
                errors.append(
                    f"External LO configured for rf_out={rf_out} but "
                    "no element uses that port."
                )

        # 8. LO frequency must be positive
        for el in self._elements.values():
            if el.lo_frequency <= 0:
                errors.append(
                    f"Element '{el.name}': lo_frequency must be positive, "
                    f"got {el.lo_frequency}."
                )

        # 9. Digital input port range
        for el in self._elements.values():
            for di_name, (port, _delay, _buf) in el.digital_inputs.items():
                if not (1 <= port <= 10):
                    errors.append(
                        f"Element '{el.name}' digital input '{di_name}': "
                        f"port={port} out of range 1-10."
                    )

        return errors

    # ------------------------------------------------------------------
    # Generation: hardware.json
    # ------------------------------------------------------------------
    def to_hardware_dict(self) -> dict[str, Any]:
        """Generate the complete hardware.json content.

        Raises
        ------
        ConfigError
            If validation fails.

        Returns
        -------
        dict
            Full hardware.json structure ready for ``json.dumps()``.
        """
        errors = self.validate()
        if errors:
            raise ConfigError(
                "HardwareDefinition validation failed:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        d: dict[str, Any] = {
            "controllers": self._build_controllers(),
            "octaves": self._build_octaves(),
            "elements": self._build_elements(),
        }
        d.update(self._build_qubox_extras())
        d["octave_links"] = self._build_octave_links()
        return d

    # ------------------------------------------------------------------
    # Generation: cqed_params seed
    # ------------------------------------------------------------------
    def to_cqed_seed(self) -> dict[str, Any]:
        """Generate seed cqed_params.json content.

        Only produces element names and initial frequencies.
        Physics parameters (chi, kappa, T1, T2, etc.) are intentionally
        omitted — they come from calibration experiments.
        """
        seed: dict[str, Any] = {}

        readout_name = self._roles.get("readout")
        qubit_name = self._roles.get("qubit")
        storage_name = self._roles.get("storage")

        seed["ro_el"] = readout_name
        seed["qb_el"] = qubit_name
        if storage_name:
            seed["st_el"] = storage_name

        if readout_name and readout_name in self._elements:
            seed["ro_fq"] = self._element_rf_frequency(self._elements[readout_name])

        if qubit_name and qubit_name in self._elements:
            seed["qb_fq"] = self._element_rf_frequency(self._elements[qubit_name])

        if storage_name and storage_name in self._elements:
            seed["st_fq"] = self._element_rf_frequency(self._elements[storage_name])

        return seed

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def save_hardware(self, path: str | Path) -> Path:
        """Write the generated hardware.json to *path*."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_hardware_dict(), indent=2), encoding="utf-8")
        _logger.info("Generated hardware.json → %s", p)
        return p

    def save_cqed_params(
        self, path: str | Path, *, merge_existing: bool = True
    ) -> Path:
        """Write or merge cqed_params.json seed at *path*.

        When *merge_existing* is True and the file already exists,
        the seed fields (element names + frequencies) are merged into
        the existing file, preserving all other fields (physics, pulse
        parameters, etc.).
        """
        p = Path(path)
        seed = self.to_cqed_seed()

        if merge_existing and p.exists():
            try:
                existing = json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:
                existing = {}
            if isinstance(existing, dict):
                existing.update(seed)
                seed = existing

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(seed, indent=4), encoding="utf-8")
        _logger.info("Seeded cqed_params.json → %s", p)
        return p

    # ------------------------------------------------------------------
    # Private generation methods
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_if(el: _ElementDef) -> float:
        """Compute intermediate frequency for an element."""
        if el.frequency is not None:
            return el.frequency - el.lo_frequency
        return el.intermediate_frequency

    @staticmethod
    def _element_rf_frequency(el: _ElementDef) -> float:
        """Compute the absolute RF frequency for an element."""
        if el.frequency is not None:
            return el.frequency
        return el.lo_frequency + el.intermediate_frequency

    def _build_controllers(self) -> dict[str, Any]:
        """Build the controllers section."""
        # Infer analog output ports from RF out assignments
        # Standard OPX+Octave wiring: RF_out N → AO (2N-1, 2N)
        used_rf_outs = {el.rf_out for el in self._elements.values()}
        ao_ports: set[int] = set()
        for rf_out in used_rf_outs:
            ao_ports.add(2 * rf_out - 1)  # I channel
            ao_ports.add(2 * rf_out)      # Q channel

        # Collect digital output ports
        digital_ports: set[int] = set()
        for el in self._elements.values():
            for _di_name, (port, _delay, _buf) in el.digital_inputs.items():
                digital_ports.add(port)

        analog_outputs = {
            str(p): {"offset": 0.0} for p in sorted(ao_ports)
        }
        digital_outputs = {str(p): {} for p in sorted(digital_ports)}
        analog_inputs = {
            str(p): {"offset": v} for p, v in sorted(self._adc_offsets.items())
        }

        return {
            self._controller: {
                "analog_outputs": analog_outputs,
                "digital_outputs": digital_outputs,
                "analog_inputs": analog_inputs,
            }
        }

    def _build_octaves(self) -> dict[str, Any]:
        """Build the octaves section."""
        rf_outputs: dict[str, Any] = {}
        rf_inputs: dict[str, Any] = {}

        for el in self._elements.values():
            rf_outputs[str(el.rf_out)] = {
                "LO_frequency": el.lo_frequency,
                "LO_source": el.lo_source,
                "output_mode": "always_on",
                "gain": el.gain,
            }
            if el.kind == "readout" and el.rf_in is not None:
                rf_inputs[str(el.rf_in)] = {
                    "RF_source": "RF_in",
                    "LO_frequency": el.lo_frequency,
                    "LO_source": el.lo_source,
                    "IF_mode_I": "direct",
                    "IF_mode_Q": "direct",
                }

        return {
            self._octave: {
                "RF_outputs": rf_outputs,
                "RF_inputs": rf_inputs,
                "connectivity": self._controller,
            }
        }

    def _build_elements(self) -> dict[str, Any]:
        """Build the elements section."""
        elements: dict[str, Any] = {}

        for el in self._elements.values():
            el_dict: dict[str, Any] = {
                "RF_inputs": {"port": [self._octave, el.rf_out]},
                "intermediate_frequency": self._compute_if(el),
                "operations": {},
            }

            if el.kind == "readout" and el.rf_in is not None:
                el_dict["RF_outputs"] = {"port": [self._octave, el.rf_in]}
                el_dict["time_of_flight"] = el.time_of_flight or 280

            if el.digital_inputs:
                di_dict: dict[str, Any] = {}
                for di_name, (port, delay, buffer) in el.digital_inputs.items():
                    di_dict[di_name] = {
                        "port": [self._controller, port],
                        "delay": delay,
                        "buffer": buffer,
                    }
                el_dict["digitalInputs"] = di_dict

            elements[el.name] = el_dict

        return elements

    def _build_qubox_extras(self) -> dict[str, Any]:
        """Build the __qubox section (bindings, aliases, external_lo_map)."""
        # --- Bindings: outputs ---
        outputs: dict[str, Any] = {}
        for el in self._elements.values():
            di_spec: dict[str, list] = {}
            for di_name, (port, _delay, _buf) in el.digital_inputs.items():
                di_spec[di_name] = [self._controller, "digital_out", port]

            outputs[el.name] = {
                "channel": [self._octave, "RF_out", el.rf_out],
                "intermediate_frequency": self._compute_if(el),
                "lo_frequency": el.lo_frequency,
                "gain": el.gain,
                "digital_inputs": di_spec,
                "operations": {},
            }

        # --- Bindings: inputs (readout ADC) ---
        inputs: dict[str, Any] = {}
        for el in self._elements.values():
            if el.kind == "readout" and el.rf_in is not None:
                adc_name = f"{el.name}_adc"
                inputs[adc_name] = {
                    "channel": [self._octave, "RF_in", el.rf_in],
                    "lo_frequency": el.lo_frequency,
                    "time_of_flight": el.time_of_flight or 280,
                    "smearing": 0,
                    "weight_keys": [["cos", "sin"], ["minus_sin", "cos"]],
                }

        # --- Bindings: roles ---
        readout_name = self._roles.get("readout")
        roles: dict[str, str] = {
            "qubit": self._roles["qubit"],
            "readout_drive": readout_name,
            "readout_acquire": f"{readout_name}_adc",
        }
        if "storage" in self._roles and self._roles["storage"]:
            roles["storage"] = self._roles["storage"]

        # --- Bindings: extras (elements not assigned to a role) ---
        role_names = set(self._roles.values())
        extras = {
            el.name: el.name
            for el in self._elements.values()
            if el.name not in role_names
        }

        # --- Aliases: element name → canonical channel ID ---
        aliases = {
            el.name: f"{self._octave}:RF_out:{el.rf_out}"
            for el in self._elements.values()
        }

        # --- External LO map ---
        external_lo_map: dict[str, Any] = {}
        for rf_out, lo_info in self._external_los.items():
            key = f"{self._octave}:{rf_out}"
            external_lo_map[key] = lo_info

        return {
            "__qubox": {
                "external_lo_map": external_lo_map,
                "bindings": {
                    "outputs": outputs,
                    "inputs": inputs,
                    "roles": roles,
                    "extras": extras,
                },
                "aliases": aliases,
            }
        }

    def _build_octave_links(self) -> list[dict[str, Any]]:
        """Build octave_links (standard OPX+Octave wiring)."""
        used_rf_outs = sorted({el.rf_out for el in self._elements.values()})
        return [
            {
                "octave": self._octave,
                "controller": self._controller,
                "rf_out": rf_out,
                "ao_i": 2 * rf_out - 1,
                "ao_q": 2 * rf_out,
            }
            for rf_out in used_rf_outs
        ]

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        el_names = sorted(self._elements.keys())
        return (
            f"HardwareDefinition(controller={self._controller!r}, "
            f"octave={self._octave!r}, elements={el_names})"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _normalize_digital_inputs(
    raw: dict[str, int | tuple[int, int, int]] | None,
) -> dict[str, tuple[int, int, int]]:
    """Normalize digital input specs to ``(port, delay, buffer)`` tuples."""
    if not raw:
        return {}
    result: dict[str, tuple[int, int, int]] = {}
    for name, spec in raw.items():
        if isinstance(spec, int):
            result[name] = (spec, _DEFAULT_DI_DELAY, _DEFAULT_DI_BUFFER)
        elif isinstance(spec, (tuple, list)) and len(spec) == 3:
            result[name] = (int(spec[0]), int(spec[1]), int(spec[2]))
        else:
            raise ConfigError(
                f"Digital input '{name}': expected int or (port, delay, buffer) "
                f"tuple, got {spec!r}."
            )
    return result
