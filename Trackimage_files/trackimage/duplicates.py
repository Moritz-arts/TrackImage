"""Finding pairs, grouping them, and similar-by-tag.

Layer 14 of 27 -- see trackimage/__init__.py for the order these load in.
"""
import sqlite3
import threading
import time as _time
from .config import HAS_NUMPY, MAX_DUP_DIST, _MAX_WORKERS, _MEM_PAIR_MIN_THR, _POPCOUNT_LUT, app, np
from .logging_setup import log
from .platform_bits import _boost_thread_qos
from .db import _db_commit_retry, _db_write_lock, _folder_cond, _get_thread_db, _name_base_conds, _search_conditions
from .media import get_filepath_hash
from .hashing import _sim_pct
from .processing import _proc, _unlink_progress


_dup_progress = {"active": False, "current": 0, "total": 0, "cancel": False}   # v3.73: cancel


def _embedding_has_backlog():
    """v3.17: pairing yields to embedding ONLY when embedding has real queued work
    -- NOT for the ~12s idle-worker drain after a run finishes, nor for a one-off
    priority request while the user browses. Previously any transient _proc.running
    aborted the whole pairing rebuild, which then restarted from zero, so the
    pairing bar looked frozen on large libraries. Uses the in-memory run counters
    (no DB hit); total-done is the work still outstanding in the current run."""
    if _unlink_progress.get("active"):   # v3.20: yield while an unlink wipes the DB
        return True
    if not _proc.get("running"):
        return False
    return (int(_proc.get("total", 0)) - int(_proc.get("done", 0))) > 0


def _popcount_func():
    try:
        (0).bit_count()
        return lambda x: x.bit_count()
    except AttributeError:
        return lambda x: bin(x).count('1')


def _pack_hashes_np(hex_list):
    """Pack hex hashes into an (N, W) uint8 matrix (big-endian, zero-padded) plus a
    validity mask. Zero-padding does not change the integer value, so popcount(a^b)
    over the bytes is bit-identical to the pure-Python int distance."""
    ints = []
    width = 1
    for h in hex_list:
        try:
            v = int(h, 16); ints.append(v)
            bl = (v.bit_length() + 7) // 8
            if bl > width: width = bl
        except Exception:
            ints.append(None)
    mat = np.zeros((len(ints), width), dtype=np.uint8)
    valid = np.zeros(len(ints), dtype=bool)
    for i, v in enumerate(ints):
        if v is None: continue
        mat[i] = np.frombuffer(v.to_bytes(width, "big"), dtype=np.uint8)
        valid[i] = True
    return mat, valid


_mem_lock = threading.Lock()


_mem_hash = {"sig": None, "ids": [], "ints": [], "ars": [], "mat": None, "valid": None, "ar_np": None}


_mem_pairs = {"sig": None, "threshold": -1, "pairs": None, "last_log": None}


_mem_compute = {"on": False}


def _mem_invalidate():
    """Drop the RAM hash matrix / pair cache; the next Duplicates view recomputes."""
    with _mem_lock:
        _mem_hash["sig"] = None
        _mem_pairs["sig"] = None; _mem_pairs["pairs"] = None; _mem_pairs["threshold"] = -1
    _group_cache["ts"] = 0


def _hash_signature(db):
    r = db.execute("SELECT COUNT(*), COALESCE(MAX(id),0) FROM images WHERE phash IS NOT NULL AND phash != ''").fetchone()
    return (r[0], r[1])


def _load_hash_matrix(db):
    """Load (and cache) ids/hashes/aspect-ratios of every hashed image."""
    sig = _hash_signature(db)
    with _mem_lock:
        if _mem_hash["sig"] == sig:
            return _mem_hash
    rows = db.execute("SELECT id, phash, width, height FROM images WHERE phash IS NOT NULL AND phash != ''").fetchall()
    ids = [r["id"] for r in rows]
    phs = [r["phash"] for r in rows]
    ars = []
    for r in rows:
        w = r["width"] or 0; hh = r["height"] or 0
        ars.append((w / max(hh, 1)) if (w and hh) else 0.0)
    ints = []
    for h_ in phs:
        try: ints.append(int(h_, 16))
        except Exception: ints.append(None)
    entry = {"sig": sig, "ids": ids, "ints": ints, "ars": ars, "mat": None, "valid": None,
             "ar_np": None}
    if HAS_NUMPY and _POPCOUNT_LUT is not None and ids:
        mat, valid = _pack_hashes_np(phs)
        entry["mat"] = mat; entry["valid"] = valid
        entry["ar_np"] = np.asarray(ars, dtype=np.float64)
    # v3.93: the region score is gone. tile_sig stays in the database and is still
    # written on import, but nothing reads it any more -- the 8x8 matrix is
    # neither loaded nor compared.
    with _mem_lock:
        _mem_hash.clear(); _mem_hash.update(entry)
    return _mem_hash


