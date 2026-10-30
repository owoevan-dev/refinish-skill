"""A finished figure moved to another hour: its colours relit in linear light, the way a colour designer makes a
night or an evening colour model (夜色指定, 夕方色指定) from the day one, not tinted over.

Each colour is read as a surface under the day's white light. Under the new light it becomes

    surface x (ambient + lit x key)

where `lit` (0..1) is how much of the key light the pixel had in the finished day picture: 1 in a part's base tone
and its lights, 0 in its shadow, read per part from the tones the finish laid (two clusters of the part's
lightness, so a cel's flat tones give it exactly and a painted finish gives it smoothly). The lines and the eyes'
dark marks take the ambient only; the catch-lights in the eyes stay bright.

After the relight:
  floor   the darkest values pulled toward the ambient's own colour (an anime night is navy, not black);
  chroma  a cap on the new colours' chroma, so a sunset's lit side glows without turning garish;
  rim     an optional thin line of the key light along the silhouette on the light's side.

The hours are presets (HOURS); a style or the command line may override any key.
"""
import cv2
import numpy as np

from _core import lab, rgb, tone_cuts

HOURS = {
    # key and ambient as linear-light RGB multipliers; light: the direction the key comes from (x, y)
    "night": {"key": [0.22, 0.28, 0.48], "ambient": [0.06, 0.08, 0.18], "light": [-0.6, -1.0],
              "floor": [14.0, 4.0, -16.0], "floor_amount": 0.55, "chroma_cap": 34.0,
              "rim": {"width": 1.2, "alpha": 0.55, "colour": [0.70, 0.86, 1.0]}},
    "sunset": {"key": [1.00, 0.66, 0.38], "ambient": [0.26, 0.21, 0.40], "light": [1.0, -0.35],
               "floor": [16.0, 10.0, -14.0], "floor_amount": 0.35, "chroma_cap": 62.0,
               "rim": {"width": 1.5, "alpha": 0.75, "colour": [1.0, 0.78, 0.45]}},
    "dusk": {"key": [0.62, 0.50, 0.62], "ambient": [0.20, 0.19, 0.36], "light": [0.8, -0.6],
             "floor": [15.0, 8.0, -15.0], "floor_amount": 0.45, "chroma_cap": 40.0, "rim": None},
    # the night of theatrical anime: the figure stays light (skin L 57-85) and loses most of its colour (skin chroma 4-7
    # against 15-25 by day); a warm key from the lanterns, a cool ambient from the sky, so the shadows turn mauve-grey.
    "film-night": {"key": [0.37, 0.32, 0.20], "ambient": [0.39, 0.485, 0.745], "light": [-0.5, -1.0],
                   "chroma": 0.45, "floor": [12.0, 4.0, -10.0], "floor_amount": 0.3, "chroma_cap": 24.0,
                   "rim": None},
}


def _lin(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055)


def lit_map(img, parts, within, lines=None, features=None, U=None):
    """How much key light each pixel had, per part: its tone between the part's shadow and its base. Lines and the
    eyes' dark marks get 0 (they are ink, lit by nothing but the ambient)."""
    Lv = lab(img)[..., 0]
    lit = np.zeros(Lv.shape, np.float32)
    ink = np.zeros(Lv.shape, bool) if lines is None else lines > 0.5
    for j in np.unique(parts[within]):
        if j == 0:
            continue
        m = (parts == j) & within & ~ink
        if m.sum() < 40:
            lit[(parts == j) & within] = 1.0
            continue
        v = Lv[m]
        cut = float(tone_cuts(v, 2)[0])
        lo, hi = np.percentile(v[v < cut], 50) if (v < cut).any() else cut - 8, np.percentile(v[v >= cut], 50)
        gap = max(4.0, hi - lo)
        # a part painted in one tone (no shadow) is all lit
        if (v < cut).mean() < 0.03 or hi - lo < 4.0:
            lit[m] = 1.0
            continue
        lit[m] = np.clip((Lv[m] - lo) / gap, 0, 1)
    if U is not None:
        lit = cv2.GaussianBlur(lit, (0, 0), max(0.6, 0.25 * U.px)) * within
    lit[ink] = 0.0
    return lit


