# qubox_v2/devices/device_manager.py
"""
DeviceManager: external device lifecycle management.

Manages a fleet of external instruments (SignalCore, OctoDac, etc.) declared
in a JSON configuration file. Supports QCoDeS and InstrumentServer backends.

This module is largely preserved from the original qubox.device_manager with
updated error imports.
"""
from __future__ import annotations

import contextlib
import importlib
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from tqdm.auto import tqdm

from ..core.errors import DeviceError

_logger = logging.getLogger(__name__)


# ─────────────────────────────────── Spec ─────────────────────────────────────
@dataclass
class DeviceSpec:
    """Declarative specification for a single external device."""

    name: str
    driver: str                       # "module.submodule:ClassName"
    backend: str = "qcodes"           # "qcodes" | "instrumentserver" | "direct"
    connect: Dict[str, Any] = field(default_factory=dict)
    settings: Dict[str, Any] = field(default_factory=dict)
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
    def from_dict(cls, name: str, d: Dict[str, Any]) -> DeviceSpec:
        if d is None:
            raise DeviceError(f"Device '{name}' spec is None.")
        backend = d.get("backend", "qcodes")
        if backend.lower() != "instrumentserver" and "driver" not in d:
            raise DeviceError(f"Device '{name}' missing required field 'driver'.")
        return cls(
            name=name,
            driver=d.get("driver", "instrumentserver:Instrument"),
            backend=backend,
            connect=d.get("connect", {}) or {},
            settings=d.get("settings", {}) or {},
            enabled=bool(d.get("enabled", True)),
        )


