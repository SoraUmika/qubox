# Prompt Log

**Date:** 2026-04-04 16:47:50
**Task:** add-qm-reachability-preflight
**Target files:** qubox/hardware/controller.py,tests/test_connection_policy.py,docs/CHANGELOG.md

## Original Request

go ahead

## Response / Changes Made

Added a bounded TCP reachability preflight in HardwareController.open_qm using the QuantumMachinesManager's resolved host and port before attempting the live open_qm RPC. The controller now raises ConnectionError immediately when the QM endpoint is unreachable instead of entering the slower open path. Added focused tests covering endpoint resolution and the fail-fast behavior, updated the changelog, and reran the focused regression suite successfully.

## Context

(none)

## Validation Performed

- [ ] Compiled successfully
- [ ] Simulator check passed
- [ ] Standard experiments verified
- [ ] Unit tests pass
- [ ] Docs updated (API_REFERENCE.md, docs/CHANGELOG.md, notebooks)
