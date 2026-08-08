"""Pure unit tests for mcp_state.next_state happy-path transitions."""

from plugin.mcp.mcp_state import (
    EventKind,
    ExecuteToolEffect,
    MCPEvent,
    MCPState,
    MCPStateStr,
    ParseRequestEffect,
    ResolveDocumentEffect,
    StreamResponseEffect,
    next_state,
)


def _idle() -> MCPState:
    return MCPState(status=MCPStateStr.IDLE)


def test_request_received_resolves_document():
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
    assert transition.state.status == MCPStateStr.RESOLVING_DOCUMENT
    assert transition.state.tool_name == "ping"
    assert transition.state.arguments == {"x": 1}
    assert transition.state.document_url == "file:///tmp/doc.odt"
    assert transition.state.is_long_running is True
    assert any(isinstance(e, ParseRequestEffect) for e in transition.effects)
    resolve = next(e for e in transition.effects if isinstance(e, ResolveDocumentEffect))
    assert resolve.document_url == "file:///tmp/doc.odt"
    assert resolve.is_long_running is True


def test_document_resolved_success_executes_tool():
    state = MCPState(
        status=MCPStateStr.RESOLVING_DOCUMENT,
        tool_name="ping",
        arguments={"x": 1},
        document_url="file:///tmp/doc.odt",
        is_long_running=False,
    )
    doc_ctx = object()
    uno_ctx = object()
    transition = next_state(
        state,
        MCPEvent(
            kind=EventKind.DOCUMENT_RESOLVED,
            data={"doc_context": doc_ctx, "doc_type": "calc", "uno_ctx": uno_ctx},
        ),
    )
    assert transition.state.status == MCPStateStr.EXECUTING_TOOL
    assert transition.state.doc_type == "calc"
    assert transition.state.doc_context is doc_ctx
    exec_effect = next(e for e in transition.effects if isinstance(e, ExecuteToolEffect))
    assert exec_effect.tool_name == "ping"
    assert exec_effect.arguments == {"x": 1}
    assert exec_effect.doc_context is doc_ctx
    assert exec_effect.doc_type == "calc"
    assert exec_effect.uno_ctx is uno_ctx
    assert exec_effect.document_url == "file:///tmp/doc.odt"


def test_document_resolved_error_streams_error_response():
    # Resolution failures use StreamResponseEffect(is_error=True), not SendErrorEffect.
    state = MCPState(status=MCPStateStr.RESOLVING_DOCUMENT, tool_name="ping")
    err = {"status": "error", "message": "no doc"}
    transition = next_state(
        state,
        MCPEvent(kind=EventKind.DOCUMENT_RESOLVED, data={"error_payload": err}),
    )
    assert transition.state.status == MCPStateStr.ERROR
    assert transition.state.is_error is True
    assert transition.state.result == err
    assert any(isinstance(e, StreamResponseEffect) and e.is_error and e.result == err for e in transition.effects)


def test_tool_execution_started_is_noop():
    state = MCPState(status=MCPStateStr.EXECUTING_TOOL, tool_name="ping", arguments={})
    transition = next_state(state, MCPEvent(kind=EventKind.TOOL_EXECUTION_STARTED, data={}))
    assert transition.state is state or transition.state == state
    assert transition.effects == []
