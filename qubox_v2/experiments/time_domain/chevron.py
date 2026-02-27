"""2-D chevron experiments (Rabi & Ramsey vs detuning)."""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase, create_clks_array
from ..result import AnalysisResult, ProgramBuildResult
from ...analysis import post_process as pp
from ...hardware.program_runner import RunResult
from ...programs import cQED_programs


class TimeRabiChevron(ExperimentBase):
    """2-D sweep: Rabi oscillations vs detuning and pulse duration."""

    def _build_impl(
        self,
        if_span: float,
        df: float,
        max_pulse_duration: int,
        dt: int,
        pulse: str = "x180",
        pulse_gain: float = 1.0,
        n_avg: int = 1000,
    ) -> ProgramBuildResult:
        attr = self.attr
        dfs = np.arange(-if_span / 2, if_span / 2 + 0.1, df, dtype=int)
        pulse_clks = create_clks_array(4, max_pulse_duration, dt, time_per_clk=4)

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()
        lo_qb = self.get_qubit_lo()
        qb_if = int(qb_fq - lo_qb)

        prog = cQED_programs.time_rabi_chevron(
            pulse, pulse_gain,
            qb_if, dfs, pulse_clks, attr.qb_therm_clks, n_avg,
            ro_el=attr.ro_el, qb_el=attr.qb_el,
            bindings=self._bindings_or_none,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("pulse_durations", pulse_clks * 4),
                pp.proc_attach("detunings", dfs),
            ),
            experiment_name="TimeRabiChevron",
            params={
                "if_span": if_span, "df": df,
                "max_pulse_duration": max_pulse_duration, "dt": dt,
                "pulse": pulse, "pulse_gain": pulse_gain, "n_avg": n_avg,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.time_rabi_chevron",
            sweep_axes={"pulse_durations": pulse_clks * 4, "detunings": dfs},
        )

    def run(
        self,
        if_span: float,
        df: float,
        max_pulse_duration: int,
        dt: int,
        pulse: str = "x180",
        pulse_gain: float = 1.0,
        n_avg: int = 1000,
    ) -> RunResult:
        build = self.build_program(
            if_span=if_span, df=df,
            max_pulse_duration=max_pulse_duration, dt=dt,
            pulse=pulse, pulse_gain=pulse_gain, n_avg=n_avg,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "timeRabiChevron")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        durations = result.output.extract("pulse_durations")
        detunings = result.output.extract("detunings")
        S = result.output.extract("S")
        mag = np.abs(S)
        return AnalysisResult.from_run(result, metrics={"shape": mag.shape})

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S = analysis.data.get("S")
        durations = analysis.data.get("pulse_durations")
        detunings = analysis.data.get("detunings")
        if S is None or durations is None or detunings is None:
            return None
        mag = np.abs(S)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 6))
        else:
            fig = ax.figure
        ax.pcolormesh(durations, detunings / 1e6, mag, shading="auto")
        ax.set_xlabel("Pulse Duration (ns)")
        ax.set_ylabel("Detuning (MHz)")
        ax.set_title("Time Rabi Chevron")
        plt.tight_layout()
        plt.show()
        return fig


