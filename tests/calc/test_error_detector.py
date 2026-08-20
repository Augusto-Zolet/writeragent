# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2024 John Balis
# Copyright (c) 2026 KeithCu (modifications and relicensing)
# Copyright (c) 2026 LibreCalc AI Assistant (Calc integration features, originally MIT)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.



def test_error_detector_data():
    from plugin.calc.error_detector import ERROR_TYPES, ERROR_PATTERNS
    assert 502 in ERROR_TYPES
    assert len(ERROR_PATTERNS) > 0
    for code, info in ERROR_TYPES.items():
        assert "name" in info
        assert "description" in info


def test_get_calc_error_name():
    from plugin.calc.error_detector import get_calc_error_name

    assert get_calc_error_name(501) == "Invalid character"
    assert get_calc_error_name(532) == "#DIV/0!"
    assert get_calc_error_name(9999) == "Unknown error (9999)"

