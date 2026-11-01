"""Colour cards (refinish-palette/1): reading one, deriving the colours a card leaves out, matching its entries to a
subject's parts, and writing them into the subject as the colour model the cel finish paints.

A colour designer gives each material a base, a shadow, often a second shadow and a highlight; the shadow is a colour
of its own, not the base darkened. When a card gives only a base, the rest is derived in OkLCh (_colour.py) the way
painters and colour designers turn shadows: a step down in lightness, a little more chroma, and a hue turned toward
the ambient light's (blue-violet, the sky's) for most materials, toward red for skin (light scattered under it), a
near-neutral given a cool tint (a white shirt's shadow is lavender-grey, not grey). See references/palette-design.md
in the recolor skill."""
import json
import re
from pathlib import Path

import numpy as np

import _colour as C
from _core import die, lab
from _style import KINDS, kind_of

PALETTE_FORMAT = "refinish-palette/1"
CLOTHLIKE = ("cloth", "cloth-white", "cloth-dark", "sheer", "accessory", "gloss", "metal")
ROLES = ("main", "sub", "accent")
SLOTS = ("base", "shadow", "deep", "highlight")

RULE = {
    "cool_hue": 290.0,       # the hue most shadows turn toward (OkLCh degrees: blue-violet)
    "warm_hue": 30.0,        # skin's shadow turns toward red
    "turn": 0.3,             # the share of the way to that hue
    "turn_cap": 18.0,        # at most this many degrees
    "skin_turn_cap": 10.0,
    "drop": [0.08, 0.04],    # shadow lightness: L - (drop[0] + drop[1] * L), Oklab L 0..1 (about 10-12 of CIELAB L,
                             # the step of a TV colour model)
    "skin_drop": [0.07, 0.03],
    "chroma": 1.08,          # shadow chroma: C * chroma + chroma_add
    "chroma_add": 0.01,
    "skin_chroma": 1.25,     # skin's shadow richer still (the light scattered under it reddens and saturates it), the
    "skin_chroma_add": 0.015,  # more so the lighter the skin (scaled by L), and never more than skin_chroma_cap above
    "skin_chroma_cap": 0.03,   # the base's chroma (a deep brown's shadow is not rust)
    "neutral": 0.03,         # below this chroma a colour is near-neutral (white, grey, black)
    "neutral_tint": 0.025,   # ... and its shadow gets this much chroma at the cool hue
    "deep": 0.8,             # the second shadow: the rule again from the shadow, its drop x this, half the turn, and
                             # no more chroma (a second shadow is deeper, not more vivid)
    "light": 0.4,            # highlight: lightness this share of the way to white (dark hair's light is a mid tone),
    "light_chroma": 0.7,     # its chroma x this,
    "light_hue": 90.0,       # its hue turned a little toward warm light
    "light_turn": 0.15,
    "light_cap": 8.0,
}


def derive(base_rgb, kind="cloth", rule=None):
    """The shadow, second shadow and highlight of a base colour (sRGB 0..1), as sRGB, by the rule above."""
    r = {**RULE, **(rule or {})}
    L, Cc, h = C.to_lch(C.srgb_to_oklab(np.asarray(base_rgb, np.float64)))
    skin = kind == "skin"

    def step(L0, C0, h0, drop_scale=1.0, turn_scale=1.0, richer=True):
        d0, d1 = r["skin_drop"] if skin else r["drop"]
        Ls = max(0.06, L0 - (d0 + d1 * L0) * drop_scale)
        if C0 < r["neutral"]:
            tint = r["neutral_tint"] * (0.6 if L0 < 0.3 else 1.0)
            Cs = max(C0 * r["chroma"], tint) if richer else max(C0, tint)
            hs = r["warm_hue"] if skin else r["cool_hue"]
        else:
            if not richer:
                Cs = C0
            elif skin:
                Cs = min(C0 * (1 + (r["skin_chroma"] - 1) * L0) + r["skin_chroma_add"] * L0, C0 + r["skin_chroma_cap"])
            else:
                Cs = C0 * r["chroma"] + r["chroma_add"]
            cap = (r["skin_turn_cap"] if skin else r["turn_cap"]) * turn_scale
            hs = float(C.hue_turn(h0, r["warm_hue"] if skin else r["cool_hue"], r["turn"] * turn_scale, cap))
        return Ls, Cs, hs

    sL, sC, sh = step(L, Cc, h)
    dL, dC, dh = step(sL, sC, sh, r["deep"], 0.5, richer=False)
    hL = L + (1 - L) * r["light"]
    hC = Cc * r["light_chroma"]
    hh = float(C.hue_turn(h, r["light_hue"], r["light_turn"], r["light_cap"])) if Cc >= r["neutral"] else h
    out = {}
    for k, (l_, c_, h_) in (("shadow", (sL, sC, sh)), ("deep", (dL, dC, dh)), ("highlight", (hL, hC, hh))):
        out[k] = C.oklab_to_srgb(C.from_lch(np.array([l_, c_, h_])))
    return out


