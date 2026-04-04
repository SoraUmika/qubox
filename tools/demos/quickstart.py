from __future__ import annotations

from qubox import Session


def build_demo():
    session = Session.open(
        sample_id="sampleA",
        cooldown_id="cd_2026_03_13",
        registry_base="E:/qubox",
        qop_ip="10.157.36.68",
        cluster_name="Cluster_2",
    )

    result = session.exp.qubit.spectroscopy(
        qubit="q0",
        readout="rr0",
        freq=session.sweep.linspace(-30e6, 30e6, 241, center="q0.ge"),
        drive_amp=0.02,
        n_avg=200,
    )
    return session, result
