# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Anthropic native API provider shim."""

from __future__ import annotations

import json
from typing import Any

from plugin.framework.url_utils import get_url_path_and_query
from .base_provider_shim import BaseProviderShim


class AnthropicShim(BaseProviderShim):
    """Shim for Anthropic native Messages API."""

    def build_chat_request(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
        tools: list[dict[str, Any]] | None,
        stream: bool,
        model_name: str | None,
        response_format: dict[str, Any] | None,
        chat_extra: dict[str, Any] | None = None,
    ) -> tuple[str, str, bytes, dict[str, str]]:
        endpoint = self.client._endpoint()
        url = f"{endpoint}/v1/messages"
        system_msg = ""
        converted: list[dict[str, Any]] = []

        for m in messages:
            role = m.get("role")
            content = m.get("content")

            if role == "system":
                if isinstance(content, list):
                    system_msg = "\n\n".join([p.get("text", "") for p in content if p.get("type") == "text"])
                else:
                    system_msg = str(content or "")
                continue

            anth_content: list[dict[str, Any]] = []

            # 1. Handle tool response messages (role == "tool")
            if role == "tool":
                tool_use_id = m.get("tool_call_id") or m.get("name")
                result_blocks: list[dict[str, Any]] = []
                if isinstance(content, list):
                    for part in content:
                        if part.get("type") == "text":
                            result_blocks.append({"type": "text", "text": part.get("text", "")})
                        elif part.get("type") == "image_url":
                            url_val = part.get("image_url", {}).get("url", "")
                            if url_val.startswith("data:"):
                                header, b64_data = url_val.split(",", 1)
                                mime_type = header.split(";")[0].split(":")[1]
                                result_blocks.append({
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime_type,
                                        "data": b64_data,
                                    },
                                })
                else:
                    result_blocks.append({"type": "text", "text": str(content or "")})

                converted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result_blocks,
                    }],
                })
                continue

            # 2. Handle assistant messages with tool calls
            tool_calls = m.get("tool_calls")
            if tool_calls:
                if isinstance(content, list):
                    for part in content:
                        if part.get("type") == "text":
                            anth_content.append({"type": "text", "text": part.get("text", "")})
                elif content:
                    anth_content.append({"type": "text", "text": str(content)})

                for tc in tool_calls:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", "{}")
                    try:
                        args_obj = json.loads(args) if isinstance(args, str) else args
                    except Exception:
                        args_obj = {}
                    anth_content.append({
                        "type": "tool_use",
                        "id": tc.get("id"),
                        "name": fn.get("name"),
                        "input": args_obj,
                    })
                converted.append({"role": "assistant", "content": anth_content})
                continue

            # 3. Handle standard user/assistant messages with potential images
            if isinstance(content, list):
                for part in content:
                    if part.get("type") == "text":
                        anth_content.append({"type": "text", "text": part.get("text", "")})
                    elif part.get("type") == "image_url":
                        url_val = part.get("image_url", {}).get("url", "")
                        if url_val.startswith("data:"):
                            header, b64_data = url_val.split(",", 1)
                            mime_type = header.split(";")[0].split(":")[1]
                            anth_content.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": mime_type,
                                    "data": b64_data,
                                },
                            })
                converted.append({"role": role or "user", "content": anth_content})
            else:
                converted.append({"role": role or "user", "content": str(content or "")})

        data: dict[str, Any] = {
            "model": model_name or "claude-3-5-sonnet-20241022",
            "messages": converted,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if system_msg:
            data["system"] = system_msg
        if tools:
            data["tools"] = [
                {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                for t in tools
            ]

        path = get_url_path_and_query(url)
        return "POST", path, json.dumps(data).encode("utf-8"), self.client._headers()

    def parse_response_chunk(self, chunk: dict[str, Any]) -> tuple[str, str | None, str | None, dict[str, Any]]:
        msg_type = chunk.get("type", "")
        content = ""
        finish_reason = None
        thinking = None
        delta: dict[str, Any] = {}

        if msg_type == "content_block_delta":
            d = chunk.get("delta", {})
            if d.get("type") == "text_delta":
                content = d.get("text") or ""
        elif msg_type == "message":
            # SYNC response
            content_parts = chunk.get("content", [])
            content = "".join([p.get("text", "") for p in content_parts if p.get("type") == "text"])
            finish_reason = chunk.get("stop_reason")
            # Handle tools
            tool_calls = []
            for p in content_parts:
                if p.get("type") == "tool_use":
                    tool_calls.append({
                        "id": p["id"],
                        "type": "function",
                        "function": {"name": p["name"], "arguments": json.dumps(p["input"])},
                    })
            delta = {"role": "assistant", "content": content}
            if tool_calls:
                delta["tool_calls"] = tool_calls
        elif msg_type == "message_delta":
            finish_reason = chunk.get("delta", {}).get("stop_reason")
        elif msg_type == "message_stop":
            finish_reason = "stop"
        return content, finish_reason, thinking, delta
