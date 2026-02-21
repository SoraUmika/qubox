"""Wigner tomography and SNAP gate optimization."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..experiment_base import ExperimentBase
from ...analysis import post_process as pp
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs


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


class SNAPOptimization(ExperimentBase):
    """SNAP gate optimization with Fock-resolved tomography.

    Combines SNAP + displacement gates with Fock-resolved state
    tomography to optimize SNAP gate angles.
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