# ─────────────────────────────────── Handle ───────────────────────────────────
class DeviceHandle:
    """Wraps a single device: import → connect → apply → disconnect."""

    def __init__(self, spec: DeviceSpec):
        self.spec = spec
        self.instance = None
        self._client = None  # instrumentserver client

    def _import_driver(self):
        mod_name, cls_name = self.spec.driver.split(":", 1)
        module = importlib.import_module(mod_name)
        return getattr(module, cls_name)

    def connect(self):
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
            cls = self._import_driver()
            _logger.info("QCoDeS create/find: %s(name=%r)", cls.__name__, name)
            self.instance = qc.find_or_create_instrument(instrument_class=cls, name=name, **kwargs)

        elif self.spec.backend.lower() == "instrumentserver":
            try:
                from instrumentserver.client import Client
            except ModuleNotFoundError as e:
                raise DeviceError(f"{self.spec.name}: instrumentserver backend not found.") from e
            c = self.spec.connect
            host, port = c.get("host"), c.get("port")
            timeout = c.get("timeout", 60000)
            inst_name = c.get("instrument_name") or self.spec.name
            if not host or not port:
                raise DeviceError(f"{self.spec.name}: 'host' and 'port' required for instrumentserver.")
            client = Client(host=host, port=port, timeout=timeout)
            self._client = client
            self.instance = client.get_instrument(inst_name)

        else:
            cls = self._import_driver()
            self.instance = cls(**self.spec.connect)

        # Apply initial settings
        if self.spec.settings:
            ramp_keys = []
            normal_settings = {}
            for k, v in self.spec.settings.items():
                if isinstance(v, (int, float)) and re.fullmatch(r"voltage\d*", k):
                    ramp_keys.append((k, float(v)))
                else:
                    normal_settings[k] = v

            step = float(self.spec.connect.get("ramp_step", 0.001))
            delay = float(self.spec.connect.get("ramp_delay_s", 0.1))

            for k, target in ramp_keys:
                try:
                    self.ramp(k, target, step=step, delay_s=delay)
                except Exception:
                    _logger.exception("Ramp on init failed for %s; falling back to direct set.", k)
                    try:
                        self._apply_one(self.instance, getattr(self.instance, "parameters", {}), k, target)
                    except Exception:
                        _logger.exception("Fallback set also failed for %s.", k)
                        raise

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
        with contextlib.suppress(Exception):
            if self._client and hasattr(self._client, "close"):
                self._client.close()
        self.instance = None
        self._client = None

    def apply(self, settings: Dict[str, Any]):
        if not settings:
            return
        inst = self.instance or self.connect()
        preferred = ["frequency", "power"]
        last = ["output_status"]
        keys = ([k for k in preferred if k in settings] +
                [k for k in settings if k not in preferred and k not in last] +
                [k for k in last if k in settings])
        params = getattr(inst, "parameters", {})
        for key in keys:
            self._apply_one(inst, params, key, settings[key])

    @staticmethod
    def _apply_one(inst, params, key, val):
        try:
            if key in params:
                p = params[key]
                try:
                    p.set(val)
                except Exception:
                    p(val)
                _logger.info("Set %s=%r via QCoDeS Parameter.", key, val)
                return
            if hasattr(inst, key) and callable(getattr(inst, key)):
                getattr(inst, key)(val)
                _logger.info("Called %s(%r).", key, val)
                return
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
        snap: Dict[str, Any] = {"name": self.spec.name, "spec": self.spec.to_dict(),
                                 "connected": self.instance is not None}
        if self.instance is None:
            return snap
        inst = self.instance
        with contextlib.suppress(Exception):
            if hasattr(inst, "snapshot"):
                s = inst.snapshot(update=False)
                snap["instrument"] = {"name": s.get("name"), "parameters": {}}
                for k, v in (s.get("parameters") or {}).items():
                    with contextlib.suppress(Exception):
                        snap["instrument"]["parameters"][k] = v.get("value")
                return snap
        with contextlib.suppress(Exception):
            ps = getattr(inst, "parameters", {})
            vals = {}
            for name, p in ps.items():
                with contextlib.suppress(Exception):
                    vals[name] = getattr(p, "get_latest", lambda: p())()
            snap["instrument"] = {"parameters": vals}
        return snap

    def ramp(self, param_name: str, target: float, step: float, delay_s: float = 0.1):
        inst = self.instance or self.connect()
        if not hasattr(inst, param_name):
            raise DeviceError(f"{self.spec.name}: parameter '{param_name}' not found.")
        p = getattr(inst, param_name)
        if not callable(p):
            raise DeviceError(f"{self.spec.name}: parameter '{param_name}' is not callable.")

        current = float(p())
        delta = target - current
        if delta == 0:
            _logger.info("No ramp needed: %s already at %.6g", param_name, current)
            return

        sign = np.sign(delta) or 1.0
        step = abs(step) * sign
        total_steps = int(ceil(abs(delta) / abs(step)))

        _logger.info("Ramping %s.%s from %.6g to %.6g (%d steps)", self.spec.name, param_name, current, target, total_steps)
        show_bar = _logger.isEnabledFor(logging.INFO)
        with tqdm(total=total_steps, desc=f"Ramping {self.spec.name}.{param_name}", unit="step", disable=not show_bar) as bar:
            for _ in range(total_steps):
                if (target - current) * sign <= 0:
                    break
                next_v = current + step
                if (target - next_v) * sign < 0:
                    next_v = target
                p(float(next_v))
                current = next_v
                bar.update(1)
                time.sleep(delay_s)
        _logger.info("Ramp complete: %s=%.6g", param_name, current)


