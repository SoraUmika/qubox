from __future__ import annotations

from ...data import ExecutionRequest


# ---------------------------------------------------------------------------
# Qubit experiments
# ---------------------------------------------------------------------------

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

    def temporal_rabi(self, *, qubit: str, readout: str, duration, pulse: str = "x180", **kwargs):
        n_avg = int(kwargs.get("n_avg", 1000))
        request = ExecutionRequest(
            kind="template",
            template="qubit.temporal_rabi",
            targets={"qubit": qubit, "readout": readout},
            params={"duration": duration, "pulse": pulse, **kwargs},
            sweep=self.session.ensure_sweep_plan(duration, averaging=n_avg),
            shots=n_avg,
        )
        return self.session.backend.run(request)

    def time_rabi_chevron(
        self, *, qubit: str, readout: str,
        freq_span: float, df: float, max_duration: int, dt: int = 4,
        **kwargs,
    ):
        n_avg = int(kwargs.get("n_avg", 1000))
        request = ExecutionRequest(
            kind="template",
            template="qubit.time_rabi_chevron",
            targets={"qubit": qubit, "readout": readout},
            params={"freq_span": freq_span, "df": df, "max_duration": max_duration, "dt": dt, **kwargs},
            shots=n_avg,
        )
        return self.session.backend.run(request)

    def power_rabi_chevron(
        self, *, qubit: str, readout: str,
        freq_span: float, df: float, max_gain: float, dg: float = 0.01,
        **kwargs,
    ):
        n_avg = int(kwargs.get("n_avg", 1000))
        request = ExecutionRequest(
            kind="template",
            template="qubit.power_rabi_chevron",
            targets={"qubit": qubit, "readout": readout},
            params={"freq_span": freq_span, "df": df, "max_gain": max_gain, "dg": dg, **kwargs},
            shots=n_avg,
        )
        return self.session.backend.run(request)

    def t1(self, *, qubit: str, readout: str, delay, **kwargs):
        n_avg = int(kwargs.get("n_avg", 1000))
        request = ExecutionRequest(
            kind="template",
            template="qubit.t1",
            targets={"qubit": qubit, "readout": readout},
            params={"delay": delay, **kwargs},
            sweep=self.session.ensure_sweep_plan(delay, averaging=n_avg),
            shots=n_avg,
        )
        return self.session.backend.run(request)

    def echo(self, *, qubit: str, readout: str, delay, **kwargs):
        n_avg = int(kwargs.get("n_avg", 1000))
        request = ExecutionRequest(
            kind="template",
            template="qubit.echo",
            targets={"qubit": qubit, "readout": readout},
            params={"delay": delay, **kwargs},
            sweep=self.session.ensure_sweep_plan(delay, averaging=n_avg),
            shots=n_avg,
        )
        return self.session.backend.run(request)


# ---------------------------------------------------------------------------
# Resonator experiments
# ---------------------------------------------------------------------------

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

    def power_spectroscopy(self, *, readout: str, freq, gain_min: float = 1e-3, gain_max: float = 0.5, **kwargs):
        n_avg = int(kwargs.get("n_avg", 1000))
        request = ExecutionRequest(
            kind="template",
            template="resonator.power_spectroscopy",
            targets={"readout": readout},
            params={"freq": freq, "gain_min": gain_min, "gain_max": gain_max, **kwargs},
            sweep=self.session.ensure_sweep_plan(freq, averaging=n_avg),
            shots=n_avg,
        )
        return self.session.backend.run(request)


# ---------------------------------------------------------------------------
# Readout experiments
# ---------------------------------------------------------------------------

class ReadoutExperimentLibrary:
    def __init__(self, session):
        self.session = session

    def trace(self, *, readout: str, drive_frequency: float, **kwargs):
        n_avg = int(kwargs.get("n_avg", 1000))
        request = ExecutionRequest(
            kind="template",
            template="readout.trace",
            targets={"readout": readout},
            params={"drive_frequency": drive_frequency, **kwargs},
            shots=n_avg,
        )
        return self.session.backend.run(request)

    def iq_blobs(self, *, qubit: str, readout: str, **kwargs):
        n_runs = int(kwargs.get("n_runs", kwargs.get("n_avg", 1000)))
        request = ExecutionRequest(
            kind="template",
            template="readout.iq_blobs",
            targets={"qubit": qubit, "readout": readout},
            params={**kwargs},
            shots=n_runs,
        )
        return self.session.backend.run(request)

    def butterfly(self, *, qubit: str, readout: str, **kwargs):
        n_samples = int(kwargs.get("n_samples", kwargs.get("n_avg", 10_000)))
        request = ExecutionRequest(
            kind="template",
            template="readout.butterfly",
            targets={"qubit": qubit, "readout": readout},
            params={**kwargs},
            shots=n_samples,
        )
        return self.session.backend.run(request)


