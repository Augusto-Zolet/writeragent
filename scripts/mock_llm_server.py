#!/usr/bin/env python3
# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""OpenAI-compatible mock LLM for sidebar soak tests (HTML chat + web-research loop).

Default bind is 127.0.0.1:18766 — not 8765 (historical MCP) or 18765 (current MCP).

Usage (repo root):
  .venv/bin/python scripts/mock_llm_server.py
  make mock-llm

Point WriterAgent Settings at http://127.0.0.1:18766 and model writeragent-mock.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

DEFAULT_HOST = "127.0.0.1"
# Not 8765 (historical MCP) or 18765 (current MCP).
DEFAULT_PORT = 18766
MOCK_MODEL_ID = "writeragent-mock"

_RESEARCH_RE = re.compile(
    r"\b(research|search|look up|look-up|latest|news|who is|what is)\b",
    re.IGNORECASE,
)
_HTTP_URL_RE = re.compile(r"https?://[^\s)>\"]+", re.IGNORECASE)


@dataclass
class MockLLMConfig:
    delay_ms: int = 25
    offline: bool = False
    always_research: bool = False


@dataclass
class Completion:
    content: str | None = None
    reasoning: str | None = None
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    finish_reason: str = "stop"


def _as_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text" or "text" in item:
                    parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content)


def _tool_names(tools: Any) -> set[str]:
    names: set[str] = set()
    if not isinstance(tools, list):
        return names
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        fn = tool.get("function")
        if isinstance(fn, dict) and fn.get("name"):
            names.add(str(fn["name"]))
        elif tool.get("name"):
            names.add(str(tool["name"]))
    return names


