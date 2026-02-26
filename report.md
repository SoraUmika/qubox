# Deeper Grounded Audit of the Binary cQED Experiment Stack + Verified `|f⟩` Extension Plan

## 1) Current Architecture Snapshot (Grounded Survey)

### Stage A — Survey of the Existing Binary Stack

This audit was performed by tracing actual execution paths in `qubox_v2` across docs, experiments, builders, macros, calibration, pulse registration, analysis, and notebook workflow. The current stack is **partially generic at the pulse/program naming layer**, but **semantically binary (`g/e`) at the measurement, discrimination, post-selection, and correction layers**.

### A.1 Core ownership map

- **Experiment API surface**: `qubox_v2/experiments/*` with `ExperimentBase` orchestration and `RunResult`/`AnalysisResult` outputs.
- **Program construction**: `qubox_v2/programs/builders/*` and `qubox_v2/programs/cQED_programs.py` wrappers.
- **Runtime sequencing**: `qubox_v2/programs/macros/measure.py` and `qubox_v2/programs/macros/sequence.py`.
- **Calibration persistence/control**: `qubox_v2/calibration/models.py`, `store.py`, `orchestrator.py`, `contracts.py`.
- **Pulse operation registration**: `qubox_v2/pulses/manager.py`, `pulse_registry.py`, plus generators.
- **Readout analysis/correction/post-selection**: `qubox_v2/analysis/analysis_tools.py`, `post_process.py`, `post_selection.py`.
- **Operational usage**: `notebooks/post_cavity_experiment_context.ipynb`.

### A.2 Where binary assumptions are anchored today

1. **Measurement state is boolean in QUA**
   - Builders/macros repeatedly declare `state = declare(bool)` and stream `boolean_to_int()`.
   - This is the strongest low-level binary anchor; all higher-level `state_x/state_y/state_z`, `states1`, GE discrimination, and post-select semantics inherit from it.

2. **Discrimination and post-selection are `g/e` constrained**
   - `post_selection` API currently validates target state as only `"g"` or `"e"`.
   - `two_state_discriminator` and downstream usage are explicitly 2-class.

3. **Calibration schema is GE-shaped for readout quality/discrimination**
   - `DiscriminationParams` stores `mu_g/mu_e`, `sigma_g/sigma_e`, `threshold`, etc.
   - `ReadoutQuality` uses 2x2 confusion matrix semantics and GE metrics (`fidelity_ge`, assignment probabilities, etc.).

4. **Many high-level workflows default to GE pulses**
   - Frequent defaults like `r180="x180"`, `x90/yn90`, and GE prep/reset assumptions.
   - Notebook workflows reinforce this by default.

5. **Tomography and cavity-tagging workflows still encode binary measurement channels**
   - Even when they are structurally flexible over prep callables, the observed outputs remain boolean state channels and two-state correction logic.

### A.3 Existing `|f⟩` readiness already present

- `QubitSpectroscopyEF` exists and can run an `ef`-targeted scan by preparing `|e⟩` and probing.
- Frequency model supports `anharmonicity` and partial frequency flexibility.
- Pulse manager/registry are operation-name flexible enough to host additional transition-scoped operations.
- `multi_state_calibration` placeholder exists in calibration schema but is not integrated into runtime readout/discrimination/post-selection contracts.

---

## 2) Experiment Inventory and Binary-Dependency Buckets

### Stage A — Per-experiment bucket classification

Buckets:
- **B0: already mostly transition-generic**
- **B1: easy to generalize with explicit transition metadata and pulse naming discipline**
- **B2: deeply binary (requires contract/schema/runtime change)**

### B0 (already mostly generic)

- Storage and Fock spectroscopy-style experiments that operate mostly on I/Q complex response and frequency sweeps (`experiments/cavity/storage.py`, `experiments/cavity/fock.py`), *except where they invoke boolean-tag readout or binary selective mapping checks*.
- Some time-domain sweeps whose logic is pulse-parameterized and does not itself classify >2 states.

### B1 (easy-to-medium generalization)

