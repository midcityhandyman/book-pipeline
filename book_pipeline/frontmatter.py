"""A small front matter reader.

Supports the subset of YAML that a manuscript header needs: `key: value`
pairs, quoted strings, inline lists (`[a, b]`) and dash lists on the
following lines. It is deliberately not a full YAML parser.
"""
from __future__ import annotations

import re


class ManuscriptError(ValueError):
    """Raised when a manuscript cannot be turned into a book."""


_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$")
_ITEM = re.compile(r"^\s*-\s+(.*)$")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def split_front_matter(text: str) -> tuple[dict, str]:
    """Return (metadata, body). A manuscript without a header gives ({}, text)."""
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        raise ManuscriptError("front matter opens with '---' but never closes") from None

    meta: dict = {}
    current = None
    for number, line in enumerate(lines[1:end], 2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = _ITEM.match(line)
        if item and current is not None and isinstance(meta[current], list):
            meta[current].append(_unquote(item.group(1)))
            continue
        pair = _KEY.match(line)
        if not pair:
            raise ManuscriptError(f"front matter line {number} is not 'key: value': {line!r}")
        key, value = pair.group(1).lower(), pair.group(2).strip()
        if value == "":
            meta[key] = []
        elif value.startswith("[") and value.endswith("]"):
            meta[key] = [_unquote(v) for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key] = _unquote(value)
        current = key
    for key, value in list(meta.items()):
        if value == []:
            meta[key] = ""
    return meta, "\n".join(lines[end + 1:])
