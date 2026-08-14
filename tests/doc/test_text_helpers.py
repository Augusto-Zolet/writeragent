from plugin.doc.text_helpers import get_string_without_tracked_deletions, normalize_linebreaks


def test_normalize_linebreaks():
    assert normalize_linebreaks("hello\r\nworld") == "hello\nworld"
    assert normalize_linebreaks("hello\n\rworld") == "hello\nworld"
    assert normalize_linebreaks("hello\rworld") == "hello\nworld"
    assert normalize_linebreaks("Line 1\nLine 2") == "Line 1\nLine 2"
    assert normalize_linebreaks("Line 1\r\nLine 2") == "Line 1\nLine 2"
    assert normalize_linebreaks("Line 1\rLine 2") == "Line 1\nLine 2"
    assert normalize_linebreaks("Line 1\n\rLine 2") == "Line 1\nLine 2"
    assert normalize_linebreaks("A\r\nB\rC\n\rD\nE") == "A\nB\nC\nD\nE"
    assert normalize_linebreaks("\r\n\r\n") == "\n\n"
    assert normalize_linebreaks("\n\r\n\r") == "\n\n"
    assert normalize_linebreaks("\r\r") == "\n\n"
    assert normalize_linebreaks("") == ""
    assert normalize_linebreaks(None) == ""


class _Enum:
    def __init__(self, items):
        self._items = list(items)
        self._idx = 0

    def hasMoreElements(self):
        return self._idx < len(self._items)

    def nextElement(self):
        item = self._items[self._idx]
        self._idx += 1
        return item


class _Portion:
    def __init__(self, text="", portion_type="Text", redline_type=None):
        self._text = text
        self._portion_type = portion_type
        self._redline_type = redline_type

    def getPropertyValue(self, name):
        if name == "TextPortionType":
            return self._portion_type
        if name == "RedlineType":
            return self._redline_type
        raise Exception(name)

    def getString(self):
        return self._text


class _Paragraph:
    def __init__(self, portions, fallback_text=""):
        self._portions = portions
        self._fallback_text = fallback_text

    def createEnumeration(self):
        return _Enum(self._portions)

    def getString(self):
        return self._fallback_text


class _TextRange:
    def __init__(self, paragraphs, fallback_text=""):
        self._paragraphs = paragraphs
        self._fallback_text = fallback_text

    def createEnumeration(self):
        return _Enum(self._paragraphs)

    def getString(self):
        return self._fallback_text


def test_get_string_without_tracked_deletions_skips_deleted_portions():
    text_range = _TextRange(
        [
            _Paragraph(
                [
                    _Portion("Keep "),
                    _Portion(portion_type="Redline", redline_type="Delete"),
                    _Portion("remove me"),
                    _Portion(portion_type="Redline", redline_type="Delete"),
                    _Portion("text"),
                ],
                fallback_text="Keep remove metext",
            ),
            _Paragraph([_Portion("Next line")], fallback_text="Next line"),
        ],
        fallback_text="Keep remove metext\nNext line",
    )

    assert get_string_without_tracked_deletions(text_range) == "Keep text\nNext line"
