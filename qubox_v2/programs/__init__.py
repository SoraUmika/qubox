# qubox_v2/programs/__init__.py
"""QUA program factories for cQED experiments.

Programs are organized by category for cleaner imports::

    # Category-based import (preferred)
    from qubox_v2.programs.spectroscopy import resonator_spectroscopy
    from qubox_v2.programs.time_domain import temporal_rabi, T1_relaxation
    from qubox_v2.programs.calibration import all_xy, randomized_benchmarking
    from qubox_v2.programs.readout import iq_blobs, readout_butterfly_measurement
    from qubox_v2.programs.cavity import storage_chi_ramsey
    from qubox_v2.programs.tomography import qubit_state_tomography

    # Legacy flat import (still works)
    from qubox_v2.programs import cQED_programs

The monolithic ``cQED_programs`` module is preserved for backward
compatibility. Category modules re-export from it.
"""
from .cQED_programs import *  # noqa: F401, F403 – re-export all program factories

# Category sub-modules (importable via qubox_v2.programs.spectroscopy, etc.)
from . import spectroscopy  # noqa: F401
from . import time_domain   # noqa: F401
from . import calibration   # noqa: F401
from . import readout       # noqa: F401
from . import cavity        # noqa: F401
from . import tomography    # noqa: F401
