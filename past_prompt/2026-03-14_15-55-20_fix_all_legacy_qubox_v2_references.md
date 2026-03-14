# Fix All Legacy qubox_v2 References

**Date**: 2026-03-14 15:55:20  
**Task**: Migrate all `qubox_v2` references across the entire codebase to use `qubox` (user-facing) and `qubox_v2_legacy` (internal runtime)

## Prompt / Request

> "please fix all the legacy issue, we will use 'qubox' from now on and will eventually remove qubox_v2"

## Context

- `qubox` v3.0.0 is the canonical user-facing package
- `qubox_v2_legacy` is the internal runtime backend (actual directory on disk)
- `qubox_tools` is the analysis toolkit
- There is NO `qubox_v2` directory — only `qubox_v2_legacy/`
- The compat layer (`qubox.compat.notebook`) uses `importlib.import_module()` to lazy-import from `qubox_v2_legacy`

## Changes Made

### Code Files (import paths → `qubox_v2_legacy`)

| File | Changes |
|------|---------|
| `qubox/compat/notebook.py` | All 62 `_ATTR_MAP` entries, `_MODULE_MAP` entries, docstring |
| `qubox/compat/__init__.py` | `LEGACY_PACKAGE = "qubox_v2_legacy"`, docstring |
| `qubox/__init__.py` | Docstring updated |
| `qubox_tools/__init__.py` | Docstring updated |
| `qubox_tools/compat/__init__.py` | Docstring updated |
| `qubox_tools/compat/legacy_analysis.py` | All 16 `LEGACY_ANALYSIS_MAP` keys |
| `qubox_tools/fitting/calibration.py` | File header + docstring |
| `qubox_tools/fitting/pulse_train.py` | File header + docstring |
| `qubox_v2_legacy/__init__.py` | Header, description, NOTE comment |
| `tests/gate_architecture/conftest.py` | ~30 references (pkg_root, sys.modules, importlib calls) |

### Tool Files

| File | Changes |
|------|---------|
| `tools/analyze_imports.py` | 8 refs: PACKAGE_ROOT path, docstrings, subsystem checks |
| `tools/build_context_notebook.py` | 34 refs: all import statements in generated cells |
| `tools/generate_codebase_graphs.py` | 5 refs: SVG title strings |
| `tools/validate_notebooks.py` | 2 refs: HARDWARE_MARKERS tuple |

### Documentation and Config

| File | Changes |
|------|---------|
| `README.md` | Full rewrite: `qubox` as canonical, new import examples |
| `API_REFERENCE.md` | Sections 21.1 and 21.3 updated (known gaps resolved) |
| `.github/copilot-instructions.md` | Title, architecture link, lint command |
| `.github/instructions/*.md` (3 files) | `applyTo` paths, test commands |
| `.github/skills/**` (8 files) | All skill references |
| `.github/WORKFLOW_BLUEPRINT.md` | Directory tree reference |
| `qubox_lab_mcp/README.md` | Model reference |
| `qubox_lab_mcp/resources/repo_resources.py` | Source code path note |

### Generated / Architecture Files

| File | Changes |
|------|---------|
| `docs/architecture_review.md` | 10 refs updated |
| `docs/architecture/centrality_metrics.json` | 30 refs updated |
| `docs/architecture/module_edges.json` | 1455 refs updated |
| `docs/architecture/*.svg` (4 files) | SVG title strings |
| `docs/codebase_graph_survey.md` | 5 refs |
| `docs/gate_architecture_review.md` | 6 refs |
| `docs/qubox_architecture.md` | 1 ref |
| `docs/qubox_experiment_framework_refactor_proposal.md` | 4 refs |
| `docs/qubox_lab_mcp_design.md` | 3 refs |
| `docs/qubox_migration_guide.md` | 6 refs |
| `docs/qubox_refactor_verification.md` | 9 refs |
| `docs/qubox_tools_analysis_split.md` | 21 refs |
| `SURVEY.md` | 7 refs |

### Deliberately Preserved

| File | Reason |
|------|--------|
| `docs/CHANGELOG.md` | Historical log — title updated with migration note; 191 historical entries left as-is |
| `claude_report.md` | Historical audit report |
| `API_REFERENCE.md` migration table | Documents old → new import paths (12 remaining refs) |
| `past_prompt/` | Prior prompt logs |

## Verification

- `import qubox` → OK (v3.0.0)
- `import qubox_v2_legacy` → OK (v2.0.0)
- `import qubox_tools` → OK
- `from qubox.compat import LEGACY_PACKAGE` → `"qubox_v2_legacy"`
- Final scan: 0 stray `qubox_v2` in active code (only legitimate historical mentions in API_REFERENCE.md migration guide and claude_report.md)

## Total Files Modified

~45 files, ~1700+ individual reference updates
