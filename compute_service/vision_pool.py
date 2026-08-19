# WriterAgent - Python Compute Service Vision Process Pool
# Copyright (c) 2026 KeithCu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Process pool supervisor for heavy, isolated OCR and Vision workloads.

Maintains a bounded pool of warm subprocesses. Fast spreadsheet calculations
in the compute service remain unblocked in their thread pool, while heavy
Docling / PaddleOCR tasks run safely in isolated worker processes.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from typing import Any

from compute_service.config import ComputeSettings

log = logging.getLogger("compute_service.vision")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKER_SCRIPT = os.path.join(_SCRIPT_DIR, "vision_worker.py")


class VisionProcessWorker:
    """Wrapper around one persistent vision worker subprocess."""

    def __init__(self, worker_id: int) -> None:
        self.worker_id = worker_id
        self.process: subprocess.Popen[str] | None = None
        self.lock = threading.Lock()
        self.tasks_executed = 0
        self._spawn()

    def _spawn(self) -> None:
        """Spawn the worker subprocess and wait for readiness handshake."""
        cmd = [sys.executable, _WORKER_SCRIPT]
        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            # Read ready line
            if self.process.stdout is not None:
                ready_line = self.process.stdout.readline()
                if ready_line:
                    try:
                        data = json.loads(ready_line.strip())
                        log.info(
                            "Vision worker #%d spawned (pid=%s, status=%s)",
                            self.worker_id,
                            data.get("pid", self.process.pid),
                            data.get("status"),
                        )
                    except Exception:
                        pass
            self.tasks_executed = 0
        except Exception as exc:
            log.error("Failed to spawn vision worker #%d: %s", self.worker_id, exc)
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
        with self.lock:
            if not self.is_alive():
                self._spawn()
                if not self.is_alive():
                    return {
                        "status": "error",
                        "code": "WORKER_SPAWN_FAILED",
                        "error": f"Vision worker #{self.worker_id} could not be started.",
                    }

            assert self.process is not None
            assert self.process.stdin is not None
            assert self.process.stdout is not None

            line_out = json.dumps(payload) + "\n"
            try:
                self.process.stdin.write(line_out)
                self.process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self.kill()
                return {
                    "status": "error",
                    "code": "WORKER_PIPE_BROKEN",
                    "error": f"Failed to send request to vision worker #{self.worker_id}: {exc}",
                }

            # Read response with timeout mechanism
            result_holder: list[dict[str, Any]] = []
            err_holder: list[str] = []

            def _reader() -> None:
                try:
                    if self.process is not None and self.process.stdout is not None:
                        resp_line = self.process.stdout.readline()
                        if resp_line:
                            result_holder.append(json.loads(resp_line.strip()))
                        else:
                            err_holder.append("EOF from worker process (process likely crashed or exited)")
                except Exception as e:
                    err_holder.append(str(e))

            reader_thread = threading.Thread(target=_reader, daemon=True)
            reader_thread.start()
            reader_thread.join(timeout=timeout_sec)

            if reader_thread.is_alive():
                # Timed out! Force-kill worker to prevent hanging and spawn replacement
                log.warning(
                    "Vision task timed out after %.1fs on worker #%d; terminating process pid=%s",
                    timeout_sec,
                    self.worker_id,
                    self.process.pid,
                )
                self.kill()
                return {
                    "status": "error",
                    "code": "VISION_TIMEOUT",
                    "error": f"Vision task exceeded execution timeout of {int(timeout_sec)}s.",
                }

            if err_holder:
                self.kill()
                return {
                    "status": "error",
                    "code": "WORKER_CRASHED",
                    "error": f"Vision worker error: {err_holder[0]}",
                }

            if not result_holder:
                self.kill()
                return {
                    "status": "error",
                    "code": "EMPTY_RESPONSE",
                    "error": "No response returned from vision worker.",
                }

            self.tasks_executed += 1
            return result_holder[0]