def _compute_mem_pairs(db, threshold):
    """Compute all pairs with distance <= max(threshold, _MEM_PAIR_MIN_THR) into RAM.
    Threaded numpy pass identical to the old table rebuild, minus the writes."""
    thr = min(max(int(threshold), _MEM_PAIR_MIN_THR), MAX_DUP_DIST)
    mh = _load_hash_matrix(db)
    ids = mh["ids"]; n = len(ids)
    _dup_progress["active"] = True; _dup_progress["total"] = n; _dup_progress["current"] = 0
    _dup_progress["cancel"] = False   # v3.73
    out = []
    try:
        if mh["mat"] is not None and n >= 2:
            mat = mh["mat"]; valid = mh["valid"]; ar_np = mh["ar_np"]; ar_pos = ar_np > 0
            lk = threading.Lock()
            nthreads = max(1, min(_MAX_WORKERS, n))
            chunks = [list(range(w, n, nthreads)) for w in range(nthreads)]
            ctr = {"n": 0}
            def _worker(my_idx):
                _boost_thread_qos()
                local = []; cnt = 0
                for qi in my_idx:
                    if _dup_progress.get("cancel"):   # v3.73: keep what we have, stop early
                        break
                    if valid[qi] and qi + 1 < n:
                        sl = slice(qi + 1, n)
                        dists = _POPCOUNT_LUT[np.bitwise_xor(mat[sl], mat[qi])].sum(axis=1)
                        mask = valid[sl] & (dists <= thr)
                        if ar_np[qi] > 0:
                            ratio = ar_np[qi] / np.where(ar_pos[sl], ar_np[sl], 1.0)
                            mask &= ((~ar_pos[sl]) | (np.abs(ratio - 1.0) <= 0.30))
                        # v3.73 region score: how many of the 64 cells stayed put.
                        # Pure arithmetic on data already in RAM -- no file access.
                        # Only computed for pairs that survived the filters above,
                        # and it never removes a pair: it is reported, not enforced.
                        base = qi + 1; id_q = ids[qi]
                        for off in np.nonzero(mask)[0]:
                            k = base + int(off); oid = ids[k]
                            pa, pb = (id_q, oid) if id_q < oid else (oid, id_q)
                            local.append((pa, pb, int(dists[int(off)]), -1))
                    cnt += 1
                    if cnt >= 128:
                        with lk:
                            ctr["n"] += cnt; _dup_progress["current"] = ctr["n"]
                        cnt = 0
                with lk:
                    ctr["n"] += cnt; _dup_progress["current"] = ctr["n"]
                    out.extend(local)
            threads = [threading.Thread(target=_worker, args=(c,), daemon=True) for c in chunks if c]
            for t in threads: t.start()
            for t in threads: t.join()
        else:   # no-numpy fallback (slow, small libraries only)
            ints = mh["ints"]; ars = mh["ars"]
            popcount = _popcount_func()
            for i in range(n):
                _dup_progress["current"] = i + 1
                if ints[i] is None: continue
                for j in range(i + 1, n):
                    if ints[j] is None: continue
                    if ars[i] > 0 and ars[j] > 0 and abs(ars[i] / ars[j] - 1) > 0.30: continue
                    dd = popcount(ints[i] ^ ints[j])
                    if dd <= thr:
                        pa, pb = (ids[i], ids[j]) if ids[i] < ids[j] else (ids[j], ids[i])
                        out.append((pa, pb, dd, -1))   # v3.73: region unknown without numpy
        out.sort(key=lambda p: p[2])
        # v3.93: a cancelled run holds only part of the pairs. Storing it under the
        # current signature would serve an incomplete duplicate list on the next
        # open -- and that list is what images get deleted from. Drop it instead so
        # the next request recomputes from scratch.
        _cancelled = bool(_dup_progress.get("cancel"))
        with _mem_lock:
            if _cancelled:
                _mem_pairs["sig"] = None; _mem_pairs["pairs"] = None
            else:
                _mem_pairs["sig"] = mh["sig"]; _mem_pairs["threshold"] = thr; _mem_pairs["pairs"] = out
        _group_cache["ts"] = 0
        # v4.32: with autosync on, every idle pass of the worker pool invalidated
        # the pair cache and recomputed it, so this line appeared every few
        # seconds saying exactly the same thing. It is worth reading when the
        # answer changes and pure noise when it does not.
        _sig = (len(out), n, thr)
        _quiet = (_mem_pairs.get("last_log") == _sig)
        _mem_pairs["last_log"] = _sig
        if not _quiet:
            log(f"Duplicate compare: {len(out):,} pairs across {n:,} images (RAM, dist<={thr})"
                + (" [stopped early]" if _dup_progress.get("cancel") else ""))
    finally:
        _dup_progress["active"] = False
        _dup_progress["cancel"] = False
        _mem_compute["on"] = False


