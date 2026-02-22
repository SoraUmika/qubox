import numpy as np

from qubox.gates.contexts import ModelContext
from qubox.gates.models.common import single_qubit_rotation, annihilation_operator

from qubox.gates.models.qubit_rotation import QubitRotationModel
from qubox.gates.models.displacement import DisplacementModel
from qubox.gates.models.sqr import SQRModel
from qubox.gates.models.snap import SNAPModel


# -----------------------------
# Helpers
# -----------------------------
def banner(name: str):
    print("\n" + "=" * 80)
    print(name)
    print("=" * 80)

def assert_close(A, B, atol=1e-10, rtol=1e-10, msg=""):
    if not np.allclose(A, B, atol=atol, rtol=rtol):
        err = np.linalg.norm(A - B)
        raise AssertionError(f"{msg} not close: ||A-B||={err}")

def assert_unitary(U: np.ndarray, atol: float = 1e-10, msg=""):
    d = U.shape[0]
    err = np.linalg.norm(U.conj().T @ U - np.eye(d))
    if err > atol:
        raise AssertionError(f"{msg} not unitary: ||U†U-I||={err}")

def idx(q: int, n: int, n_levels: int) -> int:
    return q * n_levels + n

def projector_first_levels(n_levels: int, keep: int) -> np.ndarray:
    P = np.zeros((n_levels, n_levels), dtype=np.complex128)
    for n in range(min(keep, n_levels)):
        P[n, n] = 1.0
    return P

def kron(A, B):
    return np.kron(A, B)


# -----------------------------
# Shared context
# -----------------------------
def make_ctx(*, chi_hz=-2.8e6, chi2_hz=0.0, chi3_hz=0.0, sqr_t=1.5e-6):
    # IMPORTANT: your new context uses gate_durations_s
    return ModelContext(
        dt_s=1e-9,
        st_chi=float(chi_hz),
        st_chi2=float(chi2_hz),
        st_chi3=float(chi3_hz),
        gate_durations_s={
            "SQR": float(sqr_t),
            "QubitRotation": 16e-9,
            "Displacement": 200e-9,
            "SNAP": 2.0e-6,
        },
    )


# =============================================================================
# TEST A: QubitRotationModel matrix is kron(R, I_cav) and matches formula
# =============================================================================
def test_qubit_rotation_matrix():
    banner("TEST A: QubitRotationModel intended matrix")

    n_max = 5
    n_levels = n_max + 1
    d = 2 * n_levels
    ctx = make_ctx()

    theta = 0.73
    phi = -0.41
    g = QubitRotationModel(theta=theta, phi=phi)

    U = g.unitary(n_max=n_max, ctx=ctx)
    assert U.shape == (d, d)
    assert_unitary(U, msg="QubitRotation")

    # Manual expected
    Uq = single_qubit_rotation(theta, phi)
    U_expected = kron(Uq, np.eye(n_levels, dtype=np.complex128))
    assert_close(U, U_expected, atol=1e-12, msg="QubitRotation kron check")

    # Spot check basis ordering: |g,n> block equals Uq[0,0] on diagonal
    for n in range(n_levels):
        assert_close(U[idx(0,n,n_levels), idx(0,n,n_levels)], Uq[0,0], atol=1e-12, msg="basis ordering")
        assert_close(U[idx(1,n,n_levels), idx(1,n,n_levels)], Uq[1,1], atol=1e-12, msg="basis ordering")

    print("PASS")


# =============================================================================
# TEST B: DisplacementModel invariants (unitary, inverse, Weyl, and a->a+alpha)
# =============================================================================
def test_displacement_invariants():
    banner("TEST B: DisplacementModel intended action (invariants)")

    # Use a larger cutoff so truncation error is small
    n_max = 20
    n_levels = n_max + 1
    d = 2 * n_levels
    ctx = make_ctx()

    alpha = 0.25 + 0.10j
    beta  = -0.12 + 0.05j

    D_a = DisplacementModel(alpha=alpha).unitary(n_max=n_max, ctx=ctx)
    D_b = DisplacementModel(alpha=beta).unitary(n_max=n_max, ctx=ctx)
    assert_unitary(D_a, msg="D(alpha)")
    assert_unitary(D_b, msg="D(beta)")

    # (1) D(alpha)† = D(-alpha)
    D_minus = DisplacementModel(alpha=-alpha).unitary(n_max=n_max, ctx=ctx)
    assert_close(D_a.conj().T, D_minus, atol=2e-10, msg="D(alpha) dagger")

    # (2) Weyl relation: D(a)D(b) = exp(i Im(a b*)) D(a+b)
    phase = np.exp(1j * np.imag(alpha * np.conjugate(beta)))
    D_ab = DisplacementModel(alpha=alpha+beta).unitary(n_max=n_max, ctx=ctx)
    lhs = D_a @ D_b
    rhs = phase * D_ab
    # truncation causes small mismatch; check on low Fock subspace
    keep = 12
    P = projector_first_levels(n_levels, keep)
    Ptot = kron(np.eye(2), P)
    lhs_r = Ptot @ lhs @ Ptot
    rhs_r = Ptot @ rhs @ Ptot
    assert_close(lhs_r, rhs_r, atol=2e-8, msg="Weyl relation (truncated)")

    # (3) Heisenberg transform: D† a D = a + alpha
    # This is a strong correctness test.
    a = annihilation_operator(n_levels)
    a_tot = kron(np.eye(2), a)

    A_trans = D_a.conj().T @ a_tot @ D_a
    target = a_tot + alpha * kron(np.eye(2), np.eye(n_levels))

    # Check only on a safe low subspace to avoid boundary effects
    lhs_r = Ptot @ A_trans @ Ptot
    rhs_r = Ptot @ target @ Ptot
    assert_close(lhs_r, rhs_r, atol=5e-7, msg="D† a D = a + alpha (truncated)")

    print("PASS")


