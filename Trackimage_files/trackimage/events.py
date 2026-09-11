"""Server-sent events, open tabs, and the idle shutdown timer.

Layer 7 of 27 -- see trackimage/__init__.py for the order these load in.
"""
import json
import os
import subprocess
import sys
import threading
import time as _time
from . import state
from .logging_setup import log
from .db import _cleanup_trash, _wal_checkpoint_now


sse_clients = []  # list of Queue objects, one per connected client


sse_lock = threading.Lock()


state._shutdown_timer = None


state._auto_shutdown = True


_active_tabs = set()  # track tab IDs


_tabs_lock = threading.Lock()


def sse_notify(event_type, data=None):
    """Push an SSE event to all connected clients."""
    msg = f"event: {event_type}\ndata: {json.dumps(data or {})}\n\n"
    dead = []
    with sse_lock:
        for q in sse_clients:
            try: q.put_nowait(msg)
            except: dead.append(q)
        for q in dead:
            sse_clients.remove(q)


def _shutdown_now(deadline=3.0, checkpoint_deadline=10.0):
    """v4.0: the same clean exit the tab watchdog performs, callable directly.
    The window mode uses it when the window is closed -- trash is flushed and the
    watcher stopped before the process goes, exactly as on the browser path.

    v4.26: bounded. _cleanup_trash() walks the trash over whatever filesystem the
    collection lives on and stop_watcher() waits on the observer; on a slow or
    disconnected network drive either can take minutes. The process then sat
    there holding port 5001 with no window to show for it, and the next start
    handed the user over to that ghost instead of opening -- which looks exactly
    like a launcher that does nothing. Tidying up gets `deadline` seconds; after
    that the process leaves regardless. Nothing here risks data: the trash is
    swept again on the next start, and the watcher dies with the process."""
    # imported here, not at the top: events loads before scanning, and a
    # module cannot import from one that has not been built yet.
    from .scanning import stop_watcher
    swept = threading.Event()
    done = threading.Event()

    def _tidy():
        # imported here, not at the top: events loads before scanning, and a
        # module cannot import from one that has not been built yet.
        from .scanning import stop_watcher
        try:
            _cleanup_trash()
        except Exception:
            pass
        try:
            stop_watcher()
        except Exception:
            pass
        swept.set()
        # v4.38: fold the write-ahead log back into trackimage.db on the way out.
        # Nothing is lost without it -- SQLite replays the -wal on the next open --
        # but the .db on disk is only current once this has run, which matters for
        # anyone who backs the file up or copies it somewhere.
        try:
            _wal_checkpoint_now()
        except Exception:
            pass
        done.set()

    t = threading.Thread(target=_tidy, daemon=True, name="shutdown")
    t.start()
    # v4.53: two budgets rather than one. Sweeping the trash and stopping the
    # watcher can hang on a network drive that has gone away, and that is what
    # the short deadline is for. Folding the log back in is different: it is the
    # step that leaves the .db on disk current, a user closing mid-scan can have
    # a large one, and over a 1 Gbit/s link three seconds was not always enough.
    # It is bounded too, just further out.
    if not swept.wait(deadline):
        try:
            log("Tidying up took longer than %.0fs \u2014 moving on" % deadline, "warning")
        except Exception:
            pass
    if not done.wait(checkpoint_deadline):
        try:
            log("The write-ahead log was still being folded in after %.0fs \u2014 "
                "exiting anyway. Nothing is lost; SQLite replays it on the next "
                "start." % checkpoint_deadline, "warning")
        except Exception:
            pass


def _cancel_shutdown_timer():
    if state._shutdown_timer:
        state._shutdown_timer.cancel()
        state._shutdown_timer = None


def _check_shutdown():
    """Start shutdown countdown if no tabs remain."""
    # imported here, not at the top: events loads before scanning, and a
    # module cannot import from one that has not been built yet.
    from .scanning import stop_watcher
    if not state._auto_shutdown:
        return
    _cancel_shutdown_timer()
    def do_shutdown():
        with _tabs_lock:
            # imported here, not at the top: events loads before scanning, and a
            # module cannot import from one that has not been built yet.
            from .scanning import stop_watcher
            if len(_active_tabs) > 0:
                return  # a new tab connected in time
        print("\n  ◈ All browser tabs closed — shutting down.")
        # Move expired trash to OS recycle bin (same 10-min rule)
        try:
            _cleanup_trash()
        except: pass
        stop_watcher()
        os._exit(0)
    state._shutdown_timer = threading.Timer(5.0, do_shutdown)
    state._shutdown_timer.daemon = True
    state._shutdown_timer.start()


def _restart_self():
    """Start a fresh copy and step aside so it can take the port."""
    _time.sleep(0.8)
    try:
        exe = sys.executable
        if os.name == "nt":
            pw = os.path.join(os.path.dirname(exe), "pythonw.exe")
            if os.path.isfile(pw):
                exe = pw
        script = os.path.abspath(__file__)
        state._UI_HANDOVER = True
        _shutdown_for_restart()
        _time.sleep(1.0)          # let the socket go before the new one binds
        subprocess.Popen([exe, script], cwd=os.path.dirname(script),
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                         if os.name == "nt" else 0)
    except Exception as e:
        log(f"Could not restart: {e}", "error")
    finally:
        os._exit(0)


def _shutdown_for_restart():
    try:
        _shutdown_now()          # same tidy-up the window close does
    except Exception:
        pass


state._trash_janitor_started = False
