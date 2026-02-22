# qubox/compile/tests/test_gpu_accelerators.py
"""
Tests for GPU acceleration module.
"""
import pytest
import numpy as np
from qubox.compile.gpu_accelerators import (
    is_jax_available,
    is_gpu_available,
    enable_jax_acceleration,
    disable_jax_acceleration,
    compose_unitary_gpu,
    unitary_avg_fidelity_gpu,
)


def random_unitary(d, seed=None):
    """Generate a random unitary matrix using QR decomposition."""
    if seed is not None:
        np.random.seed(seed)
    
    # Generate random complex matrix
    A = np.random.randn(d, d) + 1j * np.random.randn(d, d)
    
    # QR decomposition gives us a unitary matrix Q
    Q, R = np.linalg.qr(A)
    
    # Normalize diagonal of R to ensure Q is uniformly distributed
    Lambda = np.diag(np.diag(R) / np.abs(np.diag(R)))
    return Q @ Lambda


@pytest.mark.skipif(not is_jax_available(), reason="JAX not installed")
class TestGPUAccelerators:
    
    def test_jax_availability(self):
        """Test that JAX availability detection works."""
        assert is_jax_available() is True
        # GPU may or may not be available, just check it returns a bool
        assert isinstance(is_gpu_available(), bool)
    
    def test_compose_unitary_single_gate(self):
        """Test unitary composition with single gate."""
        # Create mock context
        class MockContext:
            qubit_dim = 2
        
        # Create mock gate
        class MockGate:
            def unitary(self, n_max, ctx):
                d = ctx.qubit_dim * (n_max + 1)
                return np.eye(d, dtype=np.complex128)
        
        ctx = MockContext()
        gate = MockGate()
        n_max = 5
        
        # Test composition
        U = compose_unitary_gpu([gate], n_max=n_max, ctx=ctx, cache=None)
        
        expected_dim = ctx.qubit_dim * (n_max + 1)
        assert U.shape == (expected_dim, expected_dim)
        assert U.dtype == np.complex128
        assert np.allclose(U, np.eye(expected_dim))
    
    def test_compose_unitary_multiple_gates(self):
        """Test unitary composition with multiple gates."""
        class MockContext:
            qubit_dim = 2
        
        class MockGate:
            def __init__(self, unitary):
                self._unitary = unitary
            
            def unitary(self, n_max, ctx):
                return self._unitary
        
        ctx = MockContext()
        n_max = 2
        d = ctx.qubit_dim * (n_max + 1)  # 6
        
        # Create test unitaries (use random UNITARY matrices)
        U1 = random_unitary(d, seed=42)
        U2 = random_unitary(d, seed=43)
        
        gates = [MockGate(U1), MockGate(U2)]
        
        # Test composition
        U_result = compose_unitary_gpu(gates, n_max=n_max, ctx=ctx, cache=None)
        
        # Expected: U2 @ U1
        U_expected = U2 @ U1
        
        assert U_result.shape == (d, d)
        assert np.allclose(U_result, U_expected)
    
    def test_fidelity_calculation(self):
        """Test fidelity calculation."""
        d = 10
        
        # Test 1: Perfect fidelity (U = V)
        U = np.eye(d, dtype=np.complex128)
        V = np.eye(d, dtype=np.complex128)
        fid = unitary_avg_fidelity_gpu(U, V)
        assert np.isclose(fid, 1.0), f"Perfect fidelity should be 1.0, got {fid}"
        
        # Test 2: Random unitaries (fidelity should be in [0, 1])
        U = random_unitary(d, seed=42)
        V = random_unitary(d, seed=43)
        fid = unitary_avg_fidelity_gpu(U, V)
        assert 0.0 <= fid <= 1.0, f"Fidelity should be in [0, 1], got {fid}"
        
        # Test 3: Global phase should not affect fidelity
        # U = I and V = -I differ only by global phase, so fidelity = 1
        U = np.eye(d, dtype=np.complex128)
        V = -np.eye(d, dtype=np.complex128)
        fid = unitary_avg_fidelity_gpu(U, V)
        assert np.isclose(fid, 1.0), f"Fidelity of I and -I should be 1.0 (global phase), got {fid}"
        
        # Test 4: Truly orthogonal unitaries should have lower fidelity
        # Create a permutation matrix (shifts all basis states)
        U = np.eye(d, dtype=np.complex128)
        V = np.roll(np.eye(d, dtype=np.complex128), 1, axis=0)  # Cyclic permutation
        fid = unitary_avg_fidelity_gpu(U, V)
        assert 0.0 <= fid <= 1.0, f"Fidelity should be in [0, 1], got {fid}"
        # Permutation matrix should have moderate/low fidelity with identity
        assert fid < 0.3, f"Fidelity of I and permutation should be low, got {fid}"
        
        # Test 5: U and U^dag (conjugate transpose) should have some fidelity
        U = random_unitary(d, seed=44)
        V = U.conj().T
        fid = unitary_avg_fidelity_gpu(U, V)
        assert 0.0 <= fid <= 1.0, f"Fidelity should be in [0, 1], got {fid}"
    
    def test_enable_disable_acceleration(self):
        """Test enabling and disabling GPU acceleration."""
        # Try to enable
        enabled = enable_jax_acceleration(verbose=False)
        
        # Should return True if JAX is available
        assert enabled is True
        
        # Try to disable
        disabled = disable_jax_acceleration(verbose=False)
        assert disabled is True
    
    def test_compose_empty_gates(self):
        """Test composition with empty gate list."""
        class MockContext:
            qubit_dim = 2
        
        ctx = MockContext()
        n_max = 5
        
        U = compose_unitary_gpu([], n_max=n_max, ctx=ctx, cache=None)
        
        expected_dim = ctx.qubit_dim * (n_max + 1)
        assert U.shape == (expected_dim, expected_dim)
        assert np.allclose(U, np.eye(expected_dim))


@pytest.mark.skipif(is_jax_available(), reason="Test JAX not available fallback")
class TestGPUAcceleratorsNoJAX:
    
    def test_jax_not_available(self):
        """Test that module handles missing JAX gracefully."""
        assert is_jax_available() is False
        enabled = enable_jax_acceleration(verbose=False)
        assert enabled is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
