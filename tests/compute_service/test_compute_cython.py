# WriterAgent - Python Compute Service Cython Startup Test
# Copyright (c) 2026 KeithCu
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import patch

from compute_service.config import ComputeSettings
from compute_service.server import run_server
from plugin.scripting.payload_codec import get_cython_status_info


def test_compute_service_cython_status_logged(capsys) -> None:
    """Verify that compute service logs Cython status on startup."""
    from plugin.scripting.payload_codec import load_cython_accelerator

    load_cython_accelerator()
    is_active, source_loc, expected_line = get_cython_status_info()

    settings = ComputeSettings(
        host="127.0.0.1",
        port=8000,
        threads=1,
        workers=1,
        ocr_workers=0,
        log_level="INFO",
    )

    with (
        patch("compute_service.server.WSGIDualStackServer") as mock_server_cls,
        patch("compute_service.formula_pool.get_formula_pool"),
        patch("compute_service.server.check_dependencies"),
    ):
        mock_server = mock_server_cls.return_value
        mock_server.serve_forever.side_effect = KeyboardInterrupt

        try:
            run_server(settings)
        except KeyboardInterrupt:
            pass

        captured = capsys.readouterr()
        assert expected_line in captured.err
