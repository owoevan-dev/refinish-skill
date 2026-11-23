"""The JSON files a script is given, checked before anything is computed from them, so a wrong field stops with a message
that names it. These files are data and may come from someone else: nothing in them is ever run.

Each check knows the shape of its format (references/subject-file.md, style-format.md, recipes.md, compositing.md,
cutout.md). A key it does not know is left alone, so a file written for a later version still loads."""
import json
import math
from pathlib import Path

from _files import MAX_PIXELS, die

HOURS = ("night", "sunset", "dusk", "film-night")
POST_OPS = ("relight", "paper", "grain", "halation", "soften", "curve", "focus", "bokashi", "mist", "wet_sky")
MAX_PARTS = 255                                         # (a part map is 8 bits)


def is_text(v):
    return isinstance(v, str) and bool(v)


def is_bool(v):
    return isinstance(v, bool)


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def is_pos(v):
    return is_num(v) and v > 0


def is_unit(v):
    return is_num(v) and 0 <= v <= 1


def is_not_negative(v):
    return is_num(v) and v >= 0


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def is_nums(v, n):
    return isinstance(v, list) and len(v) == n and all(is_num(x) for x in v)


def is_point(v):
    return is_nums(v, 2)


def is_box(v):
    return is_nums(v, 4)


def is_points(v):
    return isinstance(v, list) and all(is_point(p) for p in v)


def is_polygon(v):
    return is_points(v) and len(v) >= 3


def is_dict(v):
    return isinstance(v, dict)


class Check:
    def __init__(self, path, page):
        self.path, self.page = path, page

    def fail(self, key, want):
        die(f"{self.path}: '{key}' must be {want} ({self.page})")

    def field(self, obj, key, test, want, where="", required=False):
        name = f"{where}{key}"
        if key not in obj:
            if required:
                self.fail(name, want)
            return
        if not test(obj[key]):
            self.fail(name, want)

    def dicts(self, obj, key, where=""):
        """The list of objects at key (empty when the key is not there), each with its name for messages."""
        if key not in obj:
            return []
        items = obj[key]
        if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
            self.fail(f"{where}{key}", "a list of objects")
        return [(f"{where}{key}[{i}].", item) for i, item in enumerate(items)]


def subject(d, path):
    c = Check(path, "references/subject-file.md")
    c.field(d, "image", is_text, "a picture's file name", required=True)
    c.field(d, "regions", is_text, "a region map's file name")
    c.field(d, "families", is_dict, "an object of colour families", required=True)
    for name, pts in d["families"].items():
        if not is_points(pts):
            c.fail(f"families.{name}", "a list of [x, y] points")
    parts = c.dicts(d, "parts")
    if "parts" not in d:
        c.fail("parts", "a list of objects")
    if len(parts) > MAX_PARTS:
        c.fail("parts", f"at most {MAX_PARTS} parts")
    for at, p in parts:
        c.field(p, "name", is_text, "a name", at, required=True)
        c.field(p, "family", is_text, "the name of a family", at, required=True)
        c.field(p, "kind", is_text, "a kind", at)
        c.field(p, "as", is_text, "a kind", at)
        c.field(p, "regions", lambda v: isinstance(v, list) and all(is_int(i) for i in v), "a list of region numbers", at)
        c.field(p, "poly", is_polygon, "a polygon, a list of at least three [x, y] points", at)
        c.field(p, "polys", lambda v: isinstance(v, list) and all(is_polygon(q) for q in v), "a list of polygons", at)
        for flag in ("only_placed", "exact", "prop"):
            c.field(p, flag, is_bool, "true or false", at)
    for at, b in c.dicts(d, "protect"):
        c.field(b, "name", is_text, "a name", at, required=True)
        c.field(b, "box", is_box, "[x0, y0, x1, y1]", at, required=True)
        c.field(b, "de", is_pos, "a positive number", at)
    for at, f in c.dicts(d, "focal"):
        c.field(f, "centre", is_point, "[x, y]", at, required=True)
        c.field(f, "radii", lambda v: is_point(v) and all(x > 0 for x in v), "two positive numbers", at, required=True)
        c.field(f, "strength", is_num, "a number", at)
    c.field(d, "blush", lambda v: isinstance(v, list) and all(
        isinstance(s, list) and len(s) in (3, 4) and all(is_num(x) for x in s) and all(x > 0 for x in s[2:]) for s in v),
        "a list of [x, y, rx, ry] spots")
    for key in ("upscaled", "head_px", "protect_de"):
        c.field(d, key, is_pos, "a positive number")
    c.field(d, "follow", lambda v: v in ("drawn", "form"), "drawn or form")
    c.field(d, "rules", lambda v: isinstance(v, dict) and all(isinstance(r, dict) for r in v.values()),
            "an object of per-part rules")
    c.field(d, "recolour", is_dict, "the object palette.py wrote")


