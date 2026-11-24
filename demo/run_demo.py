"""Offline demo: build the sample book, inspect it, then break it on purpose.

Run from the repository root:  python demo/run_demo.py
The transcript is printed and also saved to demo/output.txt.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from book_pipeline.cli import build  # noqa: E402
from book_pipeline.validate import check_epub  # noqa: E402


def main() -> int:
    lines: list[str] = []
    say = lines.append
    work = Path(tempfile.mkdtemp(prefix="book-pipeline-demo-"))
    try:
        say("== 1. One command build (PDF converter set to none so the run is offline) ==")
        say("$ python -m book_pipeline build manuscript/sample.md --out dist")
        code = build(ROOT / "manuscript" / "sample.md", work, env={"BOOK_PDF_CONVERTER": "none"}, echo=say)
        say(f"exit code {code}")

        epub = work / "the-lamp-at-greywater-point.epub"
        say("")
        say("== 2. The package document inside the EPUB ==")
        with zipfile.ZipFile(epub) as archive:
            say(archive.read("OEBPS/content.opf").decode("utf-8").rstrip())

        say("")
        say("== 3. Page rules at the top of the print ready HTML ==")
        html = (work / "the-lamp-at-greywater-point.print.html").read_text(encoding="utf-8")
        start = html.index("@page")
        say(html[start:html.index("html {", start)].rstrip())

        say("")
        say("== 4. Damage the EPUB and run the checker again ==")
        broken = work / "broken.epub"
        with zipfile.ZipFile(epub) as src, zipfile.ZipFile(broken, "w", zipfile.ZIP_DEFLATED) as dst:
            for name in src.namelist():
                if name == "OEBPS/chapter-003.xhtml":
                    continue  # drop a chapter; mimetype also ends up compressed
                dst.writestr(name, src.read(name))
        say("$ python -m book_pipeline check broken.epub")
        problems = check_epub(broken)
        for problem in problems:
            say(f"- {problem}")
        say(f"{len(problems)} problem(s)")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    text = "\n".join(lines) + "\n"
    (ROOT / "demo" / "output.txt").write_text(text, encoding="utf-8", newline="\n")
    sys.stdout.write(text)
    return 0 if code == 0 and problems else 1


if __name__ == "__main__":
    sys.exit(main())
