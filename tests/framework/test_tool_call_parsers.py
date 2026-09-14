from plugin.contrib.tool_call_parsers import (
    get_parser,
    get_parser_for_model,
    resolve_parser_name,
)

def test_hermes_parser():
    parser = get_parser("hermes")
    text = 'Hello\n<tool_call>{"name": "test_tool", "arguments": {"cmd": "ls"}}</tool_call>'
    content, tool_calls = parser.parse(text)
    
    assert content == "Hello"
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "test_tool"

def test_hermes_parser_unclosed():
    parser = get_parser("hermes")
    text = '<tool_call>{"name": "test_tool", "arguments": {"cmd": "ls"}'
    content, tool_calls = parser.parse(text)
    
    # Hermes parser now uses safe_json_loads which repairs truncated JSON
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "test_tool"
    assert tool_calls[0]["function"]["arguments"] == '{"cmd": "ls"}'

def test_hermes_parser_normalization():
    parser = get_parser("hermes")
    # provider emitting arguments as an object in-text
    text = '<tool_call>{"name": "test_tool", "arguments": {"cmd": "ls", "args": ["-l", "-a"]}}</tool_call>'
    content, tool_calls = parser.parse(text)

    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "test_tool"
    assert tool_calls[0]["function"]["arguments"] == '{"cmd": "ls", "args": ["-l", "-a"]}'

def test_hermes_parser_whitespace():
    parser = get_parser("hermes")
    # provider emitting whitespace or newlines inside and around the tags
    text = (
        'Hello\n'
        '<tool_call>  \n'
        '{"name": "test_tool", "arguments": {"cmd": "ls"}} \n'
        '  </tool_call>'
    )
    content, tool_calls = parser.parse(text)

    assert content == "Hello"
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "test_tool"
    assert tool_calls[0]["function"]["arguments"] == '{"cmd": "ls"}'

def test_hermes_parser_multiple():
    parser = get_parser("hermes")
    text = (
        'Here are your calls:\n'
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

def test_deepseek_v3_parser():
    parser = get_parser("deepseek_v3")
    text = (
        'Thinking...\n'
        '<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>function<｜tool▁sep｜>get_weather\n'
        '```json\n{"city": "Paris"}\n```<｜tool▁call▁end｜><｜tool▁calls▁end｜>'
    )
    content, tool_calls = parser.parse(text)
    
    assert content == "Thinking..."
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "get_weather"

def test_deepseek_v3_parser_normalization():
    parser = get_parser("deepseek_v3")
    text = (
        '<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>function<｜tool▁sep｜>get_weather\n'
        '```json\n{"city": "Paris", "days": [1, 2, 3]}\n```<｜tool▁call▁end｜><｜tool▁calls▁end｜>'
    )
    content, tool_calls = parser.parse(text)

    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "get_weather"
    # DeepSeek just strips whitespace for args, if it's already a valid string, that's fine
    assert tool_calls[0]["function"]["arguments"] == '{"city": "Paris", "days": [1, 2, 3]}'

def test_deepseek_v3_parser_whitespace():
    parser = get_parser("deepseek_v3")
    text = (
        'Thinking...\n'
        '<｜tool▁calls▁begin｜>   \n'
        '<｜tool▁call▁begin｜> function <｜tool▁sep｜> get_weather \n'
        '```json\n{"city": "Paris"}\n```<｜tool▁call▁end｜>  \n'
        '<｜tool▁calls▁end｜>'
    )
    content, tool_calls = parser.parse(text)

    assert content == "Thinking..."
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"city": "Paris"}'

def test_deepseek_v3_parser_multiple():
    parser = get_parser("deepseek_v3")
    text = (
        'Thinking...\n'
        '<｜tool▁calls▁begin｜>'
        '<｜tool▁call▁begin｜>function<｜tool▁sep｜>get_weather\n'
        '```json\n{"city": "Paris"}\n```<｜tool▁call▁end｜>'
        '<｜tool▁call▁begin｜>function<｜tool▁sep｜>calc\n'
        '```json\n{"expr": "1+1"}\n```<｜tool▁call▁end｜>'
        '<｜tool▁calls▁end｜>'
    )
    content, tool_calls = parser.parse(text)

    assert content == "Thinking..."
    assert tool_calls is not None
    assert len(tool_calls) == 2
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"city": "Paris"}'
    assert tool_calls[1]["function"]["name"] == "calc"
    assert tool_calls[1]["function"]["arguments"] == '{"expr": "1+1"}'

