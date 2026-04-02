"""Calibration patch preview and application helpers.

Portable logic that wraps :class:`CalibrationOrchestrator` for patch preview
and optional application.  No notebook dependency.
"""

from __future__ import annotations

from typing import Any, Iterable

from ..calibration import CalibrationOrchestrator, Patch


def preview_or_apply_patch_ops(
    session_obj: Any,
    *,
    reason: str,
    proposed_patch_ops: Iterable[dict[str, Any]],
    apply: bool = False,
    print_fn=print,
) -> tuple[Patch | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Preview or apply a set of calibration patch operations.

    Parameters
    ----------
    session_obj:
        Any object accepted by :class:`CalibrationOrchestrator`.
    reason:
        Human-readable reason string for the patch.
    proposed_patch_ops:
        Iterable of dicts with ``"op"`` and optional ``"payload"`` keys.
    apply:
        If *True*, commit the patch after previewing.
    print_fn:
        Callable used for status output (default: ``print``).

    Returns
    -------
    tuple of (Patch | None, preview dict | None, apply-result dict | None)
    """
    patch_ops = list(proposed_patch_ops)
    if not patch_ops:
        print_fn(f"{reason}: no calibration updates were proposed by the fit.")
        return None, None, None

    patch = Patch(reason=reason)
    for patch_op in patch_ops:
        patch.add(patch_op["op"], **patch_op.get("payload", {}))

    orchestrator = CalibrationOrchestrator(session_obj)
    preview = orchestrator.apply_patch(patch, dry_run=True)
    print_fn(f"{reason} patch preview ({preview['n_updates']} updates):")
    for index, update in enumerate(preview.get("preview", []), start=1):
        print_fn(f"  {index}. {update['op']}: {update['payload']}")

    apply_result = None
    if apply:
        apply_result = orchestrator.apply_patch(patch, dry_run=False)
        print_fn(
            f"Applied patch with {apply_result['n_updates']} updates; "
            f"sync_ok={apply_result['sync_ok']}"
        )
    else:
        print_fn("Patch not applied. Enable the stage apply flag to commit the calibration.")

    return patch, preview, apply_result


__all__ = ["preview_or_apply_patch_ops"]
