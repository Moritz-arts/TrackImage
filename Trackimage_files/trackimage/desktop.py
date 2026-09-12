"""The application window, and main().

Layer 27 of 27 -- see trackimage/__init__.py for the order these load in."""
import logging.handlers
import os
import subprocess
import sys
import threading
import time as _time
from . import state
from .config import FFMPEG_BIN, HAS_PHASH, HAS_SEND2TRASH, HAS_WATCHDOG, HAS_WEBVIEW, NET_DEFAULT_PW, STATIC_DIR, VERSION, _MAX_WORKERS, _MEM_PAIR_MIN_THR, _webview, app
from .logging_setup import _install_crash_logging, _setup_logging, log
from .platform_bits import _apply_window_icon, _boost_process_priority, _front_existing_window, _log_system_info, _no_window, _port_owner
from .db import _cleanup_trash, _start_trash_janitor, get_db
from .events import _shutdown_now
from .thumbnails import _thumb_backfill_ensure_running
from .processing import _proc, _proc_ensure_running, _proc_load_settings
from .duplicates import _ensure_mem_pairs
from .scanning import _AUTOSYNC, _autosync_load, _purge_own_folder_rows, _scan_orphans_async, _sweep_orphan_images, start_watcher
from .network import _lan_ips, _net_cfg, _serve_on
from .runtime import _replay_install_log, _run_pending_runtime_install, check_assets, check_venv
from .importing import _bind_native_drop, native_drag_available
from .api_tags import _load_ignore_file


state._UI_WINDOW = None          # v4.25: the live pywebview window, for the mode switch


state._UI_HANDOVER = False       # set while switching, so closing must not kill the app



