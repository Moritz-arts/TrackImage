"""EXIF, XMP, IPTC and generation parameters, read and stripped.

Layer 9 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from io import BytesIO
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from .config import FFMPEG_BIN, HAS_PILLOW, Image, STRIPPABLE_EXTS, VIDEO_EXTENSIONS, _IPTC_MAP, _SD_FIELD_MAP, _SD_PARAM_RE, _XMP_MAP
from .logging_setup import log
from .platform_bits import _no_window


def strip_metadata_from_file(filepath):
    """Remove EXIF / PNG text / XMP / other sidecar metadata from an image in-place.
    Returns (ok: bool, message: str). Pixel data, orientation and mtime are preserved."""
    if not HAS_PILLOW:
        return False, "Pillow not installed"
    if not os.path.isfile(filepath):
        return False, "File not found"
    ext = Path(filepath).suffix.lower()
    if ext not in STRIPPABLE_EXTS:
        return False, f"Unsupported file type ({ext or 'no extension'})"
    # Capture original file timestamps BEFORE we touch it — we'll restore them
    # so the image keeps its real creation/modification date.
    try:
        _stat = os.stat(filepath)
        orig_atime = _stat.st_atime
        orig_mtime = _stat.st_mtime
    except Exception:
        orig_atime = None
        orig_mtime = None
    # Reject animated images — stripping would flatten them
    try:
        with Image.open(filepath) as probe:
            if getattr(probe, "n_frames", 1) > 1:
                return False, "Animated images are not supported"
            fmt = probe.format
            mode = probe.mode
    except Exception as e:
        return False, f"Cannot read image: {e}"
    # Read pixels into memory, then close original handle, then atomically rewrite
    try:
        with Image.open(filepath) as src:
            from PIL import ImageOps
            src = ImageOps.exif_transpose(src)  # bake orientation before we drop EXIF
            pixels = src.copy()
            icc_profile = src.info.get("icc_profile")  # preserve color profile
    except Exception as e:
        return False, f"Cannot decode image: {e}"
    # Build a clean image with no info dict — using tobytes/frombytes avoids
    # the deprecated getdata()/putdata() and is faster for large images
    clean = Image.frombytes(pixels.mode, pixels.size, pixels.tobytes())
    # Write to temp then os.replace for atomicity (no partial writes on crash)
    tmp_path = filepath + ".tistrip.tmp"
    save_kwargs = {}
    out_format = fmt
    try:
        if ext in (".jpg", ".jpeg"):
            # JPEG can't hold alpha/palette — convert
            if clean.mode not in ("RGB", "L"):
                clean = clean.convert("RGB")
            save_kwargs = {"quality": 100, "subsampling": 0, "optimize": True}
            if icc_profile: save_kwargs["icc_profile"] = icc_profile
            out_format = "JPEG"
        elif ext == ".png":
            # Explicitly pass pnginfo=None to drop all text chunks
            from PIL import PngImagePlugin
            save_kwargs = {"pnginfo": PngImagePlugin.PngInfo(), "optimize": True}
            if icc_profile: save_kwargs["icc_profile"] = icc_profile
            out_format = "PNG"
        elif ext == ".webp":
            save_kwargs = {"quality": 100, "method": 6}
            if icc_profile: save_kwargs["icc_profile"] = icc_profile
            out_format = "WEBP"
        elif ext == ".bmp":
            out_format = "BMP"
        elif ext in (".tif", ".tiff"):
            if icc_profile: save_kwargs["icc_profile"] = icc_profile
            out_format = "TIFF"
        clean.save(tmp_path, format=out_format, **save_kwargs)
    except Exception as e:
        if os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except: pass
        return False, f"Save failed: {e}"
    # Atomic replace
    try:
        os.replace(tmp_path, filepath)
    except Exception as e:
        if os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except: pass
        return False, f"Replace failed: {e}"
    # Restore original timestamps so the file still looks like it was created/modified
    # on its original date. Without this, Windows Explorer would show the strip time.
    if orig_mtime is not None:
        try:
            os.utime(filepath, (orig_atime, orig_mtime))
        except Exception:
            pass  # non-fatal: strip succeeded, only timestamp cosmetics failed
    return True, "OK"


_RDF_LI = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li"


def _split_keywords(raw):
    """v4.56: one keyword per entry, whatever the writer used to separate them.

    A list has already been split by whoever produced it -- rdf:li carries one
    keyword per element -- so it is taken as it stands. A string is cut on both
    separators in the wild: ExifTool writes semicolons, IPTC writers commas.
    Case-insensitive dedupe, first spelling kept.
    """
    if not raw:
        return []
    if isinstance(raw, (list, tuple, set)):
        parts = [str(x) for x in raw]
    else:
        parts = str(raw).replace(";", ",").split(",")
    out, seen = [], set()
    for part in parts:
        word = " ".join(str(part).split())   # collapse newlines and runs of space
        if not word or len(word) > 100:
            continue
        low = word.casefold()
        if low in seen:
            continue
        seen.add(low)
        out.append(word)
    return out


def merge_keywords(existing, extra):
    """Fold one keyword source into another without ever producing a duplicate.

    What the file itself carried comes first and keeps its spelling: that is the
    copy the camera or the encoder wrote. Returns a comma-joined string, or ""
    when there is nothing on either side.
    """
    words = _split_keywords(existing)
    seen = {w.casefold() for w in words}
    for word in _split_keywords(extra):
        low = word.casefold()
        if low not in seen:
            seen.add(low)
            words.append(word)
    return ", ".join(words)


def _merge_sidecar(filepath, meta):
    """v4.56: fold an XMP sidecar into what the file itself carried.

    A sidecar only ever adds -- anything the file holds wins. Read for pictures
    as well as for video since v4.56: a writer that cannot reach into an MP4
    container often cannot reach into a JPEG either and drops a .xmp next to
    both, which left those keywords invisible here while every other program
    showed them.
    """
    try:
        side = read_sidecar(filepath)
    except Exception:
        return meta
    if not side:
        return meta
    extra = side.pop("keywords", None)
    for key, val in side.items():
        meta.setdefault(key, val)
    merged = merge_keywords(meta.get("keywords"), extra)
    if merged:
        meta["keywords"] = merged
    return meta


def sidecar_paths(filepath):
    """Where a sidecar for this file could be, most common spelling first.

    Two conventions are in the wild: Bridge and most video tools keep the whole
    name and append .xmp, Lightroom replaces the extension. Both are checked.
    """
    root, _ext = os.path.splitext(filepath)
    return [filepath + ".xmp", root + ".xmp"]


def find_sidecar(filepath):
    """The sidecar that exists for this file, or None."""
    for cand in sidecar_paths(filepath):
        try:
            if os.path.isfile(cand):
                return cand
        except Exception:
            pass
    return None


def read_sidecar(filepath):
    """v4.53: read an XMP sidecar sitting next to a file.

    MP4 has no EXIF -- it carries QuickTime atoms -- so tools that write
    metadata for video write a .xmp next to it instead. TrackImage could not see
    those, which made a video's keywords and rating invisible here while every
    other program showed them. Nothing is written: the sidecar is read, and if
    there is none this costs one failed stat.
    """
    path = find_sidecar(filepath)
    if not path:
        return {}
    try:
        with open(path, "rb") as fh:
            raw = fh.read(600000)
    except Exception:
        return {}
    meta = {}
    try:
        meta = parse_xmp(raw) or {}
    except Exception:
        return {}
    if meta:
        meta["sidecar"] = os.path.basename(path)
    return meta


def move_sidecar_with(old_path, new_path):
    """Keep a sidecar next to the file it describes.

    A sidecar is bound to its file by name alone. Renaming or moving the file
    without it leaves a stray .xmp behind and a video whose metadata has
    silently gone missing, so the two travel together.
    """
    src = find_sidecar(old_path)
    if not src:
        return None
    keep_suffix = src.endswith(old_path.split(os.sep)[-1] + ".xmp")
    dest = (new_path + ".xmp") if keep_suffix else (os.path.splitext(new_path)[0] + ".xmp")
    try:
        if os.path.exists(dest):
            return None
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        shutil.move(src, dest)
        log(f"Sidecar moved with the file: {os.path.basename(dest)}", "info")
        return dest
    except Exception as e:
        log(f"Could not move the sidecar for {os.path.basename(old_path)}: "
            f"{type(e).__name__}", "warning")
        return None


def extract_video_metadata(filepath):
    """Read container/format metadata from a video via ffmpeg (-f ffmetadata).
    Surfaces SD generation parameters (prompt/steps/sampler/...) when present."""
    meta = {}
    try:
        result = subprocess.run(
            [FFMPEG_BIN, "-i", filepath, "-f", "ffmetadata", "-"],
            **_no_window({"capture_output": True, "timeout": 20}))
        out = (result.stdout or b"").decode("utf-8", errors="ignore")
        err = (result.stderr or b"").decode("utf-8", errors="ignore")
        # ffmetadata escapes special chars (=, ;, #, \\) and newlines inside values
        # with a backslash, so multi-line values (e.g. SD parameter blocks) span
        # several physical lines. Parse char-by-char honoring those escapes.
        records = []
        field = []
        esc = False
        for ch in out:
            if esc:
                field.append(ch); esc = False
            elif ch == "\\":
                esc = True
            elif ch == "\n":
                records.append("".join(field)); field = []
            else:
                field.append(ch)
        if field: records.append("".join(field))
        raw_tags = {}
        for rec in records:
            rs = rec.strip()
            if not rs or rs.startswith(";") or rs.startswith("#"):
                continue
            if "=" in rec:
                k, v = rec.split("=", 1)
                k = k.strip().lower(); v = v.strip()
                if v: raw_tags[k] = v
        # SD parameters can sit in comment/description/parameters/title
        consumed = None
        for key in ("parameters", "comment", "description", "title"):
            if key in raw_tags and "raw_parameters" not in meta:
                val = raw_tags[key]
                if "Steps:" in val or "Sampler:" in val:
                    meta["raw_parameters"] = val[:3000]
                    meta.update(parse_sd_parameters(val))
                    consumed = key
                else:
                    meta.setdefault(key, val[:2000])
        for k, v in raw_tags.items():
            if k == consumed: continue
            if k not in meta and len(v) < 500:
                meta[k] = v
        m = re.search(r'(\d{2,5})x(\d{2,5})', err)
        if m:
            meta.setdefault("width_px", m.group(1))
            meta.setdefault("height_px", m.group(2))
        d = re.search(r'Duration:\s*([\d:.]+)', err)
        if d: meta.setdefault("duration", d.group(1))
    except Exception as e:
        meta["video_meta_error"] = str(e)
    try: meta.setdefault("file_size", os.path.getsize(filepath))
    except: pass
    return meta


def _extract_comfyui_prompt(raw):
    """Pull readable prompt text out of a ComfyUI 'prompt' graph JSON. The resolved text
    of an ImpactWildcardProcessor lives in its 'populated_text' input (the CLIPTextEncode
    node only links to it), so a naive reader sees no prompt. Falls back to literal
    CLIPTextEncode 'text' inputs."""
    try:
        graph = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(graph, dict):
        return {}
    wildcard, clip = [], []
    for node in graph.values():
        if not isinstance(node, dict):
            continue
        ct = str(node.get("class_type", ""))
        inp = node.get("inputs", {})
        if not isinstance(inp, dict):
            continue
        if "Wildcard" in ct:                        # ImpactWildcardProcessor / -Encode
            pt = inp.get("populated_text")
            if isinstance(pt, str) and pt.strip():
                wildcard.append(pt.strip())
        elif ct == "CLIPTextEncode":
            t = inp.get("text")
            if isinstance(t, str) and t.strip():    # literal only, not a [node, idx] link
                clip.append(t.strip())
    texts, seen = [], set()
    for t in (wildcard or clip):
        if t not in seen:
            seen.add(t); texts.append(t)
    return {"prompt": "\n".join(texts)[:2000]} if texts else {}


def extract_metadata(filepath, _raw=None):
    metadata = {}
    ext = Path(filepath).suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        meta = extract_video_metadata(filepath)
        # v4.53: whatever the container could not hold. v4.56 moved the merge
        # into _merge_sidecar so pictures get the same treatment.
        return _merge_sidecar(filepath, meta)
    if not HAS_PILLOW: return _merge_sidecar(filepath, metadata)
    try:
        _src = BytesIO(_raw) if _raw is not None else filepath
        with Image.open(_src) as img:
            try: metadata["actual_width"], metadata["actual_height"] = img.size  # v3.24: always expose real pixel size
            except Exception: pass
            # PNG text chunks
            if ext == ".png" and hasattr(img, 'text'):
                pt = img.text or {}
                # A1111 / Forge standard
                if "parameters" in pt:
                    metadata["raw_parameters"] = pt["parameters"]
                    metadata.update(parse_sd_parameters(pt["parameters"]))
                # Forge sometimes uses generation_info or geninfo
                for gkey in ("generation_info", "geninfo", "Generation info"):
                    if gkey in pt and "raw_parameters" not in metadata:
                        metadata["raw_parameters"] = pt[gkey]
                        metadata.update(parse_sd_parameters(pt[gkey]))
                # ComfyUI / generic prompt
                if "prompt" in pt:
                    try:
                        json.loads(pt["prompt"])
                        metadata["comfyui_prompt"] = True
                        metadata["raw_parameters"] = pt["prompt"][:2000]
                        _cy = _extract_comfyui_prompt(pt["prompt"])
                        if _cy.get("prompt"):
                            metadata.setdefault("prompt", _cy["prompt"])
                    except: metadata.setdefault("prompt", pt["prompt"][:2000])
                if "workflow" in pt: metadata["comfyui_workflow"] = True
                if "Description" in pt: metadata.setdefault("prompt", pt["Description"][:2000])
                # Forge/Fooocus sometimes store JSON in postprocessing or extras
                for jkey in ("postprocessing", "extras"):
                    if jkey in pt:
                        try:
                            jd = json.loads(pt[jkey])
                            if isinstance(jd, dict):
                                for k, v in jd.items():
                                    if k not in metadata and isinstance(v, (str, int, float)):
                                        metadata[k] = v
                        except: pass
                # NAI-style Comment JSON
                if "Comment" in pt:
                    try:
                        c = json.loads(pt["Comment"])
                        if isinstance(c, dict):
                            if "uc" in c: metadata["negative_prompt"] = c["uc"][:1000]
                            for k in ("steps","sampler","seed","scheduler"):
                                if k in c: metadata[k] = c[k]
                            if "strength" in c: metadata["cfg_scale"] = c["strength"]
                            if "cfg" in c and "cfg_scale" not in metadata: metadata["cfg_scale"] = c["cfg"]
                            if "prompt" in c and "prompt" not in metadata: metadata["prompt"] = str(c["prompt"])[:2000]
                            if "negative_prompt" in c and "negative_prompt" not in metadata: metadata["negative_prompt"] = str(c["negative_prompt"])[:1000]
                    except: pass
                # Catch-all for remaining text chunks
                for key in pt:
                    kl = key.lower()
                    if kl not in metadata and kl not in ("parameters","prompt","workflow","comment","description","generation_info","geninfo","generation info","postprocessing","extras","xml:com.adobe.xmp","raw profile type xmp","raw profile type exif","raw profile type iptc"):
                        if isinstance(pt[key], str) and len(pt[key]) < 2000: metadata[key] = pt[key]

            # WEBP/JPEG XMP metadata (Forge can embed here)
            if ext in (".webp", ".jpg", ".jpeg") and hasattr(img, 'info'):
                xmp = img.info.get("xmp", b"")
                if isinstance(xmp, bytes): xmp = xmp.decode("utf-8", errors="ignore")
                if xmp and "parameters" not in metadata:
                    # Try to extract SD parameters from XMP description
                    try:
                        root = ET.fromstring(xmp)
                        for elem in root.iter():
                            desc = elem.get("{http://purl.org/dc/elements/1.1/}description", "") or elem.text or ""
                            if desc and ("Steps:" in desc or "Sampler:" in desc):
                                metadata["raw_parameters"] = desc[:3000]
                                metadata.update(parse_sd_parameters(desc))
                                break
                    except: pass
                # WEBP EXIF chunk
                if ext == ".webp" and "parameters" not in metadata:
                    exif_bytes = img.info.get("exif", b"")
                    if exif_bytes:
                        try:
                            from PIL.ExifTags import TAGS
                            e2 = img.getexif()
                            uc = e2.get(0x9286, None)  # UserComment
                            if uc:
                                uc = _decode_user_comment(uc).strip('\x00').strip()
                                if uc and ("Steps:" in uc or "Sampler:" in uc or len(uc) > 20):
                                    metadata["raw_parameters"] = uc[:3000]
                                    metadata.update(parse_sd_parameters(uc))
                        except: pass

            # JPEG/WEBP comment in img.info (COM marker)
            if hasattr(img, 'info') and "raw_parameters" not in metadata:
                for info_key in ("comment", "Comment", "description", "Description"):
                    cval = img.info.get(info_key, None)
                    if cval:
                        if isinstance(cval, bytes): cval = cval.decode('utf-8', errors='ignore')
                        cval = cval.strip('\x00').strip()
                        if cval and ("Steps:" in cval or "Sampler:" in cval or len(cval) > 50):
                            metadata["raw_parameters"] = cval[:3000]
                            metadata.update(parse_sd_parameters(cval))
                            break

            # v3.90: XMP + IPTC. ExifTool-driven writers (Grabber and friends) put
            # creator / keywords / preserved filename here, never into EXIF.
            try:
                _xm = img.info.get("xmp") or img.info.get("XML:com.adobe.xmp")
                if _xm:
                    _xd = parse_xmp(_xm)
                    _merge_keywords(metadata, _xd.pop("keywords", None))
                    for _k, _v in _xd.items(): metadata.setdefault(_k, _v)
            except Exception: pass
            try:
                _ps = img.info.get("photoshop")
                if isinstance(_ps, dict) and _ps.get(1028):
                    _id = parse_iptc(_ps.get(1028))
                    _merge_keywords(metadata, _id.pop("keywords", None))
                    for _k, _v in _id.items(): metadata.setdefault(_k, _v)
            except Exception: pass

            # Full EXIF extraction
            from PIL.ExifTags import TAGS, GPSTAGS, IFD
            exif = img.getexif() if hasattr(img, 'getexif') else None
            if exif:
                # Standard EXIF tag name mapping for nice display
                EXIF_NAMES = {
                    0x010F: "camera_make", 0x0110: "camera_model", 0x0131: "software",
                    0x0132: "date_time", 0x9003: "date_original", 0x9004: "date_digitized",
                    0x829A: "exposure_time", 0x829D: "f_number", 0x8827: "iso",
                    0x9207: "metering_mode", 0x9209: "flash", 0x920A: "focal_length",
                    0xA405: "focal_length_35mm", 0xA001: "color_space",
                    0x8822: "exposure_program", 0x9201: "shutter_speed",
                    0x9202: "aperture", 0x9204: "exposure_bias",
                    0x9206: "subject_distance", 0xA002: "pixel_x", 0xA003: "pixel_y",
                    0xA217: "sensing_method", 0xA403: "white_balance",
                    0xA406: "scene_type", 0xA431: "serial_number",
                    0xA432: "lens_info", 0xA433: "lens_make", 0xA434: "lens_model",
                    0xA300: "file_source", 0x9286: "user_comment",
                    0x010E: "image_description",
                    0x0112: "orientation", 0x011A: "x_resolution", 0x011B: "y_resolution",
                    0x0128: "resolution_unit", 0xA404: "digital_zoom",
                    0x9205: "max_aperture", 0xA402: "exposure_mode",
                    0x8824: "spectral_sensitivity", 0xA407: "gain_control",
                    0xA408: "contrast", 0xA409: "saturation", 0xA40A: "sharpness",
                }
                SKIP_TAGS = {0x8769, 0x8825, 0xA005}  # ExifOffset, GPSInfo, InteropOffset
                for tag_id, val in exif.items():
                    if tag_id in SKIP_TAGS: continue
                    if tag_id in EXIF_NAMES:
                        key = EXIF_NAMES[tag_id]
                    else:
                        key = TAGS.get(tag_id, f"tag_{tag_id}")
                    if key == "user_comment":
                        if isinstance(val, (str, bytes)):
                            val = _decode_user_comment(val).strip('\x00').strip()
                            if val and "raw_parameters" not in metadata:
                                metadata["raw_parameters"] = val[:3000]
                                metadata.update(parse_sd_parameters(val))
                        continue
                    if key == "image_description":
                        # Some tools (and some TIFF exports) put the SD infotext here.
                        if isinstance(val, (str, bytes)):
                            dv = _decode_user_comment(val).strip('\x00').strip()
                            if dv and "raw_parameters" not in metadata and \
                               ("Steps:" in dv or "Sampler:" in dv or "Negative prompt:" in dv):
                                metadata["raw_parameters"] = dv[:3000]
                                metadata.update(parse_sd_parameters(dv))
                                continue
                            if dv and "image_description" not in metadata and len(dv) < 500:
                                metadata["image_description"] = dv
                        continue
                    if isinstance(val, bytes): continue
                    if isinstance(val, tuple) and len(val) == 2 and all(isinstance(x,(int,float)) for x in val):
                        val = f"{val[0]}/{val[1]}" if val[1] else str(val[0])
                    sval = str(val).strip()
                    if sval and len(sval) < 500 and key not in metadata:
                        metadata[key] = sval

                # Try to get EXIF IFD (sub-IFD with more detailed photo info)
                try:
                    exif_ifd = exif.get_ifd(IFD.Exif)
                    if exif_ifd:
                        for tag_id, val in exif_ifd.items():
                            if tag_id in EXIF_NAMES:
                                key = EXIF_NAMES[tag_id]
                            else:
                                key = TAGS.get(tag_id, f"exif_{tag_id}")
                            if key == "user_comment":
                                if isinstance(val, (str, bytes)) and "raw_parameters" not in metadata:
                                    val = _decode_user_comment(val).strip('\x00').strip()
                                    if val:
                                        metadata["raw_parameters"] = val[:3000]
                                        metadata.update(parse_sd_parameters(val))
                                continue
                            if isinstance(val, bytes): continue
                            if isinstance(val, tuple) and len(val) == 2 and all(isinstance(x,(int,float)) for x in val):
                                val = f"{val[0]}/{val[1]}" if val[1] else str(val[0])
                            sval = str(val).strip()
                            if sval and len(sval) < 500 and key not in metadata:
                                metadata[key] = sval
                except: pass

                # GPS coordinates (the GPS IFD is skipped above) -> decimal degrees
                try:
                    gps = exif.get_ifd(IFD.GPSInfo)
                    if gps:
                        def _deg(v):
                            return float(v[0]) + float(v[1]) / 60.0 + float(v[2]) / 3600.0
                        lat, lon = gps.get(2), gps.get(4)
                        if lat and lon:
                            la, lo = _deg(lat), _deg(lon)
                            if gps.get(1) in ("S", b"S"): la = -la
                            if gps.get(3) in ("W", b"W"): lo = -lo
                            metadata["gps"] = f"{la:.6f}, {lo:.6f}"
                except Exception:
                    pass

        _kw = metadata.pop("_kw", None)
        if _kw: metadata["keywords"] = ", ".join(_kw)
        try: metadata["file_size"] = len(_raw) if _raw is not None else os.path.getsize(filepath)
        except: pass
    except Exception as e: metadata["error"] = str(e)
    try: metadata.setdefault("file_size", len(_raw) if _raw is not None else os.path.getsize(filepath))
    except: pass
    # v4.56: last, so the file's own metadata is already in place and wins.
    return _merge_sidecar(filepath, metadata)


def _sd_unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        return v[1:-1].replace('\\"', '"').replace('\\\\', '\\')
    return v


def parse_sd_parameters(text):
    result = {}
    if not text: return result
    # Drop stray null bytes (from mis-decoded UTF-16) and normalise.
    text = text.replace('\x00', '').strip()
    if not text: return result
    # The settings tail begins at the first "Steps: <n>" (A1111/Forge convention).
    # Using string positions (not line starts) so single-line infotext also splits.
    msteps = re.search(r'\bSteps:\s*\d', text)
    if msteps:
        settings_line = text[msteps.start():].strip().lstrip(',').strip()
        head = text[:msteps.start()].rstrip().rstrip(',').strip()
    else:
        settings_line = ""
        head = text
    # Normalise any newlines inside the settings tail to commas so captures stay tight.
    settings_line = re.sub(r'\s*\n\s*', ', ', settings_line)
    # Split the head into prompt / negative — works with or without newlines.
    mneg = re.search(r'\bNegative prompt:\s*', head)
    if mneg:
        prompt = head[:mneg.start()].strip()
        negative = head[mneg.end():].strip()
        if prompt: result["prompt"] = prompt[:2000]
        if negative: result["negative_prompt"] = negative[:1000]
    elif head:
        result["prompt"] = head[:2000]
    if settings_line:
        # Generic capture: pull EVERY "Key: Value" pair, not a fixed whitelist, so
        # Scheduler, VAE/Module N, Hires CFG/Sampler, the whole ADetailer block,
        # Lora hashes, Version, etc. all surface. Known keys map to canonical names;
        # everything else is kept under a normalised key so the panel still lists it.
        for m in _SD_PARAM_RE.finditer(settings_line):
            key = m.group(1).strip()
            val = _sd_unquote(m.group(2))
            if not key or val == "": continue
            kl = key.lower()
            canon = _SD_FIELD_MAP.get(kl)
            if canon:
                result[canon] = val[:300]
            else:
                nk = re.sub(r'[^a-z0-9]+', '_', kl).strip('_')
                if nk and nk not in result:
                    result[nk] = val[:300]
        # Derive the post-Hires resolution when Hires fix was used:
        # prefer an explicit "Hires resize: WxH", else base Size x Hires upscale.
        if "hires_size" not in result:
            mb = re.match(r'(\d+)\s*x\s*(\d+)', result.get("size", ""))
            if result.get("hires_resize"):
                mr = re.match(r'(\d+)\s*x\s*(\d+)', result["hires_resize"])
                if mr: result["hires_size"] = f"{mr.group(1)}x{mr.group(2)}"
            elif mb and result.get("hires_upscale"):
                try:
                    f = float(result["hires_upscale"])
                    result["hires_size"] = f"{round(int(mb.group(1))*f)}x{round(int(mb.group(2))*f)}"
                except Exception:
                    pass
    return result


def _xmp_text(elem):
    """Collect the value of one XMP property: plain text, or every rdf:li below it."""
    lis = [(e.text or "").strip() for e in elem.iter()
           if e.tag == "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}li"]
    lis = [x for x in lis if x]
    if lis: return lis
    t = (elem.text or "").strip()
    return [t] if t else []


def parse_xmp(xmp):
    """v3.90: whitelist read of an XMP packet (JPEG/WEBP APP1, PNG iTXt).

    ExifTool -- and therefore every downloader driving it -- writes creator,
    keywords and the preserved filename into XMP, never into EXIF. Only the
    fields below are taken; the rest of a packet is deliberately dropped so
    Adobe-written files do not bury the panel."""
    out = {}
    if not xmp: return out
    if isinstance(xmp, bytes): xmp = xmp.decode("utf-8", errors="ignore")
    xmp = xmp.strip().lstrip("\ufeff")
    i = xmp.find("<x:xmpmeta")
    if i < 0: i = xmp.find("<rdf:RDF")
    if i > 0: xmp = xmp[i:]
    j = xmp.rfind("<?xpacket end")
    if j > 0: xmp = xmp[:j]
    try: root = ET.fromstring(xmp)
    except Exception: return out
    kw = []
    for elem in root.iter():
        # property as a child element
        key = _XMP_MAP.get(elem.tag)
        if key:
            vals = _xmp_text(elem)
            if vals:
                if key == "keywords":
                    # v4.56: an rdf:Seq/Bag is already one keyword per <rdf:li>
                    # and must not be cut again -- "Smith, John" is one keyword.
                    # A bare text node (pdf:Keywords) is a single separated
                    # string and has to be split.
                    if any(e.tag == _RDF_LI for e in elem.iter()):
                        kw.extend(vals)
                    else:
                        kw.extend(_split_keywords(vals[0]))
                elif key not in out: out[key] = vals[0][:500]
        # property as an attribute on rdf:Description
        for a, av in elem.attrib.items():
            k2 = _XMP_MAP.get(a)
            if not k2 or not str(av).strip(): continue
            if k2 == "keywords": kw.extend(_split_keywords(av))
            elif k2 not in out: out[k2] = str(av).strip()[:500]
    if kw: out["keywords"] = kw
    return out


def parse_iptc(data):
    """v3.90: parse the IPTC-IIM payload of the Photoshop APP13 block (8BIM 0x0404).

    Pillow hands this over pre-split as img.info['photoshop'][1028]."""
    out, kw = {}, []
    if not data: return out
    utf8 = False
    q = 0
    while q < len(data) - 4:
        if data[q] != 0x1C: break
        rec, ds = data[q + 1], data[q + 2]
        ln = int.from_bytes(data[q + 3:q + 5], "big")
        if ln & 0x8000:  # extended (>32 kB) dataset -- not used by any writer here
            break
        val = data[q + 5:q + 5 + ln]
        q += 5 + ln
        if rec == 1 and ds == 90:
            utf8 = b"%G" in val   # CodedCharacterSet = ESC % G -> UTF-8
            continue
        if rec != 2: continue
        key = _IPTC_MAP.get(ds)
        if not key: continue
        try: sval = val.decode("utf-8" if utf8 else "utf-8")
        except UnicodeDecodeError: sval = val.decode("latin-1", errors="ignore")
        sval = sval.strip("\x00").strip()
        if not sval: continue
        if key == "keywords": kw.append(sval)
        elif key == "date_created" and len(sval) == 8 and sval.isdigit():
            out.setdefault(key, f"{sval[0:4]}:{sval[4:6]}:{sval[6:8]}")
        elif key not in out: out[key] = sval[:500]
    if kw: out["keywords"] = kw
    return out


def _merge_keywords(metadata, new):
    """Union of keyword lists from XMP and IPTC, order kept, case-insensitive dedupe."""
    if not new: return
    cur = metadata.get("_kw") or []
    seen = {x.lower() for x in cur}
    for k in new:
        if k.lower() not in seen:
            seen.add(k.lower()); cur.append(k)
    metadata["_kw"] = cur


def _decode_user_comment(val):
    """Decode an EXIF UserComment (0x9286) per the EXIF spec character-code prefix.
    Handles UNICODE (UTF-16), ASCII, and raw/charset-prefixed payloads, whether the
    value arrives as bytes (piexif) or str (Pillow)."""
    if isinstance(val, bytes):
        if val[:8] == b"UNICODE\x00":
            body = val[8:]
            for enc in ("utf-16-be", "utf-16-le", "utf-16"):
                try:
                    s = body.decode(enc)
                    if s: return s.replace("\x00", "")
                except Exception:
                    pass
            return body.decode("utf-8", errors="ignore")
        if val[:8] == b"ASCII\x00\x00\x00":
            return val[8:].decode("utf-8", errors="ignore")
        try:
            return val.decode("utf-8")
        except Exception:
            return val.decode("utf-8", errors="ignore")
    s = str(val)
    for pfx in ("UNICODE\x00", "ASCII\x00\x00\x00", 'charset="Ascii" ', "charset=Unicode "):
        if s.startswith(pfx):
            s = s[len(pfx):]
            break
    return s


def _icc_validate(icc, in_mode="RGB"):
    """Returns (valid, description). Valid = parseable AND usable for a transform
    from the image's own colorspace to sRGB."""
    try:
        from PIL import ImageCms
        prof = ImageCms.ImageCmsProfile(BytesIO(icc))
        cms_in = "CMYK" if in_mode == "CMYK" else "RGB"
        ImageCms.buildTransform(prof, ImageCms.createProfile("sRGB"), cms_in, "RGB")
        try: desc = (ImageCms.getProfileDescription(prof) or "").strip()
        except Exception: desc = ""
        return True, desc or "(unnamed profile)"
    except Exception:
        return False, None


