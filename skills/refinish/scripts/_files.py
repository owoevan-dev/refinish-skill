"""Files and how a script ends. Pictures open from any path, a result never replaces what its run read, every file is
written whole or not at all, and a bad input stops with a message.

Exit codes of every script: 0 done, 1 done with something to look at, 2 bad input or a file it cannot use, 3 an error it
did not expect."""
import json
import math
import os
import stat
import struct
import sys
import tempfile
import time
import traceback
from pathlib import Path

MAX_PIXELS = 100_000_000                                # (10000 x 10000; a header can claim far more than a file holds)
MAX_JSON_BYTES = 32 * 2 ** 20
_inputs = set()


def die(msg, code=2):
    """Stop with an actionable message on stderr."""
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def run_cli(main):
    """A script's main. Exit codes: 0 done, 1 done with something to look at, 2 bad input or a file it cannot use, and
    3 for what the script did not expect. A Python error also exits 1, which would read as "done with doubts", so none
    is left to end the script. REFINISH_DEBUG=1 prints the whole traceback."""
    try:
        main()
    except OSError as e:
        die(f"cannot read or write {e.filename or 'a file'}: {e.strerror or e}")
    except MemoryError:
        die(f"not enough memory for this picture: try a smaller one (limit {MAX_PIXELS} pixels)")
    except RecursionError:
        die("an input file is nested too deeply")
    except Exception as e:
        if os.environ.get("REFINISH_DEBUG"):
            traceback.print_exc()
        last = traceback.extract_tb(e.__traceback__)[-1]    # (no message: it can quote a path or an input's value)
        print(f"error: unexpected {type(e).__name__} at {Path(last.filename).name}:{last.lineno}. Check the input "
              "files; if they are right, this is a bug: please report this line. REFINISH_DEBUG=1 shows the details.",
              file=sys.stderr)
        sys.exit(3)


def _identity(path):
    try:
        s = os.stat(path)
    except (OSError, ValueError):
        return None
    return s.st_dev, s.st_ino


def note_input(path):
    """A file this run read: no output of the run may replace it, however its path is written."""
    i = _identity(path)
    if i:
        _inputs.add(i)


def refuse_input(path):
    if _identity(path) in _inputs:
        die(f"{path} is one of this run's inputs: give the result another name, so the original is kept")


def relative_path(target, start):
    """A path as a subject file keeps it: relative where it can be, so the file does not name the folders above it."""
    try:
        return os.path.relpath(Path(target).resolve(), Path(start).resolve()).replace("\\", "/")
    except ValueError:                                  # (another drive, on Windows)
        return str(Path(target).resolve()).replace("\\", "/")


