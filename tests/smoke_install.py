#!/usr/bin/env python3
"""What a new user goes through, from nothing: only the folders the plugin ships, a Python with no packages, and a
picture in a project folder that has nothing to do with the skill.

  1. check_env.py says what is missing and prints the commands.
  2. Those commands, run in the user's own shell, install the tested versions by their hashes.
  3. check_env.py says ok, on exactly the pinned versions and the right OpenCV package.
  4. Refinish and Recolor each finish the picture, run the way their SKILL.md runs them, and the card's colour arrives.

python tests/smoke_install.py [--work DIR] [--keep]

Everything happens in a new folder of its own inside --work (or the system's temporary folder), and only that folder is
removed afterwards. Needs the network, for pip. Exit code 0 when every step passed. CI runs it on its own."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPACED = "new user"                                     # a space, as in "Program Files" or "My Pictures"
CARD_COLOUR = "#3f5f8a"

MEASURE = """
import json, sys
import cv2, numpy as np
plain, carded, subject, parts_png, colour = sys.argv[1:6]
s = json.load(open(subject, encoding="utf-8"))
hair = [i for i, p in enumerate(s["parts"], 1) if p.get("kind") == "hair"]
assert hair, "no hair part in the subject"
parts = cv2.imread(parts_png, cv2.IMREAD_GRAYSCALE)
a, b = (cv2.imread(p, cv2.IMREAD_UNCHANGED) for p in (plain, carded))
assert a.shape == b.shape, "the two finishes differ in size"
m = np.isin(parts, hair) & (b[..., 3] > 200)
assert m.sum() > 500, "too little hair"
want = np.uint8([[[int(colour[5:7], 16), int(colour[3:5], 16), int(colour[1:3], 16)]]])
lab = lambda im: cv2.cvtColor(im[..., :3], cv2.COLOR_BGR2LAB).astype(np.float32)
target = cv2.cvtColor(want, cv2.COLOR_BGR2LAB).astype(np.float32)[0, 0]
before, after = (np.linalg.norm(np.median(lab(x)[m], axis=0) - target) for x in (a, b))
assert after < 14 and after < before - 10, f"the card's colour did not arrive: {before:.1f} to {after:.1f}"
rest = (parts > 0) & ~np.isin(parts, hair) & (cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8)) == 0)
rest &= cv2.dilate(m.astype(np.uint8), np.ones((15, 15), np.uint8)) == 0
assert np.abs(lab(a)[rest] - lab(b)[rest]).mean() < 1.5, "the card changed parts it does not name"
"""


def run(argv, cwd, ok=(0,), env=None):
    r = subprocess.run([str(a) for a in argv], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    if "Traceback" in r.stderr or r.returncode not in ok:
        raise SystemExit(f"FAILED ({r.returncode}): {' '.join(map(str, argv))}\n{r.stdout[-1500:]}\n{r.stderr[-3000:]}")
    return r


def result(r):
    text = r.stdout
    return json.loads(text[text.find("{"):])


def pinned(requirements, package, python_version):
    """The version a requirements file gives a package on this Python."""
    for line in requirements.read_text(encoding="utf-8").splitlines():
        m = re.match(rf'{re.escape(package)}==([\d.]+)(?:;\s*python_version\s*(<|==|>=)\s*"(\d+)\.(\d+)")?\s*\\?$', line)
        if not m:
            continue
        if not m.group(2):
            return m.group(1)
        limit = (int(m.group(3)), int(m.group(4)))
        if {"<": python_version < limit, "==": python_version == limit, ">=": python_version >= limit}[m.group(2)]:
            return m.group(1)
    raise SystemExit(f"no pin for {package} on Python {python_version}")


def shipped_skills():
    """The skills both hosts would find: Claude's list and Codex's folder must name the same ones."""
    claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    codex = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    listed = {(ROOT / rel).resolve() for rel in claude["skills"]}
    found = {p.parent.resolve() for p in (ROOT / codex["skills"]).glob("*/SKILL.md")}
    if listed != found or len(listed) != 2:
        raise SystemExit("the Claude and Codex manifests do not find the same skills")
    return sorted(listed)


def run_displayed(commands, cwd, env):
    """The commands as a person would paste them into their shell."""
    if os.name == "nt":
        for line in commands["powershell"]:
            run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 f"$ErrorActionPreference='Stop'; {line}; if ($LASTEXITCODE) {{ exit $LASTEXITCODE }}"], cwd, env=env)
    else:
        for line in commands["posix"]:
            run(["sh", "-c", line], cwd, env=env)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", help="a folder to work in; a new folder is made inside it")
    ap.add_argument("--keep", action="store_true", help="keep what it made")
    a = ap.parse_args()
    if a.work:
        Path(a.work).mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="refinish-smoke-", dir=a.work)).resolve()
    try:
        check(work)
    finally:
        if a.keep:
            print("kept:", work)
        else:
            shutil.rmtree(work, ignore_errors=True)


def check(work):
    base = work / SPACED
    home, project = base / "agent skills", base / "my project"
    project.mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    for src in shipped_skills():
        shutil.copytree(src, home / src.name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    refinish, recolor = home / "refinish", home / "recolor"
    scripts = refinish / "scripts"

    print("1. a Python with no packages")
    fresh = base / "python"
    run([sys.executable, "-m", "venv", fresh], project, env=env)
    py = fresh / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    state = result(run([py, scripts / "check_env.py"], project, ok=(2,), env=env))
    assert state["status"] == "install", state
    assert str(project) in state["use_python"], "the install must go into a separate environment"

    print("2. the commands check_env.py printed, in this system's shell")
    run_displayed(state["commands"], project, env)
    py = Path(state["use_python"])

    print("3. check_env.py again")
    state = result(run([py, scripts / "check_env.py"], project, env=env))
    assert state["status"] == "ok", state
    version = tuple(int(v) for v in state["python_version"].split(".")[:2])
    headless = sys.platform.startswith("linux") and not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))
    package = "opencv-python-headless" if headless else "opencv-python"
    assert list(state["opencv_packages"]) == [package], state
    requirements = refinish / ("requirements-headless.txt" if headless else "requirements.txt")
    assert state["versions"]["numpy"] == pinned(requirements, "numpy", version), state
    assert state["versions"]["scipy"] == pinned(requirements, "scipy", version), state
    assert state["opencv_packages"][package] == pinned(requirements, package, version), state

    print("4. Refinish, from the project folder")
    draw = ("import sys, cv2; sys.path.insert(0, sys.argv[1]); from figures import draw_figure; "
            "assert cv2.imwrite(sys.argv[2], draw_figure())")
    run([py, "-c", draw, ROOT / "tests", "drawn.png"], project, env=env)
    run([py, scripts / "check_input.py", "drawn.png"], project, ok=(0, 1), env=env)
    run([py, scripts / "prep.py", "drawn.png", "image.png", "--scale", "2"], project, env=env)
    run([py, scripts / "auto_parts.py", "image.png", "subject.json"], project, ok=(0, 1), env=env)
    style = refinish / "styles" / "tv-cel.json"
    made = result(run([py, scripts / "refinish.py", "subject.json", style, "cel.png"], project, ok=(0, 1), env=env))
    assert "check" in made and (project / "cel.png").stat().st_size > 1000, made

    print("5. Recolor, from its own folder, as its SKILL.md runs it")
    (project / "card.json").write_text(json.dumps({"format": "refinish-palette/1", "name": "smoke",
                                                   "kinds": {"hair": CARD_COLOUR}}), encoding="utf-8")
    run([py, "../refinish/scripts/palette.py", "apply", project / "subject.json", project / "card.json",
         project / "carded.json"], recolor, env=env)
    made = result(run([py, "../refinish/scripts/refinish.py", project / "carded.json", "../refinish/styles/tv-cel.json",
                       project / "recoloured.png"], recolor, ok=(0, 1), env=env))
    assert "check" in made and made["check"]["verdict"] != "fail", made.get("check")
    run([py, "-c", MEASURE, "cel.png", "recoloured.png", "subject.json", "subject.parts.png", CARD_COLOUR], project, env=env)

    print("passed:", json.dumps({"python": state["python_version"], **state["versions"], "opencv": state["opencv_packages"]}))


if __name__ == "__main__":
    main()
