# QUBOX_V2 Codebase Survey

**Date**: 2026-02-27  
**Auditor**: Automated Static Analysis + Manual Code Review  
**Scope**: All source files under `qubox_v2/`  
**Methodology**: Read-only; no source files modified.

---

## Executive Summary

`qubox_v2` is a well-structured, multi-layered experiment orchestration framework for circuit-QED on Quantum Machines OPX+ hardware. It has undergone substantial active refactoring from a ~5,200-line monolith (`cQED_Experiment`) toward a clean modular architecture with strong Pydantic-typed models, an explicit Patch/Artifact/Orchestrator pipeline, and a binding-driven hardware abstraction layer.

The framework's design intentions are sound and documented thoroughly in `docs/CHANGELOG.md`. The calibration pipeline — Run → Artifact → CalibrationResult → Patch → Apply — is properly expressed in `calibration/orchestrator.py`. The `CalibrationStore` with v5.0.0 schema, alias index, and context validation is a mature persistence layer.

Several issues present in earlier versions of the codebase have since been fixed: the missing `resonator_freq` field in `ElementFrequencies`, the absent quality guard in `run_analysis_patch_cycle`, and the unconverted T2 values emitted directly by `T2RamseyRule`/`T2EchoRule`. These are now handled correctly in the current code.

**Remaining concrete bugs and structural issues that require attention before production use:**

- **2 Critical issues**: `measureMacro` class-level singleton state and a bare `KeyError`-prone threshold access in QUA program construction.
- **3 High risk issues**: T2 unit mismatch via the `proposed_patch_ops` / `WeightRegistrationRule` path, a fragile `sync_ok` reference pattern, and an acknowledged `BUGFIX` comment in config loading.
- **8 Medium issues**: Duplicate utility functions, giant legacy god-class still actively used, orphaned model fields, fragile quality gate logic.
- **6 Low issues**: Naming inconsistencies, hard-coded element strings, style debt.

The overall calibration architecture is correct in design; the bugs are implementation-level and mostly fixable with targeted changes.

---

## Critical Issues (Red)

> Issues that can cause incorrect experimental results or hardware risk.

---

### CRIT-01 — `measureMacro` is a Class-Level Singleton: All Sessions Share Readout State

**Severity**: Critical  
**File**: `qubox_v2/programs/macros/measure.py`, class `measureMacro` (line 121)  
**Also affected**: `qubox_v2/experiments/legacy_experiment.py` (lines 947, 1083, 1373, 2786, 2820); `qubox_v2/experiments/session.py` (line 848)

**Evidence**:
```python
class measureMacro:
    _pulse_op: PulseOp | None = None           # line 122 — class attribute
    _demod_fn = dual_demod.full                # line 131 — class attribute
    _state_stack: list[tuple[str, dict]] = []  # line 141 — class attribute
    _ro_disc_params = {                        # line 149 — class attribute
        "threshold": None,
        "angle": None,
        ...
    }
    _ro_quality_params = { ... }               # class attribute
```

All discrimination parameters, integration weights, demodulation function bindings, and the state stack are **class-level** (not instance-level) attributes. There is only one global `measureMacro` state regardless of how many `SessionManager` or `cQED_Experiment` instances are active. If two experiments run sequentially or if a session is partially reset, the discrimination parameters from one run bleed into the next.

**Why critical**: Any code that relies on `measureMacro._ro_disc_params["threshold"]` or `measureMacro._ro_quality_params["confusion_matrix"]` for classification of qubit state is reading a single shared global. Reinitializing one session or experiment implicitly resets readout calibration for all.

**Impact**: State-leakage experiments will silently apply stale discrimination to new data, producing incorrect Pe/Pg assignments without any error.

---

### CRIT-02 — Bare `KeyError` on Uncalibrated Threshold in QUA Program Construction

**Severity**: Critical  
**File**: `qubox_v2/programs/builders/readout.py`, line 668  
**Also**: `qubox_v2/programs/builders/simulation.py`, line 34

**Evidence**:
```python
# readout.py:668
thr = measureMacro._ro_disc_params["threshold"]
```

```python
# simulation.py:34
sequenceMacros.conditional_reset_ground(
    I, thr=measureMacro._ro_disc_params["threshold"], r180="x180", qb_el="qubit"
)
```

