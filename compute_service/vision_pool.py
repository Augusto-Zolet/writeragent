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

import logging
import os
import threading
import time
from typing import Any

from compute_service.config import ComputeSettings
from compute_service.worker_base import BaseProcessPool

log = logging.getLogger("compute_service.vision")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_WORKER_SCRIPT = os.path.join(_SCRIPT_DIR, "vision_worker.py")


class VisionProcessPool(BaseProcessPool):
    """Bounded pool of persistent worker subprocesses for Vision/OCR."""

    def __init__(
        self,
        num_workers: int = 1,
        default_timeout_sec: int = 60,
        max_tasks: int = 100,
        idle_worker_ttl_sec: float | None = 3600.0,
    ) -> None:
        super().__init__(
            script_path=_WORKER_SCRIPT,
            num_workers=num_workers,
            default_timeout_sec=default_timeout_sec,
            max_tasks=max_tasks,
            worker_name="Vision worker",
            idle_worker_ttl_sec=idle_worker_ttl_sec,
        )

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
        image_bytes = None
        if image_b64 is not None:
            if isinstance(image_b64, (bytes, bytearray)):
                image_bytes = bytes(image_b64)
            elif isinstance(image_b64, str):
                import base64

                try:
                    image_bytes = base64.b64decode(image_b64)
                except Exception:
                    b64_val = image_b64

        payload = {
            "id": req_id,
            "helper": helper,
            "image_bytes": image_bytes,
            "image_b64": b64_val,
            "file_path": file_path,
            "params": params or {},
        }

        deadline = time.monotonic() + eff_timeout
        worker = self.lease_any(timeout_sec=max(0.01, deadline - time.monotonic()))
        if worker is None:
            return {
                "id": req_id,
                "status": "error",
                "code": "VISION_POOL_BUSY",
                "error": "All vision workers are currently busy and request timed out waiting for worker lease.",
            }

        try:
            res = worker.execute(payload, timeout_sec=max(0.01, deadline - time.monotonic()))
            if req_id is not None and isinstance(res, dict):
                res["id"] = req_id
            return res
        finally:
            self.release_worker(worker)


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
                    idle_worker_ttl_sec=settings.idle_worker_ttl_sec,
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
