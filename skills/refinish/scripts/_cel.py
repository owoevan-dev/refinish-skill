"""The cel engine: a figure repainted the way an anime finishing department paints from a colour model (色指定).

What the source picture gives: the drawing (shapes, line art) and the parts. What the style decides:
  - each part's colour model: one base, one shadow and, for hair and gloss, one light colour for every region of
    the part (the hair is one hair, not a patchwork of the picture's tones);
  - the shadow's shape, in one of two ways:
      drawn: the source's own tones where it put them (found by clustering the part's lightness), their noise
             smoothed away and the colour pulled most of the way to the flat tones; for sources drawn to the cel
             spec, and the safer default for any source;
      form:  the darkest share of the part's shading at the scale of its forms, as one clean shape; for soft
             sources whose shading has no shapes of its own;
  - the shadow colour: the source's own shadow tinted, or derived from the base by a rule;
  - the light on hair and gloss: a crisp shape, a soft band, or none;
  - the palette, the lines (found in the source, the closed outline, three colourings) and a blush.
The eyes and the mouth are kept as drawn."""
import cv2
import numpy as np
from scipy import ndimage as ndi

import _lines as ln_
import _recolour as rc_
from _core import clean_shape, cut_raggedness, ellipse_mask, lab, lab_px, protect_mask, rgb, rgb_px, spots, tone_cuts
from _style import follow, kind_of, rule


