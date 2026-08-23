# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native UNO test for Calc shared-kernel session reset (Issue #411 / Packet C2.2)."""

from __future__ import annotations

from unittest.mock import patch

from plugin.testing_runner import native_test
from plugin.tests.testing_utils import with_native_doc


@native_test
@with_native_doc("calc")
def test_shared_kernel_reset_session_uno(ctx, doc):
    from plugin.calc.python.addin import PythonFunction
    from plugin.framework.config import set_config
    import plugin.scripting.session_manager as sm

    set_config("scripting.python_session_mode", "shared")

    func = PythonFunction(ctx)

    # 1. C2.2.1: Shared names persist prior to reset
    res1 = func.py("x = 42")
    assert res1 == 42.0
    res2 = func.py("x")
    assert res2 == 42.0

    # 2. C2.2.2: Leftover result persists prior to reset
    res_r1 = func.py("result = 20")
    assert res_r1 == 20.0
    res_r2 = func.py("result")
    assert res_r2 == 20.0

    # 3. Reset Python Session (suppress UI modal msgbox)
    with patch.object(sm, "_msgbox", lambda *args, **kwargs: None):
        sm.reset_workbook_python_session(ctx)

    # 4. Verify shared variable x was dropped
    res3 = func.py("x")
    assert "not defined" in str(res3) or "Error:" in str(res3)

    # 5. Verify leftover result was cleared
    res_r3 = func.py("result")
    assert res_r3 != 20.0 or "not defined" in str(res_r3) or "Error:" in str(res_r3)