Both locations use `dict[key]` subscript access rather than `.get("threshold", 0.0)`. The default value of `_ro_disc_params["threshold"]` is `None` (set at class definition). If `float(None)` is computed downstream or `None` is passed as a threshold into a QUA `assign()`, the QUA program will be built with a `None` threshold — a semantically incorrect operation that may fail at runtime with an opaque error or silently produce all-excited or all-ground results.

In contrast, other consumers use `.get("threshold", 0.0)` (e.g., `programs/macros/sequence.py:512`), demonstrating that the safe pattern is known but inconsistently applied.

**Impact**: Any experiment using `active_reset_benchmark` or cavity simulation programs before discrimination calibration runs will produce QUA programs with incorrect state-classification logic.

---

## High Risk Issues (Orange)

> Issues that can corrupt calibration state or create misleading outputs.

---

### HIGH-01 — T2 Coherence Time Unit Mismatch via `proposed_patch_ops` / `WeightRegistrationRule` Path

**Severity**: High  
**Files**: `qubox_v2/calibration/patch_rules.py` (lines 97–100, 118–121); `qubox_v2/experiments/time_domain/coherence.py` (lines 139, 329–330); `qubox_v2/calibration/models.py` (lines 118–121)

**Evidence**:
```python
# patch_rules.py:97-100 — T2RamseyRule
if "T2_star" in params:
    patch.add("SetCalibration",
              path=f"coherence.{self.element}.T2_ramsey",
              value=params["T2_star"])   # T2_star is in ns (see below)
```

```python
# coherence.py:139 — T2Ramsey.analyze()
metrics["T2_star"] = fit.params["T2"]   # units: "ns" per metadata["units"]
```

```python
# models.py:118
T2_ramsey: float | None = None   # seconds  ← expects seconds
```

The same pattern applies to `T2Echo` (coherence.py:329 produces `T2_echo` in ns; `T2EchoRule` stores it to `T2_echo` which is a seconds field in `CoherenceParams`).

**Mitigation**: `CalibrationStore._normalize_coherence_units()` (store.py, ~line 85) detects the mismatch via `T2_star_us` / `T2_echo_us` companion fields and corrects on reload. However:
1. The in-memory `CalibrationData` object holds the wrong value **from the time `apply_patch` is called until the next `calibration.reload()`** — potentially for the entire experiment session.
2. Any code reading `get_coherence().T2_ramsey` within the same session after a T2 calibration will receive a value in ns, not seconds — off by a factor of 10⁹.
3. If `T2_star_us` is not also present (legacy path), the normalization falls through to a >1.0 heuristic that may misidentify the unit.

---

### HIGH-02 — `sync_ok` Referenced Before Assignment in `apply_patch` Dry-Run Edge Case

**Severity**: High (latent)  
**File**: `qubox_v2/calibration/orchestrator.py`, `apply_patch()` (line 270)

**Evidence**:
```python
def apply_patch(self, patch: Patch, dry_run: bool = False) -> dict[str, Any]:
    preview: list[dict[str, Any]] = []
    # ... loop ...
    if not dry_run:
        # ...
        sync_ok = True   # line 236 — only assigned inside if block
        # ...
    return {
        "sync_ok": sync_ok if not dry_run else True,  # line 270 — conditional
    }
```

Python's short-circuit evaluation means `sync_ok` is never evaluated when `not dry_run` is `False`. However, this is a fragile construct: any static analysis tool or future refactor that evaluates `sync_ok` before the conditional expression will encounter an `UnboundLocalError`. The pattern is also misleading — the reader must understand Python short-circuit semantics to verify safety.

---

### HIGH-03 — Documented `BUGFIX` in `load_exp_config` Never Fixed

**Severity**: High  
**File**: `qubox_v2/experiments/legacy_experiment.py`, lines 200–213

**Evidence**:
```python
except Exception as e:
    _logger.warning(
        "Loading configuration failed: %s. Building a minimal default.", e, exc_info=True
    )
    builder = ConfigBuilder.minimal_config()
    # BUGFIX: this should write *builder* to disk, not assign the classmethod result.
    builder.to_json(exp_path / "config.json")   # ← self-annotated bug
    _logger.info("Wrote minimal config to %s", exp_path / "config.json")
return builder
```

The comment `# BUGFIX: this should write *builder* to disk, not assign the classmethod result` was written to flag an issue but the fix was left in place as-is. The actual call `builder.to_json(...)` appears correct at this location, but the comment suggests the original intent was something different — specifically that `ConfigBuilder.minimal_config()` returns a class-level object that should not be assigned. The self-annotation indicates this was known to the developer but not resolved.

