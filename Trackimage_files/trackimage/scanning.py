"""Walking folders, watching them, autosync, and orphan cleanup.

Layer 15 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from pathlib import Path
import os
import threading
import time as _time
from . import state
from .config import APP_DIR, DB_DIR, FileSystemEventHandler, HAS_WATCHDOG, LOG_DIR, MEDIA_EXTENSIONS, Observer, STATIC_DIR, VIDEO_EXTENSIONS, _SKIP_DIR_NAMES, _SWEEP_MAX_SHARE, app, detect_media_type, USERDATA_DIR
from .logging_setup import log
from .db import _db_commit_retry, _db_write_lock, _get_thread_db, get_db
from .events import sse_notify
from .media import get_file_date
from .processing import _proc, _proc_ensure_running
from .duplicates import _mem_invalidate


_watcher_dirty = threading.Event()


_watcher_suppress = set()  # paths to ignore (set by app actions)


_watcher_suppress_lock = threading.Lock()


_watcher_changed = set()   # exact paths reported by the fs watcher (targeted sync)


_watcher_changed_lock = threading.Lock()


state._watcher_observer = None


state._watcher_running = False


_watcher_ctl_lock = threading.RLock()


_AUTOSYNC = {"on": True}   # v3.61: master switch (watcher + auto-process + auto-tag)


def _autosync_load():
    try:
        d = _get_thread_db()
        r = d.execute("SELECT value FROM config WHERE key='autosync'").fetchone()
        d.close()
        _AUTOSYNC["on"] = (r is None) or (str(r["value"]) == "1")
    except Exception:
        pass


def _incremental_sync():
    """Dispatcher: sync only the exact paths the watcher reported; fall back to a
    full diff-scan only when no specific paths were captured."""
    if not _AUTOSYNC["on"]:   # v3.61: autosync off -> drop watcher events, no auto folder updates
        with _watcher_changed_lock:
            _watcher_changed.clear()
        return
    with _watcher_changed_lock:
        changed = list(_watcher_changed)
        _watcher_changed.clear()
    if changed:
        _sync_paths(changed)
    else:
        _full_sync()


def _sync_paths(paths):
    """Fast targeted sync: insert/update/remove only the given changed paths."""
    try:
        db = _get_thread_db()
        scan_folders = db.execute("SELECT path FROM scan_folders").fetchall()
        roots = [Path(sf["path"]) for sf in scan_folders if os.path.isdir(sf["path"])]
        if not roots:
            db.close(); return
        ignore_words = {r["word"].lower() for r in db.execute("SELECT word FROM ignore_words").fetchall()}
        new_count = removed_count = modified_count = 0
        seen = set()
        for raw in paths:
            filepath = os.path.normpath(raw)
            if filepath in seen: continue
            seen.add(filepath)
            ext = Path(filepath).suffix.lower()
            if ext not in MEDIA_EXTENSIONS: continue
            root = None
            for rt in roots:
                if str(Path(filepath)).lower().startswith(str(rt).lower()):
                    root = rt; break
            if root is None: continue
            with _watcher_suppress_lock:
                if filepath in _watcher_suppress: continue
            row = db.execute("SELECT id, file_date FROM images WHERE filepath=?", (filepath,)).fetchone()
            if not os.path.isfile(filepath):
                if row:
                    db.execute("DELETE FROM images WHERE id=?", (row["id"],))
                    removed_count += 1
                continue
            rel_folder = os.path.relpath(os.path.dirname(filepath), root)
            display_folder = f"{root.name}\\{rel_folder}" if rel_folder != "." else root.name
            is_video = ext in VIDEO_EXTENSIONS
            if row:
                cur_mtime = get_file_date(filepath)
                if row["file_date"] and cur_mtime and abs(cur_mtime - (row["file_date"] or 0)) > 1:
                    # Modified: flag for re-processing (no inline file read).
                    db.execute("UPDATE images SET file_date=?, meta_done=0 WHERE id=?",
                               (cur_mtime, row["id"]))
                    modified_count += 1
                continue
            filename = os.path.basename(filepath)
            file_date = get_file_date(filepath)
            mt = detect_media_type(filepath)
            # Lean insert: metadata/thumbnail/pHash handled by the worker pool.
            cur = db.execute(
                "INSERT OR IGNORE INTO images (filename,folder,filepath,width,height,file_date,search_text,phash,media_type,meta_done) VALUES (?,?,?,?,?,?,?,?,?,0)",
                (filename, display_folder, filepath, 0, 0, file_date, "", "", mt))
            iid = cur.lastrowid
            if iid == 0: continue
            new_count += 1
        if new_count or removed_count or modified_count:
            db.execute("DELETE FROM characters WHERE id NOT IN (SELECT DISTINCT character_id FROM image_characters)")
            db.execute("DELETE FROM thumb_cache WHERE image_id NOT IN (SELECT id FROM images)")
            db.commit()
            log(f"Folder sync: {new_count:,} new \u00b7 {modified_count:,} modified (re-embed) \u00b7 {removed_count:,} removed")
            sse_notify("sync", {"new": new_count, "removed": removed_count, "modified": modified_count})
        db.close()
        with _watcher_suppress_lock:
            _watcher_suppress.clear()
        if (new_count or modified_count) and _proc["auto"]:
            _proc_ensure_running(reset_progress=True)
    except Exception as e:
        print(f"  ⚠ Targeted sync error: {e}")


def _full_sync():
    """Quick diff-scan: compare DB paths vs filesystem, sync differences."""
    try:
        db = _get_thread_db()
        scan_folders = db.execute("SELECT path FROM scan_folders").fetchall()
        if not scan_folders:
            db.close()
            return

        # Get all known paths from DB
        existing = {}
        for r in db.execute("SELECT id, filepath, filename, folder, file_date FROM images").fetchall():
            existing[r["filepath"]] = r

        # Walk filesystem
        found_paths = set()
        ignore_words = {r["word"].lower() for r in db.execute("SELECT word FROM ignore_words").fetchall()}
        new_count, removed_count, modified_count = 0, 0, 0

        for sf in scan_folders:
            root = Path(sf["path"])
            if not root.exists() or not root.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                _prune_dirs(dirpath, dirnames)      # v4.44
                if _skip_dir(dirpath):
                    continue
                dirnames.sort()
                rel_folder = os.path.relpath(dirpath, root)
                display_folder = f"{root.name}\\{rel_folder}" if rel_folder != "." else root.name
                for filename in filenames:
                    ext = Path(filename).suffix.lower()
                    if ext not in MEDIA_EXTENSIONS:
                        continue
                    filepath = os.path.join(dirpath, filename)
                    found_paths.add(filepath)
                    if filepath in existing:
                        # Modified? Flag for re-processing (worker pool handles it).
                        ex = existing[filepath]
                        cur_mtime = get_file_date(filepath)
                        if ex["file_date"] and cur_mtime and abs(cur_mtime - (ex["file_date"] or 0)) > 1:
                            db.execute("UPDATE images SET file_date=?, meta_done=0 WHERE id=?",
                                       (cur_mtime, ex["id"]))
                            modified_count += 1
                        continue
                    # New file — check suppress
                    with _watcher_suppress_lock:
                        if os.path.normpath(filepath) in _watcher_suppress:
                            continue
                    # Lean insert: metadata/thumbnail/pHash handled by the worker pool.
                    file_date = get_file_date(filepath)
                    mt = detect_media_type(filepath)
                    cur = db.execute(
                        "INSERT OR IGNORE INTO images (filename,folder,filepath,width,height,file_date,search_text,phash,media_type,meta_done) VALUES (?,?,?,?,?,?,?,?,?,0)",
                        (filename, display_folder, filepath, 0, 0, file_date, "", "", mt))
                    iid = cur.lastrowid
                    if iid == 0:
                        continue
                    new_count += 1

        # Remove DB entries for files that no longer exist
        for fp in list(existing.keys()):
            if fp not in found_paths:
                with _watcher_suppress_lock:
                    if os.path.normpath(fp) in _watcher_suppress:
                        continue
                db.execute("DELETE FROM images WHERE filepath=?", (fp,))
                removed_count += 1

        if new_count or removed_count or modified_count:
            db.execute("DELETE FROM characters WHERE id NOT IN (SELECT DISTINCT character_id FROM image_characters)")
            db.execute("DELETE FROM thumb_cache WHERE image_id NOT IN (SELECT id FROM images)")
            db.commit()
            log(f"Folder sync: {new_count:,} new \u00b7 {modified_count:,} modified (re-embed) \u00b7 {removed_count:,} removed")
            sse_notify("sync", {"new": new_count, "removed": removed_count, "modified": modified_count})
        db.close()

        # Clear suppressed paths after sync
        with _watcher_suppress_lock:
            _watcher_suppress.clear()
        if (new_count or modified_count) and _proc["auto"]:
            _proc_ensure_running(reset_progress=True)
    except Exception as e:
        print(f"  ⚠ Auto-sync error: {e}")


def _watcher_loop():
    """Background thread: waits for dirty flag, debounces, then syncs."""
    while state._watcher_running:
        _watcher_dirty.wait(timeout=5)
        if not _watcher_dirty.is_set():
            continue
        # Debounce: wait 2s of quiet
        _watcher_dirty.clear()
        _time.sleep(2)
        if _watcher_dirty.is_set():
            # More changes came in, restart debounce
            continue
        _incremental_sync()


if HAS_WATCHDOG:
    class _FSHandler(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory:
                return
            hit = []
            src = getattr(event, 'src_path', '')
            dest = getattr(event, 'dest_path', '')
            # v4.44: the watcher sees TrackImage's own .trash as ordinary folder
            # activity, so deleting a picture looked exactly like adding one.
            if src and Path(src).suffix.lower() in MEDIA_EXTENSIONS and not _skip_file(src):
                hit.append(src)
            if dest and Path(dest).suffix.lower() in MEDIA_EXTENSIONS and not _skip_file(dest):
                hit.append(dest)
            if hit:
                with _watcher_changed_lock:
                    for p in hit: _watcher_changed.add(p)
                _watcher_dirty.set()


def start_watcher():
    """v3.11: serialized entry point — every watcher start goes through the ctl lock."""
    with _watcher_ctl_lock:
        _start_watcher_impl()


def _start_watcher_impl():
    """Start the filesystem observer and sync thread."""
    if not HAS_WATCHDOG:
        return
    with app.app_context():
        db = get_db()
        folders = db.execute("SELECT path FROM scan_folders").fetchall()
    if not folders:
        print("  ℹ No folders to watch (add folders first, then restart)")
        sse_notify("watcher_status", {"active": False})
        return
    state._watcher_observer = Observer()
    handler = _FSHandler()
    watched = []
    for sf in folders:
        p = sf["path"]
        if os.path.isdir(p):
            state._watcher_observer.schedule(handler, p, recursive=True)
            watched.append(Path(p).name)
    if not watched:
        print("  ⚠ No valid folders to watch")
        # v3.91: the Observer was created above but is never started here.
        # Leaving it in the global would make the next stop_watcher() call
        # join a thread that was never started -> RuntimeError, and every
        # later "add folder" would fail with a 500.
        state._watcher_observer = None
        sse_notify("watcher_status", {"active": False})
        return
    state._watcher_running = True
    state._watcher_observer.start()
    t = threading.Thread(target=_watcher_loop, daemon=True)
    t.start()
    print(f"  👁 Watching: {', '.join(watched)}")
    sse_notify("watcher_status", {"active": True})


def stop_watcher():
    """v3.11: serialized entry point — every watcher stop goes through the ctl lock."""
    with _watcher_ctl_lock:
        _stop_watcher_impl()


def _stop_watcher_impl():
    state._watcher_running = False
    if state._watcher_observer:
        # v3.91: an observer that was created but never started raises
        # "cannot join thread before it is started". Belt and braces on top
        # of the fix in start_watcher() -- a stop must never break the caller.
        try:
            state._watcher_observer.stop()
        except RuntimeError:
            pass
        try:
            if state._watcher_observer.is_alive():
                state._watcher_observer.join(timeout=3)
        except RuntimeError:
            pass
        state._watcher_observer = None


def restart_watcher():
    """Restart watcher (e.g. after adding/removing scan folders).
    Serialized via _watcher_ctl_lock so overlapping calls (rapid unlink+relink)
    can never leave orphaned or duplicate observers behind."""
    with _watcher_ctl_lock:
        stop_watcher()
        start_watcher()


state.scan_progress = {"active": False, "folders": []}


def scan_all_folders():
    """v3.11: thin wrapper — guarantees scan_progress is ALWAYS reset, even if
    discovery throws. A stuck scan_progress={'active':True} was what made the UI
    hang on 'Scanning…' and show 0 content after a folder operation."""
    try:
        return _scan_all_folders_impl()
    except Exception as e:
        print(f"  ⚠ scan failed: {e}")
        return {"error": f"Scan failed: {e}"}
    finally:
        state.scan_progress = {"active": False, "folders": []}


def _own_dirs():
    """Every directory TrackImage itself owns, resolved."""
    out = set()
    for d in (APP_DIR, STATIC_DIR, DB_DIR, LOG_DIR,
              os.path.join(APP_DIR, "venv"), os.path.join(APP_DIR, "models"),
              USERDATA_DIR,          # v4.51

              os.path.join(DB_DIR, ".trash")):
        try:
            out.add(os.path.normcase(os.path.realpath(d)))
        except Exception:
            pass
    return out


_OWN_DIRS = _own_dirs()


def _skip_dir(dirpath, name=None):
    """True when this directory must not be scanned or watched."""
    if name is not None and name.lower() in _SKIP_DIR_NAMES:
        return True
    try:
        real = os.path.normcase(os.path.realpath(dirpath))
    except Exception:
        return False
    for own in _OWN_DIRS:
        if real == own or real.startswith(own + os.sep):
            return True
    return False


def _prune_dirs(dirpath, dirnames):
    """Drop unwanted directories from an os.walk in place, so their contents are
    never even listed."""
    keep = []
    for d in dirnames:
        if d.lower() in _SKIP_DIR_NAMES:
            continue
        if _skip_dir(os.path.join(dirpath, d), d):
            continue
        keep.append(d)
    dirnames[:] = keep


def _skip_file(path):
    """True when a single path lies somewhere a scan must not read. Used by the
    watcher, which is handed paths rather than walking them."""
    try:
        parent = os.path.dirname(path)
    except Exception:
        return False
    if _skip_dir(parent):
        return True
    # Lower-cased explicitly: os.path.normcase only folds case on Windows, so on
    # any other platform "$RECYCLE.BIN" would have slipped through a check that
    # looked correct.
    parts = path.replace("\\", os.sep).split(os.sep)
    return any(part.lower() in _SKIP_DIR_NAMES for part in parts[:-1])


def _scan_all_folders_impl():
    db = get_db()
    folders = db.execute("SELECT id, path, label FROM scan_folders").fetchall()
    if not folders: return {"error": "No folders configured"}

    state.scan_progress = {"active": True, "folders": []}

    # Count files per folder (cheap: directory listing only, no file opens)
    folder_counts = {}
    for sf in folders:
        root = Path(sf["path"])
        if not root.exists(): continue
        cnt = 0
        for dirpath, dirnames, filenames in os.walk(root):
            _prune_dirs(dirpath, dirnames)          # v4.44
            if _skip_dir(dirpath):
                continue
            cnt += sum(1 for fn in filenames if Path(fn).suffix.lower() in MEDIA_EXTENSIONS)
        folder_counts[sf["path"]] = cnt

    total_new, total_modified = 0, 0
    existing = {}
    for r in db.execute("SELECT id, filepath, file_date FROM images").fetchall():
        existing[r["filepath"]] = r
    all_found = set()
    # v4.38: a scan used to be one single transaction. Every file found across
    # every folder was written, and nothing was committed until the very last
    # one -- so closing TrackImage during a long scan rolled the whole thing
    # back and the library looked empty. On a NAS that window is minutes wide.
    # Work is saved every SCAN_COMMIT files now; an interrupted scan costs at
    # most the last few hundred, and the next run picks the rest up.
    #
    # The checkpoint on each save writes the WAL back into the .db straight
    # away, so the file on disk is current rather than a stub with a growing
    # sidecar next to it. Measured at 30,000 rows it costs nothing next to
    # walking the folders themselves.
    SCAN_COMMIT = 500
    _since = [0]
    _complete = True          # every configured folder was read to the end

    def _save(force=False):
        _since[0] += 0 if force else 1
        if not force and _since[0] < SCAN_COMMIT:
            return
        _since[0] = 0
        _db_commit_retry(db)
        try:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass          # a reader holding the WAL is normal; the next one gets it

    # ── Lean discovery ──
    # Insert new images with meta_done=0 and NO file opening (so images appear
    # instantly). Metadata, thumbnail and pHash are produced by the worker pool.
    # Only filesystem stat (file_date) + filename parsing happen here.
    for fi, sf in enumerate(folders):
        root = Path(sf["path"])
        if not root.exists() or not root.is_dir():
            # v4.38: a folder that is not there right now was NOT scanned, and
            # its images must not be counted as gone. A disconnected NAS is the
            # ordinary case here, and it used to empty the library.
            _complete = False
            log(f"Scan: {sf['path']} is not reachable \u2014 leaving its images alone", "warning")
            continue
        fname = root.name
        ftotal = folder_counts.get(sf["path"], 0)
        fprog = {"name": fname, "current": 0, "total": ftotal, "phase": "Scanning"}
        state.scan_progress["folders"].append(fprog)
        processed = 0

        for dirpath, dirnames, filenames in os.walk(root):
            _prune_dirs(dirpath, dirnames)          # v4.44
            if _skip_dir(dirpath):
                continue
            dirnames.sort()
            rel_folder = os.path.relpath(dirpath, root)
            if rel_folder == ".": rel_folder = "(Root)"
            display_folder = f"{root.name}\\{rel_folder}" if rel_folder != "(Root)" else root.name

            for filename in sorted(filenames):
                ext = Path(filename).suffix.lower()
                if ext not in MEDIA_EXTENSIONS: continue
                filepath = os.path.join(dirpath, filename)
                all_found.add(filepath)
                processed += 1
                fprog["current"] = processed
                if filepath in existing:
                    # Modified? Flag for re-processing by the worker pool (no inline read).
                    ex = existing[filepath]
                    cur_mt = get_file_date(filepath)
                    if ex["file_date"] and cur_mt and abs(cur_mt - (ex["file_date"] or 0)) > 1:
                        db.execute("UPDATE images SET file_date=?, meta_done=0 WHERE id=?",
                                   (cur_mt, ex["id"]))
                        total_modified += 1
                        _save()
                    continue

                file_date = get_file_date(filepath)
                mt = detect_media_type(filepath)  # ext-based (only sniffs animated webp)
                cur = db.execute(
                    "INSERT OR IGNORE INTO images (filename,folder,filepath,width,height,file_date,search_text,phash,media_type,meta_done) VALUES (?,?,?,?,?,?,?,?,?,0)",
                    (filename, display_folder, filepath, 0, 0, file_date, "", "", mt))
                iid = cur.lastrowid
                if iid == 0: continue
                total_new += 1
                _save()
        fprog["phase"] = "Done"

    _save(force=True)      # everything discovered is on disk before anything is removed

    # ── Removals ──
    # v4.38: only when the scan actually finished. Rows are deleted here because
    # their file was not seen -- but a folder that could not be read produces
    # exactly the same silence as a folder whose files are gone, and the two are
    # not the same thing. This is the failure that cost 5,000 images once; it is
    # not repeated on the strength of an interrupted walk.
    removed = set(existing.keys()) - all_found
    if not _complete:
        if removed:
            log(f"Scan did not reach every folder \u2014 {len(removed)} image(s) kept "
                f"that would otherwise have been removed. Run it again once all "
                f"folders are reachable.", "warning")
        removed = set()
    for fp in removed: db.execute("DELETE FROM images WHERE filepath=?", (fp,))
    if removed:
        db.execute("DELETE FROM characters WHERE id NOT IN (SELECT DISTINCT character_id FROM image_characters)")
        _mem_invalidate()   # v3.66: images removed -> RAM pair cache recomputes on demand
        db.execute("DELETE FROM thumb_cache WHERE image_id NOT IN (SELECT id FROM images)")
    _save(force=True)
    state.scan_progress = {"active": False, "folders": []}

    # Hand heavy work to the background pool (metadata/thumbnail/pHash).
    if _proc["auto"] and (total_new or total_modified):
        _proc_ensure_running(reset_progress=True)

    return {"new": total_new, "removed": len(removed), "modified": total_modified,
            "total": len(all_found), "pending": total_new + total_modified}


def _path_prefixes(root):
    """v4.26: every spelling of `root` an image filepath could have been stored
    under, as SQL LIKE prefixes. A path is not a string to compare -- the same
    folder reaches us as P:\\Photos, \\\\server\\share\\Photos or with a trailing
    separator, depending on how it was linked. SQLite LIKE is already
    case-insensitive for ASCII, so only the shape has to be covered here."""
    out, seen = [], set()

    def add(base):
        if not base:
            return
        base = base.rstrip("\\/")
        if not base or base in seen:
            return
        seen.add(base)
        out.append(base + os.sep + "%")
        out.append(base + "/%")

    add(root)
    try:
        add(os.path.normpath(root))
    except Exception:
        pass
    try:
        add(os.path.realpath(root))
    except Exception:
        pass
    # Windows: resolve a mapped drive to its UNC target and vice versa. This is
    # the case that wiped libraries -- the folder was linked as P:\... while the
    # rows had been imported as \\\\server\\share\\..., or the other way round.
    if os.name == "nt":
        try:
            import win32wnet
            add(win32wnet.WNetGetUniversalName(root, 1))
        except Exception:
            pass
    return out


def _orphan_ids(db, roots, limit=None):
    """v4.26: image ids that live under none of `roots`. Returns [] when roots is
    empty -- 'no linked folders' means 'nothing is known', never 'delete all'."""
    if not roots:
        return []
    clauses, params = [], []
    for r in roots:
        pre = _path_prefixes(r)
        if not pre:
            continue
        clauses.append("NOT (" + " OR ".join(["filepath LIKE ?"] * len(pre)) + ")")
        params += pre
    if not clauses:
        return []
    sql = "SELECT id FROM images WHERE " + " AND ".join(clauses)
    if limit:
        sql += " LIMIT %d" % int(limit)
    return [r[0] for r in db.execute(sql, params).fetchall()]


_orphan_notice = {"count": 0, "checked": False}   # surfaced by /api/orphans


def _sweep_orphan_images():
    """v4.26: finish an unlink that was interrupted -- and nothing else.

    v3.87 removed every image row that did not match a linked folder by string
    prefix. That inverted test made a normal start destructive: a folder linked
    as a mapped drive stores rows under its UNC path (or the reverse), matches
    no prefix, and the whole library was deleted before the window even opened.
    An empty scan_folders table deleted everything outright.

    The sweep now runs only while pending_unlink names the folder that was being
    removed, and only deletes rows under THAT folder. Anything else is reported,
    never deleted -- see _scan_orphans_async(). Returns the number of rows removed."""
    try:
        db = _get_thread_db()
        try:
            pend = [r[0] for r in db.execute("SELECT root FROM pending_unlink").fetchall()]
        except Exception:
            pend = []          # table missing (older DB) -> nothing was interrupted
        if not pend:
            db.close()
            return 0

        total = db.execute("SELECT COUNT(*) FROM images").fetchone()[0]
        ids = []
        for root in pend:
            pre = _path_prefixes(root)
            if not pre:
                continue
            q = "SELECT id FROM images WHERE " + " OR ".join(["filepath LIKE ?"] * len(pre))
            ids += [r[0] for r in db.execute(q, pre).fetchall()]
        ids = list(dict.fromkeys(ids))

        # The brake. An interrupted unlink of one folder cannot legitimately
        # account for most of the library; if it looks like it does, something
        # is wrong with the paths and the rows stay put.
        if ids and total and len(ids) / total > _SWEEP_MAX_SHARE and len(ids) > 1000:
            log("Unlink cleanup skipped as a precaution: %d of %d image rows matched "
                "'%s'. Nothing was deleted \u2014 use Settings \u203a Maintenance to review."
                % (len(ids), total, pend[0]), "warning")
            _orphan_notice.update({"count": len(ids), "checked": True})
            db.close()
            return 0

        if ids:
            log("Finishing an interrupted unlink: removing %d image row(s) "
                "\u2014 files on disk are untouched" % len(ids))
            _wipe_images_by_ids(db, ids)
            with _db_write_lock:
                db.execute("DELETE FROM characters WHERE id NOT IN "
                           "(SELECT DISTINCT character_id FROM image_characters)")
                _db_commit_retry(db)
        with _db_write_lock:
            db.execute("DELETE FROM pending_unlink")
            _db_commit_retry(db)
        db.close()
        return len(ids)
    except Exception as e:
        log("orphan sweep failed: %s" % e, "warning")
        return 0


def _scan_orphans_async():
    """v4.26: count rows that match no linked folder and say so -- in the
    background, after the server is up. This used to happen inline at startup
    as a full table scan, which on a large library kept the port closed for
    long enough that the launcher gave up and the app looked frozen. It never
    deletes; the count is offered in Settings and the user decides."""
    def _run():
        try:
            _time.sleep(2.0)                      # let the first page load finish
            db = _get_thread_db()
            try:
                roots = [r["path"] for r in db.execute("SELECT path FROM scan_folders").fetchall()]
                n = len(_orphan_ids(db, roots)) if roots else 0
                _orphan_notice.update({"count": n, "checked": True})
                if n:
                    log("%d image row(s) match no linked folder. Nothing was deleted \u2014 "
                        "Settings \u203a Maintenance can clean them up." % n, "warning")
            finally:
                db.close()
        except Exception as e:
            log("orphan check failed: %s" % e, "warning")
    threading.Thread(target=_run, daemon=True, name="orphan-check").start()


def _wipe_images_by_ids(db, ids, progress=None, chunk=5000):
    """v3.24: delete the given image ids fast. Files on disk are NEVER touched.
    The image rows are removed in COMMITTED chunks (cascading to thumb_cache BLOBs and
    image_characters), so progress is visible and an interruption keeps what was already
    removed. Deleting the folder's duplicate pairs row-by-row would maintain three
    indexes per deleted row -- millions of operations for a lenient MAX_DUP_DIST, which
    was the old slow unlink. Since v3.66 duplicate pairs live in RAM, so only the
    in-memory cache is invalidated; the caller
    kicks off the background pass, which rebuilds the pairs with the v3.22 bulk path.
    The user-visible delete is therefore bounded only by removing the images + their
    thumbnails, not by the pair count."""
    total = len(ids)
    done = 0
    log(f"Unlink: removing {total:,} images (files on disk are untouched)…")
    for k in range(0, total, chunk):
        part = ids[k:k + chunk]
        ph = ",".join("?" * len(part))
        with _db_write_lock:
            db.execute(f"DELETE FROM images WHERE id IN ({ph})", part)   # cascade -> thumb_cache BLOBs + image_characters
            _db_commit_retry(db)
        done += len(part)
        if progress is not None:
            progress["current"] = done
    _mem_invalidate()   # v3.66: RAM pair cache recomputes on next Duplicates view
    log(f"Unlink: {done:,} images removed")
    return done


def _purge_own_folder_rows():
    """v4.44: forget images that were read out of TrackImage's own folder.

    Before this version a scan would walk into Databank/.trash if TrackImage had
    been installed inside the library, so pictures the user had deleted came back
    as .trash\\... rows -- and showed up as duplicates of the ones he kept. The
    rows are removed here; the FILES are not touched. What is in the trash stays
    in the trash and leaves on its usual timer, so this cannot lose anything that
    a restore would have brought back.
    """
    db = get_db()
    try:
        rows = db.execute("SELECT id, filepath FROM images").fetchall()
    except Exception:
        return
    gone = [r["id"] for r in rows if r["filepath"] and _skip_file(r["filepath"])]
    if not gone:
        return
    try:
        for i in range(0, len(gone), 400):        # bounded, never one big IN list
            chunk = gone[i:i + 400]
            ph = ",".join("?" * len(chunk))
            db.execute(f"DELETE FROM images WHERE id IN ({ph})", chunk)
        db.execute("DELETE FROM thumb_cache WHERE image_id NOT IN (SELECT id FROM images)")
        db.execute("DELETE FROM characters WHERE id NOT IN "
                   "(SELECT DISTINCT character_id FROM image_characters)")
        _db_commit_retry(db)
        _mem_invalidate()
        log(f"Removed {len(gone)} library entr{'y' if len(gone) == 1 else 'ies'} that "
            f"pointed inside TrackImage's own folder (deleted pictures read back "
            f"out of the trash). The files themselves were left alone.", "warning")
    except Exception as e:
        log(f"Could not clean up entries from TrackImage's own folder: "
            f"{type(e).__name__}: {e}", "warning")
