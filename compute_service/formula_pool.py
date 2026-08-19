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
import queue
import subprocess
import sys
import threading
from typing import Any

from compute_service.config import ComputeSettings

log = logging.getLogger("compute_service.formula")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKER_SCRIPT = os.path.join(_SCRIPT_DIR, "formula_worker.py")


class FormulaProcessWorker:
    """Wrapper around one persistent formula worker subprocess."""

    def __init__(self, worker_id: int) -> None:
        self.worker_id = worker_id
        self.process: subprocess.Popen[bytes] | None = None
        self.lock = threading.Lock()
        self.tasks_executed = 0
        self._spawn()

    def _spawn(self) -> None:
        """Spawn the worker subprocess and wait for readiness handshake."""
        from plugin.scripting.ipc import read_pickle_frame

        cmd = [sys.executable, _WORKER_SCRIPT]
        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if self.process.stdout is not None:
                ready_data = read_pickle_frame(self.process.stdout)
                if isinstance(ready_data, dict):
                    log.info(
                        "Formula worker #%d spawned (pid=%s, status=%s)",
                        self.worker_id,
                        ready_data.get("pid", self.process.pid),
                        ready_data.get("status"),
                    )
            self.tasks_executed = 0
        except Exception as exc:
            log.error("Failed to spawn formula worker #%d: %s", self.worker_id, exc)
            self.process = None

    def is_alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def kill(self) -> None:
        """Forcefully terminate worker process."""
        proc = self.process
        self.process = None
        if proc is not None:
            try:
                proc.kill()
                proc.wait(timeout=1.0)
            except Exception:
                pass

    def execute(self, payload: dict[str, Any], timeout_sec: float) -> dict[str, Any]:
        """Send request to worker process and await response line with timeout."""
        from plugin.scripting.ipc import read_pickle_frame, write_pickle_frame

        with self.lock:
            if not self.is_alive():
                self._spawn()
                if not self.is_alive():
                    return {
                        "status": "error",
                        "code": "WORKER_SPAWN_FAILED",
                        "error": f"Formula worker #{self.worker_id} could not be started.",
                    }

            assert self.process is not None
            assert self.process.stdin is not None
            assert self.process.stdout is not None

            # Optimize large matrix data using zero-copy split_grid binary envelope
            raw_data = payload.get("data")
            if isinstance(raw_data, list) and raw_data:
                from plugin.scripting.payload_codec import host_pack_data
                try:
                    packed = host_pack_data(raw_data, min_cells=1000)
                    if packed is not raw_data:
                        payload = dict(payload)
                        payload["data"] = packed
                except Exception:
                    pass

            try:
                write_pickle_frame(self.process.stdin, payload)
            except (BrokenPipeError, OSError) as exc:
                self.kill()
                return {
                    "status": "error",
                    "code": "WORKER_PIPE_BROKEN",
                    "error": f"Failed to send request to formula worker #{self.worker_id}: {exc}",
                }

            if sys.platform != "win32":
                import select
                ready, _, _ = select.select([self.process.stdout], [], [], timeout_sec)
                if not ready:
                    log.warning(
                        "Formula execution timed out after %.1fs on worker #%d; terminating pid=%s",
                        timeout_sec,
                        self.worker_id,
                        self.process.pid,
                    )
                    self.kill()
                    return {
                        "status": "error",
                        "code": "EXECUTION_TIMEOUT",
                        "error": f"Execution exceeded maximum timeout of {int(timeout_sec)} seconds.",
                        "message": f"Execution exceeded maximum timeout of {int(timeout_sec)} seconds.",
                    }
                try:
                    resp = read_pickle_frame(self.process.stdout)
                except Exception as exc:
                    self.kill()
                    return {
                        "status": "error",
                        "code": "WORKER_CRASHED",
                        "error": f"Formula worker error: {exc}",
                        "message": f"Formula worker error: {exc}",
                    }
                if resp is None or not isinstance(resp, dict):
                    self.kill()
                    return {
                        "status": "error",
                        "code": "EMPTY_RESPONSE",
                        "error": "No response returned from formula worker.",
                    }
                self.tasks_executed += 1
                return resp

            # Windows fallback path
            result_holder: list[dict[str, Any]] = []
            err_holder: list[str] = []

            def _reader() -> None:
                try:
                    if self.process is not None and self.process.stdout is not None:
                        resp = read_pickle_frame(self.process.stdout)
                        if resp is not None and isinstance(resp, dict):
                            result_holder.append(resp)
                        else:
                            err_holder.append("EOF from worker process (process likely crashed or was terminated)")
                except Exception as e:
                    err_holder.append(str(e))

            reader_thread = threading.Thread(target=_reader, daemon=True)
            reader_thread.start()
            reader_thread.join(timeout=timeout_sec)

            if reader_thread.is_alive():
                log.warning(
                    "Formula execution timed out after %.1fs on worker #%d; terminating pid=%s",
                    timeout_sec,
                    self.worker_id,
                    self.process.pid,
                )
                self.kill()
                return {
                    "status": "error",
                    "code": "EXECUTION_TIMEOUT",
                    "error": f"Execution exceeded maximum timeout of {int(timeout_sec)} seconds.",
                    "message": f"Execution exceeded maximum timeout of {int(timeout_sec)} seconds.",
                }

            if err_holder:
                self.kill()
                return {
                    "status": "error",
                    "code": "WORKER_CRASHED",
                    "error": f"Formula worker error: {err_holder[0]}",
                    "message": f"Formula worker error: {err_holder[0]}",
                }

            if not result_holder:
                self.kill()
                return {
                    "status": "error",
                    "code": "EMPTY_RESPONSE",
                    "error": "No response returned from formula worker.",
                }

            self.tasks_executed += 1
            return result_holder[0]


