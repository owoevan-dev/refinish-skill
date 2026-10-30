#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python"]
# ///
"""Lay re-finished figures over a background and give the frame a camera (撮影処理): the depth of field, with the
lights out of focus opening into discs (bokeh), the background's light wrapping the figures' edges, a grade of the
background region by region, a bloom on the lights, a vignette and a fine grain.

Usage:
  python scripts/composite.py SCENE.json OUT.png [--raw]

SCENE.json (paths relative to it):
  {"frame": [1920, 1080],
   "background": {"image": "bg.png", "zoom": 1.0, "centre": [0.5, 0.5], "blur": 6.0,
                  "grade": {"chroma": 0.55, "lift": 0.0, "regions": [{"hue": [200, 290], "chroma_min": 8,
                            "L": 8.0}, {"rest": true, "L": 18.0}]}},
   "layers": [{"image": "figure.png", "place": [x0, y_bottom, scale], "blur": 0.0, "wrap": 0.22,
               "sharpen": 0.0, "grade": {...}}],
   "camera": {"bokeh": {"shape": "disk", "hot": 3.0, "knee": 0.75}, "bloom": {"threshold": 0.72,
              "radius": 14.0, "amount": 0.25}, "vignette": 0.0, "grain": 0.006}}

Everything is in pixels of the frame. Layers are listed back to front; each layer's `blur` is its own distance from
the focus (0 sharp, a foreground shoulder far out of focus 30 or more). The background is resized to cover the frame
(`zoom` > 1 crops in, a longer lens: everything behind the figure larger and closer). --raw lays the layers on the
background with nothing else, the plain paste-up, to compare with.
Prints JSON: the output and what each grade did.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core import emit, lab, rgb  # noqa: E402


def to_lin(c):
    c = np.clip(c, 0, None)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(c, 0, None)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def cover(img, w, h):
    s = max(w / img.shape[1], h / img.shape[0])
    r = cv2.resize(img, (int(np.ceil(img.shape[1] * s)), int(np.ceil(img.shape[0] * s))),
                   interpolation=cv2.INTER_LANCZOS4 if s > 1 else cv2.INTER_AREA)
    y0, x0 = (r.shape[0] - h) // 2, (r.shape[1] - w) // 2
    return np.clip(r[y0:y0 + h, x0:x0 + w], 0, 1)


def kernel(r, shape="disk", blades=6, rotation=15.0):
    """A lens's out-of-focus shape, r pixels in radius: a disk (a wide-open lens) or a polygon of `blades` sides (a
    stopped-down aperture). Anti-aliased, summing to 1."""
    r = max(0.5, float(r))
    n = int(np.ceil(r)) + 1
    yy, xx = np.mgrid[-n:n + 1, -n:n + 1].astype(np.float32)
    if shape == "disk":
        k = np.clip(r + 0.5 - np.hypot(xx, yy), 0, 1)
    else:
        ang = np.arctan2(yy, xx) - np.radians(rotation)
        seg = 2 * np.pi / blades
        # the distance to a regular polygon's edge along each direction
        d = r * np.cos(seg / 2) / np.cos((ang % seg) - seg / 2)
        k = np.clip(d + 0.5 - np.hypot(xx, yy), 0, 1)
    return (k / k.sum()).astype(np.float32)


def lens_blur(img, r, alpha=None, bokeh=None):
    """Out of focus the way a lens is: the aperture's shape convolved in linear light, the brightest lights pushed
    above white first (`hot` times at full brightness, from `knee` up) so they open into bright discs instead of grey
    smears. With alpha, a cut-out is blurred premultiplied and its alpha with it."""
    if r < 0.5:
        return (img, alpha) if alpha is not None else img
    b = bokeh or {}
    k = kernel(r, b.get("shape", "disk"), b.get("blades", 6), b.get("rotation", 15.0))
    lin = to_lin(img)
    lum = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    knee, hot = b.get("knee", 0.75), b.get("hot", 3.0)
    boost = 1 + (hot - 1) * np.clip((lum - knee) / max(1e-3, 1 - knee), 0, 1)
    lin = lin * boost[..., None]
    if alpha is None:
        return np.clip(to_srgb(cv2.filter2D(lin, -1, k)), 0, 1)
    a = cv2.filter2D(alpha, -1, k)
    c = cv2.filter2D(lin * alpha[..., None], -1, k) / np.maximum(a[..., None], 1e-4)
    return np.clip(to_srgb(c), 0, 1), np.clip(a, 0, 1)


def grade(img, g, mask=None):
    """A grade: lift, gain and chroma for the whole picture, then regions told apart by hue (a sky's blue from the
    ground under it), each brought to its own median lightness `L`; a night sky and a slope sit at nearly the same
    lightness in a day picture, so one curve cannot move them apart. Returns the graded picture and a report."""
    if not g:
        return img, {}
    f = lab(img)
    L, a, b = f[..., 0], f[..., 1], f[..., 2]
    within = np.ones(L.shape, bool) if mask is None else mask > 0.5
    rep = {}
    regs = g.get("regions", [])
    if regs:
        C = np.hypot(a, b)
        hh = np.degrees(np.arctan2(b, a)) % 360
        claimed = np.zeros(L.shape, np.float32)
        gain = np.zeros(L.shape, np.float32)
        for i, rg in enumerate(regs):
            if rg.get("rest"):
                m = 1.0 - claimed
            else:
                lo, hi = rg.get("hue", [0, 360])
                inh = ((hh - lo) % 360) <= ((hi - lo) % 360 or 360)
                m = (inh & (C >= rg.get("chroma_min", 0.0))).astype(np.float32)
                m = cv2.GaussianBlur(m, (0, 0), 3.0) * (1.0 - claimed)
            sel = (m > 0.7) & within
            med = float(np.median(L[sel])) if sel.sum() > 50 else None
            if med is not None and "L" in rg:
                k = rg["L"] / max(1.0, med)
                gain += m * k
                rep[f"region {i}"] = {"L_from": round(med, 1), "L_to": rg["L"], "share": round(float(sel.mean()), 3)}
            else:
                gain += m
            claimed = np.clip(claimed + m, 0, 1)
        gain += 1.0 - claimed
        L = L * gain
    lift, gn = g.get("lift", 0.0), g.get("gain", 1.0)
    L = lift * 100.0 + (gn - lift) * L
    f[..., 0] = L
    f[..., 1:] *= g.get("chroma", 1.0)
    f[..., 1] += g.get("cast_a", 0.0) * (1 - L / 100.0)
    f[..., 2] += g.get("cast_b", 0.0) * (1 - L / 100.0)
    out = rgb(f)
    return (np.where(within[..., None], out, img) if mask is not None else out), rep


def bloom(img, threshold=0.72, radius=14.0, amount=0.25):
    lin = to_lin(img)
    lum = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    hi = lin * np.clip((lum - threshold) / max(1e-3, 1 - threshold), 0, 1)[..., None]
    return np.clip(to_srgb(lin + cv2.GaussianBlur(hi, (0, 0), radius) * amount), 0, 1)


def load_layer(path, place, W, H):
    """A cut-out (RGBA) placed on the frame: [x0, y_bottom, scale]. The generator's faint halo (alpha far from the
    figure) is cleared first."""
    fig = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if fig is None or fig.ndim < 3 or fig.shape[2] != 4:
        raise ValueError(f"{path}: a layer must be an RGBA cut-out")
    fa = fig[..., 3].astype(np.float32) / 255.0
    fa[cv2.dilate((fa > 0.8).astype(np.uint8), np.ones((9, 9), np.uint8)) == 0] = 0
    fr = cv2.cvtColor(fig[..., :3], cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    x0, yb, s = (float(v) for v in place)
    w2, h2 = max(1, int(round(fig.shape[1] * s))), max(1, int(round(fig.shape[0] * s)))
    interp = cv2.INTER_AREA if s < 1 else cv2.INTER_LANCZOS4
    pre = cv2.resize(fr * fa[..., None], (w2, h2), interpolation=interp)
    a2 = np.clip(cv2.resize(fa, (w2, h2), interpolation=interp), 0, 1)
    col = np.where(a2[..., None] > 1e-3, pre / np.maximum(a2[..., None], 1e-3), 0)
    rgb_, al = np.zeros((H, W, 3), np.float32), np.zeros((H, W), np.float32)
    X0, Y0 = int(round(x0)), int(round(yb)) - h2
    xs0, ys0, xs1, ys1 = max(0, X0), max(0, Y0), min(W, X0 + w2), min(H, Y0 + h2)
    if xs1 > xs0 and ys1 > ys0:
        rgb_[ys0:ys1, xs0:xs1] = col[ys0 - Y0:ys1 - Y0, xs0 - X0:xs1 - X0]
        al[ys0:ys1, xs0:xs1] = a2[ys0 - Y0:ys1 - Y0, xs0 - X0:xs1 - X0]
    return np.clip(rgb_, 0, 1), al


def sharpen_lines(img, alpha, amount):
    """A fine unsharp mask on the lines only (an enlarged cut-out's soft line edges), the flat paint left smooth."""
    g = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    mag = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    on = cv2.GaussianBlur(np.clip((mag - 0.15) / 0.25, 0, 1), (0, 0), 1.0)[..., None] * (alpha[..., None] > 0.5)
    return np.clip(img + amount * on * (img - cv2.GaussianBlur(img, (0, 0), 0.9)), 0, 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("scene")
    ap.add_argument("out")
    ap.add_argument("--raw", action="store_true")
    a = ap.parse_args()
    sp = Path(a.scene)
    sc = json.loads(sp.read_text(encoding="utf-8"))
    W, H = sc.get("frame", [1920, 1080])
    cam = sc.get("camera", {})
    bk = sc.get("background", {})
    bg = cv2.imread(str(sp.parent / bk["image"]), cv2.IMREAD_COLOR)
    if bg is None:
        raise SystemExit(f"cannot read the background {bk['image']}")
    bg = cv2.cvtColor(bg, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    z = bk.get("zoom", 1.0)
    if z > 1:
        cx, cy = bk.get("centre", [0.5, 0.5])
        h0, w0 = bg.shape[:2]
        cw, ch = w0 / z, h0 / z
        x0 = int(np.clip(cx * w0 - cw / 2, 0, w0 - cw))
        y0 = int(np.clip(cy * h0 - ch / 2, 0, h0 - ch))
        bg = bg[y0:y0 + int(ch), x0:x0 + int(cw)]
    bg = cover(bg, W, H)
    report = {}
    if not a.raw:
        bg, report["background"] = grade(bg, bk.get("grade"))
        bg = lens_blur(bg, bk.get("blur", 0.0), bokeh=cam.get("bokeh"))
    out = bg.copy()
    for i, ly in enumerate(sc.get("layers", [])):
        fr, fa = load_layer(sp.parent / ly["image"], ly["place"], W, H)
        if a.raw:
            out = out * (1 - fa[..., None]) + fr * fa[..., None]
            continue
        if ly.get("grade"):
            fr, report[f"layer {i}"] = grade(fr, ly["grade"], fa)
        if ly.get("sharpen", 0) > 0:
            fr = sharpen_lines(fr, fa, ly["sharpen"])
        if ly.get("blur", 0) >= 0.5:
            fr, fa = lens_blur(fr, ly["blur"], fa, cam.get("bokeh"))
        under = out
        out = out * (1 - fa[..., None]) + fr * fa[..., None]
        wrap = ly.get("wrap", 0.0)
        if wrap > 0:
            # light wrap: the light of what lies behind reaching a little way over the layer's edge
            r = max(2, int(round(ly.get("wrap_width", 3.0))))
            edge = np.clip(fa - cv2.erode(fa, np.ones((2 * r + 1, 2 * r + 1), np.uint8)), 0, 1)
            wide = cv2.GaussianBlur(under, (0, 0), 3.0 * r)
            out = out + edge[..., None] * wrap * (1 - out) * wide
    if not a.raw:
        bl = cam.get("bloom")
        if bl:
            out = bloom(np.clip(out, 0, 1), bl.get("threshold", 0.72), bl.get("radius", 14.0), bl.get("amount", 0.25))
        vg = cam.get("vignette", 0.0)
        if vg > 0:
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            r2 = ((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2
            out = out * (1 - vg * np.clip(r2 - 0.25, 0, 1.5)[..., None] / 1.5)
        gr = cam.get("grain", 0.0)
        if gr > 0:
            rng = np.random.default_rng(cam.get("seed", 11))
            g = cv2.GaussianBlur(rng.normal(0, 1, (H, W)).astype(np.float32), (0, 0), 0.6) * gr
            out = out + g[..., None]
    cv2.imwrite(a.out, cv2.cvtColor((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR))
    emit({"out": a.out, "frame": [W, H], **report})


if __name__ == "__main__":
    main()