# ─────────────────────────────────── Manager ──────────────────────────────────
class DeviceManager:
    """Manage a fleet of external devices declared in a JSON file."""

    def __init__(self, config_path: str | Path):
        self.config_path = Path(config_path)
        self.specs: Dict[str, DeviceSpec] = {}
        self.handles: Dict[str, DeviceHandle] = {}
        self._lock = threading.RLock()

        if self.config_path.exists():
            self.load()
        else:
            self.save()
            _logger.info("Created empty device config at %s", self.config_path)

    def _connect_with_logs(self, name: str, handle: DeviceHandle):
        _logger.info("Connecting device '%s' ...", name)
        t0 = time.perf_counter()
        try:
            inst = handle.connect()
            dt = time.perf_counter() - t0
            _logger.info("Connected '%s' in %.2fs (%s).", name, dt, type(inst).__name__ if inst else "OK")
            return inst
        except Exception as e:
            dt = time.perf_counter() - t0
            _logger.error("FAILED to connect '%s' after %.2fs: %s", name, dt, e, exc_info=True)
            with self._lock:
                if self.handles.get(name) is handle:
                    self.handles.pop(name, None)
            raise

    # ── Persistence ──
    def load(self) -> None:
        try:
            raw = self.config_path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            _logger.warning("Config not found at %s; using empty.", self.config_path)
            return
        if not raw.strip():
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise DeviceError(f"Malformed devices JSON: {e}") from e
        enabled = {k: v for k, v in data.items() if v.get("enabled", True)}
        self.specs = {name: DeviceSpec.from_dict(name, spec) for name, spec in enabled.items()}
        _logger.info("Loaded %d device spec(s) from %s", len(self.specs), self.config_path)

    def save(self) -> None:
        payload = {name: spec.to_dict() for name, spec in self.specs.items()}
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ── Lifecycle ──
    def instantiate(self, *names: str | list[str] | tuple[str, ...] | set[str]) -> None:
        if len(names) == 1 and isinstance(names[0], (list, tuple, set)):
            names = tuple(names[0])
        if not names:
            return
        with self._lock:
            for name in names:
                if name not in self.specs:
                    _logger.warning("Device '%s' not in specs; skipping.", name)
                    continue
                existing = self.handles.get(name)
                if existing is not None and existing.instance is not None:
                    continue
                h = DeviceHandle(self.specs[name])
                try:
                    self._connect_with_logs(name, h)
                    self.handles[name] = h
                except Exception as e:
                    self.handles.pop(name, None)
                    _logger.warning("Skipping '%s': %s", name, e)

    def instantiate_all(self) -> None:
        if self.specs:
            self.instantiate(list(self.specs.keys()))

    def _ensure_handle(self, name: str, spec: Optional[DeviceSpec] = None) -> DeviceHandle:
        h = self.handles.get(name)
        if h is None:
            h = DeviceHandle(spec or self.specs[name])
            self.handles[name] = h
        elif spec is not None and h.spec.to_dict() != spec.to_dict():
            with contextlib.suppress(Exception):
                h.disconnect()
            h = DeviceHandle(spec)
            self.handles[name] = h
        return h

    # ── CRUD ──
    def add_or_update(self, name: str, **spec_fields: Any) -> Any:
        spec = DeviceSpec.from_dict(name, spec_fields)
        self.specs[name] = spec
        self.save()
        h = DeviceHandle(spec)
        try:
            inst = self._connect_with_logs(name, h)
            with self._lock:
                self.handles[name] = h
            return inst
        except Exception:
            with self._lock:
                self.handles.pop(name, None)
            return None

    def exists(self, name: str) -> bool:
        return name in self.specs

    def get(self, name: str, connect: bool = True) -> Any | None:
        with self._lock:
            if name not in self.specs:
                return None
            h = self.handles.get(name)
            if h is not None and h.instance is not None:
                return h.instance
            if not connect:
                return None
        h = DeviceHandle(self.specs[name])
        try:
            inst = self._connect_with_logs(name, h)
            with self._lock:
                self.handles[name] = h
            return inst
        except Exception:
            with self._lock:
                self.handles.pop(name, None)
            return None

    def apply(self, name: str, persist: bool = True, **settings: Any) -> None:
        spec = self.specs[name]
        if persist:
            spec.settings.update(settings)
            self.save()
        h = self._ensure_handle(name)
        if h.instance is None:
            self._connect_with_logs(name, h)
        h.apply(settings)

    def remove(self, name: str, disconnect: bool = True) -> None:
        if disconnect:
            with contextlib.suppress(Exception):
                h = self.handles.get(name)
                if h:
                    h.disconnect()
        self.handles.pop(name, None)
        self.specs.pop(name, None)
        self.save()

    def reload(self) -> None:
        old = {k: v.to_dict() for k, v in self.specs.items()}
        self.load()
        new = {k: v.to_dict() for k, v in self.specs.items()}
        for name in set(old) - set(new):
            self.remove(name, disconnect=True)
        for name, sd in new.items():
            if name not in old or old[name] != sd:
                self.add_or_update(name, **sd)

    def snapshot(self) -> Dict[str, Any]:
        return {name: self._ensure_handle(name).snapshot() for name in self.specs}

    def ramp(self, name: str, param: str, to: float, step: float, delay_s: float = 0.1):
        h = self._ensure_handle(name)
        if h.instance is None:
            self._connect_with_logs(name, h)
        h.ramp(param, to, step, delay_s)
