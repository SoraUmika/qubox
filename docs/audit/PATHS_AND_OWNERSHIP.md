# Paths and Ownership Audit

**Date**: 2026-02-22
**Scope**: Every file on disk involved in qubox_v2 experiment sessions.
For each file: what it stores, who reads it, who writes it, when, and
whether it is device-specific or cooldown-specific.

---

## File Inventory Table

### Source-of-Truth Configuration Files

| # | File | What It Stores | Read By | Written By | When Written | Device-Specific? | Cooldown-Specific? |
|---|------|----------------|---------|------------|--------------|------------------|--------------------|
| 1 | `config/hardware.json` | OPX+ controller topology (analog/digital ports, offsets), Octave RF outputs (LO frequency, source, gain, output mode), element definitions (resonator, qubit, storage — IF frequency, time-of-flight, digital inputs), octave links (RF-out → AO I/Q routing), `__qubox` extras (external LO map, qop_ip) | `ConfigEngine.load_hardware()` (config_engine.py:122-138), `SessionState.from_config_dir()` | `ConfigEngine.save_hardware()` (config_engine.py:140-146), manual edits | Manual edits only; `save_hardware()` called by `HardwareController.apply_changes(save_hardware=True)` but default is `False` | **Yes** — defines which physical ports/LOs are connected | **No** — wiring does not change between cooldowns (typically) |
| 2 | `config/calibration.json` | Typed calibration data (schema v3.0.0): discrimination params per element (threshold, angle, mu_g, mu_e, sigma, fidelity, confusion matrix), readout quality per element (F, Q, V, t01, t10), frequencies per element (lo_freq, if_freq, qubit_freq, anharmonicity, fock_freqs, chi, kappa, kerr), coherence per element (T1, T2_ramsey, T2_echo), pulse calibrations per pulse (amplitude, length, sigma, drag_coeff), fit history, pulse train results, fock SQR calibrations, multi-state calibration, timestamps | `CalibrationStore._load_or_create()` (store.py:71-83), `SessionState.from_config_dir()`, experiments via `calibration_store.get_*()` | `CalibrationStore.save()` (store.py:288-293), `_touch()` auto-save (store.py:348-352), `CalibrationOrchestrator.apply_patch()` (orchestrator.py:217) | On `SessionManager.close()` (session.py:501), every `set_*()` if auto_save, after orchestrator patch apply | **Yes** — keyed by element names from this device | **Should be** but currently **no** — no cooldown scoping |
| 3 | `config/pulses.json` | Compiled pulse definitions: waveforms (constant/arbitrary with sample arrays), pulse entries (operation type, length, I/Q waveform refs, digital marker), integration weights (cosine/sine segment arrays), element-operation mappings (element → op → pulse name) | `PulseOperationManager.from_json()` (session.py:117), `SessionState.from_config_dir()` | `PulseOperationManager.save_json()` via `SessionManager.save_pulses()` (session.py:288-294), `CalibrationOrchestrator.apply_patch()` (orchestrator.py:218) | On `SessionManager.close()` (session.py:494), after orchestrator patch apply | **Yes** — pulses tied to element names/wiring | **Partially** — amplitudes are cooldown-dependent |
| 4 | `config/measureConfig.json` | Readout macro state (v5): current pulse operation binding (element, op, pulse name, length, I/Q waveform names, integration weight mapping), demodulation config (dual_demod.full), readout discrimination params (threshold, angle, fidelity), rotated/unrotated blob centroids (mu_g, mu_e, sigma_g, sigma_e), confusion matrix, transition matrix, post-selection config (policy, blob radii, exclusivity), drive frequency | `measureMacro.load_json()` via `SessionManager._load_measure_config()` (session.py:465-477) | `measureMacro.save_json()` via `SessionManager.override_readout_operation()` (session.py:453), `CalibrationOrchestrator.apply_patch()` "PersistMeasureConfig" op (orchestrator.py:206-210), `CalibrateReadoutFull` pipeline | After readout calibration, after `override_readout_operation()`, after orchestrator apply | **Yes** — readout element is device-specific | **Should be** but currently **no** |
| 5 | `config/cqed_params.json` | Physics parameters: element names (ro_el, qb_el, st_el), frequencies (ro_fq, qb_fq, st_fq), linewidths (ro_kappa), dispersive shifts (ro_chi, st_chi, st_chi2, st_chi3), anharmonicity, self-Kerr (st_K), coherence times (qb_T1_relax, qb_T2_ramsey, qb_T2_echo), pulse params (r180_amp, rlen, rsigma), thermalization clocks (ro/qb/st_therm_clks), Fock frequencies, displacement params (b_coherent_amp, b_coherent_len, b_alpha) | `cQED_attributes.load()` via `SessionManager._load_attributes()` (session.py:190-196), `_load_runtime_settings()` fallback (session.py:220-237) | `cQED_attributes.save_json()` via `SessionManager.save_attributes()` (session.py:282-286), `SessionManager.save_output()` (session.py:324) | On `save_attributes()` call, after every `save_output()` | **Yes** — frequencies are device-specific | **Should be** but currently **no** |
| 6 | `config/devices.json` | External instrument declarations: device name, driver (module:Class), backend, connection params (address, port), settings (frequency, power), enabled flag. Current devices: octave_external_lo2 (sc_34F3 @ 7 GHz), octave_external_lo4 (sc_38B5 @ 12 GHz), octodac_bf, sa124b | `DeviceManager.__init__()` via `SessionManager.__init__()` (session.py:129-132) | `DeviceManager.save()`, manual edits | Manual edits; `DeviceManager.save()` after `add_or_update()` | **Yes** — instruments are physically tied to a setup | **No** — instruments don't change between cooldowns |
| 7 | `config/session_runtime.json` | Workflow runtime settings: thermalization clocks (ro/qb/st_therm_clks), displacement reference (b_coherent_amp, b_coherent_len, b_alpha), user-defined runtime settings | `SessionManager._load_runtime_settings()` (session.py:201-239) | `SessionManager.save_runtime_settings()` (session.py:241-247), `set_runtime_setting()` (session.py:252-255) | On `SessionManager.close()` (session.py:498), after `set_runtime_setting(persist=True)` | **Yes** — settings tied to device | **Should be** — therm clocks drift per cooldown |