def test_mistral_parser_v11():
    parser = get_parser("mistral")
    text = 'Result[TOOL_CALLS]get_weather{"city": "Berlin"}'
    content, tool_calls = parser.parse(text)
    
    assert content == "Result"
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "get_weather"

def test_mistral_parser_normalization():
    parser = get_parser("mistral")
    # v11 format
    text = 'Result[TOOL_CALLS]get_weather{"city": "Berlin", "days": [1, 2]}'
    _, tool_calls = parser.parse(text)

    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["arguments"] == '{"city": "Berlin", "days": [1, 2]}'

    # prev11 format
    text2 = 'Result[TOOL_CALLS] [{"name": "get_weather", "arguments": {"city": "Berlin", "days": [1, 2]}}]'
    _, tool_calls2 = parser.parse(text2)
    assert tool_calls2 is not None
    assert len(tool_calls2) == 1
    assert tool_calls2[0]["function"]["arguments"] == '{"city": "Berlin", "days": [1, 2]}'

def test_mistral_parser_whitespace():
    parser = get_parser("mistral")
    # v11 format with extra spaces
    text = 'Result[TOOL_CALLS]   get_weather   { "city" : "Berlin" }  '
    content, tool_calls = parser.parse(text)

    assert content == "Result"
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{ "city" : "Berlin" }'

    # prev11 format with extra spaces/newlines
    text2 = 'Result \n [TOOL_CALLS] \n [ \n { "name" : "get_weather" , "arguments" : {"city": "Berlin"} } \n ] '
    content2, tool_calls2 = parser.parse(text2)
    assert content2 == "Result"
    assert tool_calls2 is not None
    assert len(tool_calls2) == 1
    assert tool_calls2[0]["function"]["name"] == "get_weather"
    assert tool_calls2[0]["function"]["arguments"] == '{"city": "Berlin"}'

def test_mistral_parser_v11_multiple():
    parser = get_parser("mistral")
    text = 'Result[TOOL_CALLS]get_weather{"city": "Berlin"}[TOOL_CALLS]calc{"expr": "2+2"}'
    content, tool_calls = parser.parse(text)

    assert content == "Result"
    assert tool_calls is not None
    assert len(tool_calls) == 2
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"city": "Berlin"}'
    assert tool_calls[1]["function"]["name"] == "calc"
    assert tool_calls[1]["function"]["arguments"] == '{"expr": "2+2"}'

def test_mistral_parser_prev11():
    parser = get_parser("mistral")
    text = 'Result[TOOL_CALLS] [{"name": "get_weather", "arguments": {"city": "Berlin"}}]'
    content, tool_calls = parser.parse(text)
    
    assert content == "Result"
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "get_weather"

def test_mistral_parser_prev11_multiple():
    parser = get_parser("mistral")
    text = 'Result[TOOL_CALLS] [{"name": "get_weather", "arguments": {"city": "Berlin"}}, {"name": "calc", "arguments": {"expr": "2+2"}}]'
    content, tool_calls = parser.parse(text)

    assert content == "Result"
    assert tool_calls is not None
    assert len(tool_calls) == 2
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"city": "Berlin"}'
    assert tool_calls[1]["function"]["name"] == "calc"
    assert tool_calls[1]["function"]["arguments"] == '{"expr": "2+2"}'

def test_llama_parser():
    parser = get_parser("llama3_json")
    text = 'Output: <|python_tag|>\n{"name": "calc", "arguments": {"expr": "2+2"}}'
    content, tool_calls = parser.parse(text)
    
    assert content == "Output:"
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "calc"

def test_llama_parser_normalization():
    parser = get_parser("llama3_json")
    text = 'Output: <|python_tag|>\n{"name": "calc", "arguments": {"expr": "2+2", "flags": ["a"]}}'
    content, tool_calls = parser.parse(text)

    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "calc"
    assert tool_calls[0]["function"]["arguments"] == '{"expr": "2+2", "flags": ["a"]}'

def test_llama_parser_whitespace():
    parser = get_parser("llama3_json")
    text = (
        'Output: <|python_tag|>\n\n'
        '  {  \n'
        '  "name": "calc", \n'
        '  "arguments": {"expr": "2+2"} \n'
        '}  \n'
    )
    content, tool_calls = parser.parse(text)

    assert content == "Output:"
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "calc"
    assert tool_calls[0]["function"]["arguments"] == '{"expr": "2+2"}'

