# PM & Development Plan: Semantic Style Models in HTML

## Problem Statement

Currently, when the agent reads a Writer document via `get_document_content`, the extension flattens LibreOffice paragraph and character styles into computed inline CSS (e.g., `<p style="font-size: 10pt; font-style: italic">`). 

This creates a significant gap in the agent's understanding:
1. **Loss of Semantic Context:** The agent cannot tell that a paragraph uses the `Caption` or `Heading 1` named style. It only sees the final visual properties.
2. **Indistinguishable Overrides:** The agent cannot differentiate between properties inherited from a named style and manual "direct overrides" applied by the user (e.g., highlighting a single word).
3. **Write-Path Degradation:** Because the agent only sees inline styles, it generates inline styles when writing back to the document via `apply_document_content`. This bypasses LibreOffice's style system and pollutes the document with hardcoded formatting.

While the original proposal to add a `get_paragraph_metadata` tool provides accurate data, it introduces overhead by forcing the agent to make secondary tool calls to inspect the document structure piecemeal.

## Proposed Solution (Product Management)

Instead of a separate diagnostic tool, we will **embed the LibreOffice style model directly into the HTML representation**.

We will achieve **Read/Write Symmetry**:
- **Read:** Paragraphs will include their named style as a custom data attribute (e.g., `<p data-lo-style="Caption">`). Inline `style="..."` attributes will be reserved *exclusively* for direct formatting overrides.
- **Write:** When the agent generates HTML, it will use `<p data-lo-style="Caption">` to apply named styles. The extension will read this attribute and apply the correct LibreOffice style, applying any inline CSS as direct overrides on top.

**Benefits:**
- **Zero Tool-Call Overhead:** The agent gets the full semantic structure in a single read pass.
- **Native LLM Paradigm:** LLMs excel at understanding HTML where classes/attributes define the theme and inline styles define exceptions.
- **Cleaner Documents:** The agent naturally learns to apply named styles rather than raw formatting.

## Development Plan

### Phase 1: Update the Read Path (`get_document_content`)
*Target Files: `plugin/writer/content.py` / HTML generation logic*

1. **Inject Style Attributes:** Modify the HTML generation loop to extract the paragraph's named style and attach it as a `data-lo-style` attribute to the outgoing HTML tags (`<p>`, `<h1>`, etc.).
2. **Isolate Direct Overrides:** Integrate the `char_overrides_for_portion` logic (from the `get_paragraph_metadata` PR) to detect which properties differ from the named style's default.
3. **Filter Inline CSS:** Change the CSS generation so that it *only* outputs inline `style="..."` properties for the detected direct overrides. Do not output the computed style.

### Phase 2: Update the Write Path (`apply_document_content`)
*Target Files: `plugin/writer/format_support.py`*

1. **Parse Semantic Attributes:** Update the HTML parser to recognize the `data-lo-style` attribute on incoming block elements.
2. **Apply Named Styles:** Before applying inline CSS, look up the LibreOffice style specified in `data-lo-style` and apply it to the target paragraph.
3. **Apply Overrides:** Let the existing inline CSS parser run on top of the paragraph. Because the HTML only contains overrides, this cleanly maps the manual formatting on top of the named style without destroying the base style.

### Phase 3: Testing & Documentation
1. **UNO Regression Tests:** Add round-trip tests verifying that reading a styled paragraph with a bold override outputs `<p data-lo-style="Text Body">normal <span style="font-weight: bold">bold</span></p>`, and writing it back recreates the exact same UNO style state.
2. **Agent Prompt Updates:** Update the system prompt instructions (`WRITER_APPLY_DOCUMENT_HTML_RULES` in `constants.py`) to instruct the agent to read and write `data-lo-style` attributes for proper styling.
3. **Evaluate `get_paragraph_metadata`:** Decide if the low-level JSON tool is still needed for edge-case debugging. If so, merge it as a `specialized` tier tool rather than a core requirement.

## Implementation Details
> [!NOTE]
> **Localization:** We will use internal UI names (e.g., `Standard` instead of `Default Paragraph Style`). This is strictly for the LLM's tooling—it does not care if the names are localized. Using internal names makes the implementation simpler and more robust, as we only localize user-visible elements, not tool-visible ones.
>
> **Unsupported Styles:** If `apply_document_content` encounters a `data-lo-style` value that doesn't exist in the current document, it will gracefully fall back to the `Standard` style.
