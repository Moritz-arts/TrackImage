"""The database: connection, schema, migrations, vacuum, query helpers.

Layer 6 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, g, make_response, Response
)
from pathlib import Path
import functools
import os
import re
import sqlite3
import threading
import time as _time
from . import state
from .config import HAS_PILLOW, HAS_SEND2TRASH, VIDEO_EXTENSIONS, _IS_MP_WORKER, app, detect_media_type, send2trash
from .logging_setup import log


def _norm_base_sql(fn):
    """v3.56: normalized filename base for SQL — SAME code as the Names-column
    grouping (_norm_tag(_name_base())), so list and click can never diverge."""
    return _norm_tag(_name_base(fn or ""))


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA synchronous=NORMAL")
        g.db.execute("PRAGMA busy_timeout=15000")
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.create_function("natural_key", 1, _natural_sort_key)
        g.db.create_function("norm_base", 1, _norm_base_sql)
    return g.db


def _natural_sort_key(text):
    if not text: return ""
    return re.sub(r'(\d+)', lambda m: m.group(1).zfill(10), text.lower())


def clean_prompt_for_search(prompt):
    if not prompt: return ""
    cleaned = re.sub(r'[(){}\[\]:,.<>|/\\!?;"\'+*~`^=_]', ' ', prompt.lower())
    cleaned = re.sub(r'\b\d+\.?\d*\b', ' ', cleaned)
    return ' '.join(cleaned.split())


def extract_search_text(filepath, _raw=None):
    """Extract all metadata except negative_prompt as searchable text.
    _raw (file bytes), if given, avoids a second disk read."""
    # imported here, not at the top: db loads before metadata, and a
    # module cannot import from one that has not been built yet.
    from .metadata import extract_metadata
    ext = Path(filepath).suffix.lower()
    is_video = ext in VIDEO_EXTENSIONS
    if not HAS_PILLOW and not is_video:
        return ""
    try:
        meta = extract_metadata(filepath, _raw=_raw)
        parts = []
        for k, v in meta.items():
            if k in ("negative_prompt", "error", "raw_parameters", "comfyui_prompt",
                      "comfyui_workflow", "file_size", "video_meta_error",
                      "duration", "width_px", "height_px",
                      "major_brand", "minor_version", "compatible_brands",
                      "encoder", "handler_name", "vendor_id"): continue
            if v is not None and str(v).strip():
                parts.append(str(v).strip())
        return clean_prompt_for_search(' '.join(parts))
    except: return ""


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db: db.close()


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS scan_folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            label TEXT
        );
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL, folder TEXT NOT NULL,
            filepath TEXT NOT NULL UNIQUE,
            width INTEGER, height INTEGER, file_date REAL,
            search_text TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE
        );
        CREATE TABLE IF NOT EXISTS image_characters (
            image_id INTEGER NOT NULL, character_id INTEGER NOT NULL,
            position INTEGER DEFAULT 0,
            PRIMARY KEY (image_id, character_id),
            FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
            FOREIGN KEY (character_id) REFERENCES characters(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            category TEXT NOT NULL DEFAULT 'general'
        );
        CREATE TABLE IF NOT EXISTS image_tags (
            image_id INTEGER NOT NULL, tag_id INTEGER NOT NULL,
            score REAL DEFAULT 0, source TEXT DEFAULT 'auto',
            PRIMARY KEY (image_id, tag_id),
            FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_image_tags_tag ON image_tags(tag_id);

        -- v3.89: duplicate pairs the user marked as "wanted". Keyed by the image
        -- pair (a < b), never by group: groups are recomputed for every threshold,
        -- the distance between two images is fixed.
        CREATE TABLE IF NOT EXISTS ignored_pairs (
            a INTEGER NOT NULL, b INTEGER NOT NULL,
            created_at REAL,
            PRIMARY KEY (a, b),
            FOREIGN KEY (a) REFERENCES images(id) ON DELETE CASCADE,
            FOREIGN KEY (b) REFERENCES images(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS ignore_words (word TEXT PRIMARY KEY COLLATE NOCASE);
        -- v4.26: a folder unlink writes its root here BEFORE it touches anything,
        -- and removes it once the wipe is done. The startup sweep only ever
        -- deletes image rows while such a marker exists. Without it the sweep
        -- deleted every row that did not match a linked folder by string prefix
        -- -- and a drive letter mapped to a UNC share matches no UNC path at all,
        -- so entire libraries were wiped on a perfectly normal start.
        CREATE TABLE IF NOT EXISTS pending_unlink (
            root TEXT PRIMARY KEY,
            started_at REAL
        );
        CREATE TABLE IF NOT EXISTS trash (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_filepath TEXT NOT NULL,
            original_folder TEXT,
            original_filename TEXT,
            trash_path TEXT NOT NULL,
            width INTEGER, height INTEGER, file_date REAL,
            search_text TEXT DEFAULT '',
            characters_json TEXT DEFAULT '[]',
            deleted_at REAL
        );
    """)
    try:
        cols = [r[1] for r in db.execute("PRAGMA table_info(images)").fetchall()]
        if "thumb_hash" in cols:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS images_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL, folder TEXT NOT NULL,
                    filepath TEXT NOT NULL UNIQUE,
                    width INTEGER, height INTEGER, file_date REAL
                );
                INSERT INTO images_new (id,filename,folder,filepath,width,height)
                    SELECT id,filename,folder,filepath,width,height FROM images;
                DROP TABLE images; ALTER TABLE images_new RENAME TO images;
            """)
        elif "file_date" not in cols:
            db.execute("ALTER TABLE images ADD COLUMN file_date REAL")
        if "prompt_text" not in cols and "search_text" not in cols:
            db.execute("ALTER TABLE images ADD COLUMN search_text TEXT DEFAULT ''")
        elif "prompt_text" in cols and "search_text" not in cols:
            db.execute("ALTER TABLE images ADD COLUMN search_text TEXT DEFAULT ''")
            db.execute("UPDATE images SET search_text = prompt_text")
    except: pass
    # Add phash column for duplicate detection
    try:
        cols2 = [r[1] for r in db.execute("PRAGMA table_info(images)").fetchall()]
        if "phash" not in cols2:
            db.execute("ALTER TABLE images ADD COLUMN phash TEXT DEFAULT ''")
        if "media_type" not in cols2:
            db.execute("ALTER TABLE images ADD COLUMN media_type TEXT DEFAULT 'image'")
    except: pass
    # v4.14: indexes for the duplicate work. The hashed-image count runs on every
    # duplicate operation and used to walk the whole table; a partial index answers
    # it without touching a row. The second one serves the orphan-tag sweep that
    # follows every delete. Created here rather than with the schema, because phash
    # only exists once the migration above has added it.
    try:
        db.execute("CREATE INDEX IF NOT EXISTS idx_images_phash ON images(id) "
                   "WHERE phash IS NOT NULL AND phash != ''")
        db.execute("CREATE INDEX IF NOT EXISTS idx_image_characters_char "
                   "ON image_characters(character_id)")
        db.commit()
    except Exception:
        pass
    # Clear old 64-bit hashes (hash_size=8) — using 256-bit (hash_size=16)
    try:
        ph_ver = db.execute("SELECT value FROM config WHERE key='phash_version'").fetchone()
        if not ph_ver or ph_ver["value"] != "3":
            db.execute("UPDATE images SET phash='' WHERE length(phash) > 0 AND length(phash) < 60")
            db.execute("INSERT OR REPLACE INTO config (key,value) VALUES ('phash_version','3')")
            db.commit()
    except: pass
    # Force re-index if search_text was built with older extraction
    try:
        st_ver = db.execute("SELECT value FROM config WHERE key='search_text_version'").fetchone()
        if not st_ver or st_ver["value"] != "3":
            db.execute("UPDATE images SET search_text=''")
            db.execute("INSERT OR REPLACE INTO config (key,value) VALUES ('search_text_version','3')")
            db.commit()
    except: pass
    # Add rating column
    try:
        cols3 = [r[1] for r in db.execute("PRAGMA table_info(images)").fetchall()]
        if "rating" not in cols3:
            db.execute("ALTER TABLE images ADD COLUMN rating INTEGER DEFAULT 0")
    except: pass
    # Add source column to image_characters (auto vs manual tags)
    try:
        ic_cols = [r[1] for r in db.execute("PRAGMA table_info(image_characters)").fetchall()]
        if "source" not in ic_cols:
            db.execute("ALTER TABLE image_characters ADD COLUMN source TEXT DEFAULT 'auto'")
    except: pass
    # v3.3: background-processing state flag (0 = needs metadata/thumbnail/phash, 1 = done).
    # Lean discovery inserts new images with meta_done=0; the worker pool processes them.
    try:
        cols_md = [r[1] for r in db.execute("PRAGMA table_info(images)").fetchall()]
        if "meta_done" not in cols_md:
            db.execute("ALTER TABLE images ADD COLUMN meta_done INTEGER DEFAULT 0")
        # One-time: pre-v3.3 rows were already scanned by the old pipeline — mark them
        # done so an existing (possibly huge) collection is NOT silently re-processed.
        # A user-triggered "Reprocess all" can reset this later.
        proc_ver = db.execute("SELECT value FROM config WHERE key='proc_version'").fetchone()
        if not proc_ver:
            db.execute("UPDATE images SET meta_done=1")
            db.execute("INSERT OR REPLACE INTO config (key,value) VALUES ('proc_version','1')")
            db.commit()
    except: pass
    # v3.31: auto-tagging state flag (0 = not yet tagged by the WD model, 1 = done).
    # Existing rows start at 0 so a one-time back-fill can tag the whole library once
    # the user enables auto-tagging; new rows default to 0 and get tagged after import.
    try:
        cols_tg = [r[1] for r in db.execute("PRAGMA table_info(images)").fetchall()]
        if "tagged" not in cols_tg:
            db.execute("ALTER TABLE images ADD COLUMN tagged INTEGER DEFAULT 0")
            db.commit()
    except: pass
    # v3.78: drop stale "questionable" ratings. Before this version the tagger
    # wrote all four rating levels per image; questionable is no longer emitted
    # at all (it is resolved to sensitive/explicit), so any row carrying it is
    # left over from an older pass and would otherwise linger in the sidebar.
    try:
        db.execute("""DELETE FROM image_tags WHERE tag_id IN
                      (SELECT id FROM tags WHERE name='questionable' AND category='rating')""")
        db.execute("DELETE FROM tags WHERE name='questionable' AND category='rating'")
        db.commit()
    except Exception:
        pass
    # v3.73: file size (dedupe badges, avoids an os.stat per image on NAS shares)
    # and the 8x8 region signature used by the duplicate scan's region score.
    try:
        cols_v73 = [r[1] for r in db.execute("PRAGMA table_info(images)").fetchall()]
        if "file_size" not in cols_v73:
            db.execute("ALTER TABLE images ADD COLUMN file_size INTEGER DEFAULT 0")
        if "tile_sig" not in cols_v73:
            db.execute("ALTER TABLE images ADD COLUMN tile_sig BLOB")
        # v3.80: sticky "this file can never be hashed" marker (SVG, corrupt
        # files, unreadable codecs). Without it the duplicate scan re-decoded
        # them on every app start, because the give-up list lived in RAM only.
        if "hash_fail" not in cols_v73:
            db.execute("ALTER TABLE images ADD COLUMN hash_fail INTEGER DEFAULT 0")
        db.commit()
    except: pass
    # Backfill media_type for existing entries
    try:
        needs_mt = db.execute("SELECT id, filepath FROM images WHERE media_type IS NULL OR media_type=''").fetchall()
        if needs_mt:
            for r in needs_mt:
                mt = detect_media_type(r["filepath"]) if os.path.exists(r["filepath"]) else "image"
                db.execute("UPDATE images SET media_type=? WHERE id=?", (mt, r["id"]))
            db.commit()
    except: pass
    # v3.66: dup_pairs removed — duplicate pairs are computed on demand into RAM.
    # Existing installs: drop the table once and VACUUM (can shrink the DB by GBs).
    try:
        if db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dup_pairs'").fetchone():
            db.executescript("""
                DROP INDEX IF EXISTS idx_dup_dist;
                DROP INDEX IF EXISTS idx_dup_a;
                DROP INDEX IF EXISTS idx_dup_b;
                DROP TABLE IF EXISTS dup_pairs;
            """)
            db.commit()
            try:
                db.execute("VACUUM")
                print("  🗜 dup_pairs table removed — database vacuumed (one-time)")
            except: pass
    except: pass
    # Thumbnail cache — BLOBs in the main DB (one DB, no loose files on disk).
    # Auto-cleaned: FK cascade on image delete/unlink + orphan sweep + mtime check.
    try:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS thumb_cache (
                image_id INTEGER PRIMARY KEY,
                data BLOB NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'image/webp',
                src_mtime REAL NOT NULL DEFAULT 0,
                created_at REAL,
                FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
            );
        """)
    except: pass
    # Cache v2 (app v3.2): color pipeline corrected (validated ICC->sRGB) —
    # regenerate all thumbnails once so no wrongly tagged thumbs survive.
    try:
        tc_ver = db.execute("SELECT value FROM config WHERE key='thumb_cache_version'").fetchone()
        if not tc_ver or tc_ver["value"] != "5":
            db.execute("DELETE FROM thumb_cache")
            db.execute("INSERT OR REPLACE INTO config (key,value) VALUES ('thumb_cache_version','5')")
            db.commit()
    except: pass
    try:
        row = db.execute("SELECT value FROM config WHERE key='root_path'").fetchone()
        if row and row["value"]:
            existing = db.execute("SELECT id FROM scan_folders WHERE path=?", (row["value"],)).fetchone()
            if not existing:
                db.execute("INSERT OR IGNORE INTO scan_folders (path, label) VALUES (?, ?)",
                    (row["value"], Path(row["value"]).name))
            db.execute("DELETE FROM config WHERE key='root_path'")
    except: pass
    db.commit()


