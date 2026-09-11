"""Two checks the launcher needs, written in Python instead of shell.

v4.36. Both of these used to be one-liners squeezed into a .bat and a .sh, and
both were wrong in the same way: they answered a slightly different question than
the one that mattered.

  bootstrap  Can pip install anything at all? A virtual environment made by
         Python 3.12 holds pip and nothing else -- no setuptools, no wheel -- and
         a package that ships only a source archive then falls back to pip's old
         setup.py route, which needs exactly the setuptools that is missing. An
         older pip does not survive that on 3.12 at all: it stops on an internal
         error. So pip is repaired from Python's own bundled copy first, which
         does not go through pip, and only then asked to update itself.

  deps   Does this environment actually have what TrackImage needs to run?
         The launcher used to note a failed install in a single line that
         scrolled past and start anyway, so a missing package turned into a
         window that never appeared and no explanation anywhere.

  wait   Is the program that just started listening -- or is something else?
         The old check asked only whether anything at all held port 5001. A
         leftover process from an earlier attempt answers that question with
         yes, so the launcher reported success and closed without a word while
         nothing the user could see had happened.

Run as:  python launcher_check.py bootstrap
         python launcher_check.py deps
         python launcher_check.py wait [seconds]

Exit codes for `wait`:  0 this build is up · 2 someone else holds the port
                        1 nothing came up in time
"""

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 5001

# Without these TrackImage cannot open its library at all, so a start would only
# produce a crash the user never gets to see.
REQUIRED = [
    ("flask", "flask", "the local web server TrackImage runs on"),
    ("PIL", "pillow", "reading and resizing images"),
    ("numpy", "numpy", "the maths behind duplicate detection"),
    ("send2trash", "send2trash", "deleting to the Recycle Bin instead of for good"),
]

# These shape what TrackImage can do, but it starts and works without any of
# them -- so they are reported, never fatal.
OPTIONAL = [
    ("webview", "pywebview", "its own window instead of a browser tab"),
    ("watchdog", "watchdog", "noticing when files change on disk"),
    ("pillow_heif", "pillow-heif", "iPhone HEIC photos"),
    ("imageio_ffmpeg", "imageio-ffmpeg", "thumbnails for video files"),
    ("qrcode", "qrcode", "the scan-me code for opening TrackImage on a phone"),
    ("win32com", "pywin32", "dragging files out of the window into other programs"),
]


def _have(module):
    import importlib.util
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


def version_of_this_build():
    """Read VERSION out of app.py as text.

    Importing app.py would start the program, which is the opposite of what a
    pre-flight check should do.
    """
    # v4.49: VERSION moved with everything else into the trackimage package.
    # app.py is only the way in now. The old spot is still read as a fallback
    # so this keeps working beside an older build.
    for where in (os.path.join(HERE, "trackimage", "config.py"),
                  os.path.join(HERE, "app.py")):
        try:
            with open(where, "r", encoding="utf-8", errors="replace") as fh:
                head = fh.read(200000)
            m = re.search(r'^VERSION\s*=\s*"([^"]+)"', head, re.M)
            if m:
                return m.group(1)
        except Exception:
            continue
    return ""


MIN_PIP = (23, 1)      # below this, pip still uses the setup.py route by default


def _pip_version():
    try:
        import pip
        return tuple(int(x) for x in re.findall(r"\d+", pip.__version__)[:2])
    except Exception:
        return (0, 0)


def _toolchain_ok():
    return (_pip_version() >= MIN_PIP
            and _have("setuptools") and _have("wheel"))


def _run(args, timeout=900):
    env = dict(os.environ)
    env["PYTHONNOUSERSITE"] = "1"
    kw = {"capture_output": True, "text": True, "timeout": timeout, "env": env}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        r = subprocess.run([sys.executable] + args, **kw)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 1, str(e)


def cmd_bootstrap():
    """Put pip in a state where it can install things, and say so plainly."""
    if _toolchain_ok():
        print("       pip, setuptools and wheel are ready")
        return 0

    have = _pip_version()
    print("       preparing the installer - pip %s, setuptools and wheel ..."
          % (".".join(str(x) for x in have) if have != (0, 0) else "?"))

    # ensurepip unpacks the pip that came with this Python. It is the only route
    # that does not run through the pip being replaced, which matters when that
    # pip is the thing that is broken.
    if have < MIN_PIP:
        rc, out = _run(["-m", "ensurepip", "--upgrade"], timeout=600)
        if rc != 0:
            print("       note: ensurepip is not available here - trying pip directly")

    rc, out = _run(["-m", "pip", "install", "--upgrade", "--disable-pip-version-check",
                    "-q", "pip", "setuptools", "wheel"])
    if rc != 0:
        print("       [!] could not update the installer:")
        for line in [l for l in out.splitlines() if l.strip()][-4:]:
            print("           " + line[:110])
        print("       Carrying on - most packages install without it.")
        return 0            # never fatal: the dependency check has the last word

    print("       installer ready")
    return 0


def cmd_deps():
    missing_req = [(p, why) for mod, p, why in REQUIRED if not _have(mod)]
    missing_opt = [(p, why) for mod, p, why in OPTIONAL if not _have(mod)]

    if missing_opt:
        print("  Not installed, and TrackImage runs without them:")
        for p, why in missing_opt:
            print("      %-16s %s" % (p, why))
        if any(p == "pywebview" for p, _ in missing_opt):
            print("      -> without pywebview TrackImage opens in a browser tab instead.")
        print("")

    if not missing_req:
        print("  Everything TrackImage needs is installed.")
        return 0

    print("  MISSING - TrackImage cannot start without these:")
    for p, why in missing_req:
        print("      %-16s %s" % (p, why))
    print("")
    print("  Install them by hand with:")
    print("")
    print("      %s -m pip install %s" % (os.path.basename(sys.executable),
                                          " ".join(p for p, _ in missing_req)))
    print("")
    print("  If that fails too, the usual cause is an outdated pip in this")
    print("  environment. This brings it up to date first:")
    print("")
    print("      %s -m pip install --upgrade pip setuptools wheel"
          % os.path.basename(sys.executable))
    return 1


def _ping():
    """Ask whoever is on the port who they are. None means no answer."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/api/net/ping" % PORT, timeout=2) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        # A running TrackImage that wants a PIN first still counts as running.
        return {"version": "", "locked": True, "status": e.code}
    except Exception:
        return None


def _port_taken():
    s = socket.socket()
    s.settimeout(0.4)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        try:
            s.close()
        except Exception:
            pass


def cmd_wait(seconds=30.0):
    mine = version_of_this_build()
    deadline = time.time() + seconds
    saw_port = False
    while time.time() < deadline:
        if _port_taken():
            saw_port = True
            info = _ping()
            if info is not None:
                other = info.get("version", "")
                if not other or other == mine or info.get("locked"):
                    return 0
                print("")
                print("  Port %d is already answering, but it is TrackImage v%s," % (PORT, other))
                print("  not the v%s in this folder. An older copy is still running." % mine)
                return 2
        time.sleep(0.25)

    if saw_port:
        print("")
        print("  Something is holding port %d but it is not answering as TrackImage." % PORT)
        return 2
    return 1


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "deps"
    if what == "bootstrap":
        raise SystemExit(cmd_bootstrap())
    if what == "deps":
        raise SystemExit(cmd_deps())
    if what == "wait":
        try:
            secs = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
        except ValueError:
            secs = 30.0
        raise SystemExit(cmd_wait(secs))
    print("usage: launcher_check.py [bootstrap|deps|wait]")
    raise SystemExit(64)
