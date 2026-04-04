from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class WorkflowReport:
    name: str
    payload: dict[str, Any]

    def review(self) -> str:
        steps = list(self.payload.get("steps") or [])
        if not steps:
            return f"{self.name}: completed"
        lines = [self.name]
        for step in steps:
            lines.append(f"- {step}")
        return "\n".join(lines)

    def apply(self):
        raise RuntimeError(
            "This compatibility workflow returns a report only. Promote its staged "
            "calibration outputs explicitly through the canonical calibration proposal flow."
        )


class ReadoutWorkflowLibrary:
    def __init__(self, session):
        self.session = session

    def full(self, *, qubit: str, readout: str, update_store: bool = False, **kwargs):
        session = self.session

        class _ReadoutFullWorkflow:
            def run(self_nonlocal):
                from qubox.experiments.calibration.readout import CalibrateReadoutFull

                experiment = CalibrateReadoutFull(session.session_manager)
                payload = experiment.build_plan(
                    ro_op=kwargs.get("ro_op"),
                    drive_frequency=kwargs.get("drive_frequency"),
                    ro_el=session.resolve_alias(readout, role_hint="readout"),
                    r180=kwargs.get("r180", "x180"),
                )
                payload["requested_update_store"] = bool(update_store)
                payload["targets"] = {
                    "qubit": session.resolve_alias(qubit, role_hint="qubit"),
                    "readout": session.resolve_alias(readout, role_hint="readout"),
                }
                return WorkflowReport(name="readout.full", payload=payload)

        return _ReadoutFullWorkflow()


class WorkflowLibrary:
    def __init__(self, session):
        self.readout = ReadoutWorkflowLibrary(session)