def relight(img, alpha, parts, hour="night", lines=None, features=None, U=None, **override):
    """The figure under the hour's light (HOURS, or keys given in `override`). Returns the new RGB."""
    if hour not in HOURS and not override.get("key"):
        raise ValueError(f"hour must be one of {', '.join(HOURS)} or given as key and ambient")
    p = dict(HOURS.get(hour, {}))
    p.update({k: v for k, v in override.items() if v is not None})
    within = alpha > 0.5
    lit = lit_map(img, parts, within, lines, features, U)
    key = np.array(p["key"], np.float32)
    amb = np.array(p["ambient"], np.float32)
    surf = _lin(img)
    light = amb[None, None, :] + lit[..., None] * key[None, None, :]
    out = surf * light
    # the catch-lights in the eyes stay bright: small, near-white specks inside the eye boxes (not the skin there,
    # not the whites of the eyes, which darken with the rest)
    if features is not None:
        Lab_ = lab(img)
        spot = ((features > 0.5) & (Lab_[..., 0] > 88) & (np.hypot(Lab_[..., 1], Lab_[..., 2]) < 8)).astype(np.uint8)
        n, cc, st, _ = cv2.connectedComponentsWithStats(spot)
        small = np.zeros(n, bool)
        lim = (U.area(6.0) if U is not None else 60.0)
        small[1:] = st[1:, cv2.CC_STAT_AREA] <= lim
        catch = small[cc]
        out[catch] = np.maximum(out[catch], surf[catch] * (amb + key) * 2.2)
    res = _srgb(out).astype(np.float32)
    f = lab(res)
    # the floor: the darkest values toward the ambient's own colour, not to black
    fl = np.array(p.get("floor", [12.0, 0.0, -10.0]), np.float32)
    k = np.clip((fl[0] + 6 - f[..., 0]) / (fl[0] + 6), 0, 1) * p.get("floor_amount", 0.5)
    f = f + (fl[None, None, :] - f) * (k[..., None] * np.array([0.5, 1.0, 1.0], np.float32))
    # the hour's own loss of colour (a cinematic night grade), then a cap on chroma, the hue kept
    f[..., 1:] *= p.get("chroma", 1.0)
    cap = p.get("chroma_cap")
    if cap:
        C = np.hypot(f[..., 1], f[..., 2])
        s = np.where(C > cap, cap + (C - cap) * 0.3, C) / np.maximum(C, 1e-6)
        f[..., 1] *= s
        f[..., 2] *= s
    res = rgb(f)
    rim = p.get("rim")
    if rim and U is not None:
        res = _rim(res, alpha, U, p["light"], rim)
    return np.where(within[..., None], res, img).astype(np.float32)


def _rim(img, alpha, U, light, rim):
    """A thin line of the key light just inside the silhouette, on the side facing the light."""
    a = alpha.astype(np.float32)
    d_in = cv2.distanceTransform((a > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    width = max(1.0, U.len(rim.get("width", 1.2)))
    band = np.clip(1 - d_in / width, 0, 1) * (a > 0.5)
    g = cv2.GaussianBlur(a, (0, 0), max(1.0, 2 * width))
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    n = np.hypot(gx, gy) + 1e-6
    lx, ly = np.array(light, np.float32) / np.hypot(*light)
    facing = np.clip(-(gx * lx + gy * ly) / n, 0, 1) ** 1.5    # the outward normal, -grad, against the light
    k = (band * facing * rim.get("alpha", 0.6))[..., None]
    col = np.array(rim.get("colour", [1, 1, 1]), np.float32)
    lin = _lin(img)
    return _srgb(lin + (np.maximum(lin, col * 0.85) - lin) * k).astype(np.float32)
