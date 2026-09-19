# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for MathML HTML segmentation (no LibreOffice required)."""

import unittest

from plugin.writer.math.html_math_segment import (
    html_fragment_contains_mathml,
    html_fragment_contains_mixed_math,
    html_fragment_contains_tex_math,
    segment_html_with_mathml,
    segment_html_with_mixed_math,
)


class TestHtmlMathSegment(unittest.TestCase):
    def test_contains_mathml(self):
        self.assertFalse(html_fragment_contains_mathml(""))
        self.assertFalse(html_fragment_contains_mathml("hello"))
        self.assertTrue(html_fragment_contains_mathml("<math><mi>x</mi></math>"))
        self.assertTrue(html_fragment_contains_mathml("<MATH xmlns=...>"))

    def test_plain_html_single_segment(self):
        segs = segment_html_with_mathml("<p>hi</p>")
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0].kind, "html")
        self.assertEqual(segs[0].text, "<p>hi</p>")

    def test_order_mixed_inline(self):
        html = '<p>Before <math><mi>a</mi></math> after.</p>'
        segs = segment_html_with_mathml(html)
        self.assertEqual([s.kind for s in segs], ["html", "math", "html"])
        self.assertEqual(segs[0].text, "<p>Before ")
        self.assertTrue(segs[1].text.lower().startswith("<math"))
        self.assertTrue(segs[1].text.lower().endswith("</math>"))
        self.assertFalse(segs[1].display_block)
        self.assertEqual(segs[2].text, " after.</p>")

    def test_display_block_attribute(self):
        m = '<math display="block"><mi>x</mi></math>'
        segs = segment_html_with_mathml(m)
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0].kind, "math")
        self.assertTrue(segs[0].display_block)

    def test_mode_display_legacy(self):
        m = '<math mode="display"><mi>x</mi></math>'
        segs = segment_html_with_mathml(m)
        self.assertTrue(segs[0].display_block)

    def test_katex_wrapper_preserved(self):
        wrapped = (
            '<span class="katex">'
            '<math><semantics><mi>x</mi></semantics></math>'
            "</span>"
        )
        segs = segment_html_with_mathml(wrapped)
        kinds = [s.kind for s in segs]
        self.assertEqual(kinds, ["html", "math", "html"])
        self.assertIn("semantics", segs[1].text)

    def test_unclosed_math_becomes_html_tail(self):
        segs = segment_html_with_mathml("<p>a<math><mi>x</mi>")
        self.assertEqual([s.kind for s in segs], ["html", "html"])
        self.assertIn("<math", segs[1].text)

    def test_multiple_formulas(self):
        h = "<p><math><mi>a</mi></math>+<math><mi>b</mi></math></p>"
        segs = segment_html_with_mathml(h)
        self.assertEqual(segs[0].kind, "html")
        self.assertEqual(segs[1].kind, "math")
        self.assertEqual(segs[2].kind, "html")
        self.assertEqual(segs[3].kind, "math")
        self.assertEqual(segs[4].kind, "html")

    def test_contains_tex(self):
        self.assertFalse(html_fragment_contains_tex_math(""))
        self.assertFalse(html_fragment_contains_tex_math("no math"))
        self.assertTrue(html_fragment_contains_tex_math(r"$\alpha$"))
        self.assertTrue(html_fragment_contains_tex_math(r"$$\int$$"))
        self.assertTrue(html_fragment_contains_tex_math(r"\(x\)"))
        self.assertTrue(html_fragment_contains_tex_math(r"\[y\]"))
        self.assertFalse(html_fragment_contains_tex_math("$100 is a lot"))

    def test_mixed_math_contains_union(self):
        self.assertTrue(html_fragment_contains_mixed_math("<math></math>"))
        self.assertTrue(html_fragment_contains_mixed_math(r"$\pi$"))
        self.assertFalse(html_fragment_contains_mixed_math("<p>plain</p>"))

    def test_segment_tex_inline(self):
        segs = segment_html_with_mixed_math(r"<p>Hi \(x^2\) there</p>")
        self.assertEqual([s.kind for s in segs], ["html", "tex", "html"])
        self.assertEqual(segs[1].text, "x^2")
        self.assertFalse(segs[1].display_block)

    def test_segment_tex_display_brackets(self):
        segs = segment_html_with_mixed_math(r"pre \[a+b\] post")
        self.assertEqual([s.kind for s in segs], ["html", "tex", "html"])
        self.assertEqual(segs[1].text, "a+b")
        self.assertTrue(segs[1].display_block)

    def test_segment_tex_dollar_display(self):
        segs = segment_html_with_mixed_math(r"$$\frac{1}{2}$$")
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0].kind, "tex")
        self.assertIn("frac", segs[0].text)
        self.assertTrue(segs[0].display_block)

    def test_mathml_before_tex_in_stream(self):
        h = r'<math><mi>a</mi></math> then $\pi$'
        segs = segment_html_with_mixed_math(h)
        self.assertEqual([s.kind for s in segs], ["math", "html", "tex"])
        self.assertTrue(segs[0].text.lower().startswith("<math"))

    def test_currency_does_not_open_tex(self):
        """``R$ 1.234,56`` pairs must stay prose (issue: Writer inserted a formula)."""
        brl = (
            "<p>Requer a condena\u00e7\u00e3o em R$ 12.798,82, como montante "
            "indenizat\u00f3rio, evitando-se, assim, o enriquecimento, al\u00e9m "
            "de R$ 500,00 de custas.</p>"
        )
        self.assertFalse(html_fragment_contains_tex_math(brl))
        self.assertFalse(html_fragment_contains_mixed_math(brl))
        segs = segment_html_with_mixed_math(brl)
        self.assertEqual([s.kind for s in segs], ["html"])
        self.assertEqual(segs[0].text, brl)

    def test_currency_shapes_are_not_tex(self):
        for text in (
            "R$12.798,82 e R$500,00",
            "US$ 1,00 at\u00e9 US$ 9,00",
            "custa 100$ ou 200$",
            "total: $ 5,00 e $ 9,00",
            "$.50 e $.75",
        ):
            with self.subTest(text=text):
                self.assertFalse(html_fragment_contains_tex_math(text))
                self.assertEqual([s.kind for s in segment_html_with_mixed_math(text)], ["html"])

    def test_real_tex_still_segments_next_to_currency(self):
        h = "valor R$ 5,00 e a f\u00f3rmula $x^2$ aqui"
        self.assertTrue(html_fragment_contains_tex_math(h))
        segs = segment_html_with_mixed_math(h)
        self.assertEqual([s.kind for s in segs], ["html", "tex", "html"])
        self.assertEqual(segs[1].text, "x^2")

    def test_unclosed_dollar_is_not_tex(self):
        self.assertFalse(html_fragment_contains_tex_math(r"$\alpha with no close"))
        self.assertEqual(
            [s.kind for s in segment_html_with_mixed_math(r"$\alpha with no close")], ["html"]
        )

    def test_letter_prefixed_currency_can_close_an_open_run(self):
        """Closer is not ``_is_currency_dollar``: letter-prefixed ``R$`` can still close.

        Two currency amounts still cannot pair (those ``$`` never open). Reusing
        the opener helper on the closer would also reject ``$x$`` (``x`` is
        alphanumeric) and kill real inline math.
        """
        h = r"$\alpha with no close and R$ 500,00"
        self.assertTrue(html_fragment_contains_tex_math(h))
        segs = segment_html_with_mixed_math(h)
        self.assertEqual([s.kind for s in segs], ["tex", "html"])
        self.assertEqual(segs[0].text, r"\alpha with no close and R")
        self.assertEqual(segs[1].text, " 500,00")

        spaced = r"$\alpha with no close and $ 500"
        self.assertFalse(html_fragment_contains_tex_math(spaced))
        self.assertEqual(
            [s.kind for s in segment_html_with_mixed_math(spaced)], ["html"]
        )

    def test_tex_before_mathml(self):
        h = r'$\pi$<math><mi>x</mi></math>'
        segs = segment_html_with_mixed_math(h)
        self.assertEqual([s.kind for s in segs], ["tex", "math"])
        self.assertEqual(segs[0].text, r"\pi")


if __name__ == "__main__":
    unittest.main()
