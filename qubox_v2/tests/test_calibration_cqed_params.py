from __future__ import annotations

import json

from qubox_v2.calibration.store import CalibrationStore


def test_legacy_calibration_migrates_to_cqed_params(tmp_path):
    calibration_path = tmp_path / "calibration.json"
    calibration_path.write_text(
        json.dumps(
            {
                "version": "5.0.0",
                "alias_index": {
                    "resonator": "oct1:RF_out:1",
                    "transmon": "oct1:RF_out:3",
                },
                "frequencies": {
                    "oct1:RF_out:1": {
                        "lo_freq": 8.8e9,
                        "if_freq": -2.0e8,
                        "resonator_freq": 8.6e9,
                        "kappa": 4.1e6,
                    },
                    "oct1:RF_out:3": {
                        "qubit_freq": 6.15e9,
                    },
                },
                "coherence": {
                    "oct1:RF_out:3": {
                        "T1": 6.2e-6,
                        "T1_us": 6.2,
                        "T2_ramsey": 2.0e-5,
                        "T2_star_us": 20.0,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    store = CalibrationStore(calibration_path)

    resonator = store.get_cqed_params("resonator")
    transmon = store.get_cqed_params("transmon")

    assert resonator is not None
    assert transmon is not None
    assert resonator.resonator_freq == 8.6e9
    assert resonator.kappa == 4.1e6
    assert transmon.qubit_freq == 6.15e9
    assert transmon.T1_us == 6.2
    assert transmon.T2_star_us == 20.0


def test_set_frequencies_and_coherence_write_to_cqed_params(tmp_path):
    calibration_path = tmp_path / "calibration.json"
    store = CalibrationStore(calibration_path)

    store.set_frequencies("transmon", qubit_freq=6.101e9)
    store.set_coherence("transmon", T1=7.0e-6, T1_us=7.0)
    store.save()

    raw = json.loads(calibration_path.read_text(encoding="utf-8"))

    assert raw["version"] == "5.1.0"
    assert raw["cqed_params"]["transmon"]["qubit_freq"] == 6.101e9
    assert raw["cqed_params"]["transmon"]["T1"] == 7.0e-6
    assert raw["cqed_params"]["transmon"]["T1_us"] == 7.0
