# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Centralized management for background worker threads and external subprocesses.

Background threads created here are tagged (via thread_guard) so that the
UNO main-thread runtime guard (Layer A) can name the offending task on violation.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import traceback
import uuid
from collections import deque
from typing import Optional, Callable, Any, IO

from plugin.framework.errors import WorkerPoolError

log = logging.getLogger("writeragent.framework.worker_pool")

_DEFAULT_STDERR_TAIL_CHARS = 8192

# Thread-safety guard (Layer A): tag threads born here so assert_main_thread
# can name the offending background task in diagnostics.
from plugin.framework import thread_guard


def run_in_background(func, *args, name=None, error_callback=None, daemon=True, **kwargs):
    """
    Spawns a background thread to execute a function, catching any exceptions
    and wrapping them in WorkerPoolError for consistent error handling and task isolation.

    :param func: The callable to execute.
    :param args: Positional arguments for func.
    :param name: Optional thread name.
    :param error_callback: Optional callable(Exception) to run if func raises.
    :param daemon: Whether the thread should be a daemon (default True).
    :param kwargs: Keyword arguments for func.
    :return: The spawned threading.Thread instance.
    """

    def _worker():
        task_id = str(uuid.uuid4())
        task_name = name or getattr(func, "__name__", "anon")
        log.debug(f"Starting task {task_id}: {task_name}")

        # Tag this background thread for the UNO thread-safety guard (Layer A).
        # This lets violations report the specific worker (e.g. "run_search") instead of a generic thread name.
        thread_guard.set_background_task(task_name)

        try:
            result = func(*args, **kwargs)
            log.debug(f"Task {task_id} completed successfully")
            return result
        except Exception as e:
            error_id = str(uuid.uuid4())
            log.error(f"Task {task_id} failed: {str(e)}\n{traceback.format_exc()}", extra={"task_id": task_id, "task_name": task_name, "error_id": error_id, "error_type": type(e).__name__})

            wrapped_error = WorkerPoolError(f"Task '{task_name}' failed", code="WORKER_TASK_FAILED", details={"task_id": task_id, "task_name": task_name, "error_id": error_id, "original_error": str(e), "error_type": type(e).__name__})

            if error_callback:
                try:
                    error_callback(wrapped_error)
                except Exception as ec:
                    log.error("Error in error_callback for '%s': %s", task_name, ec)

    thread_name = name or f"worker-{getattr(func, '__name__', 'anon')}"
    t = threading.Thread(target=_worker, name=thread_name, daemon=daemon)
    t.start()
    return t


