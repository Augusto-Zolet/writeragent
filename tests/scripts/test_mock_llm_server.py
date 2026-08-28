# Tests for scripts/mock_llm_server.py

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from scripts.mock_llm_server import (
    MOCK_MODEL_ID,
    Completion,
    MockLLMConfig,
    _TurnState,
    decide_completion,
    make_handler_class,
    models_list_body,
    sync_response_body,
)


def _tools(*names: str) -> list[dict[str, Any]]:
    return [{"type": "function", "function": {"name": n, "parameters": {"type": "object", "properties": {}}}} for n in names]


def test_models_list_includes_mock_id():
    body = models_list_body()
    ids = [row["id"] for row in body["data"]]
    assert MOCK_MODEL_ID in ids


def test_chit_chat_html():
    out = decide_completion(
        {"messages": [{"role": "user", "content": "hello there"}], "tools": _tools("web_research", "apply_document_content")},
        MockLLMConfig(delay_ms=0),
        _TurnState(),
    )
    assert out.tool_name is None
    assert out.content is not None
    assert "<p>" in out.content
    assert "hello there" in out.content or "hello" in out.content


def test_research_keyword_calls_web_research():
    out = decide_completion(
        {
            "messages": [{"role": "user", "content": "look up the latest Python release"}],
            "tools": _tools("web_research"),
        },
        MockLLMConfig(delay_ms=0),
    )
    assert out.tool_name == "web_research"
    assert out.tool_args and "latest Python" in out.tool_args["query"]


def test_tool_result_becomes_html_summary():
    out = decide_completion(
        {
            "messages": [
                {"role": "user", "content": "look up cats"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "web_research", "arguments": '{"query":"cats"}'},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "c1", "content": "Findings\n- Cats are mammals"},
            ],
            "tools": _tools("web_research"),
        },
        MockLLMConfig(delay_ms=0),
    )
    assert out.tool_name is None
    assert out.content is not None
    assert "<p>" in out.content
    assert "Cats are mammals" in out.content


def test_smol_offline_final_answer_plain():
    out = decide_completion(
        {
            "messages": [{"role": "user", "content": "### CURRENT QUERY:\nPython 3.13"}],
            "tools": _tools("web_search", "visit_webpage", "final_answer"),
        },
        MockLLMConfig(offline=True),
    )
    assert out.tool_name == "final_answer"
    answer = (out.tool_args or {}).get("answer") or ""
    assert "<p>" not in answer
    assert "Python 3.13" in answer
    assert "- " in answer


def test_smol_online_sequence():
    tools = _tools("web_search", "visit_webpage", "final_answer")
    cfg = MockLLMConfig(offline=False)
    first = decide_completion({"messages": [{"role": "user", "content": "q"}], "tools": tools}, cfg)
    assert first.tool_name == "web_search"
    second = decide_completion(
        {
            "messages": [
                {"role": "user", "content": "q"},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "web_search", "arguments": '{"query":"q"}'},
                        }
                    ],
                },
                {"role": "tool", "content": "1. https://example.com/a Title"},
            ],
            "tools": tools,
        },
        cfg,
    )
    assert second.tool_name == "visit_webpage"
    assert (second.tool_args or {}).get("url", "").startswith("http")
    third = decide_completion(
        {
            "messages": [
                {"role": "user", "content": "q"},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "web_search", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "content": "hits"},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c2",
                            "type": "function",
                            "function": {"name": "visit_webpage", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "content": "page body"},
            ],
            "tools": tools,
        },
        cfg,
    )
    assert third.tool_name == "final_answer"


def test_sync_tool_call_arguments_are_json_string():
    body = sync_response_body(
        Completion(tool_name="web_research", tool_args={"query": "x"}, finish_reason="tool_calls"),
        "m",
    )
    args = body["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
    assert isinstance(args, str)
    assert json.loads(args)["query"] == "x"


@pytest.fixture
def mock_http():
    config = MockLLMConfig(delay_ms=0, offline=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler_class(config))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    base = f"http://{host}:{port}"
    yield base
    httpd.shutdown()
    thread.join(timeout=2)


def _post_json(url: str, payload: dict[str, Any]) -> Any:
    req = Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=5) as resp:
        return resp.read().decode("utf-8"), resp.headers.get_content_type()


