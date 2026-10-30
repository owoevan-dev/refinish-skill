#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python", "scipy"]
# ///
"""Grade a source picture before re-finishing it: what each family of styles can be expected to do with it.

Usage:
  python scripts/check_input.py SUBJECT.json
  python scripts/check_input.py PICTURE.png [--upscaled N]

With a subject file the part map is used too (built if needed): per-part flatness and the map's likely mistakes.
With a bare picture only the picture-wide checks run. Prints JSON:
  figure_px      the figure's height in pixels (the cut-out's, or the picture's)
  cut_out        whether the picture has a transparent background
  outline        share of the outline with a drawn line just inside it: all, left-facing, right-facing edges
  flatness       per part: how much of its lightness its own two or three tones explain (1.0 = flat cel paint)
  misfits        the part map's likely mistakes (fix them first: scripts/parts.py)
  grade          per style family: "supported", "best effort" or "not advised", each with its reasons
  advice         what would raise the grade (the source spec: references/source-spec.md)
Thresholds come from measured test pictures (references/input-check.md). Exit codes: 0 graded, 1 misfits in the
part map, 2 bad input.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _lines as ln_  # noqa: E402
from _core import Units, emit, load_rgba  # noqa: E402
from _measure import flatness, outline_coverage  # noqa: E402
from _parts import misfits  # noqa: E402
from _style import kind_of, load_subject, subject_path  # noqa: E402

OUTLINE_GOOD, OUTLINE_FAIR = 0.85, 0.65
SIDE_GAP = 0.12
FLAT_GOOD, FLAT_FAIR = 0.70, 0.62
MIN_FIGURE_PX = 2000


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="a subject file (.json) or a picture")
    ap.add_argument("--upscaled", type=int, default=None, help="for a bare picture: how many times it was enlarged")
    a = ap.parse_args()
    sj = None
    if a.source.lower().endswith(".json"):
        sj = load_subject(a.source)
        from parts import load_or_build
        img, alpha, parts = load_or_build(sj)
        upscaled = sj.get("upscaled", 1)
    else:
        img, alpha = load_rgba(a.source)
        parts = None
        upscaled = a.upscaled or 1
    U = Units(alpha, sj.get("head_px") if sj else None)
    cut_out = bool((alpha < 0.5).mean() > 0.05)
    report = {"source": a.source, "figure_px": int(U.height), "cut_out": cut_out}
    advice, grade = [], {}
    cov = None
    if cut_out:
        cov, _ = outline_coverage(img, alpha, upscaled)
        report["outline"] = cov
    flat = {}
    found = []
    if parts is not None:
        line = ln_.find_lines(img, upscaled) > 0.3
        names = [p["name"] for p in sj["parts"]]
        kinds = [kind_of(p) for p in sj["parts"]]
        flat = flatness(img, parts, names, kinds, line)
        report["flatness"] = flat
        found = misfits(sj, img, alpha, parts, scale=U.s)
        report["misfits"] = found
    flat_mean = float(np.mean(list(flat.values()))) if flat else None
    if flat_mean is not None:
        report["flatness_mean"] = round(flat_mean, 3)

    # ---- the cel family -------------------------------------------------------------------------------------------
    why = []
    level = "supported"
    if not cut_out:
        level = "not advised"
        why.append("no transparent background: the cel styles need the figure cut out (a figure fused with its "
                   "background loses its hair and edges); cut it out with scripts/cutout.py, or use a paint style "
                   "for the whole picture")
        advice.append("cut the figure out with scripts/cutout.py (references/cutout.md), or generate it on its own, "
                      "transparent or on a plain background (source-spec.md)")
    else:
        if cov["all"] < OUTLINE_FAIR or abs(cov["left"] - cov["right"]) > SIDE_GAP:
            level = "best effort"
            side = "right" if cov["right"] < cov["left"] else "left"
            why.append(f"only {cov['all']:.0%} of the outline is drawn ({side}-facing edges {cov[side]:.0%}): the "
                       "closed outline is drawn there, but a rim light's colour stays in the fill")
            advice.append("no rim light or backlight, a line all round on both sides (source-spec.md, cel)")
        elif cov["all"] < OUTLINE_GOOD:
            why.append(f"{cov['all']:.0%} of the outline is drawn; the closed outline fills the rest")
    if flat_mean is not None:
        soft = sorted(k for k, v in flat.items() if v < FLAT_FAIR)
        if flat_mean < FLAT_FAIR:
            level = "best effort" if level == "supported" else level
            why.append(f"soft shading (flatness {flat_mean:.2f}): flat tones may break into blotches")
            advice.append("hard-edged two-tone shading, flat colours (source-spec.md, cel level 2)")
        elif soft:
            why.append(f"soft parts ({', '.join(soft)}): one that comes out in blotches takes \"deblotch\": 4 in the "
                       "subject's rules (references/style-format.md)")
    grade["cel"] = {"level": level, "why": why}

    # ---- the paint family -----------------------------------------------------------------------------------------
    why = []
    level = "supported"
    if U.height < 1000:
        level = "best effort"
        why.append(f"the figure is {int(U.height)} px tall: strokes will be coarse")
    grade["paint"] = {"level": level, "why": why}

    if U.height < MIN_FIGURE_PX:
        advice.append(f"enlarge first: scripts/prep.py --scale 2 (the figure is {int(U.height)} px tall)")
    if found:
        advice.insert(0, "fix the part map's misfits first (scripts/parts.py)")
    report["grade"] = grade
    report["advice"] = list(dict.fromkeys(advice))
    emit(report)
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