---

## Medium Issues (Yellow)

> Design flaws, likely survivable but problematic.

---

### MED-01 — Duplicate Utility Functions: `create_if_frequencies`, `create_clks_array`, Segment Sweep Helpers

**Severity**: Medium  
**Files**: `qubox_v2/experiments/legacy_experiment.py` (lines 85–94) vs `qubox_v2/experiments/experiment_base.py` (lines 52–71)

**Evidence**:
```
experiments/legacy_experiment.py:85:  def create_if_frequencies(...)
experiments/experiment_base.py:52:    def create_if_frequencies(...)

experiments/legacy_experiment.py:94:  def create_clks_array(...)
experiments/experiment_base.py:71:    def create_clks_array(...)
```

And sweep-segment helpers:
```
experiments/legacy_experiment.py:47:   _make_lo_segments()
experiments/legacy_experiment.py:62:   _if_frequencies_for_segment()
experiments/legacy_experiment.py:67:   _merge_segments()

experiments/experiment_base.py:100:    make_lo_segments()
experiments/experiment_base.py:...:    if_freqs_for_segment()
experiments/experiment_base.py:...:    merge_segment_outputs()
```

Both sets coexist as separate, independent copies. The `legacy_experiment.py` versions are private (`_`) with slightly different signatures and no runtime warnings. New experiments import from `experiment_base.py` while the legacy god-class uses its own. Any bug fixes must be applied to both.

---

### MED-02 — `cQED_Experiment` God-Class: 5,214 Lines, 112 Methods

**Severity**: Medium  
**File**: `qubox_v2/experiments/legacy_experiment.py`

```
$ wc -l qubox_v2/experiments/legacy_experiment.py
5214 qubox_v2/experiments/legacy_experiment.py

$ grep -c "def " qubox_v2/experiments/legacy_experiment.py
112
```

`cQED_Experiment` (class definition begins at line 216) combines hardware control, pulse management, device management, readout calibration, spectroscopy, coherence measurement, state tomography, gate calibration, and artifact persistence in a single class. It duplicates every sweep helper, segment merge function, and frequency calculation present in the newer modular architecture.

Despite the new `SessionManager` + `ExperimentBase` architecture, `cQED_Experiment` is actively used in production notebooks (import exists in `experiments/legacy_experiment.py`) and is maintained in parallel. This creates a persistent dual-maintenance burden.

---

### MED-03 — `ReadoutQuality.alpha` and `.beta` Fields Are Orphaned (Never Populated)

**Severity**: Medium  
**Files**: `qubox_v2/calibration/models.py` (lines 52–53); `qubox_v2/calibration/patch_rules.py` (class `ReadoutQualityRule`, line 218)

**Evidence**:
```python
# models.py:52-53
class ReadoutQuality(BaseModel):
    alpha: float | None = None    # ← never written by any patch rule
    beta: float | None = None     # ← never written by any patch rule
    F: float | None = None
    Q: float | None = None
    V: float | None = None
    t01: float | None = None
    t10: float | None = None
```

```python
# patch_rules.py:218-222 — ReadoutQualityRule
for field in ("F", "Q", "V", "t01", "t10"):
    if field in params:
        patch.add(...)
# alpha, beta are never in this loop
```

`analysis/metrics.py::butterfly_metrics()` also does not produce `alpha` or `beta` keys in its Output. The fields exist in the schema, in the JSON, and in documentation but are never written by the pipeline. Any code reading `quality.alpha` will always get `None`.

---

### MED-04 — Orchestrator Quality Gate Is Ineffective for Readout Experiments

**Severity**: Medium  
**File**: `qubox_v2/calibration/orchestrator.py`, `analyze()` (lines 57–65)

**Evidence**:
```python
quality = {}
if getattr(out, "fit", None) is not None:
    fit = out.fit
    quality["r_squared"] = getattr(fit, "r_squared", None)
r_sq = quality.get("r_squared")
if r_sq is not None and r_sq < 0.5:
    quality["passed"] = False
    quality["failure_reason"] = f"r_squared={r_sq:.3f} < 0.5"
else:
    quality["passed"] = True   # ← also True when r_sq is None!
```

For any experiment where `AnalysisResult.fit` is `None` (e.g., `ReadoutGEDiscrimination`, `ReadoutButterflyMeasurement`, `AllXY`, `IQBlob`), `quality["passed"]` is always `True`. The quality gate only operates for curve-fitting experiments.

