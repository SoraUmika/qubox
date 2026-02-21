"""Rabi oscillation experiments."""
from __future__ import annotations

import numpy as np

from ..experiment_base import ExperimentBase, create_clks_array
from ...analysis import post_process as pp
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs
from ...programs.macros.measure import measureMacro
from ...pulses.manager import MAX_AMPLITUDE


class TemporalRabi(ExperimentBase):
    """Qubit Rabi oscillations vs pulse duration."""

    def run(
        self,
        pulse: str,
        pulse_len_begin: int,
        pulse_len_end: int,
        dt: int = 4,
        pulse_gain: float = 1.0,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        pulse_clks = create_clks_array(pulse_len_begin, pulse_len_end, dt, time_per_clk=4)

        self.set_standard_frequencies()

        prog = cQED_programs.temporal_rabi(
            attr.qb_el, pulse, pulse_clks, pulse_gain, attr.qb_therm_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("pulse_durations", pulse_clks * 4),
            ],
        )
        self.save_output(result.output, "temporalRabi")
        return result


class PowerRabi(ExperimentBase):
    """Qubit Rabi oscillations vs amplitude/gain."""

    def run(
        self,
        max_gain: float,
        dg: float = 1e-3,
        op: str = "x180",
        length: int | None = None,
        truncate_clks: int | None = None,
        n_avg: int = 1000,
    ) -> RunResult:
        attr = self.attr
        gains = np.arange(-max_gain, max_gain + 1e-12, dg, dtype=float)

        pulse_info = self.pulse_mgr.get_pulseOp_by_element_op(attr.qb_el, op)
        if not length:
            length = pulse_info.length

        I_wf, Q_wf = pulse_info.I_wf, pulse_info.Q_wf
        peak_amp = max(np.abs(I_wf).max(), np.abs(Q_wf).max())
        if peak_amp * max_gain > MAX_AMPLITUDE:
            raise ValueError(
                f"Max gain {max_gain} too high for pulse {op} "
                f"(peak={peak_amp:.3f}, max={MAX_AMPLITUDE/peak_amp:.3f})"
            )

        pulse_clock_len = round(length / 4)
        self.set_standard_frequencies()

        prog = cQED_programs.power_rabi(
            attr.qb_el, pulse_clock_len, gains, attr.qb_therm_clks,
            op, truncate_clks, n_avg,
        )
        result = self.run_program(
            prog, n_total=n_avg,
            processors=[
                pp.proc_default,
                pp.proc_attach("gains", gains),
            ],
        )
        self.save_output(result.output, "powerRabi")
        return result


class SequentialQubitRotations(ExperimentBase):
    """Apply a sequence of qubit rotation gates and measure."""

    def run(
        self,
        rotations: list[str] | None = None,
        apply_avg: bool = False,
        n_shots: int = 1000,
    ) -> RunResult:
        if rotations is None:
            rotations = ["x180"]
        attr = self.attr
        self.set_standard_frequencies()

        prog = cQED_programs.sequential_qb_rotations(
            attr.qb_el, rotations, apply_avg, attr.qb_therm_clks, n_shots,
        )
        return self.run_program(
            prog, n_total=n_shots,
            processors=[
                pp.proc_default,
                pp.proc_attach("rotations", rotations),
            ],
        )
