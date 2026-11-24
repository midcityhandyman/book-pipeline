import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from book_pipeline import cli
from book_pipeline.manuscript import load_manuscript
from book_pipeline.pdf import command_for, find_converter, html_to_pdf
from book_pipeline.print_html import render_print_html
from book_pipeline.validate import check_epub

SAMPLE = Path(__file__).resolve().parent.parent / "manuscript" / "sample.md"


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="book-pipeline-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


class PrintHtmlTests(unittest.TestCase):
    def test_page_css_and_structure(self):
        book = load_manuscript(SAMPLE)
        html = render_print_html(book)
        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("@page {\n  size: 5.5in 8.5in;", html)
        self.assertIn("content: counter(page)", html)
        self.assertIn("break-before: right", html)
        self.assertEqual(html.count('<section class="chapter"'), len(book.chapters))
        for chapter in book.chapters:
            self.assertIn(f'<a href="#{chapter.id}">', html)
            self.assertIn(f'id="{chapter.id}"', html)
        self.assertNotIn("http", html.split("</style>")[0])  # no remote fonts or assets


class PdfTests(TempDirCase):
    def test_none_and_missing_converters_skip(self):
        self.assertIsNone(find_converter({"BOOK_PDF_CONVERTER": "none"}))
        nothing = find_converter({}, which=lambda name: None, has_weasyprint=lambda: False)
        self.assertIsNone(nothing)
        result = html_to_pdf(self.tmp / "a.html", self.tmp / "a.pdf", finder=lambda env: None)
        self.assertEqual(result.status, "skipped")

    def test_detection_order_and_explicit_binary(self):
        which = lambda name: f"/usr/bin/{name}" if name in ("wkhtmltopdf", "chromium") else None
        self.assertEqual(find_converter({}, which=which, has_weasyprint=lambda: False), ("wkhtmltopdf", "/usr/bin/wkhtmltopdf"))
        env = {"BOOK_PDF_CONVERTER": "chromium", "BOOK_PDF_BINARY": "/opt/browser"}
        self.assertEqual(find_converter(env, which=lambda n: None, has_weasyprint=lambda: False), ("chromium", "/opt/browser"))
        with self.assertRaises(ValueError):
            find_converter({"BOOK_PDF_CONVERTER": "magic"})

    def test_built_and_failed_runs_with_a_fake_converter(self):
        html, pdf = self.tmp / "book.html", self.tmp / "book.pdf"
        html.write_text("<p>hi</p>", encoding="utf-8")
        calls = []

        def good(command, **kwargs):
            calls.append(command)
            pdf.write_bytes(b"%PDF-1.4 fake")
            return SimpleNamespace(returncode=0, stderr="")

        finder = lambda env: ("wkhtmltopdf", "fake-wk")
        result = html_to_pdf(html, pdf, runner=good, finder=finder)
        self.assertEqual((result.status, result.path), ("built", pdf.resolve()))
        self.assertEqual(calls[0], command_for("wkhtmltopdf", "fake-wk", html.resolve(), pdf.resolve()))
        self.assertTrue(all(Path(arg).is_absolute() for arg in calls[0][-2:]))

        pdf.unlink()
        bad = lambda command, **kwargs: SimpleNamespace(returncode=3, stderr="boom\nlast line")
        result = html_to_pdf(html, pdf, runner=bad, finder=finder)
        self.assertEqual(result.status, "failed")
        self.assertIn("last line", result.detail)

    def test_chromium_command_uses_a_file_uri(self):
        command = command_for("chromium", "browser", self.tmp / "b.html", self.tmp / "b.pdf")
        self.assertTrue(command[-1].startswith("file:"))
        self.assertIn("--headless", command)


class CliTests(TempDirCase):
    def run_cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(list(args))
        return code, out.getvalue()

    def test_one_command_build(self):
        code, text = self.run_cli("build", str(SAMPLE), "--out", str(self.tmp), "--no-pdf")
        self.assertEqual(code, 0, text)
        self.assertIn("Check     structure OK", text)
        self.assertIn("skipped: turned off with --no-pdf", text)
        epub = self.tmp / "the-lamp-at-greywater-point.epub"
        self.assertEqual(check_epub(epub), [])
        self.assertTrue((self.tmp / "the-lamp-at-greywater-point.print.html").is_file())
        self.assertEqual(self.run_cli("check", str(epub))[0], 0)

    def test_build_with_pdf_step_never_breaks_the_build(self):
        lines = []
        code = cli.build(SAMPLE, self.tmp, env={"BOOK_PDF_CONVERTER": "none"}, echo=lines.append)
        self.assertEqual(code, 0)
        self.assertTrue(lines[-1].startswith("PDF       skipped"))

    def test_errors_give_exit_codes(self):
        self.assertEqual(self.run_cli("build", str(self.tmp / "missing.md"), "--out", str(self.tmp))[0], 2)
        junk = self.tmp / "junk.epub"
        junk.write_text("no", encoding="utf-8")
        self.assertEqual(self.run_cli("check", str(junk))[0], 1)


if __name__ == "__main__":
    unittest.main()
