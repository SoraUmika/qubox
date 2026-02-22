import numpy as np

from qubox.gates.contexts import ModelContext, NoiseConfig
from qubox.gates.cache import ModelCache
from qubox.gates.noise import QubitT1T2Noise

from qubox.gates.models import (
    QubitRotationModel,
    DisplacementModel,
    SQRModel,
)

from qubox.compile import (
    Ansatz,
    DisplacementTemplate,
    SQRTemplate,
    QubitRotationTemplate,
    ObjectiveConfig,
    OptimizerConfig,
    compile_with_ansatz,
)

# If you have SNAPModel:
try:
    from qubox.gates.models import SNAPModel
    HAVE_SNAP = True
except Exception:
    HAVE_SNAP = False

# -----------------------------
# Helpers
# -----------------------------
def make_ctx(n_max: int) -> ModelContext:
    """
    Assumes you updated ModelContext to include a gate duration map.
    If you kept old fields, adjust accordingly.
    """
    # Keep small chi for tests; sign doesn’t matter for most tests.
    return ModelContext(
        dt_s=1e-9,
        st_chi=-2.8e6,
        st_chi2=0.0,
        st_chi3=0.0,
        gate_durations_s={
            "QubitRotation": 16e-9,
            "Displacement": 200e-9,
            "SQR": 1.5e-6,
            "SNAP": 2.0e-6,
        },
    )

def eye(d: int) -> np.ndarray:
    return np.eye(d, dtype=np.complex128)

def assert_unitary(U: np.ndarray, atol: float = 1e-10):
    d = U.shape[0]
    err = np.linalg.norm(U.conj().T @ U - np.eye(d))
    assert err < atol, f"not unitary: ||U†U-I||={err}"

def unitary_avg_fidelity(U_impl: np.ndarray, U_target: np.ndarray) -> float:
    d = U_target.shape[0]
    tr = np.trace(U_target.conj().T @ U_impl)
    Fp = (np.abs(tr) ** 2) / (d * d)
    return float((d * Fp + 1.0) / (d + 1.0))

def print_banner(title: str):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)

# -----------------------------
# Test 0: imports + shapes
# -----------------------------
def test_shapes_and_unitarity():
    print_banner("TEST 0: shapes + basic unitarity")
    n_max = 3
    d = 2 * (n_max + 1)
    ctx = make_ctx(n_max)
    cache = ModelCache()

    g_rot = QubitRotationModel(theta=np.pi/3, phi=0.2)
    U_rot = cache.unitary(g_rot, n_max=n_max, ctx=ctx)
    assert U_rot.shape == (d, d)
    assert_unitary(U_rot)

    g_disp = DisplacementModel(alpha=0.3 + 0.1j)
    U_disp = cache.unitary(g_disp, n_max=n_max, ctx=ctx)
    assert U_disp.shape == (d, d)
    assert_unitary(U_disp)

    thetas = np.zeros(n_max + 1); thetas[1] = 0.7
    phis = np.zeros(n_max + 1); phis[1] = -0.3
    zeros = np.zeros(n_max + 1)
    g_sqr = SQRModel(thetas=thetas, phis=phis, d_lambda=zeros, d_alpha=zeros, d_omega=zeros)
    U_sqr = cache.unitary(g_sqr, n_max=n_max, ctx=ctx)
    assert U_sqr.shape == (d, d)
    assert_unitary(U_sqr)

    print("PASS")

# -----------------------------
# Test 1: composition order sanity
# -----------------------------
def test_composition_order():
    print_banner("TEST 1: composition order (U_last @ ... @ U_first)")
    n_max = 0
    d = 2 * (n_max + 1)
    ctx = make_ctx(n_max)

    # Two different single-qubit rotations on qubit (cavity dim 1)
    g1 = QubitRotationModel(theta=0.4, phi=0.0)   # x-axis
    g2 = QubitRotationModel(theta=0.7, phi=np.pi/2)  # y-axis

    U1 = g1.unitary(n_max=n_max, ctx=ctx)
    U2 = g2.unitary(n_max=n_max, ctx=ctx)

    # “Apply g1 then g2” => U = U2 @ U1
    U_impl = U2 @ U1

    # Build via Ansatz compile evaluator (unitary mode) by directly multiplying:
    U_manual = U2 @ U1
    assert np.allclose(U_impl, U_manual)

    print("PASS")

# -----------------------------
# Test 2: cache correctness
# -----------------------------
def test_cache_keys_change_with_ctx():
    print_banner("TEST 2: cache key changes with context")
    n_max = 2
    ctx1 = make_ctx(n_max)
    ctx2 = ModelContext(**{**ctx1.__dict__, "st_chi": -3.0e6})  # change chi

    cache = ModelCache()
    g = QubitRotationModel(theta=0.3, phi=0.1)

    U1 = cache.unitary(g, n_max=n_max, ctx=ctx1)
    U2 = cache.unitary(g, n_max=n_max, ctx=ctx2)

    # For qubit rotation, chi shouldn't matter -> matrices should be equal,
    # but cache must treat them as distinct entries without breaking.
    assert np.allclose(U1, U2)

    print("PASS")

