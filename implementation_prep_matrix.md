# Implementation-Prep Matrix for Extending cQED Stack to Support |f⟩ (Design-Only)

This document is a code-traced pre-implementation decision artifact. No code changes were made.

## 1. Per-Experiment Implementation-Prep Matrix

Legend:
- G0 = already practically transition-generic
- G1 = generic control shape, but defaults/metadata still implicitly ge
- G2 = control reusable, but readout/correction/post-selection assumptions are binary
- G3 = deeply binary contract dependencies; defer until readout/state contracts are upgraded

| Experiment / Workflow | Code Path (class → builder → macros/analysis/calibration) | Physical Purpose | Current Default Control Assumptions | Current Measurement / Readout Semantics | Current Calibration Inputs Consumed | Current Artifacts / Outputs / Patches Produced | Binary Assumptions (Code-Grounded) | Bucket + Justification | Minimal Safe Change for |f⟩ | Recommended Phase | Notes / Risks |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Qubit spectroscopy (ge) | `experiments/spectroscopy/qubit.py::QubitSpectroscopy` → `programs/builders/spectroscopy.py::qubit_spectroscopy` → `measureMacro.measure` + `analysis/post_process.py::proc_default` | Locate qubit transition frequency via IF sweep | Caller passes pulse name; wrapper convention is ge pulse. Single transition frequency path in analyze patch target. | Raw IQ demod to complex S; no classifier required. | `frequencies.<qb_el>.qubit_freq` via `set_standard_frequencies`; pulse op provided by caller. | Metrics `f0/gamma`; optional proposed patch `frequencies.<qb_el>.qubit_freq`. | Analyze patch target is unlabeled qubit frequency slot; implicit ge meaning. | G1: control path generic, metadata target remains ge-implicit. | Add explicit `transition` field (`ge` default), and write transition-scoped frequency artifact (`qubit_freq_ge`/`qubit_freq_ef`). | Phase 1 | Low risk if backward-compatible default kept. |
| Coarse qubit spectroscopy | `QubitSpectroscopyCoarse` → same builder (`qubit_spectroscopy`) over segmented LOs | Wide-range qubit scan | Same as above plus LO segmentation. | Raw IQ only. | LO handling + same qubit frequency fields. | Same `f0` metrics and proposed frequency patch. | Same ge-implicit frequency writeback. | G1: same reason as single-LO variant. | Same as above; also transition label in stitched metadata. | Phase 1 | One call site currently passes `attr.ro_el` into builder arg slot; verify before touching behavior. |
| ef spectroscopy (already present) | `QubitSpectroscopyEF` → `qubit_spectroscopy_ef` builder | Probe e→f transition | Hardcoded `r180="x180"` for e prep in wrapper; assumes ge pi exists and is valid. | Raw IQ only. | Uses current qubit IF, ge prep pulse alias, IF sweep params. | Metrics `f_ef`; no calibration patch by default. | e prep is ge-specific alias; no explicit transition identity in outputs. | G1: already ef-capable, but ge alias and metadata not normalized. | Add explicit `prep_ge_pulse` and transition identity in result/patch schema; default maintain `x180` alias. | Phase 1 | Requires reliable ge pi prior to ef scan; should be stated in API contract. |
| Power Rabi | `time_domain/rabi.py::PowerRabi` → `builders/time_domain.py::power_rabi` | Calibrate pi amplitude | Default `op="ref_r180"`; assumes target operation is ge reference family. | IQ -> S.real fit, no classifier; no post-selection. | Pulse op from pulse manager + `pulse_calibrations.<op>` amplitude context. | Metrics `g_pi`; proposed patch to `pulse_calibrations.<op>.amplitude` (+ recompile). | Reference op naming is ge-oriented; no transition field in patch payload. | G1: control sweep generic, calibration metadata ge-implicit. | Add required/explicit `transition` and transition-scoped reference op (`ref_ge_r180`, `ref_ef_r180`) normalization. | Phase 2 | ef power-Rabi is invalid without consistent e-prep strategy per shot. |
| Temporal Rabi | `TemporalRabi` → `builders/time_domain.py::temporal_rabi` | Calibrate pi length | Generic pulse argument, but practical defaults ge operations. | IQ magnitude fit; no classifier. | Pulse op and standard frequencies. | Metric `pi_length`; can guarded-commit pulse length patch for target op. | No transition identity in calibration record (`target_op` only). | G1: mostly generic, metadata/defaults ge-like. | Same transition-scoped pulse-calibration contract as PowerRabi. | Phase 2 | For ef, requires explicit prep-to-e option before drive. |
| T1 relaxation | `T1Relaxation` → `builders/time_domain.py::T1_relaxation` | Energy relaxation time | Default `r180="x180"`, assumes g→e prep. | IQ real-part fit; no classifier. | Coherence fields + r180 pulse + frequencies. | Metrics `T1_*`; proposed coherence patches (`coherence.<qb>.T1`). | Prep pulse assumes ge; coherence field not transition-tagged. | G1: sequence simple but ge semantics in prep and storage key. | Add `prep_sequence` abstraction and transition-tagged coherence keys (`T1_ge`, `T1_ef`). | Phase 2 | ef T1 needs f prep chain (ge+ef or dedicated prep macro). |
| Ramsey | `T2Ramsey` → `builders/time_domain.py::T2_ramsey` + `sequenceMacros.qubit_ramsey` | Dephasing + detuning | Default `r90="x90"`, ge pulse family; frequency correction writes qubit_freq. | IQ real-part fit; no classifier. | qubit frequency, detune, coherence store fields. | Metrics `T2_star/f_det`; proposed coherence + optional frequency correction patch. | Pulse defaults ge; correction patch targets generic qubit_freq. | G1: control reusable, metadata ge-implicit. | Add transition-scoped pulse pair + frequency namespace and coherence keys by transition. | Phase 2 | Incorrect frequency correction risk if ef run writes into ge slot. |
| Echo | `T2Echo` → `builders/time_domain.py::T2_echo` + `sequenceMacros.qubit_echo` | Hahn echo coherence | Defaults `r90="x90"`, `r180="x180"` (ge). | IQ real-part fit; no classifier. | Coherence store + default pulse family. | Metrics `T2_echo`; proposed coherence patches. | Ge pulse assumptions and non-transition-tagged coherence key. | G1 | Add transition-scoped pulse tuple + coherence key namespace. | Phase 2 | Same transition-key collision risk as Ramsey. |
| DRAG calibration | `calibration/gates.py::DRAGCalibration` → `builders/calibration.py::drag_calibration_YALE` | Optimize DRAG coeff to suppress leakage | Builds temp pulses from `ref_r180` lineage; defaults ge primitive family. | IQ two-sequence differential; no classifier. | `pulse_calibrations.ref_r180` params (len/sigma/amp/anharm). | `optimal_alpha`; proposed patch to `pulse_calibrations.<target>.drag_coeff`. | Reference pulse semantics ge by convention; derived primitives assume ge set. | G1 | Transition-scoped reference calibrations (`ref_ge_r180`, `ref_ef_r180`) and generator mapping for derived sets. | Phase 1 | Safe early if strictly namespaced and no runtime readout changes needed. |
| Pulse-train tomography / arbitrary rotation calibration | `PulseTrainCalibration` in `calibration/gates.py` → `calibration/pulse_train_tomo.py::run_pulse_train_tomography` (uses tomography builders) | Fit rotation-systematic errors from repeated arbitrary rotations | Uses prep definitions built from ge primitives in notebook conventions. | Tomography-derived state channels (sx/sy/sz) tied to boolean state extraction path. | Reference pulse, prep macros, tomography stack assumptions. | Metrics amp_err/phase_err/delta/zeta; knob deltas. | Depends on boolean state tomography and ge pulse prep conventions. | G3: deeply coupled to binary state-channel tomography. | Defer until state/readout contracts support multi-state or explicit pairwise mode for tomography axis extraction. | Phase 3 | High risk of misleading fits if run with partial ef support only. |
| Readout GE discrimination | `ReadoutGEDiscrimination` → `builders/readout.py::iq_blobs` → `analysis_tools.two_state_discriminator` + optional `measureMacro` update | Fit g/e blobs and threshold/rotation | Hardcoded g/e acquisition via no-pulse + `r180`. | Explicit 2-state discrimination, threshold, angle, sigma_g/e. | Readout pulse mapping, weight mapping, ge prep pulse, existing measureMacro state. | Metrics + optional rotated weight ops + discrimination patch intents (`discrimination.<el>.*`). | Uses two-state model and ge-specific fields (`mu_g/mu_e`, `sigma_g/e`, `threshold`). | G2: control reusable, discrimination contract binary. | Add pairwise discriminator contract with explicit pair label (`ge`, `ef`) and pair-scoped storage entries. | Phase 1 | Recommended to include as pairwise extension (not full ternary) in first scope. |
| Butterfly readout measurement | `ReadoutButterflyMeasurement` → `builders/readout.py::readout_butterfly_measurement` + `sequenceMacros.post_select` | Estimate F, Q, QND/readout quality via M0/M1/M2 | Branches hardcoded target_state `g` then `e`; correction pulses use threshold logic and `r180`. | Uses boolean states, post-select policy keyed to g/e semantics, two-branch outputs. | measureMacro discrimination params, post-select config, threshold, rot blob params. | Readout quality metrics and possible readout-quality patch flow. | `target_state` domain g/e only; correction logic binary; quality model aligns to 2x2 confusion interpretation. | G3: deeply binary protocol semantics. | Defer core butterfly generalization until state-label/readout-mode contracts are expanded. | Phase 3 | Partial migration likely invalidates quality metrics comparability. |
| Full readout calibration workflow | `CalibrateReadoutFull` orchestrates `ReadoutWeightsOptimization` → `ReadoutGEDiscrimination` → `ReadoutButterflyMeasurement` | End-to-end readout calibration | Pipeline explicitly GE then butterfly; config defaults ge-oriented names/params. | Binary discrimination + binary butterfly quality composition. | `ReadoutConfig`, measureMacro state, calibration/orchestrator patch rules for GE artifacts. | Composite results + patch previews/apply path. | Pipeline kind names and rule mapping are GE/binary specific. | G3 | Keep pipeline stable; introduce separate pairwise `CalibrateReadoutPairwise(pair=ef)` later. | Deferred (after Phase 1 pairwise pieces prove out) | Single pipeline rewrite is high blast radius. |
| Reset benchmark | `QubitResetBenchmark` → `builders/readout.py::qubit_reset_benchmark` + `sequenceMacros.conditional_reset_ground` | Reset quality under random target prep | Uses random bit prep with `r180` and threshold-ground reset. | Boolean state M1/M2 streams. | threshold from measureMacro discrimination, `r180`, thermalization. | Raw/reset state arrays; no explicit analyze patch. | Conditional reset criterion is binary threshold on I; target semantics 0/1=>g/e. | G3 | Defer; needs generalized state reset policy and pair/multistate decision logic. | Phase 3 | Current logic cannot express reset to f manifold safely. |
| Active reset benchmark | `ActiveQubitResetBenchmark` → `builders/readout.py::active_qubit_reset_benchmark` + `sequenceMacros.post_select` | Active reset efficacy with retries | Hardcoded branches for target g/e. | Boolean M0/M1/M2 + post-select target_state g/e. | threshold + post-select kwargs from binary discriminator. | Raw metrics arrays; no direct calibration patch. | `post_select(target_state in {g,e})` hard dependency. | G3 | Defer until generalized state labels and readout modes are implemented. | Phase 3 | Very sensitive to readout-mode semantics. |
| Tomography (qubit state) | `tomography/qubit_tomo.py::QubitStateTomography` → `builders/tomography.py::qubit_state_tomography` + `sequenceMacros.qubit_state_tomography` + `ro_state_correct_proc` | Reconstruct Bloch vector sx/sy/sz | ge axis pulses (`x90`, `yn90`) defaults. | Uses boolean `state_x/y/z` channels; optional 2x2 confusion correction path. | confusion matrix from calibration store/readout quality; default pulse axes. | sx/sy/sz metrics and purity. | state channel is binary, correction assumes 2-state probabilities. | G3 | Defer until tomography measurement API can consume pairwise/multi-state labels or explicit projection contract. | Phase 3 | Using current booleans with ef control can silently mislabel populations. |
| Tomography (fock-resolved + SNAPOptimization) | `tomography/fock_tomo.py::FockResolvedStateTomography`, `tomography/wigner_tomo.py::SNAPOptimization` → tomography builders | Manifold-resolved state reconstruction / SNAP tuning | selective pulses default `sel_x180` etc; control paths mostly pulse-parameterized. | Underlying state channels still boolean-based for tomography axes. | selective pulse families, fock probe IFs, readout macro config. | Fock population-like metrics from tomography magnitudes. | Same binary state-channel anchor. | G3 | Defer until tomography/state-channel contract upgrade. | Phase 3 | Output interpretation currently tied to two-state assumption. |
| Notebook central workflow (operational chain) | `notebooks/post_cavity_experiment_context.ipynb`: imports and runs `PowerRabi`, `TemporalRabi`, `T1/T2`, `ReadoutGEDiscrimination`, `ReadoutButterflyMeasurement`, `CalibrateReadoutFull`; heavy use of `x180`, `ref_r180`, `sel_x180` | Practical session calibration and experiment orchestration | Legacy aliases and ge primitive naming dominate operational examples. | Mix of IQ fits + GE/butterfly binary readout pipeline. | Session calibration store + pulse manager aliases + orchestrator patch previews/applies. | Human-in-loop patch preview/apply plus plots and logs. | Alias usage embeds ge assumptions in practice even where APIs are parameterized. | G2 operationally (control partly generic, workflow semantics binary) | Add migration notebook path with explicit transition/pair labels and alias-normalization warnings at boundaries. | Phase 1 (docs/workflow updates) | If notebook stays alias-first, users will unintentionally run ef with ge defaults. |


