# 2026-04-02_00-19-00_p0_p1_p2_architecture_patches

## Prompt
"lets apply the patch, (we will generally be doing more and more experiments, and they will often be custom, also patch the notebooks for all the changes so far)"

## Response Summary

Applied three architecture improvement patches (P0, P1, P2) addressing the 6.4/10 velocity assessment score.

### P0 — Custom Sweep Loop Generation

Modified `CircuitRunnerV2.compile()` in `circuit_compiler.py` to detect sweep axes from circuit metadata and generate nested QUA `for_()` loops:

- Added `_SweepAxisRuntime` dataclass
- Added 4 helper methods: `_parse_sweep_axes()`, `_emit_sweep_body()`, `_classify_sweep_parameter()`, `_infer_sweep_target()`
- Modified `_lower_idle_gate()` and `_lower_play_pulse()` to be sweep-aware
- Stream processing auto-chains `.buffer(sweep_len).average()` for sweep dimensions
- Updated `lowering.py` to pass `SweepAxis.metadata` through to circuit metadata

### P1 — Template Adapter Coverage (20 → 32)

Added 12 new `LegacyExperimentAdapter` entries to `runtime.py`:
- `qubit.spectroscopy_ef`, `resonator.spectroscopy_x180`, `qubit.sequential_rotations`, `qubit.ramsey_chevron`
- `readout.ge_raw_trace`, `readout.leakage_benchmark`
- `reset.passive_benchmark`
- `storage.ramsey`, `storage.fock_spectroscopy`, `storage.fock_ramsey`, `storage.fock_power_rabi`

Added 11 corresponding library methods to `library.py`.

### P2 — @experiment Decorator

Created `qubox/experiments/decorator.py` with `@experiment()` decorator for lightweight named experiment registration. Exported from `qubox.experiments`.

### Notebooks

Notebook audit confirmed all 28 numbered notebooks are Phase 6+ compliant — no patches needed. Created `28_custom_experiment_guide.ipynb` demonstrating new P0/P1/P2 features.

## Files Modified
- `qubox/programs/circuit_compiler.py` — sweep loop generation + 4 helper methods + sweep-aware gate lowering
- `qubox/backends/qm/lowering.py` — metadata passthrough for SweepAxis
- `qubox/backends/qm/runtime.py` — 12 new adapters + 11 new arg builders
- `qubox/experiments/templates/library.py` — 11 new library methods
- `qubox/experiments/decorator.py` — NEW: @experiment decorator
- `qubox/experiments/__init__.py` — re-export decorator
- `notebooks/28_custom_experiment_guide.ipynb` — NEW: custom experiment guide
- `docs/CHANGELOG.md` — changelog entry

## Validation
- ✅ Import smoke tests: all modules pass
- ✅ 32 adapters registered (verified count and keys)
- ✅ All 11 new library methods verified on correct classes
- ✅ _classify_sweep_parameter: correctly maps frequency/amplitude/delay/other
- ✅ @experiment decorator: registration, lookup, and registry retrieval work
- ⚠️ QM server at 10.157.36.68 not reachable — full simulation test suite could not run
