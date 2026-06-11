# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Unit tests for plugin.writer.format helpers (no UNO)."""

import base64

from plugin.writer.format import strip_embedded_image_data, _apply_image_export_options


def test_strip_embedded_image_data_removes_base64_keeps_external_url():
    b64 = base64.b64encode(b"png-bytes").decode("ascii")
    html = (
        f'<p><img src="data:image/png;base64,{b64}" alt="chart"/>'
        f'<img src="image001.png" alt="linked"/></p>'
    )
    out = strip_embedded_image_data(html)
    assert "data:image" not in out
    assert b64 not in out
    assert 'src="image001.png"' in out
    assert 'alt="chart"' in out


def test_strip_embedded_image_data_css_background_url():
    b64 = base64.b64encode(b"x").decode("ascii")
    html = f'<p style="background-image: url(data:image/png;base64,{b64})">x</p>'
    out = strip_embedded_image_data(html)
    assert "data:image" not in out
    assert b64 not in out
    assert "background-image: url()" in out


def test_apply_image_export_options_skips_when_include_images_true():
    b64 = base64.b64encode(b"x").decode("ascii")
    html = f'<img src="data:image/png;base64,{b64}"/>'
    assert _apply_image_export_options(html, include_images=True) == html