def _kind(v):
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    return {str: "text", list: "list", dict: "object", type(None): "null"}[type(v)]


def _learn(v, at, out):
    out.setdefault(at, set()).add(_kind(v))
    if isinstance(v, dict):
        for k, x in v.items():
            _learn(x, f"{at}.{k}" if at else k, out)
    elif isinstance(v, list):
        for x in v:
            _learn(x, f"{at}[]", out)


_shapes = {}


def style_shapes(folder):
    """What each field holds across the bundled styles: a number, a list of numbers, an object..."""
    if not _shapes:
        for p in sorted(Path(folder).glob("*.json")):
            _learn(json.loads(p.read_text(encoding="utf-8")), "", _shapes)
    return _shapes


def _compare(v, at, known, c):
    if at in known and _kind(v) not in known[at]:
        c.fail(at, f"{' or '.join(sorted(known[at]))}, as in the bundled styles")
    if isinstance(v, dict):
        for k, x in v.items():
            _compare(x, f"{at}.{k}" if at else k, known, c)
    elif isinstance(v, list):
        for x in v:
            _compare(x, f"{at}[]", known, c)


def post_layers(value, c, known):
    if not isinstance(value, list) or not all(isinstance(x, dict) for x in value):
        c.fail("post", "a list of objects")
    for i, layer in enumerate(value):
        if layer.get("op") not in POST_OPS:
            c.fail(f"post[{i}].op", f"one of {', '.join(POST_OPS)}")
        _compare(layer, "post[]", known, c)


def style(d, path, folder):
    """A style's fields hold what the same fields hold in the bundled styles."""
    if Path(path).resolve().parent == Path(folder).resolve():
        return
    c = Check(path, "references/style-format.md")
    known = style_shapes(folder)
    if "post" in d:
        post_layers(d["post"], c, known)
    _compare({k: v for k, v in d.items() if k != "post"}, "", known, c)


def hints(d, path):
    c = Check(path, "references/subject-file.md")
    if not isinstance(d, dict):
        die(f"{path} is not a hints file: hints are one JSON object (references/subject-file.md)")
    c.field(d, "complete", is_bool, "true or false")
    c.field(d, "eyes", lambda v: isinstance(v, list) and all(is_box(b) for b in v), "a list of [x0, y0, x1, y1] boxes")
    c.field(d, "mouth", is_box, "[x0, y0, x1, y1]")
    parts = c.dicts(d, "parts")
    if len(parts) > MAX_PARTS:
        c.fail("parts", f"at most {MAX_PARTS} parts")
    for at, p in parts:
        c.field(p, "name", is_text, "a name", at, required=True)
        c.field(p, "kind", is_text, "a kind", at)
        c.field(p, "at", is_points, "a list of [x, y] points", at)
        c.field(p, "box", is_box, "[x0, y0, x1, y1]", at)
        c.field(p, "boxes", lambda v: isinstance(v, list) and all(is_box(b) for b in v), "a list of boxes", at)
        c.field(p, "within", is_box, "[x0, y0, x1, y1]", at)
        c.field(p, "prop", is_bool, "true or false", at)


def outline(d, path):
    c = Check(path, "references/cutout.md")
    if not isinstance(d, dict):
        die(f"{path} is not an outline file: an outline is one JSON object (references/cutout.md)")

    def polygons(v):
        return is_polygon(v) or (isinstance(v, list) and all(is_polygon(q) for q in v))
    c.field(d, "outline", polygons, "a polygon or a list of polygons", required=True)
    c.field(d, "holes", polygons, "a polygon or a list of polygons")
    c.field(d, "band", lambda v: is_pos(v) and v <= 2000, "a positive number, 2000 at most")
    for key in ("keep", "drop"):
        c.field(d, key, is_points, "a list of [x, y] points")
    for at, b in c.dicts(d, "bands"):
        c.field(b, "box", is_box, "[x0, y0, x1, y1]", at, required=True)
        c.field(b, "band", lambda v: is_pos(v) and v <= 2000, "a positive number, 2000 at most", at, required=True)


