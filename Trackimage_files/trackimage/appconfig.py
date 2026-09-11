"""The settings file that sits beside the database, and NAS protection.

Layer 5 of 27 -- see trackimage/__init__.py for the order these load in.
"""
import json
import os
from .config import DB_ON_NETWORK, _ORIG_DB_PATH, app


def _app_config_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "TrackImage")
    try: os.makedirs(d, exist_ok=True)
    except Exception: pass
    return d


def _app_config_load():
    try:
        with open(os.path.join(_app_config_dir(), "config.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _app_config_save(cfg):
    try:
        with open(os.path.join(_app_config_dir(), "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception:
        return False


NAS_PROTECTION = bool(_app_config_load().get("nas_db_protection", True))


NAS_ACTIVE = False


if DB_ON_NETWORK and NAS_PROTECTION:
    import hashlib as _hl, shutil as _sh
    _key = _hl.sha1(os.path.abspath(_ORIG_DB_PATH).lower().encode("utf-8")).hexdigest()[:12]
    _local_dir = os.path.join(_app_config_dir(), "db", _key)
    os.makedirs(_local_dir, exist_ok=True)
    _local_db = os.path.join(_local_dir, "trackimage.db")
    if not os.path.exists(_local_db) and os.path.exists(_ORIG_DB_PATH):
        for _suf in ("", "-wal", "-shm"):
            _src = _ORIG_DB_PATH + _suf
            if os.path.exists(_src):
                _sh.copy2(_src, _local_db + _suf)   # copy, never move
        print(f"  \U0001f6e1 NAS protection: database copied once to local storage")
    app.config["DATABASE"] = _local_db
    NAS_ACTIVE = True


def _nas_backup_now():
    """v3.59: consistent snapshot of the local DB back to the NAS. Never touches
    the original trackimage.db — writes trackimage.db.backup atomically."""
    if not NAS_ACTIVE:
        return False
    try:
        import sqlite3 as _sq, shutil as _sh
        os.makedirs(os.path.join(_app_config_dir(), "db"), exist_ok=True)
        tmp_local = os.path.join(_app_config_dir(), "db", "_backup_tmp.db")
        try: os.remove(tmp_local)
        except Exception: pass
        _src = _sq.connect(app.config["DATABASE"])
        _dst = _sq.connect(tmp_local)
        with _dst:
            _src.backup(_dst)
        _dst.close(); _src.close()
        nas_tmp = _ORIG_DB_PATH + ".backup.tmp"
        _sh.copy2(tmp_local, nas_tmp)
        os.replace(nas_tmp, _ORIG_DB_PATH + ".backup")
        try: os.remove(tmp_local)
        except Exception: pass
        print("  \U0001f6e1 NAS backup written: " + _ORIG_DB_PATH + ".backup")
        return True
    except Exception as _e:
        print("  \u26a0 NAS backup failed: " + str(_e))
        return False


if NAS_ACTIVE:
    import atexit as _ax, threading as _bth
    _ax.register(_nas_backup_now)
    def _nas_backup_loop():
        import time as _bt
        while True:
            _bt.sleep(24 * 3600)
            _nas_backup_now()
    _bth.Thread(target=_nas_backup_loop, daemon=True).start()
    print(f"  \U0001f6e1 NAS protection active \u2014 DB runs locally ({_local_db}); the collection stays on the network drive")


os.makedirs(app.instance_path, exist_ok=True)