Additionally, `r_squared < 0.5` is a very lenient threshold for a calibration pass/fail decision — a poor fit with r² = 0.4 produces `passed=False`, but r² = 0.51 still passes.

---

### MED-05 — `T1Rule` Unit Detection Heuristic Is Fragile Near 1 ms

**Severity**: Medium  
**File**: `qubox_v2/calibration/patch_rules.py`, class `T1Rule` (lines 65–76)

**Evidence**:
```python
elif "T1" in params:
    t1_raw = float(params["T1"])
    # Heuristic: physical T1 values in seconds are < 1e-3 (< 1 ms).
    # Anything above 1e-3 is assumed to be in nanoseconds.
    t1_s = t1_raw * 1e-9 if t1_raw > 1e-3 else t1_raw
```

A qubit with T1 = 1.5 ms would report `T1 = 1.5e-3 seconds`, which is ≤ 1e-3, causing the rule to interpret it as seconds and store `T1 = 1.5e-3` s — **correct by coincidence**. A qubit with T1 = 2 ms would report `T1 = 2e-3`, which passes the `> 1e-3` check, so the rule multiplies by 1e-9 and stores `T1 = 2e-12` s — catastrophically wrong.

In practice, `T1Relaxation.analyze()` always produces `T1_s` and `T1_ns` explicitly, so this branch is not triggered in the primary flow. But the heuristic is available for any legacy or third-party experiment that uses the bare `T1` key.

---

### MED-06 — `ReadoutConfig.validate()` Only Accepts Single Values for "Method" Fields

**Severity**: Medium  
**File**: `qubox_v2/experiments/calibration/readout_config.py`, `ReadoutConfig.validate()` (lines 70–88)

**Evidence**:
```python
if self.rotation_method not in {"optimal"}:
    raise ValueError(
        "rotation_method={self.rotation_method!r} not supported; only 'optimal' is valid"
    )
if self.weight_extraction_method not in {"legacy_ge_diff_norm"}:
    raise ValueError(...)
if self.histogram_fitting not in {"two_state_discriminator"}:
    raise ValueError(...)
if self.threshold_extraction not in {"legacy_discriminator"}:
    raise ValueError(...)
```

Each validator accepts exactly one value. The set notation `{"optimal"}` and the docstring `"only 'optimal' is valid"` make clear these fields are configuration stubs with no real polymorphism. Downstream code has no dispatch on these values — they read the configuration but always use the hardcoded implementation. The fields and their validators add complexity without enabling any variation.

---

### MED-07 — `ExperimentBase.attr` Duck-Types Two Different Context Classes

**Severity**: Medium  
**File**: `qubox_v2/experiments/experiment_base.py`, `ExperimentBase.__init__` and property accessors (lines 157–200)

**Evidence**:
```python
@property
def attr(self) -> cQED_attributes:
    a = getattr(self._ctx, "attributes", None)
    if a is None:
        raise RuntimeError(
            "Experiment context has no 'attributes'. Ensure cqed_params.json ..."
        )
    return a

@property
def pulse_mgr(self) -> PulseOperationManager:
    pm = getattr(self._ctx, "pulseOpMngr",
                 getattr(self._ctx, "pulse_mgr", None))
    ...
```

`ExperimentBase` accepts either a `cQED_Experiment` (legacy, uses `pulseOpMngr`) or a `SessionManager`/`ExperimentRunner` (new, uses `pulse_mgr`) as context. The `pulseOpMngr` vs `pulse_mgr` attribute divergence means that any new context type must either use one of these specific attribute names or `ExperimentBase` will silently fail at runtime when `pulse_mgr` is first accessed.

`_ctx` has type `Any` with no Protocol enforcement at construction time.

---

### MED-08 — `T2_star_us` Name Is Inconsistent with Its Canonical `T2_ramsey` Partner

**Severity**: Medium  
**File**: `qubox_v2/calibration/models.py`, class `CoherenceParams` (lines 118–121)

**Evidence**:
```python
T2_ramsey: float | None = None    # seconds
T2_star_us: float | None = None   # microseconds (convenience, from Ramsey)
T2_echo: float | None = None      # seconds
T2_echo_us: float | None = None   # microseconds
```

The canonical seconds-field is `T2_ramsey` but its µs companion is `T2_star_us`. They use different naming conventions (`ramsey` vs `star`). This makes it non-obvious that they refer to the same physical quantity. In contrast, `T2_echo`/`T2_echo_us` is consistently named.