def _mem_pairs_ready(db, threshold):
    sig = _hash_signature(db)
    thr = min(max(int(threshold), 0), MAX_DUP_DIST)
    with _mem_lock:
        return (_mem_pairs["sig"] == sig and _mem_pairs["pairs"] is not None
                and _mem_pairs["threshold"] >= thr)


def _ensure_mem_pairs(threshold):
    """Kick ONE background compute of the RAM pair set (the route polls progress)."""
    with _mem_lock:
        if _mem_compute["on"]:
            return
        _mem_compute["on"] = True
    def _run():
        try:
            d = _get_thread_db()
            _compute_mem_pairs(d, threshold)
            d.close()
        except Exception as e:
            print(f"  ⚠ pair compute error: {e}")
            _mem_compute["on"] = False
            _dup_progress["active"] = False
    threading.Thread(target=_run, daemon=True).start()


def delete_pairs_for_images(db, image_ids):
    """v4.14: forget a whole batch of images in one pass.

    The single-image version below was called once per image from the bulk
    delete, and each call counted every hashed row in the database and rebuilt
    the entire pair list. On a library of this size the list holds hundreds of
    thousands of entries, so deleting nine duplicates rebuilt it nine times --
    that is where the ten to fifteen minutes went. One signature, one filter
    pass, however many images."""
    ids = set(int(i) for i in image_ids)
    if not ids:
        return
    sig = _hash_signature(db)          # once, after the whole batch is gone
    with _mem_lock:
        if _mem_pairs["pairs"] is not None:
            _mem_pairs["pairs"] = [q for q in _mem_pairs["pairs"]
                                   if q[0] not in ids and q[1] not in ids]
            _mem_pairs["sig"] = sig
        _mem_hash["sig"] = None
    _prune_group_cache(ids)


def _prune_group_cache(ids):
    """v4.14: cut the deleted images out of the cached duplicate groups instead
    of dropping the cache. Dropping it forced a full re-scan after every delete,
    which is what made clearing a set of near-identical images so tedious: delete
    nine, wait, scan again, repeat."""
    try:
        groups = _group_cache.get("groups")
        if not groups:
            _group_cache["ts"] = 0
            return
        out = []
        for g in groups:
            imgs = [im for im in (g.get("images") or []) if im.get("id") not in ids]
            if len(imgs) > 1:                 # a group of one is not a duplicate
                g = dict(g); g["images"] = imgs
                out.append(g)
        _group_cache["groups"] = out
    except Exception:
        _group_cache["ts"] = 0                # anything unexpected: fall back to a rebuild


