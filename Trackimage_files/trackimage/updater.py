"""Asking GitHub whether the branch carries a newer TrackImage, and putting it
in place.

Layer 20 of 27 -- see trackimage/__init__.py for the order these load in.

Nothing here reaches the network on its own. A check happens when the button is
pressed, or once at start if the user switched the automatic check on. The
install is deliberate in the same way: it downloads, verifies, backs the
database up, and only then hands the swap to a small helper that runs after this
process is gone -- because a program cannot reliably replace the files it is
running from, least of all on Windows.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import zipfile

from .config import APP_DIR, USERDATA_DIR, VERSION, DB_DIR, IGNORED_TAGS_FILE
from .logging_setup import log
from .appconfig import _app_config_load, _app_config_save


GITHUB_OWNER = "Moritz-arts"
GITHUB_REPO = "TrackImage"
#: Two channels, one repository.
#:
#: "stable" is a version somebody has looked at and declared finished. Every
#: version is published automatically as a pre-release, and GitHub's
#: releases/latest never returns one of those -- so declaring a stable version
#: is the single click that takes the pre-release mark off it, and this channel
#: follows wherever that mark sits.
#:
#: "latest" is the branch itself: whatever main holds this minute. Its version
#: is raised on every push, so the two channels use the same numbers and the
#: same comparison; they differ only in which commit they point at.
#:
#: Neither needs a file to have been uploaded anywhere. What gets installed is
#: the archive GitHub builds from the tag or the branch -- the repository's own
#: folders, which is exactly what TrackImage runs from.
CHANNEL_STABLE = "stable"
CHANNEL_LATEST = "latest"
CHANNELS = (CHANNEL_STABLE, CHANNEL_LATEST)
CHANNEL_DEFAULT = CHANNEL_STABLE
BRANCH = "main"
AUTO_CHECK_DEFAULT = False  # a check happens when the button is pressed

#: The version as it stands in the branch, read straight out of the one file
#: that defines it. One small request, and no dependence on anybody having
#: tagged anything.
RAW_VERSION = ("https://raw.githubusercontent.com/%s/%s/%s/"
               "Trackimage_files/trackimage/config.py")
#: The history, at the same point. An update that skips five versions should
#: say what all five brought, not only the last one.
RAW_CHANGELOG = "https://raw.githubusercontent.com/%s/%s/%s/docs/CHANGELOG.md"
#: What that branch last received -- the message and the date shown with the
#: offer. Best effort: the update does not depend on it.
API_COMMIT = "https://api.github.com/repos/%s/%s/commits/%s"
#: The newest release that is not marked as a pre-release.
API_LATEST = "https://api.github.com/repos/%s/%s/releases/latest"
RELEASES_PAGE = "https://github.com/%s/%s/releases"
#: The archives GitHub builds from a branch or a tag. Written in the
#: github.com/<owner>/<repo>/ form so they pass the same origin check an
#: uploaded release asset used to.
BRANCH_ZIP = "https://github.com/%s/%s/archive/refs/heads/%s.zip"
TAG_ZIP = "https://github.com/%s/%s/archive/refs/tags/%s.zip"
BRANCH_PAGE = "https://github.com/%s/%s/tree/%s"

_VERSION_RE = r'^VERSION\s*=\s*["\']([^"\']+)["\']'

#: Where the install lives. APP_DIR is Trackimage_files; ROOT_DIR holds it and
#: the launchers, and is what the swap actually rearranges.
ROOT_DIR = os.path.dirname(APP_DIR)
STAGE_DIR = os.path.join(ROOT_DIR, "_ti_update")

_NET_TIMEOUT = 20
_MAX_ZIP = 500 * 1024 * 1024      # a release is under a megabyte; this is a guard
_MAX_TEXT = 256 * 1024            # config.py is a few kilobytes
_UA = "TrackImage/%s (+https://github.com/%s/%s)" % (VERSION, GITHUB_OWNER, GITHUB_REPO)

#: Progress of an install, read by /api/update/status.
_state = {
    "phase": "idle",        # idle | downloading | verifying | backing-up | staging | ready | failed
    "pct": 0,
    "detail": "",
    "error": "",
    "target": "",
}
_lock = threading.Lock()


def is_configured():
    """True once a repository has been named. Nothing tries the network before."""
    return bool(GITHUB_OWNER and GITHUB_REPO)


def channel():
    c = str(_app_config_load().get("update_channel", CHANNEL_DEFAULT))
    return c if c in CHANNELS else CHANNEL_DEFAULT


def set_channel(name):
    name = str(name or "").strip().lower()
    if name not in CHANNELS:
        raise ValueError("Unknown channel %r" % name)
    cfg = _app_config_load()
    cfg["update_channel"] = name
    _app_config_save(cfg)
    return name


def auto_check_enabled():
    return bool(_app_config_load().get("auto_check_updates", AUTO_CHECK_DEFAULT))


def set_auto_check(on):
    cfg = _app_config_load()
    cfg["auto_check_updates"] = bool(on)
    _app_config_save(cfg)
    return bool(on)


def _set(phase, pct=None, detail=None, error=None):
    with _lock:
        _state["phase"] = phase
        if pct is not None:
            _state["pct"] = int(pct)
        if detail is not None:
            _state["detail"] = detail
        if error is not None:
            _state["error"] = error


def status():
    with _lock:
        return dict(_state)


def parse_version(text):
    """'v4.57' or '4.57.1' -> (4, 57, 1). Anything unparseable sorts lowest.

    Comparison is numeric per part, so 4.9 correctly loses to 4.57 -- the trap
    every string comparison falls into.
    """
    nums = re.findall(r"\d+", str(text or ""))
    if not nums:
        return (0,)
    return tuple(int(n) for n in nums[:4])


def _newer(latest, current):
    a, b = parse_version(latest), parse_version(current)
    n = max(len(a), len(b))
    a = a + (0,) * (n - len(a))
    b = b + (0,) * (n - len(b))
    return a > b


def _get_json(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": _UA,
    })
    with urllib.request.urlopen(req, timeout=_NET_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _get_text(url):
    req = urllib.request.Request(url, headers={
        "Accept": "text/plain",
        "User-Agent": _UA,
    })
    with urllib.request.urlopen(req, timeout=_NET_TIMEOUT) as r:
        return r.read(_MAX_TEXT).decode("utf-8", "replace")


#: "## v4.62 — 2026-09-12", the heading changelog_entry.py writes.
_HEADING_RE = re.compile(r"^##\s+v?([\d][\d.]*)\s*(?:[—\-–]\s*(\S+))?\s*$", re.M)

#: Marks the workflow leaves in its own commit message. They are instructions to
#: the machinery, not a description of anything, and have no business being read
#: as "what is new in this version".
_NOISE_RE = re.compile(r"^\s*(\[skip ci\]|\[skip version\])\s*$", re.M | re.I)


def _clean_notes(text):
    text = _NOISE_RE.sub("", text or "")
    # The bump commit's subject ends in the version it produced; the dialog
    # already says which version this is.
    text = re.sub(r"\s*\(v[\d.]+\)\s*$", "", text.strip(), flags=re.M)
    return "\n".join(ln for ln in text.splitlines() if ln.strip()).strip()


def changelog_between(ref, after, upto):
    """Every changelog entry newer than `after`, up to and including `upto`.

    An update that skips five versions should say what all five brought. The
    list is read from the archive's own history file at the same ref that is
    about to be installed, so it describes exactly what is being offered.

    Returns a list of {version, date, lines}; empty when the file cannot be
    read, which is never a reason to stop an update.
    """
    try:
        text = _get_text(RAW_CHANGELOG % (GITHUB_OWNER, GITHUB_REPO,
                                          urllib.parse.quote(ref, safe="")))
    except Exception:
        return []
    out = []
    marks = list(_HEADING_RE.finditer(text))
    for i, m in enumerate(marks):
        ver = m.group(1)
        if not _newer(ver, after):
            break            # headings run newest first; everything below is older
        if upto and _newer(ver, upto):
            continue         # published after the version being offered
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        # Entries written before the one-line rule wrap across several lines, so
        # a bullet runs until the next one begins. Taking only the lines that
        # start with a dash would cut every one of those off mid-sentence.
        lines = []
        for ln in text[m.end():end].splitlines():
            stripped = ln.strip()
            if not stripped:
                continue
            if stripped[0] in "-*•":
                lines.append(stripped[1:].strip())
            elif lines:
                lines[-1] += " " + stripped
        out.append({"version": ver, "date": m.group(2) or "",
                    "lines": lines[:40]})
        if len(out) >= 25:
            break
    return out


def _branch_version():
    """The version the branch carries, read out of its config.py."""
    src = _get_text(RAW_VERSION % (GITHUB_OWNER, GITHUB_REPO,
                                   urllib.parse.quote(BRANCH, safe="")))
    m = re.search(_VERSION_RE, src, re.M)
    if not m:
        raise RuntimeError("%s has no readable version." % BRANCH)
    return m.group(1)


def _check_latest():
    """What main holds this minute."""
    latest = _branch_version()
    # What the branch last received. Nice to read before installing, and never
    # a reason to fail: the version above is what the decision rests on.
    sha = date = notes = ""
    page = BRANCH_PAGE % (GITHUB_OWNER, GITHUB_REPO, BRANCH)
    try:
        head = _get_json(API_COMMIT % (GITHUB_OWNER, GITHUB_REPO,
                                       urllib.parse.quote(BRANCH, safe="")))
        sha = (head.get("sha") or "")[:7]
        commit = head.get("commit") or {}
        notes = _clean_notes(commit.get("message") or "")[:8000]
        date = ((commit.get("committer") or {}).get("date") or "")[:10]
        page = head.get("html_url") or page
    except Exception:
        pass
    return {
        "latest": latest,
        "tag": "",
        "sha": sha,
        "name": "%s · v%s" % (BRANCH, latest),
        "notes": notes,
        "page": page,
        "published": date,
        "asset_name": "%s-%s.zip" % (GITHUB_REPO, BRANCH),
        "asset_url": BRANCH_ZIP % (GITHUB_OWNER, GITHUB_REPO,
                                   urllib.parse.quote(BRANCH, safe="")),
    }


def _check_stable():
    """The newest version somebody has taken the pre-release mark off."""
    data = _get_json(API_LATEST % (GITHUB_OWNER, GITHUB_REPO))
    tag = data.get("tag_name") or ""
    if not tag:
        raise RuntimeError("The newest release carries no tag.")
    return {
        "latest": tag.lstrip("vV"),
        "tag": tag,
        "sha": "",
        "name": data.get("name") or tag,
        "notes": _clean_notes(data.get("body") or "")[:8000],
        "page": data.get("html_url") or (RELEASES_PAGE % (GITHUB_OWNER, GITHUB_REPO)),
        "published": (data.get("published_at") or "")[:10],
        "asset_name": "%s-%s.zip" % (GITHUB_REPO, tag),
        "asset_url": TAG_ZIP % (GITHUB_OWNER, GITHUB_REPO,
                                urllib.parse.quote(tag, safe="")),
    }


def check_for_update():
    """What the chosen channel currently offers. Never raises -- returns a dict."""
    if not is_configured():
        return {"ok": False, "error": "The updater has no repository configured."}
    ch = channel()
    try:
        found = _check_stable() if ch == CHANNEL_STABLE else _check_latest()
    except Exception as e:
        msg = str(e)
        base = {"ok": False, "current": VERSION, "channel": ch}
        if "404" in msg:
            if ch == CHANNEL_STABLE:
                # Every version is published as a pre-release, and until one is
                # marked as the latest release there is no stable version to
                # offer. Saying so is more use than "not found".
                base["error"] = ("No version has been declared stable yet. "
                                 "Switch to Latest to follow the %s branch."
                                 % BRANCH)
            else:
                base["error"] = ("Branch %s is not there, or holds no "
                                 "TrackImage." % BRANCH)
            return base
        if "403" in msg:
            base["error"] = "GitHub is rate limiting this address. Try again later."
            return base
        base["error"] = "Could not reach GitHub: %s" % msg
        return base

    newer = _newer(found["latest"], VERSION)
    out = dict(found)
    out.update({
        "ok": True,
        "current": VERSION,
        "channel": ch,
        "branch": BRANCH,
        "newer": newer,
        # What every version in between brought, not only the newest one.
        "changes": changelog_between(found.get("tag") or BRANCH, VERSION,
                                     found["latest"]) if newer else [],
        # GitHub packs these archives on the fly, so their size is not known
        # until the download is running.
        "asset_size": 0,
        "asset_source": True,
    })
    return out


def _download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": _UA,
                                               "Accept": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=_NET_TIMEOUT) as r:
        total = int(r.headers.get("Content-Length") or 0)
        if total > _MAX_ZIP:
            raise RuntimeError("The download is larger than expected (%d MB)."
                               % (total // (1024 * 1024)))
        got = 0
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(64 * 1024)
                if not chunk:
                    break
                got += len(chunk)
                if got > _MAX_ZIP:
                    raise RuntimeError("The download is larger than expected.")
                f.write(chunk)
                if total:
                    _set("downloading", 5 + int(got * 55 / total),
                         "%.1f of %.1f MB" % (got / 1048576.0, total / 1048576.0))
                else:
                    # An archive GitHub packs from a branch arrives chunked, with no
                    # length announced: there is nothing to be a percentage of,
                    # so the bar creeps and the megabytes carry the truth.
                    _set("downloading", min(58, 5 + int(got / 1048576.0 * 4)),
                         "%.1f MB" % (got / 1048576.0))
    return got


def _find_prefix(zf):
    """Where Trackimage_files sits inside the archive.

    An archive GitHub builds from a branch carries a wrapper directory
    (TrackImage-main/Trackimage_files/...); one zipped by hand from inside the
    folder does not. Both are accepted by looking for the one file that must
    exist either way.
    """
    marker = "Trackimage_files/trackimage/config.py"
    for name in zf.namelist():
        n = name.replace("\\", "/")
        if n.endswith(marker):
            return n[:len(n) - len(marker)]
    return None


def _verify(zip_path, expect_version=None):
    """The archive really is TrackImage, and really is newer.

    Guards against a half-finished download, against an archive that is
    something else entirely, and against path traversal inside it.

    A branch moves, so what was announced a minute ago and what arrived can
    differ by a push. That is not an error -- being newer than what is
    installed is the condition that matters; the announced version is only
    worth a line in the log.
    """
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError("The archive is damaged (%s)." % bad)
        for n in zf.namelist():
            p = n.replace("\\", "/")
            if p.startswith("/") or ".." in p.split("/"):
                raise RuntimeError("The archive contains an unsafe path: %s" % n)
        prefix = _find_prefix(zf)
        if prefix is None:
            raise RuntimeError("This ZIP is not a TrackImage release -- "
                               "Trackimage_files/trackimage/config.py is missing.")
        src = zf.read(prefix + "Trackimage_files/trackimage/config.py").decode("utf-8", "replace")
        m = re.search(_VERSION_RE, src, re.M)
        if not m:
            raise RuntimeError("The archive has no readable version.")
        found = m.group(1)
        if expect_version and parse_version(found) != parse_version(expect_version):
            log("Update: %s said v%s, the archive carries v%s -- taking the "
                "archive." % (BRANCH, expect_version, found))
        if not _newer(found, VERSION):
            raise RuntimeError("The archive carries v%s, which is not newer than "
                               "the installed v%s." % (found, VERSION))
        return found, prefix


def backup_userdata():
    """A copy of the database and the ignore list, beside the install.

    Logs and thumbnails are left out on purpose: logs are noise and thumbnails
    are rebuilt from the pictures. What cannot be recreated is the database.
    """
    name = "Userdata-backup-v%s.zip" % VERSION
    dest = os.path.join(ROOT_DIR, name)
    tmp = dest + ".part"
    try:
        os.remove(tmp)
    except Exception:
        pass
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for root, _dirs, files in os.walk(DB_DIR):
            for fn in files:
                full = os.path.join(root, fn)
                z.write(full, os.path.join("Databank", os.path.relpath(full, DB_DIR)))
        if os.path.isfile(IGNORED_TAGS_FILE):
            z.write(IGNORED_TAGS_FILE, "ignored_tags.txt")
    os.replace(tmp, dest)
    return dest, os.path.getsize(dest)


_BAT = r"""@echo off
setlocal
set "ROOT=%(root)s"
set "STAGE=%(stage)s"
set "PID=%(pid)s"
set "SRC=%(src)s"

