from unittest.mock import MagicMock

from plugin.tests.testing_utils import setup_uno_mocks
setup_uno_mocks()

from plugin.framework.constants import (
    get_greeting_for_document,
    get_chat_system_prompt_for_document,
    get_core_directives,
    WRITER_CORE_DIRECTIVES,
    CALC_CORE_DIRECTIVES,
    DRAW_CORE_DIRECTIVES,
    DEFAULT_WRITER_GREETING,
    DEFAULT_CALC_GREETING,
    DEFAULT_DRAW_GREETING,
)

def test_get_greeting_for_document_writer():
    model = MagicMock()
    model.supportsService.return_value = False
    assert get_greeting_for_document(model) == DEFAULT_WRITER_GREETING

def test_get_greeting_for_document_calc():
    model = MagicMock()
    def supportsService(service):
        return service == "com.sun.star.sheet.SpreadsheetDocument"
    model.supportsService.side_effect = supportsService
    assert get_greeting_for_document(model) == DEFAULT_CALC_GREETING

def test_get_greeting_for_document_draw():
    model = MagicMock()
    def supportsService(service):
        return service in ("com.sun.star.drawing.DrawingDocument", "com.sun.star.presentation.PresentationDocument")
    model.supportsService.side_effect = supportsService
    assert get_greeting_for_document(model) == DEFAULT_DRAW_GREETING

def test_get_chat_system_prompt_for_document_writer():
    model = MagicMock()
    model.supportsService.return_value = False
    prompt = get_chat_system_prompt_for_document(model)
    from plugin.framework.constants import DEFAULT_CHAT_SYSTEM_PROMPT
    assert prompt == DEFAULT_CHAT_SYSTEM_PROMPT
    assert get_chat_system_prompt_for_document(model, "extra") == DEFAULT_CHAT_SYSTEM_PROMPT + "\n\nextra"


def test_writer_chat_prompt_opens_with_persona_and_color_guidance():
    model = MagicMock()
    model.supportsService.return_value = False
    prompt = get_chat_system_prompt_for_document(model)
    assert "LibreOffice Writer assistant" in prompt
    assert "thoughtful use of color" in prompt


def test_writer_chat_prompt_fix_this_grammar_defaults():
    model = MagicMock()
    model.supportsService.return_value = False
    prompt = get_chat_system_prompt_for_document(model)
    assert '"fix this"' in prompt
    assert "synonym or equivalent" in prompt
    assert "spelling and grammar" in prompt
    assert "current sentence" in prompt
    assert "context" in prompt

def test_get_chat_system_prompt_for_document_calc():
    model = MagicMock()
    def supportsService(service):
        return service == "com.sun.star.sheet.SpreadsheetDocument"
    model.supportsService.side_effect = supportsService
    prompt = get_chat_system_prompt_for_document(model)
    from plugin.framework.constants import DEFAULT_CALC_CHAT_SYSTEM_PROMPT
    assert prompt == DEFAULT_CALC_CHAT_SYSTEM_PROMPT
    assert get_chat_system_prompt_for_document(model, "extra") == DEFAULT_CALC_CHAT_SYSTEM_PROMPT + "\n\nextra"

def test_get_chat_system_prompt_for_document_draw():
    model = MagicMock()
    def supportsService(service):
        return service in ("com.sun.star.drawing.DrawingDocument", "com.sun.star.presentation.PresentationDocument")
    model.supportsService.side_effect = supportsService
    prompt = get_chat_system_prompt_for_document(model)
    from plugin.framework.constants import DEFAULT_DRAW_CHAT_SYSTEM_PROMPT
    assert prompt == DEFAULT_DRAW_CHAT_SYSTEM_PROMPT
    assert get_chat_system_prompt_for_document(model, "extra") == DEFAULT_DRAW_CHAT_SYSTEM_PROMPT + "\n\nextra"


def test_get_core_directives_writer():
    model = MagicMock()
    model.supportsService.return_value = False
    directives = get_core_directives(model)
    assert directives == WRITER_CORE_DIRECTIVES
    assert "delegate_to_specialized_writer_toolset" in directives
    assert 'domain="python"' in directives
    assert "apply_document_content" in directives
    assert 'domain="document_research"' in directives
    assert "to use information from (my / our) personal or business documents" in directives
    assert "to research public topics" in directives
    assert 'domain="web_research") first to find information' not in directives


def test_writer_chat_prompt_delegation_routing_local_vs_web():
    model = MagicMock()
    model.supportsService.return_value = False
    prompt = get_chat_system_prompt_for_document(model)
    assert "to use information from (my / our) personal or business documents" in prompt
    assert "to research public topics" in prompt
    assert "OLE in active doc only" in prompt


def test_specialized_delegation_block_is_single_line():
    from plugin.framework.constants import get_specialized_delegation_for_model, get_specialized_delegation_tool_hint
    from plugin.writer.specialized_base import ToolWriterSpecialBase

    model = MagicMock()
    model.supportsService.return_value = False
    block = get_specialized_delegation_for_model(model)
    assert "SPECIALIZED WRITER" in block
    assert "\n" not in block
    assert get_specialized_delegation_tool_hint(ToolWriterSpecialBase, "Writer") == block


def test_calc_core_directives_local_before_web():
    assert 'domain="document_research"' in CALC_CORE_DIRECTIVES
    assert "to use information from (my / our) personal or business documents" in CALC_CORE_DIRECTIVES
    assert 'domain="web_research") first to find information' not in CALC_CORE_DIRECTIVES


def test_draw_core_directives_local_before_web():
    assert 'domain="document_research"' in DRAW_CORE_DIRECTIVES
    assert "to use information from (my / our) personal or business documents" in DRAW_CORE_DIRECTIVES
    assert 'domain="web_research") first to find information' not in DRAW_CORE_DIRECTIVES


def test_get_core_directives_calc():
    model = MagicMock()
    def supportsService(service):
        return service == "com.sun.star.sheet.SpreadsheetDocument"
    model.supportsService.side_effect = supportsService
    directives = get_core_directives(model)
    assert directives == CALC_CORE_DIRECTIVES
    assert "delegate_to_specialized_calc_toolset" in directives
    assert 'domain="python"' not in directives
    assert "apply_document_content" not in directives


def test_get_core_directives_draw():
    model = MagicMock()
    def supportsService(service):
        return service in ("com.sun.star.drawing.DrawingDocument", "com.sun.star.presentation.PresentationDocument")
    model.supportsService.side_effect = supportsService
    directives = get_core_directives(model)
    assert directives == DRAW_CORE_DIRECTIVES
    assert "delegate_to_specialized_draw_toolset" in directives
    assert 'domain="python"' in directives
    assert "apply_document_content" not in directives


def test_core_directives_prohibit_asking_user_to_paste():
    # Writer
    assert "MUST NOT ask the user where to find it" in WRITER_CORE_DIRECTIVES
    assert "MUST immediately call delegate_to_specialized_writer_toolset(domain=\"document_research\")" in WRITER_CORE_DIRECTIVES
    # Calc
    assert "MUST NOT ask the user where the file is stored" in CALC_CORE_DIRECTIVES
    assert "MUST immediately call delegate_to_specialized_calc_toolset(domain=\"document_research\")" in CALC_CORE_DIRECTIVES
    # Draw
    assert "MUST NOT ask the user where the file is stored" in DRAW_CORE_DIRECTIVES
    assert "MUST immediately call delegate_to_specialized_draw_toolset(domain=\"document_research\")" in DRAW_CORE_DIRECTIVES

