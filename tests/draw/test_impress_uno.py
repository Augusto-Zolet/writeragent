# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2024 John Balis
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import json
from plugin.framework.logging import log
from plugin.testing_runner import native_test
from plugin.tests.testing_utils import TestingFactory, with_native_doc


def _exec_tool(doc, ctx, name, args):
    res = TestingFactory.execute_tool(doc, ctx, name, args, doc_type="impress")
    return json.dumps(res) if isinstance(res, dict) else res



@native_test
@with_native_doc("impress")
def test_slide_transitions(ctx, doc):
    # Initial transition state
    result = _exec_tool(doc, ctx, "get_slide_transition", {"page_index": 0})
    data = json.loads(result)
    assert data.get("status") == "ok", f"get_slide_transition failed: {result}"

    # Set a transition
    result = _exec_tool(doc, ctx, "set_slide_transition", {
        "page_index": 0,
        "effect": "fade_from_left",
        "speed": "fast",
        "duration": 5,
        "transition_duration": 1.5,
        "advance": "auto"
    })
    data = json.loads(result)
    assert data.get("status") == "ok", f"set_slide_transition failed: {result}"

    # Verify the transition is set correctly
    result = _exec_tool(doc, ctx, "get_slide_transition", {"page_index": 0})
    data = json.loads(result)
    assert data.get("status") == "ok", f"get_slide_transition failed: {result}"
    assert data.get("effect") == "fade_from_left", f"Effect mismatch: {data.get('effect')}"
    assert data.get("speed") == "fast", f"Speed mismatch: {data.get('speed')}"
    assert data.get("duration") == 5, f"Duration mismatch: {data.get('duration')}"
    assert data.get("advance") == "auto", f"Advance mismatch: {data.get('advance')}"


@native_test
@with_native_doc("impress")
def test_speaker_notes(ctx, doc):
    # Set new notes
    result = _exec_tool(doc, ctx, "set_speaker_notes", {
        "page_index": 0,
        "text": "These are my speaker notes for the first slide."
    })
    data = json.loads(result)
    assert data.get("status") == "ok", f"set_speaker_notes failed: {result}"

    # Append to notes
    result = _exec_tool(doc, ctx, "set_speaker_notes", {
        "page_index": 0,
        "text": "And some more notes.",
        "append": True
    })
    data = json.loads(result)
    assert data.get("status") == "ok", f"set_speaker_notes append failed: {result}"

    # Get notes and verify
    result = _exec_tool(doc, ctx, "get_speaker_notes", {"page_index": 0})
    data = json.loads(result)
    assert data.get("status") == "ok", f"get_speaker_notes failed: {result}"
    notes = data.get("notes")
    assert "These are my speaker notes for the first slide." in notes, f"Expected notes not found: {notes}"
    assert "And some more notes." in notes, f"Expected appended notes not found: {notes}"