:wait
tasklist /FI "PID eq %%PID%%" 2>nul | find "%%PID%%" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait
)
timeout /t 2 /nobreak >nul

if exist "%%ROOT%%\Trackimage_files.bak" rmdir /s /q "%%ROOT%%\Trackimage_files.bak"
move "%%ROOT%%\Trackimage_files" "%%ROOT%%\Trackimage_files.bak" >nul
if errorlevel 1 goto giveup

move "%%SRC%%\Trackimage_files" "%%ROOT%%\Trackimage_files" >nul
if errorlevel 1 goto rollback

move "%%ROOT%%\Trackimage_files.bak\Userdata" "%%ROOT%%\Trackimage_files\Userdata" >nul
if errorlevel 1 goto rollback
if exist "%%ROOT%%\Trackimage_files.bak\models" (
  move "%%ROOT%%\Trackimage_files.bak\models" "%%ROOT%%\Trackimage_files\models" >nul
)

copy /y "%%SRC%%\start-*.*" "%%ROOT%%\" >nul 2>nul
if exist "%%SRC%%\README.md" copy /y "%%SRC%%\README.md" "%%ROOT%%\" >nul 2>nul
rem docs is replaced whole, never merged: a file dropped from the new version
rem must not survive in the folder as a leftover of the old one.
if exist "%%SRC%%\docs" (
  if exist "%%ROOT%%\docs" rmdir /s /q "%%ROOT%%\docs"
  move "%%SRC%%\docs" "%%ROOT%%\docs" >nul
)
rem Files earlier versions put here and this one no longer ships.
if exist "%%ROOT%%\README.txt" del /q "%%ROOT%%\README.txt" >nul 2>nul

