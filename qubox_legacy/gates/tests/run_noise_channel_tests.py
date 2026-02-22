import numpy as np

from qubox.gates.contexts import ModelContext, NoiseConfig
from qubox.gates.noise import QubitT1T2Noise
from qubox.gates.cache import ModelCache
from qubox.gates.liouville import unitary_to_superop
from qubox.gates.fidelity import avg_gate_fidelity_superop

from qubox.gates.models.qubit_rotation import QubitRotationModel


def banner(name: str):
    print("\n" + "=" * 80)
    print(name)
    print("=" * 80)

def assert_close(a, b, atol=1e-10, msg=""):
    if not np.allclose(a, b, atol=atol):
        raise AssertionError(f"{msg} not close; max|a-b|={np.max(np.abs(a-b))}")

def random_density(d: int, rng: np.random.Generator) -> np.ndarray:
    X = rng.normal(size=(d, d)) + 1j * rng.normal(size=(d, d))
    rho = X @ X.conj().T
    rho /= np.trace(rho)
    return rho

def apply_superop(S: np.ndarray, rho: np.ndarray) -> np.ndarray:
    d = rho.shape[0]
    v = rho.reshape(d * d, order="F")  # column-stacking
    vp = S @ v
    return vp.reshape((d, d), order="F")


def make_ctx():
    # durations only matter when NoiseConfig.dt=None
    return ModelContext(
        dt_s=1e-9,
        st_chi=None,
        st_chi2=0.0,
        st_chi3=0.0,
        gate_durations_s={"QubitRotation": 100e-9},
    )


def test_dt_zero_identity():
    banner("NOISE TEST 1: dt=0 gives identity noise -> ideal channel")
    ctx = make_ctx()
    noise_model = QubitT1T2Noise()
    cache = ModelCache()

    n_max = 0
    d = 2

    g = QubitRotationModel(theta=np.pi/2, phi=0.0, duration_override_s=0.0)
    U = g.unitary(n_max=n_max, ctx=ctx)

    noise = NoiseConfig(dt=0.0, T1=5e-6, T2=7e-6, order="noise_after")
    S = cache.superop(g, n_max=n_max, ctx=ctx, noise=noise, noise_model=noise_model)

    F = avg_gate_fidelity_superop(S, U)
    print("Favg:", F)
    assert abs(F - 1.0) < 1e-12
    print("PASS")


def test_T1T2_infinite_no_noise():
    banner("NOISE TEST 2: T1,T2 -> inf gives ideal channel")
    ctx = make_ctx()
    noise_model = QubitT1T2Noise()
    cache = ModelCache()

    n_max = 0
    g = QubitRotationModel(theta=0.9, phi=0.2)
    U = g.unitary(n_max=n_max, ctx=ctx)

    noise = NoiseConfig(dt=100e-9, T1=1e99, T2=1e99, order="noise_after")
    S = cache.superop(g, n_max=n_max, ctx=ctx, noise=noise, noise_model=noise_model)

    F = avg_gate_fidelity_superop(S, U)
    print("Favg:", F)
    assert abs(F - 1.0) < 1e-10
    print("PASS")


def test_dephasing_monotonic():
    banner("NOISE TEST 3: smaller T2 => lower fidelity (monotonic)")
    ctx = make_ctx()
    noise_model = QubitT1T2Noise()
    cache = ModelCache()

    n_max = 0
    g = QubitRotationModel(theta=np.pi/2, phi=0.0, duration_override_s=200e-9)
    U = g.unitary(n_max=n_max, ctx=ctx)

    # Hold T1 large to isolate dephasing-ish effect
    T1 = 1e99
    dt = 200e-9

    def F_for(T2):
        noise = NoiseConfig(dt=dt, T1=T1, T2=T2, order="noise_after")
        S = cache.superop(g, n_max=n_max, ctx=ctx, noise=noise, noise_model=noise_model)
        return avg_gate_fidelity_superop(S, U)

    F_hi = F_for(1e-3)     # essentially no dephasing
    F_mid = F_for(5e-6)
    F_lo = F_for(1e-6)

    print("F(T2=1e-3):", F_hi)
    print("F(T2=5e-6):", F_mid)
    print("F(T2=1e-6):", F_lo)

    assert F_hi >= F_mid - 1e-12
    assert F_mid >= F_lo - 1e-12
    print("PASS")


def test_trace_preserving():
    banner("NOISE TEST 4: superop preserves trace on random states")
    ctx = make_ctx()
    noise_model = QubitT1T2Noise()
    cache = ModelCache()
    rng = np.random.default_rng(0)

    n_max = 0
    d = 2

    g = QubitRotationModel(theta=0.7, phi=-0.4, duration_override_s=300e-9)
    noise = NoiseConfig(dt=None, T1=10e-6, T2=12e-6, order="noise_after")
    S = cache.superop(g, n_max=n_max, ctx=ctx, noise=noise, noise_model=noise_model)

    for _ in range(10):
        rho = random_density(d, rng)
        rho_p = apply_superop(S, rho)
        tr = np.trace(rho_p)
        assert abs(tr - 1.0) < 1e-10, f"trace not preserved: Tr={tr}"
    print("PASS")


def test_pure_dephasing_signature():
    banner("NOISE TEST 5: dephasing damps off-diagonals, preserves diagonals")
    ctx = make_ctx()
    noise_model = QubitT1T2Noise()
    cache = ModelCache()

    n_max = 0
    d = 2

    # Identity unitary (so we test noise directly)
    g = QubitRotationModel(theta=0.0, phi=0.0, duration_override_s=500e-9)
    U = np.eye(d, dtype=np.complex128)

    # Set T1 huge; choose finite T2 (=> pure dephasing probability computed in your model)
    noise = NoiseConfig(dt=None, T1=1e99, T2=2e-6, order="noise_after")
    S = cache.superop(g, n_max=n_max, ctx=ctx, noise=noise, noise_model=noise_model)

    # rho = |+><+|
    plus = (1/np.sqrt(2)) * np.array([1, 1], dtype=np.complex128)
    rho = np.outer(plus, plus.conj())

    rho_p = apply_superop(S, rho)

    # diagonals should remain ~0.5
    assert_close(np.real(rho_p[0,0]), 0.5, atol=1e-8, msg="diag00")
    assert_close(np.real(rho_p[1,1]), 0.5, atol=1e-8, msg="diag11")

    # off-diagonal magnitude should decrease
    assert abs(rho_p[0,1]) < abs(rho[0,1]) + 1e-12, "off-diagonal did not decrease"
    print("rho01 before:", rho[0,1], "after:", rho_p[0,1])
    print("PASS")


def main():
    test_dt_zero_identity()
    test_T1T2_infinite_no_noise()
    test_dephasing_monotonic()
    test_trace_preserving()
    test_pure_dephasing_signature()
    banner("ALL NOISE/DEPHASING TESTS PASSED ✅")


if __name__ == "__main__":
    main()
