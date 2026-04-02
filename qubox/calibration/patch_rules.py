"""qubox.calibration.patch_rules — calibration patch rule classes.

Migrated from ``qubox_v2_legacy.calibration.patch_rules``.
No external dependencies beyond qubox.calibration.

Each rule is a callable ``(CalibrationResult) → Patch | None`` that
translates experiment analysis output into a concrete set of
:class:`~qubox.calibration.contracts.UpdateOp` items.

:func:`default_patch_rules` builds the standard rule registry for a session.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import CalibrationResult, Patch
from .transitions import resolve_pulse_name


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
    """Build pi-amplitude patch ops from a ``pi_amp`` CalibrationResult."""

    session: Any
    ref_pulse_name: str = "ge_ref_r180"

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != "pi_amp":
            return None
        params = result.params or {}
        g_pi = params.get("g_pi")
        if g_pi is None:
            return None

        patch = Patch(reason="PiAmpRule", provenance={"kind": result.kind})
        metadata = (result.evidence or {}).get("analysis_metadata", {}) or {}
        target_op = resolve_pulse_name(
            str(metadata.get("target_op", self.ref_pulse_name))
        )

        ref_cal = self.session.calibration.get_pulse_calibration(target_op)
        ref_amp_old = float(getattr(ref_cal, "amplitude", 1.0) or 1.0)
        ref_amp_new = ref_amp_old * float(g_pi)

        patch.add("SetCalibration", path=f"pulse_calibrations.{target_op}.amplitude", value=ref_amp_new)
        patch.add("SetPulseParam", pulse_name=target_op, field="amplitude", value=ref_amp_new)
        patch.add("TriggerPulseRecompile", include_volatile=True)
        return patch


@dataclass
class T1Rule:
    """Build T1 coherence patch ops."""

    alias: str = "transmon"

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != "t1":
            return None
        params = result.params or {}
        patch = Patch(reason="T1Rule", provenance={"kind": result.kind, "alias": self.alias})

        t1_s = None
        if "T1_s" in params:
            t1_s = float(params["T1_s"])
        elif "T1_ns" in params:
            t1_s = float(params["T1_ns"]) * 1e-9

        if t1_s is not None:
            patch.add("SetCalibration", path=f"cqed_params.{self.alias}.T1", value=t1_s)
        if "T1_us" in params:
            patch.add("SetCalibration", path=f"cqed_params.{self.alias}.T1_us", value=params["T1_us"])
        if "qb_therm_clks" in params:
            patch.add("SetCalibration", path=f"cqed_params.{self.alias}.qb_therm_clks", value=params["qb_therm_clks"])
        return patch if patch.updates else None


@dataclass
class T2RamseyRule:
    """Build T2-Ramsey coherence patch ops."""

    alias: str = "transmon"

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != "t2_ramsey":
            return None
        params = result.params or {}
        patch = Patch(reason="T2RamseyRule", provenance={"kind": result.kind, "alias": self.alias})

        if "T2_star_s" in params:
            patch.add("SetCalibration", path=f"cqed_params.{self.alias}.T2_ramsey", value=float(params["T2_star_s"]))
        elif "T2_star_ns" in params:
            patch.add("SetCalibration", path=f"cqed_params.{self.alias}.T2_ramsey", value=float(params["T2_star_ns"]) * 1e-9)

        if "T2_star_us" in params:
            patch.add("SetCalibration", path=f"cqed_params.{self.alias}.T2_star_us", value=params["T2_star_us"])
        if "qb_freq_corrected_Hz" in params:
            patch.add("SetCalibration", path=f"cqed_params.{self.alias}.qubit_freq", value=params["qb_freq_corrected_Hz"])
        return patch if patch.updates else None


@dataclass
class T2EchoRule:
    """Build T2-echo coherence patch ops."""

    alias: str = "transmon"

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != "t2_echo":
            return None
        params = result.params or {}
        patch = Patch(reason="T2EchoRule", provenance={"kind": result.kind, "alias": self.alias})

        if "T2_echo_s" in params:
            patch.add("SetCalibration", path=f"cqed_params.{self.alias}.T2_echo", value=float(params["T2_echo_s"]))
        elif "T2_echo_ns" in params:
            patch.add("SetCalibration", path=f"cqed_params.{self.alias}.T2_echo", value=float(params["T2_echo_ns"]) * 1e-9)

        if "T2_echo_us" in params:
            patch.add("SetCalibration", path=f"cqed_params.{self.alias}.T2_echo_us", value=params["T2_echo_us"])
        return patch if patch.updates else None


@dataclass
class FrequencyRule:
    """Build frequency calibration patch ops from spectroscopy results."""

    alias: str
    kind: str
    metric_key: str
    field: str = "qubit_freq"

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != self.kind:
            return None
        params = result.params or {}
        if self.metric_key not in params:
            return None
        patch = Patch(reason="FrequencyRule", provenance={"kind": result.kind, "alias": self.alias})
        patch.add("SetCalibration", path=f"cqed_params.{self.alias}.{self.field}", value=params[self.metric_key])
        if "kappa" in params:
            patch.add("SetCalibration", path=f"cqed_params.{self.alias}.kappa", value=params["kappa"])
        return patch


@dataclass
class DragAlphaRule:
    """Build DRAG alpha calibration patch ops."""

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != "drag_alpha":
            return None
        params = result.params or {}
        if "optimal_alpha" not in params:
            return None

        alpha = params["optimal_alpha"]
        metadata = (result.evidence or {}).get("analysis_metadata", {}) or {}
        target_op = resolve_pulse_name(str(metadata.get("target_op", "ge_ref_r180")))

        patch = Patch(reason="DragAlphaRule", provenance={"kind": result.kind})
        patch.add("SetCalibration", path=f"pulse_calibrations.{target_op}.drag_coeff", value=alpha)
        patch.add("TriggerPulseRecompile", include_volatile=True)
        return patch


@dataclass
class DiscriminationRule:
    """Build discrimination calibration patch ops."""

    element: str

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != "ReadoutGEDiscrimination":
            return None
        params = result.params or {}
        patch = Patch(reason="DiscriminationRule", provenance={"kind": result.kind, "element": self.element})

        for field in ("angle", "threshold", "fidelity", "sigma_g", "sigma_e"):
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
    """Pass through experiment-proposed patch ops that use allowed op codes."""

    allowed_ops: tuple[str, ...] = (
        "SetCalibration",
        "SetPulseParam",
        "SetMeasureWeights",
        "SetMeasureDiscrimination",
        "SetMeasureQuality",
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
    """Build pulse-train tomography correction patch ops."""

    session: Any
    ref_pulse_name: str = "ge_ref_r180"

    def __call__(self, result: CalibrationResult) -> Patch | None:
        if result.kind != "pulse_train":
            return None
        params = result.params or {}
        corrected_amp = params.get("corrected_amplitude")
        if corrected_amp is None:
            return None

        metadata = (result.evidence or {}).get("analysis_metadata", {}) or {}
        target_op = resolve_pulse_name(str(metadata.get("target_op", self.ref_pulse_name)))

        patch = Patch(reason="PulseTrainRule", provenance={"kind": result.kind})
        patch.add("SetCalibration", path=f"pulse_calibrations.{target_op}.amplitude", value=corrected_amp)
        patch.add("SetPulseParam", pulse_name=target_op, field="amplitude", value=corrected_amp)

        corrected_phase = params.get("corrected_phase")
        if corrected_phase is not None and abs(corrected_phase) > 1e-12:
            patch.add("SetCalibration", path=f"pulse_calibrations.{target_op}.phase_offset", value=corrected_phase)
        patch.add("TriggerPulseRecompile", include_volatile=True)
        return patch


def default_patch_rules(session: Any) -> dict[str, list[Any]]:
    """Build the default calibration patch rule registry for *session*.

    Parameters
    ----------
    session
        A session object with ``session.calibration`` (CalibrationStore) and
        ``session.context_snapshot()`` (or ``session.attributes``).

    Returns
    -------
    dict
        Mapping ``kind_str → [rule, ...]``.
    """
    pi_rule = PiAmpRule(session=session)
    t1_rule = T1Rule(alias="transmon")
    t2r_rule = T2RamseyRule(alias="transmon")
    t2e_rule = T2EchoRule(alias="transmon")
    qb_freq_rule = FrequencyRule(alias="transmon", kind="qubit_freq", metric_key="f0")
    ef_freq_rule = FrequencyRule(alias="transmon", kind="ef_freq", metric_key="f0", field="ef_freq")
    ro_freq_rule = FrequencyRule(alias="resonator", kind="resonator_freq", metric_key="f0", field="resonator_freq")
    st_freq_rule = FrequencyRule(alias="storage", kind="storage_freq", metric_key="f_storage")
    drag_rule = DragAlphaRule()
    weight_rule = WeightRegistrationRule()
    pulse_train_rule = PulseTrainRule(session=session)

    ctx = None
    try:
        ctx_snap = getattr(session, "context_snapshot", None)
        ctx = ctx_snap() if callable(ctx_snap) else getattr(session, "attributes", None)
    except Exception:
        pass
    ro_el = getattr(ctx, "ro_el", "rr") if ctx else "rr"
    disc_rule = DiscriminationRule(element=ro_el)
    quality_rule = ReadoutQualityRule(element=ro_el)

    return {
        "pi_amp":                    [pi_rule],
        "t1":                        [t1_rule, weight_rule],
        "t2_ramsey":                 [t2r_rule, weight_rule],
        "t2_echo":                   [t2e_rule, weight_rule],
        "resonator_freq":            [ro_freq_rule, weight_rule],
        "qubit_freq":                [qb_freq_rule, weight_rule],
        "ef_freq":                   [ef_freq_rule, weight_rule],
        "storage_freq":              [st_freq_rule, weight_rule],
        "drag_alpha":                [drag_rule, weight_rule],
        "pulse_train":               [pulse_train_rule],
        "ReadoutGEDiscrimination":   [disc_rule, weight_rule],
        "ReadoutWeightsOptimization":[weight_rule],
        "ReadoutButterflyMeasurement":[quality_rule, weight_rule],
    }
