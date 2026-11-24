"""Load a Markdown manuscript into a Book: metadata plus rendered chapters."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .frontmatter import ManuscriptError, split_front_matter
from .markdown import render_markdown

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LANG = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
_TRIM = re.compile(r"^\d+(\.\d+)?(in|mm|cm)\s+\d+(\.\d+)?(in|mm|cm)$")
_FENCE = re.compile(r"^\s{0,3}(```|~~~)")
_CHAPTER = re.compile(r"^#\s+(.+?)\s*#*\s*$")
# Characters XML 1.0 forbids; word processors leave them behind (form feeds and the like).
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# A word is a run of letters or digits in any script, with inner apostrophes.
_WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")


@dataclass
class Chapter:
    number: int
    title: str
    html: str
    words: int

    @property
    def id(self) -> str:
        return f"ch{self.number:03d}"

    @property
    def filename(self) -> str:
        return f"chapter-{self.number:03d}.xhtml"


@dataclass
class Book:
    title: str
    author: str = "Anonymous"
    language: str = "en"
    date: str = "2000-01-01"
    identifier: str = ""
    description: str = ""
    rights: str = ""
    subtitle: str = ""
    trim: str = "5.5in 8.5in"
    chapters: list[Chapter] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-") or "book"

    @property
    def modified(self) -> str:
        return f"{self.date}T00:00:00Z"

    @property
    def words(self) -> int:
        return sum(chapter.words for chapter in self.chapters)


def _split_chapters(body: str) -> list[tuple[str, str]]:
    """Split on level one headings, ignoring any that sit inside a code fence."""
    chapters: list[tuple[str, list[str]]] = []
    preface: list[str] = []
    fence = None  # the marker that opened the current code fence, if any
    for line in body.splitlines():
        marker = _FENCE.match(line)
        if fence is None and marker:
            fence = marker.group(1)
        elif fence and line.strip().startswith(fence):
            fence = None  # only the same marker closes it, as in markdown.py
        heading = None if fence else _CHAPTER.match(line)
        if heading:
            chapters.append((heading.group(1), []))
        elif chapters:
            chapters[-1][1].append(line)
        else:
            preface.append(line)
    if any(line.strip() for line in preface):
        chapters.insert(0, ("Preface", preface))
    return [(title, "\n".join(lines)) for title, lines in chapters]


def parse_manuscript(text: str) -> Book:
    meta, body = split_front_matter(_CONTROL.sub("", text))
    title = str(meta.get("title", "")).strip()
    if not title:
        raise ManuscriptError("front matter must give a title")

    def text_field(key: str, default: str = "") -> str:
        value = meta.get(key, default)
        return ", ".join(value) if isinstance(value, list) else str(value).strip()

    book = Book(title=title)
    book.author = text_field("author", book.author) or "Anonymous"
    book.language = text_field("language", book.language)
    book.date = text_field("date", book.date)
    book.description = text_field("description")
    book.rights = text_field("rights")
    book.subtitle = text_field("subtitle")
    book.trim = text_field("trim", book.trim)
    if not _LANG.match(book.language):
        raise ManuscriptError(f"language {book.language!r} is not a language tag like 'en'")
    if not _DATE.match(book.date):
        raise ManuscriptError(f"date {book.date!r} must look like YYYY-MM-DD")
    if not _TRIM.match(book.trim):
        raise ManuscriptError(f"trim {book.trim!r} must look like '5.5in 8.5in'")

    # A stable identifier keeps rebuilds of the same book byte comparable.
    book.identifier = text_field("identifier") or "urn:uuid:" + str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"book-pipeline:{book.title}:{book.author}")
    )

    for number, (chapter_title, source) in enumerate(_split_chapters(body), 1):
        words = len(_WORD.findall(source))
        book.chapters.append(Chapter(number, chapter_title, render_markdown(source), words))
    if not book.chapters:
        raise ManuscriptError("manuscript has no content; add a '# Chapter' heading and text")
    return book


def load_manuscript(path: str | Path) -> Book:
    path = Path(path)
    if not path.is_file():
        raise ManuscriptError(f"manuscript not found: {path}")
    return parse_manuscript(path.read_text(encoding="utf-8"))
