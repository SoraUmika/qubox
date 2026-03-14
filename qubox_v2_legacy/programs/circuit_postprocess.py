from __future__ import annotations

from typing import Any, Callable

from .circuit_runner import MeasurementSchema
from .measurement import StateRule, derive_state


def _iq_keys(schema: MeasurementSchema, record_key: str) -> tuple[str, str]:
    record = schema.get(record_key)
    if record is None:
        raise KeyError(f"MeasurementSchema has no record for {record_key!r}.")
    return record.output_name("I"), record.output_name("Q")


def build_state_derivation_processor(
    schema: MeasurementSchema,
    *,
    resolved_rules: dict[str, StateRule],
) -> Callable[[Any], Any]:
    resolved = dict(resolved_rules)

    def _processor(output: Any, **_kwargs: Any) -> Any:
        if not isinstance(output, dict):
            return output

        data = dict(output)
        single_record = len(schema.records) == 1

        for record in schema.records:
            rule = resolved.get(record.key)
            if rule is None:
                continue

            i_key, q_key = _iq_keys(schema, record.key)
            if i_key not in data or q_key not in data:
                if single_record and "I" in data and "Q" in data:
                    i_key, q_key = "I", "Q"
                else:
                    raise KeyError(
                        f"Cannot derive state for measurement {record.key!r}; "
                        f"missing IQ outputs {i_key!r} and/or {q_key!r}."
                    )

            data[record.state_output_name() or f"{record.key}.state"] = derive_state(
                {"I": data[i_key], "Q": data[q_key]},
                rule,
            )

        return data

    _processor.__name__ = "derive_circuit_measurement_states"
    return _processor
