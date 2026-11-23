#!/usr/bin/env python3
"""The privacy scan: nothing of the people who made this project goes out with it.

  python tests/privacy_scan.py                     what git tracks (the index, as it would be committed)
  python tests/privacy_scan.py --history           and every object a ref reaches: commits, tags, notes, trees, old files
  python tests/privacy_scan.py --history --unreachable    and what no ref reaches, which a push does not carry
  python tests/privacy_scan.py --github            and what the project has published on GitHub (needs the gh CLI)
  python tests/privacy_scan.py --terms FILE        and these words too, one a line (a name, a folder, a private project)
  python tests/privacy_scan.py --draft FILE        and a text about to be published (a pull request, release notes)
  python tests/privacy_scan.py --show-paths        name the places found, for your own terminal only

What it looks for: paths on someone's machine, addresses, keys and tokens, agent session data, files that should never be
published, metadata inside pictures (EXIF, XMP, PNG text, ICC profiles, C2PA, anything after the image), active content
in SVG, files it cannot read, and pictures nobody approved (tests/public_images.sha256).

A --terms file stays outside the repository: the list of what must not be published is itself private. By default the
report names each place by an opaque id and never prints what it found, because CI logs are public and a file's name can
be the leak.

Exit codes: 0 clean, 1 findings, 2 the scan could not run. Standard library only."""
import argparse
import hashlib
import json
import math
import re
import struct
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPROVED_IMAGES = ROOT / "tests" / "public_images.sha256"
RASTER = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".ico", ".avif", ".heic"}
IMAGE = RASTER | {".svg"}
MAX_BLOB = 64 * 2 ** 20
MAX_INFLATED = 8 * 2 ** 20                              # (what one compressed metadata chunk may expand to)
MAX_ATTACHMENT = 32 * 2 ** 20
ATTACHMENT_HOSTS = {"github.com", "user-images.githubusercontent.com", "private-user-images.githubusercontent.com",
                    "objects.githubusercontent.com", "release-assets.githubusercontent.com"}


class ScanError(Exception):
    """The scan could not finish; its message holds nothing from the files."""


@dataclass(frozen=True)
class Finding:
    rule: str
    where: str
    line: int
    hint: str

    def item(self):
        return hashlib.sha256(self.where.encode("utf-8", "replace")).hexdigest()[:10]

    def public(self):
        return {"rule": self.rule, "item": self.item(), "line": self.line, "hint": self.hint}

    def __str__(self):
        at = f"item {self.item()}" + (f":{self.line}" if self.line else "")
        return f"{self.rule}: {at}" + (f" ({self.hint})" if self.hint else "")

    def local(self):
        at = f"{self.where}:{self.line}" if self.line else self.where
        return f"{self.rule}: {at}" + (f" ({self.hint})" if self.hint else "")


def mask(value):
    """A hint at what matched that gives none of it away."""
    return f"{len(value.strip())} chars"


def entropy(s):
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values()) if n else 0.0


def luhn(number):
    digits = [int(c) for c in number if c.isdigit()][::-1]
    return sum(d if i % 2 == 0 else (d * 2 - 9 if d > 4 else d * 2) for i, d in enumerate(digits)) % 10 == 0


PLACEHOLDER = re.compile(r"(?i)your|example|sample|placeholder|changeme|dummy|redacted|xxxx|^none$|^null$|^true$|^false$|"
                         r"environ|getenv|secrets\.|\$\{|<[^>]*>|^\*+$")
CODE_VALUE = re.compile(r"(?i)[().\[\]]|key|token|secret|passw|path|file|name|env|args|config")
STRONG_NAME = re.compile(r"(?i)api[_-]?key|client[_-]?secret|secret[_-]?key|access[_-]?token|auth[_-]?token|"
                         r"refresh[_-]?token|private[_-]?key|passw(?:or)?d")