def delete_pairs_for_image(db, image_id):
    """Remove all RAM pairs involving this image (table-free since v3.66). The pair
    cache is updated in place and re-signed, so deleting duplicates one after another
    (the normal dedupe workflow) never forces a full recompute."""
    sig = _hash_signature(db)   # signature AFTER the delete (same connection)
    with _mem_lock:
        if _mem_pairs["pairs"] is not None:
            _mem_pairs["pairs"] = [p for p in _mem_pairs["pairs"] if p[0] != image_id and p[1] != image_id]
            _mem_pairs["sig"] = sig
        _mem_hash["sig"] = None   # matrix reloads lazily on the next full compute
    _group_cache["ts"] = 0


def _groups_from_db(db, threshold, folders=None, subs=True, sort="size", characters=None, search="", verify_tags=False, rating=0, show_ignored=False):
    """Build duplicate groups using clique-based grouping — every member similar to every other.
    v3.29: folder filter is recursive (matches sub-folders too, same as the gallery, using the
    real backslash path separator) and an optional character (tag) filter restricts pairing to
    images that carry ALL the given tags."""
    characters = characters or []
    thr = min(max(int(threshold), 0), MAX_DUP_DIST)
    with _mem_lock:
        _mp = _mem_pairs["pairs"] or []
    pairs = [p for p in _mp if p[2] <= thr]   # already sorted by distance
    # v3.89: drop pairs the user marked as wanted duplicates. Done here so every
    # downstream step (grouping, sorting, counts) never sees them at all.
    _ign = _ignored_load(db)
    if _ign:
        if show_ignored:
            pairs = [p for p in pairs if _ign_key(p[0], p[1]) in _ign]
        else:
            pairs = [p for p in pairs if _ign_key(p[0], p[1]) not in _ign]
    if folders or characters or search or rating:
        conds, params = [], []
        _fc, _fp = _folder_cond(folders, subs)
        if _fc:
            conds.append(_fc); params += _fp
        if rating:
            _rl = rating if isinstance(rating, list) else [rating]
            conds.append("i.rating IN (%s)" % ",".join("?" * len(_rl))); params.extend(_rl)
        if characters:
            ca, pa = _name_base_conds(characters, "i"); conds += ca; params += pa
        if search:
            sc, sp = _search_conditions(search, "i"); conds += sc; params += sp
        rows = db.execute("SELECT i.id FROM images i WHERE " + " AND ".join(conds), params).fetchall()
        elig = {r[0] for r in rows}
        pairs = [p for p in pairs if p[0] in elig and p[1] in elig]
    if not pairs: return []
    # v3.53/54: optional tag verification — a pHash pair only counts if both
    # images also share >= 30% of their tags (Jaccard). Images with < 3 tags are
    # exempt (no reliable tag context), so untagged libraries keep working.
    if verify_tags:
        vids = {p[0] for p in pairs} | {p[1] for p in pairs}
        tsets = {}
        idl = list(vids)
        for k in range(0, len(idl), 900):
            chunk = idl[k:k + 900]
            ph2 = ",".join("?" * len(chunk))
            for iid, tid in db.execute(f"SELECT image_id, tag_id FROM image_tags WHERE image_id IN ({ph2})", chunk):
                tsets.setdefault(iid, set()).add(tid)
        def _tag_ok(x, y):
            sa, sb = tsets.get(x), tsets.get(y)
            if not sa or not sb or len(sa) < 3 or len(sb) < 3: return True
            inter = len(sa & sb)
            return 13 * inter >= 3 * (len(sa) + len(sb))   # Jaccard >= 0.3
        pairs = [p for p in pairs if _tag_ok(p[0], p[1])]
        if not pairs: return []
    # Build neighbor lookup
    neighbors = {}

    for a, b, d, *_ in pairs:
        neighbors.setdefault(a, {})[b] = d
        neighbors.setdefault(b, {})[a] = d
    # Load image data
    id_set = set(neighbors.keys())
    ph = ",".join("?" * len(id_set))
    rows = db.execute(f"SELECT id,filename,folder,filepath,media_type,width,height,file_size,rating,file_date FROM images WHERE id IN ({ph})", list(id_set)).fetchall()
    img_map = {}
    for r in rows:
        img_map[r["id"]] = {"id": r["id"], "filename": r["filename"], "folder": r["folder"],
                            "fphash": get_filepath_hash(r["filepath"]), "media_type": r["media_type"] or "image",
                            "width": r["width"] or 0, "height": r["height"] or 0,     # v3.73: badges
                            "file_size": r["file_size"] or 0,
                            # v3.83: the duplicates grid renders the gallery info card
                            "rating": r["rating"] or 0, "file_date": r["file_date"] or 0}
    # Clique-based grouping: process best pairs first
    used = set()
    groups = []
    for a, b, d, *_rg in pairs:
        if a in used or b in used: continue
        if a not in img_map or b not in img_map: continue
        group = [a, b]
        group_set = {a, b}
        used.add(a)
        used.add(b)
        candidates = set()
        for m in group:
            for nb in neighbors.get(m, {}):
                if nb not in used and nb in img_map:
                    candidates.add(nb)
        def candidate_max_dist(c):
            return max(neighbors.get(m, {}).get(c, 999) for m in group_set)
        for c in sorted(candidates, key=candidate_max_dist):
            if c in used: continue
            all_similar = True
            for m in group_set:
                if c not in neighbors.get(m, {}):
                    all_similar = False
                    break
            if all_similar:
                group.append(c)
                group_set.add(c)
                used.add(c)
                for nb in neighbors.get(c, {}):
                    if nb not in used and nb in img_map:
                        candidates.add(nb)
        if len(group) > 1:
            imgs = [img_map[m] for m in group if m in img_map]
            dists = []
            for i in range(len(group)):
                for j in range(i+1, len(group)):
                    dd = neighbors.get(group[i], {}).get(group[j], 0)
                    dists.append(dd)
            # v4.45: this was the AVERAGE of every pair in the group, which hid
            # the group's worst pair behind its best ones. A clique of ten
            # images is forty-five pairs; forty-three of them identical and two
            # of them meaningfully apart still averaged out to "100% similar".
            # A user reported exactly that: pictures differing in a raised hand,
            # presented as identical. Measured on their own those two were 27%
            # apart -- the hash had always seen it, the headline just did not
            # report it.
            #
            # The number is now the WORST pair in the group. Because groups are
            # cliques -- every member within the threshold of every other -- it
            # means what a user reads into it: EVERY picture here is at least
            # this close to EVERY other.
            worst_dist = max(dists) if dists else 0
            similarity = _sim_pct(worst_dist)
            groups.append({"images": imgs, "similarity": similarity})
    if sort == "similarity_desc":
        groups.sort(key=lambda g: g["similarity"], reverse=True)
    elif sort == "similarity_asc":
        groups.sort(key=lambda g: g["similarity"])
    else:
        groups.sort(key=lambda g: len(g["images"]), reverse=True)
    return groups


