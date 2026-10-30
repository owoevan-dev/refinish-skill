#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python", "scipy"]
# ///
"""Build a subject's part map and check it.

Usage:
  python scripts/parts.py SUBJECT.json [--review REVIEW.jpg]

Writes <subject>.parts.png beside the subject file (0 outside the figure, then the parts in the order of the subject
file) and a review picture of the parts in false colour. Prints JSON: each part's pixel count and the map's likely
mistakes ("misfits": thick dark blobs labelled as a light part, a lock of hair painted as skin; large light blobs
labelled as a dark part). Fix a misfit by adding a colour sample or tightening a part's polygon, then run again.
Exit codes: 0 no misfits, 1 misfits found, 2 bad input.
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core import Units, emit, load_rgba  # noqa: E402
from _parts import misfits, part_map  # noqa: E402
from _style import load_subject, subject_path  # noqa: E402


def parts_path(sj):
    return Path(sj["_dir"]) / f"{sj['_stem']}.parts.png"


def build(sj):
    img, alpha = load_rgba(subject_path(sj, sj["image"]))
    parts = part_map(sj, img, alpha)
    cv2.imwrite(str(parts_path(sj)), parts)
    return img, alpha, parts


def load_or_build(sj):
    """The cached part map when it is newer than the subject file and its picture, else a fresh one."""
    pp = parts_path(sj)
    src = [Path(sj["_dir"]) / f"{sj['_stem']}.json", subject_path(sj, sj["image"])]
    if "regions" in sj:
        src.append(subject_path(sj, sj["regions"]))
    if pp.is_file() and all(pp.stat().st_mtime >= s.stat().st_mtime for s in src if s.is_file()):
        img, alpha = load_rgba(subject_path(sj, sj["image"]))
        parts = cv2.imread(str(pp), cv2.IMREAD_GRAYSCALE)
        if parts is not None and parts.shape == alpha.shape:
            return img, alpha, parts
    return build(sj)


def review(sj, img, alpha, parts, out):
    n = len(sj["parts"])
    pal = cv2.cvtColor(np.array([[[(i * 37) % 180, 200, 235] for i in range(n + 1)]], np.uint8), cv2.COLOR_HSV2BGR)[0]
    bgr = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2BGR).astype(np.float32)
    vis = (bgr * 0.35 + pal[parts].astype(np.float32) * 0.65).astype(np.uint8)
    vis[parts == 0] = (225, 225, 225)
    s = min(1.0, 1400.0 / vis.shape[0])
    vis = cv2.resize(vis, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    for j, p in enumerate(sj["parts"], start=1):
        cv2.rectangle(vis, (8, 8 + j * 22), (26, 24 + j * 22), tuple(int(v) for v in pal[j]), -1)
        cv2.putText(vis, p["name"], (32, 22 + j * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (30, 30, 30), 1)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), vis, [cv2.IMWRITE_JPEG_QUALITY, 88])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subject")
    ap.add_argument("--review", help="review picture (default: <subject>.parts.jpg beside the subject)")
    a = ap.parse_args()
    sj = load_subject(a.subject)
    img, alpha, parts = build(sj)
    U = Units(alpha, sj.get("head_px"))
    found = misfits(sj, img, alpha, parts, scale=U.s)
    rv = Path(a.review) if a.review else Path(sj["_dir"]) / f"{sj['_stem']}.parts.jpg"
    review(sj, img, alpha, parts, rv)
    emit({"parts": {p["name"]: int((parts == j).sum()) for j, p in enumerate(sj["parts"], start=1)},
          "misfits": found, "map": str(parts_path(sj)), "review": str(rv)})
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
