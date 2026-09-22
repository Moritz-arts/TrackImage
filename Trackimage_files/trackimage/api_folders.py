"""Routes: folders, scanning and import.

Layer 22 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, g, make_response, Response
)
from pathlib import Path
import os
import shutil
import threading
import time as _time
from . import state
from .config import MEDIA_EXTENSIONS, app, detect_media_type
from .logging_setup import log
from .platform_bits import _is_network_path, _move_file_safely
from .db import _db_commit_retry, _db_write_lock, _folder_op_lock, _get_thread_db, _natural_sort_key, folder_op, get_db
from .events import sse_notify
from .media import _free_filename, _safe_dropped_name, get_file_date, resolve_display_folder
from .metadata import find_sidecar, move_sidecar_with
from .processing import _proc, _proc_ensure_running, _proc_save_setting, _unlink_progress
from .tagger import _tag_ensure_running, _tag_save_cfg
from .duplicates import _mem_invalidate
from .scanning import _AUTOSYNC, _incremental_sync, _orphan_ids, _orphan_notice, _prune_dirs, _skip_dir, _sync_paths, _wipe_images_by_ids, restart_watcher, scan_all_folders, start_watcher, stop_watcher
from .picker import _PICKER_CODE_TK, _PICKER_CODE_WIN, _picker_env, _run_picker
from .importing import _library_row_for_path, _native_drop, _native_drop_lock, _paths_for_ids, _report_import_dupes, clipboard_image_png, clipboard_read
from .network import _is_local_request


@app.route("/api/pick-folder", methods=["POST"])
def api_pick_folder():
    """Ask for a folder, trying every dialog this machine has.

    Answers {"manual": true} when none of them worked, which is the page's cue
    to offer typing the path instead rather than leaving the user stuck.
    """
    attempts = []
    if os.name == "nt":
        attempts.append(("The Windows folder dialog", _PICKER_CODE_WIN, None))
    attempts.append(("The Tk folder dialog", _PICKER_CODE_TK, _picker_env()))

    # v4.47: every reason is kept. Reporting only the last one hid why the
    # Windows dialog had refused, which is the half that actually explains what
    # is wrong with the machine.
    problems = []
    for label, code, env in attempts:
        try:
            code_returned, folder, err = _run_picker(code, env)
        except Exception as e:
            problems.append(f"{label} could not start ({type(e).__name__})")
            log(problems[-1], "warning")
            continue
        if folder:
            return jsonify({"path": folder.replace("/", os.sep)})
        if code_returned == 0:
            return jsonify({"path": ""})            # user cancelled
        lines = [ln for ln in err.splitlines() if ln.strip()]
        problems.append(f"{label} failed: {lines[-1]}" if lines else f"{label} failed")
        log(problems[-1], "warning")
    return jsonify({"error": ". ".join(problems) or "No folder dialog is available "
                                                   "on this computer",
                    "manual": True}), 500


@app.route("/api/scan-folders", methods=["GET","POST"])
def api_scan_folders():
    db = get_db()
    if request.method == "POST":
        # POST mutates -> serialize like every other folder op. GET (list) stays free.
        if not _folder_op_lock.acquire(blocking=False):
            return jsonify({"error": "Another folder operation is in progress — please wait for it to finish."}), 409
        try:
            data = request.get_json()
            path = data.get("path","").strip().strip('"')
            if not path: return jsonify({"error": "No path provided"}), 400
            # v4.46: a path can be typed by hand, so a typo is caught before the
            # folder is stored and sits in the list scanning nothing.
            #
            # v4.47: without asking the file system anything it does not have to.
            # resolve() walked the path on disk and rewrote a junction or symlink
            # to its target, storing a library under a name the user never chose.
            # normpath+abspath is pure string work and leaves links alone.
            try:
                path = os.path.normpath(os.path.abspath(os.path.expanduser(path)))
            except Exception:
                return jsonify({"error": f"That path cannot be read: {path}"}), 400
            # v4.47: a network folder is taken on trust. isdir() on one that is
            # away costs an SMB timeout and then says no -- with the folder lock
            # held -- so a library on a NAS could not be linked while the NAS was
            # offline, which is the moment a fresh install most needs to record
            # it. Being unreachable is not the same as not existing.
            if _is_network_path(path):
                if not os.path.isdir(path):
                    log(f"{path} is not reachable right now — linking it anyway, "
                        f"it will be scanned once it comes back", "warning")
            else:
                if not os.path.isdir(path):
                    return jsonify({"error": f"Not a folder: {path}"}), 400
                if not os.access(path, os.R_OK):
                    return jsonify({"error": f"No permission to read {path}"}), 403
            label = Path(path).name or path
            with _db_write_lock:
                db.execute("INSERT OR IGNORE INTO scan_folders (path, label) VALUES (?,?)", (path, label))
                _db_commit_retry(db)
            restart_watcher()
            return jsonify({"ok": True})
        finally:
            _folder_op_lock.release()
    rows = db.execute("SELECT id, path, label FROM scan_folders ORDER BY natural_key(label)").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/scan-folders/<int:folder_id>", methods=["DELETE"])
@folder_op
def api_delete_scan_folder(folder_id):
    db = get_db()
    row = db.execute("SELECT path FROM scan_folders WHERE id=?", (folder_id,)).fetchone()
    with _db_write_lock:
        if row:
            root = row["path"]
            like_a = root + os.sep + "%"
            like_b = root + "/%"
            # Internal removal only — files on disk are not touched. Purge couples
            # first (no FK), then cascade thumb_cache + image_characters via image delete.
            _mem_invalidate()   # v3.66: RAM pair cache recomputes on demand
            db.execute("DELETE FROM images WHERE filepath LIKE ? OR filepath LIKE ?", (like_a, like_b))
            db.execute("DELETE FROM characters WHERE id NOT IN (SELECT DISTINCT character_id FROM image_characters)")
        db.execute("DELETE FROM scan_folders WHERE id=?", (folder_id,))
        _db_commit_retry(db)
    restart_watcher()
    return jsonify({"ok": True})


@app.route("/api/scan", methods=["POST"])
@folder_op
def api_scan():
    return jsonify(scan_all_folders())


@app.route("/api/scan-progress")
def api_scan_progress():
    return jsonify(state.scan_progress)


@app.route("/api/autosync", methods=["GET", "POST"])
def api_autosync():
    # v3.61: ONE switch for watcher + auto-processing + auto-tagging.
    if request.method == "POST":
        on = bool((request.get_json() or {}).get("on", True))
        _AUTOSYNC["on"] = on
        _tag_save_cfg("autosync", "1" if on else "0")
        _proc["auto"] = on
        _proc_save_setting("proc_auto", "1" if on else "0")
        _tag_save_cfg("tag_enabled", "1" if on else "0")
        if on:
            threading.Thread(target=_incremental_sync, daemon=True).start()  # catch up
            _proc_ensure_running(reset_progress=False)
            _tag_ensure_running()
    return jsonify({"on": _AUTOSYNC["on"]})


@app.route("/api/refresh-folder", methods=["POST"])
def api_refresh_folder():
    # v3.61: manual, scoped sync — ONLY the given display folder + its subfolders.
    disp = ((request.get_json() or {}).get("folder") or "").strip()
    if not disp: return jsonify({"error": "No folder"}), 400
    root = resolve_display_folder(disp)
    if not root or not os.path.isdir(root):
        return jsonify({"error": "Folder not found on disk"}), 404
    paths = set()
    for dirpath, _dirs, files in os.walk(root):
        _prune_dirs(dirpath, _dirs)                 # v4.44
        for f in files:
            if os.path.splitext(f)[1].lower() in MEDIA_EXTENSIONS:
                paths.add(os.path.join(dirpath, f))
    db = get_db()
    for r in db.execute("SELECT filepath FROM images WHERE folder=? OR folder LIKE ?",
                        (disp, disp + "\\%")).fetchall():
        paths.add(r["filepath"])   # deleted files get removed by the diff sync
    def _run(pl):
        _sync_paths(pl)
        _proc_ensure_running(reset_progress=False)   # one catch-up pass
        if _AUTOSYNC["on"]: _tag_ensure_running()
    threading.Thread(target=_run, args=(sorted(paths),), daemon=True).start()
    return jsonify({"ok": True, "checked": len(paths)})


@app.route("/api/unlink-folder", methods=["POST"])
def api_unlink_folder():
    # v3.20: kick off the wipe in a BACKGROUND thread so the HTTP request returns
    # immediately and the UI is never blocked. We grab the folder-op lock here and
    # release it inside the worker's finally (so no concurrent link/unlink).
    data = request.get_json()
    folder = data.get("folder", "").strip()
    if not folder: return jsonify({"error": "No folder"}), 400
    real_path = resolve_display_folder(folder)
    if not real_path: return jsonify({"error": "Folder not found"}), 404
    if _unlink_progress.get("active"):
        return jsonify({"error": "An unlink is already running — please wait for it to finish."}), 409
    if not _folder_op_lock.acquire(blocking=False):
        return jsonify({"error": "Another folder operation is in progress — please wait for it to finish."}), 409
    try:
        db = get_db()
        roots = [r["path"] for r in db.execute("SELECT path FROM scan_folders").fetchall()]
        unlink_root = None
        if real_path in roots:
            unlink_root = real_path
        else:
            for r in roots:
                if real_path.startswith(r + os.sep):
                    unlink_root = r
                    break
        if not unlink_root:
            _folder_op_lock.release()
            return jsonify({"error": "Not a linked folder"}), 400
        like_a = unlink_root + os.sep + "%"
        like_b = unlink_root + "/%"
        ids = [row[0] for row in db.execute(
            "SELECT id FROM images WHERE filepath LIKE ? OR filepath LIKE ?", (like_a, like_b)).fetchall()]
    except Exception as e:
        try: _folder_op_lock.release()
        except Exception: pass
        return jsonify({"error": f"Unlink failed: {e}"}), 500

    _unlink_progress.update({"active": True, "current": 0, "total": len(ids),
                             "phase": "Unlinking", "root": unlink_root})

    def _bg():
        prev_paused = _proc.get("paused", False)
        try:
            _proc["paused"] = True   # let the wipe own the write lock; avoid racing image/thumb rows
            wdb = _get_thread_db()
            # v3.87: unregister the folder BEFORE the wipe. The wipe is the slow part
            # and this thread is a daemon -- a reload or restart in the middle used to
            # leave scan_folders intact, so the watcher picked the folder up again on
            # the next start and re-imported everything. Leftover image rows are
            # handled by the startup sweep instead, which is the harmless direction.
            # v4.26: record WHICH folder is being removed, committed on its own
            # before anything is deleted. If this thread dies mid-wipe, the next
            # start finds the marker and finishes exactly this folder -- instead
            # of guessing from "matches no linked folder", which used to take the
            # whole library with it when a path was spelled differently.
            with _db_write_lock:
                wdb.execute("INSERT OR REPLACE INTO pending_unlink (root, started_at) VALUES (?, ?)",
                            (unlink_root, _time.time()))
                _db_commit_retry(wdb)
            with _db_write_lock:
                wdb.execute("DELETE FROM scan_folders WHERE path=?", (unlink_root,))
                _db_commit_retry(wdb)
            _wipe_images_by_ids(wdb, ids, _unlink_progress)
            with _db_write_lock:
                wdb.execute("DELETE FROM characters WHERE id NOT IN (SELECT DISTINCT character_id FROM image_characters)")
                wdb.execute("DELETE FROM pending_unlink WHERE root=?", (unlink_root,))   # v4.26: done
                _db_commit_retry(wdb)
            # v3.23: a folder unlink frees a lot of pages (pairs + thumbnail BLOBs).
            # Checkpoint + truncate the WAL so that space is reclaimed before the next
            # operation -- otherwise re-adding the same folder writes into a bloated WAL
            # and feels slower than adding a fresh folder.
            try:
                with _db_write_lock:
                    wdb.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception: pass
            wdb.close()
            restart_watcher()
            print(f"  \u25c8 Unlinked {unlink_root} ({len(ids)} images)")
        except Exception as e:
            print(f"  \u26a0 unlink error: {e}")
        finally:
            _unlink_progress.update({"active": False, "current": 0, "total": 0, "phase": "", "root": ""})
            _proc["paused"] = prev_paused
            try: _folder_op_lock.release()
            except Exception: pass
            try: sse_notify("unlink_done", {"root": unlink_root})
            except Exception: pass
            try: _mem_invalidate()   # v3.66: RAM pair cache recomputes on demand
            except Exception: pass
            try:
                if _proc.get("auto"): _proc_ensure_running()
            except Exception: pass

    threading.Thread(target=_bg, daemon=True, name="unlink").start()
    return jsonify({"ok": True, "started": True, "count": len(ids), "unlinked": unlink_root})


@app.route("/api/create-folder", methods=["POST"])
@folder_op
def api_create_folder():
    data = request.get_json()
    parent = data.get("parent", "").strip()
    name = data.get("name", "").strip()
    if not name: return jsonify({"error": "No name provided"}), 400
    invalid = set('<>:"/\\|?*')
    if any(c in invalid for c in name): return jsonify({"error": "Invalid characters in name"}), 400
    if parent:
        real_parent = resolve_display_folder(parent)
        if not real_parent or not os.path.isdir(real_parent):
            return jsonify({"error": "Parent folder not found"}), 404
    else:
        db = get_db()
        folders = db.execute("SELECT path FROM scan_folders").fetchall()
        if not folders: return jsonify({"error": "No scan folders configured"}), 400
        real_parent = folders[0]["path"]
    new_path = os.path.join(real_parent, name)
    if os.path.exists(new_path): return jsonify({"error": "Folder already exists"}), 409
    try: os.makedirs(new_path, exist_ok=True)
    except OSError as e: return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True, "path": new_path})


@app.route("/api/delete-folder", methods=["POST"])
@folder_op
def api_delete_folder():
    data = request.get_json()
    folder = data.get("folder", "").strip()
    if not folder: return jsonify({"error": "No folder"}), 400
    real_path = resolve_display_folder(folder)
    if not real_path or not os.path.isdir(real_path):
        return jsonify({"error": "Folder not found on disk"}), 404
    db = get_db()
    roots = [r["path"] for r in db.execute("SELECT path FROM scan_folders").fetchall()]
    is_root = real_path in roots
    file_count = 0
    for dp, dn, fns in os.walk(real_path):
        file_count += len(fns)
    # Stop watcher first — it holds file handles on Windows which block rmtree
    stop_watcher()
    try:
        shutil.rmtree(real_path)
    except OSError as e:
        start_watcher()
        return jsonify({"error": str(e)}), 500
    db.execute("DELETE FROM images WHERE filepath LIKE ? OR filepath LIKE ?",
        (real_path + os.sep + "%", real_path + "/%"))
    if is_root:
        db.execute("DELETE FROM scan_folders WHERE path=?", (real_path,))
    db.execute("DELETE FROM characters WHERE id NOT IN (SELECT DISTINCT character_id FROM image_characters)")
    _mem_invalidate()   # v3.66: images removed -> RAM pair cache recomputes on demand
    _db_commit_retry(db)
    start_watcher()
    return jsonify({"ok": True, "deleted_files": file_count})


@app.route("/api/folders/bulk-delete", methods=["POST"])
@folder_op
def api_bulk_delete_folders():
    data = request.get_json() or {}
    folders = data.get("folders", [])
    if not folders: return jsonify({"error": "No folders"}), 400
    db = get_db()
    roots = [r["path"] for r in db.execute("SELECT path FROM scan_folders").fetchall()]
    # Resolve all first, reject on any failure
    resolved = []
    for f in folders:
        rp = resolve_display_folder(f.strip())
        if not rp or not os.path.isdir(rp):
            return jsonify({"error": f"Folder not found: {f}"}), 404
        resolved.append((f.strip(), rp))
    # Stop watcher once for the whole batch
    stop_watcher()
    total_files = 0
    deleted = []
    errors = []
    for display, rp in resolved:
        try:
            fc = 0
            for dp, dn, fns in os.walk(rp):
                fc += len(fns)
            shutil.rmtree(rp)
            total_files += fc
            deleted.append(display)
            db.execute("DELETE FROM images WHERE filepath LIKE ? OR filepath LIKE ?",
                       (rp + os.sep + "%", rp + "/%"))
            if rp in roots:
                db.execute("DELETE FROM scan_folders WHERE path=?", (rp,))
        except OSError as e:
            errors.append(f"{display}: {e}")
    db.execute("DELETE FROM characters WHERE id NOT IN (SELECT DISTINCT character_id FROM image_characters)")
    _mem_invalidate()   # v3.66: images removed -> RAM pair cache recomputes on demand
    _db_commit_retry(db)
    start_watcher()
    return jsonify({"ok": True, "deleted": deleted, "deleted_files": total_files, "errors": errors})


@app.route("/api/import/native-drop", methods=["POST"])
def api_import_native_drop():
    """Import by moving the real files, when their paths are known.

    Answers {"ok": false, "reason": "no-paths"} whenever they are not, which is
    the page's signal to fall back to uploading the bytes instead.
    """
    data = request.get_json(silent=True) or {}
    names = [str(n) for n in (data.get("names") or [])][:500]
    display = (data.get("folder") or "").strip()
    keep_original = bool(data.get("copy"))          # Ctrl held: copy, do not move
    if not names or not display:
        return jsonify({"ok": False, "reason": "no-paths"})
    if not state.NATIVE_DROP_OK:
        return jsonify({"ok": False, "reason": "no-paths"})

    # The page can get here before pywebview's handler has run, so give it a
    # moment. Both are reacting to the same drop; the order is not fixed.
    deadline = _time.time() + 1.5
    matched = None
    while _time.time() < deadline:
        with _native_drop_lock:
            fresh = (_time.time() - _native_drop["ts"]) < 5.0
            files = list(_native_drop["files"])
        if fresh and len(files) == len(names) and \
                sorted(f["name"] for f in files) == sorted(names):
            matched = files
            break
        _time.sleep(0.05)
    if matched is None:
        return jsonify({"ok": False, "reason": "no-paths"})
    with _native_drop_lock:                 # one drop is used once
        _native_drop["ts"] = 0.0
        _native_drop["files"] = []

    target = resolve_display_folder(display)
    if not target or not os.path.isdir(target):
        return jsonify({"error": f"Folder not found: {display}"}), 404
    if not os.access(target, os.W_OK):
        return jsonify({"error": f"No permission to write into {display}"}), 403
    return jsonify(_import_local_files(get_db(), display, target, matched, keep_original))


def _import_local_files(db, display, target, matched, keep_original):
    """Bring files that already sit on this machine into a library folder --
    moved, or copied when keep_original. Shared by a drop whose paths pywebview
    reported and by a paste of what Explorer put on the clipboard, so a file
    arrives the same way whichever road it took."""
    added, skipped, new_ids, undo, relocated = [], [], [], [], []
    for f in matched:
        src, raw_name = f["path"], _safe_dropped_name(f["name"])
        if not os.path.isfile(src):
            skipped.append({"name": raw_name, "why": "the file is no longer there"})
            continue
        if os.path.splitext(raw_name)[1].lower() not in MEDIA_EXTENSIONS:
            skipped.append({"name": raw_name, "why": "not an image or video TrackImage handles"})
            continue
        if os.path.abspath(os.path.dirname(src)) == os.path.abspath(target):
            skipped.append({"name": raw_name, "why": "it is already in this folder"})
            continue

        # L1: a file the library already knows is not a new import -- it is the
        # same picture changing folder. Copying it in would leave the old row
        # pointing at a file that is gone and add a second row beside it.
        known = None if keep_original else _library_row_for_path(db, src)
        name = _free_filename(target, raw_name)
        dest = os.path.join(target, name)
        try:
            if keep_original:
                shutil.copy2(src, dest)
                how = "copy"
                # v4.53: a copy takes its sidecar along too, or the copy arrives
                # without the metadata the original had.
                _side = find_sidecar(src)
                if _side:
                    try:
                        shutil.copy2(_side, dest + ".xmp")
                    except Exception:
                        pass
            else:
                _ok, how = _move_file_safely(src, dest)
                move_sidecar_with(src, dest)
        except Exception as e:
            skipped.append({"name": raw_name,
                            "why": f"could not be {'copied' if keep_original else 'moved'} "
                                   f"({type(e).__name__}: {e})"})
            continue

        if known:
            try:
                db.execute("UPDATE images SET filename=?, folder=?, filepath=? WHERE id=?",
                           (name, display, dest, known["id"]))
                relocated.append({"id": known["id"], "old_folder": known["folder"],
                                  "name": name})
                added.append({"name": name, "renamed": name != raw_name, "moved": True,
                              "from_library": True})
                continue
            except Exception as e:
                skipped.append({"name": raw_name, "why": f"could not be recorded ({type(e).__name__})"})
                continue
        try:
            cur = db.execute(
                "INSERT OR IGNORE INTO images (filename,folder,filepath,width,height,"
                "file_date,search_text,phash,media_type,meta_done) VALUES (?,?,?,?,?,?,?,?,?,0)",
                (name, display, dest, 0, 0, get_file_date(dest), "", "", detect_media_type(dest)))
            if cur.lastrowid:
                new_ids.append(cur.lastrowid)
                if not keep_original:
                    # S2: enough to put the file back exactly where it came from.
                    undo.append({"id": cur.lastrowid, "src": src, "dest": dest})
            added.append({"name": name, "renamed": name != raw_name,
                          "moved": not keep_original, "how": how})
        except Exception as e:
            skipped.append({"name": raw_name, "why": f"could not be recorded ({type(e).__name__})"})

    _db_commit_retry(db)
    try:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass
    dupes = _report_import_dupes(db, new_ids, display)
    if new_ids or relocated:
        _db_commit_retry(db)
        _mem_invalidate()
    if added:
        log(f"{'Copied' if keep_original else 'Moved'} {len(added)} file(s) into {display}",
            "success")
    for sk in skipped:
        log(f"Not imported: {sk['name']} \u2014 {sk['why']}", "warning")
    if new_ids and _proc["auto"]:
        _proc_ensure_running(reset_progress=True)
    return {"ok": True, "added": added, "skipped": skipped, "duplicates": dupes,
            "folder": display, "moved": not keep_original,
            "undo": undo, "relocated": relocated}


@app.route("/api/os-clipboard")
def api_os_clipboard():
    """What a paste would bring in from outside. ids= names the page's own
    clipboard, so it can tell a copy made here from one made elsewhere since --
    the same files coming back are still its own."""
    if not _is_local_request():
        return jsonify({"sig": "", "count": 0, "image": False, "ours": False})
    c = clipboard_read()
    files = [f for f in c["files"] if os.path.isfile(f)]
    media = [f for f in files if os.path.splitext(f)[1].lower() in MEDIA_EXTENSIONS]
    ids = [int(i) for i in (request.args.get("ids") or "").split(",") if i.isdigit()][:500]
    ours = False
    if ids and files:
        norm = lambda l: sorted(os.path.normcase(os.path.abspath(x)) for x in l)
        ours = norm(files) == norm(_paths_for_ids(ids))
    return jsonify({"sig": c["sig"], "count": len(media), "other": len(files) - len(media),
                    "names": [os.path.basename(f) for f in media[:3]], "move": c["move"],
                    "image": bool(c["image"] and not files), "ours": ours})


@app.route("/api/os-clipboard/paste", methods=["POST"])
def api_os_clipboard_paste():
    """Paste what was copied outside TrackImage into a library folder: files are
    copied (moved after a Cut in Explorer, as Explorer itself would), a bare
    picture -- a screenshot, "Copy image" in a browser -- is written as a PNG."""
    if not _is_local_request():
        return jsonify({"error": "The clipboard belongs to the computer TrackImage runs on"}), 403
    display = ((request.get_json(silent=True) or {}).get("folder") or "").strip()
    target = resolve_display_folder(display) if display else None
    if not target or not os.path.isdir(target):
        return jsonify({"error": f"Folder not found: {display or '(none)'}"}), 404
    if not os.access(target, os.W_OK):
        return jsonify({"error": f"No permission to write into {display}"}), 403
    c = clipboard_read()
    files = [{"name": os.path.basename(f), "path": f} for f in c["files"][:500] if os.path.isfile(f)]
    if files:
        return jsonify(_import_local_files(get_db(), display, target, files, not c["move"]))
    png = clipboard_image_png() if c["image"] or os.name != "nt" else None
    if not png:
        return jsonify({"error": "Nothing on the clipboard to paste — copy a picture or a file first"}), 400
    name = _free_filename(target, _time.strftime("Pasted %Y-%m-%d %H%M%S.png"))
    dest = os.path.join(target, name)
    with open(dest, "wb") as fh:
        fh.write(png)
    db = get_db()
    cur = db.execute(
        "INSERT OR IGNORE INTO images (filename,folder,filepath,width,height,"
        "file_date,search_text,phash,media_type,meta_done) VALUES (?,?,?,?,?,?,?,?,?,0)",
        (name, display, dest, 0, 0, get_file_date(dest), "", "", "image"))
    new_ids = [cur.lastrowid] if cur.lastrowid else []
    _db_commit_retry(db)
    dupes = _report_import_dupes(db, new_ids, display)
    if new_ids:
        _db_commit_retry(db)
        _mem_invalidate()
    log(f"Pasted a picture into {display} as {name}", "success")
    if new_ids and _proc["auto"]:
        _proc_ensure_running(reset_progress=True)
    return jsonify({"ok": True, "added": [{"name": name, "renamed": False}], "skipped": [],
                    "duplicates": dupes, "folder": display})


@app.route("/api/import/undo-move", methods=["POST"])
def api_import_undo_move():
    """Put moved-in files back where they came from and forget them again.

    The reverse of the move above, and just as careful: the row is only dropped
    once the file is safely back at its old path.
    """
    data = request.get_json(silent=True) or {}
    entries = data.get("entries") or []
    db = get_db()
    back, failed = 0, []
    for e in entries[:500]:
        iid, src, dest = e.get("id"), e.get("src") or "", e.get("dest") or ""
        if not src or not dest:
            continue
        try:
            if not os.path.isfile(dest):
                failed.append(os.path.basename(dest) + " is no longer in the library")
                continue
            if os.path.exists(src):
                src = os.path.join(os.path.dirname(src),
                                   _free_filename(os.path.dirname(src), os.path.basename(src)))
            _move_file_safely(dest, src)
            move_sidecar_with(dest, src)     # v4.53: back where it came from
            if iid:
                db.execute("DELETE FROM images WHERE id=?", (iid,))
            back += 1
        except Exception as ex:
            failed.append(f"{os.path.basename(dest)} ({type(ex).__name__})")
    _db_commit_retry(db)
    _mem_invalidate()
    return jsonify({"ok": True, "restored": back, "failed": failed})


@app.route("/api/import-files", methods=["POST"])
def api_import_files():
    """v4.39: drop files onto the gallery and they land in the library.

    The file is written into the folder that is open on screen (T1), so where it
    appears in TrackImage and where it sits on disk are the same place. Nothing
    is overwritten (N1) and nothing is moved out from under the user -- a file
    that already lives on this machine is copied, and the original stays where
    it was (V1). From there it goes through the same pipeline as anything the
    scan finds: metadata, thumbnail, pHash, and auto-tagging if it is switched
    on. Once the pHash is known, matches already in the library are reported
    (D1) -- reported, never acted on.
    """
    display = (request.form.get("folder") or "").strip()
    if not display:
        return jsonify({"error": "No target folder given"}), 400
    target = resolve_display_folder(display)
    if not target or not os.path.isdir(target):
        return jsonify({"error": f"Folder not found: {display}"}), 404
    if not os.access(target, os.W_OK):
        return jsonify({"error": f"No permission to write into {display}"}), 403

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "Nothing to import"}), 400

    db = get_db()
    added, skipped, new_ids = [], [], []
    for f in files:
        raw_name = _safe_dropped_name(f.filename)
        ext = os.path.splitext(raw_name)[1].lower()
        if ext not in MEDIA_EXTENSIONS:
            skipped.append({"name": raw_name, "why": "not an image or video TrackImage handles"})
            continue
        name = _free_filename(target, raw_name)
        dest = os.path.join(target, name)
        try:
            f.save(dest)
        except Exception as e:
            skipped.append({"name": raw_name, "why": f"could not be written ({type(e).__name__})"})
            continue
        try:
            cur = db.execute(
                "INSERT OR IGNORE INTO images (filename,folder,filepath,width,height,"
                "file_date,search_text,phash,media_type,meta_done) VALUES (?,?,?,?,?,?,?,?,?,0)",
                (name, display, dest, 0, 0, get_file_date(dest), "", "", detect_media_type(dest)))
            if cur.lastrowid:
                new_ids.append(cur.lastrowid)
            added.append({"name": name, "renamed": name != raw_name})
        except Exception as e:
            skipped.append({"name": raw_name, "why": f"could not be recorded ({type(e).__name__})"})

    _db_commit_retry(db)
    try:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        pass

    dupes = _report_import_dupes(db, new_ids, display)

    if new_ids:
        _db_commit_retry(db)
        _mem_invalidate()

    if added:
        log(f"Imported {len(added)} file(s) into {display}", "success")
    for sk in skipped:
        log(f"Not imported: {sk['name']} \u2014 {sk['why']}", "warning")

    # Metadata, thumbnail and auto-tagging, exactly as after a scan.
    if new_ids and _proc["auto"]:
        _proc_ensure_running(reset_progress=True)

    return jsonify({"ok": True, "added": added, "skipped": skipped,
                    "duplicates": dupes, "folder": display})


@app.route("/api/import-targets")
def api_import_targets():
    """Every folder a dropped file could go into.

    Used when nothing is selected in the sidebar -- there is no obvious target
    then, and guessing one would put files somewhere the user did not look.
    """
    db = get_db()
    out = []
    for sf in db.execute("SELECT path FROM scan_folders").fetchall():
        root = sf["path"]
        if not os.path.isdir(root):
            continue
        rn = Path(root).name
        out.append({"display": rn, "path": root})
        for dirpath, dirnames, _fn in os.walk(root):
            _prune_dirs(dirpath, dirnames)          # v4.44
            dirnames.sort()
            for d in dirnames:
                full = os.path.join(dirpath, d)
                rel = os.path.relpath(full, root).replace(os.sep, "\\")
                out.append({"display": rn + "\\" + rel, "path": full})
            if len(out) > 4000:
                break
    return jsonify({"folders": out})


@app.route("/api/folders/bulk-move", methods=["POST"])
@folder_op
def api_bulk_move_folders():
    data = request.get_json() or {}
    folders = data.get("folders", [])
    target = data.get("target", "").strip()
    if not folders or not target: return jsonify({"error": "Missing data"}), 400
    target_path = resolve_display_folder(target)
    if not target_path or not os.path.isdir(target_path):
        return jsonify({"error": "Target folder not found"}), 404
    db = get_db()
    roots = [r["path"] for r in db.execute("SELECT path FROM scan_folders").fetchall()]
    # Resolve sources
    sources = []
    for f in folders:
        rp = resolve_display_folder(f.strip())
        if not rp or not os.path.isdir(rp):
            return jsonify({"error": f"Folder not found: {f}"}), 404
        # Cannot move a folder into itself or its descendant
        if target_path == rp or target_path.startswith(rp + os.sep):
            return jsonify({"error": f"Cannot move '{f}' into itself"}), 400
        if rp in roots:
            return jsonify({"error": f"Cannot move a linked root folder ('{f}'). Unlink first."}), 400
        sources.append((f.strip(), rp))
    stop_watcher()
    moved = []
    errors = []
    for display, rp in sources:
        name = os.path.basename(rp)
        new_path = os.path.join(target_path, name)
        if os.path.exists(new_path):
            errors.append(f"{display}: target already has '{name}'")
            continue
        try:
            shutil.move(rp, new_path)
            moved.append(display)
            # Update all images under this folder
            old_prefix_bs = rp + "\\"
            old_prefix_fs = rp + "/"
            matched = db.execute(
                "SELECT id,filepath,folder FROM images WHERE filepath LIKE ? OR filepath LIKE ?",
                (old_prefix_bs + "%", old_prefix_fs + "%")
            ).fetchall()
            for img in matched:
                fp = img["filepath"]
                if fp.startswith(old_prefix_bs):
                    nfp = new_path + "\\" + fp[len(old_prefix_bs):]
                elif fp.startswith(old_prefix_fs):
                    nfp = new_path + "/" + fp[len(old_prefix_fs):]
                else:
                    nfp = os.path.join(new_path, os.path.basename(fp))
                # Compute new display folder
                new_display = target
                for root_path in roots:
                    if nfp.startswith(root_path + os.sep) or nfp.startswith(root_path + "/"):
                        rel = os.path.relpath(os.path.dirname(nfp), root_path)
                        new_display = Path(root_path).name + ("\\" + rel if rel != "." else "")
                        break
                db.execute("UPDATE images SET filepath=?, folder=?, filename=? WHERE id=?",
                           (nfp, new_display, os.path.basename(nfp), img["id"]))
        except Exception as e:
            errors.append(f"{display}: {e}")
    _db_commit_retry(db)
    start_watcher()
    return jsonify({"ok": True, "moved": moved, "errors": errors})


@app.route("/api/rename-folder", methods=["POST"])
@folder_op
def api_rename_folder():
    data = request.get_json()
    folder = data.get("folder", "").strip()
    new_name = data.get("new_name", "").strip()
    if not folder or not new_name: return jsonify({"error": "Missing data"}), 400
    invalid = set('<>:"/\\|?*')
    if any(c in invalid for c in new_name): return jsonify({"error": "Invalid characters"}), 400
    real_path = resolve_display_folder(folder)
    if not real_path or not os.path.isdir(real_path):
        return jsonify({"error": "Folder not found"}), 404
    new_path = os.path.join(os.path.dirname(real_path), new_name)
    if os.path.exists(new_path) and new_path != real_path:
        return jsonify({"error": "A folder with that name already exists"}), 409
    db = get_db()
    roots = [r["path"] for r in db.execute("SELECT path FROM scan_folders").fetchall()]
    is_root = real_path in roots
    try: os.rename(real_path, new_path)
    except OSError as e: return jsonify({"error": str(e)}), 500
    # Update all image paths in DB — match both separator styles for robustness
    old_prefix_bs = real_path + "\\"
    old_prefix_fs = real_path + "/"
    # Compute new display folder from the original display path
    parent_display = folder.rsplit('\\', 1)[0] if '\\' in folder else ''
    new_display_base = (parent_display + '\\' + new_name) if parent_display else new_name
    matched = db.execute("SELECT id,filepath,folder FROM images WHERE filepath LIKE ? OR filepath LIKE ?",
        (old_prefix_bs + "%", old_prefix_fs + "%")).fetchall()
    # Fallback: match by display folder if filepath LIKE found nothing
    if not matched:
        matched = db.execute("SELECT id,filepath,folder FROM images WHERE folder=? OR folder LIKE ?",
            (folder, folder + "\\%")).fetchall()
    for img in matched:
        fp = img["filepath"]
        if fp.startswith(old_prefix_bs):
            nfp = new_path + "\\" + fp[len(old_prefix_bs):]
        elif fp.startswith(old_prefix_fs):
            nfp = new_path + "/" + fp[len(old_prefix_fs):]
        else:
            nfp = os.path.join(new_path, os.path.basename(fp))
        old_display = img["folder"]
        if old_display == folder:
            new_display = new_display_base
        elif old_display.startswith(folder + "\\"):
            new_display = new_display_base + old_display[len(folder):]
        else:
            new_display = old_display
        db.execute("UPDATE images SET filepath=?, folder=?, filename=? WHERE id=?",
            (nfp, new_display, os.path.basename(nfp), img["id"]))
    if is_root:
        db.execute("UPDATE scan_folders SET path=?, label=? WHERE path=?", (new_path, new_name, real_path))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/folders")
def api_folders():
    db = get_db()
    rows = db.execute("SELECT folder,COUNT(*) as image_count FROM images GROUP BY folder ORDER BY natural_key(folder)").fetchall()
    result = {r["folder"]: r["image_count"] for r in rows}
    # Also include empty directories from scan roots
    scan_roots = db.execute("SELECT path FROM scan_folders").fetchall()
    for sf in scan_roots:
        root = Path(sf["path"])
        if not root.exists(): continue
        for dirpath, dirnames, filenames in os.walk(root):
            _prune_dirs(dirpath, dirnames)          # v4.44
            if _skip_dir(dirpath):
                continue
            dirnames.sort()
            rel = os.path.relpath(dirpath, root)
            display = f"{root.name}\\{rel}" if rel != "." else root.name
            if display not in result:
                result[display] = 0
    return jsonify([{"folder": k, "image_count": v} for k, v in sorted(result.items(), key=lambda x: _natural_sort_key(x[0]))])


@app.route("/api/orphans")
def api_orphans():
    """v4.26: how many image rows point outside every linked folder. Reporting
    only -- the startup sweep no longer deletes on this basis, because the same
    folder can be spelled several ways and a mismatch is not proof of anything."""
    n = int(_orphan_notice.get("count", 0))
    return jsonify({"count": n, "checked": bool(_orphan_notice.get("checked")),
                    "folders": [r["path"] for r in
                                _get_thread_db().execute("SELECT path FROM scan_folders").fetchall()]})


@app.route("/api/orphans/cleanup", methods=["POST"])
@folder_op
def api_orphans_cleanup():
    """v4.26: remove the rows /api/orphans reported, on an explicit request.
    Re-counted here rather than trusting the cached number, and refused outright
    when no folder is linked -- 'nothing is linked' is the state a fresh or
    half-restored database is in, and it must never mean 'delete everything'."""
    db = _get_thread_db()
    try:
        roots = [r["path"] for r in db.execute("SELECT path FROM scan_folders").fetchall()]
        if not roots:
            return jsonify({"error": "No folder is linked. Link your folders first — "
                                     "with none linked, every image would count as orphaned."}), 400
        ids = _orphan_ids(db, roots)
        if not ids:
            _orphan_notice.update({"count": 0, "checked": True})
            return jsonify({"ok": True, "removed": 0})
        log("Removing %d orphaned image row(s) on request \u2014 files on disk are untouched" % len(ids))
        _wipe_images_by_ids(db, ids)
        with _db_write_lock:
            db.execute("DELETE FROM characters WHERE id NOT IN "
                       "(SELECT DISTINCT character_id FROM image_characters)")
            _db_commit_retry(db)
        _orphan_notice.update({"count": 0, "checked": True})
        try: _mem_invalidate()
        except Exception: pass
        return jsonify({"ok": True, "removed": len(ids)})
    except Exception as e:
        return jsonify({"error": "Cleanup failed: %s" % e}), 500
    finally:
        db.close()
