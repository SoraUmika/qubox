# qubox_v2/calibration/mixer_calibration.py
"""
Manual IQ mixer calibration via external spectrum analyzer (SA124B).

Provides two calibration methods, both operating in two separable stages:
  Stage A — Minimise LO feedthrough by scanning DC offsets (I0, Q0).
            "minimizer: element=%s  LO=%.4f GHz  IF=%.2f MHz  sideband=%s  objective=%s  save_to_db=%s",
            element, f_lo / 1e9, f_if / 1e6, self._cfg.sideband, self._cfg.objective_mode, save_to_db,
Classes
-------
MixerCalibrationConfig
    All tunable parameters for SA measurement, grid search, and minimiser.
SAMeasurementHelper
    Narrow-span peak-power measurement around desired / LO / image tones.
ManualMixerCalibrator
    Main calibration engine: ``scan_2d`` (grid search) and ``minimizer``
    (derivative-free optimiser), plus ``calibration_db.json`` persistence.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
from tqdm import tqdm
from octave_sdk import RFOutputMode

from ..programs import api as cQED_programs

_logger = logging.getLogger(__name__)

# Maximum retry attempts for atomic file replacement on Windows
_DB_WRITE_MAX_RETRIES = 5
_DB_WRITE_RETRY_BASE_DELAY = 0.1  # seconds (exponential backoff)


# ──────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────
@dataclass
class MixerCalibrationConfig:
    """All tunable parameters for manual mixer calibration.

    Parameter groups
    ----------------
    **SA measurement** — spectrum analyser sweep configuration.
    **DC offset grid** — coarse + fine 2-D grid over (I0, Q0) to minimise LO leakage.
    **IQ correction grid** — coarse + fine 2-D grid over (gain, phase) to minimise image.
    **Minimiser** — bounded derivative-free optimiser settings.
    **CW tone** — continuous-wave probe signal parameters.
    **Settle times** — hardware settle delays after parameter changes.
    """

    # SA measurement
    sa_span_hz: float = 2e6       # narrow span around each tone (Hz)
    sa_rbw: float = 1e3           # resolution bandwidth (Hz)
    sa_vbw: float = 1e3           # video bandwidth (Hz)
    sa_level: float = 0.0         # reference level (dBm)
    sa_avg: int = 5               # number of sweeps to average
    sa_settle: float = 0.0        # settle time after SA reconfigure (seconds)
    sa_extra_config: dict[str, Any] = field(default_factory=dict)  # optional driver kwargs

    # DC offset grid search
    dc_coarse_range: float = 0.1    # ±V half-range for coarse grid
    dc_coarse_n: int = 11           # points per axis (coarse)
    dc_fine_range: float = 0.02     # ±V half-range for fine grid
    dc_fine_n: int = 11             # points per axis (fine)

    # IQ correction grid search
    iq_gain_range: float = 0.1      # ±gain half-range
    iq_phase_range: float = 0.2     # ±phase half-range (rad)
    iq_coarse_n: int = 9            # points per axis (coarse)
    iq_fine_range_gain: float = 0.02   # ±gain half-range (fine)
    iq_fine_range_phase: float = 0.04  # ±phase half-range (fine, rad)
    iq_fine_n: int = 9              # points per axis (fine)

    # Minimiser
    minimizer_maxiter: int = 60
    minimizer_xtol: float = 1e-4
    max_total_evals: int = 40
    dc_maxiter: int = 12
    iq_maxiter: int = 28
    minimizer_block_passes: int = 2
    minimizer_joint_refine: bool = True
    minimizer_joint_maxiter: int = 20
    minimizer_invalid_penalty: float = 1e6

    # Hard safety bounds (manual minimizer)
    dc_i0_bounds: tuple[float, float] = (-0.2, 0.2)
    dc_q0_bounds: tuple[float, float] = (-0.2, 0.2)
    iq_gain_bounds: tuple[float, float] = (-0.2, 0.2)
    iq_phase_bounds: tuple[float, float] = (-0.35, 0.35)

    # CW tone
    cw_pulse: str = "const"
    cw_gain: float = 1.0
    cw_gain_dc: float = 0.125
    cw_truncate_clks: int = 250

    # Settle time (seconds) after parameter change
    dc_settle: float = 0.01
    iq_settle: float = 0.05

    # DB write frequency control
    # "final_only"  — write calibration_db.json only after calibration completes
    # "per_stage"   — write at the end of each stage (DC coarse, DC fine, IQ coarse, IQ fine)
    # "per_point"   — write at every grid/minimiser evaluation (legacy behaviour, slowest)
    write_db_mode: Literal["final_only", "per_stage", "per_point"] = "final_only"

    # Sideband objective (explicit target/image/carrier handling)
    # sideband="lsb" => target=LO-|IF|, image=LO+|IF|
    # sideband="usb" => target=LO+|IF|, image=LO-|IF|
    sideband: Literal["lsb", "usb"] = "lsb"
    objective_mode: Literal["weighted_sum", "ratio_db"] = "weighted_sum"
    w_carrier: float = 1.0
    w_image: float = 1.0
    w_target: float = 1.0
    target_power_ref_dbm: float | None = None
    target_power_tolerance_db: float = 0.0

    # Notebook UX controls
    quiet_qm_logs: bool = False
    live_plot: bool = False
    live_plot_every: int = 1

    # Manual-result safety guard
    manual_revert_if_worse: bool = True
    manual_revert_tolerance_db: float = 0.0


# ──────────────────────────────────────────────────────────────────
# SA Measurement Helper
# ──────────────────────────────────────────────────────────────────
class SAMeasurementHelper:
    """Narrow-span peak-power measurement at three mixer tones."""

    def __init__(self, sa_device: Any, config: MixerCalibrationConfig):
        self._sa = sa_device
        self._cfg = config
        if config.sa_rbw <= 0 or config.sa_vbw <= 0:
            raise ValueError("SA RBW and VBW must be positive")
        if config.sa_avg < 1:
            raise ValueError("SA averages must be >= 1")

    # ── single-tone measurement ────────────────────────────────
    def measure_peak_power(self, center_hz: float) -> float:
        """Return peak power (dBm) in a narrow span around *center_hz*."""
        base_cfg = {
            "center": center_hz,
            "span": self._cfg.sa_span_hz,
            "rbw": self._cfg.sa_rbw,
            "vbw": self._cfg.sa_vbw,
            "level": self._cfg.sa_level,
            "force": True,
        }
        extra_cfg = dict(self._cfg.sa_extra_config or {})
        try:
            self._sa.configure(**base_cfg, **extra_cfg)
        except TypeError:
            # Backward-compatible fallback for drivers that do not accept extras.
            self._sa.configure(**base_cfg)
        if self._cfg.sa_settle > 0:
            time.sleep(self._cfg.sa_settle)
        _freq, _tr_min, tr_max = self._sa.sweep(average_num=self._cfg.sa_avg)
        return float(np.max(tr_max))

    # ── three-tone measurement ─────────────────────────────────
    def measure_tones(self, f_lo: float, f_if: float) -> dict[str, float]:
        """Measure desired, LO-leak, and image tones; compute dBc metrics.

        Sideband is selected by ``MixerCalibrationConfig.sideband``.
        """
        if self._cfg.sideband == "usb":
            f_target = f_lo + abs(f_if)
            f_image = f_lo - abs(f_if)
        else:
            f_target = f_lo - abs(f_if)
            f_image = f_lo + abs(f_if)

        P_des = self.measure_peak_power(f_target)
        P_lo = self.measure_peak_power(f_lo)
        P_img = self.measure_peak_power(f_image)

        return {
            "P_des_dBm": P_des,
            "P_LO_dBm": P_lo,
            "P_img_dBm": P_img,
            "f_target": f_target,
            "f_image": f_image,
            "sideband": self._cfg.sideband,
            "LO_leak_dBc": P_des - P_lo,
            "IRR_dBc": P_des - P_img,
        }


# ──────────────────────────────────────────────────────────────────
# Calibration Engine
# ──────────────────────────────────────────────────────────────────
class ManualMixerCalibrator:
    """Manual IQ mixer calibration via SA124B.

    Parameters
    ----------
    hw : HardwareController
        Live hardware controller (must have an open QM).
    sa_helper : SAMeasurementHelper
        Configured SA measurement wrapper.
    calibration_db_path : Path
        Full path to ``calibration_db.json``.
    config : MixerCalibrationConfig, optional
        Override default tuning knobs.
    """

    def __init__(
        self,
        hw: Any,
        sa_helper: SAMeasurementHelper,
        calibration_db_path: Path,
        config: MixerCalibrationConfig | None = None,
    ):
        self._hw = hw
        self._sa = sa_helper
        self._db_path = Path(calibration_db_path)
        self._cfg = config or MixerCalibrationConfig()
        # In-memory DB cache used during calibration to avoid per-point writes
        self._db_cache: dict | None = None

    @contextmanager
    def _maybe_quiet_qm_logs(self, enabled: bool):
        """Temporarily suppress QM INFO noise while keeping WARN/ERROR visible."""
        if not enabled:
            yield
            return
        names = ("qm", "qm.grpc", "qm.octave", "qm.api")
        loggers = [logging.getLogger(n) for n in names]
        prev_levels = [lg.level for lg in loggers]
        try:
            for lg in loggers:
                lg.setLevel(logging.WARNING)
            yield
        finally:
            for lg, lvl in zip(loggers, prev_levels):
                lg.setLevel(lvl)

    @staticmethod
    def _objective_cost(
        *,
        p_target_dbm: float,
        p_carrier_dbm: float,
        p_image_dbm: float,
        cfg: MixerCalibrationConfig,
        p_target_ref_dbm: float | None = None,
    ) -> float:
        """Compute explicit sideband objective cost."""
        wc, wi, wt = float(cfg.w_carrier), float(cfg.w_image), float(cfg.w_target)
        if cfg.objective_mode == "ratio_db":
            eps_mw = 1e-15
            carrier_mw = 10 ** (p_carrier_dbm / 10.0)
            image_mw = 10 ** (p_image_dbm / 10.0)
            target_mw = max(eps_mw, 10 ** (p_target_dbm / 10.0))
            num = wc * carrier_mw + wi * image_mw
            den = max(eps_mw, wt * target_mw)
            return float(10.0 * np.log10(max(eps_mw, num / den)))
        ref = cfg.target_power_ref_dbm if p_target_ref_dbm is None else p_target_ref_dbm
        drop_penalty = 0.0
        if ref is not None:
            drop_threshold = float(ref) - float(cfg.target_power_tolerance_db)
            drop_penalty = max(0.0, drop_threshold - float(p_target_dbm))
        return float(
            wc * (float(p_carrier_dbm) - float(p_target_dbm))
            + wi * (float(p_image_dbm) - float(p_target_dbm))
            + wt * drop_penalty
        )

    @staticmethod
    def _objective_cost_from_tones(
        tones: dict[str, float],
        *,
        cfg: MixerCalibrationConfig,
        p_target_ref_dbm: float | None = None,
    ) -> float:
        """Compute objective from measured tones with finite-value checks."""
        p_target = float(tones["P_des_dBm"])
        p_carrier = float(tones["P_LO_dBm"])
        p_image = float(tones["P_img_dBm"])
        if not (np.isfinite(p_target) and np.isfinite(p_carrier) and np.isfinite(p_image)):
            raise ValueError("Invalid SA tones (NaN/inf).")
        cost = ManualMixerCalibrator._objective_cost(
            p_target_dbm=p_target,
            p_carrier_dbm=p_carrier,
            p_image_dbm=p_image,
            cfg=cfg,
            p_target_ref_dbm=p_target_ref_dbm,
        )
        if not np.isfinite(cost):
            raise ValueError("Objective cost evaluated to NaN/inf.")
        return float(cost)

    @staticmethod
    def _is_result_worse(candidate: dict[str, float], baseline: dict[str, float], *, tolerance_db: float = 0.0) -> bool:
        """Return True if manual candidate degrades LO leak or IRR vs baseline."""
        tol = abs(float(tolerance_db))
        cand_lo = float(candidate.get("LO_leak_dBc", float("nan")))
        base_lo = float(baseline.get("LO_leak_dBc", float("nan")))
        cand_irr = float(candidate.get("IRR_dBc", float("nan")))
        base_irr = float(baseline.get("IRR_dBc", float("nan")))

        worse_lo = np.isfinite(cand_lo) and np.isfinite(base_lo) and (cand_lo < (base_lo - tol))
        worse_irr = np.isfinite(cand_irr) and np.isfinite(base_irr) and (cand_irr < (base_irr - tol))
        return bool(worse_lo or worse_irr)

    @staticmethod
    def _init_live_heatmap(x_vals: np.ndarray, y_vals: np.ndarray, *, title: str):
        try:
            import matplotlib.pyplot as plt
            from IPython.display import clear_output, display
        except Exception:
            return None
        fig, ax = plt.subplots(figsize=(6, 5))
        z = np.full((len(y_vals), len(x_vals)), np.nan, dtype=float)
        im = ax.imshow(
            z,
            origin="lower",
            aspect="auto",
            extent=[x_vals[0], x_vals[-1], y_vals[0], y_vals[-1]],
            interpolation="nearest",
        )
        ax.set_title(title)
        cb = fig.colorbar(im, ax=ax)
        cb.set_label("Cost (dBm metric)")
        display(fig)
        return {
            "fig": fig,
            "ax": ax,
            "im": im,
            "z": z,
            "display": display,
            "clear_output": clear_output,
            "best_scatter": None,
        }

    @staticmethod
    def _update_live_heatmap(state: dict | None, *, ix: int, iy: int, value: float, best_x: float, best_y: float, every: int, counter: int):
        if not state:
            return
        state["z"][iy, ix] = value
        if every > 1 and (counter % every) != 0:
            return
        im = state["im"]
        im.set_data(state["z"])
        finite = np.isfinite(state["z"])
        if np.any(finite):
            vmin = float(np.nanmin(state["z"]))
            vmax = float(np.nanmax(state["z"]))
            if vmin < vmax:
                im.set_clim(vmin=vmin, vmax=vmax)
        ax = state["ax"]
        if state["best_scatter"] is not None:
            state["best_scatter"].remove()
        state["best_scatter"] = ax.scatter([best_x], [best_y], c="w", s=45, edgecolors="k", label="best")
        ax.legend(loc="upper right")
        state["clear_output"](wait=True)
        state["display"](state["fig"])

    @staticmethod
    def _init_live_history(*, title: str, ylabel: str = "Cost"):
        try:
            import matplotlib.pyplot as plt
            from IPython.display import clear_output, display
        except Exception:
            return None
        fig, ax = plt.subplots(figsize=(7, 4))
        line_cost, = ax.plot([], [], "b.-", label="cost")
        line_best, = ax.plot([], [], "r-", label="best-so-far")
        ax.set_xlabel("Iteration")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")
        display(fig)
        return {
            "fig": fig,
            "ax": ax,
            "line_cost": line_cost,
            "line_best": line_best,
            "cost": [],
            "best": [],
            "display": display,
            "clear_output": clear_output,
        }

    @staticmethod
    def _update_live_history(state: dict | None, value: float, *, every: int = 1):
        if not state:
            return
        state["cost"].append(float(value))
        prev_best = state["best"][-1] if state["best"] else float(value)
        state["best"].append(min(prev_best, float(value)))
        n = len(state["cost"])
        if every > 1 and (n % every) != 0:
            return
        x = np.arange(1, n + 1)
        state["line_cost"].set_data(x, np.asarray(state["cost"], dtype=float))
        state["line_best"].set_data(x, np.asarray(state["best"], dtype=float))
        state["ax"].relim()
        state["ax"].autoscale_view()
        state["clear_output"](wait=True)
        state["display"](state["fig"])

    @staticmethod
    def _init_live_minimizer_metrics(*, title: str):
        try:
            import matplotlib.pyplot as plt
            from IPython.display import clear_output, display
        except Exception:
            return None
        fig, ax = plt.subplots(figsize=(8, 4.5))
        line_lo, = ax.plot([], [], "b.-", label="LO leak (dBc)")
        line_irr, = ax.plot([], [], "g.-", label="IRR (dBc)")
        line_cost, = ax.plot([], [], "r.-", label="cost")
        ax.set_xlabel("Iteration")
        ax.set_ylabel("Metric value")
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")
        display_handle = None
        try:
            display_handle = display(fig, display_id=True)
        except Exception:
            display(fig)
        return {
            "fig": fig,
            "ax": ax,
            "line_lo": line_lo,
            "line_irr": line_irr,
            "line_cost": line_cost,
            "lo_leak_dbc": [],
            "irr_dbc": [],
            "cost": [],
            "display_handle": display_handle,
            "display": display,
            "clear_output": clear_output,
        }

    @staticmethod
    def _render_live_minimizer_metrics(state: dict | None):
        if not state:
            return
        n = len(state.get("cost", []))
        if n <= 0:
            return
        x = np.arange(1, n + 1)
        state["line_lo"].set_data(x, np.asarray(state["lo_leak_dbc"], dtype=float))
        state["line_irr"].set_data(x, np.asarray(state["irr_dbc"], dtype=float))
        state["line_cost"].set_data(x, np.asarray(state["cost"], dtype=float))
        state["ax"].relim()
        state["ax"].autoscale_view()
        handle = state.get("display_handle")
        if handle is not None and hasattr(handle, "update"):
            try:
                handle.update(state["fig"])
                return
            except Exception:
                pass
        state["clear_output"](wait=True)
        state["display"](state["fig"])

    @staticmethod
    def _publish_live_minimizer_metrics_snapshot(state: dict | None):
        if not state:
            return
        try:
            import matplotlib.pyplot as plt
            fig = state.get("fig")
            if fig is None:
                return
            plt.figure(fig.number)
            plt.show()
        except Exception:
            return

    @staticmethod
    def _update_live_minimizer_metrics(
        state: dict | None,
        *,
        lo_leak_dbc: float,
        irr_dbc: float,
        cost: float,
        every: int = 1,
    ):
        if not state:
            return
        state["lo_leak_dbc"].append(float(lo_leak_dbc))
        state["irr_dbc"].append(float(irr_dbc))
        state["cost"].append(float(cost))
        n = len(state["cost"])
        if every > 1 and (n % every) != 0:
            return
        ManualMixerCalibrator._render_live_minimizer_metrics(state)

    @staticmethod
    def _plot_parameter_history(
        *,
        title: str,
        x_label: str,
        series: list[tuple[str, list[float], str]],
    ) -> None:
        try:
            import matplotlib.pyplot as plt
        except Exception:
            return

        if not series:
            return

        fig, axes = plt.subplots(len(series), 1, figsize=(8, 2.8 * len(series)), sharex=True)
        if len(series) == 1:
            axes = [axes]

        for ax, (label, values, y_label) in zip(axes, series):
            if not values:
                continue
            x = np.arange(1, len(values) + 1)
            ax.plot(x, np.asarray(values, dtype=float), "b.-", label=label)
            ax.set_ylabel(y_label)
            ax.grid(True, alpha=0.3)
            ax.legend(loc="best")

        axes[-1].set_xlabel(x_label)
        fig.suptitle(title)
        fig.tight_layout()
        plt.show()

    # ────────── CW tone management ────────────────────────────
    def _start_cw(self, element: str, *, gain: float | None = None):
        """Start an infinite CW tone on *element*. Returns a QM job handle."""
        # Validate that the requested CW operation is available for this element.
        # This makes pulse-name migrations explicit (e.g., const_x180 -> const)
        # and avoids silent misconfiguration.
        cfg = self._hw.qm.get_config()
        ops = sorted((cfg.get("elements", {}).get(element, {}).get("operations", {}) or {}).keys())
        if self._cfg.cw_pulse not in ops:
            raise ValueError(
                f"Manual mixer calibration CW op '{self._cfg.cw_pulse}' not found for element '{element}'. "
                f"Available operations: {ops}"
            )

        # Ensure RF output is enabled for the active channel before CW execution.
        self._hw.set_octave_output(element, RFOutputMode.on)

        prog = cQED_programs.continuous_wave(
            target_el=element,
            pulse=self._cfg.cw_pulse,
            gain=self._cfg.cw_gain if gain is None else float(gain),
            truncate_clks=self._cfg.cw_truncate_clks,
        )
        return self._hw.qm.execute(prog)

    @staticmethod
    def _stop_cw(job) -> None:
        job.halt()

    # ────────── DC offset (fast, real-time) ───────────────────
    def _set_dc_offsets(self, element: str, i0: float, q0: float) -> None:
        self._hw.qm.set_output_dc_offset_by_element(element, "I", float(i0))
        self._hw.qm.set_output_dc_offset_by_element(element, "Q", float(q0))

    @staticmethod
    def _iq_imbalance_matrix(gain: float, phase: float) -> tuple[float, float, float, float]:
        """Convert gain/phase imbalance parameters to QM correction matrix."""
        g = float(gain)
        p = float(phase)
        c = float(np.cos(p))
        s = float(np.sin(p))
        denom = (1.0 - g * g) * (2.0 * c * c - 1.0)
        if abs(denom) < 1e-12:
            raise ValueError(
                f"Invalid IQ imbalance parameters: gain={g:.6g}, phase={p:.6g} produce near-singular correction."
            )
        n = 1.0 / denom
        return (
            n * (1.0 - g) * c,
            n * (1.0 + g) * s,
            n * (1.0 - g) * s,
            n * (1.0 + g) * c,
        )

    def _resolve_mixer_name(self, element: str) -> str:
        """Resolve mixer name from active QM config for an element."""
        cfg = self._hw.qm.get_config()
        el_cfg = (cfg.get("elements") or {}).get(element, {})
        mix_inputs = el_cfg.get("mixInputs") or {}
        mixer = mix_inputs.get("mixer")
        if not mixer:
            raise ValueError(
                f"Element '{element}' has no mixInputs.mixer entry in active QM config; "
                "cannot apply IQ correction matrix."
            )
        return str(mixer)

    # ────────── IQ correction (live, no QM reopen) ────────────
    def _apply_iq_correction(
        self,
        element: str,
        f_lo: float,
        f_if: float,
        gain: float,
        phase: float,
        i0: float,
        q0: float,
        *,
        write_db: bool = True,
        running_job: Any | None = None,
    ) -> None:
        """Apply trial gain/phase + DC offsets live and optionally persist trial DB values.

        Parameters
        ----------
        write_db : bool
            If True, write trial values to canonical calibration_db.json.
            If False, keep trial values only in in-memory cache.
        running_job : Any, optional
            If provided and supports ``set_element_correction``, apply the
            matrix directly to the running job (recommended for scan loops).
            Otherwise apply via ``qm.set_mixer_correction``.
        """
        db = self._get_db()
        lo_mode_id = self._resolve_lo_mode_id(db, element)
        if_mode_id = self._resolve_if_mode_id(db, element)

        db["lo_cal"][str(lo_mode_id)].update(
            {"i0": i0, "q0": q0, "timestamp": time.time(), "method": "manual"}
        )
        db["if_cal"][str(if_mode_id)].update(
            {"gain": gain, "phase": phase, "timestamp": time.time(), "method": "manual"}
        )

        if write_db:
            self._write_db(db)
        else:
            self._db_cache = db

        correction = self._iq_imbalance_matrix(gain, phase)

        if running_job is not None and hasattr(running_job, "set_element_correction"):
            running_job.set_element_correction(element, correction)
        else:
            mixer = self._resolve_mixer_name(element)
            self._hw.qm.set_mixer_correction(
                mixer,
                float(f_if),
                float(f_lo),
                correction,
            )

        self._set_dc_offsets(element, i0, q0)

    # ══════════════════════════════════════════════════════════
    #  METHOD A — Grid search (manual_scan_2d)
    # ══════════════════════════════════════════════════════════
    def scan_2d(
        self,
        element: str,
        f_lo: float,
        f_if: float,
        *,
        save_to_db: bool = True,
        **config_overrides,
    ) -> dict:
        """Two-stage coarse→fine grid search: DC offsets then IQ correction.

        Returns a dict with optimal parameters + measured tone powers.

        Any keyword argument matching a ``MixerCalibrationConfig`` field
        overrides the corresponding value for this run only.

        When ``save_to_db=False``, the canonical ``calibration_db.json`` is
        never written. Trial IQ corrections are applied live and kept in-memory
        during the run without mutating the persistent DB.
        """
        cfg = self._cfg
        if config_overrides:
            cfg = dataclasses.replace(cfg, **config_overrides)

        # Pre-load the DB into cache to avoid per-point reads
        self._db_cache = self._read_db()

        db0 = self._get_db()
        lo_mode_id = self._resolve_lo_mode_id(db0, element)
        if_mode_id = self._resolve_if_mode_id(db0, element)
        lo_cal = db0.get("lo_cal", {}).get(str(lo_mode_id), {})
        if_cal = db0.get("if_cal", {}).get(str(if_mode_id), {})
        i0_init = float(lo_cal.get("i0", 0.0))
        q0_init = float(lo_cal.get("q0", 0.0))
        gain_init = float(if_cal.get("gain", 0.0))
        phase_init = float(if_cal.get("phase", 0.0))

        # Determine per-point write behaviour
        write_db_mode = cfg.write_db_mode if save_to_db else "final_only"
        # For IQ grid, whether each point writes the canonical DB
        iq_write_per_point = (write_db_mode == "per_point") and save_to_db

        _logger.info(
            "scan_2d: element=%s  LO=%.4f GHz  IF=%.2f MHz  sideband=%s  objective=%s  save_to_db=%s  write_mode=%s",
            element, f_lo / 1e9, f_if / 1e6, cfg.sideband, cfg.objective_mode, save_to_db, write_db_mode,
        )

        with self._maybe_quiet_qm_logs(cfg.quiet_qm_logs):
            baseline = self._measure_final(
                element,
                f_lo,
                f_if,
                i0_init,
                q0_init,
                gain_init,
                phase_init,
                write_db=save_to_db,
            )

            # ── Stage A: DC offsets ───────────────────────────────
            _logger.info(
                "Stage A: DC offset optimisation (coarse %dx%d = %d points)",
                cfg.dc_coarse_n, cfg.dc_coarse_n, cfg.dc_coarse_n ** 2,
            )
            job = self._start_cw(element, gain=cfg.cw_gain_dc)
            best_i0, best_q0, _ = self._grid_search_dc(
                element, f_lo,
                center_i=0.0, center_q=0.0,
                half_range=cfg.dc_coarse_range,
                n_points=cfg.dc_coarse_n,
                cfg=cfg,
            )
            _logger.info(
                "Stage A: DC offset optimisation (fine %dx%d = %d points)",
                cfg.dc_fine_n, cfg.dc_fine_n, cfg.dc_fine_n ** 2,
            )
            best_i0, best_q0, best_P_LO = self._grid_search_dc(
                element, f_lo,
                center_i=best_i0, center_q=best_q0,
                half_range=cfg.dc_fine_range,
                n_points=cfg.dc_fine_n,
                cfg=cfg,
            )
            self._set_dc_offsets(element, best_i0, best_q0)
            self._stop_cw(job)
            _logger.info(
                "Stage A done: I0=%.6f  Q0=%.6f  P_LO=%.1f dBm",
                best_i0, best_q0, best_P_LO,
            )

            # ── Stage B: IQ correction ────────────────────────────
            _logger.info(
                "Stage B: IQ correction optimisation (coarse %dx%d = %d points)",
                cfg.iq_coarse_n, cfg.iq_coarse_n, cfg.iq_coarse_n ** 2,
            )
            best_g, best_p, _ = self._grid_search_iq(
                element, f_lo, f_if,
                best_i0, best_q0,
                center_gain=0.0, center_phase=0.0,
                half_range_gain=cfg.iq_gain_range,
                half_range_phase=cfg.iq_phase_range,
                n_points=cfg.iq_coarse_n,
                cfg=cfg,
                write_db=iq_write_per_point,
            )
            # per_stage write after IQ coarse
            if save_to_db and write_db_mode == "per_stage":
                self._write_db(self._get_db())
                _logger.info("Stage B (coarse) DB snapshot saved.")

            _logger.info(
                "Stage B: IQ correction optimisation (fine %dx%d = %d points)",
                cfg.iq_fine_n, cfg.iq_fine_n, cfg.iq_fine_n ** 2,
            )
            best_g, best_p, best_P_img = self._grid_search_iq(
                element, f_lo, f_if,
                best_i0, best_q0,
                center_gain=best_g, center_phase=best_p,
                half_range_gain=cfg.iq_fine_range_gain,
                half_range_phase=cfg.iq_fine_range_phase,
                n_points=cfg.iq_fine_n,
                cfg=cfg,
                write_db=iq_write_per_point,
            )
            _logger.info(
                "Stage B done: gain=%.6f  phase=%.6f  objective=%.3f",
                best_g, best_p, best_P_img,
            )

        # ── Final measurement ─────────────────────────────────
        final = self._measure_final(
            element, f_lo, f_if, best_i0, best_q0, best_g, best_p,
            write_db=save_to_db,
        )

        reverted_to_baseline = False
        if bool(getattr(cfg, "manual_revert_if_worse", True)) and self._is_result_worse(
            final,
            baseline,
            tolerance_db=float(getattr(cfg, "manual_revert_tolerance_db", 0.0)),
        ):
            _logger.warning(
                "Manual scan result for '%s' is worse than baseline; reverting to baseline calibration.",
                element,
            )
            candidate_final = dict(final)
            final = self._measure_final(
                element,
                f_lo,
                f_if,
                i0_init,
                q0_init,
                gain_init,
                phase_init,
                write_db=save_to_db,
            )
            best_i0, best_q0, best_g, best_p = i0_init, q0_init, gain_init, phase_init
            reverted_to_baseline = True
        else:
            candidate_final = None

        result = {
            "element": element,
            "f_lo": f_lo,
            "f_if": f_if,
            "i0": best_i0,
            "q0": best_q0,
            "gain": best_g,
            "phase": best_p,
            "reverted_to_baseline": reverted_to_baseline,
            **final,
        }
        if candidate_final is not None:
            result["candidate_manual"] = candidate_final
        result["baseline_before_manual"] = dict(baseline)
        if save_to_db:
            self._persist(result, method="manual_scan_2d")

        # Cleanup scratch file and cache
        self._cleanup_scratch()
        self._db_cache = None

        self._print_summary(result, saved=save_to_db)
        return result

    # ══════════════════════════════════════════════════════════
    #  METHOD B — Derivative-free minimiser (manual_minimizer)
    # ══════════════════════════════════════════════════════════
    def minimizer(
        self,
        element: str,
        f_lo: float,
        f_if: float,
        *,
        save_to_db: bool = True,
        **config_overrides,
    ) -> dict:
        """Bounded block-coordinate optimiser with unified three-tone objective.

        Any keyword argument matching a ``MixerCalibrationConfig`` field
        overrides the corresponding value for this run only.

        When ``save_to_db=False``, the canonical ``calibration_db.json`` is
        never written. Trial values stay in-memory during optimisation.
        """
        from scipy.optimize import minimize

        cfg = self._cfg
        if config_overrides:
            cfg = dataclasses.replace(cfg, **config_overrides)

        _logger.info(
            "minimizer: element=%s  LO=%.4f GHz  IF=%.2f MHz  sideband=%s  objective=%s  save_to_db=%s  write_mode=%s",
            element,
            f_lo / 1e9,
            f_if / 1e6,
            cfg.sideband,
            cfg.objective_mode,
            save_to_db,
            cfg.write_db_mode if save_to_db else "final_only",
        )

        self._db_cache = self._read_db()
        write_per_point = (cfg.write_db_mode == "per_point") and save_to_db

        db0 = self._get_db()
        lo_mode_id = self._resolve_lo_mode_id(db0, element)
        if_mode_id = self._resolve_if_mode_id(db0, element)
        lo_cal = db0.get("lo_cal", {}).get(str(lo_mode_id), {})
        if_cal = db0.get("if_cal", {}).get(str(if_mode_id), {})

        i0_init = float(lo_cal.get("i0", 0.0))
        q0_init = float(lo_cal.get("q0", 0.0))
        gain_init = float(if_cal.get("gain", 0.0))
        phase_init = float(if_cal.get("phase", 0.0))

        i0_lo, i0_hi = map(float, cfg.dc_i0_bounds)
        q0_lo, q0_hi = map(float, cfg.dc_q0_bounds)
        g_lo, g_hi = map(float, cfg.iq_gain_bounds)
        p_lo, p_hi = map(float, cfg.iq_phase_bounds)
        if not (i0_lo < i0_hi and q0_lo < q0_hi and g_lo < g_hi and p_lo < p_hi):
            raise ValueError("Invalid manual minimizer bounds: each lower bound must be < upper bound.")

        penalty_cost = abs(float(cfg.minimizer_invalid_penalty))
        if not np.isfinite(penalty_cost) or penalty_cost <= 0:
            penalty_cost = 1e6

        def _clip_to_bounds(x: np.ndarray) -> np.ndarray:
            return np.asarray(
                [
                    float(np.clip(float(x[0]), i0_lo, i0_hi)),
                    float(np.clip(float(x[1]), q0_lo, q0_hi)),
                    float(np.clip(float(x[2]), g_lo, g_hi)),
                    float(np.clip(float(x[3]), p_lo, p_hi)),
                ],
                dtype=float,
            )

        with self._maybe_quiet_qm_logs(cfg.quiet_qm_logs):
            baseline = self._measure_final(
                element,
                f_lo,
                f_if,
                i0_init,
                q0_init,
                gain_init,
                phase_init,
                write_db=save_to_db,
            )

            if not all(np.isfinite(float(baseline[k])) for k in ("P_des_dBm", "P_LO_dBm", "P_img_dBm")):
                raise RuntimeError("Invalid SA baseline tones (NaN/inf).")
            if abs(float(baseline["f_target"]) - float(baseline["f_image"])) <= cfg.sa_span_hz:
                raise RuntimeError(
                    "Target/image frequencies overlap within SA span. Check IF sign/sideband mapping."
                )

            dc_budget = max(6, int(cfg.dc_maxiter))
            iq_budget = max(6, int(cfg.iq_maxiter))
            total_budget = max(12, int(cfg.max_total_evals))
            if dc_budget + iq_budget > total_budget:
                dc_budget = max(6, min(dc_budget, total_budget // 2))
                iq_budget = max(6, total_budget - dc_budget)

            passes = max(1, min(2, int(cfg.minimizer_block_passes)))
            joint_maxiter = max(1, int(cfg.minimizer_joint_maxiter))
            xtol = max(float(cfg.minimizer_xtol), 1e-8)
            target_ref_dbm = (
                float(cfg.target_power_ref_dbm)
                if cfg.target_power_ref_dbm is not None
                else float(baseline["P_des_dBm"])
            )

            _logger.info(
                "Stage budgets: total<=%d evals (DC<=%d/pass, IQ<=%d/pass, passes=%d, joint_refine=%s)",
                total_budget,
                dc_budget,
                iq_budget,
                passes,
                bool(cfg.minimizer_joint_refine),
            )

            live_metrics = self._init_live_minimizer_metrics(
                title=f"{element}: minimizer live metrics (LO leak, IRR, cost)",
            ) if cfg.live_plot else None

            eval_count_dc = [0]
            eval_count_iq = [0]
            eval_count_joint = [0]
            eval_count_total = [0]
            opt_status: list[dict[str, Any]] = []

            dc_param_history = {
                "i0": [],
                "q0": [],
                "cost": [],
                "p_des_dbm": [],
                "p_lo_dbm": [],
                "p_image_dbm": [],
            }
            iq_param_history = {
                "gain": [],
                "phase": [],
                "cost": [],
                "p_des_dbm": [],
                "p_lo_dbm": [],
                "p_image_dbm": [],
            }

            x_current = _clip_to_bounds(np.asarray([i0_init, q0_init, gain_init, phase_init], dtype=float))
            best = {
                "x": np.asarray(x_current, dtype=float),
                "cost": float("inf"),
                "tones": None,
                "stage": "init",
            }

            def _record(stage: str, x: np.ndarray, cost: float, tones: dict[str, float]) -> None:
                if stage.startswith("dc"):
                    dc_param_history["i0"].append(float(x[0]))
                    dc_param_history["q0"].append(float(x[1]))
                    dc_param_history["cost"].append(float(cost))
                    dc_param_history["p_des_dbm"].append(float(tones.get("P_des_dBm", float("nan"))))
                    dc_param_history["p_lo_dbm"].append(float(tones.get("P_LO_dBm", float("nan"))))
                    dc_param_history["p_image_dbm"].append(float(tones.get("P_img_dBm", float("nan"))))
                elif stage.startswith("iq"):
                    iq_param_history["gain"].append(float(x[2]))
                    iq_param_history["phase"].append(float(x[3]))
                    iq_param_history["cost"].append(float(cost))
                    iq_param_history["p_des_dbm"].append(float(tones.get("P_des_dBm", float("nan"))))
                    iq_param_history["p_lo_dbm"].append(float(tones.get("P_LO_dBm", float("nan"))))
                    iq_param_history["p_image_dbm"].append(float(tones.get("P_img_dBm", float("nan"))))

            job = self._start_cw(element)
            try:
                def _cost_full(x_in: np.ndarray, stage: str) -> float:
                    x = _clip_to_bounds(np.asarray(x_in, dtype=float))
                    if eval_count_total[0] >= total_budget:
                        return penalty_cost

                    if stage.startswith("dc"):
                        eval_count_dc[0] += 1
                    elif stage.startswith("iq"):
                        eval_count_iq[0] += 1
                    elif stage.startswith("joint"):
                        eval_count_joint[0] += 1

                    eval_count_total[0] += 1
                    settle = cfg.dc_settle if stage.startswith("dc") else cfg.iq_settle

                    try:
                        self._apply_iq_correction(
                            element,
                            f_lo,
                            f_if,
                            float(x[2]),
                            float(x[3]),
                            float(x[0]),
                            float(x[1]),
                            write_db=write_per_point,
                            running_job=job,
                        )
                        time.sleep(settle)
                        tones = self._sa.measure_tones(f_lo, f_if)
                        cost = self._objective_cost_from_tones(
                            tones,
                            cfg=cfg,
                            p_target_ref_dbm=target_ref_dbm,
                        )
                    except Exception as exc:
                        _logger.debug("Penalizing invalid trial (%s): x=%s err=%s", stage, x.tolist(), exc)
                        cost = penalty_cost
                        tones = {
                            "P_des_dBm": float("nan"),
                            "P_LO_dBm": float("nan"),
                            "P_img_dBm": float("nan"),
                        }

                    _record(stage, x, float(cost), tones)
                    lo_leak = float("nan")
                    irr = float("nan")
                    if np.isfinite(float(tones.get("P_des_dBm", float("nan")))) and np.isfinite(float(tones.get("P_LO_dBm", float("nan")))):
                        lo_leak = float(tones["P_des_dBm"]) - float(tones["P_LO_dBm"])
                    if np.isfinite(float(tones.get("P_des_dBm", float("nan")))) and np.isfinite(float(tones.get("P_img_dBm", float("nan")))):
                        irr = float(tones["P_des_dBm"]) - float(tones["P_img_dBm"])
                    self._update_live_minimizer_metrics(
                        live_metrics,
                        lo_leak_dbc=lo_leak,
                        irr_dbc=irr,
                        cost=float(cost),
                        every=max(1, int(cfg.live_plot_every)),
                    )

                    if np.isfinite(cost) and float(cost) < float(best["cost"]):
                        best["x"] = np.asarray(x, dtype=float)
                        best["cost"] = float(cost)
                        best["tones"] = dict(tones)
                        best["stage"] = stage
                    return float(cost)

                _cost_full(x_current, "init")

                def _run_block(
                    *,
                    stage_name: str,
                    idx_a: int,
                    idx_b: int,
                    bounds_2d: list[tuple[float, float]],
                    maxiter: int,
                ) -> None:
                    nonlocal x_current
                    if eval_count_total[0] >= total_budget:
                        return
                    remaining = max(1, total_budget - eval_count_total[0])

                    def _cost_block(z: np.ndarray) -> float:
                        x_trial = np.asarray(x_current, dtype=float)
                        x_trial[idx_a] = float(z[0])
                        x_trial[idx_b] = float(z[1])
                        return _cost_full(x_trial, stage_name)

                    x0 = np.asarray([x_current[idx_a], x_current[idx_b]], dtype=float)
                    x0[0] = float(np.clip(float(x0[0]), bounds_2d[0][0], bounds_2d[0][1]))
                    x0[1] = float(np.clip(float(x0[1]), bounds_2d[1][0], bounds_2d[1][1]))

                    res = minimize(
                        _cost_block,
                        x0=x0,
                        method="Powell",
                        bounds=bounds_2d,
                        options={
                            "maxiter": max(1, int(maxiter)),
                            "maxfev": int(remaining),
                            "xtol": xtol,
                            "ftol": 1e-3,
                        },
                    )

                    z_best = np.asarray(res.x, dtype=float)
                    x_trial = np.asarray(x_current, dtype=float)
                    x_trial[idx_a] = float(np.clip(float(z_best[0]), bounds_2d[0][0], bounds_2d[0][1]))
                    x_trial[idx_b] = float(np.clip(float(z_best[1]), bounds_2d[1][0], bounds_2d[1][1]))
                    candidate_cost = _cost_full(x_trial, f"{stage_name}_final")
                    current_cost = _cost_full(x_current, f"{stage_name}_current")
                    if np.isfinite(candidate_cost) and candidate_cost <= current_cost:
                        x_current = _clip_to_bounds(x_trial)

                    opt_status.append(
                        {
                            "stage": stage_name,
                            "success": bool(getattr(res, "success", False)),
                            "status": int(getattr(res, "status", -1)),
                            "message": str(getattr(res, "message", "")),
                            "nfev": int(getattr(res, "nfev", 0)),
                            "nit": int(getattr(res, "nit", 0)) if hasattr(res, "nit") else 0,
                            "x": [float(v) for v in _clip_to_bounds(np.asarray(x_trial, dtype=float))],
                            "fun": float(candidate_cost),
                        }
                    )

                for pass_idx in range(passes):
                    _logger.info("Block pass %d/%d: DC block", pass_idx + 1, passes)
                    _run_block(
                        stage_name=f"dc_pass{pass_idx + 1}",
                        idx_a=0,
                        idx_b=1,
                        bounds_2d=[(i0_lo, i0_hi), (q0_lo, q0_hi)],
                        maxiter=dc_budget,
                    )
                    _logger.info("Block pass %d/%d: IQ block", pass_idx + 1, passes)
                    _run_block(
                        stage_name=f"iq_pass{pass_idx + 1}",
                        idx_a=2,
                        idx_b=3,
                        bounds_2d=[(g_lo, g_hi), (p_lo, p_hi)],
                        maxiter=iq_budget,
                    )

                if bool(cfg.minimizer_joint_refine) and eval_count_total[0] < total_budget:
                    remaining = max(1, total_budget - eval_count_total[0])
                    _logger.info("Final local joint refinement over (i0, q0, gain, phase)")
                    res_joint = minimize(
                        lambda x: _cost_full(np.asarray(x, dtype=float), "joint_refine"),
                        x0=np.asarray(x_current, dtype=float),
                        method="Powell",
                        bounds=[(i0_lo, i0_hi), (q0_lo, q0_hi), (g_lo, g_hi), (p_lo, p_hi)],
                        options={
                            "maxiter": int(joint_maxiter),
                            "maxfev": int(remaining),
                            "xtol": xtol,
                            "ftol": 1e-3,
                        },
                    )
                    x_joint = _clip_to_bounds(np.asarray(res_joint.x, dtype=float))
                    c_joint = _cost_full(x_joint, "joint_refine_final")
                    c_curr = _cost_full(x_current, "joint_refine_current")
                    if np.isfinite(c_joint) and c_joint <= c_curr:
                        x_current = np.asarray(x_joint, dtype=float)
                    opt_status.append(
                        {
                            "stage": "joint_refine",
                            "success": bool(getattr(res_joint, "success", False)),
                            "status": int(getattr(res_joint, "status", -1)),
                            "message": str(getattr(res_joint, "message", "")),
                            "nfev": int(getattr(res_joint, "nfev", 0)),
                            "nit": int(getattr(res_joint, "nit", 0)) if hasattr(res_joint, "nit") else 0,
                            "x": [float(v) for v in x_joint],
                            "fun": float(c_joint),
                        }
                    )
            finally:
                self._stop_cw(job)

            if cfg.live_plot:
                self._render_live_minimizer_metrics(live_metrics)
                self._publish_live_minimizer_metrics_snapshot(live_metrics)

            best_x = _clip_to_bounds(np.asarray(best["x"], dtype=float))
            best_i0, best_q0, best_g, best_p = [float(v) for v in best_x]
            final = self._measure_final(
                element,
                f_lo,
                f_if,
                best_i0,
                best_q0,
                best_g,
                best_p,
                write_db=save_to_db,
            )

        reverted_to_baseline = False
        if bool(getattr(cfg, "manual_revert_if_worse", True)) and self._is_result_worse(
            final,
            baseline,
            tolerance_db=float(getattr(cfg, "manual_revert_tolerance_db", 0.0)),
        ):
            _logger.warning(
                "Manual minimizer result for '%s' is worse than baseline; reverting to baseline calibration.",
                element,
            )
            candidate_final = dict(final)
            final = self._measure_final(
                element,
                f_lo,
                f_if,
                i0_init,
                q0_init,
                gain_init,
                phase_init,
                write_db=save_to_db,
            )
            best_i0, best_q0, best_g, best_p = i0_init, q0_init, gain_init, phase_init
            reverted_to_baseline = True
        else:
            candidate_final = None

        result = {
            "element": element,
            "f_lo": f_lo,
            "f_if": f_if,
            "i0": best_i0,
            "q0": best_q0,
            "gain": best_g,
            "phase": best_p,
            "eval_count_dc": int(eval_count_dc[0]),
            "eval_count_iq": int(eval_count_iq[0]),
            "eval_count_joint": int(eval_count_joint[0]),
            "eval_count_total": int(eval_count_total[0]),
            "optimizer_status": opt_status,
            "best_stage": str(best.get("stage", "")),
            "best_objective_cost": float(best.get("cost", float("inf"))),
            "dc_history": {
                "i0": [float(v) for v in dc_param_history["i0"]],
                "q0": [float(v) for v in dc_param_history["q0"]],
                "cost": [float(v) for v in dc_param_history["cost"]],
                "p_des_dbm": [float(v) for v in dc_param_history["p_des_dbm"]],
                "p_lo_dbm": [float(v) for v in dc_param_history["p_lo_dbm"]],
                "p_image_dbm": [float(v) for v in dc_param_history["p_image_dbm"]],
            },
            "iq_history": {
                "gain": [float(v) for v in iq_param_history["gain"]],
                "phase": [float(v) for v in iq_param_history["phase"]],
                "cost": [float(v) for v in iq_param_history["cost"]],
                "p_des_dbm": [float(v) for v in iq_param_history["p_des_dbm"]],
                "p_lo_dbm": [float(v) for v in iq_param_history["p_lo_dbm"]],
                "p_image_dbm": [float(v) for v in iq_param_history["p_image_dbm"]],
            },
            "target_power_ref_dbm": float(target_ref_dbm),
            "objective_mode": cfg.objective_mode,
            "reverted_to_baseline": reverted_to_baseline,
            **final,
        }
        if candidate_final is not None:
            result["candidate_manual"] = candidate_final
        result["baseline_before_manual"] = dict(baseline)
        if save_to_db:
            self._persist(result, method="manual_minimizer")

        self._cleanup_scratch()
        self._db_cache = None
        self._print_summary(result, saved=save_to_db)
        return result

    # ══════════════════════════════════════════════════════════
    #  Grid search helpers
    # ══════════════════════════════════════════════════════════
    def _grid_search_dc(
        self,
        element: str,
        f_lo: float,
        center_i: float,
        center_q: float,
        half_range: float,
        n_points: int,
        cfg: MixerCalibrationConfig | None = None,
    ) -> tuple[float, float, float]:
        """2-D grid over (I0, Q0); minimise P_LO.  CW must be running."""
        cfg = cfg or self._cfg
        i_vals = np.linspace(center_i - half_range, center_i + half_range, n_points)
        q_vals = np.linspace(center_q - half_range, center_q + half_range, n_points)
        best_P: float = np.inf
        best_i, best_q = center_i, center_q
        total = n_points * n_points
        done = 0
        live = self._init_live_heatmap(
            i_vals,
            q_vals,
            title=f"DC offset scan ({element})",
        ) if cfg.live_plot else None
        for ix, i0 in enumerate(tqdm(i_vals, desc="DC offset scan", unit="row", leave=False)):
            for iy, q0 in enumerate(q_vals):
                self._set_dc_offsets(element, float(i0), float(q0))
                time.sleep(cfg.dc_settle)
                P_lo = self._sa.measure_peak_power(f_lo)
                if P_lo < best_P:
                    best_P, best_i, best_q = P_lo, float(i0), float(q0)
                done += 1
                self._update_live_heatmap(
                    live,
                    ix=ix,
                    iy=iy,
                    value=float(P_lo),
                    best_x=float(best_i),
                    best_y=float(best_q),
                    every=max(1, int(cfg.live_plot_every)),
                    counter=done,
                )
            _logger.debug("  DC grid: %d/%d  best P_LO=%.1f dBm", done, total, best_P)
        return best_i, best_q, best_P

    def _grid_search_iq(
        self,
        element: str,
        f_lo: float,
        f_if: float,
        i0: float,
        q0: float,
        center_gain: float,
        center_phase: float,
        half_range_gain: float,
        half_range_phase: float,
        n_points: int,
        cfg: MixerCalibrationConfig | None = None,
        write_db: bool = False,
    ) -> tuple[float, float, float]:
        """2-D grid over (gain, phase); minimise P_img using live correction updates.

        Parameters
        ----------
        write_db : bool
            If False (default), each per-point ``_apply_iq_correction`` call
            writes to a scratch file instead of the canonical DB.
        """
        cfg = cfg or self._cfg
        g_vals = np.linspace(center_gain - half_range_gain, center_gain + half_range_gain, n_points)
        p_vals = np.linspace(center_phase - half_range_phase, center_phase + half_range_phase, n_points)
        best_P: float = np.inf
        best_g, best_p = center_gain, center_phase
        total = n_points * n_points
        done = 0
        live = self._init_live_heatmap(
            g_vals,
            p_vals,
            title=f"IQ correction scan ({element}, sideband={cfg.sideband})",
        ) if cfg.live_plot else None
        target_ref_dbm = float(cfg.target_power_ref_dbm) if cfg.target_power_ref_dbm is not None else None
        job = self._start_cw(element)
        self._set_dc_offsets(element, i0, q0)
        try:
            for ix, g in enumerate(tqdm(g_vals, desc="IQ correction scan", unit="row", leave=False)):
                for iy, p in enumerate(p_vals):
                    self._apply_iq_correction(
                        element,
                        f_lo,
                        f_if,
                        float(g),
                        float(p),
                        i0,
                        q0,
                        write_db=write_db,
                        running_job=job,
                    )
                    time.sleep(cfg.iq_settle)
                    tones = self._sa.measure_tones(f_lo, f_if)
                    if target_ref_dbm is None:
                        target_ref_dbm = float(tones["P_des_dBm"])
                    P_img = self._objective_cost_from_tones(
                        tones,
                        cfg=cfg,
                        p_target_ref_dbm=target_ref_dbm,
                    )
                    if P_img < best_P:
                        best_P, best_g, best_p = P_img, float(g), float(p)
                    done += 1
                    self._update_live_heatmap(
                        live,
                        ix=ix,
                        iy=iy,
                        value=float(P_img),
                        best_x=float(best_g),
                        best_y=float(best_p),
                        every=max(1, int(cfg.live_plot_every)),
                        counter=done,
                    )
                _logger.debug("  IQ grid: %d/%d  best P_img=%.1f dBm", done, total, best_P)
        finally:
            self._stop_cw(job)
        return best_g, best_p, best_P

    # ══════════════════════════════════════════════════════════
    #  Final measurement after calibration
    # ══════════════════════════════════════════════════════════
    def _measure_final(
        self,
        element: str,
        f_lo: float,
        f_if: float,
        i0: float,
        q0: float,
        gain: float,
        phase: float,
        *,
        write_db: bool = True,
    ) -> dict[str, float]:
        """Apply final parameters, start CW, measure all three tones."""
        self._apply_iq_correction(
            element,
            f_lo,
            f_if,
            gain,
            phase,
            i0,
            q0,
            write_db=write_db,
        )
        job = self._start_cw(element)
        time.sleep(self._cfg.iq_settle)
        tones = self._sa.measure_tones(f_lo, f_if)
        self._stop_cw(job)
        return tones

    # ══════════════════════════════════════════════════════════
    #  calibration_db.json persistence (Windows-safe)
    # ══════════════════════════════════════════════════════════
    def _read_db(self) -> dict:
        """Read calibration DB from disk (bypasses cache)."""
        with open(self._db_path, encoding="utf-8") as f:
            return json.load(f)

    def _get_db(self) -> dict:
        """Return in-memory DB cache if available, else read from disk."""
        if self._db_cache is not None:
            return self._db_cache
        return self._read_db()

    def _sanitize_db_numbers(self, obj: Any) -> Any:
        """Recursively coerce non-finite numeric values to 0.0 for JSON safety."""
        if isinstance(obj, dict):
            return {k: self._sanitize_db_numbers(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._sanitize_db_numbers(v) for v in obj]
        if isinstance(obj, tuple):
            return [self._sanitize_db_numbers(v) for v in obj]
        if isinstance(obj, np.generic):
            obj = obj.item()
        if isinstance(obj, float):
            return obj if np.isfinite(obj) else 0.0
        return obj

    def _write_db(self, db: dict) -> None:
        """Atomically write *db* to ``calibration_db.json``.

        Uses a uniquely-named temp file in the same directory and
        ``os.replace()`` for atomic semantics.  On Windows, includes a
        retry loop with exponential backoff to handle transient
        PermissionError from antivirus/indexer/editor locks.
        """
        parent = self._db_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        db_sanitized = self._sanitize_db_numbers(db)
        fd, tmp_path = tempfile.mkstemp(
            dir=parent, prefix=".mixcal_tmp_", suffix=".json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(db_sanitized, f, indent=4, allow_nan=False)
            # fd is now closed — safe to rename
            self._replace_with_retry(tmp_path, str(self._db_path))
        except BaseException:
            # Clean up temp file on any failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        # Update cache
        self._db_cache = db_sanitized

    @staticmethod
    def _replace_with_retry(src: str, dst: str) -> None:
        """``os.replace(src, dst)`` with retry on PermissionError (Windows)."""
        for attempt in range(_DB_WRITE_MAX_RETRIES):
            try:
                os.replace(src, dst)
                return
            except PermissionError:
                if attempt == _DB_WRITE_MAX_RETRIES - 1:
                    _logger.error(
                        "Failed to replace '%s' -> '%s' after %d attempts.",
                        src, dst, _DB_WRITE_MAX_RETRIES,
                    )
                    raise
                delay = _DB_WRITE_RETRY_BASE_DELAY * (2 ** attempt)
                _logger.warning(
                    "PermissionError replacing '%s' -> '%s' (attempt %d/%d), "
                    "retrying in %.2fs...",
                    src, dst, attempt + 1, _DB_WRITE_MAX_RETRIES, delay,
                )
                time.sleep(delay)

    def _write_scratch_db(self, db: dict) -> None:
        """Write *db* to a scratch file (not the canonical path).

        Kept for compatibility with older workflows that used scratch files
        for trial correction snapshots.
        The scratch file lives alongside the real DB with a ``.scratch``
        extension.
        """
        scratch = self._db_path.with_suffix(".scratch.json")
        db_sanitized = self._sanitize_db_numbers(db)
        fd, tmp_path = tempfile.mkstemp(
            dir=self._db_path.parent, prefix=".mixcal_scratch_", suffix=".json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(db_sanitized, f, indent=4, allow_nan=False)
            self._replace_with_retry(tmp_path, str(scratch))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        # Update cache so subsequent reads use the latest trial values
        self._db_cache = db_sanitized

    def _cleanup_scratch(self) -> None:
        """Remove the scratch DB file if it exists."""
        scratch = self._db_path.with_suffix(".scratch.json")
        try:
            if scratch.exists():
                scratch.unlink()
        except OSError as e:
            _logger.debug("Could not remove scratch file %s: %s", scratch, e)

    # ── element → mode ID resolution ──────────────────────────
    def _resolve_mode_id(self, db: dict, element: str) -> int:
        """Map element name → numeric mode_id via octave channel."""
        tup = self._hw._element_octave_rf_out(element)
        if tup is None:
            raise ValueError(f"Cannot resolve octave RF output for element '{element}'")
        octave_name, rf_port = tup
        for mid, info in db.get("modes", {}).items():
            if info.get("octave_name") == octave_name and info.get("octave_channel") == rf_port:
                return int(mid)
        raise ValueError(
            f"No calibration_db mode found for {octave_name} channel {rf_port} (element '{element}')"
        )

    def _resolve_lo_mode_id(self, db: dict, element: str) -> int:
        """Find the lo_mode entry for the element's mode (latest)."""
        mode_id = self._resolve_mode_id(db, element)
        for lmid, info in db.get("lo_modes", {}).items():
            if info.get("mode_id") == mode_id:
                return int(lmid)
        raise ValueError(f"No lo_mode found for mode_id={mode_id}")

    def _resolve_if_mode_id(self, db: dict, element: str) -> int:
        """Find the if_mode entry for the element's lo_mode (latest)."""
        lo_mode_id = self._resolve_lo_mode_id(db, element)
        for imid, info in db.get("if_modes", {}).items():
            if info.get("lo_mode_id") == lo_mode_id:
                return int(imid)
        raise ValueError(f"No if_mode found for lo_mode_id={lo_mode_id}")

    def _persist(self, result: dict, *, method: str) -> None:
        """Write final calibration result to ``calibration_db.json``."""
        db = self._read_db()
        lo_mode_id = self._resolve_lo_mode_id(db, result["element"])
        if_mode_id = self._resolve_if_mode_id(db, result["element"])

        method_norm = "manual" if str(method).startswith("manual") else str(method)

        ts = time.time()
        db["lo_cal"][str(lo_mode_id)] = {
            "i0": result["i0"],
            "q0": result["q0"],
            "dc_gain": result["gain"],
            "dc_phase": result["phase"],
            "temperature": None,
            "timestamp": ts,
            "method": method_norm,
        }
        db["if_cal"][str(if_mode_id)] = {
            "gain": result["gain"],
            "phase": result["phase"],
            "temperature": None,
            "timestamp": ts,
            "method": method_norm,
        }
        self._write_db(db)
        _logger.info("Calibration saved to %s (method=%s)", self._db_path, method_norm)

    # ══════════════════════════════════════════════════════════
    #  Summary output
    # ══════════════════════════════════════════════════════════
    def _print_summary(self, result: dict, *, saved: bool) -> None:
        f_lo = result["f_lo"]
        f_if = result["f_if"]
        sideband = result.get("sideband", self._cfg.sideband)
        if sideband == "usb":
            f_target = f_lo + abs(f_if)
            f_image = f_lo - abs(f_if)
        else:
            f_target = f_lo - abs(f_if)
            f_image = f_lo + abs(f_if)
        lines = [
            "",
            "=" * 60,
            f"  IQ Mixer Calibration — {result['element']}",
            "=" * 60,
            f"  LO:  {f_lo / 1e9:.6f} GHz",
            f"  IF:  {f_if / 1e6:.2f} MHz",
            f"  Sideband target: {sideband.upper()}",
            "-" * 60,
            f"  P_target  @ {f_target / 1e9:.6f} GHz : {result.get('P_des_dBm', float('nan')):+.1f} dBm",
            f"  P_LO   @ {f_lo / 1e9:.6f} GHz : {result.get('P_LO_dBm', float('nan')):+.1f} dBm"
            f"   (LO leak {result.get('LO_leak_dBc', float('nan')):+.1f} dBc)",
            f"  P_image  @ {f_image / 1e9:.6f} GHz : {result.get('P_img_dBm', float('nan')):+.1f} dBm"
            f"   (IRR {result.get('IRR_dBc', float('nan')):+.1f} dBc)",
            "-" * 60,
            f"  DC offsets:  I0 = {result['i0']:+.6f}   Q0 = {result['q0']:+.6f}",
            f"  IQ corr:     gain = {result['gain']:+.6f}   phase = {result['phase']:+.6f} rad",
            "-" * 60,
            f"  Saved to calibration_db.json: {'YES' if saved else 'NO'}",
            "=" * 60,
            "",
        ]
        summary = "\n".join(lines)
        print(summary)
        _logger.info(summary)
