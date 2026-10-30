#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python", "scipy"]
# ///
"""Mix finishes on one picture: a base finish, and layers of other finishes laid over it, each limited to some of the
picture's parts or areas and blended in (the clothes in watercolour and the face in TV cel; a screentone multiplied
over a watercolour; a heavy cel with 30 % of the film everyday look).

Usage:
  python scripts/recipe.py RECIPE.json OUT.png [--no-check]

RECIPE.json (references/recipes.md):
  {"format": "refinish-recipe/1", "subject": "subject.json", "base": "tv-cel",
   "layers": [{"style": "watercolour", "where": ["cloth", "cloth-white"], "blend": "normal", "opacity": 1.0}],
   "post": [...], "hour": "night"}

`base` and each layer's `style` are a bundled style's id, a style file's path, or "source" (the picture as it is).
`where` names parts, kinds or areas (face, eyes, mouth, features, lines, outline, figure), or is
{"only": [...], "not": [...], "box": [x0, y0, x1, y1]}; every layer's edge is feathered (`feather`, u, 1.5).
Every finish is rendered once, with the guard and the checks refinish.py gives it (the look checks O7 to O9 included).
Prints JSON: the output, each finish and its check's verdict, and each layer's share of the figure.
Exit codes: 0 done; 1 done, with a FAIL in a finish's checks to look at; 2 bad input.
"""
import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core import Units, die, ellipse_mask, emit, lab, rgb, save_rgba  # noqa: E402
from _style import KINDS, kind_of, load_style, load_subject, resolve_style, rule  # noqa: E402
from parts import load_or_build  # noqa: E402

RECIPE_FORMAT = "refinish-recipe/1"
AREAS = ("face", "eyes", "mouth", "features", "lines", "outline", "figure", "all")
SCENE_KINDS = ("sky", "far", "water", "foliage", "ground", "wood", "roof", "stone", "wall")
BLENDS = ("normal", "multiply", "screen", "overlay", "soft-light", "darken", "lighten", "colour", "lightness")


# -------------------------------------------------------------------------------------------------------- the finishes

def render(ref, sj, img, alpha, parts, U, check):
    """One finish of the picture, as refinish.py makes it: (RGB, alpha, record)."""
    if ref == "source":
        return img, alpha, {"style": "source"}
    from refinish import RESIZING, finish
    st = load_style(resolve_style(ref))
    if st["engine"] in RESIZING:
        die(f"'{ref}' gives a picture of another size (a pixel sprite, a sticker's border, a neon glow): it cannot "
            "be mixed")
    sj_g, parts_g, guard = sj, parts, {}
    if st["engine"] not in ("deai", "duotone"):
        from _guard import guard_parts
        sj_g, parts_g, guard = guard_parts(sj, st, img, alpha, parts, U, rule)
    out, out_alpha, info = finish(sj_g, st, img, alpha, parts_g, U, SimpleNamespace(seed=None, palette_from=None))
    cel = info.pop("_cel", None)
    engine_out = out
    if st.get("post"):
        import _post
        out = _post.apply(st["post"], out, out_alpha, parts_g, sj_g, U, seed=st.get("seed", 7))
    rec = {"style": st.get("id", str(ref)), "engine": st["engine"]}
    if check:
        from _check import verdict
        from refinish import run_finish_checks
        found, on, _ = run_finish_checks(sj_g, st, img, alpha, parts_g, U, engine_out, out_alpha, cel)
        rec["check"] = {"verdict": verdict(found), "fail": sum(f["level"] == "FAIL" for f in found),
                        "findings": [f"{f['id']} {f['level']} {f['part']}: {f['what']} at {f['box']}"
                                     for f in found if f["level"] == "FAIL"][:5]}
        if on:
            rec["check"]["on"] = on
    return out, out_alpha, rec


# ------------------------------------------------------------------------------------------------------------ the masks

