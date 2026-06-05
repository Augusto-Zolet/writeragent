# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2024 John Balis
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Writer content tools — read, apply, find, and paragraph operations."""

import logging

from plugin.framework.tool import ToolBase, ToolBaseDummy
from plugin.doc.document_helpers import normalize_linebreaks
from plugin.framework.errors import safe_json_loads
import re as re_mod


log = logging.getLogger("writeragent.writer")

# Cap for replace-all search (_find_all_ranges).
_MAX_SEARCH_REPLACEMENTS = 200

# Non-breaking / exotic spaces -> ASCII space. Length-preserving (each maps to a
# single BMP char) so character offsets into the document text stay valid. NBSP
# (U+00A0) in particular is a common artifact of prior edits and breaks literal
# search when old_content uses a normal space.
#
# Regenerate the inventory table: python3 -c "..."  (see git history / plan doc) or
# run the snippet in the finish-NBSP plan; paste rows here when expanding the map.
#
# | Code   | Name                         | In _SPACE_NORMALIZE_MAP | Follow-up note |
# |--------|------------------------------|-------------------------|----------------|
# | U+0020 | SPACE                        | no                      | target; not mapped |
# | U+00A0 | NO-BREAK SPACE               | yes                     | mapped today |
# | U+1680 | OGHAM SPACE MARK             | no                      | OGHAM SPACE MARK; rare in Writer |
# | U+2000 | EN QUAD                      | yes                     | mapped today |
# | U+2001 | EM QUAD                      | yes                     | mapped today |
# | U+2002 | EN SPACE                     | yes                     | mapped today |
# | U+2003 | EM SPACE                     | yes                     | mapped today |
# | U+2004 | THREE-PER-EM SPACE           | yes                     | mapped today |
# | U+2005 | FOUR-PER-EM SPACE            | yes                     | mapped today |
# | U+2006 | SIX-PER-EM SPACE             | yes                     | mapped today |
# | U+2007 | FIGURE SPACE                 | yes                     | mapped today |
# | U+2008 | PUNCTUATION SPACE            | yes                     | mapped today |
# | U+2009 | THIN SPACE                   | yes                     | mapped today |
# | U+200A | HAIR SPACE                   | yes                     | mapped today |
# | U+202F | NARROW NO-BREAK SPACE        | yes                     | mapped today |
# | U+205F | MEDIUM MATHEMATICAL SPACE    | yes                     | mapped today |
# | U+3000 | IDEOGRAPHIC SPACE            | yes                     | mapped today |
#
# DEVELOPER DISCUSSION / FUTURE WORK (Intentionally deferred to avoid complexity):
#
# - Format.py search-replace helpers:
#   Functions like format.find_text_ranges are currently LO-native only. If they need to handle
#   the exotic unicode spaces (like NBSP, Thin Space), we would need to integrate the Python-level
#   fallback here. Deferred because non-apply_document_content callers are internal or benchmark-only.
#
# - all_matches LO findNext fast path hybrid:
#   Currently, _find_all_ranges (all_matches=True) uses Python-level full-text scanning. We could
#   theoretically run LO findNext first and merge it with the offset fallback (deduplicated by start index)
#   for performance. Deferred because Python's string scan is extremely fast (<1ms) for documents
#   under the 200-replacement limit, and a hybrid path introduces offset misalignment bugs.
#
# - Casefolding & Unicode length changes:
#   Case-insensitive lookup uses .lower() which fails for German ß (folds to ss, changing length)
#   or Turkish I. Using .casefold() resolves the fold, but changes string length. If length changes,
#   character offset cursors (like goRight) will highlight the wrong text. Deferred because fixing this
#   requires complex character mapping tracking, which is overkill for rare edge cases.
#
# - Nested XText search (tables, cells, frames, headers/footers):
#   _find_range_by_offset and _find_all_ranges scan doc.getText(), which only covers the document body.
#   Search targets inside tables or text frames will be missed by the Python-level fallback.
#   We keep it this way because single-match searches prefer LO's native findFirst (which searches cells/frames).
#   To fix this, we would need to recursively scan all nested XText containers, which is highly complex.
#
# - Markup apply in nested XText:
#   When inserting HTML/markup inside a table cell, the HTML import helper (replace_single_range_with_content)
#   can sometimes jump the cursor to the end of the document body rather than the cell's end. This is a potential
#   real-world bug if the AI attempts to write rich formatting/math inside cells, but we defer it until we
#   receive actual user bug reports due to the complexity of relative cursor mapping in nested XText.
_SPACE_CODEPOINTS = (
    0x00A0,  # NO-BREAK SPACE
    0x202F,  # NARROW NO-BREAK SPACE
    0x2007,  # FIGURE SPACE
    0x2009,  # THIN SPACE
    # Typographic spaces
    0x2000,  # EN QUAD
    0x2001,  # EM QUAD
    0x2002,  # EN SPACE
    0x2003,  # EM SPACE
    0x2004,  # THREE-PER-EM SPACE
    0x2005,  # FOUR-PER-EM SPACE
    0x2006,  # SIX-PER-EM SPACE
    0x2008,  # PUNCTUATION SPACE
    0x200A,  # HAIR SPACE
    0x205F,  # MEDIUM MATHEMATICAL SPACE
    # CJK space
    0x3000,  # IDEOGRAPHIC SPACE
)
_SPACE_NORMALIZE_MAP = {cp: " " for cp in _SPACE_CODEPOINTS}
# Regex class for _normalize_search_string_for_find — must stay aligned with _SPACE_CODEPOINTS.
_HORIZONTAL_SPACE_RE = r"[ \t" + "".join("\\u%04x" % cp for cp in _SPACE_CODEPOINTS) + "]+"


def _search_try_strings(search_string):
    """Literal search string, then newline-collapsed variant (HTML wrap artifact)."""
    s = search_string or ""
    collapsed = re_mod.sub(r" +", " ", s.replace("\n", " ")).strip()
    for candidate in (s, collapsed):
        if candidate:
            yield candidate


def _all_text_containers(doc):
    """Yield all XText containers in the document: body, table cells, text frames."""
    yield doc.getText()

    if hasattr(doc, "getTextTables"):
        try:
            tables = doc.getTextTables()
            for name in tables.getElementNames():
                table = tables.getByName(name)
                for cell_name in table.getCellNames():
                    yield table.getCellByName(cell_name)
        except Exception:
            log.debug("Error iterating document text tables", exc_info=True)

    if hasattr(doc, "getTextFrames"):
        try:
            frames = doc.getTextFrames()
            for name in frames.getElementNames():
                yield frames.getByName(name)
        except Exception:
            log.debug("Error iterating document text frames", exc_info=True)


def _escape_for_lo_regex(s):
    """Escape regular expression characters and match any horizontal space sequence."""
    escaped = re_mod.sub(r'([\\^$.|?*+()\[\]{}])', r'\\\1', s)
    space_class = r"[ \t" + "".join("\\u%04x" % cp for cp in _SPACE_CODEPOINTS) + "]"
    return re_mod.sub(r' +', lambda m: space_class + '+', escaped)


def _compare_normalize(s):
    return normalize_linebreaks(s).translate(_SPACE_NORMALIZE_MAP).strip().lower()


def _find_chained_range(doc, search_string, all_matches=False):
    """Find search_string natively via Regex Search descriptors and paragraph chaining.
    Handles exotic spaces and multi-paragraph searches inside cells, frames, and body text.
    """
    if not search_string:
        return [] if all_matches else None

    # First, try to match the entire search string as a single native regex query.
    # This matches successfully if any newlines in the query are line breaks (\n) within
    # the same paragraph, or if it is a single-paragraph search.
    sd = doc.createSearchDescriptor()
    sd.SearchRegularExpression = True
    sd.SearchString = _escape_for_lo_regex(search_string)

    if not all_matches:
        for case_sens in (True, False):
            sd.SearchCaseSensitive = case_sens
            found = doc.findFirst(sd)
            if found is not None:
                return found
    else:
        ranges = []
        for case_sens in (True, False):
            sd.SearchCaseSensitive = case_sens
            found = doc.findFirst(sd)
            while found is not None:
                if len(ranges) >= _MAX_SEARCH_REPLACEMENTS:
                    return ranges
                ranges.append(found)
                found = doc.findNext(found, sd)
            if ranges:
                return ranges

    # If the whole-string search failed, and there are newlines, it means those newlines
    # represent real paragraph breaks (which LibreOffice regex cannot cross). We fall back
    # to the paragraph chaining algorithm.
    parts = search_string.split('\n')
    if len(parts) <= 1:
        return [] if all_matches else None

    # Find the first non-empty part to anchor on.
    anchor_idx = -1
    for idx, part in enumerate(parts):
        if part.strip():
            anchor_idx = idx
            break
    if anchor_idx == -1:
        return [] if all_matches else None

    sd = doc.createSearchDescriptor()
    sd.SearchRegularExpression = True
    sd.SearchString = _escape_for_lo_regex(parts[anchor_idx])

    matched_ranges = []

    for case_sens in (True, False):
        sd.SearchCaseSensitive = case_sens
        found = doc.findFirst(sd)
        while found is not None:
            text = found.getText()
            chain_ok = True

            # 1. Verify forward paragraphs (from anchor_idx + 1 to len(parts) - 1)
            forward_cursor = text.createTextCursorByRange(found)
            forward_cursor.gotoRange(found.getEnd(), False)
            last_end_cursor = None

            for i in range(anchor_idx + 1, len(parts)):
                if not forward_cursor.gotoNextParagraph(False):
                    chain_ok = False
                    break
                
                check_cursor = text.createTextCursorByRange(forward_cursor)
                check_cursor.gotoEndOfParagraph(True)
                para_text = check_cursor.getString()

                expected_norm = _compare_normalize(parts[i])
                actual_norm = _compare_normalize(para_text)

                if i == len(parts) - 1:
                    if not actual_norm.startswith(expected_norm):
                        chain_ok = False
                        break
                    skipped_leading = len(para_text) - len(para_text.lstrip())
                    match_len = skipped_leading + len(parts[i].strip())
                    last_end_cursor = text.createTextCursorByRange(forward_cursor)
                    last_end_cursor.goRight(match_len, False)
                else:
                    if actual_norm != expected_norm:
                        chain_ok = False
                        break

            if not chain_ok:
                found = doc.findNext(found, sd)
                continue

            # 2. Verify backward paragraphs (from anchor_idx - 1 down to 0)
            backward_cursor = text.createTextCursorByRange(found)
            backward_cursor.gotoRange(found.getStart(), False)
            first_start_cursor = None

            for i in range(anchor_idx - 1, -1, -1):
                if not backward_cursor.gotoPreviousParagraph(False):
                    chain_ok = False
                    break

                check_cursor = text.createTextCursorByRange(backward_cursor)
                check_cursor.gotoEndOfParagraph(True)
                para_text = check_cursor.getString()

                expected_norm = _compare_normalize(parts[i])
                actual_norm = _compare_normalize(para_text)

                if i == 0:
                    if not actual_norm.endswith(expected_norm):
                        chain_ok = False
                        break
                    trimmed_trailing = para_text.rstrip()
                    start_offset = max(0, len(trimmed_trailing) - len(parts[i].strip()))
                    first_start_cursor = text.createTextCursorByRange(backward_cursor)
                    first_start_cursor.goRight(start_offset, False)
                else:
                    if actual_norm != expected_norm:
                        chain_ok = False
                        break

            if chain_ok:
                start_range = first_start_cursor.getStart() if first_start_cursor else found.getStart()
                end_range = last_end_cursor.getStart() if last_end_cursor else found.getEnd()
                
                try:
                    result_range = text.createTextCursorByRange(start_range)
                    result_range.gotoRange(end_range, True)
                    if not all_matches:
                        return result_range
                    matched_ranges.append(result_range)
                    if len(matched_ranges) >= _MAX_SEARCH_REPLACEMENTS:
                        return matched_ranges
                except Exception:
                    log.debug("Failed creating combined XTextRange", exc_info=True)

            found = doc.findNext(found, sd)

        if matched_ranges:
            return matched_ranges

    return matched_ranges if all_matches else None


def _find_first_range(doc, search_string):
    """First match: LO native search with chaining fallback."""
    return _find_chained_range(doc, search_string, all_matches=False)


def _normalize_search_string_for_find(s):
    """Collapse horizontal whitespace (incl. NBSP & friends) to a single ASCII
    space; preserve newlines for literal find.
    """
    return re_mod.sub(_HORIZONTAL_SPACE_RE, " ", s).strip()


def _all_start_indices(haystack, needle):
    """Non-overlapping start indices of *needle* in *haystack*."""
    out = []
    if not needle:
        return out
    i = haystack.find(needle)
    while i >= 0:
        out.append(i)
        i = haystack.find(needle, i + len(needle))
    return out


def _find_all_ranges(doc, search_string):
    """All occurrences as TextRanges in document order (NBSP-aware native search with chaining)."""
    return _find_chained_range(doc, search_string, all_matches=True)


# ------------------------------------------------------------------
# GetDocumentContent
# ------------------------------------------------------------------


class GetDocumentContent(ToolBase):
    """Export the document (or a portion) as formatted content."""

    name = "get_document_content"
    description = "Get document (or selection/range) content. Result includes document_length. scope: full, selection, or range (requires start, end)."
    parameters = {
        "type": "object",
        "properties": {
            "scope": {"type": "string", "enum": ["full", "selection", "range"], "description": ("Return full document (default), current selection/cursor region, or a character range (requires start and end).")},
            "max_chars": {"type": "integer", "description": "Maximum characters to return."},
            "start": {"type": "integer", "description": "Start character offset (0-based). Required for scope 'range'."},
            "end": {"type": "integer", "description": "End character offset (exclusive). Required for scope 'range'."},
        },
        "required": [],
    }
    uno_services = ["com.sun.star.text.TextDocument"]
    tier = "core"

    def execute(self, ctx, **kwargs):
        from . import format as format_support
        scope = kwargs.get("scope", "full")
        max_chars = kwargs.get("max_chars")
        range_start = kwargs.get("start") if scope == "range" else None
        range_end = kwargs.get("end") if scope == "range" else None

        if scope == "range" and (range_start is None or range_end is None):
            return self._tool_error("scope 'range' requires start and end.")

        content = format_support.document_to_content(ctx.doc, ctx.ctx, ctx.services, max_chars=max_chars, scope=scope, range_start=range_start, range_end=range_end)
        doc_len = ctx.services.document.get_document_length(ctx.doc)
        result = {"status": "ok", "content": content, "length": len(content), "document_length": doc_len}
        if scope == "range" and range_start is not None and range_end is not None:
            result["start"] = int(range_start)
            result["end"] = int(range_end)
        return result


# ------------------------------------------------------------------
# ApplyDocumentContent
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# ApplyDocumentContent
# ------------------------------------------------------------------


class ApplyDocumentContent(ToolBase):
    """Insert or replace content in the document.

    Design notes (important for callers and future maintainers):

    - **Two edit paths**:
      - *Import path* (HTML/markup): for structural rewrites (tables, headings,
        page changes) we prepare HTML in `format_support` and import it via
        ``insertDocumentFromURL``. This is what all of the `insert_*` helpers
        use.
      - *Format‑preserving path* (plain text): for small textual corrections
        we avoid HTML entirely and call `format_support.replace_preserving_format`,
        which mutates characters in place so existing character‑level styling
        (bold, colors, background fills, etc.) is preserved even when the
        replacement text length differs.

    - **Decision rule**: we treat content as *plain text* (and thus eligible
      for format‑preserving replacement) only when `content_has_markup` is
      false. Any obvious HTML/Markdown markers force the import path. This
      keeps the heuristic simple and robust: small literal edits naturally
      stay plain text; rich formatting naturally uses HTML.

    - **Raw vs wrapped content**: `raw_content` is captured *before* any HTML
      wrapping or newline normalization and is passed to the preserving path;
      the (possibly HTML‑wrapped) `content` value is passed to the import path.
      Mixing these up will overwrite document text with serialized HTML rather
      than the intended human‑readable string.

    - **Search limitations**: LibreOffice search descriptors do not match
      across paragraphs. Single-match tries LO findFirst first, then falls back
      to `_find_range_by_offset` (full-text scan with exotic-space normalization).
      `all_matches` uses offset scan only so NBSP/normal-space variants are not
      missed. See `_SPACE_NORMALIZE_MAP` comments for follow-up work.
    """

    name = "apply_document_content"
    description = "Insert or replace content. Use target='full_document' to replace the whole document. Use target='beginning', 'end', or 'selection' to insert at those positions. Use target='search' with old_content to find and replace text. "
    parameters = {
        "type": "object",
        "properties": {
            "content": {"type": "array", "items": {"type": "string"}, "description": ("List of HTML fragments or plain-text fragments (one per block); shape and math per system prompt (APPLY_DOCUMENT_CONTENT AND HTML). No Markdown.")},
            "target": {"type": "string", "enum": ["beginning", "end", "selection", "full_document", "search"], "description": "Where to apply the content."},
            "old_content": {"type": "string", "description": ("Text to find and replace with content if target = 'search'.")},
            "all_matches": {"type": "boolean", "description": "Replace all occurrences (true) or first only. Default false. Only for target='search'."},
        },
        "required": ["content"],
    }
    uno_services = ["com.sun.star.text.TextDocument"]
    tier = "core"
    is_mutation = True

    def execute(self, ctx, **kwargs):
        from . import format as format_support
        content = kwargs.get("content", "")
        old_content = kwargs.get("old_content")
        target = kwargs.get("target")

        if not target and old_content is not None:
            target = "search"
        if not target:
            return self._tool_error("Provide a target ('beginning', 'end', 'selection', 'full_document', 'search') or old_content for find-and-replace.")

        if target == "search" and old_content is None:
            return self._tool_error("target='search' requires old_content.")

        # Normalize content:
        # - If the model (or caller) serialized a list as a JSON string,
        #   parse it back to a real list first so commas/brackets do not
        #   become literal document text.
        if isinstance(content, str):
            stripped = content.strip()
            if stripped.startswith("[") and "<" in stripped:
                parsed = safe_json_loads(stripped)
                if isinstance(parsed, list):
                    content = parsed

        # Normalize list input to a single string for HTML import paths.
        if isinstance(content, list):
            _parts = [str(x) for x in content]
            _per_part_nl = [p.count("\n") for p in _parts]
            log.debug(
                "apply_document_content: list join n_parts=%d per_part_newline_counts=%s total_chars_before_join=%d",
                len(_parts),
                _per_part_nl[:20],  # cap log size
                sum(len(p) for p in _parts),
            )
            content = "\n".join(_parts)
            log.debug("apply_document_content: after join newline_count=%d has_math_tag=%s join_preview=%r", content.count("\n"), ("<math" in content.lower()), content[:500])
        # Detect markup BEFORE any HTML wrapping.
        use_preserve = isinstance(content, str) and not format_support.content_has_markup(content)

        if use_preserve and isinstance(content, str):
            _nl_before_esc = content.count("\n")
            content = content.replace("\\n", "\n").replace("\\t", "\t")
            _nl_after_esc = content.count("\n")
            if _nl_after_esc != _nl_before_esc:
                log.debug("apply_document_content: literal \\\\n/\\\\t escape expand (plain text) newline_count %d -> %d", _nl_before_esc, _nl_after_esc)

        raw_content = content

        config_svc = ctx.services.get("config")

        if target == "full_document":
            format_support.replace_full_document(ctx.doc, ctx.ctx, content, config_svc=config_svc)
            return {"status": "ok", "message": "Replaced entire document."}
        if target == "end":
            format_support.insert_content_at_position(ctx.doc, ctx.ctx, content, "end", config_svc=config_svc)
            return {"status": "ok", "message": "Inserted content at end."}
        if target == "selection":
            format_support.insert_content_at_position(ctx.doc, ctx.ctx, content, "selection", config_svc=config_svc)
            return {"status": "ok", "message": "Inserted content at selection."}
        if target == "beginning":
            format_support.insert_content_at_position(ctx.doc, ctx.ctx, content, "beginning", config_svc=config_svc)
            return {"status": "ok", "message": "Inserted content at beginning."}

        # target == "search" from here on
        old_stripped = str(old_content).strip()

        search_string = old_stripped
        if format_support.content_has_markup(search_string):
            search_string = format_support.html_to_plain_text(search_string, ctx.ctx, config_svc)
        # Normalize for literal find: single \n (e.g. from HTML wraps) -> space; \n\n -> \n. LO regex does not work across paragraphs.
        search_string = _normalize_search_string_for_find(search_string)
        if not search_string:
            return self._tool_error("old_content is empty after normalization.")
        doc = ctx.doc
        all_matches = kwargs.get("all_matches", False)
        # FOLLOW-UP: all_matches uses _find_all_ranges (body-only offset scan); nested
        # XText hits (e.g. multiple table cells) may be missed — see _find_all_ranges.
        if all_matches:
            ranges = _find_all_ranges(doc, search_string)
            count = 0
            # Replace from last to first so earlier character offsets stay valid after edits.
            for found in reversed(ranges):
                if use_preserve:
                    format_support.replace_preserving_format(doc, found, raw_content, ctx.ctx)
                else:
                    format_support.replace_single_range_with_content(doc, found, content, ctx.ctx, config_svc)
                count += 1
            msg = "Replaced %d occurrence(s)." % count
            if use_preserve and count > 0:
                msg += " (formatting preserved)"
            if count == 0:
                msg += " No matches found. Try a shorter substring."
            return {"status": "ok", "message": msg}
        found = _find_first_range(doc, search_string)
        if found is None:
            return {"status": "error", "message": "old_content not found in document. Try a shorter, unique substring."}
        if use_preserve:
            format_support.replace_preserving_format(doc, found, raw_content, ctx.ctx)
            return {"status": "ok", "message": "Replaced 1 occurrence (by old_content). (formatting preserved)"}
        format_support.replace_single_range_with_content(doc, found, content, ctx.ctx, config_svc)
        return {"status": "ok", "message": "Replaced 1 occurrence (by old_content)."}


# ------------------------------------------------------------------
# CloneHeadingBlock
# ------------------------------------------------------------------


class CloneHeadingBlock(ToolBaseDummy):
    """Clone an entire heading block (heading + all sub-headings + body)."""

    name = "clone_heading_block"
    intent = "edit"
    description = "Clone an entire heading block (heading + all sub-headings + body). The clone is inserted right after the original block."
    parameters = {"type": "object", "properties": {"locator": {"type": "string", "description": ("Locator of the heading to clone (e.g. 'bookmark:_mcp_abc123', 'heading_text:Introduction').")}, "paragraph_index": {"type": "integer", "description": "Paragraph index of the heading (0-based)."}}}
    uno_services = ["com.sun.star.text.TextDocument"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        from com.sun.star.text.ControlCharacter import PARAGRAPH_BREAK  # type: ignore

        para_index = _resolve_para_index(ctx, kwargs)
        if para_index is None:
            return self._tool_error("Provide locator or paragraph_index.")

        # Use writer_tree service to find the heading node and block size
        tree_svc = ctx.services.get("writer_tree")
        if tree_svc is None:
            return self._tool_error("writer_nav module not loaded; cannot resolve heading block.")

        tree = tree_svc.build_heading_tree(ctx.doc)
        node = tree_svc._find_node_by_para_index(tree, para_index)
        if node is None:
            return self._tool_error("No heading found at paragraph %d." % para_index)

        # Total paragraphs in the block: heading + body + all children
        total = 1 + tree_svc._count_all_children(node)

        # Collect elements for the block
        doc_text = ctx.doc.getText()
        enum = doc_text.createEnumeration()
        elements = []
        idx = 0
        while enum.hasMoreElements():
            el = enum.nextElement()
            if para_index <= idx < para_index + total:
                elements.append(el)
            if idx >= para_index + total - 1:
                break
            idx += 1

        if not elements:
            return self._tool_error("Could not collect heading block paragraphs.")

        # Insert duplicates after the last element of the block
        last = elements[-1]
        cursor = doc_text.createTextCursorByRange(last)
        cursor.gotoEndOfParagraph(False)

        for el in elements:
            txt = el.getString()
            sty = el.getPropertyValue("ParaStyleName")
            doc_text.insertControlCharacter(cursor, PARAGRAPH_BREAK, False)
            doc_text.insertString(cursor, txt, False)
            cursor.gotoStartOfParagraph(False)
            cursor.gotoEndOfParagraph(True)
            cursor.setPropertyValue("ParaStyleName", sty)
            cursor.gotoEndOfParagraph(False)

        return {"status": "ok", "message": "Cloned heading block '%s' (%d paragraphs)." % (node.get("text", ""), total), "heading_text": node.get("text", ""), "block_size": total}


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _resolve_para_index(ctx, kwargs):
    """Resolve locator or paragraph_index from tool kwargs.

    Returns an integer paragraph index, or None if neither is provided.
    """
    locator = kwargs.get("locator")
    para_index = kwargs.get("paragraph_index")

    if locator is not None and para_index is None:
        doc_svc = ctx.services.document
        resolved = doc_svc.resolve_locator(ctx.doc, locator)
        para_index = resolved.get("para_index")

    return para_index


def _resolve_style_name(doc, style_name):
    """Resolve a style name case-insensitively against the document styles."""
    try:
        families = doc.getStyleFamilies()
        para_styles = families.getByName("ParagraphStyles")
        if para_styles.hasByName(style_name):
            return style_name
        lower = style_name.lower()
        for name in para_styles.getElementNames():
            if name.lower() == lower:
                return name
    except Exception:
        pass
    return style_name


def _count_headings(nodes):
    """Recursively count heading nodes in a nested list."""
    count = 0
    for node in nodes:
        count += 1
        count += _count_headings(node.get("children", []))
    return count


def collect_document_stats(doc, doc_svc):
    """Character/word/paragraph/page/heading counts for a Writer document."""
    from plugin.doc.document_helpers import build_heading_tree

    try:
        text_obj = doc.getText()
        cursor = text_obj.createTextCursor()
        cursor.gotoStart(False)
        cursor.gotoEnd(True)
        full_text = cursor.getString()
        char_count = len(full_text)
        word_count = len(full_text.split())
    except Exception:
        char_count = doc_svc.get_document_length(doc)
        word_count = 0

    try:
        para_ranges = doc_svc.get_paragraph_ranges(doc)
        para_count = len(para_ranges)
    except Exception:
        para_count = 0

    try:
        tree = build_heading_tree(doc)
        heading_count = _count_headings(tree.get("children", []))
    except Exception:
        heading_count = 0

    page_count = 0
    try:
        page_count = doc_svc.get_page_count(doc)
    except Exception:
        try:
            vc = doc.getCurrentController().getViewCursor()
            vc.jumpToLastPage()
            page_count = vc.getPage()
        except Exception:
            pass

    return {"character_count": char_count, "word_count": word_count, "paragraph_count": para_count, "page_count": page_count, "heading_count": heading_count}
