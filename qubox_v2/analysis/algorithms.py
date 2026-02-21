from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any, Optional
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter
from .output import Output
import math
import random
def argmin_general(data: np.ndarray):
    shape = data.shape
    flat_index = data.argmin()
    min_val = data.min()
    multi_indices = np.unravel_index(flat_index, shape)
    return multi_indices, min_val

def argmax_general(data: np.ndarray):
    """
    Return the multi-dimensional index of the maximum element
    and the maximum value itself.

    Parameters
    ----------
    data : np.ndarray
        Input array.

    Returns
    -------
    indices : tuple[int, ...]
        Multi-dimensional indices of the maximum element.
    max_val : scalar
        Maximum value in the array.
    """
    shape = data.shape
    flat_index = data.argmax()
    max_val = data.max()
    multi_indices = np.unravel_index(flat_index, shape)
    return multi_indices, max_val

def find_peaks(x_data, y_data, threshold, min_distance=0.0, plot=False):
    """
    Finds peaks in y_data that exceed a given threshold and returns the corresponding x_data values.
    
    A point in y_data is considered a peak if:
      - It is greater than both its immediate neighbors.
      - It is above the specified threshold.
    
    After finding these peaks, any two peaks whose x-values are within `min_distance`
    are merged into a single peak by keeping only the one with the higher y-value.
    
    Parameters:
        x_data (list or array-like): x-axis values.
        y_data (list or array-like): y-axis values in which to find peaks.
        threshold (float): Minimum value for a point in y_data to be considered a peak.
        min_distance (float, optional): Minimum distance between two valid peaks on the x-axis.
                                        If two peaks lie within this distance, only the one
                                        with the higher y-value is kept. Default is 0.0.
        plot (bool, optional): If True, plot x_data vs y_data with vertical lines at the peak positions.
                               Default is False.
    
    Returns:
        list: A list of x_data values corresponding to the final (merged) peaks found in y_data.
    """
    # Ensure both datasets have the same length
    if len(x_data) != len(y_data):
        raise ValueError("x_data and y_data must be the same length.")
    
    # If there aren't enough data points to form a peak
    if len(y_data) < 3:
        return []
    
    # 1. Identify all local maxima above threshold
    peak_indices = []
    for i in range(1, len(y_data) - 1):
        if (y_data[i] > threshold 
            and y_data[i] > y_data[i - 1] 
            and y_data[i] > y_data[i + 1]):
            peak_indices.append(i)
    
    # 2. Merge peaks that are too close together based on `min_distance`
    #    Sort peak indices by x_data so we can merge adjacent peaks in x-order.
    peak_indices.sort(key=lambda idx: x_data[idx])
    
    merged_indices = []
    if not peak_indices:
        return []
    
    current_peak = peak_indices[0]
    
    for i in range(1, len(peak_indices)):
        next_peak = peak_indices[i]
        # Check how far apart the two peaks are in x_data
        if abs(x_data[next_peak] - x_data[current_peak]) <= min_distance:
            # If they're too close, keep the one with the higher y-value
            if y_data[next_peak] > y_data[current_peak]:
                current_peak = next_peak
        else:
            # If they're sufficiently far apart, push current_peak and move on
            merged_indices.append(current_peak)
            current_peak = next_peak
    
    # Add the last current_peak
    merged_indices.append(current_peak)
    
    # Get the corresponding x_data values for the merged peak indices
    final_peaks_x = [x_data[i] for i in merged_indices]
    
    # 3. Plot the data and mark the peaks if requested
    if plot:
        plt.figure(figsize=(10, 5))
        plt.plot(x_data, y_data, label="Data")
        
        # Mark the final peaks with vertical lines and scatter points
        #for i in merged_indices:
        #    plt.axvline(x=x_data[i], color='r', linestyle='--', alpha=0.7)
        plt.scatter([x_data[i] for i in merged_indices], 
                    [y_data[i] for i in merged_indices],
                    color='r', label='Peaks')
        
        plt.xlabel("X Data")
        plt.ylabel("Y Data")
        plt.title("Peaks in Data (Merged)")
        plt.legend()
        plt.show()
    
    return final_peaks_x

def find_roots(x, y):
    """
    Finds approximate roots of a function represented by discrete data points using linear interpolation.

    Parameters:
        x (list or array-like): The x-values of the data points (assumed to be in ascending order).
        y (list or array-like): The corresponding y-values of the data points.

    Returns:
        list: A list of x-values where the function crosses zero.
    """
    roots = []
    n = len(x)
    
    for i in range(n - 1):
        # If the function value is exactly zero, record the root.
        if y[i] == 0:
            roots.append(x[i])
        # Check for a sign change between consecutive points.
        if y[i] * y[i + 1] < 0:
            # Linear interpolation formula:
            # x_root = x[i] - y[i] * (x[i+1] - x[i]) / (y[i+1] - y[i])
            x_root = x[i] - y[i] * (x[i+1] - x[i]) / (y[i+1] - y[i])
            roots.append(x_root)
    
    # Check the last data point.
    if y[-1] == 0:
        roots.append(x[-1])

    return np.array(roots)