### Generated Artifacts

| # | File Pattern | What It Stores | Read By | Written By | When Written | Device-Specific? | Cooldown-Specific? |
|---|--------------|----------------|---------|------------|--------------|------------------|--------------------|
| 8 | `data/{tag}_{timestamp}.npz` | Compressed numpy arrays from experiment runs (I/Q data, populations, frequencies, etc.) — large arrays filtered by persistence policy | User analysis (manual), notebook cells | `SessionManager.save_output()` (session.py:296-326) | After each experiment `run()` (optional) | **Yes** | **Yes** (implicitly, by timestamp) |
| 9 | `data/{tag}_{timestamp}.meta.json` | Run metadata: scalar params, config snapshot, persistence policy info (dropped fields), experiment name, timestamp | User analysis (manual), notebook cells | `SessionManager.save_output()` (session.py:319-322) | Same as `.npz` companion | **Yes** | **Yes** (implicitly) |
| 10 | `artifacts/calibration_runs/{tag}_{ts}.json` | Calibration attempt audit record: timestamp, experiment name, calibration_tag, validation passed/errors, fit params/model/r_squared, metrics, run metadata, extra metadata | User review, debug | `ExperimentBase.guarded_calibration_commit()` (experiment_base.py:407-464) | After every calibration commit attempt (pass or fail) | **Yes** | **Yes** (implicitly) |
| 11 | `artifacts/runtime/{name}_{ts}.npz` | Orchestrator-persisted experiment artifacts: compressed arrays from run output (same persistence filter as data/) | Orchestrator replay, debug | `CalibrationOrchestrator.persist_artifact()` (orchestrator.py:226-252) | During orchestrator `run_analysis_patch_cycle()` | **Yes** | **Yes** (implicitly) |
| 12 | `artifacts/runtime/{name}_{ts}.meta.json` | Orchestrator artifact metadata: artifact_id, artifact_meta, persistence info, dropped fields | Orchestrator replay, debug | `CalibrationOrchestrator.persist_artifact()` (orchestrator.py:250-251) | Same as companion | **Yes** | **Yes** (implicitly) |
| 13 | `artifacts/{build_hash}/session_state.json` | Frozen SessionState snapshot: hardware, pulse_specs, calibration, cqed_params dicts, schemas, build_hash, git_commit | Debug, reproducibility audits | `ArtifactManager.save_session_state()` (artifact_manager.py:74-90) | During session setup (notebook cell) | **Yes** | **No** (build_hash is cooldown-agnostic) |
| 14 | `artifacts/{build_hash}/generated_config.json` | Compiled QM config dict (the full config passed to `QuantumMachinesManager.open_qm()`) | Debug, reproducibility audits | `ArtifactManager.save_generated_config()` (artifact_manager.py:92-108) | During session setup | **Yes** | **No** |
| 15 | `artifacts/calibration_candidates/{tag}_{ts}.json` | Proposed calibration snapshots (pre-commit candidates) | Debug, rollback | Various calibration experiments | During calibration analysis | **Yes** | **Yes** (implicitly) |
| 16 | `calibration_db.json` (root-level) | Octave mixer calibration database (IQ imbalance corrections per LO frequency/IF, managed by QM SDK) | `QuantumMachinesManager` (Octave SDK), `ManualMixerCalibrator` | `ManualMixerCalibrator.run()`, Octave auto-calibration | After mixer calibration runs | **Yes** — mixer cal tied to physical Octave unit | **No** — mixer cal survives warmup |

