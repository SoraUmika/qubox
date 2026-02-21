from __future__ import annotations
from ..programs import cQED_programs
from ..analysis.output import Output
from ..analysis.analysis_tools import (
    two_state_discriminator, apply_norm_IQ, compute_probabilities
)
from ..analysis import post_process as pp
from .gates_legacy import Gate, Displacement, SNAP, Measure
from ..analysis.cQED_attributes import cQED_attributes
from ..analysis.algorithms import PeakObjective, lock_to_peak_3pt, peak_score_robust, random_sequences, refine_around, scout_windows
from ..analysis.post_selection import PostSelectionConfig
from pathlib import Path
from typing import Any, Tuple, Mapping, List, Union
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from .config_builder import ConfigBuilder, ConfigSettings
from ..hardware.program_runner import ExecMode, RunResult
from ..hardware.controller import HardwareController
from ..hardware.config_engine import ConfigEngine
# Legacy compat import QuaProgramManager, RunResult, ExecMode
from ..hardware.qua_program_manager import QuaProgramManager
from ..pulses.manager import PulseOperationManager, PulseOp, MAX_AMPLITUDE
from ..programs.macros.measure import measureMacro
from ..core.logging import temporarily_set_levels
from ..devices.device_manager import DeviceManager
from qualang_tools.config.waveform_tools import drag_gaussian_pulse_waveforms
from qualang_tools.units import unit as qm_unit
import logging
from qm import qua
from ..analysis.metrics import butterfly_metrics
from typing import Any, Dict, Optional
from octave_sdk import RFOutputMode
from tqdm import tqdm
from dataclasses import dataclass, field
# ---------------------------------------------------------------------------
# Module logger (safe to import multiple times; won't duplicate handlers)
# ---------------------------------------------------------------------------
_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Post-Selection Configuration
# ---------------------------------------------------------------------------

def _make_lo_segments(rf_begin: float, rf_end: float) -> list[float]:
    M, B = ConfigSettings.MAX_IF_BANDWIDTH, ConfigSettings.BASE_IF
    if M <= abs(B):
        raise ValueError("MAX_IF_BANDWIDTH must be greater than BASE_IF")
    span = M + B
    if (rf_end - rf_begin) <= span:
        return [rf_begin + M]
    los, LO, last = [], rf_begin + M, rf_end - B
    while LO < last:
        los.append(LO)
        LO += span
    if los[-1] < last:
        los.append(last)
    return los
        
def _if_frequencies_for_segment(LO: float, rf_end: float, df: float) -> np.ndarray:
    M, B = ConfigSettings.MAX_IF_BANDWIDTH, ConfigSettings.BASE_IF
    max_if = (rf_end - LO) if (rf_end - LO) < (M + B) else B
    return np.arange(-M, max_if + 1e-12, df, dtype=int)

def _merge_segments(outputs: list[Output], freqs: list[np.ndarray]) -> Output:
    merged = {}
    # stitch every key
    for key in outputs[0]:
        vals = [o[key] for o in outputs if key in o]
        if isinstance(vals[0], np.ndarray):
            try:
                merged[key] = np.concatenate(vals, axis=0)
            except Exception:
                merged[key] = vals
        elif isinstance(vals[0], list):
            merged[key] = sum(vals, [])
        else:
            merged[key] = vals[0] if all(v == vals[0] for v in vals) else vals
    # flatten freq axis
    merged["frequencies"] = np.concatenate(freqs, axis=0)
    return Output(merged)

def create_if_frequencies(el, start_fq, end_fq, df, lo_freq, base_if_freq=ConfigSettings.BASE_IF):
    up_converted_if = lo_freq + base_if_freq
    max_bandiwdth = np.abs(ConfigSettings.MAX_IF_BANDWIDTH - np.abs(base_if_freq))
    sweep_min_bound, sweep_max_bound = up_converted_if - max_bandiwdth, up_converted_if
    if sweep_min_bound <= start_fq <= end_fq <= sweep_max_bound:
        return np.arange(start_fq - lo_freq,  end_fq - lo_freq - 0.1, df, dtype=int)
    else:
        raise ValueError(f"Sweep range must be bounded by: [{sweep_min_bound},{sweep_max_bound}] \n for element: {el} which has LO, IF = {lo_freq*1e-6}, {base_if_freq*1e-6} MHz respectively")

