# qubox_v2/core/bindings.py
"""Binding-driven API: physical channel identity + experiment bindings.

This module replaces the implicit element-name coupling that previously
permeated the codebase.  Physical channels (``ChannelRef``) are the stable
identity layer; human-friendly aliases map to physical channels, not to QM
element definitions.

Key types
---------
- ``ChannelRef``: immutable identifier for a physical hardware port.
- ``OutputBinding``: a bound control output channel.
- ``InputBinding``: a bound acquisition input channel.
- ``ReadoutBinding``: paired output + input for readout/measurement.
- ``ExperimentBindings``: named collection of bindings passed to experiments.
- ``AliasMap``: ``dict[str, ChannelRef]`` — human-friendly names → ports.

See also: ``docs/api_refactor_output_binding_report.md`` §2.
"""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..analysis.cQED_attributes import cQED_attributes
    from .config import ElementConfig, HardwareConfig

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ChannelRef — stable physical identity
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ChannelRef:
    """Stable physical identity for a hardware port.

    Examples::

        ChannelRef("con1", "analog_out", 3)
        ChannelRef("oct1", "RF_out", 1)
        ChannelRef("con1", "analog_in", 1)
    """

    device: str          # controller or octave name
    port_type: str       # "analog_out", "analog_in", "RF_out", "RF_in", "digital_out"
    port_number: int

    @property
    def canonical_id(self) -> str:
        """Stable string key for calibration/artifact storage."""
        return f"{self.device}:{self.port_type}:{self.port_number}"

    def __str__(self) -> str:
        return self.canonical_id


# ---------------------------------------------------------------------------
# OutputBinding — a bound control output channel
# ---------------------------------------------------------------------------
@dataclass
class OutputBinding:
    """A bound control output channel.

    Attributes
    ----------
    channel : ChannelRef
        The physical channel this binding targets.
    intermediate_frequency : float
        IF frequency in Hz.
    lo_frequency : float | None
        LO frequency in Hz (when driven through an Octave).
    gain : float | None
        Output gain (Octave RF output gain).
    digital_inputs : dict[str, ChannelRef]
        Named digital inputs (e.g. ``{"switch": ChannelRef(...)}``).
    operations : dict[str, str]
        ``{op_name: pulse_name}`` — registered pulse operations.
    """

    channel: ChannelRef
    intermediate_frequency: float = 0.0
    lo_frequency: float | None = None
    gain: float | None = None
    digital_inputs: dict[str, ChannelRef] = field(default_factory=dict)
    operations: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# InputBinding — a bound acquisition input channel
# ---------------------------------------------------------------------------
@dataclass
class InputBinding:
    """A bound acquisition input channel.

    Attributes
    ----------
    channel : ChannelRef
        The physical channel (e.g. ``ChannelRef("oct1", "RF_in", 1)``).
    lo_frequency : float | None
        LO frequency for the input path.
    time_of_flight : int
        Time-of-flight in ns (default 24).
    smearing : int
        Smearing in ns.
    weight_keys : list[list[str]]
        Integration weight label pairs (default cos/sin, minus_sin/cos).
    weight_length : int | None
        Override length for weights; ``None`` means use pulse length.
    """

    channel: ChannelRef
    lo_frequency: float | None = None
    time_of_flight: int = 24
    smearing: int = 0
    weight_keys: list[list[str]] = field(
        default_factory=lambda: [["cos", "sin"], ["minus_sin", "cos"]]
    )
    weight_length: int | None = None