_group_cache = {"threshold": -1, "folder": "", "sort": "", "groups": [], "n": 0, "ts": 0}


_ignored_pairs = {"set": None}


_ignored_lock = threading.Lock()


def _ign_key(x, y):
    return (x, y) if x < y else (y, x)


def _ignored_load(db=None):
    """Pair set, cached in RAM. Rebuilt whenever a pair is added or removed."""
    with _ignored_lock:
        if _ignored_pairs["set"] is None:
            try:
                d = db or _get_thread_db()
                _ignored_pairs["set"] = {(r[0], r[1]) for r in
                                         d.execute("SELECT a, b FROM ignored_pairs").fetchall()}
                if db is None:
                    d.close()
            except Exception:
                _ignored_pairs["set"] = set()
        return _ignored_pairs["set"]


def _ignored_apply(ids, add=True):
    """Ignore (or restore) every pair inside the given set of image ids.
    Returns how many rows changed. Files are never touched."""
    ids = sorted({int(i) for i in ids})
    keys = [_ign_key(ids[i], ids[j]) for i in range(len(ids)) for j in range(i + 1, len(ids))]
    if not keys:
        return 0
    db = _get_thread_db()
    try:
        with _db_write_lock:
            if add:
                db.executemany("INSERT OR IGNORE INTO ignored_pairs (a,b,created_at) VALUES (?,?,?)",
                               [(a, b, _time.time()) for a, b in keys])
            else:
                db.executemany("DELETE FROM ignored_pairs WHERE a=? AND b=?", keys)
            _db_commit_retry(db)
    finally:
        db.close()
    with _ignored_lock:
        _ignored_pairs["set"] = None   # rebuild on next read
    _group_cache["ts"] = 0             # groups change -> drop the cached view
    return len(keys)


