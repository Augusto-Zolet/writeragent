from plugin.framework.errors import WorkerPoolError
from unittest.mock import MagicMock
import pytest
import time
import subprocess
import sys

from plugin.framework.worker_pool import run_in_background, AsyncProcess, start_stderr_drain
from plugin.framework.errors import ToolExecutionError

def test_run_in_background_success():
    result = []
    def success_func():
        result.append(True)
        return "done"

    t = run_in_background(success_func)
    t.join()
    assert result == [True]

def test_run_in_background_exception():
    error_called = []
    def error_func():
        raise ValueError("test error")

    def error_cb(err):
        error_called.append(err)

    t = run_in_background(error_func, error_callback=error_cb)
    t.join()

    assert len(error_called) == 1
    assert isinstance(error_called[0], WorkerPoolError)
    assert error_called[0].code == "WORKER_TASK_FAILED"
    assert "test error" in error_called[0].details["original_error"]
    assert error_called[0].details["error_type"] == "ValueError"

def test_run_in_background_exception_in_error_callback():
    error_called = []
    def error_func():
        raise RuntimeError("first error")

    def error_cb(err):
        error_called.append(err)
        raise RuntimeError("second error")

    # Should not crash the program
    t = run_in_background(error_func, error_callback=error_cb)
    t.join()
    assert len(error_called) == 1

def test_async_process_init():
    ap = AsyncProcess(["ls", "-l"], stdout_cb=lambda x: None)
    assert ap.args == ["ls", "-l"]
    assert ap._popen_kwargs["stdout"] == subprocess.PIPE
    assert ap._popen_kwargs["stderr"] == subprocess.PIPE
    assert ap._popen_kwargs["text"] is True
    assert ap._popen_kwargs["bufsize"] == 1
    assert ap.is_running is False

