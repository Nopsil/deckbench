"""Parse the latest ``CHANGELOG.md`` section into text, for ``GET /api/changelog``.

The GUI draws these spans itself. The response is not HTML, and a ``<script>``
or ``javascript:`` link in the file stays text.
"""
import os
import re
import sys

from . import paths

MAX_BYTES = 2_000_000
_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_RELATIVE = re.compile(r"^[A-Za-z0-9_./#?&=%+-]+$")


class ChangelogError(Exception):
    """The changelog is missing, unreadable, or too large. The message is not shown."""


def changelog_path():
    """Dev: repo root. Packaged: the PyInstaller bundle, then beside the exe."""
    candidates = []
    if paths.FROZEN:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(os.path.join(meipass, "CHANGELOG.md"))
        candidates.append(os.path.join(paths.APP_DIR, "CHANGELOG.md"))
    else:
        candidates.append(os.path.join(paths.SIM_ROOT, "CHANGELOG.md"))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return candidates[0] if candidates else ""


def load_changelog(version, path=None):
    """Return ``{version, heading, blocks}``. ``version`` is ``sts2sim.__version__``."""
    path = path or changelog_path()
    if not path or not os.path.isfile(path):
        raise ChangelogError("missing")
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise ChangelogError("unreadable") from exc
    if size > MAX_BYTES:
        raise ChangelogError("too_big")
    try:
        with open(path, encoding="utf-8-sig") as handle:
            text = handle.read(MAX_BYTES + 1)
    except OSError as exc:
        raise ChangelogError("unreadable") from exc
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ChangelogError("too_big")
    parsed = parse_changelog(text)
    parsed["version"] = version
    return parsed


def parse_changelog(text):
    """The first ``##`` section. The next ``##`` is not included."""
    heading, body = _latest_section(text or "")
    return {"heading": heading, "blocks": _parse_blocks(body)}


def _latest_section(text):
    lines = text.splitlines()
    start = None
    heading = ""
    for index, line in enumerate(lines):
        if line.startswith("## "):
            start = index
            heading = line[3:].strip()
            break
    if start is None:
        return "", ""
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return heading, "\n".join(lines[start + 1:end])


def _parse_blocks(text):
    lines = text.splitlines()
    index = 0
    blocks = []
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("```"):
            index, block = _parse_fence(lines, index)
            blocks.append(block)
            continue
        level = _heading_level(line)
        if level:
            blocks.append({
                "kind": "h",
                "level": level,
                "spans": parse_inline(line[level + 1:].strip()),
            })
            index += 1
            continue
        if _is_item(line, 0):
            index, block = _parse_list(lines, index, 0)
            if block["items"]:
                blocks.append(block)
            continue
        paragraph = [line.strip()]
        index += 1
        while index < len(lines) and lines[index].strip() and not _starts_block(lines[index]):
            paragraph.append(lines[index].strip())
            index += 1
        blocks.append({"kind": "p", "spans": parse_inline(" ".join(paragraph))})
    return blocks


def _starts_block(line):
    return line.startswith("```") or bool(_heading_level(line)) or _is_item(line, 0)


def _heading_level(line):
    if not line.startswith("#"):
        return 0
    level = 0
    while level < len(line) and line[level] == "#":
        level += 1
    if level < 2 or level > 4 or level >= len(line) or line[level] != " ":
        return 0
    return level


def _indent(line):
    width = 0
    for char in line:
        if char == " ":
            width += 1
        elif char == "\t":
            width += 4
        else:
            break
    return width


def _is_item(line, indent):
    return _indent(line) == indent and line.lstrip().startswith("- ")


def _parse_fence(lines, index):
    index += 1
    body = []
    while index < len(lines) and not lines[index].startswith("```"):
        body.append(lines[index])
        index += 1
    if index < len(lines):
        index += 1
    return index, {"kind": "pre", "text": "\n".join(body)}


