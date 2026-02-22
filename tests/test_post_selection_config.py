from __future__ import annotations

import pytest

from qubox_v2.analysis.post_selection import PostSelectionConfig


class _ExtractorStub:
    def __init__(self, data: dict):
        self._data = data

    def extract(self, *keys):
        values = tuple(self._data[k] for k in keys)
        if len(keys) == 1:
            return values[0]
        return values


def _valid_metrics() -> dict:
    return {
        "rot_mu_g": 0.0 + 0.0j,
        "rot_mu_e": 1.0 + 0.2j,
        "threshold": -1.0e-5,
        "sigma_g": 0.12,
        "sigma_e": 0.18,
    }


def test_from_discrimination_results_accepts_dict_input():
    metrics = _valid_metrics()
    cfg = PostSelectionConfig.from_discrimination_results(metrics, blob_k_g=2.0)

    assert cfg.policy == "BLOBS"
    assert cfg.kwargs["Ig"] == pytest.approx(0.0)
    assert cfg.kwargs["Qg"] == pytest.approx(0.0)
    assert cfg.kwargs["Ie"] == pytest.approx(1.0)
    assert cfg.kwargs["Qe"] == pytest.approx(0.2)
    assert cfg.kwargs["threshold"] == pytest.approx(-1.0e-5)
    assert cfg.kwargs["sigma_g"] == pytest.approx(0.12)
    assert cfg.kwargs["sigma_e"] == pytest.approx(0.18)


def test_from_discrimination_results_keeps_extract_compatibility():
    stub = _ExtractorStub(_valid_metrics())
    cfg = PostSelectionConfig.from_discrimination_results(stub, blob_k_g=2.5, blob_k_e=3.0)

    assert cfg.policy == "BLOBS"
    assert cfg.kwargs["rg2"] == pytest.approx((2.5 * 0.12) ** 2)
    assert cfg.kwargs["re2"] == pytest.approx((3.0 * 0.18) ** 2)


def test_from_discrimination_results_dict_missing_keys_raises_keyerror():
    metrics = _valid_metrics()
    metrics.pop("sigma_e")

    with pytest.raises(KeyError):
        PostSelectionConfig.from_discrimination_results(metrics)