def test_async_process_start_success():
    stdout_lines = []
    stderr_lines = []
    exit_codes = []

    def on_stdout(line):
        stdout_lines.append(line)

    def on_stderr(line):
        stderr_lines.append(line)

    def on_exit(code):
        exit_codes.append(code)

    ap = AsyncProcess(
        [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"],
        stdout_cb=on_stdout,
        stderr_cb=on_stderr,
        on_exit_cb=on_exit
    )
    ap.start()
    assert ap.is_running is True

    ap._wait_thread.join(timeout=2)
    assert ap.is_running is False

    # Allow some time for stream reading threads to finish
    if ap._stdout_thread:
        ap._stdout_thread.join(timeout=1)
    if ap._stderr_thread:
        ap._stderr_thread.join(timeout=1)

    assert any("out" in line for line in stdout_lines)
    assert any("err" in line for line in stderr_lines)
    assert exit_codes == [0]

def test_async_process_start_drain_only():
    ap = AsyncProcess([sys.executable, "-c", "print('hello')"])
    ap.start()
    ap._wait_thread.join(timeout=2)
    assert ap.is_running is False


def test_stderr_drain_prevents_pipe_deadlock():
    """Child floods stderr before reading stdin; parent must not hang on the write/read."""
    script = (
        "import sys\n"
        "sys.stderr.write('x' * (128 * 1024))\n"
        "sys.stderr.flush()\n"
        "line = sys.stdin.buffer.readline()\n"
        "sys.stdout.buffer.write(b'ok:' + line)\n"
        "sys.stdout.buffer.flush()\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    # Keep a large diagnostic tail so we can prove the flood was drained (not dropped unread).
    drain = start_stderr_drain(proc.stderr, max_tail_chars=256 * 1024, name="test-stderr-flood")
    assert drain is not None
    assert proc.stdin is not None and proc.stdout is not None
    proc.stdin.write(b"hello\n")
    proc.stdin.flush()
    # Bounded wait: without a live drain this historically deadlocks on Linux pipes.
    deadline = time.time() + 10.0
    out = b""
    while time.time() < deadline and b"\n" not in out:
        chunk = proc.stdout.read(64)
        if not chunk:
            break
        out += chunk
    proc.wait(timeout=5)
    assert out.startswith(b"ok:hello")
    assert len(drain.text()) >= 128 * 1024

def test_async_process_start_error():
    ap = AsyncProcess(["/path/to/nonexistent/executable/xyz123"])
    with pytest.raises(ToolExecutionError) as exc:
        ap.start()
    assert "Failed to start process" in str(exc.value)

def test_async_process_wait_for_exit_callback_error():
    def on_exit_error(code):
        raise ValueError("exit callback error")

    ap = AsyncProcess([sys.executable, "-c", "pass"], on_exit_cb=on_exit_error)
    ap.start()
    ap._wait_thread.join(timeout=2)
    # The error should be caught and logged, not crash
    assert ap.is_running is False

def test_async_process_terminate():
    ap = AsyncProcess([sys.executable, "-c", "import time; time.sleep(10)"])
    ap.start()
    assert ap.is_running is True

    ap.terminate()
    ap._wait_thread.join(timeout=2)
    assert ap.is_running is False

def test_async_process_terminate_timeout():
    ap = AsyncProcess([sys.executable, "-c", "import time; time.sleep(10)"])
    ap.start()

    # Force a TimeoutExpired to hit the .kill() branch
    original_wait = ap.process.wait
    def mocked_wait(*args, **kwargs):
        if "timeout" in kwargs:
            raise subprocess.TimeoutExpired(ap.args, kwargs["timeout"])
        return original_wait(*args, **kwargs)

    ap.process.wait = mocked_wait

    ap.terminate(timeout=0.1)
    ap._wait_thread.join(timeout=2)
    assert ap.is_running is False

def test_async_process_read_stream_errors():
    ap = AsyncProcess(["ls"])

    # Test ValueError
    mock_stream = MagicMock()
    mock_stream.__iter__.side_effect = ValueError("I/O operation on closed file")

    ap._read_stream(mock_stream, lambda x: None)
    mock_stream.close.assert_called()

    # Test OSError
    mock_stream = MagicMock()
    mock_stream.__iter__.side_effect = OSError("read error")

    ap._read_stream(mock_stream, lambda x: None)
    mock_stream.close.assert_called()

    # Test stream close throwing OSError
    mock_stream = MagicMock()
    mock_stream.__iter__.return_value = ["line1"]
    mock_stream.close.side_effect = OSError("close error")

    ap._read_stream(mock_stream, lambda x: None)
    mock_stream.close.assert_called()

def test_async_process_drain_stream_errors():
    ap = AsyncProcess(["ls"])

    # Test OSError in loop
    mock_stream = MagicMock()
    mock_stream.__iter__.side_effect = OSError("drain error")

    ap._drain_stream(mock_stream)
    mock_stream.close.assert_called()

    # Test stream close throwing OSError
    mock_stream = MagicMock()
    mock_stream.__iter__.return_value = ["line1"]
    mock_stream.close.side_effect = OSError("close error")

    ap._drain_stream(mock_stream)
    mock_stream.close.assert_called()

def test_async_process_terminate_not_running():
    ap = AsyncProcess([sys.executable, "-c", "pass"])
    # Not started, terminate should return silently
    ap.terminate()

    # Started but already exited
    ap.start()
    ap._wait_thread.join(timeout=2)
    ap.terminate()


class TestWorkerPoolErrorHandling():

    def test_run_in_background_success(self):

        def mock_task(x, y):
            return (x + y)
        thread = run_in_background(mock_task, 2, 3)
        thread.join()
        assert (not thread.is_alive())

    def test_run_in_background_failure(self):
        error_cb = MagicMock()

        def mock_task():
            raise ValueError('Test error')
        thread = run_in_background(mock_task, error_callback=error_cb)
        thread.join()
        assert (error_cb.call_count == 1)
        wrapped_error = error_cb.call_args[0][0]
        assert isinstance(wrapped_error, WorkerPoolError)
        assert ("Task 'mock_task' failed" in wrapped_error.message)
        assert (wrapped_error.code == 'WORKER_TASK_FAILED')
        assert (wrapped_error.details['error_type'] == 'ValueError')


class TestReadStreamStripsNewlines:
    """Regression test for Bug 1: rstrip("\\n\\r") used literal chars, not newlines."""

    def _make_stream(self, lines):
        """Return a closeable text stream that yields the given strings."""
        import io
        return io.StringIO("".join(lines))

    def test_strips_lf(self):
        # Lines from a subprocess on Unix end with \n; the callback must not see it.
        ap = AsyncProcess(["dummy"])
        received = []
        stream = self._make_stream(["hello\n", "world\n"])
        ap._read_stream(stream, received.append)
        assert received == ["hello", "world"], (
            f"Expected no trailing newlines but got: {received!r}"
        )

    def test_strips_crlf(self):
        # Lines from a subprocess on Windows (or text=True on Windows) end with \r\n.
        ap = AsyncProcess(["dummy"])
        received = []
        stream = self._make_stream(["hello\r\n", "world\r\n"])
        ap._read_stream(stream, received.append)
        assert received == ["hello", "world"], (
            f"Expected no trailing CRLF but got: {received!r}"
        )

    def test_empty_line_not_dropped(self):
        # An empty line (just "\n") should yield an empty string, not be skipped.
        ap = AsyncProcess(["dummy"])
        received = []
        stream = self._make_stream(["\n"])
        ap._read_stream(stream, received.append)
        assert received == [""], f"Expected [\"\"] but got: {received!r}"

