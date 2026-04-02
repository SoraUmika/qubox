"""@experiment decorator for lightweight experiment registration.

Provides a decorator to register named experiment functions that can be
invoked via ``session.exp.run_registered("my_experiment", ...)``.

Usage::

    from qubox.experiments.decorator import experiment

    @experiment("custom_t1", n_avg=500, category="time_domain")
    def custom_t1(session, *, delay, r180="x180"):
        '''Custom T1 measurement with specific pulse sequence.'''
        return session.exp.custom(
            sequence=session.ops.sequence("custom_t1", [
                session.ops.play(r180, "qubit"),
                session.ops.wait("qubit"),
                session.ops.measure("readout"),
            ]),
            sweep=delay,
            n_avg=500,
        )
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ExperimentDefinition:
    """Metadata for a decorated experiment function."""
    name: str
    func: Callable
    default_n_avg: int = 1000
    category: str = "custom"


_REGISTRY: dict[str, ExperimentDefinition] = {}


def experiment(
    name: str | None = None,
    *,
    n_avg: int = 1000,
    category: str = "custom",
) -> Callable:
    """Register a function as a named experiment.

    Parameters
    ----------
    name : str, optional
        Registry name.  Defaults to the function's ``__name__``.
    n_avg : int
        Default averaging count.
    category : str
        Experiment category for grouping (e.g. "spectroscopy", "time_domain").
    """
    def decorator(func: Callable) -> Callable:
        exp_name = name or func.__name__
        defn = ExperimentDefinition(
            name=exp_name,
            func=func,
            default_n_avg=n_avg,
            category=category,
        )
        _REGISTRY[exp_name] = defn

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        wrapper._experiment_definition = defn  # type: ignore[attr-defined]
        return wrapper

    return decorator


def get_registered_experiments() -> dict[str, ExperimentDefinition]:
    """Return a snapshot of the experiment registry."""
    return dict(_REGISTRY)


def lookup_experiment(name: str) -> ExperimentDefinition | None:
    """Look up a registered experiment by name."""
    return _REGISTRY.get(name)
