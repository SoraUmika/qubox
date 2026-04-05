# Prompt Log

**Date:** 2026-04-04 17:39:12
**Task:** remove-repo-owned-deprecations
**Target files:** qubox/hardware/config_engine.py, qubox/experiments/config_builder.py, qubox/programs/circuit_runner.py, qubox/pulses/factory.py, qubox/tests/test_parameter_resolution_policy.py, tests/test_connection_policy.py, docs/CHANGELOG.md

## Original Request

fix all deprecatioins(meaning remove them)

## Response / Changes Made

Removed qubox-owned deprecation emitters by dropping the deprecated top-level version key from live QM config generation, keeping CircuitRunner.compile() as a supported compatibility path without a DeprecationWarning, and treating arbitrary_blob as a supported compatibility shape without a DeprecationWarning. Added regression tests for ConfigEngine, ConfigBuilder, and PulseFactory, restored marshmallow to 3.23.3 after dependency experiments, and revalidated with focused pytest, the full pytest suite, and the hosted simulator trust gate. A raw import probe still shows 12 RemovedInMarshmallow4Warning warnings from qm-qua 1.2.6 itself, which are upstream and not removable from qubox code without patching the dependency.

## Context

Follow-up to the repo architecture hardening and warning cleanup work. The user explicitly asked to remove deprecations rather than only suppress them. The remaining import-time warnings were verified to come from qm-qua 1.2.6 itself during import qm, after reverting exploratory marshmallow downgrades back to marshmallow 3.23.3.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
