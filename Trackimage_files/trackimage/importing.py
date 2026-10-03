"""Files dropped in, dragged out, and moved into the library.

Layer 19 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from queue import Queue, Empty
import json
import os
import shutil
import subprocess
import sys
import threading
import time as _time
import urllib.parse
import urllib.request
from . import state
from .config import Image, MEDIA_EXTENSIONS
from .logging_setup import log
from .platform_bits import _no_window
from .db import _get_thread_db, get_db
from .events import sse_notify
from .hashing import _phash16, _sim_pct
from .duplicates import _popcount_func


def _report_import_dupes(db, new_ids, display):
    """v4.41: shared by both import routes -- the upload path and the move
    path report matches identically, so a file behaves the same however it
    arrived. Lifted out of api_import_files unchanged."""
    # D1: look for matches now that the files are here. The pHash is computed on
    # the spot for these few rather than waiting for the pool, so the answer
    # arrives with the import instead of minutes later.
    dupes = []
    if new_ids:
        # Every hash the library already holds, read once. Comparing in memory
        # keeps a drop onto a 20,000-image library instant; a query per pair
        # would not.
        pool = []
        _pc = _popcount_func()      # not a global; it is built where it is needed
        for r in db.execute("SELECT id, filename, folder, phash FROM images "
                            "WHERE phash IS NOT NULL AND phash != ''"):
            try:
                pool.append((int(r["phash"], 16), r["id"], r["filename"], r["folder"]))
            except Exception:
                pass
    for iid in new_ids:
        row = db.execute("SELECT filepath, filename FROM images WHERE id=?", (iid,)).fetchone()
        if not row:
            continue
        try:
            with Image.open(row["filepath"]) as im:
                from PIL import ImageOps as _IO
                ph = _phash16(_IO.exif_transpose(im))
            db.execute("UPDATE images SET phash=? WHERE id=?", (ph, iid))
            q = int(ph, 16)
            for val, oid, oname, ofolder in pool:
                if oid == iid:
                    continue
                d = _pc(q ^ val)
                if d <= 13:                       # the default "same picture" threshold
                    dupes.append({"imported": row["filename"], "match": oname,
                                  "folder": ofolder,
                                  "similarity": _sim_pct(d)})
                    break
            # so that two identical files dropped together find each other too
            pool.append((q, iid, row["filename"], display))
        except Exception as e:
            # The worker pool will hash this properly in a moment either way, so
            # the import still stands -- but say so rather than swallowing it.
            # A bare pass here hid a NameError through a whole round of testing.
            log(f"Could not check {row['filename']} against the library right away: "
                f"{type(e).__name__}", "warning")
    return dupes


_native_drop = {"ts": 0.0, "files": []}


_native_drop_lock = threading.Lock()


state.NATIVE_DROP_OK = False          # set once the DOM hook is actually bound


_native_claims = {}       # token -> (time, files): drops claimed, not yet imported


def _claim_native(files):
    """Keep the real paths of a drop under a token the page hands back when it
    imports -- which, queued, may be minutes later. Call with _native_drop_lock
    NOT held."""
    token = os.urandom(8).hex()
    with _native_drop_lock:
        now = _time.time()
        for k in [k for k, v in _native_claims.items() if now - v[0] > 3600]:
            del _native_claims[k]
        _native_claims[token] = (now, list(files))
    return token


def _record_native_drop(event):
    """pywebview's drop handler. Runs on the GUI side, off the request path --
    it only writes down what was dropped and lets the page come and ask."""
    try:
        files = ((event or {}).get("dataTransfer") or {}).get("files") or []
        seen = []
        for f in files:
            path = (f or {}).get("pywebviewFullPath") or ""
            name = (f or {}).get("name") or (os.path.basename(path) if path else "")
            if path and name:
                seen.append({"name": name, "path": path})
        if not seen:
            return
        with _native_drop_lock:
            _native_drop["ts"] = _time.time()
            _native_drop["files"] = seen
    except Exception as e:
        log(f"Could not read the dropped paths: {type(e).__name__}", "warning")


def _bind_native_drop(window):
    """Subscribe to the drop event on the document. Everything here is optional:
    an older pywebview simply has no dom attribute and the import keeps working
    the way it did, one copy at a time."""
    try:
        from webview.dom import DOMEventHandler
    except Exception:
        log("This pywebview cannot report where a dropped file came from — "
            "dropped files will be copied, not moved. Upgrade pywebview to 5 or "
            "newer for moves.", "warning")
        return
    try:
        # Neither flag is set: the page must still receive its own drop event,
        # and preventing the default here would take it away.
        window.dom.document.events.drop += DOMEventHandler(_record_native_drop, False, False)
        state.NATIVE_DROP_OK = True
        log("Dropped files will be moved into the library, not copied.", "info")
    except Exception as e:
        log(f"Could not listen for dropped paths ({type(e).__name__}) — dropped "
            f"files will be copied instead of moved.", "warning")


_REAL_BROWSER_OPEN = None
_routed_recently = {}         # uri -> time, so one drop is never imported twice
_routed_lock = threading.Lock()


def _own_or_intended(url):
    """True only for an address TrackImage opens on purpose: its own start page
    (opening the browser, switching modes) and the project's pages on GitHub
    (the "Open on GitHub" link in Settings). Everything else that wants a
    browser while the window is open is a drop -- including a picture on
    another local port or a TrackImage /file/ address, which the import itself
    recognises. Anything that cannot be read fails closed."""
    try:
        p = urllib.parse.urlsplit(str(url))
        host, port = (p.hostname or "").lower(), p.port
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    if port == 5001 and p.path in ("", "/"):
        return True
    if host == "github.com":
        from .updater import GITHUB_OWNER, GITHUB_REPO   # a layer above: at run time
        return p.path.lower().startswith(("/%s/%s/" % (GITHUB_OWNER, GITHUB_REPO)).lower())
    return False


def _guard_browser_opens():
    """A drop can never open the default browser.

    When a drop is not taken by the page, Chromium opens what it carries as a
    new tab; WebView2 reports that as a new-window request and pywebview hands
    it to webbrowser.open -- which is how pictures dragged out of Firefox ended
    up in a new Firefox window instead of TrackImage. The page cannot rule it
    out: if the drop is released before the page's "I take this" has reached
    the browser process, Chromium takes the default action regardless, and a
    window that is not in front -- Firefox writing the picture to a temp file
    while it enters -- makes that race easy to lose.

    Every pywebview version and backend opens those through webbrowser.open,
    looked up at call time, so that one function is wrapped: while the app
    window is open, an address that is not TrackImage's own goes to the import
    queue instead. It runs on the GUI thread, so it only starts a thread."""
    global _REAL_BROWSER_OPEN
    import webbrowser
    if _REAL_BROWSER_OPEN is not None:
        return
    _REAL_BROWSER_OPEN = real = webbrowser.open

    def _open(url, new=0, autoraise=True):
        try:
            if state._UI_WINDOW is not None and not _own_or_intended(url):
                threading.Thread(target=_route_dropped_uri, args=(str(url),),
                                 daemon=True, name="dropped-uri").start()
                return True
        except Exception:
            pass
        return real(url, new, autoraise)

    webbrowser.open = _open
    webbrowser.open_new = lambda url: _open(url, 1)
    webbrowser.open_new_tab = lambda url: _open(url, 2)


def _route_dropped_uri(url):
    """Turn what a drop would have opened into an import the page queues. Every
    drop gets an answer on screen: one that silently did nothing would look
    exactly like the drop that never arrived."""
    now = _time.time()
    with _routed_lock:
        for k in [k for k, t in _routed_recently.items() if now - t > 3]:
            del _routed_recently[k]
        if url in _routed_recently:
            return
        _routed_recently[url] = now
    try:
        payload = _dropped_uri_payload(url)
    except Exception as e:
        log(f"Could not read a dropped item ({type(e).__name__}: {e})", "warning")
        payload = {"error": "That drop could not be added"}
    log(f"A drop the page did not take was caught before it reached the browser: "
        f"{url[:120]}", "info")
    win = state._UI_WINDOW
    js = "window.tiExternalDrop&&tiExternalDrop(%s)" % json.dumps(payload)
    try:
        # From this thread, never the GUI thread: evaluate_js waits for the GUI
        # thread to run it, and the handler that called us IS the GUI thread.
        win.evaluate_js(js)
    except Exception as e:
        log(f"Could not hand a drop to the window ({type(e).__name__}) \u2014 "
            f"trying the event stream", "warning")
        sse_notify("external_drop", payload)


def _dropped_uri_payload(url):
    """What the page is told about one caught drop."""
    p = urllib.parse.urlsplit(url)
    if p.scheme in ("http", "https"):
        return {"url": url}
    if p.scheme != "file":
        return {"error": "That picture could not be taken over \u2014 save it first, "
                         "then drag the file in"}
    path = urllib.request.url2pathname(p.path)
    if p.netloc and p.netloc.lower() != "localhost":
        path = "\\\\" + p.netloc + path                # \\server\share\...
    name = os.path.basename(path.rstrip("\\/")) or path
    if not os.path.isfile(path):
        return {"error": f"{name} is a folder or no longer there \u2014 drag the "
                         f"pictures themselves"}
    if os.path.splitext(path)[1].lower() not in MEDIA_EXTENSIONS:
        return {"error": f"{name} is not an image or video TrackImage handles"}
    db = _get_thread_db()
    try:
        known = _library_row_for_path(db, path)
    finally:
        db.close()
    if known:
        # One of the library's own files coming back from a drag that left the
        # window. Adding it would copy it in twice, and the guard cannot tell a
        # drag out and back from a deliberate move -- so it stays where it is.
        return {"error": f"{name} is already in the library"}
    return {"token": _claim_native([{"name": name, "path": path}]), "names": [name]}


def _library_row_for_path(db, path):
    """The images row for a file already in the library, or None.

    Windows compares paths without case; a file dragged in from Explorer can
    easily carry a different capitalisation than the scan wrote down.
    """
    try:
        ap = os.path.abspath(path)
    except Exception:
        return None
    row = db.execute("SELECT id, filename, folder, filepath FROM images WHERE filepath=?",
                     (ap,)).fetchone()
    if row or os.name != "nt":
        return row
    low = ap.lower()
    for r in db.execute("SELECT id, filename, folder, filepath FROM images "
                        "WHERE filename=? COLLATE NOCASE", (os.path.basename(ap),)):
        if (r["filepath"] or "").lower() == low:
            return r
    return None


def _dropfiles_blob(paths):
    """The CF_HDROP payload: a 20-byte DROPFILES header followed by the paths as
    UTF-16LE, each NUL-terminated, the list closed by one more NUL. Kept separate
    from the Win32 calls so it can be verified without Windows."""
    import struct
    head = struct.pack("<IiiII", 20, 0, 0, 0, 1)   # pFiles, x, y, fNC, fWide=TRUE
    body = ("\0".join(paths) + "\0\0").encode("utf-16-le")
    return head + body


def _win_clip_api():
    """v4.11: declare every signature before calling.

    Without argtypes/restype ctypes marshals arguments as 32-bit int. On 64-bit
    Windows GlobalAlloc hands back a 64-bit handle, and passing that truncated to
    GlobalLock/SetClipboardData makes the call fail -- silently, because the
    truncated value can still look like a valid pointer. v4.10 set two restypes
    and no argtypes at all, which is exactly why copying did nothing."""
    import ctypes
    from ctypes import wintypes as w
    # use_last_error makes ctypes.get_last_error() meaningful for these calls
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    HANDLE, SIZE_T = ctypes.c_void_p, ctypes.c_size_t
    k32.GlobalAlloc.argtypes = [w.UINT, SIZE_T];      k32.GlobalAlloc.restype = HANDLE
    k32.GlobalLock.argtypes = [HANDLE];               k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalUnlock.argtypes = [HANDLE];             k32.GlobalUnlock.restype = w.BOOL
    k32.GlobalFree.argtypes = [HANDLE];               k32.GlobalFree.restype = HANDLE
    u32.OpenClipboard.argtypes = [w.HWND];            u32.OpenClipboard.restype = w.BOOL
    u32.EmptyClipboard.argtypes = [];                 u32.EmptyClipboard.restype = w.BOOL
    u32.CloseClipboard.argtypes = [];                 u32.CloseClipboard.restype = w.BOOL
    u32.SetClipboardData.argtypes = [w.UINT, HANDLE]; u32.SetClipboardData.restype = HANDLE
    u32.RegisterClipboardFormatW.argtypes = [w.LPCWSTR]
    u32.RegisterClipboardFormatW.restype = w.UINT
    u32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
    u32.CreateWindowExW.restype = w.HWND
    u32.DestroyWindow.argtypes = [w.HWND];            u32.DestroyWindow.restype = w.BOOL
    return k32, u32


def _clip_owner_window(u32):
    """v4.12: the clipboard needs a real owner. Windows documents that opening it
    with a NULL window handle sets the owner to NULL and makes SetClipboardData
    fail -- which is why copying a file never worked in the app window. A
    message-only window (HWND_MESSAGE as the parent) is invisible, has no z-order
    and costs nothing, and it is a perfectly valid owner. It is created on the
    thread that sets the clipboard, because window handles are thread-affine.
    Returns None when creation fails; the caller then falls back to NULL so a
    clipboard is never the reason a request dies."""
    import ctypes
    from ctypes import wintypes as w
    HWND_MESSAGE = w.HWND(-3)
    try:
        hwnd = u32.CreateWindowExW(0, "STATIC", "TrackImageClipboardOwner", 0,
                                   0, 0, 0, 0, HWND_MESSAGE, None, None, None)
        return hwnd or None
    except Exception:
        return None


def _clip_win_set(fmt, blob):
    """Hand one clipboard format over. The memory belongs to the system once
    SetClipboardData succeeded, so it must not be freed on that path."""
    import ctypes
    k32, u32 = _win_clip_api()
    GMEM_MOVEABLE = 0x0002
    h = k32.GlobalAlloc(GMEM_MOVEABLE, len(blob))
    if not h:
        raise OSError(f"GlobalAlloc failed ({ctypes.get_last_error()})")
    p = k32.GlobalLock(h)
    if not p:
        k32.GlobalFree(h); raise OSError(f"GlobalLock failed ({ctypes.get_last_error()})")
    ctypes.memmove(p, blob, len(blob))
    k32.GlobalUnlock(h)
    if not u32.SetClipboardData(fmt, h):
        err = ctypes.get_last_error()
        k32.GlobalFree(h)
        raise OSError(f"SetClipboardData(format {fmt}) failed ({err})")


def _clip_win_files(paths):
    import ctypes
    CF_HDROP, DROPEFFECT_COPY = 15, 1
    _clip_win_set(CF_HDROP, _dropfiles_blob(paths))
    # Without this Explorer may treat the paste as a MOVE and take the originals away.
    _k32, u32 = _win_clip_api()
    fmt = u32.RegisterClipboardFormatW("Preferred DropEffect")
    if fmt:
        try:
            _clip_win_set(fmt, bytes(ctypes.c_uint32(DROPEFFECT_COPY)))
        except OSError:
            pass


def _clip_win_image(path):
    import io
    CF_DIB = 8
    with Image.open(path) as im:
        im = im.convert("RGB")
        buf = io.BytesIO(); im.save(buf, "BMP")
    _clip_win_set(CF_DIB, buf.getvalue()[14:])   # a DIB is a BMP minus its 14-byte file header


state._drag_q = None


state._drag_thread = None


state._drag_last_error = ""


class _DropSource:
    """The smallest IDropSource that behaves correctly: end the drag when the left
    button comes up, cancel on Escape, and let Windows draw the cursor."""
    _public_methods_ = ["QueryContinueDrag", "GiveFeedback"]
    _com_interfaces_ = None      # filled in at import time, see _drag_worker

    def QueryContinueDrag(self, fEscapePressed, grfKeyState):
        import winerror
        if fEscapePressed:
            return winerror.DRAGDROP_S_CANCEL
        if not (grfKeyState & 0x0001):          # MK_LBUTTON released -> drop
            return winerror.DRAGDROP_S_DROP
        return 0                                 # S_OK: keep going

    def GiveFeedback(self, dwEffect):
        import winerror
        return winerror.DRAGDROP_S_USEDEFAULTCURSORS


def _drag_worker():
    """One long-lived apartment-threaded worker. OLE is initialised once; every
    drag is modal, so they are run one after another off a queue."""
    import pythoncom, win32com.server.util, ctypes
    from ctypes import wintypes as w
    pythoncom.OleInitialize()
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    u32.AttachThreadInput.argtypes = [w.DWORD, w.DWORD, w.BOOL]
    u32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
    u32.GetWindowThreadProcessId.restype = w.DWORD
    u32.GetForegroundWindow.restype = w.HWND
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _DropSource._com_interfaces_ = [pythoncom.IID_IDropSource]
    while True:
        paths = state._drag_q.get()
        if paths is None:
            break
        try:
            ok, msg = _clipboard_put(paths, "file")     # builds the CF_HDROP
            if not ok:
                state._drag_last_error = msg or "clipboard"
                continue
            # v4.40: the handover is decided a few milliseconds before this runs.
            # If the button came up in between there is no gesture left, and
            # starting one anyway would drop the files wherever the cursor
            # happens to sit. The files are on the clipboard either way.
            u32.GetAsyncKeyState.argtypes = [ctypes.c_int]
            u32.GetAsyncKeyState.restype = ctypes.c_short
            if not (u32.GetAsyncKeyState(0x01) & 0x8000):      # VK_LBUTTON
                state._drag_last_error = "button released"
                continue
            data_obj = pythoncom.OleGetClipboard()
            src = win32com.server.util.wrap(_DropSource(), pythoncom.IID_IDropSource)
            gui_tid = u32.GetWindowThreadProcessId(u32.GetForegroundWindow(), None)
            our_tid = k32.GetCurrentThreadId()
            attached = bool(gui_tid) and bool(u32.AttachThreadInput(our_tid, gui_tid, True))
            try:
                DROPEFFECT_COPY = 1
                pythoncom.DoDragDrop(data_obj, src, DROPEFFECT_COPY)
            finally:
                if attached:
                    u32.AttachThreadInput(our_tid, gui_tid, False)
            state._drag_last_error = ""
        except Exception as e:
            # A cancelled drag raises too -- it is not worth a scene either way.
            state._drag_last_error = f"{type(e).__name__}: {e}"
        finally:
            try:
                state._drag_q.task_done()
            except Exception:
                pass


def native_drag_available():
    if os.name != "nt":
        return False
    try:
        import pythoncom, win32com.server.util, winerror   # noqa: F401
        return True
    except Exception:
        return False


def start_native_drag(paths):
    """Queue one drag. Returns straight away: the drag itself is modal and lives
    on the worker, so the request that started it must not wait for the drop."""
    if not native_drag_available():
        return False, "native drag needs pywin32 on Windows"
    if not paths:
        return False, "nothing to drag"
    if state._drag_q is None:
        state._drag_q = Queue()
    if state._drag_thread is None or not state._drag_thread.is_alive():
        state._drag_thread = threading.Thread(target=_drag_worker, daemon=True, name="native-drag")
        state._drag_thread.start()
    if state._drag_q.qsize() > 2:                    # a stuck drag must not pile up
        return False, "a drag is already running"
    state._drag_q.put(list(paths))
    return True, ""


def _clipboard_put(paths, mode):
    """Put files (mode='file') or one picture (mode='image') on the OS clipboard.
    Returns (ok, message). Never raises -- a clipboard is a convenience, not a
    reason to break a request."""
    if not paths:
        return False, "nothing to copy"
    try:
        if os.name == "nt":
            import ctypes
            _k32, u32 = _win_clip_api()
            owner = _clip_owner_window(u32)     # v4.12: a NULL owner makes SetClipboardData fail
            opened = False
            for _ in range(10):                 # another program may hold it for a moment
                if u32.OpenClipboard(owner):
                    opened = True; break
                _time.sleep(0.05)
            if not opened:
                if owner:
                    u32.DestroyWindow(owner)
                return False, f"clipboard is held by another program ({ctypes.get_last_error()})"
            try:
                u32.EmptyClipboard()
                if mode == "image":
                    _clip_win_image(paths[0])
                else:
                    _clip_win_files(paths)
            finally:
                u32.CloseClipboard()
                # The handles passed to SetClipboardData belong to the system now and
                # survive the window; the owner window has done its job.
                if owner:
                    u32.DestroyWindow(owner)
            return True, ""
        if sys.platform == "darwin":
            if mode == "image":
                scr = ('set the clipboard to (read (POSIX file "%s") as JPEG picture)'
                       % paths[0].replace('"', '\\"'))
            else:
                items = ", ".join('POSIX file "%s"' % p.replace('"', '\\"') for p in paths)
                scr = "set the clipboard to {%s}" % items
            r = subprocess.run(["osascript", "-e", scr], **_no_window({"capture_output": True, "timeout": 20}))
            return (r.returncode == 0), (r.stderr or b"").decode("utf-8", "replace")[:200]
        # Linux: whichever helper is installed
        for tool, img_args, uri_args in (
                ("wl-copy", ["wl-copy", "-t", "image/png"], ["wl-copy", "-t", "text/uri-list"]),
                ("xclip", ["xclip", "-selection", "clipboard", "-t", "image/png"],
                          ["xclip", "-selection", "clipboard", "-t", "text/uri-list"])):
            if not shutil.which(tool):
                continue
            if mode == "image":
                with open(paths[0], "rb") as f:
                    subprocess.run(img_args, input=f.read(), timeout=20)
            else:
                data = "\n".join("file://" + p for p in paths).encode("utf-8")
                subprocess.run(uri_args, input=data, timeout=20)
            return True, ""
        return False, "no clipboard helper found (install wl-clipboard or xclip)"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _clip_win_read():
    """What Explorer (or anything else) left on the clipboard: the file list of a
    copy or a cut, and whether a bare picture is there. The sequence number
    changes with every change of the clipboard, which is how the page tells its
    own copy apart from something copied elsewhere afterwards."""
    import ctypes
    from ctypes import wintypes as w
    k32, u32 = _win_clip_api()
    sh = ctypes.WinDLL("shell32", use_last_error=True)
    HANDLE = ctypes.c_void_p
    u32.GetClipboardData.argtypes = [w.UINT];            u32.GetClipboardData.restype = HANDLE
    u32.IsClipboardFormatAvailable.argtypes = [w.UINT];  u32.IsClipboardFormatAvailable.restype = w.BOOL
    u32.GetClipboardSequenceNumber.argtypes = [];        u32.GetClipboardSequenceNumber.restype = w.DWORD
    sh.DragQueryFileW.argtypes = [HANDLE, w.UINT, w.LPWSTR, w.UINT]; sh.DragQueryFileW.restype = w.UINT
    out = {"sig": "w%d" % u32.GetClipboardSequenceNumber(), "files": [], "move": False, "image": False}
    for _ in range(10):
        if u32.OpenClipboard(None):
            break
        _time.sleep(0.05)
    else:
        return out
    try:
        CF_HDROP, CF_BITMAP, CF_DIB, CF_DIBV5 = 15, 2, 8, 17
        png = u32.RegisterClipboardFormatW("PNG")
        out["image"] = any(u32.IsClipboardFormatAvailable(f) for f in (CF_DIB, CF_DIBV5, CF_BITMAP, png) if f)
        h = u32.GetClipboardData(CF_HDROP) if u32.IsClipboardFormatAvailable(CF_HDROP) else None
        if h:
            for i in range(min(sh.DragQueryFileW(h, 0xFFFFFFFF, None, 0), 2000)):
                n = sh.DragQueryFileW(h, i, None, 0)
                buf = ctypes.create_unicode_buffer(n + 1)
                sh.DragQueryFileW(h, i, buf, n + 1)
                if buf.value:
                    out["files"].append(buf.value)
        fmt = u32.RegisterClipboardFormatW("Preferred DropEffect")
        if fmt and u32.IsClipboardFormatAvailable(fmt):
            hd = u32.GetClipboardData(fmt)
            p = k32.GlobalLock(hd) if hd else None
            if p:
                eff = ctypes.c_uint32.from_address(p).value
                k32.GlobalUnlock(hd)
                out["move"] = bool(eff & 2) and not (eff & 1)      # a Cut in Explorer
    finally:
        u32.CloseClipboard()
    return out


def clipboard_read():
    """The OS clipboard as {sig, files, move, image}. Never raises; an empty
    answer only means nothing usable is there."""
    out = {"sig": "", "files": [], "move": False, "image": False}
    try:
        if os.name == "nt":
            return _clip_win_read()
        if sys.platform == "darwin":
            r = subprocess.run(["osascript", "-e",
                                'set o to ""\nrepeat with f in (the clipboard as \u00abclass furl\u00bb as list)\n'
                                'set o to o & POSIX path of f & linefeed\nend repeat\nreturn o'],
                               **_no_window({"capture_output": True, "timeout": 5}))
            out["files"] = [l for l in (r.stdout or b"").decode("utf-8", "replace").splitlines() if l]
            if not out["files"]:
                r = subprocess.run(["osascript", "-e", "clipboard info"],
                                   **_no_window({"capture_output": True, "timeout": 5}))
                out["image"] = b"PNGf" in (r.stdout or b"") or b"TIFF" in (r.stdout or b"")
        else:
            for types_cmd, get_cmd in (
                    (["wl-paste", "--list-types"], ["wl-paste", "--no-newline", "--type"]),
                    (["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"],
                     ["xclip", "-selection", "clipboard", "-o", "-t"])):
                if not shutil.which(types_cmd[0]):
                    continue
                t = subprocess.run(types_cmd, capture_output=True, timeout=5).stdout.decode("utf-8", "replace")
                if "text/uri-list" in t:
                    from urllib.parse import unquote, urlparse
                    raw = subprocess.run(get_cmd + ["text/uri-list"], capture_output=True, timeout=5).stdout
                    for line in raw.decode("utf-8", "replace").splitlines():
                        u = urlparse(line.strip())
                        if u.scheme == "file" and u.path:
                            out["files"].append(unquote(u.path))
                out["image"] = "image/png" in t
                break
        import zlib
        out["sig"] = "p%d" % zlib.crc32(("\n".join(out["files"]) + ("|img" if out["image"] else "")).encode("utf-8"))
    except Exception as e:
        log(f"Could not read the clipboard: {type(e).__name__}", "warning")
    return out


def clipboard_image_png():
    """A bare picture on the clipboard as PNG bytes, or None."""
    try:
        from PIL import ImageGrab
        import io
        im = ImageGrab.grabclipboard()
        if im is None or isinstance(im, list):
            return None
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()
    except Exception as e:
        log(f"Could not read the picture on the clipboard: {type(e).__name__}", "warning")
        return None


def _paths_for_ids(ids):
    """Disk paths for a list of image ids, kept in the order they were given --
    the order a drag or a paste presents them in."""
    db = get_db()
    ph = ",".join("?" * len(ids))
    rows = db.execute(f"SELECT id, filepath FROM images WHERE id IN ({ph})", ids).fetchall()
    order = {int(v): k for k, v in enumerate(ids)}
    return [r["filepath"] for r in sorted(rows, key=lambda r: order.get(r["id"], 0))
            if r["filepath"] and os.path.isfile(r["filepath"])]


_drag_watch = {"seq": 0, "paths": [], "handed": True}


_drag_watch_lock = threading.Lock()


def _drag_cursor_foreign():
    """True when the window under the cursor does not belong to this process.
    Any failure answers False: not handing over is always the safe direction --
    the drag simply stays inside TrackImage."""
    try:
        import ctypes
        from ctypes import wintypes as w

        class _PT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        u32 = ctypes.WinDLL("user32", use_last_error=True)
        u32.GetCursorPos.argtypes = [ctypes.POINTER(_PT)]
        u32.GetCursorPos.restype = w.BOOL
        u32.WindowFromPoint.argtypes = [_PT]          # POINT is passed BY VALUE
        u32.WindowFromPoint.restype = w.HWND
        u32.GetAncestor.argtypes = [w.HWND, w.UINT]
        u32.GetAncestor.restype = w.HWND
        u32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
        u32.GetWindowThreadProcessId.restype = w.DWORD
        pt = _PT()
        if not u32.GetCursorPos(ctypes.byref(pt)):
            return False
        hwnd = u32.WindowFromPoint(pt)
        if not hwnd:
            return True                                # bare desktop
        root = u32.GetAncestor(hwnd, 2) or hwnd        # GA_ROOT
        pid = w.DWORD(0)
        u32.GetWindowThreadProcessId(root, ctypes.byref(pid))
        if not pid.value:
            return False
        return pid.value != os.getpid()
    except Exception:
        return False


def _drag_handover(seq):
    """Start the Windows drag for an armed gesture. Runs once per gesture."""
    with _drag_watch_lock:
        if _drag_watch["handed"] or _drag_watch["seq"] != seq:
            return False, "not armed"
        _drag_watch["handed"] = True
        paths = list(_drag_watch["paths"])
    if not paths:
        sse_notify("drag_handover", {"ok": False, "error": "files not found"})
        return False, "files not found"
    ok, msg = start_native_drag(paths)
    # The page is holding a preview that Windows is about to draw over, so it is
    # told either way -- the mouse belongs to the shell from here and no mouseup
    # will ever reach the page to clean up after itself.
    sse_notify("drag_handover", {"ok": bool(ok), "error": msg, "count": len(paths)})
    if not ok:
        log("Drag out of the window failed: %s" % msg, "warning")
    return ok, msg


def _drag_watch_loop(seq):
    end = _time.time() + 45
    while _time.time() < end:
        with _drag_watch_lock:
            if _drag_watch["handed"] or _drag_watch["seq"] != seq:
                return
        if _drag_cursor_foreign():
            _drag_handover(seq)
            return
        _time.sleep(0.03)
