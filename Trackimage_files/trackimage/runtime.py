"""The virtual environment, dependency installs and the model download.

Layer 17 of 27 -- see trackimage/__init__.py for the order these load in.
"""
import glob
import json
import os
import re
import subprocess
import sys
import threading
import time as _time
from . import state
from .config import LOG_DIR, REQUIRED_ASSETS, TAGGER_DIR, VERSION, _BENCH_KEY, _RT_ABSENT, _RT_BROKEN, _RT_EXPECTED, _RT_OK, _RT_SWAPPING, _RT_UNITS, _TAG_MODEL_FILES
from .logging_setup import log
from .platform_bits import _no_window
from .db import _db_commit_retry, _db_write_lock, _get_thread_db
from .tagger import _tag_ensure_running, _tag_notify, _tag_runtime_available, _tag_runtime_set


_model_dl = {"active": False, "file": "", "done": 0, "total": 0, "error": "", "phase": "",
             "step": "", "all_done": 0, "all_total": 0}


def _model_dl_missing():
    return [f for f in _TAG_MODEL_FILES if not os.path.exists(os.path.join(TAGGER_DIR, f))]


_gpu_vendor_cache = {"v": None}


def detect_gpu_vendor():
    """v4.20: which graphics card is in the machine -- "nvidia", "amd", "intel"
    or "" when it cannot be told.

    Asked before anything is installed, so an AMD owner stops downloading 2.5 GB
    of NVIDIA libraries that will never run. No new dependency: Windows is asked
    through its own CIM interface, Linux through the vendor id every card exposes
    in /sys."""
    if _gpu_vendor_cache["v"] is not None:
        return _gpu_vendor_cache["v"]
    v = ""
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_VideoController).Name"],
                capture_output=True, text=True, timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.lower()
            # A laptop often reports two cards; the discrete one decides.
            if "nvidia" in out or "geforce" in out or "quadro" in out or "rtx" in out:
                v = "nvidia"
            elif "amd" in out or "radeon" in out:
                v = "amd"
            elif "intel" in out or "arc" in out:
                v = "intel"
        elif sys.platform.startswith("linux"):
            ids = set()
            for f in glob.glob("/sys/class/drm/card*/device/vendor"):
                try:
                    ids.add(open(f).read().strip().lower())
                except OSError:
                    pass
            if "0x10de" in ids:
                v = "nvidia"
            elif "0x1002" in ids:
                v = "amd"
            elif "0x8086" in ids:
                v = "intel"
    except Exception:
        v = ""
    _gpu_vendor_cache["v"] = v
    return v


_PENDING_RT = "pending_runtime_install"


def _pending_runtime_get():
    try:
        db = _get_thread_db()
        r = db.execute("SELECT value FROM config WHERE key=?", (_PENDING_RT,)).fetchone()
        db.close()
        return str(r["value"]) if r and r["value"] else ""
    except Exception:
        return ""


def _pending_runtime_set(kind):
    try:
        db = _get_thread_db()
        with _db_write_lock:
            if kind:
                db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?,?)",
                           (_PENDING_RT, kind))
            else:
                db.execute("DELETE FROM config WHERE key=?", (_PENDING_RT,))
            _db_commit_retry(db)
        db.close()
    except Exception:
        pass


def _runtime_locked_in_process():
    """v4.28: True when onnxruntime's native libraries are mapped into THIS
    process. Python cannot unload a DLL: closing the session, dropping the
    tagger and stopping every worker all leave the libraries exactly where they
    are. pip then rewrites those files while they are still mapped, and the next
    instruction the tagging thread executes is in a library that no longer
    matches the one next to it -- an access violation, not an exception.

    This is why installing CUDA on a fresh venv works perfectly and switching to
    DirectML afterwards does not: the first has nothing loaded, the second is
    pulling the floor out from under a running session."""
    return "onnxruntime" in sys.modules


def _run_pending_runtime_install():
    """v4.28: perform a deferred runtime swap at startup, before anything has
    imported onnxruntime. Nothing is mapped this early, so pip can replace every
    file cleanly -- which is the only point at which the swap is actually safe."""
    kind = _pending_runtime_get()
    if not kind:
        return
    if _runtime_locked_in_process():
        log("Runtime swap postponed again \u2014 onnxruntime is already loaded", "warning")
        return
    pkg = {"cuda": "onnxruntime-gpu[cuda,cudnn]", "dml": "onnxruntime-directml",
           "cpu": "onnxruntime"}.get(kind)
    if not pkg:
        _pending_runtime_set("")
        return
    log("Installing the %s runtime that was selected before the last restart\u2026"
        % kind.upper())
    try:
        env = dict(os.environ); env["PYTHONNOUSERSITE"] = "1"
        for other in ("onnxruntime-gpu", "onnxruntime-directml", "onnxruntime"):
            subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", other,
                            "--disable-pip-version-check"], env=env,
                           **_no_window({"capture_output": True, "timeout": 900}))
        # v4.28: the CUDA wheels are pulled in by onnxruntime-gpu and stay behind
        # when it goes. Left in place, preload_dlls() maps cuDNN into a process
        # that is running DirectML -- two vendors' libraries in one address space,
        # for no benefit, since DirectML never asks for them.
        if kind != "cuda":
            subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y",
                            "--disable-pip-version-check"] +
                           ["nvidia-cudnn-cu12", "nvidia-cublas-cu12", "nvidia-cufft-cu12",
                            "nvidia-curand-cu12", "nvidia-cuda-runtime-cu12"], env=env,
                           **_no_window({"capture_output": True, "timeout": 900}))
        r = subprocess.run([sys.executable, "-m", "pip", "install", pkg,
                            "--disable-pip-version-check"], env=env,
                           **_no_window({"capture_output": True, "text": True, "timeout": 3600}))
        if r.returncode == 0:
            log("%s runtime installed" % kind.upper())
            _pending_runtime_set("")
        else:
            tail = (r.stderr or r.stdout or "").strip().splitlines()
            log("Runtime install failed: %s" % (tail[-1] if tail else "unknown error"), "error")
            _pending_runtime_set("")
    except Exception as e:
        log("Runtime install failed: %s" % e, "error")
        _pending_runtime_set("")


