#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Step 0: can this Python run Refinish, and with versions it was tested on? Changes nothing: it prints what it found
and, when something is missing, the commands that install the tested versions by their hashes (requirements.txt).

  python check_env.py [--venv DIR] [--here] [--share]

Prints JSON. "status" is one of:
  ok              ready
  untested        it should run, on versions outside the tested range: say so to the user
  install         run "commands" (or "argv") in order, then use "use_python" for every script
  blocked         something has to be sorted out first: "note" says what
  python-too-old  needs Python 3.10 or newer

The commands build a separate environment (--venv, by default .refinish-venv in the current folder), so nothing another
project relies on changes version. A folder there that is not such an environment is left alone and reported. --here
installs into this Python instead, for a sandbox or a Python kept for Refinish alone.

--share leaves out every path, for pasting into a bug report.

Exit codes: 0 ok, 1 untested, 2 cannot run yet. Standard library only, so it runs before anything is installed."""
import argparse
import importlib.util
import json
import os
import platform
import re
import shlex
import sys
import sysconfig
from importlib import metadata
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REQUIREMENTS = {False: SKILL / "requirements.txt", True: SKILL / "requirements-headless.txt"}
OPENCV_DISTS = ("opencv-python", "opencv-python-headless", "opencv-contrib-python", "opencv-contrib-python-headless")
# (the oldest version CI runs, the first version past the newest it runs)
TESTED = {"numpy": ((2, 2), (2, 6)), "scipy": ((1, 15), (1, 19)), "cv2": ((4, 12), (5, 2))}
PYTHONS = ((3, 10), (3, 15))
VENV_PROMPT = "refinish"


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
    stdlib = sysconfig.get_path("stdlib", sysconfig.get_default_scheme())
    return (Path(stdlib) / "EXTERNALLY-MANAGED").is_file()


def can_make_venv():
    return all(importlib.util.find_spec(m) is not None for m in ("venv", "ensurepip"))


def wants_headless(dists):
    if any("headless" in d for d in dists):
        return True
    return sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def venv_python(venv):
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def venv_state(venv):
    """new: nothing there. ours: an environment these commands built. foreign: anything else, which is left alone."""
    if venv.is_symlink():
        return "foreign"
    if not venv.exists():
        return "new"
    if not venv.is_dir():
        return "foreign"
    if not any(venv.iterdir()):
        return "new"
    cfg = venv / "pyvenv.cfg"
    if cfg.is_file() and not cfg.is_symlink() and venv_python(venv).exists():
        text = cfg.read_text(encoding="utf-8", errors="replace")
        if re.search(rf"^prompt\s*=\s*['\"]?{VENV_PROMPT}['\"]?\s*$", text, re.M):
            return "ours"
    return "foreign"


def powershell_quote(arg):
    return "'" + arg.replace("'", "''") + "'"


def shell_commands(steps):
    """The same commands for a person's shell. Agents should prefer "argv", which needs no quoting at all."""
    out = {"posix": [shlex.join(s) for s in steps]}
    if os.name == "nt":
        out["powershell"] = ["& " + " ".join(powershell_quote(a) for a in s) for s in steps]
    return out


def install_steps(venv, here, headless, state="new"):
    """The commands, as argument lists, and the Python that has the packages afterwards."""
    python = sys.executable if here else str(venv_python(venv))
    steps = []
    if not here and state == "new":
        steps.append([sys.executable, "-m", "venv", "--prompt", VENV_PROMPT, str(venv)])
    steps.append([python, "-m", "pip", "install", "--only-binary", ":all:", "--require-hashes", "-r",
                  str(REQUIREMENTS[bool(headless)])])
    return steps, python


def plan(out, venv, here, headless, status, note, code):
    """The result with its install commands, or what stands in the way of them."""
    if sys.version_info[:2] >= PYTHONS[1]:
        return {**out, "status": "blocked" if status == "install" else status,
                "note": f"the pinned packages are for Python {PYTHONS[0][0]}.{PYTHONS[0][1]} to "
                        f"{PYTHONS[1][0]}.{PYTHONS[1][1] - 1}: use one of those"}, code
    if here and externally_managed():
        return {**out, "status": "blocked", "note": "the system manages this Python, so pip will not install into it: "
                                                    "leave out --here to get a separate environment"}, 2
    state = "here" if here else venv_state(venv)
    if state == "foreign":
        return {**out, "status": "blocked", "note": f"{venv} exists and is not an environment these commands built, so "
                                                    "it is left alone: name another folder with --venv"}, 2
    if state == "new" and not can_make_venv():
        return {**out, "status": "blocked", "note": "this Python cannot make virtual environments: on Debian or Ubuntu "
                                                    "install the python3-venv package, then run this again"}, 2
    steps, python = install_steps(venv, here, headless, state)
    return {**out, "status": status, "note": note, "commands": shell_commands(steps), "argv": steps,
            "use_python": python}, code


def report(venv, here=False):
    out = {"python": sys.executable, "python_version": platform.python_version(), "platform": sys.platform}
    if sys.version_info[:2] < PYTHONS[0]:
        return {**out, "status": "python-too-old",
                "note": f"Refinish needs Python {PYTHONS[0][0]}.{PYTHONS[0][1]} or newer: install one, then run this "
                        "again"}, 2
    versions, errors = try_imports()
    dists = installed_opencv()
    out.update({"versions": versions, "opencv_packages": dists})
    if errors:
        out["errors"] = errors
    clash = len(dists) > 1
    headless = wants_headless(dists) or any(k in errors.get("cv2", "") for k in ("libGL", "libgthread"))
    if not errors and not clash:
        outside = sorted(n for n, v in versions.items() if not in_range(n, v))
        if sys.version_info[:2] >= PYTHONS[1]:
            outside.append("python")
        if not outside:
            return {**out, "status": "ok"}, 0
        out["outside_tested_range"] = outside
        return plan(out, venv, here, headless, "untested",
                    "this should run, but these versions were not tested; the commands build a separate environment "
                    "with the tested ones", 1)
    note = ("two OpenCV packages share one cv2 here, so a separate environment is the safe way" if clash
            else "the commands install the tested versions")
    return plan(out, venv, here and not clash, headless, "install", note, 2)


def shareable(result):
    """The report without a path or a raw message: safe to paste in public."""
    keep = {k: result[k] for k in ("status", "python_version", "platform", "versions", "outside_tested_range")
            if k in result}
    keep["opencv_packages"] = result.get("opencv_packages", {})
    keep["error_kinds"] = {k: v.split(":")[0] for k, v in result.get("errors", {}).items()}
    return keep


def main():
    ap = argparse.ArgumentParser(description="Check that this Python can run Refinish; changes nothing.")
    ap.add_argument("--venv", default=".refinish-venv", help="where a separate environment goes")
    ap.add_argument("--here", action="store_true", help="install into this Python instead of a separate environment")
    ap.add_argument("--share", action="store_true", help="leave out every path, for a bug report")
    a = ap.parse_args()
    result, code = report(Path(os.path.abspath(a.venv)), a.here)
    print(json.dumps(shareable(result) if a.share else result, indent=1))
    sys.exit(code)


if __name__ == "__main__":
    main()