if not _IS_MP_WORKER:
    with app.app_context():
        init_db()


_folder_op_lock = threading.Lock()


def folder_op(fn):
    """Endpoint guard: only one folder operation at a time (non-blocking).
    Returns HTTP 409 if another is already in progress."""
    @functools.wraps(fn)
    def _wrapper(*args, **kwargs):
        if not _folder_op_lock.acquire(blocking=False):
            return jsonify({"error": "Another folder operation is in progress — please wait for it to finish."}), 409
        try:
            return fn(*args, **kwargs)
        finally:
            _folder_op_lock.release()
    return _wrapper


def _wal_checkpoint_now():
    """Write the WAL back into the database file and truncate it."""
    try:
        c = sqlite3.connect(app.config["DATABASE"], timeout=5)
        try:
            c.execute("PRAGMA busy_timeout=4000")
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            c.commit()
        finally:
            c.close()
        log("Database written out \u2014 write-ahead log folded back in", "info")
    except Exception as e:
        log(f"Could not fold the write-ahead log back in: {type(e).__name__}", "warning")


def _get_thread_db():
    """Get a DB connection for background threads (not Flask request context)."""
    db = sqlite3.connect(app.config["DATABASE"])
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.execute("PRAGMA busy_timeout=15000")
    db.execute("PRAGMA foreign_keys=ON")
    db.create_function("natural_key", 1, _natural_sort_key)
    db.create_function("norm_base", 1, _norm_base_sql)
    return db


