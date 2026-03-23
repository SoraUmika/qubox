# qubox_v2/core/logging.py
"""
Unified logging configuration for qubox and qm loggers.
"""
import sys
import logging
from typing import Union, Optional
from contextlib import contextmanager
from collections.abc import Iterable

QUBOX_LOGGER_NAME = "qubox"


def configure_global_logging(
    *,
    level: Union[int, str] = logging.INFO,
    fmt: str = "[%(levelname)s] %(asctime)s %(name)s: %(message)s",
    qm_user_config=None,
) -> None:
    """
    Configure logging for both 'qubox' and 'qm' in a unified way.

    - Attaches a StreamHandler to the 'qubox' package logger.
    - Optionally calls qm.config_loggers(...) so the 'qm' logger
      uses compatible settings (stdout + Datadog, if enabled).

    Safe to call multiple times: handlers are only added once.
    """
    qlogger = logging.getLogger(QUBOX_LOGGER_NAME)

    if not qlogger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(fmt))
        qlogger.addHandler(handler)

    if isinstance(level, str):
        level = logging.getLevelName(level.upper())

    qlogger.setLevel(level)
    qlogger.propagate = False

    if qm_user_config is not None:
        try:
            from qm.logging_utils import config_loggers as qm_config_loggers
            qm_config_loggers(qm_user_config)
        except ImportError:
            pass


def get_logger(name: str) -> logging.Logger:
    """
    Convenience helper: get a logger under the 'qubox' namespace.

    Example:
        logger = get_logger(__name__)  # returns 'qubox.hardware.controller', etc.
    """
    # Handle qubox_v2.* names by mapping them under the 'qubox' namespace
    # so they inherit the configured log level from configure_global_logging().
    if name.startswith("qubox_v2."):
        suffix = name[len("qubox_v2."):]
        return logging.getLogger(f"{QUBOX_LOGGER_NAME}.{suffix}")
    if name == "qubox_v2":
        return logging.getLogger(QUBOX_LOGGER_NAME)
    if name.startswith(QUBOX_LOGGER_NAME + "."):
        return logging.getLogger(name)
    if name == QUBOX_LOGGER_NAME:
        return logging.getLogger(name)
    return logging.getLogger(f"{QUBOX_LOGGER_NAME}.{name}")


@contextmanager
def temporarily_set_levels(loggers: Iterable[logging.Logger], level: int):
    """Temporarily change log levels, restoring on exit."""
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
    """Temporarily disable loggers, restoring on exit."""
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