class Selector:
    """Masks of the picture by name: a part's name, a kind, or an area."""

    def __init__(self, sj, img, alpha, parts, U):
        self.sj, self.img, self.alpha, self.parts, self.U = sj, img, alpha, parts, U
        self.within = alpha > 0.5
        self.names = [p["name"] for p in sj["parts"]]
        self.kinds = [kind_of(p) for p in sj["parts"]]
        self._lines = None

    def word(self, w):
        h, wd = self.alpha.shape
        if w in ("figure", "all"):
            return self.within.copy()
        if w in ("face", "eyes", "mouth", "features"):
            m = np.zeros((h, wd), bool)
            if w == "face":
                m |= ellipse_mask(h, wd, self.sj.get("focal", [])) > 0.5
            for p in self.sj.get("protect", []):
                is_eye = "eye" in p["name"]
                if w in ("face", "features") or (w == "eyes" and is_eye) or (w == "mouth" and not is_eye):
                    x0, y0, x1, y1 = (int(v) for v in p["box"])
                    m[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
            return m & self.within
        if w == "lines":
            if self._lines is None:
                from _lines import find_lines
                ln = find_lines(self.img, self.sj.get("upscaled", 1)) > 0.3
                self._lines = cv2.dilate(ln.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            return self._lines & self.within
        if w == "outline":
            d = cv2.distanceTransform(self.within.astype(np.uint8), cv2.DIST_L2, 3)
            return self.within & (d <= self.U.len(3.0))
        m = np.zeros((h, wd), bool)
        hit = False
        if w in self.names:
            m |= self.parts == self.names.index(w) + 1
            hit = True
        if w in KINDS or w in SCENE_KINDS:
            m |= np.isin(self.parts, [j for j, k in enumerate(self.kinds, start=1) if k == w])
            hit = True
        if not hit:
            die(f"'{w}' is not a part ({', '.join(self.names)}), a kind ({', '.join(KINDS + SCENE_KINDS)}) or an area "
                f"({', '.join(AREAS)})")
        return m & self.within

    def where(self, spec):
        if spec is None or spec == "all":
            return self.within.copy()
        if isinstance(spec, str):
            spec = [spec]
        if isinstance(spec, list):
            spec = {"only": spec}
        only = spec.get("only")
        m = self.within.copy() if not only else np.any([self.word(w) for w in only], axis=0)
        for w in spec.get("not", []):
            m &= ~self.word(w)
        if "box" in spec:
            x0, y0, x1, y1 = (int(v) for v in spec["box"])
            b = np.zeros_like(m)
            b[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
            m &= b
        return m


# ----------------------------------------------------------------------------------------------------------- blending

def _soft_light(b, l_):
    d = np.where(b <= 0.25, ((16 * b - 12) * b + 4) * b, np.sqrt(np.clip(b, 0, 1)))
    return np.where(l_ <= 0.5, b - (1 - 2 * l_) * b * (1 - b), b + (2 * l_ - 1) * (d - b))


def blend(base, layer, mode):
    """The blend modes of a paint program, on the picture's own (sRGB) values; colour and lightness in Lab."""
    b, l_ = np.clip(base, 0, 1), np.clip(layer, 0, 1)
    if mode == "normal":
        return l_
    if mode == "multiply":
        return b * l_
    if mode == "screen":
        return 1 - (1 - b) * (1 - l_)
    if mode == "overlay":
        return np.where(b < 0.5, 2 * b * l_, 1 - 2 * (1 - b) * (1 - l_))
    if mode == "soft-light":
        return _soft_light(b, l_)
    if mode == "darken":
        return np.minimum(b, l_)
    if mode == "lighten":
        return np.maximum(b, l_)
    lb, ll = lab(b), lab(l_)
    if mode == "colour":
        return rgb(np.concatenate([lb[..., :1], ll[..., 1:]], -1))
    if mode == "lightness":
        return rgb(np.concatenate([ll[..., :1], lb[..., 1:]], -1))
    die(f"no blend mode '{mode}': {', '.join(BLENDS)}")


def lay_over(mix, layer, layer_alpha, mask, opacity, mode):
    """One layer over the mix, source-over: weighted by its mask, its opacity and its own alpha, so where a layer is
    transparent (a paper cut's trimmed edge) the mix below shows, and a half-transparent layer counts half."""
    k = (opacity * mask * np.clip(layer_alpha, 0, 1))[..., None]
    return mix * (1 - k) + blend(mix, layer, mode) * k


# ---------------------------------------------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recipe")
    ap.add_argument("out")
    ap.add_argument("--no-check", action="store_true", help="skip each finish's checks")
    a = ap.parse_args()
    t0 = time.time()
    rp = Path(a.recipe)
    try:
        rc = json.loads(rp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        die(f"cannot read the recipe {a.recipe}: {e}")
    if not isinstance(rc, dict):
        die(f"{a.recipe} is not a recipe: a recipe is one JSON object (references/recipes.md)")
    if rc.get("format") != RECIPE_FORMAT:
        die(f"{a.recipe}: 'format' must be \"{RECIPE_FORMAT}\" (references/recipes.md)")
    if "subject" not in rc or not rc.get("layers") and "base" not in rc:
        die(f"{a.recipe}: a recipe needs a 'subject' and a 'base' or 'layers'")
    sp = Path(rc["subject"])
    sj = load_subject(sp if sp.is_absolute() else rp.parent / sp)
    img, alpha, parts = load_or_build(sj)
    U = Units(alpha, sj.get("head_px"))
    sel = Selector(sj, img, alpha, parts, U)
    for lay in rc.get("layers", []):
        if lay.get("blend", "normal") not in BLENDS:
            die(f"no blend mode '{lay['blend']}': {', '.join(BLENDS)}")
        sel.where(lay.get("where"))                       # (every name checked before anything is rendered)

    finishes, records = {}, []

    def get(ref):
        key = str(ref)
        if key not in finishes:
            out, out_alpha, rec = render(ref, sj, img, alpha, parts, U, not a.no_check)
            if out.shape[:2] != alpha.shape:
                die(f"'{ref}' gives a picture of another size; it cannot be mixed")
            finishes[key] = (out, out_alpha)
            records.append(rec)
        return finishes[key]

    mix, mix_alpha = get(rc.get("base", "source"))
    mix = mix.copy()
    covered = []
    for i, lay in enumerate(rc.get("layers", [])):
        if "style" not in lay:
            die(f"layer {i} has no 'style'")
        layer, layer_alpha = get(lay["style"])
        m = sel.where(lay.get("where")).astype(np.float32)
        f = U.len(lay.get("feather", 1.5))
        if f > 0:
            m = cv2.GaussianBlur(m, (0, 0), f) * (alpha > 0.5)
        mix = lay_over(mix, layer, layer_alpha, m, float(lay.get("opacity", 1.0)), lay.get("blend", "normal"))
        covered.append({"layer": i, "style": lay["style"], "blend": lay.get("blend", "normal"),
                        "opacity": lay.get("opacity", 1.0),
                        "share": round(float((m > 0.5).sum() / max(1, (alpha > 0.5).sum())), 3)})
    post = list(rc.get("post", [])) + ([{"op": "relight", "hour": rc["hour"]}] if rc.get("hour") else [])
    if post:
        import _post
        mix = _post.apply(post, np.clip(mix, 0, 1), mix_alpha, parts, sj, U, seed=rc.get("seed", 7))
    save_rgba(a.out, np.clip(mix, 0, 1), mix_alpha)
    emit({"out": a.out, "finishes": records, "layers": covered, "seconds": round(time.time() - t0, 1)})
    sys.exit(1 if any(r.get("check", {}).get("verdict") == "fail" for r in records) else 0)


if __name__ == "__main__":
    main()
