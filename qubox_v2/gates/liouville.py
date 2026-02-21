# qubox_v2/gates/liouville.py
from __future__ import annotations
import numpy as np
from typing import List

def unitary_to_kraus(U: np.ndarray) -> List[np.ndarray]:
    U = np.asarray(U, dtype=np.complex128)
    return [U]

def compose_kraus(K_after: List[np.ndarray], K_before: List[np.ndarray]) -> List[np.ndarray]:
    if not K_after or not K_before:
        raise ValueError("compose_kraus: empty Kraus list")
    out: List[np.ndarray] = []
    for B in K_after:
        B = np.asarray(B, dtype=np.complex128)
        for A in K_before:
            A = np.asarray(A, dtype=np.complex128)
            out.append(B @ A)
    return out

def unitary_to_superop(U: np.ndarray) -> np.ndarray:
    U = np.asarray(U, dtype=np.complex128)
    return np.kron(U, U.conj())

def kraus_to_superop(kraus: List[np.ndarray]) -> np.ndarray:
    if not kraus:
        raise ValueError("kraus_to_superop: empty Kraus list")
    d = kraus[0].shape[0]
    S = np.zeros((d*d, d*d), dtype=np.complex128)
    for K in kraus:
        K = np.asarray(K, dtype=np.complex128)
        S += np.kron(K, K.conj())
    return S