# =============================================================================
# TEST C: SNAPModel is diagonal, acts only on |e,n>, and matches manual
# =============================================================================
def test_snap_matrix():
    banner("TEST C: SNAPModel intended matrix")

    n_max = 6
    n_levels = n_max + 1
    d = 2 * n_levels
    ctx = make_ctx()

    angles = np.zeros(n_levels)
    angles[0] = 0.1
    angles[3] = -0.7
    angles[6] = 0.33

    g = SNAPModel(angles=angles)
    U = g.unitary(n_max=n_max, ctx=ctx)

    assert U.shape == (d, d)
    assert_unitary(U, msg="SNAP")

    # Manual expected diagonal
    Uexp = np.eye(d, dtype=np.complex128)
    for n in range(n_levels):
        Uexp[idx(1,n,n_levels), idx(1,n,n_levels)] = np.exp(1j * float(angles[n]))

    assert_close(U, Uexp, atol=1e-12, msg="SNAP manual diagonal")

    # Ensure it's diagonal
    offdiag_norm = np.linalg.norm(U - np.diag(np.diag(U)))
    assert offdiag_norm < 1e-12, f"SNAP should be diagonal; offdiag norm={offdiag_norm}"

    print("PASS")


# =============================================================================
# TEST D: SQRModel block structure (mixes only |g,n>,|e,n|) + manual block
# =============================================================================
def test_sqr_block_structure_no_dress():
    banner("TEST D: SQRModel block structure (no dressing)")

    # Disable dressing by setting chi=None in context
    ctx = ModelContext(
        dt_s=1e-9,
        st_chi=None,
        st_chi2=0.0,
        st_chi3=0.0,
        gate_durations_s={"SQR": 1.5e-6},
    )

    n_max = 5
    n_levels = n_max + 1
    d = 2 * n_levels

    thetas = np.zeros(n_levels)
    phis   = np.zeros(n_levels)
    thetas[2] = 0.9; phis[2] = -0.3
    thetas[4] = -0.7; phis[4] = 0.2
    zeros = np.zeros(n_levels)

    g = SQRModel(thetas=thetas, phis=phis, d_lambda=zeros, d_alpha=zeros, d_omega=zeros)
    U = g.unitary(n_max=n_max, ctx=ctx)

    assert U.shape == (d, d)
    assert_unitary(U, msg="SQR")

    # Manual expected block diagonal
    Uexp = np.eye(d, dtype=np.complex128)
    for n in range(n_levels):
        th = float(thetas[n])
        if (not np.isfinite(th)) or th == 0.0:
            continue
        ph = float(phis[n])
        Un = single_qubit_rotation(th, ph)

        gn = idx(0, n, n_levels)
        en = idx(1, n, n_levels)

        Uexp[gn, gn] = Un[0, 0]
        Uexp[gn, en] = Un[0, 1]
        Uexp[en, gn] = Un[1, 0]
        Uexp[en, en] = Un[1, 1]

    assert_close(U, Uexp, atol=1e-12, msg="SQR manual block")

    # Additional structural check: no coupling between different n
    # i.e., U[*, idx(q,n)] nonzero only in rows corresponding to same n
    for n in range(n_levels):
        cols = [idx(0,n,n_levels), idx(1,n,n_levels)]
        # collect all rows that have significant magnitude in these columns
        for c in cols:
            nz_rows = np.where(np.abs(U[:, c]) > 1e-12)[0]
            allowed = set([idx(0,n,n_levels), idx(1,n,n_levels)])
            if not set(nz_rows).issubset(allowed):
                raise AssertionError(f"SQR couples different n: column {c} rows {nz_rows}")

    print("PASS")


