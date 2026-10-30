#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python", "scipy"]
# ///
"""Measure a picture's finish as numbers a style file can be written from, and compare two measurements.

Usage:
  python scripts/measure_style.py PICTURE.png [--upscaled N] [--at-height PX] [--auto-parts K] [--out M.json]
  python scripts/measure_style.py SUBJECT.json [--image OTHER.png] [--out M.json]
  python scripts/measure_style.py --compare REFERENCE.json RESULT.json

A bare picture (a finished reference, cut out or not) gives the picture-wide numbers: line width, darkness and
colouring, line density, outline coverage, chroma, value range, texture. A subject file adds the per-kind numbers
(tones and their flatness, the shadow's share, the shadow's colour shift, the softness of the shadow's edge);
--image measures another picture of the same subject with its part map (a re-finished result). --compare prints
each number of both measurements and their difference, the closest first, for the replication loop in
references/replicating-a-style.md. Prints JSON. Exit codes: 0 done, 2 bad input.
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core import die, emit, load_rgba  # noqa: E402
from _measure import FINISH, style_metrics  # noqa: E402
from _style import kind_of, load_subject, subject_path  # noqa: E402


def auto_parts(img, alpha, k, upscaled=1):
    """Stand-in parts for a bare cut-out (a model sheet, a reference with no subject file): the figure's colours
    clustered by hue and chroma only (Lab a, b), so a material's lit and shaded tones fall in one cluster while
    different materials part; every cluster is measured as cloth."""
    import cv2
    import numpy as np
    from _core import lab
    import _lines
    within = alpha > 0.5
    line = _lines.find_lines(img, upscaled) > 0.3
    L = lab(img)
    sel = within & ~line
    ab = L[..., 1:][sel].astype(np.float32)
    _, labels, _ = cv2.kmeans(ab, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.5), 3,
                              cv2.KMEANS_PP_CENTERS)
    parts = np.zeros(alpha.shape, np.uint8)
    parts[sel] = labels.ravel() + 1
    return parts, ["cloth"] * k


def at_height(img, alpha, height):
    """The picture shrunk (premultiplied) so its figure is `height` px tall: line widths, the softness of edges and
    the darkness of thin lines depend on the pixel scale, so a result is measured at the references' own scale."""
    import cv2
    import numpy as np
    from _core import resize_premultiplied
    rows = np.nonzero(alpha.max(axis=1) > 0.5)[0]
    s = height / max(1, rows[-1] - rows[0] + 1) if rows.size else 1.0
    if s >= 1.0:
        return img, alpha
    h, w = alpha.shape
    return resize_premultiplied(img, alpha, (max(1, round(w * s)), max(1, round(h * s))), cv2.INTER_AREA)


def flatten(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        elif isinstance(v, list):
            for i, x in enumerate(v):
                out[f"{key}[{i}]"] = x
        elif isinstance(v, (int, float)) and v is not None:
            out[key] = v
    return out


def profile(measurements):
    """Several references' numbers as one target: the median of each number all of them have."""
    flats = [flatten(m) for m in measurements]
    keys = set.intersection(*(set(f) for f in flats))
    return {k: round(float(statistics.median(f[k] for f in flats)), 4) for k in sorted(keys)}


def compare(ref, res, only=None):
    a, b = flatten(ref), flatten(res)
    rows = []
    for k in sorted(set(a) & set(b)):
        if k == "unit_px" or (only and k not in only):
            continue
        d = b[k] - a[k]
        scale = max(abs(a[k]), 1e-6)
        rows.append({"metric": k, "reference": a[k], "result": b[k], "diff": round(d, 3),
                     "rel": round(abs(d) / scale, 3)})
    rows.sort(key=lambda r: r["rel"])
    return {"compared": len(rows), "only_reference": sorted(set(a) - set(b)), "only_result": sorted(set(b) - set(a)),
            "rows": rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", nargs="?")
    ap.add_argument("--upscaled", type=int, default=None)
    ap.add_argument("--auto-parts", type=int, default=0, metavar="K",
                    help="a bare cut-out: measure the per-part numbers on K hue clusters as stand-in parts")
    ap.add_argument("--at-height", type=float, default=0, metavar="PX",
                    help="a bare picture: measure it shrunk so its figure is PX tall (the references' own scale)")
    ap.add_argument("--image", help="with a subject file: measure this picture with the subject's part map")
    ap.add_argument("--out", help="also write the measurement to this file")
    ap.add_argument("--compare", nargs=2, metavar=("REFERENCE", "RESULT"))
    ap.add_argument("--finish", action="store_true",
                    help="with --compare: only the numbers of the finish itself, not of the scene's light")
    ap.add_argument("--profile", nargs="+", metavar="M.json",
                    help="several references' measurements as one target (the median of each number)")
    a = ap.parse_args()
    if a.profile:
        p = profile([json.loads(Path(q).read_text(encoding="utf-8")) for q in a.profile])
        if a.out:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.out).write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
        emit(p)
        return
    if a.compare:
        ref, res = (json.loads(Path(p).read_text(encoding="utf-8")) for p in a.compare)
        emit(compare(ref, res, FINISH if a.finish else None))
        return
    if not a.source:
        die("give a picture or a subject file, or --compare REFERENCE RESULT")
    if a.source.lower().endswith(".json"):
        sj = load_subject(a.source)
        from parts import load_or_build
        img, alpha, parts = load_or_build(sj)
        if a.image:
            img2, alpha2 = load_rgba(a.image)
            if alpha2.shape != alpha.shape:
                die(f"{a.image} is not the size of the subject's picture")
            img, alpha = img2, alpha2
        m = style_metrics(img, alpha, sj.get("upscaled", 1), parts, [kind_of(p) for p in sj["parts"]], sj.get("head_px"))
        m["source"] = a.image or str(subject_path(sj, sj["image"]))
    else:
        img, alpha = load_rgba(a.source)
        if a.at_height:
            img, alpha = at_height(img, alpha, a.at_height)
        parts, kinds = (auto_parts(img, alpha, a.auto_parts, a.upscaled or 1) if a.auto_parts else (None, None))
        m = style_metrics(img, alpha, a.upscaled or 1, parts, kinds)
        m["source"] = a.source
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    emit(m)


if __name__ == "__main__":
    main()
