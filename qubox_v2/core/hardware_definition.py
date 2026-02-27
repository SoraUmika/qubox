# qubox_v2/core/hardware_definition.py
"""Notebook-first hardware definition.

Lets users define all hardware elements, LO/IF frequencies, wiring, and
external devices in the notebook.  ``HardwareDefinition`` generates the full
``hardware.json`` (controllers, octaves, elements, __qubox, octave_links),
seeds ``cqed_params.json`` (element names + initial frequencies), and
optionally generates ``devices.json`` (external instruments).

Usage::

    from qubox_v2.core.hardware_definition import HardwareDefinition

    hw = HardwareDefinition(controller="con1", octave="oct1")
    hw.add_readout("resonator", rf_out=1, rf_in=1, lo_frequency=8.8e9, ...)
    hw.add_control("qubit", rf_out=3, lo_frequency=6.2e9, ...)
    hw.set_aliases(qubit="qubit", readout="resonator", storage="storage")

    # External devices (optional — generates devices.json)
    hw.set_instrument_server("10.0.0.1", 50183)
    hw.add_device("external_lo", instrument_name="sc_34F3",
                  settings={"frequency": 3.5e9, "power": 8.5})

    # Pass to SessionManager — config files are auto-generated
    session = SessionManager.from_sample(..., hardware=hw, ...)

On subsequent sessions, the persisted config files are loaded
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


@dataclass
class _DeviceDef:
    """Internal description of one external instrument."""

    name: str
    driver: str = "instrumentserver:Instrument"
    backend: str = "instrumentserver"
    connect: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


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
        self._aliases: dict[str, str] = {}
        self._adc_offsets: dict[int, float] = {}
        self._devices: dict[str, _DeviceDef] = {}
        self._instrument_server: dict[str, Any] | None = None

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

    def set_aliases(
        self,
        aliases: dict[str, str] | None = None,
        **kwargs: str,
    ) -> "HardwareDefinition":
        """Map human-friendly alias names to element names.

        Accepts a dict, keyword arguments, or both (merged, kwargs win).
        Alias names are arbitrary.  Well-known names (``"qubit"``,
        ``"readout"``, ``"storage"``) are mapped to legacy cqed_params
        fields when generating the seed file.

        Examples::

            hw.set_aliases(qubit="transmon", readout="resonator")
            hw.set_aliases({"qubit": "transmon", "storage": "cavity"})
        """
        merged = dict(aliases) if aliases else {}
        merged.update(kwargs)
        self._aliases.update(merged)
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

    def set_instrument_server(
        self, host: str, port: int, timeout: int = 60000
    ) -> "HardwareDefinition":
        """Set shared InstrumentServer connection defaults for :meth:`add_device`.

        Devices added after this call inherit these connection parameters
        unless ``connect=`` is explicitly provided.

        Parameters
        ----------
        host : str
            InstrumentServer hostname or IP address.
        port : int
            InstrumentServer port number.
        timeout : int
            Connection timeout in milliseconds (default 60000).
        """
        self._instrument_server = {
            "host": host,
            "port": port,
            "timeout": timeout,
        }
        return self

    def add_device(
        self,
        name: str,
        *,
        driver: str = "instrumentserver:Instrument",
        backend: str | None = None,
        connect: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
        enabled: bool = True,
        instrument_name: str | None = None,
    ) -> "HardwareDefinition":
        """Add an external device definition (written to ``devices.json``).

        When :meth:`set_instrument_server` has been called and *connect* is
        not provided, the device inherits the shared server connection
        with ``instrument_name`` set to *instrument_name* (or *name* if
        not specified).

        Parameters
        ----------
        name : str
            Device identifier (e.g. ``"octave_external_lo2"``).
        driver : str
            Python class path ``"module:ClassName"`` (default
            ``"instrumentserver:Instrument"``).
        backend : str, optional
            ``"instrumentserver"``, ``"qcodes"``, or ``"direct"``.
            Defaults to ``"instrumentserver"`` when a shared server is set,
            ``"qcodes"`` otherwise.
        connect : dict, optional
            Connection parameters.  When *None* and a shared server is set,
            auto-populated from :meth:`set_instrument_server`.
        settings : dict, optional
            Initial device settings to apply on connect.
        enabled : bool
            Include this device in ``instantiate_all()`` (default True).
        instrument_name : str, optional
            Shorthand for ``connect["instrument_name"]``.  Only used when
            *connect* is *None* and a shared server is set.  Defaults to
            *name*.
        """
        if name in self._devices:
            raise ConfigError(f"Device '{name}' already defined.")

        # Resolve backend
        if backend is None:
            backend = "instrumentserver" if self._instrument_server else "qcodes"

        # Resolve connect dict
        if connect is None and self._instrument_server is not None:
            connect = {
                **self._instrument_server,
                "instrument_name": instrument_name or name,
            }
        elif connect is None:
            connect = {}

        self._devices[name] = _DeviceDef(
            name=name,
            driver=driver,
            backend=backend,
            connect=connect,
            settings=dict(settings) if settings else {},
            enabled=enabled,
        )
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

        # 1. Alias elements must exist
        for alias, name in self._aliases.items():
            if name and name not in self._elements:
                errors.append(
                    f"Alias '{alias}' references unknown element '{name}'."
                )

        # 2. Readout alias target must have rf_in (if "readout" alias set)
        readout_name = self._aliases.get("readout")
        if readout_name and readout_name in self._elements:
            el = self._elements[readout_name]
            if el.kind != "readout" or el.rf_in is None:
                errors.append(
                    f"Readout element '{readout_name}' must be added "
                    "with add_readout() including rf_in."
                )

        # 3. RF output port conflicts
        port_users: dict[int, list[str]] = {}
        for el in self._elements.values():
            port_users.setdefault(el.rf_out, []).append(el.name)
        for port, users in port_users.items():
            if len(users) > 1:
                errors.append(
                    f"RF output port {port} used by multiple elements: {users}."
                )

        # 4. RF output port range (OPX+ Octave: 1-5)
        for el in self._elements.values():
            if not (1 <= el.rf_out <= 5):
                errors.append(
                    f"Element '{el.name}': rf_out={el.rf_out} outside range 1-5."
                )

        # 5. IF frequency range (OPX+ limit: +/- 400 MHz)
        for el in self._elements.values():
            if_freq = self._compute_if(el)
            if abs(if_freq) > 400e6:
                errors.append(
                    f"Element '{el.name}': IF={if_freq / 1e6:.1f} MHz "
                    "exceeds OPX+ limit of +/- 400 MHz."
                )

        # 6. External LO consistency
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

        # 7. LO frequency must be positive
        for el in self._elements.values():
            if el.lo_frequency <= 0:
                errors.append(
                    f"Element '{el.name}': lo_frequency must be positive, "
                    f"got {el.lo_frequency}."
                )

        # 8. Digital input port range
        for el in self._elements.values():
            for di_name, (port, _delay, _buf) in el.digital_inputs.items():
                if not (1 <= port <= 10):
                    errors.append(
                        f"Element '{el.name}' digital input '{di_name}': "
                        f"port={port} out of range 1-10."
                    )

        # 9. External LO device cross-reference (warning, not error)
        defined_devices = set(self._devices.keys())
        for rf_out, lo_info in self._external_los.items():
            dev_name = lo_info.get("device", "")
            if dev_name and dev_name not in defined_devices:
                _logger.warning(
                    "set_external_lo(rf_out=%d) references device '%s' which "
                    "was not defined via add_device(). If it exists in a "
                    "pre-existing devices.json this is fine.",
                    rf_out, dev_name,
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

        Well-known alias names are mapped to legacy cqed_params fields:
        ``"qubit"`` → ``qb_el``/``qb_fq``, ``"readout"`` → ``ro_el``/``ro_fq``,
        ``"storage"`` → ``st_el``/``st_fq``.  All aliases are also stored
        under the ``__aliases`` key for forward-compatible readers.
        """
        seed: dict[str, Any] = {}

        # Well-known alias → legacy cqed_params field
        _ALIAS_TO_FIELD = {
            "qubit":   ("qb_el", "qb_fq"),
            "readout": ("ro_el", "ro_fq"),
            "storage": ("st_el", "st_fq"),
        }
        for alias, (el_field, fq_field) in _ALIAS_TO_FIELD.items():
            el_name = self._aliases.get(alias)
            if el_name:
                seed[el_field] = el_name
                if el_name in self._elements:
                    seed[fq_field] = self._element_rf_frequency(
                        self._elements[el_name]
                    )

        # Store full alias map for forward-compatible readers
        if self._aliases:
            seed["__aliases"] = dict(self._aliases)

        return seed

    # ------------------------------------------------------------------
    # Generation: devices.json
    # ------------------------------------------------------------------
    def to_devices_dict(self) -> dict[str, Any]:
        """Generate the devices.json content.

        Returns an empty dict if no devices have been defined via
        :meth:`add_device`.
        """
        return {
            dev.name: {
                "driver": dev.driver,
                "backend": dev.backend,
                "connect": dev.connect,
                "settings": dev.settings,
                "enabled": dev.enabled,
            }
            for dev in self._devices.values()
        }

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

    def save_devices(
        self, path: str | Path, *, merge_existing: bool = True
    ) -> Path | None:
        """Write devices.json to *path*.

        Returns *None* (and writes nothing) if no devices have been
        defined via :meth:`add_device`.

        When *merge_existing* is True and the file already exists, the
        builder's device definitions are merged into the existing file
        (preserving any manually-added devices).  Devices with matching
        names are overwritten by the builder definitions.
        """
        devices = self.to_devices_dict()
        if not devices:
            return None

        p = Path(path)

        if merge_existing and p.exists():
            try:
                existing = json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:
                existing = {}
            if isinstance(existing, dict):
                existing.update(devices)
                devices = existing

        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(devices, indent=2), encoding="utf-8")
        _logger.info("Generated devices.json → %s", p)
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

        # --- Bindings: roles (derived from aliases) ---
        roles: dict[str, str] = {}
        for alias, el_name in self._aliases.items():
            roles[alias] = el_name
            # Auto-add readout_acquire when "readout" alias targets a readout element
            if alias == "readout" and el_name in self._elements:
                el = self._elements[el_name]
                if el.kind == "readout" and el.rf_in is not None:
                    roles["readout_acquire"] = f"{el_name}_adc"

        # --- Bindings: extras (elements not referenced by any alias) ---
        aliased_elements = set(self._aliases.values())
        extras = {
            el.name: el.name
            for el in self._elements.values()
            if el.name not in aliased_elements
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
        dev_names = sorted(self._devices.keys())
        parts = [
            f"controller={self._controller!r}",
            f"octave={self._octave!r}",
            f"elements={el_names}",
        ]
        if self._aliases:
            parts.append(f"aliases={self._aliases}")
        if dev_names:
            parts.append(f"devices={dev_names}")
        return f"HardwareDefinition({', '.join(parts)})"


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