## 2. Cross-Cutting Dependency Summary

### Repeated binary anchors
- `measureMacro.measure(..., state=bool)` and `boolean_to_int()` streams are pervasive in tomography, reset, and butterfly flows.
- `post_selection.TargetState = Literal["g","e"]` and `sequenceMacros.prepare_state/post_select` enforce two-label semantics.
- `two_state_discriminator` and `ro_state_correct_proc` currently center on two-state correction conventions (including 2x2 confusion usage in practical paths).
- Calibration schema for discrimination/readout-quality is ge-shaped (`mu_g/mu_e`, `sigma_g/sigma_e`, GE-oriented quality usage).

### Repeated generic opportunities
- Many control loops are pulse-name parameterized and can drive transition-aware operations with minimal program changes.
- Frequency sweeps and IQ-only fits are generally transition-agnostic once transition metadata is explicit.
- Pulse manager/registry can already host transition-scoped operation names without architecture rewrite.

### Repeated notebook/default hazards
- Notebook usage strongly normalizes unprefixed aliases (`x180`, `x90`, `ref_r180`, `sel_x180`).
- Patch preview/apply patterns currently assume GE calibration paths; without transition scoping these can overwrite wrong records.
- Practical workflows rely on GE discrimination before butterfly; this coupling should not be implicitly reused for ef without explicit pair mode.


