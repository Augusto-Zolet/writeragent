# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Google Gemini Provider Shim.

Combines Google's OpenAI-compatible interface for chat/streaming/tools
with Google's native REST interface for image generation (Imagen & Gemini Multimodal).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from plugin.framework.url_utils import get_url_path_and_query
from .openai_shim import OpenAIShim

log = logging.getLogger(__name__)


class GoogleShim(OpenAIShim):
    """Shim for Google Gemini: OpenAI-compatible for chat/tools, native REST for images."""

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