def _number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _entry(v, where):
    """A card entry: a base hex, or {base, shadow?, deep?, highlight?, pieces?}; colours as sRGB 0..1."""
    if isinstance(v, str):
        v = {"base": v}
    if not isinstance(v, dict) or "base" not in v:
        die(f"{where}: an entry is a hex colour or an object with 'base' (and optionally shadow, deep, highlight)")
    for k in ("gradient", "pattern"):
        if k in v:
            die(f"{where}.{k}: not painted yet; give the part one base colour")
    e = {}
    for k in SLOTS:
        if k in v:
            c = C.parse_hex(v[k])
            if c is None:
                die(f"{where}.{k}: '{v[k]}' is not a hex colour such as #c8442f")
            e[k] = c
    if "pieces" in v:
        if v["pieces"] not in ("keep", "paint"):
            die(f"{where}.pieces: 'keep' (the part's far pieces inside another part kept as drawn) or 'paint'")
        e["pieces"] = v["pieces"]
    return e


def load_palette(path):
    p = Path(path)
    if not p.is_file():
        die(f"no colour card at {path}")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path} is not valid JSON: {e}")
    if not isinstance(d, dict) or d.get("format") != PALETTE_FORMAT:
        die(f"{path}: 'format' must be \"{PALETTE_FORMAT}\" (see the recolor skill's references/palette-format.md)")
    for key in ("parts", "kinds", "roles", "shadow_rule"):
        if not isinstance(d.get(key, {}), dict):
            die(f"{path}: '{key}' is an object of name: entry pairs, such as {{\"hair\": \"#c8442f\"}}")
    unknown = [k for k in d.get("shadow_rule", {}) if k not in RULE]
    if unknown:
        die(f"shadow_rule: no such setting {', '.join(unknown)} (the settings: {', '.join(RULE)})")
    for k, v in d.get("shadow_rule", {}).items():
        want = RULE[k]
        if isinstance(want, list):
            if not (isinstance(v, list) and len(v) == len(want) and all(_number(x) for x in v)):
                die(f"shadow_rule.{k}: a list of {len(want)} numbers, such as {want}")
        elif not _number(v):
            die(f"shadow_rule.{k}: a number, such as {want}")
    card = {"name": d.get("name", p.stem), "rule": d.get("shadow_rule", {}), "grade": d.get("grade", "card"),
            "lines": d.get("lines", "follow"), "pieces": d.get("pieces", "keep"), "parts": {}, "kinds": {},
            "roles": {}, "iris": None,
            "light": d.get("light")}
    for k, v in d.get("parts", {}).items():
        card["parts"][k.lower()] = _entry(v, f"parts.{k}")
    for k, v in d.get("kinds", {}).items():
        if k not in KINDS:
            die(f"kinds.{k}: a kind is one of {', '.join(KINDS)}")
        card["kinds"][k] = _entry(v, f"kinds.{k}")
    for k, v in d.get("roles", {}).items():
        if k not in ROLES:
            die(f"roles.{k}: a role is one of {', '.join(ROLES)}")
        card["roles"][k] = _entry(v, f"roles.{k}")
    if "iris" in d:
        card["iris"] = _entry(d["iris"], "iris")
    if card["grade"] not in ("card", "style"):
        die("grade: 'card' (the card's colours exactly) or 'style' (the style's colour grade over them)")
    if card["pieces"] not in ("keep", "paint"):
        die("pieces: 'keep' (a part's far pieces inside another part kept as drawn) or 'paint'")
    if card["lines"] not in ("follow", "keep"):
        die("lines: 'follow' (lines take the new colours) or 'keep' (as the style draws them)")
    return card


TOUCH_FORMAT = "refinish-touch/1"


def _point(q):
    return isinstance(q, list) and len(q) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                                       for v in q)