import numpy as np

def one_over_e_point(x_data, y_data):
    """
    Compute the 1/e point for a decay from max(y) down toward min(y).

    Defines:
        y_hi     = max(y_data)  (initial/high level)
        y_lo     = min(y_data)  (final/low level)
        y_target = y_lo + (y_hi - y_lo)/e

    Returns:
        x_1e, y_target, meta
    where meta includes diagnostics.
    """
    x = np.asarray(x_data, dtype=float)
    y = np.asarray(y_data, dtype=float)

    if x.shape != y.shape:
        raise ValueError(f"x_data and y_data must have same shape, got {x.shape} vs {y.shape}")
    if x.size < 2:
        raise ValueError("Need at least 2 points to interpolate a crossing.")

    # Drop NaNs/Infs
    m = np.isfinite(x) & np.isfinite(y)
    x = x[m]
    y = y[m]
    if x.size < 2:
        raise ValueError("Not enough finite points after removing NaNs/Infs.")

    y_hi = float(np.max(y))
    y_lo = float(np.min(y))

    if y_hi == y_lo:
        # flat signal: every point is already at "1/e" by this definition
        return float(x[0]), y_lo, {"status": "flat", "y_hi": y_hi, "y_lo": y_lo, "y_target": y_lo}

    y_target = y_lo + (y_hi - y_lo) / np.e

    # Find first sign change of (y - y_target)
    s = y - y_target
    sign_change = np.where(s[:-1] * s[1:] <= 0)[0]  # includes exact hits

    if sign_change.size == 0:
        # No crossing: return nearest point
        idx = int(np.argmin(np.abs(s)))
        return float(x[idx]), float(y_target), {
            "status": "no_crossing_nearest",
            "index": idx,
            "y_hi": y_hi,
            "y_lo": y_lo,
            "y_target": y_target,
            "y_at_x": float(y[idx]),
        }

    i = int(sign_change[0])
    x0, x1 = x[i], x[i + 1]
    y0, y1 = y[i], y[i + 1]

    # If exact hit
    if y0 == y_target:
        return float(x0), float(y_target), {"status": "exact", "index": i, "y_hi": y_hi, "y_lo": y_lo, "y_target": y_target}
    if y1 == y_target:
        return float(x1), float(y_target), {"status": "exact", "index": i + 1, "y_hi": y_hi, "y_lo": y_lo, "y_target": y_target}

    # Linear interpolation for crossing
    if y1 == y0:
        # should be rare; fallback to midpoint
        x_1e = 0.5 * (x0 + x1)
        status = "interp_flat_segment"
    else:
        t = (y_target - y0) / (y1 - y0)
        x_1e = x0 + t * (x1 - x0)
        status = "interp"

    return float(x_1e), float(y_target), {"status": status, "bracket": (i, i + 1), "y_hi": y_hi, "y_lo": y_lo, "y_target": y_target}


from typing import List

def random_sequences(M: int, N: int, low: int = 0, high: int = 24, *, replace: bool = True) -> List[List[int]]:
    """
    Build M sequences, each of length N, with integers in [low, high).
    replace=True  -> sampling WITH replacement inside each sequence
    replace=False -> sampling WITHOUT replacement inside each sequence (requires N <= high-low)
    """
    K = high - low
    if K <= 0:
        raise ValueError(f"Require high>low (got low={low}, high={high}).")
    if not replace and N > K:
        raise ValueError(f"replace=False requires N <= {K} (got N={N}).")

    if replace:
        return [[random.randrange(low, high) for _ in range(N)] for _ in range(M)]
    else:
        return [random.sample(range(low, high), k=N) for _ in range(M)]

    
def smooth_and_integrate(x_data, y_data, window_length=5, polyorder=2):
    """
    Smooths y_data using the Savitzky-Golay filter and integrates the smoothed data over x_data.
    
    Parameters:
        x_data (array_like): 1D array of independent variable data (must be monotonic).
        y_data (array_like): 1D array of dependent variable data to be smoothed and integrated.
        window_length (int, optional): The length of the filter window (an odd integer greater than polyorder). 
                                       Default is 5.
        polyorder (int, optional): The order of the polynomial used in the smoothing. Must be less than window_length.
                                   Default is 2.
    
    Returns:
        area (float): The computed area under the smoothed curve.
        smoothed_y (np.ndarray): The smoothed y-data.
    """
    # Check that the window_length is an odd integer.
    if window_length % 2 == 0:
        raise ValueError("window_length must be an odd integer.")
    
    # Ensure the window_length is not larger than the data set
    if window_length > len(y_data):
        raise ValueError("window_length must be less than or equal to the length of y_data.")
    
    # Smooth the y_data using the Savitzky-Golay filter.
    smoothed_y = savgol_filter(y_data, window_length, polyorder)
    
    # Integrate the smoothed data using the composite trapezoidal rule.
    area = np.trapz(smoothed_y, x=x_data)
    
    return area, smoothed_y

