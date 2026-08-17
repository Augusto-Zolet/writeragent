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
"""Writer shape drawing tools, bridging Draw's implementations."""

from ..specialized_base import ToolWriterShapeBase
from plugin.doc.visual_helpers import SHAPE_TOOL_UNO_SERVICES
from plugin.draw.shapes import UpsertShape as DrawUpsertShape
from plugin.draw.shapes import DeleteShape as DrawDeleteShape
from plugin.draw.shapes import GetDrawSummary as DrawGetDrawSummary
from plugin.draw.shapes import ConnectShapes as DrawConnectShapes
from plugin.draw.shapes import GroupShapes as DrawGroupShapes


# 1. Inherit from the Draw tool implementation.
# 2. Inherit from the specialized ToolWriterShapeBase to enforce Writer scoping.
# 3. Union services: same names as Draw tools; include Draw/Impress so registration
# order does not drop support for non-Writer documents.
_WRITER_DRAW_SHAPE_DOCS = list(SHAPE_TOOL_UNO_SERVICES)


class UpsertShape(DrawUpsertShape, ToolWriterShapeBase):
    name = "shape_upsert"
    uno_services = _WRITER_DRAW_SHAPE_DOCS
    # Specialized for all document types (use delegate_to_specialized_*_toolset(domain=shapes)).
    tier = "specialized"


class DeleteShape(DrawDeleteShape, ToolWriterShapeBase):
    name = "shape_delete"
    uno_services = _WRITER_DRAW_SHAPE_DOCS


class GetDrawSummary(DrawGetDrawSummary, ToolWriterShapeBase):
    name = "shape_summary"
    uno_services = _WRITER_DRAW_SHAPE_DOCS


class ConnectShapes(DrawConnectShapes, ToolWriterShapeBase):
    name = "shape_connect"
    uno_services = _WRITER_DRAW_SHAPE_DOCS


class GroupShapes(DrawGroupShapes, ToolWriterShapeBase):
    name = "shape_group"
    uno_services = _WRITER_DRAW_SHAPE_DOCS
