#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python", "scipy"]
# ///
"""Re-finish a subject in a style: the picture's drawing kept, its surface painted again by the style's rules.

Usage:
  python scripts/refinish.py SUBJECT.json STYLE.json OUT.png [--seed N] [--palette-from SCENE.png]
                             [--hour night|sunset|dusk|film-night] [--no-check]

SUBJECT.json describes one picture (references/subject-file.md); STYLE.json is a style file (styles/ or one written
for the project, references/style-format.md). The part map is built on the first run and reused while the subject
file and its picture are unchanged (scripts/parts.py builds and checks it on its own). Before painting, pixels the
map put in the wrong part are given back to the neighbouring part whose material they are (scripts/_guard.py; the
result's `guard` says what moved).

Engines: cel and paint paint the figure; deai cleans the picture area by area and needs no parts (a subject from
scripts/auto_parts.py without hints is enough), and so does duotone, which puts a flat finish of it in two or three
inks; pixel, tone (manga screentone), print (screen print), woodblock, wash
(watercolour and ink wash), pencil (an animator's key drawing), sticker (a die-cut sticker, the picture grown by its
border), pop (pop art in Ben-Day dots), neon (glowing tubes, the picture grown by the glow), glass (stained glass), papercut (layers of cut
paper) and drawing (charcoal or soft pastel) start from a cel finish of it, the style's `base`. The style's `post` layers (references/style-format.md) are laid over the result; --hour adds the
light of another hour to any style. A cel or paint result in the day's light is checked for the mistakes a reviewer
looks for first (scripts/check_output.py; --no-check skips it); an engine built on a cel finish has that finish
checked; the de-AI engine has its own check (H1).
Prints JSON: the output, the engine, the unit's size in pixels and the engine's own report.
Exit codes: 0 done, 2 bad input.
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core import Units, emit, save_rgba  # noqa: E402
from _style import load_style, load_subject, resolve_style  # noqa: E402
from parts import load_or_build  # noqa: E402

CHECKED = ("cel", "paint")                         # the engines whose results the checks were made for


def finish(sj, st, img, alpha, parts, U, a):
    """The engine's result: (RGB, alpha, report)."""
    engine = st["engine"]
    if engine == "cel":
        import _cel
        out, info = _cel.run(sj, st, img, alpha, parts, U)
        return out, alpha, {"colour_model": info}
    if engine == "paint":
        import _paint
        out, info = _paint.run(sj, st, img, alpha, parts, U, seed=a.seed, palette_from=a.palette_from)
        return out, alpha, info
    if engine == "deai":
        import _deai
        out, info = _deai.run(sj, st, img, alpha, parts, U)
        return out, alpha, info
    if engine == "duotone":
        import _duotone
        out, info = _duotone.run(sj, st, img, alpha, parts, U, seed=st.get("seed", 7) if a.seed is None else a.seed)
        return out, alpha, info
    # the engines that start from a cel finish of the figure
    import _cel
    base = load_style(resolve_style(st.get("base", "tv-cel")))
    cel, _ = _cel.run(sj, base, img, alpha, parts, U)
    if engine == "pixel":
        import _pixel
        px = st.get("pixel", {})
        rgba, pal = _pixel.pixelize(cel, alpha, parts, sj, int(px.get("height", 96)), px.get("outline", "selout"),
                                    int(px.get("colours", 32)), int(px.get("folds_from", 128)))
        return rgba[..., :3], rgba[..., 3], {"size": [rgba.shape[1], rgba.shape[0]], "palette": pal, "_cel": cel}
    if engine == "tone":
        import _tone
        out, info = _tone.run(sj, st, cel, alpha, parts, U, src=img)
        return out, alpha, {**info, "_cel": cel}
    mod = {"print": "_print", "woodblock": "_woodblock", "wash": "_wash", "pencil": "_pencil", "sticker": "_sticker",
           "pop": "_popart", "neon": "_neon", "glass": "_glass",
           "papercut": "_papercut", "drawing": "_drawing"}.get(engine)
    if mod is None:
        raise ValueError(f"no engine {engine!r}")
    out, info = __import__(mod).run(sj, st, cel, alpha, parts, U, seed=st.get("seed", 7) if a.seed is None else a.seed)
    # an engine may give the picture a matte of its own, of another size (a sticker's border and shadow)
    return out, info.pop("alpha", alpha), {**info, "_cel": cel}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subject")
    ap.add_argument("style", help="a style file's path, or a bundled style's id (tv-cel, watercolour, ...)")
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, help="the paint engine's random seed (default: the style's, else 7)")
    ap.add_argument("--palette-from", help="paint: a scene picture whose colours the palette leans toward")
    ap.add_argument("--hour", choices=["night", "sunset", "dusk", "film-night"],
                    help="relight the result for another hour")
    ap.add_argument("--no-check", action="store_true", help="skip the checks on the result (scripts/check_output.py)")
    a = ap.parse_args()
    t0 = time.time()
    sj = load_subject(a.subject)
    st = load_style(resolve_style(a.style))
    img, alpha, parts = load_or_build(sj)
    U = Units(alpha, sj.get("head_px"))
    guard = {}
    if st["engine"] not in ("deai", "duotone"):     # (these read their own areas and need no parts)
        from _guard import guard_parts
        from _style import rule
        sj, parts, guard = guard_parts(sj, st, img, alpha, parts, U, rule)
    out, out_alpha, info = finish(sj, st, img, alpha, parts, U, a)
    info.update(guard)
    cel_base = info.pop("_cel", None)               # the cel finish under a print, wash, pixel or pencil engine
    engine_out = out                                # what the checks look at: the finish before the layers over it
    post = list(st.get("post", [])) + ([{"op": "relight", "hour": a.hour}] if a.hour else [])
    if post and out_alpha.shape == alpha.shape:
        import _post
        out = _post.apply(post, out, out_alpha, parts, sj, U, seed=st.get("seed", 7))
    save_rgba(a.out, out, out_alpha)
    pal = info.pop("palette", None)
    if pal is not None:                             # a pixel sprite's palette, for an editor (Lospec .hex)
        hexp = Path(a.out).with_suffix(".hex")
        hexp.write_text("\n".join("%02x%02x%02x" % tuple(int(round(float(v) * 255)) for v in c) for c in pal) + "\n",
                        encoding="utf-8")
        info.update({"palette": str(hexp), "colours": len(pal)})
    check = {}
    if not a.no_check and st["engine"] in CHECKED + ("deai",):
        from _check import look_checks, review, verdict
        if st["engine"] == "deai":
            import _deai
            found = _deai.check(img, alpha, engine_out, U, sj.get("upscaled", 1),
                                st.get("deai", {}).get("chroma", 1.0))
        else:
            from check_output import run_checks
            found = run_checks(sj, img, alpha, parts, engine_out, out_alpha)
        found += look_checks(sj, img, alpha, parts, engine_out, U, st["engine"])
        rv = Path(a.out).with_suffix(".check.jpg")
        review(engine_out, out_alpha, found, rv)
        check = {"check": {"verdict": verdict(found), "fail": sum(f["level"] == "FAIL" for f in found),
                           "warn": sum(f["level"] == "WARN" for f in found), "review": str(rv),
                           "findings": [f"{f['id']} {f['level']} {f['part']}: {f['what']} at {f['box']}"
                                        for f in found]}}
    elif not a.no_check and cel_base is not None:
        # an engine built on a cel finish: the part-map and paint checks run on that finish, where the mistakes they
        # look for are made (a part painted in another's colour stays wrong in every print or wash made from it)
        from _check import look_checks, review, verdict
        from check_output import run_checks
        found = run_checks(sj, img, alpha, parts, cel_base, alpha)
        # the engine's own look on its own result: the skin, boxes round the features, mottled darks (O7 to O9)
        found += look_checks(sj, img, alpha, parts, engine_out, U, st["engine"])
        rv = Path(a.out).with_suffix(".check.jpg")
        review(cel_base, alpha, found, rv)
        check = {"check": {"verdict": verdict(found), "on": "the cel base (style '%s'); O7 to O9 on the result"
                                                            % st.get("base", "tv-cel"),
                           "fail": sum(f["level"] == "FAIL" for f in found),
                           "warn": sum(f["level"] == "WARN" for f in found), "review": str(rv),
                           "findings": [f"{f['id']} {f['level']} {f['part']}: {f['what']} at {f['box']}"
                                        for f in found],
                           "note": "beyond O7 to O9 the engine's own look is not measured: look at the result too"}}
    elif not a.no_check:
        # an engine with no parts of its own (the duotones): the look checks only, on the result
        from _check import look_checks, review, verdict
        found = look_checks(sj, img, alpha, parts, engine_out, U, st["engine"])
        rv = Path(a.out).with_suffix(".check.jpg")
        review(engine_out if engine_out.shape[:2] == alpha.shape else np.zeros(alpha.shape + (3,), np.float32),
               alpha, found, rv)
        check = {"check": {"verdict": verdict(found), "on": "the result: O7 to O9 only",
                           "fail": sum(f["level"] == "FAIL" for f in found),
                           "warn": sum(f["level"] == "WARN" for f in found), "review": str(rv),
                           "findings": [f"{f['id']} {f['level']} {f['part']}: {f['what']} at {f['box']}"
                                        for f in found]}}
    emit({"out": a.out, "engine": st["engine"], "style": st.get("id", Path(a.style).stem),
          "px_per_unit": round(U.px, 3), "seconds": round(time.time() - t0, 1), **check,
          **{k: v for k, v in info.items() if not isinstance(v, np.ndarray)}})


if __name__ == "__main__":
    main()