def run(subject, style, img, alpha, parts, U):
    h, w = alpha.shape
    within = alpha > 0.5
    plist = subject["parts"]
    kinds = [None] + [kind_of(p) for p in plist]

    def of_kind(k):
        return np.isin(parts, [j for j, kk in enumerate(kinds) if j > 0 and kk == k])

    # a colour card (palette.py apply): its parts' colour models are in the rules already; here, what else it asks.
    # First the part map's mistakes a recolour would paint, mended for it (_recolour.mend_parts)
    card = subject.get("recolour") or {}
    rec = rc_.recoloured(subject)
    kept_drawn = None
    touches = []
    touched_eyes = touched_rec = None                    # (what the touches gave an iris; a part the card recoloured)
    if rec or card.get("touch"):
        parts, kept_drawn, _ = rc_.mend_parts(subject, img, alpha, parts, U, kinds)
        touches = rc_.touch_masks(subject, img, alpha, U)
        names = [p["name"] for p in plist]
        to_kind = [kinds[names.index(t["as"]) + 1] if t.get("as") in names else None for _, t in touches]
        touched_eyes = np.zeros((h, w), bool)
        touched_rec = np.zeros((h, w), bool)
        for (m_, t), k in zip(touches, to_kind):
            if k == "eyes":
                touched_eyes |= m_
            elif k is not None and t["as"] in rec:
                touched_rec |= m_
    skin = of_kind("skin")
    prot = protect_mask(subject, h, w, img, skin, parts=parts)
    face = ellipse_mask(h, w, subject.get("focal", [])) > 0.5
    drawn_default = follow(style, subject) == "drawn"
    rec_mask = np.isin(parts, rc_.part_index(subject, rec)) & within if rec else None
    follow_lines = bool(rec) and card.get("lines", "follow") == "follow"

    # ---- the line art worth keeping ---------------------------------------------------------------------------------
    lines = style.get("lines", {})
    finder = lines.get("finder", {})
    L_line = ln_.find_lines(img, subject.get("upscaled", 1), tuple(finder.get("simplify", (3, 9))),
                            finder.get("lo", 0.18), None if drawn_default else finder.get("crisp", (0.15, 0.6)))
    keep = lines.get("keep", {})
    if drawn_default:                                  # a source's own clean lines: short ones kept (strands, folds)
        min_area, reach = U.area(keep.get("min_area_drawn", 0.67)), U.k(5, odd=True)
        # an ink colour turns a hair's short strand marks into black dashes: `kinds_drawn` keeps only the longer ones
        # there, the rest left in the hair's own dark colour as drawn
        by_part = [(of_kind(k), U.area(a)) for k, a in keep.get("kinds_drawn", {}).items()]
    else:
        min_area, reach = U.area(keep.get("min_area", 6.67)), U.k(3, odd=True)
        by_part = [(of_kind(k), U.area(a)) for k, a in keep.get("kinds", {}).items()]
    L_keep = ln_.keep_lines(L_line, min_area, reach, by_part, always=face & skin)
    is_line = L_line > 0.3
    rec_in = [j for j in rc_.part_index(subject, rec) if kinds[j] != "eyes"] if rec else []
    # an eye whose iris the part map gave to the hair or the clothes (P2) is left as drawn: its iris cannot be told
    # from the lashes and the hair round it, and half an iris recoloured is worse than none (RC3 reports it)
    eye_ok = np.ones((h, w), bool)
    Lv0 = eyes_new = None
    if rec:
        Lab0 = lab(img)
        Lv0 = Lab0[..., 0]
        for x0, y0, x1, y1 in rc_.mislabelled_irises(subject, Lab0, within, parts, kinds, skin & within):
            eye_ok[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = False
        # the irises the card recolours, once for inside the protected boxes and out: their drawing carried onto the
        # card's colours (a gradient map from the iris's own lightness to the card's knots), a catchlight left white.
        # The iris alone (_recolour.iris_core): a lash's tail or a strand the part map joined to it stays as drawn;
        # what a touch gave the iris is the iris's (a pale reflection in it the part map gave to the skin)
        eyes_new = img.copy()
        sk = skin & within
        iris_px = (eye_ok & rc_.iris_like(Lab0, np.median(Lab0[sk], axis=0) if sk.sum() > 50 else None)) | touched_eyes
        iris_m = {}
        for j, p in enumerate(plist, start=1):
            if p["name"] in rec and kinds[j] == "eyes":
                if p.get("exact"):
                    # an iris a segmenter split (auto_parts.py --parse): taken whole, its pale patches the iris's
                    m_ = (parts == j) & within & ~kept_drawn
                else:
                    m_ = ((rc_.iris_core(subject, (parts == j) & within & iris_px) | ((parts == j) & touched_eyes))
                          & ~kept_drawn)
                if m_.sum() > 10:
                    iris_m[j] = m_
                    eyes_new[m_] = rc_.transfer(img, m_, rc_.knots(rec[p["name"]]), white_keep=True)
    if rec_in:
        # the boxes give up hair and cloth reaching in across their edges; with a card, only what truly reaches in (a
        # part's fill joined to its fill outside, not across a line). A lash, a white of the eye, an iris the part map
        # gave to a recoloured part only inside a box is the feature's own drawing, kept as drawn: painted with that
        # part's new colours it would turn pink lashes or yellow eye whites
        fade = rc_.box_fade(subject, h, w)
        stray = (np.isin(parts, rec_in) & within & (fade > 0) & ~touched_rec
                 & ~rc_.reaching_in(subject, parts, rec_in, within & ~is_line, Lv0))
        if stray.any():
            prot = np.maximum(prot, cv2.GaussianBlur(stray.astype(np.float32), (0, 0), 1.0) * fade)

    # ---- each part painted from its colour model ----------------------------------------------------------------------
    Lv = lab(img)[..., 0] / 100.0
    out = img.copy()
    model = {}
    smoothed = {}
    paint_rec = np.zeros((h, w), bool)                 # (a card's parts painted from their colour models)
    sl_all = np.zeros((h, w), bool)                    # (and the strips of them beyond their lines, given away)
    for j, p in enumerate(plist, start=1):
        r = rule(style, subject, p)
        m = (parts == j) & within
        core = m & ~is_line
        src_ = img
        if p["name"] in rec and r.get("model", "part") in ("keep", "regions"):
            # a card's part the finish keeps as drawn: its own drawing carried onto the card's colours (a pattern's
            # tones onto the card's tones). An iris goes as the protected boxes paste it, not painted flat region by
            # region: the two would meet at the box's edge as a square patch
            if kinds[j] == "eyes":
                src_ = eyes_new
            else:
                src_ = img.copy()
                src_[m] = rc_.transfer(img, m, rc_.knots(rec[p["name"]]), keep=0.0)
        if core.sum() < 50 or r.get("model", "part") == "keep" or (src_ is not img and kinds[j] == "eyes"):
            if src_ is not img:
                out[m] = src_[m]
            continue                                   # (keep: a small accessory already drawn in flat cel)
        if r.get("model") == "regions":
            out = _regions(out, src_, m, is_line)
            continue
        drawn = r.get("follow", "drawn") == "drawn"
        minor = None                                   # (the few light patches of a dark part, when they are wear)
        Lf = _shading_scale(Lv, core, r, drawn, U, smoothed)
        Lf_pre = None                                  # (the shading as read, when an automatic broader reading is used)
        if (drawn and not r.get("deblotch") and kinds[j] not in ("hair", "eyes", "accessory")
                and r.get("auto_deblotch")):
            # asked for (`auto_deblotch`, off by default; references/adjusting.md): a part whose own two-tone cut comes
            # out ragged (soft airbrushed shading: the cut follows the noise into frayed edges and flecks) is read at a
            # broader scale, as `deblotch` does; decided on the cut's own shape (core.cut_raggedness). Never hair: its
            # strands are drawn shapes as fine as any fray
            thr = float(r["auto_deblotch"])
            # only a low-contrast cut: a fray is noise riding a shallow shading, a few points of lightness from side to
            # side; a pattern (light waves printed on a dark kimono) is ragged too, but its two tones lie far apart,
            # and read at a broader scale it would be painted out (on the test pictures: noise 6 to 20, a pattern 47)
            v_ = Lf[core]
            t_ = float(tone_cuts(v_, 2)[0]) if len(v_) > 400 else 0.0
            lo_, hi_ = (float(np.median(v_[v_ < t_])), float(np.median(v_[v_ >= t_]))) if (
                (v_ < t_).any() and (v_ >= t_).any()) else (0.0, 1.0)
            if hi_ - lo_ < r.get("auto_deblotch_contrast", 0.25) and cut_raggedness(Lf, core, m, U) > thr:
                # the broader the shading's scale the flatter its gradient may be under the noise (a near-white shirt
                # shaded by a few points of lightness): the smallest scale whose cut is clean
                for sc in (3.0, 6.0, 10.0):
                    num = cv2.GaussianBlur(np.where(core, Lf, 0).astype(np.float32), (0, 0), U.len(sc))
                    den = cv2.GaussianBlur(core.astype(np.float32), (0, 0), U.len(sc))
                    if cut_raggedness(np.where(core, num / np.maximum(den, 1e-3), Lf), core, m, U) < 0.5 * thr:
                        break
                r = {**r, "deblotch": sc}
                Lf_pre = Lf
        if drawn and r.get("deblotch"):
            # a part airbrushed in one tone, its shading a few points of lightness of noise (a matte black): a tone
            # cut through it follows the noise and comes out in blotches, so its shading is read at a broader scale.
            # Asked for per part: on a part drawn in tones (a strand's shadow, a pleat's, a knit's bands), which no
            # measure of its lightness tells apart from noise reliably, it would blur the drawing
            sig = U.len(r["deblotch"])
            num = cv2.GaussianBlur(np.where(core, Lf, 0).astype(np.float32), (0, 0), sig)
            den = cv2.GaussianBlur(core.astype(np.float32), (0, 0), sig)
            Lf = np.where(core, num / np.maximum(den, 1e-3), Lf)
        tones = r.get("tones", 2)
        hl = r.get("highlight", {}) or {}
        hl_mode = hl.get("mode", "none")
        if drawn:
            # the painter's own tones: the shadow (and its deeper second shadow) and the light where the source put
            # them
            n_sh = 2 if tones >= 3 else (1 if tones >= 2 else 0)
            k = 1 + n_sh + (1 if hl_mode != "none" else 0)
            cuts = tone_cuts(Lf[core], k) if k >= 2 else []
            if Lf_pre is not None and len(cuts):
                # the broader reading smooths the shadow's edge, not its size: each cut keeps the share of the part it
                # had on the shading as read (a blurred shading has no two tones left, and a fresh cut through it falls
                # near its middle, putting half of a white frill in shadow)
                pre = Lf_pre[core]
                cuts = [float(np.percentile(Lf[core], 100.0 * float((pre < c).mean())))
                        for c in tone_cuts(pre, k)]
            t_dp = cuts[0] if tones >= 3 else -1.0
            t_sh = cuts[n_sh - 1] if tones >= 2 else -1.0
            # a part drawn in fewer tones than the style asks (a two-tone shirt with a white trim): its lightest
            # cluster holds little of it and is not its base; the base is the cluster below it, with one shadow
            if tones >= 3 and (Lf[core] >= t_sh).mean() < 0.2:
                t_sh, t_dp = cuts[0], -1.0
            t_hl = cuts[-1] if hl_mode != "none" else 2.0
            if tones == 2 and hl_mode != "none" and kinds[j] == "hair":
                # hair drawn in two tones, with no light of its own: the middle of three clusters is only the soft step
                # between its two tones, a thin band along the shadow's edge. Its two tones are its base and its
                # shadow, and it has no light to find (else the band is painted as a line of base colour). Only hair:
                # on gloss (patent leather, rubber) the thin bright bands are its sheen
                band = core & (Lf >= t_sh) & (Lf <= t_hl)
                if band.sum() > 50:
                    kk = U.k(5, odd=True)
                    inner = cv2.erode(band.astype(np.uint8), np.ones((kk, kk), np.uint8)) > 0
                    if inner.sum() < 0.3 * band.sum():
                        t_sh, t_hl = float(tone_cuts(Lf[core], 2)[0]), 2.0
            Lh = Lf
            if (tones == 2 and hl_mode == "none" and np.median(Lv[core]) < r.get("dark_below", 0.33) + 0.07
                    and (Lf[core] >= t_sh).mean() < r.get("minor_light", 0.25)):
                # a dark part lit in a few places (worn leather, the sheen on a black strap): that light is wear or
                # gloss, not the part's base colour; the base and the shadow are read from the rest, and the light
                # patches take the base (otherwise the leather comes out mottled, its own colour painted as shadow)
                minor = core & (Lf >= t_sh)
                # wear and sheen lie in patches; a light area the size of a garment is another material in this part
                # (a part that holds a cloak and the trousers under it), and is left alone
                _, _, st_m, _ = cv2.connectedComponentsWithStats(minor.astype(np.uint8), connectivity=8)
                if len(st_m) > 1 and st_m[1:, cv2.CC_STAT_AREA].max() > U.area(r.get("minor_max_patch", 1500.0)):
                    minor = None
                else:
                    rest = core & ~minor
                    if rest.sum() > 60:
                        t_sh = float(tone_cuts(Lf[rest], 2)[0])
        else:
            t_sh = np.percentile(Lf[core], 100 * r.get("share", 0.35)) if tones >= 2 else -1.0
            t_dp = (np.percentile(Lf[core], 100 * r.get("deep_share", 0.35 * r.get("share", 0.35)))
                    if tones >= 3 else -1.0)
            t_hl = np.percentile(Lv[core], 100 * (1 - hl.get("share", 0.06))) if hl_mode != "none" else 2.0
            Lh = Lv
        if p["name"] in rec and hl_mode != "none":
            # a card's highlight is the light on the material (the ring of light on hair), a small part of it: a source
            # drawn light (white hair) has a lit side as wide as its lightest tone, which in the card's colours would
            # read as a second material
            t_hl = max(t_hl, float(np.percentile(Lh[core], 100 * (1 - rc_.HIGHLIGHT_SHARE))))
        mid = core & (Lf >= t_sh) & (Lh <= t_hl)
        if minor is not None:
            mid &= ~minor
        src_px = mid if mid.sum() > 30 else core
        # a colour model given outright (a colour designer's sheet) wins over the one read from the picture
        base = rgb_px(r["base_lab"]) if "base_lab" in r else _base_colour(img, Lv, core, src_px, r)
        layer = np.empty((h, w, 3), np.float32)
        layer[:] = base
        shade = base
        if tones >= 2:
            # a shadow is a real step down from the part's lit tone, not a faint tint (the pink of a knee). Measured
            # from the lit tone, not the part's middle: on a part mostly in shadow the middle lies in the shadow, and
            # half the shadow would be dropped
            lit = core & (Lf >= t_sh)
            ref = float(np.median(Lf[lit])) if lit.sum() >= 20 else float(np.median(Lf[core]))
            cand = core & (Lf < t_sh) & (Lf < ref - r.get("min_depth", 0.0))
            sm, isl, hol = (0.4, 4.44, 4.44) if drawn else (1.0, 33.3, 22.2)
            a_sh = clean_shape(cand, m, U.len(r.get("smooth", sm)), U.area(r.get("min_island", isl)),
                               U.area(r.get("min_hole", hol)))
            if r.get("soft", 0) > 0:                   # a softer turn from light to shadow (film styles)
                a_sh = cv2.GaussianBlur(a_sh, (0, 0), U.len(r["soft"])) * m
            shade = rgb_px(r["shadow_lab"]) if "shadow_lab" in r else _shadow_colour(img, cand, base, r)
            layer = layer * (1 - a_sh[..., None]) + shade * a_sh[..., None]
            if tones >= 3:
                # the second shadow (二影): the deepest of the drawn shadow, under the chin, inside a collar
                cand_d = core & (Lf < t_dp) & (a_sh > 0.5)
                a_dp = clean_shape(cand_d, m, U.len(r.get("smooth", sm)), U.area(r.get("deep_min_island", 2 * isl)),
                                   U.area(r.get("min_hole", hol)))
                if "deep_lab" in r:
                    deep = rgb_px(r["deep_lab"])
                else:
                    s_ = lab_px(shade)
                    dL, da, db = r.get("deep", [-12, 3, -3])
                    deep = rgb_px([max(2.0, s_[0] + dL), s_[1] + da, s_[2] + db])
                layer = layer * (1 - a_dp[..., None]) + deep * a_dp[..., None]
        if hl_mode != "none":
            cand = core & (Lh > t_hl)
            if hl_mode == "crisp":
                sm, isl = (0.33, 2.78) if drawn else (0.53, 4.44)
                a_hl = clean_shape(cand, m, U.len(hl.get("smooth", sm)), U.area(hl.get("min_island", isl)),
                                   U.area(2.78 if drawn else 3.33))
                hl_col = (rgb_px(hl["colour_lab"]) if "colour_lab" in hl
                          else np.median(img[cand], axis=0) if cand.sum() > 20 else base)
            else:                                      # one soft band of a lighter shade
                band = hl.get("band", {})
                sm_ = cv2.GaussianBlur(cand.astype(np.float32), (0, 0), U.len(band.get("soft", 2.67)))
                # only where the light lies in a broad patch: a few bright strands make no band
                a_hl = np.clip((sm_ - 0.25) * 2.5, 0, 1) * m * band.get("alpha", 0.5)
                b = lab_px(base)
                hl_col = rgb_px([b[0] + band.get("lift", 8.0), b[1], b[2] - 2.0])
            layer = layer * (1 - a_hl[..., None]) + hl_col * a_hl[..., None]
        if drawn:
            # most of the way to the flat tones, the lines left as drawn: the source's fine marks (strands, the
            # bangs' tips) stay under the flat colour instead of being painted out
            hd = r.get("harden", 0.85)
            sel = m & ~is_line
            under = img
            if p["name"] in rec:
                # a card's part: the marks left under the flat colour are its own drawing carried onto the card (their
                # lightness kept, the old hue gone), or the old colour would show through in every one of them
                under = img.copy()
                under[m] = rc_.transfer(img, m, rc_.knots(rec[p["name"]], ("deep", "shadow", "base") + (
                    ("highlight",) if hl_mode != "none" else ())), keep=0.0)
            out[sel] = under[sel] + hd * (layer[sel] - under[sel])
        else:
            out[m] = layer[m]
        if p["name"] in rec:
            paint_rec |= m
        model[p["name"]] = {"kind": kinds[j], "base": [round(float(v) * 255) for v in base],
                            "shadow": [round(float(v) * 255) for v in shade]}
        if tones >= 3:
            model[p["name"]]["deep"] = [round(float(v) * 255) for v in deep]

    if rec:
        # under the lines of a card's painted parts, and on the cut-out's soft edge beside them: the ink each pixel held
        # in the source over the part's new fill. A line is laid again over what is beneath it with soft edges (and
        # where the source's own line was too faint to find, at a boundary between a dark part and a light one, what
        # is beneath it is all of the line); the old fill there would show as a rim, a strand of hair drawn all in
        # line out on the cheek in the skin's colour, and a dark outline lost under a light new fill
        ink_L = rc_.ink_lightness(img, L_line, within)
        fill_src = rc_.fill_round(img, L_line, within, U.len(1.5))
        # a strip of a part beyond the line that bounds it belongs to the area on its side
        sl = rc_.slivers(parts, rc_.part_index(subject, rec), within, is_line, U)
        for m_ in sl.values():
            sl_all |= m_
        for j, m_ in sl.items():
            out[m_] = rc_.nearest_colour(out, within & ~is_line & ~sl_all & (parts != j))[m_]
        for j in rc_.part_index(subject, rec):
            ln_m = paint_rec & is_line & (parts == j)
            own = (parts == j) & within & ~is_line & ~sl_all
            if ln_m.any():
                fill_new = rc_.nearest_colour(out, own if own.any() else within & ~is_line)
                out[ln_m] = rc_.ink_over(img, fill_src, fill_new, ln_m, ink_L)
        out = rc_.fringe(out, img, alpha, within, rec_mask, is_line, fill_src, ink_L)

    # ---- cast shadows: one part's shadow on another (the fringe's on the brow, a side lock's on the cheek) -------------
    for c in style.get("touches", {}).get("cast", []):
        src_m, dst_m = of_kind(c["from"]), of_kind(c["onto"]) & within
        cols = [model[q["name"]]["shadow"] for q in plist if kind_of(q) == c["onto"] and q["name"] in model]
        if not cols or not src_m.any():
            continue
        dx, dy = (U.len(v) for v in c.get("offset", [3.0, 6.0]))  # away from the light
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        shifted = cv2.warpAffine(src_m.astype(np.uint8), M, (w, h), flags=cv2.INTER_NEAREST) > 0
        a_c = clean_shape(dst_m & shifted & ~src_m & ~is_line, dst_m, U.len(c.get("smooth", 0.8)),
                          U.area(c.get("min_island", 8.0)), U.area(4.0))
        col_c = np.array(cols[0], np.float32) / 255.0
        out = out * (1 - a_c[..., None]) + col_c * a_c[..., None]

    # ---- the palette, a blush -------------------------------------------------------------------------------------------
    pal = style.get("palette", {})
    if pal:
        # per kind where the style says so (vivid clothes beside skin of a natural chroma), eased across the borders
        maps = {}
        f = lab(out)
        for key, dflt in (("contrast", 1.0), ("lift", 0.0), ("chroma", 1.0)):
            v = np.full((h, w), pal.get(key, dflt), np.float32)
            for k, kp in pal.get("kinds", {}).items():
                if key in kp:
                    v[of_kind(k)] = kp[key]
                if key == "chroma" and "chroma_target" in kp:
                    # a measured style's chroma as a target, not a factor: each material of the kind brought to the
                    # target's median chroma (a muted navy coat gains much, a vivid red one little), within limits
                    lo_k, hi_k = kp.get("chroma_range", [0.8, 2.2])
                    for j, p in enumerate(plist, start=1):
                        if kinds[j] != k:
                            continue
                        m_ = (parts == j) & within & ~is_line
                        if m_.sum() < 50:
                            continue
                        c_med = float(np.median(np.hypot(f[..., 1][m_], f[..., 2][m_])))
                        v[(parts == j) & within] = np.clip(kp["chroma_target"] / max(c_med, 1.0), lo_k, hi_k)
            maps[key] = cv2.GaussianBlur(v, (0, 0), U.len(0.5)) if pal.get("kinds") else v
        ease = pal.get("light_ease")
        if ease:
            # a light colour boosted toward a bold style's chroma turns fluorescent (a mint shirt into neon): the boost
            # eased off above the lightness `ease[0]`, to `ease[1]` of itself at L 100
            L0, keep = ease
            t = np.clip((f[..., 0] - L0) / max(1.0, 100.0 - L0), 0, 1)
            maps["chroma"] = 1.0 + (maps["chroma"] - 1.0) * (1.0 - t * (1.0 - keep))
        if rec and card.get("grade", "card") == "card":
            # a card's colours are the colour designer's: the style's grade passes them by (eased at their borders)
            mb = cv2.GaussianBlur(rec_mask.astype(np.float32), (0, 0), U.len(0.5))
            for key, neutral in (("contrast", 1.0), ("lift", 0.0), ("chroma", 1.0)):
                maps[key] = maps[key] * (1 - mb) + neutral * mb
        pv = pal.get("pivot", 50)
        f[..., 0] = pv + (f[..., 0] - pv) * maps["contrast"] + maps["lift"]
        f = _boost_chroma(f, maps["chroma"], within)
        out = np.where(within[..., None], rgb(f), out)
    blush = style.get("touches", {}).get("blush", {})
    if blush.get("alpha", 0) > 0 and subject.get("blush"):
        a_b = (spots(h, w, subject["blush"]) * blush["alpha"])[..., None]
        out = out * (1 - a_b) + out * np.array(blush.get("colour", [1.0, 0.62, 0.64]), np.float32) * a_b

    # ---- the lines, laid again --------------------------------------------------------------------------------------------
    cut = lines.get("cut", 0.0)
    L_new = np.clip((L_keep - cut) / max(1e-3, 1 - cut), 0, 1)
    grow = U.len(lines.get("grow", 0.0))
    if grow > 0.05:                                    # every line drawn wider by this much on each side
        r = int(np.ceil(grow))
        wider = cv2.dilate(L_new, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
        L_new = L_new + (wider - L_new) * (grow / r)
    ol = lines.get("outline")
    if ol:
        L_new = np.maximum(L_new, ln_.closed_outline(alpha, U.len(ol.get("width", 1.0)), ol.get("smooth", 3))
                           * ol.get("strength", 1.0))
    jit = U.len(lines.get("jitter", 0.0))
    if jit > 0.2:
        # a hand's trace: every line moved a little off the drawing by slow noise, as a tracer's line on a cel wanders
        # off the animator's (a photographed hand-traced cel's line is never the drawing exactly)
        rng = np.random.default_rng(style.get("seed", 7) + 101)
        q = 8
        n1 = cv2.resize(cv2.GaussianBlur(rng.standard_normal((h // q + 2, w // q + 2)).astype(np.float32), (0, 0),
                                         U.len(4.0) / q), (w, h), interpolation=cv2.INTER_CUBIC)
        n2 = cv2.resize(cv2.GaussianBlur(rng.standard_normal((h // q + 2, w // q + 2)).astype(np.float32), (0, 0),
                                         U.len(4.0) / q), (w, h), interpolation=cv2.INTER_CUBIC)
        n1, n2 = n1 / (n1.std() + 1e-6) * jit, n2 / (n2.std() + 1e-6) * jit
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        L_new = cv2.remap(L_new.astype(np.float32), xx + n1, yy + n2, cv2.INTER_LINEAR)
    mode = lines.get("colour", "own")
    strength = lines.get("strength", 1.0)
    outer = lines.get("outer", {})
    thicken, band = U.len(outer.get("thicken", 0.0)), U.len(outer.get("band", 1.67))
    painted = out
    line_src = img
    if follow_lines:
        # a recoloured part's lines are a dark shade of its new colour (色トレス), not of the one it was drawn in
        k_ = 2 * max(1, int(round(U.len(1.5)))) + 1
        sm_ = cv2.GaussianBlur(cv2.dilate(rec_mask.astype(np.uint8), np.ones((k_, k_), np.uint8)).astype(np.float32),
                               (0, 0), U.len(0.5))[..., None]
        # (the lines' own pixels still hold the old drawing: the colour round each line, its new fill, stands in)
        line_src = img * (1 - sm_) + ln_.fill_under(out, L_line) * sm_
    if mode == "own":
        own = lines.get("own", {})
        out = ln_.lay_own(out, line_src, L_new, within, strength, own.get("L", 16.0), own.get("chroma", 0.9),
                          own.get("gap", 9.0))
    elif mode == "ink":
        ink = lines.get("ink", {})
        by = [(skin, ink.get("skin", [36, 18, 18]))] + [(of_kind(k), c) for k, c in ink.get("kinds", {}).items()]
        out = ln_.lay_ink(out, L_new, within, ink.get("ink", [18, 12, 10]), by, strength, thicken, band)
    elif mode == "drawn":
        # the source's own lines, their shapes, weights and soft edges exactly as drawn, over the new paint: each
        # pixel's share of line is how far it lies from the old fill toward the ink, and under it lies the new fill
        dr = lines.get("drawn", {})
        on = (L_line > 0.05) & within
        old_fill = ln_.fill_under(img, L_line)
        new_fill = ln_.fill_under(out, L_line)
        Lo, Ls = lab(old_fill)[..., 0], lab(img)[..., 0]
        ink = np.array(dr.get("ink", [2, 0, 0]), np.float32)
        a = np.clip((Lo - Ls) / np.maximum(Lo - ink[0], 5.0), 0, 1) * on * strength
        col = rgb(ink.reshape(1, 1, 3))[0, 0]
        out = np.where(on[..., None], new_fill * (1 - a[..., None]) + col * a[..., None], out)
        if ol:                                         # the closed outline, in the same ink
            a_ol = np.clip(ln_.closed_outline(alpha, U.len(ol.get("width", 1.0)), ol.get("smooth", 3)), 0, 1)
            out = out * (1 - a_ol[..., None]) + col * a_ol[..., None]
        elif follow_lines:
            # a dark part's edge needs no line: its own dark fill is the edge. Recoloured light, it does, or it melts
            # into what lies behind it: the outline its dark fill made unneeded, in the same ink, along its silhouette
            dark = rec_mask & (lab(img)[..., 0] < 40)
            a_ol = np.clip(ln_.closed_outline(alpha, U.len(1.0), 3), 0, 1) * cv2.GaussianBlur(
                cv2.dilate(dark.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32), (0, 0), 1.0)
            out = out * (1 - a_ol[..., None]) + col * a_ol[..., None]
    elif mode == "trace":
        tr = lines.get("trace", {})
        base_kw = {k: tr[k] for k in ("dark", "cap", "chroma", "neutral_bias") if k in tr}
        out_t = ln_.lay_trace(out, L_new, within, strength, thicken, band, **base_kw)
        for k, kw in tr.get("kinds", {}).items():   # a kind's lines with their own colouring (the hair's)
            alt = ln_.lay_trace(out, L_new, within, strength, thicken, band, **kw)
            by = cv2.GaussianBlur(of_kind(k).astype(np.float32), (0, 0), 1.5)[..., None]
            out_t = out_t * (1 - by) + alt * by
        out = out_t
    else:
        raise ValueError(f"lines.colour must be own, ink, trace or drawn, not {mode!r}")
    if follow_lines and mode in ("own", "trace"):
        # recoloured hair takes its lines along: the line between hair and skin is the hair's (the hair lies over
        # the face), and so is a strand drawn as a line across the face
        hair_rec = of_kind("hair") & rec_mask
        mine = rc_.hair_lines(L_new, hair_rec, prot, U) if hair_rec.any() else None
        if mine is not None and mine.any():
            fill_h = hair_rec & ~is_line & ~sl_all      # (the hair's own fill: not its lines, nor strips given away)
            near = rc_.nearest_colour(painted, fill_h if fill_h.any() else hair_rec)
            if mode == "own":
                own = lines.get("own", {})
                f_ = lab(near)
                f_[..., 0] = own.get("L", 16.0)
                f_[..., 1:] *= own.get("chroma", 0.9)
                col_h = rgb(f_)
            else:
                tr = lines.get("trace", {})
                kw = {**{k: tr[k] for k in ("dark", "cap", "chroma", "neutral_bias") if k in tr},
                      **tr.get("kinds", {}).get("hair", {})}
                col_h = ln_.trace_colour(ln_.fill_under(near, L_new), **kw)
            a_h = (ln_.alpha_of(L_new, strength) * cv2.GaussianBlur(mine.astype(np.float32), (0, 0), 0.6))[..., None]
            out = out * (1 - a_h) + col_h * a_h

    # the face's own features as drawn, in the style's colours for them if it has any (a colour model moved from
    # night to day takes the eyes along); a fine grain if the style has one (a film's, a print's)
    feat = pal.get("features") if pal else None
    src_feat = img
    if feat:
        f2 = lab(img)
        pv2 = feat.get("pivot", 50)
        f2[..., 0] = pv2 + (f2[..., 0] - pv2) * feat.get("contrast", 1.0) + feat.get("lift", 0.0)
        src_feat = rgb(_boost_chroma(f2, np.full((h, w), feat.get("chroma", 1.0), np.float32), within))
        # the eye parts (an iris, the whites) move with the features: a white of the eye a few steps from the
        # skin's colour falls outside the protected boxes' colour test, and must not keep the old colour model
        eyes_m = of_kind("eyes").astype(np.float32)
        if eyes_m.any():
            prot = np.maximum(prot, cv2.GaussianBlur(eyes_m, (0, 0), 1.0))
        # and hair caught in a protected box is hair: it takes the new hair colours, not the old ones (give the
        # irises a part of kind eyes, or a dark iris read as hair would lose its protection)
        hair_m = of_kind("hair").astype(np.float32)
        if hair_m.any():
            prot = prot * (1 - cv2.GaussianBlur(hair_m, (0, 0), 1.0))
    if rec:
        # the irises a card recoloured, as painted outside the boxes (the card's colours exactly); under the style's
        # grade (`grade: style`) carried from the features as the style colours them
        for j, m_ in iris_m.items():
            src_feat = src_feat.copy() if src_feat is img else src_feat
            src_feat[m_] = (eyes_new[m_] if card.get("grade", "card") == "card" else
                            rc_.transfer(src_feat, m_, rc_.knots(rec[plist[j - 1]["name"]]), white_keep=True))
        # any other recoloured part reaching into a box (hair over an eye, a clip by it) is painted with its part
        other = rc_.reaching_in(subject, parts, [j for j in rc_.part_index(subject, rec) if kinds[j] != "eyes"],
                                within & ~is_line, Lv0) | touched_rec
        if other.any():
            prot = prot * (1 - cv2.GaussianBlur(other.astype(np.float32), (0, 0), 1.0))
    if kept_drawn is not None and kept_drawn.any():
        # the pieces the part map joined to a recoloured part by colour alone, and what a touch keeps or paints in its
        # own colour, as drawn (mend_parts)
        out[kept_drawn] = img[kept_drawn]
    out = out * (1 - prot[..., None]) + src_feat * prot[..., None]
    if touches:
        # a touch's own colour (`to`): its drawing carried onto the colour, as an iris is. Where touches overlap, the
        # later one wins, as in the part map; a white keeps its white only inside the protected boxes (a catchlight),
        # so a white shirt takes the colour
        in_box = rc_.box_fade(subject, h, w) > 0
        later = np.zeros((h, w), bool)
        for m_, t in reversed(touches):
            mine = m_ & ~later
            if "to" in t and mine.any():
                out[mine] = rc_.transfer(img, mine, rc_.knots(t["to"]), white_keep=in_box[mine])
            later |= m_
    gr = style.get("texture", {}).get("grain", 0.0)
    if gr > 0:
        rng = np.random.default_rng(style.get("seed", 7))
        g = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), 0.7 * max(1.0, U.s)) * gr
        out = out + g[..., None] * within[..., None]
    return np.clip(out, 0, 1), model


_XYZ_TO_RGB = np.array([[3.2404542, -1.5371385, -0.4985314],
                        [-0.9692660, 1.8760108, 0.0415560],
                        [0.0556434, -0.2040259, 1.0572252]], np.float32)


def _in_gamut(L, a, b, tol=1e-3):
    """Whether Lab colours lie inside sRGB (OpenCV's own conversion clips before it answers, so it cannot tell)."""
    fy = (L + 16) / 116
    f = np.stack([fy + a / 500, fy, fy - b / 200], -1)
    xyz = np.where(f > 6 / 29, f ** 3, 3 * (6 / 29) ** 2 * (f - 4 / 29)) * np.array([0.95047, 1.0, 1.08883], np.float32)
    lin = xyz @ _XYZ_TO_RGB.T
    return ((lin >= -tol) & (lin <= 1 + tol)).all(-1)


def _boost_chroma(f, k, where):
    """Chroma multiplied by k, but never past the gamut: a colour the boost would carry out of sRGB is boosted only as
    far as it still fits, so its hue holds (clipping the channels instead turns a deep teal blue, a plum violet)."""
    ab = f[..., 1:].copy()
    f[..., 1:] = ab * k[..., None]
    over = where & ~_in_gamut(f[..., 0], f[..., 1], f[..., 2])
    if not over.any():
        return f
    Lb, a0, b0, kb = f[..., 0][over], ab[..., 0][over], ab[..., 1][over], k[over]
    lo, hi = np.minimum(kb, 1.0), kb
    for _ in range(12):
        mid = (lo + hi) / 2
        ok = _in_gamut(Lb, a0 * mid, b0 * mid)
        lo, hi = np.where(ok, mid, lo), np.where(ok, hi, mid)
    f[..., 1][over] = a0 * lo
    f[..., 2][over] = b0 * lo
    return f


def _shading_scale(Lv, core, r, drawn, U, cache):
    """The part's lightness at the scale its shadow shapes are read at."""
    if drawn:
        # edge-preserving: the drawn hard steps stay where they are, texture riding on a soft gradient (a shirt's
        # chest) is smoothed away, so a cut through that gradient is a clean curve; at half size, where it is quick
        key = (r.get("scale", 1.0), r.get("range", 0.05))
        if key not in cache:
            h, w = Lv.shape
            half = cv2.resize(Lv.astype(np.float32), (w // 2, h // 2), interpolation=cv2.INTER_AREA)
            sm = cv2.bilateralFilter(half, 0, key[1], U.len(key[0]) / 2)
            cache[key] = cv2.resize(sm, (w, h), interpolation=cv2.INTER_LINEAR)
        return np.where(core, cache[key], Lv)
    fs = U.len(r.get("scale", 1.33))
    if fs <= 0:
        return Lv
    num = cv2.GaussianBlur(Lv * core, (0, 0), fs)
    den = cv2.GaussianBlur(core.astype(np.float32), (0, 0), fs)
    return np.where(den > 1e-3, num / np.maximum(den, 1e-3), Lv)


def _base_colour(img, Lv, core, src_px, r):
    base_pct = r.get("base_pct")
    if base_pct is None and np.median(Lv[core]) < r.get("dark_below", 0.33):
        base_pct = r.get("dark_base_pct", 25)                         # a dark cloth lit here and there stays dark
    if base_pct is not None:                                           # a darker base than the middle (black gloss)
        tb = np.percentile(Lv[src_px], base_pct)
        near_b = src_px & (np.abs(Lv - tb) < 0.03)
        return np.median(img[near_b if near_b.sum() > 20 else src_px], axis=0)
    return np.median(img[src_px], axis=0)


def _shadow_colour(img, cand, base, r):
    if r.get("shadow", "own") == "own":
        own = np.median(img[cand], axis=0) if cand.sum() > 30 else base * 0.8
        tint = np.array(r.get("tint", [1, 1, 1]), np.float32)
        ta = r.get("tint_amount", 0.0)
        return own * (1 - ta) + own * tint * ta
    b = lab_px(base)
    dL, da, db = r.get("derive", [-10, 0, -4])
    return rgb_px([max(2.0, b[0] + dL), b[1] + da, b[2] + db])


def _regions(out, img, m, is_line):
    """An accessory with colours of its own: one flat colour per region its lines enclose."""
    walls = cv2.dilate(is_line.astype(np.uint8), np.ones((3, 3), np.uint8)) | ln_.colour_edges(img)
    _, regs = cv2.connectedComponents((m & (walls == 0)).astype(np.uint8), connectivity=4)
    for i, sl in enumerate(ndi.find_objects(regs), start=1):
        if sl is None:
            continue
        reg = regs[sl] == i
        blk = out[sl]
        blk[reg] = np.median(img[sl][reg], axis=0)
        out[sl] = blk
    rest = m & ~(regs > 0)
    if rest.any():
        fill = np.where((regs > 0)[..., None], out, 0)
        num = cv2.GaussianBlur(fill, (0, 0), 2.0)
        den = cv2.GaussianBlur((regs > 0).astype(np.float32), (0, 0), 2.0)[..., None]
        out[rest] = (num / np.maximum(den, 1e-3))[rest]
    return out
