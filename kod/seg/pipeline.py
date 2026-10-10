"""Shirt recoloring pipeline.

Two stages, split so the expensive one can be cached per model photo:

1. ``analyze_model``  - segment the shirt on a model photo (SegFormer + color evidence).
                        Slow on CPU (seconds); the result is a small ``ShirtMask``.
2. ``recolor``        - apply a target color to a ``ShirtMask``. Fast (tens of ms).

``extract_shirt_color`` reads the fabric color off a (hanging) shirt photo.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

# SegFormer-b2-clothes label ids
L_BG, L_HAIR, L_UPPER, L_FACE = 0, 2, 4, 11
SKIN_LABELS = (11, 12, 13, 14, 15)

_MEAN = np.array([0.485, 0.456, 0.406], np.float32)
_STD = np.array([0.229, 0.224, 0.225], np.float32)

WHITE_TARGET = 238.0  # value the white reference is normalized to


class Segmenter:
    """Thin, thread-safe wrapper around the SegFormer ONNX model."""

    def __init__(self, model_path: str | Path, threads: int = 4):
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        self._sess = ort.InferenceSession(str(model_path), so, providers=["CPUExecutionProvider"])
        self._input = self._sess.get_inputs()[0].name
        self._lock = threading.Lock()  # one inference at a time keeps CPU use predictable

    def probs(self, bgr: np.ndarray) -> dict[str, np.ndarray]:
        """Per-pixel probabilities (full resolution, float32) for the classes we care about."""
        h, w = bgr.shape[:2]
        x = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), (512, 512), interpolation=cv2.INTER_AREA)
        x = ((x.astype(np.float32) / 255.0 - _MEAN) / _STD).transpose(2, 0, 1)[None]
        with self._lock:
            logits = self._sess.run(None, {self._input: x})[0][0]
        e = np.exp(logits - logits.max(0, keepdims=True))
        p = e / e.sum(0, keepdims=True)

        def up(m):
            return np.clip(cv2.resize(m, (w, h), interpolation=cv2.INTER_CUBIC), 0.0, 1.0)

        return {
            "upper": up(p[L_UPPER]),
            "skin": up(p[list(SKIN_LABELS)].sum(0)),
            "hair": up(p[L_HAIR]),
            "lower": up(p[[5, 6]].sum(0)),   # skirt + pants
            "bg": up(p[L_BG]),
        }


@dataclass
class ShirtMask:
    """Everything ``recolor`` needs; small enough to cache on disk."""
    mask: np.ndarray      # uint8 {0,1}, shirt fabric (buttons included: they are dyed along)
    ref_lab: tuple        # (L, a, b) median of the original fabric (OpenCV 8-bit Lab)

    def save(self, path: str | Path):
        np.savez_compressed(path, mask=self.mask, ref=np.array(self.ref_lab, np.float32))

    @staticmethod
    def load(path: str | Path) -> "ShirtMask":
        z = np.load(path)
        return ShirtMask(z["mask"], tuple(float(v) for v in z["ref"]))


# --------------------------------------------------------------------------- masks

def _scale(img) -> float:
    return max(0.5, max(img.shape[:2]) / 1280.0)


def _k(size: float, s: float, shape=cv2.MORPH_ELLIPSE):
    n = max(3, int(round(size * s)) | 1)
    return cv2.getStructuringElement(shape, (n, n))


def analyze_model(img: np.ndarray, seg: Segmenter) -> ShirtMask:
    """Find the shirt on a model photo."""
    s = _scale(img)
    h, w = img.shape[:2]
    p = seg.probs(img)
    uc = (p["upper"] > 0.5).astype(np.uint8)
    if uc.sum() < 500:
        raise ValueError("Fotoğrafta gömlek/üst giyim bulunamadı.")

    lab = cv2.cvtColor(cv2.GaussianBlur(img, (0, 0), 1.2 * s), cv2.COLOR_BGR2LAB).astype(np.float32)
    L, A, B = lab[..., 0], lab[..., 1], lab[..., 2]

    # dominant fabric color = median over the interior of the upper-clothes region
    core = cv2.erode(uc, _k(21, s)) > 0
    if core.sum() < 200:
        core = uc > 0
    dL, dA, dB = (float(np.median(c[core])) for c in (L, A, B))
    neutral_dist = np.hypot(dA - 128, dB - 128)
    tc = float(np.clip(0.5 * neutral_dist, 6.0, 14.0))   # chroma radius that still counts as "shirt"
    dist = np.hypot(A - dA, B - dB)

    evidence = (uc > 0) & (dist < tc) & (L > 0.3 * dL)

    # non-shirt-colored parts of the region: deep shade belongs to the fabric, bright/low-chroma
    # parts (inner top, skin) do not
    rest = ((uc > 0) & ~evidence).astype(np.uint8)
    n, lbl, st, _ = cv2.connectedComponentsWithStats(rest, 8)
    shadow = np.zeros_like(uc)
    for i in range(1, n):
        x, y, bw, bh, area = st[i]
        sel = lbl[y:y + bh, x:x + bw] == i
        if area < 4 * s * s or float(L[y:y + bh, x:x + bw][sel].mean()) < 0.62 * dL:
            shadow[y:y + bh, x:x + bw][sel] = 1

    mask = (evidence | (shadow > 0)).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _k(5, s))

    # edge snapping: lit fabric / anti-aliased edge pixels the model boundary missed
    band = (cv2.dilate(mask, _k(13, s)) > 0) & (mask == 0)
    lit_edge = (A >= dA - 8) & (B < dB + 2.5) & (L < 195) & (dist < 11) & (p["skin"] < 0.3) & (p["hair"] < 0.3)
    mask = np.where(band & lit_edge, 1, mask).astype(np.uint8)

    # trim model-boundary spill (pixels the model itself doesn't believe are clothing)
    inner = (cv2.erode(mask, _k(9, s)) > 0)
    mask = np.where(~inner & (p["upper"] < 0.25), 0, mask).astype(np.uint8)

    # clean up: keep large components, fill tiny holes
    n, lbl, st, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n > 1:
        big = st[1:, cv2.CC_STAT_AREA].max()
        keep = np.zeros_like(mask)
        for i in range(1, n):
            if st[i, cv2.CC_STAT_AREA] > 0.02 * big:
                keep[lbl == i] = 1
        mask = keep
    inv = (1 - mask).astype(np.uint8)
    n, lbl, st, _ = cv2.connectedComponentsWithStats(inv, 4)
    for i in range(1, n):
        x, y, bw, bh, area = st[i]
        if area < 120 * s * s and x > 0 and y > 0 and x + bw < w and y + bh < h:
            mask[lbl == i] = 1
    # smooth jagged chroma-threshold edges (e.g. against the inner top) without shifting the contour
    mask = (cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 1.6 * s) > 0.5).astype(np.uint8)
    sel = mask > 0
    ref = (float(np.median(L[sel])), float(np.median(A[sel])), float(np.median(B[sel])))
    return ShirtMask(mask, ref)


# --------------------------------------------------------------------------- recolor

def hex_to_lab(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    lab = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2LAB)[0, 0]
    return tuple(float(v) for v in lab)


def lab_to_hex(lab) -> str:
    bgr = cv2.cvtColor(np.uint8([[np.clip(lab, 0, 255)]]), cv2.COLOR_LAB2BGR)[0, 0]
    return "#%02x%02x%02x" % (int(bgr[2]), int(bgr[1]), int(bgr[0]))


def recolor(img: np.ndarray, sm: ShirtMask, target_lab: tuple, chroma_keep: float = 0.35) -> np.ndarray:
    """Re-dye the shirt, keeping its shading and fabric texture. Returns BGR uint8."""
    s = _scale(img)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB).astype(np.float32)
    L, A, B = lab[..., 0], lab[..., 1], lab[..., 2]
    Ls, As, Bs = sm.ref_lab
    Lt, At, Bt = target_lab

    L2 = np.clip(Lt * np.minimum(L / max(Ls, 1.0), 1.25), 0, 255)
    A2 = At + (A - As) * chroma_keep
    B2 = Bt + (B - Bs) * chroma_keep
    new = cv2.cvtColor(np.dstack([L2, A2, B2]).clip(0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)

    alpha = cv2.GaussianBlur(sm.mask.astype(np.float32), (0, 0), 0.8 * s)
    alpha = alpha[..., None]
    return (new * alpha + img * (1.0 - alpha)).clip(0, 255).astype(np.uint8)


# --------------------------------------------------------------------------- shirt color

def extract_shirt_color(img: np.ndarray, seg: Segmenter) -> dict:
    """Read the fabric color off a shirt photo.

    Returns ``raw`` (colors exactly as photographed) and ``normalized`` (white-balanced and
    exposed using the bright background, e.g. white floor tiles, as the white reference -
    phone shots in shops vary a lot). Each is ``{"hex", "lab"}``.
    """
    s = _scale(img)
    p = seg.probs(img)
    uc = (p["upper"] > 0.5).astype(np.uint8)
    core = cv2.erode(uc, _k(25, s)) > 0
    if core.sum() < 200:
        core = uc > 0
    if core.sum() < 200:
        raise ValueError("Fotoğrafta gömlek bulunamadı.")

    def fabric_color(bgr: np.ndarray) -> dict:
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
        px = lab[core]
        # drop buttons / labels / specular spots: keep the middle of the lightness distribution
        lo, hi = np.percentile(px[:, 0], [15, 85])
        px = px[(px[:, 0] >= lo) & (px[:, 0] <= hi)]
        med = np.median(px, axis=0)
        return {"lab": tuple(float(v) for v in med), "hex": lab_to_hex(med)}

    gains = np.ones(3, np.float32)
    bgp = (p["bg"] > 0.8) & (cv2.dilate(uc, _k(41, s)) == 0)
    if bgp.sum() > 2000:
        px = img.astype(np.float32)[bgp]
        lum = px.mean(1)
        lo, hi = np.percentile(lum, [60, 94])
        ref = px[(lum >= lo) & (lum <= hi)].mean(0)
        gains = np.clip(WHITE_TARGET / np.maximum(ref, 1.0), 0.6, 2.0)
    normalized = np.clip(img.astype(np.float32) * gains, 0, 255).astype(np.uint8)
    return {"raw": fabric_color(img), "normalized": fabric_color(normalized)}
