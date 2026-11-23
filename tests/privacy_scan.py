#!/usr/bin/env python3
"""The privacy scan: nothing of the people who made this project goes out with it.

  python tests/privacy_scan.py                     the files git tracks
  python tests/privacy_scan.py --history           and every commit, tag, message and file name in the history
  python tests/privacy_scan.py --github            and what the project has published on GitHub (needs the gh CLI)
  python tests/privacy_scan.py --terms FILE        and these words too, one a line (a name, a folder, a private project)
  python tests/privacy_scan.py --draft FILE        and a text about to be published (a pull request, release notes)

What it looks for: paths on someone's machine, addresses, keys and tokens, agent session data, files that should never be
published, metadata inside pictures (EXIF, XMP, PNG text, C2PA, anything appended after the image), active content in
SVG, and pictures nobody approved (tests/public_images.sha256).

A --terms file stays outside the repository: the list of what must not be published is itself private. The report never
prints what it found, only the rule, the place and a masked hint, because CI logs are public.

Exit codes: 0 clean, 1 findings, 2 the scan could not run. Standard library only."""
import argparse
import hashlib
import json
import math
import re
import struct
import subprocess
import sys
import zlib
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPROVED_IMAGES = ROOT / "tests" / "public_images.sha256"
RASTER = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".ico", ".avif", ".heic"}
IMAGE = RASTER | {".svg"}
MAX_BLOB = 64 * 2 ** 20


@dataclass(frozen=True)
class Finding:
    rule: str
    where: str
    line: int
    hint: str

    def __str__(self):
        at = f"{self.where}:{self.line}" if self.line else self.where
        return f"{self.rule}: {at}" + (f" ({self.hint})" if self.hint else "")


def mask(value):
    """A hint at what matched that does not give it away."""
    value = value.strip()
    return f"{value[:2]}... {len(value)} chars" if len(value) > 4 else f"{len(value)} chars"


def entropy(s):
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values()) if n else 0.0


def luhn(number):
    digits = [int(c) for c in number if c.isdigit()][::-1]
    return sum(d if i % 2 == 0 else (d * 2 - 9 if d > 4 else d * 2) for i, d in enumerate(digits)) % 10 == 0


PLACEHOLDER = re.compile(r"(?i)your|example|sample|placeholder|changeme|dummy|redacted|xxxx|none|null|true|false|"
                         r"environ|getenv|secrets\.|\$\{|<[^>]*>")


def real_secret(m):
    value = m.group(1)
    return not PLACEHOLDER.search(value) and entropy(value) >= 3.2 and bool(re.search(r"\d", value))


def random_token(m):
    v = m.group(0).rstrip("=")
    if re.fullmatch(r"[0-9a-fA-F]+", v) or "/" in v or "_" in v.strip("_") and v.islower():
        return False                                    # a hash, a path, a snake_case name
    return all(re.search(p, v) for p in ("[a-z]", "[A-Z]", "[0-9]")) and entropy(v) >= 4.4


def card_number(m):
    digits = re.sub(r"\D", "", m.group(0))
    return 13 <= len(digits) <= 19 and len(set(digits)) > 1 and luhn(digits)


def tw_id(m):
    v = m.group(0)
    codes = "ABCDEFGHJKLMNPQRSTUVXYWZIO"
    n = codes.index(v[0]) + 10
    total = n // 10 + (n % 10) * 9 + sum(int(c) * w for c, w in zip(v[1:9], range(8, 0, -1))) + int(v[9])
    return total % 10 == 0


