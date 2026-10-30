#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python", "scipy"]
# ///
"""Write a style from reference pictures by measuring them: the loop of references/replicating-a-style.md, run
for you. The references' finish is measured; the bundled style nearest it is found on your subject; then each round
applies the style, measures the result the same way, and moves every number more than 10 % off one step toward the
references. The round with the most numbers within 10 % is kept.

Usage:
  python scripts/fit_style.py SUBJECT.json REF.png [REF2.png ...] --out STYLE.json
                              [--start auto|STYLE] [--rounds 4] [--height PX] [--clusters 6] [--work DIR]

REF: finished pictures in the look wanted (cut-outs are best; one to five, ideally from one set). They are measured
where they lie and never copied: the style written holds numbers only (references/replicating-a-style.md says what
can and cannot be carried over). Every picture, the references and the results alike, is measured shrunk to one
height (--height, by default the smallest figure among them) with the same stand-in parts (--clusters), so the
numbers compare like with like.
Prints JSON: the start style and why, every round's numbers against the target, the round kept, and the numbers
still off. Exit codes: 0 done, 2 bad input.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _core import die, emit, load_rgba  # noqa: E402
from _measure import FINISH, style_metrics  # noqa: E402
from _style import load_style, load_subject, resolve_style, subject_path  # noqa: E402
from measure_style import at_height, auto_parts, flatten, profile  # noqa: E402

CANDIDATES = ("tv-cel", "film-everyday-cel", "bold-ink-cel", "heavy-cel", "pastel-film-cel", "cel-90s")
TOL = 0.10


def figure_height(alpha):
    rows = np.nonzero(alpha.max(axis=1) > 0.5)[0]
    return int(rows[-1] - rows[0] + 1) if rows.size else alpha.shape[0]


def measure(path, height, k):
    img, alpha = load_rgba(path)
    img, alpha = at_height(img, alpha, height)
    parts, kinds = auto_parts(img, alpha, k)
    m = flatten(style_metrics(img, alpha, 1, parts, kinds))
    return {f: float(m[f]) for f in FINISH if f in m}


def score(target, got):
    """(numbers within the tolerance, the mean relative error)."""
    rel = [abs(got[f] - target[f]) / max(abs(target[f]), 1e-6) for f in target if f in got]
    return int(sum(r <= TOL for r in rel)), float(np.mean(rel)) if rel else 9.0


def render(subject, style, out):
    r = subprocess.run([sys.executable, str(HERE / "refinish.py"), subject, style, str(out), "--no-check"],
                       capture_output=True, text=True)
    if r.returncode:
        die(f"refinish.py failed on {style}: {r.stderr[-400:]}")


def get(d, path, dflt=None):
    for key in path.split("."):
        if not isinstance(d, dict) or key not in d:
            return dflt
        d = d[key]
    return d


def put(d, path, v):
    keys = path.split(".")
    for key in keys[:-1]:
        d = d.setdefault(key, {})
    d[keys[-1]] = v


def nudge(st, target, got, step):
    """One step of each number more than TOL off, toward the target; returns what moved. `step` holds each metric's
    step size, halved when the metric overshot last round."""
    moved = []
    drawn = get(st, "shading.follow", "drawn") == "drawn"

    def off(f):
        if f not in got or f not in target:
            return 0
        r = (got[f] - target[f]) / max(abs(target[f]), 1e-6)
        return 0 if abs(r) <= TOL else (1 if r > 0 else -1)

    def add(path, d, lo, hi, dflt):
        old = get(st, path, dflt)
        new = round(float(min(hi, max(lo, old + d))), 4)
        if new != old:
            put(st, path, new)
            moved.append((path, old, new))

    s = off("chroma.median")
    if s:
        old = get(st, "palette.chroma", 1.0)
        new = round(float(np.clip(old * np.clip(target["chroma.median"] / max(got["chroma.median"], 1e-3), 0.8, 1.25),
                                  0.4, 1.8)), 4)
        put(st, "palette.chroma", new)
        moved.append(("palette.chroma", old, new))
    s = off("line_width")
    if s:
        add("lines.grow", -s * 0.15 * step["line_width"], 0.0, 1.2, 0.0)
    s = off("line_hue_match")
    if s and target.get("line_hue_match", 0) >= 0.7 and get(st, "lines.colour", "own") == "ink":
        put(st, "lines.colour", "trace")
        moved.append(("lines.colour", "ink", "trace"))
    elif s and target.get("line_hue_match", 1) < 0.5 and get(st, "lines.colour", "own") in ("trace", "own"):
        moved.append(("lines.colour", get(st, "lines.colour", "own"), "ink"))
        put(st, "lines.colour", "ink")
    s = off("line_to_fill")
    if s:
        # the lines' lightness against their fill: moved in proportion to the miss (line_to_fill is a ratio of
        # lightnesses), so one round goes most of the way
        k = float(np.clip(target["line_to_fill"] / max(got["line_to_fill"], 1e-3), 0.7, 1.4)) ** step["line_to_fill"]
        col = get(st, "lines.colour", "own")
        if col == "trace":
            add("lines.trace.dark", get(st, "lines.trace.dark", 0.45) * (k - 1), 0.15, 0.85, 0.45)
        elif col == "own":
            add("lines.own.L", get(st, "lines.own.L", 16.0) * (k - 1), 4.0, 45.0, 16.0)
        else:                                                   # ink, or drawn: the ink's own lightness
            key = "lines.ink.ink" if col == "ink" else "lines.drawn.ink"
            ink = list(get(st, key, [18, 12, 10] if col == "ink" else [2, 0, 0]))
            ink[0] = round(float(np.clip(max(ink[0], 2.0) * k, 0.0, 45.0)), 2)
            put(st, key, ink)
            moved.append((key + "[0]", None, ink[0]))
    s = off("line_density")
    if s:
        if drawn:
            add("lines.keep.min_area_drawn", s * 0.4 * step["line_density"], 0.2, 10.0, 0.67)
        else:
            add("lines.keep.min_area", s * 2.0 * step["line_density"], 0.5, 40.0, 6.67)
        add("lines.cut", s * 0.02 * step["line_density"], 0.0, 0.25, 0.0)
    s = off("texture")
    if s:
        add("texture.grain", -s * 0.006 * step["texture"], 0.0, 0.03, 0.0)
    s = off("flatness_median")
    if s:
        add("shading.harden", -s * 0.04 * step["flatness_median"], 0.6, 1.0, 0.85)
    s = off("edge_softness_median")
    if s:
        add("shading.soft", -s * 0.4 * step["edge_softness_median"], 0.0, 3.0, 0.0)
    return moved


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("subject")
    ap.add_argument("refs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", default="auto")
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--height", type=int, default=0)
    ap.add_argument("--clusters", type=int, default=6)
    ap.add_argument("--work")
    a = ap.parse_args()
    sj = load_subject(a.subject)
    src = subject_path(sj, sj["image"])
    work = Path(a.work) if a.work else Path(a.out).with_suffix("").parent / (Path(a.out).stem + ".fit")
    work.mkdir(parents=True, exist_ok=True)
    for r in a.refs:
        if not Path(r).is_file():
            die(f"no reference picture {r}")
    heights = [figure_height(load_rgba(p)[1]) for p in [str(src)] + a.refs]
    H = a.height or min(heights)
    target = profile([measure(r, H, a.clusters) for r in a.refs])
    source = measure(str(src), H, a.clusters)
    # the start: the bundled style whose result on this subject is nearest the target
    starts = CANDIDATES if a.start == "auto" else (a.start,)
    tried = []
    for name in starts:
        out = work / f"start_{Path(name).stem}.png"
        render(a.subject, resolve_style(name), out)
        got = measure(str(out), H, a.clusters)
        tried.append((score(target, got), name, got))
    tried.sort(key=lambda t: (-t[0][0], t[0][1]))
    (best_score, start, got) = tried[0][0], tried[0][1], tried[0][2]
    st = load_style(resolve_style(start))
    st = {k: v for k, v in st.items() if not k.startswith("_")}
    rounds = [{"round": 0, "style": start, "within": best_score[0], "mean_rel": round(best_score[1], 3), "numbers": got}]
    best = (best_score, json.loads(json.dumps(st)), 0)
    step = {f: 1.0 for f in FINISH}
    last_sign = {}
    for i in range(1, a.rounds + 1):
        moved = nudge(st, target, got, step)
        if not moved:
            break
        sp = work / f"round{i}.json"
        st["id"] = Path(a.out).stem
        sp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
        out = work / f"round{i}.png"
        render(a.subject, str(sp), out)
        new = measure(str(out), H, a.clusters)
        # a number that crossed its target takes half a step from now on
        for f in FINISH:
            if f in new and f in target:
                sign = float(np.sign(new[f] - target[f]))
                if f in last_sign and sign != last_sign[f] and sign != 0:
                    step[f] *= 0.5
                last_sign[f] = sign
        sc = score(target, new)
        rounds.append({"round": i, "within": sc[0], "mean_rel": round(sc[1], 3), "moved": moved, "numbers": new})
        if (sc[0], -sc[1]) > (best[0][0], -best[0][1]):
            best = (sc, json.loads(json.dumps(st)), i)
        got = new
    style = best[1]
    style["id"] = Path(a.out).stem
    style["summary"] = (style.get("summary", "") + f" Fitted to {len(a.refs)} reference picture(s) by measurement "
                        f"from '{start}' ({best[0][0]} of {len(target)} finish numbers within 10 %).").strip()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(style, ensure_ascii=False, indent=1), encoding="utf-8")
    still = [{"metric": f, "target": target[f], "result": rounds[best[2]]["numbers"].get(f)} for f in target
             if f in rounds[best[2]]["numbers"] and
             abs(rounds[best[2]]["numbers"][f] - target[f]) / max(abs(target[f]), 1e-6) > TOL]
    emit({"out": a.out, "measured_at_height": H, "target": target, "source": source,
          "start": {"style": start, "tried": [{"style": n, "within": s[0], "mean_rel": round(s[1], 3)}
                                               for s, n, _ in tried]},
          "rounds": rounds, "kept": best[2], "still_off": still,
          "note": "line width and line density follow the drawing as much as the finish; a number the drawing holds "
                  "will not reach its target, and is better left than forced (references/replicating-a-style.md)"})


if __name__ == "__main__":
    main()
