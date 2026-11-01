#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python", "scipy"]
# ///
"""Colour cards (refinish-palette/1): write one into a subject, derive the colours it leaves out, read the swatches
of a colour card picture, draw a card to show before finishing.

Usage:
  python scripts/palette.py apply SUBJECT.json CARD.json OUT_SUBJECT.json [--touch TOUCH.json]
  python scripts/palette.py zoom PICTURE.png x0,y0,x1,y1 [--out zoom.jpg] [--width 1000]
  python scripts/palette.py derive "#c8442f" [--kind skin]
  python scripts/palette.py read CARD.png [--at x,y[,name] ...] [--out swatches.jpg]
  python scripts/palette.py board CARD.json OUT.png [--subject SUBJECT.json]

apply: every part the card covers (by name, then iris, kind, role) gets its colour model as rules, with the shadow,
second shadow and highlight the card leaves out derived by hue (references/palette-design.md in the recolor skill);
the parts it does not cover keep their own colours. Prints JSON: each part, where its colours came from, the colours.
--touch: the touches written after looking at a result (refinish-touch/1, the recolor skill's palette-format.md),
each point's colour given to a part, a colour of its own or the drawing; the report gives each touch's reach, and
<OUT_SUBJECT>.touch.jpg shows it.
zoom: a box of a picture enlarged with a grid of its coordinates, to read a touch's points off a result (a point
read off the whole figure's grid is often a few dozen pixels off).
derive: the shadow, second shadow and highlight one base colour gets. read: with --at, the median colour round each
point; without, the flat swatches it finds, numbered on --out for reading the card's labels against. board: the card
as swatches (base, shadow, second shadow, highlight per entry), for the person to approve.
Exit codes: 0 done, 2 bad input.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _colour as C  # noqa: E402
import _palette as P  # noqa: E402
from _core import die, emit, lab, load_rgba, write_image  # noqa: E402
from _style import kind_of, load_subject  # noqa: E402
from parts import load_or_build  # noqa: E402


TOUCH_COLOURS = [(255, 64, 160), (0, 200, 255), (255, 200, 0), (120, 255, 80), (255, 110, 40), (170, 110, 255)]


def touch_report(out_sj, img, alpha, dst):
    """Where each touch reaches: its pixels, box and share of the figure, and a preview beside the new subject
    (<out>.touch.jpg: each touch's reach tinted and numbered on the picture), to look at before finishing."""
    import _recolour as rc_
    from _core import Units
    U = Units(alpha, out_sj.get("head_px"))
    fig = max(1, int((alpha > 0.5).sum()))
    eye_boxes = rc_.box_fade({"protect": [b for b in out_sj.get("protect", []) if "eye" in b.get("name", "")]},
                             *alpha.shape) > 0
    kind = {p["name"]: kind_of(p) for p in out_sj["parts"]}
    a_ = np.clip(alpha, 0, 1)[..., None]
    view = (np.clip(img[..., :3] * a_ + (1 - a_), 0, 1) * 255).astype(np.uint8)          # (on white)
    rows = []
    for i, (m, t) in enumerate(rc_.touch_masks(out_sj, img, alpha, U)):
        what = {"as": t["as"]} if "as" in t else {"to": t["to"]["base"]} if "to" in t else {"keep": True}
        n = int(m.sum())
        row = {"touch": i, **what, "px": n, "share": round(n / fig, 4)}
        if n:
            ys, xs = np.nonzero(m)
            row["box"] = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
            c = np.array(TOUCH_COLOURS[i % len(TOUCH_COLOURS)], np.float32)
            view[m] = (0.35 * view[m] + 0.65 * c).astype(np.uint8)
            edge = m & ~(cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
            view[edge] = (0, 0, 0)
            x0, y0 = row["box"][:2]
            cv2.putText(view, str(i), (x0, max(14, y0 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
            cv2.putText(view, str(i), (x0, max(14, y0 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, tuple(int(v) for v in c), 1)
            notes = []
            bw, bh = row["box"][2] - row["box"][0], row["box"][3] - row["box"][1]
            if "box" not in t and max(bw, bh) > U.len(2 * rc_.TOUCH_REACH):
                notes.append("reaches well beyond its points: look at the preview (a lower tol, or a box, holds it in)")
            if "as" in t and kind.get(t["as"]) == "eyes" and eye_boxes.any() and (m & ~eye_boxes).any():
                notes.append(f"{int((m & ~eye_boxes).sum())} of its pixels lie outside the eyes' boxes")
            if notes:
                row["note"] = "; ".join(notes)
        else:
            row["note"] = "reaches nothing: the point is off the figure"
        rows.append(row)
    preview = dst.with_suffix(".touch.jpg")
    write_image(str(preview), cv2.cvtColor(view, cv2.COLOR_RGB2BGR), (cv2.IMWRITE_JPEG_QUALITY, 90))
    return rows, str(preview)


def cmd_apply(a):
    sj = load_subject(a.subject)
    card = P.load_palette(a.card)
    touches = P.load_touch(a.touch) if a.touch else None
    img, alpha, parts = load_or_build(sj)
    stats = P.part_stats(sj, img, alpha, parts)
    out = P.apply(sj, card, stats, touches)
    # paths in the subject are relative to it: keep them pointing at the same files from the new place
    src_dir, dst = Path(sj["_dir"]), Path(a.out).resolve()
    for key in ("image", "regions"):
        if key in out and not Path(out[key]).is_absolute():
            q = (src_dir / out[key]).resolve()
            try:
                out[key] = str(q.relative_to(dst.parent)).replace("\\", "/")
            except ValueError:
                out[key] = str(q).replace("\\", "/")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    rec = out["recolour"]["parts"]
    kept = [p["name"] for p in sj["parts"] if p["name"] not in rec]
    report = {"subject": str(dst), "card": card["name"],
              "recoloured": {n: {k: v[k] for k in ("from", "base", "shadow", "deep", "highlight")}
                             for n, v in rec.items()},
              "kept_as_drawn": kept}
    if touches:
        report["touches"], report["touch_preview"] = touch_report(out, img, alpha, dst)
    emit(report)


GRID = np.array([0, 110, 255], np.float32)


def cmd_zoom(a):
    img, alpha = load_rgba(a.picture)
    h, w = alpha.shape
    try:
        x0, y0, x1, y1 = (int(float(v)) for v in a.box.split(","))
    except ValueError:
        die(f"box '{a.box}': x0,y0,x1,y1 on the picture")
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        die(f"box '{a.box}' holds almost none of the {w}x{h} picture")
    a_ = np.clip(alpha[y0:y1, x0:x1], 0, 1)[..., None]
    crop = (np.clip(img[y0:y1, x0:x1, :3] * a_ + (1 - a_), 0, 1) * 255).astype(np.uint8)
    s = max(1.0, a.width / (x1 - x0))
    big = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST)
    step = next((g for g in (5, 10, 20, 25, 50, 100, 200, 500) if g * s >= 48), 1000)
    for gx in range(-(-x0 // step) * step, x1, step):
        X = int(round((gx - x0) * s))
        big[:, X] = (0.5 * big[:, X] + 0.5 * GRID).astype(np.uint8)
        cv2.putText(big, str(gx), (X + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 70, 200), 1)
    for gy in range(-(-y0 // step) * step, y1, step):
        Y = int(round((gy - y0) * s))
        big[Y] = (0.5 * big[Y] + 0.5 * GRID).astype(np.uint8)
        cv2.putText(big, str(gy), (2, Y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 70, 200), 1)
    out = a.out or str(Path(a.picture).with_suffix("")) + f".zoom_{x0}_{y0}.jpg"
    write_image(out, cv2.cvtColor(big, cv2.COLOR_RGB2BGR), (cv2.IMWRITE_JPEG_QUALITY, 92))
    emit({"zoom": out, "box": [x0, y0, x1, y1], "scale": round(s, 2), "grid": step})


def cmd_derive(a):
    c = C.parse_hex(a.colour)
    if c is None:
        die(f"'{a.colour}' is not a hex colour such as #c8442f")
    d = P.derive(c, a.kind)
    emit({"base": C.to_hex(c), "kind": a.kind, **{k: C.to_hex(v) for k, v in d.items()}})


def cmd_read(a):
    img, alpha = load_rgba(a.card)
    f = lab(img)
    h, w = alpha.shape
    found = []
    if a.at:
        for s in a.at:
            v = s.split(",")
            if len(v) < 2:
                die(f"--at {s}: give x,y or x,y,name")
            try:
                x, y = int(v[0]), int(v[1])
            except ValueError:
                die(f"--at {s}: x and y are whole numbers of pixels")
            if not (0 <= x < w and 0 <= y < h):
                die(f"--at {s}: outside the picture (x 0 to {w - 1}, y 0 to {h - 1})")
            r = max(2, int(0.006 * max(h, w)))
            box = f[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1].reshape(-1, 3)
            col = np.median(img[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1].reshape(-1, 3), axis=0)
            found.append({"name": v[2] if len(v) > 2 else f"#{len(found) + 1}", "at": [x, y], "hex": C.to_hex(col),
                          "spread": round(float(np.std(box[:, 0])), 1)})
    else:
        # flat swatches: areas of one colour (little variation round each pixel), large and roughly rectangular
        loc = cv2.blur(f, (7, 7))
        var = cv2.blur(f * f, (7, 7)) - loc * loc
        flat = (np.sqrt(np.maximum(var.sum(-1), 0)) < 2.5) & (alpha > 0.5)
        n, lbl, st, _ = cv2.connectedComponentsWithStats(flat.astype(np.uint8), connectivity=4)
        for i in range(1, n):
            x0, y0, bw, bh, ar = st[i]
            if ar < 0.0015 * h * w or ar < 0.75 * bw * bh:
                continue
            m = lbl == i
            col = np.median(img[m], axis=0)
            found.append({"name": f"#{len(found) + 1}", "box": [int(x0), int(y0), int(x0 + bw), int(y0 + bh)],
                          "hex": C.to_hex(col)})
        if a.out:
            vis = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
            for s in found:
                x0, y0, x1, y1 = s["box"]
                cv2.rectangle(vis, (x0, y0), (x1 - 1, y1 - 1), (0, 0, 255), 2)
                cv2.putText(vis, s["name"], (x0 + 4, y0 + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            write_image(a.out, vis, [cv2.IMWRITE_JPEG_QUALITY, 90])
    emit({"card": a.card, "swatches": found, **({"preview": a.out} if a.out and not a.at else {})})


def cmd_board(a):
    card = P.load_palette(a.card)
    rows = [(f"part: {n}", e, "cloth") for n, e in card["parts"].items()]
    rows += [("iris", card["iris"], "eyes")] if card["iris"] is not None else []
    rows += [(f"kind: {k}", e, k) for k, e in card["kinds"].items()]
    rows += [(f"role: {k}", e, "cloth") for k, e in card["roles"].items()]
    if a.subject:
        sj = load_subject(a.subject)
        kinds = {p["name"].lower(): kind_of(p) for p in sj["parts"]}
        rows = [(lb, e, kinds.get(lb.split(": ", 1)[-1], k)) for lb, e, k in rows]
    if not rows:
        die(f"{a.card} has no entries")
    sw, gap, lab_w, rh = 120, 10, 330, 92
    W = lab_w + 4 * (sw + gap) + 20
    H = 60 + len(rows) * (rh + gap)
    vis = np.full((H, W, 3), 250, np.uint8)
    cv2.putText(vis, f"{card['name']}   base | shadow | second shadow | highlight", (16, 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (40, 36, 34), 2)
    for i, (lb, e, kind) in enumerate(rows):
        y = 60 + i * (rh + gap)
        full = P.full_entry(e, kind, card["rule"])
        cv2.putText(vis, lb[:26], (16, y + rh // 2 + 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (40, 36, 34), 2)
        for k, slot in enumerate(P.SLOTS):
            x = lab_w + k * (sw + gap)
            c = full[slot]
            vis[y:y + rh, x:x + sw] = (np.asarray(c)[::-1] * 255).astype(np.uint8)
            given = slot in e
            ink = (255, 255, 255) if lab(np.asarray(c, np.float32).reshape(1, 1, 3))[0, 0, 0] < 55 else (30, 30, 30)
            cv2.putText(vis, C.to_hex(c) + ("" if given else " *"), (x + 4, y + rh - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        ink, 1)
    cv2.putText(vis, "* derived from the base", (16, H - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (90, 86, 82), 1)
    write_image(a.out, vis, [cv2.IMWRITE_PNG_COMPRESSION, 6] if a.out.lower().endswith(".png") else ())
    emit({"board": a.out, "rows": len(rows)})


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("apply")
    p.add_argument("subject")
    p.add_argument("card")
    p.add_argument("out")
    p.add_argument("--touch")
    p = sub.add_parser("zoom")
    p.add_argument("picture")
    p.add_argument("box")
    p.add_argument("--out")
    p.add_argument("--width", type=int, default=1000)
    p = sub.add_parser("derive")
    p.add_argument("colour")
    p.add_argument("--kind", default="cloth")
    p = sub.add_parser("read")
    p.add_argument("card")
    p.add_argument("--at", nargs="*")
    p.add_argument("--out")
    p = sub.add_parser("board")
    p.add_argument("card")
    p.add_argument("out")
    p.add_argument("--subject")
    a = ap.parse_args()
    {"apply": cmd_apply, "zoom": cmd_zoom, "derive": cmd_derive, "read": cmd_read, "board": cmd_board}[a.cmd](a)


if __name__ == "__main__":
    main()
