# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native UNO test for Calc =PY() data-arg DAG chaining (Issue #412 / Packet C2.4)."""

from __future__ import annotations

from plugin.testing_runner import native_test
from plugin.tests.testing_utils import with_native_doc


@native_test
@with_native_doc("calc")
def test_py_data_arg_dag_chain_uno(ctx, doc):
    from plugin.calc.python.addin import PythonFunction
    from plugin.scripting.venv_worker import PythonWorkerManager

    # Ensure worker subprocess is fresh with current code
    PythonWorkerManager.shutdown_all()

    # 1. Direct PythonFunction add-in calls with single-cell values & tuples
    func = PythonFunction(ctx)

    res_a1 = func.py("result = 2")
    assert res_a1 == 2.0

    res_b1 = func.py("result = data + 3", ((res_a1,),))
    assert res_b1 == 5.0

    res_c1 = func.py("result = data * 4", ((res_b1,),))
    assert res_c1 == 20.0

    # Fan-out direct calls
    res_fan_b = func.py("result = data", ((res_a1,),))
    res_fan_c = func.py("result = data", ((res_a1,),))
    assert res_fan_b == 2.0
    assert res_fan_c == 2.0

    # 2. Live Calc Sheet DAG: C2.4.1 (Chain of three) & C2.4.3 (Fan-out)
    sheet = doc.getSheets().getByIndex(0)

    # C2.4.1: A1 -> B1 -> C1
    sheet.getCellByPosition(0, 0).setFormula('=PY("result = 2")')
    sheet.getCellByPosition(1, 0).setFormula('=PY("result = data + 3"; A1)')
    sheet.getCellByPosition(2, 0).setFormula('=PY("result = data * 4"; B1)')

    # C2.4.3: D1 producer; E1 and F1 fan-out consumers
    sheet.getCellByPosition(3, 0).setFormula('=PY("result = 10")')
    sheet.getCellByPosition(4, 0).setFormula('=PY("result = data"; D1)')
    sheet.getCellByPosition(5, 0).setFormula('=PY("result = data"; D1)')

    # Recalculate
    doc.calculateAll()

    # Verify C2.4.1 values: A1=2, B1=5, C1=20
    assert sheet.getCellByPosition(0, 0).getValue() == 2.0
    assert sheet.getCellByPosition(1, 0).getValue() == 5.0
    assert sheet.getCellByPosition(2, 0).getValue() == 20.0

    # Verify C2.4.3 fan-out values: D1=10, E1=10, F1=10 (no MATRIX_SCALAR_SESSIONS collision)
    assert sheet.getCellByPosition(3, 0).getValue() == 10.0
    assert sheet.getCellByPosition(4, 0).getValue() == 10.0
    assert sheet.getCellByPosition(5, 0).getValue() == 10.0

    # 3. Hard recalc consistency (C2.6.3)
    doc.calculateAll()
    assert sheet.getCellByPosition(2, 0).getValue() == 20.0
    assert sheet.getCellByPosition(4, 0).getValue() == 10.0
    assert sheet.getCellByPosition(5, 0).getValue() == 10.0

    # 4. Issue #413: Boolean return
    res_bool_true = func.py("result = True")
    assert res_bool_true == 1.0
    assert isinstance(res_bool_true, float)

    res_bool_false = func.py("result = False")
    assert res_bool_false == 0.0
    assert isinstance(res_bool_false, float)

    # Chained boolean logic in Python add-in
    res_bool_chain = func.py("result = 'YES' if data else 'NO'", ((res_bool_true,),))
    assert res_bool_chain == "YES"

    res_bool_chain_false = func.py("result = 'YES' if data else 'NO'", ((res_bool_false,),))
    assert res_bool_chain_false == "NO"








