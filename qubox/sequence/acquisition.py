from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AcquisitionSpec:
    kind: str
    target: str
    operation: str = "readout"
    key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AcquisitionFactory:
    def iq(self, target: str, *, operation: str = "readout", key: str | None = None) -> AcquisitionSpec:
        return AcquisitionSpec(kind="iq", target=target, operation=operation, key=key)

    def classified(
        self,
        target: str,
        *,
        operation: str = "readout",
        key: str | None = None,
    ) -> AcquisitionSpec:
        return AcquisitionSpec(kind="classified", target=target, operation=operation, key=key)

    def population(
        self,
        target: str,
        *,
        operation: str = "readout",
        key: str | None = None,
    ) -> AcquisitionSpec:
        return AcquisitionSpec(kind="population", target=target, operation=operation, key=key)

    def trace(self, target: str, *, operation: str = "readout", key: str | None = None) -> AcquisitionSpec:
        return AcquisitionSpec(kind="trace", target=target, operation=operation, key=key)