# ---------------------------------------------------------------------------
# ReadoutBinding — paired output + input for measurement
# ---------------------------------------------------------------------------
@dataclass
class ReadoutBinding:
    """Paired output + input for readout/measurement.

    Encapsulates everything ``measure_with_binding`` needs: the drive output,
    the acquisition input, and all DSP configuration.

    The ``discrimination`` and ``quality`` dicts replace the class-level
    ``measureMacro._ro_disc_params`` / ``_ro_quality_params`` singletons.
    """

    drive_out: OutputBinding
    acquire_in: InputBinding

    # PulseOp currently bound for measurement
    pulse_op: Any = None          # PulseOp | None
    active_op: str | None = None  # QUA operation handle

    # Demod configuration
    demod_weight_sets: list[list[str]] = field(
        default_factory=lambda: [["cos", "sin"], ["minus_sin", "cos"]]
    )

    # Discrimination / DSP state (replaces measureMacro class-level state)
    discrimination: dict[str, Any] = field(default_factory=lambda: {
        "threshold": None,
        "angle": None,
        "fidelity": None,
        "rot_mu_g": None,
        "rot_mu_e": None,
        "sigma_g": None,
        "sigma_e": None,
    })
    quality: dict[str, Any] = field(default_factory=lambda: {
        "alpha": None,
        "beta": None,
        "F": None,
        "Q": None,
        "V": None,
        "t01": None,
        "t10": None,
        "confusion_matrix": None,
        "affine_n": None,
    })

    drive_frequency: float | None = None
    gain: float | None = None

    @property
    def physical_id(self) -> str:
        """Canonical key for calibration storage (keyed to the acquisition ADC)."""
        return self.acquire_in.channel.canonical_id

    @property
    def drive_channel_id(self) -> str:
        """Canonical key for the drive output."""
        return self.drive_out.channel.canonical_id

    def sync_from_calibration(self, cal_store: Any) -> None:
        """Populate discrimination and quality dicts from a CalibrationStore.

        Direction: CalibrationStore → ReadoutBinding (never reverse).
        """
        disc = cal_store.get_discrimination(self.physical_id)
        if disc is not None:
            dp = self.discrimination
            if disc.threshold is not None:
                dp["threshold"] = float(disc.threshold)
            if disc.angle is not None:
                dp["angle"] = float(disc.angle)
            if disc.fidelity is not None:
                dp["fidelity"] = float(disc.fidelity)
            if hasattr(disc, "mu_g") and disc.mu_g is not None:
                dp["rot_mu_g"] = (
                    complex(disc.mu_g[0], disc.mu_g[1])
                    if isinstance(disc.mu_g, (list, tuple))
                    else disc.mu_g
                )
            if hasattr(disc, "mu_e") and disc.mu_e is not None:
                dp["rot_mu_e"] = (
                    complex(disc.mu_e[0], disc.mu_e[1])
                    if isinstance(disc.mu_e, (list, tuple))
                    else disc.mu_e
                )
            if hasattr(disc, "sigma_g") and disc.sigma_g is not None:
                dp["sigma_g"] = float(disc.sigma_g)
            if hasattr(disc, "sigma_e") and disc.sigma_e is not None:
                dp["sigma_e"] = float(disc.sigma_e)

        quality_entry = cal_store.get_readout_quality(self.physical_id)
        if quality_entry is not None:
            qp = self.quality
            for key in ("alpha", "beta", "F", "Q", "V", "t01", "t10"):
                val = getattr(quality_entry, key, None)
                if val is not None:
                    qp[key] = float(val)
            if quality_entry.confusion_matrix is not None:
                import numpy as np
                qp["confusion_matrix"] = np.asarray(quality_entry.confusion_matrix)
            if hasattr(quality_entry, "affine_n") and quality_entry.affine_n is not None:
                qp["affine_n"] = quality_entry.affine_n


# ---------------------------------------------------------------------------
# ExperimentBindings — named collection passed to experiments
# ---------------------------------------------------------------------------
@dataclass
class ExperimentBindings:
    """Collection of bindings passed to an experiment.

    Replaces the implicit assumption that element names like
    ``"qubit"``, ``"resonator"``, ``"storage"`` exist in hardware.json.

    Attributes
    ----------
    qubit : OutputBinding
        Qubit drive channel.
    readout : ReadoutBinding
        Readout measurement channel pair.
    storage : OutputBinding | None
        Storage cavity drive channel (if present).
    extras : dict[str, OutputBinding | ReadoutBinding]
        Additional named bindings for multi-element experiments.
    """

    qubit: OutputBinding
    readout: ReadoutBinding
    storage: OutputBinding | None = None
    extras: dict[str, OutputBinding | ReadoutBinding] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AliasMap — user-friendly names → physical ports
# ---------------------------------------------------------------------------
AliasMap = dict[str, ChannelRef]
"""Mapping from human-friendly alias to physical ``ChannelRef``.

Example::

    {"qubit": ChannelRef("oct1", "RF_out", 3),
     "resonator": ChannelRef("oct1", "RF_out", 1)}
"""