def test_http_models_and_health(mock_http):
    with urlopen(mock_http + "/health", timeout=5) as resp:
        assert resp.read() == b"ok"
    with urlopen(mock_http + "/v1/models", timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    assert data["data"][0]["id"] == MOCK_MODEL_ID


def test_http_stream_chit_chat(mock_http):
    raw, ctype = _post_json(
        mock_http + "/v1/chat/completions",
        {
            "model": MOCK_MODEL_ID,
            "stream": True,
            "messages": [{"role": "user", "content": "hello mock"}],
            "tools": _tools("web_research"),
        },
    )
    assert "text/event-stream" in ctype or "event-stream" in ctype or "<p>" in raw
    assert "[DONE]" in raw
    assert "<p>" in raw


def test_http_stream_web_research_tool(mock_http):
    raw, unused_ctype = _post_json(
        mock_http + "/v1/chat/completions",
        {
            "model": MOCK_MODEL_ID,
            "stream": True,
            "messages": [{"role": "user", "content": "look up pandas"}],
            "tools": _tools("web_research"),
        },
    )
    assert unused_ctype is not None
    assert "web_research" in raw
    assert "tool_calls" in raw


def test_http_sync_offline_final_answer(mock_http):
    raw, unused_ctype = _post_json(
        mock_http + "/v1/chat/completions",
        {
            "model": MOCK_MODEL_ID,
            "stream": False,
            "messages": [{"role": "user", "content": "query"}],
            "tools": _tools("web_search", "final_answer"),
        },
    )
    assert unused_ctype is not None
    body = json.loads(raw)
    tc = body["choices"][0]["message"]["tool_calls"][0]
    assert tc["function"]["name"] == "final_answer"
    args = json.loads(tc["function"]["arguments"])
    assert "<p>" not in args["answer"]


def test_http_404(mock_http):
    with pytest.raises(HTTPError) as err:
        urlopen(mock_http + "/nope", timeout=5)
    assert err.value.code == 404


def test_comment_with_document_text_calls_add_comment():
    doc_system_msg = (
        "You are WriterAgent.\n\n"
        "[DOCUMENT CONTENT]\n"
        "Document length: 30 characters.\n\n"
        "[DOCUMENT START]\n"
        "Welcome to the document test.\n"
        "[END DOCUMENT]"
    )
    out = decide_completion(
        {
            "messages": [
                {"role": "system", "content": doc_system_msg},
                {"role": "user", "content": "Please add a comment to this document"},
            ],
            "tools": _tools("add_comment", "apply_document_content"),
        },
        MockLLMConfig(delay_ms=0),
    )
    assert out.tool_name == "add_comment"
    assert out.tool_args is not None
    assert out.tool_args["search"] == "Welcome"
    assert "Mock comment" in out.tool_args["content"]


def test_comment_with_empty_document_calls_apply_document_content():
    empty_system_msg = (
        "You are WriterAgent.\n\n"
        "[DOCUMENT CONTENT]\n"
        "[DOCUMENT START]\n\n"
        "[END DOCUMENT]"
    )
    out = decide_completion(
        {
            "messages": [
                {"role": "system", "content": empty_system_msg},
                {"role": "user", "content": "insert a comment"},
            ],
            "tools": _tools("add_comment", "apply_document_content"),
        },
        MockLLMConfig(delay_ms=0),
    )
    assert out.tool_name == "apply_document_content"
    assert out.tool_args is not None
    assert out.tool_args["target"] == "beginning"
    assert len(out.tool_args["content"]) > 0


def test_comment_after_apply_content_step():
    out = decide_completion(
        {
            "messages": [
                {"role": "user", "content": "insert a comment"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "apply_document_content",
                                "arguments": '{"target":"beginning","content":["<p>Hello world</p>"]}',
                            },
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "c1", "content": '{"status": "ok", "inserted": true}'},
            ],
            "tools": _tools("add_comment", "apply_document_content"),
        },
        MockLLMConfig(delay_ms=0),
    )
    assert out.tool_name == "add_comment"
    assert out.tool_args is not None
    assert out.tool_args["search"] == "Hello"


def test_comment_after_add_comment_step():
    out = decide_completion(
        {
            "messages": [
                {"role": "user", "content": "insert a comment"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c2",
                            "type": "function",
                            "function": {
                                "name": "add_comment",
                                "arguments": '{"search":"Hello","content":"Mock comment"}',
                            },
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "c2", "content": '{"status": "ok", "comment_added": true}'},
            ],
            "tools": _tools("add_comment", "apply_document_content"),
        },
        MockLLMConfig(delay_ms=0),
    )
    assert out.tool_name is None
    assert out.content is not None
    assert "Comment" in out.content
    assert out.finish_reason == "stop"

