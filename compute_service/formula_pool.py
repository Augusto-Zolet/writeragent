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
- Periodic worker memory recycling (after max_tasks)
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

from compute_service.config import ComputeSettings
from compute_service.worker_base import BaseProcessPool

log = logging.getLogger("compute_service.formula")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKER_SCRIPT = os.path.join(_SCRIPT_DIR, "formula_worker.py")


class FormulaProcessPool(BaseProcessPool):
    """Bounded pool of persistent worker subprocesses for formula calculations."""

    def __init__(
        self,
        num_workers: int = 4,
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

        # Case 1: Stateful shared session (mode="shared") -> Sticky worker affinity
        if mode == "shared" and session_id and self.workers:
            worker_idx = abs(hash(session_id)) % len(self.workers)
            target_worker = self.workers[worker_idx]
            res = target_worker.execute(payload, timeout_sec=eff_timeout)
            if target_worker.tasks_executed >= self.max_tasks:
                log.info(
                    "Recycling formula worker #%d after %d tasks to refresh memory",
                    target_worker.worker_id,
                    target_worker.tasks_executed,
                )
                target_worker.kill()
            if req_id is not None and isinstance(res, dict):
                res["id"] = req_id
            return res

        # Case 2: Stateless isolated execution (mode="isolated") -> Lease from idle queue
        leased_worker = self.lease_worker(timeout_sec=eff_timeout)
        if leased_worker is None:
            return {
                "id": req_id,
                "status": "error",
                "code": "WORKER_POOL_BUSY",
                "error": "All formula workers are currently busy and request timed out waiting for worker lease.",
            }

        try:
            res = leased_worker.execute(payload, timeout_sec=eff_timeout)
            if req_id is not None and isinstance(res, dict):
                res["id"] = req_id
            return res
        finally:
            self.release_worker(leased_worker)


# Global singleton per server process
_GLOBAL_FORMULA_POOL: FormulaProcessPool | None = None
_GLOBAL_FORMULA_POOL_LOCK = threading.Lock()


def get_formula_pool(settings: ComputeSettings | None = None) -> FormulaProcessPool:
    """Retrieve or initialize the global formula process pool."""
    global _GLOBAL_FORMULA_POOL
    with _GLOBAL_FORMULA_POOL_LOCK:
        if _GLOBAL_FORMULA_POOL is None:
            if settings is not None:
                num_w = getattr(settings, "workers", None) or settings.max_threads
                _GLOBAL_FORMULA_POOL = FormulaProcessPool(
                    num_workers=num_w,
                    default_timeout_sec=settings.default_timeout_sec,
                    max_tasks=getattr(settings, "worker_max_tasks", 500),
                )
            else:
                _GLOBAL_FORMULA_POOL = FormulaProcessPool(num_workers=min(16, (os.cpu_count() or 1) + 2))
        return _GLOBAL_FORMULA_POOL


def shutdown_formula_pool() -> None:
    """Shut down the global formula process pool."""
    global _GLOBAL_FORMULA_POOL
    with _GLOBAL_FORMULA_POOL_LOCK:
        if _GLOBAL_FORMULA_POOL is not None:
            _GLOBAL_FORMULA_POOL.shutdown()
            _GLOBAL_FORMULA_POOL = None
