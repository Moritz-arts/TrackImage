"""Routes: one image, and everything done to many at once.

Layer 23 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, g, make_response, Response
)
from io import BytesIO
from pathlib import Path
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import time as _time
from .config import HAS_PHASH, Image, app
from .logging_setup import log
from .platform_bits import _no_window
from .db import _folder_args, _folder_cond, _name_base_conds, _norm_tag, _search_conditions, extract_search_text, get_db
from .media import find_available_filename, find_next_global_number, get_filepath_hash, resolve_display_folder
from .metadata import _EXIFTOOL, _exiftool_read, extract_metadata, move_sidecar_with, strip_metadata_from_file
from .hashing import _phash16, _sim_pct, compute_hashes
from .thumbnails import generate_thumbnail_bytes
from .processing import _proc_prioritize
from .tagger import _disp_char, _disp_tag, _get_tagger, _img_char_tags, _tag_get_cfg, _tag_model_available, _tag_one, _tag_runtime_available, _tag_state
from .duplicates import _popcount_func, delete_pairs_for_image, delete_pairs_for_images


@app.route("/api/image/<int:image_id>/prioritize", methods=["POST"])
def api_image_prioritize(image_id):
    _proc_prioritize(image_id)
    return jsonify({"ok": True})


@app.route("/api/image/<int:image_id>/retag", methods=["POST"])
def api_image_retag(image_id):
    """v3.46: synchronously re-tag ONE image (reset button in the Tags panel).
    Restores auto-tags at current thresholds; manual tags survive (source='manual')."""
    db = get_db()
    row = db.execute("SELECT filepath, media_type FROM images WHERE id=?", (image_id,)).fetchone()
    if not row: return jsonify({"error": "Not found"}), 404
    if not _tag_runtime_available():
        return jsonify({"error": "onnxruntime is not installed"}), 400
    if not _tag_model_available():
        return jsonify({"error": "Model files not found in models/wd-eva02-large-tagger-v3"}), 400
    t = _get_tagger()
    if t is None:
        return jsonify({"error": _tag_state.get("error") or "Tagger failed to load"}), 500
    cfg = _tag_get_cfg()
    ok = _tag_one(db, t, image_id, row["filepath"], row["media_type"] or "image", cfg["gen"], cfg["char"])
    if not ok: return jsonify({"error": "Tagging failed"}), 500
    return jsonify({"ok": True, "characters": _img_char_tags(db, image_id)})


@app.route("/api/images")
def api_images():
    db = get_db()
    folders, subs = _folder_args()
    search = request.args.get("search","")
    sort = request.args.get("sort","newest")
    order = request.args.get("order","desc")
    page = int(request.args.get("page",1))
    per_page = int(request.args.get("per_page",60))
    offset = (page-1)*per_page

    q = "SELECT DISTINCT i.id,i.filename,i.folder,i.filepath,i.width,i.height,i.file_date,i.media_type,i.rating FROM images i"
    conds, params = [], []
    chars = request.args.getlist("character")   # v3.24: one or more selected tags
    ratings = [int(r) for r in request.args.getlist("rating") if r.isdigit() and 1 <= int(r) <= 9]  # v3.65: multi-select
    if ratings:
        conds.append("i.rating IN (%s)" % ",".join("?" * len(ratings))); params.extend(ratings)
    if chars:
        # v3.47: Names filter = filename base match (AND semantics)
        nc, np_ = _name_base_conds(chars)
        conds.extend(nc); params.extend(np_)
    tagsel = request.args.getlist("tag")   # v3.31: ML auto-tags, AND semantics
    if tagsel:
        tn = [_norm_tag(t) for t in tagsel]
        tph = ",".join("?" * len(tn))
        conds.append("i.id IN (SELECT it.image_id FROM image_tags it JOIN tags t ON it.tag_id=t.id "
                     f"WHERE REPLACE(LOWER(t.name),'_',' ') IN ({tph}) "
                     "GROUP BY it.image_id HAVING COUNT(DISTINCT REPLACE(LOWER(t.name),'_',' '))=?)")
        params.extend(tn); params.append(len(tn))
    _fc, _fp = _folder_cond(folders, subs)
    if _fc: conds.append(_fc); params.extend(_fp)
    if search:
        sc, sp = _search_conditions(search)
        conds.extend(sc); params.extend(sp)
    if conds: q += " WHERE " + " AND ".join(conds)

    cq = q.replace("SELECT DISTINCT i.id,i.filename,i.folder,i.filepath,i.width,i.height,i.file_date,i.media_type,i.rating","SELECT COUNT(DISTINCT i.id)")
    total = db.execute(cq, params).fetchone()[0]

    od = "ASC" if order=="asc" else "DESC"
    if sort=="folder":
        # Ordner > Name > Datum
        q += f" ORDER BY natural_key(i.folder) {od}, natural_key(i.filename) ASC, i.file_date ASC"
    elif sort=="newest":
        # Datum > Ordner > Name
        q += f" ORDER BY i.file_date {od}, natural_key(i.folder) ASC, natural_key(i.filename) ASC"
    else:
        # Name > Ordner > Datum
        q += f" ORDER BY natural_key(i.filename) {od}, natural_key(i.folder) ASC, i.file_date ASC"
    q += " LIMIT ? OFFSET ?"; params.extend([per_page, offset])
    rows = db.execute(q, params).fetchall()

    images = []
    for r in rows:
        mt = r["media_type"] or "image"
        images.append({
            "id": r["id"], "filename": r["filename"], "folder": r["folder"],
            "width": r["width"], "height": r["height"], "file_date": r["file_date"],
            "fphash": get_filepath_hash(r["filepath"]),
            "is_video": mt == "video", "media_type": mt,
            "rating": r["rating"] or 0
        })
    return jsonify({"images": images, "total": total, "page": page, "pages": (total+per_page-1)//per_page})


@app.route("/api/image/<int:image_id>")
def api_image_detail(image_id):
    db = get_db()
    row = db.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
    if not row: return jsonify({"error": "Not found"}), 404
    mt = row["media_type"] if "media_type" in row.keys() else "image"
    if not mt: mt = "image"
    tag_rows = db.execute("SELECT t.name, t.category, it.score FROM tags t JOIN image_tags it ON t.id=it.tag_id WHERE it.image_id=? ORDER BY it.score DESC", (image_id,)).fetchall()
    tagged = row["tagged"] if "tagged" in row.keys() else 0
    return jsonify({"id": row["id"], "filename": row["filename"], "folder": row["folder"],
        "filepath": row["filepath"], "width": row["width"], "height": row["height"],
        "file_date": row["file_date"],
        "tags": [{"name": _disp_tag(t["name"]), "category": t["category"], "score": round(t["score"], 3)} for t in tag_rows],
        "tagged": tagged,
        "fphash": get_filepath_hash(row["filepath"]),
        "is_video": mt == "video", "media_type": mt,
        "rating": row["rating"] if "rating" in row.keys() else 0})


@app.route("/api/image/<int:image_id>/metadata")
def api_image_metadata(image_id):
    db = get_db()
    row = db.execute("SELECT filepath FROM images WHERE id=?", (image_id,)).fetchone()
    if not row: return jsonify({"error": "Not found"}), 404
    md = extract_metadata(row["filepath"])
    if _EXIFTOOL and isinstance(md, dict) and not md.get("error"):
        for k, v in _exiftool_read(row["filepath"]).items():   # v3.58: enrich, never overwrite
            if md.get(k) in (None, ""):
                md[k] = v
    return jsonify(md)


@app.route("/api/image/<int:image_id>/remove-tag", methods=["POST"])
def api_remove_tag(image_id):
    db = get_db()
    data = request.get_json()
    tag = data.get("tag","").strip()
    if not tag: return jsonify({"error": "No tag"}), 400
    # v3.47: one unified path — remove the tag (any category) from THIS image only.
    n = _norm_tag(tag)
    db.execute("""DELETE FROM image_tags WHERE image_id=? AND tag_id IN
                  (SELECT id FROM tags WHERE REPLACE(LOWER(name),'_',' ')=?)""", (image_id, n))
    db.execute("DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM image_tags)")
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/image/<int:image_id>/add-tag", methods=["POST"])
def api_add_tag(image_id):
    db = get_db()
    data = request.get_json() or {}
    raw = (data.get("tag") or "").strip()
    if not raw: return jsonify({"error": "No tag"}), 400
    row = db.execute("SELECT id FROM images WHERE id=?", (image_id,)).fetchone()
    if not row: return jsonify({"error": "Not found"}), 404
    n = _norm_tag(raw)
    if not n: return jsonify({"error": "No tag"}), 400
    _t = data.get("type")
    if _t == "character":
        cat = 'character'
    elif _t == "general":
        cat = 'general'
    else:
        # v3.65: auto-detect - tags known as characters (tagger vocabulary in DB) become CHAR tags
        _ex = db.execute("SELECT 1 FROM tags WHERE category='character' AND REPLACE(LOWER(name),'_',' ')=?", (n,)).fetchone()
        cat = 'character' if _ex else 'general'
    # v3.45/3.46: manual tag; source='manual' so re-tagging keeps it. Normalized lookup.
    tr = db.execute("SELECT id FROM tags WHERE category=? AND REPLACE(LOWER(name),'_',' ')=?", (cat, n)).fetchone()
    if not tr:
        db.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)", (n.replace(" ", "_"), cat))
        tr = db.execute("SELECT id FROM tags WHERE category=? AND REPLACE(LOWER(name),'_',' ')=?", (cat, n)).fetchone()
    db.execute("INSERT OR REPLACE INTO image_tags (image_id, tag_id, score, source) VALUES (?,?,1.0,'manual')",
               (image_id, tr["id"]))
    db.commit()
    return jsonify({"ok": True, "tag": _disp_char(n) if cat == 'character' else _disp_tag(n)})


@app.route("/api/image/<int:image_id>/rating", methods=["POST"])
def api_set_rating(image_id):
    db = get_db()
    data = request.get_json() or {}
    rating = int(data.get("rating", 0))
    if rating < 0 or rating > 9:
        return jsonify({"error": "Rating must be 0-9"}), 400
    row = db.execute("SELECT id FROM images WHERE id=?", (image_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    db.execute("UPDATE images SET rating=? WHERE id=?", (rating, image_id))
    db.commit()
    return jsonify({"ok": True, "rating": rating})


@app.route("/api/images/tag-info", methods=["POST"])
def api_images_tag_info():
    """Return all tags across the given image ids with how many of those images have each tag."""
    db = get_db()
    data = request.get_json() or {}
    ids = data.get("ids", [])
    if not ids: return jsonify({"tags": [], "total": 0})
    placeholders = ",".join("?" * len(ids))
    rows = db.execute(
        f"SELECT MIN(t.name) AS name, MIN(t.category) AS category, COUNT(DISTINCT it.image_id) AS cnt "
        f"FROM tags t JOIN image_tags it ON t.id=it.tag_id "
        f"WHERE it.image_id IN ({placeholders}) "
        f"GROUP BY REPLACE(LOWER(t.name),'_',' ') ORDER BY cnt DESC, name",
        ids
    ).fetchall()
    return jsonify({"tags": [{"name": _disp_tag(r["name"]), "category": r["category"], "count": r["cnt"]} for r in rows], "total": len(ids)})


@app.route("/api/images/bulk-add-tag", methods=["POST"])
def api_bulk_add_tag():
    db = get_db()
    data = request.get_json() or {}
    ids = data.get("ids", [])
    n = _norm_tag(data.get("tag", ""))
    if not ids or not n: return jsonify({"error": "Missing ids or tag"}), 400
    _t = data.get("type")  # v3.65: CHAR toggle + auto-detect (same rules as single add-tag)
    if _t == "character":
        cat = 'character'
    elif _t == "general":
        cat = 'general'
    else:
        _ex = db.execute("SELECT 1 FROM tags WHERE category='character' AND REPLACE(LOWER(name),'_',' ')=?", (n,)).fetchone()
        cat = 'character' if _ex else 'general'
    cr = db.execute("SELECT id FROM tags WHERE category=? AND REPLACE(LOWER(name),'_',' ')=?", (cat, n)).fetchone()
    if not cr:
        db.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, ?)", (n.replace(" ", "_"), cat))
        cr = db.execute("SELECT id FROM tags WHERE category=? AND REPLACE(LOWER(name),'_',' ')=?", (cat, n)).fetchone()
    if not cr: return jsonify({"error": "Tag insert failed"}), 500
    added = 0
    for img_id in ids:
        row = db.execute("SELECT id FROM images WHERE id=?", (img_id,)).fetchone()
        if not row: continue
        db.execute("INSERT OR REPLACE INTO image_tags (image_id, tag_id, score, source) VALUES (?,?,1.0,'manual')",
                   (img_id, cr["id"]))
        added += 1
    db.commit()
    return jsonify({"ok": True, "added": added, "tag": _disp_tag(n)})


@app.route("/api/images/bulk-remove-tag", methods=["POST"])
def api_bulk_remove_tag():
    db = get_db()
    data = request.get_json() or {}
    ids = data.get("ids", [])
    n = _norm_tag(data.get("tag", ""))
    if not ids or not n: return jsonify({"error": "Missing ids or tag"}), 400
    tids = [r["id"] for r in db.execute(
        "SELECT id FROM tags WHERE REPLACE(LOWER(name),'_',' ')=?", (n,)).fetchall()]
    if not tids: return jsonify({"error": "Tag not found"}), 404
    removed = 0
    tph = ",".join("?" * len(tids))
    for img_id in ids:
        res = db.execute(f"DELETE FROM image_tags WHERE image_id=? AND tag_id IN ({tph})", [img_id] + tids)
        if res.rowcount > 0: removed += 1
    db.execute("DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM image_tags)")
    db.commit()
    return jsonify({"ok": True, "removed": removed, "protected": 0, "tag": _disp_tag(n)})


@app.route("/api/image/<int:image_id>/rename", methods=["POST"])
def api_rename_image(image_id):
    db = get_db()
    data = request.get_json()
    new_fn = data.get("filename","").strip()
    auto_inc = data.get("auto_increment", False)
    custom_start = data.get("start_number", None)
    if not new_fn: return jsonify({"error": "No filename"}), 400
    row = db.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
    if not row: return jsonify({"error": "Not found"}), 404
    mt = row["media_type"] if "media_type" in row.keys() else "image"
    if not mt: mt = "image"
    old_fp = row["filepath"]; old_dir = os.path.dirname(old_fp)
    if not Path(new_fn).suffix: new_fn += Path(old_fp).suffix
    new_fp = os.path.join(old_dir, new_fn)
    # Check global numbering — if this base name exists anywhere, assign next number
    stem = Path(new_fn).stem
    ext = Path(new_fn).suffix
    # Strip existing (N) suffix to get base name
    m_num = re.match(r'^(.*?)\s*\((\d+)\)$', stem)
    check_base = m_num.group(1) if m_num else stem
    global_n = find_next_global_number(db, check_base, exclude_ids=[image_id], media_type=mt)
    if custom_start is not None:
        # User chose a specific start number
        new_fn = f"{check_base} ({int(custom_start)}){ext}"
        new_fp = os.path.join(old_dir, new_fn)
        if os.path.exists(new_fp) and new_fp != old_fp:
            new_fn = find_available_filename(old_dir, new_fn)
            new_fp = os.path.join(old_dir, new_fn)
    elif global_n > 1 and not m_num:
        # Name used elsewhere — auto-assign global number
        new_fn = f"{check_base} ({global_n}){ext}"
        new_fp = os.path.join(old_dir, new_fn)
    elif os.path.exists(new_fp) and new_fp != old_fp:
        suggestion = find_available_filename(old_dir, new_fn)
        if auto_inc:
            new_fn = suggestion
            new_fp = os.path.join(old_dir, new_fn)
        else:
            return jsonify({"error": "File exists", "suggestion": suggestion}), 409
    try: os.rename(old_fp, new_fp)
    except OSError as e: return jsonify({"error": str(e)}), 500
    # v4.53: a sidecar is tied to its file by name and nothing else. Left behind,
    # it becomes a stray .xmp and the video quietly loses the metadata it had.
    move_sidecar_with(old_fp, new_fp)
    old_fn = row["filename"]
    db.execute("UPDATE images SET filename=?, filepath=? WHERE id=?", (new_fn, new_fp, image_id))
    # v3.46: renaming no longer touches tags — characters come from the ML tagger.
    chars = _img_char_tags(db, image_id)
    db.commit()
    return jsonify({"ok": True, "filename": new_fn, "characters": chars, "old_filename": old_fn, "fphash": get_filepath_hash(new_fp)})


@app.route("/api/image/<int:image_id>/open-explorer", methods=["POST"])
def api_open_explorer(image_id):
    db = get_db()
    row = db.execute("SELECT filepath FROM images WHERE id=?", (image_id,)).fetchone()
    if not row: return jsonify({"error": "Not found"}), 404
    fp = row["filepath"]
    if not os.path.exists(fp): return jsonify({"error": "File not found on disk"}), 404
    try:
        s = platform.system()
        if s == "Windows": subprocess.Popen(f'explorer /select,"{fp}"', shell=True, **_no_window())
        elif s == "Darwin": subprocess.Popen(["open", "-R", fp])
        else: subprocess.Popen(["xdg-open", os.path.dirname(fp)])
        return jsonify({"ok": True})
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route("/api/image/<int:image_id>/open-file", methods=["POST"])
def api_open_file(image_id):
    db = get_db()
    row = db.execute("SELECT filepath FROM images WHERE id=?", (image_id,)).fetchone()
    if not row: return jsonify({"error": "Not found"}), 404
    fp = row["filepath"]
    if not os.path.exists(fp): return jsonify({"error": "File not found on disk"}), 404
    try:
        s = platform.system()
        if s == "Windows": os.startfile(fp)
        elif s == "Darwin": subprocess.Popen(["open", fp])
        else: subprocess.Popen(["xdg-open", fp])
        return jsonify({"ok": True})
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route("/api/image/<int:image_id>/remove-metadata", methods=["POST"])
def api_remove_metadata(image_id):
    db = get_db()
    row = db.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
    if not row: return jsonify({"error": "Not found"}), 404
    fp = row["filepath"]
    ok, msg = strip_metadata_from_file(fp)
    if not ok:
        return jsonify({"error": msg}), 400
    # Re-index search text + phash so stale data doesn't linger.
    # NOTE: we do NOT update file_date — the original creation date should be preserved,
    # and strip_metadata_from_file already restored the file's mtime on disk.
    try:
        new_search = extract_search_text(fp)
        new_ph, new_ts = compute_hashes(fp)                       # v3.73
        try: new_fs = os.path.getsize(fp)
        except Exception: new_fs = 0
        db.execute("UPDATE images SET search_text=?, phash=?, tile_sig=?, file_size=?, hash_fail=0 WHERE id=?",
                   (new_search, new_ph, sqlite3.Binary(new_ts or b""), new_fs, image_id))
        db.commit()
    except Exception:
        pass
    return jsonify({"ok": True})


@app.route("/api/images/bulk-remove-metadata", methods=["POST"])
def api_bulk_remove_metadata():
    db = get_db()
    data = request.get_json() or {}
    ids = data.get("ids", [])
    if not ids: return jsonify({"error": "No ids"}), 400
    stripped = 0
    skipped = 0
    errors = []
    for img_id in ids:
        row = db.execute("SELECT * FROM images WHERE id=?", (img_id,)).fetchone()
        if not row:
            skipped += 1; continue
        fp = row["filepath"]
        ok, msg = strip_metadata_from_file(fp)
        if not ok:
            skipped += 1
            if len(errors) < 5:
                errors.append(f"{row['filename']}: {msg}")
            continue
        try:
            new_search = extract_search_text(fp)
            new_ph, new_ts = compute_hashes(fp)                   # v3.73
            try: new_fs = os.path.getsize(fp)
            except Exception: new_fs = 0
            # Preserve original file_date — strip_metadata_from_file restored the mtime on disk
            db.execute("UPDATE images SET search_text=?, phash=?, tile_sig=?, file_size=?, hash_fail=0 WHERE id=?",
                       (new_search, new_ph, sqlite3.Binary(new_ts or b""), new_fs, img_id))
        except Exception:
            pass
        stripped += 1
    db.commit()
    return jsonify({"ok": True, "stripped": stripped, "skipped": skipped, "errors": errors})


@app.route("/api/image/<int:image_id>/delete", methods=["POST"])
def api_delete_image(image_id):
    import traceback
    try:
        db = get_db()
        row = db.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
        if not row: return jsonify({"error": "Not found"}), 404
        fp = row["filepath"]
        chars = _img_char_tags(db, image_id)
        # Move to trash
        trash_dir = os.path.join(app.instance_path, ".trash")
        os.makedirs(trash_dir, exist_ok=True)
        trash_name = f"{int(_time.time()*1000)}_{row['filename']}"
        # Windows MAX_PATH safety: if combined path is too long, shorten trash_name
        trash_path = os.path.join(trash_dir, trash_name)
        if len(trash_path) > 250:
            stem, _sep, ext = row['filename'].rpartition('.')
            short = (stem[:40] if stem else 'file') + ('.' + ext if ext else '')
            trash_name = f"{int(_time.time()*1000)}_{short}"
            trash_path = os.path.join(trash_dir, trash_name)
        moved = False
        rename_err = None
        if os.path.exists(fp):
            # Try os.rename first (fast atomic on same filesystem)
            try:
                os.rename(fp, trash_path)
                moved = True
            except OSError as e:
                rename_err = e
                # Fallback: shutil.move handles cross-filesystem + some Windows handle issues
                try:
                    shutil.move(fp, trash_path)
                    moved = True
                except Exception as e2:
                    log(f"delete failed for image {image_id} ({fp}): rename={rename_err} move={e2}", "error")
                    return jsonify({"error": f"Cannot move file to trash: {e2}"}), 500
            # v4.53: the sidecar goes with it. Left in place it describes a file
            # that is no longer there, and restoring from the trash would find a
            # video whose metadata had been taken over by a stale .xmp.
            if moved and trash_path:
                move_sidecar_with(fp, trash_path)
        else:
            trash_path = ""  # file gone, still clean up DB
        db.execute("INSERT INTO trash (original_filepath,original_folder,original_filename,trash_path,width,height,file_date,search_text,characters_json,deleted_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (fp, row["folder"], row["filename"], trash_path, row["width"], row["height"], row["file_date"],
             row["search_text"] if "search_text" in row.keys() else "", json.dumps(chars), _time.time()))
        trash_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute("DELETE FROM images WHERE id=?", (image_id,))
        delete_pairs_for_image(db, image_id)
        db.execute("DELETE FROM characters WHERE id NOT IN (SELECT DISTINCT character_id FROM image_characters)")
        db.commit()
        return jsonify({"ok": True, "trash_id": trash_id})
    except Exception as e:
        log(f"api_delete_image crashed for image_id={image_id}:\n{traceback.format_exc()}", "error")
        return jsonify({"error": f"Delete failed: {type(e).__name__}: {e}"}), 500


@app.route("/api/scan-image", methods=["POST"])
def api_scan_image():
    """v3.28: hash an uploaded image IN MEMORY and return library images within the
    given Hamming threshold. The uploaded file is NEVER stored or imported."""
    # imported here, not at the top: api_images loads before api_tags, and a
    # module cannot import from one that has not been built yet.
    from .api_tags import _upload_tag_ids, _verify_by_tags
    if not HAS_PHASH:
        return jsonify({"error": "numpy not installed"}), 400
    f = request.files.get("image")
    if not f:
        return jsonify({"error": "no image uploaded"}), 400
    max_dist = int(request.args.get("threshold", 128))
    verify = request.args.get("verify") == "1"      # v4.33: same switch as the folder view
    try:
        raw = f.read()
        from PIL import ImageOps as _IO
        with Image.open(BytesIO(raw)) as _im:
            _im2 = _IO.exif_transpose(_im)
            qph = int(_phash16(_im2), 16)
        thumb = generate_thumbnail_bytes("", _raw=raw)
    except Exception as e:
        return jsonify({"error": f"cannot read image: {type(e).__name__}"}), 400
    db = get_db()
    popcount = _popcount_func()
    rows = db.execute("SELECT id,filename,folder,filepath,media_type,phash,width,height,file_size "
                      "FROM images WHERE phash IS NOT NULL AND phash != ''").fetchall()
    matches = []
    for r in rows:
        try: d = popcount(qph ^ int(r["phash"], 16))
        except Exception: continue
        if d <= max_dist:
            # v4.33: width/height/file_size travel with every match so the query
            # view can sort by size exactly like the folder view does.
            matches.append({"id": r["id"], "filename": r["filename"], "folder": r["folder"],
                            "fphash": get_filepath_hash(r["filepath"]),
                            "media_type": r["media_type"] or "image",
                            "width": r["width"] or 0, "height": r["height"] or 0,
                            "file_size": r["file_size"] or 0, "distance": d,
                            "similarity": _sim_pct(d)})
    if verify and matches:
        matches = _verify_by_tags(db, [m["id"] for m in matches], _upload_tag_ids(db, raw), matches)
    matches.sort(key=lambda m: -m["similarity"])
    import base64 as _b64
    thumb_uri = ("data:image/webp;base64," + _b64.b64encode(thumb).decode()) if thumb else ""
    return jsonify({"matches": matches[:300], "count": len(matches),
                    "filename": f.filename or "dropped image", "thumb": thumb_uri,
                    "best_similarity": matches[0]["similarity"] if matches else None})


@app.route("/api/scan-image-tags", methods=["POST"])
def api_scan_image_tags():
    """v3.54: auto-tag an uploaded image IN MEMORY and return library images with
    >= 50% tag overlap (Jaccard). The upload is NEVER stored or imported."""
    tagger = _get_tagger()
    if tagger is None:
        return jsonify({"error": "ML tagger not available — place the model in models/ first."}), 400
    f = request.files.get("image")
    if not f:
        return jsonify({"error": "no image uploaded"}), 400
    try:
        raw = f.read()
        cfg = _tag_get_cfg()
        with Image.open(BytesIO(raw)) as _im:
            res = tagger.tag_image(_im.convert("RGB"), gen_threshold=cfg["gen"], char_threshold=cfg["char"])
        thumb = generate_thumbnail_bytes("", _raw=raw)
    except Exception as e:
        return jsonify({"error": f"cannot tag image: {type(e).__name__}"}), 400
    names = {_norm_tag(t.name) for t in res.all}
    if len(names) < 3:
        return jsonify({"error": "Image produced too few tags to compare."}), 400
    db = get_db()
    qids = set()
    for n in names:
        r = db.execute("SELECT id FROM tags WHERE REPLACE(LOWER(name),'_',' ')=?", (n,)).fetchone()
        if r: qids.add(r[0])
    q_extra = len(names) - len(qids)     # query tags unknown to the library still count in the union
    sets = {}
    for iid, tid in db.execute("SELECT image_id, tag_id FROM image_tags"):
        s = sets.get(iid)
        if s is None: sets[iid] = s = set()
        s.add(tid)
    scored = []
    for iid, s in sets.items():
        if len(s) < 3: continue
        inter = len(qids & s)
        if not inter: continue
        sim = int(round(inter / (len(qids) + q_extra + len(s) - inter) * 100))
        if sim >= 50: scored.append((iid, sim))
    scored.sort(key=lambda x: -x[1])
    scored = scored[:300]
    matches = []
    for k in range(0, len(scored), 900):
        chunk = scored[k:k + 900]
        ph = ",".join("?" * len(chunk))
        rmap = {r["id"]: r for r in db.execute(
            f"SELECT id,filename,folder,filepath,media_type,width,height,file_size "
            f"FROM images WHERE id IN ({ph})", [c[0] for c in chunk]).fetchall()}
        for iid, sim in chunk:
            r = rmap.get(iid)
            if r: matches.append({"id": r["id"], "filename": r["filename"], "folder": r["folder"],
                                  "fphash": get_filepath_hash(r["filepath"]),
                                  "media_type": r["media_type"] or "image",
                                  "width": r["width"] or 0, "height": r["height"] or 0,
                                  "file_size": r["file_size"] or 0,
                                  "distance": 100 - sim, "similarity": sim})
    import base64 as _b64
    thumb_uri = ("data:image/webp;base64," + _b64.b64encode(thumb).decode()) if thumb else ""
    return jsonify({"matches": matches, "count": len(matches),
                    "filename": f.filename or "dropped image", "thumb": thumb_uri,
                    "best_similarity": matches[0]["similarity"] if matches else None})


@app.route("/api/restore/<int:trash_id>", methods=["POST"])
def api_restore(trash_id):
    db = get_db()
    row = db.execute("SELECT * FROM trash WHERE id=?", (trash_id,)).fetchone()
    if not row: return jsonify({"error": "Trash entry not found"}), 404
    tp = row["trash_path"]
    ofp = row["original_filepath"]
    # Ensure target directory exists
    target_dir = os.path.dirname(ofp)
    if not os.path.isdir(target_dir):
        try: os.makedirs(target_dir, exist_ok=True)
        except: return jsonify({"error": "Cannot recreate original directory"}), 500
    # Find available filename if original exists
    if os.path.exists(ofp):
        ofn = find_available_filename(target_dir, row["original_filename"])
        ofp = os.path.join(target_dir, ofn)
    else:
        ofn = row["original_filename"]
    if tp and os.path.exists(tp):
        try: os.rename(tp, ofp)
        except OSError as e: return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Trash file not found on disk"}), 404
    # Re-insert into images
    cur = db.execute("INSERT INTO images (filename,folder,filepath,width,height,file_date,search_text) VALUES (?,?,?,?,?,?,?)",
        (ofn, row["original_folder"], ofp, row["width"], row["height"], row["file_date"], row["search_text"]))
    new_id = cur.lastrowid
    # v3.46: restore character tags as manual tags (survive re-tagging)
    try:
        chars = json.loads(row["characters_json"])
    except: chars = []
    for cn in chars:
        nn = _norm_tag(cn)
        if not nn: continue
        tr = db.execute("SELECT id FROM tags WHERE category='character' AND REPLACE(LOWER(name),'_',' ')=?", (nn,)).fetchone()
        if not tr:
            db.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, 'character')", (nn.replace(" ", "_"),))
            tr = db.execute("SELECT id FROM tags WHERE category='character' AND REPLACE(LOWER(name),'_',' ')=?", (nn,)).fetchone()
        if tr: db.execute("INSERT OR REPLACE INTO image_tags (image_id, tag_id, score, source) VALUES (?,?,1.0,'manual')",
            (new_id, tr["id"]))
    db.execute("DELETE FROM trash WHERE id=?", (trash_id,))
    db.commit()
    return jsonify({"ok": True, "image_id": new_id})


@app.route("/api/bulk-restore", methods=["POST"])
def api_bulk_restore():
    db = get_db()
    trash_ids = request.get_json().get("trash_ids", [])
    restored = 0
    for tid in trash_ids:
        row = db.execute("SELECT * FROM trash WHERE id=?", (tid,)).fetchone()
        if not row: continue
        tp = row["trash_path"]
        ofp = row["original_filepath"]
        target_dir = os.path.dirname(ofp)
        if not os.path.isdir(target_dir):
            try: os.makedirs(target_dir, exist_ok=True)
            except: continue
        if os.path.exists(ofp):
            ofn = find_available_filename(target_dir, row["original_filename"])
            ofp = os.path.join(target_dir, ofn)
        else:
            ofn = row["original_filename"]
        if not tp or not os.path.exists(tp): continue
        try: os.rename(tp, ofp)
        except: continue
        cur = db.execute("INSERT INTO images (filename,folder,filepath,width,height,file_date,search_text) VALUES (?,?,?,?,?,?,?)",
            (ofn, row["original_folder"], ofp, row["width"], row["height"], row["file_date"], row["search_text"]))
        new_id = cur.lastrowid
        try: chars = json.loads(row["characters_json"])
        except: chars = []
        for cn in chars:
            nn = _norm_tag(cn)
            if not nn: continue
            tr = db.execute("SELECT id FROM tags WHERE category='character' AND REPLACE(LOWER(name),'_',' ')=?", (nn,)).fetchone()
            if not tr:
                db.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?, 'character')", (nn.replace(" ", "_"),))
                tr = db.execute("SELECT id FROM tags WHERE category='character' AND REPLACE(LOWER(name),'_',' ')=?", (nn,)).fetchone()
            if tr: db.execute("INSERT OR REPLACE INTO image_tags (image_id, tag_id, score, source) VALUES (?,?,1.0,'manual')",
                (new_id, tr["id"]))
        db.execute("DELETE FROM trash WHERE id=?", (tid,))
        restored += 1
    db.commit()
    return jsonify({"ok": True, "restored": restored})


@app.route("/api/images/bulk-delete", methods=["POST"])
def api_bulk_delete():
    db = get_db()
    ids = request.get_json().get("ids", [])
    trash_dir = os.path.join(app.instance_path, ".trash")
    os.makedirs(trash_dir, exist_ok=True)
    deleted = 0
    trash_ids = []
    errors = []
    gone = []                       # v4.14: the pair cache is told once, at the end
    for img_id in ids:
        row = db.execute("SELECT * FROM images WHERE id=?", (img_id,)).fetchone()
        if not row: continue
        fp = row["filepath"]
        chars = [c["name"] for c in db.execute("SELECT c.name FROM characters c JOIN image_characters ic ON c.id=ic.character_id WHERE ic.image_id=?", (img_id,)).fetchall()]
        trash_name = f"{int(_time.time()*1000)}_{row['filename']}"
        trash_path = os.path.join(trash_dir, trash_name)
        if len(trash_path) > 250:
            stem, _sep, ext = row['filename'].rpartition('.')
            short = (stem[:40] if stem else 'file') + ('.' + ext if ext else '')
            trash_name = f"{int(_time.time()*1000)}_{short}"
            trash_path = os.path.join(trash_dir, trash_name)
        if os.path.exists(fp):
            try:
                os.rename(fp, trash_path)
            except OSError:
                try:
                    shutil.move(fp, trash_path)
                except Exception as e:
                    errors.append(f"{row['filename']}: {e}")
                    continue  # skip this one, don't touch DB
        else:
            trash_path = ""
        db.execute("INSERT INTO trash (original_filepath,original_folder,original_filename,trash_path,width,height,file_date,search_text,characters_json,deleted_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (fp, row["folder"], row["filename"], trash_path, row["width"], row["height"], row["file_date"],
             row["search_text"] if "search_text" in row.keys() else "", json.dumps(chars), _time.time()))
        tid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        trash_ids.append(tid)
        db.execute("DELETE FROM images WHERE id=?", (img_id,))
        gone.append(img_id)
        deleted += 1
    db.execute("DELETE FROM characters WHERE id NOT IN (SELECT DISTINCT character_id FROM image_characters)")
    db.commit()
    delete_pairs_for_images(db, gone)
    return jsonify({"ok": True, "deleted": deleted, "trash_ids": trash_ids, "errors": errors})


@app.route("/api/images/bulk-rename", methods=["POST"])
def api_bulk_rename():
    db = get_db()
    data = request.get_json()
    ids = data.get("ids", [])
    base_name = data.get("base_name", "").strip()
    continue_numbering = data.get("continue_numbering", True)
    custom_start = data.get("start_number", None)
    if not base_name or not ids: return jsonify({"error": "Missing data"}), 400
    renamed = 0
    old_names = []  # [{id, old_filename}]

    if len(ids) == 1:
        # Single file: rename with user-chosen numbering
        row = db.execute("SELECT * FROM images WHERE id=?", (ids[0],)).fetchone()
        if row:
            ext = Path(row["filepath"]).suffix
            old_fp = row["filepath"]
            mt = row["media_type"] if "media_type" in row.keys() else "image"
            if not mt: mt = "image"
            # Determine number
            global_n = find_next_global_number(db, base_name, exclude_ids=ids, media_type=mt)
            if custom_start is not None:
                n = int(custom_start)
            elif not continue_numbering:
                n = 1
            elif global_n > 1:
                n = global_n
            else:
                n = 0  # no number needed — name is free
            if n > 0:
                new_fn = f"{base_name} ({n}){ext}"
            else:
                new_fn = f"{base_name}{ext}"
            new_fp = os.path.join(os.path.dirname(old_fp), new_fn)
            if os.path.exists(new_fp) and new_fp != old_fp:
                new_fn = find_available_filename(os.path.dirname(old_fp), new_fn)
                new_fp = os.path.join(os.path.dirname(old_fp), new_fn)
            try:
                os.rename(old_fp, new_fp)
                old_names.append({"id": ids[0], "old_filename": row["filename"]})
                db.execute("UPDATE images SET filename=?, filepath=? WHERE id=?", (new_fn, new_fp, ids[0]))
                renamed = 1
            except: pass
    else:
        # Multi file: use (N) numbering, separate per media category
        # Two-pass rename to avoid collisions when selected files already occupy target slots

        # Pass 1: rename all to temporary names (disk + DB) to free up slots
        temp_prefix = f"__trackimage_temp_{int(_time.time()*1000)}_"
        temp_map = []  # [(img_id, original_fn, temp_fp, ext, media_type)]
        for img_id in ids:
            row = db.execute("SELECT * FROM images WHERE id=?", (img_id,)).fetchone()
            if not row: continue
            old_fp = row["filepath"]
            original_fn = row["filename"]
            ext = Path(old_fp).suffix
            mt = row["media_type"] if "media_type" in row.keys() else "image"
            if not mt: mt = "image"
            temp_fn = f"{temp_prefix}{img_id}{ext}"
            temp_fp = os.path.join(os.path.dirname(old_fp), temp_fn)
            try:
                os.rename(old_fp, temp_fp)
                db.execute("UPDATE images SET filename=?, filepath=? WHERE id=?", (temp_fn, temp_fp, img_id))
                temp_map.append((img_id, original_fn, temp_fp, ext, mt))
            except:
                continue

        # Compute per-category start numbers
        category_counters = {}
        for _, _, _, _, mt in temp_map:
            if mt not in category_counters:
                if custom_start is not None:
                    category_counters[mt] = int(custom_start)
                elif continue_numbering:
                    category_counters[mt] = find_next_global_number(db, base_name, exclude_ids=ids, media_type=mt)
                else:
                    category_counters[mt] = 1

        # Pass 2: rename from temp to final sequential names
        for img_id, original_fn, temp_fp, ext, mt in temp_map:
            n = category_counters[mt]
            category_counters[mt] += 1
            new_fn = f"{base_name} ({n}){ext}"
            new_fp = os.path.join(os.path.dirname(temp_fp), new_fn)
            # Safety: if target still occupied by a non-selected file
            if os.path.exists(new_fp):
                new_fn = find_available_filename(os.path.dirname(temp_fp), new_fn)
                new_fp = os.path.join(os.path.dirname(temp_fp), new_fn)
            try: os.rename(temp_fp, new_fp)
            except:
                # Rollback: restore original name on disk + DB
                orig_fp = os.path.join(os.path.dirname(temp_fp), original_fn)
                try:
                    os.rename(temp_fp, orig_fp)
                    db.execute("UPDATE images SET filename=?, filepath=? WHERE id=?", (original_fn, orig_fp, img_id))
                except: pass
                continue
            old_names.append({"id": img_id, "old_filename": original_fn})
            db.execute("UPDATE images SET filename=?, filepath=? WHERE id=?", (new_fn, new_fp, img_id))

            renamed += 1

    db.execute("DELETE FROM characters WHERE id NOT IN (SELECT DISTINCT character_id FROM image_characters)")
    db.commit()
    return jsonify({"ok": True, "renamed": renamed, "old_names": old_names})


@app.route("/api/next-number", methods=["POST"])
def api_next_number():
    """Find the next available (N) for a given base name across all folders."""
    db = get_db()
    data = request.get_json()
    base_name = data.get("base_name", "").strip()
    exclude_ids = data.get("exclude_ids", [])
    if not base_name: return jsonify({"error": "No name"}), 400
    media_type = data.get("media_type", None)
    n = find_next_global_number(db, base_name, exclude_ids=exclude_ids, media_type=media_type)
    return jsonify({"next": n, "base_name": base_name})


@app.route("/api/image/<int:image_id>/move", methods=["POST"])
def api_move_image(image_id):
    db = get_db()
    data = request.get_json()
    target_folder = data.get("folder", "").strip()
    if not target_folder: return jsonify({"error": "No target folder"}), 400
    row = db.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
    if not row: return jsonify({"error": "Not found"}), 404
    target_path = resolve_display_folder(target_folder)
    if not target_path or not os.path.isdir(target_path):
        return jsonify({"error": "Target folder not found"}), 404
    old_fp = row["filepath"]
    new_fn = row["filename"]
    new_fp = os.path.join(target_path, new_fn)
    if os.path.exists(new_fp) and new_fp != old_fp:
        new_fn = find_available_filename(target_path, new_fn)
        new_fp = os.path.join(target_path, new_fn)
    try: os.rename(old_fp, new_fp)
    except OSError as e: return jsonify({"error": str(e)}), 500
    # Compute new display folder
    scan_roots = db.execute("SELECT path FROM scan_folders").fetchall()
    display = target_folder
    for sf in scan_roots:
        root = sf["path"]
        if new_fp.startswith(root + os.sep) or new_fp.startswith(root + "/"):
            rel = os.path.relpath(os.path.dirname(new_fp), root)
            display = Path(root).name + ("\\" + rel if rel != "." else "")
            break
    db.execute("UPDATE images SET filename=?, filepath=?, folder=? WHERE id=?", (new_fn, new_fp, display, image_id))
    db.commit()
    return jsonify({"ok": True, "folder": display})


@app.route("/api/images/bulk-move", methods=["POST"])
def api_bulk_move():
    db = get_db()
    data = request.get_json()
    ids = data.get("ids", [])
    target_folder = data.get("folder", "").strip()
    if not target_folder or not ids: return jsonify({"error": "Missing data"}), 400
    target_path = resolve_display_folder(target_folder)
    if not target_path or not os.path.isdir(target_path):
        return jsonify({"error": "Target folder not found"}), 404
    scan_roots = db.execute("SELECT path FROM scan_folders").fetchall()
    moved = 0
    for img_id in ids:
        row = db.execute("SELECT * FROM images WHERE id=?", (img_id,)).fetchone()
        if not row: continue
        old_fp = row["filepath"]
        new_fn = row["filename"]
        new_fp = os.path.join(target_path, new_fn)
        if os.path.exists(new_fp) and new_fp != old_fp:
            new_fn = find_available_filename(target_path, new_fn)
            new_fp = os.path.join(target_path, new_fn)
        try: os.rename(old_fp, new_fp)
        except: continue
        display = target_folder
        for sf in scan_roots:
            root = sf["path"]
            if new_fp.startswith(root + os.sep) or new_fp.startswith(root + "/"):
                rel = os.path.relpath(os.path.dirname(new_fp), root)
                display = Path(root).name + ("\\" + rel if rel != "." else "")
                break
        db.execute("UPDATE images SET filename=?, filepath=?, folder=? WHERE id=?", (new_fn, new_fp, display, img_id))
        moved += 1
    db.commit()
    return jsonify({"ok": True, "moved": moved})


@app.route("/api/images/bulk-copy", methods=["POST"])
def api_bulk_copy():
    """Copy files to a target folder (duplicate on disk, add new DB rows)."""
    db = get_db()
    data = request.get_json() or {}
    ids = data.get("ids", [])
    target_folder = data.get("folder", "").strip()
    if not target_folder or not ids: return jsonify({"error": "Missing data"}), 400
    target_path = resolve_display_folder(target_folder)
    if not target_path or not os.path.isdir(target_path):
        return jsonify({"error": "Target folder not found"}), 404
    scan_roots = db.execute("SELECT path FROM scan_folders").fetchall()
    copied = 0
    new_ids = []
    for img_id in ids:
        row = db.execute("SELECT * FROM images WHERE id=?", (img_id,)).fetchone()
        if not row: continue
        src_fp = row["filepath"]
        if not os.path.isfile(src_fp): continue
        new_fn = find_available_filename(target_path, row["filename"])
        new_fp = os.path.join(target_path, new_fn)
        try:
            shutil.copy2(src_fp, new_fp)
        except Exception:
            continue
        # Compute display folder
        display = target_folder
        for sf in scan_roots:
            root = sf["path"]
            if new_fp.startswith(root + os.sep) or new_fp.startswith(root + "/"):
                rel = os.path.relpath(os.path.dirname(new_fp), root)
                display = Path(root).name + ("\\" + rel if rel != "." else "")
                break
        # Insert new DB row mirroring the source
        try: mtime = int(os.path.getmtime(new_fp))
        except: mtime = row["file_date"] if "file_date" in row.keys() else 0
        cur = db.execute(
            "INSERT INTO images (filename,folder,filepath,width,height,file_date,search_text,media_type,phash) VALUES (?,?,?,?,?,?,?,?,?)",
            (new_fn, display, new_fp, row["width"], row["height"], mtime,
             row["search_text"] if "search_text" in row.keys() else "",
             row["media_type"] if "media_type" in row.keys() else "image",
             row["phash"] if "phash" in row.keys() else ""))
        new_img_id = cur.lastrowid
        new_ids.append(new_img_id)
        # v3.46: copy ML tags (characters included) so tags carry over
        for tr in db.execute("SELECT tag_id,score,source FROM image_tags WHERE image_id=?", (img_id,)).fetchall():
            db.execute("INSERT OR IGNORE INTO image_tags (image_id,tag_id,score,source) VALUES (?,?,?,?)",
                       (new_img_id, tr["tag_id"], tr["score"], tr["source"] or "auto"))
        copied += 1
    db.commit()
    return jsonify({"ok": True, "copied": copied, "new_ids": new_ids})


@app.route("/api/stats")
def api_stats():
    db = get_db()
    ti = db.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    tc = db.execute("SELECT COUNT(DISTINCT REPLACE(LOWER(name),'_',' ')) FROM tags WHERE category='character'").fetchone()[0]
    tf = db.execute("SELECT COUNT(DISTINCT folder) FROM images").fetchone()[0]
    top_c = db.execute("SELECT MIN(t.name) as name,COUNT(DISTINCT it.image_id) as count FROM tags t JOIN image_tags it ON t.id=it.tag_id WHERE t.category='character' GROUP BY REPLACE(LOWER(t.name),'_',' ') ORDER BY count DESC LIMIT 20").fetchall()
    top_f = db.execute("SELECT folder,COUNT(*) as count FROM images GROUP BY folder ORDER BY count DESC LIMIT 20").fetchall()
    cdist = db.execute("SELECT char_count,COUNT(*) as image_count FROM (SELECT i.id,COUNT(DISTINCT CASE WHEN t.category='character' THEN REPLACE(LOWER(t.name),'_',' ') END) as char_count FROM images i LEFT JOIN image_tags it ON i.id=it.image_id LEFT JOIN tags t ON it.tag_id=t.id GROUP BY i.id) GROUP BY char_count ORDER BY char_count").fetchall()
    return jsonify({"total_images": ti, "total_characters": tc, "total_folders": tf,
        "top_characters": [{"name": _disp_char(r["name"]), "count": r["count"]} for r in top_c], "top_folders": [dict(r) for r in top_f],
        "char_distribution": [dict(r) for r in cdist]})
