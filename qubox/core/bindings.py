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

Roleless experiment primitives (v2.1 API)
-----------------------------------------
- ``DriveTarget``: generic frozen control output (no role vocabulary).
- ``ReadoutCal``: frozen calibration artifact snapshot.
- ``ReadoutHandle``: ``ReadoutBinding`` + ``ReadoutCal`` + element + operation.
- ``ElementFreq``: resolved frequency for one element.
- ``FrequencyPlan``: pure, immutable frequency plan for one experiment run.

See also: ``docs/api_refactor_output_binding_report.md`` §2,
``docs/roleless_experiments_plan_v2.md``.
"""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .device_metadata import DeviceMetadata
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

    The ``discrimination`` and ``quality`` dicts hold the session-owned
    readout DSP and quality state used at build and run time.
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

    # Discrimination / DSP state for explicit readout configuration
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

    def sync_from_calibration(self, cal_store: Any, *, lookup_keys: tuple[str, ...] | list[str] | None = None) -> None:
        """Populate discrimination and quality dicts from a CalibrationStore.

        Direction: CalibrationStore → ReadoutBinding (never reverse).
        """
        disc = _lookup_calibration_entry(
            cal_store,
            "get_discrimination",
            lookup_keys,
            self.physical_id,
            self.drive_channel_id,
        )
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

        quality_entry = _lookup_calibration_entry(
            cal_store,
            "get_readout_quality",
            lookup_keys,
            self.physical_id,
            self.drive_channel_id,
        )
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
# Roleless Experiment Primitives (v2.1 API)
# ---------------------------------------------------------------------------
# These types implement the "Roleless Experiments v2" design plan.
# They carry NO role vocabulary (no field named "qubit" or "storage").
# Experiments type-check for DriveTarget and ReadoutHandle, never for
# QubitSetup or CavitySetup.


def _tuple_matrix(
    m: Any,
) -> tuple[tuple[float, ...], ...] | None:
    """Convert a nested sequence to a tuple-of-tuples, or return None."""
    if m is None:
        return None
    try:
        return tuple(tuple(float(x) for x in row) for row in m)
    except (TypeError, ValueError):
        return None


def _coerce_lookup_keys(*values: Any) -> tuple[str, ...]:
    keys: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        candidates = value if isinstance(value, (list, tuple, set)) else (value,)
        for candidate in candidates:
            if candidate is None:
                continue
            key = str(candidate)
            if not key or key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return tuple(keys)


def _lookup_calibration_entry(store: Any, getter_name: str, *keys: Any) -> Any:
    getter = getattr(store, getter_name)
    for key in _coerce_lookup_keys(*keys):
        entry = getter(key)
        if entry is not None:
            return entry
    return None


def _weight_keys_from_demod_weight_sets(weight_sets: Any) -> tuple[str, ...]:
    normalized: list[tuple[str, ...]] = []
    for spec in weight_sets or ():
        if isinstance(spec, str):
            normalized.append((spec,))
            continue
        if isinstance(spec, (list, tuple)):
            values = tuple(str(item) for item in spec if item is not None)
            if values:
                normalized.append(values)

    if not normalized:
        return ("cos", "sin", "minus_sin")

    ordered: list[str] = []
    for spec in normalized[:2]:
        for item in spec:
            if item not in ordered:
                ordered.append(item)

    return tuple(ordered or ("cos", "sin", "minus_sin"))


@dataclass(frozen=True)
class DriveTarget:
    """A single control output channel for driving.

    Generic binding primitive with no role vocabulary -- the same type
    for qubit, storage, pump, or any other control line.

    Attributes
    ----------
    element : str
        QM element name (ephemeral at runtime).
    lo_freq : float
        LO frequency in Hz.
    rf_freq : float
        Target RF frequency in Hz.
    therm_clks : int | None
        Thermalization wait in clock cycles.
    """

    element: str
    lo_freq: float
    rf_freq: float
    therm_clks: int | None = None

    @property
    def if_freq(self) -> float:
        """Intermediate frequency in Hz (``rf_freq - lo_freq``)."""
        return self.rf_freq - self.lo_freq

    @classmethod
    def from_output_binding(
        cls,
        binding: OutputBinding,
        *,
        element: str,
        rf_freq: float | None = None,
        therm_clks: int | None = None,
    ) -> "DriveTarget":
        """Construct a DriveTarget from an existing OutputBinding.

        Parameters
        ----------
        binding : OutputBinding
            The physical channel binding.
        element : str
            Ephemeral QM element name.
        rf_freq : float | None
            If *None*, computed from ``lo + IF`` on the binding.
        therm_clks : int | None
            Thermalization wait (clock cycles).
        """
        lo = binding.lo_frequency or 0.0
        rf = rf_freq if rf_freq is not None else (lo + binding.intermediate_frequency)
        return cls(element=element, lo_freq=lo, rf_freq=rf, therm_clks=therm_clks)


@dataclass(frozen=True)
class ReadoutCal:
    """Immutable snapshot of readout calibration state.

    Contains all tunable parameters that change during calibration
    (thresholds, weights, confusion matrices).  Physical wiring identity
    is NOT here -- it lives in ``ReadoutBinding``.

    Attributes
    ----------
    drive_frequency : float
        RF drive frequency in Hz.
    threshold : float | None
        Discrimination threshold (set by ``ReadoutGEDiscrimination``).
    rotation_angle : float | None
        IQ rotation angle (set by ``ReadoutGEDiscrimination``).
    confusion_matrix : tuple[tuple[float, ...], ...] | None
        Readout confusion matrix (set by ``ReadoutButterflyMeasurement``).
    fidelity : float | None
        Readout assignment fidelity.
    """

    drive_frequency: float

    # Demodulation
    demod_method: str = "dual_demod.full"
    weight_keys: tuple[str, ...] = ("cos", "sin", "minus_sin")
    weight_length: int | None = None

    # Discrimination (set by ReadoutGEDiscrimination)
    threshold: float | None = None
    rotation_angle: float | None = None

    # Quality metrics (set by ReadoutButterflyMeasurement)
    confusion_matrix: tuple[tuple[float, ...], ...] | None = None
    fidelity: float | None = None
    fidelity_definition: str | None = None
    sigma_g: float | None = None
    sigma_e: float | None = None

    # Post-selection
    post_select_threshold: float | None = None
    post_select_max_retries: int = 3

    @classmethod
    def from_calibration_store(
        cls,
        store: Any,
        channel_id: str | tuple[str, ...] | list[str],
        *,
        drive_freq: float,
    ) -> "ReadoutCal":
        """Construct from persisted calibration data.

        Parameters
        ----------
        store : CalibrationStore
            The calibration store instance.
        channel_id : str
            Physical channel ID (e.g. ``"oct1:RF_in:1"``) or alias.
        drive_freq : float
            RF drive frequency in Hz.
        """
        disc = _lookup_calibration_entry(store, "get_discrimination", channel_id)
        qual = _lookup_calibration_entry(store, "get_readout_quality", channel_id)
        fidelity = getattr(qual, "fidelity", None) if qual else None
        if fidelity is None and qual is not None:
            fidelity = getattr(qual, "F", None)
        if fidelity is None and disc is not None:
            fidelity = getattr(disc, "fidelity", None)
        return cls(
            drive_frequency=drive_freq,
            threshold=getattr(disc, "threshold", None) if disc else None,
            rotation_angle=getattr(disc, "angle", None) if disc else None,
            confusion_matrix=_tuple_matrix(
                getattr(qual, "confusion_matrix", None) if qual else None
            ),
            fidelity=fidelity,
            fidelity_definition=getattr(disc, "fidelity_definition", None) if disc else None,
            sigma_g=getattr(disc, "sigma_g", None) if disc else None,
            sigma_e=getattr(disc, "sigma_e", None) if disc else None,
        )

    @classmethod
    def from_readout_binding(cls, rb: "ReadoutBinding") -> "ReadoutCal":
        """Extract calibration state from an existing ReadoutBinding."""
        disc = rb.discrimination or {}
        qual = rb.quality or {}
        pulse_op = getattr(rb, "pulse_op", None)
        weight_length = getattr(pulse_op, "length", None)
        if weight_length is None:
            weight_length = getattr(rb.acquire_in, "weight_length", None)
        fidelity = disc.get("fidelity")
        if fidelity is None:
            fidelity = qual.get("fidelity") or qual.get("F")
        return cls(
            drive_frequency=rb.drive_frequency or 0.0,
            weight_keys=_weight_keys_from_demod_weight_sets(rb.demod_weight_sets),
            weight_length=weight_length,
            threshold=disc.get("threshold"),
            rotation_angle=disc.get("angle"),
            confusion_matrix=_tuple_matrix(qual.get("confusion_matrix")),
            fidelity=fidelity,
            fidelity_definition=disc.get("fidelity_definition"),
            sigma_g=disc.get("sigma_g"),
            sigma_e=disc.get("sigma_e"),
        )

    def with_discrimination(
        self,
        *,
        threshold: float,
        rotation_angle: float,
    ) -> "ReadoutCal":
        """Return a new ReadoutCal with updated discrimination params."""
        from dataclasses import replace as _replace
        return _replace(self, threshold=threshold, rotation_angle=rotation_angle)


def _merge_readout_cal(base: ReadoutCal, overlay: ReadoutCal, *, drive_frequency: float) -> ReadoutCal:
    return replace(
        base,
        drive_frequency=float(drive_frequency),
        threshold=overlay.threshold if overlay.threshold is not None else base.threshold,
        rotation_angle=overlay.rotation_angle if overlay.rotation_angle is not None else base.rotation_angle,
        confusion_matrix=overlay.confusion_matrix if overlay.confusion_matrix is not None else base.confusion_matrix,
        fidelity=overlay.fidelity if overlay.fidelity is not None else base.fidelity,
        fidelity_definition=(
            overlay.fidelity_definition if overlay.fidelity_definition is not None else base.fidelity_definition
        ),
        sigma_g=overlay.sigma_g if overlay.sigma_g is not None else base.sigma_g,
        sigma_e=overlay.sigma_e if overlay.sigma_e is not None else base.sigma_e,
        post_select_threshold=(
            overlay.post_select_threshold if overlay.post_select_threshold is not None else base.post_select_threshold
        ),
        post_select_max_retries=(
            overlay.post_select_max_retries if overlay.post_select_max_retries is not None else base.post_select_max_retries
        ),
    )


@dataclass(frozen=True)
class ReadoutHandle:
    """Everything needed to measure one readout channel.

    Combines physical identity (``ReadoutBinding``) with calibration
    artifact reference (``ReadoutCal``).  Both are frozen/immutable.

    Experiments type-check for ``ReadoutHandle``, never for
    ``ReadoutBinding`` directly.

    Attributes
    ----------
    binding : ReadoutBinding
        Physical wiring (from ``core.bindings``).
    cal : ReadoutCal
        Calibration artifacts (thresholds, weights).
    element : str
        QM element name (ephemeral at runtime).
    operation : str
        Pulse operation (e.g. ``"readout"``).
    gain : float | None
        Default readout gain (overridable per measurement call).
    demod_weight_sets : tuple[tuple[str, ...] | str, ...]
        Demodulation weight set pairs (e.g. ``(("cos","sin"), ("minus_sin","cos"))``).
    """

    binding: ReadoutBinding
    cal: ReadoutCal
    element: str
    operation: str = "readout"
    gain: float | None = None
    demod_weight_sets: tuple[tuple[str, ...] | str, ...] = (("cos", "sin"), ("minus_sin", "cos"))

    @property
    def drive_frequency(self) -> float:
        """RF drive frequency from the calibration snapshot."""
        return self.cal.drive_frequency

    @property
    def physical_id(self) -> str:
        """Canonical physical channel ID for the acquire input."""
        return self.binding.physical_id

    @property
    def threshold(self) -> float | None:
        """Discrimination threshold shortcut."""
        return self.cal.threshold

@dataclass(frozen=True)
class ElementFreq:
    """Resolved frequency for one element.

    Attributes
    ----------
    element : str
        QM element name.
    rf_freq : float
        Target RF frequency in Hz.
    lo_freq : float
        LO frequency in Hz.
    if_freq : float
        Intermediate frequency in Hz (``rf_freq - lo_freq``).
    source : str
        Provenance tag: ``"explicit"``, ``"calibration"``, or
        ``"sample_default"``.
    """

    element: str
    rf_freq: float
    lo_freq: float
    if_freq: float
    source: str

    @classmethod
    def from_drive_target(cls, dt: DriveTarget) -> "ElementFreq":
        """Construct from a DriveTarget (explicit source)."""
        return cls(
            element=dt.element,
            rf_freq=dt.rf_freq,
            lo_freq=dt.lo_freq,
            if_freq=dt.if_freq,
            source="explicit",
        )

    @classmethod
    def from_readout_handle(cls, rh: ReadoutHandle) -> "ElementFreq":
        """Construct from a ReadoutHandle (explicit source)."""
        lo = rh.binding.drive_out.lo_frequency or 0.0
        rf = rh.cal.drive_frequency
        return cls(
            element=rh.element,
            rf_freq=rf,
            lo_freq=lo,
            if_freq=rf - lo,
            source="explicit",
        )


@dataclass(frozen=True)
class FrequencyPlan:
    """Pure, immutable frequency configuration for one experiment run.

    Computed once at ``run()`` entry.  Applied atomically before program
    execution.  Recorded in ``RunResult`` metadata for reproducibility.

    No snapshot/restore needed -- each experiment builds its own
    ``FrequencyPlan`` from scratch.

    Attributes
    ----------
    entries : tuple[ElementFreq, ...]
        One entry per element whose frequency must be set.
    """

    entries: tuple[ElementFreq, ...]

    def get(self, element: str) -> ElementFreq:
        """Look up the frequency entry for *element*.

        Raises ``KeyError`` if not found.
        """
        for e in self.entries:
            if e.element == element:
                return e
        raise KeyError(f"No frequency entry for element '{element}'")

    def to_metadata(self) -> dict[str, dict[str, Any]]:
        """Serialize for ``RunResult`` provenance recording."""
        return {
            e.element: {
                "rf_freq": e.rf_freq,
                "lo_freq": e.lo_freq,
                "if_freq": e.if_freq,
                "source": e.source,
            }
            for e in self.entries
        }

    def apply(self, hw: Any) -> None:
        """Set IF frequencies on QM hardware.  Called once, atomically.

        Parameters
        ----------
        hw : HardwareController / QuaProgramManager
            Must expose ``qm.set_intermediate_frequency(element, if_freq)``.
        """
        qm = getattr(hw, "qm", hw)
        for e in self.entries:
            qm.set_intermediate_frequency(e.element, int(e.if_freq))

    @classmethod
    def from_targets(
        cls,
        *,
        drive: "DriveTarget | None" = None,
        readout: "ReadoutHandle | None" = None,
        storage: "DriveTarget | None" = None,
        extras: "dict[str, DriveTarget] | None" = None,
    ) -> "FrequencyPlan":
        """Build a FrequencyPlan from roleless primitives.

        Convenience factory that collects ``ElementFreq`` entries from
        the supplied drive targets and readout handle.
        """
        entries: list[ElementFreq] = []
        if drive is not None:
            entries.append(ElementFreq.from_drive_target(drive))
        if readout is not None:
            entries.append(ElementFreq.from_readout_handle(readout))
        if storage is not None:
            entries.append(ElementFreq.from_drive_target(storage))
        if extras:
            for dt in extras.values():
                entries.append(ElementFreq.from_drive_target(dt))
        return cls(entries=tuple(entries))


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


def _parse_channel_ref(spec: Any, default_port_type: str = "RF_out") -> ChannelRef | None:
    """Parse a channel ref from list/tuple, dict, or canonical-id string."""
    if isinstance(spec, ChannelRef):
        return spec

    if isinstance(spec, str):
        parts = spec.split(":")
        if len(parts) == 3:
            dev, ptype, pnum = parts
            try:
                return ChannelRef(str(dev), str(ptype), int(pnum))
            except Exception:
                return None
        return None

    if isinstance(spec, (list, tuple)):
        if len(spec) == 3:
            dev, ptype, pnum = spec
            try:
                return ChannelRef(str(dev), str(ptype), int(pnum))
            except Exception:
                return None
        if len(spec) == 2:
            dev, pnum = spec
            try:
                return ChannelRef(str(dev), default_port_type, int(pnum))
            except Exception:
                return None

    if isinstance(spec, dict):
        dev = spec.get("device")
        ptype = spec.get("port_type", default_port_type)
        pnum = spec.get("port_number")
        if dev is None:
            dev = spec.get("controller") or spec.get("octave")
        if pnum is None:
            pnum = spec.get("port") or spec.get("channel") or spec.get("rf_port")
        try:
            return ChannelRef(str(dev), str(ptype), int(pnum))
        except Exception:
            return None

    return None


def _build_output_binding_from_spec(spec: dict[str, Any]) -> OutputBinding | None:
    """Build OutputBinding from __qubox.bindings.outputs spec."""
    channel = _parse_channel_ref(spec.get("channel"), default_port_type="RF_out")
    if channel is None:
        return None

    digital_inputs: dict[str, ChannelRef] = {}
    for key, di_spec in (spec.get("digital_inputs") or {}).items():
        di_ref = _parse_channel_ref(di_spec, default_port_type="digital_out")
        if di_ref is not None:
            digital_inputs[str(key)] = di_ref

    return OutputBinding(
        channel=channel,
        intermediate_frequency=float(spec.get("intermediate_frequency", 0.0) or 0.0),
        lo_frequency=(
            None
            if spec.get("lo_frequency") is None
            else float(spec.get("lo_frequency"))
        ),
        gain=(None if spec.get("gain") is None else float(spec.get("gain"))),
        digital_inputs=digital_inputs,
        operations=dict(spec.get("operations") or {}),
    )


def _build_input_binding_from_spec(spec: dict[str, Any]) -> InputBinding | None:
    """Build InputBinding from __qubox.bindings.inputs spec."""
    channel = _parse_channel_ref(spec.get("channel"), default_port_type="RF_in")
    if channel is None:
        return None

    weight_keys = spec.get("weight_keys")
    if not isinstance(weight_keys, list):
        weight_keys = [["cos", "sin"], ["minus_sin", "cos"]]

    return InputBinding(
        channel=channel,
        lo_frequency=(
            None
            if spec.get("lo_frequency") is None
            else float(spec.get("lo_frequency"))
        ),
        time_of_flight=int(spec.get("time_of_flight", 24) or 24),
        smearing=int(spec.get("smearing", 0) or 0),
        weight_keys=weight_keys,
        weight_length=(
            None
            if spec.get("weight_length") is None
            else int(spec.get("weight_length"))
        ),
    )


def _bindings_from_qubox_extras(
    hw: "HardwareConfig",
    attr: "DeviceMetadata",
) -> ExperimentBindings | None:
    """Build bindings from canonical __qubox.bindings data if present."""
    from .errors import ConfigError

    extras = hw.get_qubox_extras()
    raw_bundle = getattr(extras, "bindings", None) or getattr(extras, "binding_bundle", None)
    if not isinstance(raw_bundle, dict) or not raw_bundle:
        return None

    outputs_raw = raw_bundle.get("outputs") or {}
    inputs_raw = raw_bundle.get("inputs") or {}
    roles = raw_bundle.get("roles") or {}
    extras_map = raw_bundle.get("extras") or {}

    outputs: dict[str, OutputBinding] = {}
    for name, spec in outputs_raw.items():
        if not isinstance(spec, dict):
            continue
        b = _build_output_binding_from_spec(spec)
        if b is not None:
            outputs[str(name)] = b

    inputs: dict[str, InputBinding] = {}
    for name, spec in inputs_raw.items():
        if not isinstance(spec, dict):
            continue
        b = _build_input_binding_from_spec(spec)
        if b is not None:
            inputs[str(name)] = b

    qb_key = str(roles.get("qubit") or attr.qb_el or "qubit")
    ro_drive_key = str(roles.get("readout_drive") or roles.get("readout") or attr.ro_el or "resonator")
    ro_acq_key = str(roles.get("readout_acquire") or roles.get("acquire") or f"{ro_drive_key}_adc")
    st_key = roles.get("storage") or attr.st_el

    if qb_key not in outputs:
        raise ConfigError(
            f"__qubox.bindings missing qubit output '{qb_key}'. "
            f"Available outputs: {sorted(outputs.keys())}"
        )
    if ro_drive_key not in outputs:
        raise ConfigError(
            f"__qubox.bindings missing readout drive '{ro_drive_key}'. "
            f"Available outputs: {sorted(outputs.keys())}"
        )
    if ro_acq_key not in inputs:
        raise ConfigError(
            f"__qubox.bindings missing readout acquire '{ro_acq_key}'. "
            f"Available inputs: {sorted(inputs.keys())}"
        )

    readout = ReadoutBinding(
        drive_out=outputs[ro_drive_key],
        acquire_in=inputs[ro_acq_key],
        drive_frequency=float(attr.ro_fq) if attr.ro_fq is not None else None,
    )

    storage: OutputBinding | None = None
    if st_key is not None:
        st_name = str(st_key)
        storage = outputs.get(st_name)

    extras_bindings: dict[str, OutputBinding | ReadoutBinding] = {}
    if isinstance(extras_map, dict):
        for ext_name, out_key in extras_map.items():
            out_binding = outputs.get(str(out_key))
            if out_binding is not None:
                extras_bindings[str(ext_name)] = out_binding

    known_keys = {qb_key, ro_drive_key}
    if st_key is not None:
        known_keys.add(str(st_key))
    for out_name, out_binding in outputs.items():
        if out_name not in known_keys and out_name not in extras_bindings:
            extras_bindings[out_name] = out_binding

    return ExperimentBindings(
        qubit=outputs[qb_key],
        readout=readout,
        storage=storage,
        extras=extras_bindings,
    )


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
    attr: "DeviceMetadata",
) -> ExperimentBindings:
    """Backward-compatible: derive ExperimentBindings from existing config.

    Uses the element names from ``attr.qb_el`` / ``attr.ro_el`` /
    ``attr.st_el`` to look up elements in ``hw.elements`` and build the
    corresponding bindings.

    Parameters
    ----------
    hw : HardwareConfig
        Parsed hardware.json.
    attr : DeviceMetadata
        Device element mapping.

    Returns
    -------
    ExperimentBindings

    Raises
    ------
    ConfigError
        If required elements are missing from the hardware config.
    """
    from .errors import ConfigError

    # Preferred v2.0.0 path: canonical __qubox.bindings data.
    binding_bundle = _bindings_from_qubox_extras(hw, attr)
    if binding_bundle is not None:
        return binding_bundle

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
    attr: "DeviceMetadata",
) -> AliasMap:
    """Build an AliasMap from hardware.json + device metadata.

    Returns a mapping from human-friendly names (e.g. ``"qubit"``,
    ``"resonator"``) to their physical ``ChannelRef``.
    """
    alias_map: AliasMap = {}

    extras = hw.get_qubox_extras()
    aliases_raw = getattr(extras, "aliases", None) or getattr(extras, "alias_map", None)
    bindings_raw = getattr(extras, "bindings", None) or getattr(extras, "binding_bundle", None)

    if isinstance(aliases_raw, dict) and aliases_raw:
        outputs_raw = {}
        if isinstance(bindings_raw, dict):
            outputs_raw = bindings_raw.get("outputs") or {}

        for alias, spec in aliases_raw.items():
            ref = _parse_channel_ref(spec, default_port_type="RF_out")
            if ref is None and isinstance(spec, str) and spec in outputs_raw:
                out_spec = outputs_raw.get(spec)
                if isinstance(out_spec, dict):
                    out_binding = _build_output_binding_from_spec(out_spec)
                    if out_binding is not None:
                        ref = out_binding.channel
            if ref is not None:
                alias_map[str(alias)] = ref

        if alias_map:
            return alias_map

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