def _last_user_text(messages: list[Any]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            return _as_text(msg.get("content")).strip()
    return ""


def _last_role(messages: list[Any]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role"):
            return str(msg["role"])
    return ""


def _assistant_tool_names(messages: list[Any]) -> list[str]:
    names: list[str] = []
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            if isinstance(fn, dict) and fn.get("name"):
                names.append(str(fn["name"]))
    return names


def _is_smol_research(tool_names: set[str]) -> bool:
    return bool(tool_names & {"web_search", "visit_webpage", "final_answer"})


def _is_main_chat(tool_names: set[str]) -> bool:
    return "web_research" in tool_names


def _looks_like_research(text: str) -> bool:
    return bool(_RESEARCH_RE.search(text or ""))


def _first_url(text: str) -> str:
    match = _HTTP_URL_RE.search(text or "")
    if match:
        return match.group(0).rstrip(".,;")
    return "https://example.com/mock-research"


def _plain_research_report(query: str) -> str:
    topic = (query or "the topic").strip()[:200]
    return (
        f"Findings for {topic}\n"
        "\n"
        "Summary\n"
        f"- Mock research report for: {topic}\n"
        "- Sources are canned (this is not a live model).\n"
        "\n"
        "Notes\n"
        "- Use this endpoint to soak-test sidebar scrolling and the web-research tool loop.\n"
        "- No HTML in this sub-agent answer; the main chat formats HTML after the tool returns."
    )


_HTML_TEMPLATES = (
    (
        "<p>Here is a <strong>mock</strong> take on {topic}. The first paragraph is padding so the "
        "sidebar has something to stream and then re-render as rich text.</p>"
        "<p>Second paragraph: keep sending messages to fill the transcript. This endpoint is "
        "<em>not</em> a real model; it only exists so scrolling and HTML paste can be tested.</p>"
    ),
    (
        "<p>Chatting about {topic}. Below is a short list so lists render in the rich control.</p>"
        "<ul><li>Streamed as plain text first</li><li>Then HTML is pasted after STREAM_DONE</li>"
        "<li>Caret follow is the scroll path</li></ul>"
        "<p>Second paragraph continues so you get two blocks of body text every turn.</p>"
    ),
    (
        "<h2>Mock notes</h2>"
        "<p>Topic: {topic}. Numbered steps exercise ordered lists in the narrow sidebar.</p>"
        "<ol><li>Send a message</li><li>Watch the stream</li><li>Confirm formatted rerender</li></ol>"
        "<p>Second paragraph is filler for scroll height. Repeat until the control is long.</p>"
    ),
    (
        "<p>A tiny table about {topic} — check that cells survive the hidden-Writer paste.</p>"
        "<table><tr><th>Col A</th><th>Col B</th></tr><tr><td>stream</td><td>plain</td></tr>"
        "<tr><td>done</td><td>HTML</td></tr></table>"
        "<p>Second paragraph after the table so the message is still two blocks tall.</p>"
    ),
    (
        "<p>Code-shaped reply for {topic}. The pre block should stay monospaced after rerender.</p>"
        "<pre><code>print('mock-llm')\n# two lines on purpose</code></pre>"
        "<p>Second paragraph: more chat text so history and scroll still have weight.</p>"
    ),
)


def _html_chat(topic: str, turn: int) -> str:
    safe = html.escape((topic or "your message").strip()[:120] or "your message")
    template = _HTML_TEMPLATES[turn % len(_HTML_TEMPLATES)]
    return template.format(topic=safe)


def _html_research_summary(topic: str, tool_text: str) -> str:
    safe = html.escape((topic or "that query").strip()[:120] or "that query")
    snippet = html.escape((tool_text or "").strip().replace("\n", " ")[:280])
    return (
        f"<p>I looked that up. Mock summary for <strong>{safe}</strong>.</p>"
        f"<p>Research sub-agent returned: {snippet or '(empty)'}</p>"
        "<ul><li>example.com/mock-research</li><li>Canned source two</li></ul>"
    )


@dataclass
class _TurnState:
    n: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def next_turn(self) -> int:
        with self.lock:
            self.n += 1
            return self.n


def decide_completion(payload: dict[str, Any], config: MockLLMConfig, turns: _TurnState | None = None) -> Completion:
    """Scripted main-chat / smol-research policy. No real model."""
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    tool_names = _tool_names(payload.get("tools"))
    user_text = _last_user_text(messages)
    last_role = _last_role(messages)
    called = _assistant_tool_names(messages)

    if _is_smol_research(tool_names):
        if config.offline:
            return Completion(
                tool_name="final_answer",
                tool_args={"answer": _plain_research_report(user_text)},
                finish_reason="tool_calls",
            )
        if "visit_webpage" in called:
            return Completion(
                tool_name="final_answer",
                tool_args={"answer": _plain_research_report(user_text)},
                finish_reason="tool_calls",
            )
        if "web_search" in called:
            last_tool_text = ""
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("role") == "tool":
                    last_tool_text = _as_text(msg.get("content"))
                    break
            return Completion(
                tool_name="visit_webpage",
                tool_args={"url": _first_url(last_tool_text)},
                finish_reason="tool_calls",
            )
        query = user_text
        marker = "### CURRENT QUERY:"
        if marker in user_text:
            query = user_text.split(marker, 1)[-1].strip()
        return Completion(
            tool_name="web_search",
            tool_args={"query": query or "mock research", "recency": "any"},
            finish_reason="tool_calls",
        )

    turn = turns.next_turn() if turns is not None else 1
    reasoning = "Mock thinking: pick HTML chat or call web_research."

    if _is_main_chat(tool_names) and last_role == "tool":
        tool_text = ""
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "tool":
                tool_text = _as_text(msg.get("content"))
                break
        return Completion(
            content=_html_research_summary(user_text, tool_text),
            reasoning=reasoning,
            finish_reason="stop",
        )

    if _is_main_chat(tool_names) and (config.always_research or _looks_like_research(user_text)):
        return Completion(
            reasoning=reasoning,
            tool_name="web_research",
            tool_args={"query": user_text or "mock research"},
            finish_reason="tool_calls",
        )

    return Completion(
        content=_html_chat(user_text, turn),
        reasoning=reasoning,
        finish_reason="stop",
    )


def _completion_id() -> str:
    return "chatcmpl-mock-" + uuid.uuid4().hex[:12]


def _chunk_obj(model: str, delta: dict[str, Any], finish_reason: str | None = None) -> dict[str, Any]:
    return {
        "id": _completion_id(),
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


def iter_sse_payloads(completion: Completion, model: str) -> Any:
    """Yield SSE JSON objects; caller writes ``data:`` lines and ``[DONE]``."""
    if completion.reasoning:
        yield _chunk_obj(model, {"reasoning": completion.reasoning})
    if completion.tool_name:
        call_id = "call_mock_" + uuid.uuid4().hex[:8]
        args = json.dumps(completion.tool_args or {}, ensure_ascii=False)
        yield _chunk_obj(
            model,
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": call_id,
                        "type": "function",
                        "function": {"name": completion.tool_name, "arguments": ""},
                    }
                ]
            },
        )
        step = 24
        for i in range(0, len(args), step):
            yield _chunk_obj(
                model,
                {"tool_calls": [{"index": 0, "function": {"arguments": args[i : i + step]}}]},
            )
        yield _chunk_obj(model, {}, finish_reason="tool_calls")
        return
    text = completion.content or ""
    for word in text.split(" "):
        piece = word + " "
        yield _chunk_obj(model, {"content": piece})
    yield _chunk_obj(model, {}, finish_reason=completion.finish_reason or "stop")


