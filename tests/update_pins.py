#!/usr/bin/env python3
"""Writes the pinned requirements, each version with the SHA-256 of every wheel PyPI publishes for it, so pip installs
only the files as they were published (its hash-checking mode):

  skills/refinish/requirements.txt           what a user installs on a desktop
  skills/refinish/requirements-headless.txt  on a server or in a sandbox
  tests/requirements-oldest.txt              the oldest versions the skill supports, for CI
  tests/requirements-newest.txt              the newest versions it is tested on, for CI

To move a pin: change it below and in check_env.py's TESTED, run this, and let CI test the result.
python tests/update_pins.py"""
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "refinish"
OPENCV = "5.0.0.93"
BY_PYTHON = {
    "numpy": (("2.2.6", 'python_version < "3.11"'), ("2.4.6", 'python_version == "3.11"'), ("2.5.5", 'python_version >= "3.12"')),
    "scipy": (("1.15.3", 'python_version < "3.11"'), ("1.17.1", 'python_version == "3.11"'), ("1.18.1", 'python_version >= "3.12"')),
}
OLDEST = (("numpy", "2.2.6"), ("scipy", "1.15.3"), ("opencv-python-headless", "4.12.0.88"))
NEWEST = (("numpy", "2.5.5"), ("scipy", "1.18.1"), ("opencv-python-headless", "5.1.0.95"))
HEADER = """# The versions Refinish is tested with, each with the SHA-256 of every wheel PyPI publishes for it, so pip installs
# only the files as they were published. scripts/check_env.py prints the install command for your machine.
#
# {which}
# Install one OpenCV package per environment: together they overwrite each other's cv2.
#
# OpenCV stays at 5.0 because the macOS wheels of 5.1 need macOS 15. NumPy and SciPy follow the Python version, since
# their newest releases have dropped the older ones. Written by tests/update_pins.py.
"""
CI_HEADER = "# {which} Written by tests/update_pins.py.\n"


def wheels(package, version):
    url = f"https://pypi.org/pypi/{package}/{version}/json"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "python-client"}), timeout=60) as r:
        rows = json.load(r)["urls"]
    found = sorted({u["digests"]["sha256"] for u in rows if u["packagetype"] == "bdist_wheel" and not u.get("yanked")})
    if not found:
        raise SystemExit(f"{package} {version}: no wheels on PyPI")
    return found


def entry(package, version, marker=""):
    head = f"{package}=={version}" + (f"; {marker}" if marker else "")
    return " \\\n".join([head, *(f"    --hash=sha256:{h}" for h in wheels(package, version))]) + "\n"


def main():
    shared = "".join(entry(p, v, m) for p, rows in BY_PYTHON.items() for v, m in rows)
    for name, package, which in (
            ("requirements.txt", "opencv-python", "For a desktop. On a server or in a sandbox use requirements-headless.txt."),
            ("requirements-headless.txt", "opencv-python-headless", "For a server or a sandbox, with no graphics libraries.")):
        (SKILL / name).write_bytes((HEADER.format(which=which) + shared + entry(package, OPENCV)).encode("utf-8"))
    for name, rows, which in (("requirements-oldest.txt", OLDEST, "The oldest versions Refinish supports, on Python 3.10."),
                              ("requirements-newest.txt", NEWEST, "The newest versions Refinish is tested on, on Python 3.13.")):
        text = CI_HEADER.format(which=which) + "".join(entry(p, v) for p, v in rows)
        (ROOT / "tests" / name).write_bytes(text.encode("utf-8"))
    print("written")


if __name__ == "__main__":
    main()
