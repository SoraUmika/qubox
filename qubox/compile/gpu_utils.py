# qubox_v2/compile/gpu_utils.py
"""
GPU acceleration utilities using CuPy.
Falls back to NumPy if CuPy is not available or GPU is not present.
"""
from __future__ import annotations
import numpy as np
from typing import Optional

# Try to import CuPy for GPU acceleration
_USE_GPU = False
_GPU_AVAILABLE = False

try:
    import cupy as cp
    from cupyx.scipy.linalg import expm as cp_expm
    _GPU_AVAILABLE = True
    print("âœ“ CuPy detected - GPU acceleration available")
except ImportError:
    cp = None
    cp_expm = None
    print("â„¹ CuPy not found - using CPU (NumPy) only")


def enable_gpu(enable: bool = True) -> bool:
    """
    Enable or disable GPU acceleration.
    
    Returns:
        bool: True if GPU is now enabled and available, False otherwise
    """
    global _USE_GPU
    if enable and not _GPU_AVAILABLE:
        print("âš  GPU requested but CuPy not available. Install with: pip install cupy-cuda11x")
        return False
    _USE_GPU = enable and _GPU_AVAILABLE
    if _USE_GPU:
        print(f"âœ“ GPU acceleration ENABLED (Device: {cp.cuda.Device().name.decode()})")
    else:
        print("â„¹ GPU acceleration DISABLED (using CPU)")
    return _USE_GPU


def is_gpu_enabled() -> bool:
    """Check if GPU acceleration is currently enabled."""
    return _USE_GPU


def is_gpu_available() -> bool:
    """Check if GPU is available (CuPy installed)."""
    return _GPU_AVAILABLE


def get_array_module(x=None):
    """
    Get the appropriate array module (cupy or numpy) based on current settings.
    If x is provided and is a cupy array, returns cupy regardless of settings.
    """
    if x is not None and _GPU_AVAILABLE:
        return cp.get_array_module(x)
    return cp if _USE_GPU else np


def to_gpu(arr: np.ndarray, dtype=None) -> np.ndarray:
    """
    Move array to GPU if GPU is enabled, otherwise return as-is.
    
    Args:
        arr: NumPy or CuPy array
        dtype: Optional dtype conversion
    
    Returns:
        Array on GPU (if enabled) or CPU
    """
    if not _USE_GPU:
        return np.asarray(arr, dtype=dtype) if dtype else arr
    
    if isinstance(arr, cp.ndarray):
        return arr if dtype is None else arr.astype(dtype)
    return cp.asarray(arr, dtype=dtype) if dtype else cp.asarray(arr)


def to_cpu(arr) -> np.ndarray:
    """
    Move array to CPU (convert CuPy to NumPy).
    
    Args:
        arr: NumPy or CuPy array
    
    Returns:
        NumPy array on CPU
    """
    if not _GPU_AVAILABLE:
        return np.asarray(arr)
    
    if isinstance(arr, cp.ndarray):
        return cp.asnumpy(arr)
    return np.asarray(arr)


def zeros(shape, dtype=np.complex128):
    """Create zeros array on GPU or CPU."""
    xp = get_array_module()
    return xp.zeros(shape, dtype=dtype)


def eye(n, dtype=np.complex128):
    """Create identity matrix on GPU or CPU."""
    xp = get_array_module()
    return xp.eye(n, dtype=dtype)


def expm(A):
    """
    Matrix exponential on GPU or CPU.
    
    Args:
        A: Square matrix
    
    Returns:
        exp(A) on same device as A
    """
    if _USE_GPU and isinstance(A, cp.ndarray):
        return cp_expm(A)
    else:
        from scipy.linalg import expm as scipy_expm
        A_cpu = to_cpu(A)
        result = scipy_expm(A_cpu)
        return to_gpu(result) if _USE_GPU else result


