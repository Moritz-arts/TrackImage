"""The WD-EVA02 model, its ONNX runtime, and the tagging workers.

Layer 13 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from io import BytesIO
import os
import threading
import time as _time
from . import state
from .config import Image, TAGGER_DIR, _AUTO_WORKERS, _CLAIM_PAGE, _MAX_WORKERS, _RT_ABSENT, _RT_BROKEN, _RT_OK, _RT_SWAPPING, _RT_UNKNOWN, _TAG_CATEGORY, _TAG_DEFAULTS, np
from .logging_setup import log, log_detail
from .platform_bits import _boost_thread_qos
from .appconfig import _app_config_load
from .db import _db_commit_retry, _db_write_lock, _get_thread_db, _norm_tag
from .events import sse_notify
from .metadata import _split_keywords
from .thumbnails import generate_video_thumbnail


def _embedded_tags_on():
    """Whether keywords already written into a file become tags here.

    Off unless asked for. Pictures out of Lightroom or Bridge often carry
    keywords someone spent time on, and reading them is the point; but they
    would land beside tags the model produced, and a library that silently
    gained a few thousand tags on a rescan is not what anyone asked for.
    """
    return bool(_app_config_load().get("import_embedded_keywords", False))


def _apply_embedded_keywords(db, image_id, metadata):
    """Store keywords found in a file as tags, marked as coming from the file.

    They are written with source='embedded', which is what tells them apart from
    what the tagger produced -- and what makes them removable again without
    touching anything else.
    """
    if not metadata:
        return 0
    # v4.56: one splitter for the whole app, so a sidecar written with
    # semicolons and a file written with commas end up as the same tags.
    words = _split_keywords(metadata.get("keywords"))
    if not words:
        return 0
    added = 0
    for word in words[:200]:
        name = _norm_tag(word)
        if not name:
            continue
        try:
            db.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
            row = db.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
            if not row:
                continue
            cur = db.execute(
                "INSERT OR IGNORE INTO image_tags (image_id, tag_id, score, source) "
                "VALUES (?,?,?,'embedded')", (image_id, row["id"], 1.0))
            added += cur.rowcount or 0
        except Exception:
            continue
    return added


state._tagger = None                       # shared WDTagger instance (lazy, thread-safe load)


_tagger_load_lock = threading.Lock()


state._tagger_failed = False               # runtime/model load failed -> stop retrying this run


_tag_state = {"running": False, "done": 0, "total": 0, "active": 0, "threads": 0,
              "floor": 0,   # v4.43: how far the tagging backlog has been walked
              "device": "", "error": "", "cancel": False}


_tag_lock = threading.Lock()


_tag_claimed = set()


_tag_claimed_lock = threading.Lock()


_tag_fail = {}


_tag_fail_lock = threading.Lock()


_tag_sse = {"ts": 0.0}


def _tag_get_cfg():
    """Read enabled flag + thresholds from config (falling back to defaults)."""
    cfg = dict(_TAG_DEFAULTS)
    try:
        db = _get_thread_db()
        for k, key in (("enabled", "tag_enabled"), ("gen", "tag_gen_threshold"), ("char", "tag_char_threshold")):
            row = db.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
            if row and row["value"] is not None:
                cfg[k] = (row["value"] == "1") if k == "enabled" else float(row["value"])
        wrow = db.execute("SELECT value FROM config WHERE key='tag_workers'").fetchone()
        if wrow and wrow["value"] is not None:
            try: cfg["workers"] = max(0, min(_MAX_WORKERS, int(float(wrow["value"]))))
            except (TypeError, ValueError): pass
        db.close()
    except Exception:
        pass
    return cfg


def _tag_save_cfg(key, value):
    try:
        db = _get_thread_db()
        db.execute("INSERT OR REPLACE INTO config (key,value) VALUES (?,?)", (key, str(value)))
        db.commit(); db.close()
    except Exception:
        pass


def _tag_model_available():
    return (os.path.exists(os.path.join(TAGGER_DIR, "model.onnx"))
            and os.path.exists(os.path.join(TAGGER_DIR, "selected_tags.csv")))


state._CUDA_DIRS_DONE = False


state._CUDA_DLL_DIRS = []


state._CUDA_FOREIGN_DIRS = []          # cuDNN found OUTSIDE the venv (reported, never used)


def _nvidia_dirs_under(root):
    out = []
    nv = os.path.join(root, "nvidia")
    if not os.path.isdir(nv):
        return out
    try:
        for pkg in sorted(os.listdir(nv)):
            for sub in ("bin", "lib"):
                d = os.path.join(nv, pkg, sub)
                if os.path.isdir(d):
                    out.append(d)
    except Exception:
        pass
    return out


def _register_cuda_dll_dirs():
    """Put the venv's nvidia wheel binaries on the DLL search path -- and ONLY
    those.

    v3.76: v3.75 also collected site.getusersitepackages(). On a machine with an
    older `pip install --user nvidia-cudnn-cu12`, that dragged a second cuDNN
    into the search path; Windows then mixed the two and cudnn_graph64_9.dll
    looked for an entry point that the older cudnn_engines_precompiled64_9.dll
    does not export ("Prozedureinsprungpunkt nicht gefunden"). Loading failed and
    tagging silently dropped to the CPU. The venv is self-contained on purpose,
    so nothing outside it is ever added."""
    # imported here, not at the top: tagger loads before runtime, and a
    # module cannot import from one that has not been built yet.
    from .runtime import _venv_site_packages
    if state._CUDA_DIRS_DONE:
        return state._CUDA_DLL_DIRS
    state._CUDA_DIRS_DONE = True
    found, foreign = [], []
    try:
        venv_sp = _venv_site_packages()
        if venv_sp:
            found = _nvidia_dirs_under(venv_sp)
        else:
            # No venv (someone runs app.py against a system Python): fall back to
            # this interpreter's own site-packages, still never the user site.
            import sysconfig
            pl = sysconfig.get_paths().get("purelib")
            if pl:
                found = _nvidia_dirs_under(pl)
        # Record foreign copies so the log can name them instead of silently
        # mixing versions -- this is what actually broke GPU tagging in v3.75.
        try:
            import site as _site
            others = []
            try: others.append(_site.getusersitepackages())
            except Exception: pass
            try: others.extend(_site.getsitepackages())
            except Exception: pass
            for o in others:
                if not o or (venv_sp and os.path.normcase(o) == os.path.normcase(venv_sp)):
                    continue
                for d in _nvidia_dirs_under(o):
                    if "cudnn" in d.lower() and d not in found:
                        foreign.append(d)
        except Exception:
            pass
    except Exception:
        return state._CUDA_DLL_DIRS
    for d in found:
        try:
            if hasattr(os, "add_dll_directory"):      # Windows, py3.8+
                os.add_dll_directory(d)
        except Exception:
            pass
    if found:
        sep = os.pathsep
        os.environ["PATH"] = sep.join(found) + sep + os.environ.get("PATH", "")
        if os.name != "nt":
            os.environ["LD_LIBRARY_PATH"] = sep.join(found) + sep + os.environ.get("LD_LIBRARY_PATH", "")
    state._CUDA_DLL_DIRS = found
    state._CUDA_FOREIGN_DIRS = foreign
    return found


def _cudnn_loadable():
    """Can the cuDNN stack actually be loaded? Returns (ok, reason).

    v3.76: only the two entry libraries are loaded; the sub-libraries are checked
    for presence. v3.75 loaded every cudnn*.dll it could find, which is exactly
    what surfaced the version clash as a modal Windows error box. Windows error
    dialogs are suppressed for the duration -- a background check must never pop
    a message box in the user's face."""
    if os.name != "nt":
        return True, ""      # dynamic loader handles LD_LIBRARY_PATH itself
    import ctypes
    files = {}
    for d in state._CUDA_DLL_DIRS:
        try:
            for f in os.listdir(d):
                if f.lower().endswith(".dll"):
                    files.setdefault(f.lower(), os.path.join(d, f))
        except Exception:
            pass
    if not files:
        return False, "no CUDA/cuDNN libraries in the venv"
    entry = [v for k, v in files.items() if k.startswith("cudnn64_")]
    graph = [v for k, v in files.items() if k.startswith("cudnn_graph64_")]
    if not entry:
        return False, "cudnn64_*.dll missing from the venv"
    # Sub-libraries cuDNN 9 loads at runtime: presence is enough, loading them
    # standalone is what tripped over the mismatched copy.
    missing = [n for n in ("cudnn_engines_precompiled64_", "cudnn_engines_runtime_compiled64_",
                           "cudnn_heuristic64_", "cudnn_ops64_")
               if not any(k.startswith(n) for k in files)]
    if missing:
        return False, "incomplete cuDNN install (missing " + missing[0] + "*.dll)"
    k32 = ctypes.windll.kernel32
    try:
        old_mode = k32.SetErrorMode(0x0001 | 0x8000)   # FAILCRITICALERRORS | NOGPFAULTERRORBOX
        k32.SetErrorMode(old_mode | 0x0001 | 0x8000)
    except Exception:
        old_mode = None
    try:
        for full in (entry + graph):
            try:
                ctypes.WinDLL(full)
            except OSError as e:
                return False, f"{os.path.basename(full)} failed to load ({getattr(e, 'winerror', '')})"
        return True, ""
    finally:
        if old_mode is not None:
            try: k32.SetErrorMode(old_mode)
            except Exception: pass