def real_secret(m):
    """A credential field holding a value. A strong name (api_key, password) needs no randomness in its value: a plain
    word is a password too. A quoted value is a value; a bare word in code is usually a variable."""
    name, quote, value = m.group(1), m.group(2), m.group(3)
    if PLACEHOLDER.search(value):
        return False
    strong = bool(STRONG_NAME.search(name))
    if quote:
        return strong or (entropy(value) >= 3.2 and bool(re.search(r"\d", value)))
    if CODE_VALUE.search(value):
        return False
    return (strong and len(value) >= 12) or (entropy(value) >= 3.2 and bool(re.search(r"\d", value)))


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
    ("secret-assigned", r"(?i)([\w-]*(?:api[_-]?key|apikey|secret|token|passw(?:or)?d|pwd|auth[_-]?key|access[_-]?key)[\w-]*)"
                        r"[\"']?\s*(?:=>|:=|:|=)\s*([\"'`]?)([^\s\"'`,;]{8,})", real_secret),
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
# .claude-plugin and .codex-plugin are the plugin's manifests and do not match the two names above.

SVG_RULES = [(rule, re.compile(pattern)) for rule, pattern in (
    ("svg-script", r"(?i)<script|javascript:|<foreignObject|<iframe|<embed|<object"),
    ("svg-handler", r"(?i)\son[a-z]+\s*="),
    ("svg-editor-data", r"(?i)<metadata|<!--|sodipodi:|inkscape:|xmlns:(?:dc|cc|rdf)\b|export-filename|docname="),
    ("svg-external", r"(?i)(?:href|src)\s*=\s*[\"'](?!#)|url\(\s*[\"']?(?!#)|@import"),
    ("svg-embedded-data", r"(?i)data:[a-z]+/"),
)]
CONTAINERS = ((b"PK\x03\x04", "zip"), (b"PK\x05\x06", "zip"), (b"\x1f\x8b", "gzip"), (b"7z\xbc\xaf", "7z"), (b"Rar!", "rar"),
              (b"%PDF", "pdf"), (b"GIF8", "gif"), (b"II*\0", "tiff"), (b"MM\0*", "tiff"), (b"BM", "bmp"),
              (b"\x00\x00\x01\x00", "ico"), (b"SQLite format", "sqlite"), (b"\x7fELF", "program"), (b"MZ", "program"))


def fold(text):
    return unicodedata.normalize("NFKC", text).casefold()


def term_hits(text, where, terms, line=0):
    low = fold(text)
    return [Finding("private-term", where, line, f"term {i + 1}") for i, t in enumerate(terms) if fold(t) in low]


def scan_text(text, where, terms=()):
    """Every rule over the text, line by line. U+2028 and the like do not end a line here, so nothing hides behind one."""
    found = []
    for n, line in enumerate(text.split("\n"), 1):
        for rule, rx, check in TEXT_RULES:
            for m in rx.finditer(line):
                if check is None or check(m):
                    found.append(Finding(rule, where, n, mask(m.group(0))))
        found += term_hits(line, where, terms, n)
    return found


def scan_svg(text, where):
    found = []
    for n, line in enumerate(text.split("\n"), 1):
        for rule, rx in SVG_RULES:
            if rx.search(line):
                found.append(Finding(rule, where, n, ""))
    return found


def json_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from json_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from json_strings(v)


def inflate(data):
    """A bounded zlib decompression: a small chunk cannot expand to fill the runner."""
    d = zlib.decompressobj()
    out = d.decompress(data, MAX_INFLATED)
    if d.unconsumed_tail:
        raise ValueError("expands past the limit")
    return out


PNG_PLAIN = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"pHYs", b"sBIT", b"bKGD", b"cICP",
             b"mDCV", b"cLLI"}


