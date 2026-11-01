"""Colour science for recolouring.

- Oklab and OkLCh (Björn Ottosson, "A perceptual color space for image processing", 2020; the matrices are his,
  public domain): CIELAB predicts hue badly in the blues (a blend from blue to white drifts to purple in it), Oklab
  keeps hue nearly constant along chroma, so every interpolation, hue turn and gradient of a recolour is done here.
- Gamut mapping to sRGB as CSS Color 4 does it (§14.2.2, "binary search gamut mapping with local MINDE"): lightness
  and hue kept, OkLCh chroma reduced by bisection until the clipped colour is within a just noticeable difference
  (deltaEOK 0.02) of it. Clipping each channel instead turns hues and flattens gradients.
- CIEDE2000 (Sharma, Wu and Dalal, "The CIEDE2000 color-difference formula: implementation notes, supplementary test
  data, and mathematical observations", Color Research & Application 30(1), 2005), on CIELAB, for the checks.

Arrays are numpy, the channels on the last axis; sRGB is 0..1, Oklab L is 0..1, CIELAB L is 0..100."""
import re

import numpy as np

JND = 0.02          # deltaEOK, CSS Color 4
EPSILON = 0.0001

_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005]])
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]])
_M2_INV = np.array([[1.0, 0.3963377774, 0.2158037573],
                    [1.0, -0.1055613458, -0.0638541728],
                    [1.0, -0.0894841775, -1.2914855480]])
_M1_INV = np.array([[4.0767416621, -3.3077115913, 0.2309699292],
                    [-1.2684380046, 2.6097574011, -0.3413193965],
                    [-0.0041960863, -0.7034186147, 1.7076147010]])


# ------------------------------------------------------------------------------------------------------ sRGB, Oklab