def curve_intersections(x, y1, y2, *, assume_sorted=False):
    """
    Find x (and y) where piecewise-linear interpolants of y1(x) and y2(x) intersect.

    Parameters
    ----------
    x, y1, y2 : array-like, same length
        Sample points (not necessarily uniformly spaced). NaNs are ignored.
    assume_sorted : bool, default False
        If False, (x, y1, y2) are sorted by x before processing.

    Returns
    -------
    x_cross : ndarray
        x-coordinates of intersections.
    y_cross : ndarray
        y-coordinates at the intersections (equal for y1 and y2).
    seg_idx  : ndarray (int)
        Indices i such that each intersection lies between x[i] and x[i+1].
    """
    x = np.asarray(x, dtype=float)
    y1 = np.asarray(y1, dtype=float)
    y2 = np.asarray(y2, dtype=float)

    # Drop any NaNs consistently
    mask = np.isfinite(x) & np.isfinite(y1) & np.isfinite(y2)
    x, y1, y2 = x[mask], y1[mask], y2[mask]

    if x.size < 2:
        return np.array([]), np.array([]), np.array([], dtype=int)

    # Sort by x if needed
    if not assume_sorted:
        order = np.argsort(x, kind="mergesort")
        x, y1, y2 = x[order], y1[order], y2[order]

    d = y1 - y2  # signed difference
    d0, d1 = d[:-1], d[1:]
    x0, x1 = x[:-1], x[1:]
    y10, y11 = y1[:-1], y1[1:]
    y20, y21 = y2[:-1], y2[1:]

    # Candidate segments: sign change or exact zero at an endpoint
    sign_change = (d0 == 0) | (d1 == 0) | (np.signbit(d0) != np.signbit(d1))

    # Exclude degenerate segments with identical x (vertical jump)
    nondeg = (x1 != x0)
    cand = np.where(sign_change & nondeg)[0]
    if cand.size == 0:
        return np.array([]), np.array([]), np.array([], dtype=int)

    # Linear interpolate zero of d(t) = d0 + t*(d1 - d0), t in [0,1]
    d0c = d0[cand]
    d1c = d1[cand]
    denom = (d0c - d1c)

    # Handle three cases:
    # 1) Regular crossing: denom != 0 â†’ t = d0 / (d0 - d1)
    # 2) Flat overlap (d0 == d1 == 0): the curves coincide over the segment â†’ return midpoint
    # 3) Endpoint exact hit (t=0 or t=1) naturally covered by formula
    regular = denom != 0
    t = np.empty_like(d0c)
    t[regular] = d0c[regular] / denom[regular]

    # For overlapping segments, pick midpoint
    overlap = (~regular) & (d0c == 0)
    t[overlap] = 0.5

    # For the remaining weird case (parallel but not overlapping), skip
    valid = ((t >= 0) & (t <= 1)) & (regular | overlap)

    if not np.any(valid):
        return np.array([]), np.array([]), np.array([], dtype=int)

    i = cand[valid]
    t = t[valid]

    x_cross = x0[i] + t * (x1[i] - x0[i])
    # y from either y1 or y2 interpolant (theyâ€™re equal at the crossing)
    y_cross = y10[i] + t * (y11[i] - y10[i])

    return x_cross, y_cross, i