def _find_exiftool():
    import shutil as _sh
    p = _sh.which("exiftool")
    if p: return p
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for c in ("exiftool.exe", os.path.join("tools", "exiftool.exe"), "exiftool"):
        fp = os.path.join(base, c)
        if os.path.isfile(fp): return fp
    return None


_EXIFTOOL = _find_exiftool()


if _EXIFTOOL:
    print(f"  \U0001f50e exiftool found \u2014 extended metadata enabled ({_EXIFTOOL})")


def _exiftool_read(fp):
    """v3.58: optional ExifTool enrichment (exotic/MakerNote fields). Read-only,
    on-demand in the detail view, graceful when the binary is missing."""
    if not _EXIFTOOL: return {}
    try:
        import subprocess
        out = subprocess.run([_EXIFTOOL, "-j", "-G1", "-fast2", "-charset", "filename=UTF8", fp],
                             **_no_window({"capture_output": True, "timeout": 15}))
        data = json.loads(out.stdout.decode("utf-8", "replace") or "[]")
        if not data: return {}
        res = {}
        for k, v in data[0].items():
            grp, _, tag = k.partition(":")
            if not tag or grp in ("ExifTool", "System", "File"):
                continue
            if isinstance(v, (dict, list)) or (isinstance(v, str) and (len(v) > 500 or v.startswith("(Binary"))):
                continue
            key = re.sub(r"(?<!^)(?=[A-Z])", "_", tag).lower()
            res.setdefault(key, v)
        return res
    except Exception:
        return {}
