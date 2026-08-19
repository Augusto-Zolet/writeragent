# WriterAgent - Python Compute Service Base Worker & Pool Infrastructure
# Copyright (c) 2026 KeithCu
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Shared subprocess worker loop, worker process wrapper, and process pool supervisor.

Provides:
- High-speed length-prefixed Pickle 5 binary framing over stdio pipes
- Zero-overhead POSIX select.select polling (with Windows thread fallback)
- Hard SIGKILL watchdog timers on hangs/timeouts
- Automatic crash recovery and worker recycling after max_tasks
"""

from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from plugin.scripting.ipc import read_pickle_frame, write_pickle_frame

log = logging.getLogger("compute_service.worker")


def run_worker_stdio_loop(handler: Callable[[dict[str, Any]], dict[str, Any]]) -> int:
    """Standard binary Pickle 5 stdio worker loop for child subprocesses."""
    stdin_bin = sys.stdin.buffer
    stdout_bin = sys.stdout.buffer

    # Signal readiness to supervisor
    write_pickle_frame(stdout_bin, {"status": "ready", "pid": os.getpid()})

    while True:
        try:
            req = read_pickle_frame(stdin_bin)
            if req is None:
                break
            if not isinstance(req, dict):
                res = {"status": "error", "error": "Request must be a dict"}
            else:
                res = handler(req)
        except Exception as exc:
            res = {"status": "error", "error": f"Invalid IPC frame or unhandled error: {exc}"}

        try:
            write_pickle_frame(stdout_bin, res)
        except Exception:
            break

    return 0


class BaseProcessWorker:
    """Wrapper around one persistent child subprocess communicating via Pickle 5 frames."""

    def __init__(self, worker_id: int, script_path: str, worker_name: str = "Worker") -> None:
        self.worker_id = worker_id
        self.script_path = script_path
        self.worker_name = worker_name
        self.process: subprocess.Popen[bytes] | None = None
        self.lock = threading.Lock()
        self.tasks_executed = 0
        self._spawn()

    def _spawn(self) -> None:
        """Spawn worker subprocess and await readiness handshake."""
        cmd = [sys.executable, self.script_path]
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
                        "%s #%d spawned (pid=%s, status=%s)",
                        self.worker_name,
                        self.worker_id,
                        ready_data.get("pid", self.process.pid),
                        ready_data.get("status"),
                    )
            self.tasks_executed = 0
        except Exception as exc:
            log.error("Failed to spawn %s #%d: %s", self.worker_name, self.worker_id, exc)
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
        """Send request to worker process and await response with timeout."""
        with self.lock:
            if not self.is_alive():
                self._spawn()
                if not self.is_alive():
                    return {
                        "status": "error",
                        "code": "WORKER_SPAWN_FAILED",
                        "error": f"{self.worker_name} #{self.worker_id} could not be started.",
                    }

            assert self.process is not None
            assert self.process.stdin is not None
            assert self.process.stdout is not None

            try:
                write_pickle_frame(self.process.stdin, payload)
            except (BrokenPipeError, OSError) as exc:
                self.kill()
                return {
                    "status": "error",
                    "code": "WORKER_PIPE_BROKEN",
                    "error": f"Failed to send request to {self.worker_name} #{self.worker_id}: {exc}",
                }

            # Fast POSIX path using select.select
            if sys.platform != "win32":
                import select

                ready, _, _ = select.select([self.process.stdout], [], [], timeout_sec)
                if not ready:
                    log.warning(
                        "%s execution timed out after %.1fs on worker #%d; terminating pid=%s",
                        self.worker_name,
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
                        "error": f"{self.worker_name} error: {exc}",
                        "message": f"{self.worker_name} error: {exc}",
                    }
                if resp is None or not isinstance(resp, dict):
                    self.kill()
                    return {
                        "status": "error",
                        "code": "EMPTY_RESPONSE",
                        "error": f"No response returned from {self.worker_name}.",
                    }
                self.tasks_executed += 1
                return resp

            # Windows reader thread fallback
            result_holder: list[dict[str, Any]] = []
            err_holder: list[str] = []

            def _reader() -> None:
                try:
                    if self.process is not None and self.process.stdout is not None:
                        resp = read_pickle_frame(self.process.stdout)
                        if resp is not None and isinstance(resp, dict):
                            result_holder.append(resp)
                        else:
                            err_holder.append(f"EOF from {self.worker_name} (crashed or terminated)")
                except Exception as e:
                    err_holder.append(str(e))

            reader_thread = threading.Thread(target=_reader, daemon=True)
            reader_thread.start()
            reader_thread.join(timeout=timeout_sec)

            if reader_thread.is_alive():
                log.warning(
                    "%s execution timed out after %.1fs on worker #%d; terminating pid=%s",
                    self.worker_name,
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
                    "error": f"{self.worker_name} error: {err_holder[0]}",
                    "message": f"{self.worker_name} error: {err_holder[0]}",
                }

            if not result_holder:
                self.kill()
                return {
                    "status": "error",
                    "code": "EMPTY_RESPONSE",
                    "error": f"No response returned from {self.worker_name}.",
                }

            self.tasks_executed += 1
            return result_holder[0]


class BaseProcessPool:
    """Base supervisor for a bounded pool of child worker subprocesses."""

    def __init__(
        self,
        script_path: str,
        num_workers: int = 1,
        default_timeout_sec: int = 30,
        max_tasks: int = 500,
        worker_name: str = "Worker",
    ) -> None:
        self.script_path = script_path
        self.num_workers = max(0, num_workers)
        self.default_timeout_sec = default_timeout_sec
        self.max_tasks = max_tasks
        self.worker_name = worker_name
        self.idle_queue: queue.Queue[BaseProcessWorker] = queue.Queue()
        self.workers: list[BaseProcessWorker] = []
        self._is_shutdown = False
        self._lock = threading.Lock()

        if self.num_workers > 0:
            for i in range(self.num_workers):
                w = BaseProcessWorker(i + 1, script_path=script_path, worker_name=worker_name)
                self.workers.append(w)
                self.idle_queue.put(w)

    def is_enabled(self) -> bool:
        return self.num_workers > 0 and not self._is_shutdown

    def lease_worker(self, timeout_sec: float) -> BaseProcessWorker | None:
        """Acquire an available idle worker or None on timeout."""
        try:
            return self.idle_queue.get(timeout=timeout_sec)
        except queue.Empty:
            return None

    def release_worker(self, worker: BaseProcessWorker) -> None:
        """Return worker to idle queue, recycling if max_tasks reached."""
        if worker.tasks_executed >= self.max_tasks:
            log.info(
                "Recycling %s #%d after %d tasks to refresh memory",
                self.worker_name,
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
            log.info("Shutting down %s pool (%d workers)...", self.worker_name, len(self.workers))
            for w in self.workers:
                w.kill()
            self.workers.clear()
