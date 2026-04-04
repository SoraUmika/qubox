# QuBox Development Workflow Blueprint
## Skills + MCP Integration Plan

---

## 1. The Three Skills

### Skill 1: `codebase-refactor-reviewer`

| Field | Detail |
|-------|--------|
| **Purpose** | Systematically review code refactors for correctness, contract compliance, and architectural consistency |
| **Invoke when** | Before merging refactor branches, after restructuring modules, when changing base classes or Pydantic models |
| **Workflow** | Scope change → Contract compliance check → Dependency impact analysis → Test coverage check → Risk assessment → Generate report |
| **Input** | List of changed files, branch name, or refactor description |
| **Output** | Structured markdown report with risk level (LOW/MEDIUM/HIGH/CRITICAL) and actionable recommendations |
| **Bundled resources** | Module map (architecture boundaries), test map (module→test mapping), contract checklist (P0–P3 invariants) |

**Invoke**: Type `/codebase-refactor-reviewer` in Copilot Chat, or the agent will auto-load it when it detects refactoring context.

### Skill 2: `calibration-experiment-audit`

| Field | Detail |
|-------|--------|
| **Purpose** | Trace and verify the full lifecycle of experiments and calibration flows — detect silent failures, contract violations, data flow gaps |
| **Invoke when** | Auditing experiment classes, debugging stale calibration data, verifying new experiment subclasses, checking cQED parameter propagation |
| **Workflow** | Identify experiment → Trace data flow (run→analyze→patch→apply) → FitResult contract audit → Patch rule validation → Cross-experiment consistency → Generate report |
| **Input** | Experiment class name, calibration flow description, or failure symptom |
| **Output** | Structured audit report with lifecycle trace, contract pass/fail, patch rule table, and recommendations |
| **Bundled resources** | Audit checklist (per-experiment verification), parameter flow map (cQED calibration dependencies) |

**Invoke**: `/calibration-experiment-audit` — or auto-detected when discussing calibration/experiment logic.

### Skill 3: `research-artifact-builder`

| Field | Detail |
|-------|--------|
| **Purpose** | Generate documentation artifacts synchronized with code — README, API docs, changelogs, LaTeX writeups, experiment reports |
| **Invoke when** | After completing features/refactors, preparing results for publication, updating docs, generating CHANGELOG entries |
| **Workflow** | Identify changes → Extract API signatures → Generate from template → Validate cross-references |
| **Input** | Description of what changed, experiment name + results, or version number |
| **Output** | Ready-to-use markdown (for docs) or compilable LaTeX (for Overleaf) |
| **Bundled resources** | API entry template, module summary template, CHANGELOG entry template, LaTeX experiment writeup template |

**Invoke**: `/research-artifact-builder` — or auto-detected when discussing documentation updates.

---

## 2. The Four MCP Integrations

### MCP 1: Filesystem Access (`@modelcontextprotocol/server-filesystem`)

| Field | Detail |
|-------|--------|
| **Exposes** | Read/write/list/search files within the workspace directory |
| **Enables** | Reading experiment source code, inspecting configs, writing documentation, searching for patterns across codebase |
| **Risks** | Write access limited to workspace root only; no parent directory traversal. Review writes before committing. |
| **Setup** | `npx -y @modelcontextprotocol/server-filesystem ${workspaceFolder}` — already configured in `.vscode/mcp.json` |
| **Workflow improvement** | Agent can directly inspect any file, search across the codebase, and write documentation updates without manual copy-paste |

### MCP 2: Git / Diff Access (`mcp-server-git`)

| Field | Detail |
|-------|--------|
| **Exposes** | Git log, diff, status, branch info, blame, commit history for the repository |
| **Enables** | Inspecting what changed between branches, reviewing commit history, understanding file evolution, feeding diffs to the refactor reviewer skill |
| **Risks** | Read-only by default (no push/commit). If write operations are enabled, require explicit confirmation before any git write. Never force-push. |
| **Setup** | `uvx mcp-server-git --repository ${workspaceFolder}` — already configured in `.vscode/mcp.json`. Requires `uv` installed (`pip install uv` or `pipx install uv`). |
| **Workflow improvement** | "Review what changed on this branch" becomes a single request instead of manual `git diff` + copy-paste |

### MCP 3: Shell / Command Runner (VS Code built-in terminal)

