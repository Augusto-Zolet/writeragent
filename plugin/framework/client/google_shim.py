# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Google Gemini provider shim."""

from __future__ import annotations

import json
import logging
from typing import Any

from plugin.framework.url_utils import get_url_path_and_query
from .base_provider_shim import BaseProviderShim

log = logging.getLogger(__name__)


class GoogleShim(BaseProviderShim):
    """Shim for Google Gemini native API."""

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
        auth_info = self.client._resolve_auth()
        key = auth_info.get("api_key", "")
        m_id = model_name or "gemini-1.5-flash"
        if not m_id.startswith("models/"):
            m_id = f"models/{m_id}"
        action = ":streamGenerateContent" if stream else ":generateContent"
        url = f"{endpoint}/v1beta/{m_id}{action}?key={key}"

        contents: list[dict[str, Any]] = []
        system_instruction: dict[str, Any] | None = None

        for m in messages:
            role = m.get("role", "user")
            parts: list[dict[str, Any]] = []

            content = m.get("content")
            if content:
                if isinstance(content, str):
                    parts.append({"text": content})
                elif isinstance(content, list):
                    for part in content:
                        if part.get("type") == "text":
                            parts.append({"text": part.get("text", "")})
                        elif part.get("type") == "image_url":
                            url_val = part.get("image_url", {}).get("url", "")
                            if url_val.startswith("data:"):
                                try:
                                    header, b64_data = url_val.split(",", 1)
                                    mime_type = header.split(";")[0].split(":")[1]
                                    parts.append({
                                        "inlineData": {
                                            "mimeType": mime_type,
                                            "data": "".join(b64_data.split()),
                                        }
                                    })
                                except Exception:
                                    log.exception("Failed to parse base64 image in GoogleShim")

            tool_calls = m.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", "{}")
                    try:
                        args_obj = json.loads(args) if isinstance(args, str) else args
                    except Exception:
                        args_obj = {}
                    parts.append({"functionCall": {"name": fn.get("name"), "args": args_obj}})

            if role == "system":
                system_instruction = {"parts": parts}
            elif role == "tool":
                try:
                    resp_obj = json.loads(content) if isinstance(content, str) else content
                except Exception:
                    resp_obj = {"result": content}
                if not isinstance(resp_obj, dict):
                    resp_obj = {"result": resp_obj}
                contents.append({
                    "role": "function",
                    "parts": [{"functionResponse": {"name": m.get("name") or m.get("tool_call_id"), "response": resp_obj}}],
                })
            else:
                if role == "assistant":
                    role = "model"
                contents.append({"role": role, "parts": parts})

        google_data: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        if system_instruction:
            google_data["system_instruction"] = system_instruction
        if tools:
            decls = [
                {
                    "name": t.get("function", {}).get("name"),
                    "description": t.get("function", {}).get("description", ""),
                    "parameters": t.get("function", {}).get("parameters", {"type": "object", "properties": {}}),
                }
                for t in tools
            ]
            google_data["tools"] = [{"function_declarations": decls}]

        path = get_url_path_and_query(url)
        return "POST", path, json.dumps(google_data).encode("utf-8"), self.client._headers()

    def parse_response_chunk(self, chunk: dict[str, Any]) -> tuple[str, str | None, str | None, dict[str, Any]]:
        candidates = chunk.get("candidates", [])
        choice = candidates[0] if candidates else {}
        content = ""
        tool_calls: list[dict[str, Any]] = []
        parts = choice.get("content", {}).get("parts", [])
        for p in parts:
            if "text" in p:
                content += p.get("text") or ""
            if "functionCall" in p:
                fc = p["functionCall"]
                tool_calls.append({
                    "id": fc.get("id", "call_" + str(len(tool_calls))),
                    "type": "function",
                    "function": {"name": fc.get("name"), "arguments": json.dumps(fc.get("args", {}))},
                })
        finish_reason = choice.get("finishReason")
        if finish_reason == "STOP":
            finish_reason = "stop"

        usage = chunk.get("usageMetadata", {})
        delta: dict[str, Any] = {"usage": usage}
        if tool_calls:
            delta["tool_calls"] = tool_calls
        return content, finish_reason, None, delta

    def build_image_request(
        self,
        prompt: str,
        model: str | None,
        width: int,
        height: int,
        steps: int | None = None,
        source_image: str | None = None,
        image_url: str | None = None,
    ) -> tuple[str, str, bytes, dict[str, str]]:
        endpoint = self.client._endpoint()
        key = self.client._resolve_auth().get("api_key", "")
        model_name = model or "imagen-3.0-generate-002"

        if model_name.startswith("imagen"):
            url = f"{endpoint}/v1beta/models/{model_name}:predict?key={key}"
            aspect = "1:1"
            if width > height * 1.5:
                aspect = "16:9"
            elif height > width * 1.5:
                aspect = "9:16"

            data: dict[str, Any] = {"instances": [{"prompt": prompt}], "parameters": {"sampleCount": 1, "aspectRatio": aspect}}
        else:
            url = f"{endpoint}/v1beta/models/{model_name}:generateContent?key={key}"
            data = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}}

        path = get_url_path_and_query(url)
        return "POST", path, json.dumps(data).encode("utf-8"), self.client._headers()

    def parse_image_responses(self, response_data: dict[str, Any]) -> list[str]:
        out: list[str] = []
        if "error" in response_data:
            msg = response_data["error"].get("message", "Unknown Google API error")
            log.error("Google image generation error: %s", msg)
            return []

        if "predictions" in response_data:
            preds = response_data.get("predictions", [])
            for pr in preds:
                if b64 := pr.get("bytesBase64Encoded"):
                    out.append(b64)

        candidates = response_data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for p in parts:
                inline = p.get("inlineData", {})
                if inline and inline.get("data"):
                    out.append(inline["data"])
        return out

    def parse_sync_response(
        self, response_data: dict[str, Any]
    ) -> tuple[str, str | None, list[dict[str, Any]] | None, dict[str, Any], list[str], dict[str, Any]]:
        content, finish_reason, _unused, delta = self.parse_response_chunk(response_data)
        tool_calls = delta.get("tool_calls")
        usage = response_data.get("usage") or response_data.get("usageMetadata") or {}
        images = delta.get("images") or []
        return content, finish_reason, tool_calls, usage, images, delta