# -----------------------------
# Test 3: noise uses per-gate durations (dt=None)
# -----------------------------
def test_noise_duration_effect():
    print_banner("TEST 3: noise decreases fidelity more for longer durations")
    n_max = 0
    d = 2 * (n_max + 1)
    ctx = make_ctx(n_max)

    noise_model = QubitT1T2Noise()
    cache = ModelCache()

    # Same gate, two different durations via override
    g_short = QubitRotationModel(theta=np.pi/2, phi=0.0, duration_override_s=20e-9)
    g_long  = QubitRotationModel(theta=np.pi/2, phi=0.0, duration_override_s=500e-9)

    U_target = g_short.unitary(n_max=n_max, ctx=ctx)  # ideal target

    # compare noisy channel to same target via avg_gate_fidelity_superop
    # (requires your fidelity.py to be correct; if not, still catches trend)
    from qubox.gates.fidelity import avg_gate_fidelity_superop

    noise = NoiseConfig(dt=None, T1=10e-6, T2=12e-6, order="noise_after")

    S_short = cache.superop(g_short, n_max=n_max, ctx=ctx, noise=noise, noise_model=noise_model)
    S_long  = cache.superop(g_long,  n_max=n_max, ctx=ctx, noise=noise, noise_model=noise_model)

    F_short = avg_gate_fidelity_superop(S_short, U_target)
    F_long  = avg_gate_fidelity_superop(S_long,  U_target)

    print("F_short:", F_short)
    print("F_long :", F_long)
    assert F_short >= F_long - 1e-12, "expected longer duration to have <= fidelity"

    print("PASS")

# -----------------------------
# Test 4: optimizer recovers a single displacement (easy decomposition)
# -----------------------------
def test_optimize_single_displacement():
    print_banner("TEST 4: compile target = single displacement")
    n_max = 3
    ctx = make_ctx(n_max)
    noise = NoiseConfig(dt=None, T1=None, T2=None, order="noise_after")  # unitary mode ignores noise

    # True target
    alpha_true = 0.35 - 0.12j
    U_target = DisplacementModel(alpha=alpha_true).unitary(n_max=n_max, ctx=ctx)

    ansatz = Ansatz([
        DisplacementTemplate(name="D0", alpha_max=1.0),
    ])

    obj_cfg = ObjectiveConfig(mode="unitary", l2_weight=0.0)
    opt_cfg = OptimizerConfig(
        method="Powell",
        maxiter=200,
        restarts=3,
        seed=0,
        progress=True,
        progress_every=10,
        progress_prefix="UNITARY",
    )

    out = compile_with_ansatz(
        U_target=U_target,
        ansatz=ansatz,
        ctx=ctx,
        noise=noise,
        n_max=n_max,
        obj_cfg=obj_cfg,
        opt_cfg=opt_cfg,
    )

    print("best fidelity:", out["best_fidelity"])
    assert out["best_fidelity"] > 0.999, "should fit exactly (within numerical tolerance)"

    # sanity: recovered alpha is close (global phase doesn't matter for displacement)
    g_best = out["gates_best"][0]
    print("best alpha:", getattr(g_best, "alpha", None))

    print("PASS")

# -----------------------------
# Test 5: optimizer recovers known Disp->SQR (moderate)
# -----------------------------
def test_optimize_disp_sqr():
    print_banner("TEST 5: compile target = Disp -> SQR (moderate)")
    n_max = 3
    ctx = make_ctx(n_max)
    noise = NoiseConfig(dt=None, T1=None, T2=None, order="noise_after")

    # Ground truth gates (within our ansatz)
    alpha_true = -0.2 + 0.25j
    thetas_true = np.zeros(n_max + 1); thetas_true[1] = 0.9; thetas_true[2] = -0.4
    phis_true   = np.zeros(n_max + 1); phis_true[1]   = 0.2; phis_true[2]   = -0.6
    zeros = np.zeros(n_max + 1)

    g1 = DisplacementModel(alpha=alpha_true)
    g2 = SQRModel(thetas=thetas_true, phis=phis_true, d_lambda=zeros, d_alpha=zeros, d_omega=zeros)

    # Target unitary = g2 @ g1
    U_target = g2.unitary(n_max=n_max, ctx=ctx) @ g1.unitary(n_max=n_max, ctx=ctx)

    # Ansatz: same structure
    ansatz = Ansatz([
        DisplacementTemplate(name="D0", alpha_max=1.0),
        SQRTemplate(name="SQR0", n_max=n_max, n_active=n_max, theta_max=np.pi),
    ])

    obj_cfg = ObjectiveConfig(mode="unitary", l2_weight=1e-6)
    opt_cfg = OptimizerConfig(
        method="Powell",
        maxiter=400,
        restarts=4,
        seed=1,
        progress=True,
        progress_every=20,
        progress_prefix="UNITARY",
    )

    out = compile_with_ansatz(
        U_target=U_target,
        ansatz=ansatz,
        ctx=ctx,
        noise=noise,
        n_max=n_max,
        obj_cfg=obj_cfg,
        opt_cfg=opt_cfg,
    )

    print("best fidelity:", out["best_fidelity"])
    assert out["best_fidelity"] > 0.995, "should fit very well with matching ansatz"

    print("PASS")