# Written so that none of them matches its own source: this file is scanned like any other.
TEXT_RULES = [(rule, re.compile(pattern), check) for rule, pattern, check in (
    # places on a machine
    ("path-windows", r"(?<![A-Za-z0-9])[A-Za-z]:[\\/](?![\\/])", None),
    ("path-unc", r"(?<![\w\\/:])\\\\[A-Za-z0-9._-]+\\[A-Za-z0-9$._-]+", None),
    ("path-user", r"[\\/](?:Users|home)[\\/][\w.-]+", None),
    ("path-root", r"(?<![\w.])/(?:root|mnt/[a-z]|private/var|var/folders)/", None),
    ("path-secret-dir", r"[\\/]\.(?:ssh|aws|gnupg|kube|docker|azure)[\\/]|\.config[\\/]gh[\\/]", None),
    ("agent-state", r"\.claude[\\/]projects|\.codex[\\/](?:sessions|auth|memories|archived)|local-agent" r"-mode-sessions|"
                    r"rollout-\d{4}-\d{2}|session_index\.jsonl", None),
    ("workspace-path", r"\w-workspace[\\/]\w", None),
    ("session-id", r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", None),
    # people
    ("email", r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b", None),
    ("phone-tw", r"(?<![0-9A-Za-z.-])09\d{2}[- ]?\d{3}[- ]?\d{3}(?![0-9A-Za-z.-])", None),
    ("national-id-tw", r"\b[A-Z][12]\d{8}\b", tw_id),
    ("card-number", r"(?<![0-9A-Za-z.])\d(?:[ -]?\d){12,18}(?![0-9A-Za-z.])", card_number),
    ("ip-private", r"(?<![\d.])(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}(?![\d.])", None),
    ("mac-address", r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b", None),
    # keys and tokens
    ("key-private", r"-{5}BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-{5}", None),
    ("key-aws", r"\b(?:AKIA|ASIA|AIDA|AROA)[0-9A-Z]{16}\b", None),
    ("key-github", r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})\b", None),
    ("key-anthropic", r"\bsk-ant-[A-Za-z0-9_-]{20,}", None),
    ("key-openai", r"\bsk-(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}", None),
    ("key-google", r"\bAIza[0-9A-Za-z_-]{35}\b", None),
    ("key-slack", r"\bxox[abeoprs]-[A-Za-z0-9-]{10,}", None),
    ("webhook", r"hooks\.slack\.com/services/[A-Za-z0-9/]+|discord(?:app)?\.com/api/webhooks/\d+", None),
    ("key-huggingface", r"\bhf_[A-Za-z0-9]{30,}\b", None),
    ("key-npm", r"\bnpm_[A-Za-z0-9]{36}\b", None),
    ("key-pypi", r"\bpypi-AgE[A-Za-z0-9_-]{40,}", None),
    ("key-stripe", r"\b[sr]k_live_[A-Za-z0-9]{16,}", None),
    ("key-sendgrid", r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{30,}", None),
    ("key-telegram", r"\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b", None),
    ("token-jwt", r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", None),
    ("url-credentials", r"\b[a-z][a-z0-9+.-]*://[^/\s:@'\"]+:[^/\s@'\"]+@[\w.-]+", None),
    ("token-bearer", r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{20,}=*", None),
    ("secret-assigned", r"(?i)(?:api[_-]?key|apikey|secret|token|passw(?:or)?d|pwd|auth[_-]?key|access[_-]?key)"
                        r"[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_\-+/=.]{12,})", real_secret),
    ("token-random", r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/_-]{32,}={0,2}(?![A-Za-z0-9+/=_-])", random_token),
)]

# Files that should never be published, wherever they sit.
FORBIDDEN_NAME = re.compile(
    r"(?i)^(?:\.env(?:\..+)?|\.netrc|\.npmrc|\.pypirc|\.git-credentials|credentials(?:\.\w+)?|auth\.json|"
    r"secrets?(?:\.\w+)?|id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?|.+\.(?:pem|key|p12|pfx|keystore|kdbx|gpg|asc)|"
    r"settings\.local\.json|session_index\.jsonl|rollout-.+\.jsonl|.+\.(?:sqlite3?|db)(?:-wal|-shm)?|"
    r"thumbs\.db|\.ds_store|desktop\.ini|.+\.(?:log|bak|orig|swp|tmp|dmp|ipynb)|.+~)$")
FORBIDDEN_DIR = re.compile(r"(?i)^(?:.+-workspace|\.venv|venv|node_modules|\.idea|\.vscode|__pycache__|\.pytest_cache|"
                           r"\.ssh|\.aws|\.claude|\.codex)$")

SVG_RULES = [(rule, re.compile(pattern)) for rule, pattern in (
    ("svg-script", r"(?i)<script|javascript:|<foreignObject|<iframe|<embed|<object"),
    ("svg-handler", r"(?i)\son[a-z]+\s*="),
    ("svg-editor-data", r"(?i)<metadata|<!--|sodipodi:|inkscape:|xmlns:(?:dc|cc|rdf)\b|export-filename|docname="),
    ("svg-external", r"(?i)(?:href|src)\s*=\s*[\"'](?!#)"),
    ("svg-embedded-data", r"(?i)data:[a-z]+/"),
)]


def scan_text(text, where, terms=()):
    """Every rule over the text, line by line. U+2028 and the like do not end a line here, so nothing hides behind one."""
    found = []
    for n, line in enumerate(text.split("\n"), 1):
        for rule, rx, check in TEXT_RULES:
            for m in rx.finditer(line):
                if check is None or check(m):
                    found.append(Finding(rule, where, n, mask(m.group(0))))
        low = line.casefold()
        for i, term in enumerate(terms):
            if term.casefold() in low:
                found.append(Finding("private-term", where, n, f"term {i + 1}"))
    return found


def scan_svg(text, where):
    found = []
    for n, line in enumerate(text.split("\n"), 1):
        for rule, rx in SVG_RULES:
            if rx.search(line):
                found.append(Finding(rule, where, n, ""))
    return found


PNG_PLAIN = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"pHYs", b"sBIT", b"bKGD", b"iCCP",
             b"cICP", b"mDCV", b"cLLI"}


def png_text(kind, body):
    try:
        if kind == b"tEXt":
            return body.replace(b"\0", b" ").decode("latin-1")
        if kind == b"zTXt":
            key, _, rest = body.partition(b"\0")
            return key.decode("latin-1") + " " + zlib.decompress(rest[1:], bufsize=2 ** 16).decode("latin-1")
        if kind == b"iTXt":
            key, _, rest = body.partition(b"\0")
            compressed, rest = rest[0], rest[2:]
            _, _, rest = rest.partition(b"\0")
            _, _, rest = rest.partition(b"\0")
            return key.decode("latin-1") + " " + (zlib.decompress(rest) if compressed else rest).decode("utf-8", "replace")
    except (zlib.error, IndexError, ValueError):
        pass
    return body[:4096].decode("latin-1")


def scan_png(data, where):
    found, pos = [], 8
    while pos + 8 <= len(data):
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        end = pos + 12 + size
        if end > len(data):
            return found + [Finding("image-damaged", where, 0, f"chunk {kind.decode('latin-1')} runs past the file")]
        if kind not in PNG_PLAIN:
            found.append(Finding("image-metadata", where, 0, f"PNG {kind.decode('latin-1')} chunk, {size} bytes"))
            if kind in (b"tEXt", b"zTXt", b"iTXt"):
                found += scan_text(png_text(kind, data[pos + 8:pos + 8 + size]), f"{where} [{kind.decode()}]")
        pos = end
        if kind == b"IEND":
            if pos != len(data):
                found.append(Finding("image-trailing-data", where, 0, f"{len(data) - pos} bytes after the image"))
            return found
    return found + [Finding("image-damaged", where, 0, "no IEND chunk")]


def scan_jpeg(data, where):
    found, pos = [], 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            return found + [Finding("image-damaged", where, 0, "a marker is missing")]
        marker = data[pos + 1]
        if marker == 0xFF:
            pos += 1
            continue
        if marker == 0xDA:                              # the scan: from here on it is image data up to the end marker
            end = data.rfind(b"\xff\xd9")
            if end < 0:
                return found + [Finding("image-damaged", where, 0, "no end marker")]
            if end + 2 != len(data):
                found.append(Finding("image-trailing-data", where, 0, f"{len(data) - end - 2} bytes after the image"))
            return found
        size = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        body = data[pos + 4:pos + 2 + size]
        plain = marker == 0xE0 and body[:5] == b"JFIF\0" or marker == 0xE2 and body[:12] == b"ICC_PROFILE\0" or \
            marker == 0xEE and body[:5] == b"Adobe"
        if (0xE0 <= marker <= 0xEF or marker == 0xFE) and not plain:
            found.append(Finding("image-metadata", where, 0, f"JPEG segment FF{marker:02X}, {size} bytes"))
            found += scan_text(body[:65536].decode("latin-1"), f"{where} [FF{marker:02X}]")
        pos += 2 + size
    return found + [Finding("image-damaged", where, 0, "no image data")]


def scan_webp(data, where):
    found, pos = [], 12
    end = 8 + struct.unpack("<I", data[4:8])[0]
    if end < len(data):
        found.append(Finding("image-trailing-data", where, 0, f"{len(data) - end} bytes after the image"))
    while pos + 8 <= min(end, len(data)):
        kind, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        if kind not in (b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ANIM", b"ANMF", b"ICCP"):
            found.append(Finding("image-metadata", where, 0, f"WebP {kind.decode('latin-1')} chunk, {size} bytes"))
            found += scan_text(data[pos + 8:pos + 8 + min(size, 65536)].decode("latin-1"), f"{where} [{kind!r}]")
        pos += 8 + size + (size & 1)
    return found


def scan_image(data, where):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return scan_png(data, where)
    if data[:2] == b"\xff\xd8":
        return scan_jpeg(data, where)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return scan_webp(data, where)
    return [Finding("image-unknown-format", where, 0, "only PNG, JPEG and WebP can be checked")]


def scan_name(path):
    parts = Path(path).as_posix().split("/")
    found = [Finding("forbidden-file", path, 0, "") for p in parts[-1:] if FORBIDDEN_NAME.match(p)]
    return found + [Finding("forbidden-folder", path, 0, "") for p in parts[:-1] if FORBIDDEN_DIR.match(p)]


def scan_blob(data, path, terms=()):
    """One file's bytes under its name: pictures for what they carry, everything else as text."""
    found = scan_name(path)
    suffix = Path(path).suffix.lower()
    if suffix in RASTER:
        found += scan_image(data, path)
        for i, term in enumerate(terms):
            needle = term.encode("utf-8")
            if needle in data or term.encode("utf-16-le") in data:
                found.append(Finding("private-term", path, 0, f"term {i + 1} in the file's bytes"))
        return found
    if b"\0" in data:
        return found + [Finding("binary-file", path, 0, f"{len(data)} bytes")]
    text = data.decode("utf-8", "replace")
    found += scan_text(text, path, terms)
    if suffix == ".svg":
        found += scan_svg(text, path)
    return found


# ---------------------------------------------------------------------------------------------------------- the tree

def git(*args):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True).stdout


def tracked_files():
    """The repository's own files: git's list in a checkout, every file in an unpacked archive."""
    try:
        listed = [f for f in git("ls-files", "-z").decode("utf-8").split("\0") if f]
        if listed:
            return listed
    except (OSError, subprocess.CalledProcessError):
        pass
    skip = {".git", "__pycache__", ".pytest_cache"}
    return [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and not skip & set(p.relative_to(ROOT).parts)]


def approved_images():
    if not APPROVED_IMAGES.is_file():
        return {}
    rows = (l.split(maxsplit=1) for l in APPROVED_IMAGES.read_text(encoding="utf-8").splitlines() if l.strip())
    return {name.strip().lstrip("*"): sha for sha, name in rows}


def scan_tree(terms=()):
    found, approved, seen = [], approved_images(), set()
    for rel in tracked_files():
        p = ROOT / rel
        if not p.is_file():                             # (deleted in the working tree, not yet staged)
            continue
        data = p.read_bytes()
        found += scan_blob(data, rel, terms)
        if Path(rel).suffix.lower() in IMAGE:
            seen.add(rel)
            if approved.get(rel) != hashlib.sha256(data).hexdigest():
                found.append(Finding("image-not-approved", rel, 0, "not in tests/public_images.sha256 as it is now"))
    found += [Finding("image-list-stale", rel, 0, "listed but not in the repository") for rel in sorted(set(approved) - seen)]
    return found


# ------------------------------------------------------------------------------------------------------- the history

ALLOWED_COMMIT_EMAIL = re.compile(r"(?i)^(?:\d+\+)?[\w-]+@users\.noreply\.github\.com$|^noreply@github\.com$|"
                                  r"^noreply@anthropic\.com$")
TRAILER_EMAIL = re.compile(r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")


def scan_message(text, where, terms=()):
    """A commit or tag message: every rule, except that a co-author's no-reply address is what git hosts ask for."""
    clean = TRAILER_EMAIL.sub(lambda m: "" if ALLOWED_COMMIT_EMAIL.match(m.group(0)) else m.group(0), text)
    return scan_text(clean, where, terms)


def scan_history(terms=()):
    found = []
    log = git("log", "--all", "--format=%H%x00%an%x00%ae%x00%cn%x00%ce%x00%B%x01").decode("utf-8", "replace")
    commits = [c.strip("\n") for c in log.split("\x01") if c.strip()]
    for row in commits:
        sha, an, ae, cn, ce, body = row.split("\0", 5)
        where = f"commit {sha[:9]}"
        for email in (ae, ce):
            if not ALLOWED_COMMIT_EMAIL.match(email):
                found.append(Finding("commit-email", where, 0, mask(email)))
        found += scan_message("\n".join((an, cn, body)), where, terms)
    tags = git("for-each-ref", "refs/tags", "--format=%(refname:short)%00%(taggeremail)%00%(contents)%01").decode("utf-8", "replace")
    for row in (t.strip("\n") for t in tags.split("\x01") if t.strip()):
        name, email, body = row.split("\0", 2)
        email = email.strip("<>")
        if email and not ALLOWED_COMMIT_EMAIL.match(email):
            found.append(Finding("commit-email", f"tag {name}", 0, mask(email)))
        found += scan_message(f"{name}\n{body}", f"tag {name}", terms)

    objects = {}
    for line in git("rev-list", "--all", "--objects").decode("utf-8", "replace").splitlines():
        sha, _, path = line.partition(" ")
        if path and sha not in objects:
            objects[sha] = path
    with subprocess.Popen(["git", "-C", str(ROOT), "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as cat:
        for sha, path in objects.items():
            cat.stdin.write(sha.encode() + b"\n")
            cat.stdin.flush()
            _, kind, size = cat.stdout.readline().split()
            size = int(size)
            data = cat.stdout.read(size)
            cat.stdout.read(1)
            if kind != b"blob":
                continue
            where = f"history {sha[:9]} {path}"
            if size > MAX_BLOB:
                found.append(Finding("history-large-blob", where, 0, f"{size} bytes"))
                continue
            found += [Finding(f.rule, where, f.line, f.hint) for f in scan_blob(data, path, terms)
                      if f.rule not in ("binary-file", "image-unknown-format")]
    return found, len(commits), len(objects)


# ------------------------------------------------------------------------------------------- what is published on GitHub

# The hidden marker a code review tool leaves on its own comment: a run's id, which says nothing of anyone.
REVIEW_MARKER = re.compile(r"<!-- claude-code-ultrareview-post:[0-9a-f-]{36} -->")


def gh_pages(endpoint):
    r = subprocess.run(["gh", "api", "--paginate", "--slurp", endpoint], capture_output=True, cwd=ROOT)
    if r.returncode:
        raise RuntimeError(f"gh api {endpoint}: {r.stderr.decode('utf-8', 'replace').strip()[:200]}")
    pages = json.loads(r.stdout.decode("utf-8"))
    return [row for page in pages for row in (page if isinstance(page, list) else [page])]


def scan_github(repo, terms=()):
    found, items = [], 0

    def text(where, *values):
        nonlocal found, items
        items += 1
        body = REVIEW_MARKER.sub("", "\n".join(v for v in values if v))
        found += scan_message(body, f"github {where}", terms)

    meta = gh_pages(f"repos/{repo}")[0]
    text("repository", meta.get("description"), meta.get("homepage"), " ".join(meta.get("topics") or []))
    prs = []
    for i in gh_pages(f"repos/{repo}/issues?state=all&per_page=100"):
        text(f"#{i['number']}", i.get("title"), i.get("body"))
        if "pull_request" in i:
            prs.append(i["number"])
    for c in gh_pages(f"repos/{repo}/issues/comments?per_page=100"):
        text(f"issue comment {c['id']}", c.get("body"))
    for c in gh_pages(f"repos/{repo}/pulls/comments?per_page=100"):
        text(f"review comment {c['id']}", c.get("body"), c.get("diff_hunk"))
    for n in prs:
        for c in gh_pages(f"repos/{repo}/pulls/{n}/reviews?per_page=100"):
            text(f"#{n} review {c['id']}", c.get("body"))
    for c in gh_pages(f"repos/{repo}/comments?per_page=100"):
        text(f"commit comment {c['id']}", c.get("body"))
    for rel in gh_pages(f"repos/{repo}/releases?per_page=100"):
        text(f"release {rel.get('tag_name')}", rel.get("name"), rel.get("body"),
             "\n".join(a.get("name", "") for a in rel.get("assets", [])))
    return found, items


def read_terms(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.lstrip().startswith("#")]


def main(argv=None):
    ap = argparse.ArgumentParser(description="The privacy scan of this repository.")
    ap.add_argument("--history", action="store_true", help="also every commit, tag and past file")
    ap.add_argument("--github", action="store_true", help="also the issues, pull requests and releases (needs gh)")
    ap.add_argument("--repo", default="owoevan-dev/refinish-skill", help="the GitHub repository for --github")
    ap.add_argument("--terms", help="a file outside the repository listing private words, one a line")
    ap.add_argument("--draft", action="append", default=[], help="a text about to be published; may be repeated")
    ap.add_argument("--json", action="store_true", help="the report as JSON")
    a = ap.parse_args(argv)
    try:
        terms = read_terms(a.terms) if a.terms else []
        found = scan_tree(terms)
        report = {"files": len(tracked_files()), "terms": len(terms)}
        for draft in a.draft:
            found += scan_message(Path(draft).read_text(encoding="utf-8"), f"draft {Path(draft).name}", terms)
        report["drafts"] = len(a.draft)
        if a.history:
            hist, report["commits"], report["objects"] = scan_history(terms)
            found += hist
        if a.github:
            gh, report["github_items"] = scan_github(a.repo, terms)
            found += gh
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as e:
        print(f"error: the privacy scan could not run: {e}", file=sys.stderr)
        return 2
    found = sorted(set(found), key=lambda f: (f.rule, f.where, f.line))
    report["findings"] = len(found)
    report["by_rule"] = dict(sorted(Counter(f.rule for f in found).items()))
    if a.json:
        print(json.dumps({**report, "items": [asdict(f) for f in found]}, indent=1))
    else:
        for f in found:
            print(f)
        print(json.dumps(report))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
