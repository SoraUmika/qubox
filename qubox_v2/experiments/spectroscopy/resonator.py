"""Resonator / readout spectroscopy experiments."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..experiment_base import (
    ExperimentBase, create_if_frequencies, create_clks_array,
)
from ...analysis import post_process as pp
from ...analysis.analysis_tools import two_state_discriminator
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs
from ...programs.macros.measure import measureMacro


class ResonatorSpectroscopy(ExperimentBase):
    """Resonator frequency sweep.

    Sweeps the readout IF frequency while measuring IQ to find the
    resonator resonance.
    """

    def run(
        self,
        readout_op: str,
        rf_begin: float = 8605e6,
        rf_end: float = 8620e6,
        df: float = 50e3,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        lo_freq = self.hw.get_element_lo(attr.ro_el)
        if_freqs = create_if_frequencies(attr.ro_el, rf_begin, rf_end, df, lo_freq)

        ro_info = self.pulse_mgr.get_pulseOp_by_element_op(attr.ro_el, readout_op)
        if ro_info is None:
            raise ValueError(
                f"No PulseOp for element={attr.ro_el!r}, op={readout_op!r}."
            )

        mm = measureMacro
        weight_len = int(ro_info.length) if ro_info.length is not None else None
        with mm.using_defaults(pulse_op=ro_info, active_op=readout_op, weight_len=weight_len):
            prog = cQED_programs.resonator_spectroscopy(
                attr.ro_el, if_freqs, attr.ro_therm_clks, n_avg,
            )
            return self.run_program(
                prog, n_total=n_avg,
                processors=[
                    pp.proc_default, pp.proc_magnitude,
                    pp.proc_attach("frequencies", lo_freq + if_freqs),
                ],
                axis=0,
            )


class ResonatorPowerSpectroscopy(ExperimentBase):
    """Resonator frequency × readout gain 2-D sweep."""

    def run(
        self,
        readout_op: str,
        rf_begin: float,
        rf_end: float,
        df: float,
        g_min: float = 1e-3,
        g_max: float = 0.5,
        N_a: int = 50,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        lo_freq = self.hw.get_element_lo(attr.ro_el)
        if_freqs = create_if_frequencies(attr.ro_el, rf_begin, rf_end, df, lo_freq)
        gains = np.geomspace(g_min, g_max, N_a)

        ro_info = self.pulse_mgr.get_pulseOp_by_element_op(attr.ro_el, readout_op)
        if ro_info is None:
            raise ValueError(
                f"No PulseOp for element={attr.ro_el!r}, op={readout_op!r}."
            )

        mm = measureMacro
        weight_len = int(ro_info.length) if ro_info.length is not None else None
        with mm.using_defaults(pulse_op=ro_info, active_op=readout_op, weight_len=weight_len):
            prog = cQED_programs.resonator_power_spectroscopy(
                if_freqs, gains, attr.ro_therm_clks, n_avg,
            )
            result = self.run_program(
                prog, n_total=n_avg,
                processors=[
                    pp.proc_default,
                    pp.proc_attach("frequencies", lo_freq + if_freqs),
                    pp.proc_attach("gains", gains),
                ],
            )
        self.save_output(result.output, "cavityPowerSpectroscopy")
        return result


class ResonatorSpectroscopyX180(ExperimentBase):
    """Resonator spectroscopy with qubit pi-pulse excitation."""

    def run(
        self,
        rf_begin: float,
        rf_end: float,
        df: float,
        r180: str = "x180",
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        lo_freq = self.hw.get_element_lo(attr.ro_el)
        if_freqs = create_if_frequencies(attr.ro_el, rf_begin, rf_end, df, lo_freq)

        self.set_standard_frequencies()

        prog = cQED_programs.resonator_spectroscopy_x180(
            attr.ro_el, attr.qb_el, if_freqs, r180,
            attr.ro_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default, pp.proc_magnitude,
                pp.proc_attach("frequencies", lo_freq + if_freqs),
            ],
        )
        self.save_output(result.output, "resonatorX180")
        return result


class ReadoutTrace(ExperimentBase):
    """Raw ADC readout trace capture."""

    def run(
        self,
        drive_frequency: float,
        ro_therm_clks: int = 10000,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        self.hw.set_element_fq(attr.ro_el, drive_frequency)

        prog = cQED_programs.readout_trace(
            attr.ro_el, ro_therm_clks, n_avg,
        )
        return self.run_program(
            prog, n_total=n_avg,
            processors=[pp.proc_default],
        )


class ReadoutFrequencyOptimization(ExperimentBase):
    """Sweep readout frequency to maximize g/e discrimination fidelity."""

    def run(
        self,
        rf_begin: float,
        rf_end: float,
        df: float,
        ro_op: str | None = None,
        r180: str = "x180",
        n_runs: int = 1000,
    ) -> RunResult:
        attr = self.attr
        lo_freq = self.hw.get_element_lo(attr.ro_el)
        if_freqs = create_if_frequencies(attr.ro_el, rf_begin, rf_end, df, lo_freq)

        self.set_standard_frequencies()

        best_fidelity = -1.0
        fidelities = []

        for if_fq in if_freqs:
            self.hw.set_element_fq(attr.ro_el, lo_freq + float(if_fq))
            prog = cQED_programs.iq_blobs(
                attr.qb_el, r180, attr.qb_therm_clks, n_runs,
            )
            result = self.run_program(prog, n_total=n_runs, processors=[pp.proc_default])

            try:
                I_g = result.output["I_g"]
                Q_g = result.output["Q_g"]
                I_e = result.output["I_e"]
                Q_e = result.output["Q_e"]
                _, _, fid, _, _, _ = two_state_discriminator(I_g, Q_g, I_e, Q_e)
                fidelities.append(fid)
            except Exception:
                fidelities.append(0.0)

        from ...analysis.output import Output
        output = Output({
            "frequencies": lo_freq + if_freqs,
            "fidelities": np.array(fidelities),
            "best_freq": lo_freq + if_freqs[int(np.argmax(fidelities))],
        })
        self.save_output(output, "readoutFreqOpt")
        return RunResult(mode=result.mode, output=output, sim_samples=None)