def get_subprocess_creationflags() -> dict[str, Any]:
    """Return popen/run kwargs to hide command prompt windows on Windows."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


class StderrTail:
    """Bounded stderr text captured by a continuous drain thread.

    Prevents the classic OS pipe deadlock: child fills stderr while parent
    blocks on stdin/stdout. Keeps a diagnostic tail for crash messages.
    """

    __slots__ = ("_lock", "_chunks", "_chars", "_max_chars", "_thread")

    def __init__(self, max_chars: int = _DEFAULT_STDERR_TAIL_CHARS) -> None:
        self._lock = threading.Lock()
        self._chunks: deque[str] = deque()
        self._chars = 0
        self._max_chars = max(256, max_chars)
        self._thread: threading.Thread | None = None

    def _append(self, text: str) -> None:
        if not text:
            return
        with self._lock:
            self._chunks.append(text)
            self._chars += len(text)
            while self._chunks and self._chars > self._max_chars:
                dropped = self._chunks.popleft()
                self._chars -= len(dropped)

    def text(self) -> str:
        with self._lock:
            return "".join(self._chunks)

    def attach_thread(self, thread: threading.Thread) -> None:
        self._thread = thread


def start_stderr_drain(
    stream: IO[Any] | None,
    *,
    max_tail_chars: int = _DEFAULT_STDERR_TAIL_CHARS,
    name: str = "stderr-drain",
) -> StderrTail | None:
    """Continuously drain a child stderr pipe into a bounded :class:`StderrTail`.

    Call this immediately after ``Popen(..., stderr=PIPE)`` for long-lived workers.
    Returns None when *stream* is None (e.g. stderr redirected to DEVNULL).
    """
    if stream is None:
        return None
    tail = StderrTail(max_chars=max_tail_chars)

    def _loop() -> None:
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    break
                if isinstance(chunk, bytes):
                    text = chunk.decode("utf-8", errors="replace")
                else:
                    text = chunk
                tail._append(text)
        except Exception:
            log.debug("%s failed", name, exc_info=True)
        finally:
            try:
                stream.close()
            except Exception:
                pass

    thread = run_in_background(_loop, name=name)
    tail.attach_thread(thread)
    return tail


class AsyncProcess:
    """
    Manages a subprocess.Popen instance, asynchronously reading its stdout/stderr
    streams and providing a callback mechanism for output and exit.
    """

    def __init__(self, args, stdout_cb: Optional[Callable[[str], None]] = None, stderr_cb: Optional[Callable[[str], None]] = None, on_exit_cb: Optional[Callable[[int], None]] = None, **popen_kwargs):
        self.args = args
        self.stdout_cb = stdout_cb
        self.stderr_cb = stderr_cb
        self.on_exit_cb = on_exit_cb
        self.process: Optional[subprocess.Popen] = None

        self._popen_kwargs = popen_kwargs
        if sys.platform == "win32":
            self._popen_kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        self._popen_kwargs.setdefault("stdout", subprocess.PIPE)
        self._popen_kwargs.setdefault("stderr", subprocess.PIPE)
        self._popen_kwargs.setdefault("text", True)
        self._popen_kwargs.setdefault("bufsize", 1)  # Line buffered

        self._stdout_thread = None
        self._stderr_thread = None
        self._wait_thread = None

    @property
    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def start(self):
        """Starts the process and its monitoring threads."""
        try:
            self.process = subprocess.Popen(self.args, **self._popen_kwargs)
        except Exception as e:
            log.error("Failed to start process: %s", self.args)
            from plugin.framework.errors import ToolExecutionError

            raise ToolExecutionError(f"Failed to start process: {self.args}", details={"error": str(e)}) from e

        if self.process.stdout and self.stdout_cb:
            self._stdout_thread = run_in_background(self._read_stream, self.process.stdout, self.stdout_cb, name=f"asyncproc-out-{self.process.pid}")
        elif self.process.stdout:
            # Drain it silently to avoid deadlocks
            run_in_background(self._drain_stream, self.process.stdout, name=f"asyncproc-outdrain-{self.process.pid}")

        if self.process.stderr and self.stderr_cb:
            self._stderr_thread = run_in_background(self._read_stream, self.process.stderr, self.stderr_cb, name=f"asyncproc-err-{self.process.pid}")
        elif self.process.stderr:
            run_in_background(self._drain_stream, self.process.stderr, name=f"asyncproc-errdrain-{self.process.pid}")

        self._wait_thread = run_in_background(self._wait_for_exit, name=f"asyncproc-wait-{self.process.pid}")

    def _read_stream(self, stream, callback):
        try:
            for line in stream:
                if line is not None:
                    callback(line.rstrip("\\n\\r"))
        except ValueError:
            pass  # ValueError: I/O operation on closed file
        except OSError as e:
            log.debug("AsyncProcess stream read error: %s", e)
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def _drain_stream(self, stream):
        try:
            for _ in stream:
                pass
        except OSError:
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def _wait_for_exit(self):
        if self.process is None:
            return
        rc = self.process.wait()
        log.debug("Process %s exited with rc=%s", self.args[0] if getattr(self.args, "__len__", lambda: 0)() > 0 else self.args, rc)
        if self.on_exit_cb:
            try:
                self.on_exit_cb(rc)
            except Exception as e:
                log.error("Error in on_exit_cb for process: %s", e)

    def terminate(self, timeout=5.0):
        """Standard graceful termination -> SIGKILL."""
        if not self.process:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
