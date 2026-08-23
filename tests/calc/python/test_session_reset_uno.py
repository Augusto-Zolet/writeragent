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
    from plugin.scripting.document_scripts import set_calc_init_script

    try:
        set_config("scripting.python_session_mode", "shared")

        # Pass doc into PythonFunction to verify explicit doc forwarding
        func = PythonFunction(ctx, doc=doc)

        sid = sm.workbook_session_id(ctx, doc=doc)
        assert sid is not None
        assert sid.startswith("calc:")

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

        # Attach an init script with custom helper function (C2.2.3)
        set_calc_init_script(doc, "def double(x):\n    return x * 2\n")
        res_init1 = func.py("result = double(3)")
        assert res_init1 == 6.0

        # 3. Reset Python Session (suppress UI modal msgbox)
        with patch.object(sm, "_msgbox", lambda *args, **kwargs: None):
            sm.reset_workbook_python_session(ctx, doc=doc)

        # 4. C2.2.1: Verify shared variable x was dropped
        res3 = func.py("x")
        assert "not defined" in str(res3) or "Error:" in str(res3)

        # 5. C2.2.2: Verify leftover result was cleared
        res_r3 = func.py("result")
        assert res_r3 != 20.0 or "not defined" in str(res_r3) or "Error:" in str(res_r3)

        # 6. C2.2.3: Verify init helper function double(x) is re-applied and functional after Reset
        res_init2 = func.py("result = double(4)")
        assert res_init2 == 8.0
    finally:
        set_config("scripting.python_session_mode", "isolated")
