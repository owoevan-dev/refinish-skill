#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Change a style file by the words people use about a finish: "softer shadows", "more vivid", "陰影柔一點",
"線を太く". Each word found moves its keys one step (scripts/_adjectives.py); --steps repeats it.

Usage:
  python scripts/tweak_style.py STYLE.json OUT.json "softer shadows, more vivid" [--steps 1]
  python scripts/tweak_style.py --list

STYLE.json is a bundled style's id or a path. Prints JSON: the words matched, each key's old and new value, the words
that have no meaning for this style's engine, and the measured number that should move (check it with
scripts/measure_style.py --compare before and after, references/replicating-a-style.md).
Exit codes: 0 done, 1 no word matched, 2 bad input.
"""
import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _adjectives import ADJECTIVES, DEFAULTS, match  # noqa: E402
from _core import die, emit  # noqa: E402
from _style import load_style, resolve_style  # noqa: E402


def get(d, path):
    for k in path.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def put(d, path, value):
    keys = path.split(".")
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def apply(style, changes):
    """The style with one step of each change; returns the list of (path, old, new)."""
    log = []
    for ch in changes:
        op = ch[0]
        if op in ("add", "mul"):
            _, path, v, lo, hi = ch
            old = get(style, path)
            base = DEFAULTS.get(path, 0.0) if old is None else old
            new = base + v if op == "add" else base * v
            new = round(float(min(hi, max(lo, new))), 4)
            put(style, path, new)
            log.append((path, old, new))
        elif op == "set":
            _, path, v = ch
            old = get(style, path)
            put(style, path, copy.deepcopy(v))
            log.append((path, old, v))
        elif op == "post":
            layer = ch[1]
            post = style.setdefault("post", [])
            old = next((l for l in post if l.get("op") == layer["op"]), None)
            if old is not None:
                post[post.index(old)] = dict(layer)
            else:
                post.append(dict(layer))
            log.append((f"post.{layer['op']}", old, layer))
        elif op == "unpost":
            post = style.get("post", [])
            gone = [l for l in post if l.get("op") == ch[1]]
            style["post"] = [l for l in post if l.get("op") != ch[1]]
            if gone:
                log.append((f"post.{ch[1]}", gone, None))
    return log


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("style", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("words", nargs="?")
    ap.add_argument("--steps", type=int, default=1)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        emit({k: {"words": e["words"], "engines": [g for g in e if g not in ("words", "measure")],
                  "measure": e["measure"]} for k, e in ADJECTIVES.items()})
        return
    if not (a.style and a.out and a.words):
        die("give STYLE.json OUT.json \"words\" (or --list)")
    st = load_style(resolve_style(a.style))
    eng = st["engine"]
    hits = match(a.words)
    if not hits:
        emit({"matched": [], "note": "no word matched: --list shows the words known"})
        sys.exit(1)
    new = copy.deepcopy(st)
    changed, skipped, measure = [], [], {}
    for k in hits:
        e = ADJECTIVES[k]
        changes = e.get(eng)
        if not changes:
            skipped.append(k)
            continue
        for _ in range(max(1, a.steps)):
            log = apply(new, changes)
        changed += [{"key": p, "was": o, "now": n} for p, o, n in log]
        measure[k] = e["measure"]
    if changed:
        new["id"] = Path(a.out).stem
        new["summary"] = st.get("summary", "") + f" (tweaked: {', '.join(k for k in hits if k not in skipped)})"
        Path(a.out).write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
    emit({"out": a.out if changed else None, "engine": eng, "matched": hits, "changed": changed,
          "not_for_this_engine": skipped, "check": measure})


if __name__ == "__main__":
    main()
