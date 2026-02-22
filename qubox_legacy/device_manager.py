import contextlib
import importlib
import json
import logging
import os
import threading
import time
import numpy as np
from math import ceil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

# --------------------------------------------------------------------------- #
# Logger (default to INFO so users actually see messages)
# --------------------------------------------------------------------------- #
_logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class DeviceError(RuntimeError):
    ...

# --------------------------------------------------------------------------- #
# Spec
# --------------------------------------------------------------------------- #
@dataclass
class DeviceSpec:
    name: str
    driver: str                       # "module.submodule:ClassName"
    backend: str = "qcodes"           # we'll use this to switch on QCoDeS
    connect: Dict[str, Any] = field(default_factory=dict)   # kwargs for construction
    settings: Dict[str, Any] = field(default_factory=dict)  # initial params
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "driver": self.driver,
            "backend": self.backend,
            "connect": self.connect,
            "settings": self.settings,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, name: str, d: Dict[str, Any]) -> "DeviceSpec":
        if d is None:
            raise DeviceError(f"Device '{name}' spec is None.")
        backend = d.get("backend", "qcodes")
        if backend.lower() != "instrumentserver" and "driver" not in d:
            raise DeviceError(f"Device '{name}' missing required field 'driver'.")
        return cls(
            name=name,
            driver=d.get("driver", "instrumentserver:Instrument"),  # dummy default
            backend=backend,
            connect=d.get("connect", {}) or {},
            settings=d.get("settings", {}) or {},
            enabled=bool(d.get("enabled", True)),
        )

