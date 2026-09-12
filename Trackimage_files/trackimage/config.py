"""Version, paths, file extensions and every other constant.

Layer 1 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, g, make_response, Response
)
from pathlib import Path
import os
import re
import sys
from . import state


VERSION = "4.66"


state.WINDOW_MODE = False   # v4.10: set when the app runs in its own window


APP_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


STATIC_DIR = os.path.join(APP_DIR, "Static")




# v4.51: the database, the logs and the ignore list are the only things in here
# that belong to the person using TrackImage rather than to the build. They now
# sit together under Userdata, so a new version can replace everything around
# them without ever reaching into them.
USERDATA_DIR = os.path.join(APP_DIR, "Userdata")


def _adopt_old_userdata():
    """Move a pre-4.51 layout into Userdata, keeping a copy of what was there.

    Only ever runs when Userdata does not exist yet and an old folder does. The
    backup is made first and is never deleted: if anything about the move looks
    wrong, the original is still on disk under its old name with .pre449 added.
    """
    import shutil
    for name in ("Databank", "Logs", "ignored_tags.txt"):
        old = os.path.join(APP_DIR, name)
        new = os.path.join(USERDATA_DIR, name)
        if not os.path.exists(old) or os.path.exists(new):
            continue
        # v4.51: the launcher makes Logs and Databank before Python runs, so on
        # a fresh install two empty folders sat here looking like an older
        # layout and got backed up as .pre449 for nothing.
        try:
            if os.path.isdir(old) and not os.listdir(old):
                os.rmdir(old)
                continue
            if os.path.isfile(old) and os.path.getsize(old) == 0:
                os.remove(old)
                continue
        except Exception:
            pass
        backup = old + ".pre449"
        try:
            if not os.path.exists(backup):
                if os.path.isdir(old):
                    shutil.copytree(old, backup)
                else:
                    shutil.copy2(old, backup)
            os.makedirs(USERDATA_DIR, exist_ok=True)
            shutil.move(old, new)
            print(f"  moved {name} into Userdata (a copy stayed as {name}.pre449)")
        except Exception as e:
            print(f"  could not move {name} into Userdata: {e}")


os.makedirs(USERDATA_DIR, exist_ok=True)
_adopt_old_userdata()

DB_DIR     = os.path.join(USERDATA_DIR, "Databank")


LOG_DIR    = os.path.join(USERDATA_DIR, "Logs")


for _d in (DB_DIR, LOG_DIR):
    try: os.makedirs(_d, exist_ok=True)
    except Exception: pass


def _ensure_std_streams():
    if sys.stdout is not None and sys.stderr is not None and sys.stdin is not None:
        return
    try:
        _p = os.path.join(LOG_DIR, "trackimage.log")
        _f = open(_p, "a", encoding="utf-8", errors="replace", buffering=1)
    except Exception:
        _f = open(os.devnull, "w")
    if sys.stdout is None: sys.stdout = _f
    if sys.stderr is None: sys.stderr = _f
    if sys.stdin is None:
        # multiprocessing/spawn duplicates this handle on Windows -- without it
        # the compute pool cannot start under pythonw.
        try: sys.stdin = open(os.devnull, "r")
        except Exception: pass


_ensure_std_streams()


for _blas_var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                  "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_blas_var, "1")


_IS_MP_WORKER = os.environ.get("TRACKIMAGE_MP_WORKER") == "1"


if _IS_MP_WORKER:
    import builtins as _bi
    _bi.print = lambda *args, **kw: None


try:
    from PIL import Image
    HAS_PILLOW = True
except Exception as _pil_err:
    HAS_PILLOW = False
    print(f"⚠ Pillow not importable ({_pil_err}) — thumbnails & metadata disabled.")
    print("   Hint: DLL import errors often mean the install path is too deep/long — move TrackImage to a short path like C:\\TrackImage and delete the venv folder.")


try:
    import imageio_ffmpeg
    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG_BIN = "ffmpeg"  # fallback to system ffmpeg


try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    print("⚠ watchdog not installed — auto-sync disabled.")


try:
    from send2trash import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False
    print("⚠ send2trash not installed — deleted files will stay in internal trash instead of Recycle Bin.")


try:
    import numpy as np
    HAS_NUMPY = True
    # 8-bit popcount lookup table — vectorised Hamming distance is bit-identical to
    # the pure-Python popcount(a ^ b), just computed in C. No accuracy change.
    _POPCOUNT_LUT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint16)
except Exception:
    HAS_NUMPY = False
    _POPCOUNT_LUT = None


HAS_PHASH = HAS_NUMPY


if not HAS_PHASH:
    print("⚠ numpy not installed — duplicate detection disabled.")


TILE_GRID = 8            # 8x8 = 64 cells per image


TILE_CELLS = TILE_GRID * TILE_GRID


app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static",
            template_folder=STATIC_DIR, instance_path=DB_DIR)


app.config["DATABASE"] = os.path.join(app.instance_path, "trackimage.db")


def _path_is_network(p):
    try:
        p = os.path.abspath(p)
        if p.startswith("\\\\"):
            return True
        if os.name == "nt":
            import ctypes
            drive = os.path.splitdrive(p)[0] + "\\"
            return ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(drive)) == 4  # DRIVE_REMOTE
    except Exception:
        pass
    return False


_ORIG_DB_PATH = app.config["DATABASE"]


try:
    import webview as _webview
    HAS_WEBVIEW = True
except Exception:
    _webview = None
    HAS_WEBVIEW = False


DB_ON_NETWORK = _path_is_network(_ORIG_DB_PATH)


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".tif", ".ico", ".svg", ".avif", ".jfif"}


VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".m4v"}


VIDEO_EXTENSIONS |= {".mpg", ".mpeg", ".ts", ".m2ts", ".3gp", ".ogv"}   # v3.58


_VIDEO_MIME = {".mkv": "video/x-matroska", ".ts": "video/mp2t", ".m2ts": "video/mp2t",
               ".ogv": "video/ogg", ".mpg": "video/mpeg", ".mpeg": "video/mpeg",
               ".3gp": "video/3gpp", ".webm": "video/webm", ".mov": "video/quicktime",
               ".m4v": "video/x-m4v", ".mp4": "video/mp4", ".avi": "video/x-msvideo",
               ".wmv": "video/x-ms-wmv", ".flv": "video/x-flv"}


try:   # v3.58: optional HEIC/HEIF (pillow-heif)
    from pillow_heif import register_heif_opener
    register_heif_opener()
    IMAGE_EXTENSIONS |= {".heic", ".heif"}
    print("  \U0001f5bc pillow-heif found \u2014 HEIC/HEIF support enabled")
except ImportError:
    pass


MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


GIF_EXTENSIONS = {".gif"}


def detect_media_type(filepath):
    """Detect media type: 'image', 'gif', or 'video'."""
    ext = Path(filepath).suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in GIF_EXTENSIONS:
        return "gif"
    if ext == ".webp" and HAS_PILLOW:
        try:
            with Image.open(filepath) as img:
                if getattr(img, 'n_frames', 1) > 1:
                    return "gif"
        except:
            pass
    return "image"


STRIPPABLE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}


_SD_FIELD_MAP = {
    "steps": "steps", "sampler": "sampler",
    "schedule type": "scheduler", "scheduler": "scheduler",
    "cfg scale": "cfg_scale", "seed": "seed", "size": "size",
    "model": "model", "model hash": "model_hash",
    "vae": "vae", "vae hash": "vae_hash",
    "clip skip": "clip_skip", "denoising strength": "denoising",
    "hires upscaler": "hires_upscaler", "hires steps": "hires_steps",
    "hires upscale": "hires_upscale", "hires resize": "hires_resize",
    "hires cfg scale": "hires_cfg", "hires checkpoint": "hires_checkpoint",
    "hires sampler": "hires_sampler",
}


_SD_PARAM_RE = re.compile(r'\s*([\w \-/()]+?):\s*("(?:\\.|[^\\"])*"|[^,]*)\s*(?:,|$)')


_XMP_MAP = {
    "{http://purl.org/dc/elements/1.1/}creator": "artist",
    "{http://purl.org/dc/elements/1.1/}title": "title",
    "{http://purl.org/dc/elements/1.1/}description": "description",
    "{http://purl.org/dc/elements/1.1/}rights": "copyright",
    "{http://purl.org/dc/elements/1.1/}subject": "keywords",
    # v4.56: ExifTool writes a plain semicolon-separated string here rather than
    # an rdf:Seq, and sidecars produced by downloaders use it instead of
    # dc:subject. Without this line their keywords were read as nothing at all.
    "{http://ns.adobe.com/pdf/1.3/}Keywords": "keywords",
    "{http://ns.adobe.com/xap/1.0/mm/}PreservedFileName": "original_filename",
    "{http://ns.adobe.com/photoshop/1.0/}DateCreated": "date_created",
    "{http://ns.adobe.com/xap/1.0/}CreateDate": "date_created",
    "{http://ns.adobe.com/exif/1.0/}DateTimeOriginal": "date_created",   # v4.56
}


_IPTC_MAP = {5: "title", 25: "keywords", 80: "artist", 116: "copyright",
             120: "description", 55: "date_created"}


FIXABLE_COLOR_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


_CPU_COUNT = os.cpu_count() or 4          # logical processors (only value Python exposes w/o extra deps)


_MAX_WORKERS = _CPU_COUNT                 # hard ceiling for the backend


_AUTO_SHARE = 0.85                        # v4.14: what "Auto" claims of the machine


_AUTO_WORKERS = max(1, min(_CPU_COUNT, max(2, int(round(_CPU_COUNT * _AUTO_SHARE)))))


_DEFAULT_WORKERS = _AUTO_WORKERS


_CLAIM_PAGE = 256


TAGGER_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "wd-eva02-large-tagger-v3")


_TAG_MODEL_FILES = {
    "model.onnx": "https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3/resolve/main/model.onnx",
    "selected_tags.csv": "https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3/resolve/main/selected_tags.csv",
}


_RT_EXPECTED = {"gpu": 2500 * 1024 * 1024, "dml": 30 * 1024 * 1024,
                "cpu": 15 * 1024 * 1024}


NET_DEFAULT_PW = "1234"


_NET_LOCK_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TrackImage</title><style>
*{box-sizing:border-box}
body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
 background:#111214;color:#e8e6e3;font-family:system-ui,-apple-system,'Segoe UI',sans-serif}
.box{width:min(360px,90vw);padding:30px 26px;background:#191a1d;border:1px solid #2a2c30;
 border-radius:14px;text-align:center}
.logo{font-size:26px;color:#d4a017;margin-bottom:4px}
h1{font-size:17px;font-weight:600;margin:0 0 6px}
p{font-size:13px;color:#9a9a9a;margin:0 0 18px;line-height:1.5}
input{width:100%;padding:11px 13px;font-size:17px;text-align:center;letter-spacing:3px;
 background:#111214;border:1px solid #2a2c30;border-radius:8px;color:#e8e6e3;outline:none}
input:focus{border-color:#d4a017}
button{width:100%;margin-top:11px;padding:11px;font-size:14px;font-weight:600;cursor:pointer;
 background:#d4a017;border:0;border-radius:8px;color:#111214}
button:disabled{opacity:.55;cursor:default}
.err{margin-top:11px;font-size:13px;color:#e05252;min-height:18px}
</style></head><body><div class="box">
<div class="logo">&#9672;</div><h1>TrackImage</h1>
<p>This library is shared on the local network. Enter the password to continue.</p>
<input id="pw" type="password" inputmode="numeric" autocomplete="current-password"
       placeholder="Password" autofocus>
<button id="go">Unlock</button><div class="err" id="err"></div>
</div><script>
var pw=document.getElementById('pw'),go=document.getElementById('go'),err=document.getElementById('err');
function unlock(){
 if(!pw.value){pw.focus();return;}
 go.disabled=true;err.textContent='';
 fetch('/api/net/unlock',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({password:pw.value})})
  .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})
  .then(function(res){
    if(res.ok&&res.j.ok){location.reload();return;}
    err.textContent=res.j.error||'Wrong password';go.disabled=false;pw.select();})
  .catch(function(){err.textContent='Could not reach TrackImage';go.disabled=false;});
}
go.addEventListener('click',unlock);
pw.addEventListener('keydown',function(e){if(e.key==='Enter')unlock();});
</script></body></html>"""