def srgb_to_linear(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((np.maximum(c, 0) + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.maximum(c, 0), 1 / 2.4) - 0.055)


def linear_to_oklab(lin):
    lms = np.asarray(lin, np.float64) @ _M1.T
    return np.cbrt(lms) @ _M2.T


def oklab_to_linear(ok):
    lms_ = np.asarray(ok, np.float64) @ _M2_INV.T
    return (lms_ ** 3) @ _M1_INV.T


def srgb_to_oklab(rgb):
    return linear_to_oklab(srgb_to_linear(rgb))


def oklab_to_srgb(ok, map_gamut=True):
    """Oklab to sRGB 0..1; colours sRGB cannot show are gamut-mapped (or, with map_gamut=False, clipped)."""
    ok = np.asarray(ok, np.float64)
    if map_gamut:
        ok = gamut_map(ok)
    return np.clip(linear_to_srgb(np.clip(oklab_to_linear(ok), 0, 1)), 0, 1)


def to_lch(ok):
    ok = np.asarray(ok, np.float64)
    return np.stack([ok[..., 0], np.hypot(ok[..., 1], ok[..., 2]),
                     np.degrees(np.arctan2(ok[..., 2], ok[..., 1])) % 360.0], -1)


def from_lch(lch):
    lch = np.asarray(lch, np.float64)
    h = np.radians(lch[..., 2])
    return np.stack([lch[..., 0], lch[..., 1] * np.cos(h), lch[..., 1] * np.sin(h)], -1)


def delta_eok(a, b):
    return np.linalg.norm(np.asarray(a, np.float64) - np.asarray(b, np.float64), axis=-1)


# ---------------------------------------------------------------------------------------------------- gamut mapping

def _in_gamut(lin, eps=1e-6):
    return np.all((lin >= -eps) & (lin <= 1 + eps), axis=-1)


def gamut_map(ok):
    """CSS Color 4 §14.2.2 for every colour at once: a colour sRGB can show is returned as it is; L at or above 1 is
    white, at or below 0 black; otherwise OkLCh chroma is bisected (lightness and hue kept) and the clipped colour is
    returned as soon as it lies within JND of the current one."""
    ok = np.array(ok, np.float64)
    shape = ok.shape
    flat = ok.reshape(-1, 3)
    out = flat.copy()
    L = flat[:, 0]
    lin = oklab_to_linear(flat)
    todo = ~_in_gamut(lin) & (L > 0) & (L < 1)
    out[L >= 1] = (1.0, 0.0, 0.0)
    out[L <= 0] = (0.0, 0.0, 0.0)
    if not todo.any():
        return out.reshape(shape)
    idx = np.nonzero(todo)[0]
    lch = to_lch(flat[idx])

    def clip_ok(lc):
        return linear_to_oklab(np.clip(oklab_to_linear(from_lch(lc)), 0, 1))

    clipped = clip_ok(lch)
    res = clipped.copy()
    active = delta_eok(clipped, from_lch(lch)) >= JND             # (else the clipped colour is the answer)
    lo = np.zeros(len(idx))
    hi = lch[:, 1].copy()
    lo_in = np.ones(len(idx), bool)
    for _ in range(64):
        act = active & (hi - lo > EPSILON)
        if not act.any():
            break
        cur = lch.copy()
        cur[:, 1] = (lo + hi) / 2
        inside = _in_gamut(oklab_to_linear(from_lch(cur)))
        step_in = act & lo_in & inside
        lo[step_in] = cur[step_in, 1]
        rest = act & ~step_in
        if rest.any():
            cl = clip_ok(cur[rest])
            e = delta_eok(cl, from_lch(cur[rest]))
            r_idx = np.nonzero(rest)[0]
            res[r_idx] = cl
            near = e < JND
            done = near & (JND - e < EPSILON)
            active[r_idx[done]] = False
            go_up = near & ~done
            lo_in[r_idx[go_up]] = False
            lo[r_idx[go_up]] = cur[r_idx[go_up], 1]
            hi[r_idx[~near]] = cur[r_idx[~near], 1]
        # an in-gamut midpoint is a candidate answer too, should the search end on it
        res[step_in] = from_lch(cur[step_in])
    out[idx] = res
    return out.reshape(shape)


# ---------------------------------------------------------------------------------------------------------- CIEDE2000

def ciede2000(lab1, lab2):
    """CIEDE2000 between CIELAB colours (kL = kC = kH = 1), following Sharma, Wu and Dalal's implementation notes:
    hues in degrees, the mean hue and the hue difference taken across 0/360 the short way, and zero for a neutral."""
    l1 = np.asarray(lab1, np.float64)
    l2 = np.asarray(lab2, np.float64)
    L1, a1, b1 = l1[..., 0], l1[..., 1], l1[..., 2]
    L2, a2, b2 = l2[..., 0], l2[..., 1], l2[..., 2]
    c_bar = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    g = 0.5 * (1 - np.sqrt(c_bar ** 7 / (c_bar ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.where((a1p == 0) & (b1 == 0), 0.0, np.degrees(np.arctan2(b1, a1p)) % 360)
    h2p = np.where((a2p == 0) & (b2 == 0), 0.0, np.degrees(np.arctan2(b2, a2p)) % 360)
    dLp = L2 - L1
    dCp = c2p - c1p
    zero = (c1p * c2p) == 0
    dh = h2p - h1p
    dhp = np.where(zero, 0.0, np.where(np.abs(dh) <= 180, dh, np.where(dh > 180, dh - 360, dh + 360)))
    dHp = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dhp) / 2)
    Lbp = (L1 + L2) / 2
    Cbp = (c1p + c2p) / 2
    hs = h1p + h2p
    hbp = np.where(zero, hs, np.where(np.abs(h1p - h2p) <= 180, hs / 2,
                                      np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2)))
    t = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    d_theta = 30 * np.exp(-(((hbp - 275) / 25) ** 2))
    rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
    sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    sc = 1 + 0.045 * Cbp
    sh = 1 + 0.015 * Cbp * t
    rt = -np.sin(np.radians(2 * d_theta)) * rc
    return np.sqrt((dLp / sl) ** 2 + (dCp / sc) ** 2 + (dHp / sh) ** 2 + rt * (dCp / sc) * (dHp / sh))


# ---------------------------------------------------------------------------------------------------------- hex

_HEX = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")


def parse_hex(s):
    """'#rrggbb', 'rrggbb' or '#rgb' to sRGB 0..1; None if it is not one."""
    m = _HEX.match(str(s).strip())
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def to_hex(rgb):
    v = np.clip(np.round(np.asarray(rgb, np.float64) * 255), 0, 255).astype(int)
    return "#{:02x}{:02x}{:02x}".format(*v)


def hue_turn(h, target, frac, cap):
    """Hue h (degrees) turned toward target by frac of the way, at most cap degrees. When the target lies straight
    across the circle the turn goes the warm way (down through red): a yellow's shadow turns orange, not green."""
    d = (np.asarray(target, np.float64) - np.asarray(h, np.float64) + 180.0) % 360.0 - 180.0
    d = np.where(np.abs(d) >= 179.5, -np.abs(d), d)
    return (h + np.clip(d * frac, -cap, cap)) % 360.0