rmdir /s /q "%%ROOT%%\Trackimage_files.bak"
rmdir /s /q "%%STAGE%%"
start "" "%%ROOT%%\start-windows.bat"
exit /b 0

:rollback
if exist "%%ROOT%%\Trackimage_files" rmdir /s /q "%%ROOT%%\Trackimage_files"
move "%%ROOT%%\Trackimage_files.bak" "%%ROOT%%\Trackimage_files" >nul
:giveup
echo.
echo   The update could not be installed. The previous version was put back.
echo   Nothing in Userdata was touched.
echo.
pause
start "" "%%ROOT%%\start-windows.bat"
exit /b 1
"""

_SH = r"""#!/bin/sh
ROOT='%(root)s'
STAGE='%(stage)s'
SRC='%(src)s'
PID=%(pid)s

while kill -0 "$PID" 2>/dev/null; do sleep 1; done
sleep 2

rm -rf "$ROOT/Trackimage_files.bak"
mv "$ROOT/Trackimage_files" "$ROOT/Trackimage_files.bak" || exit 1

if ! mv "$SRC/Trackimage_files" "$ROOT/Trackimage_files"; then
  rm -rf "$ROOT/Trackimage_files"
  mv "$ROOT/Trackimage_files.bak" "$ROOT/Trackimage_files"
  echo "The update could not be installed. The previous version was put back."
  exit 1