# ---------------------------------------------------------------------------
# Adapter: hardware.json + cqed_params → ExperimentBindings
# ---------------------------------------------------------------------------
def _parse_element_rf_port(
    port_spec: Any,
) -> ChannelRef | None:
    """Parse an element's ``RF_inputs.port`` or ``RF_outputs.port`` spec.

    The hardware.json format is ``["oct1", 1]`` (list of [device, port_number]).
    We produce a ``ChannelRef`` from this.
    """
    if isinstance(port_spec, (list, tuple)) and len(port_spec) == 2:
        device, port_num = port_spec
        return ChannelRef(str(device), "RF_out", int(port_num))
    return None


def _parse_element_digital_inputs(
    digital_inputs: dict[str, Any] | None,
) -> dict[str, ChannelRef]:
    """Parse an element's ``digitalInputs`` section into ChannelRef dict."""
    if not digital_inputs:
        return {}
    result: dict[str, ChannelRef] = {}
    for name, spec in digital_inputs.items():
        port = spec.get("port")
        if isinstance(port, (list, tuple)) and len(port) == 2:
            result[name] = ChannelRef(str(port[0]), "digital_out", int(port[1]))
    return result


def _build_output_binding(
    el_name: str,
    el_cfg: "ElementConfig",
    hw: "HardwareConfig",
) -> OutputBinding | None:
    """Build an OutputBinding from an element definition in hardware.json."""
    rf_in = el_cfg.RF_inputs or {}
    port_spec = rf_in.get("port")
    channel = _parse_element_rf_port(port_spec)
    if channel is None:
        _logger.warning(
            "Element '%s' has no parseable RF_inputs.port; skipping binding.",
            el_name,
        )
        return None

    # Resolve LO frequency from octave config
    lo_freq = None
    gain = None
    octave_name = channel.device
    rf_out_num = channel.port_number
    if octave_name in hw.octaves:
        octave_cfg = hw.octaves[octave_name]
        rf_out_entry = octave_cfg.RF_outputs.get(rf_out_num)
        if rf_out_entry is not None:
            lo_freq = rf_out_entry.LO_frequency
            gain = rf_out_entry.gain

    digital_inputs = _parse_element_digital_inputs(
        el_cfg.digitalInputs if isinstance(el_cfg.digitalInputs, dict) else None
    )

    return OutputBinding(
        channel=channel,
        intermediate_frequency=el_cfg.intermediate_frequency,
        lo_frequency=lo_freq,
        gain=gain,
        digital_inputs=digital_inputs,
        operations=dict(el_cfg.operations or {}),
    )


def _build_input_binding(
    el_name: str,
    el_cfg: "ElementConfig",
    hw: "HardwareConfig",
) -> InputBinding | None:
    """Build an InputBinding from an element's RF_outputs (readout return path)."""
    rf_out = el_cfg.RF_outputs
    if not rf_out:
        return None
    port_spec = rf_out.get("port")
    if not isinstance(port_spec, (list, tuple)) or len(port_spec) != 2:
        return None

    device, port_num = port_spec
    channel = ChannelRef(str(device), "RF_in", int(port_num))

    # Resolve input LO from octave config
    lo_freq = None
    if str(device) in hw.octaves:
        octave_cfg = hw.octaves[str(device)]
        rf_in_entry = octave_cfg.RF_inputs.get(int(port_num))
        if rf_in_entry is not None and rf_in_entry.LO_frequency is not None:
            lo_freq = rf_in_entry.LO_frequency

    tof = el_cfg.time_of_flight or 24

    return InputBinding(
        channel=channel,
        lo_frequency=lo_freq,
        time_of_flight=tof,
    )


