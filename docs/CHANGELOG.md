# qubox Change Log

> **Note:** Historical entries below may reference `qubox_v2` — the package that
> was renamed and eventually eliminated. The canonical package is now `qubox`.

## Change-Log Policy

Every modification to the codebase must be logged in this file.

Each entry must include:

- **Date** — ISO-8601 date of the change.
- **Summary** — concise description of what changed and why.
- **Files affected** — list of modified files.
- **Classification level**:
  - **Minor** — documentation, comments, formatting, trivial fixes.
  - **Moderate** — single-feature additions, non-breaking API changes, bug fixes.
  - **Major** — schema changes, breaking API changes, architectural refactors,
    multi-file structural changes.

**Rules:**

1. Entries must be **appended only** — previous records must never be modified.
2. The AI agent must self-assess the classification level for each change.
3. Each entry should be self-contained and understandable without external context.
4. **No automatic commits.** The AI agent must NEVER run `git commit` or
   `git push` without explicit user approval. All changes must be staged and
   presented for manual review before committing.

---

## Entries

### 2026-04-05 — Final Hardening Follow-Up: Public JSON Loaders

**Classification: Moderate**

**Summary:**

Completed one more targeted hardening pass after the broader robustness sweep.

1. **`qubox/hardware/config_engine.py`**: Fixed the malformed constructor type hint
  for `hardware_extras_keys` to `set[str] | None`.
2. **`qubox/notebook/runtime.py`**: Hardened notebook bootstrap loading so malformed
  JSON raises a file-specific `ValueError` and non-object payloads are rejected.
3. **`qubox/workflow/stages.py`**: Hardened both `load_legacy_reference()` and
  `load_stage_checkpoint()` with explicit `JSONDecodeError` handling and JSON-object
  validation.
4. **`qubox/devices/registry.py`**: Hardened `load_sample_info()` so corrupted
  `sample.json` files raise clear, path-specific errors instead of raw decode failures.

**Files affected:**
- `qubox/hardware/config_engine.py`
- `qubox/notebook/runtime.py`
- `qubox/workflow/stages.py`
- `qubox/devices/registry.py`

---

### 2026-04-05 — Robustness Hardening: JSON Safety, Session Guard, Type Modernization

**Classification: Moderate**

**Summary:**

Final extensive pass for inconsistencies and robustness improvements across the codebase.

1. **`qubox/calibration/store.py`**: Wrapped `json.load()` in `_load_or_create()` with
   `try/except json.JSONDecodeError` and added `isinstance(raw, dict)` check. Malformed
   calibration files now raise a clear `ValueError` instead of crashing with `AttributeError`.
2. **`qubox/calibration/patch_rules.py`**: Replaced bare `except Exception: pass` in
   `build_default_rules()` with `except Exception:` that logs at DEBUG level with
   `exc_info=True`. Added `logging` import and module-level `_logger`.
3. **`qubox/core/hardware_definition.py`**: Narrowed two bare `except Exception:` blocks
   in `seed_cqed_params()` and `save_devices()` merge paths to
   `except (json.JSONDecodeError, OSError)` with `_logger.warning()`.
4. **`qubox/core/config.py`**: Wrapped `json.loads()` in `HardwareConfig.from_json()` with
   `try/except json.JSONDecodeError`, raising `ValueError` with file path context.
5. **`qubox/hardware/config_engine.py`**: Wrapped `json.loads()` in
   `_load_hardware()` with `try/except json.JSONDecodeError` raising `ValueError`.
   Modernized type annotations: `Optional[X]` → `X | None`, `Dict[K,V]` → `dict[K,V]`,
   `Set[X]` → `set[X]`.
6. **`qubox/hardware/controller.py`**: Modernized all type annotations from
   `Optional[Union[X, Y]]` / `Dict[K,V]` / `List[X]` to PEP 604/585 syntax (`X | Y | None`,
   `dict[K,V]`, `list[X]`). Removed unused `Dict`, `List`, `Optional`, `Union` imports.
7. **`qubox/session/session.py`**: Added use-after-close guard. Session now tracks `_closed`
   flag; `close()` sets it; all hardware-accessing properties (`backend`, `hardware`,
   `config_engine`, `calibration`, `pulse_mgr`, `runner`, `devices`, `orchestrator`,
   `simulation_mode`) and `connect()` raise `RuntimeError` if accessed after close.

**Files affected:**
- `qubox/calibration/store.py`
- `qubox/calibration/patch_rules.py`
- `qubox/core/hardware_definition.py`
- `qubox/core/config.py`
- `qubox/hardware/config_engine.py`
- `qubox/hardware/controller.py`
- `qubox/session/session.py`

---

### 2026-04-05 — Codebase Consistency And Safety Hardening Pass

**Classification: Moderate**

**Summary:**

Fixed inconsistencies and safety issues identified by a full codebase audit:

1. **`qubox/core/logging.py`**: Added missing `from __future__ import annotations`;
   replaced `Union[int, str]` with `int | str`; removed unused `typing` imports.
2. **`qubox/experiments/cavity/fock.py`**: Fixed 3 error messages referencing removed
   `qubox_v2.tools.generators` → `qubox.tools.generators`.
3. **`qubox/hardware/controller.py`**: Replaced 2 bare `suppress(Exception)` blocks in
   `close()` and calibration error path with explicit `try/except` that logs warnings.
   Prevents silent hardware-state errors during shutdown.
4. **`tools/build_context_notebook.py`**: Replaced `eval(name)` with safe `locals().get()`
   registry lookup for calibration state machine collection.
5. **`qubox_lab_mcp/server.py`**: Added warning log when MCP HTTP server binds to
   non-loopback address.

**Files affected:**
- `qubox/core/logging.py`
- `qubox/experiments/cavity/fock.py`
- `qubox/hardware/controller.py`
- `tools/build_context_notebook.py`
- `qubox_lab_mcp/server.py`

---

### 2026-04-05 — Documentation Sync: API Reference And Site Docs

**Classification: Minor**

**Summary:**

Updated API_REFERENCE.md and site_docs/ to match the current repository state
after the recent cleanup sessions:

1. **API_REFERENCE.md**: Updated `notebook.workflow` description from "compatibility wrapper"
   to "re-exports portable primitives and adds shared-session notebook helpers". Updated date.
2. **site_docs/guides/migration.md**: Corrected guidance that directed users to non-existent
   `qubox.legacy.*` imports. Updated overview and breaking-changes table to reflect both
   `qubox_v2_legacy` and `qubox.legacy` are fully removed.
3. **site_docs/guides/index.md**: Changed migration guide description from referencing
   `qubox_v2_legacy` to "legacy codebases".
4. **site_docs/api/notebook.md**: Replaced fabricated function names (`nb_save_checkpoint`,
   `nb_fit_gate`, `nb_preview_patch`) with actual exports from `qubox.notebook.workflow`.
5. **site_docs/api/session.md**: Fixed experiment domain table — replaced non-existent
   `session.exp.cavity` and `session.exp.spa` with actual accessors (`readout`, `storage`, `reset`).
6. **site_docs/api/experiments/spa.md**: Added note that SPA experiments are standalone classes,
   not yet exposed through `session.exp`.
7. **site_docs/changelog.md**: Added entries for the April 2026 cleanup and hardening work.

**Files affected:**
- `API_REFERENCE.md`
- `site_docs/guides/migration.md`
- `site_docs/guides/index.md`
- `site_docs/api/notebook.md`
- `site_docs/api/session.md`
- `site_docs/api/experiments/spa.md`
- `site_docs/changelog.md`

---

### 2026-04-05 — Repository Naming And Guidance Cleanup

**Classification: Minor**

**Summary:**

Cleaned up stale naming, misleading guidance, and undated compatibility paths across the repository:

1. **Agent instruction files** (`.cursorrules`, `.clinerules`, `.windsurfrules`): Replaced stale guidance directing agents to non-existent `qubox/legacy/` and `qubox.legacy.*` imports with correct "do not exist" messaging. Fixed Python version from `3.12.13` to `3.12.10`.
2. **Module docstrings**: Updated 13 source files that still had `qubox_v2.*` module docstrings and usage examples to use correct `qubox.*` paths.
3. **Notebook workflow**: Replaced misleading `.. deprecated::` directive in `qubox/notebook/workflow.py` with a `.. note::` directive — the module is the active notebook workflow surface, not deprecated.
4. **Temporary compatibility paths**: Added `(added 2026-03)` date stamps to undated `allow_default_state_prep` compatibility paths in `qubox/experiments/cavity/fock.py` and `storage.py`.
5. **Logger mapping**: Added dated comment and removal guidance to the `qubox_v2.*` logger name mapping in `qubox/core/logging.py`.

**Files affected:**
- `.cursorrules`, `.clinerules`, `.windsurfrules`
- `qubox/programs/spectroscopy.py`, `readout.py`, `calibration.py`, `cavity.py`, `time_domain.py`, `tomography.py`
- `qubox/programs/builders/__init__.py`
- `qubox/experiments/experiment_base.py`, `result.py`, `configs.py`
- `qubox/calibration/algorithms.py`, `pulse_train_tomo.py`
- `qubox/core/hardware_definition.py`, `logging.py`
- `qubox/notebook/workflow.py`
- `qubox/experiments/cavity/fock.py`, `storage.py`

---

### 2026-04-05 — Stop Tracking Generated Docs And Validation Outputs

**Classification: Minor**

**Summary:**

Stopped tracking two generated outputs that were creating routine repository
noise: the built MkDocs HTML tree under `site/` and the local hosted-simulator
report at `tools/simulation_validation_report.json`. Both outputs remain
regenerable locally, but they are now treated as disposable artifacts instead
of source-controlled content.

**Files affected:**

- `.gitignore`
- `docs/CHANGELOG.md`
- `site/`
- `tools/simulation_validation_report.json`

### 2026-04-05 — Trim Repository Hygiene Noise

**Classification: Minor**

**Summary:**

Reduced several remaining repository-noise hotspots by cleaning the legacy
`ConfigBuilder` compatibility module header/import clutter, exporting
`load_legacy_reference()` on the canonical `qubox.workflow` surface so the
portable workflow API is more self-contained, moving the one-off import-surface
verification script out of the repo root into `tools/`, and dropping clearly
generated local artifacts from version control (`test_output.txt` and
`qubox.egg-info/`).

**Files affected:**

- `.gitignore`
- `API_REFERENCE.md`
- `qubox/experiments/config_builder.py`
- `qubox/workflow/__init__.py`
- `tests/test_qubox_public_api.py`
- `tools/validate_import_surface.py`
- `docs/CHANGELOG.md`

### 2026-04-04 — Remove Repo-Owned Deprecation Emitters

**Classification: Moderate**

**Summary:**

Removed the deprecated top-level `version` field from the live QM config paths
so qubox no longer feeds a deprecated QUA config key into the QM SDK, turned
`CircuitRunner.compile()` into a supported compatibility shim instead of a
runtime `DeprecationWarning`, and promoted the legacy `arbitrary_blob` pulse
shape to a supported compatibility format by removing its deprecation warning.
Added regression tests covering the config-engine path, the legacy
`ConfigBuilder` path, and the pulse-factory compatibility case.

**Files affected:**

- `qubox/hardware/config_engine.py`
- `qubox/experiments/config_builder.py`
- `qubox/programs/circuit_runner.py`
- `qubox/pulses/factory.py`
- `qubox/tests/test_parameter_resolution_policy.py`
- `tests/test_connection_policy.py`
- `docs/CHANGELOG.md`

### 2026-04-04 — Clean Up Test And Validation Warning Noise

**Classification: Minor**

**Summary:**

Removed warning noise from the broad validation loop by fixing the custom
module-loading helpers used in refactor-safety tests so they no longer trigger
import-spec deprecation warnings, making the legacy `CircuitRunner.compile()`
warning explicit in its regression test, suppressing the non-fatal covariance
warning in `fit_number_splitting()` when the fit still succeeds, and filtering
known third-party QM/Marshmallow deprecations in pytest and the hosted
standard-experiment simulator validation tool.

**Files affected:**

- `qubox/tests/test_workflow_safety_refactor.py`
- `qubox/tests/test_calibration_fixes.py`
- `qubox/tests/test_parameter_resolution_policy.py`
- `qubox_tools/fitting/calibration.py`
- `pyproject.toml`
- `tools/validate_standard_experiments_simulation.py`
- `docs/CHANGELOG.md`

### 2026-04-04 — Restore Notebook Compatibility Tests And Trim AllXY Validation Cost

**Classification: Moderate**

**Summary:**

Reconciled notebook compatibility drift by letting notebook runtime helpers
accept both the modern `session.hardware` surface and the older `session.hw`
alias, updated the notebook workflow tests to patch the portable workflow
modules they now wrap, replaced a stale hardcoded adapter-registry count check
with an assertion against the required standard-template set, and reduced the
standard simulator validation cost for `calibration.all_xy` to a small
representative subset so the trust gate stays aligned with the repo's quick
validation policy.

**Files affected:**

- `qubox/notebook/runtime.py`
- `tests/test_notebook_workflow.py`
- `tests/test_standard_experiments.py`
- `tools/validate_standard_experiments_simulation.py`
- `docs/CHANGELOG.md`

### 2026-04-04 — Add Bounded QM Reachability Preflight Before Open

**Classification: Moderate**

**Summary:**

Added a bounded TCP reachability preflight to `HardwareController.open_qm()`
using the QM manager's resolved host and port before attempting the live
`open_qm` RPC. This prevents the controller from entering the slower QM open
path when the endpoint is already unreachable and turns that case into an
immediate `ConnectionError` with the target endpoint in the message.

**Files affected:**

- `qubox/hardware/controller.py`
- `tests/test_connection_policy.py`
- `docs/CHANGELOG.md`

### 2026-04-04 — Consolidate Preflight Checks And Harden Session Teardown

**Classification: Moderate**

**Summary:**

Removed the duplicated standalone `qubox.preflight` implementation so the
public import path now re-exports the single `qubox.core.preflight`
implementation, preventing future safety-check drift. Also hardened
`SessionManager.close()` so shutdown keeps attempting later persistence steps
after an earlier save failure and records a structured teardown report instead
of leaving calibration save as the lone unguarded step.

**Files affected:**

- `qubox/experiments/session.py`
- `qubox/preflight.py`
- `tests/test_connection_policy.py`
- `docs/CHANGELOG.md`

### 2026-04-04 — Harden Runtime Failure Handling And Patch Validation

**Classification: Moderate**

**Summary:**

Hardened several runtime and calibration safety paths that previously allowed
silent or partially applied failures. `ProgramRunner` and `QueueManager` now
fail closed on result-fetch and processor errors unless partial results are
explicitly allowed, compiled-circuit execution now routes through the canonical
session runner and the repository-standard `Cluster_2` flow, calibration patch
preview/apply now validates patch operations before mutation and rejects
unknown ops, `ExperimentRunner.run()` no longer accepts ignored simulation-mode
flags, and the persistence verifier no longer enables pickle when reading `.npz`
artifacts.

**Files affected:**

- `qubox/hardware/program_runner.py`
- `qubox/hardware/queue_manager.py`
- `qubox/programs/circuit_execution.py`
- `qubox/calibration/orchestrator.py`
- `qubox/experiments/base.py`
- `qubox/verification/persistence_verifier.py`
- `tests/gate_architecture/conftest.py`
- `tests/gate_architecture/test_gate_architecture.py`
- `tests/test_connection_policy.py`
- `qubox/tests/test_calibration_fixes.py`
- `docs/CHANGELOG.md`

### 2026-04-04 — Harden Session Host Resolution And Reconcile Architecture Docs

**Classification: Moderate**

**Summary:**

Removed the unsafe implicit `localhost` fallback from the session bootstrap
path so both `SessionManager` and `ExperimentRunner` now require a QOP host
either explicitly or via persisted `hardware.json` extras. Reduced core-layer
type coupling by switching the internal artifacts and preflight helpers to the
shared `SessionProtocol`, cleaned central runtime docstrings and autotune
journal `code_path` metadata to use the current `qubox.*` namespace, and
updated the architecture/API docs to match the live package layout and
simulation-mode behavior.

**Files affected:**

- `qubox/core/utils.py`
- `qubox/experiments/session.py`
- `qubox/experiments/base.py`
- `qubox/core/artifacts.py`
- `qubox/core/preflight.py`
- `qubox/artifacts.py`
- `qubox/preflight.py`
- `qubox/autotune/run_post_cavity_autotune_v1_1.py`
- `README.md`
- `API_REFERENCE.md`
- `site_docs/architecture/package-map.md`
- `site_docs/architecture/execution-flow.md`
- `qubox/docs/API_REFERENCE.md`
- `qubox/docs/ARCHITECTURE.md`
- `docs/CHANGELOG.md`
- `tests/test_connection_policy.py`

### 2026-04-04 — Documentation Cleanup Pass

**Classification: Minor**

**Summary:**

Docs-only cleanup to make repository documentation clearer, internally
consistent, and aligned with the live codebase after the legacy elimination
and package tree pruning completed earlier on 2026-04-04.

Key changes:

- Rewrote `README.md` with a structured documentation map (canonical /
  supporting / historical), consistent import surfaces table, and cleaned
  repository layout.
- Cleaned `API_REFERENCE.md`: removed redundant "Important corrections vs
  older docs" framing, tightened notes & limitations, removed stale
  `qubox.legacy` reference in §6.2.
- Updated architecture references in `AGENTS.md` §4 and §11 directory guide.
- Updated `CLAUDE.md` and `.github/copilot-instructions.md` architecture
  sections to match the unified layout description.
- Fixed stale `qubox.legacy` / `qubox_v2_legacy` references in skill files:
  `experiment-design/SKILL.md`, `repo-onboarding/SKILL.md`,
  `codebase-refactor-reviewer/references/test-map.md`.
- Fixed stale `qubox_v2_legacy` reference in `.github/WORKFLOW_BLUEPRINT.md`.
- Updated `site_docs/architecture/package-map.md` scope-boundary note.
- Fixed stale backend policy in `docs/qubox_architecture.md`.
- Added historical-document labels to 9 docs that reference removed packages:
  `docs/qubox_architecture.md`, `docs/qubox_refactor_verification.md`,
  `docs/qubox_tools_analysis_split.md`, `docs/qubox_migration_guide.md`,
  `docs/qubox_experiment_framework_refactor_proposal.md`,
  `docs/architecture_review.md`, `docs/gate_architecture_review.md`,
  `docs/codebase_graph_survey.md`, `SURVEY.md`,
  `notebooks/migration_plan.md`, `notebooks/COMPILATION_VERIFICATION_REPORT.md`.

**Files affected:**

- `README.md`
- `API_REFERENCE.md`
- `AGENTS.md`
- `CLAUDE.md`
- `.github/copilot-instructions.md`
- `.github/WORKFLOW_BLUEPRINT.md`
- `docs/qubox_architecture.md`
- `docs/qubox_refactor_verification.md`
- `docs/qubox_tools_analysis_split.md`
- `docs/qubox_migration_guide.md`
- `docs/qubox_experiment_framework_refactor_proposal.md`
- `docs/architecture_review.md`
- `docs/gate_architecture_review.md`
- `docs/codebase_graph_survey.md`
- `docs/CHANGELOG.md`
- `site_docs/architecture/package-map.md`
- `.github/skills/experiment-design/SKILL.md`
- `.github/skills/repo-onboarding/SKILL.md`
- `.github/skills/codebase-refactor-reviewer/references/test-map.md`
- `SURVEY.md`
- `notebooks/migration_plan.md`
- `notebooks/COMPILATION_VERIFICATION_REPORT.md`

### 2026-04-04 — Move Demo And GUI Utilities Out Of The qubox Package Namespace

**Classification: Moderate**

**Summary:**

Moved the non-core demo and GUI helper scripts out of `qubox/` into top-level
`tools/` so the package boundary stays focused on runtime, calibration,
workflow, and QUA-facing code. The dead `qubox.migration` stub was removed,
the public docs were updated to point users at `tools/demos/` and
`tools/program_gui.py`, and the remaining verification docstrings were cleaned
to use the current `qubox` import path.

**Files affected:**

- `tools/program_gui.py`
- `tools/demos/quickstart.py`
- `tools/demos/circuit_architecture_demo.py`
- `tools/demos/session_startup_demo.py`
- `qubox/gui/*`
- `qubox/examples/*`
- `qubox/migration/__init__.py`
- `qubox/autotune/__init__.py`
- `qubox/verification/waveform_regression.py`
- `qubox/verification/schema_checks.py`
- `README.md`
- `API_REFERENCE.md`
- `site_docs/architecture/package-map.md`
- `docs/CHANGELOG.md`

### 2026-04-04 — Remove Non-Core Gate Modeling Stack From qubox.gates

**Classification: Major**

**Summary:**

Removed the dormant gate-model, gate-sequence, fidelity, noise, and free-
evolution modules from `qubox.gates`, leaving only the runtime hardware gate
implementations used by control realization and QUA compilation. The legacy
`Gate` model wrapper was also removed from the active builders in favor of
simple gate-like protocols or loose typing where needed. The wider non-core
scan also removed the empty `qubox.analysis` and `qubox.optimization`
tombstone directories.

**Files affected:**

- `qubox/gates/*`
- `qubox/gates/models/*`
- `qubox/programs/builders/simulation.py`
- `qubox/programs/builders/cavity.py`
- `README.md`
- `API_REFERENCE.md`
- `docs/CHANGELOG.md`
- `site_docs/api/gates.md`
- `site_docs/architecture/package-map.md`
- `docs/architecture_audit.md`
- `docs/architecture/ARCHITECTURE_AUDIT.md`
- `qubox.egg-info/SOURCES.txt`
- `qubox/analysis`
- `qubox/optimization`

