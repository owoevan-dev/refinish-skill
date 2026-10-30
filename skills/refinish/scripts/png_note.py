#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Write a plain text note into a PNG (a tEXt chunk, readable by any PNG tool), or read the notes it holds.

Usage:
  python scripts/png_note.py OUT.png "AI-assisted: source generated with an image model; refinished with tv-cel"
  python scripts/png_note.py OUT.png --key Description "..."
  python scripts/png_note.py OUT.png --read

The pixels are not touched: the chunk goes right after the header. A note of the same key is replaced, in whichever
of the PNG's three text chunks it was (tEXt, the compressed zTXt, iTXt), so no reader finds the old one; notes of
other keys are kept. This is a plain note for honesty and bookkeeping, not signed Content Credentials (C2PA); see
references/legal-and-disclosure.md.
Prints JSON. Exit codes: 0 done, 2 bad input.
"""
import argparse
import json
import struct
import sys
import zlib
from pathlib import Path

SIG = b"\x89PNG\r\n\x1a\n"
# escaped JSON (still valid) when the console is not UTF-8: a note's text may hold characters its code page lacks
UTF8_OUT = (getattr(sys.stdout, "encoding", "") or "").lower().replace("-", "") in ("utf8", "utf8sig")


def chunks(data):
    i = 8
    while i < len(data):
        n = struct.unpack(">I", data[i:i + 4])[0]
        kind = data[i + 4:i + 8]
        yield i, n, kind, data[i + 8:i + 8 + n]
        i += 12 + n


def text_chunk(key, text):
    """A tEXt chunk (Latin-1, the PNG standard's plain text), or an iTXt chunk (UTF-8, uncompressed, no language)
    when the text holds anything outside Latin-1 (Chinese, Japanese): a tEXt would turn it into question marks."""
    try:
        kind, body = b"tEXt", key.encode("latin-1") + b"\x00" + text.encode("latin-1")
    except UnicodeEncodeError:
        # keyword, then: compression flag 0, method 0, an empty language tag, an empty translated keyword, the text
        kind, body = b"iTXt", key.encode("latin-1") + b"\x00" + b"\x00\x00" + b"\x00" + b"\x00" + text.encode("utf-8")
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)


TEXT = (b"tEXt", b"zTXt", b"iTXt")


def read_note(kind, body):
    """(keyword, text) of a tEXt, zTXt or iTXt chunk, else None."""
    if b"\x00" not in body:
        return None
    k, rest = body.split(b"\x00", 1)
    if kind == b"tEXt":
        return k.decode("latin-1"), rest.decode("latin-1")
    if kind == b"zTXt" and len(rest) >= 1:
        try:                                            # a compression method byte (0, zlib), then the text
            return k.decode("latin-1"), zlib.decompress(rest[1:]).decode("latin-1")
        except zlib.error:
            return None
    if kind == b"iTXt" and len(rest) >= 2:
        flag, rest = rest[0], rest[2:]
        parts = rest.split(b"\x00", 2)
        if len(parts) < 3:
            return None
        txt = zlib.decompress(parts[2]) if flag == 1 else parts[2]
        return k.decode("latin-1"), txt.decode("utf-8", errors="replace")
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("png")
    ap.add_argument("text", nargs="?")
    ap.add_argument("--key", default="Comment")
    ap.add_argument("--read", action="store_true")
    a = ap.parse_args()
    p = Path(a.png)
    data = p.read_bytes() if p.is_file() else b""
    if not data.startswith(SIG):
        print(json.dumps({"error": f"{a.png} is not a PNG"}))
        sys.exit(2)
    notes = {}
    for _, _, kind, body in chunks(data):
        kv = read_note(kind, body)
        if kv:
            notes[kv[0]] = kv[1]
    if a.read or a.text is None:
        print(json.dumps({"png": a.png, "notes": notes}, ensure_ascii=not UTF8_OUT))
        return
    out = bytearray(SIG)
    for i, n, kind, body in chunks(data):
        if kind in TEXT and body.split(b"\x00", 1)[0] == a.key.encode("latin-1"):
            continue                                        # the old note of this key is replaced
        out += data[i:i + 12 + n]
        if kind == b"IHDR":
            out += text_chunk(a.key, a.text)
    p.write_bytes(bytes(out))
    notes[a.key] = a.text
    print(json.dumps({"png": a.png, "notes": notes}, ensure_ascii=not UTF8_OUT))


if __name__ == "__main__":
    main()