def test_llama_parser_multiple():
    parser = get_parser("llama3_json")
    text = 'Output: <|python_tag|>\n{"name": "calc", "arguments": {"expr": "2+2"}}\n{"name": "get_weather", "arguments": {"city": "Paris"}}'
    content, tool_calls = parser.parse(text)

    assert content == "Output:"
    assert tool_calls is not None
    assert len(tool_calls) == 2
    assert tool_calls[0]["function"]["name"] == "calc"
    assert tool_calls[0]["function"]["arguments"] == '{"expr": "2+2"}'
    assert tool_calls[1]["function"]["name"] == "get_weather"
    assert tool_calls[1]["function"]["arguments"] == '{"city": "Paris"}'

def test_get_parser_for_model():
    p1 = get_parser_for_model("hermes-2-pro")
    assert p1 is not None
    # We can check it works instead of strict isinstance on the inner class
    _, tc = p1.parse('<tool_call>{"name": "test", "arguments": {}}</tool_call>')
    assert tc is not None
    
    p2 = get_parser_for_model("deepseek-coder-v3")
    assert p2 is not None
    
    p3 = get_parser_for_model("mistral-large")
    assert p3 is not None
    
    p4 = get_parser_for_model("llama-3-70b")
    assert p4 is not None
    
    assert get_parser_for_model("unknown") is None


def test_resolve_parser_name_most_specific():
    assert resolve_parser_name("hermes-2-pro") == "hermes"
    assert resolve_parser_name("qwen/qwen3.8-27b") == "hermes"
    assert resolve_parser_name("qwen/qwen3-coder-plus") == "qwen3_coder"
    assert resolve_parser_name("qwen3coder") == "qwen3_coder"
    assert resolve_parser_name("deepseek-coder-v3") == "deepseek_v3"
    assert resolve_parser_name("deepseek-v3.1") == "deepseek_v31"
    assert resolve_parser_name("deepseek-v3.2") == "deepseek_v32"
    assert resolve_parser_name("deepseek/deepseek-v4-flash-0731") == "deepseek_v4"
    assert resolve_parser_name("deepseek/deepseek-v4.1-flash") == "deepseek_v41"
    assert resolve_parser_name("minimax/minimax-m2.5") == "minimax_m2"
    assert resolve_parser_name("moonshotai/kimi-k3") == "kimi_k3"
    assert resolve_parser_name("moonshotai/kimi-k2") == "kimi_k2"
    assert resolve_parser_name("kimi-k2-horizon") == "k2_horizon"
    assert resolve_parser_name("z-ai/glm-4.7") == "glm47"
    assert resolve_parser_name("meituan/longcat-2.0") == "longcat"
    assert resolve_parser_name("google/functiongemma-270m-it") == "functiongemma"
    assert resolve_parser_name("google/gemma-4-31b-it") == "gemma4"
    assert resolve_parser_name("llama-4-pythonic") == "llama4_pythonic"
    assert resolve_parser_name("llama-3-70b") == "llama3_json"
    assert resolve_parser_name("unknown") is None
    assert resolve_parser_name("") is None


def test_mistral_parser_args_token():
    parser = get_parser("mistral")
    text = 'Result[TOOL_CALLS]get_weather[ARGS]{"city": "Berlin"} leftover prose'
    content, tool_calls = parser.parse(text)

    assert content == "Result"
    assert tool_calls is not None
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"city": "Berlin"}'


def test_glm47_same_line_and_zero_arg():
    parser = get_parser("glm47")
    text = (
        "Hi\n"
        "<tool_call>get_weather<arg_key>city</arg_key><arg_value>Beijing</arg_value></tool_call>"
        "<tool_call>get_current_date</tool_call>"
    )
    content, tool_calls = parser.parse(text)

    assert content == "Hi"
    assert tool_calls is not None
    assert len(tool_calls) == 2
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"city": "Beijing"}'
    assert tool_calls[1]["function"]["name"] == "get_current_date"
    assert tool_calls[1]["function"]["arguments"] == "{}"


def test_qwen3_coder_whitespace_tags():
    parser = get_parser("qwen3_xml")
    text = (
        "<tool_call>\n"
        "< function=get_weather >\n"
        "< parameter = city >Paris</ parameter >\n"
        "</ function >\n"
        "</tool_call>"
    )
    content, tool_calls = parser.parse(text)
    assert tool_calls is not None
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"city": "Paris"}'


def test_deepseek_v32_parser():
    parser = get_parser("deepseek_v32")
    text = (
        "Looking up.\n"
        "<｜DSML｜function_calls>\n"
        "<｜DSML｜invoke name=\"get_weather\">\n"
        "<｜DSML｜parameter name=\"location\" string=\"true\">杭州</｜DSML｜parameter>\n"
        "<｜DSML｜parameter name=\"count\" string=\"false\">5</｜DSML｜parameter>\n"
        "</｜DSML｜invoke>\n"
        "</｜DSML｜function_calls>"
    )
    content, tool_calls = parser.parse(text)
    assert content == "Looking up."
    assert tool_calls is not None
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"location": "杭州", "count": 5}'