def load_touch(path):
    """A touch file (refinish-touch/1): the touches an agent writes after looking at a result, each a point (or
    points) on the subject's picture and what the colour there becomes: a part's (`as`), a colour of its own (`to`,
    an entry as on a card, with an optional `kind` for its derived colours) or the drawing's (`keep`); optional `tol`
    (CIELAB) and `box`. Checked for its form here; its part names against the subject in apply()."""
    p = Path(path)
    if not p.is_file():
        die(f"no touch file at {path}")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path} is not valid JSON: {e}")
    if not isinstance(d, dict) or d.get("format") != TOUCH_FORMAT:
        die(f"{path}: 'format' must be \"{TOUCH_FORMAT}\" (see the recolor skill's references/palette-format.md)")
    if not isinstance(d.get("touch", []), list):
        die(f"{path}: 'touch' is a list of touches, such as [{{\"at\": [612, 418], \"as\": \"irises\"}}]")
    out = []
    for i, t in enumerate(d.get("touch", [])):
        where = f"touch[{i}]"
        if not isinstance(t, dict):
            die(f"{where}: a touch is an object, such as {{\"at\": [612, 418], \"as\": \"irises\"}}")
        at = t.get("at")
        at = [at] if _point(at) else at
        if not isinstance(at, list) or not at or not all(_point(q) for q in at):
            die(f"{where}.at: a point [x, y] on the subject's picture, or a list of them")
        acts = [k for k in ("as", "to", "keep") if k in t]
        if len(acts) != 1:
            die(f"{where}: one of 'as' (a part's name), 'to' (a colour) or 'keep': true")
        e = {"at": [[float(v) for v in q] for q in at]}
        if "as" in t:
            if not isinstance(t["as"], str) or not t["as"]:
                die(f"{where}.as: the name of a part of the subject")
            e["as"] = t["as"]
        elif "to" in t:
            e["to"] = _entry(t["to"], f"{where}.to")
            e["kind"] = t.get("kind", "cloth")
            if e["kind"] not in KINDS:
                die(f"{where}.kind: one of {', '.join(KINDS)} (how its shadow and highlight are derived)")
        elif t["keep"] is not True:
            die(f"{where}.keep: true (the colour there kept as drawn)")
        else:
            e["keep"] = True
        if "tol" in t:
            if not isinstance(t["tol"], (int, float)) or isinstance(t["tol"], bool) or not 0 < t["tol"] <= 60:
                die(f"{where}.tol: how far (CIELAB, above 0 and at most 60) a colour may be from the point's")
            e["tol"] = float(t["tol"])
        if "box" in t:
            b = t["box"]
            if not (isinstance(b, list) and len(b) == 4 and all(isinstance(v, (int, float)) for v in b)
                    and b[0] < b[2] and b[1] < b[3]):
                die(f"{where}.box: [x0, y0, x1, y1] on the subject's picture")
            e["box"] = [float(v) for v in b]
        out.append(e)
    return out


FACE_WORDS = {"mouth", "lip", "lips", "teeth", "tooth", "tongue", "blush", "brow", "brows", "eyebrow", "eyebrows",
              "lash", "lashes", "eyelash", "eyelashes", "nose", "eye", "eyes", "eyelid", "eyelids"}