## 3. Forced Design Decisions

### Q1. Recommended first implementation scope
Recommendation: **Option B** (transition-aware control + pairwise transition-aware readout).

Why:
- Option A is too weak for trustworthy ef workflows because current readout/discrimination contracts are ge-only.
- Option C is high-risk/high-blast-radius because tomography/reset/post-selection contracts are deeply binary and would force broad simultaneous refactor.
- Option B matches current architecture: it allows rapid enablement of `ge` and `ef` pairwise workflows with bounded change scope and strong backward compatibility.

### Q2. `measureMacro.measure()` strategy
Recommendation: **Keep `measureMacro.measure()` stable for now, and introduce a separate explicit multistate API later**.

Why:
- `measureMacro.measure()` is deeply entrenched across builders and experiments; changing return semantics now is high regression risk.
- Pairwise extension can be delivered by adding pair-scoped discrimination/readout mode plumbing while preserving current bool path.
- A future explicit multistate API can be introduced once contracts and tests are ready (without breaking legacy GE notebooks).

### Q3. Canonical contract for transition identity
Recommendation:
- Canonical transition labels: `ge`, `ef`.
- Transition identity must appear in:
  - pulse operation naming (canonical internal names, e.g., `ge_x180`, `ef_x180`),
  - calibration records (transition-scoped fields or namespaced keys),
  - experiment config params (`transition`),
  - stored artifacts/metrics (include `transition` in metadata).
