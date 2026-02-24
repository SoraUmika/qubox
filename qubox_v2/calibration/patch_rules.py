from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import CalibrationResult, Patch


def _clone_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: _clone_payload(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [_clone_payload(v) for v in payload]
    if isinstance(payload, tuple):
        return [_clone_payload(v) for v in payload]
    return payload


@dataclass
class PiAmpRule:
    """Build pi-amplitude patch ops and propagate primitive family updates."""

    session: Any
    ref_pulse_name: str = "ref_r180"
    primitive_family: tuple[str, ...] = ("x180", "y180", "x90", "xn90", "y90", "yn90")

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != "pi_amp":
            return None

        params = result.params or {}
        patch = Patch(reason="PiAmpRule", provenance={"kind": result.kind})
        g_pi = params.get("g_pi")
        if g_pi is None:
            return None

        metadata = (result.evidence or {}).get("analysis_metadata", {}) or {}
        target_op = str(metadata.get("target_op", self.ref_pulse_name))

        ref_cal = self.session.calibration.get_pulse_calibration(target_op)
        ref_amp_old = float(getattr(ref_cal, "amplitude", 1.0) or 1.0)
        ref_amp_new = ref_amp_old * float(g_pi)

        patch.add("SetCalibration", path=f"pulse_calibrations.{target_op}.amplitude", value=ref_amp_new)
        patch.add("SetPulseParam", pulse_name=target_op, field="amplitude", value=ref_amp_new)

        patch.add("TriggerPulseRecompile", include_volatile=True)
        return patch


@dataclass
class T1Rule:
    """Build T1 patch ops including optional qb_therm_clks."""

    element: str

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != "t1":
            return None

        params = result.params or {}
        patch = Patch(reason="T1Rule", provenance={"kind": result.kind, "element": self.element})
        if "T1" in params:
            patch.add("SetCalibration", path=f"coherence.{self.element}.T1", value=params["T1"])
        if "T1_us" in params:
            patch.add("SetCalibration", path=f"coherence.{self.element}.T1_us", value=params["T1_us"])
        if "qb_therm_clks" in params:
            patch.add("SetCalibration", path=f"coherence.{self.element}.qb_therm_clks", value=params["qb_therm_clks"])
        return patch if patch.updates else None


@dataclass
class T2RamseyRule:
    """Build Ramsey coherence patch ops with optional frequency correction."""

    element: str

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != "t2_ramsey":
            return None

        params = result.params or {}
        patch = Patch(reason="T2RamseyRule", provenance={"kind": result.kind, "element": self.element})
        if "T2_star" in params:
            patch.add("SetCalibration", path=f"coherence.{self.element}.T2_ramsey", value=params["T2_star"])
        if "T2_star_us" in params:
            patch.add("SetCalibration", path=f"coherence.{self.element}.T2_star_us", value=params["T2_star_us"])
        if "qb_freq_corrected_Hz" in params:
            patch.add("SetCalibration", path=f"frequencies.{self.element}.qubit_freq", value=params["qb_freq_corrected_Hz"])
        return patch if patch.updates else None


@dataclass
class T2EchoRule:
    """Build T2 echo metric patch ops (no required extra mutations)."""

    element: str

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != "t2_echo":
            return None

        params = result.params or {}
        patch = Patch(reason="T2EchoRule", provenance={"kind": result.kind, "element": self.element})
        if "T2_echo" in params:
            patch.add("SetCalibration", path=f"coherence.{self.element}.T2_echo", value=params["T2_echo"])
        if "T2_echo_us" in params:
            patch.add("SetCalibration", path=f"coherence.{self.element}.T2_echo_us", value=params["T2_echo_us"])
        return patch if patch.updates else None


@dataclass
class FrequencyRule:
    """Build qubit/storage spectroscopy frequency patch ops."""

    element: str
    kind: str
    metric_key: str
    field: str = "qubit_freq"

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != self.kind:
            return None

        params = result.params or {}
        if self.metric_key not in params:
            return None
        patch = Patch(reason="FrequencyRule", provenance={"kind": result.kind, "element": self.element})
        patch.add("SetCalibration", path=f"frequencies.{self.element}.{self.field}", value=params[self.metric_key])
        if "kappa" in params:
            patch.add("SetCalibration", path=f"frequencies.{self.element}.kappa", value=params["kappa"])
        return patch


@dataclass
class DragAlphaRule:
    """Build DRAG alpha patch ops with optional primitive propagation."""

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != "drag_alpha":
            return None

        params = result.params or {}
        if "optimal_alpha" not in params:
            return None

        alpha = params["optimal_alpha"]
        metadata = (result.evidence or {}).get("analysis_metadata", {}) or {}
        target_op = str(metadata.get("target_op", "ref_r180"))

        patch = Patch(reason="DragAlphaRule", provenance={"kind": result.kind})
        # Only patch the target reference pulse — derived primitives (x180, y180, …)
        # inherit drag_coeff via the PulseFactory rotation_derived mechanism
        # and must NOT be stored in calibration.json.
        patch.add("SetCalibration", path=f"pulse_calibrations.{target_op}.drag_coeff", value=alpha)
        patch.add("TriggerPulseRecompile", include_volatile=True)
        return patch


@dataclass
class DiscriminationRule:
    """Build discrimination calibration patch ops from GE discrimination metrics."""

    element: str

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != "ReadoutGEDiscrimination":
            return None

        params = result.params or {}
        patch = Patch(reason="DiscriminationRule", provenance={"kind": result.kind, "element": self.element})

        fields = ("angle", "threshold", "fidelity", "sigma_g", "sigma_e")
        for field in fields:
            if field in params:
                patch.add("SetCalibration", path=f"discrimination.{self.element}.{field}", value=params[field])

        if "rot_mu_g" in params:
            mu_g = params["rot_mu_g"]
            if isinstance(mu_g, complex):
                mu_g = [float(mu_g.real), float(mu_g.imag)]
            patch.add("SetCalibration", path=f"discrimination.{self.element}.mu_g", value=mu_g)

        if "rot_mu_e" in params:
            mu_e = params["rot_mu_e"]
            if isinstance(mu_e, complex):
                mu_e = [float(mu_e.real), float(mu_e.imag)]
            patch.add("SetCalibration", path=f"discrimination.{self.element}.mu_e", value=mu_e)

        return patch if patch.updates else None


@dataclass
class ReadoutQualityRule:
    """Build readout quality patch ops from butterfly metrics."""

    element: str

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != "ReadoutButterflyMeasurement":
            return None

        params = result.params or {}
        patch = Patch(reason="ReadoutQualityRule", provenance={"kind": result.kind, "element": self.element})
        for field in ("F", "Q", "V", "t01", "t10"):
            if field in params:
                patch.add("SetCalibration", path=f"readout_quality.{self.element}.{field}", value=params[field])
        return patch if patch.updates else None


@dataclass
class WeightRegistrationRule:
    """Promote strict-mode proposed patch intents into executable ops."""

    allowed_ops: tuple[str, ...] = (
        "SetCalibration",
        "SetPulseParam",
        "SetMeasureWeights",
        "PersistMeasureConfig",
        "TriggerPulseRecompile",
    )

    def __call__(self, result: CalibrationResult) -> Patch | None:
        metadata = (result.evidence or {}).get("analysis_metadata", {}) or {}
        proposed = metadata.get("proposed_patch_ops", []) or []
        if not isinstance(proposed, list):
            return None

        patch = Patch(reason="WeightRegistrationRule", provenance={"kind": result.kind})
        for item in proposed:
            if not isinstance(item, dict):
                continue
            op = str(item.get("op", ""))
            payload = item.get("payload", {})
            if op in self.allowed_ops:
                patch.add(op, **(_clone_payload(payload) if isinstance(payload, dict) else {}))
        return patch if patch.updates else None


@dataclass
class PulseTrainRule:
    """Build pulse-train calibration patch ops (corrected amplitude + phase)."""

    session: Any
    ref_pulse_name: str = "ref_r180"

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != "pulse_train":
            return None

        params = result.params or {}
        corrected_amp = params.get("corrected_amplitude")
        if corrected_amp is None:
            return None

        metadata = (result.evidence or {}).get("analysis_metadata", {}) or {}
        target_op = str(metadata.get("target_op", self.ref_pulse_name))

        patch = Patch(reason="PulseTrainRule", provenance={"kind": result.kind})
        patch.add("SetCalibration", path=f"pulse_calibrations.{target_op}.amplitude", value=corrected_amp)
        patch.add("SetPulseParam", pulse_name=target_op, field="amplitude", value=corrected_amp)

        corrected_phase = params.get("corrected_phase")
        if corrected_phase is not None and abs(corrected_phase) > 1e-12:
            patch.add("SetCalibration", path=f"pulse_calibrations.{target_op}.phase_offset", value=corrected_phase)

        patch.add("TriggerPulseRecompile", include_volatile=True)
        return patch


def default_patch_rules(session) -> dict[str, list[Any]]:
    qb_el = getattr(session.attributes, "qb_el", "qb")
    ro_el = getattr(session.attributes, "ro_el", "rr")
    st_el = getattr(session.attributes, "st_el", "st")

    pi_rule = PiAmpRule(session=session)
    t1_rule = T1Rule(element=qb_el)
    t2r_rule = T2RamseyRule(element=qb_el)
    t2e_rule = T2EchoRule(element=qb_el)
    qb_freq_rule = FrequencyRule(element=qb_el, kind="qubit_freq", metric_key="f0")
    st_freq_rule = FrequencyRule(element=st_el, kind="storage_freq", metric_key="f_storage")
    drag_rule = DragAlphaRule()
    disc_rule = DiscriminationRule(element=ro_el)
    quality_rule = ReadoutQualityRule(element=ro_el)
    weight_rule = WeightRegistrationRule()
    pulse_train_rule = PulseTrainRule(session=session)

    return {
        "pi_amp": [pi_rule, weight_rule],
        "t1": [t1_rule, weight_rule],
        "t2_ramsey": [t2r_rule, weight_rule],
        "t2_echo": [t2e_rule, weight_rule],
        "resonator_freq": [weight_rule],
        "qubit_freq": [qb_freq_rule, weight_rule],
        "storage_freq": [st_freq_rule, weight_rule],
        "drag_alpha": [drag_rule, weight_rule],
        "pulse_train": [pulse_train_rule, weight_rule],
        "ReadoutGEDiscrimination": [disc_rule, weight_rule],
        "ReadoutWeightsOptimization": [weight_rule],
        "ReadoutButterflyMeasurement": [quality_rule, weight_rule],
    }
