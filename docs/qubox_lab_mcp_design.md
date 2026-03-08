# qubox_lab_mcp — Phase 0 Design Note

## Workspace survey

### Observed repository structure
- Primary source code: `qubox_v2/`
- Top-level architecture and API references: `README.md`, `API_REFERENCE.md`, `ARCHITECTURE.md`, `SURVEY.md`
- Legacy / operational notebooks: `notebooks/`
- Context-mode sample registry and cooldown artifacts: `samples/post_cavity_sample_A/`
- Existing schema and validation logic: `qubox_v2/verification/schema_checks.py`
- Tests already present: `qubox_v2/tests/`, `tests/gate_architecture/`

### Observed naming and data conventions
- Sample-level config appears under `samples/<sample_id>/config/`
  - `hardware.json`
  - `cqed_params.json`
  - `devices.json`
- Cooldown-level config appears under `samples/<sample_id>/cooldowns/<cooldown_id>/config/`
  - `calibration.json`
  - `measureConfig.json`
  - `pulses.json`
- Artifact directories appear under `samples/<sample_id>/cooldowns/<cooldown_id>/artifacts/`
- Notebooks are used as authoritative workflow records and commonly import `SessionManager`, calibration experiments, tomography, and storage workflows.
- Gate / waveform themes found in code include `SQR`, `SNAP`, `Displacement`, and `QubitRotation`.

### Gaps and implications
- No clear decomposition JSON corpus is checked into the workspace, so decomposition support should be schema-tolerant and heuristic-driven rather than tightly coupled to one artifact format.
- The first implementation should prioritize code archaeology, notebook archaeology, calibration/config inspection, and artifact directory summarization.

## Proposed MCP server layout

```text
qubox_lab_mcp/
  server.py
  config.py
  errors.py
  services.py
  prompts.py
  models/
    results.py
  adapters/
    filesystem_adapter.py
    notebook_adapter.py
    python_index_adapter.py
    json_adapter.py
    decomposition_adapter.py
    run_adapter.py
  policies/
    path_policy.py
    safety_policy.py
  resources/
    repo_resources.py
    notebook_resources.py
    json_resources.py
    decomposition_resources.py
    run_resources.py
  tools/
    repo_tools.py
    notebook_tools.py
    json_tools.py
    decomposition_tools.py
    run_tools.py
    report_tools.py
  tests/
```

## Candidate resources
- `qubox://config` — allowed roots, limits, exclusions
- `qubox://survey` — compact repository survey for AI context bootstrap
- `repo://file/{path}` — bounded text file access
- `notebook://file/{path}` — notebook summary resource
- `json://file/{path}` — JSON resource access
- `decomposition://file/{path}` — normalized decomposition artifact view
- `run://summary/{path}` — run directory summary

## Candidate tools

### Repository / code tools
- `read_file`
- `search_repo`
- `find_symbol`
- `trace_references`
- `list_directory`
- `compare_python_implementations`
- `trace_gate_usage`
- `extract_experiment_entrypoints`
- `summarize_waveform_conventions`

### Notebook tools
- `read_notebook`
- `find_notebook_cells`
- `extract_notebook_cell`
- `summarize_notebook_workflow`

### JSON / calibration tools
- `load_json`
- `compare_json_files`
- `summarize_calibration`
- `validate_json_schema`

### Decomposition / gate artifact tools
- `load_decomposition`
- `summarize_gate_sequence`
- `flag_parameter_issues`
- `estimate_sequence_metadata`

### Experiment artifact tools
- `summarize_run_directory`
- `list_generated_figures`
- `find_result_files`

## Path safety model
- Central `PathPolicy` resolves all user paths.
- Only configured roots are readable.
- Relative paths resolve against allowed roots.
- Absolute paths outside allowed roots are rejected.
- Excluded locations such as `.git`, `.venv`, and `__pycache__` are blocked.
- File access is size-limited and binary-rejected.
- Text responses pass through simple redaction for obvious secrets.

## Data model assumptions
- Files are local and UTF-8 text unless detected otherwise.
- Notebook cells follow standard `.ipynb` JSON structure.
- Calibration/config files are JSON objects, commonly with `version`, `context`, `cqed_params`, and pulse-related sections.
- Decomposition artifacts will likely encode ordered steps using keys such as `gates`, `sequence`, `steps`, or `operations`.
- Run directories may contain figures, notebooks, JSONs, logs, and generated snapshots; exhaustive parsing is intentionally avoided in v1.

## Risks and edge cases
- Large generated JSON or waveform files may exceed default limits.
- Some legacy notebooks may contain unusual or partially corrupted cell metadata.
- Python symbol lookup is best-effort and static; dynamic imports and metaprogramming are out of scope.
- Decomposition schemas may drift; heuristics should fail clearly instead of silently inventing structure.
- Secret redaction is heuristic and should be treated as defense-in-depth, not formal secret management.

## Recommended minimal first implementation
1. Path policy + safety policy
2. Filesystem adapter for read/list/search
3. Notebook adapter for archaeology workflows
4. JSON adapter for calibration/config inspection and diffing
5. Generic decomposition adapter
6. Run directory summarization adapter
7. FastMCP server exposing a conservative resource/tool surface
8. Focused tests for safety and parsing behavior

This is sufficient for practical research tasks like symbol tracing, notebook archaeology, calibration comparison, and artifact inspection while remaining read-mostly and extensible.