def estimate_intrinsic_sigmas_mog(S_g, S_e, max_iter=500, tol=1e-8, min_var=1e-8, verbose=False):
    """
    Estimate intrinsic Gaussian widths (sigma_g, sigma_e) of readout blobs
    using a 2-component 1D Gaussian Mixture Model (GMM) on the optimal axis.

    Parameters
    ----------
    S_g : array_like of complex
        IQ samples measured after preparing |g>.
    S_e : array_like of complex
        IQ samples measured after preparing |e>.
    max_iter : int
        Maximum number of EM iterations.
    tol : float
        Convergence tolerance on log-likelihood.
    min_var : float
        Minimum allowed variance to avoid degeneracy.
    verbose : bool
        If True, prints EM progress.

    Returns
    -------
    result : Output
        Output wrapping a dict with keys:
        {
          "mu_g": float,            # mean of g-component (1D, along rotated I axis)
          "mu_e": float,            # mean of e-component (1D, along rotated I axis)
          "sigma_g": float,         # std dev of g-component (along rotated I axis)
          "sigma_e": float,         # std dev of e-component (along rotated I axis)
          "eps_up": float,          # P(actual e-comp | prepared g)
          "eps_down": float,        # P(actual g-comp | prepared e)
          "axis": complex,          # complex unit vector used for projection
          "loglik": float,          # final log-likelihood
          "weights": np.ndarray,    # [pi_g, pi_e] over pooled data

          # Responsibility-weighted centers in the rotated IQ frame
          "mu_g_I_rot": float,
          "mu_g_Q_rot": float,
          "mu_e_I_rot": float,
          "mu_e_Q_rot": float,

          # Responsibility-weighted centers in the ORIGINAL IQ frame
          "mu_g_I_unrot": float,
          "mu_g_Q_unrot": float,
          "mu_e_I_unrot": float,
          "mu_e_Q_unrot": float,
        }
    """
    S_g = np.asarray(S_g, dtype=np.complex128).ravel()
    S_e = np.asarray(S_e, dtype=np.complex128).ravel()

    if S_g.size == 0 or S_e.size == 0:
        raise ValueError("S_g and S_e must both be non-empty.")

    # --- 1. Discrimination axis in complex plane ---
    mu_g_raw = S_g.mean()
    mu_e_raw = S_e.mean()
    delta = mu_e_raw - mu_g_raw
    if np.abs(delta) == 0:
        raise ValueError("Cannot define discrimination axis: g and e means are identical.")

    axis = delta / np.abs(delta)  # unit complex

    # 1D projections along this axis (for EM)
    x_g = np.real(S_g * np.conj(axis))
    x_e = np.real(S_e * np.conj(axis))

    x_all = np.concatenate([x_g, x_e])
    N = x_all.size

    # Also keep full IQ (unrotated) and rotated IQ for later center estimation
    S_all = np.concatenate([S_g, S_e])
    S_all_rot = S_all * np.conj(axis)
    I_all = np.real(S_all_rot)
    Q_all = np.imag(S_all_rot)

    # --- 2. Initialize GMM params ---
    mu1 = float(np.mean(x_g))
    mu2 = float(np.mean(x_e))
    if mu2 < mu1:
        mu1, mu2 = mu2, mu1  # enforce mu1 < mu2

    var1 = max(float(np.var(x_g)), min_var)
    var2 = max(float(np.var(x_e)), min_var)

    d1 = (x_all - mu1) ** 2
    d2 = (x_all - mu2) ** 2
    closer_to_1 = d1 < d2
    pi1 = max(closer_to_1.mean(), 1e-3)
    pi2 = 1.0 - pi1

    def log_norm_pdf(x, mean, var):
        return -0.5 * (np.log(2.0 * np.pi * var) + (x - mean) ** 2 / var)

    prev_loglik = -np.inf
    loglik = -np.inf

    # --- 3. EM ---
    for it in range(max_iter):
        # E-step
        log_p1 = np.log(pi1) + log_norm_pdf(x_all, mu1, var1)
        log_p2 = np.log(pi2) + log_norm_pdf(x_all, mu2, var2)

        max_lp = np.maximum(log_p1, log_p2)
        log_sum = max_lp + np.log(
            np.exp(log_p1 - max_lp) + np.exp(log_p2 - max_lp)
        )

        r1 = np.exp(log_p1 - log_sum)
        r2 = 1.0 - r1

        N1 = np.sum(r1)
        N2 = N - N1

        if N1 < 1e-6 or N2 < 1e-6:
            if verbose:
                print("Component collapse detected; stopping EM early.")
            break

        mu1 = float(np.sum(r1 * x_all) / N1)
        mu2 = float(np.sum(r2 * x_all) / N2)

        var1 = float(np.sum(r1 * (x_all - mu1) ** 2) / N1)
        var2 = float(np.sum(r2 * (x_all - mu2) ** 2) / N2)

        var1 = max(var1, min_var)
        var2 = max(var2, min_var)

        pi1 = N1 / N
        pi2 = 1.0 - pi1

        loglik = float(np.sum(log_sum))
        if verbose:
            print(
                f"Iter {it:3d}: loglik={loglik:.6f}, "
                f"mu=({mu1:.4g},{mu2:.4g}), "
                f"sigma=({np.sqrt(var1):.4g},{np.sqrt(var2):.4g})"
            )

        if abs(loglik - prev_loglik) < tol:
            break
        prev_loglik = loglik

    # --- 4. Relabel: lower mean -> g, higher -> e ---
    if mu1 <= mu2:
        mu_g, mu_e = mu1, mu2
        var_g, var_e = var1, var2
        r_g = r1
        r_e = r2
        weights = np.array([pi1, pi2])
    else:
        mu_g, mu_e = mu2, mu1
        var_g, var_e = var2, var1
        r_g = r2
        r_e = r1
        weights = np.array([pi2, pi1])

    sigma_g = float(np.sqrt(var_g))
    sigma_e = float(np.sqrt(var_e))

    # --- 5. eps_up / eps_down ---
    Ng = x_g.size
    Ne = x_e.size

    r_g_prep_g = r_g[:Ng]
    r_e_prep_g = r_e[:Ng]

    r_g_prep_e = r_g[Ng:]
    r_e_prep_e = r_e[Ng:]

    eps_up = float(r_e_prep_g.mean()) if Ng > 0 else np.nan
    eps_down = float(r_g_prep_e.mean()) if Ne > 0 else np.nan

    # --- 6. Rotated centers in (I_rot, Q_rot) for each component ---
    N_g_eff = float(np.sum(r_g))
    N_e_eff = float(np.sum(r_e))

    if N_g_eff > 0:
        mu_g_I_rot = float(np.sum(r_g * I_all) / N_g_eff)
        mu_g_Q_rot = float(np.sum(r_g * Q_all) / N_g_eff)
    else:
        mu_g_I_rot = np.nan
        mu_g_Q_rot = np.nan

    if N_e_eff > 0:
        mu_e_I_rot = float(np.sum(r_e * I_all) / N_e_eff)
        mu_e_Q_rot = float(np.sum(r_e * Q_all) / N_e_eff)
    else:
        mu_e_I_rot = np.nan
        mu_e_Q_rot = np.nan

    # --- 7. Centers in original IQ frame (unrotated, as I/Q) ---
    S_all_I = np.real(S_all)
    S_all_Q = np.imag(S_all)

    if N_g_eff > 0:
        mu_g_I_unrot = float(np.sum(r_g * S_all_I) / N_g_eff)
        mu_g_Q_unrot = float(np.sum(r_g * S_all_Q) / N_g_eff)
    else:
        mu_g_I_unrot = np.nan
        mu_g_Q_unrot = np.nan

    if N_e_eff > 0:
        mu_e_I_unrot = float(np.sum(r_e * S_all_I) / N_e_eff)
        mu_e_Q_unrot = float(np.sum(r_e * S_all_Q) / N_e_eff)
    else:
        mu_e_I_unrot = np.nan
        mu_e_Q_unrot = np.nan

    out = Output({
        "mu_g": mu_g,
        "mu_e": mu_e,
        "sigma_g": sigma_g,
        "sigma_e": sigma_e,
        "eps_up": eps_up,
        "eps_down": eps_down,
        "axis": axis,
        "loglik": loglik,
        "weights": weights,
        "mu_g_I_rot": mu_g_I_rot,
        "mu_g_Q_rot": mu_g_Q_rot,
        "mu_e_I_rot": mu_e_I_rot,
        "mu_e_Q_rot": mu_e_Q_rot,
        "mu_g_I_unrot": mu_g_I_unrot,
        "mu_g_Q_unrot": mu_g_Q_unrot,
        "mu_e_I_unrot": mu_e_I_unrot,
        "mu_e_Q_unrot": mu_e_Q_unrot,
    })

    return out