Downstream code must know to look for `T2_star_us` when working with `T2_ramsey`, increasing the cognitive overhead and risk of reading the wrong field.

---

## Low Issues (Green)

> Style, clarity, or maintainability only.

---

### LOW-01 — Hard-Coded Element/Operation Names in `simulation.py`

**Severity**: Low  
**File**: `qubox_v2/programs/builders/simulation.py`, line 34

```python
sequenceMacros.conditional_reset_ground(
    I, thr=measureMacro._ro_disc_params["threshold"],
    r180="x180",       # hard-coded
    qb_el="qubit"      # hard-coded
)
```

Any system that uses element names other than `"qubit"` or pulse names other than `"x180"` will silently build a broken QUA program (using the wrong element/operation) or raise a `KeyError` at runtime.

---

### LOW-02 — `cqed_params.json` / `cQED_attributes` Still the Primary Source of Element Names

**Severity**: Low  
**File**: `qubox_v2/analysis/cQED_attributes.py` (lines 31–33); `qubox_v2/experiments/experiment_base.py` (line 185)

Despite the new `ChannelRef` / `ExperimentBindings` binding-driven API, the majority of experiments still rely on `self.attr.qb_el`, `self.attr.ro_el`, `self.attr.st_el` string names from `cqed_params.json` for all hardware targeting. The binding system is opt-in and not yet the default path.

---

### LOW-03 — `CoherenceParams.qb_therm_clks` Is Stored in Both `coherence` and `cQED_attributes`

**Severity**: Low  
**Files**: `qubox_v2/calibration/models.py` (line 123); `qubox_v2/analysis/cQED_attributes.py` (line 44)

```python
# calibration/models.py
class CoherenceParams:
    qb_therm_clks: int | None = None

# analysis/cQED_attributes.py
class cQED_attributes:
    qb_therm_clks: Optional[int] = None
```

`qb_therm_clks` is the qubit thermalization wait. It appears in both the calibration store and in `cQED_attributes`. There is no documented synchronization protocol between these two locations. If an experiment reads `attr.qb_therm_clks` but the calibration store was updated via a T1 patch, the two values may diverge.

---

### LOW-04 — `ReadoutQuality.alpha`/`.beta` Comment References Old Butterfly Nomenclature

**Severity**: Low  
**File**: `qubox_v2/calibration/models.py`, line 52–53

```python
alpha: float | None = None
beta: float | None = None
```

These fields appear to be remnants of an earlier butterfly analysis output notation (`alpha`/`beta` as P(0|0) and P(1|1) style metrics). The current `butterfly_metrics()` function in `analysis/metrics.py` uses `F`, `Q`, `V`, `t01`, `t10` nomenclature. The `alpha`/`beta` fields are unreachable dead code.

---

### LOW-05 — `DiscriminationParams` Has Separate `n_shots`, `integration_time_ns` Metadata That Is Never Populated via Pipeline

**Severity**: Low  
**File**: `qubox_v2/calibration/models.py`, class `DiscriminationParams` (lines 42–46)

```python
n_shots: int | None = None
integration_time_ns: int | None = None
demod_weights: list[str] | None = None
state_prep_ops: list[str] | None = None
```

These metadata fields (also present in `ReadoutQuality`) were added in schema v1.6.0 for reproducibility purposes. However, `DiscriminationRule` in `patch_rules.py` only patches `angle`, `threshold`, `fidelity`, `sigma_g`, `sigma_e`, `mu_g`, `mu_e` — none of the provenance metadata fields. They remain `None` in all stored calibrations.

---

### LOW-06 — `WeightLabel` Enum Defined but Integration-Weight Keys Are Bare Strings Throughout

**Severity**: Low  
**File**: `qubox_v2/core/types.py` (lines 30–34); everywhere integration weights are referenced

```python
class WeightLabel(str, Enum):
    COS = "cos"
    SIN = "sin"
    MINUS_SIN = "minus_sin"
```

This enum is defined in `core/types.py` but integration weight labels are passed as bare strings ("cos", "sin", "minus_sin") everywhere else — in `PulseOperationManager`, `measureMacro`, `ReadoutConfig`, `ReadoutBinding`, and QUA program builders. The enum is never used for type safety.

---

## Architectural Observations

### 1. Dual-Architecture Technical Debt

