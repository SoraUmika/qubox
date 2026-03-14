from __future__ import annotations

from ...data import ExecutionRequest


class QubitExperimentLibrary:
    def __init__(self, session):
        self.session = session

    def spectroscopy(self, *, qubit: str, readout: str, freq, drive_amp: float, **kwargs):
        request = ExecutionRequest(
            kind="template",
            template="qubit.spectroscopy",
            targets={"qubit": qubit, "readout": readout},
            params={"freq": freq, "drive_amp": drive_amp, **kwargs},
            sweep=self.session.ensure_sweep_plan(freq, averaging=int(kwargs.get("n_avg", 200))),
            shots=int(kwargs.get("n_avg", 200)),
        )
        return self.session.backend.run(request)

    def power_rabi(self, *, qubit: str, readout: str, amplitude, **kwargs):
        request = ExecutionRequest(
            kind="template",
            template="qubit.power_rabi",
            targets={"qubit": qubit, "readout": readout},
            params={"amplitude": amplitude, **kwargs},
            sweep=self.session.ensure_sweep_plan(amplitude, averaging=int(kwargs.get("n_avg", 500))),
            shots=int(kwargs.get("n_avg", 500)),
        )
        return self.session.backend.run(request)

    def ramsey(self, *, qubit: str, readout: str, delay, detuning: float = 0.0, **kwargs):
        request = ExecutionRequest(
            kind="template",
            template="qubit.ramsey",
            targets={"qubit": qubit, "readout": readout},
            params={"delay": delay, "detuning": detuning, **kwargs},
            sweep=self.session.ensure_sweep_plan(delay, averaging=int(kwargs.get("n_avg", 500))),
            shots=int(kwargs.get("n_avg", 500)),
        )
        return self.session.backend.run(request)


class ResonatorExperimentLibrary:
    def __init__(self, session):
        self.session = session

    def spectroscopy(self, *, readout: str, freq, **kwargs):
        request = ExecutionRequest(
            kind="template",
            template="resonator.spectroscopy",
            targets={"readout": readout},
            params={"freq": freq, **kwargs},
            sweep=self.session.ensure_sweep_plan(freq, averaging=int(kwargs.get("n_avg", 200))),
            shots=int(kwargs.get("n_avg", 200)),
        )
        return self.session.backend.run(request)


class ResetExperimentLibrary:
    def __init__(self, session):
        self.session = session

    def active(self, *, qubit: str, readout: str, threshold: float | str = "calibrated", **kwargs):
        request = ExecutionRequest(
            kind="template",
            template="reset.active",
            targets={"qubit": qubit, "readout": readout},
            params={"threshold": threshold, **kwargs},
            shots=int(kwargs.get("n_avg", 200)),
        )
        return self.session.backend.run(request)


class ExperimentLibrary:
    def __init__(self, session):
        self.session = session
        self.qubit = QubitExperimentLibrary(session)
        self.resonator = ResonatorExperimentLibrary(session)
        self.reset = ResetExperimentLibrary(session)

    def custom(
        self,
        *,
        sequence=None,
        circuit=None,
        sweep=None,
        acquire=None,
        analysis: str | None = "raw",
        n_avg: int = 1,
        name: str | None = None,
        execute: bool = True,
    ):
        if sequence is None and circuit is None:
            raise ValueError("custom() requires either sequence= or circuit=")
        body = circuit if circuit is not None else sequence
        template_name = str(name or getattr(body, "name", "custom"))
        request = ExecutionRequest(
            kind="custom",
            template=template_name,
            sequence=sequence,
            circuit=circuit,
            sweep=self.session.ensure_sweep_plan(sweep, averaging=n_avg) if sweep is not None else None,
            acquisition=acquire,
            shots=int(n_avg),
            analysis=analysis,
            execute=bool(execute),
        )
        if execute:
            return self.session.backend.run(request)
        return self.session.backend.build(request)
