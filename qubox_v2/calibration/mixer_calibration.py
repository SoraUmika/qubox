# qubox_v2/calibration/mixer_calibration.py
"""
Manual IQ mixer calibration via external spectrum analyzer (SA124B).

Provides two calibration methods, both operating in two separable stages:
  Stage A — Minimise LO feedthrough by scanning DC offsets (I0, Q0).
  Stage B — Minimise image sideband by scanning gain/phase imbalance correction.

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

from ..programs import cQED_programs

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
    **Minimiser** — Nelder-Mead derivative-free optimiser settings.
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

    # CW tone
    cw_pulse: str = "const_x180"
    cw_gain: float = 1.0
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

    # Notebook UX controls
    quiet_qm_logs: bool = False
    live_plot: bool = False
    live_plot_every: int = 1


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
        return float(wc * p_carrier_dbm + wi * p_image_dbm - wt * p_target_dbm)

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

    # ────────── CW tone management ────────────────────────────
    def _start_cw(self, element: str):
        """Start an infinite CW tone on *element*. Returns a QM job handle."""
        prog = cQED_programs.continuous_wave(
            target_el=element,
            pulse=self._cfg.cw_pulse,
            gain=self._cfg.cw_gain,
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

    # ────────── IQ correction (requires QM reopen) ────────────
    def _apply_iq_correction(
        self,
        element: str,
        gain: float,
        phase: float,
        i0: float,
        q0: float,
        *,
        write_db: bool = True,
    ) -> None:
        """Write trial gain/phase + DC offsets to the calibration DB and reopen QM.

        Parameters
        ----------
        write_db : bool
            If False, update the in-memory cache and write to a temporary
            scratch file instead of the canonical calibration_db.json.
            The QM still reopens using the scratch file so corrections take
            effect, but the canonical DB is not mutated.
        """
        db = self._get_db()
        lo_mode_id = self._resolve_lo_mode_id(db, element)
        if_mode_id = self._resolve_if_mode_id(db, element)

        db["lo_cal"][str(lo_mode_id)].update(
            {"i0": i0, "q0": q0, "timestamp": time.time(), "method": "manual_trial"}
        )
        db["if_cal"][str(if_mode_id)].update(
            {"gain": gain, "phase": phase, "timestamp": time.time(), "method": "manual_trial"}
        )

        if write_db:
            self._write_db(db)
        else:
            # Write to a scratch file so QM can reopen with the trial values,
            # but do NOT touch the canonical calibration_db.json.
            self._write_scratch_db(db)

        self._hw.open_qm()

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
        never written.  Trial IQ corrections use a scratch file so QM can
        reopen with trial values without mutating the persistent DB.
        """
        cfg = self._cfg
        if config_overrides:
            cfg = dataclasses.replace(cfg, **config_overrides)

        # Pre-load the DB into cache to avoid per-point reads
        self._db_cache = self._read_db()

        # Determine per-point write behaviour
        write_db_mode = cfg.write_db_mode if save_to_db else "final_only"
        # For IQ grid, whether each point writes the canonical DB
        iq_write_per_point = (write_db_mode == "per_point") and save_to_db

        _logger.info(
            "scan_2d: element=%s  LO=%.4f GHz  IF=%.2f MHz  sideband=%s  objective=%s  save_to_db=%s  write_mode=%s",
            element, f_lo / 1e9, f_if / 1e6, cfg.sideband, cfg.objective_mode, save_to_db, write_db_mode,
        )

        with self._maybe_quiet_qm_logs(cfg.quiet_qm_logs):
            # ── Stage A: DC offsets ───────────────────────────────
            _logger.info(
                "Stage A: DC offset optimisation (coarse %dx%d = %d points)",
                cfg.dc_coarse_n, cfg.dc_coarse_n, cfg.dc_coarse_n ** 2,
            )
            job = self._start_cw(element)
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
        result = {
            "element": element,
            "f_lo": f_lo,
            "f_if": f_if,
            "i0": best_i0,
            "q0": best_q0,
            "gain": best_g,
            "phase": best_p,
            **final,
        }
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
        """Coordinate-descent optimiser: DC offsets then IQ correction.

        Any keyword argument matching a ``MixerCalibrationConfig`` field
        overrides the corresponding value for this run only.

        When ``save_to_db=False``, the canonical ``calibration_db.json`` is
        never written.  Trial IQ corrections use a scratch file.
        """
        from scipy.optimize import minimize

        _logger.info(
            "minimizer: element=%s  LO=%.4f GHz  IF=%.2f MHz  sideband=%s  objective=%s  save_to_db=%s",
            element, f_lo / 1e9, f_if / 1e6, self._cfg.sideband, self._cfg.objective_mode, save_to_db,
        )
        cfg = self._cfg
        if config_overrides:
            cfg = dataclasses.replace(cfg, **config_overrides)

        # Pre-load the DB into cache
        self._db_cache = self._read_db()
        write_per_point = (cfg.write_db_mode == "per_point") and save_to_db

        with self._maybe_quiet_qm_logs(cfg.quiet_qm_logs):
            # ── Stage A: DC offsets (fast, CW stays running) ──────
            _logger.info("Stage A: DC offset minimisation (maxiter=%d)", cfg.minimizer_maxiter)
            job = self._start_cw(element)

            dc_hist = self._init_live_history(
                title=f"{element}: DC minimizer history",
                ylabel="P_LO (dBm)",
            ) if cfg.live_plot else None
            eval_count_dc = [0]

            def _cost_dc(x):
                self._set_dc_offsets(element, x[0], x[1])
                time.sleep(cfg.dc_settle)
                p = self._sa.measure_peak_power(f_lo)
                eval_count_dc[0] += 1
                self._update_live_history(dc_hist, p, every=max(1, int(cfg.live_plot_every)))
                if eval_count_dc[0] % 10 == 0:
                    _logger.debug("  DC eval %d: I0=%.5f Q0=%.5f  P_LO=%.1f", eval_count_dc[0], x[0], x[1], p)
                return p

            def _dc_callback(xk):
                _logger.info("  DC opt step: I0=%.5f Q0=%.5f  (%d evals)", xk[0], xk[1], eval_count_dc[0])

            res_dc = minimize(
                _cost_dc,
                x0=[0.0, 0.0],
                method="Nelder-Mead",
                callback=_dc_callback,
                options={
                    "maxiter": cfg.minimizer_maxiter,
                    "xatol": cfg.minimizer_xtol,
                    "fatol": 0.5,
                    "adaptive": True,
                },
            )
            best_i0, best_q0 = float(res_dc.x[0]), float(res_dc.x[1])
            self._set_dc_offsets(element, best_i0, best_q0)
            self._stop_cw(job)
            _logger.info(
                "Stage A done (%d evals): I0=%.6f  Q0=%.6f  P_LO=%.1f dBm",
                res_dc.nfev, best_i0, best_q0, float(res_dc.fun),
            )

            # ── Stage B: IQ correction (slower, QM reopen per eval) ─
            _logger.info("Stage B: IQ correction minimisation (maxiter=%d)", cfg.minimizer_maxiter)
            eval_count_iq = [0]
            iq_hist = self._init_live_history(
                title=f"{element}: IQ minimizer objective history",
                ylabel="Objective",
            ) if cfg.live_plot else None

            def _cost_iq(x):
                self._apply_iq_correction(
                    element, x[0], x[1], best_i0, best_q0,
                    write_db=write_per_point,
                )
                job_inner = self._start_cw(element)
                self._set_dc_offsets(element, best_i0, best_q0)
                time.sleep(cfg.iq_settle)
                tones = self._sa.measure_tones(f_lo, f_if)
                self._stop_cw(job_inner)
                cost = self._objective_cost(
                    p_target_dbm=float(tones["P_des_dBm"]),
                    p_carrier_dbm=float(tones["P_LO_dBm"]),
                    p_image_dbm=float(tones["P_img_dBm"]),
                    cfg=cfg,
                )
                eval_count_iq[0] += 1
                self._update_live_history(iq_hist, cost, every=max(1, int(cfg.live_plot_every)))
                _logger.debug(
                    "  IQ eval %d: g=%.5f ph=%.5f  P_target=%.1f P_lo=%.1f P_img=%.1f cost=%.3f",
                    eval_count_iq[0], x[0], x[1], tones["P_des_dBm"], tones["P_LO_dBm"], tones["P_img_dBm"], cost,
                )
                return cost

            def _iq_callback(xk):
                _logger.info("  IQ opt step: gain=%.5f phase=%.5f  (%d evals)", xk[0], xk[1], eval_count_iq[0])

            res_iq = minimize(
                _cost_iq,
                x0=[0.0, 0.0],
                method="Nelder-Mead",
                callback=_iq_callback,
                options={
                    "maxiter": cfg.minimizer_maxiter,
                    "xatol": cfg.minimizer_xtol,
                    "fatol": 0.5,
                    "adaptive": True,
                },
            )
            best_g, best_p = float(res_iq.x[0]), float(res_iq.x[1])
            _logger.info(
                "Stage B done (%d evals): gain=%.6f  phase=%.6f  objective=%.3f",
                res_iq.nfev, best_g, best_p, float(res_iq.fun),
            )

            # ── Final measurement ─────────────────────────────────
            final = self._measure_final(
                element, f_lo, f_if, best_i0, best_q0, best_g, best_p,
                write_db=save_to_db,
            )
        result = {
            "element": element,
            "f_lo": f_lo,
            "f_if": f_if,
            "i0": best_i0,
            "q0": best_q0,
            "gain": best_g,
            "phase": best_p,
            **final,
        }
        if save_to_db:
            self._persist(result, method="manual_minimizer")

        # Cleanup scratch file and cache
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
        """2-D grid over (gain, phase); minimise P_img.  Requires QM reopen per point.

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
        for ix, g in enumerate(tqdm(g_vals, desc="IQ correction scan", unit="row", leave=False)):
            for iy, p in enumerate(p_vals):
                self._apply_iq_correction(
                    element, float(g), float(p), i0, q0,
                    write_db=write_db,
                )
                job = self._start_cw(element)
                self._set_dc_offsets(element, i0, q0)
                time.sleep(cfg.iq_settle)
                tones = self._sa.measure_tones(f_lo, f_if)
                P_img = self._objective_cost(
                    p_target_dbm=float(tones["P_des_dBm"]),
                    p_carrier_dbm=float(tones["P_LO_dBm"]),
                    p_image_dbm=float(tones["P_img_dBm"]),
                    cfg=cfg,
                )
                self._stop_cw(job)
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
        self._apply_iq_correction(element, gain, phase, i0, q0, write_db=write_db)
        job = self._start_cw(element)
        self._set_dc_offsets(element, i0, q0)
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

    def _write_db(self, db: dict) -> None:
        """Atomically write *db* to ``calibration_db.json``.

        Uses a uniquely-named temp file in the same directory and
        ``os.replace()`` for atomic semantics.  On Windows, includes a
        retry loop with exponential backoff to handle transient
        PermissionError from antivirus/indexer/editor locks.
        """
        parent = self._db_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=parent, prefix=".mixcal_tmp_", suffix=".json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(db, f, indent=4)
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
        self._db_cache = db

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

        Used when ``save_to_db=False`` so QM can reopen with trial
        correction values without modifying the canonical DB.
        The scratch file lives alongside the real DB with a ``.scratch``
        extension.
        """
        scratch = self._db_path.with_suffix(".scratch.json")
        fd, tmp_path = tempfile.mkstemp(
            dir=self._db_path.parent, prefix=".mixcal_scratch_", suffix=".json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(db, f, indent=4)
            self._replace_with_retry(tmp_path, str(scratch))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        # Update cache so subsequent reads use the latest trial values
        self._db_cache = db

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

        ts = time.time()
        db["lo_cal"][str(lo_mode_id)] = {
            "i0": result["i0"],
            "q0": result["q0"],
            "dc_gain": result["gain"],
            "dc_phase": result["phase"],
            "temperature": None,
            "timestamp": ts,
            "method": method,
        }
        db["if_cal"][str(if_mode_id)] = {
            "gain": result["gain"],
            "phase": result["phase"],
            "temperature": None,
            "timestamp": ts,
            "method": method,
        }
        self._write_db(db)
        _logger.info("Calibration saved to %s (method=%s)", self._db_path, method)

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