def bindings_from_hardware_config(
    hw: "HardwareConfig",
    attr: "cQED_attributes",
) -> ExperimentBindings:
    """Backward-compatible: derive ExperimentBindings from existing config.

    Uses the element names from ``attr.qb_el`` / ``attr.ro_el`` /
    ``attr.st_el`` to look up elements in ``hw.elements`` and build the
    corresponding bindings.

    Parameters
    ----------
    hw : HardwareConfig
        Parsed hardware.json.
    attr : cQED_attributes
        Experiment attributes (element names, frequencies).

    Returns
    -------
    ExperimentBindings

    Raises
    ------
    ConfigError
        If required elements are missing from the hardware config.
    """
    from .errors import ConfigError

    elements = hw.elements

    # --- Qubit binding ---
    qb_el_name = attr.qb_el
    if qb_el_name is None or qb_el_name not in elements:
        raise ConfigError(
            f"Qubit element '{qb_el_name}' not found in hardware.json. "
            f"Available: {sorted(elements.keys())}"
        )
    qb_binding = _build_output_binding(qb_el_name, elements[qb_el_name], hw)
    if qb_binding is None:
        raise ConfigError(
            f"Could not build OutputBinding for qubit element '{qb_el_name}'."
        )

    # --- Readout binding ---
    ro_el_name = attr.ro_el
    if ro_el_name is None or ro_el_name not in elements:
        raise ConfigError(
            f"Readout element '{ro_el_name}' not found in hardware.json. "
            f"Available: {sorted(elements.keys())}"
        )
    ro_el_cfg = elements[ro_el_name]
    ro_drive = _build_output_binding(ro_el_name, ro_el_cfg, hw)
    if ro_drive is None:
        raise ConfigError(
            f"Could not build drive OutputBinding for readout element '{ro_el_name}'."
        )
    ro_acquire = _build_input_binding(ro_el_name, ro_el_cfg, hw)
    if ro_acquire is None:
        raise ConfigError(
            f"Could not build InputBinding for readout element '{ro_el_name}'. "
            "Ensure the element has RF_outputs configured."
        )

    ro_binding = ReadoutBinding(
        drive_out=ro_drive,
        acquire_in=ro_acquire,
        drive_frequency=float(attr.ro_fq) if attr.ro_fq is not None else None,
    )

    # --- Storage binding (optional) ---
    st_binding: OutputBinding | None = None
    st_el_name = attr.st_el
    if st_el_name is not None and st_el_name in elements:
        st_binding = _build_output_binding(st_el_name, elements[st_el_name], hw)

    # --- Additional elements as extras ---
    extras: dict[str, OutputBinding | ReadoutBinding] = {}
    known_names = {qb_el_name, ro_el_name, st_el_name}
    for el_name, el_cfg in elements.items():
        if el_name in known_names:
            continue
        ob = _build_output_binding(el_name, el_cfg, hw)
        if ob is not None:
            extras[el_name] = ob

    return ExperimentBindings(
        qubit=qb_binding,
        readout=ro_binding,
        storage=st_binding,
        extras=extras,
    )


def build_alias_map(
    hw: "HardwareConfig",
    attr: "cQED_attributes",
) -> AliasMap:
    """Build an AliasMap from hardware.json + cqed_params.

    Returns a mapping from human-friendly names (e.g. ``"qubit"``,
    ``"resonator"``) to their physical ``ChannelRef``.
    """
    alias_map: AliasMap = {}
    elements = hw.elements

    for el_name, el_cfg in elements.items():
        rf_in = el_cfg.RF_inputs or {}
        port_spec = rf_in.get("port")
        channel = _parse_element_rf_port(port_spec)
        if channel is not None:
            alias_map[el_name] = channel

    return alias_map


