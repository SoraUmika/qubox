"""Wigner tomography and SNAP gate optimization."""
from __future__ import annotations

from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase
from ..result import AnalysisResult
from ...analysis import post_process as pp
from ...analysis.cQED_plottings import plot_wigner
from ...hardware.program_runner import RunResult
from ...programs import api as cQED_programs


class StorageWignerTomography(ExperimentBase):
    """Wigner function reconstruction of storage cavity state.

    Sweeps displacement amplitudes over phase-space (x, p) grid and
    measures mode-parity to reconstruct the Wigner function.
    """

    def run(
        self,
        gates: list,
        x_vals: np.ndarray | list[float],
        p_vals: np.ndarray | list[float],
        base_alpha: float = 10.0,
        r90_pulse: str = "x90",
        n_avg: int = 200,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.storage_wigner_tomography(
            attr.qb_el, attr.st_el,
            gates, np.asarray(x_vals), np.asarray(p_vals),
            base_alpha, r90_pulse,
            attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("x_vals", np.asarray(x_vals)),
                pp.proc_attach("p_vals", np.asarray(p_vals)),
            ],
        )
        self.save_output(result.output, "wignerTomography")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        S = result.output.extract("S")
        x_vals = result.output.extract("x_vals")
        p_vals = result.output.extract("p_vals")
        metrics: dict[str, Any] = {}

        if S is not None and x_vals is not None and p_vals is not None:
            # Parity data → Wigner function W(x, p)
            parity = np.real(S)
            nx, np_ = len(x_vals), len(p_vals)
            if parity.size == nx * np_:
                W = (2 / np.pi) * parity.reshape(nx, np_)
                metrics["W_min"] = float(W.min())
                metrics["W_max"] = float(W.max())
                negativity = float(-np.sum(W[W < 0]))
                metrics["negativity"] = negativity
            else:
                metrics["n_points"] = int(parity.size)

        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S = analysis.data.get("S")
        x_vals = analysis.data.get("x_vals")
        p_vals = analysis.data.get("p_vals")
        if S is None or x_vals is None or p_vals is None:
            return None

        parity = np.real(S)
        nx, np_ = len(x_vals), len(p_vals)
        if parity.size == nx * np_:
            W = (2 / np.pi) * parity.reshape(nx, np_)
            plot_wigner(W, x_vals, p_vals)
            return plt.gcf()

        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure
        ax.plot(parity, "o-", ms=3)
        ax.set_xlabel("Point Index")
        ax.set_ylabel("Parity")
        ax.set_title("Wigner Tomography (raw)")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig


class SNAPOptimization(ExperimentBase):
    """SNAP gate optimization with Fock-resolved tomography.

    Combines SNAP + displacement gates with Fock-resolved state
    tomography to optimize SNAP gate angles.

    Note: analyze/plot logic overlaps with
    :class:`~qubox_v2.experiments.tomography.fock_tomo.FockResolvedStateTomography`.
    SNAPOptimization uses ``cQED_programs.SQR_state_tomography`` (gate-level
    control) whereas FockResolvedStateTomography uses
    ``cQED_programs.fock_resolved_state_tomography`` (callable state-prep).
    """

    def run(
        self,
        snap_gate: Any,
        disp1_gate: Any,
        fock_probe_fqs: list[float] | np.ndarray,
        *,
        sel_r180: str = "sel_x180",
        sel_rxp90: str = "sel_x90",
        sel_rym90: str = "sel_yn90",
        n_avg: int = 100,
        qb_x180: str = "x180",
        post_meas_wait_clks: int = 0,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.SQR_state_tomography(
            attr.qb_el, attr.st_el,
            snap_gate, disp1_gate,
            np.asarray(fock_probe_fqs),
            sel_r180=sel_r180,
            sel_rxp90=sel_rxp90,
            sel_rym90=sel_rym90,
            qb_x180=qb_x180,
            post_meas_wait_clks=post_meas_wait_clks,
            therm_clks=attr.qb_therm_clks,
            n_avg=n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[pp.proc_default],
        )
        self.save_output(result.output, "snapOptimization")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        S = result.output.extract("S")
        metrics: dict[str, Any] = {}

        if S is not None:
            mag = np.abs(S)
            if mag.ndim == 2:
                # Per-Fock tomography axes (n_fock, 3) for sx, sy, sz
                n_fock = mag.shape[0]
                metrics["n_fock"] = n_fock
                fock_pops = np.mean(mag, axis=1)
                metrics["fock_pops"] = fock_pops.tolist()
            else:
                metrics["n_points"] = int(len(mag))

        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S = analysis.data.get("S")
        if S is None:
            return None

        mag = np.abs(S)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure

        if mag.ndim == 2:
            for n in range(mag.shape[0]):
                ax.plot(mag[n], "o-", ms=3, label=f"Fock |{n}>")
            ax.legend()
        else:
            ax.plot(mag, "o-", ms=3)

        ax.set_xlabel("Tomography Axis")
        ax.set_ylabel("Magnitude")
        ax.set_title("SNAP Optimization - State Tomography")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig
