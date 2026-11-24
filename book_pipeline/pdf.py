"""Optional PDF step. Uses whichever HTML to PDF converter is installed.

Nothing here is required: with no converter the step reports "skipped"
and the build still succeeds. Set BOOK_PDF_CONVERTER to pick one, and
BOOK_PDF_BINARY to point at an executable that is not on PATH.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

CHROMIUM_NAMES = ("chromium", "chromium-browser", "google-chrome", "chrome", "msedge")
CHOICES = ("auto", "none", "weasyprint", "wkhtmltopdf", "chromium")


@dataclass
class PdfResult:
    status: str  # "built", "skipped" or "failed"
    detail: str
    path: Path | None = None


def _has_weasyprint() -> bool:
    return importlib.util.find_spec("weasyprint") is not None


def find_converter(env=None, which=shutil.which, has_weasyprint=_has_weasyprint):
    """Return (name, executable) for the converter to use, or None."""
    env = os.environ if env is None else env
    choice = (env.get("BOOK_PDF_CONVERTER") or "auto").strip().lower()
    binary = (env.get("BOOK_PDF_BINARY") or "").strip()
    if choice not in CHOICES:
        raise ValueError(f"BOOK_PDF_CONVERTER must be one of {', '.join(CHOICES)}; got {choice!r}")
    if choice == "none":
        return None
    if choice in ("auto", "weasyprint") and has_weasyprint():
        return ("weasyprint", sys.executable)
    if choice in ("auto", "wkhtmltopdf"):
        found = (binary if choice == "wkhtmltopdf" and binary else None) or which("wkhtmltopdf")
        if found:
            return ("wkhtmltopdf", found)
    if choice in ("auto", "chromium"):
        found = (binary if choice == "chromium" and binary else None) or next(
            (which(name) for name in CHROMIUM_NAMES if which(name)), None
        )
        if found:
            return ("chromium", found)
    return None


def command_for(name: str, executable: str, html: Path, pdf: Path) -> list[str]:
    if name == "weasyprint":
        return [executable, "-m", "weasyprint", str(html), str(pdf)]
    if name == "wkhtmltopdf":
        return [executable, "--enable-local-file-access", str(html), str(pdf)]
    return [
        executable, "--headless", "--disable-gpu", "--no-pdf-header-footer",
        f"--print-to-pdf={pdf}", html.resolve().as_uri(),
    ]


def html_to_pdf(html: str | Path, pdf: str | Path, env=None, runner=subprocess.run, finder=find_converter) -> PdfResult:
    # Converters run in their own working directory, so hand them absolute paths.
    html, pdf = Path(html).resolve(), Path(pdf).resolve()
    try:
        converter = finder(env)
    except ValueError as error:
        return PdfResult("failed", str(error))
    if converter is None:
        choice = ((os.environ if env is None else env).get("BOOK_PDF_CONVERTER") or "auto").strip().lower()
        if choice == "none":
            return PdfResult("skipped", "BOOK_PDF_CONVERTER is none")
        looked = "weasyprint, wkhtmltopdf, chromium" if choice == "auto" else choice
        return PdfResult("skipped", f"no converter found (looked for {looked})")
    name, executable = converter
    try:
        done = runner(command_for(name, executable, html, pdf), capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as error:
        return PdfResult("failed", f"{name} could not run: {error}")
    if done.returncode != 0 or not pdf.is_file() or pdf.stat().st_size == 0:
        tail = (done.stderr or "").strip().splitlines()[-1:] or ["no output file"]
        return PdfResult("failed", f"{name} exited {done.returncode}: {tail[0]}")
    return PdfResult("built", f"via {name}", pdf)
