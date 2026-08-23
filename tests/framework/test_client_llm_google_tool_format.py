import json
from unittest.mock import MagicMock
from plugin.framework.client.llm_client import LlmClient
from plugin.tests.testing_utils import MockContext

from plugin.framework.client.google_shim import GoogleShim

def test_google_tool_format():
    config = {
        "endpoint": "https://generativelanguage.googleapis.com",
        "api_key": "test-key",
        "model": "gemini-2.0-flash",
        "provider": "google"
    }
    ctx = MockContext()
    client = LlmClient(config, ctx)
    client._resolve_auth = MagicMock(return_value={"provider": "google", "api_key": "test-key"})
    shim = GoogleShim(client)

    messages = [{"role": "user", "content": "What's the weather?"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the weather",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string"}
                    },
                    "required": ["location"]
                }
            }
        }
    ]

    method, path, body, headers = shim.build_chat_request(messages, max_tokens=512, temperature=0.5, tools=tools, stream=False, model_name="gemini-2.0-flash", response_format=None)
    data = json.loads(body)

    assert "tools" in data
    assert len(data["tools"]) == 1
    assert data["tools"][0]["type"] == "function"
    assert data["tools"][0]["function"]["name"] == "get_weather"
    assert data["tools"][0]["function"]["description"] == "Get the weather"
    assert data["tools"][0]["function"]["parameters"]["properties"]["location"]["type"] == "string"


if __name__ == "__main__":
    test_google_tool_format()
