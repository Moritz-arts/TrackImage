"""Perceptual hashes -- the numbers duplicate finding compares.

Layer 10 of 27 -- see trackimage/__init__.py for the order these load in.
"""
from io import BytesIO
from .config import HAS_PHASH, HAS_PILLOW, Image, TILE_GRID, np


_DCT_MATRICES = {}


def _dct_matrix(nsz):
    m = _DCT_MATRICES.get(nsz)
    if m is None:
        k = np.arange(nsz).reshape(-1, 1)
        i = np.arange(nsz).reshape(1, -1)
        m = 2.0 * np.cos(np.pi * k * (2 * i + 1) / (2 * nsz))   # DCT-II, no normalisation
        _DCT_MATRICES[nsz] = m
    return m


def _sim_pct(dist):
    """v4.45: turn a 256-bit hash distance into the percentage shown to the user.

    Two rules, both about not claiming more than is known:

    100 is reserved for a distance of exactly 0. It used to be reached by
    rounding -- a distance of 1 came out as round(99.6) = 100 -- so a pair that
    was measurably different was presented as a perfect match.

    Everything else rounds DOWN. 98.8% is shown as 98, not 99: the number is a
    floor the pair is known to clear, never an optimistic reading of it.
    """
    d = max(0, int(dist))
    if d == 0:
        return 100
    return max(0, min(99, int((1 - d / 256) * 100)))


def _tile_sig_from_px(px):
    """8x8 tile signature from the 64x64 grayscale array used by the pHash.
    Returns int16 bytes (128 B) or None when numpy is unavailable."""
    try:
        g = TILE_GRID
        n = min(px.shape[0], px.shape[1])
        b = n // g
        if b < 1:
            return None
        cells = px[:g * b, :g * b].reshape(g, b, g, b).mean(axis=(1, 3)) - float(px.mean())
        # Normalise by the spread as well, not just the mean. Subtracting the mean
        # alone only cancels ADDITIVE shifts (brightness); a multiplicative one
        # (contrast, a re-encode with a different tone curve) scales every cell and
        # would otherwise read as a local edit. Dividing by the standard deviation
        # makes the signature invariant to any linear change, so only genuinely
        # local edits move a cell. Scaled by 64 so ~1 sigma == 64 int16 units.
        sd = float(cells.std())
        cells = (cells / sd * 64.0) if sd > 1e-6 else cells * 0.0
        return np.clip(np.rint(cells), -32000, 32000).astype(np.int16).tobytes()
    except Exception:
        return None


def _phash_tiles(im, hash_size=16, highfreq_factor=4):
    """v3.73: ONE decode, TWO signatures. Returns (phash_hex, tile_sig_bytes).
    256-bit perceptual hash as hex string -- same algorithm and bit layout as
    imagehash.phash: grayscale -> 64x64 LANCZOS -> 2D DCT-II -> 16x16 low-freq
    block -> median threshold. The 64x64 array is reused for the tile signature,
    so the region score costs no additional I/O."""
    size = hash_size * highfreq_factor
    im = im.convert("L").resize((size, size), Image.LANCZOS)
    px = np.asarray(im, dtype=np.float64)
    M = _dct_matrix(size)
    low = (M @ px @ M.T)[:hash_size, :hash_size]
    med = np.median(low)
    v = 0
    for b in (low > med).flatten():
        v = (v << 1) | int(b)
    return "%0*x" % (hash_size * hash_size // 4, v), _tile_sig_from_px(px)


def _phash16(im, hash_size=16, highfreq_factor=4):
    """256-bit perceptual hash as hex string (see _phash_tiles)."""
    return _phash_tiles(im, hash_size, highfreq_factor)[0]


def compute_hashes(filepath, _raw=None):
    """v3.73: returns (phash_hex, tile_sig_bytes) for an image file --
    ('', None) on failure. Both come from a single decode.
    If _raw (file bytes) is given, decodes from memory instead of re-reading from disk."""
    if not HAS_PHASH or not HAS_PILLOW:
        return "", None
    try:
        src = BytesIO(_raw) if _raw is not None else filepath
        with Image.open(src) as im:
            from PIL import ImageOps
            im = ImageOps.exif_transpose(im)
            return _phash_tiles(im)
    except:
        return "", None
