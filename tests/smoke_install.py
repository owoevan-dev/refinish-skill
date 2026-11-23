#!/usr/bin/env python3
"""What a new user goes through, from nothing: only the folders the plugin ships, a Python with no packages, and a
picture in a project folder that has nothing to do with the skill.

  1. check_env.py says what is missing and prints the commands.
  2. Those commands install the tested versions.
  3. check_env.py says ok, on exactly the pinned versions.
  4. Refinish and Recolor each finish the picture, run the way their SKILL.md runs them.

python tests/smoke_install.py [--work DIR] [--keep]

Needs the network, for pip. Exit code 0 when every step passed. Not part of the pytest run; CI runs it on its own."""
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
# a space, as in "Program Files" or "My Pictures"
SPACED = "new user"


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    work = Path(a.work).resolve() if a.work else Path(tempfile.mkdtemp(prefix="refinish-smoke-"))
    base = work / SPACED
    if base.exists():
        shutil.rmtree(base)
    home, project = base / "agent skills", base / "my project"
    project.mkdir(parents=True)
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    # the plugin's own list of what it ships, and nothing else
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    for rel in plugin["skills"]:
        src = (ROOT / rel).resolve()
        shutil.copytree(src, home / src.name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    refinish, recolor = home / "refinish", home / "recolor"
    scripts = refinish / "scripts"

    print("1. a Python with no packages")
    fresh = base / "python"
    run([sys.executable, "-m", "venv", fresh], project, env=env)
    py = fresh / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    r = run([py, scripts / "check_env.py"], project, ok=(2,), env=env)
    state = result(r)
    assert state["status"] == "install", state

    print("2. the commands check_env.py printed")
    for argv in state["argv"]:
        run(argv, project, env=env)
    py = Path(state["use_python"])

    print("3. check_env.py again")
    state = result(run([py, scripts / "check_env.py"], project, env=env))
    assert state["status"] == "ok", state
    version = tuple(int(v) for v in state["python_version"].split(".")[:2])
    requirements = refinish / "requirements.txt"
    assert state["versions"]["numpy"] == pinned(requirements, "numpy", version), state
    assert state["versions"]["scipy"] == pinned(requirements, "scipy", version), state
    assert len(state["opencv_packages"]) == 1, state
    assert set(state["opencv_packages"].values()) == {pinned(requirements, "opencv-python", version)}, state

    print("4. Refinish, from the project folder")
    draw = ("import sys, cv2; sys.path.insert(0, sys.argv[1]); from figures import draw_figure; "
            "assert cv2.imwrite(sys.argv[2], draw_figure())")
    run([py, "-c", draw, ROOT / "tests", "drawn.png"], project, env=env)
    run([py, scripts / "check_input.py", "drawn.png"], project, ok=(0, 1), env=env)
    run([py, scripts / "prep.py", "drawn.png", "image.png", "--scale", "2"], project, env=env)
    run([py, scripts / "auto_parts.py", "image.png", "subject.json"], project, ok=(0, 1), env=env)
    made = result(run([py, scripts / "refinish.py", "subject.json", refinish / "styles" / "tv-cel.json", "cel.png"],
                      project, ok=(0, 1), env=env))
    assert "check" in made and (project / "cel.png").stat().st_size > 1000, made

    print("5. Recolor, from its own folder, as its SKILL.md runs it")
    (project / "card.json").write_text(json.dumps({"format": "refinish-palette/1", "name": "smoke",
                                                   "kinds": {"hair": "#3f5f8a"}}), encoding="utf-8")
    run([py, "../refinish/scripts/palette.py", "apply", project / "subject.json", project / "card.json",
         project / "carded.json"], recolor, env=env)
    made = result(run([py, "../refinish/scripts/refinish.py", project / "carded.json",
                       "../refinish/styles/film-everyday-cel.json", project / "recoloured.png"],
                      recolor, ok=(0, 1), env=env))
    assert "check" in made and (project / "recoloured.png").stat().st_size > 1000, made
    differ = ("import sys, cv2, numpy as np; a, b = (cv2.imread(p, cv2.IMREAD_UNCHANGED) for p in sys.argv[1:3]); "
              "assert a is not None and b is not None and a.shape == b.shape and (a != b).any()")
    run([py, "-c", differ, "cel.png", "recoloured.png"], project, env=env)

    print("passed:", json.dumps({"python": state["python_version"], **state["versions"],
                                 "opencv": state["opencv_packages"]}))
    if not a.keep and not a.work:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
