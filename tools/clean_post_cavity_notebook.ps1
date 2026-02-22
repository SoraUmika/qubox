$ErrorActionPreference = 'Stop'

$in = 'notebooks/post_cavity_experiment.ipynb'
$out = 'notebooks/post_cavity_experiment.cleaned.ipynb'

$nb = Get-Content -Raw -LiteralPath $in | ConvertFrom-Json

$remove = @(
    '50afae8c',
    '02987988',
    '076e51ee',
    'd3f9b3b2',
    '8275f787',
    'a36edddf',
    '2e73494b'
)

$nb.cells = @($nb.cells | Where-Object { $_.id -notin $remove })

$target = $nb.cells | Where-Object { $_.id -eq 'cell-6-4-code' } | Select-Object -First 1
if ($null -eq $target) {
    throw 'Cell cell-6-4-code not found'
}

$target.source = @(
    'from qubox_v2.experiments.calibration.readout import CalibrateReadoutFull',
    'from qubox_v2.experiments.calibration.readout_config import ReadoutConfig',
    'from qubox_v2.calibration.state_machine import (',
    '    CalibrationStateMachine,',
    '    CalibrationState,',
    '    CalibrationPatch,',
    '    PatchValidation,',
    ')',
    '',
    '# --- Readout calibration with state machine lifecycle ---',
    'sm_readout = CalibrationStateMachine(experiment="readout_full")',
    'sm_readout.transition(CalibrationState.CONFIGURED)',
    'sm_readout.transition(CalibrationState.ACQUIRING)',
    '',
    'cal_full = CalibrateReadoutFull(session)',
    'cfg = ReadoutConfig(',
    '    ro_op="readout",',
    '    drive_frequency=attr.ro_fq,',
    '    r180="x180",',
    '    n_samples_disc=50000,',
    '    n_shots_butterfly=50000,',
    '    max_iterations=2,',
    '    adaptive_samples=True,',
    '    gaussianity_warn_threshold=2.0,',
    '    cv_split_ratio=0.2,',
    '    k=2.5,',
    '    M0_MAX_TRIALS=16,',
    ')',
    'result = cal_full.run(config=cfg)',
    '',
    'sm_readout.transition(CalibrationState.ACQUIRED)',
    'sm_readout.transition(CalibrationState.ANALYZING)',
    '',
    'analysis = cal_full.analyze(result, update_calibration=True)',
    'cal_full.plot(analysis)',
    '',
    '# Build readout calibration patch',
    'ge_fidelity = analysis.metrics.get("ge_fidelity", 0)',
    'ge_angle = analysis.metrics.get("ge_angle", 0)',
    'ge_threshold = analysis.metrics.get("ge_threshold", 0)',
    '',
    'readout_patch = CalibrationPatch(experiment="readout_full")',
    'readout_patch.add_change("readout.ge_angle", old_value=None, new_value=float(ge_angle))',
    'readout_patch.add_change("readout.ge_threshold", old_value=None, new_value=float(ge_threshold))',
    'readout_patch.add_change("readout.ge_fidelity", old_value=None, new_value=float(ge_fidelity))',
    '',
    'fid_ok = ge_fidelity > 0.7',
    'readout_patch.validation = PatchValidation(',
    '    passed=fid_ok,',
    '    checks={"fidelity_above_70pct": fid_ok},',
    '    reasons=[] if fid_ok else [f"GE fidelity {ge_fidelity:.2%} below 70%"],',
    ')',
    'readout_patch.metadata = dict(analysis.metrics)',
    'sm_readout.patch = readout_patch',
    '',
    'sm_readout.transition(CalibrationState.ANALYZED)',
    'sm_readout.transition(CalibrationState.PENDING_APPROVAL)',
    '',
    'if readout_patch.is_approved():',
    '    sm_readout.transition(CalibrationState.COMMITTING)',
    '    sm_readout.transition(CalibrationState.COMMITTED)',
    '    am.save_artifact("readout_full_patch", readout_patch.to_dict())',
    'else:',
    '    am.save_artifact("readout_full_candidate", readout_patch.to_dict())',
    '',
    'print("\n--- Calibration Results ---")',
    'print(f"Fidelity:  {ge_fidelity:.2%}")',
    'print(f"Angle:     {ge_angle:.3f} rad")',
    'print(f"Threshold: {ge_threshold:.4f}")',
    'print(f"F (QND):   {analysis.metrics.get(''bfly_F'', 0):.2%}")',
    'print(f"Q:         {analysis.metrics.get(''bfly_Q'', 0):.2%}")',
    'print(f"V:         {analysis.metrics.get(''bfly_V'', 0):.4f}")',
    'print(f"\nState machine: {sm_readout.state.value}")'
)

$nb | ConvertTo-Json -Depth 100 | Set-Content -LiteralPath $out -Encoding UTF8
Write-Host "Wrote $out"