### 2026-04-04 — Remove Standalone Simulation And Ansatz Compile Packages From qubox

**Classification: Major**

**Summary:**

Removed the dormant `qubox.compile` and `qubox.simulation` package trees from
`qubox` so the repository boundary stays focused on session orchestration,
calibration, QUA compilation, and QM-hosted validation. Numerical cQED system
simulation and ansatz-style gate-synthesis workflows are now explicitly out of
scope for `qubox` and are intended to move to `cqed_sim` instead. QM-hosted
simulation support used for compiled-program validation remains in place.

**Files affected:**

- `qubox/compile/*`
- `qubox/simulation/*`
- `pyproject.toml`
- `qubox.egg-info/requires.txt`
- `qubox.egg-info/SOURCES.txt`
- `README.md`
- `API_REFERENCE.md`
- `test_migration.py`
- `site_docs/api/gates.md`
- `site_docs/architecture/package-map.md`
- `docs/architecture_audit.md`
- `docs/architecture/ARCHITECTURE_AUDIT.md`
- `docs/CHANGELOG.md`

### 2026-04-04 — Reconcile Canonical API And Agent Instruction Docs

**Classification: Minor**

**Summary:**

Removed stale references to the deleted in-repo legacy package surface from the
agent instruction docs and replaced the corrupted `API_REFERENCE.md` content
with a reconciled reference built from the live package layout, exports, and QM
runtime structure. This change is documentation-only and does not alter runtime
behavior.

**Files affected:**

- `AGENTS.md`
- `.github/copilot-instructions.md`
- `API_REFERENCE.md`
- `docs/CHANGELOG.md`

### 2026-04-03 — Remove measureMacro And Finish Explicit Readout Calibration Flow

**Classification: Major**

**Summary:**

Removed the remaining `measureMacro` singleton from the active code path.
Readout-calibration experiments, validation helpers, and notebook verification
tools now seed and persist explicit `MeasurementConfig` / `ReadoutHandle`
state instead of mutating hidden global measurement state. The
`qubox.programs.macros` package now exports only `emit_measurement()` and
`sequenceMacros`, notebook-facing calibration examples use
`set_active_readout` / `update_readout_config`, and `ProgramBuildResult`
snapshots consistently use `readout_state`.

**Files affected:**

- `qubox/programs/macros/measure.py`
- `qubox/programs/macros/__init__.py`
- `qubox/programs/gate_lowerers/protocol.py`
- `qubox/core/bindings.py`
- `qubox/pulses/manager.py`
- `qubox/programs/macros/sequence.py`
- `qubox/experiments/calibration/readout.py`
- `qubox/experiments/result.py`
- `qubox/programs/circuit_compiler.py`
- `tools/validate_circuit_runner_serialization.py`
- `tools/validate_gate_tuning_visualization.py`
- `tools/test_all_simulations.py`
- `qubox/autotune/run_post_cavity_autotune_v1_1.py`
- `qubox/backends/qm/runtime.py`
- `tests/test_readout_binding_ownership.py`
- `tests/test_qubox_public_api.py`
- `tests/gate_architecture/test_gate_architecture.py`
- `qubox/tests/test_workflow_safety_refactor.py`
- `qubox/tests/test_calibration_fixes.py`
- `notebooks/verify_compilation.py`
- `notebooks/post_cavity_experiment_context.ipynb`
- `notebooks/post_cavity_experiment_quantum_circuit.ipynb`
- `API_REFERENCE.md`
- `docs/CHANGELOG.md`

### 2026-04-03 — Remove Legacy Session Alias And Standard-Experiment Readout Fallbacks

**Classification: Major**

**Summary:**

Removed the deprecated `Session.legacy_session` access path in favor of
`session.session_manager`, deleted `CircuitRunner.compile_v2()`, and pushed
more of the active standard-experiment stack onto explicit binding-backed
readout flow. The QM runtime now instantiates notebook/template experiments
through the shared `SessionManager` directly, resonator readout-operation
selection no longer mutates `measureMacro`, and additional experiment build
artifacts now capture readout provenance from explicit `ReadoutHandle`s rather
than re-reading singleton state. The hosted standard-experiment simulator trust
gate remained green at 20/20 after the refactor.

**Files affected:**

- `qubox/session/session.py`
- `qubox/backends/qm/runtime.py`
- `qubox/programs/circuit_runner.py`
- `qubox/calibration/models.py`
- `qubox/experiments/workflows/library.py`
- `qubox/experiments/spectroscopy/resonator.py`
- `qubox/experiments/spectroscopy/qubit.py`
- `qubox/experiments/time_domain/coherence.py`
- `qubox/experiments/time_domain/rabi.py`
- `qubox/experiments/calibration/gates.py`
- `qubox/experiments/calibration/readout.py`
- `qubox/experiments/calibration/reset.py`
- `qubox/experiments/tomography/qubit_tomo.py`
- `qubox/experiments/tomography/wigner_tomo.py`
- `qubox/experiments/tomography/fock_tomo.py`
- `qubox/tests/test_parameter_resolution_policy.py`
- `tools/validate_standard_experiments_simulation.py`
- `tests/test_standard_experiments_simulation_helper.py`
- `tests/test_qubox_public_api.py`
- `README.md`
- `API_REFERENCE.md`
- `tutorials/01_getting_started_basic_experiments.ipynb`

### 2026-04-03 — Finalize Removal Of Tombstone Analysis Namespaces

**Classification: Moderate**

**Summary:**

Removed the last in-repo references to the deleted `qubox.analysis`
compatibility surface, migrated the circuit-validation tools onto
calibration-backed `DeviceMetadata`, and deleted the leftover
`qubox.analysis` / `qubox.optimization` tombstone packages so the tree now
matches the documented import surface.

**Changes:**

- Replaced stale `qubox.analysis.cQED_attributes` imports in the two circuit-validation tools
- Switched those tool-local session shims from mutable `cQED_attributes` snapshots to live `DeviceMetadata`
- Deleted the empty `qubox.analysis` and `qubox.optimization` tombstone namespaces
- Clarified in the API reference that those namespaces are no longer importable

**Files affected:**

- `tools/validate_circuit_runner_serialization.py` — use `DeviceMetadata` instead of removed analysis shim
- `tools/validate_gate_tuning_visualization.py` — use `DeviceMetadata` instead of removed analysis shim
- `API_REFERENCE.md` — clarified the final namespace-removal state
- `docs/CHANGELOG.md` — added this entry

### 2026-04-03 — Simulator Pull Fallback For Trust-Gate Validation

**Classification: Moderate**

**Summary:**

Hardened the hosted standard-experiment simulator validator against intermittent
QM sample-stream failures by retrying `get_simulated_samples()` and, when the
QM backend still refuses the sample pull, falling back to the waveform metadata
already returned by the simulator job. This keeps the trust-gate focused on
compiled scheduling structure instead of misclassifying transient sample-pull
transport failures as compilation regressions.

**Changes:**

- Added retry logic around simulator sample retrieval in the standard validation tool
- Added a waveform-metadata fallback that reconstructs controller activity masks when sample pulls fail
- Recorded the effective validation source (`samples` vs `waveform_report`) in PASS/FAIL messages and JSON reports
- Added unit coverage for waveform fallback reconstruction and fallback activation

**Files affected:**

- `tools/validate_standard_experiments_simulation.py` — retry + waveform-report fallback for simulator validation
- `tests/test_standard_experiments_simulation_helper.py` — added fallback reconstruction tests
- `docs/CHANGELOG.md` — added this entry

### 2026-04-03 — Standard Simulator Trust-Gate Fixes

**Classification: Moderate**

**Summary:**

Resolved the previously failing QM simulator trust-gate cases by fixing the
standard-experiment validation helper inputs, enforcing a legal minimum pulse
duration in `TimeRabiChevron`, and restoring callable state-preparation support
for storage Wigner tomography.

**Changes:**

- Registered the missing `r0` qubit pulse alias used by AllXY in the simulator helper
- Adjusted quick-validation timing inputs so T1, Ramsey, Echo, and storage T1 avoid illegal sub-4-cycle waits
- Passed an explicit minimal `state_prep` macro for NumSplitting in the simulator helper
- Updated `TimeRabiChevron` to start its duration sweep at the QM backend's legal minimum pulse length
- Allowed storage Wigner tomography prep steps to be supplied as either gate-like objects or callable QUA macros
- Normalized QM runtime Wigner args so the documented `state_prep=` API is converted into the expected `gates` list
- Re-ran `tools/validate_standard_experiments_simulation.py`; the report now shows `20` passes and `0` errors

**Files affected:**

- `tools/validate_standard_experiments_simulation.py` — fixed simulator helper pulse registration and quick-mode inputs
- `qubox/experiments/time_domain/chevron.py` — enforced legal minimum pulse duration for `TimeRabiChevron`
- `qubox/programs/builders/cavity.py` — accepted callable prep macros in storage Wigner builder
- `qubox/backends/qm/runtime.py` — normalized Wigner `state_prep` into `gates`
- `tools/simulation_validation_report.json` — updated full-suite validation result
- `limitations/qua_related_limitations.md` — removed the now-resolved standard-suite limitation entry
- `docs/CHANGELOG.md` — added this entry

### 2026-04-03 — Control-Program Execution Bridge

**Classification: Major**

**Summary:**

Completed the next control-layer milestone by making `ControlProgram` a
first-class custom execution body. Sessions can now build or normalize
control programs directly, `session.exp.custom(control=...)` can compile
them through the QM backend, and control-native barriers and pulse-phase
wrapping are lowered explicitly instead of being dropped.

**Changes:**

- Added `Session.control_program()` and `Session.to_control_program()` helpers
- Added `Session.realize_control_program()` and a best-effort control realizer for forward gate→pulse bridging
- Added `control_program` support to `ExecutionRequest` and `session.exp.custom(...)`
- Extended QM lowering so `ControlProgram` bodies map into legacy circuit IR for compilation
- Added explicit `align` / barrier lowering in `CircuitCompiler`
- Localized pulse-phase lowering by emitting matching pre/post frame updates around `PulseInstruction`
- Documented the current QM-lowering limitation for conditional `AcquireInstruction`
- Fixed two targeted public-surface regressions found during the earlier validation pass:
  `Session.resolve_alias()` now tolerates legacy sessions exposing `hw`, and
  `qubox.notebook.__all__` again exports `save_run_summary`

**Files affected:**

- `qubox/data/models.py` — added `ExecutionRequest.control_program` and manifest summary support
- `qubox/experiments/templates/library.py` — added `control=` to custom requests
- `qubox/session/session.py` — added control-program helpers and alias fallback fix
- `qubox/backends/qm/lowering.py` — lowered `ControlProgram` instructions into circuit IR
- `qubox/backends/qm/runtime.py` — accepted control-program custom bodies
- `qubox/programs/gate_lowerers/builtins.py` — added barrier lowerer
- `qubox/programs/circuit_compiler.py` — lowered `align` / barrier gates
- `qubox/notebook/__init__.py` — restored `save_run_summary` export
- `tests/test_control_program.py` — added control-program execution-path coverage
- `tests/test_qubox_public_api.py` — added session control-helper coverage
- `API_REFERENCE.md` — documented the new control-program session and custom-request APIs
- `limitations/qua_related_limitations.md` — documented unsupported conditional acquire lowering
- `docs/CHANGELOG.md` — added this entry

**Validation:**

- `get_errors` reported no diagnostics in the edited Python files
- `c:/python312/python.exe -m pytest tests/test_control_program.py tests/test_qubox_public_api.py -q` → passed (`11 passed`)
- Ruff still unavailable in the active Python environment unless installed separately

### 2026-04-02 — Control-Layer IR Kickoff

**Classification: Major**

**Summary:**

Started the new simulator/hardware bridge implementation by introducing a
canonical symbolic control-layer package and lowering hooks from `Sequence`
and `QuantumCircuit`. This establishes a shared transport for future pulse,
gate, QM, and simulator backends without replacing the current execution path
yet.

**Changes:**

- Added new `qubox.control` package with control-layer dataclasses for semantic gates,
  pulse instructions, waits, barriers, frame updates, frequency updates, acquisitions,
  sweep plans, durations, and provenance tags
- Added adapters that lower `Sequence` and `QuantumCircuit` into `ControlProgram`
- Added `.to_control_program()` methods to `Sequence` and `QuantumCircuit`
- Added focused unit tests for control-program lowering, implicit acquisition insertion,
  sweep preservation, and stable payload/text inspection
- Updated `API_REFERENCE.md` to document the new lowering methods and the new symbolic
  control-layer direction

**Files affected:**

- `qubox/control/__init__.py` — control-layer export surface
- `qubox/control/models.py` — canonical symbolic control IR dataclasses
- `qubox/control/adapters.py` — sequence/circuit lowering adapters
- `qubox/sequence/models.py` — added `Sequence.to_control_program()`
- `qubox/circuit/models.py` — added `QuantumCircuit.to_control_program()`
- `tests/test_control_program.py` — new unit tests
- `API_REFERENCE.md` — documented new lowering methods
- `docs/CHANGELOG.md` — added this entry

**Validation:**

- `get_errors` reported no workspace diagnostics in the new or edited Python files
- `c:/python312/python.exe -m pytest tests/test_control_program.py -q` → passed (`3 passed`)
- `c:/python312/python.exe -m pytest tests/test_control_program.py tests/test_qubox_public_api.py -q` surfaced 3 pre-existing unrelated failures in `tests/test_qubox_public_api.py`
- `c:/python312/python.exe -m ruff ...` could not be run because `ruff` is not installed in the active Python environment

### 2026-04-02 — Legacy Code Elimination

**Classification: Major**

**Summary:**

Complete removal of all legacy (`qubox_v2_legacy`, `qubox/legacy/`, `qubox.legacy`) references
from the codebase. The legacy packages were already deleted in prior refactors; this change
eliminates every remaining dead reference, stale comment, and backward-compatibility shim.

**Changes:**