# ---------------------------------------------------------------------------
# Calibration experiments
# ---------------------------------------------------------------------------

class CalibrationExperimentLibrary:
    def __init__(self, session):
        self.session = session

    def all_xy(self, *, qubit: str, readout: str, **kwargs):
        n_avg = int(kwargs.get("n_avg", 1000))
        request = ExecutionRequest(
            kind="template",
            template="calibration.all_xy",
            targets={"qubit": qubit, "readout": readout},
            params={**kwargs},
            shots=n_avg,
        )
        return self.session.backend.run(request)

    def drag(self, *, qubit: str, readout: str, amps, **kwargs):
        n_avg = int(kwargs.get("n_avg", 1000))
        request = ExecutionRequest(
            kind="template",
            template="calibration.drag",
            targets={"qubit": qubit, "readout": readout},
            params={"amps": amps, **kwargs},
            sweep=self.session.ensure_sweep_plan(amps, averaging=n_avg) if hasattr(amps, "values") else None,
            shots=n_avg,
        )
        return self.session.backend.run(request)


# ---------------------------------------------------------------------------
# Storage / cavity experiments
# ---------------------------------------------------------------------------

class StorageExperimentLibrary:
    def __init__(self, session):
        self.session = session

    def spectroscopy(self, *, qubit: str, readout: str, storage: str, freq, disp: str, storage_therm_time: int,
                     **kwargs):
        n_avg = int(kwargs.get("n_avg", 1000))
        request = ExecutionRequest(
            kind="template",
            template="storage.spectroscopy",
            targets={"qubit": qubit, "readout": readout, "storage": storage},
            params={"freq": freq, "disp": disp, "storage_therm_time": storage_therm_time, **kwargs},
            sweep=self.session.ensure_sweep_plan(freq, averaging=n_avg),
            shots=n_avg,
        )
        return self.session.backend.run(request)

    def t1_decay(self, *, qubit: str, readout: str, storage: str, delay, **kwargs):
        n_avg = int(kwargs.get("n_avg", 1000))
        request = ExecutionRequest(
            kind="template",
            template="storage.t1_decay",
            targets={"qubit": qubit, "readout": readout, "storage": storage},
            params={"delay": delay, **kwargs},
            sweep=self.session.ensure_sweep_plan(delay, averaging=n_avg),
            shots=n_avg,
        )
        return self.session.backend.run(request)

    def num_splitting(self, *, qubit: str, readout: str, storage: str, rf_centers, rf_spans, df: float = 50e3,
                      **kwargs):
        n_avg = int(kwargs.get("n_avg", 1000))
        request = ExecutionRequest(
            kind="template",
            template="storage.num_splitting",
            targets={"qubit": qubit, "readout": readout, "storage": storage},
            params={"rf_centers": rf_centers, "rf_spans": rf_spans, "df": df, **kwargs},
            shots=n_avg,
        )
        return self.session.backend.run(request)


# ---------------------------------------------------------------------------
# Tomography experiments
# ---------------------------------------------------------------------------

class TomographyExperimentLibrary:
    def __init__(self, session):
        self.session = session

    def qubit_state(self, *, qubit: str, readout: str, state_prep, **kwargs):
        n_avg = int(kwargs.get("n_avg", 1000))
        request = ExecutionRequest(
            kind="template",
            template="tomography.qubit_state",
            targets={"qubit": qubit, "readout": readout},
            params={"state_prep": state_prep, **kwargs},
            shots=n_avg,
        )
        return self.session.backend.run(request)

    def wigner(self, *, qubit: str, readout: str, storage: str, state_prep, x_vals, p_vals, **kwargs):
        n_avg = int(kwargs.get("n_avg", 200))
        request = ExecutionRequest(
            kind="template",
            template="tomography.wigner",
            targets={"qubit": qubit, "readout": readout, "storage": storage},
            params={"state_prep": state_prep, "x_vals": x_vals, "p_vals": p_vals, **kwargs},
            shots=n_avg,
        )
        return self.session.backend.run(request)


# ---------------------------------------------------------------------------
# Reset experiments
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Top-level experiment library (session.exp)
# ---------------------------------------------------------------------------

class ExperimentLibrary:
    def __init__(self, session):
        self.session = session
        self.qubit = QubitExperimentLibrary(session)
        self.resonator = ResonatorExperimentLibrary(session)
        self.readout = ReadoutExperimentLibrary(session)
        self.calibration = CalibrationExperimentLibrary(session)
        self.storage = StorageExperimentLibrary(session)
        self.tomography = TomographyExperimentLibrary(session)
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