- `QubitSpectroscopy`, `QubitSpectroscopyCoarse`, `PowerRabi`, `TemporalRabi`, `T1Relaxation`, `T2Ramsey`, `T2Echo`:
  - generally pulse-name parameterized,
  - but currently default to GE operation names and GE-focused calibration patch expectations.
- Builders under `programs/builders/spectroscopy.py` and `time_domain.py`:
  - mostly transition-agnostic structurally,
  - need explicit transition keying and calibration target metadata to avoid ambiguity.

### B2 (deep binary dependencies)

- Readout calibration stack in `experiments/calibration/readout.py` + `programs/builders/readout.py`.
- Runtime measurement/post-selection contracts in `programs/macros/measure.py` and `programs/macros/sequence.py`.
- Analysis and correction pipeline in `analysis/analysis_tools.py`, `analysis/post_selection.py`, `analysis/post_process.py`.
- Tomography state channels in `programs/builders/tomography.py` and `experiments/tomography/*` due to boolean state stream model.

### Key dependency chain

`measureMacro.measure (bool state)`
→ stream outputs (`boolean_to_int`) 
→ `post_selection` (`g/e` target enum)
→ two-state discriminator + 2x2 confusion correction
→ GE-specific readout calibration artifacts
→ experiment-level metrics and notebook defaults.

This chain is why `|f⟩` cannot be safely added by only introducing new pulses or a new spectroscopy class.

---

## 3) Verified `|f⟩` Extension Analysis (No Implementation)

### Stage B — Subsystem impact and required capabilities

### B.1 Experiment API layer (`experiments/*`)

- Needed: explicit transition-scoped intent (`ge`, `ef`, optionally `gf` derived) in experiment configuration and metadata.
- Needed: calibration patch payloads that include transition identity (not only operation name), especially when updating pi/2pi pulse references.
- Keep: existing class APIs where possible; prefer additive parameters to avoid breakage.

### B.2 Program builders (`programs/builders/*`, `cQED_programs.py`)

- Needed: transition-aware pulse binding without hardcoded `x180` assumptions.
- Needed: clear separation between
  - readout-state extraction mode (binary threshold vs multi-state classifier)
  - experiment control transition (GE/EF drive).
- Keep: current QUA loop structure and stream conventions where not tied to binary state fields.

### B.3 Macro contracts (`measureMacro`, `sequenceMacros`)

- Needed: measurement API mode that can return **multi-state label** (or posterior vector) in addition to current boolean path.
- Needed: post-selection API generalized from `{g,e}` to configurable state set (`g,e,f`).
- Needed: prep/reset helpers to target configurable computational manifold without changing current default behavior.
- This is the highest-leverage refactor point.

### B.4 Calibration schema/store/orchestrator

- Needed: versioned extension of discrimination/readout-quality records to support:
  - multi-class centroids/covariances or classifier params,
  - NxN confusion matrix,
  - per-state assignment metrics.
- Needed: orchestrator patch validation capable of both legacy GE and new multi-state model.
- Keep: existing GE schema fields and read path for backward compatibility.

### B.5 Pulse registration/generation

- Needed: transition-scoped operation naming convention (e.g., `ge_x180`, `ef_x180`) and metadata map.
- Needed: generation helpers that avoid ambiguous aliases in saved calibrations.
- Keep: registry/manager architecture; it already supports flexible operation registration.

### B.6 Analysis/post-selection/correction

- Needed: generalization from `two_state_discriminator` to `multi_state_discriminator` contract (or classifier adapter).
- Needed: post-selection utility that accepts generic state labels and supports manifold filters.
- Needed: correction routines upgraded from 2x2 to NxN confusion handling.
- Keep: existing GE correction path as compatibility mode.

### B.7 Notebook/wrapper UX

- Needed: explicit transition defaults in notebook recipes to prevent accidental GE pulse reuse for EF routines.
- Needed: concise migration examples from `x180` to transition-scoped aliases.
- Keep: GE-first happy path for current users.

---

## 4) Layered Architecture Recommendation

### Stage C — What to build first, what to defer

### Layer 0 (do first): Contracts and compatibility envelope