def part_stats(subject, img, alpha, parts):
    """Each part's area, median CIELAB colour (from the picture) and share inside the protected boxes, for matching
    irises and roles and for keeping the face's features out of kinds and roles."""
    f = lab(img)
    h, w = alpha.shape
    boxes = np.zeros((h, w), bool)
    for b in subject.get("protect", []):
        x0, y0, x1, y1 = (int(v) for v in b["box"])
        boxes[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
    out = {}
    for j, p in enumerate(subject["parts"], start=1):
        m = (parts == j) & (alpha > 0.5)
        n = int(m.sum())
        out[p["name"]] = {"area": n, "kind": kind_of(p),
                          "lab": np.median(f[m], axis=0) if n else np.array([50.0, 0.0, 0.0]),
                          "in_boxes": float((m & boxes).sum() / n) if n else 0.0}
    return out


def is_feature(name, st):
    """A feature of the face (a mouth, a brow, a blush): recoloured only when the card names it. By the whole words of
    its name ('lips', 'upper_lip', 'eyebrows'; a hair 'clip' is no lip, a 'brown-coat' no brow, 'eyewear' no eye)."""
    words = re.findall(r"[a-z]+", name.lower())
    return st["kind"] != "eyes" and (any(w in FACE_WORDS for w in words)
                                     or st["kind"] == "accessory" and st["in_boxes"] > 0.5)


def is_ink(st):
    """Solid black given a part of its own (ベタ, the spot blacks of an inked style; the checks ask for it, O6): the
    colour of the ink, not of a material, so a card's roles pass it by (a card names it to recolour it)."""
    L, a, b = st["lab"]
    return st["kind"] == "accessory" and L < 20 and np.hypot(a, b) < 8


def is_iris(name, st):
    """An eye part that is an iris, not the white of the eye: named so, or coloured / dark."""
    if st["kind"] != "eyes":
        return False
    n = name.lower()
    if "white" in n:
        return False
    if "iris" in n or "pupil" in n:
        return True
    L, a, b = st["lab"]
    return L < 70 or np.hypot(a, b) > 12


def match(subject, card, stats):
    """{part name: (entry, where it came from)} for every part the card covers; precedence parts > iris > kinds >
    roles (the cloth-like parts ranked by area: main, sub, then accent). A prop (a thing the character holds: a brush,
    a cup) is no part of the costume, so only a card that names it recolours it."""
    got = {}
    props = {p["name"] for p in subject["parts"] if p.get("prop")}
    for p in subject["parts"]:
        n, k = p["name"], kind_of(p)
        if n.lower() in card["parts"]:
            got[n] = (card["parts"][n.lower()], "parts")
        elif n in props:
            continue
        elif card["iris"] is not None and is_iris(n, stats[n]):
            got[n] = (card["iris"], "iris")
        elif k in card["kinds"] and (is_iris(n, stats[n]) if k == "eyes" else
                                     not is_feature(n, stats[n]) and not is_ink(stats[n])):
            got[n] = (card["kinds"][k], "kinds")
    if card["roles"]:
        rest = sorted((n for n, st in stats.items() if n not in got and n not in props and st["kind"] in CLOTHLIKE
                       and st["area"] > 0 and not is_feature(n, st) and not is_ink(st)), key=lambda n: -stats[n]["area"])
        for i, n in enumerate(rest):
            role = ROLES[min(i, 2)]
            if role in card["roles"]:
                got[n] = (card["roles"][role], f"roles.{role}")
    return got


def full_entry(entry, kind, rule):
    """An entry with every slot filled: the card's colours where it gives them, derived ones elsewhere."""
    base = entry.get("base")
    if base is None:                                   # (a gradient alone: its middle stands for the part)
        stops = entry["gradient"]["stops"]
        base = C.parse_hex(stops[len(stops) // 2][1])
    d = derive(base, kind, rule)
    out = {"base": base}
    for k in ("shadow", "deep", "highlight"):
        out[k] = entry.get(k, d[k])
    for k in ("gradient", "pattern", "pieces"):
        if k in entry:
            out[k] = entry[k]
    return out


def cielab(rgb):
    return [round(float(v), 2) for v in lab(np.asarray(rgb, np.float32).reshape(1, 1, 3))[0, 0]]


def apply(subject, card, stats, touches=None):
    """The subject with the card written in: each matched part's colour model as rules (CIELAB, as the cel finish
    reads them) and a `recolour` record (hex colours, where each came from) for the checks and the other engines;
    with touches (load_touch), those too, their part names as the subject spells them and their own colours filled."""
    sj = {k: v for k, v in subject.items() if not k.startswith("_")}
    rules = dict(sj.get("rules", {}))
    rec = {"card": card["name"], "grade": card["grade"], "lines": card["lines"], "parts": {}}
    if card.get("light"):
        rec["light"] = card["light"]
    for n, (entry, where) in match(subject, card, stats).items():
        kind = stats[n]["kind"]
        e = full_entry(entry, kind, card["rule"])
        r = dict(rules.get(n, {}))
        r["base_lab"], r["shadow_lab"], r["deep_lab"] = cielab(e["base"]), cielab(e["shadow"]), cielab(e["deep"])
        r["highlight"] = {**r.get("highlight", {}), "colour_lab": cielab(e["highlight"])}
        rules[n] = r
        rec["parts"][n] = {**{k: C.to_hex(e[k]) for k in SLOTS}, "kind": kind, "from": where,
                           "pieces": e.get("pieces", card["pieces"]),
                           **{k: e[k] for k in ("gradient", "pattern") if k in e}}
    if touches:
        names = {p["name"].lower(): p["name"] for p in subject["parts"]}
        rec["touch"] = []
        for i, t in enumerate(touches):
            e = {k: v for k, v in t.items() if k not in ("to", "kind")}
            if "as" in t:
                if t["as"].lower() not in names:
                    die(f"touch[{i}].as: the subject has no part '{t['as']}' (its parts: {', '.join(names.values())})")
                e["as"] = names[t["as"].lower()]
            if "to" in t:
                full = full_entry(t["to"], t["kind"], card["rule"])
                e["to"] = {k: C.to_hex(full[k]) for k in SLOTS}
            rec["touch"].append(e)
    sj["rules"] = rules
    sj["recolour"] = rec
    return sj
