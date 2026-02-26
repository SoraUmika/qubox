"""Focused tests for Phase 2: transition-aware spectroscopy and frequency storage.

Tests verify:
- ElementFrequencies model includes ef_freq field
- _TRANSITION_FREQ_MAP routing correctness
- FrequencyRule routes ef_freq correctly
- default_patch_rules includes ef_freq kind
- Canonical naming contracts for spectroscopy (QubitSpectroscopyEF defaults)
"""
from __future__ import annotations

import pytest

from qubox_v2.calibration.models import ElementFrequencies, CalibrationData
from qubox_v2.calibration.contracts import CalibrationResult, Patch
from qubox_v2.calibration.patch_rules import FrequencyRule, default_patch_rules
from qubox_v2.calibration.transitions import (
    Transition,
    resolve_pulse_name,
    canonical_derived_pulse,
)


# ---------------------------------------------------------------------------
# ElementFrequencies: ef_freq field
# ---------------------------------------------------------------------------

class TestElementFrequenciesEfFreq:
    def test_ef_freq_default_none(self):
        ef = ElementFrequencies()
        assert ef.ef_freq is None

    def test_ef_freq_roundtrip(self):
        ef = ElementFrequencies(qubit_freq=6.15e9, ef_freq=5.894e9)
        assert ef.ef_freq == pytest.approx(5.894e9)
        assert ef.qubit_freq == pytest.approx(6.15e9)

    def test_ef_freq_serialization(self):
        ef = ElementFrequencies(ef_freq=5.894e9)
        d = ef.model_dump(exclude_none=True)
        assert "ef_freq" in d
        assert d["ef_freq"] == pytest.approx(5.894e9)

    def test_ef_freq_omitted_when_none(self):
        ef = ElementFrequencies(qubit_freq=6.15e9)
        d = ef.model_dump(exclude_none=True)
        assert "ef_freq" not in d

    def test_ef_freq_in_calibration_data(self):
        cd = CalibrationData(
            frequencies={"qubit": ElementFrequencies(qubit_freq=6.15e9, ef_freq=5.894e9)}
        )
        assert cd.frequencies["qubit"].ef_freq == pytest.approx(5.894e9)


# ---------------------------------------------------------------------------
# Transition → frequency-field routing map
# ---------------------------------------------------------------------------

class TestTransitionFreqMap:
    def test_ge_route(self):
        from qubox_v2.experiments.spectroscopy.qubit import _TRANSITION_FREQ_MAP
        cal_kind, field = _TRANSITION_FREQ_MAP["ge"]
        assert cal_kind == "qubit_freq"
        assert field == "qubit_freq"

    def test_ef_route(self):
        from qubox_v2.experiments.spectroscopy.qubit import _TRANSITION_FREQ_MAP
        cal_kind, field = _TRANSITION_FREQ_MAP["ef"]
        assert cal_kind == "ef_freq"
        assert field == "ef_freq"


# ---------------------------------------------------------------------------
# FrequencyRule for ef_freq
# ---------------------------------------------------------------------------

class TestFrequencyRuleEf:
    def test_ef_freq_rule_generates_patch(self):
        rule = FrequencyRule(element="qubit", kind="ef_freq", metric_key="f0", field="ef_freq")
        result = CalibrationResult(
            kind="ef_freq",
            transition="ef",
            params={"f0": 5.894e9},
        )
        patch = rule(result)
        assert patch is not None
        assert len(patch.updates) == 1
        op = patch.updates[0]
        assert op.payload["path"] == "frequencies.qubit.ef_freq"
        assert op.payload["value"] == pytest.approx(5.894e9)

    def test_ef_freq_rule_ignores_ge_kind(self):
        rule = FrequencyRule(element="qubit", kind="ef_freq", metric_key="f0", field="ef_freq")
        result = CalibrationResult(kind="qubit_freq", params={"f0": 6.15e9})
        assert rule(result) is None

    def test_ef_freq_rule_ignores_missing_metric(self):
        rule = FrequencyRule(element="qubit", kind="ef_freq", metric_key="f0", field="ef_freq")
        result = CalibrationResult(kind="ef_freq", params={"gamma": 1e6})
        assert rule(result) is None

    def test_ge_freq_rule_unchanged(self):
        rule = FrequencyRule(element="qubit", kind="qubit_freq", metric_key="f0")
        result = CalibrationResult(kind="qubit_freq", params={"f0": 6.15e9})
        patch = rule(result)
        assert patch is not None
        assert patch.updates[0].payload["path"] == "frequencies.qubit.qubit_freq"


# ---------------------------------------------------------------------------
# default_patch_rules includes ef_freq
# ---------------------------------------------------------------------------

class TestDefaultPatchRulesEfFreq:
    def test_ef_freq_kind_registered(self):
        class FakeSession:
            class attributes:
                qb_el = "qubit"
                ro_el = "resonator"
                st_el = "storage"
            class calibration:
                @staticmethod
                def get_pulse_calibration(name):
                    return None
        rules = default_patch_rules(FakeSession())
        assert "ef_freq" in rules
        assert len(rules["ef_freq"]) >= 1

    def test_ef_freq_rule_in_default_rules_is_correct(self):
        class FakeSession:
            class attributes:
                qb_el = "qubit"
                ro_el = "resonator"
                st_el = "storage"
            class calibration:
                @staticmethod
                def get_pulse_calibration(name):
                    return None
        rules = default_patch_rules(FakeSession())
        ef_rules = rules["ef_freq"]
        freq_rule = ef_rules[0]
        assert isinstance(freq_rule, FrequencyRule)
        assert freq_rule.field == "ef_freq"
        assert freq_rule.kind == "ef_freq"
        assert freq_rule.element == "qubit"


# ---------------------------------------------------------------------------
# Canonical naming: EF spectroscopy defaults
# ---------------------------------------------------------------------------

class TestEFSpectroscopyDefaults:
    def test_ge_x180_is_canonical(self):
        assert resolve_pulse_name("ge_x180") == "ge_x180"

    def test_legacy_x180_resolves_to_ge(self):
        assert resolve_pulse_name("x180") == "ge_x180"

    def test_canonical_derived_ef_x180(self):
        assert canonical_derived_pulse("ef", "x180") == "ef_x180"

    def test_canonical_derived_ge_x180(self):
        assert canonical_derived_pulse("ge", "x180") == "ge_x180"
