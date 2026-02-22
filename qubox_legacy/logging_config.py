# qubox/logging_config.py
import sys
import logging
from typing import Union, Optional
from contextlib import contextmanager
from qm.user_config import UserConfig
from qm.logging_utils import config_loggers as qm_config_loggers  # adjust import path if needed
from collections.abc import Iterable

QUBOX_LOGGER_NAME = "qubox"


def configure_global_logging(
    *,
    level: Union[int, str] = logging.INFO,
    fmt: str = "[%(levelname)s] %(asctime)s %(name)s: %(message)s",
    qm_user_config: Optional[UserConfig] = None,
) -> None:
    """
    Configure logging for both 'qubox' and 'qm' in a unified way.

    - Attaches a StreamHandler to the 'qubox' package logger.
    - Optionally calls qm.config_loggers(...) so the 'qm' logger
      uses compatible settings (stdout + Datadog, if enabled).

    Safe to call multiple times: handlers are only added once.
    """

    # ── 1) Configure the qubox logger ──────────────────────────────
    qlogger = logging.getLogger(QUBOX_LOGGER_NAME)

    if not qlogger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(fmt))
        qlogger.addHandler(handler)

    # You can either accept strings ("DEBUG") or ints (10)
    if isinstance(level, str):
        level = logging.getLevelName(level.upper())

    qlogger.setLevel(level)
    # If you don't want messages bubbling up to the root logger:
    qlogger.propagate = False

    # ── 2) Configure the qm logger using its own helper ───────────
    if qm_user_config is not None:
        # This will configure logger "qm" (stdout + Datadog)
        qm_config_loggers(qm_user_config)


def get_logger(name: str) -> logging.Logger:
    """
    Convenience helper: get a logger under the 'qubox' namespace.

    Example:
        logger = get_logger(__name__)  # returns 'qubox.qua', etc.
    """
    # If you pass module __name__ (e.g. "qubox.qua"), just return that:
    if name.startswith(QUBOX_LOGGER_NAME):
        return logging.getLogger(name)

    # Otherwise, attach under 'qubox.'
    return logging.getLogger(f"{QUBOX_LOGGER_NAME}.{name}")

@contextmanager
def temporarily_set_levels(loggers: Iterable[logging.Logger], level: int):
    old_levels = {}
    loggers = list(loggers)
    for lg in loggers:
        old_levels[lg] = lg.getEffectiveLevel()
        lg.setLevel(level)
    try:
        yield
    finally:
        for lg, old in old_levels.items():
            lg.setLevel(old)

@contextmanager
def temporarily_disable(loggers: Iterable[logging.Logger]):
    old_states = {}
    loggers = list(loggers)
    for lg in loggers:
        old_states[lg] = lg.disabled
        lg.disabled = True
    try:
        yield
    finally:
        for lg, old in old_states.items():
            lg.disabled = old
