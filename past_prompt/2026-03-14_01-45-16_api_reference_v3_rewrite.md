# Prompt Log: API_REFERENCE.md v3.0.0 Rewrite

**Date**: 2026-03-14 01:45
**Task**: Deep code-driven refresh of API_REFERENCE.md

## Request

User requested a comprehensive, code-driven rewrite of `API_REFERENCE.md`
so that it becomes the canonical source of truth for the current `qubox`
v3.0.0 public API, replacing the stale `qubox_v2`-based documentation
(4681 lines).

Key requirements:
- Treat code as source of truth, not the old document
- Update all `qubox_v2` → `qubox` import paths
- Focus on public API, not internal clutter
- Cover: Overview, Package Architecture, Main User Workflow, Public Entry
  Points, Sessions, Experiments, Calibration/Patch, Results/Artifacts,
  Analysis, Examples
- Audit passes: stale references, signature correctness, notebook
  consistency, terminology consistency

## Approach

1. Read README.md and AGENTS.md for project context
2. Explored full `qubox/` package structure (all subdirectories)
3. Read every implementation file in `qubox/`:
   - `__init__.py` (14 public exports, v3.0.0)
   - `session/session.py` (Session class, all methods and properties)
   - `sequence/models.py` (Operation, Condition, Sequence)
   - `sequence/sweeps.py` (SweepAxis, SweepPlan, SweepFactory)
   - `sequence/acquisition.py` (AcquisitionSpec, AcquisitionFactory)
   - `operations/library.py` (OperationLibrary, 11 semantic ops)
   - `circuit/models.py` (QuantumGate, QuantumCircuit)
   - `data/models.py` (ExecutionRequest, ExperimentResult)
   - `calibration/models.py` (CalibrationSnapshot, CalibrationProposal)
   - `analysis/pipelines.py` (run_named_pipeline)
   - `experiments/templates/library.py` (ExperimentLibrary)
   - `experiments/workflows/library.py` (WorkflowLibrary)
   - `backends/qm/runtime.py` (QMRuntime, 5 template adapters)
   - `backends/qm/lowering.py` (lower_to_legacy_circuit)
   - `compat/notebook.py` (60+ lazy re-exports)
   - `examples/quickstart.py`
4. Read `qubox_tools/__init__.py` for analysis toolkit exports
5. Inspected tutorial notebook for actual usage patterns
6. Read and analyzed full old API_REFERENCE.md (4681 lines, 28 sections)
7. Composed complete new API_REFERENCE.md (1443 lines, 21 sections + 3 appendices)

## Result

New `API_REFERENCE.md` created (1443 lines) covering:
- 21 main sections + 3 appendices
- All public API surfaces documented from code
- Session lifecycle, Sequence IR, Sweep/Acquisition factories
- Operation library with all 11 operation types
- Circuit IR, Experiment templates (5), Workflow system
- Execution/Results, Calibration proposal flow
- QM backend runtime and lowering details
- Compatibility layer (60+ re-exports documented)
- qubox_tools analysis toolkit
- Legacy internals reference
- 5 usage examples (template, custom seq, custom circuit, notebook compat, analysis)
- Migration guide appendix (qubox_v2 → qubox)
- Known gaps and inconsistencies section (6 items documented)

## Files Changed

- `API_REFERENCE.md`: Replaced (4681 lines → 1443 lines)

## Known Issues Documented

1. README.md still references qubox_v2 as active framework
2. Only 5 of 30+ experiments have QMRuntime template adapters
3. qubox.compat.notebook references qubox_v2 (not qubox_v2_legacy) internally
4. SweepAxis center resolution happens at runtime, not construction
5. Custom experiment sweep integration incomplete (no QUA loop driving)
6. Analysis pipelines are basic; sophisticated analysis requires qubox_tools