def png_text(kind, body):
    if kind == b"tEXt":
        return body.replace(b"\0", b" ").decode("latin-1")
    if kind == b"zTXt":
        key, _, rest = body.partition(b"\0")
        return key.decode("latin-1") + " " + inflate(rest[1:]).decode("latin-1")
    key, _, rest = body.partition(b"\0")
    compressed, rest = rest[0], rest[2:]
    _, _, rest = rest.partition(b"\0")
    _, _, rest = rest.partition(b"\0")
    return key.decode("latin-1") + " " + (inflate(rest) if compressed else rest).decode("utf-8", "replace")


def profile_text(data):
    """What an ICC profile can say about who made it: its text, in the encodings a profile uses."""
    return data.decode("latin-1") + "\n" + data.decode("utf-16-be", "ignore") + "\n" + data[1:].decode("utf-16-be", "ignore")


def scan_profile(data, where, terms):
    return [Finding(f.rule, where, 0, "in an ICC profile") for f in term_hits(profile_text(data), where, terms)]


def scan_png(data, where, terms=()):
    found, pos = [], 8
    while pos + 12 <= len(data):
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        end = pos + 12 + size
        label = kind.decode("latin-1")
        if end > len(data):
            return found + [Finding("image-damaged", where, 0, f"chunk {label} runs past the file")]
        body = data[pos + 8:pos + 8 + size]
        if kind == b"iCCP":
            try:
                found += scan_profile(inflate(body.partition(b"\0")[2][1:]), where, terms)
                found += term_hits(body.partition(b"\0")[0].decode("latin-1"), where, terms)
            except (zlib.error, ValueError):
                found.append(Finding("image-metadata", where, 0, "an ICC profile that cannot be read"))
        elif kind not in PNG_PLAIN:
            found.append(Finding("image-metadata", where, 0, f"PNG {label} chunk, {size} bytes"))
            if kind in (b"tEXt", b"zTXt", b"iTXt"):
                try:
                    found += scan_text(png_text(kind, body), f"{where} [{label}]", terms)
                except (zlib.error, ValueError, IndexError):
                    found.append(Finding("image-metadata", where, 0, f"PNG {label} that cannot be read"))
        pos = end
        if kind == b"IEND":
            if pos != len(data):
                found.append(Finding("image-trailing-data", where, 0, f"{len(data) - pos} bytes after the image"))
            return found
    return found + [Finding("image-damaged", where, 0, "no IEND chunk")]


def jpeg_scan_end(data, pos):
    """Where the entropy-coded data from pos ends: at the first marker that is not stuffing or a restart."""
    while True:
        pos = data.find(b"\xff", pos)
        if pos < 0 or pos + 1 >= len(data):
            return -1
        following = data[pos + 1]
        if following == 0 or 0xD0 <= following <= 0xD7 or following == 0xFF:
            pos += 1 if following == 0xFF else 2
            continue
        return pos


def scan_jpeg(data, where, terms=()):
    found, pos = [], 2
    while pos + 2 <= len(data):
        if data[pos] != 0xFF:
            return found + [Finding("image-damaged", where, 0, "a marker is missing")]
        marker = data[pos + 1]
        if marker == 0xFF:
            pos += 1
            continue
        if marker == 0xD9:                              # the end of the first image: anything after it is hidden
            if pos + 2 != len(data):
                found.append(Finding("image-trailing-data", where, 0, f"{len(data) - pos - 2} bytes after the image"))
            return found
        if pos + 4 > len(data):
            break
        size = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        if size < 2 or pos + 2 + size > len(data):
            return found + [Finding("image-damaged", where, 0, "a segment runs past the file")]
        body = data[pos + 4:pos + 2 + size]
        icc = marker == 0xE2 and body[:12] == b"ICC_PROFILE\0"
        plain = marker == 0xE0 and body[:5] == b"JFIF\0" or marker == 0xEE and body[:5] == b"Adobe"
        if icc:
            found += scan_profile(body[14:], where, terms)
        elif (0xE0 <= marker <= 0xEF or marker == 0xFE) and not plain:
            found.append(Finding("image-metadata", where, 0, f"JPEG segment FF{marker:02X}, {size} bytes"))
            found += scan_text(body[:65536].decode("latin-1"), f"{where} [FF{marker:02X}]", terms)
        pos += 2 + size
        if marker == 0xDA:
            pos = jpeg_scan_end(data, pos)
            if pos < 0:
                return found + [Finding("image-damaged", where, 0, "no end marker")]
    return found + [Finding("image-damaged", where, 0, "no end marker")]


