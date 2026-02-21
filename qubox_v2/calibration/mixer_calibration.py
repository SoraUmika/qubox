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

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ..programs import cQED_programs

_logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────
@dataclass
class MixerCalibrationConfig:
    """All tunable parameters for manual mixer calibration."""

    # SA measurement
    sa_span_hz: float = 2e6
    sa_rbw: float = 1e3
    sa_vbw: float = 1e3
    sa_level: float = 0.0
    sa_avg: int = 5

    # DC offset grid search
    dc_coarse_range: float = 0.1    # ±V
    dc_coarse_n: int = 11
    dc_fine_range: float = 0.02
    dc_fine_n: int = 11

    # IQ correction grid search
    iq_gain_range: float = 0.1
    iq_phase_range: float = 0.2     # rad
    iq_coarse_n: int = 9
    iq_fine_range_gain: float = 0.02
    iq_fine_range_phase: float = 0.04
    iq_fine_n: int = 9

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


# ──────────────────────────────────────────────────────────────────
# SA Measurement Helper
# ──────────────────────────────────────────────────────────────────
class SAMeasurementHelper:
    """Narrow-span peak-power measurement at three mixer tones."""

    def __init__(self, sa_device: Any, config: MixerCalibrationConfig):
        self._sa = sa_device
        self._cfg = config

    # ── single-tone measurement ────────────────────────────────
    def measure_peak_power(self, center_hz: float) -> float:
        """Return peak power (dBm) in a narrow span around *center_hz*."""
        self._sa.configure(
            center=center_hz,
            span=self._cfg.sa_span_hz,
            rbw=self._cfg.sa_rbw,
            vbw=self._cfg.sa_vbw,
            level=self._cfg.sa_level,
            force=True,
        )
        _freq, _tr_min, tr_max = self._sa.sweep(average_num=self._cfg.sa_avg)
        return float(np.max(tr_max))

    # ── three-tone measurement ─────────────────────────────────
    def measure_tones(self, f_lo: float, f_if: float) -> dict[str, float]:
        """Measure desired, LO-leak, and image tones; compute dBc metrics.

        Assumes LSB convention: f_des = f_LO − |f_IF|.
        """
        f_des = f_lo - abs(f_if)
        f_img = f_lo + abs(f_if)

        P_des = self.measure_peak_power(f_des)
        P_lo = self.measure_peak_power(f_lo)
        P_img = self.measure_peak_power(f_img)

        return {
            "P_des_dBm": P_des,
            "P_LO_dBm": P_lo,
            "P_img_dBm": P_img,
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
    ) -> None:
        """Write trial gain/phase + DC offsets to the calibration DB and reopen QM."""
        db = self._read_db()
        lo_mode_id = self._resolve_lo_mode_id(db, element)
        if_mode_id = self._resolve_if_mode_id(db, element)

        db["lo_cal"][str(lo_mode_id)].update(
            {"i0": i0, "q0": q0, "timestamp": time.time(), "method": "manual_trial"}
        )
        db["if_cal"][str(if_mode_id)].update(
            {"gain": gain, "phase": phase, "timestamp": time.time(), "method": "manual_trial"}
        )
        self._write_db(db)
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
    ) -> dict:
        """Two-stage coarse→fine grid search: DC offsets then IQ correction.

        Returns a dict with optimal parameters + measured tone powers.
        """
        _logger.info(
            "scan_2d: element=%s  LO=%.4f GHz  IF=%.2f MHz",
            element, f_lo / 1e9, f_if / 1e6,
        )

        # ── Stage A: DC offsets ───────────────────────────────
        _logger.info("Stage A: DC offset optimisation (coarse)")
        job = self._start_cw(element)
        best_i0, best_q0, _ = self._grid_search_dc(
            element, f_lo,
            center_i=0.0, center_q=0.0,
            half_range=self._cfg.dc_coarse_range,
            n_points=self._cfg.dc_coarse_n,
        )
        _logger.info("Stage A: DC offset optimisation (fine)")
        best_i0, best_q0, best_P_LO = self._grid_search_dc(
            element, f_lo,
            center_i=best_i0, center_q=best_q0,
            half_range=self._cfg.dc_fine_range,
            n_points=self._cfg.dc_fine_n,
        )
        self._set_dc_offsets(element, best_i0, best_q0)
        self._stop_cw(job)
        _logger.info(
            "Stage A done: I0=%.6f  Q0=%.6f  P_LO=%.1f dBm",
            best_i0, best_q0, best_P_LO,
        )

        # ── Stage B: IQ correction ────────────────────────────
        _logger.info("Stage B: IQ correction optimisation (coarse)")
        best_g, best_p, _ = self._grid_search_iq(
            element, f_lo, f_if,
            best_i0, best_q0,
            center_gain=0.0, center_phase=0.0,
            half_range_gain=self._cfg.iq_gain_range,
            half_range_phase=self._cfg.iq_phase_range,
            n_points=self._cfg.iq_coarse_n,
        )
        _logger.info("Stage B: IQ correction optimisation (fine)")
        best_g, best_p, best_P_img = self._grid_search_iq(
            element, f_lo, f_if,
            best_i0, best_q0,
            center_gain=best_g, center_phase=best_p,
            half_range_gain=self._cfg.iq_fine_range_gain,
            half_range_phase=self._cfg.iq_fine_range_phase,
            n_points=self._cfg.iq_fine_n,
        )
        _logger.info(
            "Stage B done: gain=%.6f  phase=%.6f  P_img=%.1f dBm",
            best_g, best_p, best_P_img,
        )

        # ── Final measurement ─────────────────────────────────
        final = self._measure_final(element, f_lo, f_if, best_i0, best_q0, best_g, best_p)
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
    ) -> dict:
        """Coordinate-descent optimiser: DC offsets then IQ correction."""
        from scipy.optimize import minimize

        _logger.info(
            "minimizer: element=%s  LO=%.4f GHz  IF=%.2f MHz",
            element, f_lo / 1e9, f_if / 1e6,
        )
        cfg = self._cfg

        # ── Stage A: DC offsets (fast, CW stays running) ──────
        _logger.info("Stage A: DC offset minimisation")
        job = self._start_cw(element)

        eval_count_dc = [0]

        def _cost_dc(x):
            self._set_dc_offsets(element, x[0], x[1])
            time.sleep(cfg.dc_settle)
            p = self._sa.measure_peak_power(f_lo)
            eval_count_dc[0] += 1
            if eval_count_dc[0] % 10 == 0:
                _logger.debug("  DC eval %d: I0=%.5f Q0=%.5f  P_LO=%.1f", eval_count_dc[0], x[0], x[1], p)
            return p

        res_dc = minimize(
            _cost_dc,
            x0=[0.0, 0.0],
            method="Nelder-Mead",
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
        _logger.info("Stage B: IQ correction minimisation")
        f_img = f_lo + abs(f_if)
        eval_count_iq = [0]

        def _cost_iq(x):
            self._apply_iq_correction(element, x[0], x[1], best_i0, best_q0)
            job_inner = self._start_cw(element)
            self._set_dc_offsets(element, best_i0, best_q0)
            time.sleep(cfg.iq_settle)
            p = self._sa.measure_peak_power(f_img)
            self._stop_cw(job_inner)
            eval_count_iq[0] += 1
            _logger.debug("  IQ eval %d: g=%.5f ph=%.5f  P_img=%.1f", eval_count_iq[0], x[0], x[1], p)
            return p

        res_iq = minimize(
            _cost_iq,
            x0=[0.0, 0.0],
            method="Nelder-Mead",
            options={
                "maxiter": cfg.minimizer_maxiter,
                "xatol": cfg.minimizer_xtol,
                "fatol": 0.5,
                "adaptive": True,
            },
        )
        best_g, best_p = float(res_iq.x[0]), float(res_iq.x[1])
        _logger.info(
            "Stage B done (%d evals): gain=%.6f  phase=%.6f  P_img=%.1f dBm",
            res_iq.nfev, best_g, best_p, float(res_iq.fun),
        )

        # ── Final measurement ─────────────────────────────────
        final = self._measure_final(element, f_lo, f_if, best_i0, best_q0, best_g, best_p)
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
    ) -> tuple[float, float, float]:
        """2-D grid over (I0, Q0); minimise P_LO.  CW must be running."""
        i_vals = np.linspace(center_i - half_range, center_i + half_range, n_points)
        q_vals = np.linspace(center_q - half_range, center_q + half_range, n_points)
        best_P: float = np.inf
        best_i, best_q = center_i, center_q
        total = n_points * n_points
        done = 0
        for i0 in i_vals:
            for q0 in q_vals:
                self._set_dc_offsets(element, float(i0), float(q0))
                time.sleep(self._cfg.dc_settle)
                P_lo = self._sa.measure_peak_power(f_lo)
                if P_lo < best_P:
                    best_P, best_i, best_q = P_lo, float(i0), float(q0)
                done += 1
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
    ) -> tuple[float, float, float]:
        """2-D grid over (gain, phase); minimise P_img.  Requires QM reopen per point."""
        g_vals = np.linspace(center_gain - half_range_gain, center_gain + half_range_gain, n_points)
        p_vals = np.linspace(center_phase - half_range_phase, center_phase + half_range_phase, n_points)
        f_img = f_lo + abs(f_if)
        best_P: float = np.inf
        best_g, best_p = center_gain, center_phase
        total = n_points * n_points
        done = 0
        for g in g_vals:
            for p in p_vals:
                self._apply_iq_correction(element, float(g), float(p), i0, q0)
                job = self._start_cw(element)
                self._set_dc_offsets(element, i0, q0)
                time.sleep(self._cfg.iq_settle)
                P_img = self._sa.measure_peak_power(f_img)
                self._stop_cw(job)
                if P_img < best_P:
                    best_P, best_g, best_p = P_img, float(g), float(p)
                done += 1
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
    ) -> dict[str, float]:
        """Apply final parameters, start CW, measure all three tones."""
        self._apply_iq_correction(element, gain, phase, i0, q0)
        job = self._start_cw(element)
        self._set_dc_offsets(element, i0, q0)
        time.sleep(self._cfg.iq_settle)
        tones = self._sa.measure_tones(f_lo, f_if)
        self._stop_cw(job)
        return tones

    # ══════════════════════════════════════════════════════════
    #  calibration_db.json persistence
    # ══════════════════════════════════════════════════════════
    def _read_db(self) -> dict:
        with open(self._db_path) as f:
            return json.load(f)

    def _write_db(self, db: dict) -> None:
        tmp = self._db_path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(db, f, indent=4)
        tmp.replace(self._db_path)

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
        lines = [
            "",
            "=" * 60,
            f"  IQ Mixer Calibration — {result['element']}",
            "=" * 60,
            f"  LO:  {f_lo / 1e9:.6f} GHz",
            f"  IF:  {f_if / 1e6:.2f} MHz",
            "-" * 60,
            f"  P_des  @ {(f_lo - abs(f_if)) / 1e9:.6f} GHz : {result.get('P_des_dBm', float('nan')):+.1f} dBm",
            f"  P_LO   @ {f_lo / 1e9:.6f} GHz : {result.get('P_LO_dBm', float('nan')):+.1f} dBm"
            f"   (LO leak {result.get('LO_leak_dBc', float('nan')):+.1f} dBc)",
            f"  P_img  @ {(f_lo + abs(f_if)) / 1e9:.6f} GHz : {result.get('P_img_dBm', float('nan')):+.1f} dBm"
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
