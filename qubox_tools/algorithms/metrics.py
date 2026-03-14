from dataclasses import dataclass

import numpy as np
from ..data.containers import Output

try:
    import pandas as pd
except ImportError:  # pragma: no cover - exercised only in reduced local envs
    pd = None


@dataclass
class MatrixTable:
    values: np.ndarray
    index: list[str]
    columns: list[str]

    def __array__(self):
        return self.values

    def __repr__(self) -> str:
        return (
            f"MatrixTable(index={self.index!r}, columns={self.columns!r}, "
            f"values={np.array2string(self.values)})"
        )


def _make_table(values, *, index, columns):
    if pd is not None:
        return pd.DataFrame(values, index=index, columns=columns)
    return MatrixTable(np.asarray(values, dtype=float), list(index), list(columns))


def wilson_interval(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a binomial proportion.

    Parameters
    ----------
    p : float
        Observed proportion (0 to 1).
    n : int
        Number of trials.
    z : float
        Z-score for desired confidence level (1.96 = 95% CI).

    Returns
    -------
    (lower, upper) : tuple[float, float]
        Confidence interval bounds, clipped to [0, 1].
    """
    if n <= 0:
        return (0.0, 1.0)
    denom = 1.0 + z ** 2 / n
    centre = (p + z ** 2 / (2.0 * n)) / denom
    spread = z * np.sqrt((p * (1.0 - p) + z ** 2 / (4.0 * n)) / n) / denom
    return (max(0.0, centre - spread), min(1.0, centre + spread))


def gaussianity_score(x: np.ndarray) -> float:
    """
    Non-Gaussianity diagnostic along 1D:
    NG = |skew| + |kurtosis - 3|
    (kurtosis here is non-Fisher, i.e. 3 for Gaussian).
    """
    x = np.asarray(x, float)
    if x.size < 3:
        return np.nan
    m = np.mean(x)
    v = np.mean((x - m) ** 2)
    if v <= 0:
        return np.nan
    std = np.sqrt(v)
    z = (x - m) / std
    skew = np.mean(z**3)
    kurt = np.mean(z**4)
    return float(abs(skew) + abs(kurt - 3.0))

def gaussian2D_score(x: np.ndarray, y: np.ndarray) -> float:
    """
    Non-Gaussianity diagnostic for a 2D distribution.

    Steps:
    1) Take (x, y) samples and build a 2D array of shape (N, 2).
    2) Estimate mean and covariance, whiten the data so that a true
       2D Gaussian becomes (approximately) iid N(0, 1) in each axis.
    3) Apply the 1D gaussianity_score to each whitened axis.
    4) Check the radial distribution r^2 = x^2 + y^2:
       For a 2D Gaussian, r^2 ~ chi2(df=2), so:
           E[r^2]  = 2
           E[r^4]  = 8
       We add deviations of these from their ideal values.

    Returns:
        NG_2D = NG_x + NG_y + |E[r^2] - 2| + |E[r^4] - 8|
        (smaller is "more Gaussian"; 0 is ideal in the infinite-sample limit)
    """
    x = np.asarray(x, float).ravel()
    y = np.asarray(y, float).ravel()

    if x.size != y.size or x.size < 3:
        return np.nan

    data = np.column_stack([x, y])  # shape (N, 2)

    # Mean and covariance
    mu = np.mean(data, axis=0)
    cov = np.cov(data, rowvar=False)

    # Guard against degenerate / non-positive-definite covariance
    if not np.all(np.isfinite(cov)) or np.linalg.det(cov) <= 0:
        return np.nan

    try:
        # Cholesky: cov = L L^T
        L = np.linalg.cholesky(cov)
    except np.linalg.LinAlgError:
        # Fallback: covariance too nasty
        return np.nan

    # Whiten: z = L^{-1} (x - mu)
    z = np.linalg.solve(L, (data - mu).T).T  # shape (N, 2)
    z1 = z[:, 0]
    z2 = z[:, 1]

    # 1D Gaussianity along each whitened axis
    NG1 = gaussianity_score(z1)
    NG2 = gaussianity_score(z2)

    # Radial diagnostics
    r2 = z1**2 + z2**2
    if r2.size < 3 or not np.all(np.isfinite(r2)):
        return np.nan

    m2 = float(np.mean(r2))      # should be 2
    m4 = float(np.mean(r2**2))   # E[r^4] for 2D Gaussian = 8

    NG_rad_mean = abs(m2 - 2.0)
    NG_rad_kurt = abs(m4 - 8.0)

    NG_total = float(NG1 + NG2 + NG_rad_mean + NG_rad_kurt)
    return NG_total


def butterfly_metrics(
    m1_g,
    m1_e,
    m2_g,
    m2_e,
    det_L_threshold: float = 1e-8,
) -> Output:
    """
    Compute F, Q, V, Lambda_M, and the post-measurement transition matrix T
    for the butterfly experiment, given binary outcomes of m1 and m2.

    Parameters
    ----------
    m1_g, m1_e : array_like
        Outcomes of the first measurement M1 (0/1) for initial |0>_i and |1>_i.
    m2_g, m2_e : array_like
        Outcomes of the second measurement M2 (0/1) for initial |0>_i and |1>_i.
    det_L_threshold : float
        Minimum allowed |det(Lambda_M)| before we consider the matrix invalid.

    Returns
    -------
    out : Output
        Keys:
            - "F", "Q", "V", "det_L", "Lambda_M_valid"
            - "Lambda_M", "confusion_matrix"
            - "transition_matrix"
            - "t01", "t10"
            - optional "note" if invalid
    """
    m1_g = np.asarray(m1_g, dtype=int)
    m1_e = np.asarray(m1_e, dtype=int)
    m2_g = np.asarray(m2_g, dtype=int)
    m2_e = np.asarray(m2_e, dtype=int)

    # ---- Confusion matrix Lambda_M: P(m1 | state_i) -------------------------
    a0 = float(np.mean(m1_g))           # P(m1=1 | |0>_i)
    a1 = float(np.mean(1 - m1_e))       # P(m1=0 | |1>_i)

    P10_g = a0                          # P(m1=1 | 0_i)
    P00_g = 1.0 - P10_g                 # P(m1=0 | 0_i)
    P00_e = a1                          # P(m1=0 | 1_i)
    P10_e = 1.0 - P00_e                 # P(m1=1 | 1_i)

    Lambda_M = np.array(
        [
            [P00_g, P00_e],    # row m1=0
            [P10_g, P10_e],    # row m1=1
        ],
        dtype=float,
    )

    confusion_matrix = _make_table(
        Lambda_M,
        index=["m1=0", "m1=1"],
        columns=["|0>_i", "|1>_i"],
    )

    # Fidelity from Eq. (60)
    F = float(np.clip(1.0 - 0.5 * (a0 + a1), 0.0, 1.0))

    # Visibility / determinant check
    V = (1.0 - a1) - a0  # = P(m1=1|1_i) - P(m1=1|0_i)
    det_L = float(np.linalg.det(Lambda_M))

    # Pre-initialize everything to "invalid"
    Q   = np.nan
    t01 = np.nan
    t10 = np.nan

    transition_matrix = _make_table(
        np.full((2, 2), np.nan, dtype=float),
        index=["|0>_o", "|1>_o"],
        columns=["|0>_i", "|1>_i"],
    )

    Lambda_M_valid = (
        (V > 0.0)
        and np.isfinite(V)
        and np.isfinite(det_L)
        and (abs(det_L) >= det_L_threshold)
    )

    out = Output()

    if not Lambda_M_valid:
        note = (
            "Invalid Lambda_M (low visibility / near-singular): "
            f"V={V:.4g}, det(Lambda_M)={det_L:.3e} < {det_L_threshold:.3e}. "
            "Thresholds / weights likely off; Q, t01, t10 set to NaN, "
            "transition_matrix is all-NaN."
        )
        old_note = out.get("note", "")
        out["note"] = (old_note + " | " + note) if old_note else note

    else:
        # --- Joint probabilities P(m2, m1 | Ïˆ_i) ------------------------
        Lambda_inv = np.linalg.inv(Lambda_M)

        def joint_probs(m1, m2):
            m1 = np.asarray(m1, dtype=int)
            m2 = np.asarray(m2, dtype=int)
            N = len(m1)
            p00 = np.sum((m1 == 0) & (m2 == 0)) / N
            p10 = np.sum((m1 == 0) & (m2 == 1)) / N
            p01 = np.sum((m1 == 1) & (m2 == 0)) / N
            p11 = np.sum((m1 == 1) & (m2 == 1)) / N
            return np.array([[p00, p01], [p10, p11]], dtype=float)

        # For initial |0>_i
        J_g = joint_probs(m1_g, m2_g)
        vec_g_0 = J_g[:, 0]   # m1=0 column
        vec_g_1 = J_g[:, 1]   # m1=1 column

        # For initial |1>_i
        J_e = joint_probs(m1_e, m2_e)
        vec_e_0 = J_e[:, 0]
        vec_e_1 = J_e[:, 1]

        # Eq. (64): P(|phi>_o, m1 | Ïˆ_i) = Lambda_M^{-1} P(m2, m1 | Ïˆ_i)
        state_g_0 = Lambda_inv @ vec_g_0
        state_g_1 = Lambda_inv @ vec_g_1
        state_e_0 = Lambda_inv @ vec_e_0
        state_e_1 = Lambda_inv @ vec_e_1

        # Eqs. (65â€“66): sum over m1 to get unconditional post state
        P_1o_given_0 = float(state_g_0[1] + state_g_1[1])  # P(|1>_o | 0_i)
        P_0o_given_1 = float(state_e_0[0] + state_e_1[0])  # P(|0>_o | 1_i)

        t01 = float(np.clip(P_1o_given_0, 0.0, 1.0))       # 0 -> 1
        t10 = float(np.clip(P_0o_given_1, 0.0, 1.0))       # 1 -> 0

        Q = float(np.clip(1.0 - 0.5 * (t01 + t10), 0.0, 1.0))

        T = np.array(
            [
                [1.0 - t01, t10],  # final |0> given initial |0>,|1>
                [t01, 1.0 - t10],  # final |1> given initial |0>,|1>
            ],
            dtype=float,
        )
        if pd is not None:
            transition_matrix.iloc[:, :] = T
        else:
            transition_matrix.values[:, :] = T

    out.update(
        {
            "V": V,
            "F": F,
            "Q": Q,
            "t01": t01,
            "t10": t10,
            "det_L": det_L,
            "Lambda_M_valid": Lambda_M_valid,
            "Lambda_M": Lambda_M,
            "confusion_matrix": confusion_matrix,
            "transition_matrix": transition_matrix,
        }
    )
    return out