_NET_SESSION_TTL = 15 * 60


_VPN_HINTS = ("vpn", "proton", "mullvad", "wireguard", "wg", "nord", "surfshark",
              "express", "openvpn", "tap-windows", "tap adapter", "tun", "tailscale",
              "zerotier", "hamachi", "radmin", "hyper-v", "vethernet", "virtualbox",
              "vmware", "docker", "wsl", "loopback", "bluetooth")


_RT_UNITS = {"kB": 1024, "MB": 1024 * 1024, "GB": 1024 * 1024 * 1024}


_TAG_DEFAULTS = {"enabled": True, "gen": 0.30, "char": 0.70, "workers": 0}   # v3.58: 0 = Auto (max)


_TAG_CATEGORY = {0: "general", 4: "character", 9: "rating"}


_RT_UNKNOWN, _RT_OK, _RT_BROKEN, _RT_ABSENT, _RT_SWAPPING = (
    "unknown", "ok", "broken", "absent", "swapping")


_SKIP_DIR_NAMES = {
    ".trash", "$recycle.bin", "system volume information", "$windows.~ws",
    "$windows.~bt", ".git", ".svn", "__pycache__", "node_modules",
    ".thumbnails", ".cache", "lost+found", ".spotlight-v100", ".fseventsd",
    ".temporaryitems", ".trashes",
}