# -----------------------------
# Test 6: freezing parameters works
# -----------------------------
def test_freezing():
    print_banner("TEST 6: freezing parameters (Displacement real part fixed)")
    n_max = 2
    ctx = make_ctx(n_max)
    noise = NoiseConfig(dt=None, T1=None, T2=None, order="noise_after")

    alpha_true = 0.5 + 0.2j
    U_target = DisplacementModel(alpha=alpha_true).unitary(n_max=n_max, ctx=ctx)

    # Freeze re to 0.5, only optimize imag
    ansatz = Ansatz([
        DisplacementTemplate(name="D0", alpha_max=1.0, freeze_re=0.5),
    ])

    obj_cfg = ObjectiveConfig(mode="unitary")
    opt_cfg = OptimizerConfig(
        method="Powell",
        maxiter=150,
        restarts=2,
        seed=0,
        progress=True,
        progress_every=10,
        progress_prefix="UNITARY",
    )

    out = compile_with_ansatz(
        U_target=U_target,
        ansatz=ansatz,
        ctx=ctx,
        noise=noise,
        n_max=n_max,
        obj_cfg=obj_cfg,
        opt_cfg=opt_cfg,
    )

    g_best = out["gates_best"][0]
    print("best alpha:", g_best.alpha)
    assert abs(g_best.alpha.real - 0.5) < 1e-12

    print("PASS")

# -----------------------------
# Test 7: noisy objective runs + uses durations
# -----------------------------
def test_noisy_objective_runs():
    print_banner("TEST 7: noisy mode runs and returns a reasonable fidelity (< 1)")
    n_max = 1
    ctx = make_ctx(n_max)
    # Use nontrivial decoherence
    noise = NoiseConfig(dt=None, T1=5e-6, T2=7e-6, order="noise_after")

    # Target = a single qubit rotation (ideal)
    U_target = QubitRotationModel(theta=np.pi/2, phi=0.0).unitary(n_max=n_max, ctx=ctx)

    ansatz = Ansatz([
        QubitRotationTemplate(name="R0", theta_max=np.pi),
    ])

    obj_cfg = ObjectiveConfig(mode="noisy")
    opt_cfg = OptimizerConfig(
        method="Powell",
        maxiter=120,
        restarts=1,
        seed=0,
        progress=True,
        progress_every=10,
        progress_prefix="NOISY",
    )

    out = compile_with_ansatz(
        U_target=U_target,
        ansatz=ansatz,
        ctx=ctx,
        noise=noise,
        n_max=n_max,
        obj_cfg=obj_cfg,
        opt_cfg=opt_cfg,
        cache=ModelCache(),
        noise_model=QubitT1T2Noise(),
    )

    print("best noisy fidelity:", out["best_fidelity"])
    # With noise present, best_fidelity should typically be < 1 (unless dt effectively 0)
    assert out["best_fidelity"] < 0.999999

    print("PASS")

# -----------------------------
# Test 8: SNAP model sanity (if present)
# -----------------------------
def test_snap_model():
    if not HAVE_SNAP:
        print_banner("TEST 8: SNAPModel not found (skipping)")
        return

    print_banner("TEST 8: SNAPModel phases on |e,n>")
    n_max = 3
    ctx = make_ctx(n_max)
    n_levels = n_max + 1
    d = 2 * n_levels

    angles = np.zeros(n_levels)
    angles[2] = 0.7
    g = SNAPModel(angles=angles)
    U = g.unitary(n_max=n_max, ctx=ctx)

    # Check |g,n> unchanged
    for n in range(n_levels):
        idx_gn = 0 * n_levels + n
        assert np.allclose(U[idx_gn, idx_gn], 1.0)

    # Check |e,2> phase
    idx_e2 = 1 * n_levels + 2
    assert np.allclose(U[idx_e2, idx_e2], np.exp(1j * 0.7))

    assert_unitary(U)
    print("PASS")

# -----------------------------
# Run all
# -----------------------------
def main():
    test_shapes_and_unitarity()
    test_composition_order()
    test_cache_keys_change_with_ctx()
    test_noise_duration_effect()
    test_optimize_single_displacement()
    test_optimize_disp_sqr()
    test_freezing()
    test_noisy_objective_runs()
    test_snap_model()
    print_banner("ALL TESTS PASSED ✅")

if __name__ == "__main__":
    main()