- Unprefixed names like `x180` should be **kept as migration aliases**, accepted only at input boundaries, then normalized internally to transition-scoped canonical names.

### Q4. Canonical contract for state labels and readout modes
Recommendation:
- Canonical external state labels: `"g"`, `"e"`, `"f"`.
- Numeric IDs are internal-only for storage/performance layers.
- Define explicit readout modes:
  - `binary_ge`
  - `binary_ef`
  - `pairwise` (requires explicit pair argument)
  - `multistate_gef` (future)
- For first rollout, implement/use `binary_ge`, `binary_ef`, and `pairwise`; defer `multistate_gef` until Phase 3.


## 4. Recommended First Implementation Boundary

### Include in first coding pass
- Transition identity plumbing (`ge`/`ef`) across spectroscopy/time-domain wrappers and calibration metadata.
- Canonical transition-scoped pulse naming + alias normalization layer.
- Pairwise readout discrimination support for `ef` alongside existing `ge` (`ReadoutGEDiscrimination`-style path generalized by pair label).
- Minimal orchestrator/store schema additions required to persist pairwise discrimination artifacts without breaking existing GE records.
- Notebook migration cells/examples that explicitly choose transition and pairwise readout mode.

### Exclude from first coding pass
- Full butterfly protocol generalization to non-ge targets.
- Full ternary/multistate classifier and 3x3 confusion-matrix correction end-to-end.
- Tomography state-channel redesign.
- Reset benchmarking redesign for generalized state targets.


## 5. Do Not Touch Yet List

Do not modify these in the first pass (except additive compatibility wrappers/adapters around them):
- `qubox_v2/programs/macros/measure.py` core bool `measure()` semantics.
- `qubox_v2/programs/macros/sequence.py` deep semantics of `prepare_state/post_select` for non-ge states.
- `qubox_v2/experiments/calibration/readout.py::ReadoutButterflyMeasurement` protocol logic.
- `qubox_v2/experiments/calibration/readout.py::CalibrateReadoutFull` orchestration flow.
- `qubox_v2/experiments/tomography/*` state-channel interpretation path.
- `qubox_v2/experiments/calibration/reset.py` active/reset benchmark branching logic.
- Global replacement/removal of legacy aliases in notebooks before normalization adapters land.


## Confidence / Uncertainty Notes

- Confidence is high for code-path and dependency mapping above (directly traced in experiments/builders/macros/analysis/calibration/notebook).
- One concrete code-path inconsistency was observed in coarse spectroscopy builder argument passing; this should be verified during implementation prep before editing.
- Pulse-train tomography internals call additional helper code in `calibration/pulse_train_tomo.py`; classification above is based on wrapper behavior and its dependence on tomography state-channel semantics.
