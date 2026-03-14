# qubox_v2/hardware/queue_manager.py
"""
QueueManager: multi-user queue operations for the QM queue system.

Extracted from QuaProgramManager — provides queue submission, multi-job
execution with global progress bars, and queue administration helpers.
"""
from __future__ import annotations

import contextlib
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Union

import numpy as np
from grpclib.exceptions import StreamTerminatedError
from tqdm import tqdm

from ..core.errors import ConfigError, ConnectionError, JobError
from ..core.utils import require
from .program_runner import ExecMode, RunResult, ProgramRunner

_logger = logging.getLogger(__name__)


class QueueManager:
    """
    Queue-based multi-user job management.

    Depends on:
        - ProgramRunner (for program memory, processors, output collection)
        - HardwareController (for QM instance and quiet_external_logs)
    """

    def __init__(self, runner: ProgramRunner):
        self.runner = runner

    @property
    def _qm(self):
        return self.runner.hw.qm

    def _require_qm(self):
        require(self._qm is not None, "QM not initialized.", ConfigError)

    # ─── Queue info ───────────────────────────────────────────────
    def count(self) -> int:
        self._require_qm()
        return int(self._qm.queue.count)

    def pending_jobs(self) -> list:
        self._require_qm()
        return list(self._qm.queue.pending_jobs)

    def get_at(self, position: int):
        self._require_qm()
        require(position >= 1, "Queue is 1-based: position must be >= 1", JobError)
        return self._qm.queue.get_at(int(position))

    def get(self, job_id: str):
        self._require_qm()
        return self._qm.queue.get(job_id)

    def get_by_user_id(self, user_id: str):
        self._require_qm()
        return self._qm.queue.get_by_user_id(user_id)

    def remove_by_id(self, job_id: str) -> None:
        self._require_qm()
        self._qm.queue.remove_by_id(job_id)

    def remove_by_position(self, position: int) -> None:
        self._require_qm()
        require(position >= 1, "Queue is 1-based: position must be >= 1", JobError)
        self._qm.queue.remove_by_position(int(position))

    def remove_by_user_id(self, user_id: str) -> None:
        self._require_qm()
        self._qm.queue.remove_by_user_id(user_id)

    # ─── Submit ───────────────────────────────────────────────────
    def submit(self, qua_prog, *, to_start: bool = False, quiet: bool = True):
        """Submit a program to the QM queue. Returns QmPendingJob."""
        self._require_qm()

        cfg_snapshot = self.runner.config.build_qm_config()
        self.runner._remember_program(
            qua_prog, cfg=cfg_snapshot,
            meta={"last_mode": "hardware", "queued": True, "queue_submit": True, "queue_to_start": bool(to_start)},
        )

        cm = self._quiet_logs() if quiet else contextlib.nullcontext()
        with cm:
            try:
                pending = (
                    self._qm.queue.add_to_start(qua_prog) if to_start
                    else self._qm.queue.add(qua_prog)
                )
            except StreamTerminatedError as e:
                raise ConnectionError("Connection lost while adding job to queue.") from e
            except Exception as e:
                raise JobError(f"Failed to add job to queue: {e}") from e

        self.runner._remember_program(
            qua_prog, cfg=cfg_snapshot,
            meta={
                "job_id": getattr(pending, "job_id", None),
                "time_added": getattr(pending, "time_added", None),
                "user_added": getattr(pending, "user_added", None),
            },
        )
        return pending

    def submit_many(self, programs, *, to_start: bool = False, quiet: bool = True):
        """Submit multiple programs. Last submitted becomes current_program."""
        return [self.submit(p, to_start=to_start, quiet=quiet) for p in programs]

    def submit_many_with_progress(
        self,
        programs,
        *,
        to_start: bool = False,
        quiet: bool = True,
        show_submit_progress: bool = True,
        desc: str = "Submitting to queue...",
    ) -> list:
        """Submit many programs with a progress bar."""
        self._require_qm()
        show_bar = bool(show_submit_progress) and _logger.isEnabledFor(logging.INFO)
        cm = self._quiet_logs() if quiet else contextlib.nullcontext()

        pendings = []
        with cm, tqdm(total=len(programs), desc=desc, disable=not show_bar, leave=True) as bar:
            for prog in programs:
                pending = self.submit(prog, to_start=to_start, quiet=False)
                pendings.append(pending)
                bar.update(1)
        return pendings

    # ─── Run many ─────────────────────────────────────────────────
    def run_many(
        self,
        pending_jobs: list,
        *,
        n_totals: int | list[int],
        processors: list | None = None,
        progress_handle: str = "iteration",
        show_total_progress: bool = True,
        print_report: bool = False,
        auto_job_halt: bool = True,
        quiet: bool = True,
        desc: str = "Running queued...",
        sleep_s: float = 0.05,
        **proc_kwargs,
    ) -> list[RunResult]:
        """Run queued jobs sequentially with a single global progress bar."""
        self._require_qm()

        if isinstance(n_totals, int):
            n_list = [int(n_totals)] * len(pending_jobs)
        else:
            n_list = [int(x) for x in n_totals]
            require(len(n_list) == len(pending_jobs), "n_totals length must match pending_jobs.", JobError)

        total_iters = int(sum(n_list))
        procs = processors or self.runner.processors

        show_bar = bool(show_total_progress) and _logger.isEnabledFor(logging.INFO)
        cm = self._quiet_logs() if quiet else contextlib.nullcontext()

        results: list[RunResult] = []
        offset = 0

        with cm, tqdm(total=total_iters, desc=desc, disable=not show_bar, leave=True) as bar:
            for pending, n_total in zip(pending_jobs, n_list):
                try:
                    job = pending.wait_for_execution()
                except StreamTerminatedError as e:
                    raise ConnectionError("Connection lost waiting for queued job.") from e
                except Exception as e:
                    raise JobError(f"Queued job failed to start: {e}") from e

                handles = job.result_handles
                last = 0

                if progress_handle in handles.keys():
                    while handles.is_processing():
                        time.sleep(float(sleep_s))
                        with contextlib.suppress(Exception):
                            h = handles.get(progress_handle)
                            if h is not None:
                                cur = self.runner._progress_value(h.fetch_all())
                                cur = max(0, min(int(cur), int(n_total)))
                                if cur != last:
                                    last = cur
                                    bar.n = offset + last
                                    bar.refresh()
                    with contextlib.suppress(Exception):
                        h = handles.get(progress_handle)
                        if h is not None:
                            cur = self.runner._progress_value(h.fetch_all())
                            cur = max(0, min(int(cur), int(n_total)))
                            last = cur
                            bar.n = offset + last
                            bar.refresh()
                else:
                    while handles.is_processing():
                        time.sleep(float(sleep_s))

                try:
                    out = self.runner._collect_output_from_job(job, print_report=print_report)
                finally:
                    if auto_job_halt:
                        with contextlib.suppress(Exception):
                            job.halt()

                if procs:
                    for proc in procs:
                        try:
                            out = proc(out, **proc_kwargs)
                        except Exception as e:
                            _logger.error("Processor %s failed: %s", getattr(proc, "__name__", repr(proc)), e)

                bar.n = offset + int(n_total)
                bar.refresh()

                results.append(RunResult(
                    mode=ExecMode.HARDWARE, output=out, sim_samples=None,
                    metadata={"n_total": int(n_total), "queued": True},
                ))
                offset += int(n_total)

            bar.n = total_iters
            bar.refresh()

        return results

    # ─── Submit + Run ─────────────────────────────────────────────
    def submit_and_run_many(
        self,
        programs,
        *,
        n_totals: int | list[int],
        to_start: bool = False,
        processors: list | None = None,
        progress_handle: str = "iteration",
        show_submit_progress: bool = True,
        show_total_progress: bool = True,
        quiet: bool = True,
        submit_desc: str = "Submitting to queue...",
        run_desc: str = "Running queued...",
        print_report: bool = False,
        auto_job_halt: bool = True,
        sleep_s: float = 0.05,
        **proc_kwargs,
    ) -> list[RunResult]:
        """Submit many programs then run them sequentially with two progress bars."""
        pendings = self.submit_many_with_progress(
            programs, to_start=to_start, quiet=quiet,
            show_submit_progress=show_submit_progress, desc=submit_desc,
        )
        return self.run_many(
            pendings, n_totals=n_totals, processors=processors,
            progress_handle=progress_handle, show_total_progress=show_total_progress,
            print_report=print_report, auto_job_halt=auto_job_halt,
            quiet=quiet, desc=run_desc, sleep_s=sleep_s, **proc_kwargs,
        )

    # ─── Logging ──────────────────────────────────────────────────
    @contextlib.contextmanager
    def _quiet_logs(self, *, qm_level: int = logging.WARNING):
        names = ["qm"]
        old = []
        for name in names:
            lg = logging.getLogger(name)
            old.append((lg, lg.level))
            lg.setLevel(qm_level)
        try:
            yield
        finally:
            for lg, lvl in old:
                lg.setLevel(lvl)
