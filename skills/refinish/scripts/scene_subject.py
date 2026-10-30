#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python", "scipy"]
# ///
"""Write a subject file for a scene (a background, a landscape, a room) instead of a figure: no face is looked for,
the picture's frame is its border (nothing is outlined along it), and the parts are the scene's materials found by
colour, not by lines: a painted background closes few areas with lines, so its colours are flattened (mean shift),
grouped into a few families, and each family's connected areas are its regions.

Usage:
  python scripts/scene_subject.py IMAGE.png SUBJECT.json [--families 10] [--detail 1.0]

Each area's kind is guessed from its colour and where it lies: `sky` (blue or pale, reaching the top of the picture,
and the clouds in it), `far` (blue with distance: far hills), `water` (blues low down), `foliage` (greens), `ground` (earth and grass low down), `wood`, `roof`, `stone`, `wall`,
else `cloth`; a part is one family of one kind. The kinds steer the scene effects of the styles (a woodblock sky's
bokashi, an ink wash's mist) and nothing else, so a wrong guess paints that area like any other; fix a kind in the
subject file when it matters. --detail above 1 keeps smaller areas apart (a busy street), below 1 merges more.
Prints JSON: the subject, the parts with their kind, colour and share. Exit codes: 0 done, 2 bad input.
"""
import argparse
import json
import math
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core import die, emit, lab, load_rgba, write_image  # noqa: E402

KINDS = ("sky", "far", "water", "foliage", "ground", "wood", "roof", "stone", "wall", "cloth")


def kind_of_area(c, top, bottom, touches_top):
    """An area's likely kind from its Lab colour and its vertical extent (fractions of the picture's height)."""
    L, a, b = (float(v) for v in c)
    C = math.hypot(a, b)
    h = math.degrees(math.atan2(b, a)) % 360
    mid = (top + bottom) / 2
    if touches_top and mid < 0.5 and ((190 <= h <= 300 and C > 5) or (L > 82 and C < 12)):
        return "sky"
    if 190 <= h <= 300 and C > 14 and mid > 0.55:
        return "water"                                 # (a night-tinted stone floor is bluish too, but greyer)
    if 190 <= h <= 330 and C > 5 and mid < 0.5 and L > 40:
        return "far"                                   # blue with distance: far hills, a far town (aerial perspective)
    if 100 <= h <= 175 and C > 10:
        return "ground" if (mid > 0.75 and L > 55) else "foliage"
    if 45 <= h <= 100 and C > 8 and mid > 0.6:
        return "ground"
    if 20 <= h <= 80 and C > 10 and L < 55:
        return "wood"
    if (h < 45 or h > 330) and C > 18:
        return "roof"
    if C < 9:
        return "stone" if L < 72 else "wall"
    return "wall" if L > 72 else "cloth"


