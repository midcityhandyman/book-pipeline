"""Write an EPUB 3 container with nothing but the standard library."""
from __future__ import annotations

import zipfile
from html import escape
from pathlib import Path

from .manuscript import Book

MIMETYPE = "application/epub+zip"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)  # constant timestamps make builds repeatable

EPUB_CSS = """\
body { font-family: serif; line-height: 1.5; margin: 5%; }
h1 { font-size: 1.6em; text-align: center; margin: 2em 0 1.5em; }
h2 { font-size: 1.2em; margin-top: 1.5em; }
p { margin: 0; text-indent: 1.4em; text-align: justify; }
h1 + p, h2 + p, hr + p, blockquote p { text-indent: 0; }
blockquote { margin: 1em 2em; font-style: italic; }
hr.scene-break { border: 0; text-align: center; margin: 1.2em 0; }
hr.scene-break:after { content: "* * *"; }
.title-page { text-align: center; margin-top: 30%; }
.title-page .author { margin-top: 2em; font-size: 1.2em; }
nav ol { list-style: none; padding: 0; }
"""

_CONTAINER = """\
<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def _page(book: Book, title: str, body: str) -> str:
    lang = escape(book.language)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        f'xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}" xml:lang="{lang}">\n'
        f'<head>\n<meta charset="utf-8"/>\n<title>{escape(title)}</title>\n'
        '<link rel="stylesheet" type="text/css" href="style.css"/>\n</head>\n'
        f"<body>\n{body}\n</body>\n</html>\n"
    )


def _title_page(book: Book) -> str:
    parts = [f"<h1>{escape(book.title)}</h1>"]
    if book.subtitle:
        parts.append(f'<p class="subtitle">{escape(book.subtitle)}</p>')
    parts.append(f'<p class="author">{escape(book.author)}</p>')
    if book.rights:
        parts.append(f'<p class="rights">{escape(book.rights)}</p>')
    return _page(book, book.title, '<section class="title-page">\n' + "\n".join(parts) + "\n</section>")


def _nav(book: Book) -> str:
    items = "\n".join(
        f'<li><a href="{c.filename}">{escape(c.title)}</a></li>' for c in book.chapters
    )
    body = f'<nav epub:type="toc" id="toc">\n<h1>Contents</h1>\n<ol>\n{items}\n</ol>\n</nav>'
    return _page(book, "Contents", body)


def _ncx(book: Book) -> str:
    points = "\n".join(
        f'    <navPoint id="{c.id}" playOrder="{c.number}">\n'
        f"      <navLabel><text>{escape(c.title)}</text></navLabel>\n"
        f'      <content src="{c.filename}"/>\n    </navPoint>'
        for c in book.chapters
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n  <head>\n'
        f'    <meta name="dtb:uid" content="{escape(book.identifier)}"/>\n'
        '    <meta name="dtb:depth" content="1"/>\n  </head>\n'
        f"  <docTitle><text>{escape(book.title)}</text></docTitle>\n"
        f"  <navMap>\n{points}\n  </navMap>\n</ncx>\n"
    )


def _opf(book: Book) -> str:
    meta = [
        f'<dc:identifier id="book-id">{escape(book.identifier)}</dc:identifier>',
        f"<dc:title>{escape(book.title)}</dc:title>",
        f"<dc:language>{escape(book.language)}</dc:language>",
        f"<dc:creator>{escape(book.author)}</dc:creator>",
        f"<dc:date>{escape(book.date)}</dc:date>",
    ]
    if book.description:
        meta.append(f"<dc:description>{escape(book.description)}</dc:description>")
    if book.rights:
        meta.append(f"<dc:rights>{escape(book.rights)}</dc:rights>")
    meta.append(f'<meta property="dcterms:modified">{book.modified}</meta>')

    xhtml = "application/xhtml+xml"
    manifest = [
        f'<item id="nav" href="nav.xhtml" media-type="{xhtml}" properties="nav"/>',
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        '<item id="css" href="style.css" media-type="text/css"/>',
        f'<item id="title-page" href="title.xhtml" media-type="{xhtml}"/>',
    ]
    manifest += [f'<item id="{c.id}" href="{c.filename}" media-type="{xhtml}"/>' for c in book.chapters]
    spine = ['<itemref idref="title-page"/>', '<itemref idref="nav"/>']
    spine += [f'<itemref idref="{c.id}"/>' for c in book.chapters]

    def block(lines: list[str]) -> str:
        return "\n".join("    " + line for line in lines)

    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        f'unique-identifier="book-id" xml:lang="{escape(book.language)}">\n'
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        f"{block(meta)}\n  </metadata>\n  <manifest>\n{block(manifest)}\n  </manifest>\n"
        f'  <spine toc="ncx">\n{block(spine)}\n  </spine>\n</package>\n'
    )


def epub_files(book: Book) -> list[tuple[str, str]]:
    """Every file in the container, in the order it is written."""
    files = [
        ("mimetype", MIMETYPE),
        ("META-INF/container.xml", _CONTAINER),
        ("OEBPS/content.opf", _opf(book)),
        ("OEBPS/nav.xhtml", _nav(book)),
        ("OEBPS/toc.ncx", _ncx(book)),
        ("OEBPS/style.css", EPUB_CSS),
        ("OEBPS/title.xhtml", _title_page(book)),
    ]
    for chapter in book.chapters:
        body = f'<section epub:type="chapter" id="{chapter.id}">\n<h1>{escape(chapter.title)}</h1>\n{chapter.html}\n</section>'
        files.append((f"OEBPS/{chapter.filename}", _page(book, chapter.title, body)))
    return files


def build_epub(book: Book, out_path: str | Path) -> Path:
    """Write the EPUB. The mimetype entry goes first and is stored uncompressed,
    which is what the container format requires."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w") as archive:
        for name, content in epub_files(book):
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content.encode("utf-8"))
    return out_path
