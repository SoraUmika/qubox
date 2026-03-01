"""qubox_v2.experiments.session
================================
SessionManager: wires together all qubox services for an experiment session.

Replaces the "god-object" wiring role of the legacy ``cQED_Experiment`` class
while staying thinner — it owns the infrastructure components and lets
individual experiment classes handle the physics.

Usage::

    from qubox_v2.experiments.session import SessionManager

    with SessionManager("./cooldown_2025", qop_ip="10.0.0.1") as session:
        from qubox_v2.experiments.spectroscopy import QubitSpectroscopy
        spec = QubitSpectroscopy(session)
        result = spec.run(pulse="x180", freq_start=6.13e9, ...)
"""
from __future__ import annotations

import logging
import json
import warnings
from pathlib import Path
from typing import Any, Optional

from ..core.errors import ConfigError
from ..core.logging import get_logger
from ..hardware.config_engine import ConfigEngine
from ..hardware.controller import HardwareController
from ..hardware.program_runner import ProgramRunner
from ..hardware.queue_manager import QueueManager
from ..pulses.manager import PulseOperationManager
from ..pulses.pulse_registry import PulseRegistry
from ..devices.device_manager import DeviceManager
from ..calibration.store import CalibrationStore
from ..analysis.cQED_attributes import cQED_attributes
from ..analysis.output import Output
from ..core.persistence_policy import split_output_for_persistence
from ..calibration.orchestrator import CalibrationOrchestrator

_logger = get_logger(__name__)