def _runtime_pref():
    """"auto", "cuda" or "dml" -- what the user asked for, if anything."""
    try:
        db = _get_thread_db()
        r = db.execute("SELECT value FROM config WHERE key='onnx_runtime'").fetchone()
        db.close()
        if r and str(r["value"]) in ("auto", "cuda", "dml", "cpu"):
            return str(r["value"])
    except Exception:
        pass
    return "auto"


def pick_runtime():
    """Which package to install: ("cuda"|"dml"|"cpu", pip name, reason)."""
    pref = _runtime_pref()
    vendor = detect_gpu_vendor()
    win = (os.name == "nt")
    if pref == "cuda":
        return "cuda", "onnxruntime-gpu[cuda,cudnn]", "chosen by hand"
    if pref == "dml":
        return "dml", "onnxruntime-directml", "chosen by hand"
    if pref == "cpu":
        return "cpu", "onnxruntime", "chosen by hand"
    if sys.platform == "darwin":
        return "cpu", "onnxruntime", "macOS has no GPU runtime for ONNX"
    if vendor == "nvidia":
        return "cuda", "onnxruntime-gpu[cuda,cudnn]", "NVIDIA card found"
    if vendor in ("amd", "intel") and win:
        return "dml", "onnxruntime-directml", f"{vendor.upper()} card found \u2014 DirectML"
    if vendor in ("amd", "intel"):
        return "cpu", "onnxruntime", f"{vendor.upper()} card, but DirectML is Windows-only"
    # Nothing recognised: CUDA is the safe guess on Windows/Linux, it falls back
    # to the processor by itself if no NVIDIA card turns up.
    return "cuda", "onnxruntime-gpu[cuda,cudnn]", "no card identified"


_RT_PROGRESS_RAW = re.compile(r"^Progress (\d+) of (\d+)")


_RT_PROGRESS_BAR = re.compile(r"([\d.]+)/([\d.]+)\s*(kB|MB|GB)")


_RT_DOWNLOADING  = re.compile(r"^\s*Downloading\s+(\S+)")


