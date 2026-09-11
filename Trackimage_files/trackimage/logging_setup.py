"""The log file, the console mirror, and log().

Layer 3 of 27 -- see trackimage/__init__.py for the order these load in.
"""
import collections
import logging.handlers
import os
import sys
import threading
import traceback
from . import state
from .config import LOG_DIR


_LOG_PATH = os.path.join(LOG_DIR, "trackimage.log")


_logger = logging.getLogger("trackimage")


def log(msg, level="info"):
    """Timestamped, levelled output to console + rotating logfile."""
    (getattr(_logger, level, None) or _logger.info)(msg)


class _ConsoleOnly(logging.Filter):
    """v4.19: keeps the file-by-file commentary out of the logfile.

    Those lines are for watching the program work, not for keeping. Writing them
    to disk pushed the file past its 2 MB limit within minutes, and every line
    after that tried to roll it over -- see _SafeRotatingFileHandler below for
    what that turned into."""
    def filter(self, record):
        return not getattr(record, "ti_detail", False)


def log_detail(msg):  # noqa: E302
    """v4.15: the file-by-file commentary behind the Detail switch.

    The console only ever reported milestones -- "2,810 embedded", "backfill done"
    -- so opening it to see what the program was doing right now showed nothing at
    all. These lines answer that. They are off by default because a library of
    this size produces thousands of them, and they are dropped at the source when
    the switch is off, so they cost nothing while nobody is watching."""
    # v4.19: always on, and marked so the logfile handler drops it.
    _logger.info(msg, extra={"ti_detail": True})


_CONSOLE_MAX = 4000    # v4.14: enough to still see how a long import went


_console_lines = collections.deque(maxlen=_CONSOLE_MAX)


state._console_seq = 0


_console_lock = threading.Lock()


def _console_add(text):
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        with _console_lock:
            state._console_seq += 1
            _console_lines.append((state._console_seq, line))


class _ConsoleTee:
    """Writes through to the real stream and keeps a copy for the UI."""
    def __init__(self, stream):
        self._s = stream
        self._buf = ""

    def write(self, data):
        try:
            self._s.write(data)
        except Exception:
            pass
        try:
            self._buf += data
            if "\n" in self._buf:
                head, self._buf = self._buf.rsplit("\n", 1)
                _console_add(head)
        except Exception:
            self._buf = ""
        return len(data)

    def flush(self):
        try: self._s.flush()
        except Exception: pass

    def isatty(self):
        try: return self._s.isatty()
        except Exception: return False

    def fileno(self):
        return self._s.fileno()


def _install_console_tee():
    if getattr(sys.stdout, "_ti_tee", False):
        return
    for name in ("stdout", "stderr"):
        st = getattr(sys, name, None)
        if st is None:
            continue
        tee = _ConsoleTee(st)
        tee._ti_tee = True
        setattr(sys, name, tee)


class _SafeRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """A rotating logfile that gives up quietly when it cannot rotate.

    v4.19: on Windows the rename fails whenever anything else holds the file
    open -- a second copy of TrackImage, a virus scanner, the search indexer. The
    stock handler then raises, the file stays at its maximum size, and every
    single line from then on tries again and raises again. Carrying on with the
    file as it stands is the right answer: a logfile that cannot be renamed is a
    small inconvenience, a traceback per line is a catastrophe."""
    def doRollover(self):
        try:
            super().doRollover()
        except Exception:
            # Reopen and keep writing. The file grows past its limit until
            # whatever holds it lets go, and the next rollover succeeds.
            try:
                if self.stream is None:
                    self.stream = self._open()
            except Exception:
                pass


def _setup_logging():
    if _logger.handlers: return
    _install_console_tee()
    _logger.setLevel(logging.INFO); _logger.propagate = False
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-5s %(message)s", datefmt="%H:%M:%S"))
    _logger.addHandler(sh)
    # v4.19: logging must never report its own troubles to stderr. The console
    # tee picks stderr up, so a handler that fails once ends up failing on every
    # line and printing a traceback each time -- which is exactly what happened.
    logging.raiseExceptions = False
    try:
        fh = _SafeRotatingFileHandler(_LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-5s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        fh.addFilter(_ConsoleOnly())      # detail lines stay out of the file
        _logger.addHandler(fh)
    except Exception as e:
        _logger.warning(f"could not open logfile {_LOG_PATH}: {e}")


def _install_crash_logging():
    """Log full tracebacks for uncaught exceptions in the main thread AND worker
    threads, so a crash is always visible with its cause."""
    def _hook(et, ev, tb):
        if issubclass(et, KeyboardInterrupt):
            sys.__excepthook__(et, ev, tb); return
        _logger.critical("UNCAUGHT EXCEPTION\n" + "".join(traceback.format_exception(et, ev, tb)))
    sys.excepthook = _hook
    try:
        def _thook(a):
            _logger.error(f"UNCAUGHT EXCEPTION in thread '{a.thread.name}'\n"
                          + "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))
        threading.excepthook = _thook
    except Exception: pass