def _where(v):
    if v is None or isinstance(v, str):
        return True
    if isinstance(v, list):
        return all(isinstance(w, str) for w in v)
    if not isinstance(v, dict):
        return False
    words = all(isinstance(v.get(k, []), list) and all(isinstance(w, str) for w in v.get(k, [])) for k in ("only", "not"))
    return words and ("box" not in v or is_box(v["box"]))


def recipe(d, path, folder):
    c = Check(path, "references/recipes.md")
    c.field(d, "subject", is_text, "a subject file's path", required=True)
    c.field(d, "base", is_text, "a style or \"source\"")
    c.field(d, "hour", lambda v: v in HOURS, f"one of {', '.join(HOURS)}")
    c.field(d, "seed", is_int, "a whole number")
    for at, lay in c.dicts(d, "layers"):
        c.field(lay, "style", is_text, "a style", at, required=True)
        c.field(lay, "where", _where, "a word, a list of words, or {only, not, box}", at)
        c.field(lay, "blend", is_text, "a blend mode", at)
        c.field(lay, "opacity", is_unit, "a number from 0 to 1", at)
        c.field(lay, "feather", is_not_negative, "a number, 0 or more", at)
    if "post" in d:
        post_layers(d["post"], c, style_shapes(folder))


def _grade(g, at, c):
    if not isinstance(g, dict):
        c.fail(at, "an object")
    for key, value in g.items():
        if key == "regions":
            if not isinstance(value, list) or not all(isinstance(r, dict) for r in value):
                c.fail(f"{at}.regions", "a list of objects")
            for i, r in enumerate(value):
                for k, x in r.items():
                    if k == "hue" and not is_point(x):
                        c.fail(f"{at}.regions[{i}].hue", "[from, to] in degrees")
                    if k != "hue" and not isinstance(x, bool) and not is_num(x):
                        c.fail(f"{at}.regions[{i}].{k}", "a number")
        elif not is_num(value):
            c.fail(f"{at}.{key}", "a number")


def scene(d, path):
    c = Check(path, "references/compositing.md")
    if not isinstance(d, dict):
        die(f"{path} is not a scene: a scene is one JSON object (references/compositing.md)")
    c.field(d, "frame", lambda v: isinstance(v, list) and len(v) == 2 and all(is_int(x) and x > 0 for x in v)
            and v[0] * v[1] <= MAX_PIXELS, f"[width, height] in pixels, {MAX_PIXELS} pixels at most")
    c.field(d, "camera", is_dict, "an object")
    cam = d.get("camera", {})
    for key in ("vignette", "grain"):
        c.field(cam, key, is_not_negative, "a number, 0 or more", "camera.")
    c.field(cam, "seed", is_int, "a whole number", "camera.")
    if cam.get("bloom"):
        c.field(cam, "bloom", lambda v: isinstance(v, dict) and all(is_num(x) for x in v.values()),
                "an object of numbers", "camera.")
    c.field(d, "background", is_dict, "an object", required=True)
    bk = d["background"]
    c.field(bk, "image", is_text, "a picture's file name", "background.", required=True)
    c.field(bk, "zoom", is_pos, "a positive number", "background.")
    c.field(bk, "centre", is_point, "[x, y] from 0 to 1", "background.")
    c.field(bk, "blur", is_not_negative, "a number, 0 or more", "background.")
    if bk.get("grade"):
        _grade(bk["grade"], "background.grade", c)
    for at, ly in c.dicts(d, "layers"):
        c.field(ly, "image", is_text, "a picture's file name", at, required=True)
        c.field(ly, "place", lambda v: is_nums(v, 3) and v[2] > 0, "[x0, y_bottom, scale]", at, required=True)
        for key in ("blur", "sharpen", "wrap", "wrap_width"):
            c.field(ly, key, is_not_negative, "a number, 0 or more", at)
        c.field(ly, "clear_halo", is_bool, "true or false", at)
        if ly.get("grade"):
            _grade(ly["grade"], f"{at}grade", c)
