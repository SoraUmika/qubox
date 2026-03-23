"""Notebook session bootstrap, sharing, and lifecycle management.

Provides helpers for managing a shared ``Session`` across multiple notebook
cells and across separate notebook kernels within the same cooldown.
"""

from __future__ import annotations

import json
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..devices import SampleRegistry
from ..session import Session

_BOOTSTRAP_FILE_NAME = "notebook_session.json"
_DEFAULT_SHARED_SESSION_KEY: str | None = None
_SHARED_NOTEBOOK_SESSIONS: dict[str, Session] = {}


@dataclass(frozen=True, slots=True)
class NotebookSessionBootstrap:
    """Serializable bootstrap record for reopening a notebook session."""

    sample_id: str
    cooldown_id: str
    registry_base: str
    qop_ip: str | None = None
    cluster_name: str | None = None
    auto_save_calibration: bool = True

    @property
    def session_key(self) -> str:
        return f"{self.registry_base}|{self.sample_id}|{self.cooldown_id}"


def get_notebook_session_bootstrap_path(
    *,
    sample_id: str,
    cooldown_id: str,
    registry_base: str | Path,
) -> Path:
    """Return the default bootstrap file path for the given cooldown."""
    registry = SampleRegistry(Path(registry_base))
    cooldown_path = registry.cooldown_path(sample_id, cooldown_id)
    return cooldown_path / "artifacts" / "runtime" / _BOOTSTRAP_FILE_NAME


def save_notebook_session_bootstrap(
    bootstrap: NotebookSessionBootstrap,
    *,
    path: str | Path | None = None,
) -> Path:
    """Persist a bootstrap record to disk."""
    target = Path(path) if path is not None else get_notebook_session_bootstrap_path(
        sample_id=bootstrap.sample_id,
        cooldown_id=bootstrap.cooldown_id,
        registry_base=bootstrap.registry_base,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(bootstrap), indent=2), encoding="utf-8")
    return target