| Field | Detail |
|-------|--------|
| **Exposes** | Execute shell commands (pytest, ruff, pip, python scripts) |
| **Enables** | Running test suites, linting, validation scripts, installing dependencies, executing tools like `strip_raw_artifacts.py` |
| **Risks** | **Highest risk surface.** Commands execute with user's full permissions. Mitigations: (1) Agent asks before destructive commands, (2) no `rm -rf` or `git push --force` without explicit approval, (3) prefer reversible commands |
| **Setup** | Already available via VS Code Copilot's built-in terminal tool — no additional MCP server needed |
| **Workflow improvement** | "Run tests and lint" becomes one request. Agent can validate its own changes immediately after editing. |

### MCP 4: Documentation / Knowledge Access (GitKraken MCP — already installed)

| Field | Detail |
|-------|--------|
| **Exposes** | Git operations (status, log, diff, blame, branch, stash), issue tracking, PR management via the GitKraken MCP server already available in this workspace |
| **Enables** | Deep git history inspection, PR review workflows, issue tracking, connecting code changes to issues, blame analysis for understanding code ownership |
| **Risks** | PR creation and issue comments are visible to collaborators — confirm before creating. Read operations are safe. |
| **Setup** | Already installed and available (GitKraken MCP tools detected in workspace). No additional setup needed. |
| **Workflow improvement** | Full PR lifecycle from the agent: create branch → make changes → create PR → request review. Issue-driven development with automatic linking. |

---

## 3. Rollout Order

| Phase | What | Why First | Setup Effort |
|-------|------|-----------|--------------|
| **Phase 1** | Workspace instructions (`.github/copilot-instructions.md`) + file instructions | **Immediate payoff**: Every interaction benefits. Zero MCP dependency. | ~5 min (already done) |
| **Phase 2** | Skill: `codebase-refactor-reviewer` | **Highest daily use**: You refactor constantly. Structured reviews > ad-hoc prompting. | Already created |
| **Phase 3** | MCP: Git server + GitKraken | **Unlocks diff-driven reviews**: Refactor reviewer skill can now pull real diffs automatically. | Install `uv`, verify GitKraken MCP |
| **Phase 4** | Skill: `calibration-experiment-audit` | **Domain-specific**: Once git access works, audit trails become powerful. | Already created |
| **Phase 5** | Skill: `research-artifact-builder` | **Documentation**: After code stabilizes, generate docs from the reviewed/audited code. | Already created |
| **Phase 6** | MCP: Filesystem server | **Optional upgrade**: Built-in tools already cover most file access. Useful for batch search/write operations. | `npx` must be available |

**Immediate next step**: Install `uv` if not already present, then reload VS Code to activate the MCP servers in `.vscode/mcp.json`.

---

## 4. Daily Workflow: Before vs. After

### Refactor Review

| Before (manual) | After (Skill + MCP) |
|-----------------|---------------------|
| 1. Run `git diff main..feature` in terminal | 1. Ask: "Review the refactor on this branch" |
| 2. Copy diff output into chat | 2. Agent auto-loads `codebase-refactor-reviewer` skill |
| 3. Manually describe what changed | 3. Agent pulls diff via git MCP, maps to module boundaries |
| 4. Ask about contract compliance | 4. Runs contract checklist automatically |
| 5. Ask about test coverage | 5. Cross-references test map, identifies gaps |
| 6. Manually compile risk assessment | 6. Produces structured report with risk level |
| **~15 min of prompting** | **~1 prompt, structured output** |

### Branch Diff Inspection

| Before | After |
|--------|-------|
| `git log --oneline -20` → copy → paste → "explain these" | "What changed in the last 20 commits?" → Agent uses git MCP → returns classified summary |

### Running Tests

| Before | After |
|--------|-------|
| Switch to terminal → `pytest` → copy failures → paste → "explain" | "Run tests and explain any failures" → Agent runs pytest → reads output → diagnoses |

### Updating README / API Docs

| Before | After |
|--------|-------|
| Read changed code → manually update docs → hope you didn't miss anything | "Update API docs for the calibration module" → Agent loads `research-artifact-builder` → reads source → generates doc entries → writes to file |

### Generating Research Writeups