def scan_webp(data, where, terms=()):
    found, pos = [], 12
    if len(data) < 12:
        return [Finding("image-damaged", where, 0, "too short")]
    end = 8 + struct.unpack("<I", data[4:8])[0]
    if end > len(data):
        return [Finding("image-damaged", where, 0, "the file is shorter than it says")]
    if end < len(data):
        found.append(Finding("image-trailing-data", where, 0, f"{len(data) - end} bytes after the image"))
    while pos < end:
        if pos + 8 > end:
            return found + [Finding("image-damaged", where, 0, "a chunk header runs past the image")]
        kind, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        label = kind.decode("latin-1")
        if pos + 8 + size > end:
            return found + [Finding("image-damaged", where, 0, f"chunk {label} runs past the image")]
        body = data[pos + 8:pos + 8 + size]
        if kind == b"ICCP":
            found += scan_profile(body, where, terms)
        elif kind not in (b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ANIM", b"ANMF"):
            found.append(Finding("image-metadata", where, 0, f"WebP {label} chunk, {size} bytes"))
            found += scan_text(body[:65536].decode("latin-1"), f"{where} [{label}]", terms)
        pos += 8 + size + (size & 1)
    return found


def image_kind(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def scan_image(data, where, terms=()):
    kind = image_kind(data)
    if kind:
        return {"png": scan_png, "jpeg": scan_jpeg, "webp": scan_webp}[kind](data, where, terms)
    return [Finding("image-unknown-format", where, 0, "only PNG, JPEG and WebP can be checked")]


def scan_name(path, terms=()):
    """A path, every part of it: a file's name can be the private thing."""
    parts = str(path).replace("\\", "/").split("/")
    found = [Finding("forbidden-file", str(path), 0, "") for p in parts[-1:] if FORBIDDEN_NAME.match(p)]
    found += [Finding("forbidden-folder", str(path), 0, "") for p in parts[:-1] if FORBIDDEN_DIR.match(p)]
    return found + [Finding(f.rule, str(path), 0, "in the name") for f in scan_text(str(path), str(path), terms)]


def decode(data):
    """(text, why it is not plain UTF-8 or None); text None when it cannot be read as text at all."""
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe\0\0", "utf-32-le"), (b"\0\0\xfe\xff", "utf-32-be"),
                     (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
        if data.startswith(bom):
            try:
                return data[len(bom):].decode(enc), None if enc == "utf-8" else enc
            except UnicodeDecodeError:
                return None, enc
    if b"\0" in data:
        return None, "binary"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return data.decode("latin-1"), "not UTF-8"


def scan_content(data, where, terms=(), suffix=""):
    """One file's bytes, judged by what they are and not by what they are called."""
    if image_kind(data) or suffix in RASTER:
        found = scan_image(data, where, terms)
        for i, term in enumerate(terms):
            if any(term.encode(enc) in data for enc in ("utf-8", "utf-16-le", "utf-16-be")):
                found.append(Finding("private-term", where, 0, f"term {i + 1} in the file's bytes"))
        return found
    for magic, name in CONTAINERS:
        if data.startswith(magic):
            return [Finding("unreadable-file", where, 0, f"a {name} file cannot be checked")]
    text, why = decode(data)
    if text is None:
        return [Finding("binary-file", where, 0, f"{len(data)} bytes")]
    found = [Finding("not-utf8", where, 0, why)] if why else []
    found += scan_text(text, where, terms)
    start = text.lstrip()[:200]
    if start.startswith("version https://git-lfs."):
        found.append(Finding("lfs-pointer", where, 0, "its content is stored elsewhere"))
    if suffix == ".svg" or start.startswith("<svg") or (start.startswith("<?xml") and "<svg" in text):
        found += scan_svg(text, where)
    if suffix == ".json" or start[:1] in ("{", "["):
        try:
            value = json.loads(text)
        except (ValueError, RecursionError):
            value = None
        for s in json_strings(value):                   # (a @ in the file is an @ once read)
            found += [Finding(f.rule, where, 0, f.hint) for f in scan_text(s, where, terms)]
    return found


def scan_blob(data, path, terms=()):
    """A file under its name."""
    return scan_name(path, terms) + scan_content(data, path, terms, Path(path).suffix.lower())


# ------------------------------------------------------------------------------------------------------------- git

def git(*args):
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)
    if r.returncode:
        raise ScanError(f"git {args[0]} failed with exit code {r.returncode}")
    return r.stdout


class Objects:
    """git's object store, read one object at a time, each checked for its full length."""

    def __enter__(self):
        self.cat = subprocess.Popen(["git", "-C", str(ROOT), "cat-file", "--batch"], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return self

    def read(self, sha):
        self.cat.stdin.write(sha.encode() + b"\n")
        self.cat.stdin.flush()
        head = self.cat.stdout.readline().split()
        if len(head) != 3:
            raise ScanError("git could not read an object")
        size = int(head[2])
        data = self.cat.stdout.read(size)
        tail = self.cat.stdout.read(1)
        if len(data) != size or tail != b"\n":
            raise ScanError("git returned a short object")
        return head[1].decode(), data

    def __exit__(self, kind, *_):
        self.cat.stdin.close()
        self.cat.stdout.close()
        code = self.cat.wait()
        if code and kind is None:
            raise ScanError(f"git cat-file ended with exit code {code}")


def index_entries():
    """(mode, sha, path) of what git tracks, as staged; [] outside a checkout."""
    try:
        rows = git("ls-files", "-s", "-z").decode("utf-8", "surrogateescape").split("\0")
    except (OSError, ScanError):
        return []
    out = []
    for row in rows:
        if row:
            meta, path = row.split("\t", 1)
            mode, sha, _ = meta.split()
            out.append((mode, sha, path))
    return out


def tracked_files():
    entries = index_entries()
    if entries:
        return [p for _, _, p in entries]
    skip = {".git", "__pycache__", ".pytest_cache"}
    return [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and not skip & set(p.relative_to(ROOT).parts)]


def approved_images():
    if not APPROVED_IMAGES.is_file():
        return {}
    rows = (l.split(maxsplit=1) for l in APPROVED_IMAGES.read_text(encoding="utf-8").splitlines() if l.strip())
    return {name.strip().lstrip("*"): sha for sha, name in rows}


def scan_tree(terms=()):
    """The index: what the next commit holds, whatever the working copy says."""
    found, approved, seen = [], approved_images(), set()
    entries = index_entries()

    def check_image(rel, data):
        if Path(rel).suffix.lower() in IMAGE or image_kind(data):
            seen.add(rel)
            if approved.get(rel) != hashlib.sha256(data).hexdigest():
                found.append(Finding("image-not-approved", rel, 0, "not in tests/public_images.sha256 as it is now"))

    if entries:
        with Objects() as store:
            for mode, sha, rel in entries:
                if mode == "160000":
                    found.append(Finding("submodule", rel, 0, "its content lives elsewhere"))
                    found += scan_name(rel, terms)
                    continue
                _, data = store.read(sha)
                if mode == "120000":
                    found.append(Finding("link-in-repository", rel, 0, ""))
                    found += scan_name(rel, terms) + scan_text(data.decode("utf-8", "replace"), rel, terms)
                    continue
                found += scan_blob(data, rel, terms)
                check_image(rel, data)
    else:
        for rel in tracked_files():
            data = (ROOT / rel).read_bytes()
            found += scan_blob(data, rel, terms)
            check_image(rel, data)
    found += [Finding("image-list-stale", rel, 0, "listed but not in the repository") for rel in sorted(set(approved) - seen)]
    return found


ALLOWED_COMMIT_EMAIL = re.compile(r"(?i)^(?:\d+\+)?[\w-]+@users\.noreply\.github\.com$|^noreply@github\.com$|"
                                  r"^noreply@anthropic\.com$")
ANY_EMAIL = re.compile(r"[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")
PERSON = re.compile(rb"^(author|committer|tagger) (.*?) <([^>]*)>", re.M)


def scan_message(text, where, terms=()):
    """A commit or tag message: every rule, except that a co-author's no-reply address is what git hosts ask for. Private
    words are looked for first, so none can hide inside such an address."""
    found = term_hits(text, where, terms)
    clean = ANY_EMAIL.sub(lambda m: "" if ALLOWED_COMMIT_EMAIL.match(m.group(0)) else m.group(0), text)
    return found + scan_text(clean, where)


def parse_tree(data):
    """(mode, name) of each entry of a raw tree object."""
    pos, out = 0, []
    while pos < len(data):
        space = data.index(b" ", pos)
        nul = data.index(b"\0", space)
        out.append((data[pos:space].decode(), data[space + 1:nul].decode("utf-8", "surrogateescape")))
        pos = nul + 21
    return out


def scan_commit_or_tag(data, where, terms):
    head, _, body = data.partition(b"\n\n")
    found = []
    for role, name, email in PERSON.findall(head):
        email = email.decode("utf-8", "replace")
        if not ALLOWED_COMMIT_EMAIL.match(email):
            found.append(Finding("commit-email", where, 0, f"{role.decode()}, {mask(email)}"))
        found += scan_message(name.decode("utf-8", "replace"), where, terms)
    for line in head.split(b"\n"):
        if line.startswith(b"tag "):
            found += scan_message(line[4:].decode("utf-8", "replace"), where, terms)
    return found + scan_message(body.decode("utf-8", "replace"), where, terms)


def object_list(unreachable):
    """(sha, type, size) of what a push could carry: everything any ref reaches, tags inside tags included. With
    `unreachable`, every object in the store: what a failed commit or an old `git add` left behind, which never leaves
    this machine by a push."""
    check = "--batch-check=%(objectname) %(objecttype) %(objectsize)"
    if unreachable:
        return [row.split() for row in git("cat-file", "--batch-all-objects", check).decode().splitlines()]
    wanted = {line.split()[0] for line in git("rev-list", "--all", "--objects").decode("utf-8", "replace").splitlines()}
    wanted |= {line.split()[0] for line in git("for-each-ref", "--format=%(objectname)").decode().splitlines()}
    rows, queue, seen = [], sorted(wanted), set()
    with Objects() as store:
        while queue:
            sha = queue.pop()
            if sha in seen:
                continue
            seen.add(sha)
            kind, data = store.read(sha)
            rows.append([sha, kind, str(len(data))])
            if kind == "tag":
                queue.append(data.split(b"\n", 1)[0].split()[1].decode())
    return rows


def scan_history(terms=(), unreachable=False):
    """Every object a ref reaches: each commit's and tag's people and message, each name in each tree, each file that
    ever existed, and the names of the refs."""
    found = []
    refs = git("for-each-ref", "--format=%(refname)").decode("utf-8", "surrogateescape").split()
    for ref in refs:
        found += [Finding(f.rule, f"ref {ref}", 0, f.hint) for f in scan_message(ref, f"ref {ref}", terms)]
    objects = object_list(unreachable)
    named = {}
    for line in git("rev-list", "--all", "--objects").decode("utf-8", "surrogateescape").splitlines():
        sha, _, path = line.partition(" ")
        if path:
            named.setdefault(sha, path)
    commits = 0
    with Objects() as store:
        for sha, kind, size in objects:
            where = f"{kind} {sha[:12]}" + (f" {named[sha]}" if sha in named else "")
            if int(size) > MAX_BLOB:
                found.append(Finding("history-large-object", where, 0, f"{size} bytes"))
                continue
            _, data = store.read(sha)
            if kind == "blob":
                found += scan_content(data, where, terms, Path(named.get(sha, "")).suffix.lower())
            elif kind == "tree":
                for mode, name in parse_tree(data):
                    entry = f"{where}/{name}"
                    if mode == "160000":
                        found.append(Finding("submodule", entry, 0, "its content lives elsewhere"))
                    found += [Finding(f.rule, entry, 0, f.hint)
                              for f in scan_name(name + ("/x" if mode == "40000" else ""), terms)]
            else:
                commits += kind == "commit"
                found += scan_commit_or_tag(data, where, terms)
    return found, commits, len(objects)


# ------------------------------------------------------------------------------------------- what is published on GitHub

# The hidden marker a code review tool leaves on its own comment: a run's id, which says nothing of anyone.
REVIEW_MARKER = re.compile(r"<!-- claude-code-ultrareview-post:[0-9a-f-]{36} -->")
ATTACHMENT = re.compile(r"https://(?:github\.com/user-attachments/(?:assets|files)/[\w./-]+|"
                        r"(?:private-)?user-images\.githubusercontent\.com/[\w./%-]+)")


def gh_pages(endpoint):
    r = subprocess.run(["gh", "api", "--paginate", "--slurp", endpoint], capture_output=True, cwd=ROOT)
    if r.returncode:
        raise ScanError(f"a GitHub request failed with exit code {r.returncode}")
    pages = json.loads(r.stdout.decode("utf-8"))
    return [row for page in pages for row in (page if isinstance(page, list) else [page])]


class AllowedHosts(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urllib.parse.urlparse(newurl)
        if u.scheme != "https" or u.hostname not in ATTACHMENT_HOSTS:
            raise urllib.error.URLError("a redirect left the expected hosts")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    opener = urllib.request.build_opener(AllowedHosts)
    with opener.open(urllib.request.Request(url, headers={"User-Agent": "privacy-scan"}), timeout=60) as r:
        data = r.read(MAX_ATTACHMENT + 1)
    if len(data) > MAX_ATTACHMENT:
        raise ValueError("too large")
    return data


def scan_github(repo, terms=()):
    found, items, seen = [], 0, set()

    def text(where, *values):
        nonlocal found, items
        items += 1
        body = REVIEW_MARKER.sub("", "\n".join(str(v) for v in values if v))
        found += scan_message(body, f"github {where}", terms)
        for url in ATTACHMENT.findall(body):
            if url in seen:
                continue
            seen.add(url)
            try:
                found += scan_content(fetch(url), f"github attachment in {where}", terms)
            except (OSError, ValueError):
                found.append(Finding("github-unreadable", f"github attachment in {where}", 0, "could not be checked"))

    meta = gh_pages(f"repos/{repo}")[0]
    text("repository", meta.get("description"), meta.get("homepage"), " ".join(meta.get("topics") or []))
    for surface in ("has_wiki", "has_pages", "has_discussions"):
        if meta.get(surface):
            found.append(Finding("github-surface-unchecked", f"github {surface}", 0, "enabled, and not read by this scan"))
    for b in gh_pages(f"repos/{repo}/branches?per_page=100"):
        text(f"branch {b['name']}", b["name"])
    for t in gh_pages(f"repos/{repo}/tags?per_page=100"):
        text(f"tag {t['name']}", t["name"])
    prs = []
    for i in gh_pages(f"repos/{repo}/issues?state=all&per_page=100"):
        text(f"#{i['number']}", i.get("title"), i.get("body"))
        if "pull_request" in i:
            prs.append(i["number"])
    for c in gh_pages(f"repos/{repo}/issues/comments?per_page=100"):
        text(f"issue comment {c['id']}", c.get("body"))
    for c in gh_pages(f"repos/{repo}/pulls/comments?per_page=100"):
        text(f"review comment {c['id']}", c.get("body"), c.get("diff_hunk"), c.get("path"))
    for n in prs:
        pr = gh_pages(f"repos/{repo}/pulls/{n}")[0]
        text(f"#{n} branch", pr["head"]["ref"], pr["head"].get("label"))
        for c in gh_pages(f"repos/{repo}/pulls/{n}/reviews?per_page=100"):
            text(f"#{n} review {c['id']}", c.get("body"))
    for c in gh_pages(f"repos/{repo}/comments?per_page=100"):
        text(f"commit comment {c['id']}", c.get("body"), c.get("path"))
    for rel in gh_pages(f"repos/{repo}/releases?per_page=100"):
        text(f"release {rel.get('id')}", rel.get("tag_name"), rel.get("name"), rel.get("body"))
        for asset in rel.get("assets", []):
            text(f"release asset {asset['id']}", asset.get("name"))
            try:
                data = fetch(asset["browser_download_url"])
                found += scan_content(data, f"github release asset {asset['id']}", terms,
                                      Path(asset.get("name", "")).suffix.lower())
            except (OSError, ValueError):
                found.append(Finding("github-unreadable", f"github release asset {asset['id']}", 0, "could not be checked"))
    for page in gh_pages(f"repos/{repo}/actions/artifacts?per_page=100"):
        for art in page.get("artifacts", []):
            text(f"artifact {art['id']}", art.get("name"))
    return found, items


def read_terms(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [l.strip() for l in lines if l.strip() and not l.lstrip().startswith("#")]


def main(argv=None):
    ap = argparse.ArgumentParser(description="The privacy scan of this repository.")
    ap.add_argument("--history", action="store_true", help="also every object a branch, tag or other ref reaches")
    ap.add_argument("--unreachable", action="store_true", help="with --history: also objects no ref reaches")
    ap.add_argument("--github", action="store_true", help="also what is published on GitHub (needs gh)")
    ap.add_argument("--repo", default="owoevan-dev/refinish-skill", help="the GitHub repository for --github")
    ap.add_argument("--terms", help="a file outside the repository listing private words, one a line")
    ap.add_argument("--draft", action="append", default=[], help="a text about to be published; may be repeated")
    ap.add_argument("--show-paths", action="store_true", help="name the places found: for your own terminal, never CI")
    ap.add_argument("--json", action="store_true", help="the report as JSON")
    a = ap.parse_args(argv)
    try:
        terms = read_terms(a.terms) if a.terms else []
        found = scan_tree(terms)
        report = {"files": len(tracked_files()), "terms": len(terms)}
        for i, draft in enumerate(a.draft):
            found += scan_message(Path(draft).read_text(encoding="utf-8"), f"draft {i + 1}", terms)
        report["drafts"] = len(a.draft)
        if a.history:
            hist, report["commits"], report["objects"] = scan_history(terms, a.unreachable)
            found += hist
        if a.github:
            gh, report["github_items"] = scan_github(a.repo, terms)
            found += gh
    except ScanError as e:
        print(f"error: the privacy scan could not run: {e}", file=sys.stderr)
        return 2
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as e:
        print(f"error: the privacy scan could not run: {type(e).__name__}", file=sys.stderr)
        return 2
    found = sorted(set(found), key=lambda f: (f.rule, f.where, f.line))
    report["findings"] = len(found)
    report["by_rule"] = dict(sorted(Counter(f.rule for f in found).items()))
    if a.json:
        items = [{**f.public(), **({"where": f.where} if a.show_paths else {})} for f in found]
        print(json.dumps({**report, "items": items}, indent=1))
    else:
        for f in found:
            print(f.local() if a.show_paths else f)
        print(json.dumps(report))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
