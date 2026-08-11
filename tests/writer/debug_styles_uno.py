# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
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
from plugin.testing_runner import native_test
from plugin.writer.styles import StyleGetInfo
from plugin.tests.testing_utils import TestingFactory, with_native_doc


@native_test
@with_native_doc("writer")
def test_inspect_heading1_properties(ctx, doc):
    tool_ctx = TestingFactory.create_context(doc=doc, ctx=ctx, env="native")

    tool = StyleGetInfo()
    res = tool.execute(tool_ctx, style_name="Heading 1", family="ParagraphStyles")

    # Print all keys to find the parent style property
    print("STYLE PROPERTIES:", list(res.get("properties", {}).keys()))
    if "ParentStyle" in res.get("properties", {}):
        print("Found ParentStyle:", res["properties"]["ParentStyle"])
    elif "ParentStyleName" in res.get("properties", {}):
        print("Found ParentStyleName:", res["properties"]["ParentStyleName"])

    # Also check the object directly
    style = doc.getStyleFamilies().getByName("ParagraphStyles").getByName("Heading 1")
    print("HAS ParentStyle:", hasattr(style, "ParentStyle"))
    try:
        print("ParentStyle value:", style.ParentStyle)
    except Exception as e:
        print("ParentStyle error:", e)