class TagResult:
    """One predicted tag. Kept tiny — a few thousand of these per image."""
    __slots__ = ("name", "category", "score")
    def __init__(self, name, category, score):
        self.name = name; self.category = category; self.score = float(score)
    def __repr__(self):
        return f"<{self.category}:{self.name} {self.score:.3f}>"


class TagPrediction:
    """Grouped predictions for one image. `.all` is what the writer consumes."""
    __slots__ = ("all", "general", "character", "rating")
    def __init__(self, all_tags):
        self.all = all_tags
        self.general = [t for t in all_tags if t.category == "general"]
        self.character = [t for t in all_tags if t.category == "character"]
        self.rating = [t for t in all_tags if t.category == "rating"]


class WDTagger:
    """ONNX wrapper around SmilingWolf/wd-eva02-large-tagger-v3.

    Preprocessing follows the model card exactly, and every step matters:
      * flatten alpha onto WHITE — the model was trained on opaque images, and
        a transparent PNG left as-is turns black and predicts nonsense
      * pad to a square with white, do NOT stretch — the aspect ratio carries
        compositional meaning the model relies on
      * resize to the size the graph declares (448 for this model)
      * RGB -> BGR, float32 in 0..255 (no /255 normalisation)

    Thresholds are applied per call, so moving the sliders in Settings never
    requires reloading the ~1.2 GB session."""

    def __init__(self, model_dir):
        self.model_dir = model_dir
        self.session = None
        self.device = ""
        self.size = 448
        self.input_name = None
        self.tags = []          # [(name, category_str)] in model output order

    # -- tag vocabulary ----------------------------------------------------
    def _load_tags(self):
        import csv
        path = os.path.join(self.model_dir, "selected_tags.csv")
        out = []
        with open(path, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                try:
                    cat = int(row.get("category", 0))
                except Exception:
                    cat = 0
                out.append((row.get("name", ""), _TAG_CATEGORY.get(cat, "general")))
        if not out:
            raise ValueError("selected_tags.csv contained no tags")
        self.tags = out

    # -- session -----------------------------------------------------------
    def load(self):
        _register_cuda_dll_dirs()          # v3.75: before onnxruntime touches CUDA
        import onnxruntime as ort
        self._load_tags()
        avail = list(ort.get_available_providers())
        # v3.75: only offer CUDA when its runtime libraries genuinely load. Without
        # this check onnxruntime happily builds a CUDA session, then falls back to
        # CPU on the first Conv while still reporting CUDAExecutionProvider --
        # tagging crawls at ~1 image/s and the UI claims GPU.
        self.cuda_note = ""
        if "CUDAExecutionProvider" in avail:
            ok, why = _cudnn_loadable()
            if not ok:
                avail = [p for p in avail if p != "CUDAExecutionProvider"]
                self.cuda_note = why or "cuDNN libraries could not be loaded"
                if state._CUDA_FOREIGN_DIRS:
                    self.cuda_note += (" \u2014 another cuDNN also exists outside the venv at "
                                       + state._CUDA_FOREIGN_DIRS[0])
        # Try the fastest provider first and fall back quietly. A GPU wheel on a
        # machine without a usable driver raises here, and that must not be fatal.
        order = [p for p in ("CUDAExecutionProvider", "DmlExecutionProvider",
                             "ROCMExecutionProvider", "CPUExecutionProvider") if p in avail]
        if "CPUExecutionProvider" not in order:
            order.append("CPUExecutionProvider")
        so = ort.SessionOptions()
        so.log_severity_level = 3
        # One intra-op thread per session: several tagger threads share this model
        # and would otherwise each spawn a full-width BLAS pool and fight for cores.
        so.intra_op_num_threads = 1
        so.inter_op_num_threads = 1
        # v4.29: DirectML does not accept the defaults. The memory-pattern
        # optimiser assumes static shapes it cannot honour, and parallel
        # execution is unsupported -- ONNX Runtime documents both, and leaving
        # them on makes session creation fail or behave erratically. Applied
        # whenever the DML provider is in play, since the loop below may fall
        # back to it after CUDA declines.
        if "DmlExecutionProvider" in order:
            so.enable_mem_pattern = False
            so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        model_path = os.path.join(self.model_dir, "model.onnx")
        last = None
        for i in range(len(order)):
            attempt = order[i:]
            try:
                self.session = ort.InferenceSession(model_path, sess_options=so, providers=attempt)
                break
            except Exception as e:
                last = e; self.session = None
        if self.session is None:
            # v4.15: a model file that will not parse is a damaged download, not a
            # configuration problem, and no amount of retrying the same bytes will
            # fix it. Remove it so the next start fetches it again -- otherwise
            # auto-tagging stays dead until someone deletes the file by hand, with
            # only "Protobuf parsing failed" to explain why.
            if any(k in str(last).upper() for k in ("INVALID_PROTOBUF", "PROTOBUF PARSING",
                                                    "FAILED TO LOAD MODEL", "CORRUPT")):
                try:
                    os.remove(model_path)
                    log("The auto-tagging model file was damaged and has been deleted. "
                        "It will be downloaded again \u2014 restart TrackImage or press "
                        "\"Install auto-tagging\" once more.", "warning")
                except OSError:
                    log(f"The auto-tagging model file is damaged: {model_path}. "
                        f"Delete it and start again.", "error")
            raise RuntimeError(f"could not create ONNX session: {last}")
        used = self.session.get_providers()
        # v4.29: DirectML is not safe to call concurrently. Auto-tagging runs one
        # worker per core -- twenty of them on this machine -- all calling run()
        # on this single session, which CUDA tolerates and DML does not. A lock
        # only when DML is actually in use: serialising CUDA would throw away
        # most of its throughput for no reason.
        self._serialise = "DmlExecutionProvider" in used
        self._infer_lock = threading.Lock()
        self.device = ("CUDA" if "CUDAExecutionProvider" in used else
                       "DirectML" if "DmlExecutionProvider" in used else
                       "ROCm" if "ROCMExecutionProvider" in used else "CPU")
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        # v3.77: take the input size from the graph rather than assuming it.
        # EVA02-Large is a vision transformer with 14x14 patches, so its input is
        # 448x448 -- exactly a 32x32 patch grid. That number belongs to the model,
        # not to us: a different checkpoint with different geometry just works.
        # Shape is typically [batch, H, W, 3] with a symbolic batch dimension.
        try:
            dims = [d for d in inp.shape if isinstance(d, int) and d > 3]
            if dims:
                self.size = int(dims[0])
        except Exception:
            pass
        n_out = 0
        try:
            n_out = int(self.session.get_outputs()[0].shape[-1])
        except Exception:
            pass
        if n_out and n_out != len(self.tags):
            raise ValueError(f"model outputs {n_out} tags but selected_tags.csv has {len(self.tags)}")
        return self

    # -- preprocessing -----------------------------------------------------
    def _prepare(self, image):
        im = image
        if im.mode != "RGB":
            # composite onto white so transparency never reads as black
            rgba = im.convert("RGBA")
            canvas = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            canvas.alpha_composite(rgba)
            im = canvas.convert("RGB")
        w, h = im.size
        m = max(w, h)
        if w != h:
            sq = Image.new("RGB", (m, m), (255, 255, 255))
            sq.paste(im, ((m - w) // 2, (m - h) // 2))
            im = sq
        if im.size != (self.size, self.size):
            im = im.resize((self.size, self.size), Image.BICUBIC)
        arr = np.asarray(im, dtype=np.float32)      # HWC, 0..255
        arr = arr[:, :, ::-1]                        # RGB -> BGR
        return np.ascontiguousarray(arr[np.newaxis, ...])

    # -- inference ---------------------------------------------------------
    def tag_image(self, image, gen_threshold=0.35, char_threshold=0.85):
        if self.session is None:
            raise RuntimeError("tagger not loaded")
        x = self._prepare(image)
        try:
            if getattr(self, "_serialise", False):
                with self._infer_lock:
                    preds = self.session.run(None, {self.input_name: x})[0][0]
            else:
                preds = self.session.run(None, {self.input_name: x})[0][0]
        except Exception as e:
            # v3.75: onnxruntime can degrade to CPU mid-flight (driver hiccup,
            # missing sub-library). Correct the reported device instead of
            # leaving a stale "CUDA" on screen while it crawls on the processor.
            if self.device != "CPU":
                self.device = "CPU"
                self.cuda_note = f"GPU execution failed at runtime ({str(e)[:80]}) \u2014 running on CPU"
            raise
        p = np.asarray(preds, dtype=np.float32)
        # v3 models already emit probabilities; if a variant emits logits, squash.
        if p.size and (p.min() < 0.0 or p.max() > 1.0):
            p = 1.0 / (1.0 + np.exp(-np.clip(p, -30.0, 30.0)))
        out = []
        ratings = {}
        n = min(len(self.tags), p.shape[0])
        for i in range(n):
            name, cat = self.tags[i]
            sc = float(p[i])
            # The four rating outputs are a mutually exclusive set -- the model
            # says how likely EACH level is, and exactly one of them applies.
            # Collected here and resolved to a single winner after the loop.
            if cat == "rating":
                ratings[name] = sc
                continue
            thr = char_threshold if cat == "character" else gen_threshold
            if sc >= thr:
                out.append(TagResult(name, cat, sc))
        if ratings:
            best = max(ratings, key=ratings.get)
            score = ratings[best]
            # TrackImage exposes three levels, not four. "questionable" sits
            # between sensitive and explicit and is the ambiguous one, so it is
            # resolved to whichever neighbour the model scored higher. The score
            # kept is the winning one -- it is the model's confidence that the
            # image belongs at that level; the resolved name only says which way
            # it leans.
            if best == "questionable":
                best = ("explicit" if ratings.get("explicit", 0.0) >= ratings.get("sensitive", 0.0)
                        else "sensitive")
            out.append(TagResult(best, "rating", score))
        out.sort(key=lambda t: -t.score)
        return TagPrediction(out)


state._tag_runtime_state = _RT_UNKNOWN


def _tag_runtime_set(state_, why=""):
    state._tag_runtime_state = state_
    state._TAG_RUNTIME_BROKEN = why if state_ == _RT_BROKEN else ""


def _tag_runtime_available():
    """True only when a child process has actually built a session with it."""
    return state._tag_runtime_state == _RT_OK


def _tag_runtime_note():
    """What to tell the user about the current verdict."""
    return {
        _RT_UNKNOWN: "checking the auto-tagging runtime\u2026",
        _RT_OK: "",
        _RT_ABSENT: "",
        _RT_SWAPPING: "the runtime is being replaced \u2014 tagging resumes after a restart",
        _RT_BROKEN: state._TAG_RUNTIME_BROKEN or "the runtime will not load",
    }.get(state._tag_runtime_state, "")


def _get_tagger():
    """Lazily construct + load the shared WDTagger. Returns None on any failure
    (missing runtime/model). Thresholds are applied per call, so a settings change
    never requires a reload."""
    if state._tagger is not None:
        return state._tagger
    if state._tagger_failed:
        return None
    with _tagger_load_lock:
        if state._tagger is not None:
            return state._tagger
        if state._tagger_failed:
            return None
        if not _tag_model_available():
            _tag_state["error"] = "model files not found"; state._tagger_failed = True
            return None
        # v4.26: this is the only place allowed to pull onnxruntime into the
        # server, and only once probe_runtime() has built a session with it in a
        # child process. preload_dlls() maps native CUDA/cuDNN libraries, so
        # reaching it with a half-replaced installation does not raise -- it ends
        # the process.
        if not _tag_runtime_available():
            _tag_state["error"] = _tag_runtime_note() or "runtime not available"
            state._tagger_failed = True
            return None
        try:
            # Load CUDA/cuDNN DLLs from the venv's nvidia-*-cu12 wheels (no system
            # CUDA needed). preload_dlls exists since onnxruntime 1.21; harmless on CPU.
            try:
                import onnxruntime as _ort
                # v4.28: only when CUDA is actually the provider. preload_dlls()
                # maps the nvidia-*-cu12 libraries, and doing that in a DirectML
                # or CPU build pulls a second vendor's libraries into the address
                # space for nothing -- the provider never asks for them.
                _provs = []
                try:
                    _provs = list(_ort.get_available_providers())
                except Exception:
                    pass
                if "CUDAExecutionProvider" in _provs and hasattr(_ort, "preload_dlls"):
                    _ort.preload_dlls()
            except Exception as _pe:
                log(f"onnxruntime preload_dlls skipped: {_pe}", "warning")
            # v3.74: WDTagger lives in this file now. An external tagger.py is
            # still honoured if someone dropped one in, but is no longer required.
            _TG = WDTagger
            try:
                from tagger import WDTagger as _ExtTagger   # optional override
                _TG = _ExtTagger
            except Exception:
                pass
            t = _TG(TAGGER_DIR).load()
            state._tagger = t
            _tag_state["device"] = t.device
            note = getattr(t, "cuda_note", "") or ""
            _tag_state["error"] = ""
            _tag_state["device_note"] = note
            if t.device == "CPU" and note:
                # v3.75: say so loudly. A silent CPU fallback is the difference
                # between tagging 12k images in minutes and in hours.
                log(f"Auto-tagger running on CPU \u2014 {note}", "warning")
            else:
                log(f"Auto-tagger loaded on {t.device}")
            return state._tagger
        except Exception as e:
            _tag_state["error"] = str(e)[:200]; state._tagger_failed = True
            log(f"Auto-tagger failed to load: {e}", "warning")
            return None


def _tag_load_image(fp, mt):
    """Return an RGB PIL.Image for the tagger: original for image/gif (gif -> first
    frame by default), a decoded first frame for video. None on hard failure."""
    try:
        if mt == "video":
            jpg = generate_video_thumbnail(fp, max_size=512)
            if not jpg:
                return None
            return Image.open(BytesIO(jpg)).convert("RGB")
        with open(fp, "rb") as f:
            raw = f.read()
        return Image.open(BytesIO(raw)).convert("RGB")
    except Exception:
        return None


def _tag_counts(db):
    try:
        row = db.execute("SELECT COUNT(*), COALESCE(SUM(tagged),0) FROM images").fetchone()
        return int(row[0]), int(row[1])
    except Exception:
        return 0, 0


def _tag_one(db, tagger, iid, fp, mt, gen_t, char_t):
    """Tag one image. Inference happens OUTSIDE the write lock; only the upsert is
    locked. Returns True on success (or deliberate skip), False to retry later."""
    img = _tag_load_image(fp, mt)
    if img is None:
        # hard decode failure -> mark tagged so the worker doesn't loop on it forever
        try:
            with _db_write_lock:
                chk = db.execute("SELECT filepath FROM images WHERE id=?", (iid,)).fetchone()
                if chk and chk["filepath"] == fp:
                    db.execute("UPDATE images SET tagged=1 WHERE id=?", (iid,))
                    _db_commit_retry(db)
        except Exception:
            return False
        return True
    try:
        res = tagger.tag_image(img, gen_threshold=gen_t, char_threshold=char_t)
    except Exception:
        return False
    finally:
        try: img.close()
        except Exception: pass
    rows = [(t.name, t.category, float(t.score)) for t in res.all]
    try:   # v3.46: ignore words are never assigned by the tagger
        ign = {r["word"] for r in db.execute("SELECT word FROM ignore_words").fetchall()}
        if ign:
            rows = [(n, c, sc) for (n, c, sc) in rows if _norm_tag(n) not in ign]
    except Exception:
        pass
    try:
        with _db_write_lock:
            chk = db.execute("SELECT filepath FROM images WHERE id=?", (iid,)).fetchone()
            if not chk or chk["filepath"] != fp:
                return True  # row removed or path changed mid-flight -> discard
            # replace only auto tags (any future manual tags are preserved)
            db.execute("DELETE FROM image_tags WHERE image_id=? AND source='auto'", (iid,))
            for name, cat, score in rows:
                db.execute("INSERT OR IGNORE INTO tags (name, category) VALUES (?,?)", (name, cat))
                tid = db.execute("SELECT id FROM tags WHERE name=? COLLATE NOCASE", (name,)).fetchone()
                if tid:
                    db.execute("INSERT INTO image_tags (image_id, tag_id, score, source) VALUES (?,?,?, 'auto') "
                               "ON CONFLICT(image_id, tag_id) DO UPDATE SET score=excluded.score "
                               "WHERE image_tags.source != 'manual'",  # v3.65: never overwrite manual tags
                               (iid, tid["id"], score))
            db.execute("UPDATE images SET tagged=1 WHERE id=?", (iid,))
            _db_commit_retry(db)
        sse_notify("tagged", {"id": iid})
        return True
    except Exception:
        return False


def _tag_claim_next(db):
    """v4.43: the same unbounded "id NOT IN (?,?,...)" that killed the embedding
    pool lived here too -- one SQL parameter per skipped image, against a limit
    of 32,766. A library big enough with enough unreadable files would have taken
    every tagging thread down the same way. Paged and filtered in Python for the
    same reason and by the same rules; see _claim_next."""
    with _tag_fail_lock:
        failed = {k for k, v in _tag_fail.items() if v >= 3}
    with _tag_claimed_lock:
        cursor = _tag_state["floor"]
        advance = cursor
        walking = True
        while True:
            rows = db.execute(
                "SELECT id, filepath, media_type FROM images WHERE tagged=0 AND id > ? "
                "ORDER BY id LIMIT ?", (cursor, _CLAIM_PAGE)).fetchall()
            if not rows:
                _tag_state["floor"] = advance
                return None, None, None
            for r in rows:
                rid = r["id"]
                if rid in failed:
                    if walking:
                        advance = rid
                    continue
                walking = False
                if rid in _tag_claimed:
                    continue
                _tag_claimed.add(rid)
                _tag_state["floor"] = advance
                return rid, r["filepath"], (r["media_type"] or "image")
            cursor = rows[-1]["id"]


def _tag_notify(force=False):
    # imported here, not at the top: tagger loads before runtime, and a
    # module cannot import from one that has not been built yet.
    from .runtime import _bench_get, _model_dl
    now = _time.time()
    if not force and (now - _tag_sse["ts"]) < 1.2:
        return
    _tag_sse["ts"] = now
    try:
        d = _get_thread_db(); total_rows, done = _tag_counts(d); d.close()
    except Exception:
        total_rows = done = 0
    # v3.74: the model-download state travels with every tag_progress event.
    # It used to be missing entirely, so the "Installing auto-tagging..." line
    # only ever updated when the page was reloaded -- the download itself pushed
    # events, they just carried no download numbers.
    try:
        _dl = {"active": bool(_model_dl.get("active")), "file": _model_dl.get("file", ""),
               "done": int(_model_dl.get("done") or 0), "total": int(_model_dl.get("total") or 0),
               "error": _model_dl.get("error", ""),
               # v3.88: the runtime install reports progress too
               "phase": _model_dl.get("phase", ""), "step": _model_dl.get("step", ""),
               "all_done": int(_model_dl.get("all_done") or 0),
               "all_total": int(_model_dl.get("all_total") or 0)}
    except Exception:
        _dl = {"active": False, "file": "", "done": 0, "total": 0, "error": "",
               "phase": "", "step": "", "all_done": 0, "all_total": 0}
    sse_notify("tag_progress", {
        "running": _tag_state["running"], "active": _tag_state["active"],
        "done": done, "total": total_rows, "pending": max(0, total_rows - done),
        "device": _tag_state["device"], "error": _tag_state["error"],
        "device_note": _tag_state.get("device_note", ""),
        "max_workers": _MAX_WORKERS,
        # v3.87: BOTH flags travel with the event. "runtime" used to be missing, so
        # the UI guessed it was installed and showed the wrong download size.
        "runtime": _tag_runtime_available(),
        "runtime_state": state._tag_runtime_state,
        "runtime_note": _tag_runtime_note(),
        "benchmark": _bench_get(),
        "warmup_ms": round(state._TAG_WARMUP * 1000) if state._TAG_WARMUP else 0,
        "model": _tag_model_available(),
        "model_download": _dl,
    })


def _tag_worker():
    # imported here, not at the top: tagger loads before api_media, and a
    # module cannot import from one that has not been built yet.
    from .api_media import _detail_name
    _boost_thread_qos()   # v3.75: keep tagging off the efficiency cores too
    db = _get_thread_db()
    cfg = _tag_get_cfg()
    tagger = _get_tagger()
    if tagger is None:
        with _tag_lock:
            _tag_state["threads"] = max(0, _tag_state["threads"] - 1)
            if _tag_state["threads"] <= 0:
                _tag_state["running"] = False
        _tag_notify(force=True); db.close(); return
    if not _tag_state["device"]:
        _tag_state["device"] = tagger.device
    idle = 0
    try:
        while _tag_state["running"] and not _tag_state["cancel"]:
            iid, fp, mt = _tag_claim_next(db)
            if iid is None:
                idle += 1
                if idle >= 20:   # ~8s with no work -> exit
                    break
                _time.sleep(0.4); continue
            idle = 0
            with _tag_lock:
                _tag_state["active"] += 1
            ok = False
            try:
                ok = _tag_one(db, tagger, iid, fp, mt, cfg["gen"], cfg["char"])
            except Exception as e:
                print(f"  ⚠ tagging #{iid}: {e}"); ok = False
            finally:
                log_detail(("Tagged " if ok else "Tagging failed for ") + _detail_name(fp))
                with _tag_lock:
                    _tag_state["active"] = max(0, _tag_state["active"] - 1)
                    if ok:
                        _tag_state["done"] += 1
                with _tag_claimed_lock:
                    _tag_claimed.discard(iid)
                with _tag_fail_lock:
                    if ok:
                        _tag_fail.pop(iid, None)
                    else:
                        _tag_fail[iid] = _tag_fail.get(iid, 0) + 1
                _tag_notify()
    finally:
        db.close()
        with _tag_lock:
            _tag_state["threads"] = max(0, _tag_state["threads"] - 1)
            if _tag_state["threads"] <= 0:
                _tag_state["running"] = False; _tag_state["active"] = 0
        _tag_notify(force=True)


def _tag_ensure_running():
    """Start tagging if enabled, available, and work exists. Safe to call repeatedly
    (no-op while already running or when disabled). Spawns a small pool of single-image
    workers that share one ONNX session and call Run() concurrently — the same model
    Anima-TrainFlow uses to tag thousands of images quickly on the GPU."""
    cfg = _tag_get_cfg()
    if not cfg["enabled"] or not _tag_runtime_available() or not _tag_model_available():
        return
    with _tag_lock:
        if _tag_state["running"]:
            return
        try:
            db = _get_thread_db(); total_rows, done = _tag_counts(db); db.close()
        except Exception:
            total_rows = done = 0
        if total_rows - done <= 0:
            return
        _tag_state["running"] = True; _tag_state["cancel"] = False
        _eff = int(cfg["workers"])
        # v4.15: 0 => Auto, and Auto is the same share the other stages use.
        _eff = _AUTO_WORKERS if _eff <= 0 else max(1, min(_MAX_WORKERS, _eff))
        # v4.29: under DirectML the session is serialised, so extra workers only
        # queue up on the lock -- twenty threads taking turns is strictly worse
        # than one, and each still holds a decoded image in memory while it waits.
        if _tag_state.get("device") == "DirectML" and _eff > 1:
            _eff = 1
        _tag_state["threads"] = _eff
        _tag_state["floor"] = 0        # v4.43: walk the backlog from the start again
        with _tag_fail_lock:
            _tag_fail.clear()
        for _ in range(_tag_state["threads"]):
            threading.Thread(target=_tag_worker, daemon=True, name="auto-tagger").start()
    _tag_notify(force=True)


def _tag_progress_payload():
    # imported here, not at the top: tagger loads before runtime, and a
    # module cannot import from one that has not been built yet.
    from .runtime import _model_dl
    try:
        d = _get_thread_db(); total_rows, done = _tag_counts(d); d.close()
    except Exception:
        total_rows = done = 0
    cfg = _tag_get_cfg()
    return {
        "model_download": dict(_model_dl),
        "enabled": cfg["enabled"], "gen": cfg["gen"], "char": cfg["char"], "workers": cfg["workers"],
        "max_workers": _MAX_WORKERS,
        "runtime": _tag_runtime_available(), "model": _tag_model_available(),
        "runtime_state": state._tag_runtime_state, "runtime_note": _tag_runtime_note(),
        "running": _tag_state["running"], "active": _tag_state["active"],
        "device": _tag_state["device"], "error": _tag_state["error"],
        "done": done, "total": total_rows, "pending": max(0, total_rows - done),
    }


def _disp_tag(name):
    """Display form of a general tag: underscores become spaces."""
    return (name or "").replace("_", " ")


def _disp_char(name):
    """Display form of a character tag: spaces + Title Case."""
    return _disp_tag(name).title()


def _img_char_tags(db, image_id):
    """Character tags of one image (display form, deduped by normalized name)."""
    rows = db.execute("""SELECT t.name FROM tags t JOIN image_tags it ON t.id=it.tag_id
        WHERE it.image_id=? AND t.category='character'
        ORDER BY it.score DESC, t.name COLLATE NOCASE""", (image_id,)).fetchall()
    seen, out = set(), []
    for r in rows:
        n = _norm_tag(r["name"])
        if n in seen: continue
        seen.add(n); out.append(_disp_char(r["name"]))
    return out


state._TAG_RUNTIME_BROKEN = ""


state._TAG_PROV_USED = ""        # v4.29: providers the probe's session actually bound


state._TAG_WARMUP = 0.0          # v4.29: seconds per inference measured by the probe


state._TAG_PROVIDERS = ""
