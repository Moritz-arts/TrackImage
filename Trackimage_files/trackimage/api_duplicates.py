"""Routes: duplicates and similar.

Layer 25 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, g, make_response, Response
)
import threading
import time as _time
from .config import HAS_PHASH, app
from .db import _db_commit_retry, _db_write_lock, _folder_args, _get_thread_db, get_db
from .media import get_filepath_hash
from .hashing import _sim_pct
from .processing import _hash_progress, _proc, _proc_counts, _rate_eta
from .duplicates import _compute_simtag_pairs, _dup_progress, _ensure_mem_pairs, _group_cache, _groups_from_db, _ignored_apply, _ignored_load, _ignored_lock, _ignored_pairs, _mem_pairs_ready, _popcount_func, _simgroup_cache, _simtag_cache, _simtag_groups, _simtag_lock, _simtag_progress, _tag_signature
from .api_tags import _verify_by_tags


@app.route("/api/duplicates")
def api_duplicates():
    if not HAS_PHASH:
        return jsonify({"error": "numpy not installed"}), 400
    db = get_db()
    threshold = int(request.args.get("threshold", 12))
    folders, subs = _folder_args()
    sort = request.args.get("sort", "size")
    characters = request.args.getlist("character")   # v3.29: tag filter (AND), same as gallery
    search = request.args.get("search", "")          # v3.30: search filter, same as gallery
    rating = [int(r) for r in request.args.getlist("rating") if r.isdigit() and 1 <= int(r) <= 9]  # v3.65: multi rating, same as gallery
    verify = request.args.get("verify") == "1"       # v3.53: tag verification
    show_ignored = request.args.get("show_ignored") == "1"   # v3.89
    # v3.12 (point 8): never scan duplicates on incomplete data. While the
    # background pool still has images to process, report 'computing' with the
    # PROCESSING progress so the UI waits and polls until everything is hashed.
    try:
        _tot, _done = _proc_counts(db)
    except Exception:
        _tot = _done = 0
    _pending = max(0, _tot - _done)
    if _pending > 0 or _proc.get("running"):
        _r, _eta = _rate_eta("proc", _done, _tot)
        return jsonify({"computing": True, "phase": "processing", "pending": _pending,
                        "progress": round(_done / max(1, _tot) * 100),
                        "rate": _r, "eta": _eta, "done": _done, "total": _tot,
                        "groups": [], "total_groups": 0, "total_duplicates": 0, "hashed": _done})
    if _hash_progress["active"]:   # v3.70: gap-fill hashing first, pair scan after
        return jsonify({"computing": True,
                        "progress": round(_hash_progress["current"] / max(1, _hash_progress["total"]) * 100) if _hash_progress["total"] else 0,
                        "groups": [], "total_groups": 0, "total_duplicates": 0, "hashed": 0})
    if _dup_progress["active"]:
        _r, _eta = _rate_eta("dup", _dup_progress["current"], _dup_progress["total"])
        return jsonify({"computing": True, "phase": "comparing",
                        "progress": round(_dup_progress["current"] / max(1, _dup_progress["total"]) * 100),
                        "rate": _r, "eta": _eta,
                        "done": _dup_progress["current"], "total": _dup_progress["total"],
                        "groups": [], "total_groups": 0, "total_duplicates": 0, "hashed": 0})
    if not _mem_pairs_ready(db, threshold):   # v3.66: pairs live in RAM, computed on demand
        _ensure_mem_pairs(threshold)
        return jsonify({"computing": True,
                        "progress": round(_dup_progress["current"] / max(1, _dup_progress["total"]) * 100) if _dup_progress["total"] else 0,
                        "groups": [], "total_groups": 0, "total_duplicates": 0, "hashed": 0})
    # Check in-memory cache
    _ign_n = len(_ignored_load(db))
    gc = _group_cache
    if gc.get("show_ignored") != show_ignored:
        gc["ts"] = 0
    if gc["threshold"] == threshold and gc["folder"] == folders and gc.get("subs") == subs and gc["sort"] == sort and gc.get("characters") == characters and gc.get("search") == search and gc.get("verify") == verify and gc.get("rating") == rating and gc["ts"] > _time.time() - 300:
        return jsonify({"groups": gc["groups"], "total_groups": len(gc["groups"]),
                        "total_duplicates": sum(len(g["images"]) for g in gc["groups"]),
                        "hashed": gc["n"], "ignored_pairs": _ign_n, "showing_ignored": show_ignored})
    n_hashed = db.execute("SELECT COUNT(*) FROM images WHERE phash IS NOT NULL AND phash != ''").fetchone()[0]
    groups = _groups_from_db(db, threshold, folders, subs, sort, characters, search, verify, rating, show_ignored)
    _group_cache.update({"threshold": threshold, "folder": folders, "subs": subs, "sort": sort, "characters": characters, "search": search, "verify": verify, "rating": rating, "groups": groups, "n": n_hashed, "ts": _time.time(), "show_ignored": show_ignored})
    return jsonify({"groups": groups, "total_groups": len(groups),
                    "total_duplicates": sum(len(g["images"]) for g in groups),
                    "ignored_pairs": _ign_n, "showing_ignored": show_ignored,
                    "hashed": n_hashed})


@app.route("/api/similar/<int:image_id>")
def api_find_similar(image_id):
    """Find similar images using live in-memory comparison (O(n), fast)."""
    if not HAS_PHASH:
        return jsonify({"error": "numpy not installed"}), 400
    db = get_db()
    max_dist = int(request.args.get("threshold", 128))
    verify = request.args.get("verify") == "1"      # v4.33
    target = db.execute("SELECT id,filename,folder,filepath,media_type,phash,width,height,file_size FROM images WHERE id=?", (image_id,)).fetchone()
    if not target or not target["phash"]:
        return jsonify({"error": "Image not found or not hashed"}), 404
    try: ph1 = int(target["phash"], 16)
    except: return jsonify({"error": "Invalid hash"}), 400
    popcount = _popcount_func()
    rows = db.execute("SELECT id,filename,folder,filepath,media_type,phash,width,height,file_size FROM images WHERE phash IS NOT NULL AND phash != '' AND id != ?", (image_id,)).fetchall()
    results = []
    for r in rows:
        try: ph2 = int(r["phash"], 16)
        except: continue
        dist = popcount(ph1 ^ ph2)
        if dist <= max_dist:
            similarity = _sim_pct(dist)
            results.append({"id": r["id"], "filename": r["filename"], "folder": r["folder"],
                            "fphash": get_filepath_hash(r["filepath"]), "media_type": r["media_type"] or "image",
                            "similarity": similarity, "distance": dist,
                            "width": r["width"] or 0, "height": r["height"] or 0,
                            "file_size": r["file_size"] or 0})
    if verify and results:
        qtags = {r[0] for r in db.execute("SELECT tag_id FROM image_tags WHERE image_id=?", (image_id,))}
        results = _verify_by_tags(db, [m["id"] for m in results], qtags, results)
    results.sort(key=lambda x: x["distance"])
    target_d = {"id": target["id"], "filename": target["filename"], "folder": target["folder"],
                "fphash": get_filepath_hash(target["filepath"]), "media_type": target["media_type"] or "image",
                "width": target["width"] or 0, "height": target["height"] or 0,
                "file_size": target["file_size"] or 0}
    return jsonify({"target": target_d, "similar": results})


@app.route("/api/similar-tags")
def api_similar_tags():
    db = get_db()
    min_sim = max(50, min(99, int(request.args.get("threshold", 70))))
    folders, subs = _folder_args()
    sort = request.args.get("sort", "size")
    characters = request.args.getlist("character")
    search = request.args.get("search", "")
    rating = [int(r) for r in request.args.getlist("rating") if r.isdigit() and 1 <= int(r) <= 9]  # v3.65: multi rating
    n_tagged = db.execute("SELECT COUNT(DISTINCT image_id) FROM image_tags").fetchone()[0]
    if n_tagged < 2:
        return jsonify({"error": "no_tags", "tagged": n_tagged}), 400
    if _simtag_progress["active"]:
        return jsonify({"computing": True,
                        "progress": round(_simtag_progress["current"] / max(1, _simtag_progress["total"]) * 100),
                        "groups": [], "total_groups": 0, "total_duplicates": 0, "hashed": n_tagged})
    sig = _tag_signature(db)
    if _simtag_cache["pairs"] is None or _simtag_cache.get("sig") != sig:
        with _simtag_lock:
            if not _simtag_progress["active"]:
                _simtag_progress.update({"active": True, "current": 0, "total": 1})
                threading.Thread(target=_compute_simtag_pairs, args=(sig,), daemon=True).start()
        return jsonify({"computing": True, "progress": 0,
                        "groups": [], "total_groups": 0, "total_duplicates": 0, "hashed": n_tagged})
    gc = _simgroup_cache
    if (gc["threshold"] == min_sim and gc["folder"] == folders and gc.get("subs") == subs and gc["sort"] == sort
            and gc.get("characters") == characters and gc.get("search") == search
            and gc.get("rating") == rating and gc.get("sig") == sig):
        groups = gc["groups"]
    else:
        groups = _simtag_groups(db, min_sim, folders, subs, sort, characters, search, rating)
        gc.update({"threshold": min_sim, "folder": folders, "subs": subs, "sort": sort, "characters": characters,
                   "search": search, "rating": rating, "groups": groups, "sig": sig, "ts": _time.time()})
    return jsonify({"groups": groups, "total_groups": len(groups),
                    "total_duplicates": sum(len(g["images"]) for g in groups),
                    "hashed": n_tagged})


@app.route("/api/similar-tags/<int:image_id>")
def api_similar_tags_one(image_id):
    """Per-image 'Find Similar' (context menu): exact Jaccard against all tagged images."""
    db = get_db()
    target = db.execute("SELECT id,filename,folder,filepath,media_type FROM images WHERE id=?", (image_id,)).fetchone()
    if not target:
        return jsonify({"error": "Image not found"}), 404
    tset = {r[0] for r in db.execute("SELECT tag_id FROM image_tags WHERE image_id=?", (image_id,))}
    if not tset:
        return jsonify({"error": "This image has no tags yet — run auto-tagging first."}), 400
    sets = {}
    for iid, tid in db.execute("SELECT image_id, tag_id FROM image_tags"):
        if iid == image_id: continue
        s = sets.get(iid)
        if s is None: sets[iid] = s = set()
        s.add(tid)
    scored = []
    tlen = len(tset)
    for iid, s in sets.items():
        inter = len(tset & s)
        if not inter: continue
        sim = int(round(inter / (tlen + len(s) - inter) * 100))
        if sim >= 50:
            scored.append((iid, sim))
    scored.sort(key=lambda x: -x[1])
    scored = scored[:800]
    results = []
    for k in range(0, len(scored), 900):
        chunk = scored[k:k + 900]
        ph = ",".join("?" * len(chunk))
        rows = db.execute(f"SELECT id,filename,folder,filepath,media_type,width,height,file_size "
                          f"FROM images WHERE id IN ({ph})",
                          [c[0] for c in chunk]).fetchall()
        rmap = {r["id"]: r for r in rows}
        for iid, sim in chunk:
            r = rmap.get(iid)
            if not r: continue
            results.append({"id": r["id"], "filename": r["filename"], "folder": r["folder"],
                            "fphash": get_filepath_hash(r["filepath"]), "media_type": r["media_type"] or "image",
                            "width": r["width"] or 0, "height": r["height"] or 0,
                            "file_size": r["file_size"] or 0,
                            "similarity": sim, "distance": 100 - sim})
    target_d = {"id": target["id"], "filename": target["filename"], "folder": target["folder"],
                "fphash": get_filepath_hash(target["filepath"]), "media_type": target["media_type"] or "image"}
    return jsonify({"target": target_d, "similar": results})


@app.route("/api/duplicates/ignore", methods=["POST"])
def api_duplicates_ignore():
    """v3.89: mark every pair inside a group as a wanted duplicate (or undo that).
    Only rows in ignored_pairs are written -- no image row and no file is touched."""
    data = request.get_json() or {}
    add = bool(data.get("ignore", True))
    if data.get("all") and not add:          # restore everything at once
        db = _get_thread_db()
        try:
            with _db_write_lock:
                db.execute("DELETE FROM ignored_pairs")
                _db_commit_retry(db)
        finally:
            db.close()
        with _ignored_lock:
            _ignored_pairs["set"] = None
        _group_cache["ts"] = 0
        return jsonify({"ok": True, "restored_all": True, "ignored_pairs": 0})
    ids = [int(i) for i in (data.get("ids") or []) if str(i).isdigit()]
    if len(ids) < 2:
        return jsonify({"error": "Need at least two images"}), 400
    n = _ignored_apply(ids, add=add)
    return jsonify({"ok": True, "pairs": n, "ignored_pairs": len(_ignored_load())})


@app.route("/api/duplicates/cancel", methods=["POST"])
def api_duplicates_cancel():
    """Stop a running duplicate comparison. Whatever the workers already found is
    kept and returned -- nothing is thrown away."""
    if _dup_progress.get("active"):
        _dup_progress["cancel"] = True
        return jsonify({"ok": True, "cancelling": True})
    return jsonify({"ok": True, "cancelling": False})