# --------------------------------------------------------------------------- #
# Handle (does the actual import/connect/apply/disconnect/snapshot)
# --------------------------------------------------------------------------- #
class DeviceHandle:
    def __init__(self, spec: DeviceSpec):
        self.spec = spec
        self.instance = None  # the live driver/instrument

    def _import_driver(self):
        mod_name, cls_name = self.spec.driver.split(":", 1)
        module = importlib.import_module(mod_name)
        return getattr(module, cls_name)

    def connect(self):
        """Construct the instrument; for QCoDeS, mirror qc.find_or_create_instrument."""
        if self.instance is not None:
            return self.instance

        cls = None
        if self.spec.backend.lower() == "qcodes":
            import qcodes as qc
            kwargs = dict(self.spec.connect)
            name = kwargs.pop("name", self.spec.name)

            dllpath = kwargs.get("dllpath")
            if dllpath and hasattr(os, "add_dll_directory"):
                with contextlib.suppress(Exception):
                    os.add_dll_directory(str(Path(dllpath).resolve().parent))

            if cls is None:
                cls = self._import_driver()
            _logger.info("QCoDeS create/find: %s(name=%r, kwargs=%s)", cls.__name__, name, kwargs)
            self.instance = qc.find_or_create_instrument(instrument_class=cls, name=name, **kwargs)

        elif self.spec.backend.lower() == "instrumentserver":
            try:
                from instrumentserver.client import Client
            except ModuleNotFoundError as e:
                raise DeviceError(
                    f"{self.spec.name}: instrumentserver backend requested but package not found "
                    "(pip install instrumentserver-client or similar)."
                ) from e

            c = self.spec.connect
            host = c.get("host")
            port = c.get("port")
            timeout = c.get("timeout", 60000)
            inst_name = c.get("instrument_name") or self.spec.name
            if not host or not port:
                raise DeviceError(f"{self.spec.name}: 'host' and 'port' required for instrumentserver backend.")

            _logger.info("InstrumentServer connect: host=%s port=%s timeout=%s name=%s", host, port, timeout, inst_name)
            client = Client(host=host, port=port, timeout=timeout)
            self._client = client
            self.instance = client.get_instrument(inst_name)

        else:
            # Fallback: direct constructor
            if cls is None:
                cls = self._import_driver()
            self.instance = cls(**self.spec.connect)

        # Apply initial settings after construction
        if self.spec.settings:
            # Ramp any "voltageN" keys on init; everything else uses normal apply().
            import re
            ramp_keys = []
            normal_settings = {}
            for k, v in self.spec.settings.items():
                if isinstance(v, (int, float)) and re.fullmatch(r"voltage\d*", k):
                    ramp_keys.append((k, float(v)))
                else:
                    normal_settings[k] = v

            # Defaults (can be overridden via connect: {"ramp_step": ..., "ramp_delay_s": ...})
            step = float(self.spec.connect.get("ramp_step", 0.001))      # 10 mV
            delay = float(self.spec.connect.get("ramp_delay_s", 0.1))  # 50 ms
            
            # Do ramps first
            for k, target in ramp_keys:
                try:
                    print(f"Ramping {self.spec.name}.{k} to {target} (step={step}, delay={delay})")
                    self.ramp(k, target, step=step, delay_s=delay)
                except Exception:
                    # If ramp fails, fall back to a direct set so init still completes
                    _logger.exception("Ramp on init failed for %s; falling back to direct set.", k)
                    try:
                        self._apply_one(self.instance, getattr(self.instance, "parameters", {}), k, target)
                    except Exception:
                        _logger.exception("Fallback direct set also failed for %s.", k)
                        raise

            # Then apply any non-voltage settings normally
            if normal_settings:
                self.apply(normal_settings)

        return self.instance

    def disconnect(self):
        if self.instance is None:
            return
        with contextlib.suppress(Exception):
            close = getattr(self.instance, "close", None)
            if callable(close):
                close()
        # also close underlying instrumentserver client if present
        with contextlib.suppress(Exception):
            client = getattr(self, "_client", None)
            if client and hasattr(client, "close"):
                client.close()
        self.instance = None
        if hasattr(self, "_client"):
            delattr(self, "_client")

    def apply(self, settings: Dict[str, Any]):
        """Apply settings to the live instrument (Parameter.set / call / set_<name>)."""
        if not settings:
            return
        inst = self.instance or self.connect()

        # Prefer a safe order: set frequency/power first, toggle output last
        preferred = ["frequency", "power"]
        last = ["output_status"]
        keys = [k for k in preferred if k in settings] + \
               [k for k in settings.keys() if k not in preferred and k not in last] + \
               [k for k in last if k in settings]

        params = getattr(inst, "parameters", {})

        for key in keys:
            val = settings[key]
            self._apply_one(inst, params, key, val)

    @staticmethod
    def _apply_one(inst, params, key, val):
        try:
            if key in params:
                p = params[key]
                # try parameter API first
                try:
                    p.set(val)
                except Exception:
                    p(val)  # call-style fallback
                _logger.info("Set %s=%r via QCoDeS Parameter.", key, val)
                return

            # driver method named exactly 'key'
            if hasattr(inst, key) and callable(getattr(inst, key)):
                getattr(inst, key)(val)
                _logger.info("Called %s(%r).", key, val)
                return

            # driver method 'set_<key>'
            setter = f"set_{key}"
            if hasattr(inst, setter) and callable(getattr(inst, setter)):
                getattr(inst, setter)(val)
                _logger.info("Called %s(%r).", setter, val)
                return

            _logger.warning("Unknown setting '%s' for %r; skipping.", key, inst)

        except Exception as e:
            _logger.error("Failed applying %s=%r to %r: %s", key, val, inst, e, exc_info=True)
            raise

    def snapshot(self) -> Dict[str, Any]:
        """Return a light snapshot with spec + key parameter values if available."""
        snap: Dict[str, Any] = {"name": self.spec.name, "spec": self.spec.to_dict(), "connected": self.instance is not None}
        if self.instance is None:
            return snap

        inst = self.instance
        # Try QCoDeS snapshot
        with contextlib.suppress(Exception):
            if hasattr(inst, "snapshot"):
                s = inst.snapshot(update=False)
                snap["instrument"] = {"name": s.get("name"), "parameters": {}}
                params = s.get("parameters") or {}
                # include only simple scalars
                for k, v in params.items():
                    with contextlib.suppress(Exception):
                        val = v.get("value")
                        snap["instrument"]["parameters"][k] = val
                return snap

        # Fallback: read parameters dict directly
        with contextlib.suppress(Exception):
            ps = getattr(inst, "parameters", {})
            vals = {}
            for name, p in ps.items():
                with contextlib.suppress(Exception):
                    val = getattr(p, "get_latest", lambda: p())()
                    vals[name] = val
            snap["instrument"] = {"parameters": vals}
        return snap

    def ramp(self, param_name: str, target: float, step: float, delay_s: float = 0.1):
        """
        Ramp a callable parameter (e.g., inst.voltage5) to 'target' in steps of 'step',
        waiting 'delay_s' between steps. Shows a tqdm progress bar.
        """
        import time as _time
        from tqdm.auto import tqdm

        inst = self.instance or self.connect()
        if not hasattr(inst, param_name):
            raise DeviceError(f"{self.spec.name}: parameter '{param_name}' not found.")
        p = getattr(inst, param_name)
        if not callable(p):
            raise DeviceError(f"{self.spec.name}: parameter '{param_name}' is not callable.")

        # getter: calling with no args returns current value for instrumentserver params
        current = float(p())
        delta = target - current

        if delta == 0:
            _logger.info("No ramp needed: %s already at %.6g", param_name, current)
            return

        sign = np.sign(delta) or 1.0
        step = abs(step) * sign
        if step == 0:
            raise ValueError("step must be non-zero.")

        total_steps = int(ceil(abs(delta) / abs(step)))

        _logger.info(
            "Ramping %s.%s from %.6g to %.6g in steps of %.6g (delay %.3fs, %d steps)",
            self.spec.name, param_name, current, target, step, delay_s, total_steps
        )
        desc = f"Ramping {self.spec.name}.{param_name}"
        show_bar = _logger.isEnabledFor(logging.INFO)

        with tqdm(
            total=total_steps,
            desc=desc,
            unit="step",
            disable=not show_bar,   # <- key line
        ) as bar:
            for _ in range(total_steps):
                # stop if we've reached or crossed the target
                if (target - current) * sign <= 0:
                    break

                next_v = current + step
                # avoid overshoot on last step
                if (target - next_v) * sign < 0:
                    next_v = target

                p(float(next_v))
                current = next_v
                _logger.debug(" … set %s=%.6g", param_name, current)

                bar.update(1)
                _time.sleep(delay_s)

        _logger.info("Ramp complete: %s=%.6g", param_name, current)