_db_write_lock = threading.Lock()     # GLOBAL single-writer gate: every background


def _db_commit_retry(db, attempts=6):
    """Commit with exponential backoff if SQLite reports 'database is locked'.
    With the global write lock this is just a safety net for rare request-handler
    write overlaps. Re-raises any non-lock error and the final lock error."""
    delay = 0.05
    for i in range(attempts):
        try:
            db.commit(); return True
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() and i < attempts - 1:
                _time.sleep(delay); delay = min(delay * 2, 1.0); continue
            raise
    return False


_vacuum = {"running": False, "before": 0, "after": 0, "error": "", "at": 0.0}


def _db_file_bytes():
    """Size of the database including its WAL sidecar files."""
    total = 0
    base = app.config["DATABASE"]
    for suf in ("", "-wal", "-shm"):
        try:
            total += os.path.getsize(base + suf)
        except Exception:
            pass
    return total


def _vacuum_run(reason=""):
    """Compact the database. Returns True on success. Safe to call from any
    thread: it takes the global write lock, so no worker writes while SQLite
    rewrites the file. Readers are not blocked (WAL)."""
    import shutil as _sh
    if _vacuum["running"]:
        return False
    _vacuum.update(running=True, error="", before=0, after=0)
    try:
        base = app.config["DATABASE"]
        before = _db_file_bytes()
        _vacuum["before"] = before
        # VACUUM builds a full temporary copy -- refuse rather than fail halfway.
        try:
            free = _sh.disk_usage(os.path.dirname(os.path.abspath(base))).free
            if free < before * 1.2:
                raise IOError("not enough free disk space (%d MB needed, %d MB available)"
                              % (int(before * 1.2 / 1048576), int(free / 1048576)))
        except IOError:
            raise
        except Exception:
            pass   # disk_usage unavailable -> attempt anyway

        log("Database compaction started%s (%.1f MB)" % (
            (" after " + reason) if reason else "", before / 1048576.0))
        with _db_write_lock:
            vdb = sqlite3.connect(base, isolation_level=None, timeout=60)
            try:
                vdb.execute("PRAGMA busy_timeout=60000")
                try: vdb.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception: pass
                vdb.execute("VACUUM")
                try: vdb.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception: pass
            finally:
                vdb.close()
        after = _db_file_bytes()
        _vacuum.update(after=after, at=_time.time())
        log("Database compaction done: %.1f MB -> %.1f MB (%.1f MB freed)" % (
            before / 1048576.0, after / 1048576.0, max(0, before - after) / 1048576.0))
        return True
    except Exception as e:
        _vacuum["error"] = str(e)
        log("Database compaction failed: %s" % e, "error")
        return False
    finally:
        _vacuum["running"] = False


