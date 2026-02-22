# qubox/compile/__init__.py

from .param_space import ParamBlock, ParamSpace
from .templates import (
    GateTemplate,
    DisplacementTemplate,
    SQRTemplate,
    QubitRotationTemplate,
    SNAPTemplate,
)
from .ansatz import Ansatz
from .evaluators import compose_unitary, compose_superop, unitary_avg_fidelity
from .objectives import ObjectiveConfig, make_objective
from .optimizers import OptimizerConfig, run_optimization
from .api import compile_with_ansatz

# GPU acceleration utilities
from .gpu_accelerators import (
    enable_jax_acceleration,
    disable_jax_acceleration,
    is_jax_available,
    is_gpu_available,
    is_acceleration_enabled,
    benchmark_gpu_speedup,
)

__all__ = [
    "ParamBlock",
    "ParamSpace",
    "GateTemplate",
    "DisplacementTemplate",
    "SQRTemplate",
    "QubitRotationTemplate",
    "SNAPTemplate",
    "Ansatz",
    "compose_unitary",
    "compose_superop",
    "unitary_avg_fidelity",
    "ObjectiveConfig",
    "make_objective",
    "OptimizerConfig",
    "run_optimization",
    "compile_with_ansatz",
    # GPU acceleration
    "enable_jax_acceleration",
    "disable_jax_acceleration",
    "is_jax_available",
    "is_gpu_available",
    "is_acceleration_enabled",
    "benchmark_gpu_speedup",
]