1. Introduce transition and readout-mode abstractions in runtime contracts (non-breaking defaults).
2. Keep existing GE behavior as default and fully operational.
3. Add explicit internal capability flags (binary-only vs multi-state enabled).

**Why first:** prevents ad-hoc EF additions from bypassing calibration/analysis correctness.

### Layer 1: Calibration + analysis backbone for multi-state

1. Extend calibration data model for multi-state discrimination and NxN confusion.
2. Add store/orchestrator validation + migration path.
3. Generalize post-selection/correction/discriminator interfaces with GE compatibility adapter.

**Why second:** this is required before trusting any `|f⟩` metrics.

### Layer 2: Measurement macro and sequence API generalization

1. Extend `measureMacro` outputs beyond boolean state in a controlled mode.
2. Generalize `sequenceMacros.prepare_state` and `post_select` target labels.
3. Add readout-mode plumbing to builders.

**Why third:** unblocks broad experiment support once ground truth and correction contracts are valid.

### Layer 3: Experiment-by-experiment enablement

1. Upgrade B1 experiments first (spectroscopy/time-domain with transition parameterization).
2. Then upgrade B2 readout/tomography stack.
3. Preserve notebook compatibility and provide explicit EF examples.

### Layer 4: Optional optimizations

- Advanced classifier backends, posterior-driven adaptive selection, richer tomography manifolds.
- Only after baseline multi-state correctness is verified.

---

## 5) Prioritized Implementation Plan (Proposed, No Code Yet)

### P0 — Safety and compatibility

- Define transition/readout-mode enums + capability flags.
- Add compatibility adapters so existing GE notebooks run unchanged.
- Add validation tests for “legacy GE parity” behavior.

### P1 — Data model and correction pipeline

- Introduce multi-state discrimination schema and NxN confusion representation.
- Wire orchestrator/store validation and serialization.
- Generalize correction utilities and post-selection APIs.

### P2 — Macro/runtime extension

- Extend measurement macro for multi-state outputs with fallback boolean path.
- Update sequence helpers (`prepare_state`, post-select) to accept configurable labels.

### P3 — Experiment onboarding

- Migrate B1 classes/builders to explicit transition parameterization.
- Onboard EF-ready calibration and selected time-domain experiments.
- Finally migrate B2 readout/tomography workflows.

### P4 — Documentation and notebook migration

- Add migration guide: operation naming, transition-safe defaults, calibration requirements.
- Update notebook recipes with explicit GE/EF examples.

---

## 6) Risks, Ambiguities, and “Do Not Change Yet” Scope

### Principal risks

1. **Silent semantic drift**: adding EF pulses without upgrading discrimination/correction can produce plausible but invalid metrics.
2. **Backward incompatibility**: replacing GE schema/contracts in place can break existing sessions and notebooks.
3. **Naming ambiguity**: unscoped operation names (`x180`) can map to wrong transition in mixed GE/EF contexts.
4. **Partial migration hazards**: enabling multi-state in one layer without others yields inconsistent results.

### Ambiguities to resolve before implementation

- Canonical state label taxonomy (`g/e/f` strings vs numeric IDs).
- Whether runtime state outputs should be hard labels, posterior vectors, or both.
- Exact minimal viable EF scope (spectroscopy-only first vs immediate time-domain + readout pipeline).

### What not to change yet (explicit deferrals)

- Do **not** remove or reinterpret existing GE fields in calibration schema.
- Do **not** convert all experiments at once.
- Do **not** force notebook users onto EF naming before compatibility adapters exist.
- Do **not** collapse pulse aliases until transition-scoped registry policy is finalized.

---

## Final Conclusion

The current stack is **not uniformly binary at the control layer**, but it is **decisively binary at readout-state semantics and analysis/correction contracts**. A verified `|f⟩` extension is feasible and should proceed, but only through a **contract-first, compatibility-preserving staged rollout**:

1) define transition/readout modes,
2) upgrade calibration + correction backbone,
3) generalize measurement/sequence macros,
4) migrate experiments in priority buckets,
5) update notebook UX.

This ordering minimizes scientific risk and prevents invalid EF conclusions from partially upgraded pipelines.