# =============================================================================
# TEST E: SQRModel dispersive dressing phase matches formula (order='after')
# =============================================================================
def test_sqr_dressing_matches_formula():
    banner("TEST E: SQRModel dressing matches expected diagonal phase")

    n_max = 6
    n_levels = n_max + 1
    d = 2 * n_levels

    chi_hz = -2.8e6
    chi2_hz = 0.15e6
    t = 1.2e-6
    ctx = make_ctx(chi_hz=chi_hz, chi2_hz=chi2_hz, sqr_t=t)

    # Choose a simple block: only one n rotates so we can see both effects.
    thetas = np.zeros(n_levels)
    phis   = np.zeros(n_levels)
    thetas[3] = np.pi/2
    phis[3] = 0.1
    zeros = np.zeros(n_levels)

    g = SQRModel(
        thetas=thetas, phis=phis,
        d_lambda=zeros, d_alpha=zeros, d_omega=zeros,
        dress_order="after",      # important
        chi_is_angular=False,     # ctx chi in Hz
        duration_override_s=None, # use ctx duration table
    )
    U = g.unitary(n_max=n_max, ctx=ctx)
    assert_unitary(U, msg="SQR dressed")

    # Manual:
    # U = U_disp @ U_block
    U_block = np.eye(d, dtype=np.complex128)
    for n in range(n_levels):
        th = float(thetas[n])
        if (not np.isfinite(th)) or th == 0.0:
            continue
        ph = float(phis[n])
        Un = single_qubit_rotation(th, ph)
        gn = idx(0,n,n_levels); en = idx(1,n,n_levels)
        U_block[gn, gn] = Un[0,0]; U_block[gn, en] = Un[0,1]
        U_block[en, gn] = Un[1,0]; U_block[en, en] = Un[1,1]

    # Dressing (same as your _sqr_dispersive_dressing definition)
    chi = 2*np.pi*chi_hz
    chi2 = 2*np.pi*chi2_hz
    U_disp = np.eye(d, dtype=np.complex128)
    n_arr = np.arange(n_levels, dtype=float)
    coeff = 0.5 * t * (chi*n_arr + chi2*n_arr*(n_arr-1.0))

    phase_g = np.exp(-1j * (+1.0) * coeff)
    phase_e = np.exp(-1j * (-1.0) * coeff)

    for n in range(n_levels):
        U_disp[idx(0,n,n_levels), idx(0,n,n_levels)] = phase_g[n]
        U_disp[idx(1,n,n_levels), idx(1,n,n_levels)] = phase_e[n]

    Uexp = U_disp @ U_block
    assert_close(U, Uexp, atol=1e-10, msg="SQR dressing formula")

    print("PASS")

# =============================================================================
# TEST C: SNAPModel is diagonal, acts only on |e,n>, and matches manual
# =============================================================================
def test_snap_matrix():
    banner("TEST C: SNAPModel intended matrix")

    n_max = 6
    n_levels = n_max + 1
    d = 2 * n_levels
    ctx = make_ctx()

    angles = np.zeros(n_levels)
    angles[0] = 0.1
    angles[3] = -0.7
    angles[6] = 0.33

    g = SNAPModel(angles=angles)
    U = g.unitary(n_max=n_max, ctx=ctx)

    assert U.shape == (d, d)
    assert_unitary(U, msg="SNAP")

    # Manual expected diagonal
    Uexp = np.eye(d, dtype=np.complex128)
    for n in range(n_levels):
        Uexp[idx(1, n, n_levels), idx(1, n, n_levels)] = np.exp(1j * float(angles[n]))

    assert_close(U, Uexp, atol=1e-12, msg="SNAP manual diagonal")

    # Stronger: ensure ALL |g,n> are exactly unchanged (diagonal=1)
    for n in range(n_levels):
        gn = idx(0, n, n_levels)
        assert_close(U[gn, gn], 1.0 + 0.0j, atol=1e-12, msg=f"SNAP leaves |g,{n}> unchanged")

    # Stronger: ensure it is exactly diagonal (no leakage at all)
    offdiag = U.copy()
    np.fill_diagonal(offdiag, 0.0)
    offdiag_norm = np.linalg.norm(offdiag)
    assert offdiag_norm < 1e-12, f"SNAP should be diagonal; offdiag norm={offdiag_norm}"

    # Additional spot check: |e,n> phase matches exactly exp(i*angle_n)
    for n in range(n_levels):
        en = idx(1, n, n_levels)
        expected = np.exp(1j * float(angles[n]))
        assert_close(U[en, en], expected, atol=1e-12, msg=f"SNAP phase on |e,{n}>")

    print("PASS")

def test_snap_composition():
    banner("TEST C2: SNAP composition property")

    n_max = 6
    n_levels = n_max + 1
    ctx = make_ctx()

    a = np.zeros(n_levels); a[2] = 0.4; a[5] = -0.2
    b = np.zeros(n_levels); b[2] = 0.1; b[5] = 0.7

    U1 = SNAPModel(angles=a).unitary(n_max=n_max, ctx=ctx)
    U2 = SNAPModel(angles=b).unitary(n_max=n_max, ctx=ctx)
    U12 = U1 @ U2

    Uexp = SNAPModel(angles=a + b).unitary(n_max=n_max, ctx=ctx)
    assert_close(U12, Uexp, atol=1e-12, msg="SNAP composition")

    print("PASS")

def main():
    test_qubit_rotation_matrix()
    test_displacement_invariants()
    test_snap_matrix()
    test_snap_composition()
    test_sqr_block_structure_no_dress()
    test_sqr_dressing_matches_formula()
    banner("ALL MODEL-MATRIX TESTS PASSED ✅")


if __name__ == "__main__":
    main()
