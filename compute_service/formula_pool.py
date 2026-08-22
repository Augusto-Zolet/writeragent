# WriterAgent - Python Compute Service Formula Process Pool
# Copyright (c) 2026 KeithCu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Process pool supervisor for formula and general sandboxed Python execution.

Maintains a bounded pool of warm subprocesses. Provides:
- 100% crash isolation (master HTTP server never crashes)
- Hard SIGKILL termination for hangs/timeouts
- Multi-core linear CPU scaling (bypasses single-interpreter GIL)
- Sticky session affinity for stateful sessions (mode="shared")
- Exclusive occupancy so sticky and isolated jobs never share a worker concurrently
- Periodic worker memory recycling (after max_tasks)
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

from compute_service.config import ComputeSettings
from compute_service.worker_base import BaseProcessPool, BaseProcessWorker

log = logging.getLogger("compute_service.formula")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKER_SCRIPT = os.path.join(_SCRIPT_DIR, "formula_worker.py")


def _remaining_sec(deadline: float, *, floor: float = 0.01) -> float:
    return max(floor, deadline - time.monotonic())


class FormulaProcessPool(BaseProcessPool):
    """Bounded pool of persistent worker subprocesses for formula calculations."""

    def __init__(
        self,
        num_workers: int = 1,
        default_timeout_sec: int = 30,
        max_tasks: int = 500,
    ) -> None:
        super().__init__(
            script_path=_WORKER_SCRIPT,
            num_workers=num_workers,
            default_timeout_sec=default_timeout_sec,
            max_tasks=max_tasks,
            worker_name="Formula worker",
        )

    def check_dependencies(
        self,
        packages: list[str] | None = None,
        timeout_sec: float = 10.0,
    ) -> tuple[bool, str | None]:
        """Ask an idle worker to verify required dependencies (e.g. numpy, sympy).

        Returns (success, error_message).
        """
        if self._is_shutdown or not self.workers:
            return False, "Formula compute pool is not running."

        target_packages = ["numpy", "sympy"] if packages is None else packages
        leased = self.lease_any(timeout_sec=timeout_sec)
        if leased is None:
            return False, "Failed to lease a formula worker subprocess for dependency check."

        try:
            payload = {
                "action": "check_dependencies",
                "packages": target_packages,
            }
            res = leased.execute(payload, timeout_sec=timeout_sec)
            if res.get("status") == "ok":
                return True, None
            missing = res.get("missing")
            if missing and isinstance(missing, list):
                missing_str = ", ".join(str(m) for m in missing)
                return False, (
                    f"Error: {missing_str} is not installed in the current Python environment.\n"
                    "Please start the server using './compute_service/start.sh' or activate the correct virtual environment."
                )
            err = res.get("error") or "Unknown error during worker dependency check."
            return False, str(err)
        finally:
            self.release_worker(leased)

    def execute(
        self,
        code: str,
        data: Any = None,
        session_id: str | None = None,
        timeout_sec: int | None = None,
        *,
        mode: str = "isolated",
        init_script: str | None = None,
        req_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute formula code on an appropriate worker subprocess."""
        if self._is_shutdown or not self.workers:
            return {
                "id": req_id,
                "status": "error",
                "code": "SERVICE_SHUTDOWN",
                "error": "Formula compute pool is shutting down.",
            }

        eff_timeout = float(timeout_sec or self.default_timeout_sec)
        deadline = time.monotonic() + eff_timeout

        # Optimize large matrix data using zero-copy split_grid binary envelope
        wire_data = data
        if isinstance(data, list) and data:
            from plugin.scripting.payload_codec import host_pack_data

            try:
                wire_data = host_pack_data(data, min_cells=1000)
            except Exception:
                wire_data = data

        payload = {
            "id": req_id,
            "code": code,
            "data": wire_data,
            "session_id": session_id,
            "mode": mode,
            "timeout_sec": int(eff_timeout),
            "init_script": init_script,
        }

        leased: BaseProcessWorker | None
        # Snapshot workers under the pool lock to avoid a TOCTOU race with
        # concurrent shutdown() which calls self.workers.clear() under the same lock.
        # Without the snapshot, the IndexError window between len() and [] access
        # is real even on CPython when shutdown races execute on another thread.
        with self._lock:
            workers_snapshot = list(self.workers)
        if mode == "shared" and session_id and workers_snapshot:
            worker_idx = abs(hash(session_id)) % len(workers_snapshot)
            target_worker = workers_snapshot[worker_idx]
            leased = self.lease_specific(target_worker, timeout_sec=_remaining_sec(deadline))
            busy_code = "WORKER_POOL_BUSY"
            busy_err = "Sticky session worker is busy and request timed out waiting for worker lease."
        else:
            leased = self.lease_any(timeout_sec=_remaining_sec(deadline))
            busy_code = "WORKER_POOL_BUSY"
            busy_err = "All formula workers are currently busy and request timed out waiting for worker lease."

        if leased is None:
            return {
                "id": req_id,
                "status": "error",
                "code": busy_code,
                "error": busy_err,
            }

        try:
            res = leased.execute(payload, timeout_sec=_remaining_sec(deadline))
            if req_id is not None and isinstance(res, dict):
                res["id"] = req_id
            return res
        finally:
            self.release_worker(leased)


# Global singleton per server process
_GLOBAL_FORMULA_POOL: FormulaProcessPool | None = None
_GLOBAL_FORMULA_POOL_LOCK = threading.Lock()


def get_formula_pool(settings: ComputeSettings | None = None) -> FormulaProcessPool:
    """Retrieve or initialize the global formula process pool."""
    global _GLOBAL_FORMULA_POOL
    with _GLOBAL_FORMULA_POOL_LOCK:
        if _GLOBAL_FORMULA_POOL is None:
            if settings is not None:
                num_w = getattr(settings, "workers", None) or getattr(settings, "max_workers", None) or 2
                _GLOBAL_FORMULA_POOL = FormulaProcessPool(
                    num_workers=num_w,
                    default_timeout_sec=settings.default_timeout_sec,
                    max_tasks=getattr(settings, "worker_max_tasks", 500),
                )
            else:
                _GLOBAL_FORMULA_POOL = FormulaProcessPool(num_workers=1)
        return _GLOBAL_FORMULA_POOL


def shutdown_formula_pool() -> None:
    """Shut down the global formula process pool."""
    global _GLOBAL_FORMULA_POOL
    with _GLOBAL_FORMULA_POOL_LOCK:
        if _GLOBAL_FORMULA_POOL is not None:
            _GLOBAL_FORMULA_POOL.shutdown()
            _GLOBAL_FORMULA_POOL = None