class VisionProcessPool:
    """Bounded pool of persistent worker subprocesses for Vision/OCR."""

    def __init__(
        self,
        num_workers: int = 1,
        default_timeout_sec: int = 60,
        max_tasks: int = 100,
    ) -> None:
        self.num_workers = max(0, num_workers)
        self.default_timeout_sec = default_timeout_sec
        self.max_tasks = max_tasks
        self.worker_queue: queue.Queue[VisionProcessWorker] = queue.Queue()
        self.workers: list[VisionProcessWorker] = []
        self._is_shutdown = False
        self._lock = threading.Lock()

        if self.num_workers > 0:
            for i in range(self.num_workers):
                w = VisionProcessWorker(i + 1)
                self.workers.append(w)
                self.worker_queue.put(w)

    def is_enabled(self) -> bool:
        return self.num_workers > 0 and not self._is_shutdown

    def execute(
        self,
        helper: str,
        image_b64: str | bytes | None = None,
        file_path: str | None = None,
        params: dict[str, Any] | None = None,
        timeout_sec: int | None = None,
        req_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a vision task on an available worker process."""
        if not self.is_enabled():
            return {
                "id": req_id,
                "status": "error",
                "code": "VISION_SERVICE_DISABLED",
                "error": "Vision / OCR service is not enabled on this instance (ocr_workers=0).",
            }

        eff_timeout = float(timeout_sec or self.default_timeout_sec)
        b64_val = None
        if image_b64 is not None:
            b64_val = image_b64 if isinstance(image_b64, str) else image_b64.decode("ascii", errors="ignore")

        payload = {
            "id": req_id,
            "helper": helper,
            "image_b64": b64_val,
            "file_path": file_path,
            "params": params or {},
        }

        try:
            # Lease a worker
            worker = self.worker_queue.get(timeout=eff_timeout)
        except queue.Empty:
            return {
                "id": req_id,
                "status": "error",
                "code": "VISION_POOL_BUSY",
                "error": "All vision workers are currently busy and request timed out waiting for worker lease.",
            }

        start_t = time.perf_counter()
        try:
            res = worker.execute(payload, timeout_sec=eff_timeout)
            if req_id is not None and isinstance(res, dict):
                res["id"] = req_id
            return res
        finally:
            # Check if worker should be recycled after max_tasks
            if worker.tasks_executed >= self.max_tasks:
                log.info(
                    "Recycling vision worker #%d after %d tasks to refresh memory",
                    worker.worker_id,
                    worker.tasks_executed,
                )
                worker.kill()
            self.worker_queue.put(worker)
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            log.info("Vision task %s completed in %.2fms", helper, duration_ms)

    def shutdown(self) -> None:
        """Terminate all worker processes."""
        with self._lock:
            if self._is_shutdown:
                return
            self._is_shutdown = True
            log.info("Shutting down VisionProcessPool (%d workers)...", len(self.workers))
            for w in self.workers:
                w.kill()
            self.workers.clear()


# Global singleton per server process
_GLOBAL_VISION_POOL: VisionProcessPool | None = None
_GLOBAL_VISION_POOL_LOCK = threading.Lock()


def get_vision_pool(settings: ComputeSettings | None = None) -> VisionProcessPool:
    """Retrieve or initialize the global vision process pool."""
    global _GLOBAL_VISION_POOL
    with _GLOBAL_VISION_POOL_LOCK:
        if _GLOBAL_VISION_POOL is None:
            if settings is not None:
                _GLOBAL_VISION_POOL = VisionProcessPool(
                    num_workers=settings.ocr_workers,
                    default_timeout_sec=settings.ocr_timeout_sec,
                    max_tasks=settings.ocr_max_tasks,
                )
            else:
                _GLOBAL_VISION_POOL = VisionProcessPool(num_workers=1)
        return _GLOBAL_VISION_POOL


def shutdown_vision_pool() -> None:
    """Shut down the global vision process pool."""
    global _GLOBAL_VISION_POOL
    with _GLOBAL_VISION_POOL_LOCK:
        if _GLOBAL_VISION_POOL is not None:
            _GLOBAL_VISION_POOL.shutdown()
            _GLOBAL_VISION_POOL = None
