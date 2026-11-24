"""A compact Markdown to XHTML converter.

Covers what prose manuscripts use: headings, paragraphs, hard line breaks,
emphasis, links, block quotes, lists, fenced code and scene breaks. The
output is always well formed XML so it can go straight into an EPUB.
"""
from __future__ import annotations

import re
from html import escape

_FENCE = re.compile(r"^\s{0,3}(```|~~~)")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_BULLET = re.compile(r"^\s{0,3}[-*+]\s+(.*)$")
_NUMBER = re.compile(r"^\s{0,3}(\d+)[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s{0,3}>\s?(.*)$")

_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_STRONG = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S)
_EM_STAR = re.compile(r"\*(?=\S)(.+?)(?<=\S)\*", re.S)
_EM_UNDER = re.compile(r"(?<!\w)_(?=\S)(.+?)(?<=\S)_(?!\w)", re.S)


def render_inline(text: str) -> str:
    """Render inline Markdown. Everything that is not markup is escaped."""
    out = []
    for index, part in enumerate(re.split(r"(`[^`]+`)", text)):
        if index % 2:
            out.append(f"<code>{escape(part[1:-1])}</code>")
            continue
        # Links are set aside while emphasis runs, so a URL holding _ or *
        # is never rewritten into markup inside the href attribute.
        links: list[str] = []

        def stash(match: re.Match) -> str:
            links.append(f'<a href="{match.group(2)}">{_emphasis(match.group(1))}</a>')
            return f"\x01{len(links) - 1}\x01"

        part = _emphasis(_LINK.sub(stash, escape(part.replace("\x01", ""))))
        out.append(re.sub("\x01(\\d+)\x01", lambda m: links[int(m.group(1))], part))
    return "".join(out)


def _emphasis(text: str) -> str:
    text = _STRONG.sub(r"<strong>\1</strong>", text)
    text = _EM_STAR.sub(r"<em>\1</em>", text)
    return _EM_UNDER.sub(r"<em>\1</em>", text)


def _starts_block(line: str) -> bool:
    return bool(
        _FENCE.match(line) or _HEADING.match(line) or _RULE.match(line)
        or _QUOTE.match(line) or _BULLET.match(line) or _NUMBER.match(line)
    )


def _paragraph(lines: list[str]) -> str:
    # Join first so emphasis may span source lines; \x00 marks a hard break.
    joined = []
    for i, line in enumerate(lines):
        hard = (line.endswith("  ") or line.endswith("\\")) and i < len(lines) - 1
        joined.append(line.rstrip().rstrip("\\").strip() + ("\x00" if hard else ""))
    return "<p>" + render_inline("\n".join(joined)).replace("\x00", "<br/>") + "</p>"


def render_markdown(text: str) -> str:
    """Render a block of Markdown to an XHTML fragment."""
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        fence = _FENCE.match(line)
        if fence:
            body = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence.group(1)):
                body.append(lines[i])
                i += 1
            i += 1  # closing fence, or end of text
            out.append("<pre><code>" + escape("\n".join(body)) + "</code></pre>")
            continue

        heading = _HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            out.append(f"<h{level}>{render_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        if _RULE.match(line):
            out.append('<hr class="scene-break"/>')
            i += 1
            continue

        if _QUOTE.match(line):
            quoted = []
            while i < len(lines) and _QUOTE.match(lines[i]):
                quoted.append(_QUOTE.match(lines[i]).group(1))
                i += 1
            out.append("<blockquote>\n" + render_markdown("\n".join(quoted)) + "\n</blockquote>")
            continue

        for pattern, tag in ((_BULLET, "ul"), (_NUMBER, "ol")):
            if not pattern.match(line):
                continue
            items: list[str] = []
            while i < len(lines) and lines[i].strip():
                match = pattern.match(lines[i])
                if match:
                    items.append(match.group(match.lastindex))
                elif lines[i].startswith((" ", "\t")):
                    items[-1] += " " + lines[i].strip()
                else:
                    break
                i += 1
            body = "\n".join(f"<li>{render_inline(item)}</li>" for item in items)
            # Keep the author's first number: a list that opens at 3 must not print as 1.
            first = int(pattern.match(line).group(1)) if tag == "ol" else 1
            start = f' start="{first}"' if first != 1 else ""
            out.append(f"<{tag}{start}>\n{body}\n</{tag}>")
            break
        else:
            para = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not _starts_block(lines[i]):
                para.append(lines[i])
                i += 1
            out.append(_paragraph(para))
    return "\n".join(out)