def sync_response_body(completion: Completion, model: str) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": completion.content}
    if completion.reasoning:
        message["reasoning"] = completion.reasoning
    if completion.tool_name:
        message["content"] = None
        message["tool_calls"] = [
            {
                "id": "call_mock_" + uuid.uuid4().hex[:8],
                "type": "function",
                "function": {
                    "name": completion.tool_name,
                    "arguments": json.dumps(completion.tool_args or {}, ensure_ascii=False),
                },
            }
        ]
    return {
        "id": _completion_id(),
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": completion.finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def models_list_body() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [{"id": MOCK_MODEL_ID, "object": "model", "owned_by": "writeragent-mock"}],
    }


def make_handler_class(config: MockLLMConfig, turns: _TurnState | None = None) -> type[BaseHTTPRequestHandler]:
    state = turns if turns is not None else _TurnState()

    class MockLLMHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

        def _send_json(self, status: int, body: dict[str, Any]) -> None:
            raw = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/health", "/"):
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")
                return
            if path in ("/v1/models", "/models"):
                self._send_json(200, models_list_body())
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path not in ("/v1/chat/completions", "/chat/completions"):
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self.send_error(400, "invalid json")
                return
            if not isinstance(payload, dict):
                self.send_error(400, "expected object")
                return
            model = str(payload.get("model") or MOCK_MODEL_ID)
            completion = decide_completion(payload, config, state)
            stream = bool(payload.get("stream"))
            if not stream:
                self._send_json(200, sync_response_body(completion, model))
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            delay = max(0, int(config.delay_ms)) / 1000.0
            for obj in iter_sse_payloads(completion, model):
                line = "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
                if delay:
                    time.sleep(delay)
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()

    return MockLLMHandler


def serve(host: str, port: int, config: MockLLMConfig) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler_class(config))
    print(
        f"Mock LLM on http://{host}:{port}/v1 (model {MOCK_MODEL_ID}; "
        f"offline={config.offline} always_research={config.always_research} delay_ms={config.delay_ms})",
        flush=True,
    )
    httpd.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WriterAgent mock OpenAI chat endpoint")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--delay-ms", type=int, default=25, help="Pause between SSE chunks")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Smol research path skips web_search/visit_webpage (final_answer only)",
    )
    parser.add_argument(
        "--always-research",
        action="store_true",
        help="Main chat always emits web_research on user turns",
    )
    args = parser.parse_args(argv)
    config = MockLLMConfig(delay_ms=args.delay_ms, offline=args.offline, always_research=args.always_research)
    serve(args.host, args.port, config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
