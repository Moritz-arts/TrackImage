#!/usr/bin/env python3
"""Write the new version's entry into CHANGELOG.md, from the commits behind it.

"What happened between v4.59 and v4.73" is a question the repository can always
answer -- the commits are right there -- but only if somebody writes it down
while it is still one version's worth of work. So it is written here, by the
same workflow that raises the number: every commit since the previous tag
becomes a line under the new heading, and that heading is what the release
notes on GitHub say too.

Called as: changelog_entry.py <new-version>
Prints the entry body on stdout, so the workflow can hand it to `gh release`.
"""
import os
import pathlib
import re
import subprocess
import sys
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"

#: The workflow's own commits. They say nothing a reader wants and would
#: otherwise open every entry with the number the entry is already titled with.
_BUMP = re.compile(r"^v[\d.]+(\s*\[skip ci\])?$")

#: Key: value lines git puts at the foot of a message.
_TRAILER = re.compile(r"^[A-Za-z][A-Za-z-]*:\s")


def _git(*args):
    return subprocess.run(("git",) + args, cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout.strip()


def previous_tag():
    """The last version tag before HEAD, or nothing on the very first run."""
    try:
        return _git("describe", "--tags", "--abbrev=0", "HEAD")
    except subprocess.CalledProcessError:
        return ""


def commits_since(tag):
    """Subject and body of every real commit since that tag, newest first."""
    span = ("%s..HEAD" % tag) if tag else "HEAD"
    # NUL between commits, \x01 between subject and body: a commit message can
    # contain any amount of blank lines, so nothing printable can separate them.
    # Written as %x00/%x01 -- git turns those into the bytes, which is the only
    # way to ask for a NUL that argv itself is not allowed to carry.
    raw = _git("log", span, "--no-merges", "--reverse", "--pretty=format:%s%x01%b%x00")
    out = []
    for chunk in raw.split("\x00"):
        chunk = chunk.strip()
        if not chunk:
            continue
        subject, _, body = chunk.partition("\x01")
        subject = subject.strip()
        if not subject or _BUMP.match(subject):
            continue
        out.append((subject, body.strip()))
    return out


def entry_body(tag):
    lines = []
    for subject, body in commits_since(tag):
        lines.append("- %s" % subject)
        for para in [p.strip() for p in body.split("\n\n") if p.strip()]:
            # A block of trailers -- Co-Authored-By, Claude-Session, Signed-off-by
            # -- says who committed it, not what changed. They arrive together at
            # the end, so a paragraph made of nothing else is dropped whole.
            if all(_TRAILER.match(ln) for ln in para.splitlines() if ln.strip()):
                continue
            lines.append("")
            for ln in para.splitlines():
                lines.append("  %s" % ln.strip())
        lines.append("")
    if not lines:
        lines = ["- Maintenance."]
    return "\n".join(lines).strip()


def prepend(version, body):
    """Put the entry directly under the file's heading, newest first."""
    heading = "## v%s — %s" % (version, date.today().isoformat())
    text = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.is_file() else \
        "# TrackImage — version history\n"
    if ("## v%s " % version) in text or text.rstrip().endswith("## v%s" % version):
        return False                      # already written; nothing to do
    marker = "\n## "
    at = text.find(marker)
    if at < 0:
        new = text.rstrip() + "\n\n" + heading + "\n\n" + body + "\n"
    else:
        new = text[:at + 1] + heading + "\n\n" + body + "\n\n" + text[at + 1:]
    CHANGELOG.write_text(new, encoding="utf-8")
    return True


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: changelog_entry.py <new-version>")
    version = sys.argv[1].lstrip("vV")
    body = entry_body(previous_tag())
    prepend(version, body)
    print(body)
    # Handed to `gh release` as a file rather than as a shell argument: this
    # text is whatever was written in a commit message, and a commit message is
    # allowed to contain quotes, backticks and $(...).
    notes_file = os.environ.get("TI_NOTES_FILE")
    if notes_file:
        pathlib.Path(notes_file).write_text(body + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
