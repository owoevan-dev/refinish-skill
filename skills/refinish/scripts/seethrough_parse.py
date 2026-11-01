#!/usr/bin/env python3
"""A character's body parts and eyes read by models, for auto_parts.py --parse (optional; references/seethrough.md).

Usage (with the Python of the environment See-Through and SAM 2 are installed in):
  python scripts/seethrough_parse.py IMAGE.png PARSE.png [--seethrough DIR] [--sam2 DIR] [--eyes EYES.json]
                                     [--no-eyes] [--device cuda|cpu]

The parts: See-Through's part segmentation (github.com/shitagaki-lab/see-through, Apache-2.0), 19 body parts from a
model fine-tuned from Segment Anything. The picture is read whole, then with the face's box cut out and enlarged (the
model reads 1024 pixels a side, and a head is a small part of a figure), the head's parts taken from that reading.

The eyes: each of See-Through's eyes split by SAM 2 (github.com/facebookresearch/sam2, Apache-2.0) into its iris, its
white and its lashes (_eyes.py). An eye whose split looks wrong by its proportions is reported, and its split left out
(auto_parts.py reads that eye by colour, as without a parse), unless EYES.json (refinish-eyes/1) gives it clicks:
  {"format": "refinish-eyes/1", "eyes": [{"eye": 0, "iris": [[x, y]], "white": [[x, y]], "not": [[x, y]]},
                                         {"eye": 1, "keep": true}]}
"eye" is the eye's number in the report (left to right); points are in IMAGE's pixels; a click on the white is a click
off the iris too; "keep": the eye stays as drawn under every finish.

Neither model ships with this skill: references/seethrough.md says what to install. Writes PARSE.png: 0 outside the
figure or where no part is sure; See-Through's parts from 1 (PARSE_PARTS); then EYE_PARTS from 20 (an eye's iris, white,
lashes, or the whole eye kept). Writes <PARSE>.eyes.jpg: each eye enlarged with a grid of the picture's coordinates,
beside its split (red the iris, blue the white, green the lashes), the doubtful ones first. Prints JSON: the parts'
shares, the head's box, each eye (its number, box, status: auto, fixed, doubtful or kept; its doubts), the 'eyes'
pieces found below the nose and given to the mouth (eyes_below_nose), the seconds.
Exit codes: 0 done, 1 done with doubtful eyes, 2 bad input or a model not found.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _eyes  # noqa: E402
from _core import die, emit, load_rgba, write_image  # noqa: E402

from _parse_labels import EYE0, EYE_PARTS, PARSE_PARTS  # noqa: E402
HEAD_PARTS = ('hair', 'headwear', 'face', 'eyes', 'eyewear', 'ears', 'earwear', 'nose', 'mouth')
FACE_PARTS = ('face', 'eyes', 'eyewear', 'ears', 'earwear', 'nose', 'mouth')
WEIGHTS = ("24yearsold/l2d_sam_iter2", "checkpoint-18000.pt")
SAM2_CONFIG = "configs/sam2.1/sam2.1_hiera_l.yaml"
SAM2_CKPT = "checkpoints/sam2.1_hiera_large.pt"
EYES_FORMAT = "refinish-eyes/1"


def load_parser(st_dir, device):
    common = Path(st_dir) / "common"
    if not (common / "modules" / "semanticsam.py").is_file():
        die(f"no See-Through code at {st_dir} (expected common/modules/semanticsam.py there): give its folder with "
            "--seethrough or SEETHROUGH_DIR")
    sys.path.insert(0, str(common))
    try:
        from modules.semanticsam import SemanticSam
        from utils.torch_utils import init_model_from_pretrained
    except ImportError as e:
        die(f"See-Through's environment is missing a package ({e}): run this script with the Python of the environment "
            "See-Through is installed in")
    model = init_model_from_pretrained(WEIGHTS[0], module_cls=SemanticSam, weights_name=WEIGHTS[1],
                                       download_from_hf=True, model_args=dict(class_num=len(PARSE_PARTS)))
    return model.to(device=device)


def load_segmenter(sam2_dir, device):
    """SAM 2's image predictor, from its checkpoint in sam2_dir (or SAM2_CHECKPOINT); None when SAM 2 is missing."""
    try:
        from sam2.build_sam import build_sam2
        from sam2.sam2_image_predictor import SAM2ImagePredictor
    except ImportError:
        return None
    ckpt = os.environ.get("SAM2_CHECKPOINT") or (str(Path(sam2_dir) / SAM2_CKPT) if sam2_dir else None)
    if not ckpt or not Path(ckpt).is_file():
        die(f"no SAM 2 checkpoint at {ckpt}: give SAM 2's folder with --sam2 (its {SAM2_CKPT}) or the file with "
            "SAM2_CHECKPOINT, or run with --no-eyes")
    return SAM2ImagePredictor(build_sam2(SAM2_CONFIG, ckpt, device=device))


