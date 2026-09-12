#!/usr/bin/env python3
"""Raise TrackImage's version by one, everywhere it is written down.

The updater decides whether to offer an update by comparing the version in the
branch with the version that is installed. That only works if the number moves
whenever the code does -- and remembering to move it by hand is exactly the
kind of thing that gets forgotten, which is how a release ended up announcing
itself as newer while carrying the older number inside.

So the number is raised here instead, by the workflow that runs on every push
to the branch. VERSION in config.py is the one that matters; the rest are the
places the same number is printed to a human, and they are kept in step so the
window title, the launcher banner and the README never disagree with it.

Prints the new version, and writes it to $GITHUB_OUTPUT as `version` when the
workflow is the caller.
"""
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = ROOT / "Trackimage_files" / "trackimage" / "config.py"

#: Every place the version is spelled out. Group `pre` is kept, group `v` is
#: replaced, and whatever follows is matched by a lookahead so the rewrite can
#: never reach past the number itself -- a trailing \s* would happily swallow
#: the blank lines after it.
#:
#: Each file is rewritten once: the first match is the definition or the
#: heading, and every later mention is history that must keep the version it
#: describes.
PLACES = [
    (CONFIG,
     r'^(?P<pre>VERSION\s*=\s*")(?P<v>[^"]+)(?=")'),
    # The repository's front page. Whoever opens it should be able to see which
    # version main is without reading a commit log.
    (ROOT / "README.md",
     r'^(?P<pre>\*\*Version )(?P<v>[\d.]+)(?=\*\*)'),
    (ROOT / "Trackimage_files" / "app.py",
     r'^(?P<pre>TrackImage v)(?P<v>[\d.]+)(?=[ \t]*\r?$)'),
    (ROOT / "start-linux.sh",
     r'(?P<pre>TrackImage v)(?P<v>[\d.]+)(?= - Setup)'),
    (ROOT / "start-macos.command",
     r'(?P<pre>TrackImage v)(?P<v>[\d.]+)(?= - Setup)'),
    (ROOT / "start-windows.bat",
     r'(?P<pre>TrackImage v)(?P<v>[\d.]+)(?= - Setup)'),
]


def _read(path):
    """Text with its line endings left exactly as they are on disk.

    start-windows.bat is CRLF and has to stay CRLF: a batch file whose labels
    end in a bare newline is a batch file that stops working on some Windows
    versions, and nothing here is worth that risk.
    """
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def current_version():
    m = re.search(r'^VERSION\s*=\s*"([^"]+)"', _read(CONFIG), re.M)
    if not m:
        sys.exit("config.py has no VERSION line to raise.")
    return m.group(1)


def raised(v):
    """4.58 -> 4.59. The last part counts up; nothing else is touched.

    Past .99 it simply carries on (4.100), which sorts correctly because the
    updater compares the parts as numbers rather than as text.
    """
    parts = v.split(".")
    if not parts[-1].isdigit():
        sys.exit("Version %r does not end in a number, so it cannot be raised "
                 "automatically." % v)
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)


def main():
    old = current_version()
    new = raised(old)
    for path, pattern in PLACES:
        if not path.is_file():
            print("skipped (missing): %s" % path.name)
            continue
        text = _read(path)
        out, n = re.subn(pattern, lambda m: m.group("pre") + new,
                         text, count=1, flags=re.M)
        if not n:
            print("skipped (no version line): %s" % path.name)
            continue
        _write(path, out)
        print("%s: %s -> %s" % (path.relative_to(ROOT), old, new))
    print(new)
    out_file = os.environ.get("GITHUB_OUTPUT")
    if out_file:
        with open(out_file, "a", encoding="utf-8") as f:
            f.write("version=%s\n" % new)
            f.write("previous=%s\n" % old)


if __name__ == "__main__":
    main()
