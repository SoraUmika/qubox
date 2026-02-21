"""qubox_v2.compat.legacy
========================
Import this module to enable ``from qubox.…`` style imports that
transparently redirect to ``qubox_v2.…``.

Example::

    import qubox_v2.compat.legacy   # activate shim
    from qubox.program_manager import QuaProgramManager  # works!
"""
# The actual machinery lives in compat/__init__.py — this module
# exists purely so ``import qubox_v2.compat.legacy`` works as
# documented.
from . import _finder as _  # noqa: F401 — ensure finder is installed