# ---------------------------------------------------------------------------
# ConfigBuilder: Binding → QM Element dicts
# ---------------------------------------------------------------------------
class ConfigBuilder:
    """Synthesize QM config element dicts from bindings at compile time.

    This is the ONLY place where QM ``element`` dicts should be created
    from bindings. The element names are ephemeral — used only for the
    QM config dict and QUA program references.
    """

    # Ephemeral element name prefixes
    _QB_NAME = "__qb"
    _RO_NAME = "__ro"
    _ST_NAME = "__st"

    @staticmethod
    def _build_control_element(
        name: str,
        binding: OutputBinding,
    ) -> dict[str, Any]:
        """Build a QM control element dict from an OutputBinding."""
        el: dict[str, Any] = {}

        # RF_inputs (drive output path from octave)
        ch = binding.channel
        el["RF_inputs"] = {"port": [ch.device, ch.port_number]}

        # Intermediate frequency
        el["intermediate_frequency"] = binding.intermediate_frequency

        # Digital inputs
        if binding.digital_inputs:
            di: dict[str, Any] = {}
            for di_name, di_ch in binding.digital_inputs.items():
                di[di_name] = {
                    "port": [di_ch.device, di_ch.port_number],
                    "delay": 0,
                    "buffer": 0,
                }
            el["digitalInputs"] = di

        # Operations
        el["operations"] = dict(binding.operations)

        return el

    @staticmethod
    def _build_readout_element(
        name: str,
        binding: ReadoutBinding,
    ) -> dict[str, Any]:
        """Build a QM measurement element dict from a ReadoutBinding."""
        drive = binding.drive_out
        acquire = binding.acquire_in
        el: dict[str, Any] = {}

        # RF_inputs (drive path)
        ch_drive = drive.channel
        el["RF_inputs"] = {"port": [ch_drive.device, ch_drive.port_number]}

        # RF_outputs (acquisition return path)
        ch_acq = acquire.channel
        el["RF_outputs"] = {"port": [ch_acq.device, ch_acq.port_number]}

        # Intermediate frequency
        el["intermediate_frequency"] = drive.intermediate_frequency

        # Time of flight
        el["time_of_flight"] = acquire.time_of_flight

        # Digital inputs
        if drive.digital_inputs:
            di: dict[str, Any] = {}
            for di_name, di_ch in drive.digital_inputs.items():
                di[di_name] = {
                    "port": [di_ch.device, di_ch.port_number],
                    "delay": 0,
                    "buffer": 0,
                }
            el["digitalInputs"] = di

        # Operations
        el["operations"] = dict(drive.operations)

        return el

    @classmethod
    def build_element(
        cls,
        name: str,
        binding: OutputBinding | ReadoutBinding,
    ) -> dict[str, Any]:
        """Build a single QM element definition from a binding.

        This is the ONLY place where QM ``element`` dicts are created
        from bindings. The *name* is ephemeral.
        """
        if isinstance(binding, ReadoutBinding):
            return cls._build_readout_element(name, binding)
        return cls._build_control_element(name, binding)

    @classmethod
    def build_elements(
        cls,
        bindings: ExperimentBindings,
    ) -> dict[str, dict[str, Any]]:
        """Build a complete elements dict from an ExperimentBindings bundle.

        Returns
        -------
        dict[str, dict]
            Mapping of ephemeral element name → QM element definition.
        """
        elements: dict[str, dict[str, Any]] = {}
        elements[cls._QB_NAME] = cls.build_element(cls._QB_NAME, bindings.qubit)
        elements[cls._RO_NAME] = cls.build_element(cls._RO_NAME, bindings.readout)
        if bindings.storage is not None:
            elements[cls._ST_NAME] = cls.build_element(cls._ST_NAME, bindings.storage)
        for k, b in bindings.extras.items():
            ext_name = f"__ext_{k}"
            elements[ext_name] = cls.build_element(ext_name, b)
        return elements

    @classmethod
    def ephemeral_names(
        cls,
        bindings: ExperimentBindings,
    ) -> dict[str, str]:
        """Return a mapping of role → ephemeral element name.

        Useful for program builders that need to reference elements by name
        in QUA code.

        Returns
        -------
        dict[str, str]
            ``{"qubit": "__qb", "readout": "__ro", "storage": "__st", ...}``
        """
        names: dict[str, str] = {
            "qubit": cls._QB_NAME,
            "readout": cls._RO_NAME,
        }
        if bindings.storage is not None:
            names["storage"] = cls._ST_NAME
        for k in bindings.extras:
            names[k] = f"__ext_{k}"
        return names


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_binding(
    binding: OutputBinding | ReadoutBinding,
    hw: "HardwareConfig | None" = None,
) -> list[str]:
    """Check that a binding is internally consistent.

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []

    if isinstance(binding, ReadoutBinding):
        drive_ch = binding.drive_out.channel
        acq_ch = binding.acquire_in.channel

        # Drive and acquire should be on the same octave
        if drive_ch.device != acq_ch.device:
            errors.append(
                f"ReadoutBinding drive ({drive_ch}) and acquire ({acq_ch}) "
                "are on different devices."
            )

        # LO frequencies should match if both set
        drive_lo = binding.drive_out.lo_frequency
        acq_lo = binding.acquire_in.lo_frequency
        if drive_lo is not None and acq_lo is not None:
            if abs(drive_lo - acq_lo) > 1.0:
                errors.append(
                    f"ReadoutBinding LO mismatch: drive_lo={drive_lo}, "
                    f"acquire_lo={acq_lo}."
                )

    elif isinstance(binding, OutputBinding):
        ch = binding.channel
        if ch.port_type not in ("RF_out", "analog_out"):
            errors.append(
                f"OutputBinding channel type '{ch.port_type}' is unusual "
                "for a control output."
            )

    return errors