class SessionManager:
    """Central service container for a qubox experiment session.

    Owns all infrastructure components and provides a unified context that
    experiment classes can reference.  Can be used as a context-manager for
    automatic cleanup.

    Parameters
    ----------
    experiment_path : str | Path | None
        Optional registry base path hint. In strict mode, session location is
        always resolved from ``sample_id`` + ``cooldown_id``.
    qop_ip : str | None
        OPX+ IP / hostname.  Resolved from hardware JSON if *None*.
    cluster_name : str | None
        QM cluster identifier.
    load_devices : bool | list[str]
        Which external instruments to initialise on startup.
    oct_cal_path : str | Path | None
        Path to Octave calibration database.
    auto_save_calibration : bool
        If True, calibration data auto-saves on every mutation.
    sample_id : str | None
        Sample identifier.  When set together with ``cooldown_id``,
        enables context mode with full sample/cooldown scoping.
    cooldown_id : str | None
        Cooldown cycle identifier (requires ``sample_id``).
    registry_base : str | Path | None
        Root directory for the sample registry. Defaults to
        ``experiment_path`` or current directory.
    strict_context : bool
        If True (default), sample/wiring mismatches raise
        ``ContextMismatchError`` when loading calibration.
    kwargs
        Forwarded to ``ConfigEngine`` / ``HardwareController``.
    """

    def __init__(
        self,
        experiment_path: str | Path | None = None,
        *,
        qop_ip: str | None = None,
        cluster_name: str | None = None,
        load_devices: bool | list[str] = True,
        oct_cal_path: str | Path | None = None,
        auto_save_calibration: bool = False,
        sample_id: str | None = None,
        cooldown_id: str | None = None,
        registry_base: str | Path | None = None,
        strict_context: bool = True,
        hardware: Any = None,
        **kwargs: Any,
    ) -> None:
        # --- Context resolution ---
        self._experiment_context = None
        self._sample_config_dir: Path | None = None

        if sample_id is None or cooldown_id is None:
            raise ConfigError(
                "Both 'sample_id' and 'cooldown_id' are required in strict session mode."
            )

        # Context mode: resolve paths from sample registry
        from ..devices.sample_registry import SampleRegistry
        from ..devices.context_resolver import ContextResolver

        base = Path(registry_base) if registry_base else (
            Path(experiment_path) if experiment_path else Path.cwd()
        )
        registry = SampleRegistry(base)
        if not registry.sample_exists(sample_id):
            raise ConfigError(
                f"Sample '{sample_id}' not found in registry at {base}. "
                f"Available: {registry.list_samples()}"
            )
        if not registry.cooldown_exists(sample_id, cooldown_id):
            raise ConfigError(
                f"Cooldown '{cooldown_id}' not found for sample '{sample_id}'. "
                f"Available: {registry.list_cooldowns(sample_id)}"
            )

        resolver = ContextResolver(registry)
        self._experiment_context = resolver.resolve(sample_id, cooldown_id)

        # Set experiment_path to the cooldown directory
        self.experiment_path = registry.cooldown_path(sample_id, cooldown_id)
        self._sample_config_dir = registry.sample_path(sample_id) / "config"
        _logger.info(
            "Context mode: sample=%s cooldown=%s wiring=%s",
            sample_id, cooldown_id, self._experiment_context.wiring_rev,
        )

        self.experiment_path.mkdir(parents=True, exist_ok=True)

        _logger.info("SessionManager initialising at %s", self.experiment_path)

        # --- 0. Process HardwareDefinition (notebook-first setup) ---
        if hardware is not None:
            self._apply_hardware_definition(hardware)

        # --- 1. Configuration engine ---
        self.config_engine = ConfigEngine(
            hardware_path=self._resolve_path("hardware.json", required=True),
        )

        # --- 2. QM connection ---
        from qm import QuantumMachinesManager
        host = qop_ip or self.config_engine.hardware_extras.get("qop_ip", "localhost")
        cal_db = str(oct_cal_path) if oct_cal_path else str(self.experiment_path)
        self._qmm = QuantumMachinesManager(
            host=host,
            cluster_name=cluster_name,
            octave_calibration_db_path=cal_db,
        )

        self.hardware = HardwareController(
            qmm=self._qmm,
            config_engine=self.config_engine,
        )
        self.hardware._cal_db_dir = Path(cal_db)

        # --- 3. Program runner + queue ---
        self.runner = ProgramRunner(
            qmm=self._qmm,
            controller=self.hardware,
            config_engine=self.config_engine,
        )
        self.queue = QueueManager(runner=self.runner)

        # --- 4. Pulse management (both legacy POM and new PulseRegistry) ---
        pl_path = self._resolve_path("pulses.json", required=False)
        if pl_path:
            self.pulse_mgr = PulseOperationManager.from_json(pl_path)
        else:
            self.pulse_mgr = PulseOperationManager()
        self.pulses = PulseRegistry()

        # --- 5. Calibration store ---
        cal_path = self.experiment_path / "config" / "calibration.json"
        self.calibration = CalibrationStore(
            cal_path,
            auto_save=auto_save_calibration,
            context=self._experiment_context,
            strict_context=strict_context,
        )

        # --- 6. External devices ---
        device_path = self._resolve_path("devices.json", required=False)
        if device_path is None:
            device_path = self.experiment_path / "devices.json"
        self.devices = DeviceManager(device_path)
        if load_devices is True:
            self.devices.instantiate_all()
        elif isinstance(load_devices, (list, tuple, set)):
            if load_devices:
                self.devices.instantiate(list(load_devices))
        self.hardware.set_device_manager(self.devices)

        # --- 7. Experiment attributes (cQED parameters) ---
        self.attributes = self._load_attributes()
        self._runtime_settings = self._load_runtime_settings()
        self.allow_inline_mutations = False
        self.orchestrator = CalibrationOrchestrator(self)
        self.calibration_orchestrator = self.orchestrator
        self._opened = False

        _logger.info("SessionManager ready.")

    # ------------------------------------------------------------------
    # Compatibility properties — experiment classes access these via ctx
    # ------------------------------------------------------------------
    @property
    def hw(self) -> HardwareController:
        """Alias for experiment_base.py compatibility."""
        return self.hardware

    @property
    def pulseOpMngr(self) -> PulseOperationManager:
        """Alias for legacy code that accesses ``ctx.pulseOpMngr``."""
        return self.pulse_mgr

    @property
    def quaProgMngr(self):
        """Alias used by legacy experiment code."""
        return self.hardware

    @property
    def context(self):
        """The ExperimentContext for this session, or None in legacy mode."""
        return self._experiment_context

    # ------------------------------------------------------------------
    # Binding-driven API
    # ------------------------------------------------------------------
    _bindings_cache = None

    @property
    def bindings(self):
        """Auto-derived ExperimentBindings from hardware.json + cqed_params.

        Lazily constructed on first access.  Call :meth:`invalidate_bindings`
        after changing hardware config or attributes to force re-derivation.

        Returns
        -------
        ExperimentBindings
        """
        if self._bindings_cache is None:
            from ..core.bindings import bindings_from_hardware_config
            self._bindings_cache = bindings_from_hardware_config(
                self.config_engine.hardware, self.attributes,
            )
            # Sync readout DSP state from calibration store
            try:
                self._bindings_cache.readout.sync_from_calibration(self.calibration)
            except Exception:
                pass
            # Register aliases in calibration store
            self._register_alias_index()
            _logger.info("ExperimentBindings derived from hardware config.")
        return self._bindings_cache

    def invalidate_bindings(self) -> None:
        """Force re-derivation of bindings on next access."""
        self._bindings_cache = None

    def _register_alias_index(self) -> None:
        """Register element-name → physical-ID aliases in the CalibrationStore."""
        from ..core.bindings import build_alias_map
        alias_map = build_alias_map(self.config_engine.hardware, self.attributes)
        for alias, channel_ref in alias_map.items():
            self.calibration.register_alias(alias, channel_ref.canonical_id)

    # ------------------------------------------------------------------
    # Roleless experiment factories (v2.1 API)
    # ------------------------------------------------------------------
    # These methods produce *generic* DriveTarget / ReadoutHandle instances
    # that carry no role vocabulary.  They are ergonomic shortcuts; the
    # underlying primitives remain role-free.

    def drive_target(
        self,
        alias: str,
        *,
        rf_freq: float | None = None,
        therm_clks: int | None = None,
    ) -> "DriveTarget":
        """Construct a :class:`DriveTarget` from a named alias.

        Resolves element name, LO frequency, and RF frequency from the
        hardware config and calibration store.

        Parameters
        ----------
        alias : str
            Human-friendly name (e.g. ``"qubit"``, ``"storage"``).
        rf_freq : float | None
            Explicit RF frequency override.  If *None*, resolved from
            calibration store or sample attributes.
        therm_clks : int | None
            Thermalization wait override.  If *None*, resolved from
            ``attr.<alias>_therm_clks`` or default 250 000.
        """
        from ..core.bindings import DriveTarget

        b = self.bindings
        # Resolve the OutputBinding for this alias
        if alias in ("qubit", "qb") or alias == getattr(self.attributes, "qb_el", None):
            ob = b.qubit
            element = self.attributes.qb_el or alias
            default_therm = getattr(self.attributes, "qb_therm_clks", 250_000) or 250_000
            cal_field = "qubit_freq"
        elif alias in ("storage", "st") or alias == getattr(self.attributes, "st_el", None):
            ob = b.storage
            if ob is None:
                raise ValueError(f"No storage binding available for alias '{alias}'.")
            element = self.attributes.st_el or alias
            default_therm = getattr(self.attributes, "st_therm_clks", 500_000) or 500_000
            cal_field = "storage_freq"
        elif alias in b.extras:
            ob = b.extras[alias]
            element = alias
            default_therm = 250_000
            cal_field = None
        else:
            raise ValueError(
                f"Unknown alias '{alias}'. Known: qubit, storage, "
                f"{', '.join(b.extras.keys()) if b.extras else '(no extras)'}."
            )

        # Resolve RF frequency
        if rf_freq is None and cal_field is not None:
            from ..experiments.experiment_base import ExperimentBase
            # Try calibration store first
            cal = getattr(self, "calibration", None)
            if cal is not None:
                try:
                    freq_entry = cal.get_frequencies(element)
                    if freq_entry is not None:
                        v = getattr(freq_entry, cal_field, None)
                        if v is not None and v != 0.0:
                            rf_freq = float(v)
                except Exception:
                    pass
            # Fallback to sample attributes
            if rf_freq is None:
                attr_field = {"qubit_freq": "qb_fq", "storage_freq": "st_fq"}.get(cal_field)
                if attr_field:
                    v = getattr(self.attributes, attr_field, None)
                    if v is not None:
                        rf_freq = float(v)

        therm = therm_clks if therm_clks is not None else int(default_therm)

        return DriveTarget.from_output_binding(
            ob, element=element, rf_freq=rf_freq, therm_clks=therm,
        )

    def readout_handle(
        self,
        alias: str = "resonator",
        operation: str = "readout",
    ) -> "ReadoutHandle":
        """Construct a :class:`ReadoutHandle` from a named alias.

        Resolves physical binding from hardware config and calibration
        artifacts from ``CalibrationStore``.

        Parameters
        ----------
        alias : str
            Human-friendly name (default ``"resonator"``).
        operation : str
            Pulse operation (default ``"readout"``).
        """
        from ..core.bindings import ReadoutHandle, ReadoutCal

        b = self.bindings
        rb = b.readout  # ReadoutBinding
        element = getattr(self.attributes, "ro_el", None) or alias

        # Build ReadoutCal from CalibrationStore (always fresh)
        drive_freq = rb.drive_frequency
        if not isinstance(drive_freq, (int, float)) or drive_freq == 0.0:
            drive_freq = float(getattr(self.attributes, "ro_fq", 0.0) or 0.0)

        cal = ReadoutCal.from_calibration_store(
            self.calibration,
            rb.physical_id,
            drive_freq=drive_freq,
        )

        return ReadoutHandle(
            binding=rb, cal=cal, element=element, operation=operation,
        )

    # Ergonomic shortcuts for common patterns
    def qubit(self, alias: str = "qubit", **kw) -> "DriveTarget":
        """Shortcut for ``drive_target("qubit")``.

        Returns a :class:`DriveTarget` — a generic type with no role
        vocabulary.
        """
        return self.drive_target(alias, **kw)

    def storage(self, alias: str = "storage", **kw) -> "DriveTarget":
        """Shortcut for ``drive_target("storage")``.

        Returns a :class:`DriveTarget` — a generic type with no role
        vocabulary.
        """
        return self.drive_target(alias, **kw)

    def readout(self, alias: str = "resonator", **kw) -> "ReadoutHandle":
        """Shortcut for ``readout_handle("resonator")``.

        Returns a :class:`ReadoutHandle` — a generic type with no role
        vocabulary.
        """
        return self.readout_handle(alias, **kw)

    def _apply_hardware_definition(self, hw_def: Any) -> None:
        """Generate hardware.json, cqed_params.json, and devices.json from a HardwareDefinition.

        Called before ``ConfigEngine`` creation when the user passes a
        ``HardwareDefinition`` object to the session constructor.

        When the ``HardwareDefinition`` is provided it *always* regenerates
        hardware.json (the user explicitly wants to set/update the wiring).
        cqed_params.json is seeded with element names and initial frequencies
        but existing physics parameters are preserved.  devices.json is
        generated only when :meth:`HardwareDefinition.add_device` was called.
        """
        from ..core.hardware_definition import HardwareDefinition

        if not isinstance(hw_def, HardwareDefinition):
            raise ConfigError(
                f"'hardware' must be a HardwareDefinition instance, got {type(hw_def).__name__}."
            )

        # Validate
        errors = hw_def.validate()
        if errors:
            raise ConfigError(
                "HardwareDefinition validation failed:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

        # Determine target paths.
        # hardware.json and devices.json are sample-level files (shared across cooldowns).
        if self._sample_config_dir is not None:
            hw_path = self._sample_config_dir / "hardware.json"
            cqed_path = self._sample_config_dir / "cqed_params.json"
            dev_path = self._sample_config_dir / "devices.json"
        else:
            hw_path = self.experiment_path / "config" / "hardware.json"
            cqed_path = self.experiment_path / "config" / "cqed_params.json"
            dev_path = self.experiment_path / "config" / "devices.json"

        # Warn if overwriting an existing hardware.json
        if hw_path.exists():
            _logger.info(
                "Overwriting existing hardware.json from HardwareDefinition: %s",
                hw_path,
            )

        # Generate and write hardware.json
        hw_def.save_hardware(hw_path)

        # Seed cqed_params.json (merge with existing to preserve physics params)
        hw_def.save_cqed_params(cqed_path, merge_existing=True)

        # Generate devices.json (merge with existing to preserve manual devices)
        hw_def.save_devices(dev_path, merge_existing=True)

    @classmethod
    def from_sample(
        cls,
        sample_id: str,
        cooldown_id: str,
        registry_base: str | Path,
        **kwargs: Any,
    ) -> "SessionManager":
        """Convenience constructor for context mode.

        Parameters
        ----------
        sample_id : str
            Sample identifier in the registry.
        cooldown_id : str
            Cooldown cycle identifier.
        registry_base : str | Path
            Root directory for the sample registry.
        **kwargs
            Forwarded to :class:`SessionManager` constructor.
        """
        return cls(
            sample_id=sample_id,
            cooldown_id=cooldown_id,
            registry_base=registry_base,
            **kwargs,
        )

    # Backward compatibility alias
    from_device = from_sample

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------
    def _resolve_path(self, filename: str, *, required: bool = False) -> Path | None:
        """Look for *filename* in config/ or experiment root.

        In context mode, sample-level files (hardware.json, devices.json,
        cqed_params.json, pulse_specs.json) are resolved from the sample
        config directory first.
        """
        # Context mode: check sample-level config dir for sample files
        if self._sample_config_dir is not None:
            from ..devices.sample_registry import SAMPLE_LEVEL_FILES
            if filename in SAMPLE_LEVEL_FILES:
                p = self._sample_config_dir / filename
                if p.exists():
                    return p

        candidates = [
            self.experiment_path / "config" / filename,
            self.experiment_path / filename,
        ]
        for p in candidates:
            if p.exists():
                return p
        if required:
            raise ConfigError(
                f"Required file '{filename}' not found. Searched: "
                f"{[str(c) for c in candidates]}"
            )
        return None

    @property
    def device_manager(self) -> DeviceManager:
        """Alias so ExperimentBase can access ``ctx.device_manager``."""
        return self.devices

    def _load_attributes(self) -> cQED_attributes:
        """Load or create cQED experiment attributes."""
        resolved = self._resolve_path("cqed_params.json")
        if resolved is not None:
            _logger.info("Loading experiment context from %s", resolved)
            obj = cQED_attributes.from_json(resolved)
            obj._log_bindings()
            obj.validate()
            return obj
        _logger.info("No cqed_params.json found — using default attributes")
        return cQED_attributes()

    def _runtime_settings_path(self) -> Path:
        return self.experiment_path / "config" / "session_runtime.json"

    def _load_runtime_settings(self) -> dict[str, Any]:
        """Load runtime/session-owned workflow settings.

        Source of truth:
        1) ``config/session_runtime.json``
        """
        path = self._runtime_settings_path()
        data: dict[str, Any] = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
                    _logger.info("Loaded runtime settings from %s", path)
            except Exception as exc:
                _logger.warning("Failed to load runtime settings from %s: %s", path, exc)

        return data

    def save_runtime_settings(self) -> Path:
        path = self._runtime_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._runtime_settings, f, indent=2, default=str)
        _logger.info("Saved runtime settings to %s", path)
        return path

    def get_runtime_setting(self, key: str, default: Any = None) -> Any:
        return self._runtime_settings.get(key, default)

    def set_runtime_setting(self, key: str, value: Any, *, persist: bool = True) -> None:
        self._runtime_settings[key] = value
        if persist:
            self.save_runtime_settings()

    def get_therm_clks(self, channel: str, default: int | None = None) -> int | None:
        key = f"{channel}_therm_clks"
        val = self.get_runtime_setting(key, None)
        if val is None:
            return default
        return int(val)

    def get_displacement_reference(self) -> dict[str, Any]:
        return {
            "coherent_amp": self.get_runtime_setting("b_coherent_amp", None),
            "coherent_len": self.get_runtime_setting("b_coherent_len", None),
            "b_alpha": self.get_runtime_setting("b_alpha", None),
        }

    def refresh_attribute_frequencies_from_calibration(self, *, persist: bool = False) -> dict[str, float]:
        """Bind runtime attribute frequencies to latest calibration values.

        Source-of-truth precedence:
        1) CalibrationStore frequencies.<element>.qubit_freq
        2) Existing attribute value (unchanged)
        """
        updates: dict[str, float] = {}

        attr = getattr(self, "attributes", None)
        cal = getattr(self, "calibration", None)
        if attr is None or cal is None:
            return updates

        bindings = (
            ("qb_el", "qb_fq"),
            ("st_el", "st_fq"),
        )
        for el_attr, fq_attr in bindings:
            element = getattr(attr, el_attr, None)
            if not element:
                continue
            freq_entry = cal.get_frequencies(element)
            if freq_entry is None:
                continue
            fq = getattr(freq_entry, "qubit_freq", None)
            if fq is None:
                continue
            fq = float(fq)
            setattr(attr, fq_attr, fq)
            updates[fq_attr] = fq

        if updates and persist:
            self.save_attributes()

        return updates

    # ------------------------------------------------------------------
    # Pulse helpers
    # ------------------------------------------------------------------
    def burn_pulses(self, include_volatile: bool = True) -> None:
        """Push all registered pulses into the QM config."""
        self.config_engine.merge_pulses(self.pulse_mgr, include_volatile=include_volatile)
        self.hardware.apply_changes()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save_attributes(self) -> None:
        """Persist cQED attributes to JSON."""
        p = self.experiment_path / "config" / "cqed_params.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        self.attributes.save_json(p)

    def save_pulses(self, path: str | Path | None = None) -> Path:
        """Persist PulseOperationManager permanent store to pulses.json."""
        dst = Path(path) if path is not None else (self.experiment_path / "config" / "pulses.json")
        dst.parent.mkdir(parents=True, exist_ok=True)
        self.pulse_mgr.save_json(str(dst))
        _logger.info("Saved pulse manager state to %s", dst)
        return dst

    def save_output(self, output: Output | dict, tag: str = "") -> Path:
        """Save experiment output data to disk."""
        import datetime
        from typing import Mapping
        import numpy as np

        target = self.experiment_path / "data"
        target.mkdir(parents=True, exist_ok=True)

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"{tag}_{ts}" if tag else ts
        path = target / f"{stem}.npz"

        data = dict(output) if isinstance(output, Mapping) else output
        arrays, meta, dropped = split_output_for_persistence(data)
        if dropped:
            meta["_persistence"] = {
                "raw_data_policy": "drop_shot_level_arrays",
                "dropped_fields": dropped,
            }

        np.savez_compressed(path, **arrays)

        import json
        meta_path = path.with_suffix(".meta.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2, default=str)

        self.save_attributes()
        _logger.info("Output saved to %s", path)
        return path

    # ------------------------------------------------------------------
    # Open QM connection
    # ------------------------------------------------------------------
    def open(self) -> "SessionManager":
        """Open the QM connection and initialise hardware elements."""
        if self._opened:
            _logger.warning("SessionManager.open() called again; closing previous session first.")
            self.close()
        self.config_engine.merge_pulses(self.pulse_mgr)
        self.hardware.open_qm()
        self._load_measure_config()
        self.validate_runtime_elements(auto_map=True, verbose=True)
        self._opened = True
        return self

    def validate_runtime_elements(self, *, auto_map: bool = True, verbose: bool = True) -> dict[str, Any]:
        """Validate configured attributes against live QM element names.

        Returns a summary with available/missing/mapped entries and applies safe
        aliases when ``auto_map=True``.
        """
        qm_elements = set((self.hardware.elements or {}).keys())
        attr = self.attributes
        requested = {
            "ro_el": getattr(attr, "ro_el", None),
            "qb_el": getattr(attr, "qb_el", None),
            "st_el": getattr(attr, "st_el", None),
        }

        mapped: dict[str, str] = {}
        missing: dict[str, str] = {}
        notes: list[str] = []

        for field, name in requested.items():
            if not name:
                continue
            if name in qm_elements:
                mapped[field] = name
                continue
            low = str(name).lower()
            candidate = None
            if low == "readout" and "resonator" in qm_elements:
                candidate = "resonator"
            if candidate and auto_map:
                setattr(attr, field, candidate)
                mapped[field] = candidate
                notes.append(f"{field}: '{name}' -> '{candidate}'")
            else:
                missing[field] = name

        summary = {
            "available": sorted(qm_elements),
            "requested": requested,
            "mapped": mapped,
            "missing": missing,
            "notes": notes,
        }

        if verbose:
            _logger.info("Runtime element validation: available=%s", sorted(qm_elements))
            for note in notes:
                _logger.warning("Runtime element auto-map applied: %s", note)
            for field, name in missing.items():
                _logger.error(
                    "Runtime element mismatch: %s='%s' not in QM config. Available=%s",
                    field,
                    name,
                    sorted(qm_elements),
                )
        return summary

    def override_readout_operation(
        self,
        *,
        element: str,
        operation: str,
        weights: list | tuple | str | None = None,
        drive_frequency: float | None = None,
        demod: str | None = None,
        threshold: float | None = None,
        weight_len: int | None = None,
        apply_to_attributes: bool = True,
        persist_measure_config: bool = True,
    ) -> dict[str, Any]:
        """Override active readout op/weights at runtime via ``measureMacro``."""
        from ..programs.macros.measure import measureMacro

        pulse_info = self.pulse_mgr.get_pulseOp_by_element_op(element, operation, strict=False)
        if pulse_info is None:
            cfg = self.config_engine.build_qm_config()
            available_ops = sorted((cfg.get("elements", {}).get(element, {}).get("operations", {}) or {}).keys())
            raise ValueError(
                f"No pulse mapping for element={element!r}, operation={operation!r}. "
                f"Available operations for element: {available_ops}"
            )

        selected_weights = weights
        if selected_weights is None:
            iw_map = pulse_info.int_weights_mapping or {}
            if all(k in iw_map for k in ("cos", "sin", "minus_sin")):
                selected_weights = [["cos", "sin"], ["minus_sin", "cos"]]
            else:
                selected_weights = [["cos", "sin"], ["minus_sin", "cos"]]

        measureMacro.set_pulse_op(
            pulse_info,
            active_op=operation,
            weights=selected_weights,
            weight_len=(weight_len or pulse_info.length),
        )

        if drive_frequency is not None:
            measureMacro.set_drive_frequency(drive_frequency)

        if demod:
            from qm.qua import dual_demod
            if demod == "dual_demod.full":
                measureMacro.set_demodulator(dual_demod.full)

        if threshold is not None:
            from ..calibration.contracts import Patch

            patch = Patch(reason="override_readout_operation_threshold")
            patch.add("SetMeasureDiscrimination", threshold=float(threshold))
            self.orchestrator.apply_patch(patch, dry_run=False)

        if apply_to_attributes:
            self.attributes.ro_el = element

        dst = None
        if persist_measure_config:
            dst = self.experiment_path / "config" / "measureConfig.json"
            dst.parent.mkdir(parents=True, exist_ok=True)
            measureMacro.save_json(str(dst))

        return {
            "element": element,
            "operation": operation,
            "pulse": pulse_info.pulse,
            "weights": selected_weights,
            "attributes_ro_el": self.attributes.ro_el,
            "measure_config_path": str(dst) if dst else None,
            "qm_config_entry": f"elements.{element}.operations.{operation} -> {pulse_info.pulse}",
        }

    def _load_measure_config(self) -> None:
        """Load measureMacro state from measureConfig.json if it exists,
        then sync discrimination/quality params from CalibrationStore."""
        from ..programs.macros.measure import measureMacro

        path = self._resolve_path("measureConfig.json", required=False)
        if path is not None:
            measureMacro.load_json(str(path))
            _logger.info("Loaded measureMacro state from %s", path)
        else:
            _logger.warning(
                "No measureConfig.json found — measureMacro will use defaults. "
                "Run readout calibration to populate it."
            )

        # Sync discrimination/quality params from CalibrationStore → measureMacro.
        # CalibrationStore is the canonical source of truth; this ensures the
        # macro reflects any CalibrationStore updates that may have occurred
        # after the last measureConfig.json save.
        cal = getattr(self, "calibration", None)
        ro_el = getattr(getattr(self, "attributes", None), "ro_el", None)
        if cal is not None and ro_el is not None:
            try:
                measureMacro.sync_from_calibration(cal, ro_el)
                _logger.info("Synced measureMacro from CalibrationStore (element=%s)", ro_el)
            except Exception as exc:
                _logger.warning("Failed to sync measureMacro from CalibrationStore: %s", exc)

    # ------------------------------------------------------------------
    # Ad-hoc program simulation
    # ------------------------------------------------------------------
    def simulate_program(
        self,
        program: Any,
        sim_config: Any = None,
    ) -> Any:
        """Simulate an ad-hoc QUA program not tied to an experiment class.

        Parameters
        ----------
        program
            A QUA program object (``qm.qua._Program``).
        sim_config : QuboxSimulationConfig, optional
            Simulation parameters.  If ``None``, uses defaults
            (4000 ns, plot=True).

        Returns
        -------
        SimulatorSamples
            Relabelled simulator samples with element-named channels.
        """
        from ..hardware.program_runner import QuboxSimulationConfig

        if sim_config is None:
            sim_config = QuboxSimulationConfig()

        return self.runner.simulate(
            program,
            duration=sim_config.duration_ns,
            plot=sim_config.plot,
            plot_params=sim_config.plot_params,
            controllers=sim_config.controllers,
            t_begin=sim_config.t_begin,
            t_end=sim_config.t_end,
            compiler_options=sim_config.compiler_options,
        )

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------
    def close(self) -> None:
        """Release hardware and device connections."""
        try:
            self.hardware.close()
        except Exception as e:
            _logger.warning("Error closing hardware: %s", e, exc_info=True)
        for name, handle in self.devices.handles.items():
            try:
                handle.disconnect()
            except Exception as e:
                _logger.warning("Error disconnecting device '%s': %s", name, e, exc_info=True)
        try:
            self.save_pulses()
        except Exception as e:
            _logger.warning("Error saving pulses: %s", e, exc_info=True)
        try:
            self.save_runtime_settings()
        except Exception as e:
            _logger.warning("Error saving runtime settings: %s", e, exc_info=True)
        self.calibration.save()
        try:
            from ..programs.macros.measure import measureMacro
            dst = self.experiment_path / "config" / "measureConfig.json"
            dst.parent.mkdir(parents=True, exist_ok=True)
            measureMacro.save_json(str(dst))
        except Exception as e:
            _logger.warning("Error saving measureConfig.json on close: %s", e, exc_info=True)
        self._opened = False
        _logger.info("SessionManager closed.")

    def __enter__(self) -> "SessionManager":
        return self.open()

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return f"SessionManager(path={self.experiment_path})"