def _name_base(fn):
    """v3.47: filename base for the Names column — extension and a trailing
    ' (N)' counter stripped: 'Oliver (3).jpg' -> 'Oliver'."""
    stem = fn.rsplit(".", 1)[0] if "." in fn else fn
    return re.sub(r"[\s_]*\(\d+\)$", "", stem).strip() or stem


def _name_base_conds(bases, alias="i"):
    """WHERE conditions matching images whose filename base equals one of `bases`
    (normalized: '_'==' ', case-insensitive). AND semantics across bases."""
    conds, params = [], []
    for b in bases:
        conds.append(f"norm_base({alias}.filename) = ?")
        params.append(_norm_tag(b))
    return conds, params


def _norm_tag(s):
    """v3.46: canonical tag form — lowercase, '_' == ' ', collapsed whitespace."""
    return re.sub(r"\s+", " ", (s or "").lower().replace("_", " ")).strip()


def _search_conditions(search, alias="i"):
    """Build the per-term WHERE conditions for a search query (alias `i` for images).
    v3.46: terms are COMMA separated only — spaces belong to the term, and '_'
    and ' ' are interchangeable on both sides. All terms must match (AND).
    Matches filename, any tag name (characters included), or search_text."""
    conds, params = [], []
    terms = [t for t in (_norm_tag(t) for t in search.split(",")) if t]
    for term in terms:
        conds.append(f"""(REPLACE(LOWER({alias}.filename),'_',' ') LIKE ? OR {alias}.id IN (
            SELECT it2.image_id FROM image_tags it2
            JOIN tags t2 ON it2.tag_id=t2.id
            WHERE REPLACE(LOWER(t2.name),'_',' ') LIKE ?) OR REPLACE(LOWER({alias}.search_text),'_',' ') LIKE ?)""")
        params.extend([f"%{term}%", f"%{term}%", f"%{term}%"])
    return conds, params


