"""Routes: version, events, tabs, settings, power, network.

Layer 21 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, g, make_response, Response
)
from queue import Queue, Empty
import json
import os
import re
import sqlite3
import threading
import time as _time
from . import state
from .config import DB_ON_NETWORK, HAS_PHASH, HAS_WATCHDOG, HAS_WEBVIEW, NET_DEFAULT_PW, VERSION, _AUTO_WORKERS, _MAX_WORKERS, app
from .logging_setup import _LOG_PATH, _console_lines, _console_lock, log
from .appconfig import NAS_ACTIVE, NAS_PROTECTION, _app_config_load, _app_config_save
from .updater import (check_for_update, start_install, status as update_status,
                       auto_check_enabled, set_auto_check, is_configured,
                       GITHUB_OWNER, GITHUB_REPO)
from .db import _db_commit_retry, _db_file_bytes, _db_write_lock, _get_thread_db, _vacuum, _vacuum_run, get_db
from .events import _active_tabs, _cancel_shutdown_timer, _check_shutdown, _restart_self, _tabs_lock, sse_clients, sse_lock
from .thumbnails import _thumb_cfg, _thumb_regen, _thumb_regen_worker, _thumb_target_workers, _thumb_workers_cfg
from .processing import _dispatch_compute, _hash_gaveup, _hash_progress, _mark_hash_fail, _mp_configured, _mp_set_workers, _mp_target_procs, _power_state, _proc, _proc_ensure_running, _proc_lock, _proc_notify, _proc_progress_payload, _proc_save_setting, _proc_stop
from .tagger import _tag_notify, _tag_state
from .duplicates import _dup_progress, _mem_invalidate
from .network import _NET_FAILS, _NET_REACHED, _NET_SESSIONS, _apply_network_state, _has_qrcode, _is_local_request, _lan_ips, _lan_ips_detail, _net_cfg, _net_cfg_save, _net_note_fail, _net_note_reached, _net_rate_limited, _net_token_new
from .runtime import _package_of, _runtime_pref, detect_gpu_vendor, pick_runtime, repair_packages, verify_installed_files
from .importing import _clipboard_put, _drag_handover, _drag_watch, _drag_watch_lock, _drag_watch_loop, _paths_for_ids, native_drag_available, start_native_drag


@app.route("/")
def index():
    # v4.25: window_mode is per CLIENT, not per server. The app window carries
    # ?ti_app=1; anything else is a browser, whatever the server was started as.
    client_window = state.WINDOW_MODE and (request.args.get("ti_app") == "1"
                                     or request.cookies.get("ti_app") == "1")
    resp = make_response(render_template(
        "index.html", version=VERSION, window_mode=client_window,
        native_drag=native_drag_available(), is_windows=(os.name == "nt"),
        native_drop=(state.NATIVE_DROP_OK and client_window),
        server_window=state.WINDOW_MODE))
    if client_window:
        # The window navigates within itself after this, losing the query string,
        # so the answer is remembered for this client only.
        resp.set_cookie("ti_app", "1", max_age=86400, samesite="Lax")
    return resp


@app.route("/api/version")
def api_version():
    return jsonify({"version": VERSION})


@app.route("/api/events")
def api_events():
    """SSE endpoint — streams live change events to the frontend."""
    q = Queue(maxsize=50)
    with sse_lock:
        sse_clients.append(q)
    # Send initial watcher status
    status = {"active": state._watcher_running and state._watcher_observer is not None}
    q.put(f"event: watcher_status\ndata: {json.dumps(status)}\n\n")
    def stream():
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield msg
                except Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            with sse_lock:
                if q in sse_clients:
                    sse_clients.remove(q)
    resp = Response(stream(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


@app.route("/api/tab-open", methods=["POST"])
def api_tab_open():
    """Register a browser tab. Cancels any pending shutdown."""
    data = request.get_json(silent=True) or {}
    tab_id = data.get("tab_id", "")
    if tab_id:
        with _tabs_lock:
            _active_tabs.add(tab_id)
        _cancel_shutdown_timer()
    return jsonify({"ok": True})


@app.route("/api/tab-close", methods=["POST"])
def api_tab_close():
    """Unregister a browser tab. Starts shutdown if last tab."""
    data = request.get_json(silent=True) or {}
    tab_id = data.get("tab_id", "")
    if tab_id:
        with _tabs_lock:
            _active_tabs.discard(tab_id)
            remaining = len(_active_tabs)
        if remaining == 0:
            _check_shutdown()
    return jsonify({"ok": True})


@app.route("/api/watcher-status")
def api_watcher_status():
    return jsonify({"active": state._watcher_running and state._watcher_observer is not None, "has_watchdog": HAS_WATCHDOG})


@app.route("/api/processing/status")
def api_processing_status():
    db = get_db()
    return jsonify(_proc_progress_payload(db))


@app.route("/api/processing/start", methods=["POST"])
def api_processing_start():
    _proc["paused"] = False
    _proc_ensure_running(reset_progress=True)
    db = get_db()
    return jsonify(_proc_progress_payload(db))


@app.route("/api/processing/pause", methods=["POST"])
def api_processing_pause():
    _proc["paused"] = True
    _proc_notify(force=True)
    db = get_db()
    return jsonify(_proc_progress_payload(db))


@app.route("/api/processing/resume", methods=["POST"])
def api_processing_resume():
    _proc["paused"] = False
    _proc_ensure_running()          # wake the pool (restart if it had exited)
    _proc_notify(force=True)
    db = get_db()
    return jsonify(_proc_progress_payload(db))


@app.route("/api/processing/reprocess-all", methods=["POST"])
def api_processing_reprocess_all():
    db = get_db()
    db.execute("UPDATE images SET meta_done=0")
    db.commit()
    _proc["paused"] = False
    _proc_ensure_running(reset_progress=True)
    return jsonify(_proc_progress_payload(db))


@app.route("/api/processing/settings", methods=["POST"])
def api_processing_settings():
    data = request.get_json() or {}
    restart = False
    if "workers" in data:
        try:
            # v3.74: 0 = Auto (all logical processors), mirroring Compute processes.
            n = max(0, min(_MAX_WORKERS, int(data["workers"])))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid worker count"}), 400
        eff = n if n else _AUTO_WORKERS     # v4.15: same Auto as every other stage
        if eff != _proc["workers"]:
            _proc["workers"] = eff
            restart = _proc["running"]      # apply new count to a live pool
        _proc["workers_cfg"] = n
        _proc_save_setting("proc_workers", n)
        log(f"Worker threads set to {'Auto' if not n else n} \u2014 {eff} organiser threads")
    if "auto" in data:
        _proc["auto"] = bool(data["auto"])
        _proc_save_setting("proc_auto", "1" if _proc["auto"] else "0")
    if restart:
        _proc_stop()
        _proc_ensure_running(reset_progress=False)
    db = get_db()
    return jsonify(_proc_progress_payload(db))


@app.route("/api/embedded-keywords", methods=["GET", "POST"])
def api_embedded_keywords():
    """Read or set whether keywords in a file are imported as tags."""
    cfg = _app_config_load()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        cfg["import_embedded_keywords"] = bool(data.get("enabled"))
        _app_config_save(cfg)
        log("Keywords already in a file %s imported as tags"
            % ("are now" if cfg["import_embedded_keywords"] else "are no longer"), "info")
    return jsonify({"enabled": bool(cfg.get("import_embedded_keywords", False))})


@app.route("/api/update/check")
def api_update_check():
    """Ask GitHub what the newest release is. Only ever on request."""
    return jsonify(check_for_update())


@app.route("/api/update/install", methods=["POST"])
def api_update_install():
    """Download, verify, back the database up, then restart into the new version.

    The caller hands back the result of the check rather than the server looking
    it up again, so the version being installed is the one the user was shown
    and agreed to.
    """
    info = request.get_json(silent=True) or {}
    if not str(info.get("asset_url") or "").startswith(
            "https://github.com/%s/%s/" % (GITHUB_OWNER, GITHUB_REPO)):
        # The only place an update may come from. Without this the endpoint
        # would fetch and run whatever URL it was handed.
        return jsonify({"error": "That download does not come from the "
                                 "TrackImage repository."}), 400
    if not start_install(info):
        return jsonify({"error": "An update is already being installed."}), 409
    log("Update to %s requested" % (info.get("tag") or "?"))
    return jsonify({"ok": True})


@app.route("/api/update/status")
def api_update_status():
    return jsonify(update_status())


@app.route("/api/update/auto", methods=["GET", "POST"])
def api_update_auto():
    """Whether TrackImage looks for an update once at start."""
    if request.method == "POST":
        on = bool((request.get_json(silent=True) or {}).get("enabled"))
        set_auto_check(on)
        log("Automatic update check %s" % ("enabled" if on else "disabled"), "info")
    return jsonify({"enabled": auto_check_enabled(), "configured": is_configured()})


@app.route("/api/keymap", methods=["GET", "POST"])
def api_keymap():
    """The user's key bindings, kept beside the other settings.

    Only action names shaped like the front end's are stored, and a binding is a
    short chord string. Anything else is dropped rather than trusted.
    """
    cfg = _app_config_load()
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        given = data.get("keymap")
        if given is None:
            cfg.pop("keymap", None)          # reset to defaults
        elif isinstance(given, dict):
            clean = {}
            for k, v in list(given.items())[:40]:
                k, v = str(k)[:32], str(v)[:32]
                if re.match(r"^[a-z_]+$", k) and re.match(r"^[A-Za-z0-9+]+$", v):
                    clean[k] = v
            cfg["keymap"] = clean
        _app_config_save(cfg)
    return jsonify({"keymap": cfg.get("keymap") or {}})


@app.route("/api/db-vacuum", methods=["POST"])
def api_db_vacuum():
    if _vacuum["running"]:
        return jsonify({"error": "A compaction is already running."}), 409
    if _thumb_regen.get("running"):
        return jsonify({"error": "Thumbnails are being regenerated \u2014 the database is "
                                 "compacted automatically when that finishes."}), 409
    threading.Thread(target=_vacuum_run, daemon=True, name="vacuum").start()
    return jsonify({"ok": True, "started": True})


@app.route("/api/thumb-settings", methods=["GET","POST"])
def api_thumb_settings():
    # v3.24/27: read or update thumbnail resolution + WebP quality. A POST saves the
    # settings and kicks off a parallel background job that regenerates every thumbnail.
    db = get_db()
    if request.method == "POST":
        data = request.get_json() or {}
        sz = max(256, min(2048, int(data.get("max_size", 1024))))
        q  = max(40, min(100, int(data.get("quality", 90))))
        db.execute("INSERT OR REPLACE INTO config (key,value) VALUES ('thumb_max_size',?)", (str(sz),))
        db.execute("INSERT OR REPLACE INTO config (key,value) VALUES ('thumb_quality',?)", (str(q),))
        db.commit()
        state._THUMB_CFG = None
        if not _thumb_regen["running"]:
            threading.Thread(target=_thumb_regen_worker, daemon=True, name="thumb-regen").start()
        return jsonify({"ok": True, "max_size": sz, "quality": q, "regenerating": True})
    sz, q = _thumb_cfg()
    row = db.execute("SELECT COUNT(*) c, COALESCE(SUM(LENGTH(data)),0) b FROM thumb_cache").fetchone()
    return jsonify({"max_size": sz, "quality": q, "count": row["c"], "total_bytes": row["b"],
                    "regenerating": _thumb_regen["running"], "regen_done": _thumb_regen["done"], "regen_total": _thumb_regen["total"]})


@app.route("/api/db-info")
def api_db_info():
    # v3.21: expose the images-table schema so Settings can show what is actually
    # stored per image (how many columns a file entry has, and their names).
    db = get_db()
    try:
        cols = [r[1] for r in db.execute("PRAGMA table_info(images)").fetchall()]
    except Exception:
        cols = []
    try:
        rows = db.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    except Exception:
        rows = 0
    return jsonify({"columns": cols, "count": len(cols), "rows": rows,
                    "db_path": app.config["DATABASE"], "db_on_network": DB_ON_NETWORK,
                    "nas_protection": NAS_PROTECTION, "nas_active": NAS_ACTIVE,
                    "db_bytes": _db_file_bytes(), "vacuum": dict(_vacuum),
                    "thumb_regen": bool(_thumb_regen.get("running"))})


@app.route("/api/nas-protection", methods=["POST"])
def api_nas_protection():
    # v3.58: persisted in the local app-config file (read before the DB opens).
    data = request.get_json() or {}
    cfg = _app_config_load()
    cfg["nas_db_protection"] = bool(data.get("enabled", True))
    return jsonify({"ok": _app_config_save(cfg), "needs_restart": True})


@app.route("/api/processing-power", methods=["GET", "POST"])
def api_processing_power():
    """Set every stage at once. 0 = Auto (all logical processors)."""
    if request.method == "GET":
        return jsonify(_power_state())
    data = request.get_json() or {}
    try:
        n = max(0, min(_MAX_WORKERS, int(data.get("n", 0))))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid value"}), 400
    eff = _AUTO_WORKERS if not n else n     # v4.15: Auto is one number for every stage

    # compute pool (restarts itself)
    try: _mp_set_workers(n)
    except Exception: pass
    # organiser threads
    with _proc_lock:
        _proc["workers_cfg"] = n
        _proc["workers"] = eff
    try: _proc_save_setting("proc_workers", n)
    except Exception: pass
    # thumbnail back-fill
    _thumb_workers_cfg["n"] = n
    # auto-tagging
    try:
        db = get_db()
        db.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('thumb_workers', ?)", (str(n),))
        db.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('tag_workers', ?)", (str(n),))
        db.commit()
    except Exception:
        pass
    log(f"Processing power set to {'Auto' if not n else n} \u2014 {eff} across all stages")
    try: _proc_ensure_running()
    except Exception: pass
    _proc_notify(force=True)
    try: _tag_notify(force=True)
    except Exception: pass
    return jsonify(_power_state())


@app.route("/api/thumb-workers", methods=["POST"])
def api_thumb_workers():
    """Set the thumbnail back-fill worker count. 0 = Auto (matches the compute
    process pool). Persisted, so it survives a restart."""
    data = request.get_json() or {}
    try:
        n = max(0, min(_MAX_WORKERS, int(data.get("n", 0))))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid worker count"}), 400
    _thumb_workers_cfg["n"] = n
    try:
        db = get_db()
        db.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('thumb_workers', ?)", (str(n),))
        db.commit()
    except Exception:
        pass
    eff = _thumb_target_workers()
    log(f"Thumbnail workers set to {'Auto' if not n else n} \u2014 {eff} threads")
    return jsonify({"ok": True, "n": n, "effective": eff, "max": _MAX_WORKERS})


@app.route("/api/net/ping")
def api_net_ping():
    """v4.33: the interface asks this every few seconds and locks itself the
    moment it does not get an answer.

    A phone with the gallery on screen kept showing it after the server was
    gone -- thumbnails, filenames, folder names, all still readable from the page
    it had already loaded. Nothing on the device knew the connection had ended.
    Now it does: no reply, or a reply that says locked, and the interface clears
    itself immediately."""
    return jsonify({"ok": True, "remote": not _is_local_request(),
                    "net_on": bool(state._NET_ON), "version": VERSION})


@app.route("/api/net/unlock", methods=["POST"])
def api_net_unlock():
    addr = request.remote_addr or "?"
    if _net_rate_limited(addr):
        return jsonify({"error": "Too many attempts. Wait five minutes and try again."}), 429
    given = str((request.get_json(silent=True) or {}).get("password", ""))
    if given and given == _net_cfg()["password"]:
        _NET_FAILS.pop(addr, None)
        _net_note_reached()
        r = jsonify({"ok": True})
        # No max_age and no expires: a session cookie. The browser drops it when
        # it closes, so the next visit starts at the PIN screen again.
        r.set_cookie("ti_net", _net_token_new(), httponly=True, samesite="Lax")
        log("A device on the network unlocked TrackImage (%s)" % addr)
        return r
    _net_note_fail(addr)
    log("Wrong network password from %s" % addr, "warning")
    return jsonify({"error": "Wrong password"}), 403


@app.route("/api/network/qr")
def api_network_qr():
    """v4.31: the LAN address as a QR code, so a phone can scan it instead of
    someone typing an IP with a port on a touch keyboard.

    qrcode is optional on purpose. It is 110 KB of pure Python and does one small
    job, so it must not be able to stop TrackImage from starting if it is absent
    -- the address is shown as text regardless and the code is a convenience on
    top. (I wrote an encoder by hand first to avoid the dependency at all; it
    produced codes I could not verify against a reference, and an unverifiable
    QR code is worse than none.)"""
    url = request.args.get("url", "").strip()
    if not url:
        ips = _lan_ips()
        if not ips:
            return "no address", 404
        url = "http://%s:%d" % (ips[0], _net_cfg()["port"])
    if not (url.startswith("http://") or url.startswith("https://")):
        return "bad url", 400
    try:
        import qrcode
        import qrcode.image.svg as _svg
        img = qrcode.make(url, image_factory=_svg.SvgPathImage, box_size=10, border=2)
        import io as _io
        buf = _io.BytesIO()
        img.save(buf)
        r = app.response_class(buf.getvalue(), mimetype="image/svg+xml")
        r.headers["Cache-Control"] = "no-cache"
        return r
    except ImportError:
        return "qrcode not installed", 501
    except Exception as e:
        log("QR code failed: %s" % e, "warning")
        return "qr failed", 500


@app.route("/api/network")
def api_network():
    c = _net_cfg()
    ips = _lan_ips()
    best = ips[0] if ips else ""
    return jsonify({"enabled": c["enabled"], "password": c["password"],
                    "port": c["port"], "active": state._NET_ON,
                    "addresses": ips,
                    "best_url": ("http://%s:%d" % (best, c["port"])) if best else "",
                    "urls": ["http://%s:%d" % (ip, c["port"]) for ip in ips],
                    "detail": _lan_ips_detail(),
                    "confirmed": _NET_REACHED.get("host", ""),
                    "sessions": len(_NET_SESSIONS),
                    "qr": _has_qrcode(),
                    "is_default_password": c["password"] == NET_DEFAULT_PW})


@app.route("/api/network", methods=["POST"])
def api_network_save():
    """Settings are writable from this machine only. A device that unlocked with
    the password must not be able to change that password or open the door wider."""
    if not _is_local_request():
        return jsonify({"error": "Network settings can only be changed on the "
                                 "computer running TrackImage."}), 403
    d = request.get_json(silent=True) or {}
    upd, msgs = {}, []
    if "enabled" in d:
        upd["network_enabled"] = bool(d["enabled"])
        msgs.append("sharing " + ("on" if d["enabled"] else "off"))
    if "password" in d:
        pw = str(d["password"] or "").strip()
        if len(pw) < 4:
            return jsonify({"error": "The password needs at least four characters."}), 400
        upd["network_password"] = pw
        _NET_SESSIONS.clear()          # a new password logs every device out
        msgs.append("password changed")
    applied = True
    if upd:
        _net_cfg_save(**upd)
        if "network_enabled" in upd:
            applied = _apply_network_state(upd["network_enabled"])
        log("Network settings updated: %s" % ", ".join(msgs))
    return jsonify({"ok": True, "restart_required": not applied,
                    "active": state._NET_ON, **_net_cfg()})


@app.route("/api/network/logout-all", methods=["POST"])
def api_network_logout():
    if not _is_local_request():
        return jsonify({"error": "Only on the computer running TrackImage."}), 403
    n = len(_NET_SESSIONS)
    _NET_SESSIONS.clear()
    log("Signed out %d network device(s)" % n)
    return jsonify({"ok": True, "signed_out": n})


@app.route("/api/drag/arm", methods=["POST"])
def api_drag_arm():
    """The page has started a drag. Remember the files and start watching."""
    if os.name != "nt" or not native_drag_available():
        return jsonify({"ok": False, "error": "native drag unavailable"})
    data = request.get_json(silent=True) or {}
    ids = [int(i) for i in (data.get("ids") or []) if str(i).isdigit()][:500]
    seq = int(data.get("seq") or 0)
    paths = _paths_for_ids(ids) if ids else []
    if not paths:
        return jsonify({"ok": False, "error": "files not found on disk"})
    with _drag_watch_lock:
        _drag_watch["seq"] = seq
        _drag_watch["paths"] = paths
        _drag_watch["handed"] = False
    threading.Thread(target=_drag_watch_loop, args=(seq,), daemon=True,
                     name="drag-watch").start()
    return jsonify({"ok": True, "count": len(paths)})


@app.route("/api/drag/handover", methods=["POST"])
def api_drag_handover():
    """The page saw the cursor leave the window itself -- no need to wait for the
    watch to notice the same thing a moment later."""
    seq = int((request.get_json(silent=True) or {}).get("seq") or 0)
    ok, msg = _drag_handover(seq)
    return jsonify({"ok": bool(ok), "error": msg})


@app.route("/api/drag/disarm", methods=["POST"])
def api_drag_disarm():
    """The drag ended inside TrackImage (a folder, or nowhere). Stop watching."""
    seq = int((request.get_json(silent=True) or {}).get("seq") or 0)
    with _drag_watch_lock:
        if _drag_watch["seq"] == seq:
            _drag_watch["handed"] = True
            _drag_watch["paths"] = []
    return jsonify({"ok": True})


@app.route("/api/native-drag", methods=["POST"])
def api_native_drag():
    """v4.13: hand the gesture over to Windows. The page recognises the drag --
    WebView2 cannot start one -- and this hands the file list to DoDragDrop. It
    answers immediately; the drag runs on its own thread until the button is let
    go, and waiting for that here would only block the page."""
    data = request.get_json(silent=True) or {}
    ids = [int(i) for i in (data.get("ids") or []) if str(i).isdigit()][:500]
    if not ids:
        return jsonify({"error": "no images given"}), 400
    paths = _paths_for_ids(ids)
    if not paths:
        return jsonify({"error": "files not found on disk"}), 404
    ok, msg = start_native_drag(paths)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 200
    return jsonify({"ok": True, "count": len(paths)})


@app.route("/api/localpath", methods=["POST"])
def api_localpath():
    """v4.13: the disk paths behind a selection. Linux and macOS drag a file by
    passing a file:// address along, and the page needs the real path to build
    one. Windows never asks -- it takes the native route instead."""
    data = request.get_json(silent=True) or {}
    ids = [int(i) for i in (data.get("ids") or []) if str(i).isdigit()][:500]
    if not ids:
        return jsonify({"error": "no images given"}), 400
    return jsonify({"ok": True, "paths": _paths_for_ids(ids)})


@app.route("/api/clipboard", methods=["POST"])
def api_clipboard():
    data = request.get_json(silent=True) or {}
    mode = "image" if data.get("mode") == "image" else "file"
    ids = [int(i) for i in (data.get("ids") or []) if str(i).isdigit()][:500]
    if not ids:
        return jsonify({"error": "no images given"}), 400
    db = get_db()
    ph = ",".join("?" * len(ids))
    rows = db.execute(f"SELECT id, filepath FROM images WHERE id IN ({ph})", ids).fetchall()
    order = {int(v): k for k, v in enumerate(ids)}
    paths = [r["filepath"] for r in sorted(rows, key=lambda r: order.get(r["id"], 0))
             if r["filepath"] and os.path.isfile(r["filepath"])]
    if not paths:
        return jsonify({"error": "files not found on disk"}), 404
    ok, msg = _clipboard_put(paths, mode)
    if not ok:
        # v4.11: never fail silently again -- the console panel shows the reason.
        log(f"Clipboard ({mode}) failed: {msg or 'unknown'}", "warning")
        return jsonify({"error": msg or "clipboard unavailable"}), 500
    log(f"Clipboard: {len(paths) if mode == 'file' else 1} {mode}(s) copied")
    return jsonify({"ok": True, "count": (1 if mode == "image" else len(paths)), "mode": mode})


@app.route("/api/ui-mode", methods=["POST"])
def api_ui_mode():
    """v4.25: move TrackImage between its own window and a browser tab.

    One direction is free: the server is already running, so going to a tab only
    means opening one and letting the window go. The other needs a restart --
    pywebview has to create its window from the main thread, and this process is
    long past that point. The preference is stored either way, so the next start
    obeys it regardless."""
    want = str((request.get_json(silent=True) or {}).get("mode") or "")
    if want not in ("window", "browser"):
        return jsonify({"error": "mode must be window or browser"}), 400
    db = get_db()
    db.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('ui_mode', ?)", (want,))
    db.commit()
    log(f"Interface set to {want} mode")
    if want == "browser" and state.WINDOW_MODE:
        try:
            import webbrowser as _wb
            _wb.open("http://localhost:5001")
        except Exception:
            pass
        def _close_window():
            _time.sleep(1.2)      # let the browser come up first
            try:
                state._UI_HANDOVER = True
                if state._UI_WINDOW is not None:
                    state._UI_WINDOW.destroy()
            except Exception:
                pass
        threading.Thread(target=_close_window, daemon=True).start()
        return jsonify({"ok": True, "mode": want, "restart": False,
                        "note": "Opening a browser tab \u2014 the window closes in a moment."})
    if want == "window" and not state.WINDOW_MODE:
        if not HAS_WEBVIEW:
            return jsonify({"error": "pywebview is not installed \u2014 the app window "
                                     "is unavailable on this machine"}), 400
        threading.Thread(target=_restart_self, daemon=True).start()
        return jsonify({"ok": True, "mode": want, "restart": True,
                        "note": "Restarting in its own window \u2014 this tab can be closed."})
    return jsonify({"ok": True, "mode": want, "restart": False,
                    "note": "Already in that mode."})


@app.route("/api/venv/check")
def api_venv_check():
    """What the installation looks like right now. deep=1 also hashes every file,
    which reads gigabytes and is only worth doing on request."""
    deep = request.args.get("deep") == "1"
    miss, bad, n = verify_installed_files(deep=deep)
    pkgs = sorted({_package_of(f) for f, *_ in bad} | {_package_of(f) for f in miss})
    kind, pkg, why = pick_runtime()
    return jsonify({
        "ok": not miss and not bad, "checked": n, "deep": deep,
        "missing": [os.path.basename(f) for f in miss[:20]],
        "damaged": [{"file": os.path.basename(f), "expected": str(w), "found": str(g)}
                    for f, w, g in bad[:20]],
        "packages": [p for p in pkgs if p],
        "gpu": detect_gpu_vendor(), "runtime": kind, "runtime_reason": why,
        "runtime_pref": _runtime_pref(),
        "device": (_tag_state.get("device") or ""),
    })


@app.route("/api/venv/repair", methods=["POST"])
def api_venv_repair():
    """Reinstall whatever the check found wanting."""
    data = request.get_json(silent=True) or {}
    names = [str(x) for x in (data.get("packages") or []) if x][:20]
    if not names:
        miss, bad, _ = verify_installed_files()
        names = sorted({_package_of(f) for f, *_ in bad} | {_package_of(f) for f in miss})
        names = [n for n in names if n][:20]
    if not names and data.get("force"):
        # v4.21: the button is always on screen now, so asking to repair a healthy
        # install has to mean something. It reinstalls the runtime the card would
        # use -- the usual answer when tagging misbehaves for no visible reason.
        kind, pkg, _why = pick_runtime()
        names = [pkg]
    if not names:
        return jsonify({"ok": True, "results": [], "note": "nothing needed repairing"})
    log(f"Repairing installation: {', '.join(names)}")
    res = repair_packages(names)
    for n, good, msg in res:
        # v4.36: the em dash used to sit inside the f-string expression as an
        # escape. Python 3.12 allows a backslash in there; 3.10 and 3.11 do not,
        # and refuse the whole file with a SyntaxError before anything runs --
        # so on those versions TrackImage did not start at all, and the message
        # pointed at a corrupt install rather than at this one character.
        _what = "reinstalled" if good else "could not be reinstalled \u2014 " + msg
        log(f"{n}: {_what}", "info" if good else "error")
    return jsonify({"ok": all(g for _n, g, _m in res),
                    "results": [{"package": n, "ok": g, "detail": m} for n, g, m in res],
                    "note": "Restart TrackImage so the repaired files are loaded."})


@app.route("/api/venv/runtime", methods=["POST"])
def api_venv_runtime():
    """Choose which ONNX runtime to use. Applies on the next install/restart."""
    v = str((request.get_json(silent=True) or {}).get("pref") or "auto")
    if v not in ("auto", "cuda", "dml", "cpu"):
        return jsonify({"error": "unknown runtime"}), 400
    if v == "dml" and os.name != "nt":
        return jsonify({"error": "DirectML exists only on Windows"}), 400
    db = get_db()
    db.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('onnx_runtime', ?)", (v,))
    db.commit()
    kind, pkg, why = pick_runtime()
    log(f"ONNX runtime preference set to {v} \u2014 will install {pkg}")
    return jsonify({"ok": True, "pref": v, "runtime": kind, "reason": why})


@app.route("/api/console")
def api_console():
    """v4.03: tail of the console for the Settings panel. `since` is the last
    sequence number the client already has, so each poll only ships new lines."""
    try:
        since = int(request.args.get("since", 0))
    except ValueError:
        since = 0
    with _console_lock:
        lines = [{"n": n, "t": t} for n, t in _console_lines if n > since]
        last = state._console_seq
    if since == 0:
        lines = lines[-1200:]      # v4.14: a first look reaches further back
    return jsonify({"lines": lines, "seq": last, "path": _LOG_PATH})


@app.route("/api/hash-status")
def api_hash_status():
    db = get_db()
    # v3.81: only count files that can actually produce a pHash. Videos are
    # excluded by media_type, and files already proven undecodable (hash_fail)
    # drop out too -- otherwise total-hashed never reaches 0 and the UI keeps
    # showing the blocking "Hashing images..." screen forever.
    total = db.execute("SELECT COUNT(*) FROM images WHERE COALESCE(media_type,'image') != 'video' "
                       "AND COALESCE(hash_fail,0)=0").fetchone()[0]
    hashed = db.execute("SELECT COUNT(*) FROM images WHERE phash IS NOT NULL AND phash != ''").fetchone()[0]
    needs_pairs = 0   # v3.66: no background pairing phase anymore
    return jsonify({"total": total, "hashed": hashed, "available": HAS_PHASH,
                    "hashing": _hash_progress.get("active", False) or _dup_progress.get("active", False),
                    "phase": "hashing" if _hash_progress.get("active") else ("comparing" if _dup_progress.get("active") else "idle"),
                    "hash_current": _hash_progress.get("current", 0) if _hash_progress.get("active") else _dup_progress.get("current", 0),
                    "hash_total": _hash_progress.get("total", 0) if _hash_progress.get("active") else _dup_progress.get("total", 0),
                    "needs_pairs": needs_pairs})


@app.route("/api/compute-hashes", methods=["POST"])
def api_compute_hashes():
    if not HAS_PHASH:
        return jsonify({"error": "numpy not installed"}), 400
    if _hash_progress["active"]:
        return jsonify({"ok": True, "status": "already running"})
    def do_hash():
        _hash_progress["active"] = True
        try:
            db = _get_thread_db()
            # The background pool computes pHash for every meta_done=0 image, so the
            # dup scan only GAP-FILLS images the pool will not touch (already meta_done=1
            # but still missing a hash). This avoids two writers racing the same rows.
            # v3.73: cheap file_size back-fill first (stat only, no decode) --
            # covers videos too, which never get a pHash.
            try:
                _fsrows = db.execute("SELECT id,filepath FROM images WHERE file_size IS NULL OR file_size=0").fetchall()
                if _fsrows:
                    for _fr in _fsrows:
                        try: _sz = os.path.getsize(_fr["filepath"])
                        except Exception: continue
                        with _db_write_lock:
                            db.execute("UPDATE images SET file_size=? WHERE id=?", (_sz, _fr["id"]))
                    with _db_write_lock:
                        _db_commit_retry(db)
            except Exception:
                pass
            # v3.73: rows with a pHash but no region signature are re-decoded once
            # so the region score becomes available for the existing library.
            # v3.80: videos are excluded by media_type (the old hard-coded list of
            # five extensions let .m4v/.wmv/.ts/.mpg/... through forever), and files
            # already known to be undecodable are skipped via the sticky hash_fail flag.
            rows = db.execute("SELECT id,filepath FROM images WHERE (phash IS NULL OR phash='' OR tile_sig IS NULL) "
                              "AND meta_done=1 AND COALESCE(hash_fail,0)=0 "
                              "AND COALESCE(media_type,'image') != 'video'").fetchall()
            rows = [r for r in rows if r["id"] not in _hash_gaveup]   # v3.70: skip known-unhashable
            _hash_progress["total"] = len(rows)
            _hash_progress["current"] = 0
            _new = 0
            for i, r in enumerate(rows):
                _hash_progress["current"] = i + 1
                try:
                    pay = _dispatch_compute(r["filepath"], want_thumb=False)   # v3.70: process pool
                    ph = pay["ph"] if pay else ""
                    _ts = pay.get("ts") if pay else None                       # v3.73
                    _fs = int(pay.get("fs") or 0) if pay else 0
                    if ph:
                        # Commit inside the lock so no open write transaction lingers
                        # outside it (which would block the pool at the SQLite level).
                        with _db_write_lock:
                            db.execute("UPDATE images SET phash=?, tile_sig=?, file_size=? WHERE id=?",
                                       (ph, sqlite3.Binary(_ts or b""), _fs, r["id"]))
                            _db_commit_retry(db)
                        _new += 1
                    else:
                        _mark_hash_fail(db, r["id"])
                except Exception:
                    _mark_hash_fail(db, r["id"])
            _hash_progress["active"] = False
            if _new:
                _mem_invalidate()   # v3.70: only when hashes actually changed
            db.close()
        except Exception as e:
            print(f"  ⚠ Hashing error: {e}")
        _hash_progress["active"] = False
        _dup_progress["active"] = False
    threading.Thread(target=do_hash, daemon=True).start()
    return jsonify({"ok": True, "status": "started"})


@app.route("/api/mp-workers", methods=["GET", "POST"])
def api_mp_workers():
    """v3.72: size of the compute process pool. 0 = Auto (half the logical
    processors). A change restarts the pool on the next dispatch."""
    if request.method == "POST":
        n = int((request.get_json() or {}).get("n", 0))
        _mp_set_workers(n, log_it=True)
    return jsonify({"n": _mp_configured(), "procs": _mp_target_procs(), "max": _MAX_WORKERS,
                    "auto": _mp_configured() <= 0, "up": state._MP_POOL is not None})
