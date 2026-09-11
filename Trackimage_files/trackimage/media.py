"""What a file is, when it was made, and what to call a new one.

Layer 8 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from itertools import permutations
from pathlib import Path
import hashlib
import os
import platform
import re
import time as _time
from .config import VERSION
from .db import get_db


def get_file_date(filepath):
    """Return the oldest filesystem date (mtime vs ctime)."""
    try:
        stat = os.stat(filepath)
        dates = []
        if stat.st_mtime: dates.append(stat.st_mtime)
        birth = getattr(stat, 'st_birthtime', None)
        if birth: dates.append(birth)
        if platform.system() == "Windows" and stat.st_ctime:
            dates.append(stat.st_ctime)
        return min(dates) if dates else 0.0
    except: return 0.0


def get_filepath_hash(filepath):
    try:
        mt = os.path.getmtime(filepath)
    except:
        mt = 0
    return hashlib.md5(f"{VERSION}:{filepath}:{mt}".encode()).hexdigest()[:8]


def find_available_filename(directory, desired_name):
    """If desired_name exists in directory, return 'name (N).ext' with lowest free N."""
    fp = os.path.join(directory, desired_name)
    if not os.path.exists(fp):
        return desired_name
    stem = Path(desired_name).stem
    ext = Path(desired_name).suffix
    # Strip existing (N) suffix for clean base
    m = re.match(r'^(.*?)\s*\((\d+)\)$', stem)
    base = m.group(1) if m else stem
    n = 2
    while True:
        candidate = f"{base} ({n}){ext}"
        if not os.path.exists(os.path.join(directory, candidate)):
            return candidate
        n += 1
        if n > 9999:
            break
    return desired_name


def find_next_global_number(db, base_name, exclude_ids=None, media_type=None):
    """Find the highest (N) number used for base_name across ALL folders, return N+1.
    Matches: 'base_name.ext' (counts as 1), 'base_name (N).ext' patterns.
    media_type: if set, only count files with matching media_type (images/gifs/videos numbered separately).
    exclude_ids: list of image IDs to ignore (e.g. the ones being renamed)."""
    if exclude_ids is None: exclude_ids = []
    parts = re.split(r'[+]', base_name.strip())
    patterns = set()
    if len(parts) > 1:
        clean = [p.strip() for p in parts]
        # Match the real on-disk format (separators with spaces, e.g. "Oliver + Luca"),
        # plus space-less variants for backward compatibility.
        for perm in permutations(clean):
            patterns.add(' + '.join(perm))
            patterns.add('+'.join(perm))
    else:
        patterns.add(base_name.strip())

    max_n = 0
    ex_set = set(exclude_ids)
    mt_filter = " AND media_type=?" if media_type else ""
    mt_params = [media_type] if media_type else []
    for pattern in patterns:
        bare_rows = db.execute("SELECT id, filename FROM images WHERE filename LIKE ?" + mt_filter,
            [pattern + ".%"] + mt_params).fetchall()
        for row in bare_rows:
            if row["id"] in ex_set: continue
            stem = Path(row["filename"]).stem
            if stem.lower() == pattern.lower():
                max_n = max(max_n, 1)

        rows = db.execute("SELECT id, filename FROM images WHERE filename LIKE ?" + mt_filter,
            [pattern + " (%).%"] + mt_params).fetchall()
        for row in rows:
            if row["id"] in ex_set: continue
            fn = row["filename"]
            stem = Path(fn).stem
            m = re.match(r'^' + re.escape(pattern) + r'\s*\((\d+)\)$', stem, re.IGNORECASE)
            if m:
                max_n = max(max_n, int(m.group(1)))
    return max_n + 1


def resolve_display_folder(display_folder):
    """Resolve a display folder (e.g. 'output\\sub') to a real filesystem path.

    v4.39: accept either separator. The scan writes these labels with a
    backslash on every platform, while this function split them on os.sep --
    the same character on Windows, so the mismatch never showed there, and a
    silent no-match everywhere else. Both are read now and the pieces are
    rejoined with whatever this system actually uses.
    """
    db = get_db()
    want = (display_folder or "").replace("\\", "/").strip("/")
    folders = db.execute("SELECT path FROM scan_folders").fetchall()
    for sf in folders:
        root = sf["path"]
        root_name = Path(root).name
        if want == root_name:
            return root
        prefix = root_name + "/"
        if want.startswith(prefix):
            rel = want[len(prefix):]
            return os.path.join(root, *rel.split("/"))
    return None


def _free_filename(directory, filename):
    """A name in `directory` that is not taken, without touching what is there.

    v4.39: N1 -- dropping a file never overwrites one. 'shoyo.jpg' next to an
    existing 'shoyo.jpg' becomes 'shoyo (2).jpg'. The two may well be different
    pictures that happen to share a name, and the one already on disk is the one
    the user has had longer.
    """
    base, ext = os.path.splitext(filename)
    candidate = filename
    n = 2
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{base} ({n}){ext}"
        n += 1
        if n > 9999:                       # pathological, but never loop forever
            candidate = f"{base} ({int(_time.time())}){ext}"
            break
    return candidate


def _safe_dropped_name(name):
    """Keep only the file name itself out of whatever the browser reported.

    A dropped file carries a name chosen elsewhere. Anything that could reach
    outside the target folder -- separators, drive letters, '..' -- is stripped
    here rather than trusted.
    """
    name = (name or "").replace("\\", "/").split("/")[-1].strip()
    name = name.split(":")[-1]                      # 'C:file.jpg'
    name = "".join(c for c in name if c not in '<>:"|?*' and ord(c) >= 32)
    name = name.strip(". ")
    return name or "dropped"
