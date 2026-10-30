"""Dry drawing media on toned paper: charcoal, or soft pastel. The cel base's tones are laid as strokes of the medium
that catch on the paper's tooth (the hollows stay paper), hatched along each part's shading in a few directions, the
darks pressed in heavier; the line art redrawn as the medium's own line, broken where the stick skipped; the lights
lifted with a white chalk or left as the paper.

  charcoal  one black on a warm grey or cream paper: the tones as values only
  pastel    the parts' own colours, chalky and a little lighter, on a toned paper (blue-grey by default), the pigment
            dusted over the tooth; the lines in a darker pastel of the part's colour

Style keys, section `drawing`: `medium` ("charcoal" or "pastel"), `paper` (RGB), `tooth` (0..1, how much the paper's
grain shows, 0.6), `hatch` (u, the strokes' spacing, 3.5), `angles` (degrees, one per tone from light to dark),
`strength` (0..1), `lines` (0..1, the line's strength), `lift` (0..1, the white chalk on the lights), `smudge` (u, the
blending finger's reach, 1.5)."""
import cv2
import numpy as np

import _flat
import _texture as tx
from _core import lab, protect_mask, rgb
from _lines import find_lines


def _hatch(h, w, spacing, angle, rng, jitter=0.35):
    """A field of parallel strokes at one angle: 1 on a stroke, 0 between, the strokes wavering a little."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    a = np.radians(angle)
    u = xx * np.cos(a) + yy * np.sin(a)
    v = -xx * np.sin(a) + yy * np.cos(a)
    wob = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), spacing * 3) * spacing * jitter * 8
    ph = (u + wob) / spacing
    s = 0.5 + 0.5 * np.cos(2 * np.pi * ph)
    # strokes vary in pressure along their length: a slow noise lightens some lengths, a little (strong, its broad
    # patches read as a mottle over the whole drawing rather than as pressure)
    brk = cv2.GaussianBlur(rng.random((h, w)).astype(np.float32), (0, 0), spacing * 2.5)
    brk = (brk - brk.min()) / max(1e-6, brk.max() - brk.min())
    return np.clip(s * 1.6 - 0.4, 0, 1) * np.clip(0.75 + (brk - 0.5) * 0.5, 0, 1)


def run(subject, style, cel, alpha, parts, U, seed=7):
    ds = style.get("drawing", {})
    medium = ds.get("medium", "charcoal")
    rng = np.random.default_rng(seed)
    h, w = alpha.shape
    within = alpha > 0.5
    plist = subject["parts"]
    kinds = [None] + [p.get("kind", "cloth") for p in plist]
    paper = np.array(ds.get("paper", [214, 206, 190] if medium == "charcoal" else [150, 160, 170]), np.float32) / 255
    hgt, _ = tx.paper("cold-press", h, w, U, seed=seed)
    tooth = float(ds.get("tooth", 0.6))
    # where the medium catches: the paper's peaks take it first, the hollows last. Only the tooth's grain: the sheet's
    # broad undulation (a cold-press paper's) under a dry medium reads as blotches, not as tooth
    fine = hgt - cv2.GaussianBlur(hgt, (0, 0), max(1.5, U.len(1.5))) + 0.5
    catch = np.clip((fine - 0.5) * 2.6 * tooth + 0.5, 0, 1)
    sp = max(2.0, U.len(ds.get("hatch", 3.5)))
    angles = ds.get("angles", [62.0, 28.0, -20.0])
    strokes = [_hatch(h, w, sp, a, rng) for a in angles]
    Lc = lab(cel)
    # the value to draw (0 paper .. 1 the medium at full): from the cel base's lightness, the parts' tones flat
    val = np.zeros((h, w), np.float32)
    col = np.zeros((h, w, 3), np.float32)
    for lay in _flat.layers(cel, parts, within, kinds):
        for i, c in enumerate(lay["colours"]):
            m = lay["mask"] & (lay["tone"] == i)
            if not m.any():
                continue
            v = float(np.clip((92 - c[0]) / 80, 0, 1))
            val[m] = v
            if medium == "pastel":
                cc = np.array(c, np.float32).copy()
                cc[0] = min(96, cc[0] + 6)
                col[m] = rgb(cc.reshape(1, 1, 3))[0, 0]
    if medium == "pastel":
        # on toned paper a pastel painter covers by how far a colour is from the paper, not by how dark it is: a
        # light skin on a blue-grey sheet is laid thick, or the sheet's blue shows through it
        pl = lab(paper.reshape(1, 1, 3))[0, 0]
        dist = np.linalg.norm(lab(col) - pl, axis=2)
        val = np.where(within, np.clip(0.35 + dist / 45, 0, 1), 0).astype(np.float32)
    # the strokes build the value: a light tone one direction, darker ones crossing it, pressed into the tooth
    cover = np.zeros((h, w), np.float32)
    for k, s in enumerate(strokes):
        lo = k / len(strokes)
        need = np.clip((val - lo) * len(strokes), 0, 1)
        cover = 1 - (1 - cover) * (1 - need * s)
    cover = np.clip(cover * (0.55 + 0.45 * catch) + val * 0.35 * catch, 0, 1) * float(ds.get("strength", 1.0))
    # a dark is laid with the stick on its side and pressed in, not hatched: crossed hatching leaves a lattice of light
    # holes that reads as a pattern on a black coat; the tooth alone shows in it
    solid = np.clip((val - 0.55) / 0.3, 0, 1)
    cover = cover * (1 - solid) + val * (0.8 + 0.2 * catch) * float(ds.get("strength", 1.0)) * solid
    sm = U.len(ds.get("smudge", 1.5))
    if sm > 0:
        cover = cv2.GaussianBlur(cover, (0, 0), sm * 0.5) * 0.6 + cover * 0.4
    if medium == "charcoal":
        # the skin blended with a stump, as a charcoal portrait is: its values smooth, only the tooth showing in them
        # (hatching over a face reads as stubble or dirt, and on a dark skin it buries the features)
        skin_k = np.isin(parts, [j for j, k in enumerate(kinds) if k == "skin"]) & within
        stump = np.clip(cv2.GaussianBlur(val, (0, 0), sp) * (0.82 + 0.18 * catch), 0, 1)
        sk_a = cv2.GaussianBlur(skin_k.astype(np.float32), (0, 0), max(1.0, sp * 0.5))
        cover = cover * (1 - sk_a) + stump * float(ds.get("strength", 1.0)) * sk_a
        ink = np.array([0.09, 0.085, 0.09], np.float32)
        out = paper * (1 - cover[..., None]) + ink * cover[..., None]
    else:
        # pastel: the pigment laid broad and blended with the finger, chalky; the paper shows only in the tooth's
        # hollows, not in patches (the hatching's pressure is blended away)
        blend = cv2.GaussianBlur(cover, (0, 0), sp * 1.5)
        dust = np.clip((0.75 * blend + 0.25 * cover) * 1.15 + val * 0.45, 0, 1)
        # a dark pastel is pressed in until it fills the tooth: the sheet shows in the hollows of a light colour only
        # (light flecks of a blue-grey sheet all over a navy coat read as a mottle)
        dark_c = np.clip((55.0 - lab(col)[..., 0]) / 35.0, 0, 1)
        dust = np.clip(dust - (1 - catch) * 0.35 * tooth * (1 - 0.75 * dark_c), 0, 1)[..., None]
        out = paper * (1 - dust) + col * dust
    # the lights lifted with white chalk
    lift = float(ds.get("lift", 0.35 if medium == "charcoal" else 0.2))
    if lift > 0:
        lights = np.clip((Lc[..., 0] - 82) / 14, 0, 1) * within * catch
        out = out * (1 - lift * lights[..., None]) + np.array([0.97, 0.96, 0.93], np.float32) * lift * lights[..., None]
    # the line art in the medium, broken where the stick skipped
    L_line = find_lines(cel, subject.get("upscaled", 1))
    skip = np.clip((catch - 0.15) * 1.6, 0, 1)
    la = (np.clip(L_line * 1.3, 0, 1) * skip * float(ds.get("lines", 0.9)) * within)[..., None]
    if medium == "charcoal":
        line_c = np.array([0.06, 0.055, 0.06], np.float32)
        out = out * (1 - la) + line_c * la
    else:
        dark = col * 0.45
        out = out * (1 - la) + dark * la
    # the eyes and the mouth as drawn, in the medium's colour (charcoal: their values only)
    prot = protect_mask(subject, h, w, cel, np.isin(parts, [j for j, k in enumerate(kinds) if k == "skin"]),
                        parts=parts)
    feat = cel if medium == "pastel" else np.repeat(lab(cel)[..., :1] / 100, 3, axis=2) * (paper / paper.max())
    out = out * (1 - prot[..., None]) + feat * prot[..., None]
    out = out * tx.lit(hgt, U, 0.05 * tooth)[..., None]
    return np.clip(out, 0, 1).astype(np.float32), {"medium": medium}
