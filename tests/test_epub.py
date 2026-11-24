import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from book_pipeline.epub import build_epub
from book_pipeline.manuscript import load_manuscript
from book_pipeline.validate import NS, check_epub

SAMPLE = Path(__file__).resolve().parent.parent / "manuscript" / "sample.md"


def rewrite(source: Path, target: Path, edit=None, drop=(), stored_first=True, order=None):
    """Copy an EPUB while changing one thing, to prove the checker notices."""
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, "w") as dst:
        names = [n for n in src.namelist() if n not in drop]
        for name in order(names) if order else names:
            data = src.read(name)
            if edit:
                data = edit(name, data)
            kind = zipfile.ZIP_STORED if name == "mimetype" and stored_first else zipfile.ZIP_DEFLATED
            dst.writestr(zipfile.ZipInfo(name), data, compress_type=kind)
    return target


class EpubStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="book-pipeline-"))
        cls.book = load_manuscript(SAMPLE)
        cls.epub = build_epub(cls.book, cls.tmp / "sample.epub")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_sample_passes_every_check(self):
        self.assertEqual(check_epub(self.epub), [])

    def test_mimetype_is_first_stored_and_exact(self):
        with zipfile.ZipFile(self.epub) as archive:
            first = archive.infolist()[0]
            self.assertEqual(first.filename, "mimetype")
            self.assertEqual(first.compress_type, zipfile.ZIP_STORED)
            self.assertEqual(first.extra, b"")
            self.assertEqual(archive.read("mimetype"), b"application/epub+zip")
        # The raw bytes matter too: readers sniff the type at a fixed offset.
        raw = self.epub.read_bytes()
        self.assertEqual(raw[:4], b"PK\x03\x04")
        self.assertEqual(raw[30:58], b"mimetypeapplication/epub+zip")

    def test_container_points_at_package(self):
        with zipfile.ZipFile(self.epub) as archive:
            root = ET.fromstring(archive.read("META-INF/container.xml"))
            rootfile = root.find("c:rootfiles/c:rootfile", NS)
            self.assertEqual(rootfile.get("full-path"), "OEBPS/content.opf")
            self.assertEqual(rootfile.get("media-type"), "application/oebps-package+xml")

    def test_package_metadata_manifest_and_spine(self):
        with zipfile.ZipFile(self.epub) as archive:
            package = ET.fromstring(archive.read("OEBPS/content.opf"))
            names = set(archive.namelist())
        self.assertEqual(package.find("opf:metadata/dc:title", NS).text, "The Lamp at Greywater Point")
        self.assertEqual(package.find("opf:metadata/dc:language", NS).text, "en")
        self.assertEqual(package.find("opf:metadata/dc:identifier", NS).text, self.book.identifier)
        items = {i.get("id"): i for i in package.findall("opf:manifest/opf:item", NS)}
        for item in items.values():
            self.assertIn("OEBPS/" + item.get("href"), names)
        spine = [r.get("idref") for r in package.findall("opf:spine/opf:itemref", NS)]
        self.assertEqual(spine, ["title-page", "nav", "ch001", "ch002", "ch003", "ch004"])
        self.assertTrue(set(spine) <= set(items))
        self.assertEqual(items["nav"].get("properties"), "nav")

    def test_every_content_document_is_well_formed_xhtml(self):
        with zipfile.ZipFile(self.epub) as archive:
            pages = [n for n in archive.namelist() if n.endswith(".xhtml")]
            self.assertEqual(len(pages), 6)
            for name in pages:
                root = ET.fromstring(archive.read(name))
                self.assertEqual(root.tag, "{http://www.w3.org/1999/xhtml}html", name)

    def test_contents_lists_every_chapter_in_order(self):
        with zipfile.ZipFile(self.epub) as archive:
            nav = ET.fromstring(archive.read("OEBPS/nav.xhtml"))
            ncx = ET.fromstring(archive.read("OEBPS/toc.ncx"))
        links = [(a.get("href"), a.text) for a in nav.iter("{http://www.w3.org/1999/xhtml}a")]
        expected = [(c.filename, c.title) for c in self.book.chapters]
        self.assertEqual(links, expected)
        points = [p.find("ncx:content", NS).get("src") for p in ncx.findall("ncx:navMap/ncx:navPoint", NS)]
        self.assertEqual(points, [c.filename for c in self.book.chapters])

    def test_build_is_repeatable(self):
        again = build_epub(load_manuscript(SAMPLE), self.tmp / "again.epub")
        self.assertEqual(again.read_bytes(), self.epub.read_bytes())


class CheckerCatchesDamageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="book-pipeline-"))
        cls.epub = build_epub(load_manuscript(SAMPLE), cls.tmp / "good.epub")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def problems(self, **changes):
        return "\n".join(check_epub(rewrite(self.epub, self.tmp / "bad.epub", **changes)))

    def test_compressed_mimetype(self):
        self.assertIn("stored without compression", self.problems(stored_first=False))

    def test_mimetype_not_first(self):
        self.assertIn("first entry", self.problems(order=lambda names: names[1:] + names[:1]))

    def test_missing_chapter_file(self):
        self.assertIn("missing file OEBPS/chapter-002.xhtml", self.problems(drop=("OEBPS/chapter-002.xhtml",)))

    def test_broken_xhtml(self):
        def edit(name, data):
            return data.replace(b"</section>", b"") if name == "OEBPS/chapter-001.xhtml" else data
        self.assertIn("not well formed", self.problems(edit=edit))

    def test_spine_reference_without_manifest_item(self):
        def edit(name, data):
            return data.replace(b'<itemref idref="ch001"/>', b'<itemref idref="ghost"/>') if name.endswith(".opf") else data
        self.assertIn("itemref ghost", self.problems(edit=edit))

    def test_missing_title_and_nav(self):
        def edit(name, data):
            if name.endswith(".opf"):
                data = data.replace(b' properties="nav"', b"")
                data = data.replace(b"<dc:title>The Lamp at Greywater Point</dc:title>", b"")
            return data
        found = self.problems(edit=edit)
        self.assertIn("dc:title is missing", found)
        self.assertIn("exactly one item with properties='nav'", found)

    def test_unlisted_file_and_missing_container(self):
        def edit(name, data):
            return data.replace(b'<item id="css" href="style.css" media-type="text/css"/>', b"") if name.endswith(".opf") else data
        self.assertIn("OEBPS/style.css is in the archive but not in the manifest", self.problems(edit=edit))
        self.assertIn("container.xml is missing", self.problems(drop=("META-INF/container.xml",)))

    def test_not_a_zip(self):
        junk = self.tmp / "junk.epub"
        junk.write_text("plain text", encoding="utf-8")
        self.assertIn("not a readable zip", check_epub(junk)[0])


if __name__ == "__main__":
    unittest.main()
