from plugin.contrib.tool_call_parsers import (
    get_parser,
    get_parser_for_model,
)


def test_hermes_parser():
    parser = get_parser()
    text = 'Hello\n<tool_call>{"name": "test_tool", "arguments": {"cmd": "ls"}}</tool_call>'
    content, tool_calls = parser.parse(text)

    assert content == "Hello"
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "test_tool"


def test_hermes_parser_unclosed():
    parser = get_parser()
    text = '<tool_call>{"name": "test_tool", "arguments": {"cmd": "ls"}'
    content, tool_calls = parser.parse(text)

    # Hermes parser uses safe_json_loads which repairs truncated JSON
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "test_tool"
    assert tool_calls[0]["function"]["arguments"] == '{"cmd": "ls"}'


def test_hermes_parser_normalization():
    parser = get_parser()
    # provider emitting arguments as an object in-text
    text = '<tool_call>{"name": "test_tool", "arguments": {"cmd": "ls", "args": ["-l", "-a"]}}</tool_call>'
    content, tool_calls = parser.parse(text)

    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "test_tool"
    assert tool_calls[0]["function"]["arguments"] == '{"cmd": "ls", "args": ["-l", "-a"]}'


def test_hermes_parser_string_arguments():
    parser = get_parser()
    # arguments already encoded as a JSON string
    text = '<tool_call>{"name": "test_tool", "arguments": "{\\"cmd\\": \\"ls\\"}"}</tool_call>'
    content, tool_calls = parser.parse(text)

    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "test_tool"
    assert tool_calls[0]["function"]["arguments"] == '{"cmd": "ls"}'


def test_hermes_parser_whitespace():
    parser = get_parser()
    # provider emitting whitespace or newlines inside and around the tags
    text = (
        "Hello\n"
        "<tool_call>  \n"
        '{"name": "test_tool", "arguments": {"cmd": "ls"}} \n'
        "  </tool_call>"
    )
    content, tool_calls = parser.parse(text)

    assert content == "Hello"
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "test_tool"
    assert tool_calls[0]["function"]["arguments"] == '{"cmd": "ls"}'


def test_hermes_parser_multiple():
    parser = get_parser()
    text = (
        "Here are your calls:\n"
        '<tool_call>{"name": "tool1", "arguments": {"a": 1}}</tool_call>\n'
        '<tool_call>{"name": "tool2", "arguments": {"b": 2}}</tool_call>'
    )
    content, tool_calls = parser.parse(text)

    assert content == "Here are your calls:"
    assert tool_calls is not None
    assert len(tool_calls) == 2
    assert tool_calls[0]["function"]["name"] == "tool1"
    assert tool_calls[0]["function"]["arguments"] == '{"a": 1}'
    assert tool_calls[1]["function"]["name"] == "tool2"
    assert tool_calls[1]["function"]["arguments"] == '{"b": 2}'


def test_get_parser_for_model():
    parser = get_parser_for_model("hermes-2-pro")
    assert parser is not None
    text = '<tool_call>{"name": "calc", "arguments": {"expr": "1+1"}}</tool_call>'
    content, tool_calls = parser.parse(text)
    assert tool_calls is not None
    assert tool_calls[0]["function"]["name"] == "calc"

    # None for empty model name
    assert get_parser_for_model("") is None