_simtag_progress = {"active": False, "current": 0, "total": 0}


_simtag_cache = {"pairs": None, "sig": "", "ts": 0}


_simtag_lock = threading.Lock()


_simgroup_cache = {"threshold": -1, "folder": "", "sort": "", "characters": None,
                   "search": "", "groups": [], "sig": "", "ts": 0}


def _tag_signature(db):
    """Cheap change-detection fingerprint of the image_tags table."""
    r = db.execute("SELECT COUNT(*), COALESCE(SUM(image_id),0), COALESCE(SUM(tag_id),0) FROM image_tags").fetchone()
    return f"{r[0]}:{r[1]}:{r[2]}"


def _compute_simtag_pairs(tag_sig):
    """Background job: build all image pairs with tag-set similarity >= 50%."""
    try:
        db = sqlite3.connect(app.config["DATABASE"])
        try:
            raw = {}
            for iid, tid in db.execute("SELECT image_id, tag_id FROM image_tags"):
                s = raw.get(iid)
                if s is None: raw[iid] = s = set()
                s.add(tid)
        finally:
            db.close()
        # images with fewer than 3 tags carry too little context to compare
        sets = {i: frozenset(s) for i, s in raw.items() if len(s) >= 3}
        pairs = []
        # 1) collapse identical tag sets (common with batch generations) — those
        #    members are 100% similar by definition and skip the heavy path.
        by_set = {}
        for iid, fs in sets.items():
            by_set.setdefault(fs, []).append(iid)
        reps = list(by_set.items())              # [(frozenset(tags), [image_ids])]
        n = len(reps)
        _simtag_progress.update({"active": True, "current": 0, "total": max(1, n + 1)})
        for fs, ids in reps:
            if len(ids) > 1:
                ids = ids[:300]                  # safety cap for degenerate cases
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        pairs.append((ids[i], ids[j], 100))
        # 2) MinHash signatures over the unique tag sets
        cand = set()
        if n >= 2 and HAS_NUMPY:
            df = {}
            for fs, _ids in reps:
                for t in fs:
                    df[t] = df.get(t, 0) + 1
            # df==1 tags can never contribute to a match — dropping them from the
            # hash universe only *raises* candidate recall, never lowers it.
            vocab = {t: k for k, t in enumerate(t for t, c in df.items() if c >= 2)}
            if vocab:
                H, B, R = 64, 16, 4
                rng = np.random.default_rng(3452)
                tag_h = rng.integers(0, 2 ** 62, size=(len(vocab), H), dtype=np.int64).astype(np.uint64)
                sigs = np.full((n, H), np.uint64(0xFFFFFFFFFFFFFFFF), dtype=np.uint64)
                for i, (fs, _ids) in enumerate(reps):
                    idx = [vocab[t] for t in fs if t in vocab]
                    if idx:
                        sigs[i] = tag_h[np.asarray(idx)].min(axis=0)
                    if (i & 1023) == 0: _simtag_progress["current"] = i >> 1
                capped = False
                for b in range(B):
                    band = np.ascontiguousarray(sigs[:, b * R:(b + 1) * R])
                    buckets = {}
                    for i in range(n):
                        buckets.setdefault(band[i].tobytes(), []).append(i)
                    for members in buckets.values():
                        m = len(members)
                        if m < 2 or m > 3000: continue
                        for x in range(m):
                            for y in range(x + 1, m):
                                cand.add((members[x], members[y]))
                        if len(cand) > 3_000_000: capped = True; break
                    if capped: break
        # 3) exact Jaccard verification of candidate representative pairs
        cl = list(cand)
        _simtag_progress["total"] = max(1, n + len(cl))
        for k, (x, y) in enumerate(cl):
            fa, ia = reps[x]; fb, ib = reps[y]
            inter = len(fa & fb)
            if inter:
                sim = int(round(inter / len(fa | fb) * 100))
                if sim >= 50:
                    for a in ia[:300]:
                        for b2 in ib[:300]:
                            pairs.append((a, b2, sim))
            if (k & 2047) == 0: _simtag_progress["current"] = n + k
        pairs.sort(key=lambda p: -p[2])
        _simtag_cache.update({"pairs": pairs, "sig": tag_sig, "ts": _time.time()})
        _simgroup_cache["threshold"] = -1        # invalidate grouped view
        log(f"Similar-tags pairing: {len(pairs):,} pairs across {len(sets):,} tagged images.")
    except Exception as e:
        log(f"Similar-tags pairing failed: {e}", "error")
        _simtag_cache.update({"pairs": [], "sig": tag_sig, "ts": _time.time()})
    finally:
        _simtag_progress.update({"active": False, "current": 0, "total": 0})


