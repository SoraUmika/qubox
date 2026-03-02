"""Fock-resolved state tomography."""
from __future__ import annotations

from typing import Any, Callable

import numpy as np
import matplotlib.pyplot as plt

from ..experiment_base import ExperimentBase
from ..result import AnalysisResult, ProgramBuildResult
from ...analysis import post_process as pp
from ...analysis.cQED_plottings import display_fock_populations
from ...hardware.program_runner import RunResult
from ...programs import api as cQED_programs
from ...programs.measurement import try_build_readout_snapshot_from_macro


class FockResolvedStateTomography(ExperimentBase):
    """State tomography in individual Fock manifolds.

    Supports single or multiple state-preparation callables.
    Measures sigma_x, sigma_y, sigma_z conditioned on Fock number.
    """

    def _build_impl(
        self,
        fock_fqs: list[float] | np.ndarray,
        state_prep: Callable | list[Callable],
        *,
        tag_off_idle_duration: int | None = None,
        sel_r180: str = "sel_x180",
        rxp90: str = "x90",
        rym90: str = "yn90",
        qb_if: float | None = None,
        n_avg: int = 1000,
        therm_clks: int | None = None,
    ) -> ProgramBuildResult:
        attr = self.attr
        resolved_therm = self.resolve_param(
            "qb_therm_clks",
            override=therm_clks,
            calibration_value=self._calibration_cqed_value("transmon", "qb_therm_clks"),
            calibration_path="cqed_params.transmon.qb_therm_clks",
            owner="FockResolvedStateTomography",
            cast=int,
        )

        prog = cQED_programs.fock_resolved_state_tomography(
            attr.qb_el, attr.st_el,
            np.asarray(fock_fqs),
            state_prep,
            tag_off_idle_duration=tag_off_idle_duration,
            sel_r180=sel_r180,
            rxp90=rxp90, rym90=rym90,
            qb_if=qb_if,
            therm_clks=resolved_therm,
            n_avg=n_avg,
        )
        return ProgramBuildResult(
            program=prog,
            n_total=n_avg,
            processors=(pp.proc_default,),
            experiment_name="FockResolvedStateTomography",
            params={
                "fock_fqs": np.asarray(fock_fqs, dtype=float).tolist(),
                "state_prep_count": (1 if callable(state_prep) else len(list(state_prep))),
                "tag_off_idle_duration": tag_off_idle_duration,
                "sel_r180": sel_r180,
                "rxp90": rxp90,
                "rym90": rym90,
                "qb_if": qb_if,
                "n_avg": n_avg,
                "qb_therm_clks": resolved_therm,
            },
            resolved_frequencies={
                attr.ro_el: self._resolve_readout_frequency(),
                attr.qb_el: self._resolve_qubit_frequency(),
                attr.st_el: self.get_storage_frequency(),
            },
            bindings_snapshot=self._serialize_bindings(),
            builder_function="cQED_programs.fock_resolved_state_tomography",
            measure_macro_state=try_build_readout_snapshot_from_macro(),
        )

    def run(
        self,
        fock_fqs: list[float] | np.ndarray,
        state_prep: Callable | list[Callable],
        *,
        tag_off_idle_duration: int | None = None,
        sel_r180: str = "sel_x180",
        rxp90: str = "x90",
        rym90: str = "yn90",
        qb_if: float | None = None,
        n_avg: int = 1000,
        therm_clks: int | None = None,
    ) -> RunResult:
        build = self.build_program(
            fock_fqs=fock_fqs,
            state_prep=state_prep,
            tag_off_idle_duration=tag_off_idle_duration,
            sel_r180=sel_r180,
            rxp90=rxp90,
            rym90=rym90,
            qb_if=qb_if,
            n_avg=n_avg,
            therm_clks=therm_clks,
        )
        result = self.run_program(
            build.program,
            n_total=build.n_total,
            processors=list(build.processors),
        )
        self.save_output(result.output, "fockResolvedTomography")
        return result

    def analyze(self, result: RunResult, *, update_calibration: bool = False, **kw) -> AnalysisResult:
        S = result.output.extract("S")
        metrics: dict[str, Any] = {}

        if S is not None:
            mag = np.abs(S)
            if mag.ndim == 2:
                n_fock = mag.shape[0]
                fock_pops = np.mean(mag, axis=1)
                metrics["n_fock"] = n_fock
                metrics["fock_pops"] = fock_pops.tolist()
            else:
                metrics["n_points"] = int(len(mag))

        return AnalysisResult.from_run(result, metrics=metrics)

    def plot(self, analysis: AnalysisResult, *, ax=None, **kwargs):
        S = analysis.data.get("S")
        if S is None:
            return None

        mag = np.abs(S)
        if mag.ndim == 2:
            n_fock = mag.shape[0]
            fock_states = list(range(n_fock))
            fock_pops = np.mean(mag, axis=1)
            display_fock_populations(
                fock_states, fock_pops,
                title="Fock-Resolved State Tomography",
            )
            return plt.gcf()

        if ax is None:
            fig, ax = plt.subplots(figsize=(10, 5))
        else:
            fig = ax.figure
        ax.bar(range(len(mag)), mag)
        ax.set_xlabel("Fock State")
        ax.set_ylabel("Population")
        ax.set_title("Fock-Resolved State Tomography")
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
        return fig