- Removed `# qubox_v2/` path-marker header comments from 69 source files
- Removed `CircuitRunnerV2 = CircuitCompiler` backward-compatibility alias
- Removed 2 dead test functions that imported from `qubox_v2_legacy` (package doesn't exist)
- Updated all `qubox_v2_legacy.*` imports in `tools/` scripts to `qubox.*` equivalents
- Updated `qubox.legacy.*` imports in `notebooks/verify_compilation.py` to `qubox.*`
- Replaced stale `qubox_v2_legacy` docstring/comment references in 17 source files
- Updated `qubox_lab_mcp/resources/repo_resources.py` description (removed legacy path)
- Updated `CLAUDE.md`: removed `qubox/legacy/` from architecture, updated memory table and banned patterns
- Updated `docs/CHANGELOG.md` header note

**Files affected:**

- 69 files: `# qubox_v2/` header comment removal (across `qubox/compile/`, `qubox/gates/`,
  `qubox/core/`, `qubox/calibration/`, `qubox/verification/`, `qubox/hardware/`, `qubox/pulses/`,
  `qubox/programs/`, `qubox/simulation/`, `qubox/gui/`, `qubox/migration/`, `qubox/examples/`,
  `qubox/experiments/`, `qubox/tests/`)
- `qubox/programs/circuit_compiler.py` — removed `CircuitRunnerV2` alias
- `tests/qubox_tools/test_analysis_split.py` — removed 2 dead legacy test functions
- `tools/pulses_converter.py` — redirected imports
- `tools/analyze_imports.py` — redirected imports
- `tools/validate_notebooks.py` — redirected imports
- `tools/validate_gate_tuning_visualization.py` — redirected imports
- `tools/validate_circuit_runner_serialization.py` — redirected imports
- `tools/log_prompt.py` — updated example paths
- `notebooks/verify_compilation.py` — redirected imports
- `qubox/verification/__init__.py` — updated docstring
- `qubox_lab_mcp/resources/repo_resources.py` — updated description
- `qubox_tools/fitting/pulse_train.py` — updated docstring
- `CLAUDE.md` — updated architecture reference and banned patterns
- `docs/CHANGELOG.md` — updated header note, added this entry

**Validation:**

- `grep -r qubox_v2_legacy *.py` → 0 results
- `grep -r "# qubox_v2/" qubox/*.py` → 0 results
- `grep -r CircuitRunnerV2 *.py` → 0 results
- Test suite: 8 pre-existing failures (unchanged), 56 passing (up from 54 — 2 dead tests removed)

---

### 2026-04-02 — Architecture Refactor Phases 0–5

**Classification: Major**

**Summary:**

Six-phase architecture refactoring driven by `docs/architecture_audit.md`:
- **Phase 0**: Deleted 4 duplicate modules (session/context.py, session/state.py, core/persistence_policy.py, devices/sample_registry.py), redirected all imports
- **Phase 1**: Enhanced `SessionProtocol` typing on `ExperimentBase.__init__`, `CircuitCompiler.__init__`, `CalibrationOrchestrator.__init__`; enhanced `CalibrationSnapshot.from_session()` factory; added calibration snapshot capture to `ExperimentBase.build_program()` and `CircuitCompiler`
- **Phase 2**: Made `measureMacro` instantiable (was singleton-only); `CircuitCompiler` now uses per-instance approach when `measurement_config` is provided
- **Phase 3**: Extracted 12 IR frozen dataclasses + helpers from `circuit_runner.py` → new `circuit_ir.py` (460→ lines); migrated 6 downstream importers; `circuit_runner.py` re-exports for backward compat; deprecated `CircuitRunner.compile()` in favor of `CircuitCompiler.compile()`; migrated `circuit_execution.py` and `QMRuntime._run_custom` to use `CircuitCompiler` directly
- **Phase 4**: Fixed hardcoded `qubox_version="3.0.0"` in `QMRuntime` to import from `qubox.__version__`; added `mixer_calibration_path` field to `CalibrationSnapshot`; deduplicated `sanitize_nonfinite()` utility (was duplicated in HardwareController + ManualMixerCalibrator); added `CalibrationSnapshot.to_dict()` serialization; updated `RunManifest.to_dict()` to include mixer_calibration_path
- **Phase 5**: Created `SessionFactory` dataclass for programmatic/agent session creation; exported from `qubox.__init__.__all__`

**Files created:**

- `qubox/programs/circuit_ir.py` — IR types extracted from circuit_runner.py

**Files modified:**

- `qubox/programs/circuit_runner.py` — IR types replaced with re-exports from circuit_ir; `compile()` deprecated
- `qubox/programs/circuit_compiler.py` — imports from circuit_ir; lazy StreamSpec import updated
- `qubox/programs/circuit_display.py` — imports from circuit_ir
- `qubox/programs/circuit_postprocess.py` — imports from circuit_ir
- `qubox/programs/circuit_protocols.py` — imports from circuit_ir
- `qubox/programs/circuit_execution.py` — uses CircuitCompiler directly
- `qubox/programs/__init__.py` — added circuit_ir export; updated docstring
- `qubox/backends/qm/lowering.py` — imports from circuit_ir
- `qubox/backends/qm/runtime.py` — uses CircuitCompiler; version from __version__; _qubox_version() helper
- `qubox/calibration/models.py` — CalibrationSnapshot: mixer_calibration_path field, to_dict(), from_session with mixer path detection
- `qubox/calibration/mixer_calibration.py` — _sanitize_db_numbers delegates to core.persistence.sanitize_nonfinite
- `qubox/core/persistence.py` — added sanitize_nonfinite() utility
- `qubox/data/models.py` — RunManifest.to_dict() includes mixer_calibration_path
- `qubox/hardware/controller.py` — _sanitize_calibration_db_file uses sanitize_nonfinite
- `qubox/session/session.py` — added SessionFactory dataclass; added readout_handle() delegation
- `qubox/session/__init__.py` — exports SessionFactory
- `qubox/__init__.py` — exports SessionFactory

**Validation:**

- All 55 passing tests remain passing (pre-existing failures unchanged)
- No syntax errors in any modified file
- No runtime imports of qubox_v2_legacy or qubox.legacy remain

---

### 2026-04-02 — Architecture Extension: CircuitCompiler Rename + Registry-Based Dispatch

**Classification: Major**

**Summary:**

Three-phase architecture extension to improve extensibility and naming clarity:

**Phase 1 — Rename V2-suffixed symbols:**
- `CircuitRunnerV2` → `CircuitCompiler` (class name now reflects its compiler role)
- `compile_v2()` → `compile_program()` (canonical method name)
- Backward-compatible aliases retained: `CircuitRunnerV2 = CircuitCompiler` in
  `circuit_compiler.py`, `compile_v2()` emits `DeprecationWarning` and delegates
  to `compile_program()`
- All call sites, tests, and golden files updated

**Phase 2 — Gate Lowerer Registry (Strategy pattern):**
- New `qubox/programs/gate_lowerers/` package with `protocol.py` and `builtins.py`
- `GateLowerer` Protocol: `__call__(ctx, gate, *, gate_index, targets, measurements, resolved_params)`
- `CompilationContext` Protocol: typed interface for lowerer ↔ compiler interaction
- 7 built-in lowerer classes: `MeasurementLowerer`, `IdleLowerer`, `FrameUpdateLowerer`,
  `PlayPulseLowerer`, `QubitRotationLowerer`, `DisplacementLowerer`, `SQRLowerer`
- `build_default_registry()` creates 13-entry mapping (gate types + aliases)
- `CircuitCompiler._lower_gate()` dispatch replaced: if/elif chain → registry lookup
- `CircuitCompiler.register_lowerer(gate_type, lowerer)` — public extension point

**Phase 3 — Sweep Strategy Registry:**
- New `qubox/programs/sweep_strategies.py` module
- `SweepStrategy` Protocol: `qua_type`, `apply(ctx, qua_var, target, parameter)`
- 4 built-in strategies: `FrequencySweepStrategy`, `AmplitudeSweepStrategy`,
  `WaitSweepStrategy`, `PhaseSweepStrategy`
- `classify_sweep_parameter()` — alias-based parameter name → strategy key mapping
- `build_default_sweep_registry()` returns 4-entry strategy map
- `CircuitCompiler._emit_sweep_body()` and `_classify_sweep_parameter()` now delegate
  to strategies instead of hardcoded conditionals
- `CircuitCompiler.register_sweep_strategy(name, strategy)` — public extension point
- QUA variable type declaration now reads `strategy.qua_type` instead of hardcoded check

**Test conftest modernization:**
- `tests/gate_architecture/conftest.py` migrated from `qubox_v2_legacy.*` → `qubox.*`
- SDK stubs and `qubox_tools` stubs preserved for test isolation
- Minimal `qubox` package pre-registration to bypass heavy `__init__.py` imports

**Files affected:**
- `qubox/programs/circuit_compiler.py` — renamed class, registry-based dispatch
- `qubox/programs/circuit_runner.py` — `compile_program()` canonical, `compile_v2()` deprecated
- `qubox/programs/circuit_execution.py` — updated call site
- `qubox/programs/circuit_protocols.py` — updated warning string
- `qubox/backends/qm/runtime.py` — updated call site
- `qubox/programs/gate_lowerers/__init__.py` — new package
- `qubox/programs/gate_lowerers/protocol.py` — GateLowerer + CompilationContext protocols
- `qubox/programs/gate_lowerers/builtins.py` — 7 built-in lowerers + default registry
- `qubox/programs/sweep_strategies.py` — SweepStrategy protocol + 4 built-in strategies
- `tests/gate_architecture/conftest.py` — migrated from qubox_v2_legacy to qubox
- `tests/gate_architecture/test_gate_architecture.py` — CircuitCompiler refs + import fix
- `tests/gate_architecture/golden/active_reset_analysis_snapshot.txt` — golden file update
- `docs/CHANGELOG.md`

---

### 2026-04-01 — P0/P1/P2 Architecture Patches: Custom Sweeps, Adapter Coverage, @experiment Decorator

**Classification: Major**

**Summary:**

Three architectural improvement patches addressing the 6.4/10 velocity assessment:

**P0 — Custom Sweep Loop Generation (CircuitRunnerV2):**
- `CircuitRunnerV2.compile()` now detects `sweep_axes` from circuit metadata and
  emits nested QUA `for_()` loops via `from_array()` from `qualang_tools.loops`
- Added `_SweepAxisRuntime` dataclass for sweep state during program generation
- Added helper methods: `_parse_sweep_axes()`, `_emit_sweep_body()`,
  `_classify_sweep_parameter()`, `_infer_sweep_target()`
- `_lower_idle_gate()` is sweep-aware: uses QUA variable when gate has no concrete
  duration and a wait sweep is active
- `_lower_play_pulse()` is sweep-aware: uses `amp(sweep_var)` when no concrete
  amplitude and an amplitude sweep is active
- Stream processing auto-chains `.buffer(sweep_len).average()` for sweep dimensions
- `lower_to_legacy_circuit()` now passes `SweepAxis.metadata` through to circuit metadata

**P1 — Template Adapter Coverage (20 → 31 registered):**
- 11 new `LegacyExperimentAdapter` entries: `qubit.spectroscopy_ef`,
  `resonator.spectroscopy_x180`, `qubit.sequential_rotations`, `qubit.ramsey_chevron`,
  `readout.ge_raw_trace`, `reset.passive_benchmark`, `readout.leakage_benchmark`,
  `storage.ramsey`, `storage.fock_spectroscopy`, `storage.fock_ramsey`,
  `storage.fock_power_rabi`
- 11 new arg builder functions for translating `ExecutionRequest` params to experiment args
- 11 new library methods on `QubitExperimentLibrary`, `ResonatorExperimentLibrary`,
  `ReadoutExperimentLibrary`, `ResetExperimentLibrary`, `StorageExperimentLibrary`
- Coverage: 31/51 classes (61%) registered; remaining 10 can't be single-program adapted,
  10 have complex state dependencies

**P2 — @experiment Decorator:**
- New `qubox/experiments/decorator.py` with `@experiment()` decorator for named
  experiment registration
- Registry-based pattern: `experiment(name, n_avg, category)` → `ExperimentDefinition`
- Exported from `qubox.experiments`: `experiment`, `get_registered_experiments`,
  `lookup_experiment`

**Files affected:**
- `qubox/programs/circuit_compiler.py` — sweep loop generation + helper methods
- `qubox/backends/qm/lowering.py` — metadata passthrough
- `qubox/backends/qm/runtime.py` — 11 new adapters + arg builders
- `qubox/experiments/templates/library.py` — 11 new library methods
- `qubox/experiments/decorator.py` — new file
- `qubox/experiments/__init__.py` — re-export decorator
- `docs/CHANGELOG.md`

---

### 2026-04-01 — measureMacro Phase 6: Dead Code & Deprecation Cleanup

**Classification: Moderate**

**Summary:**

Final cleanup pass on `measureMacro`. Removes 237 lines of dead code (1605 → 1368 lines):

- **Removed 4 dead analysis wrappers** that had zero external callers (pure functions
  remain in `readout_analysis.py`):
  `compute_Pe_from_S()`, `compute_posterior_weights()`,
  `compute_posterior_state_weight()`, `check_iq_blob_rotation_consistency_2d()`
- **Removed `set_save_raw_data()`** method and `_save_raw_data` class variable (no callers)
- **Removed `measure_with_binding()`** standalone function — superseded by
  `emit_measurement()`, was never called from any production code
- **Stripped all 5 `DeprecationWarning` calls** from `active_element()`, `set_pulse_op()`,
  `_update_readout_discrimination()`, `_update_readout_quality()`, and `measure()` —
  these methods are still actively used across 12+ production files with no complete
  migration path, so the warnings were premature
- **Removed unused `import warnings`** from module top-level

**Validation:** 23 PASS, 1 SKIP, 0 FAIL (unchanged baseline).

**Files affected:**
- `qubox/programs/macros/measure.py`
- `docs/CHANGELOG.md`

---

### 2026-04-01 — measureMacro Phase 4+5: Extract Analysis Utilities & Dead Code Removal

**Classification: Major**

**Summary:**

Phase 4 extracts four analysis methods from `measureMacro` into pure functions in
`qubox_tools/algorithms/readout_analysis.py`. Phase 5 removes 18 dead methods from
`measureMacro` (572 lines removed) and adds deprecation warnings to the three
remaining legacy API methods. Also fixes `emit_measurement()` to accept `with_state`,
`axis`, `x90`, `yn90`, `qb_el` parameters and restores the internally-required
`use_weight_set()` method that was incorrectly marked as dead.

**New module:**

- `qubox_tools/algorithms/readout_analysis.py` — 4 pure analysis functions:
  - `compute_Pe_from_S(S, rot_mu_g, rot_mu_e)` — P(e) from projected IQ signal
  - `compute_posterior_weights(S, disc_params, *, model_type, pi_e, require_finite)` — Bayesian posterior weights
  - `compute_posterior_state_weight(S, disc_params, *, target_state, model_type, pi_e, require_finite)` — single-state convenience wrapper
  - `check_iq_blob_rotation_consistency_2d(S_g, S_e, disc_params, ...)` — 2D IQ blob rotation consistency check

**measureMacro thin wrappers now delegate to the new module:**

- `measureMacro.compute_Pe_from_S()` → `readout_analysis.compute_Pe_from_S()`
- `measureMacro.compute_posterior_weights()` → `readout_analysis.compute_posterior_weights()`
- `measureMacro.compute_posterior_state_weight()` → `readout_analysis.compute_posterior_state_weight()`
- `measureMacro.check_iq_blob_rotation_consistency_2d()` → `readout_analysis.check_iq_blob_rotation_consistency_2d()`

**Deprecation warnings added to:**

- `measureMacro.active_element()` — use `ReadoutHandle.element`
- `measureMacro.set_pulse_op()` — use `ReadoutHandle` / `emit_measurement()`
- `measureMacro.measure()` — use `emit_measurement()`

**emit_measurement() signature expanded:**

- Added `with_state`, `axis`, `x90`, `yn90`, `qb_el` parameters for basis rotation
  and state discrimination parity with `measureMacro.measure()`

**Dead methods removed from measureMacro (~18):**

- `set_active_op`, `show_settings`, `get_gain`, `default`, `get_IQ_mod`,
  `use_dual_demod`, `get_demod_weight_len`, `report_thresholding`,
  `compute_Pe_from_IQ`, `compute_posterior_model`, `compute_posterior_confusion`,
  `calibrate_readout_qua`, `export_readout_calibration`, and others

**Import path fixes:**

- `qubox.analysis.analysis_tools` → `qubox_tools.algorithms.transforms`
- `qubox.analysis.post_selection` → `qubox_tools.algorithms.post_selection`

**Validation:**

- 23 PASS, 1 SKIP, 0 FAIL on `tools/test_all_simulations.py` (matches baseline)
- All 4 analysis wrapper functions tested with synthetic data
- Dead method absence verified, live method presence verified

**Files modified:**

- `qubox/programs/macros/measure.py` — thin wrappers, dead code removal, import fixes, deprecation warnings, `use_weight_set` restored, `emit_measurement()` expanded
- `qubox_tools/algorithms/readout_analysis.py` — new module (4 pure analysis functions)
- `qubox_tools/algorithms/__init__.py` — added `readout_analysis` to exports

---

### 2026-03-31 — Legacy Elimination: Remove backward-compat code, resolve all deprecation warnings

**Classification: Major**

**Summary:**

Comprehensive legacy elimination pass.  All backward-compatibility shims,
deprecated module proxies, and `DeprecationWarning` code paths have been removed.
The `simulation_mode` default has been changed from `False` to `True` everywhere
so sessions open safely by default.

**Breaking changes:**

1. **`Session.__getattr__` forwarding removed** — accessing undefined attributes
   on `Session` now raises `AttributeError` instead of silently delegating to
   `SessionManager` with a deprecation warning.  Use `session.hardware`,
   `session.calibration`, `session.pulse_mgr`, etc. (new direct properties).
2. **`SessionManager` compat aliases removed** — `hw`, `pulseOpMngr`, `mgr`,
   `quaProgMngr` properties deleted.  Use `hardware`, `pulse_mgr` directly.
3. **`simulation_mode` default → `True`** — `Session.open()`,
   `SessionManager.__init__()`, `open_shared_session()`,
   `require_shared_session()`, `open_notebook_stage()` all default to
   simulation mode.  Pass `simulation_mode=False` for real hardware execution.
4. **`QuaProgramManager` removed** — the backward-compat facade combining the
   four split hardware classes has been deleted.  Use `HardwareController`,
   `ConfigEngine`, `ProgramRunner`, `QueueManager` directly.
5. **`qubox.analysis` shim removed** — import from `qubox_tools` directly.
6. **`qubox.optimization` shim removed** — import from
   `qubox_tools.optimization` directly.
7. **Bare calibration keys rejected** — `T1`, `T2_star`, `T2_echo` (without
   unit suffix) are no longer auto-converted.  Provide `T1_s` / `T1_ns`,
   `T2_star_s` / `T2_star_ns`, `T2_echo_s` / `T2_echo_ns`.
8. **`MeasurementConfig.apply_to_measure_macro()` removed** — pass
   `MeasurementConfig` to experiment builders directly.
9. **`ReadoutConfig` legacy value names rejected** —
   `legacy_ge_diff_norm` and `legacy_discriminator` no longer auto-convert.
   Use `ge_diff_norm` and `optimal_discriminator`.
10. **Waveform `delta` parameter removed** — use `anharmonicity`.

**Files modified:**

- `qubox/session/session.py` — complete rewrite: remove `__getattr__`, add 8
  direct `@property` accessors, change `simulation_mode` default to `True`
- `qubox/experiments/session.py` — remove `hw`, `pulseOpMngr`, `mgr`,
  `quaProgMngr` compat aliases; change `simulation_mode` default to `True`
- `qubox/experiments/experiment_base.py` — `hw`/`pulse_mgr` properties now
  look up `hardware`/`pulse_mgr` first (not `quaProgMngr`/`pulseOpMngr`);
  remove displacement-reference `DeprecationWarning`
- `qubox/notebook/runtime.py` — all `simulation_mode` defaults → `True`;
  `session.hw` → `session.hardware` in `resolve_active_mixer_targets()`
- `qubox/notebook/workflow.py` — `simulation_mode` default → `True`
- `qubox/backends/qm/runtime.py` — `.hw` → `.hardware`
- `qubox/hardware/__init__.py` — remove `QuaProgramManager` export
- `qubox/calibration/patch_rules.py` — remove bare T1/T2_star/T2_echo fallbacks
- `qubox/programs/macros/measure.py` — remove `DeprecationWarning` from
  `_update_readout_discrimination()` and `_update_readout_quality()`
- `qubox/experiments/calibration/readout_config.py` — remove legacy value
  auto-conversion
- `qubox/core/measurement_config.py` — remove `apply_to_measure_macro()`
- `qubox/tools/waveforms.py` — remove `delta` parameter path from all 4
  waveform functions
- `qubox/analysis/__init__.py` — gut shim contents (tombstone docstring only)
- `qubox/optimization/__init__.py` — gut shim contents (tombstone docstring only)

**Files deleted:**

- `qubox/analysis/cQED_attributes.py`
- `qubox/analysis/pipelines.py`
- `qubox/analysis/pulseOp.py`
- `qubox/optimization/optimization.py`
- `qubox/optimization/smooth_opt.py`
- `qubox/optimization/stochastic_opt.py`
- `qubox/hardware/qua_program_manager.py`

**Tests updated:**

- `qubox/tests/test_parameter_resolution_policy.py` — rename mock attrs
  `hw` → `hardware`, `pulseOpMngr` → `pulse_mgr`
- `qubox/tests/test_workflow_safety_refactor.py` — update T1/T2 bare-key tests
  from `pytest.warns(DeprecationWarning)` to `assert patch is None`

---

### 2026-03-31 — Add simulation_mode to Session Launch

**Classification: Moderate**

**Summary:**

Added a `simulation_mode: bool = False` parameter to the session-opening stack
so experiments can be compiled and simulated via QM's simulator without
activating any hardware outputs.  When `simulation_mode=True`:

- `SessionManager.open()` skips `hardware.open_qm()` — no `QuantumMachine`
  instance is created and RF outputs are never enabled.
- `ProgramRunner.exec_mode` is locked to `ExecMode.SIMULATE` at construction,
  so `run_program()` raises `JobError` on any hardware-execution attempt.
- `qmm.simulate()` (and therefore all `experiment.simulate()` calls) continues
  to work because `ProgramRunner.simulate()` only requires the
  `QuantumMachinesManager`, not an open `QuantumMachine`.
- `session.simulation_mode` property returns `True` for introspection.
- `NotebookSessionBootstrap` stores the flag so `restore_shared_session()`
  reopens in the same mode automatically.

**Files affected:**

- `qubox/experiments/session.py` — `SessionManager.__init__()`, `open()`, new `simulation_mode` property
- `qubox/session/session.py` — `Session.open()` explicit parameter + docstring
- `qubox/notebook/runtime.py` — `NotebookSessionBootstrap`, `open_shared_session()`, `require_shared_session()`
- `API_REFERENCE.md` — new §17.4 Simulation Mode
- `docs/CHANGELOG.md`

### 2026-03-31 — Architecture Refactor Phase 2: Analysis Merge, Workflow Extraction, Notebook Surface Slimming

**Classification: Major**

**Summary:**

Continued the multi-session architecture refactor from the audit plan. This session completed three major items:

1. **Analysis → qubox_tools merge (Item 6):** Eliminated all 50+ `from qubox.analysis.*` import references across the codebase, redirecting them to their canonical `qubox_tools` locations (`qubox_tools.algorithms`, `qubox_tools.fitting`, `qubox_tools.data`, `qubox_tools.plotting`). The `qubox/analysis/` package now contains only backward-compatible shims with deprecation notices. 13 pure-wrapper files were deleted in the prior session; this session fixed all remaining broken import chains.

2. **Workflow generalization (Item 8):** Created `qubox.workflow` package with four modules (`stages`, `calibration_helpers`, `fit_gates`, `pulse_seeding`). Core workflow primitives (stage checkpoints, fit quality gates, patch preview/apply, DRAG pulse seeding) are now importable from `qubox.workflow` without a notebook kernel. `qubox.notebook.workflow` is now a thin wrapper that adds shared-session management on top.

3. **Notebook surface slimming (Item 7):** Split `qubox.notebook` exports into two tiers:
   - `qubox.notebook` (essentials): experiments, session management, workflow, waveform generators, basic calibration tools (~65 symbols)
   - `qubox.notebook.advanced` (infrastructure): CalibrationStore, data models, artifact management, schemas, verification, device registry (~45 symbols)

**Import mapping (deleted wrappers → canonical locations):**
- `qubox.analysis.analysis_tools` → `qubox_tools.algorithms.transforms`
- `qubox.analysis.algorithms` → `qubox_tools.algorithms.core`
- `qubox.analysis.cQED_models` → `qubox_tools.fitting.cqed`
- `qubox.analysis.cQED_plottings` → `qubox_tools.plotting.cqed`
- `qubox.analysis.output` → `qubox_tools.data.containers`
- `qubox.analysis.metrics` → `qubox_tools.algorithms.metrics`
- `qubox.analysis.post_selection` → `qubox_tools.algorithms.post_selection`
- `qubox.analysis.post_process` → `qubox_tools.algorithms.post_process`
- `qubox.analysis.pulseOp` → `qubox.core.pulse_op`
- `qubox.analysis.pipelines` → `qubox_tools.algorithms.pipelines`

**Files created:**
- `qubox/workflow/__init__.py`
- `qubox/workflow/stages.py`
- `qubox/workflow/calibration_helpers.py`
- `qubox/workflow/fit_gates.py`
- `qubox/workflow/pulse_seeding.py`
- `qubox/notebook/advanced.py`

**Files modified (import updates — 30+ files):**
- `qubox/experiments/base.py`, `experiment_base.py`, `session.py`
- `qubox/experiments/calibration/gates.py`, `readout.py`, `reset.py`
- `qubox/experiments/spectroscopy/resonator.py`, `qubit.py`
- `qubox/experiments/time_domain/rabi.py`, `relaxation.py`, `coherence.py`, `chevron.py`
- `qubox/experiments/cavity/storage.py`, `fock.py`
- `qubox/experiments/tomography/wigner_tomo.py`, `qubit_tomo.py`, `fock_tomo.py`
- `qubox/experiments/spa/flux_optimization.py`
- `qubox/programs/macros/measure.py`
- `qubox/backends/qm/runtime.py`
- `qubox/hardware/program_runner.py`
- `qubox/pulses/manager.py`, `pulse_registry.py`
- `qubox/calibration/algorithms.py`, `pulse_train_tomo.py`
- `qubox/notebook/__init__.py`, `workflow.py`

### 2026-03-23 — Retune Mixer Validation Power Targets for Notebook 01

**Classification: Moderate**

**Summary:**

Aligned the notebook 00 hardware-definition defaults, notebook 01 auto-calibration gain overrides, and the persisted sample `hardware.json` gains so the notebook 01 CW post-check now targets about `-30 dBm` on `transmon`, `storage`, `storage_gf`, and `resonator_gf`, while intentionally keeping `resonator` near `-40 dBm` to protect the readout path. This keeps the intended power plan explicit in both the notebook authoring flow and the runtime config that session bootstrap actually reads.

**Files affected:**

- `notebooks/00_hardware_defintion.ipynb`
- `notebooks/01_mixer_calibrations.ipynb`
- `samples/post_cavity_sample_A/config/hardware.json`
- `docs/CHANGELOG.md`

### 2026-03-24 — Validate and Fine-Tune Notebook 01 CW Calibration Power Targets

**Classification: Moderate**

**Summary:**

Executed the notebook 00 to notebook 01 mixer-calibration flow live against the current hardware and spectrum-analyzer post-check. The first run showed `storage_gf` and `resonator_gf` overshooting the intended CW target power, so their default gains were reduced and the full auto-calibration path was rerun. The verified power plan is now approximately `-30 dBm` for `resonator_gf`, `storage`, `storage_gf`, and `transmon`, while `resonator` remains intentionally near `-40 dBm`.

**Files affected:**

- `notebooks/00_hardware_defintion.ipynb`
- `notebooks/01_mixer_calibrations.ipynb`
- `samples/post_cavity_sample_A/config/hardware.json`
- `docs/CHANGELOG.md`

### 2026-03-23 — Emit Default Element Ops in HardwareDefinition

**Classification: Moderate**

**Summary:**

Fixed the notebook-facing `HardwareDefinition` generator so sample-level `hardware.json` now includes the default `const` and `zero` operations for every element, and both generated config files now include their schema/version fields. This removes misleading schema warnings during notebook 00 preflight and aligns the hardware-definition output with the rest of the pulse infrastructure.

**Files affected:**

- `qubox/core/hardware_definition.py`
- `tests/test_schemas.py`
- `API_REFERENCE.md`
- `docs/CHANGELOG.md`
- `samples/post_cavity_sample_A/config/hardware.json`
- `samples/post_cavity_sample_A/config/devices.json`

### 2026-03-23 — Remove All Backward-Compatibility Shims

**Classification: Major**

**Summary:**

Removed the `qubox/compat/` and `qubox_tools/compat/` directories entirely.
All backward-compatibility shims that redirected imports to `qubox.notebook`
have been deleted. `qubox.notebook` is now the sole notebook import surface
with no legacy indirection layer.

**Changes:**
- **Deleted:** `qubox/compat/__init__.py`, `qubox/compat/notebook.py`, `qubox/compat/notebook_runtime.py`, `qubox/compat/notebook_workflow.py`
- **Deleted:** `qubox_tools/compat/__init__.py`, `qubox_tools/compat/legacy_analysis.py`
- **Updated:** `qubox/__init__.py` — removed `qubox.compat` from subpackage docstring
- **Updated:** `qubox_tools/__init__.py` — removed `compat` from `_SUBMODULES` and `__all__`
- **Updated:** `qubox/notebook/__init__.py`, `qubox/notebook/runtime.py`, `qubox/notebook/workflow.py` — removed historical migration references from docstrings
- **Updated:** `tests/test_qubox_public_api.py` — renamed compat test to `test_notebook_surface_is_lazy`, imports `qubox.notebook` directly
- **Updated:** `test_migration.py` — renamed compat check label
- **Updated:** `notebooks/verify_compilation.py`, `notebooks/COMPILATION_VERIFICATION_REPORT.md`, `notebooks/migration_plan.md`, `notebooks/post_cavity_experiment_context.ipynb`
- **Updated:** `API_REFERENCE.md` — removed `qubox.compat` and `qubox_tools.compat` rows
- **Updated:** `.clinerules`, `.cursorrules`, `.windsurfrules`, `CLAUDE.md`, `.github/copilot-instructions.md`, `.skills/repo-onboarding/SKILL.md`

---

### 2026-03-23 — Promote qubox.notebook as First-Class Import Surface

**Classification: Major**

**Summary:**

Moved the notebook import surface from `qubox.compat.notebook` to `qubox.notebook`.
Created a new `qubox/notebook/` subpackage containing:
- `__init__.py` — primary import surface (200+ re-exported symbols)
- `runtime.py` — shared session bootstrap, lifecycle management
- `workflow.py` — stage context, checkpoints, fit helpers, primitive rotations

The former `qubox/compat/` modules (`notebook.py`, `notebook_runtime.py`,
`notebook_workflow.py`) are now thin backward-compatibility shims that redirect
to `qubox.notebook.*`. All 30 experiment notebooks, tests, tutorials, and
documentation have been updated to import from `qubox.notebook`.

**Files affected:**

- **Created:** `qubox/notebook/__init__.py`, `qubox/notebook/runtime.py`, `qubox/notebook/workflow.py`
- **Modified (shims):** `qubox/compat/__init__.py`, `qubox/compat/notebook.py`, `qubox/compat/notebook_runtime.py`, `qubox/compat/notebook_workflow.py`
- **Modified (imports):** `qubox/__init__.py`, all 30 notebooks in `notebooks/`, `test_migration.py`, `tests/test_notebook_runtime.py`, `tests/test_notebook_workflow.py`, `tests/test_qubox_public_api.py`, `tutorials/01_getting_started_basic_experiments.ipynb`
- **Modified (docs):** `API_REFERENCE.md`, `README.md`, `CLAUDE.md`, `.clinerules`, `.cursorrules`, `.windsurfrules`, `.skills/repo-onboarding/SKILL.md`

---

### 2026-03-22 — Remove Legacy cqed_params Comparisons from Numbered Notebooks

**Classification: Moderate**

**Summary:**

Removed legacy `cqed_params.json` loading and comparison logic from the numbered bring-up notebooks. Notebook 00 now shows runtime-only sanity plots, notebooks 02 through 04 use runtime-only diagnostics for readout and resonator workflows, and notebooks 05 and 06 no longer seed defaults or report deltas from legacy `cqed_params` values.

**Files affected:**

- `docs/CHANGELOG.md`
- `notebooks/00_hardware_defintion.ipynb`
- `notebooks/02_time_of_flight.ipynb`
- `notebooks/03_resonator_spectroscopy.ipynb`
- `notebooks/04_resonator_power_chevron.ipynb`
- `notebooks/05_qubit_spectroscopy_pulse_calibration.ipynb`
- `notebooks/06_coherence_experiments.ipynb`

### 2026-03-22 — Operator Workflow Refactor for Numbered Notebooks

**Classification: Major**

**Summary:**

Redesigned the numbered post-cavity bring-up notebooks around explicit operator-stage contracts instead of notebook-local workflow policy. Added a shared compat helper layer for stage bootstrap, stage checkpoint persistence, calibration patch preview and apply, fit gates, and primitive pulse seeding, then rewired notebooks 03 through 06 to consume that layer. The resonator spectroscopy notebook now records whether its readout-frequency patch was actually applied, the power chevron notebook is explicitly characterization-only with advisory outputs, and the qubit and coherence notebooks now persist stage checkpoints that separate measured results from committed calibration updates.

**Files affected:**

- `docs/CHANGELOG.md`
- `API_REFERENCE.md`
- `notebooks/03_resonator_spectroscopy.ipynb`
- `notebooks/04_resonator_power_chevron.ipynb`
- `notebooks/05_qubit_spectroscopy_pulse_calibration.ipynb`
- `notebooks/06_coherence_experiments.ipynb`
- `notebooks/WORKFLOW_REDESIGN.md`
- `qubox/compat/notebook.py`
- `qubox/compat/notebook_workflow.py`
- `tests/test_notebook_workflow.py`
- `tests/test_qubox_public_api.py`

### 2026-03-22 — Python 3.12.10 Repository Standardization

**Classification: Minor**

**Summary:**

Updated the repository policy and documentation to make Python 3.12.10 the required interpreter target, explicitly allowing either the workspace `.venv` or a global Python 3.12.10 interpreter. This replaces the previous 3.12.13 guidance while preserving Python 3.11.8 as the machine-specific fallback on ECE-SHANKAR-07.

**Files affected:**

- `AGENTS.md`
- `CLAUDE.md`
- `.github/copilot-instructions.md`
- `README.md`
- `API_REFERENCE.md`
- `.skills/repo-onboarding/SKILL.md`
- `docs/CHANGELOG.md`

### 2026-03-22 — Projected-Signal Audit for Rabi and Coherence Analysis

**Classification: Moderate**

**Summary:**

Audited the time-domain Rabi and coherence analysis paths to verify that fitted quantities are derived from the projected complex readout signal rather than raw IQ or magnitude data. Tightened `PowerRabi.analyze()` so it fits the direct projected `S_I` trace instead of an offset-restored variant, updated `T1Relaxation`, `T2Ramsey`, `T2Echo`, and `ResidualPhotonRamsey` to persist the exact projected signal used for fitting into `analysis.data["projected_S"]`, and adjusted the matching plot paths to consume that stored projected trace. Added regression tests that monkeypatch the projection and fitting steps to verify the fit input is the projected I-quadrature signal for the Rabi and coherence workflows.

**Files affected:**

- `docs/CHANGELOG.md`
- `qubox/legacy/experiments/time_domain/rabi.py`
- `qubox/legacy/experiments/time_domain/relaxation.py`
- `qubox/legacy/experiments/time_domain/coherence.py`
- `qubox/legacy/tests/test_projected_signal_analysis.py`

### 2026-03-22 — End-to-End Bring-Up Notebook Verification Pass

**Classification: Moderate**

**Summary:**

Validated the numbered bring-up workflow against the live post-cavity device chain from notebook 00 through notebook 06 using reduced-cost settings and repaired the runtime issues uncovered in the process. Simplified notebook 01 to a single mixer-calibration mode selector and fixed its active-target plotting bug, hardened notebooks 02 through 05 to reopen a fresh shared session after QM restarts, shortened notebook 02 and added an automatic one-time reconnect for dropped QM handles, widened notebook 04's default chevron window and fixed its missing `ro_therm_clks` override, and tightened notebook 06 so non-physical coherence fits such as negative Ramsey `T2*` values no longer apply calibration patches. Re-ran the full sequence live, including mixer calibration, time-of-flight, resonator spectroscopy, resonator power chevron, qubit spectroscopy, Power Rabi, Temporal Rabi, and coherence experiments, and restored the qubit-frequency calibration after the earlier Ramsey gate allowed a bad fit through during validation.

**Files affected:**

- `docs/CHANGELOG.md`
- `notebooks/01_mixer_calibrations.ipynb`
- `notebooks/02_time_of_flight.ipynb`
- `notebooks/03_resonator_spectroscopy.ipynb`
- `notebooks/04_resonator_power_chevron.ipynb`
- `notebooks/05_qubit_spectroscopy_pulse_calibration.ipynb`
- `notebooks/06_coherence_experiments.ipynb`

### 2026-03-21 — Legacy-Style Analysis Pass for Numbered Experiment Notebooks

**Classification: Moderate**

**Summary:**

Finished the numbered post-cavity notebook sequence by aligning the analysis cells with the legacy workflow instead of relying on generic comparison bars. Added an explicit 00→06 sequence map in `notebooks/00_hardware_defintion.ipynb`, replaced notebook 00's startup summary with runtime-versus-legacy delta views, updated notebook 02 to show the legacy-style raw ADC overlay and arrival-envelope analysis, replaced notebook 03 with explicit resonator magnitude and phase traces, replaced notebook 04 with legacy-style chevron `pcolormesh` maps for magnitude and phase, and upgraded notebooks 05 and 06 to show experiment-specific diagnostic plots built from the real spectroscopy, Rabi, and coherence fit outputs. Validated the revised cells in preview mode and executed the updated notebook 00 startup path against a live session state.

**Files affected:**

- `docs/CHANGELOG.md`
- `notebooks/00_hardware_defintion.ipynb`
- `notebooks/02_time_of_flight.ipynb`
- `notebooks/03_resonator_spectroscopy.ipynb`
- `notebooks/04_resonator_power_chevron.ipynb`
- `notebooks/05_qubit_spectroscopy_pulse_calibration.ipynb`
- `notebooks/06_coherence_experiments.ipynb`

### 2026-03-21 — Notebook Preview Validation and Kernel Bootstrap Hardening

**Classification: Moderate**

**Summary:**

Hardened the downstream numbered experiment notebooks so they can bootstrap cleanly in both the workspace virtual environment and the global Python 3.12.10 kernel. Added an explicit repository-root import shim to notebooks 02 through 06, then smoke-tested their non-destructive bootstrap and preview cells with hardware execution flags disabled. Tightened notebook 05's reference-pulse preview plot to avoid complex-value plotting warnings, and updated notebook 06 to surface a resolved `qb_therm_clks` fallback from legacy calibration data while guarding T1 and T2 Echo execution when the runtime session does not expose that calibration yet.

**Files affected:**

- `docs/CHANGELOG.md`
- `notebooks/02_time_of_flight.ipynb`
- `notebooks/03_resonator_spectroscopy.ipynb`
- `notebooks/04_resonator_power_chevron.ipynb`
- `notebooks/05_qubit_spectroscopy_pulse_calibration.ipynb`
- `notebooks/06_coherence_experiments.ipynb`

### 2026-03-22 — Numbered Spectroscopy and Rabi Notebook Expansion

**Classification: Moderate**

**Summary:**

Updated `notebooks/01_mixer_calibrations.ipynb` so both the Octave auto-calibration path and the SA-driven manual calibration path operate as single run cells over the full active mixer target set, while keeping both paths preview-first by default. Added `notebooks/02_resonator_spectroscopy.ipynb` for the broad resonator spectroscopy and resonator power chevron workflow, and added `notebooks/03_power_rabi_temporal_rabi.ipynb` for the power Rabi and temporal Rabi workflow using legacy-derived sweep defaults.

**Files affected:**

- `docs/CHANGELOG.md`
- `notebooks/01_mixer_calibrations.ipynb`
- `notebooks/02_resonator_spectroscopy.ipynb`
- `notebooks/03_power_rabi_temporal_rabi.ipynb`

### 2026-03-21 — Shared Notebook Session Reuse and Full Mixer Target Discovery

**Classification: Moderate**

**Summary:**

Added a notebook runtime helper layer so numbered experiment notebooks can reuse
the live session opened in `00_hardware_defintion.ipynb` when they share a kernel,
and can reopen the same sample or cooldown session from a persisted bootstrap file
when started in a fresh kernel. Extended the mixer-calibration flow to derive manual
calibration targets from the live hardware state instead of hard-coding only the
readout, qubit, and storage aliases, which allows the notebook workflow to see all
five active Octave outputs.

**Files affected:**

- `qubox/compat/notebook_runtime.py`
- `qubox/compat/notebook.py`
- `tests/test_notebook_runtime.py`
- `tests/test_qubox_public_api.py`
- `API_REFERENCE.md`
- `docs/CHANGELOG.md`
- `notebooks/00_hardware_defintion.ipynb`
- `notebooks/01_mixer_calibrations.ipynb`

### 2026-03-21 — Explicit Notebook Hardware Definition Controls

**Classification: Moderate**

**Summary:**

Extended the notebook-facing compat surface with `HardwareDefinition` and updated
`notebooks/00_hardware_defintion.ipynb` so users can explicitly define sample-level
hardware bindings, LO and IF settings, aliases, and external device definitions
before opening a session. This removes the need to rely on opaque copied defaults
when starting a new hardware campaign.

**Files affected:**

- `qubox/compat/notebook.py`
- `tests/test_qubox_public_api.py`
- `API_REFERENCE.md`
- `docs/CHANGELOG.md`
- `notebooks/00_hardware_defintion.ipynb`

### 2026-03-21 — Devices Schema Validation Compatibility Fix

**Classification: Moderate**

**Summary:**

Updated schema validation so devices.json accepts the flat top-level device map
used by the runtime and by HardwareDefinition, while still accepting an optional
wrapped devices block. This removes the false validation failure reported by
notebooks/00_hardware_defintion.ipynb during sample-level schema checks.

**Files affected:**

- `qubox/schemas.py`
- `qubox/legacy/core/schemas.py`
- `tests/test_schemas.py`
- `docs/CHANGELOG.md`

### 2026-03-21 — Sequential Notebook Mixer Calibration Follow-On

**Classification: Moderate**

**Summary:**

Added `notebooks/01_mixer_calibrations.ipynb` as the next step in the numbered
experiment workflow. The notebook extracts the mixer-calibration stage from the
legacy post-cavity context notebook, reopens the session for the active sample and
cooldown, summarizes active mixer targets, and exposes both built-in Octave auto
calibration and SA-driven manual calibration through preview-first controls so the
notebook can execute safely before enabling live calibration.

**Files affected:**

- `docs/CHANGELOG.md`
- `notebooks/01_mixer_calibrations.ipynb`

### 2026-03-21 — Sequential Notebook Experiment Workflow Bootstrap

**Classification: Moderate**

**Summary:**

Defined a numbered notebook workflow for experiment execution so future agent-driven
calibration and experiment tasks create separate notebooks under `notebooks/` rather
than extending a single monolithic workflow notebook. Added the first required startup
notebook, `00_hardware_defintion.ipynb`, by extracting the shared hardware definition,
sample or cooldown bootstrap, session open, and preflight validation steps from the
existing post-cavity context notebook.

**Files affected:**

- `AGENTS.md`
- `docs/CHANGELOG.md`
- `notebooks/00_hardware_defintion.ipynb`

### 2026-03-14 — Standard Experiment Suite: 20 Canonical Experiments

**Classification: Major**

**Summary:**

Migrated 20 representative experiments from the legacy `cQED_programs.py` into the
new `qubox` API as the canonical standard experiment suite. This expands the
`ExperimentLibrary` from 5 template experiments to 21 (20 standard + 1 reset).

New experiment sub-libraries added to `session.exp`:
- `session.exp.readout` — ReadoutExperimentLibrary (trace, iq_blobs, butterfly)
- `session.exp.calibration` — CalibrationExperimentLibrary (all_xy, drag)
- `session.exp.storage` — StorageExperimentLibrary (spectroscopy, t1_decay, num_splitting)
- `session.exp.tomography` — TomographyExperimentLibrary (qubit_state, wigner)

Existing sub-libraries extended:
- `session.exp.qubit` — added temporal_rabi, time_rabi_chevron, power_rabi_chevron, t1, echo
- `session.exp.resonator` — added power_spectroscopy

Each experiment follows the established adapter pattern: user calls template method →
`ExecutionRequest` → `QMRuntime._run_template()` → `LegacyExperimentAdapter` →
legacy experiment class → QUA program → hardware execution → analysis.

16 new arg_builder functions translate high-level `ExecutionRequest` params to
legacy constructor arguments, preserving physics intent and sweep semantics.

**Files affected:**
- `qubox/experiments/templates/library.py` — 4 new sub-library classes, 16 new methods
- `qubox/experiments/templates/__init__.py` — updated exports
- `qubox/backends/qm/runtime.py` — 16 new arg_builder functions, 16 new adapter entries
- `API_REFERENCE.md` — Section 11 expanded with all 20 experiment signatures
- `standard_experiments.md` — updated with canonical 20-experiment list
- `tests/test_standard_experiments.py` — new test file (23 tests)
- `docs/CHANGELOG.md` — this entry

### 2026-03-14 — Complete Legacy qubox_v2 Reference Migration

**Classification: Major**

**Summary:**

Migrated all `qubox_v2` references across the entire codebase (~45 files,
~1700+ replacements) so that:
- `qubox` is the sole user-facing package name in docs, examples, and comments
- `qubox_v2_legacy` is used consistently for internal runtime import paths
- The compat layer (`qubox.compat.notebook`) correctly points to `qubox_v2_legacy`
- API_REFERENCE.md known gaps 21.1 and 21.3 resolved
- CHANGELOG.md title updated with historical note

Historical documents (CHANGELOG entries, claude_report.md, past_prompt/)
retain original `qubox_v2` mentions as historical records.

**Files affected:**

- `qubox/compat/notebook.py`, `qubox/compat/__init__.py`, `qubox/__init__.py`
- `qubox_tools/__init__.py`, `qubox_tools/compat/__init__.py`,
  `qubox_tools/compat/legacy_analysis.py`, `qubox_tools/fitting/calibration.py`,
  `qubox_tools/fitting/pulse_train.py`
- `qubox_v2_legacy/__init__.py`
- `tests/gate_architecture/conftest.py`
- `tools/analyze_imports.py`, `tools/build_context_notebook.py`,
  `tools/generate_codebase_graphs.py`, `tools/validate_notebooks.py`
- `README.md`, `API_REFERENCE.md`, `SURVEY.md`
- `.github/copilot-instructions.md`, `.github/instructions/*.md`,
  `.github/skills/**`, `.github/WORKFLOW_BLUEPRINT.md`
- `qubox_lab_mcp/README.md`, `qubox_lab_mcp/resources/repo_resources.py`
- `docs/architecture_review.md`, `docs/architecture/*.json`, `docs/architecture/*.svg`
- `docs/codebase_graph_survey.md`, `docs/gate_architecture_review.md`,
  `docs/qubox_architecture.md`, `docs/qubox_experiment_framework_refactor_proposal.md`,
  `docs/qubox_lab_mcp_design.md`, `docs/qubox_migration_guide.md`,
  `docs/qubox_refactor_verification.md`, `docs/qubox_tools_analysis_split.md`
- `docs/CHANGELOG.md`

### 2026-03-14 — Beginner Tutorial Notebook and Notebook Compat Additions

**Classification: Moderate**

**Summary:**

1. Added a new onboarding tutorial notebook under `tutorials/` that teaches
   the real current `qubox` workflow for session startup, artifact
   inspection, standard baseline experiments, and calibration patch review.
2. Extended `qubox.compat.notebook` with notebook-facing runtime result and
   artifact helpers so tutorials can stay under the `qubox` namespace while
   still using the existing execution stack.
3. Updated the public API reference to document the expanded
   `qubox.compat.notebook` tutorial-facing surface.

**Files affected:**

- `API_REFERENCE.md`
- `docs/CHANGELOG.md`
- `qubox/compat/notebook.py`
- `tests/test_qubox_public_api.py`
- `tutorials/01_getting_started_basic_experiments.ipynb`

### 2026-03-13 — Analysis API Extraction and Refactor Verification

**Classification: Major**

**Summary:**

1. Added `qubox_tools` as the canonical analysis package for fitting,
   plotting, post-processing, metrics, and optimization helpers.
2. Converted `qubox_v2.analysis.*` and `qubox_v2.optimization.*` into
   compatibility wrappers that point to the extracted analysis code.
3. Hardened optional dependency imports so missing `pandas`, `pycma`,
   `scikit-optimize`, `tqdm`, and `qm`-related notebook/runtime dependencies
   do not block analysis-only validation.
4. Added notebook-local `qubox_tools` sanity cells, explicit hardware
   boundaries, notebook validation tooling, and new tests for the extracted
   analysis surface.
5. Added an explicit verification document showing that the earlier `qubox`
   runtime migration was partial rather than complete.
6. Final validation for this task was re-run with
   `E:\Program Files\Python311\python.exe` (Python 3.11.8), including an
   existing `qubox_v2` workflow-safety compatibility suite and deeper notebook
   startup execution.
7. Migrated the repository notebooks off direct `qubox_v2` imports by adding
   the centralized `qubox.compat.notebook` shim and updating notebook sources
   to import only from `qubox`, `qubox.compat.notebook`, and `qubox_tools`.

**Files affected:**

- `README.md`
- `API_REFERENCE.md`
- `docs/CHANGELOG.md`
- `docs/qubox_refactor_verification.md`
- `docs/qubox_tools_analysis_split.md`
- `notebooks/post_cavity_experiment_context.ipynb`
- `notebooks/post_cavity_experiment_quantum_circuit.ipynb`
- `qubox_tools/**`
- `qubox/compat/**`
- `qubox_v2/__init__.py`
- `qubox_v2/analysis/**`
- `qubox_v2/calibration/__init__.py`
- `qubox_v2/optimization/**`
- `qubox_v2/pyproject.toml`
- `tests/qubox_tools/test_analysis_split.py`
- `tools/validate_notebooks.py`

### 2026-03-02 — Workflow Safety Refactoring (v2.1.0)

**Classification: Major**

Comprehensive safety refactoring of the experiment workflow based on
architecture review findings H1–H5.  Six coordinated changes across
calibration, analysis, experiment, and core layers.

**Summary:**

1. **P0.1 — FitResult.success contract** (`experiments/result.py`,
   `analysis/fitting.py`, `calibration/orchestrator.py`,
   `analysis/calibration_algorithms.py`)
   - `FitResult` gains `success: bool` and `reason: str | None` fields.
   - `fit_and_wrap()` failure paths set `success=False`.
   - `CalibrationOrchestrator.analyze()` short-circuits on `fit.success is False`.
   - `fit_number_splitting()` / `fit_chi_ramsey()` emit `RuntimeWarning` on
     fallback and flag `_fit_success` in return dicts.

2. **P0.2 — Transactional apply_patch** (`calibration/orchestrator.py`,
   `calibration/store.py`)
   - `apply_patch()` default changed from `dry_run=False` → `dry_run=True`.
   - Non-dry-run operations now take a CalibrationStore snapshot and roll back
     on exception; failure raises `RuntimeError(…rolled back…)`.
   - `CalibrationStore.create_in_memory_snapshot()` / `restore_in_memory_snapshot()`
     added.

3. **P0.3 — Remove heuristic unit conversions** (`calibration/patch_rules.py`)
   - `T1Rule`: Removed `if t1_raw > 1e-3` heuristic; prefers `T1_s` then
     `T1_ns`, bare `T1` emits `DeprecationWarning` if > 1 ms.
   - `T2RamseyRule` / `T2EchoRule`: Prefer `_s` then `_ns` keys; bare keys
     emit `DeprecationWarning`.

4. **P1.1 — CalibrationStore as single source of truth**
   (`analysis/cQED_attributes.py`)
   - `verify_consistency(store)` detects drift between `cQED_attributes` and
     `CalibrationStore`.
   - `from_calibration_store(store, …)` classmethod builds a snapshot from
     the store.
   - `_CQED_FIELD_MAP` / `_PULSE_FIELD_MAP` ClassVar dicts for canonical
     name mapping.

5. **P1.2 — Session-scoped MeasurementConfig** (`core/measurement_config.py`,
   NEW file)
   - Frozen `@dataclass MeasurementConfig` with discrimination/quality params.
   - Factory methods: `from_calibration_store()`,
     `from_measure_macro_snapshot()`.
   - `apply_to_measure_macro()` with `DeprecationWarning`.

6. **P2.1 — MultiProgramExperiment** (`experiments/multi_program.py`, NEW file)
   - `MultiProgramExperiment(ExperimentBase)` abstract base with
     `build_programs()` and `run_all()` orchestrator.
   - `MultiProgramResult` dataclass for combined results.

**Tests:** 32 tests in `tests/test_workflow_safety_refactor.py` — all passing.

**Files affected:**

- `qubox_v2/experiments/result.py` — `FitResult` fields
- `qubox_v2/analysis/fitting.py` — `fit_and_wrap()` success/failure
- `qubox_v2/calibration/orchestrator.py` — analyze guard, transactional apply
- `qubox_v2/analysis/calibration_algorithms.py` — warnings
- `qubox_v2/calibration/store.py` — snapshot/restore
- `qubox_v2/calibration/patch_rules.py` — T1/T2 rule rework
- `qubox_v2/analysis/cQED_attributes.py` — verify_consistency, from_store
- `qubox_v2/core/measurement_config.py` (NEW)
- `qubox_v2/experiments/multi_program.py` (NEW)
- `qubox_v2/tests/test_workflow_safety_refactor.py` (NEW)
- `qubox_v2/docs/workflow_safety_refactor.md` (NEW)
- `docs/CHANGELOG.md` — This entry
- `README.md` — Version bump

---

### 2026-02-27 — Generic Alias System (v2.3.1)

**Classification: Minor**

Replaced the fixed-role `set_roles(qubit=..., readout=..., storage=...)` API
with a generic `set_aliases()` that accepts arbitrary alias→element mappings.
No mandatory role names are enforced by the builder; well-known names
(`"qubit"`, `"readout"`, `"storage"`) are convention-mapped to legacy
`cqed_params.json` fields for backward compatibility.

**Summary:**

1. **`set_aliases()` replaces `set_roles()` (`hardware_definition.py`)**
   - Accepts `dict[str, str]` and/or `**kwargs` (merged, kwargs win).
   - No specific alias names are required — the builder is fully generic.
   - Internally stores `self._aliases` instead of `self._roles`.

2. **Validation relaxed**
   - Removed check 1 (qubit/readout roles required).
   - Check 2 (readout alias validation) only triggers when a `"readout"`
     alias is present.
   - Remaining checks renumbered 1–9.

3. **`to_cqed_seed()` convention-based mapping**
   - Well-known aliases map to legacy fields: `"qubit"` → `qb_el`/`qb_fq`,
     `"readout"` → `ro_el`/`ro_fq`, `"storage"` → `st_el`/`st_fq`.
   - All aliases stored under `__aliases` key for forward-compatible readers.

4. **`_build_qubox_extras()` generic roles**
   - `__qubox.bindings.roles` now populated from all aliases (not just
     hardcoded qubit/readout/storage).
   - `readout_acquire` auto-added when `"readout"` alias targets a readout
     element with `rf_in`.

5. **Notebook update (`post_cavity_experiment_context.ipynb`)**
   - Cell 4: `set_roles(...)` → `set_aliases(...)`.

6. **Documentation (`API_REFERENCE.md`)**
   - Section 27.4 renamed to "Wiring & Alias Methods"; `set_roles()` docs
     replaced with `set_aliases()` including alias→cqed_params mapping table.
   - Validation table updated (checks renumbered, check 1 removed).

**Files affected:**

- `qubox_v2/core/hardware_definition.py`
- `notebooks/post_cavity_experiment_context.ipynb`
- `qubox_v2/docs/API_REFERENCE.md` — Section 27
- `qubox_v2/docs/CHANGELOG.md` — This entry

---

### 2026-02-26 — HardwareDefinition Device Builder (v2.3)

**Classification: Moderate**

Extended `HardwareDefinition` to generate `devices.json` alongside
`hardware.json` and `cqed_params.json`, making notebook cell 4 the single
source of truth for all hardware setup — no manual JSON editing required.

**Summary:**

1. **`_DeviceDef` dataclass (`hardware_definition.py`)**
   - Internal representation for external instrument definitions: `name`,
     `driver`, `backend`, `connect`, `settings`, `enabled`.

2. **`set_instrument_server()` method**
   - Stores shared InstrumentServer connection defaults (`host`, `port`,
     `timeout`).  Devices added after this call auto-inherit these
     connection parameters.

3. **`add_device()` method**
   - Adds an external device with smart defaults: when a shared server is
     set and `connect=None`, auto-populates the connect dict.
     `instrument_name` shorthand avoids verbose connect dicts for the
     common InstrumentServer case.

4. **`to_devices_dict()` / `save_devices()` methods**
   - `to_devices_dict()` returns the flat dict matching the existing
     `devices.json` schema.
   - `save_devices(path, merge_existing=True)` writes the file, preserving
     any manually-added devices.  Returns `None` if no devices defined.

5. **Validation check 10**
   - `validate()` now warns (not errors) when `set_external_lo(device=X)`
     references a device not defined via `add_device()`.

6. **Session integration (`session.py`)**
   - `_apply_hardware_definition()` now also generates `devices.json` after
     `hardware.json` and `cqed_params.json`.

7. **Notebook update (`post_cavity_experiment_context.ipynb`)**
   - Cell 4 updated with `set_instrument_server()` and `add_device()` calls
     for all 4 external instruments (`octave_external_lo2`,
     `octave_external_lo4`, `octodac_bf`, `sa124b`).

8. **Documentation (`API_REFERENCE.md`)**
   - Added Section 27 "HardwareDefinition Builder (v2.3)" covering
     constructor, element methods, device builder methods, generation &
     persistence, validation, session integration, and usage example.

**Files affected:**

- `qubox_v2/core/hardware_definition.py`
- `qubox_v2/experiments/session.py`
- `notebooks/post_cavity_experiment_context.ipynb`
- `qubox_v2/docs/API_REFERENCE.md` — Section 27
- `qubox_v2/docs/CHANGELOG.md` — This entry

---

### 2026-02-26 — QUA Program Build & Simulation Refactor (v2.2)

**Classification: Major**

Added first-class `build_program()` → `ProgramBuildResult` and `simulate()` →
`SimulationResult` support to all 26 experiment classes, enabling program
introspection and offline waveform simulation without touching hardware.

**Summary:**

1. **Phase 0 — Core infrastructure (`experiments/result.py`, `experiment_base.py`, `hardware/program_runner.py`)**
   - `ProgramBuildResult` frozen dataclass (12 fields): captures QUA program,
     resolved parameters, frequency assignments, processors, and provenance.
   - `QuboxSimulationConfig` dataclass: centralises simulation parameters
     (duration_ns, plot, controllers, compiler_options).
   - `SimulationResult` dataclass: wraps simulated waveform samples +
     full provenance chain back to `ProgramBuildResult`.
   - Base class `build_program()` calls `_build_impl()` then applies
     `resolved_frequencies` to hardware config.
   - Base class `simulate()` calls `build_program()` then `runner.simulate()`.
   - Pure frequency resolvers: `_resolve_readout_frequency()` (bindings →
     measureMacro → attributes), `_resolve_qubit_frequency(detune=)`.
   - `_serialize_bindings()` for JSON-safe provenance snapshots.

2. **Phase 1 — Pilot experiments (4 classes)**
   - PowerRabi, T1Relaxation, QubitSpectroscopy, ResonatorSpectroscopy
     migrated to `_build_impl()` pattern. `run()` delegates to
     `build_program()` + `run_program()`.

3. **Phase 2 — Full migration (22 remaining classes)**
   - **Spectroscopy**: ResonatorSpectroscopyX180, ReadoutTrace,
     ResonatorPowerSpectroscopy, QubitSpectroscopyEF.
   - **Time domain**: TemporalRabi, SequentialQubitRotations, T2Ramsey,
     T2Echo, ResidualPhotonRamsey, TimeRabiChevron, PowerRabiChevron,
     RamseyChevron.
   - **Cavity/storage**: StorageSpectroscopy, NumSplittingSpectroscopy,
     StorageRamsey, StorageChiRamsey, StoragePhaseEvolution.
   - **Cavity/fock**: FockResolvedSpectroscopy, FockResolvedT1,
     FockResolvedRamsey, FockResolvedPowerRabi.
   - **Multi-program (NotImplementedError)**: QubitSpectroscopyCoarse,
     ReadoutFrequencyOptimization, StorageSpectroscopyCoarse — these use
     multi-LO segment loops and cannot produce a single ProgramBuildResult.

4. **Key migration patterns applied across all classes:**
   - `set_standard_frequencies()` replaced with pure resolvers.
   - `attr.qb_fq`/`attr.ro_fq` direct references replaced with
     `_resolve_qubit_frequency()` / `_resolve_readout_frequency()`.
   - Processors stored as immutable tuples in ProgramBuildResult.
   - measureMacro-dependent experiments use `_setup_measure_context()` +
     `simulate()` override.
   - Non-serializable params (callables, large arrays) excluded from `params`.

5. **Documentation (API_REFERENCE.md)**
   - Added Section 26 "Program Build & Simulation (v2.2)" covering design
     principles, data types, base class methods, migration pattern,
     measureMacro context pattern, multi-program experiments, usage examples,
     and migration status table.

**Files affected:**

- `qubox_v2/experiments/result.py` — ProgramBuildResult, SimulationResult
- `qubox_v2/experiments/experiment_base.py` — build_program(), _build_impl(),
  simulate(), pure resolvers
- `qubox_v2/hardware/program_runner.py` — QuboxSimulationConfig
- `qubox_v2/experiments/time_domain/rabi.py`
- `qubox_v2/experiments/time_domain/relaxation.py`
- `qubox_v2/experiments/time_domain/coherence.py`
- `qubox_v2/experiments/time_domain/chevron.py`
- `qubox_v2/experiments/spectroscopy/qubit.py`
- `qubox_v2/experiments/spectroscopy/resonator.py`
- `qubox_v2/experiments/cavity/storage.py`
- `qubox_v2/experiments/cavity/fock.py`
- `qubox_v2/docs/API_REFERENCE.md` — Section 26
- `qubox_v2/docs/CHANGELOG.md` — This entry

---

### 2026-02-26 — Roleless experiment primitives (v2.1 API)

**Classification: Moderate**

Introduced frozen, role-free types that decouple experiment code from the
mutable `ExperimentBindings` role vocabulary.  Experiments type-check for
generic `DriveTarget` and `ReadoutHandle` — never for "qubit" or "storage"
specifically.  Added per-experiment frozen Config dataclasses and session
factory methods.

**Summary:**

1. **Phase 0 frozen primitives** (`core/bindings.py`):
   - `DriveTarget` — frozen control output (element, lo_freq, rf_freq, therm_clks).
     `if_freq` property, `from_output_binding()` classmethod.
   - `ReadoutCal` — frozen calibration artifact snapshot (drive_frequency,
     threshold, rotation_angle, confusion_matrix, fidelity, weight_keys).
     `from_calibration_store()`, `from_readout_binding()`, `with_discrimination()`.
   - `ReadoutHandle` — frozen readout channel + ReadoutCal + element + operation.
   - `ElementFreq` — resolved frequency per element with provenance `source` tag
     ("explicit", "calibration", "sample_default").
   - `FrequencyPlan` — immutable frequency plan applied atomically per run.
     `from_targets()`, `apply(hw)`, `to_metadata()`.

2. **`emit_measurement()`** (`programs/macros/measure.py`) — Pure function
   replacement for `measureMacro.measure()`.  Takes a `ReadoutHandle`, builds
   demod from `cal.weight_keys`, returns QUA variables.

3. **Session factory methods** (`experiments/session.py`):
   - `session.drive_target(alias)` — resolves alias to `DriveTarget` from
     hardware config + calibration store.
   - `session.readout_handle(alias)` — resolves alias to `ReadoutHandle`.
   - Ergonomic shortcuts: `session.qubit()`, `session.storage()`, `session.readout()`.

4. **Per-experiment Config dataclasses** (`experiments/configs.py`):
   - `PowerRabiConfig`, `TemporalRabiConfig`, `T1RelaxationConfig`,
     `T2RamseyConfig`, `T2EchoConfig`, `ResonatorSpectroscopyConfig`,
     `QubitSpectroscopyConfig`, `StorageSpectroscopyConfig`.
   - All frozen, composable via `dataclasses.replace()`.

5. **Notebook update** — Added v2.1 API imports, explanation markdown cell,
   and interactive demonstration cell to `post_cavity_experiment_context.ipynb`.

6. **Documentation** — Added Section 25 to API_REFERENCE.md covering all v2.1
   types, session factories, Config dataclasses, and migration guidance.

**Files affected:**
- `qubox_v2/core/bindings.py` — Added 5 frozen dataclasses
- `qubox_v2/core/__init__.py` — Updated `__all__` exports
- `qubox_v2/programs/macros/measure.py` — Added `emit_measurement()`
- `qubox_v2/experiments/session.py` — Added factory methods
- `qubox_v2/experiments/configs.py` — Created (8 Config dataclasses)
- `notebooks/post_cavity_experiment_context.ipynb` — Added v2.1 cells
- `qubox_v2/docs/API_REFERENCE.md` — Added Section 25
- `qubox_v2/docs/CHANGELOG.md` — This entry

---

### 2026-02-26 — Complete builder bindings coverage + implementation audit

**Classification: Moderate**

Added `bindings: ExperimentBindings | None = None` parameter to all remaining
program builder functions (18 functions across 4 files) and appended a
comprehensive implementation status checklist to the refactor report.

**Summary:**

1. **Builder bindings coverage** — Added binding resolution pattern to:
   - `readout.py`: `readout_ge_raw_trace`, `readout_ge_integrated_trace`,
     `readout_core_efficiency_calibration`, `readout_butterfly_measurement`,
     `readout_leakage_benchmarking`, `qubit_reset_benchmark`,
     `active_qubit_reset_benchmark` (7 functions)
   - `calibration.py`: `all_xy`, `randomized_benchmarking`,
     `drag_calibration_YALE`, `drag_calibration_GOOGLE` (4 functions)
   - `cavity.py`: `sel_r180_calibration0`, `fock_resolved_spectroscopy`,
     `fock_resolved_T1_relaxation`, `fock_resolved_power_rabi`,
     `fock_resolved_qb_ramsey`, `storage_wigner_tomography` (6 functions)
   - `tomography.py`: `fock_resolved_state_tomography` (1 function)

2. **Implementation status checklist** — Appended §10 to
   `docs/api_refactor_output_binding_report.md` cross-referencing every
   recommendation from §2–§6 against codebase state.  Covers 80+ checklist
   items across binding model, measureMacro redesign, 12 ranked coupling
   items, calibration schema, and migration phases.

**Files affected:**
- `qubox_v2/programs/builders/readout.py`
- `qubox_v2/programs/builders/calibration.py`
- `qubox_v2/programs/builders/cavity.py`
- `qubox_v2/programs/builders/tomography.py`
- `docs/api_refactor_output_binding_report.md`
- `qubox_v2/docs/CHANGELOG.md` (this entry)

---

### 2026-02-24 — Notebook Usability Refactor + Rotation Calibration Port

**Classification: Moderate**

Comprehensive refactoring of `post_cavity_experiment_context.ipynb` for
improved usability, mixer calibration workflow, bug fixes, and porting
of the legacy arbitrary qubit rotation calibration pipeline.

**Summary:**

1. **A1 — Setup flow merge (Sections 1+2+2.1 -> Section 1)**
   - Merged 11 cells (registry, sample, cooldown, session, open, preflight,
     readout override) into a 4-cell idempotent initialization flow.
   - Combined `SessionManager` creation and `session.open()` into a single cell.
   - Preflight validation, config snapshot, and schema validation in Section 1.1.
   - Imports consolidated into a single cell with all dependencies.

2. **A2 — Dedicated readout override cell (Section 1.2)**
   - Extracted readout override into its own cell with explicit I/O documentation.
   - Clear inputs: element, operation, weights, demod, threshold, weight length.
   - Clear outputs: updated measureMacro state, persisted measureConfig.json.

3. **B — Mixer calibration overhaul (Section 2)**
   - Added Section 2.0: Auto Calibration (Octave built-in) with
     `hw.calibrate_element(method="auto", auto_sa_validate=True)`.
   - Added Section 2.1: Manual Calibration UX Controls (scan bounds, SA settings).
   - Added Section 2.2: Manual IQ Calibration Run with before/after metrics.
   - Section renumbered from 3 to 2.

4. **C — Bug fixes**
   - Fixed `ro_pipeline_summary.get("discrimination")` using nonexistent keys;
     replaced with `ro_pipeline_analysis.metrics` access.
   - Fixed `eval(name)` security issue in session summary; replaced with
     `globals().get(name)`.

5. **D — Arbitrary qubit rotation calibration port (Sections 5.1d-5.1f)**
   - Section 5.1d: Verify Run — applies knob corrections and re-runs
     pulse-train tomography on a 3-prep subset at half n_avg.
   - Section 5.1e: Verify Analysis — compares before/after angular deviations.
   - Section 5.1f: Apply Corrections to All Standard Rotations — broadcasts
     d_lambda/d_alpha/d_omega knob maps to all pi/2 and pi gates via
     `register_rotations_from_ref_iq`.

6. **Section renumbering**
   - All sections renumbered: 3->2, 4->3, ..., 14->13 (net reduction of 1).
   - TOC and summary table updated to match.

7. **E — No auto-commit policy**
   - Added Rule #4 to CHANGELOG.md policy section.

**Files affected:**
- `notebooks/post_cavity_experiment_context.ipynb` (116 cells, restructured)
- `qubox_v2/docs/CHANGELOG.md` (policy update + this entry)

---

### 2026-02-24 — Namespace Rename: device -> sample

---

### 2026-03-23 — Notebook 00 Recovery for Wiring Mismatch and Schema-Versioned Devices

**Classification: Moderate**

**Summary:**

1. **Notebook recovery for stale calibration context**
  - Updated `notebooks/00_hardware_defintion.ipynb` so session bootstrap detects a `ContextMismatchError` caused by a wiring revision change, creates a timestamped backup of the stale cooldown `calibration.json`, deletes the stale file, and retries opening the session against the current hardware definition.
  - This preserves strict calibration-context safety while giving the notebook an explicit recovery path after hardware-definition edits.

2. **Schema-version-aware device loading**
  - Fixed `qubox/devices/device_manager.py` so `devices.json` files with top-level metadata like `schema_version` load correctly.
  - The loader now accepts either a flat top-level device map or a wrapped `devices` map, ignores non-dict metadata entries, and preserves `schema_version` when saving.

3. **Regression coverage**
  - Added tests covering schema-versioned flat `devices.json` loading and schema-version preservation on save.

**Files affected:**
- `notebooks/00_hardware_defintion.ipynb`
- `qubox/devices/device_manager.py`
- `tests/test_schemas.py`
- `docs/CHANGELOG.md`

**Classification: Major**

Renamed the experiment database namespace from "device" to "sample" across
the entire codebase.  The sample registry, experiment context, calibration
context, session manager, notebook builder, and on-disk data all now use
`sample_id` as the canonical identifier for physical chip samples.

**Summary:**

1. **Core rename (`qubox_v2/devices/sample_registry.py`)**
   - `DeviceRegistry` -> `SampleRegistry`, `DeviceInfo` -> `SampleInfo`.
   - Field renames: `device_id` -> `sample_id`, `sample_info` -> `metadata`.
   - `DEVICE_LEVEL_FILES` -> `SAMPLE_LEVEL_FILES`.
   - All method renames: `create_device` -> `create_sample`,
     `device_exists` -> `sample_exists`, `device_path` -> `sample_path`,
     `list_devices` -> `list_samples`, `load_device_info` -> `load_sample_info`.
   - On-disk directory: `devices/` -> `samples/`, `device.json` -> `sample.json`.

2. **Experiment context (`qubox_v2/core/experiment_context.py`)**
   - `ExperimentContext.device_id` -> `sample_id`.
   - `matches_device()` -> `matches_sample()`.
   - `from_dict()` accepts legacy `"device_id"` key as fallback.

3. **Session state (`qubox_v2/core/session_state.py`)**
   - `device_id` field -> `sample_id`.
   - `device_config_dir` param -> `sample_config_dir`.

4. **Calibration layer**
   - `CalibrationContext.device_id` -> `sample_id` (`calibration/models.py`).
   - `CalibrationStore` migrates legacy `context.device_id` on load (`calibration/store.py`).
   - `schemas.py` validation accepts both `sample_id` and `device_id` in context.

5. **Context resolver (`qubox_v2/devices/context_resolver.py`)**
   - All `device_id` params -> `sample_id`.

6. **Session manager (`qubox_v2/experiments/session.py`)**
   - Constructor param `device_id` -> `sample_id`.
   - `_device_config_dir` -> `_sample_config_dir`.
   - `from_device()` -> `from_sample()` (alias preserved).

7. **Notebook and tools**
   - `tools/build_context_notebook.py` updated (~25 edits).
   - Notebook regenerated (110 cells).
   - `tools/migrate_device_to_samples.py` created for on-disk data migration.

8. **On-disk data migration**
   - `devices/post_cavity_sample_A/` -> `samples/post_cavity_sample_A/`.
   - `device.json` -> `sample.json` with key renames.
   - 980 files migrated and validated.

9. **Backward compatibility**
   - `DeviceRegistry = SampleRegistry` alias in `devices/__init__.py`.
   - `DeviceInfo = SampleInfo` alias.
   - `SessionManager.from_device = from_sample` alias.
   - `SampleRegistry` falls back to `devices/` dir if `samples/` missing.
   - `from_dict()` methods accept legacy `"device_id"` keys.

10. **Documentation**
    - `API_REFERENCE.md` updated: 74 occurrences across 13 sections.
    - Version bumped to 1.7.0.

**Files affected:**
- qubox_v2/devices/sample_registry.py (renamed from device_registry.py)
- qubox_v2/devices/__init__.py
- qubox_v2/devices/context_resolver.py
- qubox_v2/core/experiment_context.py
- qubox_v2/core/session_state.py
- qubox_v2/core/schemas.py
- qubox_v2/calibration/models.py
- qubox_v2/calibration/store.py
- qubox_v2/experiments/session.py
- qubox_v2/docs/API_REFERENCE.md
- qubox_v2/docs/CHANGELOG.md
- tools/build_context_notebook.py
- tools/migrate_device_to_samples.py (new)
- notebooks/post_cavity_experiment_context.ipynb (regenerated)

---

### 2026-02-23 — Time-Unit Audit + Frequency Binding Hardening

**Classification: Major**

Targeted audit and fixes for time-unit consistency (`_clks` vs `ns`) and
runtime frequency binding to calibrated state.

**Summary:**

1. **Canonical coherence unit enforcement (seconds)**
   - T1 analysis now emits explicit `T1_ns`, `T1_s`, and `T1_us` metrics.
   - Patch generation writes `coherence.<qb>.T1` in **seconds**.
   - Added backward-compatible T1 patch rule handling for legacy keys.

2. **Legacy coherence migration guard**
   - Calibration store now normalizes legacy coherence values that were
     accidentally persisted in ns to canonical seconds (using `*_us` when
     available as authoritative companion values).

3. **Butterfly T1-decay correction unit fix**
   - `measureMacro.active_length()` is now treated explicitly as ns.
   - Conversion path is explicit and validated:
     `ns -> clks (internal canonical) -> seconds`.
   - Added metrics for `readout_duration_ns`, `readout_duration_clks`, and
     robust legacy T1 fallback handling.

4. **Additional time mismatch fix from codebase sweep**
   - `programs/builders/spectroscopy.py` had a confirmed mismatch:
     depletion wait argument documented/passed as clock cycles but divided
     by 4 internally.
   - Fixed to use clock cycles directly.
   - Added backward-compatible alias handling (`depletion_len` ->
     `depletion_clks`) with validation.

5. **Explicit time naming for residual-photon Ramsey**
   - `ResidualPhotonRamsey.run()` now uses explicit `t_relax_ns` and
     `t_buffer_ns` naming, with backward-compatible aliases
     (`t_relax`, `t_buffer`) and 4 ns grid validation.

6. **Frequency binding to calibrated state**
   - Added calibrated-frequency resolution helpers in `ExperimentBase`.
   - Ramsey and related detuned paths now use calibrated qubit frequency
     source first, then attributes fallback.
   - After patch commit, session now refreshes runtime attributes from
     calibration frequencies so `attr.qb_fq` tracks the calibrated state.

7. **Notebook context diagnostics (Section 7.5 builder)**
   - Added explicit prints for butterfly readout duration in ns/clks,
     T1 decay factor, and calibrated-vs-runtime qubit frequency delta.

**Files affected:**

- `qubox_v2/experiments/time_domain/relaxation.py`

---

### 2026-02-26 — Additional Migration: samples/ + post_cavity notebook to binding-driven path

**Classification: Major**

Completed follow-up migration work after the v2.0.0 binding-driven redesign, covering sample configuration canonicalization and notebook-level API updates.

**Summary:**

1. **Binding-first sample config support**
  - Extended `__qubox` hardware extras schema to include canonical binding payloads and aliases:
    - `bindings`, `binding_bundle`, `aliases`, `alias_map`
  - `bindings_from_hardware_config()` now prefers canonical `__qubox.bindings`, with legacy `elements` fallback.
  - `build_alias_map()` now prefers canonical alias maps and resolves to physical `ChannelRef`s.

2. **Representative sample migrated (`post_cavity_sample_A`)**
  - Added canonical `__qubox.bindings` and `__qubox.aliases` to sample-level `hardware.json`.
  - Preserved ergonomic user aliases (`qubit`, `resonator`) mapped to physical IDs.
  - Migrated cooldown `calibration.json` from schema `4.0.0` to `5.0.0`:
    - stable keys by physical channel ID
    - `alias_index` for dual alias/physical lookup

3. **Notebook migration (binding-driven setup bridge)**
  - Updated `post_cavity_experiment_context.ipynb` setup/readout workflow toward `session.bindings` path.
  - Added binding aliases and compatibility bridge variables to keep legacy element-op helper calls usable during transition.

4. **Validation**
  - Verified binding resolution from migrated sample config (`qubit`, `resonator`, readout acquire chain).
  - Verified calibration dual lookup by alias and physical ID on migrated v5.0.0 calibration file.

**Files affected:**
- `qubox_v2/core/config.py`
- `qubox_v2/core/bindings.py`
- `samples/post_cavity_sample_A/config/hardware.json`
- `samples/post_cavity_sample_A/cooldowns/cd_2025_02_22/config/calibration.json`
- `notebooks/post_cavity_experiment_context.ipynb`
- `docs/api_refactor_output_binding_report.md`
- `qubox_v2/docs/CHANGELOG.md`
- `qubox_v2/calibration/patch_rules.py`
- `qubox_v2/calibration/store.py`
- `qubox_v2/experiments/calibration/readout.py`
- `qubox_v2/programs/builders/spectroscopy.py`
- `qubox_v2/experiments/time_domain/coherence.py`
- `qubox_v2/experiments/experiment_base.py`
- `qubox_v2/experiments/session.py`
- `qubox_v2/calibration/orchestrator.py`
- `qubox_v2/experiments/calibration/gates.py`
- `tools/build_context_notebook.py`
- `qubox_v2/docs/CHANGELOG.md`

### 2026-02-23 — Calibration Schema + Notebook Refactor + Changelog Policy

**Classification: Major**

Structured refactor of the calibration schema, readout calibration workflow,
and API documentation.

**Summary:**

1. **Calibration schema refactor (`models.py`)**
   - `ElementFrequencies.lo_freq` and `if_freq` changed from required `float`
     to optional `float | None = None`.
   - Added `rf_freq: float | None = None` for explicit RF frequency storage.
   - `PulseCalibration.element` changed from required `str` to
     `str | None = None`.
   - Added readout calibration metadata fields to `DiscriminationParams` and
     `ReadoutQuality`: `n_shots`, `integration_time_ns`, `demod_weights`,
     `state_prep_ops`.
   - `CalibrationData.version` default changed from `"3.0.0"` to `"4.0.0"`.

2. **Calibration store refactor (`store.py`)**
   - `_atomic_write()` now uses `model_dump(exclude_none=True)` — unset
     optional fields are omitted from persisted JSON.
   - `set_frequencies()` no longer defaults `lo_freq`/`if_freq` to `0.0`.
   - `set_pulse_calibration()` no longer defaults `element` to `""`.

3. **Calibration JSON cleanup (`calibration.json`)**
   - Removed `x180` entry from `pulse_calibrations` — derived pulses must
     not be stored in calibration.
   - Fixed `element: ""` to `element: "qubit"` for `ref_r180` and
     `sel_ref_r180`.
   - Removed `lo_freq: 0.0` / `if_freq: 0.0` placeholders from qubit
     frequencies block.
   - Removed all `null` placeholder fields (confusion_matrix, alpha, beta,
     affine_n, qubit-only params in resonator block, etc.).

4. **Patch rules update (`patch_rules.py`)**
   - `DragAlphaRule` now patches only `ref_r180.drag_coeff` — derived
     primitives inherit via `PulseFactory` `rotation_derived`.

5. **Notebook refactor (`post_cavity_experiment_context.ipynb`)**
   - Section 7.5 (Full Readout Calibration): refactored to explicit
     Run → Analyze → Patch workflow.  `analyze()` called with
     `update_calibration=False`; calibration patched explicitly in
     section 7.6.
   - Section 8.3 replaced: new "Selective Pulse Calibration Update"
     following the same explicit patch pattern as section 5.7.
   - Old section 8.3 (Register Storage Cavity Pulse Definitions) moved
     to section 9.0 as the first subsection of Storage Cavity.

6. **API Reference update (`API_REFERENCE.md`)**
   - Version bumped to 1.6.0.
   - Section 4.4: updated data model table, added null-handling policy,
     frequency convention, and pulse calibration storage policy.
   - Section 4.5: readout calibration example updated to explicit patch model.
   - Section 7.2: calibration.json structure updated to v4.0.0 schema with
     context block and new conventions.
   - Section 7.4: calibration version updated from "3.0.0" to "4.0.0".

7. **Changelog policy (`CHANGELOG.md`)**
   - Introduced formal append-only change-log policy.

**Files affected:**

- `qubox_v2/calibration/models.py`
- `qubox_v2/calibration/store.py`
- `qubox_v2/calibration/patch_rules.py`
- `qubox_v2/docs/API_REFERENCE.md`
- `qubox_v2/docs/CHANGELOG.md` (new)
- `devices/post_cavity_sample_A/cooldowns/cd_2025_02_22/config/calibration.json`
- `notebooks/post_cavity_experiment_context.ipynb`

### 2026-02-23 — Derived-Pulse Calibration Write Cleanup (Consistency Scan)

**Classification: Moderate**

Post-refactor consistency scan: removed all remaining code paths that wrote
derived pulse names (x180, y180, etc.) or the deprecated
`propagate_drag_to_primitives` parameter to calibration stores, patch ops,
or orchestrator defaults.

**Summary:**

1. **DRAGCalibration analysis (`gates.py`)**
   - Removed `x180` `SetCalibration` op from `proposed_patch_ops` in
     `DRAGCalibration.analyze()`.
   - Removed the entire `propagate_drag_to_primitives` loop that generated
     per-derived-pulse `SetCalibration` ops.
   - Now emits only `ref_r180.drag_coeff` + `TriggerPulseRecompile`.

2. **Rabi experiments (`rabi.py`)**
   - `TemporalRabi.analyze()`: Changed calibration commit target from
     `name="x180"` to `name="ref_r180"`.
   - `PowerRabi.run()`: Changed default `op` parameter from `"x180"` to
     `"ref_r180"`.
   - `PowerRabi.analyze()`: Changed fallback `target_op` from `"x180"` to
     `"ref_r180"`.

3. **Orchestrator (`orchestrator.py`)**
   - `_set_pulse_param()`: Removed `"element": ""` from the fallback dict
     when no existing calibration is found, preventing empty-string element
     values from being written.

4. **API Reference (`API_REFERENCE.md`)**
   - Removed `propagate_drag_to_primitives=True` from two DRAG calibration
     examples (sections 4.5 and 9.3).

5. **Notebooks**
   - `post_cavity_experiment_context.ipynb`: Removed
     `"propagate_drag_to_primitives": True` from DRAG orchestrator
     `analyze_kwargs`.
   - `post_cavity_experiment.ipynb`: Same removal from DRAG calibration cell.

**Files affected:**

- `qubox_v2/experiments/calibration/gates.py`
- `qubox_v2/experiments/time_domain/rabi.py`
- `qubox_v2/calibration/orchestrator.py`
- `qubox_v2/docs/API_REFERENCE.md`
- `notebooks/post_cavity_experiment_context.ipynb`
- `notebooks/post_cavity_experiment.ipynb`
- `tools/build_context_notebook.py`
- `qubox_v2/examples/session_startup_demo.py`

### 2026-02-23 — Codebase Audit Cleanup (Post-Refactor Sweep)

**Classification: Major**

Comprehensive codebase audit and cleanup covering ~30 distinct issues across
all modules. Removes dead `CalibrationStateMachine` subsystem per architecture
decision to standardize on `CalibrationOrchestrator`.

**Summary:**

1. **Architecture: Remove CalibrationStateMachine (H1/H2)**
   - Deleted `calibration/state_machine.py` and `calibration/patch.py` (dead code).
   - Removed CalibrationStateMachine demo from `examples/session_startup_demo.py`.
   - Updated notebook cells referencing state machines (cells 44, 45, 104, 112).
   - Updated `API_REFERENCE.md` sections 4.2, 4.3, 4.6 and 7.5 to remove
     CalibrationStateMachine references, replaced with CalibrationOrchestrator
     and Contracts documentation.

2. **Critical field mismatches (C1)**
   - Added `T1_us`, `T2_star_us`, `T2_echo_us`, `qb_therm_clks` to
     `CoherenceParams` in `calibration/models.py`.
   - Added `phase_offset` to `PulseCalibration` in `calibration/models.py`.

3. **Return type fix (C2)**
   - `compute_probabilities()` in `analysis/analysis_tools.py` now returns
     `dict` matching its `-> Mapping[str, float]` annotation.

4. **Missing exports (C3, C4, H5)**
   - Exported `SNAPHardware` from `gates/hardware/__init__.py`.
   - Exported `PulseTrainRule` from `calibration/__init__.py`.
   - Exported `PulseError`, `CalibrationError` from `core/__init__.py`.

5. **Standardize qua.align() (H6)**
   - `DisplacementHardware.play_qua()`: `qua.align(self.target)` → `qua.align()`.

6. **Stub analyze/plot methods (H3)**
   - Added `analyze()` and `plot()` to `TimeRabiChevron`, `PowerRabiChevron`,
     `RamseyChevron` in `experiments/time_domain/chevron.py`.
   - Added `analyze()` and `plot()` to `SequentialQubitRotations` in
     `experiments/time_domain/rabi.py`.

7. **Orchestrator: list_applied_patches() (notebook support)**
   - Added `_applied_patches` tracking list and `list_applied_patches()` method
     to `CalibrationOrchestrator`.

8. **Deduplicate constants (M6)**
   - `pulses/manager.py` now imports `MAX_AMPLITUDE`, `BASE_AMPLITUDE` from
     `core/types.py` instead of redefining them.

9. **Remove duplicate imports (M7)**
   - Cleaned duplicate imports in `tools/waveforms.py`, `gates/contexts.py`,
     `analysis/analysis_tools.py`, `analysis/cQED_models.py`.

10. **Fix analysis/__all__ (M8)**
    - Removed misleading `"calibration_algorithms"` from `analysis/__init__.py`
      `__all__` (lazy-loaded module, not eagerly imported).

11. **Unused import removal (L1)**
    - Removed unused `from dataclasses import asdict` in `calibration/orchestrator.py`.

12. **Encoding artifact fix (L5)**
    - Fixed UTF-8 mojibake in `analysis/cQED_plottings.py` line 443.

**Files affected:**

- `qubox_v2/calibration/state_machine.py` (deleted)
- `qubox_v2/calibration/patch.py` (deleted)
- `qubox_v2/calibration/models.py`
- `qubox_v2/calibration/__init__.py`
- `qubox_v2/calibration/orchestrator.py`
- `qubox_v2/analysis/analysis_tools.py`
- `qubox_v2/analysis/cQED_models.py`
- `qubox_v2/analysis/cQED_plottings.py`
- `qubox_v2/analysis/__init__.py`
- `qubox_v2/core/__init__.py`
- `qubox_v2/gates/hardware/__init__.py`
- `qubox_v2/gates/hardware/displacement.py`
- `qubox_v2/gates/contexts.py`
- `qubox_v2/pulses/manager.py`
- `qubox_v2/tools/waveforms.py`
- `qubox_v2/experiments/time_domain/chevron.py`
- `qubox_v2/experiments/time_domain/rabi.py`
- `qubox_v2/examples/session_startup_demo.py`
- `qubox_v2/docs/API_REFERENCE.md`
- `qubox_v2/docs/CHANGELOG.md`
- `notebooks/post_cavity_experiment_context.ipynb`

---

### 2026-02-25 — Audit-Driven Bug Fixes & Hardening (v1.8.0)

**Classification: Moderate**

Systematic fixes for all issues identified in the audit (see below): 4 bugs,
duplicate/missing patch rules, dead parameters, incomplete calibration
patterns, and documentation updates.

**Summary:**

1. **BUG-1 — Wigner negativity formula (`wigner_tomo.py:67`)**
   - `negativity = np.abs(np.sum(W[W < 0]))` was applying `np.abs` to
     already-negative values, which is correct mathematically but masked
     intent.  Changed to `negativity = float(-np.sum(W[W < 0]))` for
     clarity and to match the standard Wigner negativity definition
     (sum of negative volume).

2. **BUG-2 — Silent exception swallowing in SPAPumpFrequencyOptimization
   (`flux_optimization.py`)**
   - Bare `except Exception: pass` silently swallowed errors during SPA
     frequency optimization.  Added `logging` import and replaced with
     `logger.exception("SPA pump frequency optimization step failed")`
     so failures are recorded.

3. **BUG-3 — T1Rule heuristic unit guess (`patch_rules.py:~120`)**
   - T1 unit-detection heuristic used `T1_val > 1.0` to distinguish
     seconds vs nanoseconds.  A 10 us T1 (1e-5 s) would be incorrectly
     treated as nanoseconds and divided by 1e9 again.  Changed threshold
     to `T1_val > 1e-3`, which correctly classifies all realistic T1
     values (sub-ms coherence times in seconds vs nanosecond-scale raw
     values).

4. **BUG-4 — QubitStateTomography plot reading reduced metrics
   (`qubit_tomo.py:89-100`)**
   - `plot()` read scalar `sx/sy/sz` from `analysis.metrics`, discarding
     multi-prep array data in `analysis.data`.  Changed to prefer
     `analysis.data.get("sx")` (full array) with fallback to
     `analysis.metrics.get("sx")` (scalar mean).

5. **Patch rule deduplication (`patch_rules.py:282-313`)**
   - `WeightRegistrationRule` was redundantly included in `pi_amp` and
     `pulse_train` kinds where it has no effect (those experiments don't
     produce `proposed_patch_ops` metadata).  Removed from both to avoid
     confusing no-op rule invocations.

6. **Missing `resonator_freq` FrequencyRule (`patch_rules.py:292,305`)**
   - `default_patch_rules()` had no rule for `resonator_freq` kind,
     meaning `ResonatorSpectroscopy.analyze()` calibration results were
     silently dropped by the orchestrator.  Added
     `FrequencyRule(element=ro_el, kind="resonator_freq",
     metric_key="f0", field="resonator_freq")` mapped to kind
     `"resonator_freq"`.

7. **Dead `update_calibration` warnings (5 experiments)**
   - `FockResolvedSpectroscopy`, `FockResolvedT1`, `FockResolvedRamsey`,
     `FockResolvedPowerRabi` (all in `cavity/fock.py`) and
     `NumSplittingSpectroscopy` (`cavity/storage.py`) accepted
     `update_calibration=True` but silently ignored it.  Added explicit
     `logger.warning(...)` directing users to the CalibrationOrchestrator.

8. **StorageSpectroscopyCoarse calibration pattern (`cavity/storage.py`)**
   - `StorageSpectroscopyCoarse.analyze()` had no calibration path.
     Added `proposed_patch_ops` metadata (matching `StorageSpectroscopy`
     pattern) so the orchestrator can apply storage frequency patches.

9. **FockResolvedSpectroscopy peak extraction (`cavity/fock.py`)**
   - `analyze()` stored `float(mag.min())` as each Fock frequency, which
     is the minimum signal magnitude rather than the frequency at the
     minimum.  Changed to `float(frequencies[np.argmin(fock_mag)])` to
     extract the actual frequency of the spectroscopic dip.

10. **Dead parameters removed from SPAFluxOptimization2
    (`spa/flux_optimization.py`)**
    - Removed 5 `run()` parameters that were accepted but never used:
      `flux_step`, `spa_gain`, `readout_gain`, `readout_len`,
      `saturation_amp`.  The underlying program builder does not consume
      them.

11. **SNAPOptimization / FockResolvedStateTomography documentation
    (`tomography/wigner_tomo.py`)**
    - Added cross-reference docstring noting that SNAPOptimization uses
      `cQED_programs.SQR_state_tomography` (gate-level control) whereas
      `FockResolvedStateTomography` uses
      `cQED_programs.fock_resolved_state_tomography` (callable
      state-prep).  No code merge: different QUA programs justify
      separate classes.

12. **API_REFERENCE.md v1.8.0 update**
    - Version bumped to 1.8.0, date updated to 2026-02-25.
    - Section 13.4 (Patch Rules): expanded table with `PulseTrainRule`,
      added detailed default rule mapping table showing all 12 kinds.
      Updated `FrequencyRule` to list `resonator_freq` kind.  Updated
      `T1Rule` description with unit heuristic detail.
    - Section 9.1 (SPA): updated `SPAFluxOptimization2` description.

**Files affected:**

- `qubox_v2/experiments/tomography/wigner_tomo.py`
- `qubox_v2/experiments/tomography/qubit_tomo.py`
- `qubox_v2/experiments/cavity/fock.py`
- `qubox_v2/experiments/cavity/storage.py`
- `qubox_v2/experiments/spa/flux_optimization.py`
- `qubox_v2/calibration/patch_rules.py`
- `qubox_v2/docs/API_REFERENCE.md`
- `qubox_v2/docs/CHANGELOG.md`

---

### 2026-02-25 — Readout Pipeline Consistency Audit & Fixes

**Classification: Moderate**

Audited the full readout pipeline (GE Discrimination → Butterfly → CalibrateReadoutFull)
for consistency between legacy `cQED_Experiment` and qubox_v2.  Produced a mapping
document and fixed 4 bugs in the state-handoff path.

**Summary:**

1. **Audit document (inline in this CHANGELOG)**
   - Full Legacy ↔ qubox_v2 pipeline ordering comparison.
   - Policy-object tables: readout discrimination, quality, and state-prep.
   - State-handoff invariant analysis (GE → Butterfly).
   - 4 bugs and 2 mismatches identified and documented.

2. **BUG-R1 — `qbx_readout_state` missing from default dict (`measure.py:148`)**
   - `_ro_disc_params` did not include `qbx_readout_state` in its default keys,
     causing `_apply_defaults()` to silently drop it.  Added
     `"qbx_readout_state": None` to the default dict.

3. **BUG-R2 — `_update_readout_quality` dead code (`measure.py:441–452`)**
   - The `t01`/`t10` transition-probability and `eta_g`/`eta_e` update code
     inside `_update_readout_quality()` was wrapped in a triple-quoted string
     literal (dead code).  Restored the code so butterfly metrics propagate
     to `_ro_quality_params` immediately on `SetMeasureQuality` patch ops.

4. **BUG-R3 — `sync_from_calibration` loses `qbx_readout_state` (`measure.py:455`)**
   - `sync_from_calibration()` overwrites `_ro_disc_params` from CalibrationStore
     but `qbx_readout_state` is a runtime-only hash not stored in CalibStore.
     Added save/restore of `qbx_readout_state` around the sync so Butterfly's
     hash comparison survives calibration commits.

5. **BUG-R4 — Orchestrator swallows sync errors silently (`orchestrator.py:243`)**
   - Bare `except Exception: pass` after `sync_from_calibration()` in
     `apply_patch()` silently discarded errors.  Replaced with
     `_logger.warning(...)` so failures are logged.

**Files affected:**

- `qubox_v2/programs/macros/measure.py`
- `qubox_v2/calibration/orchestrator.py`
- `qubox_v2/docs/CHANGELOG.md` (audit content inline)

---

### 2026-02-25 — Canonical Transition Identity Layer (Phase 1)

**Classification: Major**

Defined and applied the canonical naming / metadata normalization layer for
qubit transition identity (`ge`, `ef`).  All pulse names, calibration records,
and patch rules now use a single source of truth for transition-prefixed names.

**Summary:**

1. **New module: `calibration/transitions.py`**
   - `Transition` enum (`GE`, `EF`), `DEFAULT_TRANSITION`, `TransitionLiteral`.
   - `CANONICAL_REF_PULSES` / `CANONICAL_DERIVED_PULSES` / `ALL_CANONICAL` sets.
   - Legacy alias map: bare names (`x180`, `ref_r180`) → canonical `ge_*`.
   - Public helpers: `resolve_pulse_name()`, `canonical_ref_pulse()`,
     `canonical_derived_pulse()`, `extract_transition()`,
     `strip_transition_prefix()`, `primitive_family()`, `is_canonical()`.

2. **Model metadata: `transition` field**
   - Added `transition: str | None = None` to `PulseCalibration`,
     `PulseTrainResult` (models), `CalibrationResult` (contracts),
     and `PulseSpecEntry` (spec_models).

3. **Calibration store migration**
   - `CalibrationStore` resolves aliases on get/set via `resolve_pulse_name()`.
   - `_migrate_pulse_cal_keys()` auto-renames legacy bare keys on load.

4. **Patch rules canonical defaults**
   - `PiAmpRule`, `DragAlphaRule`, `PulseTrainRule` default to `ge_ref_r180`.
   - All rules resolve target ops through `resolve_pulse_name()`.

5. **cQED_attributes canonical fields**
   - Added `ge_r180_amp`, `ge_rlen`, `ge_rsigma`, `ef_r180_amp`, `ef_rlen`,
     `ef_rsigma` with legacy promotion in `__post_init__`.

6. **Experiment defaults**
   - `DRAGCalibration`, `PowerRabi` default ops updated to canonical names.

7. **Sample data migration**
   - `calibration.json`: keys renamed to `ge_ref_r180`, `ge_sel_ref_r180`
     with `transition: "ge"` field.
   - `cqed_params.json`: added `ge_*` prefixed fields.

8. **Exports**
   - `calibration/__init__.py` exports entire transitions module.

**Files affected:**

- `qubox_v2/calibration/transitions.py` (new)
- `qubox_v2/calibration/models.py`
- `qubox_v2/calibration/contracts.py`
- `qubox_v2/calibration/store.py`
- `qubox_v2/calibration/patch_rules.py`
- `qubox_v2/calibration/__init__.py`
- `qubox_v2/pulses/spec_models.py`
- `qubox_v2/analysis/cQED_attributes.py`
- `qubox_v2/experiments/calibration/gates.py`
- `qubox_v2/experiments/time_domain/rabi.py`
- `samples/post_cavity_sample_A/cooldowns/cd_2025_02_22/config/calibration.json`
- `samples/post_cavity_sample_A/config/cqed_params.json`
- `qubox_v2/docs/CHANGELOG.md`

---

### 2026-02-25 — Transition-Aware Spectroscopy & Frequency Storage (Phase 2)

**Classification: Moderate**

Made the spectroscopy layer and frequency storage contract explicitly
transition-aware using the canonical naming layer from Phase 1.

**Summary:**

1. **`ElementFrequencies.ef_freq` field (`models.py`)**
   - Added `ef_freq: float | None = None` to `ElementFrequencies`.
   - `qubit_freq` remains the legacy/canonical GE slot; `ef_freq` is the
     new canonical EF slot.

2. **`QubitSpectroscopy` transition-aware (`spectroscopy/qubit.py`)**
   - `run()` accepts `transition: str = "ge"` parameter.
   - `analyze()` reads transition from `result.metadata`, routes
     `calibration_kind` and patch path via `_TRANSITION_FREQ_MAP`.
   - GE → `qubit_freq` field, EF → `ef_freq` field.

3. **`QubitSpectroscopyCoarse` transition-aware + bug fix**
   - Added `pulse: str` parameter (was missing — first arg to builder was
     incorrectly `attr.ro_el`, a readout element name, not a pulse op).
   - Added `transition: str = "ge"` parameter.
   - `analyze()` routes via `_TRANSITION_FREQ_MAP` like `QubitSpectroscopy`.

4. **`QubitSpectroscopyEF` canonical cleanup**
   - Hardcoded `"x180"` → configurable `ge_prep_pulse: str = "ge_x180"`.
   - Added `transition="ef"` metadata to run result.
   - `analyze()` now produces `calibration_kind: "ef_freq"` metadata and
     `proposed_patch_ops` targeting `frequencies.<qb_el>.ef_freq`.
   - Emits both `f0` and `f_ef` metrics for compatibility.

5. **`default_patch_rules` EF frequency rule (`patch_rules.py`)**
   - Added `FrequencyRule(element=qb_el, kind="ef_freq", metric_key="f0",
     field="ef_freq")` registered under `"ef_freq"` kind.

6. **Focused tests (`tests/test_transition_spectroscopy.py`)**
   - 17 tests covering: `ElementFrequencies.ef_freq` model, transition
     routing map, `FrequencyRule` for EF, `default_patch_rules` registration,
     and canonical naming defaults.

**Files affected:**

- `qubox_v2/calibration/models.py`
- `qubox_v2/calibration/patch_rules.py`
- `qubox_v2/experiments/spectroscopy/qubit.py`
- `tests/test_transition_spectroscopy.py` (new)
- `qubox_v2/docs/CHANGELOG.md`

---

### 2026-02-26 — Binding-Driven API Redesign (v2.0.0)

**Classification: Major**

Complete architectural refactor replacing implicit element-name coupling
with explicit binding objects throughout the codebase.  This is a
**breaking change** that affects calibration storage, measurement macros,
program builders, sequence macros, and session management.

**What broke:**

- `CalibrationData` schema bumped from v4.0.0 to v5.0.0.  All per-element
  dicts now key by physical channel ID (`ChannelRef.canonical_id`) instead
  of element name strings.  An `alias_index` field provides backward
  compatibility for legacy access patterns.
- `PulseRegistry._RESERVED_OPS` no longer includes `"readout"`.  The
  wildcard `"*"` element-ops mapping no longer auto-registers a `"readout"`
  operation on every element.
- Program builder functions' element-name parameters changed from
  hardcoded defaults (e.g. `qb_el="qubit"`) to `None` with runtime
  resolution from `bindings` when provided.
- `sequence.py` macro defaults similarly changed from hardcoded strings
  to `None` + conditional resolution.

**Migration path:**

1. **Existing code** continues to work unchanged -- all old-style element
   name parameters are still accepted.  When `bindings=None` (the default),
   functions fall back to the original string defaults.
2. **New code** should pass `bindings=session.bindings` to experiments and
   program builders.  Element names are derived from bindings at call time.
3. **Calibration data** is auto-migrated from v4 to v5 on load.  Legacy
   element-name keys continue to resolve through `alias_index`.

**Compatibility shims:**

- `measureMacro` singleton remains fully functional -- existing callsites
  are unaffected.
- `cQED_attributes.ro_el` / `qb_el` / `st_el` remain stored and usable.
  A new `.to_bindings(hw)` method bridges to the binding-driven API.
- `CalibrationStore` accessors accept both physical channel IDs and legacy
  element names transparently via dual-lookup.

**Summary:**

1. **New module: `core/bindings.py`** -- ChannelRef, OutputBinding,
   InputBinding, ReadoutBinding, ExperimentBindings, ConfigBuilder,
   bindings_from_hardware_config(), build_alias_map(), validate_binding().

2. **CalibrationStore updates** -- v5.0.0 schema, alias_index, dual-lookup
   accessors, register_alias(), auto-migration v3->v4->v5.

3. **`measure_with_binding()` free function** -- binding-based drop-in
   replacement for measureMacro.measure().

4. **Session + ExperimentBase** -- .bindings property, invalidate_bindings(),
   auto alias registration.

5. **Preflight** -- bindings validation check #8.

6. **PulseRegistry** -- _RESERVED_OPS cleared, wildcard readout removed.

7. **cQED_attributes** -- to_bindings(hw) method.

8. **ReadoutConfig** -- from_binding(ro) factory.

9. **CalibrationOrchestrator** -- post-patch ReadoutBinding sync.

10. **Program builders + sequence macros** -- optional bindings parameter,
    element-name defaults changed to None + conditional resolution.

**Files affected:**

- `qubox_v2/core/bindings.py` (new)
- `qubox_v2/core/preflight.py`
- `qubox_v2/calibration/models.py`
- `qubox_v2/calibration/store.py`
- `qubox_v2/calibration/orchestrator.py`
- `qubox_v2/programs/macros/measure.py`
- `qubox_v2/programs/macros/sequence.py`
- `qubox_v2/programs/builders/*.py`
- `qubox_v2/experiments/session.py`
- `qubox_v2/experiments/experiment_base.py`
- `qubox_v2/experiments/calibration/readout_config.py`
- `qubox_v2/analysis/cQED_attributes.py`
- `qubox_v2/pulses/pulse_registry.py`
- `qubox_v2/docs/CHANGELOG.md`
- `qubox_v2/docs/API_REFERENCE.md`
- `docs/api_refactor_output_binding_report.md`

---

### 2026-03-01 — Measurement Refactor Kickoff (Stage 0/1)

**Classification: Moderate**

Started the approved refactor away from implicit singleton-only measurement
usage by introducing first-class measurement specification primitives and a
compatibility lowering wrapper. This is the first migration slice and is
non-breaking: existing `measureMacro` behavior is preserved while the new API
is introduced for incremental adoption.

**Summary:**

1. **New module: `programs/measurement.py`**
   - Added immutable `MeasureSpec` and `MeasureGate` dataclasses.
   - Added deterministic snapshot hashing utility (`version_hash`).
   - Added snapshot builders:
     - `build_readout_snapshot_from_macro()`
     - `build_readout_snapshot_from_handle()`
     - `try_build_readout_snapshot_from_macro()` (safe optional capture)
   - Added `emit_measurement_spec(...)` compatibility lowering wrapper that
     routes through current measurement backends while establishing the new
     first-class call shape.

2. **Builder migration start (`programs/builders/time_domain.py`)**
   - `temporal_rabi()` and `power_rabi()` now call
     `emit_measurement_spec(MeasureSpec(kind="iq"), ...)` instead of direct
     `measureMacro.measure(...)`.
   - Readout alignment and output semantics are unchanged.

3. **Build provenance enhancement (`experiments/time_domain/rabi.py`)**
   - `ProgramBuildResult.measure_macro_state` now captures optional readout
     snapshot provenance via `try_build_readout_snapshot_from_macro()` for
     `TemporalRabi` and `PowerRabi`.

4. **Package exposure (`programs/__init__.py`)**
   - Exported `measurement` submodule for discoverability and import
     consistency.

**Files affected:**

- `qubox_v2/programs/measurement.py` (new)
- `qubox_v2/programs/builders/time_domain.py`
- `qubox_v2/experiments/time_domain/rabi.py`
- `qubox_v2/programs/__init__.py`
- `docs/CHANGELOG.md` — This entry

---

### 2026-03-01 — CircuitRunner + Serialization Validation (Simulator-Only)

**Classification: Major**

Implemented an initial Gate/QuantumCircuit/CircuitRunner path and added a
mandatory serialization-based validation workflow that compares legacy and new
compiled QUA scripts for four scoped experiments (Power Rabi, T1, GE
discrimination, Butterfly), without executing live hardware runs.

**Summary:**

1. **New CircuitRunner module (`programs/circuit_runner.py`)**
   - Added first-class abstractions: `Gate`, `QuantumCircuit`, `SweepAxis`,
     `SweepSpec`, `CircuitBuildResult`, and `CircuitRunner`.
   - Added compiler routes for:
     - `power_rabi`
     - `t1`
     - `readout_ge_discrimination`
     - `readout_butterfly`
   - Added serialization helper and snapshot capture for build provenance.

2. **Programs package exposure**
   - Exported `circuit_runner` module via `programs/__init__.py`.

3. **Serialization validation tool (`tools/validate_circuit_runner_serialization.py`)**
   - Added simulator-only compile/serialize comparator.
   - Produces per-experiment legacy/new serialized scripts under:
     `docs/circuit_serialized/*.py`.
   - Generates validation report:
     `docs/circuit_runner_serialization_validation.md`.
   - Uses isolated temporary sample-registry copy for safe, non-destructive
     validation and context compatibility with legacy calibration files.

4. **Validation outcome (current state)**
   - All four scoped experiments currently report **Behaviorally different**
     under strict textual serialization comparison and are marked **REVIEW** in
     the report.
   - No hardware execution was performed in this phase.

**Files affected:**

- `qubox_v2/programs/circuit_runner.py` (new)
- `qubox_v2/programs/__init__.py`
- `tools/validate_circuit_runner_serialization.py` (new)
- `docs/circuit_runner_serialization_validation.md` (new generated report)
- `docs/circuit_serialized/*.py` (new generated serialized artifacts)
- `docs/CHANGELOG.md` — This entry

---

### 2026-03-01 — Serialization Comparator Normalization (Timestamp-Only Diffs)

**Classification: Moderate**

Improved the CircuitRunner validation comparator to normalize known
non-semantic serialization metadata (`# Single QUA script generated at ...`).
This removes false behavioral mismatches caused purely by per-run timestamps in
generated QUA headers.

**Summary:**

1. **Comparator enhancement (`tools/validate_circuit_runner_serialization.py`)**
  - Added `_normalize_script()` to strip generation timestamp header lines.
  - Updated `_diff_scripts()` to classify normalized-equal scripts as:
    `Functionally equivalent with timing notes`.

2. **Validation rerun (same four-scope set)**
  - Power Rabi: PASS (functionally equivalent, timestamp-only diff)
  - T1: PASS (functionally equivalent, timestamp-only diff)
  - Readout GE discrimination: PASS (functionally equivalent, timestamp-only diff)
  - Butterfly measurement: PASS (functionally equivalent, timestamp-only diff)

3. **Report regeneration**
  - Rewrote `docs/circuit_runner_serialization_validation.md` with updated
    per-experiment outcomes and overall `PASS` verdict.

**Files affected:**

- `tools/validate_circuit_runner_serialization.py`
- `docs/circuit_runner_serialization_validation.md`
- `docs/CHANGELOG.md` — This entry

---

### 2026-03-01 — Phase 2 Migration Start: Experiment Build Paths + Hard Serialization Gate

**Classification: Major**

Continued CircuitRunner adoption by migrating production experiment build paths
for `PowerRabi` and `T1Relaxation` to compile via `CircuitRunner` (with
safe fallback to legacy builders), and enforced serialization validation as a
hard gate (`non-PASS` exits with status code 1).

**Summary:**

1. **Experiment-level CircuitRunner integration**
   - `PowerRabi` now supports `use_circuit_runner` in `_build_impl()` / `run()`.
   - `T1Relaxation` now supports `use_circuit_runner` in `_build_impl()` / `run()`.
   - Both default to CircuitRunner path with automatic fallback to legacy
     builder on compile exceptions, preserving runtime compatibility.
   - `ProgramBuildResult.builder_function` now reflects actual compilation
     route (`CircuitRunner.*` vs legacy builder).

2. **Serialization gate enforcement**
   - `tools/validate_circuit_runner_serialization.py` now exits with non-zero
     status when any experiment verdict is not `PASS`, making it CI-friendly
     as a required validation gate.

3. **Validation rerun after migration**
   - Re-ran serialization validation across all four scoped experiments.
   - Current outcome remains `PASS` for all four, with only timestamp-header
     metadata differences.

**Files affected:**

- `qubox_v2/experiments/time_domain/rabi.py`
- `qubox_v2/experiments/time_domain/relaxation.py`
- `tools/validate_circuit_runner_serialization.py`
- `docs/circuit_runner_serialization_validation.md` (regenerated)
- `docs/CHANGELOG.md` — This entry

---

### 2026-03-01 — Phase 2 Readout Run-Path Migration + Serialization Re-Validation

**Classification: Major**

Extended CircuitRunner integration to readout-heavy calibration experiments by
migrating production `run()` compile paths for GE discrimination and Butterfly
measurement (with legacy fallback preserved), then re-ran the serialization
equivalence gate to confirm no behavioral drift.

**Summary:**

1. **Readout experiment run-path migration**
   - `ReadoutGEDiscrimination.run()` now supports `use_circuit_runner` and
     compiles via `CircuitRunner.compile_ge_discrimination(...)` by default.
   - `ReadoutButterflyMeasurement.run()` now supports `use_circuit_runner` and
     compiles via `CircuitRunner.compile_butterfly(...)` by default.
   - Both methods preserve safe fallback to existing legacy builders when
     CircuitRunner compilation raises.

2. **Post-migration validation rerun**
   - Re-ran `tools/validate_circuit_runner_serialization.py` after this patch.
   - Power Rabi: PASS (functionally equivalent with timing notes)
   - T1: PASS (functionally equivalent with timing notes)
   - Readout GE discrimination: PASS (functionally equivalent with timing notes)
   - Butterfly measurement: PASS (functionally equivalent with timing notes)

3. **Report refresh**
   - Regenerated `docs/circuit_runner_serialization_validation.md` with current
     all-PASS outcomes for the four scoped experiments.

**Files affected:**

- `qubox_v2/experiments/calibration/readout.py`
- `tools/validate_circuit_runner_serialization.py` (executed for gate verification)
- `docs/circuit_runner_serialization_validation.md` (regenerated)
- `docs/CHANGELOG.md` — This entry

---

### 2026-03-01 — Readout Build-Protocol Migration (_build_impl + build_program)

**Classification: Major**

Migrated `ReadoutGEDiscrimination` and `ReadoutButterflyMeasurement` to the
v2.2 experiment build protocol by introducing `_build_impl()` return paths with
`ProgramBuildResult`, and making `run()` delegate through `build_program()`.
This aligns readout calibration experiments with the unified build/simulate
architecture while preserving legacy fallback behavior and serialization parity.

**Summary:**

1. **Protocol alignment in readout experiments**
  - Added `_build_impl()` in `ReadoutGEDiscrimination`.
  - Added `_build_impl()` in `ReadoutButterflyMeasurement`.
  - `run()` in both classes now calls `build_program(...)` then `run_program(...)`.

2. **Provenance and execution metadata**
  - Build results now include `builder_function`, `resolved_frequencies`,
    `bindings_snapshot`, and `measure_macro_state` snapshots.
  - GE discrimination build stores `run_program_kwargs` targets for
    deterministic output extraction parity.

3. **Compatibility preserved**
  - CircuitRunner compile path remains default where enabled.
  - Existing legacy `cQED_programs.*` builders remain as safe fallback.

4. **Validation rerun after migration**
  - Re-ran `tools/validate_circuit_runner_serialization.py` after this change.
  - Power Rabi: PASS
  - T1: PASS
  - Readout GE discrimination: PASS
  - Butterfly measurement: PASS

**Files affected:**

- `qubox_v2/experiments/calibration/readout.py`
- `docs/circuit_runner_serialization_validation.md` (regenerated)
- `docs/CHANGELOG.md` — This entry

---

### 2026-03-01 — Experiment Refactor Closure: Full `_build_impl()` Coverage

**Classification: Major**

Completed the refactor sweep so all `ExperimentBase` subclasses now define
`_build_impl()` contracts. Single-program experiments were migrated to the
v2.2 build protocol (`build_program()` + `ProgramBuildResult`), while true
multi-run orchestrators now expose explicit non-support contracts via
`NotImplementedError` in `_build_impl()` and retain run-driven execution.

**Summary:**

1. **Single-program migration completed**
   - Migrated `calibration/reset.py` classes:
     `QubitResetBenchmark`, `ActiveQubitResetBenchmark`,
     `ReadoutLeakageBenchmarking`.
   - Migrated tomography classes:
     `QubitStateTomography`, `FockResolvedStateTomography`,
     `StorageWignerTomography`, `SNAPOptimization`.
   - Migrated gate calibration classes:
     `AllXY`, `DRAGCalibration`.

2. **Orchestrator contract formalization**
   - Added explicit `_build_impl()` non-support contracts for multi-run
     orchestrators in:
     - `calibration/readout.py` (`CalibrateReadoutFull`, `ReadoutAmpLenOpt`)
     - `calibration/gates.py` (`RandomizedBenchmarking`, `PulseTrainCalibration`)
     - `spa/flux_optimization.py` (`SPAFluxOptimization`,
       `SPAFluxOptimization2`, `SPAPumpFrequencyOptimization`)

3. **Global coverage verification**
   - Repository audit now reports:
     `ALL_EXPERIMENT_CLASSES_HAVE__BUILD_IMPL`

4. **Post-refactor serialization validation**
   - Re-ran `tools/validate_circuit_runner_serialization.py`.
   - Power Rabi: PASS
   - T1: PASS
   - Readout GE discrimination: PASS
   - Butterfly measurement: PASS

**Files affected:**

- `qubox_v2/experiments/calibration/reset.py`
- `qubox_v2/experiments/calibration/gates.py`
- `qubox_v2/experiments/calibration/readout.py`
- `qubox_v2/experiments/tomography/qubit_tomo.py`
- `qubox_v2/experiments/tomography/fock_tomo.py`
- `qubox_v2/experiments/tomography/wigner_tomo.py`
- `qubox_v2/experiments/spa/flux_optimization.py`
- `docs/circuit_runner_serialization_validation.md` (regenerated)
- `docs/CHANGELOG.md` — This entry

---

### 2026-03-01 — Gate Tune-Up Framework + Circuit Visualization System (MVP Phase 1)

**Classification: Major**

Implemented the requested Gate Tune-Up extension for `qubox_v2` with
family-based tuning artifacts, compiler-level tuning application hooks,
deterministic gate identity naming, and dual circuit visualization
representations (logical diagram + pulse-level view).

**Summary:**

1. **Gate tuning framework implementation**
   - Added `qubox_v2/programs/gate_tuning.py` with:
     - `GateFamily`
     - `GateTuningRecord`
     - `GateTuningStore`
     - `make_xy_tuning_record()` and default X-family derivation (`x90=0.5*x180`)
   - Added tuning provenance (`record_id`) and deterministic resolution per
     `(target, operation)`.

2. **Circuit abstraction and identity upgrades**
   - Extended `Gate` with `instance_name` and deterministic `resolved_name()`.
   - Added `QuantumCircuit.with_stable_gate_names()`.
   - Implemented deterministic gate naming convention of the form:
     `<GateFamily>_<AngleOrParam>_<Target>_<Index>`.

3. **Visualization APIs (required dual representation)**
   - Implemented `QuantumCircuit.draw_logical(...)`:
     deterministic wire layout, gate boxes, label composition, export support.
   - Implemented `QuantumCircuit.draw_pulses(...)` delegating to runner.
   - Implemented `CircuitRunner.visualize_pulses(...)`:
     - Preferred path: compiled program simulation samples
     - Fallback path: compiled timing-model + pulse registry waveforms
     - Per-element subplot grouping, I/Q overlays, gate-boundary annotations,
       optional zoom and save.

4. **Compiler-level tuning hook integration**
   - `CircuitRunner.compile()` now applies tuning resolution before lowering.
   - `power_rabi` compile path applies tuned amplitude scale to sweep gains and
     records `applied_gain_scale` in build metadata.
   - Added short-circuit helper flow: `make_xy_pair_circuit(...)` and compile
     support (`xy_pair`) for validation scenarios.

5. **Design + validation deliverables generated**
   - Added required design docs:
     - `docs/design_gate_tuning_framework.md`
     - `docs/design_circuit_visualization.md`
   - Added validation tooling:
     - `tools/validate_gate_tuning_visualization.py`
   - Generated required validation docs:
     - `docs/gate_tuning_serialization_validation.md`
     - `docs/circuit_pulse_visualization_validation.md`
   - Generated serialization artifacts:
     - `docs/circuit_tuning_serialized/*.py`
   - Generated pulse figures:
     - `docs/figures/circuit_pulses/*.png`

6. **Regression and compatibility verification**
   - Re-ran existing serialization parity gate:
     `tools/validate_circuit_runner_serialization.py`.
   - Outcomes remain PASS for Power Rabi, T1, Readout GE discrimination,
     and Butterfly.

**Files affected:**

- `qubox_v2/programs/gate_tuning.py` (new)
- `qubox_v2/programs/circuit_runner.py`
- `qubox_v2/programs/__init__.py`
- `tools/validate_gate_tuning_visualization.py` (new)
- `docs/design_gate_tuning_framework.md` (new)
- `docs/design_circuit_visualization.md` (new)
- `docs/gate_tuning_serialization_validation.md` (generated)
- `docs/circuit_pulse_visualization_validation.md` (generated)
- `docs/circuit_tuning_serialized/*.py` (generated)
- `docs/figures/circuit_pulses/*.png` (generated)
- `docs/circuit_runner_serialization_validation.md` (regenerated)
- `docs/CHANGELOG.md` — This entry

---

### 2026-03-01 — Orchestrator Refactor: Explicit Pipeline Build Plans

**Classification: Moderate**

Added explicit, non-invasive planning APIs to orchestrator-style readout
experiments so their execution flow is introspectable and refactor-aligned
without forcing a single-program `_build_impl()` model where it does not fit.

**Summary:**

1. **`CalibrateReadoutFull.build_plan(...)`**
  - Added a configuration-resolved pipeline planner that returns structured
    step metadata for weights optimization and iterative GE+Butterfly phases.
  - Planner validates and resolves the same effective configuration contract
    as `run()`, but performs no QUA build or execution.

2. **`ReadoutAmpLenOpt.build_plan(...)`**
  - Added a 2-D scan planner returning resolved sweep axes, total grid size,
    and delegated sub-experiment execution metadata.

3. **Behavior preserved**
  - No runtime behavior change to `run()` in either orchestrator class.
  - Existing execution remains run-driven and multi-program where appropriate.

4. **Post-change validation rerun**
  - Re-ran `tools/validate_circuit_runner_serialization.py`.
  - Power Rabi: PASS
  - T1: PASS
  - Readout GE discrimination: PASS
  - Butterfly measurement: PASS

**Files affected:**

- `qubox_v2/experiments/calibration/readout.py`
- `docs/circuit_runner_serialization_validation.md` (regenerated)
- `docs/CHANGELOG.md` — This entry

---

### 2026-03-01 — Readout Protocol Closure: Weights Optimization Migration

**Classification: Major**

Completed the next readout refactor slice by migrating
`ReadoutWeightsOptimization` to the unified v2.2 build protocol while
retaining existing algorithmic behavior and output semantics.

**Summary:**

1. **`ReadoutWeightsOptimization` build migration**
  - Added `_build_impl()` returning `ProgramBuildResult`.
  - Updated `run()` to delegate via `build_program()` and execute with
    `run_program(...)`.
  - Reused `ReadoutGEIntegratedTrace.build_program(...)` internally to avoid
    duplicating trace-construction logic.

2. **Behavior and provenance preservation**
  - Kept existing run-parameter side effects used by `analyze()`.
  - Preserved output artifact save path (`readoutWeightsOpt`).
  - Added build provenance (`builder_function`, snapshots, resolved frequencies).

3. **Intentional non-migration in this slice**
  - `CalibrateReadoutFull` and `ReadoutAmpLenOpt` remain orchestrator-style
    multi-run workflows (not single-program build artifacts), so they are
    intentionally kept as `run()`-driven controllers.

4. **Validation rerun after migration**
  - Re-ran `tools/validate_circuit_runner_serialization.py`.
  - Power Rabi: PASS
  - T1: PASS
  - Readout GE discrimination: PASS
  - Butterfly measurement: PASS

**Files affected:**

- `qubox_v2/experiments/calibration/readout.py`
- `docs/circuit_runner_serialization_validation.md` (regenerated)
- `docs/CHANGELOG.md` — This entry

---

### 2026-03-01 — Readout Protocol Expansion: IQBlob/RawTrace/IntegratedTrace

**Classification: Major**

Expanded the v2.2 build-protocol migration in readout calibration by moving
three additional classes to `_build_impl()` + `build_program()` execution flow:
`IQBlob`, `ReadoutGERawTrace`, and `ReadoutGEIntegratedTrace`.

**Summary:**

1. **Unified build protocol adoption**
   - Added `_build_impl()` to `IQBlob` and updated `run()` to delegate via
     `build_program()`.
   - Added `_build_impl()` to `ReadoutGERawTrace` and updated `run()` to
     delegate via `build_program()`.
   - Added `_build_impl()` to `ReadoutGEIntegratedTrace` and updated `run()`
     to delegate via `build_program()`.

2. **Program provenance and frequency resolution**
   - Added `ProgramBuildResult` payloads with resolved frequencies,
     `builder_function`, `bindings_snapshot`, and `measure_macro_state`.
   - Preserved legacy output shaping through `run_program_kwargs` for target
     mapping and simulation processing flags where applicable.

3. **Legacy behavior parity preserved**
   - Kept integrated-trace measureMacro push/restore and custom post-process
     closure logic unchanged in semantics.

4. **Validation rerun after migration**
   - Re-ran `tools/validate_circuit_runner_serialization.py` post-change.
   - Power Rabi: PASS
   - T1: PASS
   - Readout GE discrimination: PASS
   - Butterfly measurement: PASS

**Files affected:**

- `qubox_v2/experiments/calibration/readout.py`
- `docs/circuit_runner_serialization_validation.md` (regenerated)
- `docs/CHANGELOG.md` — This entry
---

### 2026-03-03 â€” Gate/Protocol/Circuit Hardening: Post-Processing Split, Honest Display, Schema Validation

**Classification: Moderate**

Hardened the new gate-driven circuit pipeline so compile-time behavior,
analysis-time behavior, display semantics, and OPX cluster guard behavior are
explicitly separated and regression-locked.

**Summary:**

1. **State derivation moved out of compilation**
   - `compile_v2` no longer derives boolean state inside QUA lowering.
   - Measurement compilation remains IQ-only.
   - Resolved `StateRule` metadata is now attached as post-processing via
     `ProgramBuildResult.processors`.
   - Added `qubox_v2/programs/circuit_postprocess.py` to apply
     `derive_state()` after execution.

2. **Active-reset display and branching behavior hardened**
   - Analysis-only active reset is now labeled explicitly in diagram text and
     block metadata.
   - Text diagrams now include explicit analysis sections describing
     `MeasureIQ -> derive_state(...) -> external/next-shot conditional action`.
   - Real-time branch requests remain visible in the IR/display, but
     `compile_v2` now raises a loud error instead of silently pretending to
     lower post-processed state into QUA branching.

3. **Measurement schema invariants added**
   - Added `MeasurementSchema.validate()`.
   - Enforced unique record keys, required IQ streams, valid shapes and
     aggregates, namespaced output uniqueness, and truthful state-output claims.
   - Measurement outputs are now saved with deterministic namespaced keys such
     as `ramsey_readout.I` and `active_reset_m0.Q`.

4. **Cluster guard audit completed**
   - Confirmed legacy cluster selection remains in the legacy session / QMM
     construction path and was not modified.
   - Confirmed new guarded circuit execution keeps cluster selection local to
     `qubox_v2/programs/circuit_execution.py`.
   - `Cluster_2` requests hard-fail immediately in the guarded runner tests.

5. **Documentation and reporting added**
   - Updated `architecture_design.md` to document:
     - IQ-only compilation contract
     - analysis-time state derivation
     - measurement schema validation
     - legacy versus new cluster selection locations
   - Added `test_case_report.md` summarizing the feature-area tests and run
     commands.

6. **Golden and regression coverage expanded**
   - Updated gate-architecture goldens for namespaced stream outputs and
     analysis-only active-reset snapshots.
   - Added tests for:
     - schema validation failures
     - post-processing state derivation
     - loud failure on unsupported real-time derived-state branching
     - Cluster_2 hard-fail behavior

**Files affected:**

- `qubox_v2/programs/circuit_runner.py`
- `qubox_v2/programs/circuit_protocols.py`
- `qubox_v2/programs/circuit_compiler.py`
- `qubox_v2/programs/circuit_display.py`
- `qubox_v2/programs/circuit_postprocess.py` (new)
- `tests/gate_architecture/conftest.py`
- `tests/gate_architecture/test_gate_architecture.py`
- `tests/gate_architecture/golden/*`
- `architecture_design.md`
- `test_case_report.md` (new)
- `docs/CHANGELOG.md` â€” This entry

---

### 2026-03-13 - Architecture Refactor Proposal Documentation

**Classification: Minor**

Added a dedicated architecture review and refactor proposal document for the
qubox experiment framework. The document audits the current experiment,
calibration, compilation, and analysis architecture, critiques the current
usability from a cQED workflow perspective, proposes a target design centered
on experiment templates plus sequence and sweep primitives, and outlines a
staged migration roadmap.

**Files affected:**

- `docs/qubox_experiment_framework_refactor_proposal.md`
- `past_prompt/2026-03-13_03-59-01_architecture_review_qubox_framework.md`
- `docs/CHANGELOG.md` - This entry

---

### 2026-03-13 - qubox Canonical Package Refactor

**Classification: Major**

Introduced a new canonical `qubox` package on top of the existing repository,
with a Session-first public API, experiment-template namespaces, sequence and
QuantumCircuit authoring surfaces, first-class sweep and acquisition objects,
a QM runtime adapter, calibration snapshots and proposals, migration
documentation, a root README, and public API tests. The older `qubox_v2`
package remains available as a compatibility layer while the backend migration
continues.

**Files affected:**

- `README.md`
- `API_REFERENCE.md`
- `docs/qubox_architecture.md`
- `docs/qubox_migration_guide.md`
- `qubox/__init__.py`
- `qubox/session/*`
- `qubox/experiments/*`
- `qubox/sequence/*`
- `qubox/circuit/*`
- `qubox/operations/*`
- `qubox/calibration/*`
- `qubox/backends/*`
- `qubox/data/*`
- `qubox/analysis/*`
- `qubox/compat/__init__.py`
- `tests/test_qubox_public_api.py`
- `qubox_v2/pyproject.toml`
- `docs/CHANGELOG.md` - This entry

---

### 2026-04-01 — measureMacro Decoupling: Phase 0–3 (ReadoutHandle + Builder + Experiment Migration)

**Classification: Major**

**Summary:**

Decoupled all QUA builder functions and experiment subclasses from the
`measureMacro` singleton by introducing `ReadoutHandle` as an explicit,
immutable readout configuration carrier. This is Phase 0–3 of the
measureMacro refactoring plan (`docs/measureMacro_refactoring_plan.md`).

**What changed:**

1. **`ReadoutHandle` enhanced** (`qubox/core/bindings.py`) — Added `gain`,
   `demod_weight_sets` fields, `threshold` property shortcut, and
   `from_measure_macro()` factory method that bridges from the singleton.
2. **`emit_measurement()` rewritten** (`qubox/programs/macros/measure.py`) —
   New pure function with full parity to `measureMacro.measure()`: supports
   `with_state`, `axis` (tomography), `gain`, `adc_stream`, `targets`, and
   single-variable return when `num_out==1`.
3. **`emit_measurement_spec()` updated** (`qubox/programs/measurement.py`) —
   Accepts optional `readout` parameter; when provided, dispatches to
   `emit_measurement()` instead of `measureMacro.measure()`.
4. **`ExperimentBase.readout_handle` property** added
   (`qubox/experiments/experiment_base.py`) — Calls
   `ReadoutHandle.from_measure_macro()` to provide experiments a handle.
5. **ALL 8 builder files migrated** (36 builder functions total):
   - `readout.py` (8), `time_domain.py` (10), `spectroscopy.py` (6),
     `calibration.py` (5), `cavity.py` (11), `simulation.py` (1),
     `utility.py` (1), `tomography.py` (2)
   - Each now requires `readout: "ReadoutHandle"` as a parameter.
   - All `measureMacro.measure(...)` → `emit_measurement(readout, ...)`.
   - All `measureMacro.active_element()` → `readout.element`.
   - All `measureMacro._ro_disc_params.get("threshold")` → `readout.threshold`.
6. **`sequence.py` macros migrated** (5 methods): `qubit_state_tomography`,
   `num_splitting_spectroscopy`, `fock_resolved_spectroscopy`, `prepare_state`,
   `post_select`.
7. **ALL 15 experiment subclass files updated** — Each `build_program()` now
   passes `readout=self.readout_handle` to its builder function calls.
8. **`circuit_runner.py` updated** — 5 builder calls now pass
   `readout=self.session.readout_handle()`.
9. **`circuit_compiler.py` unchanged** — Uses `measureMacro` fallback path
   in `emit_measurement_spec(readout=None)`, left for future phase.

**Not breaking (no backward compat needed per user direction):**
- `measureMacro` singleton is still used internally by `ReadoutHandle.from_measure_macro()`
  and as fallback in `emit_measurement_spec(readout=None)`.
- Slimming `measureMacro` is deferred to Phase 5.

**Validation:**

- All 24 experiment simulation tests: **23 PASS, 1 SKIP, 0 FAIL** (matches
  pre-migration baseline).
- `import qubox` — clean, no syntax errors.

**Files modified:**

- `qubox/core/bindings.py` — ReadoutHandle enhanced + corruption fix
- `qubox/programs/macros/measure.py` — `emit_measurement()` rewritten
- `qubox/programs/measurement.py` — `emit_measurement_spec()` updated
- `qubox/experiments/experiment_base.py` — `readout_handle` property added
- `qubox/programs/builders/readout.py` — 8 functions migrated
- `qubox/programs/builders/time_domain.py` — 10 functions migrated
- `qubox/programs/builders/spectroscopy.py` — 6 functions migrated
- `qubox/programs/builders/calibration.py` — 5 functions migrated
- `qubox/programs/builders/cavity.py` — 11 functions migrated
- `qubox/programs/builders/simulation.py` — 1 function migrated
- `qubox/programs/builders/utility.py` — 1 function migrated
- `qubox/programs/builders/tomography.py` — 2 functions migrated
- `qubox/programs/macros/sequence.py` — 5 macro methods migrated
- `qubox/experiments/time_domain/rabi.py` — readout= wired
- `qubox/experiments/time_domain/relaxation.py` — readout= wired
- `qubox/experiments/time_domain/coherence.py` — readout= wired
- `qubox/experiments/time_domain/chevron.py` — readout= wired
- `qubox/experiments/spectroscopy/resonator.py` — readout= wired
- `qubox/experiments/spectroscopy/qubit.py` — readout= wired
- `qubox/experiments/calibration/readout.py` — readout= wired
- `qubox/experiments/calibration/reset.py` — readout= wired
- `qubox/experiments/calibration/gates.py` — readout= wired
- `qubox/experiments/tomography/qubit_tomo.py` — readout= wired
- `qubox/experiments/tomography/fock_tomo.py` — readout= wired
- `qubox/experiments/tomography/wigner_tomo.py` — readout= wired
- `qubox/experiments/cavity/storage.py` — readout= wired
- `qubox/experiments/cavity/fock.py` — readout= wired
- `qubox/experiments/spa/flux_optimization.py` — readout= wired
- `qubox/programs/circuit_runner.py` — readout= wired
- `docs/CHANGELOG.md` — this entry