def main():
    _setup_logging()
    _install_crash_logging()
    # v4.64: clear whatever an earlier layout left beside the launchers. It
    # belongs here rather than in the update helper: that helper comes from the
    # version being replaced, so it only ever knows the names the PREVIOUS
    # version knew, and a newly dropped file would linger for one update longer
    # than it should.
    try:
        from .updater import tidy_installation
        tidy_installation()
    except Exception:
        pass
    # v4.02: a second start must never fight the first one for port 5001. Until now
    # it crashed on bind, which the launcher then reported as "Server crashed!"
    # while the running instance was perfectly fine. Hand the user over to the
    # instance that is already there and leave quietly instead.
    import socket as _sock0
    try:
        with _sock0.create_connection(("127.0.0.1", 5001), timeout=0.6):
            _busy = True
    except OSError:
        _busy = False
    if _busy:
        # v4.05: give the user a window here too. Clicking the launcher while an
        # older instance is still alive used to open a browser tab at best, which
        # looks exactly like "nothing happened".
        log("TrackImage is already running")
        # v4.24: bring the window that already exists to the front rather than
        # opening a second one onto the same instance. Two windows on one program
        # was never the intention, and each one starts its own browser engine --
        # which is a thing to avoid, not to do twice.
        if os.name == "nt" and _front_existing_window(f"TrackImage v{VERSION}"):
            log("Brought the running window to the front")
            sys.exit(0)
        # v4.26: no window was found, so something is listening on 5001 that the
        # user cannot see -- a previous run that did not get all the way out, or
        # another program on the port. Until now this branch opened a browser tab
        # at best and exited without a word at worst, so starting TrackImage a
        # second time simply appeared to do nothing at all. Say what is going on.
        _who = _port_owner(5001)
        log("Port 5001 is in use but no TrackImage window was found" +
            (" (PID %s: %s)" % _who if _who else ""), "warning")
        print("")
        print("  TrackImage seems to be running already, but it has no window.")
        if _who:
            print("  Port 5001 is held by PID %s (%s)." % _who)
        print("")
        print("  Close that process and start TrackImage again:")
        print("")
        if os.name == "nt":
            print("      taskkill /PID %s /F" % (_who[0] if _who else "<pid>"))
        else:
            print("      kill %s" % (_who[0] if _who else "<pid>"))
        print("")
        print("  Opening a browser onto the instance that is there, in case it still works.")
        print("")
        try:
            import webbrowser as _wb
            _wb.open("http://localhost:5001")
        except Exception:
            pass
        sys.exit(3)
    log("=" * 60)
    log(f"TrackImage v{VERSION} starting up")
    _log_system_info()
    log("=" * 60)

    # v4.54: the log jumped from "everything is ready" straight to "the window is
    # up" with six seconds of silence in between, and no way to tell what had
    # spent them. Each stage says how long it took now, so the next slow start
    # answers itself instead of being guessed at.
    _t_boot = _time.time()
    _t_mark = [_t_boot]

    def _stage(what):
        now = _time.time()
        took = now - _t_mark[0]
        _t_mark[0] = now
        if took >= 0.25:
            log(f"  {what} took {took:.1f}s", "info")

    with app.app_context():
        _load_ignore_file()
        _purge_own_folder_rows()   # v4.44: before anything reads the library
        _cleanup_trash()
        _sweep_orphan_images()   # v3.87: before the watcher or the processor start
        # v4.28: earliest safe moment -- the database is open, nothing has
        # imported onnxruntime yet, so pip can replace every file cleanly.
        _run_pending_runtime_install()
    _stage("opening the database and tidying up")
    _scan_orphans_async()        # v4.26: report-only, off the startup path
    try:
        subprocess.run([FFMPEG_BIN, "-version"], **_no_window({"capture_output": True, "timeout": 5}))
        log("ffmpeg found — video thumbnails enabled")
    except: log("ffmpeg not found — video thumbnails will use a placeholder", "warning")
    _replay_install_log()               # v4.22: what setup did, before this log starts
    check_assets()                      # v4.13: say it when fonts or icons are missing
    check_venv()                        # v4.14: name a package that did not install cleanly
    if os.name == "nt":
        if native_drag_available():
            log("pywin32 found — files can be dragged out of the app window")
        else:
            log("pywin32 not installed (pip install pywin32) — dragging out of the app "
                "window falls back to the clipboard", "warning")
    if HAS_WATCHDOG:
        log("watchdog found — auto-sync enabled"); start_watcher()
    else:
        log("watchdog not installed (pip install watchdog) — auto-sync disabled", "warning")
    if HAS_PHASH:
        log("pHash engine ready (in-house numpy DCT) — duplicate detection enabled")
    else:
        log("numpy not installed (pip install numpy) — duplicate detection disabled", "warning")
    if HAS_SEND2TRASH:
        log("send2trash found — deleted files go to Recycle Bin after 10 min")
    else:
        log("send2trash not installed — deleted files stay in internal trash", "warning")
    _proc_load_settings()
    _boost_process_priority()
    _start_trash_janitor()
    log(f"Processing pool ready — {_proc['workers']}/{_MAX_WORKERS} parallel threads (auto={'on' if _proc['auto'] else 'off'})")
    if _proc["auto"]:
        _proc_ensure_running(reset_progress=True)
    if HAS_PHASH:
        log("Duplicate engine: on-demand RAM pairs (numpy-accelerated)")   # v3.66: no background pairing
    _autosync_load()   # v3.61
    log(f"Autosync {'ON' if _AUTOSYNC['on'] else 'OFF'} \u2014 watcher, auto-processing and auto-tagging follow this switch")
    # v4.26: _tag_ensure_running() asked whether onnxruntime was importable, and
    # answered by importing it -- right here on the way up. After a runtime swap
    # left the installation mixed, that import crashed the start itself, which is
    # why TrackImage could not be opened again afterwards. The probe reports from
    # its own thread and starts tagging then; until it does, the verdict is
    # "unknown" and tagging stays off.
    _stage("starting the engines")
    _thumb_backfill_ensure_running()   # v3.68: fill any missing thumbnails in the background
    _ensure_mem_pairs(_MEM_PAIR_MIN_THR)   # v3.71: pre-warm the duplicate pair cache at startup
    _stage("warming the duplicate cache")
    # v4.0: --browser forces the old behaviour even when pywebview is installed.
    # v4.25: the saved preference decides, unless --browser overrules it on the
    # command line. Set through Settings > Interface & Gallery.
    _ui_pref = ""
    try:
        with app.app_context():
            _r = get_db().execute("SELECT value FROM config WHERE key='ui_mode'").fetchone()
            if _r:
                _ui_pref = str(_r["value"])
    except Exception:
        pass
    _want_window = (HAS_WEBVIEW and "--browser" not in sys.argv
                    and _ui_pref != "browser")
    _stage("reading the saved interface mode")
    # v4.54: this asks the network for a machine called "trackimage" so the
    # browser can be sent to a friendlier address. There usually is no such
    # machine, and Windows works through DNS, then LLMNR, then NetBIOS before it
    # agrees -- several seconds, every single start. The answer is only ever used
    # for the address printed for a browser, so the window mode does not ask at
    # all, and when it does ask it gives up quickly.
    import socket as _sock
    _urlhost = "localhost"
    if not _want_window:
        _prev_timeout = _sock.getdefaulttimeout()
        try:
            _sock.setdefaulttimeout(0.3)
            if _sock.gethostbyname("trackimage").startswith("127."):
                _urlhost = "trackimage"
        except Exception:
            pass
        finally:
            try:
                _sock.setdefaulttimeout(_prev_timeout)
            except Exception:
                pass
        _stage("looking up the trackimage hostname")
    # v4.30: opening the port to the LAN is decided once, here, so the request
    # gate can trust a single flag instead of re-reading config on every call.
    _nc = _net_cfg()
    state._NET_ON = bool(_nc["enabled"])
    state._BIND_HOST = "0.0.0.0" if state._NET_ON else "127.0.0.1"
    if state._NET_ON:
        # v4.55: counting the network adapters took over a second of every start,
        # and the answer is only ever a line in the log -- the window connects to
        # 127.0.0.1 either way, and the settings page asks for the address when it
        # needs it. It is worked out alongside the rest of the start now and
        # reported when it arrives.
        def _announce_lan():
            try:
                _ips = _lan_ips()
                log("Network sharing is ON \u2014 reachable at %s"
                    % (", ".join("http://%s:5001" % i for i in _ips)
                       or "this machine's IP address"))
            except Exception as e:
                log("Network sharing is ON, but the address could not be worked "
                    "out (%s)" % type(e).__name__, "warning")

        threading.Thread(target=_announce_lan, daemon=True,
                         name="lan-address").start()
        if _nc["password"] == NET_DEFAULT_PW:
            log("The network password is still the default (1234) \u2014 change it in "
                "Settings \u203a Network.", "warning")
    _stage("working out the network address")
    if _want_window:
        log(f"TrackImage v{VERSION} is running in its own window (closes when you close it)")
    else:
        log(f"TrackImage v{VERSION} is running — open http://{_urlhost}:5001 (closes when you close the tab)")
    log(f"  startup so far: {_time.time() - _t_boot:.1f}s")
    # Open the browser only once the server is actually accepting connections, so the
    # first page load never lands on a "connection failed" page. The launchers no longer
    # open it themselves (that raced ahead of Flask binding the port).
    def _open_browser_when_ready(url, port):
        import webbrowser
        for _ in range(120):                     # up to ~60s
            try:
                with _sock.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                _time.sleep(0.5)
        try:
            webbrowser.open(url)
        except Exception:
            pass
        # v3.47: auto-minimize the terminal window once the browser is open (Windows only)
        if os.name == "nt":
            try:
                import ctypes
                hwnd = ctypes.windll.kernel32.GetConsoleWindow()
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
            except Exception:
                pass
    if not _want_window:
        threading.Thread(target=_open_browser_when_ready,
                         args=(f"http://{_urlhost}:5001", 5001), daemon=True).start()
    # v3.19: silence the high-frequency poller access logs (status + SSE) so the
    # console stays readable for real events; everything else still logs normally.
    class _PollLogFilter(logging.Filter):
        def filter(self, record):
            try:
                m = record.getMessage()
            except Exception:
                return True
            # v4.09: the console panel polls itself, so its own access log lines
            # were the loudest thing in it. Same for the other pure pollers --
            # they say nothing that the app's own messages do not say better.
            for _q in ("/api/processing/status", "/api/events", "/api/console",
                       "/api/scan-progress", "/api/hash-status", "/api/duplicates?"):
                if _q in m:
                    return False
            return True
    logging.getLogger("werkzeug").addFilter(_PollLogFilter())

    def _serve():
        # v4.32: the server now lives in a thread so the address can change while
        # TrackImage runs. This call blocks exactly as app.run() did.
        if not _serve_on(state._BIND_HOST):
            sys.exit(1)
        try:
            while True:
                _time.sleep(3600)
        except KeyboardInterrupt:
            pass

    if not _want_window:
        _serve()
    else:
        # The webview has to own the MAIN thread (a hard requirement on macOS and
        # the documented path on Windows), so Flask moves into a daemon thread.
        threading.Thread(target=_serve, daemon=True).start()
        # v4.55: the same sixty-second ceiling, asked twenty times a second
        # instead of twice. Flask binds the port when it binds it; half a second
        # between attempts meant up to half a second of standing around after it
        # already had, and the log was reporting that wait as if it were Flask
        # being slow.
        for _ in range(1200):                      # wait for the port, as the browser path does
            try:
                with _sock.create_connection(("127.0.0.1", 5001), timeout=0.2):
                    break
            except OSError:
                _time.sleep(0.05)
        _stage("waiting for the web server to accept connections")
        # The tab counter has no meaning here -- closing the window IS the exit.
        state._auto_shutdown = False
        state.WINDOW_MODE = True
        _apply_window_icon(f"TrackImage v{VERSION}")
        # v4.25: the marker is what tells the page it is the app window. It used
        # to be decided on the server, so a browser tab pointed at the same
        # program was told it was the window -- and had its drag and drop
        # switched off in favour of a native drag that only exists in the window.
        _win = _webview.create_window(f"TrackImage v{VERSION}",
                                      f"http://127.0.0.1:5001/?ti_app=1",
                                      width=1600, height=1000, min_size=(900, 600),
                                      text_select=True)
        state._UI_WINDOW = _win     # v4.25: reachable from the mode switch
        _stage("building the window")
        # v4.41: pywebview sees the same drop from the Windows side, where the
        # real paths are. The DOM is only there once the page has loaded, so the
        # hook goes on the loaded event rather than here.
        def _bind_drop():
            try:
                _bind_native_drop(_win)
            except Exception as _e:
                log(f"Dropped files will be copied, not moved ({type(_e).__name__})", "warning")
        try:
            _win.events.loaded += _bind_drop
        except Exception:
            pass
        def _on_closed():
            # v4.25: when the window is closed BY the mode switch, the server has
            # to stay up -- the browser tab that was just opened is talking to it.
            if state._UI_HANDOVER:
                return
            try:
                _shutdown_now()
            except Exception:
                pass
            os._exit(0)
        try:
            _win.events.closed += _on_closed
        except Exception:
            pass
        try:
            # v4.05: the icon must never be able to stop the window from opening.
            # pywebview only accepts icon= on GTK/Qt and rejects it elsewhere --
            # v4.04 passed it everywhere and only caught TypeError, so on Windows
            # the ValueError escaped, the window never appeared and the whole
            # start fell through to the browser path. Cosmetics come last now.
            _icon = os.path.join(STATIC_DIR, "trackimage.png")
            _started = False
            if os.name != "nt" and sys.platform != "darwin" and os.path.exists(_icon):
                try:
                    _webview.start(icon=_icon)
                    _started = True
                except Exception:
                    _started = False                # nothing ran yet -- retry plain
            if not _started:
                _webview.start()
        except Exception as e:
            # No usable webview runtime after all -- fall back instead of dying.
            log(f"Window mode failed ({e}) — falling back to the browser", "warning")
            if sys.platform.startswith("linux"):
                log("Linux needs the GTK bindings of your distribution — pip cannot supply them: "
                    "apt install python3-gi gir1.2-webkit2-4.1 (Debian/Ubuntu), "
                    "dnf install python3-gobject webkit2gtk4.1 (Fedora), "
                    "pacman -S python-gobject webkit2gtk-4.1 (Arch)", "warning")
            elif sys.platform == "darwin":
                log("macOS uses the system WKWebView through pyobjc — reinstall pywebview "
                    "into the venv if this keeps failing", "warning")
            state._auto_shutdown = True
            try:
                import webbrowser; webbrowser.open(f"http://{_urlhost}:5001")
            except Exception:
                pass
            while True:
                _time.sleep(3600)
        os._exit(0)
