# Prompt Log

**Date:** 2026-04-03 03:19:54
**Task:** remove-legacy-session-and-standard-measuremacro-debt
**Target files:** qubox/session/session.py,qubox/backends/qm/runtime.py,qubox/programs/circuit_runner.py,qubox/calibration/models.py,qubox/experiments/workflows/library.py,qubox/experiments/spectroscopy/resonator.py,qubox/experiments/spectroscopy/qubit.py,qubox/experiments/time_domain/coherence.py,qubox/experiments/time_domain/rabi.py,qubox/experiments/calibration/gates.py,qubox/experiments/calibration/readout.py,qubox/experiments/calibration/reset.py,qubox/experiments/tomography/qubit_tomo.py,qubox/experiments/tomography/wigner_tomo.py,qubox/experiments/tomography/fock_tomo.py,qubox/tests/test_parameter_resolution_policy.py,tests/test_standard_experiments_simulation_helper.py,tests/test_qubox_public_api.py,README.md,API_REFERENCE.md,docs/CHANGELOG.md,tutorials/01_getting_started_basic_experiments.ipynb,tools/validate_standard_experiments_simulation.py

## Original Request

runs simulator, refactor/redesign stadnard expierments so that it works veryfy them, remove depcreated v2 version, remove ALL LEGACY and measureMacro dependencies

## Response / Changes Made

Removed the deprecated Session.legacy_session alias, deleted CircuitRunner.compile_v2(), migrated the hosted standard-experiment simulator helper to binding-backed readout configuration, pushed resonator readout-op selection and additional experiment build provenance onto explicit ReadoutHandle flow, updated stale docs/tutorial references, migrated stale qubox_v2 test monkeypatch paths, and revalidated with focused pytest, circuit-runner serialization checks, and a hosted 20/20 standard-experiment simulator trust gate.

## Context

Refactor roadmap slice focused on standard experiments, readout ownership, deprecated v2 surfaces, and simulator validation. Required preserving compiled QUA fidelity, Python 3.12.10, QM/QUA 1.2.6, hosted validation on 10.157.36.68 / Cluster_2, and keeping notebook workflows synchronized with user-visible API changes.

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