def create_clks_array(t_begin, t_end, dt, time_per_clk: float = 4):
    """
    Return an array in units of 'clks', given times in a consistent unit.

    - 1 clk = time_per_clk (same unit as t_begin/t_end/dt, e.g. 4 ns).
    - If t_begin, t_end, or dt are not multiples of time_per_clk,
      they are rounded to the nearest multiple and a warning is issued.

    Parameters
    ----------
    t_begin : int or float
        Start time (arbitrary but consistent unit).
    t_end : int or float
        End time (same unit, must be >= t_begin).
    dt : int or float
        Step (same unit, must be > 0).
    time_per_clk : float
        Time per clock tick in the same unit.

    Returns
    -------
    np.ndarray of int
        Clock indices: [clk_begin, clk_begin + step_clks, ..., clk_end]
    """
    if t_end < t_begin:
        raise ValueError("t_end must be >= t_begin")
    if dt <= 0:
        raise ValueError("dt must be positive")
    if time_per_clk <= 0:
        raise ValueError("time_per_clk must be positive")

    def _round_to_multiple(x, base):
        return round(x / base) * base

    # Save originals
    orig_t_begin, orig_t_end, orig_dt = t_begin, t_end, dt

    # Snap to nearest grid
    t_begin = _round_to_multiple(t_begin, time_per_clk)
    t_end   = _round_to_multiple(t_end,   time_per_clk)
    dt      = _round_to_multiple(dt,      time_per_clk)

    # Warn if anything changed
    if (t_begin != orig_t_begin) or (t_end != orig_t_end) or (dt != orig_dt):
        warnings.warn(
            f"Times were rounded to nearest {time_per_clk} unit multiple: "
            f"t_begin {orig_t_begin}â†’{t_begin}, "
            f"t_end {orig_t_end}â†’{t_end}, "
            f"dt {orig_dt}â†’{dt}",
            RuntimeWarning,
        )

    # Re-check after rounding
    if t_end < t_begin:
        raise ValueError(f"After rounding, t_end ({t_end}) < t_begin ({t_begin}).")
    if dt <= 0:
        raise ValueError(f"After rounding, dt must be positive (got {dt}).")

    clk_begin = int(t_begin // time_per_clk)
    clk_end   = int(t_end   // time_per_clk)
    clk_step  = int(dt      // time_per_clk)

    return np.arange(clk_begin, clk_end + 1, clk_step, dtype=int)


def time_to_clks(time, time_per_clk: float = 4):
    """
    Convert a time (or array of times) to clock indices.

    - 1 clk = time_per_clk (same unit as `time`).
    - Rounds to nearest clock.
    - Issues a warning if any value is not exactly on the clock grid.

    Parameters
    ----------
    time : float | int | array-like
        Time(s) in any consistent unit.
    time_per_clk : float
        Time per clock tick in the same unit.

    Returns
    -------
    int | np.ndarray
        Clock index/indices.
    """
    if time_per_clk <= 0:
        raise ValueError("time_per_clk must be positive")

    arr = np.asarray(time, dtype=float)

    clks = np.rint(arr / time_per_clk).astype(int)
    snapped = clks * time_per_clk

    if np.any(snapped != arr):
        warnings.warn(
            f"Times were rounded to nearest {time_per_clk} unit grid: "
            f"original={arr}, snapped={snapped}",
            RuntimeWarning,
        )

    if np.isscalar(time):
        return int(clks.item())
    return clks

def load_exp_config(exp_path: str | Path):
    exp_path = Path(exp_path)
    try:
        _logger.info("Loading experiment ConfigBuilder from %s", exp_path / "config" / "config.json")
        builder = ConfigBuilder.from_json(exp_path/"config.json")
    except Exception as e:
        _logger.warning(
            "Loading configuration failed: %s. Building a minimal default.", e, exc_info=True
        )
        builder = ConfigBuilder.minimal_config()
        # BUGFIX: this should write *builder* to disk, not assign the classmethod result.
        builder.to_json(exp_path/"config.json")
        _logger.info("Wrote minimal config to %s", exp_path/"config.json")
    return builder

from pathlib import Path
import json, warnings

class cQED_Experiment:
    def __init__(self,
        experiment_path: str | Path,
        progMngr: QuaProgramManager | None = None,
        pulseOpMngr: PulseOperationManager | None = None,
        *,
        qop_ip: str | None = None,
        cluster_name: str | None = None,
        oct_cal_path: str | Path | None = None,
        load_devices: bool | list[str] | tuple[str, ...] | set[str] = True,
        **kwargs
    ):
        t0 = time.perf_counter()
        self.base_path = Path(experiment_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        _logger.info("Initializing cQED_Experiment at %s", self.base_path)

        cfg_dir = self.base_path / "config"
        hw_file = cfg_dir / "hardware.json"
        pl_file = cfg_dir / "pulses.json"
        device_file = cfg_dir / "devices.json"

        # ---- pull-through kwargs --------------------------------------
        # For QuaProgramManager __init__
        qm_ctor_keys = {"default_output_mode", "override_octave_json_mode"}
        qm_ctor_kwargs = {k: kwargs.pop(k) for k in list(kwargs) if k in qm_ctor_keys}

        # For runtime element outputs
        output_mode = kwargs.pop("output_mode", None)              # RFOutputMode | str | None
        per_element_modes: dict[str, Any] | None = kwargs.pop("per_element_modes", None)

        # complain if anything unexpected remains (helps catch typos)
        if kwargs:
            _logger.warning("Unused kwargs in cQED_Experiment.__init__: %s", sorted(kwargs.keys()))

        # helper: coerce string -> RFOutputMode
        def _as_mode(m):
            if m is None:
                return None
            if isinstance(m, RFOutputMode):
                return m
            s = str(m).lower().strip()
            lut = {
                "on": RFOutputMode.on,
                "off": RFOutputMode.off,
                "debug": RFOutputMode.debug,
                "trig_normal": RFOutputMode.trig_normal,
                "trig-inverse": RFOutputMode.trig_inverse,
                "trig_inverse": RFOutputMode.trig_inverse,
            }
            try:
                return lut[s]
            except KeyError:
                raise ValueError(f"Unknown output_mode '{m}'. "
                                 "Use one of: on/off/debug/trig_normal/trig_inverse or RFOutputMode.")

        # 1) QuaProgramManager ------------------------------------------
        if progMngr is None:
            _logger.info("No QuaProgramManager provided; constructing from %s", hw_file)
            if not hw_file.exists():
                raise FileNotFoundError(
                    "You did not supply a QuaProgramManager and no "
                    f"hardware.json found at {hw_file}"
                )
            if None in (qop_ip, cluster_name, oct_cal_path):
                raise ValueError(
                    "When progMngr is omitted you must pass qop_ip, "
                    "cluster_name and oct_cal_path."
                )
            progMngr = QuaProgramManager(
                qop_ip, cluster_name, oct_cal_path,
                hardware_path=hw_file,
                **qm_ctor_kwargs,                       # pass-through ctor knobs
            )
        else:
            _logger.info("Using provided QuaProgramManager")
            if progMngr.hardware is None:
                _logger.info("QuaProgramManager has no hardware loaded; attempting %s", hw_file)
                if hw_file.exists():
                    progMngr.load_hardware(hw_file)
                else:
                    raise FileNotFoundError(
                        "QuaProgramManager supplied without hardware and "
                        f"'{hw_file}' not found."
                    )
        self.quaProgMngr = progMngr

        # 2) PulseOperationManager --------------------------------------
        if pulseOpMngr is None:
            if pl_file.exists():
                _logger.info("Loading pulses from %s", pl_file)
                pulseOpMngr = PulseOperationManager.from_json(pl_file)
            else:
                _logger.warning("No pulses.json at %s; starting with empty pulse library.", pl_file)
                pulseOpMngr = PulseOperationManager()
        else:
            _logger.info("Using provided PulseOperationManager")
        self.pulseOpMngr = pulseOpMngr

        # 3) Merge pulses â†’ hardware and launch QM ----------------------
        _logger.info("Burning pulses to QM and initializing...")
        self.quaProgMngr.burn_pulse_to_qm(self.pulseOpMngr, include_volatile=True)
        self.quaProgMngr.init_qm()

        # 4) DeviceManager (must come before init_config so external LOs are available)
        self.device_manager = None

        if load_devices:
            _logger.info("Loading devices from %s", device_file)
            dm = DeviceManager(device_file)
            self.device_manager = dm

            try:
                if load_devices is True:
                    # Backwards-compatible: instantiate everything
                    _logger.info("load_devices=True â†’ instantiating all configured devices.")
                    dm.instantiate_all()

                elif isinstance(load_devices, (list, tuple, set)):
                    names = list(load_devices)
                    _logger.info(
                        "load_devices list/tuple/set â†’ instantiating selected device(s): %s",
                        ", ".join(names) or "(none)",
                    )
                    if names:
                        dm.instantiate(names)
                    else:
                        _logger.info("Empty load_devices list â†’ no devices instantiated.")

                else:
                    # Any other truthy value: load specs only, no connections
                    _logger.warning(
                        "Unrecognized load_devices=%r; loaded specs only (no devices instantiated).",
                        load_devices,
                    )

            except Exception as e:
                _logger.error(
                    "One or more devices failed during instantiation: %s",
                    e,
                    exc_info=True,
                )
        else:
            _logger.info("Devices not loaded (load_devices=%r).", load_devices)

        # Wire DeviceManager into QPM so set_element_lo() can route external LOs
        if self.device_manager is not None:
            self.quaProgMngr.set_device_manager(self.device_manager)

        # Optionally auto-configure SPA pump
        if self.device_manager is not None:
            sc = self.device_manager.get("signalcore_pump", connect=False)
            if sc is not None:
                _logger.info("Configuring SPA pump with 'signalcore_pump'.")
                try:
                    self.quaProgMngr.set_spa_pump(sc)
                except Exception as e:
                    _logger.error("Failed to set SPA pump: %s", e, exc_info=True)
            else:
                _logger.info(
                    "SPA pump NOT configured: 'signalcore_pump' is either not in specs or not instantiated."
                )

        # 5) Apply global output mode (if provided) and any per-element overrides
        try:
            if output_mode is not None:
                self.quaProgMngr.init_config(output_mode=_as_mode(output_mode))
            else:
                self.quaProgMngr.init_config()  # uses QPM default
        except TypeError:
            # backward-compat in case init_config signature differs
            if output_mode is not None:
                self.quaProgMngr.init_config(_as_mode(output_mode))
            else:
                self.quaProgMngr.init_config()

        if per_element_modes:
            for el, m in per_element_modes.items():
                self.quaProgMngr.set_octave_output(el, _as_mode(m))
                _logger.info("Per-element override: %s â†’ %s", el, _as_mode(m).name)

        # 6) Load or create experiment attributes -----------------------
        attrs_file = self.base_path / "cqed_params.json"
        if attrs_file.exists():
            _logger.info("Loading experiment attributes from %s", attrs_file)
            self.attributes = cQED_attributes.from_json(attrs_file)
        else:
            _logger.info("No attributes file found; starting with defaults")
            self.attributes = cQED_attributes()

        # Post-selection configuration (updated by readout_ge_discrimination)
        self.post_sel_config: PostSelectionConfig | None = None

        self.save_unique_identifier = None
        _logger.info("cQED_Experiment ready in %.2fs", time.perf_counter() - t0)

    def register_pulse(
        self,
        pulse: PulseOp,
        *,
        override: bool   = False,
        persist:  bool   = False,
        save:     bool   = False,
        burn:     bool   = True,
        include_volatile: bool = True,
    ):
        """
        Wrapper around
            self.pulseOpMngr.register_pulse_op(...)
            self.quaProgMngr.burn_pulse_to_qm(...)

        Parameters
        ----------
        pulse : PulseOp
            The pulse description to register.
        override : bool, default False
            Forwarded to `register_pulse_op`.
        persist : bool, default False
            If True the pulse is saved in the permanent store.
        burn : bool, default True
            If True, immediately call `burn_pulse_to_qm()` so the QM is ready
            to play the new pulse.  Set False if you want to batch-register
            many pulses and burn once at the end.
        include_volatile : bool, default True
            Forwarded to `burn_pulse_to_qm` (ignored when *burn* is False).
        """
        # 1) add / update in the PulseOperationManager
        self.pulseOpMngr.register_pulse_op(
            pulse,
            override=override,
            persist=persist,
        )

        # 2) push to QM right away (optional)
        if burn:
            self.burn_pulses(include_volatile)

        if save:
            self.save_pulses()
    

    def burn_pulses(self, include_volatile: bool = True):
            self.quaProgMngr.burn_pulse_to_qm(
                self.pulseOpMngr,
                include_volatile=include_volatile,
            )

    def save_pulses(self, path: str | Path | None = None) -> Path:
        """
        Serialize the *permanent* part of ``self.pulseOpMngr`` to JSON.

        Parameters
        ----------
        path : str | Path | None, optional
            Destination file.  If omitted, the default is
            ``<base_path>/config/pulses.json``.

        Returns
        -------
        pathlib.Path
            The location of the saved file (useful for logging).
        """
        cfg_dir = self.base_path / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)

        dst = Path(path) if path is not None else cfg_dir / "pulses.json"
        self.pulseOpMngr.save_json(dst)

        print(f"[cQED] permanent pulses saved â†’ {dst}")
        return dst
        
    def save_output(self, output: Output, target_folder: str, save_cqed_attributes=True):
        if save_cqed_attributes:
            output["cQED_params"] = self.attributes.to_dict()

        folder_path = self.base_path / target_folder
        
        folder_path.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        if self.save_unique_identifier:
            timestamp += f"_{self.save_unique_identifier}"
        filename_unique = f"{timestamp}.npz"
        save_path = folder_path / filename_unique
        
        output.save(save_path)

    def save_attributes(self):
        self.attributes.to_json(self.base_path / 'cqed_params.json')
    
    def save_measureMacro_state(self):
        measureMacro.save_json(self.base_path / 'measureConfig.json')

    def load_measureMacro_state(self, path: str | Path | None = None):
        if path is not None:
            measureMacro.load_json(Path(path))
        else:
            measureMacro.load_json(self.base_path / 'measureConfig.json')
    
    def set_readout_SPA_pump_power(self, power: float, sc_device: str = "signalcore_pump"):
        sc = self.device_manager.get(sc_device)
        sc.do_set_power(power)

    def set_readout_SPA_pump_frequency(self, frequency: float, sc_device: str = "signalcore_pump"):
        sc = self.device_manager.get(sc_device)
        sc.do_set_frequency(frequency)
        
    def readout_trace(self, drive_frequency, ro_therm_clks=10000, n_avg=1000) -> RunResult:
        attr = self.attributes
        ro_program = cQED_programs.readout_trace(ro_therm_clks, n_avg)
        u = qm_unit()
        def _voltify_and_stats(out, **_):
            adc1, adc2, adc1_single, adc2_single = out.extract(
                "adc1", "adc2", "adc1_single_run", "adc2_single_run"
            )
            out["adc1"], out["adc2"], out["adc1_single_run"], out["adc2_single_run"] = map(
                u.raw2volts, (adc1, adc2, adc1_single, adc2_single)
            )
            out["adc1_mean"], out["adc2_mean"] = np.average(out["adc1"]), np.average(out["adc2"])
            return out

        self.quaProgMngr.set_element_fq(attr.ro_el, drive_frequency)
        runres = self.quaProgMngr.run_program(
            ro_program,
            n_total=n_avg,
            processors=[_voltify_and_stats],
            process_in_sim=False,    # skip in SIM
        )
        return runres
    
    def resonator_spectroscopy(
        self,
        readout_op,
        rf_begin=8605e6,
        rf_end=8620e6,
        df=50e3,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attributes

        # Figure out IF grid for the requested span
        lo_freq = self.quaProgMngr.get_element_lo(attr.ro_el)
        if_freqs = create_if_frequencies(attr.ro_el, rf_begin, rf_end, df, lo_freq)

        # Lookup the PulseOp corresponding to this readout_op
        ro_info = self.pulseOpMngr.get_pulseOp_by_element_op(attr.ro_el, readout_op)
        if ro_info is None:
            raise ValueError(
                f"resonator_spectroscopy: no PulseOp found for element={attr.ro_el!r}, "
                f"op={readout_op!r}. Make sure it is registered."
            )

        mm = measureMacro
        # Use a clean default readout configuration for this experiment
        weight_len = int(ro_info.length) if ro_info.length is not None else None
        with mm.using_defaults(pulse_op=ro_info, active_op=readout_op, weight_len=weight_len):
            prog = cQED_programs.resonator_spectroscopy(
                attr.ro_el,
                if_freqs,
                attr.ro_therm_clks,
                n_avg,
            )

            runres = self.quaProgMngr.run_program(
                prog,
                n_total=n_avg,
                processors=[
                    pp.proc_default,
                    pp.proc_magnitude,
                    pp.proc_attach("frequencies", lo_freq + if_freqs),
                ],
                process_in_sim=False,
                axis=0,
                # optionally: demod_len=mm.get_demod_weight_len(),
            )

        return runres

    def resonator_power_spectroscopy(
        self,
        readout_op,
        rf_begin,
        rf_end,
        df,
        g_min=1e-3,
        g_max=0.5,
        N_a=50,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attributes

        lo_freq  = self.quaProgMngr.get_element_lo(attr.ro_el)
        if_freqs = create_if_frequencies(attr.ro_el, rf_begin, rf_end, df, lo_freq)
        gains    = np.geomspace(g_min, g_max, N_a)

        # Look up the PulseOp backing this readout operation
        ro_info = self.pulseOpMngr.get_pulseOp_by_element_op(attr.ro_el, readout_op)
        if ro_info is None:
            raise ValueError(
                f"resonator_power_spectroscopy: no PulseOp found for "
                f"element={attr.ro_el!r}, op={readout_op!r}. Make sure it is registered."
            )

        mm = measureMacro
        weight_len = int(ro_info.length) if ro_info.length is not None else None
        # Clean default readout settings for this scan
        with mm.using_defaults(pulse_op=ro_info, active_op=readout_op, weight_len=weight_len):
            prog = cQED_programs.resonator_power_spectroscopy(
                if_freqs,
                gains,
                attr.ro_therm_clks,
                n_avg,
            )

            runres = self.quaProgMngr.run_program(
                prog,
                n_total=n_avg,
                processors=[
                    pp.proc_default,
                    pp.proc_attach("frequencies", lo_freq + if_freqs),
                    pp.proc_attach("gains", gains),
                ],
                process_in_sim=False,
                # optionally: demod_len=mm.get_demod_weight_len(),
            )

        self.save_output(runres.output, "cavityPowerSpectroscopy")
        return runres

    def qubit_spectroscopy(self, pulse, rf_begin, rf_end, df, qb_gain, qb_len, n_avg: int = 1000) -> RunResult:
        attr     = self.attributes
        lo_qb    = self.quaProgMngr.get_element_lo(attr.qb_el)
        if_freqs = create_if_frequencies(attr.qb_el, rf_begin, rf_end, df, lo_freq=lo_qb)

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        prog = cQED_programs.qubit_spectroscopy(
            pulse, attr.qb_el, if_freqs, qb_gain, qb_len, attr.qb_therm_clks, n_avg
        )

        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=[pp.proc_default, pp.proc_attach("frequencies", lo_qb + if_freqs)],
            process_in_sim=False,
        )
        self.save_output(runres.output, "qubitSpectroscopy")
        return runres

    def qubit_spectroscopy_coarse(self, rf_begin, rf_end, df, qb_gain, qb_len, n_avg=1000) -> RunResult:
        attr    = self.attributes
        lo_list = _make_lo_segments(rf_begin, rf_end)

        seg_results: list[RunResult] = []
        all_freqs = []

        for LO in lo_list:
            self.quaProgMngr.set_element_lo(attr.qb_el, LO)
            if_freqs = _if_frequencies_for_segment(LO, rf_end, df)

            prog = cQED_programs.qubit_spectroscopy(
                attr.ro_el, attr.qb_el, if_freqs, qb_gain, qb_len, attr.qb_therm_clks, n_avg
            )

            rr = self.quaProgMngr.run_program(
                prog,
                n_total=n_avg,
                processors=[pp.proc_default, pp.proc_attach("frequencies", LO + if_freqs)],
                process_in_sim=False,
            )
            seg_results.append(rr)
            all_freqs.append(LO + if_freqs)

        final_output = _merge_segments([r.output for r in seg_results], all_freqs)
        merged_mode = seg_results[0].mode if seg_results else ExecMode.SIMULATE
        final_runres = RunResult(mode=merged_mode, output=final_output, sim_samples=None, metadata={"segments": len(seg_results)})

        self.save_output(final_output, "qubitSpectroscopy")
        return final_runres

    def qubit_spectroscopy_ef(self, pulse, rf_begin, rf_end, df, qb_gain, qb_len, n_avg) -> RunResult:
        attr     = self.attributes
        lo_qb    = self.quaProgMngr.get_element_lo(attr.qb_el)
        if_freqs = create_if_frequencies(attr.qb_el, rf_begin, rf_end, df, lo_freq=lo_qb)

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        prog = cQED_programs.qubit_spectroscopy_ef(
            pulse, attr.qb_el, if_freqs,
            self.quaProgMngr.get_element_if(attr.qb_el),
            qb_gain, qb_len, "x180", attr.qb_therm_clks, n_avg
        )
        
        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=[pp.proc_default, pp.proc_attach("frequencies", lo_qb + if_freqs)],
            process_in_sim=False,
        )
        self.save_output(runres.output, "qubit_efSpectroscopy")
        return runres


    def temporal_rabi(self, pulse, pulse_len_begin, pulse_len_end, dt: int = 4, pulse_gain=1.0, n_avg: int = 1000) -> RunResult:
        attr = self.attributes

        pulse_clks = create_clks_array(pulse_len_begin, pulse_len_end, dt, time_per_clk=4)
        prog = cQED_programs.temporal_rabi(
            attr.qb_el, pulse, pulse_clks, pulse_gain, attr.qb_therm_clks, n_avg
        )

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=[pp.proc_default, pp.proc_attach("pulse_durations", pulse_clks * 4)],
            process_in_sim=False,
        )
        self.save_output(runres.output, "temporalRabi")
        return runres

    def power_rabi(self, max_gain: int, dg: float = 1e-3, op="x180",
                length: int | None = None, truncate_clks=None, n_avg: int = 1000) -> RunResult:
        attr  = self.attributes
        gains = np.arange(-max_gain, max_gain + 1e-12, dg, dtype=float)

        pulseInfo = self.pulseOpMngr.get_pulseOp_by_element_op(attr.qb_el, op)
        if not length:
            length = pulseInfo.length

        I_wf, Q_wf = pulseInfo.I_wf, pulseInfo.Q_wf
        peak_amp = max(np.abs(I_wf).max(), np.abs(Q_wf).max())
        if peak_amp * max_gain > MAX_AMPLITUDE:
            raise ValueError(
                f"Max gain {max_gain} too high for pulse {op} with peak amplitude {peak_amp:.3f}. "
                f"Max gain for this pulse is {MAX_AMPLITUDE/peak_amp:.3f} so max amplitude does not exceed {MAX_AMPLITUDE}" 
            )

        pulse_clock_len = round(length / 4)
        prog = cQED_programs.power_rabi(
            attr.qb_el, pulse_clock_len, gains, attr.qb_therm_clks, op, truncate_clks, n_avg
        )

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=[pp.proc_default, pp.proc_attach("gains", gains)],
            process_in_sim=False,
        )
        self.save_output(runres.output, "powerRabi")
        return runres

    def sequential_qb_rotations(self, rotations: list[str] = ["x180"], apply_avg = False, n_shots=1000) -> RunResult:
        attr = self.attributes
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        qb_rot_prog = cQED_programs.sequential_qb_rotations(
            attr.qb_el, rotations, apply_avg, attr.qb_therm_clks, n_shots
        )

        runres = self.quaProgMngr.run_program(
            qb_rot_prog,
            n_total=n_shots,
            processors=[pp.proc_default, pp.proc_attach("rotations", rotations)],
            process_in_sim=False,
        )
        return runres


    def T1_relaxation(self, delay_end: int, dt: int, delay_begin=4, r180="x180", n_avg: int = 1000) -> RunResult:
        attr = self.attributes

        delay_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=4)

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        T1_prog = cQED_programs.T1_relaxation(
            attr.qb_el, r180, delay_clks, attr.qb_therm_clks, n_avg
        )

        runres = self.quaProgMngr.run_program(
            T1_prog,
            n_total=n_avg,
            processors=[pp.proc_default, pp.proc_attach("delays", delay_clks * 4)],
            process_in_sim=False,
        )
        self.save_output(runres.output, "T1Relaxation")
        return runres


    def T2_ramsey(self, qb_detune: int, delay_end: int, dt: int, delay_begin: int = 4, r90: str = "x90", n_avg: int = 1000) -> RunResult:
        attr = self.attributes

        if qb_detune > ConfigSettings.MAX_IF_BANDWIDTH:
            raise ValueError("qb detune can't exceed maximum IF bandwidth")

        # delays in *clks* (1 clk = 4 ns)
        delay_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=4)

        # set frequencies
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq + qb_detune)
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)

        T2_ramsey_prog = cQED_programs.T2_ramsey(
            attr.qb_el, r90, delay_clks, attr.qb_therm_clks, n_avg,
        )

        runres = self.quaProgMngr.run_program(
            T2_ramsey_prog,
            n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("delays", delay_clks * 4),   # ns
                pp.proc_attach("qb_detune", qb_detune),
            ],
            process_in_sim=False
        )

        self.save_output(runres.output, "T2Ramsey")
        return runres


    def T2_echo(self, delay_end: int, dt: int, delay_begin: int = 8, r180: str = "x180", r90: str = "x90", n_avg: int = 1000) -> RunResult:
        attr = self.attributes

        # half_wait_clks: units such that total delay 2Ï„ = half_wait_clks * 8 ns
        half_wait_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=8)

        T2_echo_prog = cQED_programs.T2_echo(
            attr.qb_el, r180, r90, half_wait_clks, attr.qb_therm_clks, n_avg,
        )

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        runres = self.quaProgMngr.run_program(
            T2_echo_prog,
            n_total=n_avg,
            processors=[
                pp.proc_default,
                # attach total delay 2Ï„ in ns for analysis:
                pp.proc_attach("delays", half_wait_clks * 8),
            ],
            process_in_sim=False,
            axis=0,
        )

        self.save_output(runres.output, "T2Echo")
        return runres


    def residual_photon_ramsey(
        self,
        t_R_begin,
        t_R_end,
        dt,
        test_ro_op,
        qb_detuning=0,
        t_relax=40,
        t_buffer=400,
        r90="x90",
        r180="x180",
        prep_e=False,
        test_ro_amp=1.0,
        measure_ro_op="readout_long",
        n_avg: int = 1000,
    ) -> RunResult:
        """
        Residual photon Ramsey experiment to measure cavity photon depletion dynamics.
        Based on: Reed et al., Phys. Rev. Applied 5, 011001 (2016)
        """
        attr = self.attributes

        # --- Frequencies (Hz) ---
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq + qb_detuning)

        # --- Times â†’ clks ---
        # If your helper uses ns_per_clk, switch the kw accordingly.
        t_R_clks     = create_clks_array(t_R_begin, t_R_end, dt, time_per_clk=4)
        t_relax_clk  = time_to_clks(t_relax)
        t_buffer_clk = time_to_clks(t_buffer)

        # --- Build program ---
        prog = cQED_programs.residual_photon_ramsey(
            attr.qb_el,
            test_ro_op,
            t_R_clks,
            t_relax_clk,
            t_buffer_clk,
            prep_e,
            test_ro_amp,
            r90,
            r180,
            attr.qb_therm_clks,
            n_avg,
        )

        def _proc(out: Output, **_):
            out["t_R"]        = np.array(t_R_clks) * 4   # ns, if 1 clk = 4 ns
            out["t_relax"]    = t_relax_clk * 4
            out["t_buffer"]   = t_buffer_clk * 4
            out["qb_detuning"]= qb_detuning
            return out


        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=[pp.proc_default, _proc],
            process_in_sim=False,
            normalize_params=measureMacro._ro_disc_params.get("norm_params"),
            targets=[("I","Q")],
        )

        self.save_output(runres.output, "residualPhotonRamsey")
        return runres

    def time_rabi_chevron(self, if_span, df, max_pulse_duration, dt,
                        pulse="x180", pulse_gain=1.0, n_avg: int = 1000) -> RunResult:
        
        attr = self.attributes
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        qb_if = self.quaProgMngr.get_element_if(attr.qb_el)

        if_dfs = np.arange(-if_span/2, if_span/2 + 0.1, df, dtype=int)
        duration_clks = np.arange(4, max_pulse_duration / 4 + 1, dt, dtype=int)

        rabi_chevron_duration = cQED_programs.time_rabi_chevron(
            attr.ro_el, attr.qb_el, pulse, pulse_gain, qb_if, if_dfs, duration_clks, attr.qb_therm_clks, n_avg
        )

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        runres = self.quaProgMngr.run_program(
            rabi_chevron_duration,
            n_total=n_avg,
            processors=[pp.proc_default,
                        pp.proc_attach("durations", duration_clks * 4),
                        pp.proc_attach("detunings", if_dfs)],
            process_in_sim=False,
        )
        self.save_output(runres.output, "rabiChevronTime")
        return runres


    def power_rabi_chevron(self, if_span, df, max_gain, dg,
                        pulse="x180", pulse_duration=100, n_avg: int = 1000) -> RunResult:
        attr = self.attributes

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)
        qb_if = self.quaProgMngr.get_element_if(attr.qb_el)
        if_dfs = np.arange(-if_span/2, if_span/2 + 0.1, df, dtype=int)
        gains  = np.arange(-max_gain, max_gain + 1e-12, dg, dtype=float)

        rabi_chevron_amplitude = cQED_programs.power_rabi_chevron(
            attr.ro_el, attr.qb_el, pulse, pulse_duration, qb_if, if_dfs, gains, attr.qb_therm_clks, n_avg
        )

        runres = self.quaProgMngr.run_program(
            rabi_chevron_amplitude,
            n_total=n_avg,
            processors=[pp.proc_default,
                        pp.proc_attach("gains", gains),
                        pp.proc_attach("detunings", if_dfs)],
            process_in_sim=False
        )
        self.save_output(runres.output, "rabiChevronAmplitude")
        return runres

    def ramsey_chevron(self, if_span, df, max_delay_duration, dt, r90="x90", n_avg: int = 1000) -> RunResult:
        attr = self.attributes

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)
        qb_if = self.quaProgMngr.get_element_if(attr.qb_el)

        if_dfs    = np.arange(-if_span/2, if_span/2 + 0.1, df, dtype=int)
        delay_clks = np.arange(0, max_delay_duration / 4 + 1, dt, dtype=int)


        ramsey_chevron_duration = cQED_programs.ramsey_chevron(
            attr.ro_el, attr.qb_el, r90, qb_if, if_dfs, delay_clks, attr.qb_therm_clks, n_avg
        )

        runres = self.quaProgMngr.run_program(
            ramsey_chevron_duration,
            n_total=n_avg,
            processors=[pp.proc_default,
                        pp.proc_attach("delays", delay_clks * 4),
                        pp.proc_attach("detunings", if_dfs)],
            process_in_sim=False
        )
        self.save_output(runres.output, "ramseyChevronAmplitude")
        return runres

    def all_XY(self, gate_indices=None, prefix="", qb_detuning=0, n_avg=1000) -> RunResult:
        """
        Run All-XY experiment to characterize gate errors.
        
        Parameters
        ----------
        n_avg : int
            Number of averages
        gate_indices : list of int or None
            Optional list of gate pair indices to run (0-20). 
            If None, runs all 21 gate pairs.
            Example: [0, 1, 2] runs only the first three pairs.
        
        Returns
        -------
        RunResult
        """
        attr = self.attributes
        all_ops = (
            ["r0", "r0"], ["x180", "x180"], ["y180", "y180"], ["x180", "y180"], ["y180", "x180"],
            ["x90", "r0"], ["y90", "r0"],
            ["x90", "y90"], ["y90", "x90"], ["x90", "y180"], ["y90", "x180"], ["x180", "y90"], ["y180", "x90"],
            ["x90", "x180"], ["x180", "x90"], ["y90", "y180"], ["y180", "y90"],
            ["x180", "r0"], ["y180", "r0"], ["x90", "x90"], ["y90", "y90"],
        )
        
        # Select specific gate pairs if requested
        if gate_indices is not None:
            ops = [all_ops[i] for i in gate_indices]
        else:
            ops = all_ops

        if prefix:
            ops = [[f"{prefix}{g1}", f"{prefix}{g2}"] for (g1, g2) in ops]
        all_xy_program = cQED_programs.all_xy(
            attr.qb_el, ops, attr.qb_therm_clks, n_avg
        )

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq + qb_detuning)

        runres = self.quaProgMngr.run_program(
            all_xy_program,
            n_total=n_avg,
            processors=[pp.ro_state_correct_proc, pp.proc_attach("ops", ops)],
            process_in_sim=False,
            targets= [("Pe", "sz")],
            confusion=measureMacro._ro_quality_params.get("confusion_matrix"),
            to_sigmaz=True
        )
        self.save_output(runres.output, "allXY")
        return runres
        
    def randomized_benchmarking(
        self,
        m_list: list[int],
        num_sequence: int,
        n_avg: int = 1000,
        *,
        interleave_op: str | None = None,     # None => reference RB ; string => interleaved RB
        primitives_by_id: dict[int, str] | None = None,
        primitive_prefix: str = "",
        max_sequences_per_compile: int = 10,
        guard_clks: int = 18,
    ) -> "RunResult":
        import numpy as np

        attr = self.attributes

        # ----------------------------
        # Canonical 1Q Clifford set
        # ----------------------------
        CLIFFORD_1Q_SEQS = [
            ["r0"],
            ["x180"],
            ["x90"],
            ["xn90"],
            ["y180"],
            ["y90"],
            ["yn90"],
            ["x180", "y180"],
            ["x180", "y90"],
            ["x180", "yn90"],
            ["x90", "y180"],
            ["x90", "y90"],
            ["x90", "yn90"],
            ["xn90", "y180"],
            ["xn90", "y90"],
            ["xn90", "yn90"],
            ["y90", "x90"],
            ["y90", "xn90"],
            ["yn90", "x90"],
            ["yn90", "xn90"],
            ["x90", "y90", "x90"],
            ["x90", "y90", "xn90"],
            ["x90", "yn90", "x90"],
            ["x90", "yn90", "xn90"],
        ]
        n_cliff = len(CLIFFORD_1Q_SEQS)
        CANON = ["r0", "x180", "x90", "xn90", "y180", "y90", "yn90"]

        # ----------------------------
        # Ideal unitary model (for inverse computation)
        # ----------------------------
        def _rot(pauli: str, theta: float) -> np.ndarray:
            I2 = np.eye(2, dtype=complex)
            X = np.array([[0, 1], [1, 0]], dtype=complex)
            Y = np.array([[0, -1j], [1j, 0]], dtype=complex)
            Z = np.array([[1, 0], [0, -1]], dtype=complex)
            P = {"x": X, "y": Y, "z": Z}[pauli.lower()]
            return np.cos(theta / 2) * I2 - 1j * np.sin(theta / 2) * P

        PRIM_U = {
            "r0":   np.eye(2, dtype=complex),
            "x90":  _rot("x", +np.pi / 2),
            "xn90": _rot("x", -np.pi / 2),
            "x180": _rot("x", +np.pi),
            "y90":  _rot("y", +np.pi / 2),
            "yn90": _rot("y", -np.pi / 2),
            "y180": _rot("y", +np.pi),
        }

        def clifford_U_from_seq(seq_ops: list[str]) -> np.ndarray:
            U = np.eye(2, dtype=complex)
            for op in seq_ops:
                U = PRIM_U[op] @ U
            return U

        # âœ… Full list of Clifford unitaries (24)
        CLIFF_U = [clifford_U_from_seq(seq) for seq in CLIFFORD_1Q_SEQS]

        # âœ… Unitary-to-Clifford lookup
        def find_clifford_index_for_unitary(U_target: np.ndarray, tol: float = 1e-6) -> int:
            overlaps = [abs(np.trace(Uk.conj().T @ U_target)) / 2.0 for Uk in CLIFF_U]
            k = int(np.argmax(overlaps))
            if overlaps[k] < (1 - tol):
                raise RuntimeError(f"Could not match inverse to a Clifford. best overlap={overlaps[k]:.9f}")
            return k

        # ----------------------------
        # primitives_by_id defaults + canon2id
        # ----------------------------
        if primitives_by_id is None:
            primitives_by_id = {
                0: f"{primitive_prefix}r0",
                1: f"{primitive_prefix}x180",
                2: f"{primitive_prefix}x90",
                3: f"{primitive_prefix}xn90",
                4: f"{primitive_prefix}y180",
                5: f"{primitive_prefix}y90",
                6: f"{primitive_prefix}yn90",
            }
        if not primitives_by_id:
            raise ValueError("primitives_by_id cannot be empty.")

        # âœ… sentinel = max id + 1
        interleave_sentinel = int(max(primitives_by_id.keys())) + 1

        canon2id: dict[str, int] = {}
        for pid, opname in primitives_by_id.items():
            opname = str(opname)
            if opname in CANON:
                canon2id[opname] = int(pid)
            else:
                for c in CANON:
                    if opname.endswith(c):
                        canon2id[c] = int(pid)
                        break

        missing = [c for c in CANON if c not in canon2id]
        if missing:
            raise ValueError(f"primitives_by_id missing canonical mappings: {missing}")

        # ----------------------------
        # PulseOpMngr timing helper: op string -> clks
        # ----------------------------
        def _op_to_clks(op: str) -> int:
            opInfo = self.pulseOpMngr.get_pulseOp_by_element_op(attr.qb_el, op)
            if opInfo is None:
                raise ValueError(f"Could not find op '{op}' on element '{attr.qb_el}' in PulseOpMngr.")
            L = int(opInfo.length)
            if L % 4 != 0:
                raise ValueError(f"opInfo.length for '{op}' is {L}, not divisible by 4.")
            return L // 4

        # primitive_clks: assume all primitives same duration -> use x90 if possible else first
        prim_op_for_timing = primitives_by_id.get(canon2id.get("x90", -1), None)
        if prim_op_for_timing is None:
            prim_op_for_timing = primitives_by_id[sorted(primitives_by_id.keys())[0]]
        primitive_clks = _op_to_clks(str(prim_op_for_timing))

        # ----------------------------
        # Optional interleave settings
        # ----------------------------
        do_interleave = interleave_op is not None
        interleave_clks = None
        g_canon = None
        g_idx = None

        if do_interleave:
            op_str = str(interleave_op).strip()

            # infer canonical Clifford primitive name (by suffix)
            for c in CANON:
                if op_str == c or op_str.endswith(c):
                    g_canon = c
                    break
            if g_canon is None:
                raise ValueError(
                    f"interleave_op='{op_str}' is not recognized as a single-primitive Clifford.\n"
                    f"It must be (or end with) one of: {CANON}"
                )

            g_idx = CLIFFORD_1Q_SEQS.index([g_canon])
            interleave_clks = _op_to_clks(op_str)

        # ----------------------------
        # Allocate outputs
        # ----------------------------
        m_list = [int(m) for m in m_list]
        n_m = len(m_list)

        I_mat = np.full((n_m, num_sequence), np.nan, dtype=float)
        Q_mat = np.full((n_m, num_sequence), np.nan, dtype=float)
        Pe_mat = np.full((n_m, num_sequence), np.nan, dtype=float)
        Pe_corr_mat = np.full((n_m, num_sequence), np.nan, dtype=float)

        meta_2d: list[list[dict]] = [[{} for _ in range(num_sequence)] for _ in range(n_m)]

        # frequencies once
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        # batching
        B = int(max_sequences_per_compile)
        if B <= 0:
            raise ValueError("max_sequences_per_compile must be >= 1")

        programs: list = []
        queued_meta: list[dict] = []

        # ----------------------------
        # Build sequences + programs
        # ----------------------------
        for m_idx, m in enumerate(m_list):
            seqs = random_sequences(num_sequence, m, low=0, high=n_cliff, replace=True)

            ids_full_list: list[list[int]] = []

            for seq_idx, seq in enumerate(seqs):
                seq = list(map(int, seq))

                if not do_interleave:
                    # Reference RB: inverse of C_m...C_1
                    U = np.eye(2, dtype=complex)
                    for c_idx in seq:
                        U = CLIFF_U[int(c_idx)] @ U
                    inv_idx = find_clifford_index_for_unitary(U.conj().T)

                    ops_full: list[str] = []
                    for k in (seq + [int(inv_idx)]):
                        ops_full.extend(CLIFFORD_1Q_SEQS[int(k)])
                    ids_full = [canon2id[op] for op in ops_full]

                else:
                    assert g_idx is not None and g_canon is not None and interleave_clks is not None

                    # Recovery for interleaved product (C1 G C2 G ... Cm G)
                    U = np.eye(2, dtype=complex)
                    for c_idx in seq:
                        U = CLIFF_U[int(c_idx)] @ U
                        U = CLIFF_U[int(g_idx)] @ U
                    inv_idx = find_clifford_index_for_unitary(U.conj().T)

                    ids_full = []
                    ops_full = []

                    for c_idx in seq:
                        ops = CLIFFORD_1Q_SEQS[int(c_idx)]
                        ops_full.extend(ops)
                        ids_full.extend([canon2id[o] for o in ops])

                        # Insert sentinel meaning "play interleave_op"
                        ids_full.append(int(interleave_sentinel))
                        ops_full.append(f"<INTERLEAVE:{interleave_op}>")

                    # Append recovery Clifford (expanded normally; no sentinel)
                    ops_inv = CLIFFORD_1Q_SEQS[int(inv_idx)]
                    ops_full.extend(ops_inv)
                    ids_full.extend([canon2id[o] for o in ops_inv])

                ids_full_list.append(ids_full)

                d = dict(
                    m_idx=int(m_idx),
                    m=int(m),
                    seq_idx=int(seq_idx),
                    clifford_indices=seq,
                    inv_idx=int(inv_idx),
                    sequence_ids=ids_full,
                    primitive_clks=int(primitive_clks),
                    guard_clks=int(guard_clks),
                    interleave_sentinel=int(interleave_sentinel),
                )
                if do_interleave:
                    d.update(
                        interleave_op=str(interleave_op),
                        interleave_canon=str(g_canon),
                        interleave_clifford_idx=int(g_idx),
                        interleave_clks=int(interleave_clks),
                    )
                meta_2d[m_idx][seq_idx] = d

            # Build programs per batch
            for start in range(0, num_sequence, B):
                end = min(start + B, num_sequence)
                batch_sequences_ids = ids_full_list[start:end]

                prog = cQED_programs.randomized_benchmarking(
                    qb_el=attr.qb_el,
                    sequences_ids=batch_sequences_ids,
                    qb_therm_clks=attr.qb_therm_clks,
                    n_avg=n_avg,
                    primitives_by_id=primitives_by_id,
                    primitive_clks=int(primitive_clks),
                    guard_clks=int(guard_clks),
                    interleave_op=(str(interleave_op) if do_interleave else None),
                    interleave_clks=(int(interleave_clks) if do_interleave else None),
                    interleave_sentinel=int(interleave_sentinel),
                )

                programs.append(prog)
                queued_meta.append(dict(m_idx=int(m_idx), start=int(start), end=int(end)))

        # ----------------------------
        # Submit + run
        # ----------------------------
        confusion = measureMacro._ro_quality_params.get("confusion_matrix")
        desc_prefix = "iRB" if do_interleave else "RB"

        pendings = self.quaProgMngr.queue_submit_many_with_progress(
            programs,
            to_start=False,
            quiet=True,
            show_submit_progress=True,
            desc=f"{desc_prefix}: submitting to queue...",
        )

        results = self.quaProgMngr.queue_run_many(
            pendings,
            n_totals=n_avg,
            processors=[pp.ro_state_correct_proc],
            process_in_sim=False,
            targets=[("Pe", "Pe_corr")],
            confusion=confusion,
            to_sigmaz=False,
            progress_handle="iteration",
            show_total_progress=True,
            desc=f"{desc_prefix}: running (total)...",
            print_report=False,
            auto_job_halt=True,
            quiet=True,
        )

        runres_template = results[0] if results else RunResult(
            mode=ExecMode.HARDWARE,
            output=Output(),
            sim_samples=None,
            metadata={"n_total": int(n_avg)},
        )

        for meta, runres in zip(queued_meta, results):
            I_batch = np.asarray(runres.output.extract("I"), dtype=float)
            Q_batch = np.asarray(runres.output.extract("Q"), dtype=float)
            Pe_batch = np.asarray(runres.output.extract("Pe"), dtype=float)
            Pe_corr_batch = np.asarray(runres.output.extract("Pe_corr"), dtype=float)

            m_idx = meta["m_idx"]
            start = meta["start"]
            end = meta["end"]

            I_mat[m_idx, start:end] = I_batch
            Q_mat[m_idx, start:end] = Q_batch
            Pe_mat[m_idx, start:end] = Pe_batch
            Pe_corr_mat[m_idx, start:end] = Pe_corr_batch

        out_meta = dict(
            m_list=list(m_list),
            num_sequence=int(num_sequence),
            n_avg=int(n_avg),
            primitives_by_id=dict(primitives_by_id),
            sequences=meta_2d,
            max_sequences_per_compile=int(max_sequences_per_compile),
            queued_batches=int(len(programs)),
            primitive_clks=int(primitive_clks),
            guard_clks=int(guard_clks),
            interleave_sentinel=int(interleave_sentinel),
        )
        if do_interleave:
            out_meta.update(
                interleave_op=str(interleave_op),
                interleave_canon=str(g_canon),
                interleave_clifford_idx=int(g_idx),
                interleave_clks=int(interleave_clks),
            )

        runres_template.output["I"] = I_mat
        runres_template.output["Q"] = Q_mat
        runres_template.output["Pe"] = Pe_mat
        runres_template.output["Pe_corr"] = Pe_corr_mat
        try:
            runres_template.output["meta_data"] = out_meta
        except Exception:
            pass

        save_tag = "interleavedRandomizedBenchmarking" if do_interleave else "randomizedBenchmarking"
        self.save_output(runres_template.output, save_tag)
        return runres_template


    def qubit_pulse_train_legacy(self, N_values, K=2, rotation_pulse="x180", n_avg=1000, r90_pulse="x90") -> RunResult:
        """
        Qubit pulse train experiment to calibrate pi_val-pulse amplitude.
        
        For each N in N_values:
            |gâŸ© --(pi_val/2)--> superposition --[KN Ã— rotation pulse]--> final state --> measure P_e(N)
        
        If the rotation pulse amplitude is correct, P_e(N) should ideally be independent of N.
        Any deviation indicates amplitude miscalibration.
        
        Parameters
        ----------
        N_values : array-like
            Array of N values; for each N, applies KN rotation pulses.
            Example: np.arange(0, 20, 1) for N = 0, 1, 2, ..., 19
        n_avg : int
            Number of averages per N value
        r90_pulse : str
            Name of the pi_val/2 pulse (default: "x90")
        rotation_pulse : str
            Name of the rotation pulse (default: "x180")
        
        Returns
        -------
        RunResult
            Contains 'I', 'Q', 'N_values' in output
        """
        attr = self.attributes
        
        # Build the QUA program
        pulse_train_prog = cQED_programs.qubit_pulse_train_legacy(
            qb_el=attr.qb_el,
            r90=r90_pulse,
            rotation_pulse=rotation_pulse,
            N_values=N_values,
            K=K, 
            qb_therm_clks=attr.qb_therm_clks,
            n_avg=n_avg
        )
        
        # Set frequencies
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)
        
        
        # Run the program
        runres = self.quaProgMngr.run_program(
            pulse_train_prog,
            n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("N_values", N_values),
                pp.proc_attach("ro_len", measureMacro.active_length)
            ],
            process_in_sim=False
        )
        
        self.save_output(runres.output, "pulseTrain")
        return runres

    def qubit_pulse_train(
        self,
        N_values,
        reference_pulse="x90",
        rotation_pulse="x180",
        run_reference=False,
        n_avg=1000
    ) -> RunResult:
        """
        Wrapper for qubit_pulse_train experiment.
        
        Applies a reference pulse followed by N rotation pulses to calibrate
        pulse amplitudes. Optionally runs a reference measurement with rotation
        pulses at zero amplitude for background subtraction.
        
        Parameters
        ----------
        N_values : array-like
            Array of N values (number of rotation pulses to apply).
            Example: np.arange(0, 50, 2) for N = 0, 2, 4, ..., 48
        reference_pulse : str, optional
            Name of reference pulse (e.g., pi_val/2 pulse). Default: "x90"
        rotation_pulse : str, optional
            Name of rotation pulse to calibrate. Default: "x180"
        run_reference : bool, optional
            If True, runs reference measurements with rotation pulses at zero amplitude
            for each N value before the actual measurement. This doubles the output size.
            Default: False
        n_avg : int, optional
            Number of averages. Default: 1000
            
        Returns
        -------
        RunResult
            Contains 'I', 'Q', 'state', 'iteration' in output.
            If run_reference=True, output arrays have shape (2, len(N_values))
            where index 0 is reference (amp=0) and index 1 is actual measurement.
            If run_reference=False, output arrays have shape (len(N_values),).
            
        Notes
        -----
        The sequence for each N value:
            If run_reference=True:
                1. play(reference_pulse)
                2. play(rotation_pulse * amp(0)) Ã— N times (zero amplitude)
                3. measure (reference)
                4. thermalize
            
            5. play(reference_pulse)
            6. play(rotation_pulse) Ã— N times (actual amplitude)
            7. measure
            8. thermalize
        
        Use this to calibrate rotation pulse amplitude by finding the amplitude
        that minimizes variation in P_e across different N values.
        """
        attr = self.attributes
        
        # Build the QUA program
        pulse_train_prog = cQED_programs.qubit_pulse_train(
            qb_el=attr.qb_el,
            reference_pulse=reference_pulse,
            rotation_pulse=rotation_pulse,
            N_values=N_values,
            qb_therm_clks=attr.qb_therm_clks,
            n_avg=n_avg,
            run_reference=run_reference
        )
        
        # Set frequencies
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)
        
        def _proc(out: Output, **_):
            targets = [("I", "Q")]
            if run_reference:
                targets.append(("I_ref", "Q_ref"))
            out = pp.proc_default(out, targets=targets)
            out["N_values"] = np.array(N_values, dtype=int)
            out["reference_pulse"] = str(reference_pulse)
            out["rotation_pulse"] = str(rotation_pulse)
            out["run_reference"] = bool(run_reference)
            return out
        
        # Run the program
        targets = [("state", "Pe")]
        if run_reference:
            targets.append(("state_ref", "Pe_ref"))
            
        runres = self.quaProgMngr.run_program(
            pulse_train_prog,
            n_total=n_avg,
            processors=[
                _proc,
                pp.ro_state_correct_proc
            ],
            process_in_sim=False,
            targets=targets,
            confusion=measureMacro._ro_quality_params.get("confusion_matrix"),
        )
        
        self.save_output(runres.output, "pulseTrain")
        return runres

    def qubit_state_tomography(
        self,
        state_prep,
        n_avg,
        *,
        x90_pulse="x90",
        yn90_pulse="yn90",
        therm_clks=None,
    ):
        """
        High-level driver to run qubit state tomography on hardware.

        It:
        1. Sets the readout and qubit element frequencies to the calibrated values.
        2. Builds a QUA program that:
            - For each shot (n_avg total):
                - For each state_prep callable (if multiple):
                    - For each axis (x, y, z):
                        - calls `state_prep()`
                        - applies the correct projection pulse(s)
                        - measures with_state=True
                        - saves the boolean (and optionally I/Q)
        3. Runs that program on the QM via quaProgMngr.
        4. Returns the RunResult.

        Parameters
        ----------
        state_prep : QUA callable **or** list/tuple of callables
            Your preparation macro (called once per axis per shot).
            When a single callable is passed the behaviour is identical to
            the original single-prep version.
            When a sequence of P callables is passed, the program runs the
            full x/y/z tomography for every prep inside each averaging
            iteration, producing output arrays with an extra leading
            dimension of size P.
        n_avg : int
            Number of averages (shots).
        x90_pulse : str, optional
            Pulse name that implements +pi_val/2 about X (used to map Ïƒ_y â†’ Z).
            Default "x90".
        yn90_pulse : str, optional
            Pulse name that implements -pi_val/2 about Y (used to map Ïƒ_x â†’ Z).
            Default "yn90".
        therm_clks : int or None, optional
            Wait time (clock cycles) after each axis measurement.
            If None, uses ``attr.qb_therm_clks``.

        Returns
        -------
        runres : RunResult
            Contains ``"sx"``, ``"sy"``, ``"sz"`` (corrected âŸ¨ÏƒâŸ© values).
            - Single prep  â†’ scalars.
            - P preps      â†’ arrays of shape ``(P,)``.
        """

        attr = self.attributes

        # Normalise to list so we can query length
        if callable(state_prep):
            preps = [state_prep]
        else:
            preps = list(state_prep)
        n_preps = len(preps)

        # make sure the QM config knows the correct carrier / IF for this run
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el,        attr.qb_fq)

        # build the actual QUA program with the generalized tomography macro
        if therm_clks is None:
            therm_clks = attr.qb_therm_clks
        state_tomography_prog = cQED_programs.qubit_state_tomography(
            state_prep=state_prep,
            therm_clks=therm_clks,
            n_avg=n_avg,
            qb_el=attr.qb_el,
            x90=x90_pulse,
            yn90=yn90_pulse
        )

        # run on hardware
        runres = self.quaProgMngr.run_program(
            state_tomography_prog,
            n_total=n_avg,
            processors=[pp.ro_state_correct_proc],
            process_in_sim=False,
            targets=[("state_x", "sx"), ("state_y", "sy"), ("state_z", "sz")],
            confusion=measureMacro._ro_quality_params.get("confusion_matrix"),
            to_sigmaz=True
        )

        # For multi-prep convenience: attach prep count metadata
        if n_preps > 1:
            runres.output["n_preps"] = n_preps

        return runres


    def readout_ge_raw_trace(self, ro_freq, r180, ro_depl_clks, n_avg) -> RunResult:
        attr = self.attributes
        
        ro_ge_trace = cQED_programs.readout_ge_raw_trace(
            attr.qb_el, r180, attr.qb_therm_clks, ro_depl_clks, n_avg
        )
        self.quaProgMngr.set_element_fq(attr.ro_el, ro_freq)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        # If you want volts/statistics here, add a processor; otherwise return raw.
        runres = self.quaProgMngr.run_program(
            ro_ge_trace,
            n_total=2 * n_avg,          # matches your original call
            processors=[],               # or [some_pp_processor]
            process_in_sim=False,
        )
        self.save_output(runres.output, "readout_ge_raw_trace")
        return runres

    def qubit_readout_leakage_benchmarking(
        self, control_bits, r180="x180", num_sequences=10, n_avg=1000
    ) -> RunResult:
        attr = self.attributes
        rlb_prog = cQED_programs.readout_leakage_benchmarking(
            attr.ro_el, attr.qb_el, r180, control_bits, attr.qb_therm_clks, num_sequences, n_avg
        )

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        runres = self.quaProgMngr.run_program(
            rlb_prog,
            n_total=num_sequences,
            processors=[pp.proc_default, pp.proc_attach("control_bits", control_bits)],
            process_in_sim=False,
        )
        self.save_output(runres.output, "qubitReadoutLeakage")
        return runres

    def qubit_reset_benchmark(self, bit_size: int = 1_000, num_shots: int = 20_000,
                            r180: str = "x180", random_seed: int | None = None) -> RunResult:
        attr = self.attributes
        if random_seed is not None:
            np.random.seed(random_seed)
        initial_bits = np.random.randint(0, 2, bit_size).astype(np.bool_)

        prog = cQED_programs.qubit_reset_benchmark(
            qb_el=attr.qb_el, random_bits=initial_bits, r180=r180,
            qb_therm_clks=attr.qb_therm_clks, num_shots=num_shots
        )

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        def _reset_metrics(out, **_):
            tgt = np.array(out["target"], dtype=bool)
            m1  = np.array(out["state_M1"], dtype=bool)
            m2  = np.array(out["state_M2"], dtype=bool)

            Pe_star = m2.mean()
            need_reset = m1
            eps_cond = (m2 & need_reset).sum() / need_reset.sum() if need_reset.any() else np.nan
            eps_unc  = Pe_star

            out.update({"Pe_star": float(Pe_star),
                        "eps_cond": float(eps_cond),
                        "eps_unc": float(eps_unc)})
            return out

        runres = self.quaProgMngr.run_program(
            prog, num_shots,
            processors=[pp.bare_proc, _reset_metrics, pp.proc_attach("r180", r180)],
            process_in_sim=False
        )
        self.save_output(runres.output, "qubitResetBenchmark")
        return runres

    def readout_ge_discrimination(
        self,
        measure_op: str,
        drive_frequency: int,
        r180: str = "x180",
        gain = 1,
        update_measureMacro: bool = False,
        burn_rot_weights: bool = True,
        persist: bool = False,
        n_samples: int = 10_000,
        base_weight_keys: tuple[str, str, str] | None = None,  # (cos, sin, m_sin) labels
        auto_update_postsel: bool = True,
        blob_k_g: float = 2.0,
        blob_k_e: float | None = None,
        **kwargs,
    ) -> RunResult:
        """
        Fit a G/E discriminator using IQ blobs, then build *rotated* integration weights.

        Extra kwargs:
        - k_g, k_e (optional): hysteresis factors for ground/excited thresholds in
        the set_measureMacro branch (defaults 2.0, 2.0).
        - auto_update_postsel (bool): If True, automatically update self.post_sel_config
        with the discrimination results for use in subsequent butterfly measurements.
        - blob_k_g, blob_k_e (float): Sigma multipliers for BLOBS post-selection region.
        """

        # -------- pull hysteresis params from kwargs (do NOT pass them to discriminator) ----
        raw_k_g = kwargs.pop("k_g", None)
        raw_k_e = kwargs.pop("k_e", None)
        if raw_k_g is None:
            k_g = 2.0
        else:
            k_g = float(raw_k_g)
        if raw_k_e is None:
            k_e = k_g
        else:
            k_e = float(raw_k_e)
        
        # Set blob_k_e default if not provided
        if blob_k_e is None:
            blob_k_e = blob_k_g

        # -------- helpers ----------------------------------------------------------
        def _name(prefix: str | None, stem: str) -> str:
            return stem if not prefix else f"{prefix}{stem}"

        def _choose_default_keys(mapping: dict, prefix: str) -> Tuple[str, str, str]:
            """
            Choose default base-weight keys for a pulse.

            Canonical labels are:
                prefix+'cos', prefix+'sin', prefix+'m_sin'
            falling back to unprefixed:
                'cos', 'sin', 'm_sin'
            """
            # Canonical, prefixed
            cand = (_name(prefix, "cos"), _name(prefix, "sin"), _name(prefix, "m_sin"))
            if all(k in mapping for k in cand):
                return cand

            # Canonical, unprefixed
            cand_un = ("cos", "sin", "m_sin")
            if all(k in mapping for k in cand_un):
                return cand_un

            # Legacy, prefixed (back-compat)
            legacy = (_name(prefix, "rot_cos"), _name(prefix, "rot_sin"), _name(prefix, "rot_m_sin"))
            if all(k in mapping for k in legacy):
                warnings.warn(
                    "Using legacy 'rot_*' weight labels. Please rename to 'cos', 'sin', 'm_sin' "
                    "(optionally with your prefix).",
                    DeprecationWarning,
                    stacklevel=2,
                )
                return legacy

            # Legacy, unprefixed (back-compat)
            legacy_un = ("rot_cos", "rot_sin", "rot_m_sin")
            if all(k in mapping for k in legacy_un):
                warnings.warn(
                    "Using legacy 'rot_*' weight labels. Please rename to 'cos', 'sin', 'm_sin'.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                return legacy_un

            raise KeyError(
                "Default weight labels not found on pulse. Provide base_weight_keys explicitly, "
                "e.g., base_weight_keys=('opt_cos','opt_sin','opt_m_sin'). "
                f"Available labels: {sorted(mapping.keys())}"
            )

        def _total_len(iw_name: str) -> int:
            cos, sin = self.pulseOpMngr.get_integration_weights(iw_name)
            return max(sum(L for _, L in cos), sum(L for _, L in sin))

        # -------- resolve pulse + mapping -----------------------------------------
        attr = self.attributes
        pulseInfo = self.pulseOpMngr.get_pulseOp_by_element_op(attr.ro_el, measure_op)
        weight_mapping = pulseInfo.int_weights_mapping or {}
        if not isinstance(weight_mapping, dict):
            weight_mapping = {}

        is_readout = (pulseInfo.op == "readout")
        op_prefix  = "" if is_readout else f"{pulseInfo.op}_"

        if base_weight_keys is None:
            cos_key, sin_key, m_sin_key = _choose_default_keys(weight_mapping, op_prefix)
        else:
            cos_key, sin_key, m_sin_key = base_weight_keys

        try:
            base_cos_name    = weight_mapping[cos_key]
            base_sin_name    = weight_mapping[sin_key]
            base_m_sin_name  = weight_mapping[m_sin_key]
        except KeyError as e:
            raise KeyError(
                f"Mapping label {e!s} not found on measurement pulse '{pulseInfo.pulse}'. "
                f"Available labels: {sorted(weight_mapping.keys())}"
            )

        Li1, Li2 = _total_len(base_cos_name), _total_len(base_sin_name)
        if Li1 != Li2:
            raise ValueError(
                f"I-channel IW lengths differ: {Li1} vs {Li2} "
                f"({cos_key}->{base_cos_name}, {sin_key}->{base_sin_name})"
            )
        Lq1, Lq2 = _total_len(base_m_sin_name), _total_len(base_cos_name)
        if Lq1 != Lq2:
            raise ValueError(
                f"Q-channel IW lengths differ: {Lq1} vs {Lq2} "
                f"({m_sin_key}->{base_m_sin_name}, {cos_key}->{base_cos_name})"
            )

        # -------- configure measureMacro for acquisition --------------------------
        mm = cQED_programs.measureMacro
        mm.push_settings()
        mm.set_pulse_op(pulseInfo, active_op=measure_op, weights=([cos_key, sin_key], [m_sin_key, cos_key]), weight_len=pulseInfo.length)
        mm.set_gain(gain)
        # -------- processors: blobs + discriminator fit ---------------------------
        def _proc_make_blobs(out, **_):
            if "S" in out and "S_g" not in out and "S_e" not in out:
                S = np.asarray(out["S"])
                if S.ndim >= 2 and S.shape[1] >= 2:
                    out["S_g"] = S[:, 0]
                    out["S_e"] = S[:, 1]
            return out

        def _proc_fit_disc(out: Output, **_) -> Output:
            if "S_g" in out and "S_e" in out:
                S_g = np.asarray(out["S_g"])
                S_e = np.asarray(out["S_e"])
                disc = two_state_discriminator(
                    S_g.real,
                    S_g.imag,
                    S_e.real,
                    S_e.imag,
                    **kwargs,
                )

                out.update(disc)
                angle = float(out["angle"])
                phi = -angle
                C = float(np.cos(phi))
                S_ = float(np.sin(phi))

                out["w_plus_cos"]  = C
                out["w_plus_sin"]  = -S_
                out["w_minus_sin"] = -S_
                out["w_minus_cos"] = -C
            return out
        
        self.quaProgMngr.set_element_fq(attr.ro_el, drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        iq_blob_prog = cQED_programs.iq_blobs(
            attr.ro_el, attr.qb_el, r180, attr.qb_therm_clks, n_samples
        )
        rr = self.quaProgMngr.run_program(
            iq_blob_prog,
            n_total=n_samples,
            processors=[pp.proc_default, _proc_make_blobs, _proc_fit_disc],
            process_in_sim=False, targets=[("Ig", "Qg", "g"), ("Ie", "Qe", "e")],
        )

        if rr.mode == ExecMode.SIMULATE:
            mm.restore_settings()
            return rr
        out = rr.output
        if "angle" not in out:
            mm.restore_settings()
            return rr

        # -------- build rotated weights from base pair ----------------------------
        C = float(out["w_plus_cos"])   # cos(phi)
        S = -float(out["w_plus_sin"])  # +sin(phi)

        label_prefix   = "" if is_readout else f"{pulseInfo.op}_"
        rot_cos_name   = _name(label_prefix, "rot_cos")
        rot_sin_name   = _name(label_prefix, "rot_sin")
        rot_m_sin_name = _name(label_prefix, "rot_m_sin")

        base_is_segmented = self.pulseOpMngr.is_segmented_integration_weight(base_cos_name)

        if not base_is_segmented:
            L = int(pulseInfo.length or 0)
            if L <= 0:
                mm.restore_settings()
                raise ValueError(
                    f"Pulse length invalid for '{pulseInfo.pulse}': {pulseInfo.length}"
                )
            self.pulseOpMngr.add_int_weight(rot_cos_name,   C,  -S, L, persist=persist)
            self.pulseOpMngr.add_int_weight(rot_sin_name,   S,   C, L, persist=persist)
            self.pulseOpMngr.add_int_weight(rot_m_sin_name, -S, -C, L, persist=persist)
        else:
            cos_cos_segs, cos_sin_segs = self.pulseOpMngr.get_integration_weight_segments(base_cos_name)
            sin_cos_segs, sin_sin_segs = self.pulseOpMngr.get_integration_weight_segments(base_sin_name)

            if len(cos_cos_segs) != len(sin_cos_segs) or len(cos_sin_segs) != len(sin_sin_segs):
                mm.restore_settings()
                raise ValueError("Segment count mismatch between base cos/sin weights.")
            for i, ((_, La), (_, Lb)) in enumerate(zip(cos_cos_segs, sin_cos_segs)):
                if La != Lb:
                    mm.restore_settings()
                    raise ValueError(f"Cos-channel segment length mismatch at {i}: {La} vs {Lb}")
            for i, ((_, La), (_, Lb)) in enumerate(zip(cos_sin_segs, sin_sin_segs)):
                if La != Lb:
                    mm.restore_settings()
                    raise ValueError(f"Sin-channel segment length mismatch at {i}: {La} vs {Lb}")

            rc_cos = self.pulseOpMngr.lincomb_segments(C,  -S, cos_cos_segs, sin_cos_segs)
            rc_sin = self.pulseOpMngr.lincomb_segments(C,  -S, cos_sin_segs, sin_sin_segs)
            self.pulseOpMngr.add_int_weight_segments(rot_cos_name, rc_cos, rc_sin, persist=persist)

            rs_cos = self.pulseOpMngr.lincomb_segments(S,   C, cos_cos_segs, sin_cos_segs)
            rs_sin = self.pulseOpMngr.lincomb_segments(S,   C, cos_sin_segs, sin_sin_segs)
            self.pulseOpMngr.add_int_weight_segments(rot_sin_name, rs_cos, rs_sin, persist=persist)

            rm_cos = self.pulseOpMngr.lincomb_segments(-S, -C, cos_cos_segs, sin_cos_segs)
            rm_sin = self.pulseOpMngr.lincomb_segments(-S, -C, cos_sin_segs, sin_sin_segs)
            self.pulseOpMngr.add_int_weight_segments(rot_m_sin_name, rm_cos, rm_sin, persist=persist)

        # -------- update pulse mapping (+ synonyms) -------------------------------
        map_rot_cos      = _name(op_prefix, "rot_cos")
        map_rot_sin      = _name(op_prefix, "rot_sin")
        map_rot_m_sin    = _name(op_prefix, "rot_m_sin")
        map_rot_cosine   = _name(op_prefix, "rot_cosine")
        map_rot_sine_lbl = _name(op_prefix, "rot_sine")
        map_rot_m_sin2   = _name(op_prefix, "rot_m_sin")

        for lab, iw in (
            (map_rot_cos,      rot_cos_name),
            (map_rot_sin,      rot_sin_name),
            (map_rot_m_sin,    rot_m_sin_name),
            (map_rot_cosine,   rot_cos_name),
            (map_rot_sine_lbl, rot_sin_name),
            (map_rot_m_sin2,   rot_m_sin_name),
        ):
            self.pulseOpMngr.append_integration_weight_mapping(
                pulseInfo.pulse, lab, iw, override=True
            )

        updated_map = dict(weight_mapping)
        updated_map.update({
            map_rot_cos:      rot_cos_name,
            map_rot_sin:      rot_sin_name,
            map_rot_m_sin:    rot_m_sin_name,
            map_rot_cosine:   rot_cos_name,
            map_rot_sine_lbl: rot_sin_name,
            map_rot_m_sin2:   rot_m_sin_name,
        })

        # Build a *patch* PulseOp: only names + mapping, no raw samples.
        patch = PulseOp(
            element=pulseInfo.element,
            op=pulseInfo.op,
            pulse=pulseInfo.pulse,
            type=pulseInfo.type,
            length=pulseInfo.length,
            digital_marker=pulseInfo.digital_marker,
            I_wf_name=pulseInfo.I_wf_name,
            Q_wf_name=pulseInfo.Q_wf_name,
            I_wf=None,
            Q_wf=None,
            int_weights_mapping=updated_map,
            int_weights_defs=None,
        )

        self.pulseOpMngr.modify_pulse_op(patch, persist=persist)

        # -------- optionally apply rotated labels to the macro --------------------
        if update_measureMacro:
            mm.set_pulse_op(
                pulseInfo,
                active_op=measure_op,
                weights=([map_rot_cos, map_rot_sin], [map_rot_m_sin, map_rot_cos]),
                weight_len=pulseInfo.length,
            )
            mm.set_drive_frequency(drive_frequency)
            mm._update_readout_discrimination(out)
        else:
            mm.restore_settings()

        if burn_rot_weights:
            self.burn_pulses()
        # -------- stash debug/metadata -------------------------------------------
        out["base_labels_used"] = (cos_key, sin_key, m_sin_key)
        out["base_names_used"]  = (base_cos_name, base_sin_name, base_m_sin_name)
        out["rot_labels"]       = ([map_rot_cos, map_rot_sin], [map_rot_m_sin, map_rot_cos])
        out["rot_names"]        = ([rot_cos_name, rot_sin_name], [rot_m_sin_name, rot_cos_name])
        
        # Auto-update post-selection config if requested
        if auto_update_postsel:
            post_sel_config = PostSelectionConfig.from_discrimination_results(
                rr.output, blob_k_g=blob_k_g, blob_k_e=blob_k_e
            )

            measureMacro.set_post_select_config(post_sel_config)
            _logger.info(
                "Auto-updated post-selection config: policy=%s (use in butterfly without passing params)",
                post_sel_config.policy
            )


        return rr

    def readout_ge_integrated_trace(
        self,
        ro_op,
        drive_frequency,
        weights,
        num_div: int | None = None,
        *,
        r180: str = "x180",
        ro_depl_clks=None,
        n_avg: int = 100,
        process_in_sim: bool = False,
    ) -> RunResult:
        """
        Run cQED_programs.readout_ge_sliced_trace and return g/e traces.

        Responsibilities:
        - sanity check num_div / div_clks vs pulse length
        - if num_div is None, choose the largest valid num_div such that:
            * pulse_len % num_div == 0
            * (pulse_len / num_div) is a multiple of 4 ns
        - set element frequencies
        - build & run the QUA program
        - convert II, IQ, QI, QQ into g_trace and e_trace

        It does NOT:
        - normalize the traces
        - build segmented weights
        - touch measureMacro or PulseOp mappings
        """
        attr = self.attributes
        if ro_depl_clks is None:
            ro_depl_clks = attr.ro_therm_clks

        # ----- pulse length & tiling checks ---------------------------------
        pulseOp   = self.pulseOpMngr.get_pulseOp_by_element_op(attr.ro_el, ro_op)
        pulse_len = pulseOp.length  # in ns

        # Pre-compute all valid (num_div, div_clks) pairs:
        #  - pulse_len % d == 0  â†’ slice length is integer
        #  - (pulse_len // d) % 4 == 0 â†’ slice length is multiple of 4 ns
        valid_pairs = [
            (d, pulse_len // d // 4)
            for d in range(1, pulse_len + 1)
            if pulse_len % d == 0 and ((pulse_len // d) % 4 == 0)
        ]

        if not valid_pairs:
            raise ValueError(
                "readout_ge_integrated_trace: no valid num_div for this pulse length.\n"
                f"- pulse_len = {pulse_len} ns\n"
                "You must choose pulse_len so it can be tiled into slices that are "
                "integer multiples of 4 ns."
            )

        # If num_div not given, choose the largest valid one
        if num_div is None:
            num_div = max(d for d, _ in valid_pairs)

        if num_div <= 0:
            raise ValueError(f"num_div must be > 0, got {num_div}")

        # Check that the requested num_div is valid
        if not any(d == num_div for d, _ in valid_pairs):
            raise ValueError(
                "readout_ge_integrated_trace: invalid num_div.\n"
                f"- pulse_len = {pulse_len} ns\n"
                f"- requested num_div = {num_div}\n"
                f"- pulse_len / num_div = {pulse_len / num_div:.3f} ns (must be an "
                "integer multiple of 4 ns)\n\n"
                "Choose num_div such that pulse_len / num_div is an integer multiple of 4 ns.\n"
                f"Valid (num_div, div_clks) pairs are: {valid_pairs}"
            )

        # At this point num_div is guaranteed valid; you can also compute div_clks if needed:
        div_clks = (pulse_len // num_div) // 4

        # we still want measureMacro configured before program construction
        measureMacro.push_settings()
        measureMacro.set_pulse_op(pulseOp, active_op=ro_op)

        # ----- frequencies & QUA program ------------------------------------
        self.quaProgMngr.set_element_fq(attr.ro_el, drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        prog = cQED_programs.readout_ge_integrated_trace(
            attr.qb_el, weights, num_div, div_clks, r180, ro_depl_clks, n_avg
        )

        # ----- local helpers ------------------------------------------------
        def _divide_array_in_half(arr):
            split_index = len(arr) // 2
            return arr[:split_index], arr[split_index:]

        def _post_proc(out: Output, **_):
            # Expect II, IQ, QI, QQ coming from the QUA program
            II, IQ, QI, QQ = out.extract("II", "IQ", "QI", "QQ")

            # Split into |g> / |e> halves
            IIg, IIe = _divide_array_in_half(II)
            IQg, IQe = _divide_array_in_half(IQ)
            QIg, QIe = _divide_array_in_half(QI)
            QQg, QQe = _divide_array_in_half(QQ)

            Ig = np.asarray(IIg) + np.asarray(IQg)
            Ie = np.asarray(IIe) + np.asarray(IQe)
            Qg = np.asarray(QIg) + np.asarray(QQg)
            Qe = np.asarray(QIe) + np.asarray(QQe)

            out["g_trace"] = Ig + 1j * Qg
            out["e_trace"] = Ie + 1j * Qe
            out["div_clks"] = div_clks
            out["num_div"] = num_div
            time_list = np.arange(div_clks * 4, pulse_len + 1, 4*div_clks)
            out["time_list"] = time_list
            return out

        measureMacro.restore_settings()
        # ----- run program --------------------------------------------------
        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=[_post_proc],
            process_in_sim=process_in_sim,
        )
        return runres

    def readout_weights_optimization(
        self,
        ro_op,
        drive_frequency,
        cos_w_key,
        sin_w_key,
        m_sin_w_key,
        *,
        num_div=1,
        r180="x180",
        ro_depl_clks=None,
        n_avg=100,
        persist=False,
        set_measureMacro=False,
        make_plots: bool = True,
    ) -> RunResult:

        # ------------------ pull attributes / pulse info ------------------
        attr = self.attributes
        if ro_depl_clks is None:
            ro_depl_clks = attr.ro_therm_clks

        weights = [cos_w_key, sin_w_key, m_sin_w_key, cos_w_key]

        pulseOp = self.pulseOpMngr.get_pulseOp_by_element_op(attr.ro_el, ro_op)
        pulse   = pulseOp.pulse
        pulse_len = pulseOp.length            # total readout length in clk cycles
        
        # ------------------ run sliced-trace program ------------------
        runres = self.readout_ge_integrated_trace(
            ro_op,
            drive_frequency,
            weights,
            num_div,
            r180=r180,
            ro_depl_clks=ro_depl_clks,
            n_avg=n_avg,
        )
        o = runres.output

        # ------------------ helper functions (optimization-side) -------------
        def _normalize_complex_array(arr):
            arr = np.asarray(arr)
            norm = np.sqrt(np.sum(np.abs(arr) ** 2))
            if norm == 0:
                return arr
            arr = arr / norm
            mx = np.max(np.abs(arr))
            return arr / (mx if mx != 0 else 1.0)

        def _segments_per_slice(vec, L_clks):
            vec = np.asarray(vec, dtype=float).tolist()
            return [(a, int(4 * L_clks)) for a in vec]

        # ------------------ build ge_diff, normalized vector & segments ------

        g_trace, e_trace = o.extract("g_trace", "e_trace")
        div_clks = o["div_clks"]

        division_len = 4 * div_clks  
        ge_diff = e_trace - g_trace
        ge_diff_norm = _normalize_complex_array(ge_diff)

        # stash for later inspection
        o["ge_diff_trace"]      = ge_diff
        o["ge_diff_trace_norm"] = ge_diff_norm

        Re  = ge_diff_norm.real
        Im  = ge_diff_norm.imag
        nRe = -Re
        nIm = -Im

        seg_cosine_cos    = _segments_per_slice(Re,  div_clks)
        seg_cosine_sin    = _segments_per_slice(nIm, div_clks)

        seg_sine_cos      = _segments_per_slice(Im,  div_clks)
        seg_sine_sin      = _segments_per_slice(Re,  div_clks)

        seg_minus_sin_cos = _segments_per_slice(nIm, div_clks)
        seg_minus_sin_sin = _segments_per_slice(nRe, div_clks)

        o["seg_cosine_cos"]      = seg_cosine_cos
        o["seg_cosine_sin"]      = seg_cosine_sin
        o["seg_sine_cos"]        = seg_sine_cos
        o["seg_sine_sin"]        = seg_sine_sin
        o["seg_minus_sin_cos"]   = seg_minus_sin_cos
        o["seg_minus_sin_sin"]   = seg_minus_sin_sin
        o["opt_vec_Re"]          = Re
        o["opt_vec_Im"]          = Im

        # ------------------ map segmented weights into PulseOp ---------------
        weight_mapping = pulseOp.int_weights_mapping
        cos_weights, sine_weights, m_sine_weights = (
            weight_mapping[cos_w_key],
            weight_mapping[sin_w_key],
            weight_mapping[m_sin_w_key],
        )

        opt_cos_label   = f"opt_{cos_weights}"
        opt_sin_label   = f"opt_{sine_weights}"
        opt_m_sin_label = f"opt_{m_sine_weights}"

        self.pulseOpMngr.add_int_weight_segments(
            opt_cos_label, seg_cosine_cos, seg_cosine_sin, persist=persist
        )
        self.pulseOpMngr.add_int_weight_segments(
            opt_sin_label, seg_sine_cos, seg_sine_sin, persist=persist
        )
        self.pulseOpMngr.add_int_weight_segments(
            opt_m_sin_label, seg_minus_sin_cos, seg_minus_sin_sin, persist=persist
        )

        opt_cos_key   = f"opt_{cos_w_key}"
        opt_sin_key   = f"opt_{sin_w_key}"
        opt_m_sin_key = f"opt_{m_sin_w_key}"

        self.pulseOpMngr.append_integration_weight_mapping(
            pulse, opt_cos_key, opt_cos_label, override=True
        )
        self.pulseOpMngr.append_integration_weight_mapping(
            pulse, opt_sin_key, opt_sin_label, override=True
        )
        self.pulseOpMngr.append_integration_weight_mapping(
            pulse, opt_m_sin_key, opt_m_sin_label, override=True
        )

        o["opt_cos_key"]   = opt_cos_key
        o["opt_sin_key"]   = opt_sin_key
        o["opt_m_sin_key"] = opt_m_sin_key

        # ------------------ measureMacro bindings / persistence --------------
        if set_measureMacro:
            measureMacro.set_outputs(
                [[opt_cos_key, opt_sin_key], [opt_m_sin_key, opt_cos_key]],
                weight_len=int(div_clks * 4),
            )
            self.burn_pulses()

        # ------------------ plotting (analysis) -------------------------------
        if make_plots:
            ns_per_clk = getattr(attr, "ns_per_clk", 4)  # default 4 ns / clk
            readout_len_ns = pulse_len * ns_per_clk
            step_ns = division_len * ns_per_clk
            time_list = np.arange(step_ns, readout_len_ns + 1e-9, step_ns) / 4

            fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14, 5))

            # --- axis 1: ground trace ---
            ax1.plot(time_list, g_trace.real, label="real")
            ax1.plot(time_list, g_trace.imag, label="imag")
            ax1.set_title("ground trace")
            ax1.set_xlabel("time [ns]")
            ax1.set_ylabel("demod [a.u.]")
            ax1.legend()

            # --- axis 2: excited trace ---
            ax2.plot(time_list, e_trace.real, label="real")
            ax2.plot(time_list, e_trace.imag, label="imag")
            ax2.set_title("excited trace")
            ax2.set_xlabel("time [ns]")
            ax2.set_ylabel("demod [a.u.]")
            ax2.legend()

            # --- axis 3: normalized vs unnormalized ge_diff ---
            # left y-axis: normalized difference
            l1 = ax3.plot(time_list, ge_diff_norm.real, label="Re (norm)")
            l2 = ax3.plot(time_list, ge_diff_norm.imag, label="Im (norm)")
            ax3.set_title(r"|eâŸ© âˆ’ |gâŸ© (normalized)")
            ax3.set_xlabel("time [ns]")
            ax3.set_ylabel("norm diff [a.u.]")

            # right y-axis: unnormalized difference
            ax3b = ax3.twinx()
            l3 = ax3b.plot(time_list, ge_diff.real, "--", label="Re (unnorm)")
            l4 = ax3b.plot(time_list, ge_diff.imag, "--", label="Im (unnorm)")
            ax3b.set_ylabel("unnorm diff [a.u.]")

            # combined legend for both axes
            lines  = l1 + l2 + l3 + l4
            labels = [ln.get_label() for ln in lines]
            ax3.legend(lines, labels, loc="best")

            plt.tight_layout()
            plt.show()

        return runres

    def readout_butterfly_measurement(
        self,
        prep_policy: str | None = None,
        prep_kwargs: dict | None = None,
        r180: str = "x180",
        update_measureMacro: bool = False,
        show_analysis: bool = False,
        n_samples: int = 10_000,
        M0_MAX_TRIALS: int = 16,
        *,
        use_stored_config: bool = True,
        det_L_threshold: float = 1e-8,
    ) -> RunResult:
        """
        Butterfly readout measurement with post-selection.
        """
        # ------------------ resolve config ------------------
        if use_stored_config and (prep_policy is None or prep_kwargs is None):
            stored_config = measureMacro.get_post_select_config()
            if stored_config is None:
                raise ValueError(
                    "No prep_policy/prep_kwargs provided and no stored config available. "
                    "Either pass explicit prep_policy and prep_kwargs, or run "
                    "readout_ge_discrimination(auto_update_postsel=True) first."
                )
            if prep_policy is None:
                prep_policy = stored_config.policy
                _logger.info("Using stored prep_policy: %s", prep_policy)
            if prep_kwargs is None:
                prep_kwargs = stored_config.kwargs
                _logger.info("Using stored prep_kwargs from post_sel_config")
        elif prep_policy is None or prep_kwargs is None:
            raise ValueError(
                "Both prep_policy and prep_kwargs must be provided when use_stored_config=False "
                "or when no stored config is available."
            )

        attr = self.attributes
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        # ------------------ build + run butterfly ------------------
        prog = cQED_programs.readout_butterfly_measurement(
            attr.qb_el, r180, prep_policy, prep_kwargs, M0_MAX_TRIALS, n_samples
        )

        def _butterfly_metrics(out: Output, **_):
            import numpy as np
            
            states = out.extract("states")
            m0_g, m1_g, m2_g = states[:, 0, 0].astype(bool), states[:, 0, 1].astype(bool), states[:, 0, 2].astype(bool)
            m0_e, m1_e, m2_e = states[:, 1, 0].astype(bool), states[:, 1, 1].astype(bool), states[:, 1, 2].astype(bool)

            I0, Q0, I1, Q1, I2, Q2 = out.extract("I0", "Q0", "I1", "Q1", "I2", "Q2")
            
            S0_g = I0[:, 0] + 1j * Q0[:, 0]
            S0_e = I0[:, 1] + 1j * Q0[:, 1]
            S1_g = I1[:, 0] + 1j * Q1[:, 0]
            S1_e = I1[:, 1] + 1j * Q1[:, 1]
            S2_g = I2[:, 0] + 1j * Q2[:, 0]
            S2_e = I2[:, 1] + 1j * Q2[:, 1]

            # clean raw blobs from out
            if "I1" in out: del out["I1"]
            if "Q1" in out: del out["Q1"]
            if "I2" in out: del out["I2"]
            if "Q2" in out: del out["Q2"]

            # ---- M0/M1/M2 outcome probabilities -----------------------------
            P0_g = compute_probabilities(m0_g)[0]
            P0_e = compute_probabilities(m0_e)[1]
            P1_g = compute_probabilities(m1_g)[0]
            P1_e = compute_probabilities(m1_e)[1]
            P2_g = compute_probabilities(m2_g)[0]
            P2_e = compute_probabilities(m2_e)[1]

            df = pd.DataFrame(
                {
                    "Ground (g)":  [P0_g, P1_g, P2_g],
                    "Excited (e)": [P0_e, P1_e, P2_e],
                },
                index=["m0", "m1", "m2"],
            )

            metrics = butterfly_metrics(
                m1_g=m1_g,
                m1_e=m1_e,
                m2_g=m2_g,
                m2_e=m2_e,
                det_L_threshold=det_L_threshold,
            )

            if "note" in metrics:
                new_note = metrics["note"]
                old_note = out.get("note", "")
                out["note"] = (old_note + " | " + new_note) if old_note else new_note

            for key, val in metrics.items():
                if key == "note":
                    continue
                out[key] = val

            out.update(
                {
                    "m0_g": m0_g,
                    "m0_e": m0_e,
                    "m1_g": m1_g,
                    "m1_e": m1_e,
                    "m2_g": m2_g,
                    "m2_e": m2_e,
                    "S0_g": S0_g,
                    "S0_e": S0_e,
                    "S1_g": S1_g,
                    "S1_e": S1_e,
                    "S2_g": S2_g,
                    "S2_e": S2_e,
                    "butterfly_df": df,
            })
            return out

        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_samples,
            processors=[_butterfly_metrics],
            process_in_sim=False,
        )
        out = runres.output

        # ------------------ optional printing / analysis ------------------
        # ---- Optional analysis / printing ----------------------------------------
        if show_analysis:
            import numpy as np

            # --------- Pull key metrics (if present) ----------
            F = out.get("F", np.nan)
            Q = out.get("Q", np.nan)
            V = out.get("V", np.nan)

            # --------- T1-limited bounds (same as your original) ----------
            T1 = getattr(attr, "qb_T1_relax", None)
            try:
                delay_t_measure = 60
                t_base = measureMacro.active_length() + delay_t_measure
            except Exception:
                t_base = None

            if (T1 is not None) and (T1 > 0) and (t_base is not None):
                F_max = 0.5 * (1.0 + np.exp(-float(t_base) / T1))
                Q_max = 0.5 * (1.0 + np.exp(-float(t_base) / T1))
            else:
                F_max = np.nan
                Q_max = np.nan

            out["F_max"] = F_max
            out["Q_max"] = Q_max

            # --------- Print headline metrics ----------
            if np.isfinite(F) and np.isfinite(Q) and np.isfinite(V):
                print(
                    f"Fidelity of M1: {F:.4f}, "
                    f"QND-ness of M1: {Q:.4f}, "
                    f"Visibility of M1: {V:.4f}"
                )
                if np.isfinite(F_max) and np.isfinite(Q_max):
                    print(
                        f"T1-limited F_max: {F_max:.4f}, "
                        f"T1-limited Q_max: {Q_max:.4f}"
                    )
            else:
                print("Butterfly measurement produced invalid F/Q/V (check thresholds / weights).")

            # --------- Probabilities table ----------
            df = out.get("butterfly_df", None)
            if df is not None:
                print("\nSingle-shot outcome probabilities P(m_k | state_i):")
                print(df.to_markdown(floatfmt=".4f"))
            else:
                print("\n(butterfly_df missing)")

            # --------- Confusion matrix ----------
            confusion_matrix = out.get("confusion_matrix", None)
            if confusion_matrix is not None:
                print("\nMeasurement confusion matrix Lambda_M = P(m1 | state_i):")
                print(confusion_matrix.to_markdown(floatfmt=".4f"))
            else:
                print("\n(confusion_matrix missing)")

            # --------- Transition matrix ----------
            transition_matrix = out.get("transition_matrix", None)
            if transition_matrix is not None:
                print("\nPost-measurement transition matrix T = P(state_o | state_i):")
                print(transition_matrix.to_markdown(floatfmt=".4f"))

            # --------- Acceptance + tries ----------
            try:
                accept_rate, average_tries = out.extract("acceptance_rate", "average_tries")
                print("\nacceptance rate:", accept_rate)
                print("average tries:", average_tries)
            except Exception:
                # older runs might not have these keys
                pass

            # --------- Optional Î·-calibration summary ----------
            if ("eta_g" in out) and ("eta_e" in out):
                print("\nCore-efficiency calibration (single-shot):")
                print(f"eta_g = {out['eta_g']:.4f}, eta_e = {out['eta_e']:.4f}")
                if ("eta_fp_e_given_g" in out) and ("eta_fp_g_given_e" in out):
                    print(
                        f"false pos e|g = {out['eta_fp_e_given_g']:.4e}, "
                        f"g|e = {out['eta_fp_g_given_e']:.4e}"
                    )
                if ("eta_unknown_g" in out) and ("eta_unknown_e" in out):
                    print(
                        f"unknown g = {out['eta_unknown_g']:.4f}, "
                        f"unknown e = {out['eta_unknown_e']:.4f}"
                    )

            # --------- Two-state discriminator plots (your original M0/M1/M2 analysis) ----------
            try:
                # These are stored by _butterfly_metrics
                S0_g, S0_e, S1_g, S2_g, S1_e, S2_e = out.extract(
                    "S0_g", "S0_e", "S1_g", "S2_g", "S1_e", "S2_e"
                )

                kwargs_m0 = {"plots": ("raw_blob", "hist"), "fig_title": "M0 analysis", "b_plot": True}
                kwargs_m1 = {"plots": ("rot_blob", "hist", "info"), "fig_title": "M1 analysis", "b_plot": True}
                kwargs_m2 = {"plots": ("rot_blob", "hist", "info"), "fig_title": "M2 analysis", "b_plot": True}

                _ = two_state_discriminator(S0_g.real, S0_g.imag, S0_e.real, S0_e.imag, **kwargs_m0)
                _ = two_state_discriminator(S1_g.real, S1_g.imag, S1_e.real, S1_e.imag, **kwargs_m1)
                _ = two_state_discriminator(S2_g.real, S2_g.imag, S2_e.real, S2_e.imag, **kwargs_m2)

            except Exception as e:
                print(f"\n(two_state_discriminator M0/M1/M2 plots skipped: {e})")


        # ------------------ optional update cache ------------------
        if update_measureMacro:
            measureMacro._update_readout_quality(out)

        return runres


    
    def active_qubit_reset_benchmark(self, post_sel_policy, post_sel_kwargs, show_analysis=True, MAX_PREP_TRIALS=100, n_shots=10000) -> RunResult:
        """
        Benchmark active qubit reset using M0-based feedback.

        Runs the cQED_programs.active_qubit_reset_benchmark QUA program,
        which performs repeated qubit preparations and measures the
        effectiveness of active reset.

        Returns:
            RunResult: The result of the QUA program execution, containing
                       measurement outcomes and statistics.
        """
        attr = self.attributes
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        prog = cQED_programs.active_qubit_reset_benchmark(
            qb_el=attr.qb_el,
            post_sel_policy=post_sel_policy,
            post_sel_kwargs=post_sel_kwargs,
            r180="x180",
            qb_therm_clks=attr.qb_therm_clks,
            MAX_PREP_TRIALS=MAX_PREP_TRIALS,
            n_shots=n_shots
        )

        def _process_reset_benchmark(out: dict, **_):
            """
            Post-process active reset benchmark using a *soft posterior* for the final verification (M2).

            Assumptions:
            - pp.proc_default(out, targets=[("I0","Q0"),("I1","Q1"),("I2","Q2")]) creates complex streams:
                S_0, S_1, S_2 with S_k = I_k + i Q_k  (shape: (n_shots, 2))
            - out["m0"], out["m1"], out["m2"] exist (shape: (n_shots, 2))
            - out["accept"] exists (preferred) with shape (n_shots, 2); otherwise fallback to m0 masks
            - measureMacro._ro_disc_params contains:
                threshold, rot_mu_g, rot_mu_e, sigma_g, sigma_e
                where rot_mu_* are complex means in the *rotated* IQ frame used for discrimination.

            Outputs:
            out["reset_benchmark"]["matrices"]["C_trigger"]["matrix"]:
                C_trigger[trigger_bit, initial] = P(trigger_bit | initial)
                rows: rep0(no_pi), rep1(pi)   cols: init_g, init_e

            out["reset_benchmark"]["matrices"]["R_sim"]["matrix"]:
                R_sim[final, trigger_bit] = P(final | trigger_bit)
                rows: g,e   cols: rep0(no_pi), rep1(pi)

            Also stores m2_corrected (soft) in out for downstream use.
            """
            import numpy as np
            import warnings

            out = pp.proc_default(out, axis=0, targets=[("I0", "Q0"), ("I1", "Q1"), ("I2", "Q2")])

            # Complex IQ after proc_default
            S0 = np.asarray(out["S_0"])
            S1 = np.asarray(out["S_1"])
            S2 = np.asarray(out["S_2"])

            m0 = np.asarray(out["m0"])
            m1 = np.asarray(out["m1"])
            m2 = np.asarray(out["m2"])

            # Basic checks
            for name, arr in [("S_0", S0), ("S_1", S1), ("S_2", S2), ("m0", m0), ("m1", m1), ("m2", m2)]:
                if arr.ndim != 2 or arr.shape[1] != 2:
                    raise ValueError(f"Expected {name} shape (n_shots,2), got {arr.shape}")
            n_shots = int(m0.shape[0])

            # ------------------------------------------------------------
            # Accept masks (preferred): from QUA post-selection stream "accept"
            # ------------------------------------------------------------
            acc = out.get("accept", None)
            use_acc_stream = False
            if acc is not None:
                acc = np.asarray(acc)
                if acc.shape == m0.shape:
                    acc = acc.astype(bool)
                    use_acc_stream = True

            if use_acc_stream:
                acc_g = acc[:, 0]
                acc_e = acc[:, 1]
            else:
                warnings.warn(
                    "accept missing or wrong shape; falling back to m0-based masks. "
                    "For best correctness, save accept as (n_shots,2).",
                    RuntimeWarning,
                )
                m0_g = m0[:, 0].astype(bool)
                m0_e = m0[:, 1].astype(bool)
                acc_g = ~m0_g
                acc_e = m0_e

            # ------------------------------------------------------------
            # Soft posterior: m2_corrected = P(e | S2)
            # Using isotropic Gaussian blobs in the rotated IQ frame.
            # ------------------------------------------------------------
            disc = getattr(measureMacro, "_ro_disc_params", {}) or {}
            mu_g = disc.get("rot_mu_g", None)
            mu_e = disc.get("rot_mu_e", None)
            sig_g = disc.get("sigma_g", None)
            sig_e = disc.get("sigma_e", None)

            if mu_g is None or mu_e is None or sig_g is None or sig_e is None:
                raise ValueError(
                    "measureMacro._ro_disc_params must contain rot_mu_g, rot_mu_e, sigma_g, sigma_e "
                    "to compute soft posterior m2_corrected."
                )

            mu_g = np.complex128(mu_g)
            mu_e = np.complex128(mu_e)
            sig_g = float(sig_g)
            sig_e = float(sig_e)
            if sig_g <= 0 or sig_e <= 0:
                raise ValueError(f"Invalid sigma values: sigma_g={sig_g}, sigma_e={sig_e}")

            # Equal priors by default; you can change if you want
            prior_e = 0.5
            prior_g = 1.0 - prior_e

            # log-likelihoods (up to additive constants)
            dg2 = np.abs(S2 - mu_g) ** 2
            de2 = np.abs(S2 - mu_e) ** 2
            lg = -dg2 / (2.0 * sig_g**2 + 1e-30) + np.log(prior_g + 1e-30)
            le = -de2 / (2.0 * sig_e**2 + 1e-30) + np.log(prior_e + 1e-30)

            # stable posterior
            m2_corrected = 1.0 / (1.0 + np.exp(lg - le))
            m2_corrected = np.asarray(m2_corrected, dtype=float)  # shape (n_shots,2)

            # Store for downstream debugging
            out["m2_corrected"] = m2_corrected

            # ------------------------------------------------------------
            # Define the *actual trigger bit* used by reset:
            # r = 1[ I1 > thr ], with I1 = real(S1) after proc_default
            # ------------------------------------------------------------
            thr = disc.get("threshold", None)
            if thr is None:
                raise ValueError("measureMacro._ro_disc_params['threshold'] must be set.")
            thr = float(thr)

            I1 = np.real(S1)
            trig = (I1 > thr)  # shape (n_shots,2), bool
            trig_g = trig[:, 0]
            trig_e = trig[:, 1]

            # ------------------------------------------------------------
            # Helper: mean + SE on masked values
            # ------------------------------------------------------------
            def mean_se(x, mask):
                x = np.asarray(x, dtype=float)
                mask = np.asarray(mask, dtype=bool)
                x = x[mask]
                n = int(x.size)
                if n == 0:
                    return np.nan, np.nan, 0
                p = float(np.mean(x))
                se = float(np.sqrt(max(p * (1.0 - p), 0.0) / n))
                return p, se, n

            # ------------------------------------------------------------
            # (A) Benchmark-style: P(final | initial branch) using m2_corrected
            # ------------------------------------------------------------
            pe_g, pe_g_se, Ng = mean_se(m2_corrected[:, 0], acc_g)  # P(e | init g)
            pe_e, pe_e_se, Ne = mean_se(m2_corrected[:, 1], acc_e)  # P(e | init e)

            R_init = np.array([[1.0 - pe_g, 1.0 - pe_e],
                            [pe_g,       pe_e      ]], dtype=float)
            col = R_init.sum(axis=0)
            col = np.where(col > 0, col, 1.0)
            R_init = R_init / col

            # ------------------------------------------------------------
            # (B) Confusion of the trigger bit: C_trigger[trigger_bit, initial]
            #     rows: rep0(no_pi)=0, rep1(pi)=1 ; cols: init_g, init_e
            # ------------------------------------------------------------
            p_trig_g, p_trig_g_se, Ng_tr = mean_se(trig_g.astype(float), acc_g)
            p_trig_e, p_trig_e_se, Ne_tr = mean_se(trig_e.astype(float), acc_e)

            C_trigger = np.array([[1.0 - p_trig_g, 1.0 - p_trig_e],
                                [p_trig_g,       p_trig_e      ]], dtype=float)
            col = C_trigger.sum(axis=0)
            col = np.where(col > 0, col, 1.0)
            C_trigger = C_trigger / col

            # ------------------------------------------------------------
            # (C) Simulator reset matrix: R_sim[final, trigger_bit] using m2_corrected
            #     Pool both initial branches, but condition on the ACTUAL trigger bit.
            # ------------------------------------------------------------
            rep0_vals = np.concatenate([
                m2_corrected[:, 0][acc_g & (~trig_g)],
                m2_corrected[:, 1][acc_e & (~trig_e)],
            ])
            rep1_vals = np.concatenate([
                m2_corrected[:, 0][acc_g & ( trig_g)],
                m2_corrected[:, 1][acc_e & ( trig_e)],
            ])

            pe_rep0, pe_rep0_se, N_rep0 = mean_se(rep0_vals, np.ones(rep0_vals.size, dtype=bool))
            pe_rep1, pe_rep1_se, N_rep1 = mean_se(rep1_vals, np.ones(rep1_vals.size, dtype=bool))

            R_sim = np.array([[1.0 - pe_rep0, 1.0 - pe_rep1],
                            [pe_rep0,       pe_rep1      ]], dtype=float)
            col = R_sim.sum(axis=0)
            col = np.where(col > 0, col, 1.0)
            R_sim = R_sim / col

            # Trigger stats (diagnostics)
            trig_stats = dict(
                g=dict(p_trig=p_trig_g, p_trig_se=p_trig_g_se, N=int(np.sum(acc_g))),
                e=dict(p_trig=p_trig_e, p_trig_se=p_trig_e_se, N=int(np.sum(acc_e))),
                threshold=thr,
            )

            out["reset_benchmark"] = dict(
                counts=dict(
                    N_total=n_shots,
                    N_accept_g=int(np.sum(acc_g)),
                    N_accept_e=int(np.sum(acc_e)),
                    accept_source=("stream" if use_acc_stream else "m0_fallback"),
                ),
                residual_excitation_corrected=dict(
                    pe_g=pe_g, pe_g_se=pe_g_se, N_g=Ng,
                    pe_e=pe_e, pe_e_se=pe_e_se, N_e=Ne,
                ),
                trigger=trig_stats,
                matrices=dict(
                    R_init=dict(
                        matrix=R_init,
                        labels=dict(
                            rows=["g", "e"],
                            cols=["init_g", "init_e"],
                            convention="R_init[final, initial] = P(final | initial) using m2_corrected over accepted shots",
                        ),
                    ),
                    C_trigger=dict(
                        matrix=C_trigger,
                        labels=dict(
                            rows=["rep0(no_pi)", "rep1(pi)"],
                            cols=["init_g", "init_e"],
                            convention="C_trigger[trigger_bit, initial] = P(trigger_bit | initial) using accepted shots",
                        ),
                    ),
                    R_sim=dict(
                        matrix=R_sim,
                        labels=dict(
                            rows=["g", "e"],
                            cols=["rep0(no_pi)", "rep1(pi)"],
                            convention="R_sim[final, trigger_bit] = P(final | trigger_bit) using m2_corrected over accepted shots",
                        ),
                        stats=dict(
                            pe_rep0=pe_rep0, pe_rep0_se=pe_rep0_se, N_rep0=int(N_rep0),
                            pe_rep1=pe_rep1, pe_rep1_se=pe_rep1_se, N_rep1=int(N_rep1),
                        ),
                    ),
                ),
            )

            return out

        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_shots,
            processors=[pp.ro_state_correct_proc, _process_reset_benchmark],
            process_in_sim=False,
            targets= [("m2", "m2_corrected")],
            confusion=measureMacro._ro_quality_params.get("confusion_matrix"),
        )

        if show_analysis:
            pass
        return runres

    def calibrate_readout_full(
        self,
        ro_op: str,
        drive_frequency: float,
        *,
        ro_el: str = "resonator",
        r180: str = "x180",
        n_avg_weights: int = 200_000,
        n_samples_disc: int = 250_000,
        n_shots_butterfly: int = 50_000,   # kept name for backward compat; used as butterfly n_samples
        display_analysis: bool = False,
        persist_weights: bool = True,
        save: bool = True,
        skip_weights_optimization: bool = False,  # NEW: skip step 1 if True

        blob_k_g: float = 3.0,
        blob_k_e: float | None = None,
        # NEW: extra kwargs routed to each sub-experiment
        wopt_kwargs: dict | None = None,
        ge_kwargs: dict | None = None,
        bfly_kwargs: dict | None = None,
    ) -> dict:
        """
        End-to-end readout calibration (updated to match your new usage).

        Steps:
        (1) Optimize time-sliced integration weights (optional, skipped if skip_weights_optimization=True).
        (2) Run G/E discriminator, rotate weights, set threshold.
            -> update_measureMacro is used (your new API name).
        (3) Build BLOBS prep_kwargs from discriminator (rot_mu/sigma/threshold) and run butterfly.
        (4) Validation / IQ normalization extraction (uses ge_disc_res outputs).
        (5) Save snapshot of all calibration data.

        Parameters:
        - skip_weights_optimization: If True, skips step 1 (weights optimization) and uses existing weights.

        Kwargs routing:
        - wopt_kwargs -> readout_weights_optimization(...)
        - ge_kwargs   -> readout_ge_discrimination(...)
        - bfly_kwargs -> readout_butterfly_measurement(...)
        """

        wopt_kwargs = dict(wopt_kwargs or {})
        ge_kwargs   = dict(ge_kwargs   or {})
        bfly_kwargs = dict(bfly_kwargs or {})

        if blob_k_e is None:
            blob_k_e = blob_k_g

        mmacro = cQED_programs.measureMacro

        # -------------------------------------------------
        # (1) Integration-weight optimization
        # -------------------------------------------------
        if skip_weights_optimization:
            _logger.info("[readout calib 1/4] Skipping integration weight optimization (using existing weights)...")
            
            # Use default weight keys when skipping optimization
            pulse_op = self.pulseOpMngr.get_pulseOp_by_element_op(ro_el, ro_op)
            cos_w_key, sin_w_key, m_sin_w_key = "cos", "sin", "minus_sin"
            opt_cos_key, opt_sin_key, opt_m_sin_key = cos_w_key, sin_w_key, m_sin_w_key
            
        else:
            _logger.info("[readout calib 1/4] Optimizing integration weights...")

            pulse_op = self.pulseOpMngr.get_pulseOp_by_element_op(ro_el, ro_op)

            # logical labels (and also what you use later as base_weight_keys)
            cos_w_key, sin_w_key, m_sin_w_key = "cos", "sin", "minus_sin"

            wopt_call_kwargs = dict(
                n_avg=n_avg_weights,
                persist=persist_weights,
                make_plots=display_analysis,
                set_measureMacro=True,
            )
            wopt_call_kwargs.update(wopt_kwargs)

            wopt_res = self.readout_weights_optimization(
                ro_op,
                drive_frequency,
                cos_w_key,
                sin_w_key,
                m_sin_w_key,
                **wopt_call_kwargs,
            )

            opt_cos_key, opt_sin_key, opt_m_sin_key = wopt_res.output.extract(
                "opt_cos_key", "opt_sin_key", "opt_m_sin_key"
            )


        # -------------------------------------------------
        # (2) Discriminator fit / rotated weights / threshold
        # -------------------------------------------------
        _logger.info("[readout calib 2/4] Running G/E discrimination & updating measureMacro...")

        ge_call_kwargs = dict(
            n_samples=n_samples_disc,
            base_weight_keys=(opt_cos_key, opt_sin_key, opt_m_sin_key),
            update_measureMacro=True,
            persist=True,
            b_plot=display_analysis,
            plots=("rot_blob", "hist", "info"),
            r180=r180,
            auto_update_postsel=True,  # Auto-update post_sel_config
            blob_k_g=blob_k_g,
            blob_k_e=blob_k_e,
        )
        ge_call_kwargs.update(ge_kwargs)

        ge_disc_res = self.readout_ge_discrimination(
            ro_op,
            drive_frequency,
            **ge_call_kwargs,
        )

        # -------------------------------------------------
        # (3) Butterfly using BLOBS policy from discriminator (now auto-configured)
        # -------------------------------------------------
        _logger.info("[readout calib 3/4] Running butterfly (BLOBS) for alpha/beta/QND + eta calibration...")

        self.burn_pulses()
        
        # Allow override from bfly_kwargs if provided
        bfly_prep_policy = bfly_kwargs.pop("prep_policy", None)
        bfly_prep_kwargs = bfly_kwargs.pop("prep_kwargs", None)

        bfly_call_kwargs = dict(
            prep_policy=bfly_prep_policy,  # Uses stored config if None
            prep_kwargs=bfly_prep_kwargs,  # Uses stored config if None
            show_analysis=display_analysis,
            update_measureMacro=True,
            n_samples=bfly_kwargs.pop("n_samples", n_shots_butterfly),
            M0_MAX_TRIALS=bfly_kwargs.pop("M0_MAX_TRIALS", 1000),
        )
        bfly_call_kwargs.update(bfly_kwargs)
        
        ro_bfly_res = self.readout_butterfly_measurement(**bfly_call_kwargs)

        # -------------------------------------------------
        # (4) Validation / IQ normalization
        # -------------------------------------------------
        _logger.info("[readout calib 4/4] Validating discriminator & computing normalization...")

        self.burn_pulses()

        # NOTE: assumes your readout_ge_discrimination still provides these keys
        S_cg, S_ce, norm_params = ge_disc_res.output.extract("S_g", "S_e", "norm_params")
        factor, offset = norm_params["factor"], norm_params["offset"]

        Sg_norm = apply_norm_IQ(S_cg, factor, offset)
        Se_norm = apply_norm_IQ(S_ce, factor, offset)
        _logger.info("  norm check: <g'>=%.3f, <e'>=%.3f",
                    np.mean(Sg_norm.real), np.mean(Se_norm.real))

        self.attributes.norm_IQ = {"factor": factor, "offset": offset}

        if save:
            self.save_pulses()
            self.save_attributes()
            self.save_measureMacro_state()

        return wopt_res, ge_disc_res, ro_bfly_res


    def readout_amp_len_opt(
        self,
        drive_frequency,
        min_len, max_len, dlen,                # in *ns* (drive-on part)
        min_g, max_g, dg,                      # dimensionless readout gain sweep
        ringdown_len=None,                     # in ns (DEFAULT); if None, computed from kappa (Hz)
        r180="x180",
        base_voltage=0.01,
        ge_disc_kwargs: Mapping[str, Any] | None = None,
        butterfly_kwargs: Mapping[str, Any] | None = None,
    ) -> Output:
        """
        Sweep readout lengths and gains:

        â€¢ For each drive length L_body (ns): use a waveform of length L_body + ringdown_ns:
            - first L_body has constant amplitude `base_voltage`
            - trailing ringdown_ns has zero amplitude
        â€¢ For each (gain, L_body): run GE discrimination â†’ rotated weights + threshold + (mu/sigma)
        â€¢ For each (gain, L_body): run butterfly â†’ F, Q (QND) using those rotated weights

        Conventions:
        â€¢ min_len, max_len, dlen, ringdown_len are all in ns.
        min_len/max_len/dlen refer to the *drive-on* part only.
        â€¢ ringdown_len is a fixed extra â€œdrive-offâ€ duration appended after the drive.
        â€¢ min_g, max_g, dg define the gain sweep (dimensionless).
        â€¢ All lengths are snapped to integer clock cycles (t_clk_ns, default 4 ns) and
        the total length (drive + ringdown) is constrained so that the clock count is a multiple of 4.
        â€¢ PulseOp.length and integration-weight length are specified in ns.
        """

        attr = self.attributes
        mm = cQED_programs.measureMacro

        # Save the original measureMacro state
        base_state_id = mm.push_settings("readout_amp_len_opt_base")

        qubox_logger = logging.getLogger("qubox")
        qm_logger = logging.getLogger("qm")

        try:
            with temporarily_set_levels([qubox_logger, qm_logger], logging.WARNING):
                # ------------------------ timing constants ------------------------
                t_clk_ns = float(getattr(attr, "qm_clk_ns", 4.0))  # ns per QM clock
                drive_frequency = float(drive_frequency)

                # ------------------------ helpers ------------------------
                def _make_aligned_range_ns_and_clks(
                    min_len_ns, max_len_ns, step_ns,
                    mult_clks: int = 4,
                ):
                    """
                    Build a drive-length grid:

                    â€¢ Inputs are in ns.
                    â€¢ Convert to clocks, round *up* to multiples of `mult_clks`.
                    â€¢ Returns (lens_ns, lens_clks) for the *drive-on* part.
                    """
                    def _up_to_mult_clks(x_ns: float) -> int:
                        x_clks = x_ns / t_clk_ns
                        return int(np.ceil(x_clks / mult_clks) * mult_clks)

                    min_c  = _up_to_mult_clks(float(min_len_ns))
                    max_c  = _up_to_mult_clks(float(max_len_ns))
                    step_c = _up_to_mult_clks(float(step_ns))

                    arr_clks = np.arange(min_c, max_c + 1e-9, step_c, dtype=int)
                    arr_clks = (arr_clks // mult_clks) * mult_clks  # safety

                    arr_ns = arr_clks * t_clk_ns
                    return arr_ns.astype(int), arr_clks.astype(int)

                def _ensure_base_rect_weights(pulse: str, L_ns: int, *, prefix: str = ""):
                    """
                    Create single-segment rectangular integration weights of length L_ns (ns).

                    Internally:
                    â€¢ L_clks = round(L_ns / t_clk_ns)
                    â€¢ enforce L_clks % 4 == 0 (QM constraint)
                    """
                    L_ns = int(L_ns)
                    L_clks = int(round(L_ns / t_clk_ns))

                    if abs(L_ns - L_clks * t_clk_ns) > 1e-6:
                        raise ValueError(
                            f"Integration weight length {L_ns} ns is not an integer "
                            f"multiple of clk time {t_clk_ns} ns (L_clks={L_clks})."
                        )
                    if L_clks % 4 != 0:
                        raise ValueError(
                            f"Integration weight length {L_ns} ns â†’ {L_clks} clocks, "
                            f"which is not a multiple of 4."
                        )

                    cos_name  = f"{prefix}rect_cos_{L_ns}"
                    sin_name  = f"{prefix}rect_sin_{L_ns}"
                    msin_name = f"{prefix}rect_msin_{L_ns}"

                    self.pulseOpMngr.add_int_weight(cos_name,   1.0,  0.0, L_ns, persist=False)
                    self.pulseOpMngr.add_int_weight(sin_name,   0.0,  1.0, L_ns, persist=False)
                    self.pulseOpMngr.add_int_weight(msin_name,  0.0, -1.0, L_ns, persist=False)

                    for lab, iw in (
                        ("cos",       cos_name),
                        ("sin",       sin_name),
                        ("m_sin",     msin_name),
                        ("minus_sin", msin_name),  # alias
                    ):
                        self.pulseOpMngr.append_integration_weight_mapping(
                            pulse, lab, iw, override=True
                        )

                # ------------------------ ringdown: Hz â†’ ns ------------------------
                if ringdown_len is None:
                    kappa_hz = float(attr.ro_kappa)
                    if kappa_hz <= 0:
                        raise ValueError("attributes.ro_kappa must be > 0 (Hz).")
                    ringdown_ns_raw = 1e9 / kappa_hz  # Ï„ = 1/kappa, in ns
                else:
                    ringdown_ns_raw = float(ringdown_len)

                # Snap ringdown to a multiple-of-4 clocks as well
                ringdown_clks = int(np.ceil((ringdown_ns_raw / t_clk_ns) / 4.0) * 4)
                ringdown_ns   = int(ringdown_clks * t_clk_ns)

                # ------------------------ sweep grids (ns + clks) ------------------------
                ro_gains = np.arange(min_g, max_g + 1e-12, dg, dtype=float)

                # Drive-on part sweep (no ringdown here)
                body_lens_ns, body_lens_clks = _make_aligned_range_ns_and_clks(
                    min_len, max_len, dlen,
                    mult_clks=4,
                )

                # Total measurement length = drive-on + ringdown
                total_lens_clks = body_lens_clks + ringdown_clks
                total_lens_ns   = (total_lens_clks * t_clk_ns).astype(int)

                ro_pulses = [f"readout_{L_ns}_pulse" for L_ns in body_lens_ns]
                ro_ops    = [f"readout_{L_ns}"       for L_ns in body_lens_ns]

                fidelity_matrix = np.zeros((len(ro_gains), len(body_lens_ns)))
                QND_matrix      = np.zeros((len(ro_gains), len(body_lens_ns)))

                # Map state_id -> prep_kwargs (required by new butterfly API)
                prep_kwargs_map: dict[str, dict] = {}

                # ------------------------ 1) register per-length pulses ------------------------
                for L_body_ns, L_body_clks, L_tot_ns, L_tot_clks, ro_pulse, ro_op in zip(
                    body_lens_ns, body_lens_clks, total_lens_ns, total_lens_clks, ro_pulses, ro_ops
                ):
                    # sanity: QM constraints
                    L_body_ns = int(L_body_ns)
                    L_tot_ns  = int(L_tot_ns)

                    calc_body_clks = int(round(L_body_ns / t_clk_ns))
                    if calc_body_clks != int(L_body_clks):
                        raise ValueError(
                            f"Inconsistent clock conversion for drive length {L_body_ns} ns: "
                            f"L_body_clks={L_body_clks}, L_body_ns/t_clk={calc_body_clks}."
                        )
                    if int(L_body_clks) % 4 != 0:
                        raise ValueError(
                            f"Drive length {L_body_ns} ns â†’ {L_body_clks} clocks, not a multiple of 4."
                        )
                    if int(L_tot_clks) % 4 != 0:
                        raise ValueError(
                            f"Total length {L_tot_ns} ns â†’ {L_tot_clks} clocks, not a multiple of 4."
                        )

                    # Build waveform: drive-on then ringdown=0
                    I_wf = np.zeros(L_tot_ns, dtype=float)
                    I_wf[:L_body_ns] = float(base_voltage)

                    pulseOp = PulseOp(
                        element=attr.ro_el,
                        op=ro_op,
                        pulse=ro_pulse,
                        type="measurement",
                        length=L_tot_ns,                        # total ns = drive + ringdown
                        I_wf_name=f"readout_I_wf_{L_body_ns}",
                        Q_wf_name=f"readout_Q_wf_{L_body_ns}",
                        I_wf=I_wf.tolist(),
                        Q_wf=0.0,
                    )
                    self.pulseOpMngr.register_pulse_op(pulseOp, override=True, persist=False)

                    # Integration weights: also full length (drive + ringdown)
                    _ensure_base_rect_weights(pulseOp.pulse, L_tot_ns)

                # Push everything (including the newly defined weights) to the QM
                self.quaProgMngr.burn_pulse_to_qm(self.pulseOpMngr, include_volatile=True)

                # ------------------------ kwargs normalization ------------------------
                ge_disc_kwargs = dict(ge_disc_kwargs or {})
                butterfly_kwargs = dict(butterfly_kwargs or {})

                # Extract blob-scaling params from ge_disc_kwargs (NOT passed into readout_ge_discrimination)
                k_g = float(ge_disc_kwargs.pop("k_g", 3.0))
                k_e = float(ge_disc_kwargs.pop("k_e", 3.0))

                # Butterfly now uses n_samples; accept legacy alias n_shots
                if "n_shots" in butterfly_kwargs and "n_samples" not in butterfly_kwargs:
                    butterfly_kwargs["n_samples"] = int(butterfly_kwargs.pop("n_shots"))

                # Defaults for the two sub-experiments
                ge_disc_defaults = dict(
                    update_measureMacro=True,
                    burn_rot_weights=False,
                    persist=False,
                    n_samples=10_000,
                    base_weight_keys=("cos", "sin", "minus_sin"),
                    auto_update_postsel=False,  # We manually manage prep_kwargs for each length/gain combo
                    blob_k_g=k_g,
                    blob_k_e=k_e,
                )
                # Extract prep_policy for butterfly
                bfly_prep_policy = butterfly_kwargs.pop("prep_policy", "BLOBS")
                
                bfly_defaults = dict(
                    update_measureMacro=butterfly_kwargs.pop("update_measureMacro", False),
                    show_analysis=butterfly_kwargs.pop("show_analysis", False),
                    n_samples=int(butterfly_kwargs.pop("n_samples", 10_000)),
                    M0_MAX_TRIALS=int(butterfly_kwargs.pop("M0_MAX_TRIALS", 128)),
                    det_L_threshold=float(butterfly_kwargs.pop("det_L_threshold", 1e-8)),
                )
                # Any remaining butterfly_kwargs are ignored (or you can choose to error)
                # If you prefer strictness:
                # if butterfly_kwargs:
                #     raise TypeError(f"Unknown butterfly_kwargs keys: {tuple(butterfly_kwargs.keys())}")

                def _run_ge_disc(measure_op: str, gain_val: float) -> RunResult:
                    call_kwargs = {
                        **ge_disc_defaults,
                        **ge_disc_kwargs,          # allow override of the defaults
                        "measure_op": measure_op,
                        "drive_frequency": drive_frequency,
                        "r180": r180,
                        "gain": gain_val,
                    }
                    return self.readout_ge_discrimination(**call_kwargs)

                def _run_butterfly(prep_kwargs: dict) -> RunResult:
                    return self.readout_butterfly_measurement(
                        prep_policy=bfly_prep_policy,
                        prep_kwargs=prep_kwargs,
                        r180=r180,
                        update_measureMacro=bfly_defaults["update_measureMacro"],
                        show_analysis=bfly_defaults["show_analysis"],
                        n_samples=bfly_defaults["n_samples"],
                        M0_MAX_TRIALS=bfly_defaults["M0_MAX_TRIALS"],
                        det_L_threshold=bfly_defaults["det_L_threshold"],
                        use_stored_config=False,  # Always use explicit prep_kwargs in this sweep
                    )

                # ------------------------ 2) per-gain loop ------------------------
                for i, gain in enumerate(tqdm(ro_gains, desc="Sweeping readout gain", disable=False)):
                    mm.set_gain(float(gain))

                    # 2a) per-length discrimination + snapshot of measureMacro + compute prep_kwargs
                    for j, ro_op in enumerate(ro_ops):
                        rr_ge = _run_ge_disc(measure_op=ro_op, gain_val=float(gain))

                        state_id = f"amp_len_opt:g{i}_L{j}"
                        mm.push_settings(state_id)

                        # Build prep_kwargs using PostSelectionConfig helper
                        config = PostSelectionConfig.from_discrimination_results(
                            rr_ge.output, blob_k_g=k_g, blob_k_e=k_e
                        )
                        prep_kwargs_map[state_id] = config.kwargs

                    # Burn after discrimination pass (keeps your original behavior)
                    self.burn_pulses()

                    # 2b) per-length butterfly using stored states + stored prep_kwargs
                    for j, ro_op in enumerate(
                        tqdm(ro_ops, desc=f"Butterfly @ gain={gain:.3f}", leave=False, disable=False)
                    ):
                        state_id = f"amp_len_opt:g{i}_L{j}"
                        mm.retrieve_state(state_id)

                        rr_bfly = _run_butterfly(prep_kwargs=prep_kwargs_map[state_id])
                        F, Q = rr_bfly.output.extract("F", "Q")
                        fidelity_matrix[i, j] = float(F)
                        QND_matrix[i, j]      = float(Q)

                out = Output()
                out["ro_gains"]           = ro_gains
                out["amplitudes"]         = ro_gains * float(base_voltage)
                out["ro_body_lens_ns"]    = body_lens_ns          # drive-on part
                out["ro_total_lens_ns"]   = total_lens_ns         # drive + ringdown
                out["ro_body_lens_clks"]  = body_lens_clks
                out["ro_total_lens_clks"] = total_lens_clks

                # legacy-ish aliases (keep if your downstream code expects them)
                out["ro_lens_ns"]         = body_lens_ns
                out["ro_lens_clks"]       = body_lens_clks
                out["ro_lens"]            = body_lens_ns

                out["fidelity_matrix"]    = fidelity_matrix
                out["QND_matrix"]         = QND_matrix
                out["ringdown_ns"]        = ringdown_ns
                out["t_clk_ns"]           = t_clk_ns

                return out

        finally:
            try:
                mm.retrieve_state(base_state_id)
            except Exception as exc:
                _logger.warning(
                    "readout_amp_len_opt: failed to restore base measureMacro state %r: %s",
                    base_state_id,
                    exc,
                )

    def readout_frequency_optimization(self, rf_begin, rf_end, df, ro_op=None, r180="x180", n_runs=1000) -> RunResult:
        attr = self.attributes
        ro_fq_list = np.arange(rf_begin, rf_end + 1e-12, df, dtype=float)
        fidelity_list = np.zeros(len(ro_fq_list), dtype=float)

        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        iq_blob_prog = cQED_programs.iq_blobs(
            attr.ro_el, attr.qb_el, r180, attr.qb_therm_clks, n_runs
        )

        qubox_logger = logging.getLogger("qubox")
        qm_logger    = logging.getLogger("qm")

        with temporarily_set_levels([qubox_logger, qm_logger], logging.WARNING):
            for i, ro_fq in enumerate(
                tqdm(ro_fq_list, desc="Scanning readout freq", unit="pt")
            ):
                self.quaProgMngr.set_element_fq(attr.ro_el, ro_fq)
                blob_res = self.quaProgMngr.run_program(
                    iq_blob_prog,
                    n_total=n_runs,
                    processors=[pp.proc_default],
                    process_in_sim=False,
                    targets=[("Ig", "Qg", "g"), ("Ie", "Qe", "e")],
                )
                S_g, S_e = blob_res.output.extract("S_g", "S_e")
                disc_out = two_state_discriminator(S_g, S_e, b_plot=False)
                fidelity = disc_out.extract("fidelity")
                fidelity_list[i] = fidelity
        out = Output()
        runres = RunResult(ExecMode.HARDWARE, out)
        runres.output["frequencies"] = ro_fq_list
        runres.output["fidelities"] = fidelity_list
        return runres

    def drag_calibration_YALE(self, amps, base_alpha: float, n_avg: int) -> RunResult:
        """
        Create TEMP (volatile) DRAG pulses that include `base_alpha` in the Q channel,
        register them via register_pulse (no disk writes), and run the DRAG sweep program.
        The QUA program should scale the derivative channel with alpha via amp(..., v11=alpha),
        so alpha = base_alpha * amps.
        """
        attr  = self.attributes
        rlen  = attr.rlen
        sigma = attr.rsigma
        anh   = attr.anharmonicity
        r180_amp = attr.r180_amp
        r90_amp  = 0.5 * r180_amp

        # --- build DRAG waveforms with base DRAG already baked in ---
        ga_r180, dr_r180 = drag_gaussian_pulse_waveforms(r180_amp, rlen, sigma, base_alpha, anh)
        ga_r90,  dr_r90  = drag_gaussian_pulse_waveforms(r90_amp,  rlen, sigma, base_alpha, anh)

        # Build complex waveforms and apply rotation (same convention as generate_rotations)
        z_r180 = np.array(ga_r180) + 1j * np.array(dr_r180)
        z_r90  = np.array(ga_r90)  + 1j * np.array(dr_r90)
        
        # Rotation by pi_val/2 to generate Y pulses from X pulses
        pi_rot = np.exp(1j * np.pi / 2)
        z_y180 = z_r180 * pi_rot
        z_y90  = z_r90  * pi_rot

        # --- register TEMP pulses (VOLATILE) via register_pulse ---
        # Note: pass I_wf/Q_wf data so register_pulse will create/overwrite the waveforms.
        p_x180 = PulseOp(
            element=attr.qb_el,
            op="x180_tmp",
            pulse="x180_tmp_pulse",
            type="control",
            length=rlen,
            I_wf_name="gauss_r180_tmp_wf",
            Q_wf_name="drag_r180_tmp_wf",
            I_wf=z_r180.real,
            Q_wf=z_r180.imag,
        )
        p_y180 = PulseOp(
            element=attr.qb_el,
            op="y180_tmp",
            pulse="y180_tmp_pulse",
            type="control",
            length=rlen,
            I_wf_name="y180_tmp_I_wf",
            Q_wf_name="y180_tmp_Q_wf",
            I_wf=z_y180.real,
            Q_wf=z_y180.imag,
        )
        p_x90 = PulseOp(
            element=attr.qb_el,
            op="x90_tmp",
            pulse="x90_tmp_pulse",
            type="control",
            length=rlen,
            I_wf_name="gauss_r90_tmp_wf",
            Q_wf_name="drag_r90_tmp_wf",
            I_wf=z_r90.real,
            Q_wf=z_r90.imag,
        )
        p_y90 = PulseOp(
            element=attr.qb_el,
            op="y90_tmp",
            pulse="y90_tmp_pulse",
            type="control",
            length=rlen,
            I_wf_name="y90_tmp_I_wf",
            Q_wf_name="y90_tmp_Q_wf",
            I_wf=z_y90.real,
            Q_wf=z_y90.imag,
        )

        # volatile, no save/burn; override in the volatile store if they already exist
        for p in (p_x180, p_y180, p_x90, p_y90):
            self.register_pulse(p, override=True, persist=False, save=False, burn=False)

        self.burn_pulses()
        # --- build QUA program using TEMP ops ---
        qb_el    = attr.qb_el
        qb_therm = attr.qb_therm_clks
        drag_prog = cQED_programs.drag_calibration_YALE(
            qb_el,
            amps,                 # alpha multipliers
            "x180_tmp", "x90_tmp",
            "y180_tmp", "y90_tmp",
            qb_therm, n_avg
        )

        # --- frequencies + run ---
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        runres = self.quaProgMngr.run_program(
            drag_prog,
            n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("amps", amps),
                pp.proc_attach("base_alpha", float(base_alpha)),
                pp.proc_attach("pulse_len", int(rlen)),
            ],
            process_in_sim=False,
            targets=[("I1", "Q1"), ("I2", "Q2")]
        )
        return runres

    def resonator_spectroscopy_x180(self, rf_begin, rf_end, df, r180="x180", n_avg: int = 1000) -> RunResult:
        attr = self.attributes

        lo_freq  = self.quaProgMngr.get_element_lo(attr.ro_el)
        if_freqs = create_if_frequencies(attr.ro_el, rf_begin, rf_end, df, lo_freq)


        # Build the QUA program (assumes calibrated "x180" in config)
        prog = cQED_programs.resonator_spectroscopy_x180(
            attr.qb_el, if_freqs, r180, attr.qb_therm_clks, n_avg
        )

        # Ensure elements are at the right IFs before running
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        # Attach absolute probe frequencies for convenience in post-proc
        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=[pp.proc_default, pp.proc_attach("frequencies", lo_freq + if_freqs)],
            process_in_sim=False,
        )

        self.save_output(runres.output, "resonatorSpectroscopy_x180")
        return runres

    def storage_spectroscopy(self, disp, rf_begin, rf_end, df, storage_therm_time, sel_r180="sel_x180" , n_avg=1000) -> RunResult:
        attr    = self.attributes
        lo_freq = self.quaProgMngr.get_element_lo(attr.st_el)
        if_freqs = create_if_frequencies(attr.st_el, rf_begin, rf_end, df, lo_freq=lo_freq)

        storage_spec_prog = cQED_programs.storage_spectroscopy(
            attr.qb_el, attr.st_el, disp, sel_r180, if_freqs, storage_therm_time, n_avg
        )

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        runres = self.quaProgMngr.run_program(
            storage_spec_prog,
            n_total=n_avg,
            processors=[pp.proc_default, pp.proc_attach("frequencies", lo_freq + if_freqs)],
            process_in_sim=False,
        )
        return runres

    def storage_spectroscopy_coarse(self, rf_begin: float, rf_end: float, df: float,
                                    storage_therm_time: int, n_avg: int = 1000) -> RunResult:
        attr    = self.attributes
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)

        lo_list = _make_lo_segments(rf_begin, rf_end)
        seg_results: list[RunResult] = []
        all_freqs = []

        for LO in lo_list:
            self.quaProgMngr.set_element_lo(attr.st_el, LO)
            if_freqs = _if_frequencies_for_segment(LO, rf_end, df)

            prog = cQED_programs.storage_spectroscopy(
                attr.ro_el, attr.qb_el, attr.st_el, if_freqs, storage_therm_time, n_avg
            )

            rr = self.quaProgMngr.run_program(
                prog,
                n_total=n_avg,
                processors=[pp.proc_default, pp.proc_attach("frequencies", LO + if_freqs)],
                process_in_sim=False,

            )
            seg_results.append(rr)
            all_freqs.append(LO + if_freqs)

        final_output = _merge_segments([r.output for r in seg_results], all_freqs)
        merged_mode  = seg_results[0].mode if seg_results else ExecMode.SIMULATE
        final_runres = RunResult(mode=merged_mode, output=final_output, sim_samples=None,
                                metadata={"segments": len(seg_results)})

        self.save_output(final_output, "storageWideSpectroscopy")
        return final_runres

    def num_splitting_spectroscopy(self, rf_centers, rf_spans, df,
                                disp_pulses="const_alpha", sel_r180="sel_x180", state_prep=None,
                                n_avg: int = 1000) -> RunResult:
        if not isinstance(rf_centers, (list, tuple, np.ndarray)):
            rf_centers = [rf_centers]
        if not isinstance(rf_spans, (list, tuple, np.ndarray)):
            rf_spans = [rf_spans]
        if not isinstance(disp_pulses, (list, tuple, np.ndarray)):
            disp_pulses = [disp_pulses]
        if len(rf_centers) != len(rf_spans):
            raise ValueError("rf_centers and rf_spans must have the same length")
        if len(rf_centers) != len(disp_pulses):
            raise ValueError("rf_centers and disp_pulse must have the same length")

        attr = self.attributes
        qb_lo_frequency = self.quaProgMngr.get_element_lo(attr.qb_el)

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.st_el, attr.st_fq)
        
        seg_results: list[RunResult] = []
        for rf_center, rf_span, disp_pulse in zip(rf_centers, rf_spans, disp_pulses):
            if not state_prep:
                def state_prep():
                    qua.play(disp_pulse, attr.st_el)
            
            self.quaProgMngr.set_element_fq(attr.qb_el, rf_center)
            rf_begin, rf_end = rf_center - rf_span / 2, rf_center + rf_span / 2
            qb_ifs = create_if_frequencies(attr.qb_el, rf_begin, rf_end, df,
                                        lo_freq=self.quaProgMngr.get_element_lo(attr.qb_el))

            num_split_spec_prog = cQED_programs.num_splitting_spectroscopy(
                state_prep, attr.qb_el, attr.st_el, 
                sel_r180, qb_ifs, attr.st_therm_clks, n_avg
            )

            rr = self.quaProgMngr.run_program(
                num_split_spec_prog,
                n_total=n_avg,
                processors=[pp.proc_default, pp.proc_attach("frequencies", qb_ifs + qb_lo_frequency)],
                process_in_sim=False,
            )
            seg_results.append(rr)

        final_output = Output.merge([r.output for r in seg_results])
        final_runres = RunResult(mode=seg_results[0].mode if seg_results else ExecMode.SIMULATE,
                                output=final_output, sim_samples=None,
                                metadata={"sweeps": len(seg_results)})
        self.save_output(final_output, "numSplitSpecSpectroscopy")
        return final_runres


    def fock_resolved_spectroscopy3(
        self,
        probe_fqs,
        *,
        state_prep,
        sel_r180: str = "sel_x180",
        n_avg: int = 100,
        sel_r180_transfer_calibration: bool = False,
    ):
        """
        Uses program with shared M0, then M1_sel and M1_null.

        From SEL+NULL:
        Pe_g_sel  = <w0g*w1e_sel>/<w0g>
        Pe_g_null = <w0g*w1e_null>/<w0g>
        Delta_g   = Pe_g_sel - Pe_g_null

        Pg_e_sel  = <w0e*w1g_sel>/<w0e>
        Pg_e_null = <w0e*w1g_null>/<w0e>
        Delta_e   = Pg_e_sel - Pg_e_null

        Then:
        P(n|g) â‰ˆ Delta_g / s_g
        P(n|e) â‰ˆ Delta_e / s_e
        where s_g,s_e come from optional CAL (single-point) as constants.

        Joint pops:
        Pg_n = Pg0 * P(n|g)
        Pe_n = Pe0 * P(n|e)
        """

        attr = self.attributes
        qb_lo_frequency = self.quaProgMngr.get_element_lo(attr.qb_el)

        fock_ifs = self.quaProgMngr.calculate_el_if_fq(
            attr.qb_el, probe_fqs, lo_freq=qb_lo_frequency
        )

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)
        self.quaProgMngr.set_element_fq(attr.st_el, attr.st_fq)

        qb_if = self.quaProgMngr.calculate_el_if_fq(
            attr.qb_el, attr.qb_fq, lo_freq=qb_lo_frequency
        )

        qb_therm_clks = getattr(attr, "qb_therm_clks", None)
        if qb_therm_clks is None:
            qb_therm_clks = getattr(attr, "st_therm_clks", 0)

        # Program now produces: I0/Q0, I_sel/Q_sel, I_null/Q_null (+ optional cal)
        prog = cQED_programs.fock_resolved_spectroscopy(
            attr.qb_el,
            state_prep,
            qb_if,
            fock_ifs,
            sel_r180,
            attr.st_therm_clks,
            n_avg,
            sel_r180_transfer_calibration=sel_r180_transfer_calibration,
            qb_therm_clks=qb_therm_clks,
        )

        def _plain(a):
            if a is None:
                return None
            arr = np.asarray(a)
            if arr.dtype.fields is not None:
                if "value" in arr.dtype.fields:
                    arr = arr["value"]
                else:
                    arr = arr[next(iter(arr.dtype.fields.keys()))]
            return np.asarray(arr)

        def _as_complex_from_IQ(out: "Output", I_key: str, Q_key: str):
            I = _plain(out.get(I_key))
            Q = _plain(out.get(Q_key))
            if I is None or Q is None:
                return None
            I = np.asarray(I)
            Q = np.asarray(Q)
            if I.shape != Q.shape:
                return None
            return I + 1j * Q

        def _safe_weight(S, *, target_state: str):
            w = measureMacro.compute_posterior_state_weight(S, target_state=target_state)
            w = _plain(w)
            return np.asarray(w, dtype=float)

        def _weighted_conditional(num_w, den_w, eps: float = 1e-12):
            den = np.nanmean(den_w, axis=0)
            num = np.nanmean(num_w, axis=0)
            return num / np.maximum(den, eps)

        def _compute_pg_pe_n(out: "Output", **_):
            # ----------------------------
            # Read SIGNAL+NULL streams (shots, L)
            # ----------------------------
            S0 = _as_complex_from_IQ(out, "I0", "Q0")
            S1_sel = _as_complex_from_IQ(out, "I_sel", "Q_sel")
            S1_null = _as_complex_from_IQ(out, "I_null", "Q_null")

            if S0 is None or S1_sel is None or S1_null is None:
                _logger.warning("Missing one or more IQ streams (I0/Q0, I_sel/Q_sel, I_null/Q_null)")
                return out

            S0 = np.asarray(S0)
            S1_sel = np.asarray(S1_sel)
            S1_null = np.asarray(S1_null)

            if S0.ndim != 2 or S1_sel.ndim != 2 or S1_null.ndim != 2:
                _logger.warning(f"Expected 2D arrays: S0 {S0.shape}, S1_sel {S1_sel.shape}, S1_null {S1_null.shape}")
                return out
            if S0.shape != S1_sel.shape or S0.shape != S1_null.shape:
                _logger.warning(f"Shape mismatch: S0 {S0.shape}, S1_sel {S1_sel.shape}, S1_null {S1_null.shape}")
                return out

            n_shots, L = S0.shape

            # ----------------------------
            # Posteriors
            # ----------------------------
            w0g = _safe_weight(S0, target_state="g")
            w0e = 1.0 - w0g

            w1e_sel = _safe_weight(S1_sel, target_state="e")
            w1g_sel = 1.0 - w1e_sel

            w1e_null = _safe_weight(S1_null, target_state="e")
            w1g_null = 1.0 - w1e_null

            # Qubit marginals at M0
            Pg = np.clip(np.nanmean(w0g, axis=0), 0.0, 1.0)
            Pe = 1.0 - Pg

            # Conditionals: SEL
            Pe_g_sel = _weighted_conditional(w0g * w1e_sel, w0g)
            Pg_e_sel = _weighted_conditional(w0e * w1g_sel, w0e)

            # Conditionals: NULL
            Pe_g_null = _weighted_conditional(w0g * w1e_null, w0g)
            Pg_e_null = _weighted_conditional(w0e * w1g_null, w0e)

            # Baseline-canceled deltas
            Delta_g = Pe_g_sel - Pe_g_null
            Delta_e = Pg_e_sel - Pg_e_null

            out["Pg0"] = Pg
            out["Pe0"] = Pe

            out["Pe_given_g_sel"] = Pe_g_sel
            out["Pg_given_e_sel"] = Pg_e_sel
            out["Pe_given_g_null"] = Pe_g_null
            out["Pg_given_e_null"] = Pg_e_null
            out["Delta_g"] = Delta_g
            out["Delta_e"] = Delta_e

            # ----------------------------
            # Optional CAL scale factors (single-point)
            # ----------------------------
            if sel_r180_transfer_calibration:
                S1_cal = _as_complex_from_IQ(out, "I_cal", "Q_cal")
                if S1_cal is None:
                    _logger.warning("sel_r180_transfer_calibration=True but missing I_cal/Q_cal")
                    return out
                S1_cal = np.asarray(S1_cal)
                if S1_cal.ndim != 2 or S1_cal.shape[0] != n_shots or S1_cal.shape[1] != 2:
                    _logger.warning(f"Expected S1_cal shape (shots,2); got {S1_cal.shape}")
                    return out

                S1_cal_g = S1_cal[:, 0]  # g-prep
                S1_cal_e = S1_cal[:, 1]  # e-prep

                # compute_posterior_state_weight expects 2D; reshape to (shots,1)
                w_cal_e_from_g = _safe_weight(S1_cal_g.reshape(-1, 1), target_state="e").reshape(-1)
                w_cal_e_from_e = _safe_weight(S1_cal_e.reshape(-1, 1), target_state="e").reshape(-1)

                # These are "contrast-like" scalars; we apply them to DELTAs
                s_g = float(np.clip(np.nanmean(w_cal_e_from_g), 0.0, 1.0))               # P(e|g) after pulse
                s_e = float(np.clip(np.nanmean(1.0 - w_cal_e_from_e), 0.0, 1.0))         # P(g|e) after pulse

                eps = 1e-12
                Pn_given_g = Delta_g / np.maximum(s_g, eps)
                Pn_given_e = Delta_e / np.maximum(s_e, eps)
            else:
                # No scale => return delta-based proxies
                Pn_given_g = Delta_g
                Pn_given_e = Delta_e
                s_g = None
                s_e = None

            Pn_given_g = np.clip(Pn_given_g, 0.0, 1.0)
            Pn_given_e = np.clip(Pn_given_e, 0.0, 1.0)

            Pg_n = np.clip(Pg * Pn_given_g, 0.0, 1.0)
            Pe_n = np.clip(Pe * Pn_given_e, 0.0, 1.0)

            out["Pn_given_g"] = Pn_given_g
            out["Pn_given_e"] = Pn_given_e
            out["Pg_n"] = Pg_n
            out["Pe_n"] = Pe_n
            out["Pflip"] = np.clip(Pg_n + Pe_n, 0.0, 1.0)
            out["Delta"] = np.clip(Pg_n - Pe_n, -1.0, 1.0)

            if s_g is not None:
                out["s_g_cal"] = s_g
                out["s_e_cal"] = s_e

            # debug weights
            out["w0g"] = w0g
            out["w1e_sel"] = w1e_sel
            out["w1e_null"] = w1e_null

            return out

        # -----------------------------
        # Targets to fetch (match new program keys)
        # -----------------------------
        targets_list = [
            ("I0", "Q0"),
            ("I_sel", "Q_sel"),
            ("I_null", "Q_null"),
        ]
        if sel_r180_transfer_calibration:
            targets_list += [
                ("I_cal", "Q_cal"),
                # optionally for debugging:
                # ("I0_cal", "Q0_cal"),
            ]

        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=[
                pp.proc_attach("probe_fqs", probe_fqs),
                _compute_pg_pe_n,
            ],
            process_in_sim=False,
            targets=targets_list,
        )

        return runres





    def fock_resolved_spectroscopy(
        self,
        probe_fqs,
        *,
        state_prep,
        sel_r180="sel_x180",
        calibrate_ref_r180_S = True,
        n_avg: int = 100,
    ):
        attr = self.attributes

        # --- figure out IFs for each probe line and the bare qubit IF ---
        qb_lo_frequency = self.quaProgMngr.get_element_lo(attr.qb_el)

        fock_ifs = self.quaProgMngr.calculate_el_if_fq(
            attr.qb_el,
            probe_fqs,
            lo_freq=qb_lo_frequency,
        )

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)
        self.quaProgMngr.set_element_fq(attr.st_el, attr.st_fq)

        qb_if = self.quaProgMngr.calculate_el_if_fq(
            attr.qb_el,
            attr.qb_fq,
            lo_freq=qb_lo_frequency,
        )

        # --- build the actual QUA program ---
        prog = cQED_programs.fock_resolved_spectroscopy(
            attr.qb_el,           # qb_el
            state_prep,           # state_prep callable
            qb_if,
            fock_ifs,             # fock_ifs array[int]
            sel_r180,             # selective pi_val
            calibrate_ref_r180_S,
            attr.qb_therm_clks,
            attr.st_therm_clks,   # st_therm_clks
            n_avg,                # n_avg
        )

        # --- post-processor for double post-selection analysis ---
        def _compute_post_selected_data(out: Output, **_):
            """
            Double post-selected analysis for Fock-resolved spectroscopy.

            Notes:
            - Using BLOBS exclusive "core" post-selection means rates are *core* rates.
            - We compute:
                Pg_n_joint_core = P(M0 in g-core AND M1 in e-core)
                and (optionally) a corrected estimate:
                Pg_n_joint_corr â‰ˆ Pg_n_joint_core / (eta_g * eta_e)
                where eta_g/eta_e come from measureMacro._ro_quality_params (butterfly-derived).
            """
            S_0 = out.get("S_0")  # complex, shape [shots, n_probe]
            S   = out.get("S")    # complex, shape [shots, n_probe]

            if S_0 is None or S is None:
                _logger.warning("S_0 or S not found in output; skipping post-selection analysis")
                return out

            post_sel_config = measureMacro.get_post_select_config()
            if post_sel_config is None:
                _logger.warning("No post-selection config in measureMacro; skipping post-selection analysis")
                return out

            S_0 = np.asarray(S_0)
            S   = np.asarray(S)

            if S_0.ndim != 2 or S.ndim != 2:
                _logger.warning(f"Expected 2D arrays for S_0 and S; got shapes {S_0.shape} and {S.shape}")
                return out

            n_shots, n_probe = S.shape
            if S_0.shape != S.shape:
                _logger.warning(f"S_0 and S shape mismatch: {S_0.shape} vs {S.shape}")
                return out

            # ---------------- First post-selection (M0): g-core ----------------
            mask2ds_g0 = post_sel_config.post_select_mask(S_0, target_state="g")
            mask2ds_g0 = np.asarray(mask2ds_g0, dtype=bool)

            S_accepted_shots = [S[:, j][mask2ds_g0[:, j]] for j in range(n_probe)]

            nan_c = np.nan + 1j * np.nan
            Sg_n_cplx = np.array(
                [np.mean(col) if len(col) > 0 else nan_c for col in S_accepted_shots],
                dtype=np.complex128
            )

            acceptance_rate_g_core = np.array(
                [np.mean(mask2ds_g0[:, j]) if n_shots > 0 else np.nan for j in range(n_probe)],
                dtype=float
            )

            # ---------------- Second post-selection (M1): e-core within accepted ----------------
            mask2ds_S_e = post_sel_config.post_select_mask(S_accepted_shots, target_state="e")

            S_post_selected_e = [
                S_accepted_shots[j][np.asarray(mask2ds_S_e[j], dtype=bool)]
                for j in range(n_probe)
            ]

            S_post_selected_e_mean_cplx = np.array(
                [np.mean(col) if len(col) > 0 else nan_c for col in S_post_selected_e],
                dtype=np.complex128
            )

            acceptance_rate_e_core = np.array(
                [len(S_post_selected_e[j]) / len(S_accepted_shots[j]) if len(S_accepted_shots[j]) > 0 else np.nan
                for j in range(n_probe)],
                dtype=float
            )

            # ---------------- Core joint probability ----------------
            Pe_n_counts = np.array([len(col) for col in S_post_selected_e], dtype=int)
            Pg_n_joint_core = Pe_n_counts / float(n_shots) if n_shots > 0 else np.full(n_probe, np.nan)

            Pg_n_joint_from_rates = acceptance_rate_g_core * acceptance_rate_e_core
            Pn_given_g_core = acceptance_rate_e_core.copy()

            # ---------------- Correction using eta from readout quality cache ----------------
            ro_q = getattr(measureMacro, "_ro_quality_params", {}) or {}
            eta_g = ro_q.get("eta_g", None)
            eta_e = ro_q.get("eta_e", None)

            Pg_n_joint_corr = Pg_n_joint_core.copy()
            corr_ok = False

            try:
                eta_g = float(eta_g) if eta_g is not None else np.nan
                eta_e = float(eta_e) if eta_e is not None else np.nan
                scale = eta_g * eta_e
                if np.isfinite(scale) and (scale > 0):
                    Pg_n_joint_corr = Pg_n_joint_core / scale
                    # physically it cannot be negative; clip high end loosely (<=1 is safe)
                    Pg_n_joint_corr = np.clip(Pg_n_joint_corr, 0.0, 1.0)
                    corr_ok = True
            except Exception:
                corr_ok = False

            # ---------------- Store results ----------------
            # Keep complex means (and legacy real projections)

            out["Sg_n"] = Sg_n_cplx
        

            out["S_accepted_shots"] = S_accepted_shots
            #out["S_post_selected_e"] = S_post_selected_e
            #out["S_post_selected_e_mean_cplx"] = S_post_selected_e_mean_cplx
            #out["S_post_selected_e_mean"] = np.real(S_post_selected_e_mean_cplx)

           # out["acceptance_rate_g"] = acceptance_rate_g_core
            #out["acceptance_rate_e"] = acceptance_rate_e_core
            #out["Pe_n_counts"] = Pe_n_counts

            # Core joint (what you directly measured)
            #out["Pg_n_joint_core"] = Pg_n_joint_core

            # Corrected joint estimate (recommended for epsilon extraction)
           # out["Pg_n_joint_corr"] = Pg_n_joint_corr
            #out["Pg_n_joint_corr_ok"] = bool(corr_ok)
            #out["eta_g_used"] = eta_g
            #out["eta_e_used"] = eta_e

            # Backward compat: keep Pg_n_joint as the corrected one OR keep core â€” choose one.
            # I recommend NOT overwriting old semantics; keep both explicitly.
            #out["Pg_n_joint"] = Pg_n_joint_core  # preserve old meaning

            #out["Pn_given_g"] = Pn_given_g_core

            #out["Pg_n_joint_from_rates"] = Pg_n_joint_from_rates
            #out["Pg_n_joint_diff"] = Pg_n_joint_core - Pg_n_joint_from_rates
        
            if calibrate_ref_r180_S:
                ref_r180_I, ref_r180_Q = out.extract("sel_r180_ref_I", "sel_r180_ref_Q")
                ref_S = ref_r180_I + 1j*ref_r180_Q
                out["ref_sel_r180_S"] = ref_S
                out["Pg_n_joint_from_S"] = measureMacro.compute_Pe_from_S(Sg_n_cplx)/measureMacro.compute_Pe_from_S(ref_S)
            return out
        
        # --- run on hardware / simulator ---
        # Only include sel_r180_ref targets if calibration is enabled
        targets_list = [("I0", "Q0"), ("I", "Q")]
        
        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("probe_fqs", probe_fqs),
                _compute_post_selected_data,
            ],
            process_in_sim=False,
            targets=targets_list,
        )

        return runres
    
    def fock_resolved_power_rabi(self, fock_fqs, gains, sel_qb_pulse, disp_n_list, n_avg=1000):
        attr = self.attributes
        qb_lo_frequency = self.quaProgMngr.get_element_lo(attr.qb_el)
        
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)
        self.quaProgMngr.set_element_fq(attr.st_el, attr.st_fq)

        fock_ifs = self.quaProgMngr.calculate_el_if_fq(
            attr.qb_el,
            fock_fqs,
            lo_freq=qb_lo_frequency,
        )
        prog = cQED_programs.fock_resolved_power_rabi(attr.qb_el, attr.st_el, gains, disp_n_list, fock_ifs, sel_qb_pulse, attr.st_therm_clks, n_avg)

        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("probe_fqs", fock_fqs),
            ],
            process_in_sim=False,
        )

        return runres

    def fock_resolved_qb_ramsey(
        self,
        fock_fqs: Union[list[int], np.ndarray],
        detunings, 
        disps: list[str],
        delay_end: int,
        dt: int,
        delay_begin: int = 4,
        sel_r90: str = "sel_x90",
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attributes
        
        fock_ifs = self.quaProgMngr.calculate_el_if_fq(attr.qb_el, fock_fqs)
        if len(fock_ifs) != len(disps):
            raise ValueError(f"fock_ifs (len={len(fock_ifs)}) and disps (len={len(disps)}) must have the same length.")
            
        # Create timing array in clock cycles (1 clk = 4 ns)
        delay_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=4)
        
        # Ensure readout frequency is set
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.st_el, attr.st_fq)

        # Create and compile the QUA program
        prog = cQED_programs.fock_resolved_qb_ramsey(
            qb_el=attr.qb_el,
            st_el=attr.st_el,
            fock_ifs=fock_ifs,
            detunings=detunings,
            disps=disps,
            sel_r90=sel_r90,
            delay_clks=delay_clks,
            st_therm_clk=attr.st_therm_clks,
            n_avg=n_avg
        )
        
        # Run the program
        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("delays", delay_clks * 4), 
                pp.proc_attach("fock_ifs", fock_ifs),
                pp.proc_attach("disps", disps),
            ],
            process_in_sim=False,
        )
        
        self.save_output(runres.output, "fockResolvedRamsey")
        return runres
    
    def fock_resolved_T1_relaxation(self, fock_fqs, fock_disps, delay_end, dt, delay_begin=4, sel_r180="sel_x180", n_avg=1000) -> RunResult:
        attr = self.attributes
        
        # delays in *clks* (1 clk = 4 ns)
        delay_clks = create_clks_array(delay_begin, delay_end, dt, time_per_clk=4)
        delays_ns = delay_clks * 4

        qb_lo_frequency = self.quaProgMngr.get_element_lo(attr.qb_el)
        
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.st_el, attr.st_fq)

        fock_ifs = self.quaProgMngr.calculate_el_if_fq(
            attr.qb_el,
            fock_fqs,
            lo_freq=qb_lo_frequency,
        )

        prog = cQED_programs.fock_resolved_T1_relaxation(
            attr.qb_el, 
            attr.st_el, 
            fock_disps, 
            fock_ifs, 
            sel_r180, 
            delay_clks, 
            attr.st_therm_clks, 
            n_avg
        )

        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=[
                pp.proc_default, 
                pp.proc_attach("delays", delays_ns),
                pp.proc_attach("probe_fqs", fock_fqs)
            ],
            process_in_sim=False,
        )
        self.save_output(runres.output, "fock_resolved_T1")
        return runres


    def fock_resolved_state_tomography(
        self,
        fock_fqs,                        # iterable of int absolute frequencies (one per Fock manifold)
        state_prep,                      # callable or list of callables
        *,
        tag_off_idle_duration=None,
        sel_r180="sel_x180",             # selective pi_val (|g,n> <-> |e,n>)
        rxp90="x90",                   # global +pi_val/2 about x (maps Ïƒ_yâ†’Ïƒ_z)
        rym90="yn90",                   # global -pi_val/2 about y (maps Ïƒ_xâ†’Ïƒ_z)
        qb_if=None,                      # interaction/idle IF during state_prep; defaults to qb_fq
        n_avg: int = 1000,
    ):
        attr = self.attributes

        # Normalise to list to query length, but pass through as-is
        if callable(state_prep):
            _preps_list = [state_prep]
        else:
            _preps_list = list(state_prep)
        n_preps = len(_preps_list)

        # Ensure array of ints
        fock_ifs = self.quaProgMngr.calculate_el_if_fq(attr.qb_el, fock_fqs).astype(int)
        if fock_ifs.ndim != 1 or fock_ifs.size == 0:
            raise ValueError("fock_ifs must be a 1-D non-empty list/array of IFs (int).")

        # Program LO / element parking
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.st_el, attr.st_fq)

        # Default interaction IF (for state_prep)
        if qb_if is None:
            qb_if = self.quaProgMngr.calculate_el_if_fq(attr.qb_el, attr.qb_fq)
        else:
            qb_if = int(qb_if)

        if not tag_off_idle_duration:
            tag_off_idle_duration = self.pulseOpMngr.get_pulseOp_by_element_op("qubit", sel_r180).length
        tag_off_idle_clks = tag_off_idle_duration // 4

        # Build the QUA program
        prog = cQED_programs.fock_resolved_state_tomography(
            qb_el=attr.qb_el,
            state_prep=_preps_list if n_preps > 1 else _preps_list[0],
            qb_if=qb_if,
            fock_ifs=[int(x) for x in fock_ifs],
            sel_r180=sel_r180,
            rxp90=rxp90,
            rym90=rym90,
            st_therm_clks=attr.st_therm_clks,
            tag_off_idle_clks=tag_off_idle_clks,
            n_avg=n_avg,
        )
        def _ro_correct(out, **kw):
            out = pp.ro_state_correct_proc(
                out,
                targets=[
                    ("state_x_off", "sigma_x_off_corr"),
                    ("state_x_on",  "sigma_x_on_corr"),
                    ("state_y_off", "sigma_y_off_corr"),
                    ("state_y_on",  "sigma_y_on_corr"),
                    ("state_z_off", "sigma_z_off_corr"),
                    ("state_z_on",  "sigma_z_on_corr"),
                ],
                confusion=measureMacro._ro_quality_params.get("confusion_matrix"),
                to_sigmaz=True,
                **kw
            )

            sx_off, sx_on = out.extract("sigma_x_off_corr", "sigma_x_on_corr")
            sy_off, sy_on = out.extract("sigma_y_off_corr", "sigma_y_on_corr")
            sz_off, sz_on = out.extract("sigma_z_off_corr", "sigma_z_on_corr")

            out["sigma_x_n"] = ((sx_off - sx_on) / 2) 
            out["sigma_y_n"] = ((sy_off - sy_on) / 2) 
            out["sigma_z_n"] = ((sz_off - sz_on) / 2)
            
            out["delta_x"] = (sx_off - sx_on)
            out["delta_y"] = (sy_off - sy_on)
            out["delta_z"] = (sz_off - sz_on)
            return out
        
        processors = [pp.proc_default, pp.proc_attach("fock_fqs", fock_fqs), _ro_correct]
        if n_preps > 1:
            processors.append(pp.proc_attach("n_preps", n_preps))

        runres: RunResult = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=processors,
            process_in_sim=False,
        )

        return runres
    
    def iq_blob(self, r180, n_runs: int = 1000) -> RunResult:
        attr = self.attributes
        
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)

        iq_blob_prog = cQED_programs.iq_blobs(
            attr.ro_el, attr.qb_el, r180, attr.qb_therm_clks, n_runs
        )
        runres = self.quaProgMngr.run_program(
            iq_blob_prog,
            n_total=n_runs,
            processors=[pp.proc_default],
            process_in_sim=False, targets=[("Ig", "Qg", "g"), ("Ie", "Qe", "e")],
        )
        return runres


    def snap_optimization(self, snap_gate, disp1_gate, fock_probe_fqs, *,
                        sel_r180: str = "sel_x180",
                        sel_rxp90: str = "sel_x90",
                        sel_rym90: str = "sel_yn90",
                        n_avg: int = 100,
                        qb_x180: str = "x180",
                        post_meas_wait_clks: int = 0) -> RunResult:
        attr = self.attributes

        qb_lo_frequency = self.quaProgMngr.get_element_lo(attr.qb_el)
        fock_ifs = self.quaProgMngr.calculate_el_if_fq(attr.qb_el, fock_probe_fqs, lo_freq=qb_lo_frequency)
        qb_if    = self.quaProgMngr.calculate_el_if_fq(attr.qb_el, attr.qb_fq, lo_freq=qb_lo_frequency)

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)
        self.quaProgMngr.set_element_fq(attr.st_el, attr.st_fq)

        prog = cQED_programs.SQR_state_tomography(
            attr.ro_el, attr.st_el, attr.qb_el, snap_gate, disp1_gate,
            qb_if, fock_ifs, sel_r180, sel_rxp90, sel_rym90,
            attr.st_therm_clks, n_avg, qb_x180=qb_x180,
            post_meas_wait_clks=post_meas_wait_clks
        )

        def _expectations(out, **_):
            import numpy as np
            def _to_exp(arr_bool):
                a = np.asarray(arr_bool, dtype=float)
                return 2.0 * a.mean(axis=0) - 1.0 if a.ndim == 2 else 2.0 * a - 1.0
            for key, outkey in (("sz_n_i", "sz_i_exp"), ("sz_n_f", "sz_f_exp"),
                                ("sx_n", "sx_exp"), ("sy_n", "sy_exp")):
                if key in out:
                    out[outkey] = _to_exp(out[key])
            return out

        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=[pp.proc_default,
                        pp.proc_attach("probe_fqs", np.asarray(fock_probe_fqs)),
                        pp.proc_attach("probe_ifs", np.asarray(fock_ifs)),
                        _expectations],
            process_in_sim=False,
        )
        return runres
    
    def storage_phase_evolution(self, n, fock_probe_fqs, theta_np_array, snap_np_list,
                                delay_clks, max_n_drive=12,
                                disp_alpha=None, disp_epsilon=None,
                                sel_r180_pulse="sel_x180", n_avg=200) -> RunResult:
        def choose_displacements(n: int, alpha_cap: float = 6.0, eps_abs: float = 0.10):
            alpha_amp = min(np.sqrt(n + 0.5), alpha_cap)
            return alpha_amp, eps_abs

        alpha_amp, eps_amp = choose_displacements(n)
        if disp_alpha is None:
            disp_alpha = Displacement(alpha=alpha_amp, build=True)
            print(f"[info] |alpha| = {alpha_amp:.3f}")
        if disp_epsilon is None:
            disp_epsilon = Displacement(alpha=eps_amp, build=True)
            print(f"[info] |mu| = {eps_amp:.3f}")

        if not snap_np_list:
            snap_np_list = []
            for theta_np in theta_np_array:
                theta_np_vec = np.zeros(max_n_drive)
                theta_np_vec[n+1] = theta_np
                snap_np = SNAP(theta_np_vec, apply_corrections=False, build=True)
                snap_np_list.append(snap_np.name)

        attr = self.attributes
        self.quaProgMngr.burn_pulse_to_qm(self.pulseOpMngr)

        fock0_if       = self.quaProgMngr.calculate_el_if_fq(attr.qb_el, attr.qb_fq)
        fock_probe_ifs = self.quaProgMngr.calculate_el_if_fq(attr.qb_el, fock_probe_fqs)

        prog = cQED_programs.phase_evolution_prog(
            attr.ro_el, attr.qb_el, attr.st_el,
            disp_alpha.name, disp_epsilon.name, sel_r180_pulse,
            fock0_if, fock_probe_ifs,
            delay_clks, snap_np_list, attr.st_therm_clks, n_avg
        )

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)
        self.quaProgMngr.set_element_fq(attr.st_el, attr.st_fq)

        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=[pp.proc_default,
                        pp.proc_attach("delays", np.array(delay_clks) * 4),
                        pp.proc_attach("thetas", np.array(theta_np_array)),
                        pp.proc_attach("fock_probe_fqs", fock_probe_fqs),
                        pp.proc_attach("fock_n", n),
                        pp.proc_attach("max_n_drive", max_n_drive)],
            process_in_sim=False,
        )
        self.save_output(runres.output, "phaseEvolution")
        return runres

    def storage_wigner_tomography(self, gates: list[Gate], x_vals, p_vals,
                                base_alpha=10, r90_pulse="x90", n_avg=200) -> RunResult:
        attr = self.attributes
        base_disp = Displacement(base_alpha).build()

        self.quaProgMngr.burn_pulse_to_qm(self.pulseOpMngr)

        parity_wait_clks = np.pi / (abs(attr.st_chi)) * 1e9 / 4
        parity_wait_clks = 4 * round(parity_wait_clks / 4)

        prog = cQED_programs.storage_wigner_tomography(
            gates, attr.st_el, attr.qb_el, attr.ro_el, base_disp,
            x_vals, p_vals, base_alpha, r90_pulse, parity_wait_clks,
            attr.st_therm_clks, n_avg
        )

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)
        self.quaProgMngr.set_element_fq(attr.st_el, attr.st_fq)

        gate_names = [g.name for g in gates]
        runres = self.quaProgMngr.run_program(
            prog,
            n_total=n_avg,
            processors=[pp.proc_default,
                        pp.proc_attach("x_vals", x_vals),
                        pp.proc_attach("p_vals", p_vals),
                        pp.proc_attach("gates", gate_names)],
            process_in_sim=False
        )
        self.save_output(runres.output, "storageWignerTomography")
        return runres

    
    def storage_chi_ramsey(self, fock_fq, delay_ticks, disp_pulse: str = "const_alpha",
                        x90_pulse: str = "x90", n_avg: int = 200) -> RunResult:
        attr = self.attributes
        prog = cQED_programs.storage_chi_ramsey(
            attr.ro_el, attr.qb_el, attr.st_el, disp_pulse, x90_pulse,
            delay_ticks, attr.st_therm_clks, n_avg
        )

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, fock_fq)
        self.quaProgMngr.set_element_fq(attr.st_el, attr.st_fq)

        runres = self.quaProgMngr.run_program(
            prog, n_avg,
            processors=[pp.proc_default, pp.proc_attach("delay_ticks", np.array(delay_ticks))],
            process_in_sim=False,
        )
        self.save_output(runres.output, "storageChiRamsey")
        return runres
 
    def storage_ramsey(self, delay_ticks, st_detune=0, disp_pulse: str = "const_alpha",
                    sel_r180: str = "sel_x180", n_avg: int = 200) -> RunResult:
        attr = self.attributes
        prog = cQED_programs.storage_ramsey(
            attr.ro_el, attr.qb_el, attr.st_el, disp_pulse, sel_r180,
            delay_ticks, attr.st_therm_clks, n_avg
        )

        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)
        self.quaProgMngr.set_element_fq(attr.st_el, attr.st_fq + st_detune)

        runres = self.quaProgMngr.run_program(
            prog, n_avg,
            processors=[pp.proc_default,
                        pp.proc_attach("delay_ticks", np.array(delay_ticks)),
                        pp.proc_attach("st_detune", float(st_detune))],
            process_in_sim=False,
        )
        self.save_output(runres.output, "storageRamsey")
        return runres

    def SPA_flux_optimization2(
        self,
        dc_list,
        sample_fqs,
        n_avg: int,
        *,
        odc_name: str = "octodac_bf",
        odc_param: str = "voltage5",
        step: float = 0.005,
        delay_s: float = 0.1,
        use_absolute_ro_freqs: bool = True,
        ro_depl_clks: int | None = None,

        # -------- NEW knobs for non-Markov automation --------
        mode: str = "sweep",  # "sweep" | "auto_peak"
        objective: "PeakObjective | None" = None,

        # scout/refine/lock params
        scout_window: float = 0.20,
        scout_step: float = 0.01,
        refine_half_width: float = 0.03,
        refine_step: float = 0.002,
        peak_score_thresh: float = 8.0,

        lock_delta: float = 0.001,
        lock_gain: float = 0.75,
        lock_max_iters: int = 25,
        lock_min_delta: float = 1e-4,
        lock_loss_frac: float = 0.6,

        # standardize approach (highly recommended for hysteresis)
        approach_direction: str = "up",       # "up" or "down"
        approach_reset: float | None = None,  # if set, ramp here before evaluating any candidate
    ) -> "RunResult":

        attr = self.attributes
        qpm  = self.quaProgMngr

        if ro_depl_clks is None:
            ro_depl_clks = int(attr.ro_therm_clks or 0)

        if self.device_manager.get(odc_name) is None:
            raise RuntimeError(f"Device '{odc_name}' not found in device_manager.")

        # --- normalize frequency list (accept scalar or array) ---
        sample_fqs = np.atleast_1d(np.array(sample_fqs, dtype=float))
        if use_absolute_ro_freqs:
            sel_IFs = qpm.calculate_el_if_fq(attr.ro_el, sample_fqs, as_int=True)
            samp_meta = sample_fqs.copy()  # absolute Hz for output
        else:
            sel_IFs = qpm.calculate_el_if_fq(
                attr.ro_el,
                measureMacro._drive_frequency + sample_fqs,
                as_int=True
            )
            samp_meta = (measureMacro._drive_frequency + sample_fqs).astype(float)

        # Park RO at base frequency; QUA will call update_frequency() with IFs
        qpm.set_element_fq(attr.ro_el, measureMacro._drive_frequency)

        if objective is None:
            objective = PeakObjective(method="max")

        qubox_logger = logging.getLogger("qubox")
        qm_logger = logging.getLogger("qm")

        def _ramp_to(dc: float):
            self.device_manager.ramp(
                odc_name,
                odc_param,
                to=float(dc),
                step=float(step),
                delay_s=float(delay_s),
            )

        def _run_one_dc(dc: float):
            """
            EXACTLY your desired run_program format.
            Returns rr (RunResult), plus mag_1d (np.ndarray [n_freq]).
            """
            # 1) ramp hardware
            _ramp_to(dc)

            # 2) compile & run the one-DC program (kept EXACT)
            prog = cQED_programs.SPA_flux_optimization(sel_IFs, ro_depl_clks, n_avg)

            rr = qpm.run_program(
                prog,
                n_total=n_avg,
                processors=[
                    pp.proc_attach("sample_fqs_abs", samp_meta.copy()),
                    pp.proc_attach("sel_IFs", np.asarray(sel_IFs, dtype=int)),
                    pp.proc_attach("flux_dc", float(dc)),
                ],
                process_in_sim=False,
            )

            # Defensive: ensure I/Q present
            keys = rr.output.keys()
            if not all(k in keys for k in ("I", "Q")):
                raise KeyError(
                    f"Expected 'I'/'Q' in program output, got keys: {sorted(keys)}"
                )

            I = np.asarray(rr.output["I"])
            Q = np.asarray(rr.output["Q"])
            mag_1d = np.abs(I + 1j * Q)
            return rr, mag_1d

        def _standardize_before_eval(dc_target: float):
            """
            Enforce a consistent approach to reduce hysteresis:
            - optional reset
            - overshoot/approach from one side
            """
            if approach_reset is not None:
                _ramp_to(float(approach_reset))

            if approach_direction.lower() == "up":
                pre = float(dc_target) - 5.0 * float(lock_delta)
                _ramp_to(pre)
                _ramp_to(dc_target)
            elif approach_direction.lower() == "down":
                pre = float(dc_target) + 5.0 * float(lock_delta)
                _ramp_to(pre)
                _ramp_to(dc_target)
            else:
                raise ValueError("approach_direction must be 'up' or 'down'")

        # ==========================================================
        # MODE 1: original sweep (keeps your loop style)
        # ==========================================================
        if mode == "sweep":
            flux_dc_list = list(map(float, dc_list))
            seg_results: list["RunResult"] = []

            with temporarily_set_levels([qubox_logger, qm_logger], logging.WARNING):
                for dc in tqdm(flux_dc_list, desc="Sweeping flux bias", unit="pt", disable=False):
                    rr, _ = _run_one_dc(float(dc))
                    seg_results.append(rr)

            I_mat = np.stack([np.asarray(rr.output["I"]) for rr in seg_results], axis=1)
            Q_mat = np.stack([np.asarray(rr.output["Q"]) for rr in seg_results], axis=1)
            mag_matrix = np.abs(I_mat + 1j * Q_mat)

            out = Output()
            out["mag_matrix"] = mag_matrix
            out["sample_fqs_abs"] = samp_meta
            out["sel_IFs"] = np.asarray(sel_IFs, int)
            out["flux_dc_list"] = np.asarray(flux_dc_list, float)
            out["odc_name"] = odc_name
            out["odc_param"] = odc_param
            out["ramp_step"] = float(step)
            out["ramp_delay_s"] = float(delay_s)
            out["n_avg"] = int(n_avg)
            out["ro_depl_clks"] = int(ro_depl_clks)

            mode0 = seg_results[0].mode if seg_results else ExecMode.SIMULATE
            runres = RunResult(
                mode=mode0,
                output=out,
                sim_samples=None,
                metadata={"segments": len(seg_results), "mode": "sweep"},
            )
            self.save_output(out, "spaFluxOptimization")
            return runres

        # ==========================================================
        # MODE 2: auto_peak (scout -> refine -> lock), using the same
        #         _run_one_dc() primitive (thus same run_program format).
        # ==========================================================
        if mode != "auto_peak":
            raise ValueError(f"Unknown mode={mode!r}. Use 'sweep' or 'auto_peak'.")

        dc_arr = np.asarray(list(map(float, dc_list)), dtype=float)
        if dc_arr.size < 2:
            raise ValueError("mode='auto_peak' needs dc_list defining a range (>=2 values).")
        dc_start = float(np.min(dc_arr))
        dc_stop  = float(np.max(dc_arr))

        history = []
        locked_dc = None
        locked_S = None
        locked_mag_1d = None
        locked_rr = None

        def measure_S(dc: float) -> float:
            # critical: standardize approach BEFORE evaluation
            _standardize_before_eval(dc)
            rr, mag_1d = _run_one_dc(dc)
            return float(objective(mag_1d))

        with temporarily_set_levels([qubox_logger, qm_logger], logging.WARNING):

            # A) SCOUT: sweep in windows using YOUR sweep-style primitive
            for w_left, w_right, dc_win in scout_windows(dc_start, dc_stop, scout_window, scout_step):
                # We do a window sweep by iterating dc_win and collecting mags
                mags = []
                for dc in tqdm(dc_win, desc=f"Scout [{w_left:.4f},{w_right:.4f}]", unit="pt", disable=False):
                    # For scouting, we generally do NOT need standardize/reset each point
                    # (too slow). We just scan monotonically in dc_win.
                    rr, mag_1d = _run_one_dc(float(dc))
                    mags.append(mag_1d)

                mag_win = np.stack(mags, axis=1)     # [n_freq, n_dcwin]
                S_win = np.max(mag_win, axis=0)      # or use per-column objective if desired
                score = float(peak_score_robust(S_win))
                history.append(("scout", float(w_left), float(w_right), score))

                if score < float(peak_score_thresh):
                    continue

                # B) REFINE: smaller sweep around window-best
                i_best = int(np.argmax(S_win))
                dc_est = float(dc_win[i_best])
                dc_ref = refine_around(dc_est, refine_half_width, refine_step)

                mags_ref = []
                for dc in tqdm(dc_ref, desc="Refine", unit="pt", disable=False):
                    rr, mag_1d = _run_one_dc(float(dc))
                    mags_ref.append(mag_1d)
                mag_ref = np.stack(mags_ref, axis=1)
                S_ref = np.max(mag_ref, axis=0)
                j_best = int(np.argmax(S_ref))
                dc_ref_best = float(dc_ref[j_best])
                history.append(("refine", dc_ref_best, float(np.max(S_ref))))

                # C) LOCK: use standardized approach for each evaluation
                dc_lock, S_lock = lock_to_peak_3pt(
                    measure_S,
                    dc0=dc_ref_best,
                    delta=float(lock_delta),
                    gain=float(lock_gain),
                    max_iters=int(lock_max_iters),
                    min_delta=float(lock_min_delta),
                    loss_frac=float(lock_loss_frac),
                )
                history.append(("lock", float(dc_lock), float(S_lock)))

                # Final spectrum at locked point (standardized)
                _standardize_before_eval(dc_lock)
                locked_rr, locked_mag_1d = _run_one_dc(float(dc_lock))
                locked_dc = float(dc_lock)
                locked_S = float(S_lock)
                break

        # D) Output for auto_peak
        out = Output()
        out["sample_fqs_abs"] = samp_meta
        out["sel_IFs"] = np.asarray(sel_IFs, int)
        out["odc_name"] = odc_name
        out["odc_param"] = odc_param
        out["ramp_step"] = float(step)
        out["ramp_delay_s"] = float(delay_s)
        out["n_avg"] = int(n_avg)
        out["ro_depl_clks"] = int(ro_depl_clks)

        out["dc_search_start"] = float(dc_start)
        out["dc_search_stop"] = float(dc_stop)
        out["scout_window"] = float(scout_window)
        out["scout_step"] = float(scout_step)
        out["refine_half_width"] = float(refine_half_width)
        out["refine_step"] = float(refine_step)
        out["peak_score_thresh"] = float(peak_score_thresh)

        out["approach_direction"] = str(approach_direction)
        out["approach_reset"] = float(approach_reset) if approach_reset is not None else None
        out["lock_delta"] = float(lock_delta)
        out["lock_gain"] = float(lock_gain)
        out["lock_max_iters"] = int(lock_max_iters)
        out["lock_min_delta"] = float(lock_min_delta)
        out["lock_loss_frac"] = float(lock_loss_frac)

        # If your Output can't store python lists, remove this line and move to metadata
        out["history"] = history

        if locked_dc is None:
            out["locked_dc"] = None
            out["locked_S"] = None
            out["locked_mag_1d"] = None
            mode0 = ExecMode.SIMULATE
            runres = RunResult(
                mode=mode0,
                output=out,
                sim_samples=None,
                metadata={"segments": 0, "mode": "auto_peak", "status": "no_peak"},
            )
            self.save_output(out, "spaFluxOptimization_autoPeak")
            return runres

        out["locked_dc"] = float(locked_dc)
        out["locked_S"] = float(locked_S)
        out["locked_mag_1d"] = np.asarray(locked_mag_1d, dtype=float)

        mode0 = locked_rr.mode if locked_rr is not None else ExecMode.SIMULATE
        runres = RunResult(
            mode=mode0,
            output=out,
            sim_samples=None,
            metadata={"segments": 1, "mode": "auto_peak", "status": "locked"},
        )
        self.save_output(out, "spaFluxOptimization_autoPeak")
        return runres

        
    def SPA_flux_optimization(
        self,
        dc_list,
        sample_fqs,
        n_avg: int,
        *,
        odc_name: str = "octodac_bf",
        odc_param: str = "voltage5",
        step: float = 0.005,
        delay_s: float = 0.1,
        use_absolute_ro_freqs: bool = True,   # if True, sample_fqs are absolute RO freqs; else IFs
        ro_depl_clks: int | None = None
    ) -> RunResult:
        """
        For each flux-bias (ramped via DeviceManager.ramp), run the QUA program that sweeps sel_IFs and
        averages I/Q. Returns I/Q with shape [len(sample_fqs), len(dc_list)].

        - sample_fqs: scalar or array-like. If use_absolute_ro_freqs=True (default),
        theyâ€™re interpreted as absolute RO frequencies (Hz) and converted to IFs.
        Otherwise they are treated as IFs directly.
        """

        attr = self.attributes
        qpm  = self.quaProgMngr

        if ro_depl_clks is None:
            ro_depl_clks = int(attr.ro_therm_clks or 0)

        # --- devices ---
        if self.device_manager.get(odc_name) is None:
            raise RuntimeError(f"Device '{odc_name}' not found in device_manager.")

        # --- normalize frequency list (accept scalar or array) ---
        sample_fqs = np.atleast_1d(np.array(sample_fqs, dtype=float))
        if use_absolute_ro_freqs:
            sel_IFs = qpm.calculate_el_if_fq(attr.ro_el, sample_fqs, as_int=True)
            samp_meta = sample_fqs.copy()  # absolute Hz for the output
        else:
            # already IFs; keep a copy of absolute frequencies for metadata, too
            sel_IFs = qpm.calculate_el_if_fq(attr.ro_el, measureMacro._drive_frequency + sample_fqs, as_int=True) - 0  # validates range
            samp_meta = (measureMacro._drive_frequency + sample_fqs).astype(float)

        # Park RO at base frequency; QUA will call update_frequency() with IFs
        qpm.set_element_fq(attr.ro_el, measureMacro._drive_frequency)

        flux_dc_list = list(map(float, dc_list))
        seg_results: list[RunResult] = []

        qubox_logger = logging.getLogger("qubox")
        qm_logger = logging.getLogger("qm")
        with temporarily_set_levels([qubox_logger, qm_logger], logging.WARNING):
            for dc in tqdm(
                flux_dc_list,
                desc="Sweeping flux bias",
                unit="pt",        # or 'step', 'dc', etc. â€“ optional
                disable=False,    # keep bar ON regardless of log level
            ):
                # 1) ramp hardware to the next DC setpoint
                self.device_manager.ramp(
                    odc_name,
                    odc_param,
                    to=float(dc),
                    step=float(step),
                    delay_s=float(delay_s),
                )

                # 2) compile & run the one-DC program
                prog = cQED_programs.SPA_flux_optimization(sel_IFs, ro_depl_clks, n_avg)

                rr = qpm.run_program(
                    prog,
                    n_total=n_avg,
                    processors=[
                        pp.proc_attach("sample_fqs_abs", samp_meta.copy()),
                        pp.proc_attach("sel_IFs", np.asarray(sel_IFs, dtype=int)),
                        pp.proc_attach("flux_dc", float(dc)),
                    ],
                    process_in_sim=False,
                )

                print(dc, np.abs(rr.output["I"] + 1j * rr.output["Q"]))
                # Defensive: ensure I/Q present
                keys = rr.output.keys()
                if not all(k in keys for k in ("I", "Q")):
                    raise KeyError(
                        f"Expected 'I'/'Q' in program output, got keys: {sorted(keys)}"
                    )
                seg_results.append(rr)

        # 3) stack over DC â†’ matrices [n_freqs, n_dc]
        I_mat = np.stack([np.asarray(rr.output["I"]) for rr in seg_results], axis=1)
        Q_mat = np.stack([np.asarray(rr.output["Q"]) for rr in seg_results], axis=1)
        mag_matrix = np.abs(I_mat + 1j * Q_mat)
        out = Output()
        out["mag_matrix"] = mag_matrix      # shape [n_freqs, n_dc]
        out["sample_fqs_abs"] = samp_meta            # absolute RO freqs (Hz)
        out["sel_IFs"] = np.asarray(sel_IFs, int)    # IFs used in QUA (Hz, int)
        out["flux_dc_list"] = np.asarray(flux_dc_list, float)
        out["odc_name"] = odc_name
        out["odc_param"] = odc_param
        out["ramp_step"] = float(step)
        out["ramp_delay_s"] = float(delay_s)
        out["n_avg"] = int(n_avg)
        out["ro_depl_clks"] = int(ro_depl_clks)
        
        mode = seg_results[0].mode if seg_results else ExecMode.SIMULATE
        runres = RunResult(mode=mode, output=out, sim_samples=None,
                        metadata={"segments": len(seg_results)})
        self.save_output(out, "spaFluxOptimization")
        return runres

    def SPA_pump_frequency_optimization(
        self,
        readout_op: str,
        drive_frequency,
        pump_powers,
        pump_detunings,
        r180: str = "x180",
        samples_per_run: int = 25_000,
        metric: str = "assignment_fidelity",
        assignment_kwargs: dict[str, Any] | None = None,
        butterfly_kwargs: dict[str, Any] | None = None,
    ) -> RunResult:
        """
        Sweep SPA pump powers and frequencies.

        - If metric == "assignment_fidelity":
            Acquire IQ blobs and run two_state_discriminator.
            Configurable via `assignment_kwargs`.

        - Otherwise:
            Run readout_butterfly_measurement (optionally with GE discrimination).
            Configurable via `butterfly_kwargs` (which can include `ge_disc_kwargs`).

        Parameters
        ----------
        samples_per_run : int
            Default number of IQ samples per point *for the assignment_fidelity metric*.
            Can be overridden via assignment_kwargs["samples_per_run"].
        assignment_kwargs : dict, optional
            Kwargs that control the "simple" assignment-fidelity path.
            Recognized keys:
                - "samples_per_run": int
                - "disc_kwargs": dict  (forwarded to two_state_discriminator)
        butterfly_kwargs : dict, optional
            Kwargs forwarded to readout_butterfly_measurement.
            Typical shape:
                {
                    "show_analysis": False,
                    "n_shots": 50_000,
                    "M0_MAX_TRIALS": 256,
                    "run_ge_discrimination": True,
                    "ge_disc_kwargs": {...}
                }
        """
        attr = self.attributes
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)

        pump_powers      = np.asarray(pump_powers, float)
        pump_frequencies = np.asarray(pump_detunings, float) + measureMacro._drive_frequency * 2

        nP = pump_powers.size
        nF = pump_frequencies.size

        disc_matrix      = np.empty((nP, nF), dtype=object)
        butterfly_matrix = np.empty((nP, nF), dtype=object)

        sc = self.device_manager.get("signalcore_pump")

        # Configure measureMacro with the actual PulseOp for this readout
        ro_info = self.pulseOpMngr.get_pulseOp_by_element_op(attr.ro_el, readout_op)

        mm = measureMacro
        mm.reset()
        mm.set_pulse_op(ro_info, active_op=readout_op)
        if ro_info.length is not None:
            mm.set_demod_weight_len(int(ro_info.length))

        first_mode = ExecMode.SIMULATE  # default if no runs happen
        did_any = False

        qubox_logger = logging.getLogger("qubox")
        qm_logger    = logging.getLogger("qm")

        n_total = len(pump_powers) * len(pump_frequencies)
        with temporarily_set_levels([qubox_logger, qm_logger], logging.WARNING):
            with tqdm(
                total=n_total,
                desc="Sweeping SPA pump power/frequency",
                unit="pt",
                disable=False,
            ) as bar:
                for i, power in enumerate(pump_powers):
                    sc.do_set_power(power)
                    _logger.info("SPA pump power set to %.3f dBm", power)

                    for j, frequency in enumerate(pump_frequencies):
                        sc.do_set_frequency(frequency)
                        _logger.info(
                            "SPA pump frequency set to %.6f MHz", frequency / 1e6
                        )

                        if metric == "assignment_fidelity":
                            # ---- assignment_fidelity path ------------------------
                            # Defaults for this mode
                            default_assign = {
                                "samples_per_run": samples_per_run,
                                "disc_kwargs": {
                                    "b_plot": False,
                                },
                            }
                            if assignment_kwargs is not None:
                                # handle nested disc_kwargs merge
                                ak = dict(assignment_kwargs)  # shallow copy
                                if "disc_kwargs" in ak:
                                    default_assign["disc_kwargs"].update(ak["disc_kwargs"])
                                    ak.pop("disc_kwargs")
                                default_assign.update(ak)

                            eff_samples_per_run = int(default_assign["samples_per_run"])
                            disc_kwargs_eff     = default_assign["disc_kwargs"]

                            # IQ blob acquisition program
                            iq_blob_prog = cQED_programs.iq_blobs(
                                attr.ro_el,
                                attr.qb_el,
                                r180,
                                attr.qb_therm_clks,
                                eff_samples_per_run,
                            )

                            rr = self.quaProgMngr.run_program(
                                iq_blob_prog,
                                eff_samples_per_run,
                                processors=[],
                                process_in_sim=False,
                            )

                            if not did_any:
                                first_mode, did_any = rr.mode, True

                            S   = rr.output["S"]
                            S_g, S_e = S[:, 0], S[:, 1]

                            disc: Output = two_state_discriminator(
                                S_g.real,
                                S_g.imag,
                                S_e.real,
                                S_e.imag,
                                **disc_kwargs_eff,
                            )

                            disc_matrix[i, j] = disc

                        else:
                            if readout_op == "readout":
                                persist = True
                            else:
                                persist = False
                            # ---- butterfly path -------------------------------
                            # Use the combined readout_ge_discrimination_and_butterfly method
                            default_combined_kwargs: dict[str, Any] = {
                                "r180": r180,
                                "show_analysis": False,
                                "update_measureMacro": False,  # Don't update in sweep
                                "burn_rot_weights": False,      # Don't burn in sweep
                                "persist": persist,               # Don't persist in sweep
                                "n_samples_disc": 20_000,
                                "n_samples_butterfly": 50_000,
                                "base_weight_keys": None,       # Auto-detect
                                "blob_k_g": 2.0,
                                "blob_k_e": None,
                                "M0_MAX_TRIALS": 1000,
                                "k_g": 1.0,
                                "k_e": 1.0,
                            }

                            if butterfly_kwargs is not None:
                                default_combined_kwargs.update(butterfly_kwargs)

                            ge_res, bfly_res = self.readout_ge_discrimination_and_butterfly(
                                measure_op=readout_op,
                                drive_frequency=drive_frequency,
                                **default_combined_kwargs
                            )

                            if not did_any:
                                first_mode, did_any = bfly_res.mode, True
                            F, Q, V = bfly_res.output.extract("F", "Q", "V")
                            butterfly_matrix[i, j] = {"F": F, "Q": Q, "V": V}
                            # Store discriminator results as well
                            disc_matrix[i, j] = ge_res.output

                        bar.update(1)

        out = Output()
        out["pump_powers"]      = pump_powers
        out["pump_detunings"]   = pump_detunings
        out["disc_matrix"]      = disc_matrix
        out["butterfly_matrix"] = butterfly_matrix
        out["num_frequencies"]  = len(pump_detunings)
        out["num_powers"]       = len(pump_powers)

        runres = RunResult(
            mode=first_mode,
            output=out,
            sim_samples=None,
            metadata={"runs": nP * nF},
        )

        self.save_output(runres.output, "spaPumpPowerFrequencyOptimization")
        
        return runres

    def sequential_simulation(self, gates: list[Gate], measurement_gates: List[Union[Measure, None]], num_shots=1000):
        attr = self.attributes
    
        self.quaProgMngr.set_element_fq(attr.ro_el, measureMacro._drive_frequency)
        self.quaProgMngr.set_element_fq(attr.qb_el, attr.qb_fq)
        self.quaProgMngr.set_element_fq(attr.st_el, attr.st_fq)

        prog = cQED_programs.sequential_simulation(gates, measurement_gates, attr.st_therm_clks, num_shots)
        
        runres = self.quaProgMngr.run_program(
            prog,
            n_total=num_shots,
            processors=[pp.bare_proc],
            process_in_sim=False
        )
        
        return runres