def _runtime_install_worker(then_model=True):
    import subprocess, importlib
    _model_dl.update(active=True, phase="runtime", file="", step="starting",
                     done=0, total=0, all_done=0, all_total=_RT_EXPECTED["gpu"], error="")
    try:
        _tag_notify(force=True)
    except Exception:
        pass

    def _pip(*args, **kw):
        """Run pip and stream its output. pip only emits a progress bar when it
        thinks it is talking to a terminal; over a pipe it prints one summary
        line per file. --progress-bar raw (pip >= 24.1) gives real byte counts
        instead, so we ask for that first and fall back if pip rejects it."""
        raw = kw.get("raw", True)
        env = dict(os.environ)
        env["PYTHONNOUSERSITE"] = "1"
        _ensure_pip_toolchain(env)
        cmd = [sys.executable, "-m", "pip", "--disable-pip-version-check"] + list(args)
        if raw and args and args[0] == "install":
            cmd += ["--progress-bar", "raw"]
        last_push = [0.0]

        def _push(force=False):
            now = _time.time()
            if force or now - last_push[0] >= 0.5:   # keep the SSE stream calm
                last_push[0] = now
                try: _tag_notify(force=True)
                except Exception: pass

        try:
            pr = subprocess.Popen(cmd, env=env, **_no_window({
                "stdout": subprocess.PIPE, "stderr": subprocess.STDOUT,
                "text": True, "bufsize": 1}))
        except Exception as e:
            return 1, str(e)

        tail, base = [], 0            # base = bytes of the wheels already finished
        bad_flag = False
        try:
            for line in pr.stdout:
                line = line.rstrip("\r\n")
                if not line:
                    continue
                if "--progress-bar" in line and ("invalid choice" in line or "no such option" in line):
                    bad_flag = True   # old pip -> retry without raw
                if len(tail) < 40:
                    tail.append(line)

                m = _RT_PROGRESS_RAW.match(line.strip())
                if m:
                    cur, tot = int(m.group(1)), int(m.group(2))
                    _model_dl.update(done=cur, total=tot, all_done=base + cur, step="downloading")
                    if _model_dl["all_done"] > _model_dl["all_total"]:
                        _model_dl["all_total"] = int(_model_dl["all_done"] * 1.05)
                    if cur >= tot and tot:
                        base += tot
                    _push()
                    continue

                d = _RT_DOWNLOADING.match(line)
                if d:
                    name = d.group(1).split("/")[-1]
                    if name.endswith(".whl"):
                        name = name[:-4]
                    _model_dl.update(file=name.split("-")[0] or name, step="downloading",
                                     done=0, total=0)
                    _push(force=True)
                    continue

                b = _RT_PROGRESS_BAR.search(line)
                if b and not m:      # fallback for pip < 24.1
                    u = _RT_UNITS.get(b.group(3), 1)
                    cur, tot = int(float(b.group(1)) * u), int(float(b.group(2)) * u)
                    _model_dl.update(done=cur, total=tot, all_done=base + cur, step="downloading")
                    if _model_dl["all_done"] > _model_dl["all_total"]:
                        _model_dl["all_total"] = int(_model_dl["all_done"] * 1.05)
                    if cur >= tot and tot:
                        base += tot
                    _push()
                    continue

                if line.startswith("Installing collected packages"):
                    _model_dl.update(step="installing", file="", done=0, total=0)
                    _push(force=True)
        except Exception:
            pass
        pr.wait()
        if bad_flag and raw:
            return _pip(*args, raw=False)
        return pr.returncode, "\n".join(tail[-12:])

    def _importable():
        """v4.26: ask a CHILD process whether the runtime works.

        This used to `import onnxruntime` right here, inside the server. Two ways
        that ends badly, and switching to DirectML hit both. If the runtime had
        already been imported -- which it has, whenever tagging ran even once --
        the import is a no-op against a module whose libraries pip has just
        replaced underneath it, so it reports success and the crash arrives later.
        If it had not, the first import loads whatever mixture is on disk, and a
        mismatched native library does not raise a Python exception: it takes the
        process out on the spot, which is why TrackImage simply vanished.
        probe_runtime() builds a real session somewhere expendable instead."""
        try:
            importlib.invalidate_caches()
        except Exception:
            pass
        if state._TAG_RUNTIME_BROKEN:
            state._TAG_RUNTIME_BROKEN = ""    # a reinstall earns a fresh verdict
        ok, why = probe_runtime(timeout=120)
        if ok is True:
            return True
        if ok is None:
            return False
        state._TAG_RUNTIME_BROKEN = why
        return False

    def _runtime_loaded():
        """True once onnxruntime's native libraries are mapped into THIS process.
        pip cannot replace a DLL that Windows has open, so a runtime swap while
        tagging has already run leaves the two builds mixed on disk no matter
        what the installer does. The only honest answer then is a restart."""
        return "onnxruntime" in sys.modules

    ok = False
    try:
        if _importable():
            ok = True
        elif sys.platform == "darwin":
            # No CUDA wheels exist for macOS -- CPU runtime is the only option.
            print("  \u2b07 Installing ONNX Runtime (CPU) into the venv...")
            _tag_runtime_set(_RT_SWAPPING)          # v4.26: same no-touch window
            _model_dl["all_total"] = _RT_EXPECTED["cpu"]
            _pip("install", "onnxruntime")
            ok = _importable()
        elif _runtime_locked_in_process():
            # v4.28: a session is live in this process and its libraries are
            # mapped. pip cannot replace a mapped DLL on Windows, and rewriting
            # the ones it can reach leaves the running session half on the old
            # build and half on the new -- which ends the process outright. The
            # swap is recorded and done at the next start, before anything has
            # imported onnxruntime. CUDA on a fresh venv never hit this because
            # nothing was loaded yet; switching to DirectML afterwards always did.
            kind, pkg, why = pick_runtime()
            _pending_runtime_set(kind)
            _tag_runtime_set(_RT_SWAPPING)
            _model_dl.update(active=False, phase="", error=(
                "%s will be installed the next time TrackImage starts. The runtime "
                "in use right now is loaded into the running program and Windows "
                "will not let it be replaced while it is; doing it anyway is what "
                "used to close TrackImage. Please restart when convenient."
                % {"cuda": "CUDA", "dml": "DirectML", "cpu": "The CPU runtime"}.get(kind, "The runtime")))
            log("Runtime swap to %s deferred to the next start (a session is loaded)" % kind)
            try:
                _tag_notify(force=True)
            except Exception:
                pass
            return True
        else:
            kind, pkg, why = pick_runtime()
            # v4.26: from here until the child process has passed judgement,
            # nothing in this process may touch onnxruntime. pip is about to
            # overwrite its libraries, and the progress callback below pushes a
            # status update every half second -- that path used to ask whether
            # the runtime was importable, mid-write, which is what ended the
            # program.
            _tag_runtime_set(_RT_SWAPPING)
            _model_dl["all_total"] = _RT_EXPECTED.get(kind, _RT_EXPECTED["gpu"])
            size = {"cuda": "~2.5 GB", "dml": "~25 MB", "cpu": "~15 MB"}.get(kind, "")
            print(f"  \u2b07 Installing the {kind.upper()} runtime into the venv "
                  f"(one-time, {size}) \u2014 {why}...")
            # v4.25: all three of these install INTO THE SAME onnxruntime folder,
            # so any two of them present at once means libraries overwriting each
            # other. v4.20 tried to keep the one being installed by asking whether
            # its name appeared inside the target -- and "onnxruntime" appears
            # inside "onnxruntime-directml", so the processor build was never
            # removed. Every one of them goes first; pip has nothing to do when a
            # package is not there.
            for other in ("onnxruntime-gpu", "onnxruntime-directml", "onnxruntime"):
                _pip("uninstall", "-y", other)
            # v4.26: on Windows pip cannot delete a DLL this process still has
            # open, and it reports success anyway -- the file is simply skipped.
            # Anything left behind here will be loaded alongside the new runtime
            # and is exactly the mixture that crashes on the first session.
            leftovers = _runtime_leftovers()
            _pip("install", pkg)
            ok = _importable()
            if leftovers or _runtime_loaded():
                _model_dl.update(active=False, phase="", error=(
                    "%s is installed. TrackImage has to restart before it can be "
                    "used: the previous runtime is still loaded in this process, "
                    "so both versions are in memory at once and starting a "
                    "tagging session now would close the program."
                    % {"cuda": "CUDA", "dml": "DirectML", "cpu": "The CPU runtime"}.get(kind, "The runtime")))
                log("Runtime switched to %s \u2014 restart required before tagging" % kind)
                try:
                    _tag_notify(force=True)
                except Exception:
                    pass
                return True
            if not ok and kind != "cpu":
                print("  \u26a0 No matching wheel -- falling back to the CPU runtime...")
                _model_dl.update(all_total=_RT_EXPECTED["cpu"], all_done=0, done=0, total=0)
                _pip("uninstall", "-y", pkg.split("[")[0])
                _pip("install", "onnxruntime")
                ok = _importable()
        if not ok:
            _model_dl.update(active=False, phase="", error=(
                "The runtime was installed but could not be imported into the "
                "running process. Restart TrackImage to finish the setup."))
            return False
        print("  \u2705 ONNX runtime ready")
    except Exception as e:
        _model_dl.update(active=False, phase="", error=str(e))
        return False

    if then_model and _model_dl_missing():
        _model_dl_worker()
    else:
        _model_dl.update(active=False, phase="", error="")
        try:
            _tag_notify(force=True)
            _tag_ensure_running()
        except Exception:
            pass
    return True


