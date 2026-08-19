# WriterAgent - Python Compute Service Formula Pool tests
# Copyright (c) 2026 KeithCu
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

from compute_service.config import ComputeSettings
from compute_service.formula_pool import (
    FormulaProcessPool,
    shutdown_formula_pool,
)
from compute_service.server import WSGIDualStackServer, create_wsgi_app


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def cleanup_formula_pool():
    yield
    shutdown_formula_pool()


class TestFormulaPoolSupervisor:
    def test_pool_lifecycle(self) -> None:
        pool = FormulaProcessPool(num_workers=2, default_timeout_sec=15)
        try:
            assert pool.is_enabled()
            assert len(pool.workers) == 2
            res = pool.execute(code="result = 10 + 20", req_id="f-1")
            assert res.get("id") == "f-1"
            assert res.get("status") == "ok"
            assert res.get("result") == 30
        finally:
            pool.shutdown()
            assert not pool.is_enabled()

    def test_sticky_session_affinity(self) -> None:
        pool = FormulaProcessPool(num_workers=4, default_timeout_sec=15)
        try:
            session_id = "test-workbook-session-42"
            # First cell execution: set a variable
            res1 = pool.execute(
                code="x = 100\nresult = x",
                session_id=session_id,
                mode="shared",
                req_id="c-1",
            )
            assert res1.get("status") == "ok"
            assert res1.get("result") == 100

            # Second cell execution: read and increment variable in same session
            res2 = pool.execute(
                code="x += 50\nresult = x",
                session_id=session_id,
                mode="shared",
                req_id="c-2",
            )
            assert res2.get("status") == "ok"
            assert res2.get("result") == 150
        finally:
            pool.shutdown()

    def test_worker_crash_recovery(self) -> None:
        pool = FormulaProcessPool(num_workers=1, default_timeout_sec=10)
        try:
            worker = pool.workers[0]
            # Kill worker externally
            worker.kill()
            assert not worker.is_alive()

            # Next request should automatically spawn a fresh worker and succeed
            res = pool.execute(code="result = 'recovered'", req_id="f-rec")
            assert res.get("status") == "ok"
            assert res.get("result") == "recovered"
            assert worker.is_alive()
        finally:
            pool.shutdown()

    def test_stderr_flood_does_not_deadlock(self, tmp_path) -> None:
        """Child OS-stderr flood must not deadlock the parent pickle reader."""
        from compute_service.worker_base import BaseProcessWorker

        script = tmp_path / "flood_worker.py"
        script.write_text(
            "\n".join(
                [
                    "import os, sys",
                    f"sys.path.insert(0, {os.path.abspath('.')!r})",
                    "from compute_service.worker_base import run_worker_stdio_loop",
                    "def handle(req):",
                    "    sys.stderr.write('x' * 200000)",
                    "    sys.stderr.flush()",
                    "    return {'status': 'ok', 'result': 1}",
                    "if __name__ == '__main__':",
                    "    raise SystemExit(run_worker_stdio_loop(handle))",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        worker = BaseProcessWorker(1, str(script), worker_name="Flood worker")
        try:
            res = worker.execute({"ping": True}, timeout_sec=10)
            assert res.get("status") == "ok"
            assert res.get("result") == 1
        finally:
            worker.kill()

    def test_shared_and_isolated_exclusive_occupancy(self) -> None:
        pool = FormulaProcessPool(num_workers=1, default_timeout_sec=15)
        try:
            sid = "occupancy-session"
            first = pool.execute(
                code="x = 5\nresult = x",
                session_id=sid,
                mode="shared",
                req_id="occ-1",
            )
            assert first.get("status") == "ok"

            isolated_holder: list[dict] = []

            def _isolated() -> None:
                isolated_holder.append(
                    pool.execute(
                        code="import time\ntime.sleep(0.2)\nresult = 99",
                        mode="isolated",
                        timeout_sec=10,
                        req_id="occ-iso",
                    )
                )

            thread = threading.Thread(target=_isolated)
            thread.start()
            time.sleep(0.05)
            shared = pool.execute(
                code="result = x",
                session_id=sid,
                mode="shared",
                timeout_sec=10,
                req_id="occ-2",
            )
            thread.join(timeout=10)
            assert isolated_holder and isolated_holder[0].get("status") == "ok"
            assert isolated_holder[0].get("result") == 99
            assert shared.get("status") == "ok"
            assert shared.get("result") == 5
        finally:
            pool.shutdown()

    def test_timeout_watchdog_kill(self) -> None:
        pool = FormulaProcessPool(num_workers=1, default_timeout_sec=1)
        try:
            # Code that takes longer than 1s timeout
            res = pool.execute(
                code="import time\ntime.sleep(5)\nresult = 'done'",
                timeout_sec=1,
                req_id="f-timeout",
            )
            assert res.get("status") == "error"
            # Code is either EXECUTION_TIMEOUT from pool or timeout from sandbox
            assert "timeout" in str(res.get("error", "")).lower() or "timeout" in str(res.get("code", "")).lower()
        finally:
            pool.shutdown()


class TestFormulaHttpEndpoint:
    @pytest.fixture
    def formula_server(self):
        port = get_free_port()
        settings = ComputeSettings(
            host="127.0.0.1",
            port=port,
            api_key="formula-secret",
            max_threads=2,
        )
        app = create_wsgi_app(settings)
        server = WSGIDualStackServer("127.0.0.1", port, max_threads=2)
        server.set_app(app)

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.15)
        yield f"http://127.0.0.1:{port}"
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    def _post(self, url: str, payload: dict, headers: dict | None = None) -> tuple[int, dict]:
        req_headers = {"Content-Type": "application/json"}
        if headers:
            req_headers.update(headers)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{url}/v1/execute", data=data, headers=req_headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return resp.status, body
        except urllib.error.HTTPError as e:
            body = json.loads(e.read().decode("utf-8"))
            return e.code, body

    def test_execute_success(self, formula_server: str) -> None:
        status, body = self._post(
            formula_server,
            {"id": "req-1", "code": "result = 7 * 8"},
            headers={"Authorization": "Bearer formula-secret"},
        )
        assert status == 200
        assert body.get("id") == "req-1"
        assert body.get("status") == "ok"
        assert body.get("result") == 56

    def test_execute_shared_session(self, formula_server: str) -> None:
        session_id = "session-http-123"
        status1, body1 = self._post(
            formula_server,
            {"id": "req-s1", "code": "val = 42\nresult = val", "session_id": session_id, "mode": "shared"},
            headers={"Authorization": "Bearer formula-secret"},
        )
        assert status1 == 200
        assert body1.get("result") == 42

        status2, body2 = self._post(
            formula_server,
            {"id": "req-s2", "code": "val += 8\nresult = val", "session_id": session_id, "mode": "shared"},
            headers={"Authorization": "Bearer formula-secret"},
        )
        assert status2 == 200
        assert body2.get("result") == 50
