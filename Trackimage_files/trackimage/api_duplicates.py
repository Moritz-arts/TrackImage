"""Routes: duplicates and similar.

Layer 25 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, g, make_response, Response
)
import os
import threading
import time as _time
from .config import HAS_PHASH, Image, app, np
from .logging_setup import log
from .db import _db_commit_retry, _db_write_lock, _folder_args, _get_thread_db, get_db
from .media import get_filepath_hash
from .hashing import _sim_pct
from .processing import _hash_progress, _oriented_size, _proc, _proc_counts, _rate_eta
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


# ---- Smart clean -------------------------------------------------------------
# A matching hash says two pictures LOOK alike at thumbnail scale, which is not
# the same thing as being the same picture. Measured on real photographs, a
# recompressed copy sits 2-6 bits away -- and so does a shut eye, a tear or a
# changed colour; a moved finger can sit at 0. So nothing is deleted on the
# strength of the hash. Every copy is compared with the one that stays, pixel
# against pixel, and it only goes when it is that picture at a lower quality:
# the same framing, not moved by a single pixel, not changed anywhere.
#
# The limits below were calibrated on portraits, a painting, a close-up and a
# synthetic picture, each saved at JPEG 85/70/50, as PNG and downscaled three
# ways -- all of which must pass -- against the same pictures with the framing
# moved by 1-3 px, a faint tear, an eyelid 24x10 px, +8% saturation, +3%
# brightness and +5% contrast, all of which must be kept. Where the two came
# close, the limit sits on the side of keeping: a duplicate left behind costs a
# little disk, a picture deleted in error costs the picture.

_SC_CAP = 1600           # compared at up to this long edge
_SC_SHIFT = 0.8          # moved by a pixel or two: a shifted overlay fits better than the straight one
_SC_LOCAL = 2.5          # one area stands out from the pair's own compression noise by this factor
_SC_LOCAL_ABS = 6.0      # ... or by this much outright (luma, 8 px block means)
_SC_LUMA = 0.6           # brightness of the whole picture
_SC_MEDIAN = 1.0         # contrast / tone curve: every block moved a little
_SC_CHROMA = 3.2         # colour, 16 px block means of Cb/Cr
_SC_SHARP = 3.0          # detail lost or gained in one area, against the pair's own spread


def _sc_load(path, box=None):
    """Decoded, upright RGB -- or None for anything that moves. An animated GIF,
    WebP or PNG is never a lesser copy of a still, whatever its size."""
    from PIL import ImageOps
    im = Image.open(path)
    if getattr(im, "n_frames", 1) > 1 or getattr(im, "is_animated", False):
        return None
    try:
        im.draft("RGB", (box or (_SC_CAP, _SC_CAP)))   # JPEG decodes at a fraction
    except Exception:
        pass
    im = ImageOps.exif_transpose(im)
    return im.convert("RGB")


def _sc_blocks(x, bs):
    h, w = x.shape[0] // bs, x.shape[1] // bs
    return x[:h * bs, :w * bs].reshape((h, bs, w, bs) + x.shape[2:]).mean(axis=(1, 3))


def _sc_same_picture(keep, other):
    """(True, '') when other is keep at a lower quality, else (False, why).
    Both are decoded PIL images; keep has at least as many pixels."""
    from PIL import ImageFilter
    kw, kh = keep.size
    ow, oh = other.size
    # The same framing: other is keep scaled, to within rounding. A crop of even
    # a few pixels changes one side and not the other.
    if abs(kh * ow / kw - oh) > max(1.5, 0.002 * oh):
        return False, "a different framing"
    tw, th = (ow, oh) if kw * kh >= ow * oh else (kw, kh)
    c = min(1.0, _SC_CAP / max(tw, th))
    tw, th = max(32, round(tw * c)), max(32, round(th * c))
    a = keep if keep.size == (tw, th) else keep.resize((tw, th), Image.LANCZOS)
    b = other if other.size == (tw, th) else other.resize((tw, th), Image.LANCZOS)
    A = np.asarray(a.convert("YCbCr"), np.float32)
    B = np.asarray(b.convert("YCbCr"), np.float32)

    # Moved by a pixel or two: slid over each other, some other offset fits
    # better than none. For a true copy the straight overlay is always best
    # (measured 1.4x or more); every shifted framing came in under 0.5x.
    ya = np.asarray(a.convert("L").filter(ImageFilter.GaussianBlur(1)), np.float32)
    yb = np.asarray(b.convert("L").filter(ImageFilter.GaussianBlur(1)), np.float32)
    m, H, W = 3, ya.shape[0], ya.shape[1]
    ref = yb[m:H - m, m:W - m]
    def _e(dx, dy):
        return float(np.abs(ya[m + dy:H - m + dy, m + dx:W - m + dx] - ref).mean())
    e0 = _e(0, 0)
    if e0 > 0.3:
        best = min(_e(dx, dy) for dx in range(-2, 3) for dy in range(-2, 3) if dx or dy)
        if best < _SC_SHIFT * e0:
            return False, "the framing is moved by a pixel or two"

    if abs(float(A[..., 0].mean() - B[..., 0].mean())) > _SC_LUMA:
        return False, "brighter or darker"
    d = np.abs(_sc_blocks(A[..., 0], 8) - _sc_blocks(B[..., 0], 8))
    if float(np.median(d)) > _SC_MEDIAN:
        return False, "a different contrast or tone"
    if float(np.abs(_sc_blocks(A[..., 1:], 16) - _sc_blocks(B[..., 1:], 16)).max()) > _SC_CHROMA:
        return False, "a different colour"
    # One area that stands out from the rest -- an eye, a tear, a hand. Measured
    # against this pair's own noise, so heavy compression spread evenly over the
    # picture does not look like a change, and a small change in a clean picture
    # does.
    worst, p99 = float(d.max()), float(np.percentile(d, 99))
    if worst > _SC_LOCAL_ABS or (worst > 1.5 and worst > _SC_LOCAL * (p99 + 0.3)):
        return False, "differs in one area"
    # Sharpness: an area softened (or sharpened) in one copy only. Compression
    # and scaling take detail away everywhere alike; a retouch takes it from one
    # place. Block means cannot see it -- a blur keeps the mean -- so the detail
    # itself (a Laplacian) is compared, block by block, in textured blocks only.
    def _detail(y):
        return _sc_blocks(np.abs(4 * y[1:-1, 1:-1] - y[:-2, 1:-1] - y[2:, 1:-1]
                                 - y[1:-1, :-2] - y[1:-1, 2:]), 16)
    la, lb = _detail(A[..., 0]), _detail(B[..., 0])
    tex = la > 2.0
    if int(tex.sum()) >= 10:
        lr = np.log((lb[tex] + 0.5) / (la[tex] + 0.5))
        dev = np.abs(lr - np.median(lr))
        top = float(dev.max())
        if top > 0.8 and top > _SC_SHARP * (float(np.percentile(dev, 99)) + 0.05):
            return False, "sharper or softer in one area"
    return True, ""


def _sc_rank(r):
    """Among copies that are equally good, the one that stays: a rating, then
    the oldest -- a copy is made after its original."""
    return (-(r["px"]), -(r["size"]), -(r["rating"] or 0), r["file_date"] or 0, r["id"])


def _sc_dominates(o, c):
    """o is at least as good as c on BOTH counts -- resolution and file size, the
    latter being the least compression at the same size -- and better on one,
    or the same on both and first in line. A copy with more pixels but a
    smaller file is not beaten by either rule, so both are kept."""
    if o["px"] < c["px"] or o["size"] < c["size"]:
        return False
    return o["px"] > c["px"] or o["size"] > c["size"] or _sc_rank(o) < _sc_rank(c)


@app.route("/api/duplicates/smart-clean", methods=["POST"])
def api_duplicates_smart_clean():
    """Plan (apply false) or carry out (apply true) the removal of the lesser
    copies in each group. A plan is only ever carried out as it was shown: the
    page sends back the pairs it confirmed, and each is checked to still exist."""
    from .api_images import trash_images
    if not HAS_PHASH:
        return jsonify({"error": "numpy not installed"}), 400
    data = request.get_json(silent=True) or {}
    db = get_db()
    if data.get("apply"):
        pairs = [(int(p.get("id")), int(p.get("keep"))) for p in (data.get("remove") or [])
                 if str(p.get("id", "")).isdigit() and str(p.get("keep", "")).isdigit()][:20000]
        # A copy that stays for one pair is never removed for another: that
        # would take away the very picture the other copies were kept against.
        keepers = {k for _i, k in pairs}
        ids = [i for i, k in pairs if i != k and i not in keepers and
               db.execute("SELECT 1 FROM images WHERE id=?", (k,)).fetchone()]
        deleted, trash_ids, errors = trash_images(db, ids)
        _group_cache["ts"] = 0
        log(f"Smart clean: {deleted} lesser cop{'y' if deleted == 1 else 'ies'} moved to the trash",
            "success" if deleted else "info")
        return jsonify({"ok": True, "deleted": deleted, "trash_ids": trash_ids, "errors": errors})

    groups = [[int(i) for i in grp if str(i).isdigit()] for grp in (data.get("groups") or [])][:5000]
    remove, skipped, freed, torn, jobs = [], [], 0, 0, []
    for grp in groups:
        grp = list(dict.fromkeys(grp))[:200]
        if len(grp) < 2:
            continue
        rows = db.execute("SELECT id, filename, folder, filepath, width, height, file_date, "
                          "media_type, rating FROM images WHERE id IN (%s)" % ",".join("?" * len(grp)),
                          grp).fetchall()
        cand = []
        for r in rows:
            if (r["media_type"] or "image") != "image":
                skipped.append({"id": r["id"], "filename": r["filename"],
                                "why": ("a video" if r["media_type"] == "video" else "a GIF") + " \u2014 never removed"})
                continue
            try:
                size = os.path.getsize(r["filepath"])
                with Image.open(r["filepath"]) as _im:     # the header: true size, and whether it moves
                    if getattr(_im, "n_frames", 1) > 1:
                        skipped.append({"id": r["id"], "filename": r["filename"],
                                        "why": "animated \u2014 never removed"})
                        continue
                    px = _oriented_size(_im)
            except Exception as e:
                skipped.append({"id": r["id"], "filename": r["filename"],
                                "why": f"could not be read ({type(e).__name__})"})
                continue
            cand.append({"id": r["id"], "filename": r["filename"], "folder": r["folder"],
                         "path": r["filepath"], "px": px[0] * px[1],
                         "size": size, "rating": r["rating"], "file_date": r["file_date"]})
        if len(cand) < 2:
            continue
        cand.sort(key=_sc_rank)
        top = [c for c in cand if not any(_sc_dominates(o, c) for o in cand if o is not c)]
        if len(top) > 1:
            torn += 1                       # the sharpest copy is not the largest file
        top_ids = {t["id"] for t in top}
        for c in cand:
            k = None if c["id"] in top_ids else next((o for o in top if _sc_dominates(o, c)), None)
            if k:
                jobs.append((c, k))

    def _check(job):
        c, k = job
        try:
            ref = _sc_load(k["path"])
            oth = _sc_load(c["path"], ref.size if ref is not None else None)
            if ref is None or oth is None:
                return False, "animated \u2014 never removed"
            return _sc_same_picture(ref, oth)
        except Exception as e:
            return False, f"could not be read ({type(e).__name__})"
    # Decoding and the array work release the GIL, so a few threads really do
    # run side by side; the pool of the background workers is left alone.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, min(4, (os.cpu_count() or 2) - 1))) as ex:
        results = list(ex.map(_check, jobs))
    kept = {}
    for (c, k), (same, why) in zip(jobs, results):
        if same:
            remove.append({"id": c["id"], "keep": k["id"], "filename": c["filename"],
                           "folder": c["folder"], "size": c["size"]})
            freed += c["size"]
            kept[k["id"]] = {"id": k["id"], "filename": k["filename"], "folder": k["folder"]}
        else:
            skipped.append({"id": c["id"], "filename": c["filename"], "why": why})
    keep = list(kept.values())
    return jsonify({"ok": True, "keep": keep, "remove": remove, "skipped": skipped,
                    "bytes": freed, "undecided": torn})