def load_notebook_session_bootstrap(path: str | Path) -> NotebookSessionBootstrap:
    """Load a bootstrap record from disk."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return NotebookSessionBootstrap(**payload)


def get_shared_session(*, session_key: str | None = None) -> Session | None:
    """Return the currently registered shared session, or *None*."""
    key = session_key or _DEFAULT_SHARED_SESSION_KEY
    if key is None:
        return None
    return _SHARED_NOTEBOOK_SESSIONS.get(key)


def register_shared_session(
    session: Session,
    *,
    bootstrap: NotebookSessionBootstrap,
    persist_bootstrap: bool = True,
    set_default: bool = True,
) -> Session:
    """Register *session* as the shared notebook session."""
    global _DEFAULT_SHARED_SESSION_KEY

    _SHARED_NOTEBOOK_SESSIONS[bootstrap.session_key] = session
    if set_default:
        _DEFAULT_SHARED_SESSION_KEY = bootstrap.session_key
    if persist_bootstrap:
        save_notebook_session_bootstrap(bootstrap)
    return session


def open_shared_session(
    *,
    sample_id: str,
    cooldown_id: str,
    registry_base: str | Path,
    qop_ip: str | None = None,
    cluster_name: str | None = None,
    auto_save_calibration: bool = True,
    connect: bool = True,
    reuse_existing: bool = True,
    force_reopen: bool = False,
    persist_bootstrap: bool = True,
    set_default: bool = True,
    **kwargs: Any,
) -> Session:
    """Open (or reuse) a shared notebook session for the given cooldown."""
    bootstrap = NotebookSessionBootstrap(
        sample_id=sample_id,
        cooldown_id=cooldown_id,
        registry_base=str(Path(registry_base)),
        qop_ip=qop_ip,
        cluster_name=cluster_name,
        auto_save_calibration=auto_save_calibration,
    )
    existing = get_shared_session(session_key=bootstrap.session_key)
    if existing is not None and reuse_existing and not force_reopen:
        if persist_bootstrap:
            save_notebook_session_bootstrap(bootstrap)
        if set_default:
            global _DEFAULT_SHARED_SESSION_KEY
            _DEFAULT_SHARED_SESSION_KEY = bootstrap.session_key
        return existing

    if existing is not None and force_reopen:
        with suppress(Exception):
            existing.close()

    session = Session.open(
        sample_id=sample_id,
        cooldown_id=cooldown_id,
        registry_base=Path(registry_base),
        qop_ip=qop_ip,
        cluster_name=cluster_name,
        auto_save_calibration=auto_save_calibration,
        connect=connect,
        **kwargs,
    )
    return register_shared_session(
        session,
        bootstrap=bootstrap,
        persist_bootstrap=persist_bootstrap,
        set_default=set_default,
    )


def restore_shared_session(
    path: str | Path,
    *,
    connect: bool = True,
    reuse_existing: bool = True,
    force_reopen: bool = False,
    set_default: bool = True,
    **kwargs: Any,
) -> Session:
    """Restore a shared session from a persisted bootstrap file."""
    bootstrap = load_notebook_session_bootstrap(path)
    return open_shared_session(
        sample_id=bootstrap.sample_id,
        cooldown_id=bootstrap.cooldown_id,
        registry_base=bootstrap.registry_base,
        qop_ip=bootstrap.qop_ip,
        cluster_name=bootstrap.cluster_name,
        auto_save_calibration=bootstrap.auto_save_calibration,
        connect=connect,
        reuse_existing=reuse_existing,
        force_reopen=force_reopen,
        persist_bootstrap=True,
        set_default=set_default,
        **kwargs,
    )


def require_shared_session(
    *,
    bootstrap_path: str | Path | None = None,
    sample_id: str | None = None,
    cooldown_id: str | None = None,
    registry_base: str | Path | None = None,
    qop_ip: str | None = None,
    cluster_name: str | None = None,
    auto_save_calibration: bool = True,
    connect: bool = True,
    reuse_existing: bool = True,
    force_reopen: bool = False,
    **kwargs: Any,
) -> Session:
    """Return the shared session, opening one if necessary."""
    existing = get_shared_session()
    if existing is not None and reuse_existing and not force_reopen:
        return existing

    if bootstrap_path is not None and Path(bootstrap_path).exists():
        return restore_shared_session(
            bootstrap_path,
            connect=connect,
            reuse_existing=reuse_existing,
            force_reopen=force_reopen,
            **kwargs,
        )

    if sample_id is None or cooldown_id is None or registry_base is None:
        raise RuntimeError(
            "No shared notebook session is registered. Open one in notebook 00 or provide "
            "bootstrap_path plus sample_id/cooldown_id/registry_base."
        )

    return open_shared_session(
        sample_id=sample_id,
        cooldown_id=cooldown_id,
        registry_base=registry_base,
        qop_ip=qop_ip,
        cluster_name=cluster_name,
        auto_save_calibration=auto_save_calibration,
        connect=connect,
        reuse_existing=reuse_existing,
        force_reopen=force_reopen,
        **kwargs,
    )


def close_shared_session(*, session_key: str | None = None) -> None:
    """Close and deregister the shared notebook session."""
    global _DEFAULT_SHARED_SESSION_KEY

    key = session_key or _DEFAULT_SHARED_SESSION_KEY
    if key is None:
        return
    session = _SHARED_NOTEBOOK_SESSIONS.pop(key, None)
    if session is not None:
        with suppress(Exception):
            session.close()
    if _DEFAULT_SHARED_SESSION_KEY == key:
        _DEFAULT_SHARED_SESSION_KEY = next(iter(_SHARED_NOTEBOOK_SESSIONS), None)


def resolve_active_mixer_targets(session: Session, *, include_skipped: bool = False) -> dict[str, Any]:
    """Return a dict of active mixer elements and their LO/IF/RF frequencies."""
    resolved = session.hw.get_active_mixer_elements(include_skipped=True)
    active_elements = list(resolved.get("active", []))
    skipped_elements = list(resolved.get("skipped", []))

    active_targets = []
    for element in active_elements:
        lo_hz = float(session.hw.get_element_lo(element))
        if_hz = float(session.hw.get_element_if(element))
        active_targets.append(
            {
                "element": element,
                "lo_hz": lo_hz,
                "if_hz": if_hz,
                "rf_hz": lo_hz + if_hz,
            }
        )

    payload = {"active": active_targets}
    if include_skipped:
        payload["skipped"] = skipped_elements
    return payload


__all__ = [
    "NotebookSessionBootstrap",
    "close_shared_session",
    "get_notebook_session_bootstrap_path",
    "get_shared_session",
    "load_notebook_session_bootstrap",
    "open_shared_session",
    "register_shared_session",
    "require_shared_session",
    "resolve_active_mixer_targets",
    "restore_shared_session",
    "save_notebook_session_bootstrap",
]
