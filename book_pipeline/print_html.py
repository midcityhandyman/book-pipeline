"""Render the whole book as one HTML file styled for paged media.

Any CSS paged media engine (or a browser's print dialog) can turn this
file into a print PDF: trim size, margins, running page numbers and
chapter openings all come from the @page rules below.
"""
from __future__ import annotations

from html import escape
from pathlib import Path

from .manuscript import Book

PRINT_CSS = """\
@page {
  size: %(trim)s;
  margin: 0.75in 0.625in 0.875in;
  @bottom-center { content: counter(page); font-size: 9pt; }
}
@page :left { margin-right: 0.75in; }
@page :right { margin-left: 0.75in; }
@page front { @bottom-center { content: none; } }
html { font-family: Georgia, "Times New Roman", serif; font-size: 11pt; line-height: 1.45; }
body { margin: 0; }
.title-page, .contents { page: front; break-after: page; page-break-after: always; }
.title-page { text-align: center; padding-top: 2.5in; }
.title-page h1 { font-size: 24pt; margin: 0 0 0.25in; }
.title-page .author { margin-top: 1in; font-size: 14pt; }
.title-page .rights { margin-top: 2in; font-size: 8pt; }
.contents ol { list-style: none; padding: 0; }
.contents a { color: inherit; text-decoration: none; }
.contents a::after { content: leader(".") target-counter(attr(href), page); }
.chapter { break-before: right; page-break-before: right; }
.chapter h1 { font-size: 18pt; text-align: center; margin: 1.5in 0 0.5in; }
h2 { font-size: 12pt; break-after: avoid; }
p { margin: 0; text-indent: 1.4em; text-align: justify; orphans: 2; widows: 2; hyphens: auto; }
h1 + p, h2 + p, hr + p, blockquote p { text-indent: 0; }
blockquote { margin: 1em 2em; font-style: italic; }
pre { font-size: 9pt; white-space: pre-wrap; }
hr.scene-break { border: 0; text-align: center; margin: 1em 0; }
hr.scene-break::after { content: "* * *"; }
@media screen { body { max-width: 34em; margin: 2em auto; padding: 0 1em; } }
"""


def render_print_html(book: Book) -> str:
    toc = "\n".join(f'<li><a href="#{c.id}">{escape(c.title)}</a></li>' for c in book.chapters)
    title = [f"<h1>{escape(book.title)}</h1>"]
    if book.subtitle:
        title.append(f'<p class="subtitle">{escape(book.subtitle)}</p>')
    title.append(f'<p class="author">{escape(book.author)}</p>')
    if book.rights:
        title.append(f'<p class="rights">{escape(book.rights)}</p>')
    chapters = "\n".join(
        f'<section class="chapter" id="{c.id}">\n<h1>{escape(c.title)}</h1>\n{c.html}\n</section>'
        for c in book.chapters
    )
    css = PRINT_CSS % {"trim": book.trim}
    return (
        f'<!DOCTYPE html>\n<html lang="{escape(book.language)}">\n<head>\n<meta charset="utf-8"/>\n'
        f"<title>{escape(book.title)}</title>\n"
        f'<meta name="author" content="{escape(book.author)}"/>\n'
        f"<style>\n{css}</style>\n</head>\n<body>\n"
        '<section class="title-page">\n' + "\n".join(title) + "\n</section>\n"
        f'<nav class="contents">\n<h2>Contents</h2>\n<ol>\n{toc}\n</ol>\n</nav>\n'
        f"{chapters}\n</body>\n</html>\n"
    )


def build_print_html(book: Book, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_print_html(book), encoding="utf-8", newline="\n")
    return out_path
