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
"""Structural tools: section_list, nav_goto_page, get_page_objects, section_read, bookmark_resolve.

(Index refresh, field refresh, and bookmark list/cleanup live in specialized domains.)"""

from plugin.framework.prompts import PARAGRAPH_INDEX_DIRECTIVE
from plugin.framework.tool import ToolBase, ToolBaseDummy

from .specialized_base import ToolWriterStructuralBase


class SectionList(ToolWriterStructuralBase):
    name = "section_list"
    intent = "navigate"
    description = "List all named sections in the document."
    parameters = {"type": "object", "properties": {}, "required": []}
    uno_services = ["com.sun.star.text.TextDocument"]

    def execute(self, ctx, **kwargs):
        doc = ctx.doc
        if not hasattr(doc, "getTextSections"):
            return {"status": "ok", "sections": [], "count": 0}
        supplier = doc.getTextSections()
        names = supplier.getElementNames()
        sections = []
        for name in names:
            section = supplier.getByName(name)
            sections.append({"name": name, "is_visible": getattr(section, "IsVisible", True), "is_protected": getattr(section, "IsProtected", False)})
        return {"status": "ok", "sections": sections, "count": len(sections)}


class NavGotoPage(ToolWriterStructuralBase):
    name = "nav_goto_page"
    intent = "navigate"
    is_mutation = False
    description = "Navigate the view cursor to a specific page."
    parameters = {"type": "object", "properties": {"page": {"type": "integer", "description": "Page number to navigate to"}}, "required": ["page"]}
    uno_services = ["com.sun.star.text.TextDocument"]

    def execute(self, ctx, **kwargs):
        controller = ctx.doc.getCurrentController()
        vc = controller.getViewCursor()
        vc.jumpToPage(kwargs["page"])
        return {"status": "ok", "page": vc.getPage()}