| Before | After |
|--------|-------|
| Manually extract fit params → format LaTeX table → write sections → fill template | "Generate a LaTeX writeup for the Rabi experiment results" → Agent loads skill → reads experiment class + results → produces compilable `.tex` |

---

## 5. Starter Template & Setup

### File Layout (created)

```
e:\repo\qubox\
├── .github\
│   ├── copilot-instructions.md          ← Workspace instructions (active)
│   ├── instructions\
│   │   ├── calibration.instructions.md  ← Auto-loaded for calibration/ files
│   │   ├── experiments.instructions.md  ← Auto-loaded for experiments/ files
│   │   └── testing.instructions.md      ← Auto-loaded for test files
│   └── skills\
│       ├── codebase-refactor-reviewer\
│       │   ├── SKILL.md                 ← Skill entry point
│       │   └── references\
│       │       ├── module-map.md        ← Architecture boundaries
│       │       ├── test-map.md          ← Module → test mapping
│       │       └── contract-checklist.md← P0–P3 invariant checklist
│       ├── calibration-experiment-audit\
│       │   ├── SKILL.md
│       │   └── references\
│       │       ├── audit-checklist.md   ← Per-experiment verification
│       │       └── parameter-flow.md    ← cQED parameter dependencies
│       └── research-artifact-builder\
│           ├── SKILL.md
│           └── assets\
│               ├── api-entry.md         ← API doc template
│               ├── module-summary.md    ← Module summary template
│               ├── changelog-entry.md   ← CHANGELOG template
│               └── experiment-writeup.tex ← LaTeX writeup template
├── .vscode\
│   └── mcp.json                         ← MCP server configuration
└── ...
```

> **Note:** The `qubox_v2_legacy` directory referenced in earlier versions of
> this blueprint has been eliminated. All code now lives directly under `qubox/`.

### Windows + WSL Setup

**Prerequisites** (run once):

```powershell
# 1. Node.js (for filesystem MCP server)
winget install OpenJS.NodeJS.LTS

# 2. uv (for git MCP server)
pip install uv
# or: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 3. Verify
node --version   # v18+ required
uv --version     # 0.1+ required
```

**Activate MCP servers**:
1. Open VS Code in the qubox workspace
2. The `.vscode/mcp.json` file is already configured
3. Reload VS Code window (Ctrl+Shift+P → "Reload Window")
4. MCP servers start automatically when Copilot Chat is opened

### Example Invocations

Once the system is ready:

```
# Refactor review (auto-loads skill + git MCP)
> Review the changes I made to the calibration module this week

# Experiment audit (auto-loads skill)
> Audit the Rabi experiment lifecycle — trace from run() to apply_patch()

# Documentation generation (auto-loads skill)
> Update API_REFERENCE.md for the new PulseOperationManager methods

# LaTeX writeup (auto-loads skill + templates)
> Generate a LaTeX results section for the Ramsey experiment with these fit parameters: f_01 = 5.123 GHz ± 1 MHz, T2* = 12.3 μs ± 0.5 μs

# Direct skill invocation
> /codebase-refactor-reviewer Changed ExperimentRunner.__init__ signature to accept optional device_filter parameter
> /calibration-experiment-audit ReadoutCalibration
> /research-artifact-builder CHANGELOG entry for v2.1.1
```

---

## Security & Permission Notes

1. **Filesystem MCP**: Scoped to `${workspaceFolder}` only. Cannot escape the repository root. Safe for read/write within the project.
2. **Git MCP**: Read-only operations (log, diff, status, blame) are safe. If the server supports write operations (commit, push), the agent will ask before executing.
3. **Shell access**: The highest-risk surface. The agent follows operational safety rules: asks before destructive commands (`rm`, `git push --force`, `git reset --hard`), never bypasses safety checks (`--no-verify`), and prefers reversible operations.
4. **GitKraken MCP**: PR creation and issue comments are visible to collaborators. The agent asks before any operation that's visible to others.

---

## Extensibility

This setup is modular. Future additions:

| Future Skill / MCP | Purpose |
|--------------------|---------|
| `notebook-recovery` skill | Clean and recover corrupted Jupyter notebooks |
| `gate-tuning-audit` skill | Specialized audit for gate system architecture |
| `benchmarking-report` skill | Generate performance comparison reports |
| Fetch MCP server | Pull external documentation (QM docs, QuTiP API) |
| Database MCP server | Query experiment result databases |
