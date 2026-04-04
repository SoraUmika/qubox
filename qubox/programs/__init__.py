"""QUA program factories for cQED experiments.

Programs are organized by category for cleaner imports::

    # Category-based import (preferred)
    from qubox.programs.spectroscopy import resonator_spectroscopy
    from qubox.programs.time_domain import temporal_rabi, T1_relaxation
    from qubox.programs.calibration import all_xy, randomized_benchmarking
    from qubox.programs.readout import iq_blobs, readout_butterfly_measurement
    from qubox.programs.cavity import storage_chi_ramsey
    from qubox.programs.tomography import qubit_state_tomography

Internal code should import from ``qubox.programs.api`` or directly
from category modules.
"""
from .api import *  # noqa: F401, F403

# Category sub-modules (importable via qubox_v2.programs.spectroscopy, etc.)
from . import spectroscopy  # noqa: F401
from . import time_domain   # noqa: F401
from . import calibration   # noqa: F401
from . import readout       # noqa: F401
from . import cavity        # noqa: F401
from . import tomography    # noqa: F401
from . import measurement   # noqa: F401
from . import circuit_ir  # noqa: F401
from . import circuit_runner  # noqa: F401
from . import gate_tuning  # noqa: F401