The codebase runs two parallel architectures simultaneously:

| Path | Entry Point | Size | Status |
|------|-------------|------|--------|
| Legacy | `cQED_Experiment` (`legacy_experiment.py`) | 5,214 lines | Active, not deprecated |
| New | `SessionManager` + `ExperimentBase` subclasses | ~40 files | Preferred, growing |

The `ExperimentBase.attr` duck-type pattern (MED-07) is the bridge between them. New experiments (`T2Ramsey`, `ReadoutGEDiscrimination`, etc.) all subclass `ExperimentBase` and work with both contexts, which is good. However, `cQED_Experiment` reimplements sweep helpers, config loading, and readout pipeline independently.

### 2. The Patch Pipeline Is Correct by Design but Has Implementation Gaps

The `Run → Artifact → CalibrationResult → Patch → Apply` flow in `CalibrationOrchestrator` is architecturally clean and correct. The Patch object with named `UpdateOp` operations (`SetCalibration`, `SetPulseParam`, `TriggerPulseRecompile`, etc.) is an excellent design for auditability and dry-run previewing.

The gaps are:
- The quality gate for non-fitting experiments is absent (MED-04).
- The T2 unit mismatch via `proposed_patch_ops` means the patch writes a wrong value (HIGH-01).

### 3. `measureMacro` Is a Design Antipattern

`measureMacro` is a class-level configuration singleton — effectively a global. The `sync_from_calibration()` method was introduced (per `CHANGELOG.md` v1.4.0) to solve the "dual-truth" problem between `CalibrationStore` and `measureMacro`. This is a correct mitigation, but the underlying problem remains: readout state is global.

The bindings system (`core/bindings.py`, `ReadoutBinding`) provides a proper alternative: `ReadoutBinding.discrimination` and `ReadoutBinding.quality` dicts replace `measureMacro._ro_disc_params` / `_ro_quality_params`. But this API is not yet adopted across the full experiment surface.

### 4. `SessionState` / `ArtifactManager` Are Well-Designed but Opt-In Only

`SessionState` (`core/session_state.py`) — the frozen, hashable, build-hash-stamped config snapshot — and `ArtifactManager` (`core/artifact_manager.py`) — build-hash-keyed artifact storage — are both well-designed. However, they are not yet wired into `SessionManager.__init__()` automatically. Their use is voluntary.

---

## API Consistency Review

### Naming Conventions

| Category | Convention Used | Consistency |
|----------|----------------|-------------|
| Calibration kind strings | Inconsistent: `"t1"`, `"t2_ramsey"`, `"t2_echo"` (lowercase with underscores) vs `"ReadoutGEDiscrimination"`, `"ReadoutButterflyMeasurement"` (PascalCase) | ❌ Mixed |
| Pulse name prefix | `ge_`, `ef_` prefixes enforced via `transitions.py` | ✅ Consistent |
| Element attributes | `qb_el`, `ro_el`, `st_el` in `cQED_attributes`; `physical_id` in `ChannelRef` | ⚠️ Dual system |
| Calibration store keys | Physical channel IDs (`con1:analog_in:1`) in v5.0.0; legacy element names via alias | ✅ Versioned |

### Return Types

All `ExperimentBase` subclasses return `RunResult` from `run()` and `AnalysisResult` from `analyze()` — consistent.  
`CalibrationOrchestrator.analyze()` returns `CalibrationResult` — distinct from `AnalysisResult` but consistently typed.

### Artifact Naming

`Artifact.name` is set to `exp.__class__.__name__` in `CalibrationOrchestrator.run_experiment()` (line 18). This means the artifact file is named by class (e.g., `T1Relaxation_20250714_123456.npz`), which is convenient but not unique if the same experiment class is run multiple times in one session.

---

## Calibration Pipeline Integrity Review

### Run → Artifact → CalibrationResult → Patch → Apply

```
ExperimentBase.run()          → RunResult (output dict)
Orchestrator._artifact_from_result()  → Artifact (data + meta)
Orchestrator.persist_artifact()       → .npz + .meta.json on disk
Orchestrator.analyze()                → CalibrationResult (kind + params + quality)
Orchestrator.build_patch()            → Patch (list[UpdateOp])
Orchestrator.apply_patch(dry_run=True) → preview dict (no mutations)
Orchestrator.apply_patch(dry_run=False) → mutations to CalibrationStore + pulse recompile
```

The pipeline design is correct. Key integrity gaps:

