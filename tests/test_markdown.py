import unittest
from xml.etree import ElementTree as ET

from book_pipeline.frontmatter import ManuscriptError, split_front_matter
from book_pipeline.manuscript import parse_manuscript
from book_pipeline.markdown import render_inline, render_markdown


class FrontMatterTests(unittest.TestCase):
    def test_reads_pairs_quotes_and_lists(self):
        meta, body = split_front_matter(
            '---\ntitle: "A: Title"\nauthor: Anonymous\ntags: [one, two]\nnotes:\n  - first\n  - second\n---\n\nBody text\n'
        )
        self.assertEqual(meta["title"], "A: Title")
        self.assertEqual(meta["tags"], ["one", "two"])
        self.assertEqual(meta["notes"], ["first", "second"])
        self.assertEqual(body.strip(), "Body text")

    def test_no_header_returns_text_untouched(self):
        self.assertEqual(split_front_matter("# Only a chapter\n"), ({}, "# Only a chapter\n"))

    def test_unclosed_header_is_an_error(self):
        with self.assertRaises(ManuscriptError):
            split_front_matter("---\ntitle: Broken\n")

    def test_bad_line_is_an_error(self):
        with self.assertRaises(ManuscriptError):
            split_front_matter("---\nthis is not a pair\n---\n")


class MarkdownTests(unittest.TestCase):
    def assert_well_formed(self, fragment):
        ET.fromstring(f"<div>{fragment}</div>")

    def test_inline_markup(self):
        html = render_inline("A **bold** and *soft* word, `x < y`, and [a link](https://example.com/a?b=1&c=2).")
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn("<em>soft</em>", html)
        self.assertIn("<code>x &lt; y</code>", html)
        self.assertIn('<a href="https://example.com/a?b=1&amp;c=2">a link</a>', html)
        self.assert_well_formed(html)

    def test_text_is_escaped(self):
        html = render_markdown("Fish & chips <script>alert(1)</script>")
        self.assertEqual(html, "<p>Fish &amp; chips &lt;script&gt;alert(1)&lt;/script&gt;</p>")

    def test_blocks(self):
        source = (
            "First line\nsame paragraph.\n\n## Part\n\n> Quoted\\\n> again\n\n"
            "- one\n- two\n  continued\n\n1. alpha\n2. beta\n\n* * *\n\n```\n# not a heading & raw\n```\n"
        )
        html = render_markdown(source)
        self.assertIn("<p>First line\nsame paragraph.</p>", html)
        self.assertIn("<h2>Part</h2>", html)
        self.assertIn("<blockquote>\n<p>Quoted<br/>\nagain</p>\n</blockquote>", html)
        self.assertIn("<li>two continued</li>", html)
        self.assertIn("<ol>\n<li>alpha</li>\n<li>beta</li>\n</ol>", html)
        self.assertIn('<hr class="scene-break"/>', html)
        self.assertIn("<pre><code># not a heading &amp; raw</code></pre>", html)
        self.assert_well_formed(html)

    def test_emphasis_may_span_lines(self):
        self.assertEqual(render_markdown("*one\ntwo*"), "<p><em>one\ntwo</em></p>")


class ManuscriptTests(unittest.TestCase):
    def test_chapters_split_on_level_one_headings(self):
        book = parse_manuscript(
            "---\ntitle: Test Book\n---\nOpening note.\n\n# One\n\nText one.\n\n```\n# fenced\n```\n\n# Two\n\nText two.\n"
        )
        self.assertEqual([c.title for c in book.chapters], ["Preface", "One", "Two"])
        self.assertEqual(book.chapters[2].filename, "chapter-003.xhtml")
        self.assertEqual(book.author, "Anonymous")
        self.assertEqual(book.slug, "test-book")
        self.assertTrue(book.identifier.startswith("urn:uuid:"))
        self.assertEqual(book.identifier, parse_manuscript("---\ntitle: Test Book\n---\n# A\nb\n").identifier)

    def test_rejects_bad_metadata(self):
        for header in ("author: Nobody", "title: T\ndate: last week", "title: T\nlanguage: 12", "title: T\ntrim: big"):
            with self.subTest(header=header), self.assertRaises(ManuscriptError):
                parse_manuscript(f"---\n{header}\n---\n# One\n\nText.\n")

    def test_rejects_empty_body(self):
        with self.assertRaises(ManuscriptError):
            parse_manuscript("---\ntitle: Empty\n---\n\n")


if __name__ == "__main__":
    unittest.main()
