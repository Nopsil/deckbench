"""Project version and an on-demand GitHub release check.

The version string is the assignment in ``sts2sim/__init__.py``. This module
reads that file. It does not import the simulator, and it does not contact
the network unless ``check_latest`` is called.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

REPO = "Nopsil/deckbench"
RELEASES_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
_MAX_BODY = 1_000_000
_TIMEOUT = 8.0

_ASSIGNMENT = re.compile(r"""^__version__\s*=\s*["']([^"']+)["']""", re.MULTILINE)
_SEMVER = re.compile(
    r"^v?"
    r"(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_PRE_NUM = re.compile(r"^(0|[1-9]\d*)$")
_PRE_WORD = re.compile(r"^[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*$")
_TOKEN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+-]*$")


def _package_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_project_version(root=None):
    """Return ``sts2sim.__version__`` from source. ``root`` is the repo or ``sim/``."""
    root = root or _package_root()
    path = os.path.join(root, "sts2sim", "__init__.py")
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    match = _ASSIGNMENT.search(text)
    if not match:
        raise ValueError(f"sts2sim.__version__ was not found in {path}")
    version = match.group(1).strip()
    if not _TOKEN.fullmatch(version):
        raise ValueError(f"sts2sim.__version__ is not a version token: {version!r}")
    return version


def parse_semver(value):
    """Parse a semver string. A single leading ``v`` is accepted. Build metadata is ignored."""
    text = str(value or "").strip()
    match = _SEMVER.fullmatch(text)
    if not match:
        raise ValueError(f"not a semver version: {value!r}")
    pre = []
    if match.group("pre"):
        for part in match.group("pre").split("."):
            if _PRE_NUM.fullmatch(part) or _PRE_WORD.fullmatch(part):
                pre.append(part)
            else:
                raise ValueError(f"not a semver version: {value!r}")
    return (int(match.group("major")), int(match.group("minor")), int(match.group("patch")), tuple(pre))


def canonical_semver(value):
    major, minor, patch, pre = parse_semver(value)
    text = f"{major}.{minor}.{patch}"
    if pre:
        text += "-" + ".".join(pre)
    return text


def compare_semver(left, right):
    """Return -1, 0, or 1. Build metadata does not affect the result.

    A pre-release is older than the same numbers without a pre-release.
    """
    la, lb = parse_semver(left), parse_semver(right)
    for a, b in zip(la[:3], lb[:3]):
        if a != b:
            return -1 if a < b else 1
    pa, pb = la[3], lb[3]
    if not pa and not pb:
        return 0
    if pa and not pb:
        return -1
    if pb and not pa:
        return 1
    for a, b in zip(pa, pb):
        if a == b:
            continue
        an, bn = bool(_PRE_NUM.fullmatch(a)), bool(_PRE_NUM.fullmatch(b))
        if an and bn:
            ia, ib = int(a), int(b)
            return -1 if ia < ib else 1
        if an:
            return -1
        if bn:
            return 1
        return -1 if a < b else 1
    if len(pa) == len(pb):
        return 0
    return -1 if len(pa) < len(pb) else 1


def windows_file_version(version):
    """Four-part Windows file version, ``0.1.5`` → ``0.1.5.0``. Pre-release text is dropped."""
    major, minor, patch, _pre = parse_semver(version)
    parts = (major, minor, patch, 0)
    if any(part > 65535 for part in parts):
        raise ValueError(f"Windows file version is out of range: {version}")
    return ".".join(str(part) for part in parts)


def version_info_text(version):
    """PyInstaller version resource. ASCII. ``ProductVersion`` is the semver string."""
    semver = canonical_semver(version)
    file_ver = windows_file_version(version)
    parts = tuple(int(part) for part in file_ver.split("."))
    return (
        "VSVersionInfo(\n"
        "  ffi=FixedFileInfo(\n"
        f"    filevers={parts},\n"
        f"    prodvers={parts},\n"
        "    mask=0x3f,\n"
        "    flags=0x0,\n"
        "    OS=0x40004,\n"
        "    fileType=0x1,\n"
        "    subtype=0x0,\n"
        "    date=(0, 0)\n"
        "    ),\n"
        "  kids=[\n"
        "    StringFileInfo([\n"
        "      StringTable(\n"
        "        '040904B0',\n"
        "        [StringStruct('CompanyName', 'DeckBench'),\n"
        "         StringStruct('FileDescription', 'DeckBench'),\n"
        f"         StringStruct('FileVersion', '{file_ver}'),\n"
        "         StringStruct('InternalName', 'DeckBench.exe'),\n"
        "         StringStruct('OriginalFilename', 'DeckBench.exe'),\n"
        "         StringStruct('ProductName', 'DeckBench'),\n"
        f"         StringStruct('ProductVersion', '{semver}')])\n"
        "      ]),\n"
        "    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n"
        "  ]\n"
        ")\n"
    )


def _headers(value):
    if not value:
        return {}
    try:
        items = value.items()
    except AttributeError:
        items = value
    return {str(key).lower(): str(item) for key, item in items}


def default_fetch(url, timeout):
    """GET ``url``. Return ``(status, headers, body)``. ``HTTPError`` is a status, not a raise."""
    version = "0"
    try:
        version = read_project_version()
    except (OSError, ValueError):
        pass
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"DeckBench/{version} (+{RELEASES_PAGE})",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, _headers(res.headers), res.read(_MAX_BODY + 1)
    except urllib.error.HTTPError as exc:
        raw = exc.read(_MAX_BODY + 1) if exc.fp is not None else b""
        return exc.code, _headers(exc.headers), raw


def _safe_release_url(url):
    if isinstance(url, str) and url.startswith(f"https://github.com/{REPO}/"):
        return url
    return RELEASES_PAGE


def _rate_limited(status, headers, body):
    if status == 429:
        return True
    text = body.decode("utf-8", "replace").lower()
    remaining = headers.get("x-ratelimit-remaining", "")
    if status == 403 and remaining.strip() == "0":
        return True
    return status in (403, 429) and "rate limit" in text


def _result(current, status, ok, latest=None, tag=None, html_url=None, message=""):
    return {
        "ok": ok,
        "current": current,
        "latest": latest,
        "tag": tag,
        "status": status,
        "html_url": html_url or RELEASES_PAGE,
        "repo": REPO,
        "message": message,
    }


def check_latest(current=None, fetch=None, timeout=_TIMEOUT):
    """Compare ``current`` (default: the project version) with the latest GitHub release.

    Network and HTTP failures return a dict. They do not raise.
    ``status`` is ``up_to_date``, ``update_available``, ``offline``, ``rate_limited``,
    ``not_published``, or ``error``.
    """
    if current is None:
        try:
            current = read_project_version()
        except (OSError, ValueError):
            current = "?"
    fetch = fetch or default_fetch
    try:
        status, headers, body = fetch(RELEASES_LATEST, timeout)
    except (urllib.error.URLError, TimeoutError, OSError):
        return _result(current, "offline", False, message="Offline. Could not check for updates.")
    headers = _headers(headers)
    if not isinstance(body, (bytes, bytearray)):
        body = b""
    body = bytes(body)
    if len(body) > _MAX_BODY:
        return _result(current, "error", False, message="Could not check for updates.")
    if _rate_limited(status, headers, body):
        return _result(current, "rate_limited", False, message="GitHub rate limit reached. Try again later.")
    if status == 404:
        return _result(current, "not_published", False, message="No published release to compare.")
    if status != 200:
        return _result(current, "error", False, message="Could not check for updates.")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return _result(current, "error", False, message="Could not check for updates.")
    if not isinstance(payload, dict):
        return _result(current, "error", False, message="Could not check for updates.")
    tag = str(payload.get("tag_name") or "").strip()
    html_url = _safe_release_url(payload.get("html_url"))
    try:
        latest = canonical_semver(tag)
        order = compare_semver(current, latest)
    except ValueError:
        return _result(current, "error", False, tag=tag or None, html_url=html_url,
                       message="Could not check for updates.")
    if order < 0:
        return _result(
            current, "update_available", True, latest=latest, tag=tag, html_url=html_url,
            message=f"New version {latest} available.",
        )
    return _result(
        current, "up_to_date", True, latest=latest, tag=tag, html_url=html_url,
        message="Up to date.",
    )
