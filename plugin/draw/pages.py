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
"""Page/slide management tools for Draw/Impress documents."""

from plugin.framework.tool import ToolBase


class AddSlide(ToolBase):
    name = "add_slide"
    intent = "edit"
    description = "Inserts a new slide (page) at the specified index."
    parameters = {
        "type": "object",
        "properties": {
            "page_index": {"type": "integer", "description": "0-based index where to insert the new slide (defaults to appending at the end if omitted)"},
            "switch_to_new_slide": {"type": "boolean", "description": "Whether to switch the view to the new slide (default: true)"},
        },
        "required": [],
    }
    uno_services = ["com.sun.star.drawing.DrawingDocument", "com.sun.star.presentation.PresentationDocument"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        from plugin.draw.bridge import DrawBridge

        bridge = DrawBridge(ctx.doc)
        bridge.create_slide(kwargs.get("page_index"), switch=kwargs.get("switch_to_new_slide", True))
        
        # Resolve active index
        active_idx = bridge.get_active_page_index()
        
        return {"status": "ok", "message": "Slide added", "active_page_index": active_idx}


class DeleteSlide(ToolBase):
    name = "delete_slide"
    intent = "edit"
    description = "Deletes the slide (page) at the specified index."
    parameters = {"type": "object", "properties": {"page_index": {"type": "integer", "description": "0-based index of slide to delete"}}, "required": ["page_index"]}
    uno_services = ["com.sun.star.drawing.DrawingDocument", "com.sun.star.presentation.PresentationDocument"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        from plugin.draw.bridge import DrawBridge

        bridge = DrawBridge(ctx.doc)
        bridge.delete_slide(kwargs["page_index"])
        
        # Resolve active index
        active_idx = bridge.get_active_page_index()
        
        return {"status": "ok", "message": "Slide deleted", "active_page_index": active_idx}


class ReadSlideText(ToolBase):
    """Read all text content from a slide plus speaker notes."""

    name = "read_slide_text"
    description = "Read all text content from a slide (shapes text) and speaker notes. Returns structured text per shape."
    parameters = {"type": "object", "properties": {"page_index": {"type": "integer", "description": "0-based slide index (default: active slide)."}}, "required": []}
    uno_services = ["com.sun.star.drawing.DrawingDocument"]
    tier = "core"

    def execute(self, ctx, **kwargs):
        from plugin.draw.bridge import DrawBridge

        bridge = DrawBridge(ctx.doc)
        # Resolve page
        idx = kwargs.get("page_index")
        actual_idx = idx if idx is not None else ctx.active_page_index
        if actual_idx is None:
            actual_idx = bridge.get_active_page_index()

        try:
            page = bridge.get_pages().getByIndex(actual_idx)
        except Exception:
            return self._tool_error("Invalid page index: %s" % actual_idx)

        if page is None:
            return self._tool_error("No draw page available.")

        texts = []
        for i in range(page.getCount()):
            shape = page.getByIndex(i)
            try:
                txt = shape.getString()
                if txt and txt.strip():
                    entry = {"shape_index": i, "text": txt}
                    try:
                        entry["shape_name"] = shape.Name
                    except Exception:
                        pass
                    texts.append(entry)
            except Exception:
                pass

        # Speaker notes
        notes_text = ""
        try:
            notes_page = page.getNotesPage()
            if notes_page and notes_page.getCount() > 1:
                notes_shape = notes_page.getByIndex(1)
                notes_text = notes_shape.getString()
        except Exception:
            pass

        return {"status": "ok", "page_index": actual_idx, "texts": texts, "notes": notes_text}


class GetPresentationInfo(ToolBase):
    """Get presentation metadata."""

    name = "get_presentation_info"
    description = "Get presentation metadata: slide count, dimensions, master slide names, and whether it is an Impress document."
    parameters = {"type": "object", "properties": {}, "required": []}
    uno_services = ["com.sun.star.drawing.DrawingDocument"]
    tier = "core"

    def execute(self, ctx, **kwargs):
        doc = ctx.doc
        pages = doc.getDrawPages()
        count = pages.getCount()

        # Dimensions from first page
        width_mm = 0
        height_mm = 0
        if count > 0:
            p = pages.getByIndex(0)
            try:
                width_mm = p.Width // 100
                height_mm = p.Height // 100
            except Exception:
                pass

        # Master pages
        masters = []
        try:
            mp = doc.getMasterPages()
            for i in range(mp.getCount()):
                m = mp.getByIndex(i)
                masters.append(m.Name if hasattr(m, "Name") else "Master_%d" % i)
        except Exception:
            pass

        from plugin.draw.bridge import DrawBridge
        bridge = DrawBridge(doc)
        active_idx = ctx.active_page_index
        if active_idx is None:
            active_idx = bridge.get_active_page_index()
        is_impress = hasattr(doc, "getPresentation")

        return {"status": "ok", "slide_count": count, "width_mm": width_mm, "height_mm": height_mm, "master_slides": masters, "is_impress": is_impress, "active_page_index": active_idx}

class SetActivePage(ToolBase):
    name = "set_active_page"
    intent = "navigate"
    description = "Changes the currently active slide (page) in Draw/Impress."
    parameters = {"type": "object", "properties": {"page_index": {"type": "integer", "description": "0-based index of page to activate"}}, "required": ["page_index"]}
    uno_services = ["com.sun.star.drawing.DrawingDocument", "com.sun.star.presentation.PresentationDocument"]
    is_mutation = True

    def execute(self, ctx, **kwargs):
        from plugin.draw.bridge import DrawBridge

        bridge = DrawBridge(ctx.doc)
        pages = bridge.get_pages()
        idx = kwargs["page_index"]
        if idx < 0 or idx >= pages.getCount():
            return self._tool_error("Page index %d out of range." % idx)

        page = pages.getByIndex(idx)
        controller = ctx.doc.getCurrentController()
        if controller is not None and hasattr(controller, "setCurrentPage"):
            try:
                controller.setCurrentPage(page)
                return {"status": "ok", "message": "Active page changed to %d" % idx, "active_page_index": idx}
            except Exception as e:
                return self._tool_error("Failed to set active page: %s" % e)
        return self._tool_error("Document controller does not support switching pages.")