def _model_dl_worker():
    import urllib.request as _ur, time as _mt
    _last_n = [0.0]
    _model_dl.update(active=True, phase="model", error="", step="",
                     all_done=0, all_total=0)
    try:
        os.makedirs(TAGGER_DIR, exist_ok=True)
        for fname in list(_TAG_MODEL_FILES):
            if not _model_dl_missing() or fname not in _model_dl_missing():
                if os.path.exists(os.path.join(TAGGER_DIR, fname)):
                    continue
            url = _TAG_MODEL_FILES[fname]
            dest = os.path.join(TAGGER_DIR, fname); part = dest + ".part"
            attempt = 0
            while not os.path.exists(dest):
                attempt += 1
                try:
                    _model_dl.update(file=fname, done=0, total=0, error="")
                    total, ranges_ok = 0, False
                    try:   # probe size + range support
                        _h = _ur.Request(url, headers={"User-Agent": "TrackImage/" + VERSION}, method="HEAD")
                        with _ur.urlopen(_h, timeout=30) as hr:
                            total = int(hr.headers.get("Content-Length") or 0)
                            ranges_ok = "bytes" in (hr.headers.get("Accept-Ranges") or "")
                    except Exception:
                        pass
                    _model_dl["total"] = total

                    def _pull(lo, hi, idx, errs):
                        """One slice of the file.

                        v4.15: every assumption here is now checked. This ran on
                        trust before -- ask for a range, seek, write whatever comes
                        back -- and when a redirect to the CDN dropped the Range
                        header the server answered 200 with the entire file. This
                        thread then wrote all 1064 MB starting at ITS offset, over
                        the slices its neighbours had just written. The result was
                        the right size and unreadable, and nothing noticed until
                        the tagger tried to parse it."""
                        want = hi - lo + 1
                        try:
                            rq = _ur.Request(url, headers={"User-Agent": "TrackImage/" + VERSION,
                                                           "Range": f"bytes={lo}-{hi}"})
                            with _ur.urlopen(rq, timeout=30) as rr, open(part, "r+b") as f:
                                # 206 is the only answer that means "here is your slice".
                                code = getattr(rr, "status", None) or rr.getcode()
                                if code != 206:
                                    raise IOError(f"server ignored the range request (HTTP {code})")
                                cr = rr.headers.get("Content-Range") or ""
                                if not cr.startswith(f"bytes {lo}-{hi}/"):
                                    raise IOError(f"server sent a different range ({cr or 'none'})")
                                f.seek(lo)
                                got = 0
                                while True:
                                    c = rr.read(512 * 1024)
                                    if not c: break
                                    got += len(c)
                                    if got > want:          # never run past our own slice
                                        raise IOError("range delivered more bytes than it promised")
                                    f.write(c); _model_dl["done"] += len(c)
                                    if _mt.time() - _last_n[0] >= 0.4:   # v3.74: smoother live progress
                                        _last_n[0] = _mt.time()
                                        try: _tag_notify(force=True)
                                        except Exception: pass
                                if got != want:
                                    raise IOError(f"range stopped short ({got} of {want} bytes)")
                        except Exception as pe:
                            errs.append(pe)

                    if ranges_ok and total > 16 * 1024 * 1024:   # v3.62: 6 parallel range streams
                        with open(part, "wb") as f:
                            f.truncate(total)
                        n_conn = 6
                        step = total // n_conn
                        errs, ths = [], []
                        import threading as _dt
                        for i in range(n_conn):
                            lo = i * step
                            hi = (total - 1) if i == n_conn - 1 else (lo + step - 1)
                            t = _dt.Thread(target=_pull, args=(lo, hi, i, errs), daemon=True)
                            t.start(); ths.append(t)
                        for t in ths: t.join()
                        if errs: raise errs[0]
                    else:   # fallback: single stream
                        req = _ur.Request(url, headers={"User-Agent": "TrackImage/" + VERSION})
                        with _ur.urlopen(req, timeout=30) as r, open(part, "wb") as out:
                            if not _model_dl["total"]:
                                _model_dl["total"] = int(r.headers.get("Content-Length") or 0)
                            while True:
                                chunk = r.read(512 * 1024)
                                if not chunk: break
                                out.write(chunk); _model_dl["done"] += len(chunk)
                                if _mt.time() - _last_n[0] >= 1.0:
                                    _last_n[0] = _mt.time()
                                    try: _tag_notify(force=True)
                                    except Exception: pass
                    if _model_dl["total"] and os.path.getsize(part) != _model_dl["total"]:
                        raise IOError("size mismatch \u2014 incomplete download")
                    # v4.16: no checksum comparison here. v4.15 held the file against
                    # the ETag, believing it to be a sha256 of the contents; it is a
                    # git hash for a small file and a Xet content hash for a large
                    # one, so the test failed on every correct download. What the
                    # file is actually guaranteed by is the per-range verification in
                    # _pull above and the tagger discarding anything it cannot parse.
                    # The digest is recorded so a known-good value can be pinned if
                    # that is ever wanted.
                    if fname.endswith(".onnx"):
                        _dg = _sha256_file(part)
                        if _dg:
                            log(f"Model {fname} sha256 {_dg}")
                    os.replace(part, dest)   # atomic: never a half-written model file
                    print("  \u2b07 Model file downloaded: " + fname + " (" + str(_model_dl["done"] // (1024 * 1024)) + " MB)")
                except Exception as e:
                    try: os.remove(part)
                    except Exception: pass
                    _model_dl["error"] = str(e)
                    wait = 60 if attempt >= 3 else 5
                    print("  \u26a0 Model download failed (" + fname + "): " + str(e) + " \u2014 retry in " + str(wait) + " s")
                    _mt.sleep(wait)
        _model_dl.update(active=False, phase="", error="")
        print("  \u2705 Auto-tagging model ready \u2014 tagging the whole library in the background")
        try:
            _tag_notify(force=True)
            _tag_ensure_running()   # retroactive: tags every already-embedded image
        except Exception: pass
    except Exception as e:
        _model_dl.update(active=False, phase="", error=str(e))


def _sha256_file(path):
    """v4.15: read a file once and return its sha256, or "" if it cannot be read.
    Used to hold a downloaded model against the checksum its host publishes."""
    import hashlib as _hl
    try:
        h = _hl.sha256()
        with open(path, "rb") as f:
            for blk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(blk)
        return h.hexdigest()
    except Exception:
        return ""


def _venv_site_packages():
    """site-packages of the venv we are running in, or None outside a venv.

    v3.76: derived from sys.prefix instead of asking the site module. Everything
    TrackImage needs lives in its own venv by design, and a --user install of the
    same nvidia wheels elsewhere on the machine must never be mixed in."""
    if getattr(sys, "base_prefix", sys.prefix) == sys.prefix:
        return None                                   # not in a venv
    cands = []
    if os.name == "nt":
        cands.append(os.path.join(sys.prefix, "Lib", "site-packages"))
    else:
        v = f"python{sys.version_info[0]}.{sys.version_info[1]}"
        cands.append(os.path.join(sys.prefix, "lib", v, "site-packages"))
        cands.append(os.path.join(sys.prefix, "lib64", v, "site-packages"))
    for c in cands:
        if os.path.isdir(c):
            return c
    return None


def _replay_install_log():
    """v4.22: put the launcher's setup output into the console.

    Everything the launcher prints happens before Python is even running, so the
    console in Settings never showed any of it -- the one moment a user most
    wants to look back at what was installed. The launcher writes those same
    lines to install.log; they are replayed here so the record is in one place."""
    path = os.path.join(LOG_DIR, "install.log")
    try:
        if not os.path.isfile(path):
            return
        lines = [l.rstrip() for l in open(path, encoding="utf-8", errors="replace")]
        lines = [l for l in lines if l.strip()][-60:]
        if not lines:
            return
        log("\u2500\u2500 setup, from the launcher window \u2500\u2500")
        for l in lines:
            log(l)
        log("\u2500\u2500 end of setup \u2500\u2500")
    except Exception:
        pass


def check_assets():
    """v4.13: the interface asks for seven font files and the window for its icon.
    When they were missing the fonts fell back to a system face and Windows drew
    the generic Python feather -- both silent, both easy to miss for a long time.
    Say what is missing instead."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    missing = [a for a in REQUIRED_ASSETS if not os.path.isfile(os.path.join(root, *a.split("/")))]
    if missing:
        log(f"{len(missing)} file(s) missing from this install \u2014 the interface still "
            f"runs but does not look as intended: {', '.join(missing)}", "warning")
    return missing


def _dist_info_dirs(prefixes):
    """Every *.dist-info folder whose package name starts with one of prefixes."""
    # v4.20: ask Python where packages actually live rather than guessing. A venv,
    # a Debian dist-packages layout and a Windows Lib/site-packages are all
    # different, and a wrong guess would silently check nothing at all.
    bases = set()
    try:
        import site, sysconfig
        for b in (site.getsitepackages() or []):
            bases.add(b)
        try:
            bases.add(site.getusersitepackages())
        except Exception:
            pass
        for k in ("purelib", "platlib"):
            v = sysconfig.get_paths().get(k)
            if v:
                bases.add(v)
    except Exception:
        pass
    bases |= {os.path.join(sys.prefix, "Lib", "site-packages")}
    bases |= set(glob.glob(os.path.join(sys.prefix, "lib", "python3*", "site-packages")))
    out = []
    for base in bases:
        if not base or not os.path.isdir(base):
            continue
        for d in glob.glob(os.path.join(base, "*.dist-info")):
            name = os.path.basename(d).split("-")[0].lower().replace("_", "-")
            if any(name.startswith(px) for px in prefixes):
                out.append(d)
    return out


def verify_installed_files(prefixes=("onnxruntime", "nvidia"), deep=False):
    """v4.20: hold the installed files against what pip says it wrote.

    pip leaves a RECORD next to every package listing the sha256 and the byte
    count of each file it installed. A library that arrived truncated -- a
    download cut short, a disk that ran out -- therefore has a size that does not
    match, and can be named precisely instead of guessed at. Size alone catches
    the truncation case and costs nothing; the hash is only computed when asked
    for, because these are gigabytes of CUDA libraries.

    Returns (missing, damaged, checked) -- damaged as (path, expected, actual)."""
    import csv
    missing, damaged, checked = [], [], 0
    for info in _dist_info_dirs(prefixes):
        rec = os.path.join(info, "RECORD")
        if not os.path.isfile(rec):
            continue
        root = os.path.dirname(info)
        try:
            with open(rec, encoding="utf-8", newline="") as fh:
                rows = list(csv.reader(fh))
        except Exception:
            continue
        for row in rows:
            if len(row) < 3 or not row[1] or not row[2]:
                continue                      # no hash recorded (RECORD itself)
            rel, want_hash, want_size = row[0], row[1], row[2]
            if rel.endswith((".pyc", ".pyo")) or ".dist-info" in rel:
                continue
            fp = os.path.normpath(os.path.join(root, rel))
            try:
                size = os.path.getsize(fp)
            except OSError:
                missing.append(fp)
                continue
            checked += 1
            try:
                if size != int(want_size):
                    damaged.append((fp, int(want_size), size))
                    continue
            except ValueError:
                continue
            if deep and want_hash.startswith("sha256="):
                import hashlib, base64
                h = hashlib.sha256()
                try:
                    with open(fp, "rb") as f:
                        for blk in iter(lambda: f.read(1024 * 1024), b""):
                            h.update(blk)
                except OSError:
                    missing.append(fp); continue
                got = base64.urlsafe_b64encode(h.digest()).rstrip(b"=").decode()
                if got != want_hash[7:]:
                    damaged.append((fp, "sha256 " + want_hash[7:][:12], "sha256 " + got[:12]))
    return missing, damaged, checked


_PIP_TOOLCHAIN_DONE = [False]


def _ensure_pip_toolchain(env=None):
    """Make sure pip itself can build what it is about to be asked for.

    v4.36: a virtual environment created by Python 3.12 contains pip and nothing
    else -- no setuptools, no wheel. A package that ships only a source archive
    and no pyproject.toml then falls back to pip's old setup.py route, which
    needs precisely the setuptools that is missing, and an older pip does not
    recover from that: it prints a deprecation notice and stops. The launcher
    handles this before the first install; this covers the installs that happen
    later, from inside the running program.

    Runs once per session and never blocks anything -- if it fails, the install
    that follows is no worse off than it would have been.
    """
    if _PIP_TOOLCHAIN_DONE[0]:
        return
    _PIP_TOOLCHAIN_DONE[0] = True
    try:
        import importlib.util as _ilu
        if _ilu.find_spec("setuptools") and _ilu.find_spec("wheel"):
            return
        e = dict(env or os.environ)
        e["PYTHONNOUSERSITE"] = "1"
        log("Preparing the installer (pip, setuptools, wheel) \u2014 first time only", "info")
        subprocess.run([sys.executable, "-m", "pip", "--disable-pip-version-check",
                        "install", "--upgrade", "pip", "setuptools", "wheel"],
                       capture_output=True, text=True, timeout=900, env=e,
                       **_no_window({}))
    except Exception as ex:
        log(f"Could not update pip beforehand ({type(ex).__name__}) \u2014 continuing anyway", "warning")


def repair_packages(names):
    """Reinstall packages, bypassing pip's cache.

    v4.20: --no-cache-dir matters more than it looks. Without it pip hands back
    the very file that arrived damaged, and the repair changes nothing."""
    done = []
    for n in names:
        cmd = [sys.executable, "-m", "pip", "--disable-pip-version-check",
               "install", "--force-reinstall", "--no-cache-dir", n]
        env = dict(os.environ); env["PYTHONNOUSERSITE"] = "1"
        _ensure_pip_toolchain(env)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, env=env)
            done.append((n, r.returncode == 0, (r.stderr or r.stdout or "")[-300:]))
        except Exception as e:
            done.append((n, False, str(e)))
    return done


def _package_of(path):
    """Which pip package a damaged file belongs to, for the repair button."""
    parts = os.path.normpath(path).split(os.sep)
    i = -1
    for marker in ("site-packages", "dist-packages"):   # venv vs. distro layout
        if marker in parts:
            i = parts.index(marker); break
    if i < 0:
        return ""
    top = parts[i + 1] if len(parts) > i + 1 else ""
    if top == "nvidia" and len(parts) > i + 2:
        return "nvidia-%s-cu12" % parts[i + 2].replace("_", "-")
    if top.startswith("onnxruntime"):
        return "onnxruntime"
    return top.replace("_", "-")


def _runtime_leftovers():
    """v4.26: files still sitting in the onnxruntime package after it was
    uninstalled. All three builds share one folder name, so a leftover from the
    previous runtime is loaded together with the new one -- the mixture that
    made switching to DirectML close the program."""
    try:
        import site
        out = []
        for base in set((site.getsitepackages() or [])):
            d = os.path.join(base, "onnxruntime")
            if os.path.isdir(d):
                for root, _dirs, files in os.walk(d):
                    out += [os.path.join(root, f) for f in files
                            if f.lower().endswith((".dll", ".pyd", ".so", ".dylib"))]
        return out
    except Exception:
        return []


def _bench_get():
    try:
        db = _get_thread_db()
        r = db.execute("SELECT value FROM config WHERE key=?", (_BENCH_KEY,)).fetchone()
        db.close()
        return json.loads(r["value"]) if r and r["value"] else {}
    except Exception:
        return {}


def _bench_set(d):
    try:
        db = _get_thread_db()
        with _db_write_lock:
            db.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?,?)",
                       (_BENCH_KEY, json.dumps(d)))
            _db_commit_retry(db)
        db.close()
    except Exception:
        pass


def _bench_runtime(model_path, runs=6, timeout=300):
    """v4.29: time this model on the GPU provider and on the CPU, in a child
    process, and report seconds per image for each.

    Assuming the GPU is faster is wrong often enough to matter. For a 1.26 GB
    EVA02-Large transformer the published evidence runs from a clear win on a
    discrete card to a loss against a well-threaded CPU on integrated graphics,
    and there is no benchmark anywhere for this model on AMD. So measure it on
    the machine it is actually running on rather than guessing from the vendor
    name. Runs in a child process for the same reason everything else here does:
    a DirectML fault is a crash, not an exception."""
    code = (
        "import os,sys,json,time\n"
        "if os.name == 'nt':\n"
        "    import ctypes\n"
        "    ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)\n"
        "import onnxruntime as ort, numpy as np\n"
        "m=os.environ['TI_BENCH_MODEL']; runs=int(os.environ.get('TI_BENCH_RUNS','6'))\n"
        "avail=list(ort.get_available_providers())\n"
        "gpu=[p for p in ('CUDAExecutionProvider','DmlExecutionProvider',"
        "'ROCMExecutionProvider') if p in avail]\n"
        "out={}\n"
        "def bench(prov):\n"
        "    so=ort.SessionOptions(); so.log_severity_level=3\n"
        "    so.intra_op_num_threads=1 if prov!='CPUExecutionProvider' else 0\n"
        "    if prov=='DmlExecutionProvider':\n"
        "        so.enable_mem_pattern=False\n"
        "        so.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL\n"
        "    s=ort.InferenceSession(m, sess_options=so, providers=[prov,'CPUExecutionProvider'])\n"
        "    if prov not in s.get_providers(): return None\n"
        "    i=s.get_inputs()[0]\n"
        "    shp=[(1 if (not isinstance(d,int) or d<1) else d) for d in i.shape]\n"
        "    dt=np.float16 if 'float16' in (i.type or '') else np.float32\n"
        "    x=np.zeros(shp,dtype=dt)\n"
        "    s.run(None,{i.name:x})\n"          # discard the first: shader compilation
        "    t0=time.perf_counter()\n"
        "    for _ in range(runs): s.run(None,{i.name:x})\n"
        "    return (time.perf_counter()-t0)/runs\n"
        "for prov in (gpu[:1] + ['CPUExecutionProvider']):\n"
        "    try:\n"
        # v4.29: microsecond resolution. Rounding to 4 places turned a fast
        # result into a stored 0.0, which then reads as "no measurement" and
        # divides by zero when the two providers are compared.
        "        v=bench(prov)\n"
        "        if v and v>0: out[prov]=round(v,6)\n"
        "    except Exception as e:\n"
        "        sys.stderr.write('%s failed: %s\\n' % (prov, e))\n"
        "sys.stdout.write(json.dumps(out))\n"
        "sys.exit(0)\n")
    env = dict(os.environ)
    env["TI_BENCH_MODEL"] = model_path
    env["TI_BENCH_RUNS"] = str(runs)
    env["PYTHONNOUSERSITE"] = "1"
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           timeout=timeout, env=env,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return {}
    if r.returncode != 0:
        return {}
    try:
        return json.loads((r.stdout or "{}").strip())
    except Exception:
        return {}


def _bench_runtime_async():
    """Run the comparison once per runtime, then say which won."""
    def _run():
        model_path = os.path.join(TAGGER_DIR, "model.onnx")
        if not os.path.isfile(model_path) or not _tag_runtime_available():
            return
        rt = state._TAG_PROV_USED or state._TAG_PROVIDERS or "?"
        old = _bench_get()
        if old.get("_for") == rt:
            return                      # already measured for this runtime
        res = _bench_runtime(model_path)
        if not res:
            return
        res["_for"] = rt
        _bench_set(res)
        gpu = {k: v for k, v in res.items()
               if k not in ("CPUExecutionProvider", "_for")}
        cpu = res.get("CPUExecutionProvider")
        if gpu and cpu and cpu > 0:
            name, gt = sorted(gpu.items(), key=lambda kv: kv[1])[0]
            if gt <= 0:
                return
            short = {"CUDAExecutionProvider": "CUDA", "DmlExecutionProvider": "DirectML",
                     "ROCMExecutionProvider": "ROCm"}.get(name, name)
            if gt < cpu:
                log("%s is %.1fx faster than the processor for auto-tagging "
                    "(%.0f ms vs %.0f ms per image)" % (short, cpu / gt, gt * 1000, cpu * 1000))
            else:
                log("The processor is %.1fx faster than %s here (%.0f ms vs %.0f ms per "
                    "image). Auto-tagging will be quicker with the CPU runtime on this "
                    "machine \u2014 Settings \u203a Auto-tagging can switch it."
                    % (gt / cpu, short, cpu * 1000, gt * 1000), "warning")
        elif cpu:
            log("Auto-tagging runs at %.0f ms per image on the processor" % (cpu * 1000))
    threading.Thread(target=_run, daemon=True, name="runtime-bench").start()


def probe_runtime(timeout=45):
    """v4.25: build an actual ONNX session in a child process.

    probe_module below only imports, and a runtime whose libraries have been
    overwritten by another runtime imports perfectly well -- it dies afterwards,
    when a session is created, on whichever thread asked for it. Doing the real
    thing over here means that failure is an exit code rather than the end of the
    program."""
    code = (
        "import importlib.util,sys\n"
        # v4.26: a native crash in here otherwise raises Windows Error Reporting,
        # which puts a modal dialog on an invisible child process and holds it
        # until the timeout. That turned a broken runtime into a three minute
        # freeze on every start -- long past the point where the launcher gives
        # up, which is why TrackImage would not come back after a runtime swap.
        "import os\n"
        "if os.name == 'nt':\n"
        "    import ctypes\n"
        "    ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)\n"
        "    try: ctypes.windll.ntdll.RtlSetProcessPlaceholderCompatibilityMode(1)\n"
        "    except Exception: pass\n"
        "if importlib.util.find_spec('onnxruntime') is None: sys.exit(3)\n"
        "import onnxruntime as ort\n"
        "provs=list(ort.get_available_providers())\n"
        "sys.stderr.write('providers=' + ','.join(provs) + '\\n')\n"
        "so=ort.SessionOptions(); so.log_severity_level=3\n"
        # v4.29: DirectML rejects the memory-pattern optimiser and parallel
        # execution -- with the defaults left in place the session either fails
        # to build or behaves unpredictably. The probe has to configure the
        # runtime exactly as the tagger will, or it is answering a different
        # question than the one being asked.
        "if 'DmlExecutionProvider' in provs:\n"
        "    so.enable_mem_pattern=False\n"
        "    so.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL\n"
        "m=os.environ.get('TI_TAG_MODEL','')\n"
        "if m and os.path.isfile(m):\n"
        "    s=ort.InferenceSession(m, sess_options=so, providers=provs)\n"
        "    sys.stderr.write('used=' + ','.join(s.get_providers()) + '\\n')\n"
        # v4.29: and it has to RUN something. Building a session proves very
        # little: DirectML crashes are routinely thrown by the first or even the
        # second inference, not by session creation, so a probe that stopped at
        # construction reported a healthy runtime that then took the program down
        # on its first real image.
        "    import numpy as np\n"
        "    i=s.get_inputs()[0]\n"
        "    shp=[(1 if (not isinstance(d,int) or d<1) else d) for d in i.shape]\n"
        "    dt=np.float16 if 'float16' in (i.type or '') else np.float32\n"
        "    x=np.zeros(shp, dtype=dt)\n"
        "    t0=__import__('time').perf_counter()\n"
        "    s.run(None, {i.name: x})\n"
        "    s.run(None, {i.name: x})\n"
        "    sys.stderr.write('warmup=%.3f\\n' % ((__import__('time').perf_counter()-t0)/2))\n"
        "sys.exit(0)\n")
    env = dict(os.environ)
    env["PYTHONNOUSERSITE"] = "1"
    model = os.path.join(TAGGER_DIR, "model.onnx")
    if os.path.isfile(model):
        env["TI_TAG_MODEL"] = model
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, timeout=timeout, env=env,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        # subprocess.run has already killed the child by the time this lands.
        _why = ("building a session did not finish within %d seconds \u2014 the "
                "runtime is most likely damaged; Settings \u203a Auto-tagging \u203a "
                "Repair installation reinstalls it" % timeout)
        _tag_runtime_set(_RT_BROKEN, _why)
        return False, _why
    except Exception as e:
        return False, f"could not be tested ({e})"
    if r.returncode == 3:
        _tag_runtime_set(_RT_ABSENT)
        return None, ""
    if r.returncode == 0:
        for line in (r.stderr or "").splitlines():
            if line.startswith("providers="):
                state._TAG_PROVIDERS = line[10:].strip()
            elif line.startswith("used="):
                state._TAG_PROV_USED = line[5:].strip()
            elif line.startswith("warmup="):
                try:
                    state._TAG_WARMUP = float(line[7:].strip())
                except ValueError:
                    pass
        _tag_runtime_set(_RT_OK)
        return True, ""
    err = [l for l in (r.stderr or "").strip().splitlines() if l and not l.startswith("providers=")]
    detail = err[-1] if err else ""
    if not detail:
        detail = ("building a session crashed the interpreter (exit code %s) \u2014 two "
                  "runtimes were probably installed over each other; Repair "
                  "installation puts it right" % r.returncode)
    _tag_runtime_set(_RT_BROKEN, detail)
    return False, detail


def probe_module(mod, timeout=90):
    """Try to import a module in a CHILD process.

    v4.24: some imports do not fail, they crash. onnxruntime loads the CUDA
    libraries, and a damaged one takes the whole process with it -- an access
    violation, no traceback, an empty logfile and a program that simply will not
    start. Doing it over there means the worst case is an exit code.

    Returns (True, "") when it imported, (None, "") when it is not installed, and
    (False, reason) when it is present but unusable."""
    code = ("import importlib.util,sys\n"
            "sys.exit(3) if importlib.util.find_spec(%r) is None else None\n"
            "import %s\n"
            "sys.exit(0)\n" % (mod, mod))
    env = dict(os.environ)
    env["PYTHONNOUSERSITE"] = "1"
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, timeout=timeout, env=env,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return False, "the import did not finish within %d seconds" % timeout
    except Exception as e:
        return False, f"could not be tested ({e})"
    if r.returncode == 0:
        return True, ""
    if r.returncode == 3:
        return None, ""
    err = (r.stderr or "").strip().splitlines()
    detail = err[-1] if err else ""
    if not detail:
        # No Python error at all: the interpreter died inside native code.
        detail = ("the import crashed the interpreter (exit code %s) \u2014 this is a "
                  "damaged or mismatched native library, not a Python fault" % r.returncode)
    return False, detail


def _probe_runtime_async():
    """v4.26: verify the ONNX runtime in the background, after the port is open.
    Tagging is held back until this answers -- a runtime that cannot build a
    session must never be reached by the tagging thread, because that failure is
    a native crash and takes the whole program with it."""
    def _run():
        ok, why = probe_runtime()
        if ok is True:
            log("onnxruntime loads cleanly \u2014 auto-tagging is available")
            state._TAG_RUNTIME_BROKEN = ""
            _bench_runtime_async()       # v4.29: measure GPU against CPU, once
            try:
                _tag_ensure_running()
            except Exception:
                pass
        elif ok is None:
            log("onnxruntime is not installed \u2014 auto-tagging is unavailable")
        else:
            state._TAG_RUNTIME_BROKEN = why
            log("onnxruntime is installed but will not load \u2014 %s. Auto-tagging is "
                "switched off so this cannot take TrackImage down. "
                "Settings \u203a Auto-tagging \u203a Repair installation reinstalls it." % why,
                "error")
        try:
            _tag_notify(force=True)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True, name="runtime-probe").start()


def check_venv():
    """v4.14: a package can arrive half-installed -- a download cut short, a full
    disk -- and the only sign is a crash much later, in a place that has nothing
    to do with the real cause. One user lost a single CUDA DLL that way. Import
    what the program relies on and name whatever does not answer.

    Optional pieces are reported as a note, not a fault: the program runs without
    them, it just does less."""
    core = [("flask", "the web server"), ("PIL", "image reading"),
            ("numpy", "duplicate detection")]
    extra = [("webview", "the app window"), ("watchdog", "folder watching"),
             ("send2trash", "the Recycle Bin"),
             ("imageio_ffmpeg", "video thumbnails")]
    if os.name == "nt":
        extra.append(("win32com", "dragging files out of the window"))
    # v4.24: onnxruntime is NOT in that list. Importing it pulls the CUDA
    # libraries into this process, and a damaged one does not raise -- it kills
    # the process outright, before the window ever appears and before anything
    # reaches the logfile. It is tried in a child process instead, further down.
    broken, absent = [], []
    for mod, what in core + extra:
        try:
            __import__(mod)
        except ImportError:
            absent.append((mod, what))
        except Exception as e:
            # Present but unusable -- a missing DLL of its own lands here, which
            # is exactly the case this check exists for.
            broken.append((mod, what, f"{type(e).__name__}: {e}"))
    for mod, what, why in broken:
        log(f"{mod} is installed but will not load ({what}) — {why}. "
            f"Delete the venv folder and start again to reinstall it.", "error")
    missing_core = [m for m, _w in absent if m in dict((c, w) for c, w in core)]
    for mod, what in absent:
        lvl = "error" if mod in missing_core else "info"
        log(f"{mod} is not installed — {what} is unavailable", lvl)
    # v4.26: this used to run right here, before the port was open. Building a
    # session takes seconds on a healthy install and up to the full timeout on a
    # damaged one, and the launcher waits 30s before declaring the start failed
    # -- so the one situation where the check matters was also the one where it
    # stopped TrackImage from starting at all. It moves off the startup path;
    # tagging stays disabled until it reports back, which is the safe direction.
    _probe_runtime_async()
    _cuda_dll_check()
    # v4.20: a size that disagrees with pip's own record is a damaged file, and
    # naming it now saves an unexplained fall back to the processor later.
    try:
        miss, bad, n = verify_installed_files()
        if bad or miss:
            for fp, want, got in bad[:5]:
                log(f"{os.path.basename(fp)} is damaged \u2014 expected {want} bytes, found {got}. "
                    f"Settings \u2192 Auto-tagging \u2192 Repair installation puts it right.", "error")
            for fp in miss[:5]:
                log(f"{os.path.basename(fp)} is missing from the installation", "error")
            if len(bad) + len(miss) > 10:
                log(f"\u2026 and {len(bad) + len(miss) - 10} more", "error")
        elif n:
            log(f"Installation check: {n:,} files match pip's record")
    except Exception:
        pass
    return broken, absent


def _cuda_dll_check():
    """The CUDA wheels ship loose DLLs; one of them going missing is silent until
    onnxruntime tries to start the GPU and falls back with no reason given."""
    if os.name != "nt":
        return
    try:
        import ctypes, glob
        base = os.path.join(sys.prefix, "Lib", "site-packages", "nvidia")
        if not os.path.isdir(base):
            return
        bad = []
        for dll in glob.glob(os.path.join(base, "*", "bin", "*.dll")):
            if os.path.getsize(dll) == 0:
                bad.append(os.path.basename(dll))
        if bad:
            log(f"{len(bad)} CUDA library file(s) are empty and did not download "
                f"completely: {', '.join(sorted(bad)[:6])}. Auto-tagging will fall back "
                f"to the processor. Delete the venv folder and start again.", "error")
    except Exception:
        pass