class FormulaProcessPool:
    """Bounded pool of persistent worker subprocesses for formula calculations."""

    def __init__(
        self,
        num_workers: int = 4,
        default_timeout_sec: int = 30,
        max_tasks: int = 500,
    ) -> None:
        self.num_workers = max(1, num_workers)
        self.default_timeout_sec = default_timeout_sec
        self.max_tasks = max_tasks
        self.idle_queue: queue.Queue[FormulaProcessWorker] = queue.Queue()
        self.workers: list[FormulaProcessWorker] = []
        self._is_shutdown = False
        self._lock = threading.Lock()

        for i in range(self.num_workers):
            w = FormulaProcessWorker(i + 1)
            self.workers.append(w)
            self.idle_queue.put(w)

    def is_enabled(self) -> bool:
        return not self._is_shutdown

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
        if self._is_shutdown:
            return {
                "id": req_id,
                "status": "error",
                "code": "SERVICE_SHUTDOWN",
                "error": "Formula compute pool is shutting down.",
            }

        eff_timeout = float(timeout_sec or self.default_timeout_sec)
        payload = {
            "id": req_id,
            "code": code,
            "data": data,
            "session_id": session_id,
            "mode": mode,
            "timeout_sec": int(eff_timeout),
            "init_script": init_script,
        }

        # Case 1: Stateful shared session (mode="shared") -> Sticky worker affinity
        if mode == "shared" and session_id and self.workers:
            # Deterministic hash to map session_id to a specific worker
            worker_idx = abs(hash(session_id)) % len(self.workers)
            worker = self.workers[worker_idx]
            res = worker.execute(payload, timeout_sec=eff_timeout)
            if worker.tasks_executed >= self.max_tasks:
                log.info(
                    "Recycling formula worker #%d after %d tasks to refresh memory",
                    worker.worker_id,
                    worker.tasks_executed,
                )
                worker.kill()
            if req_id is not None and isinstance(res, dict):
                res["id"] = req_id
            return res

        # Case 2: Stateless isolated execution (mode="isolated") -> Lease from idle queue
        try:
            worker = self.idle_queue.get(timeout=eff_timeout)
        except queue.Empty:
            return {
                "id": req_id,
                "status": "error",
                "code": "WORKER_POOL_BUSY",
                "error": "All formula workers are currently busy and request timed out waiting for worker lease.",
            }

        try:
            res = worker.execute(payload, timeout_sec=eff_timeout)
            if req_id is not None and isinstance(res, dict):
                res["id"] = req_id
            return res
        finally:
            if worker.tasks_executed >= self.max_tasks:
                log.info(
                    "Recycling formula worker #%d after %d tasks to refresh memory",
                    worker.worker_id,
                    worker.tasks_executed,
                )
                worker.kill()
            self.idle_queue.put(worker)

    def shutdown(self) -> None:
        """Terminate all worker processes."""
        with self._lock:
            if self._is_shutdown:
                return
            self._is_shutdown = True
            log.info("Shutting down FormulaProcessPool (%d workers)...", len(self.workers))
            for w in self.workers:
                w.kill()
            self.workers.clear()


# Global singleton per server process
_GLOBAL_FORMULA_POOL: FormulaProcessPool | None = None
_GLOBAL_FORMULA_POOL_LOCK = threading.Lock()


def get_formula_pool(settings: ComputeSettings | None = None) -> FormulaProcessPool:
    """Retrieve or initialize the global formula process pool."""
    global _GLOBAL_FORMULA_POOL
    with _GLOBAL_FORMULA_POOL_LOCK:
        if _GLOBAL_FORMULA_POOL is None:
            if settings is not None:
                # Use settings.max_threads or settings.workers
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