def optimal_threshold_empirical(Ig_rot, Ie_rot, weights=None):
    Ig = np.asarray(Ig_rot)
    Ie = np.asarray(Ie_rot)

    # if class priors or weights not given, assume equal effective weight per point set
    if weights is None:
        wg = np.ones_like(Ig, float)
        we = np.ones_like(Ie, float)
    else:
        wg, we = weights
        if wg is None: wg = 1.0
        if we is None: we = 1.0
        wg = np.broadcast_to(wg, Ig.shape).astype(float)
        we = np.broadcast_to(we, Ie.shape).astype(float)

    # sort samples
    Ig_sorted_idx = np.argsort(Ig)
    Ie_sorted_idx = np.argsort(Ie)
    Ig_s = Ig[Ig_sorted_idx]
    Ie_s = Ie[Ie_sorted_idx]
    wg_s = wg[Ig_sorted_idx]
    we_s = we[Ie_sorted_idx]

    # cumulative weights for "g misclassified" when threshold moves right
    wg_total = wg_s.sum()
    we_total = we_s.sum()

    # Start with threshold below all points -> all g misclassified? No: rule is g if I < t.
    # If t is -inf: all Ig > t => all g misclassified; all Ie < t is false => no e misclassified.
    # We'll instead sweep over candidate midpoints and compute directly.

    # Candidate thresholds: midpoints between sorted unique samples of both sets
    all_points = np.concatenate([Ig_s, Ie_s])
    all_points = np.unique(all_points)
    if all_points.size == 0:
        raise ValueError("No points to threshold.")
    # midpoints between consecutive unique points
    t_candidates = (all_points[:-1] + all_points[1:]) / 2.0

    # To be safe, also consider below-min and above-max (though theyâ€™ll be terrible)
    # but usually not needed; the optimum sits between.

    best_t = t_candidates[0]
    best_err = np.inf

    # Precompute cumulative sums to avoid O(N^2)
    wg_cum = np.cumsum(wg_s)                 # weight of g with Ig <= value
    we_cum = np.cumsum(we_s)                 # weight of e with Ie <= value

    # For each candidate t:
    # mis_g: Ig > t  -> wg_total - wg_cum[idx_last_<=t]
    # mis_e: Ie < t  -> we_cum[idx_last_<=t]
    jg = 0
    je = 0
    for t in t_candidates:
        # advance pointers
        while jg < Ig_s.size and Ig_s[jg] <= t:
            jg += 1
        while je < Ie_s.size and Ie_s[je] <= t:
            je += 1

        mis_g = wg_total - (wg_cum[jg - 1] if jg > 0 else 0.0)
        mis_e = (we_cum[je - 1] if je > 0 else 0.0)
        err = mis_g + mis_e

        if err < best_err:
            best_err = err
            best_t = t

    total = wg_total + we_total
    err_rate = best_err / total if total > 0 else np.nan
    return float(best_t), float(err_rate)

