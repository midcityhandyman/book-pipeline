"""Structural checks for an EPUB file.

This is not a replacement for a full conformance checker. It covers the
rules that break reading systems most often: the mimetype entry, the
container pointer, package metadata, manifest and spine consistency, the
navigation document, and well formed XHTML.
"""
from __future__ import annotations

import posixpath
import re
import zipfile
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET

NS = {
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "x": "http://www.w3.org/1999/xhtml",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
}
EPUB_TYPE = "{http://www.idpf.org/2007/ops}type"
_MODIFIED = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _parse(archive: zipfile.ZipFile, name: str, problems: list[str]):
    try:
        return ET.fromstring(archive.read(name))
    except ET.ParseError as error:
        problems.append(f"{name}: not well formed XML ({error})")
        return None


def check_epub(path: str | Path) -> list[str]:
    """Return a list of problems. An empty list means the structure is sound."""
    problems: list[str] = []
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as error:
        return [f"not a readable zip archive: {error}"]

    with archive:
        infos = archive.infolist()
        names = {info.filename for info in infos}
        if not infos or infos[0].filename != "mimetype":
            problems.append("mimetype must be the first entry in the archive")
        if "mimetype" in names:
            info = archive.getinfo("mimetype")
            if info.compress_type != zipfile.ZIP_STORED:
                problems.append("mimetype must be stored without compression")
            if info.extra:
                problems.append("mimetype entry must not carry an extra field")
            if archive.read("mimetype") != b"application/epub+zip":
                problems.append("mimetype content must be exactly 'application/epub+zip'")
        else:
            problems.append("mimetype entry is missing")

        if "META-INF/container.xml" not in names:
            return problems + ["META-INF/container.xml is missing"]
        container = _parse(archive, "META-INF/container.xml", problems)
        rootfile = None if container is None else container.find("c:rootfiles/c:rootfile", NS)
        if rootfile is None or not rootfile.get("full-path"):
            return problems + ["container.xml names no rootfile"]
        opf_name = rootfile.get("full-path")
        if opf_name not in names:
            return problems + [f"package document {opf_name} is missing"]
        package = _parse(archive, opf_name, problems)
        if package is None:
            return problems
        base = posixpath.dirname(opf_name)

        # Metadata
        if package.get("version") != "3.0":
            problems.append("package version should be 3.0")
        uid_ref = package.get("unique-identifier")
        identifiers = {el.get("id"): (el.text or "").strip() for el in package.findall("opf:metadata/dc:identifier", NS)}
        if not uid_ref or not identifiers.get(uid_ref):
            problems.append("unique-identifier does not point at a non empty dc:identifier")
        for tag in ("title", "language"):
            element = package.find(f"opf:metadata/dc:{tag}", NS)
            if element is None or not (element.text or "").strip():
                problems.append(f"dc:{tag} is missing or empty")
        modified = [m.text or "" for m in package.findall("opf:metadata/opf:meta", NS) if m.get("property") == "dcterms:modified"]
        if len(modified) != 1 or not _MODIFIED.match(modified[0]):
            problems.append("exactly one dcterms:modified in CCYY-MM-DDThh:mm:ssZ form is required")

        # Manifest
        manifest: dict[str, str] = {}
        nav_items = []
        for item in package.findall("opf:manifest/opf:item", NS):
            item_id, href = item.get("id"), item.get("href")
            if not item_id or not href or not item.get("media-type"):
                problems.append("manifest item lacks id, href or media-type")
                continue
            if item_id in manifest:
                problems.append(f"duplicate manifest id {item_id}")
            target = posixpath.normpath(posixpath.join(base, unquote(href)))
            manifest[item_id] = target
            if target not in names:
                problems.append(f"manifest item {item_id} points at missing file {target}")
            if "nav" in (item.get("properties") or "").split():
                nav_items.append(target)
        listed = set(manifest.values()) | {"mimetype", opf_name}
        for name in sorted(names - listed):
            if not name.startswith("META-INF/") and not name.endswith("/"):
                problems.append(f"{name} is in the archive but not in the manifest")

        # Spine
        spine = package.find("opf:spine", NS)
        refs = [] if spine is None else [ref.get("idref") for ref in spine.findall("opf:itemref", NS)]
        if not refs:
            problems.append("spine is empty")
        for ref in refs:
            if ref not in manifest:
                problems.append(f"spine itemref {ref} is not in the manifest")
        toc_id = None if spine is None else spine.get("toc")
        if toc_id and toc_id not in manifest:
            problems.append(f"spine toc attribute {toc_id} is not in the manifest")

        # Content documents
        for item in package.findall("opf:manifest/opf:item", NS):
            target = manifest.get(item.get("id") or "")
            if item.get("media-type") == "application/xhtml+xml" and target in names:
                root = _parse(archive, target, problems)
                if root is not None and root.tag != f"{{{NS['x']}}}html":
                    problems.append(f"{target}: root element is not XHTML html")

        # Navigation
        if len(nav_items) != 1:
            problems.append("manifest must hold exactly one item with properties='nav'")
        elif nav_items[0] in names:
            nav_root = _parse(archive, nav_items[0], problems)
            toc = None
            if nav_root is not None:
                toc = next((n for n in nav_root.iter(f"{{{NS['x']}}}nav") if n.get(EPUB_TYPE) == "toc"), None)
            if nav_root is not None and toc is None:
                problems.append("navigation document has no nav element with epub:type='toc'")
            links = [] if toc is None else [a.get("href") or "" for a in toc.iter(f"{{{NS['x']}}}a")]
            if toc is not None and not links:
                problems.append("table of contents has no links")
            nav_base = posixpath.dirname(nav_items[0])
            for href in links:
                target = posixpath.normpath(posixpath.join(nav_base, unquote(href.split("#")[0])))
                if target not in manifest.values():
                    problems.append(f"contents link {href} does not resolve to a manifest item")

        # NCX, when present, must agree with the package identifier
        if toc_id in manifest and manifest[toc_id] in names:
            ncx = _parse(archive, manifest[toc_id], problems)
            if ncx is not None:
                uid = next((m.get("content") for m in ncx.findall("ncx:head/ncx:meta", NS) if m.get("name") == "dtb:uid"), None)
                if uid != identifiers.get(uid_ref or ""):
                    problems.append("toc.ncx dtb:uid does not match the package identifier")
    return problems


def describe_epub(path: str | Path) -> list[str]:
    """One line per archive entry, for build reports."""
    with zipfile.ZipFile(path) as archive:
        return [
            f"{info.filename:<28} {'stored' if info.compress_type == zipfile.ZIP_STORED else 'deflated':<8} {info.file_size:>6} bytes"
            for info in archive.infolist()
        ]
