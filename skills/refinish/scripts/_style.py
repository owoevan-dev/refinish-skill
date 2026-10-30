"""Style files and subject files: loading, checking, and each part's rule (the style's defaults, then the rule for
the part's kind, then the subject's own rule for that part, merged key by key)."""
import json
from pathlib import Path

from _core import die

STYLE_FORMAT = "refinish-style/1"
SUBJECT_FORMAT = "refinish-subject/1"
ENGINES = ("cel", "paint", "deai", "duotone", "pixel", "tone", "print", "woodblock", "wash", "pencil", "sticker",
           "pop", "neon", "glass", "papercut", "drawing")
STYLES = Path(__file__).resolve().parent.parent / "styles"
KINDS = ("skin", "hair", "eyes", "cloth", "cloth-white", "cloth-dark", "sheer", "gloss", "metal", "accessory")


def merge(*dicts):
    """Later dicts win key by key; nested dicts (a highlight, a line colouring) are merged the same way."""
    out = {}
    for d in dicts:
        for k, v in (d or {}).items():
            out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def resolve_style(name):
    """A style named by a bundled style's id ("tv-cel") or by a path."""
    p = Path(name)
    if p.suffix == ".json" and p.is_file():
        return p
    q = STYLES / f"{name}.json"
    if q.is_file():
        return q
    die(f"no style '{name}': give a bundled style's id ({', '.join(sorted(x.stem for x in STYLES.glob('*.json')))}) "
        "or a style file's path")


def load_style(path):
    p = Path(path)
    if not p.is_file():
        die(f"no style file at {path}; the bundled styles are in styles/")
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path} is not valid JSON: {e}")
    if st.get("format") != STYLE_FORMAT:
        die(f"{path}: 'format' must be \"{STYLE_FORMAT}\" (see references/style-format.md)")
    if st.get("engine") not in ENGINES:
        die(f"{path}: 'engine' must be one of {', '.join(ENGINES)}")
    return st


def load_subject(path):
    p = Path(path)
    if not p.is_file():
        die(f"no subject file at {path}")
    try:
        sj = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{path} is not valid JSON: {e}")
    if sj.get("format") != SUBJECT_FORMAT:
        die(f"{path}: 'format' must be \"{SUBJECT_FORMAT}\" (see references/subject-file.md)")
    for key in ("image", "families", "parts"):
        if key not in sj:
            die(f"{path}: '{key}' is missing (see references/subject-file.md)")
    for part in sj["parts"]:
        if part.get("family") not in sj["families"]:
            die(f"{path}: part '{part.get('name')}' names the family '{part.get('family')}', which has no samples")
    sj["_dir"] = str(p.resolve().parent)
    sj["_stem"] = p.stem
    return sj


def subject_path(sj, rel):
    """A path in a subject file is relative to the subject file."""
    q = Path(rel)
    return q if q.is_absolute() else Path(sj["_dir"]) / q


def kind_of(part):
    return part.get("kind", part.get("as", "cloth"))


def follow(style, subject):
    """Whether the shadows follow the source's drawn shapes or are read off its forms: the style's choice, unless the
    subject file says otherwise for its picture."""
    return subject.get("follow", style.get("shading", {}).get("follow", "drawn"))


def rule(style, subject, part):
    """One part's rule: the style's shading defaults, its rule for the part's kind, the subject's choice of follow,
    the subject's own rule for the part."""
    return merge(style.get("shading", {}), style.get("kinds", {}).get(kind_of(part), {}),
                 {"follow": subject["follow"]} if "follow" in subject else {},
                 subject.get("rules", {}).get(part["name"], {}))
