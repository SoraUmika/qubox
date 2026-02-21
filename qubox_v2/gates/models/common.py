# qubox/gates_v2/models/common.py
from __future__ import annotations
import numpy as np

def single_qubit_rotation(theta: float, phi: float) -> np.ndarray:
    """
    Ideal single-qubit rotation about equatorial axis (cos Ï†, sin Ï†, 0):
        U(Î¸, Ï†) = exp[-i Î¸/2 (cos Ï† Ïƒ_x + sin Ï† Ïƒ_y)]
    """
    theta = float(theta)
    phi = float(phi)

    cx = np.cos(theta / 2.0)
    sx = np.sin(theta / 2.0)

    nx = np.cos(phi)
    ny = np.sin(phi)

    sigma_x = np.array([[0, 1],
                        [1, 0]], dtype=np.complex128)
    sigma_y = np.array([[0, -1j],
                        [1j, 0]], dtype=np.complex128)

    n_dot_sigma = nx * sigma_x + ny * sigma_y
    return cx * np.eye(2, dtype=np.complex128) - 1j * sx * n_dot_sigma


def annihilation_operator(n_levels: int) -> np.ndarray:
    """
    a |n> = sqrt(n) |n-1>
    """
    n_levels = int(n_levels)
    a = np.zeros((n_levels, n_levels), dtype=np.complex128)
    for n in range(1, n_levels):
        a[n - 1, n] = np.sqrt(n)
    return a