class PowerRabiChevron(ExperimentBase):
    """2-D sweep: Rabi oscillations vs detuning and amplitude."""

    def _build_impl(
        self,
        if_span: float,
        df: float,
        max_gain: float,
        dg: float,
        pulse: str = "x180",
        pulse_duration: int = 100,
        n_avg: int = 1000,
    ) -> ProgramBuildResult:
        attr = self.attr
        dfs = np.arange(-if_span / 2, if_span / 2 + 0.1, df, dtype=int)
        gains = np.arange(-max_gain, max_gain + 1e-12, dg, dtype=float)

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()
        lo_qb = self.get_qubit_lo()
        qb_if = int(qb_fq - lo_qb)

        prog = cQED_programs.power_rabi_chevron(
            pulse, int(pulse_duration / 4),
            qb_if, dfs, gains, attr.qb_therm_clks, n_avg,
            ro_el=attr.ro_el, qb_el=attr.qb_el,
            bindings=self._bindings_or_none,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("gains", gains),
                pp.proc_attach("detunings", dfs),
            ),
            experiment_name="PowerRabiChevron",
            params={
                "if_span": if_span, "df": df,
                "max_gain": max_gain, "dg": dg,
                "pulse": pulse, "pulse_duration": pulse_duration, "n_avg": n_avg,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.power_rabi_chevron",
            sweep_axes={"gains": gains, "detunings": dfs},
        )

    def run(
        self,
        if_span: float,
        df: float,
        max_gain: float,
        dg: float,
        pulse: str = "x180",
        pulse_duration: int = 100,
        n_avg: int = 1000,
    ) -> RunResult:
        build = self.build_program(
            if_span=if_span, df=df,
            max_gain=max_gain, dg=dg,
            pulse=pulse, pulse_duration=pulse_duration, n_avg=n_avg,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "powerRabiChevron")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        gains = result.output.extract("gains")
        detunings = result.output.extract("detunings")
        S = result.output.extract("S")
        mag = np.abs(S)
        return AnalysisResult.from_run(result, metrics={"shape": mag.shape})

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S = analysis.data.get("S")
        gains = analysis.data.get("gains")
        detunings = analysis.data.get("detunings")
        if S is None or gains is None or detunings is None:
            return None
        mag = np.abs(S)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 6))
        else:
            fig = ax.figure
        ax.pcolormesh(gains, detunings / 1e6, mag, shading="auto")
        ax.set_xlabel("Amplitude (a.u.)")
        ax.set_ylabel("Detuning (MHz)")
        ax.set_title("Power Rabi Chevron")
        plt.tight_layout()
        plt.show()
        return fig


class RamseyChevron(ExperimentBase):
    """2-D sweep: Ramsey fringes vs detuning and delay."""

    def _build_impl(
        self,
        if_span: float,
        df: float,
        max_delay_duration: int,
        dt: int,
        r90: str = "x90",
        n_avg: int = 1000,
    ) -> ProgramBuildResult:
        attr = self.attr
        dfs = np.arange(-if_span / 2, if_span / 2 + 0.1, df, dtype=int)
        delay_clks = create_clks_array(4, max_delay_duration, dt, time_per_clk=4)

        ro_fq = self._resolve_readout_frequency()
        qb_fq = self._resolve_qubit_frequency()
        lo_qb = self.get_qubit_lo()
        qb_if = int(qb_fq - lo_qb)

        prog = cQED_programs.ramsey_chevron(
            r90,
            qb_if, dfs, delay_clks, attr.qb_therm_clks, n_avg,
            ro_el=attr.ro_el, qb_el=attr.qb_el,
            bindings=self._bindings_or_none,
        )

        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(
                pp.proc_default,
                pp.proc_attach("delays", delay_clks * 4),
                pp.proc_attach("detunings", dfs),
            ),
            experiment_name="RamseyChevron",
            params={
                "if_span": if_span, "df": df,
                "max_delay_duration": max_delay_duration, "dt": dt,
                "r90": r90, "n_avg": n_avg,
            },
            resolved_frequencies={attr.ro_el: ro_fq, attr.qb_el: qb_fq},
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.ramsey_chevron",
            sweep_axes={"delays": delay_clks * 4, "detunings": dfs},
        )

    def run(
        self,
        if_span: float,
        df: float,
        max_delay_duration: int,
        dt: int,
        r90: str = "x90",
        n_avg: int = 1000,
    ) -> RunResult:
        build = self.build_program(
            if_span=if_span, df=df,
            max_delay_duration=max_delay_duration, dt=dt,
            r90=r90, n_avg=n_avg,
        )
        result = self.run_program(
            build.program, n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "ramseyChevron")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        delays = result.output.extract("delays")
        detunings = result.output.extract("detunings")
        S = result.output.extract("S")
        mag = np.abs(S)
        return AnalysisResult.from_run(result, metrics={"shape": mag.shape})

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S = analysis.data.get("S")
        delays = analysis.data.get("delays")
        detunings = analysis.data.get("detunings")
        if S is None or delays is None or detunings is None:
            return None
        mag = np.abs(S)
        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 6))
        else:
            fig = ax.figure
        ax.pcolormesh(delays, detunings / 1e6, mag, shading="auto")
        ax.set_xlabel("Delay (ns)")
        ax.set_ylabel("Detuning (MHz)")
        ax.set_title("Ramsey Chevron")
        plt.tight_layout()
        plt.show()
        return fig
