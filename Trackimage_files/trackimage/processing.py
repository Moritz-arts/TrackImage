"""The worker pool that turns a file on disk into a row in the database.

Layer 12 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from collections import deque
from io import BytesIO
from pathlib import Path
import os
import sqlite3
import threading
import time as _time
import traceback
from . import state
from .config import Image, VIDEO_EXTENSIONS, _AUTO_SHARE, _AUTO_WORKERS, _CLAIM_PAGE, _CPU_COUNT, _DEFAULT_WORKERS, _MAX_WORKERS, _MEM_PAIR_MIN_THR, _ensure_std_streams
from .logging_setup import log, log_detail
from .platform_bits import _Unreachable, _boost_process_priority, _boost_thread_qos
from .db import _db_commit_retry, _db_write_lock, _get_thread_db, extract_search_text, get_db
from .events import sse_notify
from .metadata import extract_metadata
from .hashing import compute_hashes
from .thumbnails import _thumb_backfill_ensure_running, _thumb_load_workers_cfg, _thumb_progress, _thumb_target_workers, _thumb_workers_cfg, generate_thumbnail_bytes


_proc = {
    "running": False,      # any worker threads alive
    "paused": False,       # user paused
    "auto": True,          # auto-start workers after discovery
    "workers": _DEFAULT_WORKERS,
    "total": 0,            # this-run workload snapshot (meta_done=0 at run start)
    "base_done": 0,        # files already processed before this run started
    "done": 0,             # processed since this run started
    "active": 0,           # currently being processed
    "floor": 0,            # v4.43: highest id already walked past in the backlog
    "died": "",            # v4.43: why the pool stopped, when it was not asked to
    "threads": [],
}


_proc_lock = threading.Lock()


_proc_prio = deque()                  # user-requested image IDs (front = next)


_proc_prio_lock = threading.Lock()


_proc_claimed = set()                 # IDs currently in-flight (avoid double work)


_proc_claimed_lock = threading.Lock()


_proc_sse = {"ts": 0.0}               # throttle progress SSE


_proc_fail = {}                       # iid -> consecutive transient failures


_proc_failed_run = set()              # iids set aside this run after repeated failure


_proc_fail_lock = threading.Lock()


_timing = {"n": 0, "read": 0.0, "compute": 0.0, "wait": 0.0, "write": 0.0}


_timing_lock = threading.Lock()


def _timing_record(read, compute, wait, write):
    with _timing_lock:
        _timing["n"] += 1
        _timing["read"] += read; _timing["compute"] += compute
        _timing["wait"] += wait; _timing["write"] += write
        if _timing["n"] % 200 == 0:
            n = _timing["n"]
            log(f"Embedding · this run {_proc.get('done',0):,} / {_proc.get('total',0):,} · lifetime {n:,} · per-image avg: read {_timing['read']/n*1000:.0f}ms · "
                f"compute {_timing['compute']/n*1000:.0f}ms · write-wait {_timing['wait']/n*1000:.0f}ms · "
                f"write {_timing['write']/n*1000:.0f}ms")


def _proc_load_settings():
    """Load the auto-process flag from config. The worker count is no longer
    configurable — v3.13 always uses EVERY detected logical processor (user
    request: stop the slider trouble, just run at full width)."""
    try:
        db = _get_thread_db()
        row = db.execute("SELECT value FROM config WHERE key=?", ("proc_auto",)).fetchone()
        if row and row["value"] is not None:
            _proc["auto"] = (row["value"] == "1")
        db.close()
    except: pass
    # v3.74: honour the saved organiser-thread count. This line used to hard-set
    # full width on every start, so /api/processing/settings wrote proc_workers to
    # the config and nothing ever read it back -- the slider reset on restart.
    # 0 (or unset) still means Auto = all logical processors.
    _wn = 0
    try:
        db = _get_thread_db()
        row = db.execute("SELECT value FROM config WHERE key=?", ("proc_workers",)).fetchone()
        if row and row["value"] is not None and str(row["value"]).strip() != "":
            _wn = max(0, min(_MAX_WORKERS, int(row["value"])))
        db.close()
    except Exception:
        _wn = 0
    _proc["workers_cfg"] = _wn                       # 0 = Auto, for the UI
    _proc["cpu_count"] = _CPU_COUNT                  # v4.14: for the percent readout
    _proc["auto_workers"] = _AUTO_WORKERS
    _proc["workers"] = _wn if _wn else _AUTO_WORKERS  # effective count (Auto = 85%)
    try: _thumb_load_workers_cfg()                   # v3.76
    except Exception: pass


def _proc_save_setting(key, value):
    try:
        db = _get_thread_db()
        db.execute("INSERT OR REPLACE INTO config (key,value) VALUES (?,?)", (key, str(value)))
        db.commit(); db.close()
    except: pass


def _proc_counts(db):
    """Return (total_rows, done_count) in ONE atomic query. Reading pending and
    done as two separate COUNTs let an image flip between them mid-read, making
    the total flicker by 1; a single statement is consistent."""
    try:
        row = db.execute("SELECT COUNT(*), COALESCE(SUM(meta_done),0) FROM images").fetchone()
        return int(row[0]), int(row[1])
    except:
        return 0, 0


_unlink_progress = {"active": False, "current": 0, "total": 0, "phase": "", "root": ""}


def _proc_progress_payload(db=None):
    # imported here, not at the top: processing loads before duplicates, and a
    # module cannot import from one that has not been built yet.
    from .duplicates import _dup_progress, _mem_compute
    if db is not None:
        total_rows, done_total = _proc_counts(db)
        pending = max(0, total_rows - done_total)
        # "files processed" = completed THIS run = current completed minus the
        # baseline captured at run start. Derived from live DB counts (never an
        # incrementing counter), so it can't drift or exceed the real file count;
        # total grows if new images arrive mid-run, so done never jumps backwards.
        done = max(0, done_total - _proc.get("base_done", 0))
        total = max(_proc["total"], done + pending)
        done = min(done, total)
    else:
        done = _proc["done"]; total = _proc["total"]
        pending = max(0, total - done)
    # v3.15: per-phase sub-progress so the Settings page can show one bar per task
    # (folder scan / embedding / duplicate pairing). Cheap to assemble; scan_progress,
    # _dup_progress and _pairs_running are module globals populated by their workers.
    try:
        _sf = state.scan_progress.get("folders", [])
        _sc_cur = sum(int(f.get("current", 0)) for f in _sf)
        _sc_tot = sum(int(f.get("total", 0)) for f in _sf)
        _sc_name = ""
        for _f in _sf:
            if _f.get("current", 0) < _f.get("total", 0):
                _sc_name = _f.get("name", ""); break
        if not _sc_name and _sf:
            _sc_name = _sf[-1].get("name", "")
        _scan = {"active": bool(state.scan_progress.get("active")), "current": _sc_cur, "total": _sc_tot, "folder": _sc_name}
    except Exception:
        _scan = {"active": False, "current": 0, "total": 0, "folder": ""}
    _pairs = {"active": bool(_dup_progress.get("active")), "current": int(_dup_progress.get("current", 0)),
              "total": int(_dup_progress.get("total", 0)), "running": bool(_mem_compute.get("on", False)),
              "pending": False}
    _thumbs = {"active": bool(_thumb_progress.get("active")), "current": int(_thumb_progress.get("current", 0)),
               "total": int(_thumb_progress.get("total", 0)), "workers": int(_thumb_progress.get("workers", 0)),
               "workers_cfg": int(_thumb_workers_cfg.get("n", 0)),          # v3.76: 0 = Auto
               "workers_eff": _thumb_target_workers(), "max_workers": _MAX_WORKERS}
    _ul = {"active": bool(_unlink_progress.get("active")), "current": int(_unlink_progress.get("current", 0)),
           "total": int(_unlink_progress.get("total", 0)), "phase": _unlink_progress.get("phase", ""),
           "root": _unlink_progress.get("root", "")}
    return {
        "running": _proc["running"], "paused": _proc["paused"], "auto": _proc["auto"],
        "workers": _proc["workers"], "active": _proc["active"],
        # v4.43: a pool that stopped on an error, and a drive that is not
        # answering, are both things the interface has to be able to say out
        # loud. Silence is what made a dead pool look like a frozen program.
        "died": _proc.get("died", ""),
        "stalled": int(_proc_stall_state.get("n", 0)),
        "done": done, "total": total, "pending": pending,
        "max_workers": _MAX_WORKERS,
        "power": _power_state(),                       # v3.77: master control
        "workers_cfg": _proc.get("workers_cfg", 0),
        # v4.14: the sliders show the share of the machine, not just a count.
        "cpu_count": _CPU_COUNT, "auto_workers": _AUTO_WORKERS,
        "auto_share": _AUTO_SHARE,
        "workers_eff": max(1, min(_MAX_WORKERS, int(_proc.get("workers") or _AUTO_WORKERS))),
        "scan": _scan, "pairs": _pairs, "unlink": _ul, "thumbs": _thumbs,
        "mp": {"procs": _mp_target_procs(), "auto": _mp_configured() <= 0, "max": _MAX_WORKERS},
    }


def _proc_notify(force=False):
    """Throttled SSE progress broadcast (at most ~every 1.2s, unless forced)."""
    now = _time.time()
    if not force and (now - _proc_sse["ts"]) < 1.2:
        return
    _proc_sse["ts"] = now
    try:
        d = _get_thread_db()
        payload = _proc_progress_payload(d)
        d.close()
    except:
        payload = _proc_progress_payload()
    sse_notify("proc_progress", payload)


def _claim_next(db):
    """Return (image_id, filepath) for the next unit of work, or (None, None).
    Priority queue is drained first, then the background backlog."""
    # 1) priority (user-requested)
    with _proc_prio_lock:
        prio_ids = []
        while _proc_prio:
            prio_ids.append(_proc_prio.popleft())
    for iid in prio_ids:
        with _proc_claimed_lock:
            if iid in _proc_claimed:
                continue
        row = db.execute("SELECT filepath, meta_done FROM images WHERE id=?", (iid,)).fetchone()
        if row and not row["meta_done"]:
            with _proc_claimed_lock:
                _proc_claimed.add(iid)
            # push any other prio ids back to the front (preserve order)
            with _proc_prio_lock:
                for other in reversed(prio_ids):
                    if other != iid and other not in _proc_prio:
                        _proc_prio.appendleft(other)
            return iid, row["filepath"]
    # 2) background backlog (skip in-flight + images set aside after repeated failure)
    # v3.74 RACE FIX: the snapshot of _proc_claimed, the SELECT and the add()
    # must happen under ONE lock. Previously the lock was released between
    # reading the skip set and claiming the row, so with many worker threads two
    # of them routinely picked the SAME id -- every image got decoded, hashed and
    # written twice. Visible in the log as a "this run" counter climbing past the
    # file total. The query is indexed and takes microseconds, so serialising it
    # costs far less than the duplicated work it prevents.
    # v4.43: this used to name every skipped id as its own SQL parameter --
    # "id NOT IN (?,?,?,...)" -- which put a hard ceiling on how many images could
    # be set aside. A user's network drive stopped answering mid-run, every read
    # timed out, and the set-aside list grew to 32,754 entries; SQLite allows
    # 32,766 parameters, so the next call raised "too many SQL variables" and
    # took ALL 27 worker threads with it. Processing was dead from that moment
    # and nothing said so -- the progress bar simply stopped at the last image
    # that worked and the program looked frozen.
    #
    # The list is also why everything crawled long before it crashed. This
    # SELECT runs while holding _proc_claimed_lock, which every worker needs, so
    # a query that grows with the number of failures holds up the entire pool.
    #
    # Nothing is named in SQL any more. A short indexed page of candidates is
    # read and the skipping happens in Python, so the query costs the same
    # whether nothing has been set aside or the entire library has. _proc_floor
    # remembers how far the backlog has already been walked, so pages are not
    # re-read from the beginning each time.
    # _proc_failed_run is read without its lock on purpose: membership on a set
    # is a single operation, and the worst a stale answer can do is let one image
    # be attempted once more. Taking that lock here would mean holding it around
    # _proc_claimed_lock, and nothing else in the pool nests the two.
    failed = _proc_failed_run
    with _proc_claimed_lock:
        cursor = _proc["floor"]
        advance = cursor
        walking = True          # still at the head of the backlog
        while True:
            rows = db.execute(
                "SELECT id, filepath FROM images WHERE meta_done=0 AND id > ? "
                "ORDER BY id LIMIT ?", (cursor, _CLAIM_PAGE)).fetchall()
            if not rows:
                _proc["floor"] = advance
                return None, None
            for r in rows:
                rid = r["id"]
                if rid in failed:
                    # Given up on for this run -- the floor may pass it.
                    if walking:
                        advance = rid
                    continue
                # Anything else may still come back: an image in flight is
                # released when its worker is done, and one that failed once or
                # twice is owed another two attempts. The floor stops here.
                walking = False
                if rid in _proc_claimed:
                    continue
                _proc_claimed.add(rid)
                _proc["floor"] = advance
                return rid, r["filepath"]
            cursor = rows[-1]["id"]


def _compute_image_payload(fp, want_thumb):
    """Pure compute for one image file (no DB, picklable) — safe in a worker
    process. Returns None on a transient read/decode failure (caller retries)."""
    _r0 = _time.perf_counter()
    try:
        with open(fp, "rb") as f:
            raw = f.read()
    except Exception:
        # v4.43: "could not reach the file" is a different thing from "could not
        # make sense of it", and telling them apart is what stops a drive going
        # quiet from writing off an entire library. Returning the string means
        # every caller either handles it or fails loudly, which a None shared
        # with the decode path did not.
        return "unreadable"
    _r1 = _time.perf_counter()
    try:
        mt = os.stat(fp).st_mtime
    except Exception:
        mt = 0
    w = h = 0
    try:
        with Image.open(BytesIO(raw)) as im0:
            w, h = im0.size
    except Exception:
        pass
    try:
        ph, tsig = compute_hashes(fp, _raw=raw)      # v3.73: one decode, two signatures
        st = extract_search_text(fp, _raw=raw)
        thumb = generate_thumbnail_bytes(fp, _raw=raw) if want_thumb else None
    except Exception:
        return None
    return {"w": w, "h": h, "ph": ph, "ts": tsig, "fs": len(raw), "st": st,
            "thumb": thumb, "mtime": mt,
            "read_s": _r1 - _r0, "comp_s": _time.perf_counter() - _r1}


state._MP_POOL = None


state._MP_TRIED = False


_mp_lock = threading.Lock()


_MP_CFG = {"v": None}   # cached 'mp_workers' config (0 = Auto = half the logical processors)


def _mp_configured():
    if _MP_CFG["v"] is None:
        n = 0
        try:
            d = _get_thread_db()
            r = d.execute("SELECT value FROM config WHERE key='mp_workers'").fetchone()
            d.close()
            n = int(r["value"]) if r else 0
        except Exception:
            n = 0
        _MP_CFG["v"] = n
    return _MP_CFG["v"]


def _mp_target_procs():
    """Effective compute process count. 0/unset = Auto.

    v3.77: Auto is now ALL logical processors. It used to be half, chosen back
    when 24 processes measurably hurt -- but that slowdown came from the spawned
    workers being parked on the E-cores, not from oversubscription. Since the
    v3.75 pool initializer gives every worker its own EcoQoS opt-out, the same
    24 processes went from ~100 ms to ~37 ms per image on a 13700KF."""
    n = _mp_configured()
    if n <= 0:
        return _AUTO_WORKERS          # v4.14: 85% of the machine, not all of it
    return max(2, min(_MAX_WORKERS, n))


def _mp_set_workers(n, log_it=False):
    """v3.77: resize the compute pool. 0 = Auto. Extracted from the route so the
    master 'processing power' control can drive it too."""
    n = 0 if (n is None or n <= 0 or n > _MAX_WORKERS) else int(n)
    try:
        db = get_db()
        db.execute("INSERT OR REPLACE INTO config (key,value) VALUES ('mp_workers',?)", (str(n),))
        db.commit()
    except Exception:
        pass
    _MP_CFG["v"] = n
    with _mp_lock:   # terminate; next dispatch recreates with the new size
        try:
            if state._MP_POOL is not None: state._MP_POOL.terminate()
        except Exception: pass
        state._MP_POOL = None
        state._MP_TRIED = False
    if log_it:
        log(f"Compute process pool set to {'Auto' if n == 0 else n} \u2014 restarting with {_mp_target_procs()} processes")
    return n


def _mp_ping():
    return 1


def _mp_worker_init():
    """v3.75: runs once inside every spawned compute process.

    v4.0: the streams are fixed up first -- a worker spawned from pythonw.exe
    inherits its missing stdout and would die on the first print().

    The pool is created with the "spawn" start method, so each worker is a brand
    new python.exe. Windows classifies a fresh background process as
    'efficiency' and parks it on the E-cores -- on a 13700KF that is 8 E-cores
    for ALL processes, which is why Task Manager showed only a third of the
    machine busy while 24 workers were supposedly running. The parent's opt-out
    does not reach them, so each worker asks for full-speed scheduling itself."""
    _ensure_std_streams()
    try:
        _boost_process_priority(worker=True)     # v4.14: never outrank the interface
    except Exception:
        pass
    try:
        _boost_thread_qos()
    except Exception:
        pass
    # One BLAS/OMP thread per worker: 24 processes each spawning a full-width
    # math pool would fight over the same cores and lose more than they gain.
    for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ.setdefault(_v, "1")


def _mp_get_pool():
    """Lazily start ONE process pool (spawn, half the logical cores). Workers
    re-import this module with TRACKIMAGE_MP_WORKER=1 (no init_db, no prints).
    Returns None if unavailable — callers then compute in-thread."""
    with _mp_lock:
        if state._MP_TRIED:
            return state._MP_POOL
        state._MP_TRIED = True
        try:
            import multiprocessing as _mp
            os.environ["TRACKIMAGE_MP_WORKER"] = "1"   # inherited by (re)spawned workers
            _nproc = _mp_target_procs()
            _pool = _mp.get_context("spawn").Pool(processes=_nproc,
                                                   initializer=_mp_worker_init)
            _pool.apply_async(_mp_ping, ()).get(timeout=90)   # verify workers actually start
            state._MP_POOL = _pool
            log(f"Compute process pool ready — {_nproc} worker processes (GIL-free)")
        except Exception as e:
            print(f"  ⚠ process pool unavailable ({type(e).__name__}: {e}) — computing in threads")
            try:
                if '_pool' in dir() and _pool is not None: _pool.terminate()
            except Exception: pass
            state._MP_POOL = None
        return state._MP_POOL


def _mp_disable(e):
    print(f"  ⚠ process pool failed ({e}) — falling back to in-thread compute")
    try:
        if state._MP_POOL is not None: state._MP_POOL.terminate()
    except Exception: pass
    state._MP_POOL = None


def _dispatch_compute(fp, want_thumb=False):
    pool = _mp_get_pool()
    if pool is not None:
        try:
            return pool.apply_async(_compute_image_payload, (fp, want_thumb)).get(timeout=300)
        except Exception as e:
            _mp_disable(e)
    return _compute_image_payload(fp, want_thumb)


def _dispatch_thumb(fp):
    pool = _mp_get_pool()
    if pool is not None:
        try:
            return pool.apply_async(generate_thumbnail_bytes, (fp,)).get(timeout=300)
        except Exception as e:
            _mp_disable(e)
    return generate_thumbnail_bytes(fp)


_ondemand = {"ts": 0.0}


def _ondemand_mark():
    _ondemand["ts"] = _time.time()


def _ondemand_recent():
    return (_time.time() - _ondemand["ts"]) < 2.0


def _process_one_image(db, iid, fp):
    """Read the file ONCE, derive metadata+thumbnail+pHash, write via the global
    write lock. Returns True if handled (done or legitimately skipped), False on a
    transient failure that should be retried later. Race-safe: discards the result
    if the row was deleted/renamed mid-flight. Never touches trash/delete paths."""
    # imported here, not at the top: processing loads before tagger, and a
    # module cannot import from one that has not been built yet.
    from .tagger import _apply_embedded_keywords, _embedded_tags_on
    ext = Path(fp).suffix.lower()
    is_video = ext in VIDEO_EXTENSIONS

    # File moved/deleted before we got to it -> mark done (sweep removes gone files).
    if not os.path.isfile(fp):
        try:
            with _db_write_lock:
                chk = db.execute("SELECT filepath FROM images WHERE id=?", (iid,)).fetchone()
                if chk and chk["filepath"] == fp:
                    db.execute("UPDATE images SET meta_done=1 WHERE id=?", (iid,))
                    _db_commit_retry(db)
            return True
        except Exception:
            return False

    if is_video:
        st = ""
        w = h = 0
        meta = {}
        try:
            # v4.53: through extract_metadata, so a video picks up its sidecar.
            # MP4 has no EXIF, and the tools that write metadata for video put it
            # in a .xmp next to the file instead.
            meta = extract_metadata(fp)
            st = extract_search_text(fp)
            w = int(meta.get("width_px") or 0); h = int(meta.get("height_px") or 0)
        except: pass
        try:
            with _db_write_lock:
                chk = db.execute("SELECT filepath FROM images WHERE id=?", (iid,)).fetchone()
                if not chk or chk["filepath"] != fp:
                    return True  # row gone/renamed -> nothing to do
                db.execute("UPDATE images SET width=?, height=?, search_text=?, "
                           "tile_sig=?, meta_done=1 WHERE id=?",
                           (w, h, st, sqlite3.Binary(b""), iid))
                if _embedded_tags_on():
                    _apply_embedded_keywords(db, iid, meta)
                _db_commit_retry(db)
            sse_notify("processed", {"id": iid})
            return True
        except Exception:
            return False

    # v3.68 Phase A: metadata + search index + pHash only — the thumbnail moved to
    # the Phase B backfill (and stays available on demand). Compute runs in a worker
    # PROCESS when the pool is up (GIL-free), in this thread otherwise.
    payload = _dispatch_compute(fp, want_thumb=False)
    if payload == "unreadable":
        # The file could not be opened at all. On a drive that has gone quiet
        # this is about to be true of every remaining image, so it is reported
        # separately -- see _proc_worker, which pauses the pool rather than
        # marching through the backlog turning it into failures.
        raise _Unreachable(fp)
    if payload is None:
        return False  # decoded badly -> retry later, then set aside
    w = payload["w"]; h = payload["h"]; ph = payload["ph"]; st = payload["st"]
    thumb = payload["thumb"]; src_mtime = payload["mtime"]
    tsig = payload.get("ts"); fsz = int(payload.get("fs") or 0)   # v3.73
    _t2 = _time.perf_counter()

    try:
        with _db_write_lock:
            _t3 = _time.perf_counter()
            chk = db.execute("SELECT filepath FROM images WHERE id=?", (iid,)).fetchone()
            if not chk or chk["filepath"] != fp:
                return True  # row removed or path changed mid-flight -> discard
            db.execute("UPDATE images SET width=?, height=?, phash=?, search_text=?, "
                       "tile_sig=?, file_size=?, meta_done=1 WHERE id=?",
                       (w, h, ph, st, sqlite3.Binary(tsig or b""), fsz, iid))
            # v4.53: keywords a photo already carries, when asked for. Read here
            # rather than in the worker process, which returns only what it can
            # pickle and never saw the metadata dictionary.
            if _embedded_tags_on():
                try:
                    _apply_embedded_keywords(db, iid, extract_metadata(fp))
                except Exception:
                    pass
            if thumb:
                db.execute(
                    "INSERT OR REPLACE INTO thumb_cache (image_id, data, content_type, src_mtime, created_at) VALUES (?,?,?,?,?)",
                    (iid, sqlite3.Binary(thumb), "image/webp", src_mtime, _time.time()))
            _db_commit_retry(db)
        _t4 = _time.perf_counter()
        _timing_record(payload.get("read_s", 0.0), payload.get("comp_s", 0.0), _t3 - _t2, _t4 - _t3)
        sse_notify("processed", {"id": iid})
        return True
    except Exception:
        return False


_proc_stall_lock = threading.Lock()


_proc_stall_state = {"n": 0, "until": 0.0, "said": 0.0}


def _proc_stall(fp):
    # imported here, not at the top: processing loads before api_media, and a
    # module cannot import from one that has not been built yet.
    from .api_media import _detail_name
    with _proc_stall_lock:
        now = _time.time()
        if now < _proc_stall_state["until"]:
            wait = _proc_stall_state["until"] - now
        else:
            _proc_stall_state["n"] += 1
            wait = min(60.0, 2.0 * _proc_stall_state["n"])
            _proc_stall_state["until"] = now + wait
            if now - _proc_stall_state["said"] > 30:
                _proc_stall_state["said"] = now
                log(f"Cannot read {_detail_name(fp)} \u2014 waiting "
                    f"{int(wait)}s for the drive rather than skipping the rest "
                    f"of the library", "warning")
    _time.sleep(min(wait, 60.0))


def _proc_stall_clear():
    if _proc_stall_state["n"]:
        with _proc_stall_lock:
            if _proc_stall_state["n"]:
                log("The drive is answering again \u2014 processing continues", "info")
                _proc_stall_state["n"] = 0
                _proc_stall_state["until"] = 0.0


def _proc_worker():
    # imported here, not at the top: processing loads before api_media, duplicates, tagger, and a
    # module cannot import from one that has not been built yet.
    from .api_media import _detail_name
    from .duplicates import _ensure_mem_pairs, _mem_invalidate
    from .tagger import _tag_ensure_running
    _boost_thread_qos()   # v3.16: keep this worker off the E-cores (per-thread QoS)
    db = _get_thread_db()
    idle = 0
    try:
      # v4.43: an unexpected error in the loop below used to end the thread on
      # the spot. When one hits every worker at once -- as the SQL parameter
      # limit did -- the whole pool disappears in the same second, the progress
      # bar freezes at the last image that worked, and nothing anywhere says
      # processing has stopped. The user reasonably reads that as the program
      # hanging. The claim itself is retried a few times before this worker gives
      # up, and the reason is recorded so the interface can say it out loud.
      hiccups = 0
      while True:
        try:
            while _proc["running"]:
                if _proc["paused"]:
                    _time.sleep(0.4); continue
                iid, fp = _claim_next(db)
                if iid is None:
                    idle += 1
                    if idle >= 30:   # ~12s with no work -> let this worker exit
                        break
                    _time.sleep(0.4); continue
                idle = 0
                with _proc_lock:
                    _proc["active"] += 1
                ok = False
                unreachable = False
                try:
                    ok = _process_one_image(db, iid, fp)
                except _Unreachable:
                    # v4.43: the drive did not answer. Marching on would turn the
                    # rest of the library into failures at one timeout each --
                    # which is exactly what happened to a user whose network
                    # drive went quiet: 52,000 images written off in an hour, for
                    # files that were perfectly fine and read without a complaint
                    # the next morning. So the pool waits instead, and the image
                    # keeps its place in the queue.
                    unreachable = True
                    ok = False
                except Exception as e:
                    print(f"  \u26a0 processing #{iid}: {e}")
                    ok = False
                finally:
                    log_detail(("Embedded " if ok else "Failed ") + _detail_name(fp))
                    with _proc_lock:
                        _proc["active"] = max(0, _proc["active"] - 1)
                        if ok:
                            _proc["done"] += 1
                    with _proc_claimed_lock:
                        _proc_claimed.discard(iid)
                    if ok:
                        _proc_stall_clear()
                    with _proc_fail_lock:
                        if ok:
                            _proc_fail.pop(iid, None)
                        elif unreachable:
                            pass          # not the image's fault -- do not count it
                        else:
                            c = _proc_fail.get(iid, 0) + 1
                            _proc_fail[iid] = c
                            if c >= 3:
                                _proc_failed_run.add(iid)   # set aside; retried on next run
                                print(f"  \u26a0 giving up on #{iid} after {c} attempts (will retry next run)")
                    _proc_notify()
                if unreachable:
                    _proc_stall(fp)
            break            # the loop ended because the run did, not by error
        except Exception as e:
            hiccups += 1
            _proc["died"] = f"{type(e).__name__}: {e}"
            log(f"Background worker error ({hiccups}/3):\n{traceback.format_exc()}", "error")
            if hiccups >= 3:
                log(f"Background processing stopped: {_proc['died']}", "error")
                break
            _time.sleep(1.0)
    finally:
        db.close()
        with _proc_lock:
            alive = [t for t in _proc["threads"] if t.is_alive() and t is not threading.current_thread()]
            _proc["threads"] = alive
            if not alive:
                _proc["running"] = False
                _proc["active"] = 0
                _proc_notify(force=True)
                if _proc["auto"]:
                    _mem_invalidate()         # v3.66: hashes changed -> RAM pair cache recomputes on demand
                    _tag_ensure_running()     # v3.31: auto-tag freshly imported files
                    _thumb_backfill_ensure_running()   # v3.68: Phase B — thumbnail backfill
                    _ensure_mem_pairs(_MEM_PAIR_MIN_THR)   # v3.71: pre-warm duplicate pairs (RAM)


def _proc_ensure_running(reset_progress=False):
    """Start the worker pool if there is work and it isn't already running.
    If it IS already running, top it up to the configured worker count — so a
    folder added (or the slider raised) while the pool is busy immediately uses
    the FULL thread count instead of whatever the pool started with. v3.12 fix:
    the first folder after launch no longer stays stuck on the moderate default.
    Honors the auto flag for background work; priority requests bypass it."""
    notify = False
    with _proc_lock:
        target = max(1, min(_MAX_WORKERS, int(_proc["workers"])))
        alive = [t for t in _proc["threads"] if t.is_alive()]
        if _proc["running"] and alive:
            # already running -> scale UP to the configured count if short
            if len(alive) < target:
                for _ in range(target - len(alive)):
                    t = threading.Thread(target=_proc_worker, daemon=True)
                    t.start()
                    alive.append(t)
                _proc["threads"] = alive
                notify = True
        else:
            # snapshot pending + already-done baseline for progress display (atomic)
            try:
                db = _get_thread_db()
                total_rows, done_now = _proc_counts(db)
                pending = max(0, total_rows - done_now)
                db.close()
            except:
                pending = 0; done_now = 0
            has_prio = False
            with _proc_prio_lock:
                has_prio = len(_proc_prio) > 0
            if pending or has_prio:
                if reset_progress or not _proc["running"]:
                    _proc["base_done"] = done_now      # files already processed before this run
                    _proc["done"] = 0
                    _proc["total"] = pending
                    _proc["floor"] = 0      # v4.43: walk the backlog from the start again
                    _proc["died"] = ""
                    _proc_stall_state["n"] = 0
                    _proc_stall_state["until"] = 0.0
                    with _proc_fail_lock:
                        _proc_fail.clear()
                        _proc_failed_run.clear()
                _proc["running"] = True
                _proc["paused"] = False
                _proc["threads"] = []
                for _ in range(target):
                    t = threading.Thread(target=_proc_worker, daemon=True)
                    t.start()
                    _proc["threads"].append(t)
                notify = True
    if notify:
        _proc_notify(force=True)


def _proc_prioritize(image_id):
    """User opened an image: jump it to the front of the queue and wake the pool."""
    with _proc_prio_lock:
        if image_id in _proc_prio:
            _proc_prio.remove(image_id)
        _proc_prio.appendleft(image_id)
    _proc_ensure_running()


def _proc_stop():
    with _proc_lock:
        _proc["running"] = False
        threads = list(_proc["threads"])
    for t in threads:
        t.join(timeout=2)
    with _proc_lock:
        _proc["threads"] = []
        _proc["active"] = 0


def _power_state():
    """v3.77: the four worker counts as one number.

    Three of the four were never real decisions: the organiser threads and the
    thumbnail threads only ever want to match the compute pool -- fewer starves
    it, more just queues up. So they are driven by a single "processing power"
    value, with the individual sliders kept for anyone who wants to split them.
    Returns 0 when the stages disagree (the UI then shows "Custom")."""
    # imported here, not at the top: processing loads before tagger, and a
    # module cannot import from one that has not been built yet.
    from .tagger import _tag_get_cfg
    try:
        vals = {
            "workers": int(_proc.get("workers_cfg", 0) or 0),
            "procs": int(_mp_configured() or 0),
            "thumbs": int(_thumb_workers_cfg.get("n", 0) or 0),
            "tag": int(_tag_get_cfg().get("workers", 0) or 0),
        }
    except Exception:
        return {"power": 0, "custom": False, "max": _MAX_WORKERS, "stages": {}}
    uniq = set(vals.values())
    power = vals["procs"] if len(uniq) == 1 else 0
    return {"power": power, "custom": len(uniq) > 1, "max": _MAX_WORKERS,
            "auto": _AUTO_WORKERS, "cpu_count": _CPU_COUNT,
            "effective": _mp_target_procs(), "stages": vals}


_rate_samples = {}


def _rate_eta(key, current, total, window=60.0):
    """Return (per_second, seconds_remaining) or (0, 0) until a rate is known."""
    now = _time.time()
    buf = _rate_samples.setdefault(key, [])
    if buf and current < buf[-1][1]:
        buf.clear()                      # counter restarted -> old samples are noise
    if not buf or now - buf[-1][0] >= 1.0:
        buf.append((now, current))
    while len(buf) > 2 and now - buf[0][0] > window:
        buf.pop(0)
    if len(buf) < 2:
        return 0.0, 0
    dt = buf[-1][0] - buf[0][0]
    dn = buf[-1][1] - buf[0][1]
    if dt <= 0 or dn <= 0:
        return 0.0, 0
    rate = dn / dt
    left = max(0, int(total) - int(current))
    return round(rate, 2), int(left / rate) if rate > 0 else 0


_hash_progress = {"active": False, "current": 0, "total": 0}


_hash_gaveup = set()   # v3.70: ids that produced no hash this session — do not re-decode every visit


def _mark_hash_fail(db, iid):
    """v3.80: remember permanently that this file yields no pHash, so the
    duplicate scan stops re-decoding it after every restart."""
    _hash_gaveup.add(iid)
    try:
        with _db_write_lock:
            db.execute("UPDATE images SET hash_fail=1 WHERE id=?", (iid,))
            _db_commit_retry(db)
    except Exception:
        pass
