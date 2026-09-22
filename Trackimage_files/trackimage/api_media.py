"""Routes: serving thumbnails, full images and original files.

Layer 26 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, g, make_response, Response
)
from pathlib import Path
from urllib.parse import quote as _url_quote
import hashlib
import os
from .config import VERSION, VIDEO_EXTENSIONS, VIDEO_THUMB_SVG, _VIDEO_MIME, app
from .logging_setup import log_detail
from .db import get_db
from .thumbnails import _store_thumb_cache, generate_video_thumbnail
from .processing import _dispatch_thumb, _ondemand_mark


@app.route("/thumb/<int:image_id>")
def serve_thumbnail(image_id):
    db = get_db()
    row = db.execute("SELECT filepath,filename FROM images WHERE id=?", (image_id,)).fetchone()
    if not row: return "Not found", 404
    fp = row["filepath"]
    ext = Path(row["filename"]).suffix.lower()
    try:
        st = os.stat(fp)
        mt = st.st_mtime
        # Size included: a color-profile repair preserves mtime but changes size,
        # so browser caches must be busted via the ETag.
        etag = hashlib.md5(f"{VERSION}:{image_id}:{fp}:{mt}:{st.st_size}".encode()).hexdigest()
    except:
        mt = 0
        etag = hashlib.md5(f"{VERSION}:{image_id}:{fp}".encode()).hexdigest()
    if request.headers.get("If-None-Match") == etag: return "", 304

    # Cache hit: serve stored thumbnail if the source file is unchanged
    try:
        cached = db.execute("SELECT data, content_type, src_mtime FROM thumb_cache WHERE image_id=?", (image_id,)).fetchone()
        if cached and cached["data"] and abs((cached["src_mtime"] or 0) - mt) < 1:
            resp = make_response(bytes(cached["data"]))
            resp.headers["Content-Type"] = cached["content_type"] or "image/webp"
            resp.headers["Cache-Control"] = "public, max-age=604800, immutable"
            resp.headers["ETag"] = etag
            return resp
    except: pass

    # Past this point the cache did not have it, so it is being made right now --
    # which is exactly the kind of thing Detail is switched on to see.
    log_detail("Thumbnail on demand: " + _detail_name(fp))
    if ext in VIDEO_EXTENSIONS:
        tb = generate_video_thumbnail(fp)
        if tb:
            _store_thumb_cache(db, image_id, tb, "image/jpeg", mt)
            resp = make_response(tb)
            resp.headers["Content-Type"] = "image/jpeg"
            resp.headers["Cache-Control"] = "public, max-age=604800, immutable"
            resp.headers["ETag"] = etag
            return resp
        resp = make_response(VIDEO_THUMB_SVG)
        resp.headers["Content-Type"] = "image/svg+xml"
        resp.headers["Cache-Control"] = "no-cache"
        return resp
    _ondemand_mark()               # v3.70: user is browsing -> backfill yields
    tb = _dispatch_thumb(fp)       # v3.70: decode/encode in the process pool (GIL-free)
    if tb:
        _store_thumb_cache(db, image_id, tb, "image/webp", mt)
        resp = make_response(tb)
        resp.headers["Content-Type"] = "image/webp"
        resp.headers["Cache-Control"] = "public, max-age=604800, immutable"
        resp.headers["ETag"] = etag
        return resp
    return send_from_directory(os.path.dirname(fp), os.path.basename(fp))


@app.route("/full/<int:image_id>")
def serve_full_image(image_id):
    """Note: the detail line below is what makes "what is it doing right now"
    answerable while simply browsing."""
    db = get_db()
    row = db.execute("SELECT filepath FROM images WHERE id=?", (image_id,)).fetchone()
    if not row: return "Not found", 404
    fp = row["filepath"]
    log_detail("Opened " + _detail_name(fp))
    _mt = _VIDEO_MIME.get(os.path.splitext(fp)[1].lower())   # v3.58: explicit video MIME
    resp = send_from_directory(os.path.dirname(fp), os.path.basename(fp), mimetype=_mt)
    # Always revalidate (cheap ETag 304) so a repaired color profile is
    # never hidden behind a stale browser cache.
    resp.headers["Cache-Control"] = "no-cache"
    return resp


def _detail_name(fp):
    """Folder + file, which is what makes a line in the log recognisable."""
    try:
        return os.path.join(os.path.basename(os.path.dirname(fp)), os.path.basename(fp))
    except Exception:
        return str(fp)


# The route sat on _detail_name above for a while, so /file/ answered every drag
# out of a browser tab with a 500 and the drop arrived as nothing -- or as a
# page. It belongs on the function that serves the original.
@app.route("/file/<int:image_id>")
def serve_original_file(image_id):
    """v4.12: the same bytes as /full/, but announced as a download and named.
    A drag hands this URL over, so the receiving program writes the file under its
    ORIGINAL NAME instead of the numeric id, and writes the ORIGINAL BYTES --
    nothing is re-encoded or resized on this path. Kept apart from /full/ so the
    viewer's <img>/<video> is not turned into a download by the same header."""
    db = get_db()
    row = db.execute("SELECT filepath FROM images WHERE id=?", (image_id,)).fetchone()
    if not row:
        return "Not found", 404
    fp = row["filepath"]
    if not os.path.isfile(fp):
        return "Not found", 404
    name = os.path.basename(fp)
    _mt = _VIDEO_MIME.get(os.path.splitext(fp)[1].lower())
    resp = send_from_directory(os.path.dirname(fp), name, mimetype=_mt)
    # as_attachment is not used: it would guess the name again. Setting the header
    # directly keeps the name byte-for-byte, and the UTF-8 form carries umlauts and
    # anything else the ASCII fallback cannot.
    try:
        ascii_name = name.encode("ascii", "replace").decode("ascii").replace('"', "_")
    except Exception:
        ascii_name = "file"
    resp.headers["Content-Disposition"] = (
        'attachment; filename="%s"; filename*=UTF-8\'\'%s'
        % (ascii_name, _url_quote(name)))
    resp.headers["Cache-Control"] = "no-cache"
    return resp
