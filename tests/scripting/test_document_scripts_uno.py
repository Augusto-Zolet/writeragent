# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""UNO tests for document-attached Run Python Script persistence."""

from __future__ import annotations

import os
import tempfile

import uno

from plugin.scripting.document_scripts import (
    DOCUMENT_SCRIPTS_UDPROP,
    attach_document_script,
    get_document_scripts,
)
from plugin.testing_runner import native_test, setup, teardown
from plugin.tests.testing_utils import TestingFactory

_test_ctx = None
_temp_dir = None
_saved_path = None


def _hidden_prop():
    return uno.createUnoStruct("com.sun.star.beans.PropertyValue", Name="Hidden", Value=True)


@setup
def setup_document_scripts_uno(ctx):
    global _test_ctx, _temp_dir, _saved_path
    _test_ctx = ctx
    _temp_dir = tempfile.mkdtemp(prefix="wa_doc_scripts_")


@teardown
def teardown_document_scripts_uno(ctx):
    global _test_ctx, _temp_dir, _saved_path
    _test_ctx = None
    if _temp_dir and os.path.isdir(_temp_dir):
        for name in os.listdir(_temp_dir):
            try:
                os.remove(os.path.join(_temp_dir, name))
            except OSError:
                pass
        try:
            os.rmdir(_temp_dir)
        except OSError:
            pass
    _temp_dir = None
    _saved_path = None


@native_test
def test_document_scripts_survive_save_reopen():
    global _saved_path
    from plugin.framework.uno_context import get_desktop

    desktop = get_desktop(_test_ctx)
    doc = TestingFactory.create_native_doc(_test_ctx, "writer", hidden=True)
    assert attach_document_script(doc, "RoundTrip", "result = 42") is None
    assert get_document_scripts(doc)["RoundTrip"] == "result = 42"

    _saved_path = os.path.join(_temp_dir, "doc_scripts_test.odt")
    file_url = uno.systemPathToFileUrl(_saved_path)
    doc.storeAsURL(file_url, ())
    doc.close(True)

    reopened = desktop.loadComponentFromURL(file_url, "_blank", 0, (_hidden_prop(),))
    try:
        scripts = get_document_scripts(reopened)
        assert scripts.get("RoundTrip") == "result = 42"
        raw = reopened.getDocumentProperties().UserDefinedProperties.getPropertyValue(DOCUMENT_SCRIPTS_UDPROP)
        assert "RoundTrip" in str(raw)
    finally:
        reopened.close(True)
