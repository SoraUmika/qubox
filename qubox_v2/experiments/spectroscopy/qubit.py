"""Qubit spectroscopy experiments."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..experiment_base import (
    ExperimentBase, create_if_frequencies,
    make_lo_segments, if_freqs_for_segment, merge_segment_outputs,
)
from ...analysis import post_process as pp
from ...analysis.output import Output
from ...hardware.program_runner import ExecMode, RunResult
from ...programs import cQED_programs
from ...programs.macros.measure import measureMacro


class QubitSpectroscopy(ExperimentBase):
    """Single-LO qubit spectroscopy scan over IF frequencies."""

    def run(
        self,
        pulse: str,
        rf_begin: float,
        rf_end: float,
        df: float,
        qb_gain: float,
        qb_len: int,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        lo_qb = self.hw.get_element_lo(attr.qb_el)
        if_freqs = create_if_frequencies(attr.qb_el, rf_begin, rf_end, df, lo_freq=lo_qb)

        self.set_standard_frequencies()

        prog = cQED_programs.qubit_spectroscopy(
            pulse, attr.qb_el, if_freqs, qb_gain, qb_len,
            attr.qb_therm_clks, n_avg,
        )

        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("frequencies", lo_qb + if_freqs),
            ],
        )
        self.save_output(result.output, "qubitSpectroscopy")
        return result


class QubitSpectroscopyCoarse(ExperimentBase):
    """Multi-LO qubit spectroscopy for wide frequency sweeps.

    Automatically segments the frequency range into multiple LO
    windows and stitches the results.
    """

    def run(
        self,
        rf_begin: float,
        rf_end: float,
        df: float,
        qb_gain: float,
        qb_len: int,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        lo_list = make_lo_segments(rf_begin, rf_end)

        seg_results: list[RunResult] = []
        all_freqs: list[np.ndarray] = []

        for LO in lo_list:
            self.hw.set_element_lo(attr.qb_el, LO)
            ifs = if_freqs_for_segment(LO, rf_end, df)

            prog = cQED_programs.qubit_spectroscopy(
                attr.ro_el, attr.qb_el, ifs, qb_gain, qb_len,
                attr.qb_therm_clks, n_avg,
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
        self.save_output(final_output, "qubitSpectroscopy")
        return final


class QubitSpectroscopyEF(ExperimentBase):
    """e→f transition spectroscopy with prior pi-pulse excitation."""

    def run(
        self,
        pulse: str,
        rf_begin: float,
        rf_end: float,
        df: float,
        qb_gain: float,
        qb_len: int,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        lo_qb = self.hw.get_element_lo(attr.qb_el)
        if_freqs = create_if_frequencies(attr.qb_el, rf_begin, rf_end, df, lo_freq=lo_qb)

        self.set_standard_frequencies()

        prog = cQED_programs.qubit_spectroscopy_ef(
            pulse, attr.qb_el, if_freqs,
            self.hw.get_element_if(attr.qb_el),
            qb_gain, qb_len, "x180", attr.qb_therm_clks, n_avg,
        )

        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("frequencies", lo_qb + if_freqs),
            ],
        )
        self.save_output(result.output, "qubit_efSpectroscopy")
        return result
