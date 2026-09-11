"""Making thumbnails, and the worker that fills in the missing ones.

Layer 11 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from io import BytesIO
import os
import sqlite3
import subprocess
import threading
import time as _time
import traceback
from . import state
from .config import FFMPEG_BIN, HAS_PILLOW, Image, _AUTO_WORKERS, _CPU_COUNT, _MAX_WORKERS
from .logging_setup import log
from .platform_bits import _no_window
from .db import _db_commit_retry, _db_write_lock, _get_thread_db, _vacuum_run
from .metadata import _icc_validate


state._THUMB_CFG = None


def _thumb_cfg():
    """Cached (max_size, webp_quality) thumbnail settings from config. Reset to None
    whenever the settings change so the next call re-reads them."""
    if state._THUMB_CFG is None:
        sz, q = 1024, 90
        try:
            tdb = _get_thread_db()
            r1 = tdb.execute("SELECT value FROM config WHERE key='thumb_max_size'").fetchone()
            r2 = tdb.execute("SELECT value FROM config WHERE key='thumb_quality'").fetchone()
            tdb.close()
            if r1: sz = max(256, min(2048, int(r1["value"])))
            if r2: q  = max(40, min(100, int(r2["value"])))
        except Exception: pass
        state._THUMB_CFG = (sz, q)
    return state._THUMB_CFG


def generate_thumbnail_bytes(filepath, max_size=None, _raw=None):
    if not HAS_PILLOW: return None
    try:
        from PIL import ImageOps, ImageFilter
        _msz, _q = _thumb_cfg()
        if max_size is None: max_size = _msz
        _src = BytesIO(_raw) if _raw is not None else filepath
        with Image.open(_src) as img:
            try: img.draft("RGB", (max_size, max_size))   # v3.68: JPEG decodes at reduced scale
            except Exception: pass
            img = ImageOps.exif_transpose(img)
            icc = img.info.get("icc_profile")
            img.thumbnail((max_size, max_size), Image.LANCZOS, reducing_gap=2.0)
            if img.mode != "RGB": img = img.convert("RGB")
            # Mild sharpen after downscale to counteract softness (local contrast only, no hue shift)
            img = img.filter(ImageFilter.UnsharpMask(radius=0.5, percent=40, threshold=3))
            # v3.21: keep the ORIGINAL embedded ICC profile (do NOT force sRGB) so the
            # thumbnail matches the detail view, which serves the original file -- the
            # browser colour-manages both with the same profile. A broken/unreadable
            # profile is dropped (treated as sRGB), exactly as the original would render.
            save_kwargs = {"quality": _q, "method": 2}   # v3.68: faster WebP encode
            try:
                if icc and _icc_validate(icc)[0]:
                    save_kwargs["icc_profile"] = icc
            except Exception: pass
            buf = BytesIO(); img.save(buf, "WEBP", **save_kwargs); buf.seek(0)
            return buf.getvalue()
    except: return None


_thumb_progress = {"active": False, "current": 0, "total": 0}


_thumb_bf_lock = threading.Lock()


_thumb_bf = {"on": False}


_thumb_workers_cfg = {"n": 0}          # 0 = Auto


def _thumb_target_workers():
    """v3.76: organiser threads for the thumbnail back-fill. These are NOT extra
    CPU workers -- like the embedding threads they hand the actual decode to the
    shared compute process pool, so Auto simply matches the pool width. Was
    hard-coded to 10, which on a 24-thread machine looked like only every second
    core was used."""
    # imported here, not at the top: thumbnails loads before processing, and a
    # module cannot import from one that has not been built yet.
    from .processing import _mp_target_procs
    n = int(_thumb_workers_cfg.get("n") or 0)
    if n > 0:
        return max(1, min(_MAX_WORKERS, n))
    try:
        return max(2, min(_MAX_WORKERS, _mp_target_procs()))
    except Exception:
        return _AUTO_WORKERS


def _thumb_load_workers_cfg():
    try:
        db = _get_thread_db()
        r = db.execute("SELECT value FROM config WHERE key='thumb_workers'").fetchone()
        db.close()
        if r and str(r["value"]).strip() != "":
            _thumb_workers_cfg["n"] = max(0, min(_MAX_WORKERS, int(r["value"])))
    except Exception:
        pass


def _thumb_backfill_worker():
    # imported here, not at the top: thumbnails loads before duplicates, processing, and a
    # module cannot import from one that has not been built yet.
    from .duplicates import _embedding_has_backlog
    from .processing import _dispatch_thumb, _ondemand_recent
    try:
        db = _get_thread_db()
        rows = db.execute("SELECT id, filepath FROM images WHERE meta_done=1 "
                          "AND COALESCE(media_type,'image') != 'video' "
                          "AND id NOT IN (SELECT image_id FROM thumb_cache) "
                          "ORDER BY id DESC").fetchall()   # v3.70: newest first = what the gallery shows
        db.close()
        if not rows:
            return
        nthreads = _thumb_target_workers()   # v3.76: configurable, Auto = compute processes
        _thumb_progress.update({"active": True, "total": len(rows), "current": 0, "workers": nthreads})
        log(f"Thumbnail backfill: {len(rows):,} images, {nthreads} workers (background, yields to imports)")
        ctr = {"n": 0}
        clock = threading.Lock()
        def _bf(mine):
            # imported here, not at the top: thumbnails loads before duplicates, processing, and a
            # module cannot import from one that has not been built yet.
            from .duplicates import _embedding_has_backlog
            from .processing import _dispatch_thumb, _ondemand_recent
            d2 = _get_thread_db()
            try:
                for r in mine:
                    if _embedding_has_backlog():
                        return   # yield; re-triggered after the pool drains
                    while _ondemand_recent() and not _embedding_has_backlog():
                        _time.sleep(0.5)   # v3.70: user is browsing -> on-demand thumbs go first
                    with clock:
                        ctr["n"] += 1; _thumb_progress["current"] = ctr["n"]
                    fp = r["filepath"]
                    if not os.path.isfile(fp):
                        continue
                    try:
                        tb = _dispatch_thumb(fp)
                        if not tb:
                            continue
                        try: mt = os.stat(fp).st_mtime
                        except Exception: mt = 0
                        with _db_write_lock:
                            chk = d2.execute("SELECT filepath FROM images WHERE id=?", (r["id"],)).fetchone()
                            if chk and chk["filepath"] == fp:
                                d2.execute("INSERT OR REPLACE INTO thumb_cache (image_id, data, content_type, src_mtime, created_at) VALUES (?,?,?,?,?)",
                                           (r["id"], sqlite3.Binary(tb), "image/webp", mt, _time.time()))
                                _db_commit_retry(d2)
                    except Exception:
                        pass
            finally:
                try: d2.close()
                except Exception: pass
        threads = [threading.Thread(target=_bf, args=(rows[w::nthreads],), daemon=True) for w in range(nthreads)]
        for t in threads: t.start()
        for t in threads: t.join()
        log(f"Thumbnail backfill: {ctr['n']:,} / {len(rows):,} done")
    except Exception as e:
        print(f"  ⚠ thumbnail backfill error: {e}")
    finally:
        _thumb_progress["active"] = False
        with _thumb_bf_lock:
            _thumb_bf["on"] = False


def _thumb_backfill_ensure_running():
    # imported here, not at the top: thumbnails loads before duplicates, and a
    # module cannot import from one that has not been built yet.
    from .duplicates import _embedding_has_backlog
    if not HAS_PILLOW or _embedding_has_backlog():
        return
    with _thumb_bf_lock:
        if _thumb_bf["on"]:
            return
        _thumb_bf["on"] = True
    threading.Thread(target=_thumb_backfill_worker, daemon=True).start()


_thumb_regen = {"running": False, "done": 0, "total": 0, "cancel": False}


def _thumb_regen_worker():
    # v3.27: rebuild EVERY thumbnail at the current settings, in parallel, so changing
    # resolution/quality actually takes effect everywhere (not lazily one-by-one).
    import concurrent.futures
    _thumb_regen.update(running=True, done=0, total=0, cancel=False)
    try:
        rdb = _get_thread_db()
        rows = rdb.execute("SELECT id, filepath FROM images WHERE media_type='image'").fetchall()
        total = len(rows); _thumb_regen["total"] = total
        log(f"Thumbnail regeneration started: {total:,} images at new settings")
        done = [0]; clk = threading.Lock()
        def work(r):
            if _thumb_regen.get("cancel"): return
            try:
                tb = generate_thumbnail_bytes(r["filepath"])
                if tb:
                    mt = 0
                    try: mt = os.path.getmtime(r["filepath"])
                    except Exception: pass
                    wdb = _get_thread_db()
                    with _db_write_lock:
                        wdb.execute("INSERT OR REPLACE INTO thumb_cache (image_id,data,content_type,src_mtime,created_at) VALUES (?,?,?,?,?)",
                                    (r["id"], tb, "image/webp", mt, _time.time()))
                        _db_commit_retry(wdb)
            except Exception: pass
            with clk:
                done[0] += 1; _thumb_regen["done"] = done[0]
                if done[0] % 200 == 0: log(f"Thumbnail regeneration · {done[0]:,}/{total:,}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, _CPU_COUNT)) as ex:
            list(ex.map(work, rows))
        log(f"Thumbnail regeneration done: {done[0]:,} thumbnails")
        # v3.86: the old BLOBs are gone but the file is not smaller until VACUUM.
        # Skipped on cancel -- a partial regeneration has nothing to reclaim yet.
        if not _thumb_regen.get("cancel"):
            _thumb_regen["running"] = False   # release before the exclusive rewrite
            _vacuum_run("thumbnail regeneration")
    except Exception:
        log("thumbnail regeneration crashed:\n" + traceback.format_exc(), "error")
    finally:
        _thumb_regen["running"] = False


def generate_video_thumbnail(filepath, max_size=768):
    """Extract a frame from video via ffmpeg, return JPEG bytes or None."""
    for seek in ["0.5", "0", None]:
        try:
            cmd = [FFMPEG_BIN]
            if seek is not None:
                cmd += ["-ss", seek]
            cmd += [
                "-i", filepath,
                "-frames:v", "1", "-vf", f"scale={max_size}:{max_size}:force_original_aspect_ratio=decrease",
                "-f", "image2", "-c:v", "mjpeg", "-q:v", "5", "-y", "pipe:1"
            ]
            result = subprocess.run(cmd, **_no_window({"capture_output": True, "timeout": 15}))
            if result.returncode == 0 and len(result.stdout) > 100:
                return result.stdout
        except: pass
    return None


def _store_thumb_cache(db, image_id, data, content_type, mt):
    """Persist a generated thumbnail as a BLOB. Uses the global write lock so an
    on-demand thumbnail never collides with the background pool. The expensive
    decode/resize already happened before this call (outside the lock), so the
    user only ever waits on a tiny single-row write here."""
    try:
        with _db_write_lock:
            db.execute("INSERT OR REPLACE INTO thumb_cache (image_id, data, content_type, src_mtime, created_at) VALUES (?,?,?,?,?)",
                       (image_id, sqlite3.Binary(data), content_type, mt or 0, _time.time()))
            _db_commit_retry(db)
    except Exception as e:
        print(f"  ⚠ thumb cache store failed for #{image_id}: {e}")