class GetPageObjects(ToolBase):
    name = "get_page_objects"
    intent = "read"
    description = (
        "Get images, tables, frames, and Draw shapes visible on a specific physical page. Provide "
        "page number, locator, or paragraph. " + PARAGRAPH_INDEX_DIRECTIVE
    )
    parameters = {
        "type": "object",
        "properties": {"page": {"type": "integer", "description": "1-based page number to analyze"}, "locator": {"type": "string", "description": "Locator to determine page"}, "paragraph": {"type": "integer", "description": "Paragraph index to determine page"}},
        "required": [],
    }
    uno_services = ["com.sun.star.text.TextDocument"]
    tier = "core"

    def execute(self, ctx, **kwargs):
        doc = ctx.doc
        doc_svc = ctx.services.document
        page = kwargs.get("page")

        if page is None:
            locator = kwargs.get("locator")
            para_idx = kwargs.get("paragraph")
            if locator:
                try:
                    resolved = doc_svc.resolve_locator(doc, locator)
                    para_idx = resolved.get("para_index", 0)
                except ValueError as e:
                    return self._tool_error(str(e))
            if para_idx is not None:
                page = doc_svc.get_page_for_paragraph(doc, para_idx)
            else:
                try:
                    page = doc.getCurrentController().getViewCursor().getPage()
                except Exception:
                    page = 1

        controller = doc.getCurrentController()
        vc = controller.getViewCursor()
        saved = None
        try:
            saved = doc.getText().createTextCursorByRange(vc.getStart())
        except Exception:
            pass

        doc.lockControllers()
        try:
            objects = self._scan_page(ctx, doc, vc, page)
        finally:
            if saved is not None:
                vc.gotoRange(saved, False)
            doc.unlockControllers()
        return {"status": "ok", "page": page, **objects}

    def _scan_page(self, ctx, doc, vc, page):
        images = []
        if hasattr(doc, "getGraphicObjects"):
            for name in doc.getGraphicObjects().getElementNames():
                try:
                    g = doc.getGraphicObjects().getByName(name)
                    vc.gotoRange(g.getAnchor(), False)
                    if vc.getPage() == page:
                        size = g.getPropertyValue("Size")
                        images.append({"name": name, "width_mm": size.Width // 100, "height_mm": size.Height // 100, "title": g.getPropertyValue("Title")})
                except Exception:
                    pass

        tables = []
        if hasattr(doc, "getTextTables"):
            for name in doc.getTextTables().getElementNames():
                try:
                    t = doc.getTextTables().getByName(name)
                    vc.gotoRange(t.getAnchor(), False)
                    if vc.getPage() == page:
                        tables.append({"name": name, "rows": t.getRows().getCount(), "cols": t.getColumns().getCount()})
                except Exception:
                    pass

        frames = []
        if hasattr(doc, "getTextFrames"):
            for fname in doc.getTextFrames().getElementNames():
                try:
                    fr = doc.getTextFrames().getByName(fname)
                    vc.gotoRange(fr.getAnchor(), False)
                    if vc.getPage() == page:
                        size = fr.getPropertyValue("Size")
                        frames.append({"name": fname, "width_mm": size.Width // 100, "height_mm": size.Height // 100})
                except Exception:
                    pass

        shapes = []
        if hasattr(doc, "getDrawPage"):
            draw_page = doc.getDrawPage()
            from com.sun.star.text.TextContentAnchorType import AT_PAGE, AT_PARAGRAPH, AT_CHARACTER, AS_CHARACTER

            doc_svc = ctx.services.document
            para_ranges = doc_svc.get_paragraph_ranges(doc)
            text_obj = doc.getText()

            # Find starting and ending paragraphs for the physical page
            if vc.jumpToPage(page):
                vc.jumpToStartOfPage()
                page_start = text_obj.createTextCursorByRange(vc.getStart())
                vc.jumpToEndOfPage()
                page_end = text_obj.createTextCursorByRange(vc.getEnd())

                start_idx = doc_svc.find_paragraph_for_range(page_start.getStart(), para_ranges, text_obj)
                end_idx = doc_svc.find_paragraph_for_range(page_end.getEnd(), para_ranges, text_obj)

                for i in range(draw_page.getCount()):
                    shape = draw_page.getByIndex(i)
                    include_shape = False
                    anchor = shape.getAnchor()

                    try:
                        anchor_type = shape.getPropertyValue("AnchorType")

                        if anchor_type == AT_PAGE:
                            shape_page_no = shape.getPropertyValue("AnchorPageNo")
                            if shape_page_no == page:
                                include_shape = True
                        elif anchor_type in (AT_PARAGRAPH, AT_CHARACTER, AS_CHARACTER) and anchor:
                            shape_para_idx = doc_svc.find_paragraph_for_range(anchor.getStart(), para_ranges, text_obj)
                            if start_idx <= shape_para_idx <= end_idx:
                                include_shape = True
                    except Exception:
                        pass

                    if include_shape:
                        shape_type = shape.getShapeType().replace("com.sun.star.drawing.", "")
                        shape_info = {"type": shape_type, "name": getattr(shape, "Name", ""), "text": shape.getString().strip() if hasattr(shape, "getString") else ""}
                        try:
                            pos = shape.getPosition()
                            size = shape.getSize()
                            shape_info["geometry"] = {"x": pos.X, "y": pos.Y, "width": size.Width, "height": size.Height}
                        except Exception:
                            pass
                        shapes.append(shape_info)

        return {"images": images, "tables": tables, "frames": frames, "shapes": shapes}


class SectionRead(ToolWriterStructuralBase):
    """Read the content of a named text section."""

    name = "section_read"
    intent = "navigate"
    description = "Read the text content of a named section. Returns the full text within the section boundaries."
    parameters = {"type": "object", "properties": {"section": {"type": "string", "description": "Name of the section to read."}}, "required": ["section"]}
    uno_services = ["com.sun.star.text.TextDocument"]

    def execute(self, ctx, **kwargs):
        section_name = kwargs.get("section", "")
        if not section_name:
            return self._tool_error("section is required.")

        doc = ctx.doc
        if not hasattr(doc, "getTextSections"):
            return self._tool_error("Document does not support sections.")

        sections = doc.getTextSections()
        if not sections.hasByName(section_name):
            available = list(sections.getElementNames())
            return self._tool_error("Section '%s' not found." % section_name, available=available)

        section = sections.getByName(section_name)
        anchor = section.getAnchor()

        # Extract paragraphs within the section
        enum = anchor.createEnumeration()
        paragraphs = []
        while enum.hasMoreElements():
            para = enum.nextElement()
            if para.supportsService("com.sun.star.text.Paragraph"):
                paragraphs.append(para.getString())
            else:
                paragraphs.append("[Table]")

        content = "\n".join(paragraphs)
        return {"status": "ok", "section": section_name, "section_name": section_name, "paragraphs": paragraphs, "content": content, "length": len(content)}


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