def picture_size(data):
    """(width, height) from a PNG, JPEG or WebP header, before anything is decoded; None for another format."""
    b = data[:64].tobytes() if hasattr(data, "tobytes") else bytes(data[:64])
    try:
        if b[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", b[16:24])
        if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
            if b[12:16] == b"VP8X":
                return 1 + int.from_bytes(b[24:27], "little"), 1 + int.from_bytes(b[27:30], "little")
            if b[12:16] == b"VP8L":
                v = int.from_bytes(b[21:25], "little")
                return 1 + (v & 0x3FFF), 1 + ((v >> 14) & 0x3FFF)
            if b[12:16] == b"VP8 ":
                return struct.unpack("<HH", b[26:30])[0] & 0x3FFF, struct.unpack("<HH", b[26:30])[1] & 0x3FFF
        if b[:2] == b"\xff\xd8":
            raw, pos = bytes(data[:2 ** 20]) if not hasattr(data, "tobytes") else data[:2 ** 20].tobytes(), 2
            while pos + 9 < len(raw):
                if raw[pos] != 0xFF:
                    return None
                marker = raw[pos + 1]
                if marker == 0xFF:
                    pos += 1
                elif 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", raw[pos + 5:pos + 9])
                    return w, h
                else:
                    pos += 2 + struct.unpack(">H", raw[pos + 2:pos + 4])[0]
    except (struct.error, IndexError):
        return None
    return None


def read_picture(path, flags=-1, is_input=True):
    """cv2.imread that opens any path: on Windows imread cannot open a folder or file named in Chinese, Japanese or
    Korean. Refuses a picture whose header claims more than MAX_PIXELS before decoding it. None if it cannot be read.
    flags: OpenCV's; -1 is IMREAD_UNCHANGED."""
    import cv2
    import numpy as np
    try:
        data = np.fromfile(str(path), np.uint8)
    except (OSError, ValueError):
        return None
    if data.size == 0:
        return None
    size = picture_size(data)
    if size and size[0] * size[1] > MAX_PIXELS:
        die(f"{path} is {size[0]}x{size[1]}, more than the {MAX_PIXELS} pixels the scripts take: make it smaller first")
    if is_input:
        note_input(path)
    try:
        im = cv2.imdecode(data, flags)
    except cv2.error:
        return None
    if im is not None and im.shape[0] * im.shape[1] > MAX_PIXELS:     # (a format whose header is not read above)
        die(f"{path} is {im.shape[1]}x{im.shape[0]}, more than the {MAX_PIXELS} pixels the scripts take")
    return im


def _mode_for(path):
    """The mode a replaced file had, or what a new file gets under this process's umask."""
    if path.is_file():
        return stat.S_IMODE(os.stat(path).st_mode)
    mask = os.umask(0)
    os.umask(mask)
    return 0o666 & ~mask


def write_bytes(path, data):
    """A file written whole or not at all: beside its place first, then moved there, so a crash or a full disk leaves
    the earlier file as it was. It never replaces one of this run's inputs."""
    path = Path(path)
    refuse_input(path)
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".refinish-", suffix=".tmp", dir=path.parent)    # (private until it is whole)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if os.name != "nt":
            os.chmod(tmp, _mode_for(path))
        for attempt in range(6):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:                     # (a viewer or a virus scanner holding it for a moment)
                if attempt == 5:
                    raise
                time.sleep(0.1 * (attempt + 1))
    except OSError as e:
        die(f"cannot write {path}: {e.strerror or e}")
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def write_text(path, content):
    write_bytes(path, content.encode("utf-8"))


def _finite(v):
    if isinstance(v, float):
        return math.isfinite(v)
    if isinstance(v, dict):
        return all(_finite(x) for x in v.values())
    if isinstance(v, list):
        return all(_finite(x) for x in v)
    return True


def _no_constant(name):
    raise ValueError(f"{name} is not a number JSON allows")


def read_json(path):
    """A JSON file, or a message saying what is wrong with it. A byte order mark, which Notepad adds, is fine."""
    p = Path(path)
    if not p.is_file():
        die(f"no file at {path}")
    if p.stat().st_size > MAX_JSON_BYTES:
        die(f"{path} is larger than the {MAX_JSON_BYTES // 2 ** 20} MB a JSON file here may be")
    note_input(p)
    try:
        d = json.loads(p.read_bytes().decode("utf-8-sig"), parse_constant=_no_constant)
    except UnicodeDecodeError:
        die(f"{path} is not valid JSON: it is not UTF-8 text")
    except RecursionError:
        die(f"{path} is not valid JSON: it is nested too deeply")
    except ValueError as e:
        die(f"{path} is not valid JSON: {e}")
    try:
        ok = _finite(d)
    except RecursionError:
        die(f"{path} is not valid JSON: it is nested too deeply")
    if not ok:
        die(f"{path} is not valid JSON: it holds a number too large to use")
    return d


def write_image(path, img, params=()):
    """Write a picture, whole or not at all. A picture that cannot be written stops the script: it never reports a
    file that is not there."""
    import cv2
    path = Path(path)
    try:
        ok, buf = cv2.imencode(path.suffix, img, list(params))
    except cv2.error:
        ok = False
    if not ok:
        die(f"cannot write {path}")
    write_bytes(path, buf.tobytes())