def read(model, rgb):
    """The parts' logits (19, h, w) for an RGB uint8 picture."""
    import torch
    with torch.inference_mode():
        return model.inference(rgb)[0].float().cpu().numpy()


def load_fixes(path):
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        die(f"cannot read the eyes file {path}: {e}")
    if not isinstance(d, dict) or d.get("format") != EYES_FORMAT or not isinstance(d.get("eyes"), list):
        die(f"{path}: 'format' must be \"{EYES_FORMAT}\" and 'eyes' a list (see references/seethrough.md)")
    fixes = {}
    for i, f in enumerate(d["eyes"]):
        if not isinstance(f, dict) or not isinstance(f.get("eye"), int):
            die(f"eyes[{i}]: an object with 'eye', the eye's number in the report")
        for k in ("iris", "white", "not"):
            pts = f.get(k, [])
            if not isinstance(pts, list) or not all(isinstance(q, list) and len(q) == 2 and
                                                    all(isinstance(v, (int, float)) for v in q) for q in pts):
                die(f"eyes[{i}].{k}: a list of points [x, y] in the picture's pixels")
        if not f.get("keep") and not f.get("iris"):
            die(f"eyes[{i}]: give the iris's points ('iris') or 'keep': true")
        fixes[f["eye"]] = f
    return fixes


def eye_crop(x, y, bw, bh, w, h, clicks=()):
    """An eye's crop for the segmenter: its box widened by half its width on each side and 0.6 of its height above
    and below, and further to hold every click given for it (a 'not' click on the brow above a small eye), inside
    the picture. (x0, y0, x1, y1)."""
    x0, y0 = x - bw // 2, y - int(0.6 * bh)
    x1, y1 = x + bw + bw // 2, y + bh + int(0.6 * bh)
    for cx, cy in clicks:
        x0, y0 = min(x0, int(cx) - 2), min(y0, int(cy) - 2)
        x1, y1 = max(x1, int(cx) + 3), max(y1, int(cy) + 3)
    return max(0, x0), max(0, y0), min(w, x1), min(h, y1)


def settle(status, iris, why):
    """An eye's status once split. An automatic split with doubts is doubtful. Clicks settle the doubts about its
    proportions, but not an iris that did not come out: that eye stays doubtful, keeps its parse label and is left to
    the colours."""
    if status == "fixed" and (iris is None or not iris.any()):
        return "doubtful"
    if status == "auto" and why:
        return "doubtful"
    return status


