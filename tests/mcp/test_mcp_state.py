"""Pure unit tests for mcp_state.next_state happy-path transitions."""

from plugin.mcp.mcp_state import (
    EventKind,
    ExecuteToolEffect,
    MCPEvent,
    MCPState,
    MCPStateStr,
    ParseRequestEffect,
    next_state,
)


def _idle() -> MCPState:
    return MCPState(status=MCPStateStr.IDLE)


def test_request_received_executes_tool():
    transition = next_state(
        _idle(),
        MCPEvent(
            kind=EventKind.REQUEST_RECEIVED,
            data={
                "tool_name": "ping",
                "arguments": {"x": 1},
                "document_url": "file:///tmp/doc.odt",
                "is_long_running": True,
            },
        ),
    )
    assert transition.state.status == MCPStateStr.EXECUTING_TOOL
    assert transition.state.tool_name == "ping"
    assert transition.state.arguments == {"x": 1}
    assert transition.state.document_url == "file:///tmp/doc.odt"
    assert transition.state.is_long_running is True
    assert any(isinstance(e, ParseRequestEffect) for e in transition.effects)
    exec_effect = next(e for e in transition.effects if isinstance(e, ExecuteToolEffect))
    assert exec_effect.tool_name == "ping"
    assert exec_effect.arguments == {"x": 1}
    assert exec_effect.document_url == "file:///tmp/doc.odt"
    assert exec_effect.is_long_running is True


def test_tool_execution_started_is_noop():
    state = MCPState(status=MCPStateStr.EXECUTING_TOOL, tool_name="ping", arguments={})
    transition = next_state(state, MCPEvent(kind=EventKind.TOOL_EXECUTION_STARTED, data={}))
    assert transition.state is state or transition.state == state
    assert transition.effects == []