class DeviceManager:
    """Manage a fleet of external devices declared in a JSON file.

    Typical use:
        dm = DeviceManager(cfg_dir/"devices.json")
        dm.instantiate_all()  # optional eager connect
        sc = dm.get("signalcore_pump")
        dm.apply("signalcore_pump", frequency=4.2e9)

    Edit devices.json (e.g., change serial/port), then call dm.reload().
    """

    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)
        self.specs: Dict[str, DeviceSpec] = {}
        self.handles: Dict[str, DeviceHandle] = {}
        self._lock = threading.RLock()

        if self.config_path.exists():
            self.load()
        else:
            self.save()  # create empty file
            _logger.info("Created empty device config at %s", self.config_path)

    # ---- helpers ---- #
    def _connect_with_logs(self, name: str, handle: DeviceHandle):
        _logger.info("Connecting device '%s' ...", name)
        t0 = time.perf_counter()
        try:
            inst = handle.connect()
            dt = time.perf_counter() - t0
            kind = type(inst).__name__ if inst is not None else "OK"
            _logger.info("Connected '%s' in %.2fs (%s).", name, dt, kind)
            return inst
        except Exception as e:
            dt = time.perf_counter() - t0
            _logger.error("FAILED to connect '%s' after %.2fs: %s", name, dt, e, exc_info=True)
            # ensure no dangling handle
            with self._lock:
                # only drop if this exact handle is currently registered
                if self.handles.get(name) is handle:
                    self.handles.pop(name, None)
            raise

    # ---- persistence ---- #
    def load(self) -> None:
        try:
            raw = self.config_path.read_text(encoding="utf-8-sig")
            _logger.info("Reading %s (%d bytes)", self.config_path, len(raw))
        except FileNotFoundError:
            _logger.warning("Config not found at %s; using empty.", self.config_path)
            raw = ""

        if not raw.strip():
            _logger.warning("Config file %s is empty.", self.config_path)
            data = {}
        else:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                raise DeviceError(f"Malformed devices JSON at {self.config_path}: {e}") from e

        # keep only enabled devices (default True)
        enabled_items = {k: v for k, v in data.items() if v.get("enabled", True)}
        skipped = set(data) - set(enabled_items)
        if skipped:
            _logger.info("Skipping disabled device(s): %s", ", ".join(sorted(skipped)))

        self.specs = {name: DeviceSpec.from_dict(name, spec) for name, spec in enabled_items.items()}
        _logger.info("Loaded %d device spec(s) from %s", len(self.specs), self.config_path)

    def save(self) -> None:
        payload = {name: spec.to_dict() for name, spec in self.specs.items()}
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        _logger.info("Saved %d device spec(s) to %s", len(payload), self.config_path)

    def instantiate(self, *names: str | list[str] | tuple[str, ...] | set[str]) -> None:
        """
        Instantiate a subset of devices.

        Usage:
            dm.instantiate("signalcore_pump")
            dm.instantiate("signalcore_pump", "octodac_bf")
            dm.instantiate(["signalcore_pump", "octodac_bf"])
        """
        # Allow a single iterable argument
        if len(names) == 1 and isinstance(names[0], (list, tuple, set)):
            names = tuple(names[0])

        if not names:
            _logger.info("instantiate(): no device names provided.")
            return

        with self._lock:
            for name in names:
                if name not in self.specs:
                    _logger.warning("instantiate(): device '%s' not in specs; skipping.", name)
                    continue

                # If already connected, skip
                existing = self.handles.get(name)
                if existing is not None and existing.instance is not None:
                    _logger.info("instantiate(): device '%s' already connected; skipping.", name)
                    continue

                spec = self.specs[name]
                temp_handle = DeviceHandle(spec)
                try:
                    self._connect_with_logs(name, temp_handle)
                    # success → store the handle
                    self.handles[name] = temp_handle
                except Exception as e:
                    # failure → do NOT store; ensure it isn't present
                    self.handles.pop(name, None)
                    _logger.warning("instantiate(): skipping '%s' (connect failed): %s", name, e)
                    
    # ---- lifecycle ---- #
    def instantiate_all(self) -> None:
        """
        Instantiate all enabled devices from specs.
        """
        with self._lock:
            if not self.specs:
                _logger.info("No devices to instantiate.")
                return
            _logger.info("Instantiating all %d device(s)...", len(self.specs))
            # Reuse the selective instantiate logic
            self.instantiate(list(self.specs.keys()))

    def _ensure_handle(self, name: str, spec: Optional[DeviceSpec] = None) -> DeviceHandle:
        h = self.handles.get(name)
        if h is None:
            _logger.info("Creating handle for '%s'.", name)
            h = DeviceHandle(spec or self.specs[name])
            self.handles[name] = h
        elif spec is not None and h.spec.to_dict() != spec.to_dict():
            _logger.info("Rebuilding handle for '%s' (spec changed).", name)
            with contextlib.suppress(Exception):
                h.disconnect()
            h = DeviceHandle(spec)
            self.handles[name] = h
        return h

    # ---- CRUD ---- #
    def add_or_update(self, name: str, **spec_fields: Any) -> Any:
        _logger.info("Add/update device '%s' with: %s", name, spec_fields)
        spec = DeviceSpec.from_dict(name, spec_fields)
        self.specs[name] = spec
        self.save()

        temp_handle = DeviceHandle(spec)
        try:
            inst = self._connect_with_logs(name, temp_handle)
            # success → register handle
            with self._lock:
                self.handles[name] = temp_handle
            return inst
        except Exception as e:
            # failure → ensure not present
            with self._lock:
                self.handles.pop(name, None)
            _logger.warning("Device '%s' not loaded due to connect failure: %s", name, e)
            # Return None (or re-raise if you prefer strict failure)
            return None

    def exists(self, name: str) -> bool:
        """True if an enabled spec with this name exists."""
        with self._lock:
            return name in self.specs
    
    def get(self, name: str, connect: bool = True) -> Any | None:
        with self._lock:
            if name not in self.specs:
                _logger.debug("Device '%s' not in specs.", name)
                return None

            h = self.handles.get(name)
            if h is not None and h.instance is not None:
                return h.instance

            if not connect:
                _logger.debug("Device '%s' present but not connected; connect=False.", name)
                return None

        # Attempt connect without registering until it succeeds
        temp_handle = DeviceHandle(self.specs[name])
        try:
            inst = self._connect_with_logs(name, temp_handle)
            with self._lock:
                self.handles[name] = temp_handle
            return inst
        except Exception as e:
            with self._lock:
                self.handles.pop(name, None)
            _logger.warning("get(%s): not loaded due to connect failure: %s", name, e)
            return None

    def apply(self, name: str, persist: bool = True, **settings: Any) -> None:
        _logger.info("Applying settings to '%s': %s (persist=%s)", name, settings, persist)
        spec = self.specs[name]
        if persist:
            spec.settings.update(settings)
            self.save()
        h = self._ensure_handle(name)
        if h.instance is None:
            self._connect_with_logs(name, h)
        h.apply(settings)
        _logger.info("Applied settings to '%s'.", name)

    def remove(self, name: str, disconnect: bool = True) -> None:
        _logger.info("Removing device '%s' (disconnect=%s).", name, disconnect)
        if disconnect:
            with contextlib.suppress(Exception):
                self.handles.get(name, None) and self.handles[name].disconnect()
        self.handles.pop(name, None)
        self.specs.pop(name, None)
        self.save()

    def reload(self) -> None:
        _logger.info("Reloading device config from %s ...", self.config_path)
        old = {k: v.to_dict() for k, v in self.specs.items()}
        self.load()
        new = {k: v.to_dict() for k, v in self.specs.items()}

        # removals
        for name in set(old) - set(new):
            _logger.info("Detected removal '%s'.", name)
            self.remove(name, disconnect=True)

        # additions/updates
        for name, spec_dict in new.items():
            if name not in old or old[name] != spec_dict:
                _logger.info("Detected %s for '%s'.", "new device" if name not in old else "spec change", name)
                inst = self.add_or_update(name, **spec_dict)
                if inst is None:
                    _logger.warning("Reload: '%s' not loaded (connect failed); leaving spec present.", name)


    # ---- info ---- #
    def snapshot(self) -> Dict[str, Any]:
        _logger.info("Snapshotting %d device(s).", len(self.specs))
        return {name: self._ensure_handle(name).snapshot() for name in self.specs}

    def ramp(self, name: str, param: str, to: float, step: float, delay_s: float = 0.1):
        h = self._ensure_handle(name)
        if h.instance is None:
            self._connect_with_logs(name, h)
        h.ramp(param, to, step, delay_s)