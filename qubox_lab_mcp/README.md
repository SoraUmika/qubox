# qubox_lab_mcp

Read-mostly MCP server for local `qubox` / cQED research workflows.

## Goals
- Safe repository and notebook archaeology
- Calibration/config inspection and diffing
- Generic decomposition artifact summaries
- Experiment artifact directory summaries
- No live hardware control
- No arbitrary shell execution
- No write tools in v1

## Implemented capabilities

### Resources
- `qubox://config`
- `qubox://survey`
- `repo://file/{path}`
- `notebook://file/{path}`
- `json://file/{path}`
- `decomposition://file/{path}`
- `run://summary/{path}`

### Tools
- `read_file`
- `search_repo`
- `find_symbol`
- `trace_references`
- `list_directory`
- `read_notebook`
- `find_notebook_cells`
- `extract_notebook_cell`
- `summarize_notebook_workflow`
- `load_json`
- `compare_json_files`
- `summarize_calibration`
- `validate_json_schema`
- `load_decomposition`
- `summarize_gate_sequence`
- `flag_parameter_issues`
- `estimate_sequence_metadata`
- `summarize_run_directory`
- `list_generated_figures`
- `find_result_files`
- `compare_python_implementations`
- `trace_gate_usage`
- `extract_experiment_entrypoints`
- `summarize_waveform_conventions`
- `generate_refactor_report`

### Prompts
- `trace_gate_usage_prompt`
- `compare_calibrations_prompt`
- `notebook_archaeology_prompt`

## Installation

### Minimal package install
Install the MCP SDK alongside the repository package:

```bash
pip install "mcp[cli]"
pip install -e .
```

### Optional root configuration
Set explicit roots if you want to restrict access:

```powershell
$env:QUBOX_MCP_ROOTS = "E:\qubox"
```

Multiple roots can be separated with `;` on Windows.

## Running the server

### STDIO
```bash
python -m qubox_lab_mcp.server
```

### Streamable HTTP
```bash
python -m qubox_lab_mcp.server --transport streamable-http --host 127.0.0.1 --port 8000
```

## Example MCP client configuration

### Claude Desktop / compatible JSON config
```json
{
  "mcpServers": {
    "qubox-lab": {
      "command": "E:/qubox/.venv/Scripts/python.exe",
      "args": ["-m", "qubox_lab_mcp.server"],
      "env": {
        "QUBOX_MCP_ROOTS": "E:/qubox"
      }
    }
  }
}
```

## Example prompts for an AI assistant
- Find every place `include_unselective` is used and summarize refactor risk.
- Open `notebooks/post_cavity_experiment_context.ipynb`, find storage tomography cells, and summarize the workflow.
- Compare two calibration JSON files and highlight changes in `chi`, `chi2`, `Kerr`, and pulse references.
- Load this decomposition JSON, list the ordered gates, and flag suspicious `SQR` `theta` values.
- Summarize `samples/post_cavity_sample_A/cooldowns/cd_2025_02_22/artifacts` and list generated figures.

## Safety model
- Allowed-root enforcement through a central policy layer
- Blocked excluded paths such as `.git` and `.venv`
- Binary-file rejection
- File-size and result-count limits
- Read-only scope in v1
- Heuristic secret redaction for obvious inline credentials

## Tests
Run:

```bash
python -m unittest discover -s qubox_lab_mcp/tests -v
```

## Next additions for Phase 2
- Schema-aware calibration validators using existing `qubox` models when available
- Better decomposition-schema adapters for actual gate artifact corpora
- Offline simulation wrappers for safe local validation
- Richer report generators and compatibility impact summaries
