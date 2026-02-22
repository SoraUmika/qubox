import numpy as np

from qubox.gates.contexts import ModelContext, NoiseConfig
from qubox.compile import (
    Ansatz,
    DisplacementTemplate,
    SQRTemplate,
    QubitRotationTemplate,
    ObjectiveConfig,
    OptimizerConfig,
    compile_with_ansatz,
)
from qubox.compile.evaluators import compose_unitary, unitary_avg_fidelity


def banner(name: str):
    print("\n" + "=" * 80)
    print(name)
    print("=" * 80)


def make_ctx():
    # Use small, consistent durations; unitary-mode ignores noise anyway.
    return ModelContext(
        dt_s=1e-9,
        st_chi=-2.8e6,
        st_chi2=0.0,
        st_chi3=0.0,
        gate_durations_s={
            "QubitRotation": 16e-9,
            "Displacement": 200e-9,
            "SQR": 1.5e-6,
        },
    )


def build_teacher_target(ansatz: Ansatz, ctx: ModelContext, n_max: int, x_true: np.ndarray) -> np.ndarray:
    ps = ansatz.param_space()
    x_true = ps.apply_fixed(np.asarray(x_true, dtype=float))
    gates = ansatz.build_gates(x_true, ctx=ctx, n_max=n_max, ps=ps)
    U = compose_unitary(gates, n_max=n_max, ctx=ctx, cache=None)
    return U


def run_recovery_case(
    *,
    title: str,
    ansatz: Ansatz,
    n_max: int,
    x_true: np.ndarray,
    maxiter: int = 300,
    restarts: int = 4,
    method: str = "Powell",
    seed: int = 0,
    fidelity_goal: float = 0.999,
):
    banner(title)

    ctx = make_ctx()
    noise = NoiseConfig(dt=None, T1=None, T2=None, order="noise_after")  # unitary mode

    U_target = build_teacher_target(ansatz, ctx, n_max, x_true)

    obj_cfg = ObjectiveConfig(mode="unitary", l2_weight=0.0)
    opt_cfg = OptimizerConfig(
        method=method,
        maxiter=maxiter,
        restarts=restarts,
        seed=seed,
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

    # verify achieved fidelity directly
    gates_best = out["gates_best"]
    U_best = compose_unitary(gates_best, n_max=n_max, ctx=ctx, cache=None)
    F = unitary_avg_fidelity(U_best, U_target)

    print("Reported best_fidelity:", out["best_fidelity"])
    print("Recomputed fidelity    :", F)
    print("Gate sequence          :", [g.__class__.__name__ for g in gates_best])

    assert F >= fidelity_goal, f"Fidelity {F} < goal {fidelity_goal}"
    print("PASS ✅")


def main():
    # Keep n_max small for fast, reliable recovery tests
    n_max = 3

    # ------------------------------------------------------------------
    # CASE 1: Single QubitRotation (2 params) — easiest
    # ------------------------------------------------------------------
    ansatz1 = Ansatz([
        QubitRotationTemplate(name="R0", theta_max=np.pi),
    ])
    # x_true = [theta, phi]
    x_true1 = np.array([0.8, -0.4], dtype=float)
    run_recovery_case(
        title="CASE 1: recover single QubitRotation",
        ansatz=ansatz1,
        n_max=0,  # cavity dim 1 => true 2x2 unitary
        x_true=x_true1,
        maxiter=200,
        restarts=3,
        method="Powell",
        seed=0,
        fidelity_goal=0.999999,
    )

    # ------------------------------------------------------------------
    # CASE 2: Single Displacement (2 params) — also easy (but expm)
    # ------------------------------------------------------------------
    ansatz2 = Ansatz([
        DisplacementTemplate(name="D0", alpha_max=1.0),
    ])
    # x_true = [alpha_re, alpha_im]
    x_true2 = np.array([0.35, -0.12], dtype=float)
    run_recovery_case(
        title="CASE 2: recover single Displacement",
        ansatz=ansatz2,
        n_max=n_max,
        x_true=x_true2,
        maxiter=250,
        restarts=3,
        method="Powell",
        seed=1,
        fidelity_goal=0.99999,
    )

    # ------------------------------------------------------------------
    # CASE 3: Disp -> QubitRotation (4 params) — simple mixed gate set
    # ------------------------------------------------------------------
    ansatz3 = Ansatz([
        DisplacementTemplate(name="D0", alpha_max=1.0),
        QubitRotationTemplate(name="R0", theta_max=np.pi),
    ])
    # x_true = [a_re, a_im, theta, phi]
    x_true3 = np.array([-0.20, 0.25, 0.7, 0.3], dtype=float)
    run_recovery_case(
        title="CASE 3: recover Displacement -> QubitRotation",
        ansatz=ansatz3,
        n_max=n_max,
        x_true=x_true3,
        maxiter=400,
        restarts=4,
        method="Powell",
        seed=2,
        fidelity_goal=0.999,
    )

    # ------------------------------------------------------------------
    # CASE 4: Disp -> SQR (moderate) with restricted n_active
    #         This mimics your earlier moderate test, but teacher–student style.
    # ------------------------------------------------------------------
    # n_active=2 => optimize only n=0,1,2; higher levels fixed to 0
    ansatz4 = Ansatz([
        DisplacementTemplate(name="D0", alpha_max=1.0),
        SQRTemplate(name="SQR0", n_max=n_max, n_active=2, theta_max=np.pi),
    ])
    # x_true layout:
    #   Displacement: [a_re, a_im]
    #   SQR thetas:  [th0, th1, th2]
    #   SQR phis:    [ph0, ph1, ph2]
    x_true4 = np.array([
        0.10, -0.15,     # alpha
        0.0, 0.9, -0.4,  # thetas
        0.0, 0.2, -0.6,  # phis
    ], dtype=float)
    run_recovery_case(
        title="CASE 4: recover Displacement -> SQR (n_active=2)",
        ansatz=ansatz4,
        n_max=n_max,
        x_true=x_true4,
        maxiter=600,
        restarts=5,
        method="Powell",
        seed=3,
        fidelity_goal=0.995,
    )

    # ------------------------------------------------------------------
    # CASE 5: Two-layer Disp->SQR->Disp->SQR (harder)
    #         Still “known solvable” because teacher uses same ansatz.
    # ------------------------------------------------------------------
    ansatz5 = Ansatz([
        DisplacementTemplate(name="D0", alpha_max=1.0),
        SQRTemplate(name="SQR0", n_max=n_max, n_active=2, theta_max=np.pi),
        DisplacementTemplate(name="D1", alpha_max=1.0),
        SQRTemplate(name="SQR1", n_max=n_max, n_active=2, theta_max=np.pi),
    ])
    x_true5 = np.array([
        # D0
        0.12, 0.05,
        # SQR0 (thetas 0..2, phis 0..2)
        0.0, 0.6, -0.2,
        0.0, -0.1, 0.4,
        # D1
        -0.08, 0.10,
        # SQR1
        0.0, -0.5, 0.25,
        0.0, 0.3, -0.2,
    ], dtype=float)
    run_recovery_case(
        title="CASE 5: recover 2-layer Disp/SQR ansatz (n_active=2)",
        ansatz=ansatz5,
        n_max=n_max,
        x_true=x_true5,
        maxiter=900,
        restarts=6,
        method="Powell",
        seed=4,
        fidelity_goal=0.99,
    )

    banner("ALL OPTIMIZER RECOVERY TESTS PASSED ✅")


if __name__ == "__main__":
    main()
