#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python", "scipy"]
# ///
"""Check a re-finished picture against its source for the mistakes a careful reviewer looks for first.

Usage:
  python scripts/check_output.py SUBJECT.json OUT.png [--style STYLE] [--review REVIEW.jpg] [--json REPORT.json]

The checks (references/checks.md): the part map's (a misfit, an eye read as hair or cloth, a patch of another colour
inside a part), the result's (a patch kept as drawn while the rest of its part changed, the white of an eye painted
as skin, a dark line where the frame cuts the figure, a halo) and the look checks O7 to O9 (a skin printed another
colour, a box round the features, mottled darks). With --style, the checks scripts/refinish.py runs for that style's
engine, and the same verdict; for an engine built on a cel finish, whose cel base is not in the file, the look checks
only. scripts/refinish.py runs them after every picture.
Prints JSON: the verdict (pass, warn, fail), the findings (each with its check, part, box and what to do) and the
review picture (each finding boxed and numbered on the result).
Exit codes: 0 pass or warnings only, 1 a FAIL, 2 bad input.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _check import look_checks, part_map_checks, result_checks, review, verdict  # noqa: E402
from _core import Units, die, emit, load_rgba  # noqa: E402
from _lines import find_lines  # noqa: E402
from _style import load_style, load_subject, resolve_style  # noqa: E402
from parts import load_or_build  # noqa: E402


def run_checks(sj, img, alpha, parts, out, out_alpha):
    U = Units(alpha, sj.get("head_px"))
    line = (find_lines(img, sj.get("upscaled", 1)) > 0.3) & (alpha > 0.5)
    return (part_map_checks(sj, img, alpha, parts, U, line)
            + result_checks(sj, img, alpha, parts, out, out_alpha, U, line))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subject")
    ap.add_argument("out")
    ap.add_argument("--style", help="the style the result was made in (a bundled id or a style file)")
    ap.add_argument("--review", help="review picture (default: <out>.check.jpg)")
    ap.add_argument("--json", help="also write the report here")
    a = ap.parse_args()
    sj = load_subject(a.subject)
    st = load_style(resolve_style(a.style)) if a.style else None
    img, alpha, parts = load_or_build(sj)
    out, out_alpha = load_rgba(a.out)
    if out.shape[:2] != img.shape[:2]:
        die(f"{a.out} is {out.shape[1]}x{out.shape[0]}, the subject's picture {img.shape[1]}x{img.shape[0]}")
    U = Units(alpha, sj.get("head_px"))
    if st is not None:
        # the checks refinish.py runs for the style's engine, on this file (an engine built on a cel finish has no cel
        # base here: the look checks only)
        from refinish import run_finish_checks
        found, _, _ = run_finish_checks(sj, st, img, alpha, parts, U, out, out_alpha, None)
    else:
        found = run_checks(sj, img, alpha, parts, out, out_alpha) + look_checks(sj, img, alpha, parts, out, U)
    rv = Path(a.review) if a.review else Path(a.out).with_suffix(".check.jpg")
    review(out, out_alpha, found, rv)
    res = {"verdict": verdict(found), "fail": sum(f["level"] == "FAIL" for f in found),
           "warn": sum(f["level"] == "WARN" for f in found), "findings": found, "review": str(rv)}
    if a.json:
        Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    emit(res)
    sys.exit(1 if res["verdict"] == "fail" else 0)


if __name__ == "__main__":
    main()
