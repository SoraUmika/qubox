# Hardware Acceptance Checklist

**Purpose:** Verify that the refactored qubox_v2 declarative architecture operates correctly on real quantum hardware before production use.

**Prerequisites:**
- All offline audit checks pass (`python audit_offline.py` -- 161/166 minimum)
- OPX hardware connected and responsive
- Quantum Machine Manager (QMM) accessible
- Qubit(s) at known operating point (from prior calibration)

---

## Phase 1: Connectivity & Basic I/O

### 1.1 QMM Connection
- [ ] `QuantumMachinesManager()` connects without error
- [ ] `qmm.list_open_quantum_machines()` returns expected list
- [ ] Network latency to OPX < 50ms

### 1.2 Hardware Config Upload
- [ ] `SessionState.from_config_dir("seq_1_device/config")` succeeds (build hash matches offline audit)
- [ ] `qmm.open_qm(hardware_config)` succeeds
- [ ] No waveform overflow errors on upload
- [ ] Element count matches expected (resonator, qubit, qubit2, storage)

### 1.3 Constant Pulse Smoke Test
- [ ] Play `constant` pulse on qubit element (amplitude=0.1, length=100ns)
- [ ] Oscilloscope or internal ADC confirms output amplitude within 5% of expected
- [ ] Play `zero` pulse -- output is flat zero
- [ ] Play `constant` on resonator element -- output confirmed

---

## Phase 2: Waveform Fidelity

### 2.1 DRAG Gaussian Verification
- [ ] Compile `ref_r180` pulse via PulseFactory
- [ ] Upload and play on qubit element
- [ ] Captured I/Q trace matches compiled waveform (L2 < 1e-6 after scaling for DAC/ADC gain)
- [ ] Repeat for `x90`, `y180` -- rotation-derived pulses play correctly

### 2.2 Flat-Top Pulse Verification
- [ ] Compile flat-top Gaussian (amplitude=0.2, flat=200ns, rise_fall=20ns)
- [ ] Play and capture -- flat region stable within 1% of target amplitude
- [ ] Rise/fall edges are smooth (no discontinuities)

### 2.3 Integration Weights Verification
- [ ] Upload integration weights for readout
- [ ] Verify weight segments are correctly timed (multiples of 4ns)
- [ ] Run single-shot readout -- returns I/Q values (not NaN or zero)

---

## Phase 3: Calibration State Machine on Hardware

### 3.1 Power Rabi (Minimal Calibration Cycle)
- [ ] Create `CalibrationStateMachine(experiment="hw_power_rabi")`
- [ ] Walk through: IDLE -> CONFIGURED -> ACQUIRING -> ACQUIRED -> ANALYZING -> ANALYZED
- [ ] Verify state transitions match expected sequence
- [ ] Generate CalibrationPatch from Rabi fit
- [ ] Attach patch, walk to PENDING_APPROVAL
- [ ] `is_committable()` returns True with valid fit (R^2 > 0.95)

### 3.2 Patch Application
- [ ] Commit patch to calibration store
- [ ] Verify calibration.json updated with new amplitude
- [ ] Roll back patch
- [ ] Verify calibration.json reverted to original value

### 3.3 Abort Path
- [ ] Start new calibration, transition to ACQUIRING
- [ ] Call `abort("hardware test abort")`
- [ ] Verify state is ABORTED
- [ ] Verify no partial writes to calibration store

---

## Phase 4: Full Calibration Loop

### 4.1 Readout Optimization
- [ ] Run `ReadoutWeightsOptimization` experiment
- [ ] Verify GE discrimination fidelity > 90%
- [ ] Verify integration weights updated correctly
- [ ] Verify SNR matches or exceeds offline synthetic benchmark (SNR > 1.0)

### 4.2 Qubit Spectroscopy + Rabi + Ramsey
- [ ] Run spectroscopy -- find qubit frequency
- [ ] Run Power Rabi -- find pi-pulse amplitude
- [ ] Run Ramsey -- verify T2* measurement
- [ ] All three use CalibrationStateMachine lifecycle without errors
- [ ] All three produce valid CalibrationPatches

### 4.3 Multi-Experiment Sequence
- [ ] Run 3+ calibrations in sequence without restarting QM
- [ ] Verify each builds fresh SessionState with correct build_hash
- [ ] Verify artifact directories created with unique build hashes
- [ ] Verify no state leakage between experiments (each starts IDLE)

---

## Phase 5: Artifact & Reproducibility

### 5.1 Artifact Generation
- [ ] After full calibration loop, verify artifact directory exists at `<experiment_path>/artifacts/<build_hash>/`
- [ ] Verify `session_state.json` artifact matches runtime SessionState
- [ ] Verify `generated_config.json` artifact is valid JSON
- [ ] Verify all reports saved as markdown files

### 5.2 Reproducibility
- [ ] Re-run same calibration from saved config -- build_hash identical
- [ ] Load saved dataset from artifact, re-run analysis -- results match
- [ ] Verify no timestamp-dependent behavior in deterministic paths

### 5.3 Cleanup
- [ ] Run `cleanup_artifacts(experiment_path, keep_latest=3)`
- [ ] Verify only 3 most recent build dirs remain
- [ ] Verify no data corruption in remaining artifacts

---

## Phase 6: Legacy Parity (Hardware)

### 6.1 Side-by-Side Waveform Comparison
- [ ] Run legacy code to generate waveforms for: x180, x90, y180, readout
- [ ] Run qubox_v2 PulseFactory to generate same pulses
- [ ] Compare using `legacy_parity.compare_waveforms()`:
  - L2 norm < 1e-10
  - Normalized dot product > 0.999999
  - Peak amplitude difference < 1e-10
  - No sign flips

### 6.2 Side-by-Side Measurement Comparison
- [ ] Run identical Rabi experiment with legacy code and qubox_v2
- [ ] Compare fitted pi-pulse amplitudes -- within 1% of each other
- [ ] Compare raw I/Q distributions -- KL divergence < 0.01

---

## Acceptance Criteria

| Criterion | Threshold | Required? |
|---|---|---|
| All Phase 1 checks pass | 100% | YES |
| All Phase 2 checks pass | 100% | YES |
| All Phase 3 checks pass | 100% | YES |
| Phase 4: GE fidelity | > 90% | YES |
| Phase 4: All calibrations complete | 100% | YES |
| Phase 5: Artifacts generated | 100% | YES |
| Phase 6: Legacy parity L2 | < 1e-10 | YES |
| Phase 6: Measurement agreement | < 1% | RECOMMENDED |

### Sign-Off

| Role | Name | Date | Signature |
|---|---|---|---|
| Developer | | | |
| Hardware Engineer | | | |
| PI / Lead | | | |

---

*Generated as part of qubox_v2 Post-Refactor Stabilization Audit*