def gridded(crop, x0, y0, s):
    """A crop enlarged s times with a grid of the picture's coordinates."""
    t = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
    h, w = t.shape[:2]
    step = next((g for g in (5, 10, 20, 25, 50, 100) if g * s >= 40), 200)
    for gx in range(-(-x0 // step) * step, x0 + int(w / s) + 1, step):
        X = int(round((gx - x0) * s))
        if 0 <= X < w:
            t[:, X] = (0.5 * t[:, X] + (0, 55, 128)).astype(np.uint8)
            cv2.putText(t, str(gx), (X + 2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 60, 200), 1)
    for gy in range(-(-y0 // step) * step, y0 + int(h / s) + 1, step):
        Y = int(round((gy - y0) * s))
        if 0 <= Y < h:
            t[Y] = (0.5 * t[Y] + (0, 55, 128)).astype(np.uint8)
            cv2.putText(t, str(gy), (2, max(12, Y - 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 60, 200), 1)
    return t


def eyes_below_nose(lab_map):
    """The parse's 'eyes' pieces lying below the nose (with no nose, in the face's lowest 30 %) given to the mouth, in
    place: the part segmentation can read an open mouth as an eye (its teeth a white, its tongue a round iris: a
    laughing face with its eyes closed), and an eye is never below the nose. The floor is the nose's lowest pixel, so
    the lower eye of a tilted head stays an eye; a piece below the chin is no part of the face, and is left unsure (0).
    Returns how many pieces moved."""
    E, N, F, M = (PARSE_PARTS.index(p) + 1 for p in ("eyes", "nose", "face", "mouth"))
    k, cc, st, _ = cv2.connectedComponentsWithStats((lab_map == F).astype(np.uint8), connectivity=8)
    if k < 2:
        return 0
    c = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    top, chin = st[c, cv2.CC_STAT_TOP], st[c, cv2.CC_STAT_TOP] + st[c, cv2.CC_STAT_HEIGHT]
    k, _, st, _ = cv2.connectedComponentsWithStats((lab_map == N).astype(np.uint8), connectivity=8)
    if k > 1:
        c = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
        floor = st[c, cv2.CC_STAT_TOP] + st[c, cv2.CC_STAT_HEIGHT]
    else:
        floor = top + 0.7 * (chin - top)
    k, cc, _, cen = cv2.connectedComponentsWithStats((lab_map == E).astype(np.uint8), connectivity=8)
    low = [c for c in range(1, k) if cen[c][1] > floor]
    for c in low:
        lab_map[cc == c] = M if cen[c][1] <= chin else 0
    return len(low)


def split_eyes(segmenter, rgb, lab_map, fixes, device):
    """Each eye of the parse split into iris, white and lashes (written into lab_map from EYE0), its report and its
    review row."""
    import torch
    eyes_m = lab_map == PARSE_PARTS.index("eyes") + 1
    k, cc, st, cen = cv2.connectedComponentsWithStats(eyes_m.astype(np.uint8), connectivity=8)
    comps = sorted(range(1, k), key=lambda c: -st[c, cv2.CC_STAT_AREA])[:2]
    if len(comps) == 2 and st[comps[1], cv2.CC_STAT_AREA] < 0.25 * st[comps[0], cv2.CC_STAT_AREA]:
        comps = comps[:1]                                  # (the second piece a brow; the other eye hidden)
    h, w = eyes_m.shape
    report, rows = [], []
    for n, c in enumerate(sorted(comps, key=lambda c: cen[c][0])):
        x, y, bw, bh = (int(v) for v in st[c][:4])
        fix = fixes.get(n)
        x0, y0, x1, y1 = eye_crop(x, y, bw, bh, w, h, [] if not fix or fix.get("keep") else
                                  [q for k_ in ("iris", "white", "not") for q in fix.get(k_, [])])
        crop = np.ascontiguousarray(rgb[y0:y1, x0:x1])
        eye = (cc == c)[y0:y1, x0:x1]
        status, iris, white, lash = "kept", None, np.zeros_like(eye), np.zeros_like(eye)
        if not (fix and fix.get("keep")):
            ctx = torch.autocast("cuda", dtype=torch.bfloat16) if device == "cuda" else torch.autocast("cpu",
                                                                                                    enabled=False)
            with torch.inference_mode(), ctx:
                segmenter.set_image(crop)

                def predict(pts, labels):
                    masks, scores, _ = segmenter.predict(point_coords=pts, point_labels=labels, multimask_output=True)
                    return masks, scores

                def to(q):                                 # (a click off the picture lands on its edge)
                    return [(min(max(float(a) - x0, 0.0), x1 - x0 - 1.0), min(max(float(b) - y0, 0.0), y1 - y0 - 1.0))
                            for a, b in q]

                if fix:
                    iris, white, lash = _eyes.split(predict, crop, eye, to(fix["iris"]), to(fix.get("white", [])),
                                                    to(fix.get("not", [])))
                    status = "fixed"
                else:
                    iris, white, lash = _eyes.split(predict, crop, eye)
                    status = "auto"
        why = _eyes.doubts(iris, white, lash, eye) if status != "kept" else []
        status = settle(status, iris, why)
        blk = lab_map[y0:y1, x0:x1]
        if status == "kept":
            blk[eye] = EYE0 + 3
        elif status != "doubtful":
            for m_, v in ((iris, EYE0), (white, EYE0 + 1), (lash, EYE0 + 2)):
                if m_ is not None:
                    blk[m_ & eye] = v
        report.append({"eye": n, "centre": [int(cen[c][0]), int(cen[c][1])], "box": [x, y, x + bw, y + bh],
                       "status": status, **({"doubts": why} if why else {}),
                       "iris_px": 0 if iris is None else int(iris.sum()), "white_px": int(white.sum()),
                       "lash_px": int(lash.sum())})
        s = 300.0 / max(1, crop.shape[0])
        left = gridded(crop, x0, y0, s)
        right = crop.copy()
        for m_, col in ((iris, (230, 40, 40)), (white, (40, 120, 255)), (lash, (40, 200, 60))):
            if m_ is not None and m_.any():
                right[m_] = (0.35 * right[m_] + 0.65 * np.array(col)).astype(np.uint8)
        right = cv2.resize(right, (left.shape[1], left.shape[0]), interpolation=cv2.INTER_NEAREST)
        cv2.putText(right, f"#{n} {status}", (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
        rows.append((status != "doubtful", n, np.hstack([left, right])))
    return report, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--seethrough", default=os.environ.get("SEETHROUGH_DIR"),
                    help="the folder of See-Through's code (or SEETHROUGH_DIR)")
    ap.add_argument("--sam2", default=os.environ.get("SAM2_DIR"),
                    help="the folder of SAM 2's code, its checkpoints/ in it (or SAM2_DIR, or SAM2_CHECKPOINT)")
    ap.add_argument("--eyes", help="clicks for the eyes the report doubted (refinish-eyes/1)")
    ap.add_argument("--no-eyes", action="store_true", help="the parts only: the eyes left to auto_parts.py's colours")
    ap.add_argument("--device", default=None, help="cuda or cpu (default: cuda when there is one)")
    a = ap.parse_args()
    if Path(a.out).suffix.lower() != ".png":
        die(f"{a.out}: the parse is a map of labels; save it as a .png (a lossy format changes the labels)")
    if not a.seethrough:
        die("give the folder of See-Through's code with --seethrough or SEETHROUGH_DIR")
    img, alpha = load_rgba(a.image)
    within = alpha > 0.5
    if within.sum() < 1000:
        die(f"{a.image}: the figure is too small or the picture is fully transparent")
    fixes = load_fixes(a.eyes) if a.eyes else {}
    t0 = time.time()
    import torch
    device = a.device or ("cuda" if torch.cuda.is_available() else "cpu")
    model = load_parser(a.seethrough, device)
    a_ = np.clip(alpha, 0, 1)[..., None]
    rgb = (np.clip(img[..., :3] * a_ + (1 - a_), 0, 1) * 255).astype(np.uint8)        # (on white)
    logit = read(model, rgb)
    # the head again, cut out and enlarged: its parts from the second reading. The box is the face's (long hair would
    # take in half the figure), widened to the crown and the hair at its sides
    h, w = within.shape
    head_ids = [PARSE_PARTS.index(p) for p in HEAD_PARTS]
    face = (logit[[PARSE_PARTS.index(p) for p in FACE_PARTS]].max(0) > 0) & within
    head_box = None
    if face.sum() > 200:
        ys, xs = np.nonzero(face)
        x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        fw, fh = x1 - x0, y1 - y0
        x0, y0, x1, y1 = max(0, x0 - int(0.6 * fw)), max(0, y0 - int(0.7 * fh)), min(w, x1 + int(0.6 * fw)), \
            min(h, y1 + int(0.3 * fh))
        head_box = [x0, y0, x1, y1]
        sub = read(model, np.ascontiguousarray(rgb[y0:y1, x0:x1]))
        best = sub.argmax(0)
        mine = np.isin(best, head_ids) & (sub.max(0) > 0)
        blk = logit[:, y0:y1, x0:x1]
        blk[:, mine] = sub[:, mine]
    lab_map = np.where((logit.max(0) > 0) & within, logit.argmax(0) + 1, 0).astype(np.uint8)
    to_mouth = eyes_below_nose(lab_map)
    del model
    report, rows = [], []
    if not a.no_eyes:
        segmenter = load_segmenter(a.sam2, device)
        if segmenter is None:
            die("SAM 2 is not installed in this environment: install it (references/seethrough.md), or run with "
                "--no-eyes to leave the eyes to auto_parts.py's colours")
        else:
            report, rows = split_eyes(segmenter, rgb, lab_map, fixes, device)
    write_image(a.out, lab_map)
    review = None
    if rows:
        rows.sort(key=lambda r: (r[0], r[1]))
        wmax = max(r[2].shape[1] for r in rows)
        sheet = np.vstack([np.pad(r[2], ((0, 6), (0, wmax - r[2].shape[1]), (0, 0)), constant_values=255) for r in rows])
        review = str(Path(a.out).with_suffix("")) + ".eyes.jpg"
        write_image(review, cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR), (cv2.IMWRITE_JPEG_QUALITY, 90))
    fig = float(within.sum())
    names = PARSE_PARTS + EYE_PARTS
    out = {"parse": str(a.out), "parts": PARSE_PARTS, "eye_parts": EYE_PARTS,
           "share": {p: round(float((lab_map == k + 1).sum()) / fig, 4) for k, p in enumerate(names)
                     if (lab_map == k + 1).any()},
           "unsure": round(float(((lab_map == 0) & within).sum()) / fig, 4), "head_box": head_box,
           "eyes": report, **({"eyes_review": review} if review else {}),
           **({"eyes_below_nose": to_mouth} if to_mouth else {}), "device": device,
           "seconds": round(time.time() - t0, 1)}
    emit(out)
    sys.exit(1 if any(e["status"] == "doubtful" for e in report) else 0)


if __name__ == "__main__":
    main()