### Snapshot / Backup Files

| # | File Pattern | What It Stores | Read By | Written By | When Written |
|---|--------------|----------------|---------|------------|--------------|
| 17 | `config/calibration_{ts}_{tag}.json` | Timestamped backup of `calibration.json` at a point in time | Manual recovery | `CalibrationStore.snapshot(tag)` (store.py:295-308) | On explicit `snapshot()` call |

---

## Key Observations

### 1. Dual-Truth for Discrimination Params

Readout discrimination parameters (threshold, angle, fidelity, confusion
matrix) exist in **two** files with no enforced sync:

- `config/calibration.json` → `discrimination.<element>.*`
- `config/measureConfig.json` → `current.ro_disc_params.*`

The values can (and do) diverge.  Current `calibration.json` shows
`threshold = -2.07e-5`, while `measureConfig.json` shows
`threshold = -2.42e-5`.

### 2. Dual-Truth for Physics Frequencies

Qubit/resonator/storage frequencies exist in:

- `config/calibration.json` → `frequencies.<element>.*`
- `config/cqed_params.json` → `ro_fq`, `qb_fq`, `st_fq`

There is no enforced sync mechanism.

### 3. No Cooldown-Scoped Files

Every file in the device directory is shared across cooldowns.
There is no directory structure like `cooldowns/<id>/calibration.json`.
The only implicit cooldown boundary is the timestamp in
`calibration.json:last_modified`.

### 4. Write Ordering on Close

`SessionManager.close()` (session.py:482-502) writes in order:

1. `hardware.close()` — releases QM connection
2. Device handles disconnected
3. `save_pulses()` → `pulses.json`
4. `save_runtime_settings()` → `session_runtime.json`
5. `calibration.save()` → `calibration.json`

If the process crashes between steps 3 and 5, pulses may be updated but
calibration may not be (or vice versa), creating an inconsistent state.
