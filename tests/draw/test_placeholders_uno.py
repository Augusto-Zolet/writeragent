# WriterAgent - AI Writing Assistant for LibreOffice
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native probe: add_slide layout + placeholder discovery.

Findings-only probe for docs/draw/impress-ai-mercury-2.5-headed-findings.md.
It answers one question: after ``add_slide`` on an Impress doc, do
placeholders exist, and does setting ``page.Layout = 1`` ("text", title+body)
create them immediately? Also checks which shape ``role="body"`` targets.
"""
import json

from plugin.testing_runner import native_test
from plugin.tests.testing_utils import TestingFactory, with_native_doc
from plugin.draw.placeholders import _list_placeholders


def _dv(value):
    """UNO enum / struct / anything -> something json can print."""
    try:
        if hasattr(value, "value"):
            return value.value
    except Exception:
        pass
    return value


def _describe(page):
    rows = []
    for i in range(page.getCount()):
        shape = page.getByIndex(i)
        row = {"index": i}
        for attr in ("Name", "ClassName", "ShapeType"):
            try:
                row[attr] = str(getattr(shape, attr))
            except Exception:
                row[attr] = "-"
        try:
            row["text"] = shape.getString()
        except Exception:
            row["text"] = None
        for prop in ("PresObj", "IsEmptyPresentationObject", "PresObjType"):
            try:
                row[prop] = _dv(shape.getPropertyValue(prop))
            except Exception:
                row[prop] = "-"
        rows.append(row)
    return rows


def _p(label, payload):
    print("PROBE %s: %s" % (label, json.dumps(payload, default=str)), flush=True)


@native_test
@with_native_doc("impress")
def test_add_slide_placeholder_probe(ctx, doc):
    pages = doc.getDrawPages()
    _p("start", {"count": pages.getCount(), "slide0_layout": _dv(pages.getByIndex(0).Layout)})

    res = TestingFactory.execute_tool(doc, ctx, "add_slide", {}, doc_type="impress")
    _p("add_slide", res)

    idx = pages.getCount() - 1
    page = pages.getByIndex(idx)
    _p("new_page", {"idx": idx, "shape_count": page.getCount(), "layout": _dv(page.Layout)})
    _p("before.layout_shapes", _describe(page))

    res = TestingFactory.execute_tool(doc, ctx, "list_placeholders", {"page": idx}, doc_type="impress")
    _p("list_placeholders(before)", res)

    res = TestingFactory.execute_tool(
        doc, ctx, "set_placeholder_text",
        {"page": idx, "role": "title", "text": "T-before"}, doc_type="impress",
    )
    _p("set_title(before.layout)", res)

    # The hypothesis: a fresh insertNewByIndex page has no autolayout, so no
    # placeholders. Setting Layout to 1 ("text" = title + content outline)
    # should instantiate them via the same path SetSlideLayout uses.
    page.Layout = 1
    _p("after.set_layout_immediate", {
        "layout": _dv(page.Layout),
        "shape_count": page.getCount(),
        "shapes": _describe(page),
        "list_placeholders": _list_placeholders(page),
    })

    res = TestingFactory.execute_tool(doc, ctx, "list_placeholders", {"page": idx}, doc_type="impress")
    _p("list_placeholders(after.layout)", res)

    res = TestingFactory.execute_tool(
        doc, ctx, "set_placeholder_text",
        {"page": idx, "role": "title", "text": "TITLE_MARKER"}, doc_type="impress",
    )
    _p("set_title(after.layout)", res)

    res = TestingFactory.execute_tool(
        doc, ctx, "set_placeholder_text",
        {"page": idx, "role": "body", "text": "BODY_MARKER"}, doc_type="impress",
    )
    _p("set_body(after.layout)", res)

    final = _describe(page)
    _p("final_shapes", final)
    for row in final:
        if row.get("text") in ("TITLE_MARKER", "BODY_MARKER"):
            _p("marker_landing", {
                "text": row["text"],
                "index": row["index"],
                "class": row.get("ClassName"),
                "name": row.get("Name"),
            })