1. **T2 unit mismatch in-flight** (HIGH-01): `T2Ramsey.analyze()` and `T2Echo.analyze()` populate `proposed_patch_ops` in metadata with raw ns values. `WeightRegistrationRule` applies these after `T2RamseyRule`/`T2EchoRule` (which correctly convert ns→s), overwriting the correct seconds value with ns. The in-memory and on-disk value is wrong until the session is restarted.

2. **Quality gate ineffective for non-fitting experiments** (MED-04): For readout experiments with no `fit` object (e.g., `ReadoutGEDiscrimination`), `quality["passed"]` is always `True` regardless of actual IQ blob quality. The guard in `run_analysis_patch_cycle` is correct, but the quality gate it relies on is meaningless for these experiments.

3. **No rollback mechanism**: There is no `undo` or transaction boundary. `CalibrationStore.snapshot()` must be called manually before a patch cycle to enable rollback.

### Patch Rule Coverage

All standard calibration flows have corresponding patch rules in `default_patch_rules()`:

| Calibration Kind | Rule | Status |
|-----------------|------|--------|
| `"t1"` | `T1Rule` | ✅ |
| `"t2_ramsey"` | `T2RamseyRule` + `WeightRegistrationRule` | ⚠️ (unit bug HIGH-01: proposed_patch_ops ns→WeightRegistrationRule overwrites) |
| `"t2_echo"` | `T2EchoRule` + `WeightRegistrationRule` | ⚠️ (unit bug HIGH-01: same as above) |
| `"qubit_freq"` | `FrequencyRule(field="qubit_freq")` | ✅ |
| `"ef_freq"` | `FrequencyRule(field="ef_freq")` | ✅ |
| `"resonator_freq"` | `FrequencyRule(field="resonator_freq")` | ✅ (`resonator_freq` field present in `ElementFrequencies`) |
| `"pi_amp"` | `PiAmpRule` | ✅ |
| `"drag_alpha"` | `DragAlphaRule` | ✅ |
| `"pulse_train"` | `PulseTrainRule` | ✅ |
| `"ReadoutGEDiscrimination"` | `DiscriminationRule` | ✅ (no quality gate: MED-04) |
| `"ReadoutWeightsOptimization"` | `WeightRegistrationRule` | ✅ |
| `"ReadoutButterflyMeasurement"` | `ReadoutQualityRule` | ✅ (alpha/beta orphaned: MED-03) |

---

## Hardware Abstraction Review

### Layered Architecture

`ConfigEngine` (`hardware/config_engine.py`) correctly implements a 5-layer config merge:
1. `hardware_base` — parsed `hardware.json`
2. `hardware_extras` — `__qubox`, `octave_links`
3. `pulse_overlay` — generated by `PulseOperationManager`
4. `element_ops_overlay` — element→operation mappings
5. `runtime_overrides` — ephemeral patches

This separation is clean and auditable. `build_qm_config()` produces a deterministic merge with `deep_merge()`.

### Channel Binding System

`ChannelRef` (`core/bindings.py`) provides stable physical identity (e.g., `con1:analog_out:3`). `ReadoutBinding` pairs `OutputBinding` + `InputBinding` and replaces the `measureMacro` singleton for new-style experiments. The `alias_index` in `CalibrationData` maps human-friendly names to physical IDs.

**Gap**: The binding-driven path (`measure_with_binding()`) and the legacy `measureMacro`-driven path coexist without forcing migration. The `ExperimentBase` binding accessor (`self._bindings_or_none`) is optional — experiments that don't use it fall back to element name strings.

### `hardware.json` as Source of Truth

`ConfigEngine.wiring_rev` computes a SHA-256 hash of `hardware.json` content, providing a stable identifier for the hardware configuration. `CalibrationStore._validate_context()` checks `wiring_rev` against stored context, raising `ContextMismatchError` if the hardware changed between calibration runs.

This is a strong protection against using stale calibrations after hardware rewiring.

---

## Recommended Strategic Improvements (Non-Breaking)

### 1. Fix T2 Unit Mismatch in `proposed_patch_ops` (HIGH-01)