PICKER_TIMEOUT = 60      # v4.47: two dialogs at 300s each blocked a request


_SWEEP_MAX_SHARE = 0.20


IGNORED_TAGS_FILE = os.path.join(USERDATA_DIR, "ignored_tags.txt")


VIDEO_THUMB_SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200"><rect width="200" height="200" fill="#16161c"/><polygon points="80,60 80,140 140,100" fill="#d4a017" opacity="0.7"/><rect x="40" y="155" width="120" height="20" rx="4" fill="#2a2a35"/><text x="100" y="169" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#8888a0">VIDEO</text></svg>'


MAX_DUP_DIST = 128  # 50% — full range, no faking


_MEM_PAIR_MIN_THR = 64   # compute at least this far so slider moves reuse the cache


REQUIRED_ASSETS = [
    "launcher_check.py",
    "Static/index.html",
    "Static/trackimage.png", "Static/trackimage.ico",
    "Static/fonts/dm-sans-300.ttf", "Static/fonts/dm-sans-400.ttf",
    "Static/fonts/dm-sans-500.ttf", "Static/fonts/dm-sans-600.ttf",
    "Static/fonts/dm-sans-700.ttf",
    "Static/fonts/space-mono-400.ttf", "Static/fonts/space-mono-700.ttf",
    # v4.50: the page is a shell; without these it renders and does nothing
    "Static/css/app.css",
    "Static/js/01-state.js",
    "Static/js/02-util.js",
    "Static/js/03-api.js",
    "Static/js/04-render.js",
    "Static/js/05-gallery.js",
    "Static/js/06-detail.js",
    "Static/js/07-folders.js",
    "Static/js/08-tags.js",
    "Static/js/09-duplicates.js",
    "Static/js/10-import.js",
    "Static/js/11-settings.js",
    "Static/js/12-modals.js",
    "Static/js/13-startup.js",
]


_BENCH_KEY = "runtime_benchmark"        # v4.29: cached {provider: seconds/image}


# see the note in the header: these must exist either way
globals().setdefault("FileSystemEventHandler", None)
globals().setdefault("Image", None)
globals().setdefault("Observer", None)
globals().setdefault("_webview", None)
globals().setdefault("imageio_ffmpeg", None)
globals().setdefault("np", None)
globals().setdefault("register_heif_opener", None)
globals().setdefault("send2trash", None)