def samples_for_k_sigma_event(k, Y, two_sided=True):
    """
    Compute how many iid Gaussian samples are needed so that the probability
    of seeing at least one sample with |X - mu| >= k*sigma (or X - mu >= k*sigma)
    is at least Y.

    Parameters
    ----------
    k : float
        Number of sigmas away from the mean (e.g. k = 2.5).
    Y : float
        Target probability (confidence level) of seeing at least one such event.
        Must be between 0 and 1 (e.g. Y = 0.95 for 95%).
    two_sided : bool, optional
        If True  â†’ use |X - mu| >= k*sigma (both tails).
        If False â†’ use X - mu >= k*sigma (upper tail only).

    Returns
    -------
    n : int
        Minimum number of samples needed so that P(â‰¥ 1 success) â‰¥ Y.
    """
    if not (0 < Y < 1):
        raise ValueError("Y must be between 0 and 1 (e.g. 0.95 for 95%).")

    # For Z ~ N(0, 1):
    # two-sided: p = P(|Z| >= k) = erfc(k / sqrt(2))
    # one-sided: p = P(Z >= k)   = 0.5 * erfc(k / sqrt(2))
    if two_sided:
        p = math.erfc(k / math.sqrt(2.0))
    else:
        p = 0.5 * math.erfc(k / math.sqrt(2.0))

    if p <= 0:
        raise ValueError("p is numerically zero for this k; k is too large.")

    # Need n such that: 1 - (1 - p)^n >= Y  â†’  (1 - p)^n <= 1 - Y
    n_real = math.log(1.0 - Y) / math.log(1.0 - p)
    return math.ceil(n_real)

from math import exp, pi
from scipy.integrate import quad  # or mpmath.quad

def p_exclusive_ground(d, sigma_g, sigma_e, k_g, k_e):
    delta = d / sigma_g
    beta  = k_g
    alpha = k_e * (sigma_e / sigma_g)

    # Probability inside ground disc
    p_in_g = 1.0 - exp(-0.5 * beta**2)

    # Fraction of angles where a ring at radius r is inside the excited disc
    def angle_fraction(r):
        if r == 0:
            # At center, it's inside E iff delta <= alpha
            return 1.0 if delta <= alpha else 0.0

        # Entire ring inside E?
        if r + delta <= alpha:
            return 1.0

        # Entire ring outside E?
        if abs(r - delta) >= alpha:
            return 0.0

        # Partial intersection
        C = (r**2 + delta**2 - alpha**2) / (2.0 * r * delta)
        # numerical safety
        C = max(-1.0, min(1.0, C))
        return np.arccos(C) / pi

    def integrand(r):
        return r * np.exp(-0.5 * r**2) * angle_fraction(r)

    p_overlap, _ = quad(integrand, 0.0, beta)
    return p_in_g - p_overlap

def mean_trials_ground(d, sigma_g, sigma_e, k_g, k_e):
    p = p_exclusive_ground(d, sigma_g, sigma_e, k_g, k_e)
    return int(1.0 / p)


