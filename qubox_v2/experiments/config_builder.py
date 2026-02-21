from __future__ import annotations
"""config_builder.py

Typed helper classes and a fluent ``ConfigBuilder`` to assemble Quantumâ€‘Machines
configuration dictionaries in code, *then* dump / load them to JSON.

This file is fully selfâ€‘contained; no external project imports are required.

Features:
  â€¢ Build a config programmatically via fluent API or minimal factory.
  â€¢ Call ``builder.to_json(path)`` / ``ConfigBuilder.from_json(path)``.
  â€¢ Call ``builder.to_dict()`` to hand straight to QuantumMachinesManager.
  â€¢ Roundâ€‘trip JSON validation (minimal and real configs).

Usage:
  python config_builder.py [config.json]

If no argument is given, exercises the minimal example.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Literal, Any
import importlib.util
import json
import yaml
from pathlib import Path


__all__ = [
    "Waveform", "IntegrationWeight", "Pulse", "Element", "Controller", "OctavePort",
    "ConfigBuilder"
]

@dataclass
class ConfigSettings:
    MAX_AMPLITUDE = 0.450
    MAX_IF_BANDWIDTH = 400e6
    BASE_IF = -20e6
    TIME_PER_CLOCK_CYCLE = 4

# -----------------------------------------------------------------------------
# â”€â”€â”€ Dataclasses for the domain model â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# -----------------------------------------------------------------------------

@dataclass
class Waveform:
    name: str
    wf_type: Literal["constant", "arbitrary"]
    samples: Any  # float for constant, List[float] for arbitrary

    def as_dict(self) -> Dict[str, Any]:
        if self.wf_type == "constant":
            return {"type": "constant", "sample": float(self.samples)}
        return {"type": "arbitrary", "samples": list(self.samples)}

@dataclass
class IntegrationWeight:
    name: str
    cosine: List[Tuple[float, int]]
    sine: List[Tuple[float, int]]

    def as_dict(self) -> Dict[str, Any]:
        return {"cosine": [list(p) for p in self.cosine], "sine": [list(p) for p in self.sine]}

@dataclass
class Pulse:
    name: str
    operation: Literal["control", "measurement"]
    length: int
    waveforms: Dict[str, str]
    digital_marker: str = "ON"
    integration_weights: Optional[Dict[str, str]] = None

    def as_dict(self) -> Dict[str, Any]:
        out = {
            "operation": self.operation,
            "length": self.length,
            "waveforms": self.waveforms,
            "digital_marker": self.digital_marker,
        }
        if self.operation == "measurement":
            out["integration_weights"] = self.integration_weights or {}
        return out

@dataclass
class Element:
    name: str
    rf_inputs: Dict[str, Tuple[str, int]]
    rf_outputs: Optional[Dict[str, Tuple[str, int]]] = None
    intermediate_frequency: float = 0.0
    digital_inputs: Optional[Dict[str, Any]] = None
    time_of_flight: Optional[int] = None
    operations: Dict[str, str] = field(default_factory=dict)
    type: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "RF_inputs": {k: list(v) for k, v in self.rf_inputs.items()},
            "intermediate_frequency": self.intermediate_frequency,
            "operations": self.operations,
        }
        if self.rf_outputs:
            d["RF_outputs"] = {k: list(v) for k, v in self.rf_outputs.items()}
        if self.digital_inputs:
            d["digitalInputs"] = self.digital_inputs
        if self.time_of_flight is not None:
            d["time_of_flight"] = self.time_of_flight
        if self.type:
            d["type"] = self.type
        return d

@dataclass
class Controller:
    name: str
    analog_outputs: Dict[int, Dict[str, float]]
    digital_outputs: Dict[int, Dict]
    analog_inputs: Dict[int, Dict[str, float]]

    def as_dict(self) -> Dict[str, Any]:
        return {self.name: {"analog_outputs": self.analog_outputs,
                             "digital_outputs": self.digital_outputs,
                             "analog_inputs": self.analog_inputs}}

@dataclass
class OctavePort:
    name: str
    rf_outputs: Dict[int, Dict[str, Any]]
    rf_inputs: Dict[int, Dict[str, Any]]
    connectivity: str

    def as_dict(self) -> Dict[str, Any]:
        return {self.name: {"RF_outputs": self.rf_outputs,
                             "RF_inputs": self.rf_inputs,
                             "connectivity": self.connectivity}}

def _import_module_from_path(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# -----------------------------------------------------------------------------
# â”€â”€â”€ ConfigBuilder â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# -----------------------------------------------------------------------------

class ConfigBuilder:
    _VERSION = 1

    def __init__(self):
        self.controllers: Dict[str, Controller] = {}
        self.octaves: Dict[str, OctavePort] = {}
        self.waveforms: Dict[str, Waveform] = {}
        self.int_weights: Dict[str, IntegrationWeight] = {}
        self.pulses: Dict[str, Pulse] = {}
        self.elements: Dict[str, Element] = {}
        self.digital_waveforms: Dict[str, Any] = {"ON": {"samples": [[1, 0]]}, "OFF": {"samples": [[0, 0]]}}

    @classmethod
    def minimal_config(cls) -> ConfigBuilder:
        """Factory: returns a builder preâ€‘populated with the minimal example."""
        b = cls()
        # controller & octave
        b.add_controller(Controller("con1", {1: {"offset": 0.0}, 2: {"offset": 0.0}}, {1: {}}, {1: {"offset": 0.0}}))
        b.add_octave(OctavePort("oct1",
            {1: {"LO_frequency": 8.8e9, "LO_source": "internal", "output_mode": "always_on", "gain": 0}},
            {}, "con1"))
        # waveforms & weights
        b.define_waveform("zero_wf", "constant", 0.0)
        b.define_waveform("const_wf", "constant", 0.24)
        b.define_int_weight("cosine_weights", [(1.0, 1000)], [(0.0, 1000)])
        b.define_int_weight("sine_weights",   [(0.0, 1000)], [(1.0, 1000)])
        b.define_int_weight("minus_cosine_weights", [(-1.0, 1000)], [(0.0, 1000)])
        b.define_int_weight("minius_sine_weights",   [(0.0, 1000)], [(-1.0, 1000)])
        # pulses
        b.define_pulse("const_pulse", "control",     1000, {"I": "const_wf", "Q": "zero_wf"})
        b.define_pulse("readout_pulse", "measurement", 1000,
                       {"I": "const_wf", "Q": "zero_wf"},
                       integration_weights={"cos": "cosine", "sin": "sine_weights",
                                            "minus_cos": "minus_cosine_weights", "minus_sine":"minius_sine_weights"})
        # element & operations
        b.define_element("resonator",
                         {"port": ("oct1", 1)}, {"port": ("oct1", 1)},
                         intermediate_frequency=-50e6, time_of_flight=256)
        b.map_operation("resonator", "const",   "const_pulse")
        b.map_operation("resonator", "readout", "readout_pulse")
        return b

    def add_controller(self, c: Controller) -> ConfigBuilder:
        self.controllers[c.name] = c
        return self

    def add_octave(self, o: OctavePort) -> ConfigBuilder:
        self.octaves[o.name] = o
        return self

    def define_waveform(self, name: str, wf_type: Literal["constant","arbitrary"], samples: Any) -> ConfigBuilder:
        self.waveforms[name] = Waveform(name, wf_type, samples)
        return self

    def define_int_weight(self, name: str, cosine: List[Tuple[float,int]], sine: List[Tuple[float,int]]) -> ConfigBuilder:
        self.int_weights[name] = IntegrationWeight(name, cosine, sine)
        return self

    def define_pulse(self, name: str, operation: Literal["control","measurement"], length: int,
                     waveforms: Dict[str,str], digital_marker: str = "ON",
                     integration_weights: Optional[Dict[str,str]] = None) -> ConfigBuilder:
        for ch, wf in waveforms.items():
            if wf not in self.waveforms:
                raise ValueError(f"Missing waveform '{wf}' for pulse '{name}'")
        if operation == "measurement":
            if integration_weights is None:
                raise ValueError("Measurement pulses require integration_weights mapping")
            for lbl, iw in integration_weights.items():
                if iw not in self.int_weights:
                    raise ValueError(f"Missing integration weight '{iw}' for pulse '{name}'")
        self.pulses[name] = Pulse(name, operation, length, waveforms, digital_marker, integration_weights)
        return self

    def define_element(self, name: str, rf_inputs: Dict[str,Tuple[str,int]],
                       rf_outputs: Optional[Dict[str,Tuple[str,int]]] = None,
                       intermediate_frequency: float = 0.0,
                       digital_inputs: Optional[Dict[str,Any]] = None,
                       time_of_flight: Optional[int] = None,
                       type: Optional[str] = None) -> ConfigBuilder:
        self.elements[name] = Element(name, rf_inputs, rf_outputs, intermediate_frequency, digital_inputs, time_of_flight, {}, type)
        return self

    def map_operation(self, el: str, op: str, pulse: str) -> ConfigBuilder:
        if pulse not in self.pulses:
            raise ValueError(f"Pulse '{pulse}' not defined")
        if el not in self.elements:
            raise ValueError(f"Element '{el}' not defined")
        self.elements[el].operations[op] = pulse
        return self

    def to_dict(self) -> Dict[str,Any]:
        cfg: Dict[str,Any] = {"version": self._VERSION}
        cfg["controllers"] = {};
        cfg["octaves"] = {};
        for c in self.controllers.values(): cfg["controllers"].update(c.as_dict())
        for o in self.octaves.values():    cfg["octaves"].update(o.as_dict())
        cfg["elements"] = {n: e.as_dict() for n,e in self.elements.items()}
        cfg["pulses"] = {n: p.as_dict() for n,p in self.pulses.items()}
        cfg["waveforms"] = {n: w.as_dict() for n,w in self.waveforms.items()}
        cfg["integration_weights"] = {n: iw.as_dict() for n,iw in self.int_weights.items()}
        # normalize digital waveforms
        dw = { name: {"samples": [list(p) for p in data.get("samples",[])]} 
               for name,data in self.digital_waveforms.items() }
        cfg["digital_waveforms"] = dw
        return cfg

    def pprint(self) -> None:
        import pprint; pprint.pp(self.to_dict(), sort_dicts=False)

    def to_json(self, path: str, **kw) -> None:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=4, **kw)

    def to_split_sources(
        self,
        hardware_path: str | Path,
        pulses_py_path: str | Path,
        mapping_path: str | Path,
        **kw
    ) -> None:
        """
        Write out three source files:
          - hardware.json: controllers, octaves, elements (no operations)
          - pulses.py: Python module with WAVEFORMS, INTEGRATION_WEIGHTS, PULSES dicts
          - mapping.json: element->operation mappings
        """
        # hardware.json
        hw = {"version": self._VERSION,
              "controllers": {n: c.as_dict()[n] for n, c in self.controllers.items()},
              "octaves":     {n: o.as_dict()[n] for n, o in self.octaves.items()},
              "elements": {} }
        for name, el in self.elements.items():
            d = el.as_dict().copy()
            d.pop("operations", None)
            hw["elements"][name] = d
        Path(hardware_path).write_text(json.dumps(hw, indent=4, **kw), encoding="utf-8")

        # pulses.py
        pulses_py = Path(pulses_py_path)
        header = [
            "# Auto-generated pulses library",
            "from qualang_tools.config.waveform_tools import drag_gaussian_pulse_waveforms",
            "from qualang_tools.units import unit",
            ""
        ]
        lines = header[:]
        # WAVEFORMS
        lines.append("WAVEFORMS = {")
        for nm, wf in self.waveforms.items():
            lines.append(f"    {nm!r}: {wf.as_dict()!r},")
        lines.append("}\n")
        # INTEGRATION_WEIGHTS
        lines.append("INTEGRATION_WEIGHTS = {")
        for nm, iw in self.int_weights.items():
            lines.append(f"    {nm!r}: {iw.as_dict()!r},")
        lines.append("}\n")
        # PULSES
        lines.append("PULSES = {")
        for nm, p in self.pulses.items():
            lines.append(f"    {nm!r}: {p.as_dict()!r},")
        lines.append("}\n")
        pulses_py.write_text("\n".join(lines), encoding="utf-8")

        # mapping.json
        mp = {"version": self._VERSION,
              "elements": {n: el.operations for n, el in self.elements.items()}}
        Path(mapping_path).write_text(json.dumps(mp, indent=4, **kw), encoding="utf-8")

    @classmethod
    def from_split_sources(
        cls,
        hardware_path: str | Path,
        pulses_py_path: str | Path,
        mapping_path: str | Path
    ) -> ConfigBuilder:
        """
        Build a ConfigBuilder by reading:
          - hardware.json (controllers, octaves, elements)
          - pulses.py    (WAVEFORMS, INTEGRATION_WEIGHTS, PULSES dicts)
          - mapping.json (element->operation map)
        """
        b = cls()

        # helper to turn "1", "2", etc. into int(1), int(2), but leave "switch" as-is
        def coerce_numeric_keys(d: dict) -> dict:
            out = {}
            for k, v in d.items():
                try:
                    new_k = int(k)
                except ValueError:
                    new_k = k
                out[new_k] = v
            return out

        # --- load hardware ---
        hw = json.loads(Path(hardware_path).read_text(encoding="utf-8"))

        # controllers
        for name, c in hw.get("controllers", {}).items():
            analog_outputs  = coerce_numeric_keys(c.get("analog_outputs", {}))
            digital_outputs = coerce_numeric_keys(c.get("digital_outputs", {}))
            analog_inputs   = coerce_numeric_keys(c.get("analog_inputs",  {}))
            b.add_controller(Controller(
                name,
                analog_outputs,
                digital_outputs,
                analog_inputs
            ))

        # octaves
        for name, o in hw.get("octaves", {}).items():
            rf_outputs = coerce_numeric_keys(o.get("RF_outputs", {}))
            rf_inputs  = coerce_numeric_keys(o.get("RF_inputs",  {}))
            b.add_octave(OctavePort(
                name,
                rf_outputs,
                rf_inputs,
                o.get("connectivity", "con1")
            ))

        # elements
        for name, el in hw.get("elements", {}).items():
            # numeric-string â†’ int for digitalInputs keys; leave others
            digital_inputs = coerce_numeric_keys(el.get("digitalInputs", {}))

            # ensure all RF port channels are ints
            rf_inputs = {
                port_name: (device, int(chan))
                for port_name, (device, chan) in el.get("RF_inputs", {}).items()
            }
            rf_outputs = {
                port_name: (device, int(chan))
                for port_name, (device, chan) in el.get("RF_outputs", {}).items()
            }

            b.define_element(
                name,
                rf_inputs,
                rf_outputs,
                el.get("intermediate_frequency", 0.0),
                digital_inputs,
                el.get("time_of_flight"),
                el.get("type")
            )

        # --- load pulses.py module ---
        spec = importlib.util.spec_from_file_location("pulses", Path(pulses_py_path))
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        for nm, wf in getattr(mod, "WAVEFORMS", {}).items():
            if wf["type"] == "constant":
                b.define_waveform(nm, wf["type"], wf.get("sample"))
            else:
                b.define_waveform(nm, wf["type"], wf.get("samples"))

        for nm, iw in getattr(mod, "INTEGRATION_WEIGHTS", {}).items():
            b.define_int_weight(nm, iw.get("cosine", []), iw.get("sine", []))

        for nm, p in getattr(mod, "PULSES", {}).items():
            b.define_pulse(
                nm,
                p.get("operation"),
                p.get("length"),
                p.get("waveforms", {}),
                p.get("digital_marker", "ON"),
                p.get("integration_weights")
            )

        # --- load mapping.json ---
        mp = json.loads(Path(mapping_path).read_text(encoding="utf-8"))
        for el_n, ops in mp.get("elements", {}).items():
            for op, pulse in ops.items():
                b.map_operation(el_n, op, pulse)

        return b

    
    # Keep original to_json for backward compatibility
    def to_json(self, path: str, **kw) -> None:
        """Dump the full combined config to a single JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=4, **kw)

    @classmethod
    def from_json(cls, path: str) -> ConfigBuilder:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, d: Dict[str,Any]) -> ConfigBuilder:
        b = cls()
        # controllers
        for c_name, c_dict in d.get("controllers", {}).items():
            ao = {int(k): v for k, v in c_dict.get("analog_outputs", {}).items()}
            do = {int(k): v for k, v in c_dict.get("digital_outputs", {}).items()}
            ai = {int(k): v for k, v in c_dict.get("analog_inputs", {}).items()}
            b.controllers[c_name] = Controller(c_name, ao, do, ai)
        # octaves
        for o_name, o_dict in d.get("octaves", {}).items():
            ro = {int(k): v for k, v in o_dict.get("RF_outputs", {}).items()}
            ri = {int(k): v for k, v in o_dict.get("RF_inputs", {}).items()}
            b.octaves[o_name] = OctavePort(o_name, ro, ri, o_dict.get("connectivity", "con1"))
        # waveforms
        for wf_name, wf_dict in d.get("waveforms", {}).items():
            samples = wf_dict["sample"] if wf_dict["type"] == "constant" else wf_dict["samples"]
            b.waveforms[wf_name] = Waveform(wf_name, wf_dict["type"], samples)
        # integration weights
        for iw_name, iw_dict in d.get("integration_weights", {}).items():
            cosine = [(c[0], c[1]) for c in iw_dict.get("cosine", [])]
            sine   = [(s[0], s[1]) for s in iw_dict.get("sine", [])]
            b.int_weights[iw_name] = IntegrationWeight(iw_name, cosine, sine)
        # pulses
        for p_name, p_dict in d.get("pulses", {}).items():
            b.pulses[p_name] = Pulse(
                p_name,
                p_dict["operation"],
                p_dict["length"],
                p_dict["waveforms"],
                p_dict.get("digital_marker", "ON"),
                p_dict.get("integration_weights")
            )
        # elements
        for el_name, el_dict in d.get("elements", {}).items():
            rf_in = {k: tuple(v) for k, v in el_dict.get("RF_inputs", {}).items()}
            rf_out = {k: tuple(v) for k, v in el_dict.get("RF_outputs", {}).items()} if el_dict.get("RF_outputs") else None
            b.elements[el_name] = Element(
                el_name,
                rf_in,
                rf_out,
                el_dict.get("intermediate_frequency", 0.0),
                el_dict.get("digitalInputs"),
                el_dict.get("time_of_flight"),
                el_dict.get("operations", {}),
                el_dict.get("type")
            )

        # restore any digital waveforms override
        b.digital_waveforms = d.get("digital_waveforms", b.digital_waveforms)
        # *** missing return ***
        return b



if __name__ == "__main__":

    from qm.qua import *
    from qm.octave import *
    from qm import QuantumMachinesManager

    builder = ConfigBuilder.from_json("data/seq_1_device/config.json")
    config_dict = builder.to_dict()
    qmm = QuantumMachinesManager(host="10.157.36.68", cluster_name="Cluster_2", octave_calibration_db_path="./")
    qm = qmm.open_qm(config_dict)

