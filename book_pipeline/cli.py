"""Command line entry point: `python -m book_pipeline build`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .epub import build_epub
from .frontmatter import ManuscriptError
from .manuscript import load_manuscript
from .pdf import PdfResult, html_to_pdf
from .print_html import build_print_html
from .validate import check_epub, describe_epub

DEFAULT_MANUSCRIPT = "manuscript/sample.md"


def build(manuscript: str | Path, out_dir: str | Path, pdf: bool = True, env=None, echo=print,
          to_pdf=html_to_pdf) -> int:
    """Run the whole pipeline. Returns a process exit code: 0 built, 1 the EPUB
    failed its check, 2 the manuscript could not be read, 3 the PDF converter failed."""
    out_dir = Path(out_dir)
    try:
        book = load_manuscript(manuscript)
    except ManuscriptError as error:
        echo(f"error: {error}")
        return 2

    echo(f"Book      {book.title} by {book.author} ({book.language}, {book.date})")
    echo(f"Chapters  {len(book.chapters)} ({book.words} words)")
    for chapter in book.chapters:
        echo(f"          {chapter.number}. {chapter.title} ({chapter.words} words)")

    epub_path = build_epub(book, out_dir / f"{book.slug}.epub")
    echo(f"EPUB      {epub_path.name}")
    for line in describe_epub(epub_path):
        echo(f"          {line}")
    problems = check_epub(epub_path)
    if problems:
        echo(f"Check     FAILED with {len(problems)} problem(s)")
        for problem in problems:
            echo(f"          - {problem}")
    else:
        echo("Check     structure OK")

    html_path = build_print_html(book, out_dir / f"{book.slug}.print.html")
    echo(f"Print     {html_path.name} (page size {book.trim})")

    if pdf:
        result = to_pdf(html_path, out_dir / f"{book.slug}.pdf", env=env)
    else:
        result = PdfResult("skipped", "turned off with --no-pdf")
    name = result.path.name + " " if result.path else ""
    echo(f"PDF       {name}{result.status}: {result.detail}")
    if problems:
        return 1
    # A missing converter is a skip; one that ran and broke must not look like success.
    return 3 if result.status == "failed" else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="book-pipeline", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    build_cmd = commands.add_parser("build", help="build EPUB, print HTML and optional PDF")
    build_cmd.add_argument("manuscript", nargs="?", default=DEFAULT_MANUSCRIPT)
    build_cmd.add_argument("--out", default="dist", help="output folder (default: dist)")
    build_cmd.add_argument("--no-pdf", action="store_true", help="skip the PDF step")

    check_cmd = commands.add_parser("check", help="check the structure of an EPUB file")
    check_cmd.add_argument("epub")

    args = parser.parse_args(argv)
    if args.command == "build":
        return build(args.manuscript, args.out, pdf=not args.no_pdf)
    problems = check_epub(args.epub)
    for problem in problems:
        print(f"- {problem}")
    print("structure OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