def test_deepseek_v4_parser():
    parser = get_parser("deepseek_v4")
    text = (
        "<think>plan</think>\n"
        "<｜DSML｜tool_calls>\n"
        "<｜DSML｜invoke name=\"calc\">\n"
        "<｜DSML｜parameter name=\"expr\" string=\"true\">1+1</｜DSML｜parameter>\n"
        "</｜DSML｜invoke>\n"
        "</｜DSML｜tool_calls>"
    )
    content, tool_calls = parser.parse(text)
    assert tool_calls is not None
    assert tool_calls[0]["function"]["name"] == "calc"
    assert tool_calls[0]["function"]["arguments"] == '{"expr": "1+1"}'


def test_deepseek_v41_parser():
    parser = get_parser("deepseek_v41")
    text = (
        "<｜DSML｜ calls>\n"
        "<｜DSML｜ invoke name=\"calc\">\n"
        "<｜DSML｜ parameter name=\"expr\" string=\"true\">2+2</｜DSML｜ parameter>\n"
        "</｜DSML｜ invoke>\n"
        "</｜DSML｜ calls>"
    )
    content, tool_calls = parser.parse(text)
    assert tool_calls is not None
    assert tool_calls[0]["function"]["name"] == "calc"
    assert tool_calls[0]["function"]["arguments"] == '{"expr": "2+2"}'


def test_minimax_m2_parser():
    parser = get_parser("minimax_m2")
    text = (
        "Checking.\n"
        "<minimax:tool_call><invoke name=\"get_weather\">"
        "<parameter name=\"city\">Seattle</parameter>"
        "</invoke></minimax:tool_call>"
    )
    content, tool_calls = parser.parse(text)
    assert content == "Checking."
    assert tool_calls is not None
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"city": "Seattle"}'


def test_kimi_k3_parser():
    parser = get_parser("kimi_k3")
    text = (
        "<|open|>response<|sep|>Hi<|close|>response<|sep|>"
        "<|open|>tools<|sep|>"
        '<|open|>call tool="python" index="1"<|sep|>'
        '<|open|>argument key="code" type="string"<|sep|>print(1)<|close|>argument<|sep|>'
        "<|close|>call<|sep|>"
        "<|close|>tools<|sep|>"
    )
    content, tool_calls = parser.parse(text)
    assert content == "Hi"
    assert tool_calls is not None
    assert tool_calls[0]["function"]["name"] == "python"
    assert tool_calls[0]["function"]["arguments"] == '{"code": "print(1)"}'


def test_functiongemma_parser():
    parser = get_parser("functiongemma")
    text = (
        "Call it.\n"
        "<start_function_call>call:get_weather"
        "{city:<escape>\"Paris\"<escape>}<end_function_call>"
    )
    content, tool_calls = parser.parse(text)
    assert content == "Call it."
    assert tool_calls is not None
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"city": "Paris"}'


def test_gemma4_parser():
    parser = get_parser("gemma4")
    text = (
        "Thinking done.\n"
        '<|tool_call>call:get_weather{city:<|"|>Tokyo<|"|>,unit:<|"|>celsius<|"|>}<tool_call|>'
    )
    content, tool_calls = parser.parse(text)
    assert content == "Thinking done."
    assert tool_calls is not None
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"city": "Tokyo", "unit": "celsius"}'


def test_llama4_pythonic_parser():
    parser = get_parser("llama4_pythonic")
    text = '<|python_start|>[get_weather(city="Paris", unit="celsius")]<|python_end|>'
    content, tool_calls = parser.parse(text)
    assert content is None
    assert tool_calls is not None
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"city": "Paris", "unit": "celsius"}'


def test_k2_horizon_parser():
    parser = get_parser("k2_horizon")
    text = (
        "Sure.\n"
        "<ifm|tool_calls>"
        "<ifm|tool_call>get_weather"
        "<ifm|arg_key>city</ifm|arg_key>"
        "<ifm|arg_value>Paris</ifm|arg_value>"
        "</ifm|tool_call>"
        "</ifm|tool_calls>"
    )
    content, tool_calls = parser.parse(text)
    assert content == "Sure."
    assert tool_calls is not None
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["function"]["arguments"] == '{"city": "Paris"}'
