"""Storage resonator spectroscopy and dynamics experiments."""
from __future__ import annotations

from typing import Any, Union

import numpy as np

from ..experiment_base import (
    ExperimentBase, create_if_frequencies, create_clks_array,
    make_lo_segments, if_freqs_for_segment, merge_segment_outputs,
)
from ...analysis import post_process as pp
from ...analysis.output import Output
from ...hardware.program_runner import ExecMode, RunResult
from ...programs import cQED_programs


class StorageSpectroscopy(ExperimentBase):
    """Storage resonator frequency sweep with selective qubit rotation."""

    def run(
        self,
        disp: str,
        rf_begin: float,
        rf_end: float,
        df: float,
        storage_therm_time: int,
        sel_r180: str = "sel_x180",
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        lo_freq = self.hw.get_element_lo(attr.st_el)
        if_freqs = create_if_frequencies(attr.st_el, rf_begin, rf_end, df, lo_freq)

        self.set_standard_frequencies()

        prog = cQED_programs.storage_spectroscopy(
            attr.st_el, attr.qb_el, disp, if_freqs,
            sel_r180, storage_therm_time, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("frequencies", lo_freq + if_freqs),
            ],
        )
        self.save_output(result.output, "storageSpectroscopy")
        return result


class StorageSpectroscopyCoarse(ExperimentBase):
    """Multi-LO storage spectroscopy for wide frequency sweeps."""

    def run(
        self,
        rf_begin: float,
        rf_end: float,
        df: float,
        storage_therm_time: int,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        lo_list = make_lo_segments(rf_begin, rf_end)

        seg_results: list[RunResult] = []
        all_freqs: list[np.ndarray] = []

        for LO in lo_list:
            self.hw.set_element_lo(attr.st_el, LO)
            ifs = if_freqs_for_segment(LO, rf_end, df)

            prog = cQED_programs.storage_spectroscopy(
                attr.st_el, attr.qb_el, "const_alpha", ifs,
                "sel_x180", storage_therm_time, n_avg,
            )
            rr = self.run_program(
                prog, n_total=n_avg,
                processors=[
                    pp.proc_default,
                    pp.proc_attach("frequencies", LO + ifs),
                ],
            )
            seg_results.append(rr)
            all_freqs.append(LO + ifs)

        final_output = merge_segment_outputs(
            [r.output for r in seg_results], all_freqs,
        )
        mode = seg_results[0].mode if seg_results else ExecMode.SIMULATE
        final = RunResult(
            mode=mode, output=final_output, sim_samples=None,
            metadata={"segments": len(seg_results)},
        )
        self.save_output(final_output, "storageSpectroscopyCoarse")
        return final


class NumSplittingSpectroscopy(ExperimentBase):
    """Photon number splitting spectroscopy.

    Probes qubit spectroscopy peaks at individual Fock-number-dependent
    frequencies to resolve photon-number-dependent shifts.
    """

    def run(
        self,
        rf_centers: list[float] | np.ndarray,
        rf_spans: list[float] | np.ndarray,
        df: float,
        disp_pulses: str = "const_alpha",
        sel_r180: str = "sel_x180",
        state_prep: Any = None,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.num_splitting_spectroscopy(
            attr.qb_el, attr.st_el,
            rf_centers, rf_spans, df,
            disp_pulses, sel_r180,
            state_prep, attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[pp.proc_default],
        )
        self.save_output(result.output, "numSplittingSpectroscopy")
        return result


class StorageRamsey(ExperimentBase):
    """Storage resonator decoherence via Ramsey interferometry."""

    def run(
        self,
        delay_ticks: np.ndarray | list[int],
        st_detune: int = 0,
        disp_pulse: str = "const_alpha",
        sel_r180: str = "sel_x180",
        n_avg: int = 200,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.storage_ramsey(
            attr.st_el, attr.qb_el,
            np.asarray(delay_ticks, dtype=int),
            st_detune, disp_pulse, sel_r180,
            attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("delays", np.asarray(delay_ticks) * 4),
            ],
        )
        self.save_output(result.output, "storageRamsey")
        return result


class StorageChiRamsey(ExperimentBase):
    """Storage chi (dispersive shift) measurement via Ramsey.

    Measures the cavity-qubit dispersive coupling chi by performing
    Ramsey around a single Fock frequency.
    """

    def run(
        self,
        fock_fq: float,
        delay_ticks: np.ndarray | list[int],
        disp_pulse: str = "const_alpha",
        x90_pulse: str = "x90",
        n_avg: int = 200,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.storage_chi_ramsey(
            attr.qb_el, attr.st_el,
            fock_fq, np.asarray(delay_ticks, dtype=int),
            disp_pulse, x90_pulse,
            attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("delays", np.asarray(delay_ticks) * 4),
            ],
        )
        self.save_output(result.output, "storageChiRamsey")
        return result


class StoragePhaseEvolution(ExperimentBase):
    """Storage state phase evolution tracking with SNAP gates."""

    def run(
        self,
        n: int,
        fock_probe_fqs: list[float] | np.ndarray,
        theta_np_array: np.ndarray,
        snap_np_list: list,
        delay_clks: np.ndarray | list[int],
        max_n_drive: int = 12,
        disp_alpha: float | None = None,
        disp_epsilon: float | None = None,
        sel_r180_pulse: str = "sel_x180",
        n_avg: int = 200,
    ) -> RunResult:
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.phase_evolution_prog(
            attr.qb_el, attr.st_el,
            n, fock_probe_fqs, theta_np_array,
            snap_np_list, np.asarray(delay_clks, dtype=int),
            max_n_drive, disp_alpha, disp_epsilon,
            sel_r180_pulse, attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[pp.proc_default],
        )
        self.save_output(result.output, "storagePhaseEvolution")
        return result