def _parse_list(lines, index, indent):
    items = []
    while index < len(lines):
        if not lines[index].strip():
            look = index + 1
            while look < len(lines) and not lines[look].strip():
                look += 1
            if look < len(lines) and _is_item(lines[look], indent):
                index = look
            else:
                break
        if index >= len(lines) or not _is_item(lines[index], indent):
            break
        content = lines[index].lstrip()[2:]
        index += 1
        extras = []
        while index < len(lines) and lines[index].strip() and _indent(lines[index]) > indent:
            if lines[index].lstrip().startswith("- "):
                index, nested = _parse_list(lines, index, _indent(lines[index]))
                extras.append(("ul", nested))
            else:
                extras.append(("text", lines[index].strip()))
                index += 1
        blocks = [{"kind": "p", "spans": parse_inline(content)}]
        pending = []
        for kind, value in extras:
            if kind == "text":
                pending.append(value)
                continue
            if pending:
                blocks.append({"kind": "p", "spans": parse_inline(" ".join(pending))})
                pending = []
            blocks.append(value)
        if pending:
            blocks.append({"kind": "p", "spans": parse_inline(" ".join(pending))})
        items.append({"blocks": blocks})
    return index, {"kind": "ul", "items": items}


def parse_inline(text):
    spans, _end = _parse_inline(text or "", 0, None)
    return _clean(spans)


def _parse_inline(text, index, stop):
    spans = []
    buf = []

    def flush():
        if buf:
            spans.append({"t": "text", "s": "".join(buf)})
            buf.clear()

    while index < len(text):
        if (
            stop
            and text.startswith(stop, index)
            and not (stop == "*" and text.startswith("**", index))
        ):
            flush()
            return spans, index
        if text.startswith("**", index):
            inner, end = _parse_inline(text, index + 2, "**")
            if end < len(text) and text.startswith("**", end):
                flush()
                spans.append({"t": "strong", "c": inner})
                index = end + 2
                continue
            buf.append("*")
            index += 1
            continue
        if text.startswith("`", index):
            end = text.find("`", index + 1)
            if end != -1:
                flush()
                spans.append({"t": "code", "s": text[index + 1:end]})
                index = end + 1
                continue
        if text.startswith("*", index):
            inner, end = _parse_inline(text, index + 1, "*")
            if end < len(text) and text.startswith("*", end) and not text.startswith("**", end):
                flush()
                spans.append({"t": "em", "c": inner})
                index = end + 1
                continue
            buf.append("*")
            index += 1
            continue
        if text.startswith("[", index):
            label_end = text.find("]", index + 1)
            if (
                label_end != -1
                and label_end + 1 < len(text)
                and text[label_end + 1] == "("
            ):
                href_end = text.find(")", label_end + 2)
                if href_end != -1:
                    label = text[index + 1:label_end]
                    href = safe_href(text[label_end + 2:href_end])
                    flush()
                    if href:
                        spans.append({"t": "link", "href": href, "c": parse_inline(label)})
                    else:
                        spans.append({"t": "text", "s": text[index:href_end + 1]})
                    index = href_end + 1
                    continue
        buf.append(text[index])
        index += 1
    flush()
    return spans, index


def _clean(spans):
    out = []
    for span in spans:
        kind = span.get("t")
        if kind in ("strong", "em", "link"):
            children = _clean(span.get("c") or [])
            if not children:
                continue
            span = dict(span)
            span["c"] = children
            out.append(span)
        elif kind == "code" or (kind == "text" and span.get("s")):
            out.append(span)
    return out


def safe_href(href):
    """http(s) or a relative path. ``javascript:`` and other schemes are not links."""
    href = (href or "").strip()
    if not href or len(href) > 2000:
        return None
    if any(ord(char) < 32 or char in "<>\"'" for char in href):
        return None
    lower = href.lower()
    if lower.startswith(("https://", "http://")):
        return href
    if _SCHEME.match(href) or href.startswith("//") or "\\" in href:
        return None
    if href.startswith(("#", "/")) or _RELATIVE.fullmatch(href):
        return href
    return None