fi

if ! mv "$ROOT/Trackimage_files.bak/Userdata" "$ROOT/Trackimage_files/Userdata"; then
  rm -rf "$ROOT/Trackimage_files"
  mv "$ROOT/Trackimage_files.bak" "$ROOT/Trackimage_files"
  echo "The update could not be installed. The previous version was put back."
  exit 1
fi
[ -d "$ROOT/Trackimage_files.bak/models" ] && \
  mv "$ROOT/Trackimage_files.bak/models" "$ROOT/Trackimage_files/models"

cp -f "$SRC"/start-* "$ROOT/" 2>/dev/null
[ -f "$SRC/README.md" ] && cp -f "$SRC/README.md" "$ROOT/"
# docs is replaced whole, never merged: a file dropped from the new version
# must not survive in the folder as a leftover of the old one.
if [ -d "$SRC/docs" ]; then
  rm -rf "$ROOT/docs"
  mv "$SRC/docs" "$ROOT/docs"
fi
# Files earlier versions put here and this one no longer ships.
rm -f "$ROOT/README.txt"
chmod +x "$ROOT"/start-linux.sh "$ROOT"/start-macos.command 2>/dev/null

rm -rf "$ROOT/Trackimage_files.bak" "$STAGE"

if [ -x "$ROOT/start-macos.command" ] && [ "$(uname)" = "Darwin" ]; then
  open "$ROOT/start-macos.command"
