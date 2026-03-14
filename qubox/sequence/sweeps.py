from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np


@dataclass(frozen=True)
class SweepAxis:
    parameter: str
    values: tuple[Any, ...]
    spacing: str = "custom"
    center: str | float | None = None
    unit: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_array(self) -> np.ndarray:
        return np.asarray(self.values)


@dataclass(frozen=True)
class SweepPlan:
    axes: tuple[SweepAxis, ...] = ()
    averaging: int = 1

    def primary_axis(self) -> SweepAxis | None:
        return self.axes[0] if self.axes else None


class SweepParameterBuilder:
    def __init__(self, parameter: str):
        self.parameter = parameter

    def values(
        self,
        values: Iterable[Any],
        *,
        center: str | float | None = None,
        unit: str | None = None,
    ) -> SweepAxis:
        return SweepAxis(
            parameter=self.parameter,
            values=tuple(values),
            spacing="custom",
            center=center,
            unit=unit,
        )

    def linspace(
        self,
        start: float,
        stop: float,
        num: int,
        *,
        center: str | float | None = None,
        unit: str | None = None,
    ) -> SweepAxis:
        return SweepAxis(
            parameter=self.parameter,
            values=tuple(float(v) for v in np.linspace(start, stop, int(num))),
            spacing="linspace",
            center=center,
            unit=unit,
        )

    def geomspace(
        self,
        start: float,
        stop: float,
        num: int,
        *,
        center: str | float | None = None,
        unit: str | None = None,
    ) -> SweepAxis:
        return SweepAxis(
            parameter=self.parameter,
            values=tuple(float(v) for v in np.geomspace(start, stop, int(num))),
            spacing="geomspace",
            center=center,
            unit=unit,
        )


class SweepFactory:
    """Factory for first-class sweep objects."""

    def param(self, parameter: str) -> SweepParameterBuilder:
        return SweepParameterBuilder(parameter)

    def values(
        self,
        values: Iterable[Any],
        *,
        parameter: str = "value",
        center: str | float | None = None,
        unit: str | None = None,
    ) -> SweepAxis:
        return self.param(parameter).values(values, center=center, unit=unit)

    def linspace(
        self,
        start: float,
        stop: float,
        num: int,
        *,
        parameter: str = "value",
        center: str | float | None = None,
        unit: str | None = None,
    ) -> SweepAxis:
        return self.param(parameter).linspace(start, stop, num, center=center, unit=unit)

    def geomspace(
        self,
        start: float,
        stop: float,
        num: int,
        *,
        parameter: str = "value",
        center: str | float | None = None,
        unit: str | None = None,
    ) -> SweepAxis:
        return self.param(parameter).geomspace(start, stop, num, center=center, unit=unit)

    def grid(self, *axes: SweepAxis, averaging: int = 1) -> SweepPlan:
        return SweepPlan(axes=tuple(axes), averaging=int(averaging))

    def plan(self, *axes: SweepAxis, averaging: int = 1) -> SweepPlan:
        return self.grid(*axes, averaging=averaging)
