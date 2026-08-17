# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Calc shape drawing tools, bridging Draw's implementations."""

import logging
from .base import ToolCalcShapeBase
from plugin.doc.visual_helpers import SHAPE_TOOL_UNO_SERVICES
from plugin.draw.shapes import UpsertShape as DrawUpsertShape
from plugin.draw.shapes import DeleteShape as DrawDeleteShape
from plugin.draw.shapes import GetDrawSummary as DrawGetDrawSummary
from plugin.draw.shapes import ConnectShapes as DrawConnectShapes
from plugin.draw.shapes import GroupShapes as DrawGroupShapes

log = logging.getLogger("writeragent.calc")

_CALC_DRAW_SHAPE_DOCS = list(SHAPE_TOOL_UNO_SERVICES)

class UpsertShape(DrawUpsertShape, ToolCalcShapeBase):
    name = "shape_upsert"
    uno_services = _CALC_DRAW_SHAPE_DOCS
    tier = "specialized"

class DeleteShape(DrawDeleteShape, ToolCalcShapeBase):
    name = "shape_delete"
    uno_services = _CALC_DRAW_SHAPE_DOCS

class GetDrawSummary(DrawGetDrawSummary, ToolCalcShapeBase):
    name = "shape_summary"
    uno_services = _CALC_DRAW_SHAPE_DOCS

class ConnectShapes(DrawConnectShapes, ToolCalcShapeBase):
    name = "shape_connect"
    uno_services = _CALC_DRAW_SHAPE_DOCS

class GroupShapes(DrawGroupShapes, ToolCalcShapeBase):
    name = "shape_group"
    uno_services = _CALC_DRAW_SHAPE_DOCS