def _folder_args():
    """Read the folder filter from the query string.

    Several `folder=` parameters select several folders at once (v3.91);
    `subfolders=0` restricts each of them to its own direct contents.
    A single `folder=` without `subfolders` behaves exactly as before.
    """
    folders = [f for f in request.args.getlist("folder") if f]
    return folders, request.args.get("subfolders", "1") != "0"


def _folder_cond(folders, subs=True, col="i.folder"):
    """OR-group over the selected folders. Returns ("", []) when nothing is selected."""
    if not folders:
        return "", []
    parts, params = [], []
    for f in folders:
        if subs:
            parts.append("({c}=? OR {c} LIKE ? OR {c} LIKE ?)".format(c=col))
            params.extend([f, f + "\\%", f + "/%"])
        else:
            parts.append("{c}=?".format(c=col))
            params.append(f)
    return "(" + " OR ".join(parts) + ")", params


def _cleanup_trash(max_age=600):
    """Move trash entries older than max_age seconds to the OS Recycle Bin.
    If send2trash is not available, files stay in internal trash (never permanently deleted)."""
    try:
        db = _get_thread_db()
        cutoff = _time.time() - max_age
        old = db.execute("SELECT id, trash_path FROM trash WHERE deleted_at < ?", (cutoff,)).fetchall()
        for r in old:
            tp = r["trash_path"]
            if tp and os.path.exists(tp):
                if HAS_SEND2TRASH:
                    try:
                        send2trash(tp)
                    except Exception as e:
                        print(f"  ⚠ Could not send to Recycle Bin: {tp} ({e})")
                        continue  # don't delete DB row if recycle bin failed
                else:
                    # No send2trash: leave file in internal trash, do NOT permanently delete
                    continue
            db.execute("DELETE FROM trash WHERE id=?", (r["id"],))
        if old:
            db.commit()
            # Clean empty .trash dir
            trash_dir = os.path.join(app.instance_path, ".trash")
            if os.path.isdir(trash_dir) and not os.listdir(trash_dir):
                try: os.rmdir(trash_dir)
                except: pass
        db.close()
    except: pass


def _start_trash_janitor(interval=60):
    """v3.12 (point 1): run _cleanup_trash periodically so the internal-trash
    timer actually fires during a running session. Once the per-item delay
    elapses, the file goes to the Recycle Bin and its trash row is deleted — so
    after the timer NO TrackImage trace of a deleted image remains (the image's
    own row + thumbnail BLOB + dup_pairs were already removed at delete time)."""
    if state._trash_janitor_started:
        return
    state._trash_janitor_started = True
    def _loop():
        while True:
            _time.sleep(interval)
            try: _cleanup_trash()
            except Exception: pass
    threading.Thread(target=_loop, daemon=True).start()