def compute_waveform_fft(
    z: np.ndarray,
    dt: float = 1e-9,
    zero_pad_factor: int = 16,
    freq_range: tuple[float, float] | None = None,
    time_window: tuple[int, int] | None = None,
    domain: str = "both",
    window_note: str = "",
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute FFT of a complex waveform and plot time/frequency domains.

    Parameters
    ----------
    z : np.ndarray
        Complex waveform (I + 1j*Q).
    dt : float, optional
        Sample spacing in seconds (default 1e-9).
    zero_pad_factor : int, optional
        Factor to extend the FFT length via zero-padding (default 16).
    freq_range : tuple[float, float] or None, optional
        (f_min, f_max) in MHz for the frequency plot x-axis.
    time_window : tuple[int, int] or None, optional
        (t_begin, t_end) using 1-based sample numbers, inclusive of t_end.
        By convention, z[0] â†” t=1.
    domain : {"both", "time", "frequency"}, optional
        Which domain(s) to plot. Default "both".
    window_note : str, optional
        Additional text to add to plot titles.

    Returns
    -------
    t : np.ndarray
        Time axis in microseconds.
    z_windowed : np.ndarray
        Complex waveform (after applying time_window if specified).
    f : np.ndarray
        Frequency axis in MHz (empty array if domain="time").
    mag_norm : np.ndarray
        Normalized magnitude of FFT (empty array if domain="time").
    mag_log : np.ndarray
        Magnitude of FFT with floor applied for log plotting (empty array if domain="time").
    """
    # --- validate domain ---
    domain_norm = str(domain).strip().lower()
    if domain_norm not in {"both", "time", "frequency"}:
        raise ValueError('domain must be one of {"both", "time", "frequency"}')

    N_full = z.size

    # --- handle time window (1-based, inclusive) ---
    if time_window is not None:
        if not (isinstance(time_window, (tuple, list)) and len(time_window) == 2):
            raise ValueError("time_window must be a 2-element tuple/list: (t_begin, t_end).")
        t_begin, t_end = time_window

        if not (isinstance(t_begin, (int, np.integer)) and isinstance(t_end, (int, np.integer))):
            raise TypeError("t_begin and t_end must be integers.")
        if t_begin < 1:
            raise ValueError("t_begin must be >= 1 (since z[0] â†” t=1).")
        if t_end < t_begin:
            raise ValueError("t_end must be >= t_begin.")
        if t_end > N_full:
            raise ValueError(f"t_end cannot exceed waveform length ({N_full}).")

        # convert 1-based inclusive to Python slice [start:end)
        idx0 = t_begin - 1
        idx1 = t_end
        z_windowed = z[idx0:idx1]
        N = z_windowed.size

        # time axis in microseconds (1-based sample numbers)
        sample_numbers = np.arange(t_begin, t_begin + N)  # 1..N within window
        t = sample_numbers * dt * 1e6  # Î¼s
    else:
        z_windowed = z
        N = z.size
        sample_numbers = np.arange(1, N + 1)  # 1..N because z[0] â†” t=1
        t = sample_numbers * dt * 1e6  # Î¼s

    # --- compute FFT only if needed ---
    if domain_norm in {"both", "frequency"}:
        if zero_pad_factor < 1:
            raise ValueError("zero_pad_factor must be >= 1")
        Nfft = int(N * zero_pad_factor)
        Z = np.fft.fftshift(np.fft.fft(z_windowed, n=Nfft)) * dt
        f = np.fft.fftshift(np.fft.fftfreq(Nfft, dt)) / 1e6  # MHz

        mag = np.abs(Z)
        mag_max = float(mag.max()) if mag.size else 0.0
        denom = mag_max if mag_max > 0 else 1.0
        mag_norm = mag / denom

        # floor for log axis to avoid log(0)
        eps = max(mag_max * 1e-12, 1e-30)
        mag_log = np.maximum(mag, eps)
    else:
        f = np.array([])
        mag_norm = np.array([])
        mag_log = np.array([])

    # --- plotting ---
    if domain_norm == "both":
        fig, (ax_time, ax_freq) = plt.subplots(2, 1, figsize=(8, 6), tight_layout=True)

        # time-domain
        ax_time.plot(t, np.real(z_windowed), label="I (real)")
        ax_time.plot(t, np.imag(z_windowed), label="Q (imag)")
        ax_time.set_xlabel("Time (Î¼s)")
        ax_time.set_ylabel("Amplitude")
        ax_time.set_title("Time-Domain Pulse" + window_note)
        ax_time.legend()
        ax_time.grid(alpha=0.3)

        # frequency-domain: normalized (linear) + raw (log) on twin y-axis
        l_norm, = ax_freq.plot(f, mag_norm, linestyle="--", label="Normalized |FFT| (linear)")
        ax_freq.set_xlabel("Frequency (MHz)")
        ax_freq.set_ylabel("Normalized |FFT|")
        ax_freq.set_title(f"Zero-padded FFT (Ã—{zero_pad_factor})" + window_note)
        if freq_range is not None:
            ax_freq.set_xlim(freq_range)
        ax_freq.grid(alpha=0.3)

        ax_freq_r = ax_freq.twinx()
        l_raw, = ax_freq_r.plot(f, mag_log, label="|FFT| (log)")
        ax_freq_r.set_yscale("log")
        ax_freq_r.set_ylabel("|FFT|")

        # combined legend
        lines = [l_norm, l_raw]
        labels = [ln.get_label() for ln in lines]
        ax_freq.legend(lines, labels, loc="best")

        plt.show()

    elif domain_norm == "time":
        fig, ax = plt.subplots(1, 1, figsize=(8, 3.5), tight_layout=True)
        ax.plot(t, np.real(z_windowed), label="I (real)")
        ax.plot(t, np.imag(z_windowed), label="Q (imag)")
        ax.set_xlabel("Time (Î¼s)")
        ax.set_ylabel("Amplitude")
        ax.set_title("Time-Domain Pulse" + window_note)
        ax.legend()
        ax.grid(alpha=0.3)
        plt.show()

    else:  # "frequency"
        fig, ax = plt.subplots(1, 1, figsize=(8, 3.5), tight_layout=True)

        # left y-axis: normalized (linear)
        l_norm, = ax.plot(f, mag_norm, linestyle="--", label="Normalized |FFT| (linear)")
        ax.set_xlabel("Frequency (MHz)")
        ax.set_ylabel("Normalized |FFT|")
        ax.set_title(f"Zero-padded FFT (Ã—{zero_pad_factor})" + window_note)
        if freq_range is not None:
            ax.set_xlim(freq_range)
        ax.grid(alpha=0.3)

        # right y-axis: raw magnitude (log)
        ax_r = ax.twinx()
        l_raw, = ax_r.plot(f, mag_log, label="|FFT| (log)")
        ax_r.set_yscale("log")
        ax_r.set_ylabel("|FFT|")

        # combined legend
        lines = [l_norm, l_raw]
        labels = [ln.get_label() for ln in lines]
        ax.legend(lines, labels, loc="best")

        plt.show()

    return t, z_windowed, f, mag_norm, mag_log

# ==============================
# Put these helper algorithms in a separate module and import them.
# (You said youâ€™ll place them somewhere and import them.)
# ==============================




@dataclass
class PeakObjective:
    """
    Turns a per-DC spectrum mag[freq] into a scalar S(dc).
    Defaults to max-over-frequency.
    """
    method: str = "max"           # "max" | "sum"
    i0: Optional[int] = None      # for "sum"
    i1: Optional[int] = None

    def __call__(self, mag_1d: np.ndarray) -> float:
        mag_1d = np.asarray(mag_1d, dtype=float)
        if self.method == "max":
            return float(np.max(mag_1d))
        if self.method == "sum":
            i0 = 0 if self.i0 is None else int(self.i0)
            i1 = mag_1d.size if self.i1 is None else int(self.i1)
            return float(np.sum(mag_1d[i0:i1]))
        raise ValueError(f"Unknown objective method: {self.method}")


def peak_score_robust(S: np.ndarray) -> float:
    """
    Cheap â€œis there a real peak?â€ score.
    Returns prominence in units of MAD.
    """
    S = np.asarray(S, dtype=float)
    med = float(np.median(S))
    mad = float(np.median(np.abs(S - med))) + 1e-12
    return (float(np.max(S)) - med) / mad


def scout_windows(dc_start: float, dc_stop: float, window: float, step: float):
    """
    Yields (dc_left, dc_right, dc_list) for scouting.
    """
    dc_left = float(dc_start)
    dc_stop = float(dc_stop)
    window = float(window)
    step = float(step)
    if step <= 0:
        raise ValueError("step must be > 0")
    if window <= 0:
        raise ValueError("window must be > 0")
    if dc_stop < dc_left:
        raise ValueError("dc_stop must be >= dc_start")

    while dc_left < dc_stop - 1e-15:
        dc_right = min(dc_left + window, dc_stop)
        dc_list = np.arange(dc_left, dc_right + 0.5 * step, step, dtype=float)
        yield dc_left, dc_right, dc_list
        dc_left = dc_right


def refine_around(dc_est: float, half_width: float, step: float) -> np.ndarray:
    half_width = float(half_width)
    step = float(step)
    if half_width <= 0:
        raise ValueError("half_width must be > 0")
    if step <= 0:
        raise ValueError("step must be > 0")
    dc_est = float(dc_est)
    return np.arange(dc_est - half_width, dc_est + half_width + 0.5 * step, step, dtype=float)


def lock_to_peak_3pt(
    measure_S: Callable[[float], float],
    *,
    dc0: float,
    delta: float,
    gain: float = 0.75,
    max_iters: int = 30,
    min_delta: float = 1e-4,
    loss_frac: float = 0.6,
):
    """
    Local peak tracker / lock using 3-point hill climb.
    - measure_S(dc) returns scalar S at that dc.
    Returns (best_dc, best_S).
    """
    dc = float(dc0)
    d = float(delta)
    if d <= 0:
        raise ValueError("delta must be > 0")

    S0 = float(measure_S(dc))
    best_dc, best_S = dc, S0

    for _ in range(int(max_iters)):
        Sm = float(measure_S(dc - d))
        S0 = float(measure_S(dc))
        Sp = float(measure_S(dc + d))

        if S0 > best_S:
            best_dc, best_S = dc, S0

        # lost: recentre and tighten
        if S0 < loss_frac * best_S:
            dc = best_dc
            d = max(float(min_delta), 0.5 * d)
            continue

        # hill climb
        if Sp > S0 and Sp >= Sm:
            dc = dc + gain * d
        elif Sm > S0 and Sm > Sp:
            dc = dc - gain * d
        else:
            d = max(float(min_delta), 0.7 * d)

    return best_dc, best_S

