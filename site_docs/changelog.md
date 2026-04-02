# Changelog

!!! info "Policy"
    Every modification to the codebase is logged here. Entries are append-only — previous records are never modified.

---

::: tip
For the full raw changelog, see [`docs/CHANGELOG.md`](https://github.com/SoraUmika/qubox/blob/main/docs/CHANGELOG.md) in the repository.
:::

## 2026-03-31 — Architecture Refactor Phase 2

**Classification: Major**

Completed three major consolidation items from the architecture audit:

### Analysis → qubox_tools Merge

Eliminated all 50+ `from qubox.analysis.*` import references across the codebase, redirecting them to canonical `qubox_tools` locations. The `qubox/analysis/` package now contains only backward-compatible shims.

| Old Import | New Canonical Location |
|-----------|----------------------|
| `qubox.analysis.analysis_tools` | `qubox_tools.algorithms.transforms` |
| `qubox.analysis.algorithms` | `qubox_tools.algorithms.core` |
| `qubox.analysis.cQED_models` | `qubox_tools.fitting.cqed` |
| `qubox.analysis.cQED_plottings` | `qubox_tools.plotting.cqed` |
| `qubox.analysis.output` | `qubox_tools.data.containers` |
| `qubox.analysis.metrics` | `qubox_tools.algorithms.metrics` |
| `qubox.analysis.fitting` | `qubox_tools.fitting.routines` |
| `qubox.analysis.post_process` | `qubox_tools.algorithms.post_process` |
| `qubox.analysis.pulseOp` | `qubox.core.pulse_op` |

### Workflow Extraction

Created `qubox.workflow` package with portable stage-checkpoint, fit-gate, calibration-patch, and pulse-seeding logic. `qubox.notebook.workflow` is now a thin wrapper.

### Notebook Surface Slimming

Split `qubox.notebook` (~120 exports) into two tiers:

- **`qubox.notebook`** — essentials (~65 symbols)
- **`qubox.notebook.advanced`** — infrastructure (~45 symbols)

---

## 2026-03-31 — Architecture Refactor Phase 1

**Classification: Major**

Replaced `cQED_attributes` (god-object dict) with `DeviceMetadata` — a frozen dataclass with live `CalibrationStore` reference. Updated all experiment classes, session management, and tests.

---

## Earlier Entries

See the full [changelog in the repository](https://github.com/SoraUmika/qubox/blob/main/docs/CHANGELOG.md) for historical entries.