def _simtag_groups(db, min_sim, folders=None, subs=True, sort="size", characters=None, search="", rating=0):
    """Clique-based grouping of cached tag-similarity pairs — every member must
    be similar to every other member (same rule as the duplicate groups)."""
    characters = characters or []
    all_pairs = _simtag_cache["pairs"] or []
    elig = None
    if folders or characters or search or rating:
        conds, params = [], []
        _fc, _fp = _folder_cond(folders, subs)
        if _fc:
            conds.append(_fc)
            params += _fp
        if rating:
            _rl = rating if isinstance(rating, list) else [rating]
            conds.append("i.rating IN (%s)" % ",".join("?" * len(_rl))); params.extend(_rl)
        if characters:
            ca, pa = _name_base_conds(characters, "i"); conds += ca; params += pa
        if search:
            sc, sp = _search_conditions(search, "i"); conds += sc; params += sp
        rows = db.execute("SELECT i.id FROM images i WHERE " + " AND ".join(conds), params).fetchall()
        elig = {r[0] for r in rows}
    pairs = [(a, b, s) for (a, b, s) in all_pairs
             if s >= min_sim and (elig is None or (a in elig and b in elig))]
    if not pairs: return []
    neighbors = {}
    for a, b, s in pairs:
        neighbors.setdefault(a, {})[b] = s
        neighbors.setdefault(b, {})[a] = s
    img_map = {}
    idl = list(neighbors.keys())
    for k in range(0, len(idl), 900):
        chunk = idl[k:k + 900]
        ph = ",".join("?" * len(chunk))
        for r in db.execute(f"SELECT id,filename,folder,filepath,media_type,width,height,file_size,rating,file_date FROM images WHERE id IN ({ph})", chunk).fetchall():
            img_map[r["id"]] = {"id": r["id"], "filename": r["filename"], "folder": r["folder"],
                                "fphash": get_filepath_hash(r["filepath"]), "media_type": r["media_type"] or "image",
                                # v3.83: same payload as pixel mode so the gallery info card + badges work
                                "width": r["width"] or 0, "height": r["height"] or 0,
                                "file_size": r["file_size"] or 0,
                                "rating": r["rating"] or 0, "file_date": r["file_date"] or 0}
    used = set(); groups = []
    for a, b, s in pairs:                        # sorted best-first
        if a in used or b in used: continue
        if a not in img_map or b not in img_map: continue
        group = [a, b]; group_set = {a, b}
        used.add(a); used.add(b)
        candidates = set()
        for m in group:
            for nb in neighbors.get(m, {}):
                if nb not in used and nb in img_map: candidates.add(nb)
        def cand_min_sim(c):
            return min(neighbors.get(m, {}).get(c, -1) for m in group_set)
        for c in sorted(candidates, key=cand_min_sim, reverse=True):
            if c in used: continue
            if all(c in neighbors.get(m, {}) for m in group_set):
                group.append(c); group_set.add(c); used.add(c)
                for nb in neighbors.get(c, {}):
                    if nb not in used and nb in img_map: candidates.add(nb)
        if len(group) > 1:
            sims = [neighbors[group[i]][group[j]]
                    for i in range(len(group)) for j in range(i + 1, len(group))
                    if group[j] in neighbors.get(group[i], {})]
            similarity = round(sum(sims) / len(sims)) if sims else min_sim
            groups.append({"images": [img_map[m] for m in group], "similarity": similarity})
    if sort == "similarity_desc":
        groups.sort(key=lambda g: g["similarity"], reverse=True)
    elif sort == "similarity_asc":
        groups.sort(key=lambda g: g["similarity"])
    else:
        groups.sort(key=lambda g: len(g["images"]), reverse=True)
    return groups