In `T2Ramsey.analyze()` and `T2Echo.analyze()` (`experiments/time_domain/coherence.py`), convert the fit value to seconds before populating `proposed_patch_ops`:
```python
# coherence.py — T2Ramsey.analyze() proposed_patch_ops correction
"value": float(fit.params["T2"]) * 1e-9,   # ns → s
```
This ensures the `WeightRegistrationRule` path also produces the correct seconds value, and eliminates the overwrite race with `T2RamseyRule`/`T2EchoRule`. Alternatively, suppress the `SetCalibration` ops for `T2_ramsey`/`T2_echo` from `proposed_patch_ops` entirely and rely solely on the dedicated `T2RamseyRule`/`T2EchoRule` which already perform the conversion correctly.

### 2. Replace Bare Dict Access with `.get()` for `threshold` (CRIT-02)

In `programs/builders/readout.py:668` and `programs/builders/simulation.py:34`, change:
```python
thr = measureMacro._ro_disc_params["threshold"]
```
to:
```python
thr = measureMacro._ro_disc_params.get("threshold") or 0.0
```
And add a warning log if the value was `None`.

### 3. Add Explicit Quality Metric for Readout Experiments (MED-04)

`ReadoutGEDiscrimination.analyze()` should populate `metadata["quality"]` with a fidelity-based threshold (e.g., `passed = fidelity > 85.0`). `CalibrationOrchestrator.analyze()` should extract this if present. One approach: extend `AnalysisResult` to carry a `quality_passed: bool` flag.

### 4. Consolidate Duplicate Utility Functions (MED-01)

Remove `create_if_frequencies`, `create_clks_array`, `_make_lo_segments`, `_if_frequencies_for_segment`, `_merge_segments` from `legacy_experiment.py` and have it import from `experiment_base.py`. This requires verifying that signatures are compatible (they are nearly identical already).

---

## Long-Term Refactor Suggestions

### 1. Complete the `ExperimentBase` Migration; Deprecate `cQED_Experiment`

The most impactful long-term improvement is completing the modular experiment architecture and issuing a formal deprecation of `cQED_Experiment`. The path is clear: every experiment method in `legacy_experiment.py` that duplicates an `ExperimentBase` subclass in `experiments/` can be removed.

A staged approach:
1. Add `DeprecationWarning` to `cQED_Experiment.__init__()`.
2. Audit all 112 methods; identify those not yet covered by `ExperimentBase` subclasses.
3. Port remaining methods.
4. Remove `legacy_experiment.py` in a major version bump.

### 2. Migrate `measureMacro` to Instance-Level State

Replace the class-level singleton with an instance that is owned by `SessionManager` (or `ExperimentBase`). The `ReadoutBinding.discrimination` dict in `core/bindings.py` already provides the correct blueprint. Transition path:
1. Make `measureMacro` instantiable (move all class attributes to `__init__`).
2. Store the instance on `SessionManager` as `self.measure_macro`.
3. Expose via `ExperimentBase.measure_macro` property.
4. Phase out `measureMacro._ro_disc_params` class access over 1-2 releases.

### 3. Enforce Quality Gates as Part of Patch Construction

Move quality evaluation from `CalibrationOrchestrator.analyze()` into each `PatchRule.__call__()`. If the rule can't produce a patch (quality too low, params out of range), it returns `None`. This makes quality gating automatic for every rule rather than requiring callers to check the returned dict.

### 4. Adopt `SessionState` as the Required First Step

Wire `SessionState.from_config_dir()` into `SessionManager.__init__()` unconditionally, making it the canonical record of what config files were loaded. Currently it's available but optional. Making it mandatory would eliminate the possibility of sessions running without build-hash traceability.

### 5. Unify Artifact Naming with `ArtifactManager`

The current artifact path (`artifacts/runtime/{name}_{ts}.npz`) is flat and does not use build hashes. Switching to `ArtifactManager` (which keys under `artifacts/{build_hash}/`) would make all artifacts traceable to the exact configuration that produced them.

### 6. Replace `cqed_params.json` Element Name Dependency with `ExperimentBindings`

The `cQED_attributes.qb_el`, `.ro_el`, `.st_el` string names are the last major dependency on the legacy naming layer. The `ExperimentBindings` system in `core/bindings.py` provides element-name-free physical-channel-identity-based targeting. A migration path exists: `SessionManager.bindings` is already available and `ExperimentBase` exposes `self._bindings_or_none`. Completing this migration would make experiments fully portable across hardware configurations without manual `cqed_params.json` editing.

---

*Report generated by read-only static analysis of all Python source files under `qubox_v2/`. No source files were modified. All file references are absolute paths relative to repository root `/home/runner/work/qubox/qubox/`.*