def samples(mask, n=3):
    """A few points deep inside a mask's largest pieces."""
    k, cc, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    pts = []
    for c in (np.argsort(-st[1:, cv2.CC_STAT_AREA])[:n] + 1 if k > 1 else []):
        d = cv2.distanceTransform((cc == c).astype(np.uint8), cv2.DIST_L2, 3)
        y, x = np.unravel_index(int(np.argmax(d)), d.shape)
        pts.append([int(x), int(y)])
    return pts


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("image")
    ap.add_argument("subject")
    ap.add_argument("--families", type=int, default=10)
    ap.add_argument("--detail", type=float, default=1.0)
    a = ap.parse_args()
    if not Path(a.image).is_file():
        die(f"no picture {a.image}")
    img, alpha = load_rgba(a.image)
    within = alpha > 0.5
    H, W = alpha.shape
    # the work is done at about 900 px: a scene's materials are large, and mean shift is slow
    s = min(1.0, 900.0 / max(H, W))
    small = cv2.resize(img, (max(1, int(W * s)), max(1, int(H * s))), interpolation=cv2.INTER_AREA)
    h, w = small.shape[:2]
    bgr = (np.clip(small[..., ::-1], 0, 1) * 255).astype(np.uint8)
    flat = cv2.pyrMeanShiftFiltering(bgr, 10, 16)
    L = lab(flat[..., ::-1].astype(np.float32) / 255.0)
    feat = np.dstack([L[..., 0] * 0.6, L[..., 1], L[..., 2]]).reshape(-1, 3).astype(np.float32)
    rng = np.random.default_rng(5)
    sample = feat[rng.choice(len(feat), min(len(feat), 40000), replace=False)]
    cv2.setRNGSeed(5)
    _, _, cen = cv2.kmeans(sample, a.families, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 60, 0.2), 4,
                           cv2.KMEANS_PP_CENTERS)
    fam = np.argmin(((feat[:, None, :] - cen[None, :, :]) ** 2).sum(-1), axis=1).reshape(h, w).astype(np.uint8)
    # specks smoothed away (a mode filter), then each family's connected areas; areas below the floor join the
    # neighbouring area they share most border with
    for _ in range(2):
        fam = cv2.medianBlur(fam, 5)
    floor = max(12, int(0.0004 * h * w / max(0.25, a.detail)))
    reg = np.zeros((h, w), np.int32)
    nid = 0
    for f in range(a.families):
        k, cc = cv2.connectedComponents((fam == f).astype(np.uint8), connectivity=8)
        m = cc > 0
        reg[m] = cc[m] + nid
        nid += k - 1
    for _ in range(3):
        area = np.bincount(reg.ravel(), minlength=nid + 1)
        tiny = area < floor
        tiny[0] = False
        if not tiny[reg].any():
            break
        keep = np.where(tiny[reg], 0, reg)
        _, (iy, ix) = ndi.distance_transform_edt(keep == 0, return_indices=True)
        reg = np.where(tiny[reg], keep[iy, ix], reg)
    # renumber, and each area's colour (from the picture, not the flattened copy), extent and kind
    ids, reg = np.unique(reg, return_inverse=True)
    reg = reg.reshape(h, w).astype(np.int32) + (0 if ids[0] > 0 else 0)
    if ids[0] == 0:
        reg = reg                                       # (0 never survives: every pixel belongs to some area)
    reg += 1
    n = int(reg.max())
    Lp = lab(small)
    fam_of = np.zeros(n + 1, np.int32)
    fam_of[reg.ravel()] = fam.ravel()
    sl = ndi.find_objects(reg)
    groups = {}
    for i in range(1, n + 1):
        if sl[i - 1] is None:
            continue
        m = reg[sl[i - 1]] == i
        col = np.median(Lp[sl[i - 1]][m], axis=0)
        top, bottom = sl[i - 1][0].start / h, sl[i - 1][0].stop / h
        kind = kind_of_area(col, top, bottom, sl[i - 1][0].start <= max(1, h // 100))
        if kind == "sky":
            # a tall, narrow, greyish area reaching the top is a pillar or a door frame, not a piece of sky
            ah, aw = sl[i - 1][0].stop - sl[i - 1][0].start, sl[i - 1][1].stop - sl[i - 1][1].start
            if aw < 0.08 * w and ah > 0.25 * h and math.hypot(float(col[1]), float(col[2])) < 15:
                kind = "stone" if col[0] < 72 else "wall"
        groups.setdefault((int(fam_of[i]), kind), []).append(i)
    # a cloud is sky: a light, quiet area high in the picture whose border is mostly the sky's
    kind_of = {i: k_ for (f_, k_), regs_ in groups.items() for i in regs_}
    a_ = np.concatenate([reg[:, :-1].ravel(), reg[:-1, :].ravel()])
    b_ = np.concatenate([reg[:, 1:].ravel(), reg[1:, :].ravel()])
    diff = a_ != b_
    border = {}
    for x, y in zip(a_[diff], b_[diff]):
        border.setdefault(int(x), {}).setdefault(int(y), 0)
        border[int(x)][int(y)] += 1
        border.setdefault(int(y), {}).setdefault(int(x), 0)
        border[int(y)][int(x)] += 1
    moved = True
    while moved:
        moved = False
        for (f_, k_), regs_ in list(groups.items()):
            if k_ == "sky":
                continue
            for i in list(regs_):
                if sl[i - 1] is None:
                    continue
                m = reg[sl[i - 1]] == i
                col = np.median(Lp[sl[i - 1]][m], axis=0)
                mid = (sl[i - 1][0].start + sl[i - 1][0].stop) / 2 / h
                nb = border.get(i, {})
                tot = sum(nb.values())
                sky_b = sum(c_ for j, c_ in nb.items() if kind_of.get(j) == "sky")
                if (tot and sky_b / tot > 0.6 and mid < 0.45 and col[0] > 68
                        and math.hypot(float(col[1]), float(col[2])) < 22):
                    regs_.remove(i)
                    groups.setdefault((f_, "sky"), []).append(i)
                    kind_of[i] = "sky"
                    moved = True
        groups = {k_: v for k_, v in groups.items() if v}
    full = cv2.resize(reg.astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST).astype(np.int32)
    parts, used = [], {}
    area_full = np.bincount(full.ravel(), minlength=n + 1)
    for (f, kind), regs in sorted(groups.items(), key=lambda t: -sum(area_full[i] for i in t[1])):
        used[kind] = used.get(kind, 0) + 1
        name = kind if used[kind] == 1 else f"{kind}-{used[kind]}"
        regs = sorted(regs, key=lambda i: -area_full[i])
        m = np.isin(reg, regs)
        parts.append({"name": name, "family": name, "kind": kind, "regions": [int(i) for i in regs],
                      "_colour": np.median(Lp[m], axis=0), "_share": float(area_full[regs].sum() / (H * W)),
                      "_samples": [[int(x / s), int(y / s)] for x, y in samples(m)]})
    sub_path = Path(a.subject)
    sub_path.parent.mkdir(parents=True, exist_ok=True)
    rp = sub_path.with_name(f"{sub_path.stem}.regions.png")
    if n > 65535:
        die("more than 65535 areas: raise the floor with --detail below 1")
    write_image(str(rp), full.astype(np.uint16))
    try:
        image_rel = os.path.relpath(Path(a.image).resolve(), sub_path.resolve().parent).replace("\\", "/")
    except ValueError:
        image_rel = str(Path(a.image).resolve()).replace("\\", "/")
    sj = {"format": "refinish-subject/1", "image": image_rel, "upscaled": 1, "scene": True,
          "regions": rp.name, "families": {p["name"]: p["_samples"] for p in parts},
          "parts": [{k_: v for k_, v in p.items() if not k_.startswith("_")} for p in parts],
          "protect": [], "focal": [], "blush": []}
    sub_path.write_text(json.dumps(sj, ensure_ascii=False, indent=1), encoding="utf-8")
    emit({"subject": str(sub_path), "areas": n,
          "parts": [{"name": p["name"], "kind": p["kind"], "colour_lab": [round(float(v), 1) for v in p["_colour"]],
                     "share": round(p["_share"], 4)} for p in parts]})


if __name__ == "__main__":
    main()
