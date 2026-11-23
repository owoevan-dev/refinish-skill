#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Step 0: can this Python run Refinish, and with versions it was tested on? Changes nothing: it prints what it found
and, when something is missing, the commands that install the tested versions, by their hashes (requirements.txt).

  python check_env.py [--venv DIR]

Prints JSON. "status" is one of:
  ok              ready
  untested        it should run, on versions outside the tested range: say so to the user
  install         run "commands" in order, then use "python" for every script
  python-too-old  needs Python 3.10 or newer

When none of the packages are installed, the commands install them into this Python. When some are, or this Python is
managed by the system, they build a separate environment (--venv, by default .refinish-venv in the current folder), so
nothing another project relies on changes version.

Exit codes: 0 ok, 1 untested, 2 cannot run yet. Standard library only, so it runs before anything is installed."""
import argparse
import json
import os
import platform
import re
import shlex
import subprocess
import sys
from importlib import metadata
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REQUIREMENTS = {False: SKILL / "requirements.txt", True: SKILL / "requirements-headless.txt"}
OPENCV_DISTS = ("opencv-python", "opencv-python-headless", "opencv-contrib-python", "opencv-contrib-python-headless")
# (lowest tested, first version past the tested range)
TESTED = {"numpy": ((2, 0), (3, 0)), "scipy": ((1, 15), (2, 0)), "cv2": ((4, 12), (5, 2))}
MIN_PYTHON = (3, 10)


def version_tuple(text):
    return tuple(int(v) for v in re.findall(r"\d+", str(text))[:2])


def in_range(name, version):
    low, high = TESTED[name]
    return low <= version_tuple(version) < high


def installed_opencv():
    found = {}
    for name in OPENCV_DISTS:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    return found


def try_imports():
    """Each package's version, or why it does not load (a desktop OpenCV without graphics libraries fails here)."""
    versions, errors = {}, {}
    for name in ("numpy", "scipy", "cv2"):
        try:
            versions[name] = __import__(name).__version__
        except Exception as e:                          # (a broken binary raises more than ImportError)
            errors[name] = f"{type(e).__name__}: {str(e)[:160]}"
    return versions, errors


def externally_managed():
    """A Python the system's package manager owns refuses pip (PEP 668). A virtual environment never does."""
    if sys.prefix != sys.base_prefix:
        return False
    stdlib = Path(os.__file__).resolve().parent
    return (stdlib / "EXTERNALLY-MANAGED").is_file()


def wants_headless(dists):
    if any("headless" in d for d in dists):
        return True
    return sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def command_line(argv):
    return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)


def install_steps(venv, separate, headless):
    """The commands, as argument lists, and the Python that has the packages afterwards."""
    python = sys.executable
    steps = []
    if separate:
        steps.append([sys.executable, "-m", "venv", str(venv)])
        python = str(venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    steps.append([python, "-m", "pip", "install", "--only-binary", ":all:", "--require-hashes", "-r",
                  str(REQUIREMENTS[bool(headless)])])
    return steps, python


def report(venv):
    out = {"python": sys.executable, "python_version": platform.python_version()}
    if sys.version_info[:2] < MIN_PYTHON:
        return {**out, "status": "python-too-old",
                "note": f"Refinish needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer: install one, then run this again"}, 2
    versions, errors = try_imports()
    dists = installed_opencv()
    out.update({"versions": versions, "opencv_packages": dists})
    if errors:
        out["errors"] = errors
    clash = len(dists) > 1
    if not errors and not clash:
        outside = sorted(n for n, v in versions.items() if not in_range(n, v))
        if not outside:
            return {**out, "status": "ok"}, 0
        steps, python = install_steps(venv, True, wants_headless(dists))
        return {**out, "status": "untested", "outside_tested_range": outside,
                "note": "this should run, but these versions were not tested; the commands build a separate environment "
                        "with the tested ones",
                "commands": [command_line(s) for s in steps], "argv": steps, "use_python": python}, 1
    nothing_there = not versions and not dists and not any(_is_installed(n) for n in ("numpy", "scipy"))
    separate = not nothing_there or externally_managed()
    # a desktop OpenCV that cannot load is what the headless build is for
    headless = wants_headless(dists) or "libGL" in errors.get("cv2", "") or "libgthread" in errors.get("cv2", "")
    steps, python = install_steps(venv, separate, headless)
    note = ("two OpenCV packages share one cv2 here, so a separate environment is the safe way"
            if clash else "the commands install the tested versions")
    return {**out, "status": "install", "note": note, "commands": [command_line(s) for s in steps], "argv": steps,
            "use_python": python}, 2


def _is_installed(name):
    try:
        metadata.version(name)
        return True
    except metadata.PackageNotFoundError:
        return False


def main():
    ap = argparse.ArgumentParser(description="Check that this Python can run Refinish; changes nothing.")
    ap.add_argument("--venv", default=".refinish-venv", help="where a separate environment would go")
    a = ap.parse_args()
    result, code = report(Path(a.venv).resolve())
    print(json.dumps(result, indent=1))
    sys.exit(code)


if __name__ == "__main__":
    main()
