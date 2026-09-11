"""Routes: tags, ignore words and suggestions.

Layer 24 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, g, make_response, Response
)
from io import BytesIO
import os
import re
import threading
from .config import IGNORED_TAGS_FILE, Image, _MAX_WORKERS, app
from .logging_setup import log
from .db import _folder_args, _folder_cond, _name_base, _natural_sort_key, _norm_tag, _search_conditions, get_db
from .tagger import _disp_char, _disp_tag, _get_tagger, _tag_ensure_running, _tag_get_cfg, _tag_model_available, _tag_notify, _tag_progress_payload, _tag_runtime_available, _tag_save_cfg, _tag_state
from .runtime import _model_dl, _model_dl_missing, _model_dl_worker, _runtime_install_worker


@app.route("/api/tag-settings", methods=["GET", "POST"])
def api_tag_settings():
    if request.method == "POST":
        data = request.get_json() or {}
        if "enabled" in data:
            _tag_save_cfg("tag_enabled", "1" if data["enabled"] else "0")
        for k, key in (("gen", "tag_gen_threshold"), ("char", "tag_char_threshold")):
            if k in data:
                try: _tag_save_cfg(key, max(0.0, min(1.0, float(data[k]))))
                except (TypeError, ValueError): pass
        if "workers" in data:
            try: _tag_save_cfg("tag_workers", max(0, min(_MAX_WORKERS, int(data["workers"]))))
            except (TypeError, ValueError): pass
        if _tag_get_cfg()["enabled"]:
            _tag_ensure_running()   # enabling tags anything still untagged
        return jsonify(_tag_progress_payload())
    return jsonify(_tag_progress_payload())


@app.route("/api/tag/install", methods=["POST"])
def api_tag_install():
    # v3.61: user-triggered optional model download.
    # v3.85: the same button also installs the runtime, so a fresh install that
    # never tags never pays for the ~2.5 GB of CUDA/cuDNN wheels.
    if not _model_dl["active"]:
        if not _tag_runtime_available():
            _model_dl["active"] = True
            threading.Thread(target=_runtime_install_worker, daemon=True,
                             name="rt-install").start()
        elif _model_dl_missing():
            _model_dl["active"] = True
            threading.Thread(target=_model_dl_worker, daemon=True).start()
    return jsonify(_tag_progress_payload())


@app.route("/api/tag/start", methods=["POST"])
def api_tag_start():
    if not _tag_get_cfg()["enabled"]:
        return jsonify({"error": "Auto-tagging is disabled"}), 400
    if not _tag_runtime_available():
        return jsonify({"error": "The auto-tagging runtime is not installed \u2014 install it in Settings"}), 400
    if not _tag_model_available():
        return jsonify({"error": "Model files not found in models/wd-eva02-large-tagger-v3"}), 400
    _tag_state["cancel"] = False
    _tag_ensure_running()
    return jsonify(_tag_progress_payload())


@app.route("/api/tag/stop", methods=["POST"])
def api_tag_stop():
    _tag_state["cancel"] = True
    _tag_notify(force=True)
    return jsonify(_tag_progress_payload())


@app.route("/api/tag/retag-all", methods=["POST"])
def api_tag_retag_all():
    db = get_db()
    db.execute("UPDATE images SET tagged=0")
    db.commit()
    _tag_state["cancel"] = False
    _tag_ensure_running()
    return jsonify(_tag_progress_payload())


@app.route("/api/characters")
def api_characters():
    db = get_db()
    folders, subs = _folder_args()
    search = request.args.get("search", "")

    # v3.47: Names column = filename bases, grouped on the fly (no DB tables).
    conds, params = [], []
    _fc, _fp = _folder_cond(folders, subs)
    if _fc:
        conds.append(_fc); params.extend(_fp)
    if search:
        sc, sp = _search_conditions(search); conds.extend(sc); params.extend(sp)
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    groups = {}
    for r in db.execute(f"SELECT i.filename FROM images i{where}", params).fetchall():
        base = _name_base(r["filename"])
        key = _norm_tag(base)
        if not key: continue
        g = groups.get(key)
        if g: g["image_count"] += 1
        else: groups[key] = {"id": 0, "name": re.sub(r"\s+", " ", base.replace("_", " ")).strip(), "image_count": 1}
    rest = sorted(groups.values(), key=lambda x: _natural_sort_key(x["name"]))

    # Rating pseudo-tags, constrained by the same filter
    rconds, rparams = ["i.rating>0"], []
    if _fc:
        rconds.append(_fc); rparams.extend(_fp)
    if search:
        sc, sp = _search_conditions(search); rconds.extend(sc); rparams.extend(sp)
    rating_rows = db.execute(
        f"SELECT i.rating as rating, COUNT(*) as cnt FROM images i WHERE {' AND '.join(rconds)} GROUP BY i.rating ORDER BY i.rating",
        rparams).fetchall()
    rating_tags = [{"id": -r["rating"], "name": str(r["rating"]), "image_count": r["cnt"]} for r in rating_rows]
    return jsonify(rating_tags + rest)


@app.route("/api/tags")
def api_tags():
    # v3.31: ML auto-tag list for the sidebar (Booru order: most common first).
    # v3.46: character tags live in the Characters column, so exclude them here.
    db = get_db()
    folders, subs = _folder_args()
    search = request.args.get("search", "")
    conds, params = [], []
    _fc, _fp = _folder_cond(folders, subs)
    if _fc:
        conds.append(_fc); params.extend(_fp)
    if search:
        sc, sp = _search_conditions(search); conds.extend(sc); params.extend(sp)
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    rows = db.execute(f"""
        SELECT t.id, t.name, t.category, COUNT(DISTINCT it.image_id) as image_count
        FROM tags t
        JOIN image_tags it ON t.id=it.tag_id
        JOIN images i ON it.image_id=i.id{where}
        GROUP BY t.id ORDER BY image_count DESC, t.name COLLATE NOCASE ASC
    """, params).fetchall()
    return jsonify([{"id": r["id"], "name": _disp_tag(r["name"]), "category": r["category"],
                     "image_count": r["image_count"]} for r in rows])


def _verify_by_tags(db, ids, qtags, items):
    """v4.33: 'Verify with tags' for a single-image scan.

    The folder view has had this since v3.53 -- a pixel match only counts if the
    two images also share at least 30% of their tags. The query view had the
    checkbox nowhere, so the same scan gave a different answer depending on how
    it was started. Same rule here: fewer than three tags on either side means no
    reliable tag context, so the pair is left alone rather than thrown away."""
    if not qtags or len(qtags) < 3:
        return items
    tsets = {}
    idl = list(ids)
    for k in range(0, len(idl), 900):
        chunk = idl[k:k + 900]
        ph = ",".join("?" * len(chunk))
        for iid, tid in db.execute(f"SELECT image_id, tag_id FROM image_tags WHERE image_id IN ({ph})", chunk):
            tsets.setdefault(iid, set()).add(tid)
    out = []
    for m in items:
        s = tsets.get(m["id"])
        if not s or len(s) < 3:
            out.append(m); continue
        inter = len(qtags & s)
        if 13 * inter >= 3 * (len(qtags) + len(s)):   # Jaccard >= 0.3
            out.append(m)
    return out


def _upload_tag_ids(db, raw):
    """Tag an uploaded image in memory and map its tags onto library tag ids.

    Nothing is written: the bytes are never stored, no row is created, no tag is
    inserted. Only ids that already exist in the library can match anyway, so
    reading is all this needs. If the tagger is not installed the result is
    empty and _verify_by_tags then leaves the matches untouched."""
    try:
        tagger = _get_tagger()
        if tagger is None:
            return set()
        cfg = _tag_get_cfg()
        with Image.open(BytesIO(raw)) as _im:
            res = tagger.tag_image(_im.convert("RGB"), gen_threshold=cfg["gen"], char_threshold=cfg["char"])
        out = set()
        for t in res.all:
            r = db.execute("SELECT id FROM tags WHERE REPLACE(LOWER(name),'_',' ')=?", (_norm_tag(t.name),)).fetchone()
            if r: out.add(r[0])
        return out
    except Exception as e:
        log(f"Tag verification for the dropped image was skipped: {type(e).__name__}", "warning")
        return set()


@app.route("/api/suggest-tags")
def api_suggest_tags():
    """v3.46: suggestions for the Tags panel add-input — character + general ML tags,
    labeled, underscore-normalized, and (with ?image_id=) excluding tags the image
    already carries."""
    db = get_db()
    q = _norm_tag(request.args.get("q", ""))
    if not q: return jsonify([])
    image_id = request.args.get("image_id", type=int)
    existing = set()
    if image_id:
        existing = {_norm_tag(r["name"]) for r in db.execute(
            "SELECT t.name FROM tags t JOIN image_tags it ON t.id=it.tag_id WHERE it.image_id=?",
            (image_id,)).fetchall()}
    out = []
    for r in db.execute("""SELECT MIN(t.name) name, COUNT(DISTINCT it.image_id) cnt FROM tags t
        JOIN image_tags it ON t.id=it.tag_id
        WHERE t.category='character' AND REPLACE(LOWER(t.name),'_',' ') LIKE ?
        GROUP BY REPLACE(LOWER(t.name),'_',' ') ORDER BY cnt DESC LIMIT 10""",
        (f"%{q}%",)).fetchall():
        if _norm_tag(r["name"]) in existing: continue
        out.append({"name": _disp_char(r["name"]), "value": _disp_char(r["name"]), "count": r["cnt"], "type": "name"})
    for r in db.execute("""SELECT MIN(t.name) name, COUNT(DISTINCT it.image_id) cnt FROM tags t
        JOIN image_tags it ON t.id=it.tag_id
        WHERE t.category!='character' AND REPLACE(LOWER(t.name),'_',' ') LIKE ?
        GROUP BY REPLACE(LOWER(t.name),'_',' ') ORDER BY cnt DESC LIMIT 10""",
        (f"%{q}%",)).fetchall():
        if _norm_tag(r["name"]) in existing: continue
        out.append({"name": _disp_tag(r["name"]), "value": _disp_tag(r["name"]), "count": r["cnt"], "type": "auto"})
    out.sort(key=lambda x: (0 if _norm_tag(x["name"]).startswith(q) else 1, -x["count"]))
    return jsonify(out[:14])


@app.route("/api/suggest")
def api_suggest():
    """v3.46: search-box suggestions — character tags (gold), general ML tags (teal),
    FOLDERS (blue) and metadata words. Underscore-normalized matching."""
    db = get_db()
    q = _norm_tag(request.args.get("q", ""))
    if len(q) < 1: return jsonify([])
    results = {}
    # Filename bases (Names column)
    bases = {}
    for r in db.execute("SELECT filename FROM images WHERE REPLACE(LOWER(filename),'_',' ') LIKE ?",
                        (f"%{q}%",)).fetchall():
        base = _name_base(r["filename"])
        key = _norm_tag(base)
        if q not in key: continue
        b = bases.get(key)
        if b: b["count"] += 1
        else: bases[key] = {"name": base.replace("_", " "), "value": base.replace("_", " "), "count": 1, "type": "tag"}
    for b in sorted(bases.values(), key=lambda x: -x["count"])[:8]:
        results[b["name"].lower()] = b
    # ML tags (characters included — gold text lives in the Tags column)
    for r in db.execute("""SELECT MIN(t.name) name, COUNT(DISTINCT it.image_id) cnt FROM tags t
        JOIN image_tags it ON t.id=it.tag_id
        WHERE REPLACE(LOWER(t.name),'_',' ') LIKE ?
        GROUP BY REPLACE(LOWER(t.name),'_',' ') ORDER BY cnt DESC LIMIT 8""",
        (f"%{q}%",)).fetchall():
        d = _disp_tag(r["name"])
        if d.lower() not in results:
            results[d.lower()] = {"name": d, "value": d, "count": r["cnt"], "type": "mltag"}
    # Folders — display the path FROM the matched segment on (v3.47)
    for r in db.execute("""SELECT folder, COUNT(*) cnt FROM images
        WHERE REPLACE(LOWER(folder),'_',' ') LIKE ? GROUP BY folder ORDER BY cnt DESC LIMIT 5""",
        (f"%{q}%",)).fetchall():
        segs = [x for x in re.split(r"[\\/]", r["folder"]) if x]
        idx = next((k for k, sg in enumerate(segs) if q in _norm_tag(sg)), len(segs) - 1)
        disp = "\\" + "\\".join(segs[idx:])
        results["\x00f:" + r["folder"].lower()] = {"name": disp, "value": r["folder"],
            "hint": r["folder"], "count": r["cnt"], "type": "folder"}
    # Metadata word matches (single-word only)
    if " " not in q:
        word_counts = {}
        for r in db.execute("SELECT search_text FROM images WHERE search_text LIKE ?", (f"%{q}%",)).fetchall():
            for word in r["search_text"].split():
                if q in word and len(word) >= 2:
                    word_counts[word] = word_counts.get(word, 0) + 1
        for word, cnt in sorted(word_counts.items(), key=lambda x: -x[1])[:15]:
            nice = word.title()
            if nice.lower() not in results and cnt >= 2:
                results[nice.lower()] = {"name": nice, "value": nice, "count": cnt, "type": "meta"}
    out = sorted(results.values(), key=lambda x: (-1 if _norm_tag(x["name"]).startswith(q) or _norm_tag(x.get("value","")).startswith(q) else 0, -x["count"]))
    return jsonify(out[:12])


def _save_ignore_file(db):
    """Write the ignore words to ignored_tags.txt. v4.14: only once there is
    something to write. The file used to be created empty on the first save and
    then shipped that way, which made it look like a file the user had to fill
    in. An empty list removes it again instead of leaving a husk behind."""
    words = [r["word"] for r in db.execute("SELECT word FROM ignore_words ORDER BY word").fetchall()]
    try:
        if not words:
            if os.path.exists(IGNORED_TAGS_FILE):
                os.remove(IGNORED_TAGS_FILE)
            return
        with open(IGNORED_TAGS_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(words))
    except OSError as e:
        log(f"Could not write ignored_tags.txt: {e}", "warning")


def _load_ignore_file():
    """Load ignored_tags.txt into DB on startup (merge)."""
    if not os.path.exists(IGNORED_TAGS_FILE):
        return
    try:
        with open(IGNORED_TAGS_FILE, "r", encoding="utf-8") as f:
            words = [w.strip().lower() for w in f.readlines() if w.strip()]
        if words:
            db = get_db()
            for w in words:
                db.execute("INSERT OR IGNORE INTO ignore_words (word) VALUES (?)", (w,))
            db.commit()
            print(f"  ✓ Loaded {len(words)} ignored tags from ignored_tags.txt")
    except Exception as e:
        print(f"  ⚠ Could not load ignored_tags.txt: {e}")


@app.route("/api/ignore-words", methods=["GET","POST","DELETE"])
def api_ignore_words():
    db = get_db()
    if request.method == "GET":
        return jsonify([r["word"] for r in db.execute("SELECT word FROM ignore_words ORDER BY word").fetchall()])
    if request.method == "POST":
        w = request.get_json().get("word","").strip()
        if not w: return jsonify({"error": "No word"}), 400
        db.execute("INSERT OR IGNORE INTO ignore_words (word) VALUES (?)", (w.lower(),))
        db.commit(); _save_ignore_file(db); return jsonify({"ok": True})
    if request.method == "DELETE":
        w = request.get_json().get("word","").strip()
        if not w: return jsonify({"error": "No word"}), 400
        db.execute("DELETE FROM ignore_words WHERE word=? COLLATE NOCASE", (w,))
        db.commit(); _save_ignore_file(db); return jsonify({"ok": True})