else
  "$ROOT/start-linux.sh" &
fi
exit 0
"""


def _write_helper(src_dir):
    """The script that does the swap once this process is gone."""
    subs = {"root": ROOT_DIR, "stage": STAGE_DIR, "src": src_dir, "pid": os.getpid()}
    if os.name == "nt":
        path = os.path.join(STAGE_DIR, "apply.bat")
        text, enc = _BAT % subs, "utf-8"
    else:
        path = os.path.join(STAGE_DIR, "apply.sh")
        text, enc = _SH % subs, "utf-8"
    with open(path, "w", encoding=enc, newline="\r\n" if os.name == "nt" else "\n") as f:
        f.write(text)
    if os.name != "nt":
        os.chmod(path, 0o755)
    return path


def _run(info):
    try:
        _set("downloading", 5, "contacting GitHub", error="")
        os.makedirs(STAGE_DIR, exist_ok=True)
        zip_path = os.path.join(STAGE_DIR, "update.zip")
        _download(info["asset_url"], zip_path)

        _set("verifying", 62, "checking the archive")
        found, prefix = _verify(zip_path, info.get("latest"))

        _set("backing-up", 68, "copying the database")
        try:
            bpath, bsize = backup_userdata()
            log("Update: database backed up to %s (%.1f MB)"
                % (os.path.basename(bpath), bsize / 1048576.0))
        except Exception as e:
            raise RuntimeError("The database could not be backed up, so the update "
                               "was stopped: %s" % e)

        _set("staging", 80, "unpacking")
        src_dir = os.path.join(STAGE_DIR, "new")
        shutil.rmtree(src_dir, ignore_errors=True)
        os.makedirs(src_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            for n in zf.namelist():
                p = n.replace("\\", "/")
                if prefix and not p.startswith(prefix):
                    continue
                rel = p[len(prefix):] if prefix else p
                if not rel or rel.endswith("/"):
                    continue
                # Userdata and models belong to this machine and are carried
                # over by the helper, never taken from the archive.
                head = rel.split("/")
                if len(head) > 1 and head[0] == "Trackimage_files" and \
                        len(head) > 2 and head[1] in ("Userdata", "models"):
                    continue
                target = os.path.join(src_dir, *rel.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(n) as s, open(target, "wb") as d:
                    shutil.copyfileobj(s, d)
        if not os.path.isdir(os.path.join(src_dir, "Trackimage_files")):
            raise RuntimeError("Unpacking produced no Trackimage_files folder.")

        helper = _write_helper(src_dir)
        _set("ready", 100, "restarting into %s" % found)
        log("Update to v%s staged. Restarting." % found)

        if os.name == "nt":
            DETACHED = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_PROCESS_GROUP
            subprocess.Popen(["cmd", "/c", helper], cwd=ROOT_DIR,
                             creationflags=DETACHED, close_fds=True)
        else:
            subprocess.Popen(["/bin/sh", helper], cwd=ROOT_DIR,
                             start_new_session=True, close_fds=True)

        def _bye():
            time.sleep(2.0)
            os._exit(0)
        threading.Thread(target=_bye, daemon=True).start()
    except Exception as e:
        _set("failed", 0, "", error=str(e))
        log("Update failed: %s" % e, "error")
        shutil.rmtree(STAGE_DIR, ignore_errors=True)


def start_install(info):
    """Kick the install off in the background. Returns False if one is running."""
    with _lock:
        if _state["phase"] not in ("idle", "failed"):
            return False
        _state.update({"phase": "downloading", "pct": 1, "detail": "",
                       "error": "", "target": info.get("latest") or ""})
    threading.Thread(target=_run, args=(info,), daemon=True).start()
    return True