def batch_matmul(A_list, B_list):
    """
    Batch matrix multiplication: [A1@B1, A2@B2, ...].
    More efficient on GPU with batch operations.
    """
    xp = get_array_module(A_list[0] if A_list else None)
    
    if len(A_list) == 0:
        return []
    
    # Stack into batch and use batched matmul
    if _USE_GPU and isinstance(A_list[0], cp.ndarray):
        A_batch = cp.stack(A_list)
        B_batch = cp.stack(B_list)
        # CuPy supports batched matmul via @
        result_batch = A_batch @ B_batch
        return [result_batch[i] for i in range(len(A_list))]
    else:
        # CPU fallback - just loop
        return [A @ B for A, B in zip(A_list, B_list)]


# Context manager for temporary GPU mode
class gpu_mode:
    """Context manager to temporarily enable/disable GPU."""
    
    def __init__(self, enable: bool = True):
        self.enable = enable
        self.prev_state = None
    
    def __enter__(self):
        global _USE_GPU
        self.prev_state = _USE_GPU
        _USE_GPU = self.enable and _GPU_AVAILABLE
        return self
    
    def __exit__(self, *args):
        global _USE_GPU
        _USE_GPU = self.prev_state


def get_gpu_memory_info():
    """Get GPU memory usage information."""
    if not _GPU_AVAILABLE:
        return "GPU not available"
    
    if not _USE_GPU:
        return "GPU not enabled"
    
    mempool = cp.get_default_memory_pool()
    used = mempool.used_bytes() / 1024**2  # MB
    total = mempool.total_bytes() / 1024**2  # MB
    
    return f"GPU Memory: {used:.1f} MB used / {total:.1f} MB allocated"


def benchmark_gpu_vs_cpu(n: int = 512, iterations: int = 100):
    """
    Benchmark GPU vs CPU performance for matrix operations.
    
    Args:
        n: Matrix size (n x n)
        iterations: Number of iterations
    """
    import time
    
    print(f"\nBenchmarking {n}x{n} matrix multiplication ({iterations} iterations):")
    
    # CPU benchmark
    A_cpu = np.random.randn(n, n) + 1j * np.random.randn(n, n)
    B_cpu = np.random.randn(n, n) + 1j * np.random.randn(n, n)
    
    t0 = time.time()
    for _ in range(iterations):
        C_cpu = A_cpu @ B_cpu
    t_cpu = time.time() - t0
    print(f"  CPU (NumPy): {t_cpu:.3f}s ({t_cpu/iterations*1000:.2f}ms per iter)")
    
    if not _GPU_AVAILABLE:
        print("  GPU (CuPy): Not available")
        return
    
    # GPU benchmark
    A_gpu = cp.asarray(A_cpu)
    B_gpu = cp.asarray(B_cpu)
    
    # Warm-up
    C_gpu = A_gpu @ B_gpu
    cp.cuda.Stream.null.synchronize()
    
    t0 = time.time()
    for _ in range(iterations):
        C_gpu = A_gpu @ B_gpu
    cp.cuda.Stream.null.synchronize()
    t_gpu = time.time() - t0
    
    speedup = t_cpu / t_gpu
    print(f"  GPU (CuPy): {t_gpu:.3f}s ({t_gpu/iterations*1000:.2f}ms per iter)")
    print(f"  Speedup: {speedup:.2f}x")
    
    return speedup


if __name__ == "__main__":
    print("GPU Utilities Test")
    print("=" * 50)
    print(f"GPU Available: {is_gpu_available()}")
    
    if is_gpu_available():
        enable_gpu(True)
        print(get_gpu_memory_info())
        
        # Small benchmark
        print("\nSmall matrices (typical for quantum circuits):")
        benchmark_gpu_vs_cpu(n=24, iterations=1000)  # 2x12 qubitâŠ—cavity
        
        print("\nMedium matrices:")
        benchmark_gpu_vs_cpu(n=128, iterations=100)
        
        print("\nLarge matrices:")
        benchmark_gpu_vs_cpu(n=512, iterations=10)

