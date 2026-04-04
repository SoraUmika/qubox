# qubox Migration Guide

> **Historical document (2026-03-13).** This describes the original migration
> path from `qubox_v2_legacy` to `qubox`. The `qubox_v2_legacy` package has
> since been fully eliminated. The current API is documented in
> [API Reference](../API_REFERENCE.md).

Date: 2026-03-13

## Goal

Move user-facing code from `qubox_v2_legacy` to `qubox` without requiring an immediate
rewrite of the entire backend stack.

## Canonical Import Changes

- Old: `from qubox_v2_legacy.experiments.session import SessionManager`
- New: `from qubox import Session`

- Old: instantiate `SessionManager(...)` then call `session.open()`
- New: call `Session.open(...)`

## Old Path -> New Path

- `SessionManager` -> `Session`
- direct experiment classes -> `session.exp.*` template namespaces
- ad hoc gate objects -> `session.ops.*`
- circuit-first wrappers -> `session.sequence()` or `session.circuit()`
- hidden sweep kwargs -> explicit `session.sweep.*`
- implicit acquisition handling -> explicit `session.acquire.*`

## Examples

### Session startup

Old:

```python
from qubox_v2_legacy.experiments.session import SessionManager

session = SessionManager(
    sample_id="sampleA",
    cooldown_id="cd_2026_03_13",
    registry_base="E:/qubox",
)
session.open()
```

New:

```python
from qubox import Session

session = Session.open(
    sample_id="sampleA",
    cooldown_id="cd_2026_03_13",
    registry_base="E:/qubox",
)
```

### Standard experiments

Old:

```python
from qubox_v2_legacy.experiments.spectroscopy.qubit import QubitSpectroscopy

exp = QubitSpectroscopy(session)
result = exp.run(...)
analysis = exp.analyze(result)
```

New:

```python
result = session.exp.qubit.spectroscopy(...)
```

### Custom control

Old:

```python
from qubox_v2_legacy.programs.circuit_runner import QuantumCircuit, Gate
```

New:

```python
seq = session.sequence()
seq.add(session.ops.x90("q0"))
...
result = session.exp.custom(sequence=seq, ...)
```

## Compatibility Notes

- `qubox_v2_legacy` is still present for compatibility and deep internals.
- The new `Session` object proxies unknown attributes to the underlying legacy
  session object, so notebook flows can migrate incrementally.
- Not every historical experiment class has a first-class `session.exp.*`
  wrapper yet. For unported cases, continue to use the compatibility path.

## Removed or Quarantined Public Direction

The refactor deliberately stops advertising several overlapping entry points as
equally canonical:

- direct use of multiple circuit/compiler facades
- notebook-only session initialization patterns
- scattered public access to builder internals for routine experiment work

## Notebook Migration

The notebooks now start from `qubox.Session` as the canonical session surface.
Deeper legacy imports may remain temporarily where the notebook still exercises
compatibility-only features that have not yet been migrated into the new public
API.
