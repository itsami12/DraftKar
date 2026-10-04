"""CNIC back-side IMAGE PROCESSING (stage 1 of the pipeline). Pure functions, in-memory only, nothing is stored.

    uploaded image (EXIF already applied by image.read_upload)
      -> find_card()            locate the card in a camera photo (fingers / table / dark background tolerated)
      -> rectify_card()         perspective + tilt correction, output is landscape
      -> orientation_candidates()  upright / 180° (card found) or 0/90/180/270° (card not found). Which one is right is
                                   decided later by OCR scoring, never guessed blindly.
      -> enhancement_variants()  OCR-friendly copies (A contrast+upscale, B sharpened, C adaptive threshold)

The original image is never modified; every function returns new images. If card detection is not reliable the full image
is used instead of failing. OpenCV is optional: without it the code degrades to Pillow-only (full image, 4 rotations).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from PIL import Image, ImageFilter, ImageOps

try:  # OpenCV is used for card detection / perspective / thresholding; everything still works (less well) without it
    import cv2
    import numpy as np
except Exception:  # pragma: no cover
    cv2 = None
    np = None

log = logging.getLogger("draftkar.cnic.image")
CARD_RATIO = 85.6 / 54.0  # ID-1 card (CNIC): 1.585
MIN_OCR_WIDTH = 1500      # small crops are upscaled to at least this width before OCR


@dataclass
class Candidate:
    """One orientation hypothesis. `image` is an RGB PIL image; `rotation` is degrees counter-clockwise from the card/frame base."""
    label: str
    rotation: int
    image: Image.Image
    source: str  # "card" (detected + rectified) | "full" (whole photo)
    meta: dict = field(default_factory=dict)


# ---------------------------------------------------------------- card detection
def _to_bgr(img: Image.Image):
    return cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def _to_pil(bgr) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def _order_quad(pts):
    pts = np.asarray(pts, dtype="float32").reshape(4, 2)
    s, d = pts.sum(axis=1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype="float32")  # tl tr br bl


def _quad_ratio(q):
    w = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2
    h = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    return max(w, h) / max(1.0, min(w, h))


def _contour_quad(im):
    """Strategy 1: a bright/pale-green blob whose outline is a clean quadrilateral with a card-like aspect ratio."""
    H, W = im.shape[:2]
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    mask = cv2.bitwise_or(cv2.inRange(hsv, (0, 0, 140), (180, 110, 255)), cv2.inRange(hsv, (30, 25, 110), (90, 255, 255)))
    best = None
    for k in (21, 41):  # larger opening separates the card from bright neighbours (table, marble)
        m = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(cs, key=cv2.contourArea, reverse=True)[:4]:
            area = cv2.contourArea(c) / (H * W)
            if area < 0.12 or area > 0.97:
                continue
            hull = cv2.convexHull(c)
            poly = cv2.approxPolyDP(hull, 0.03 * cv2.arcLength(hull, True), True)
            if len(poly) != 4:
                continue
            q = _order_quad(poly)
            rect = cv2.contourArea(hull) / max(1.0, cv2.contourArea(q.astype("float32")))
            ratio = _quad_ratio(q)
            if 1.35 <= ratio <= 1.85 and 0.9 <= rect <= 1.12:
                score = area * (1 - abs(ratio - CARD_RATIO))
                if best is None or score > best[0]:
                    best = (score, q, area)
    return (best[1], "contour", min(1.0, best[2] * 2)) if best else None


def _cover(intervals, lo, hi):
    if hi <= lo:
        return 0.0
    tot, cur = 0.0, lo
    for a, b in sorted(intervals):
        a, b = max(a, lo), min(b, hi)
        if b <= max(cur, a):
            continue
        tot += b - max(cur, a)
        cur = b
    return tot / (hi - lo)


def _cluster(items, tol):
    """items: [(pos, lo, hi, length)] -> [(pos, [(lo,hi)], total_length)] merged when positions are within tol."""
    out = []
    for pos, lo, hi, ln in sorted(items):
        if out and abs(out[-1][0] - pos) <= tol:
            p, iv, t = out[-1]
            n = len(iv)
            out[-1] = ((p * n + pos) / (n + 1), iv + [(lo, hi)], t + ln)
        else:
            out.append((pos, [(lo, hi)], ln))
    return out


def _line_rect(im):
    """Strategy 2: long straight edges (Hough) -> dominant tilt -> best axis-aligned rectangle with a card aspect ratio in the
    de-tilted frame -> mapped back to a quadrilateral. Works when colour segmentation fails (hand, marble, dark table)."""
    H, W = im.shape[:2]
    g = cv2.createCLAHE(2.0, (8, 8)).apply(cv2.cvtColor(im, cv2.COLOR_BGR2GRAY))
    edges = cv2.Canny(cv2.GaussianBlur(g, (5, 5), 0), 30, 100)
    L = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=40, minLineLength=int(0.15 * min(H, W)), maxLineGap=int(0.03 * max(H, W)))
    if L is None or len(L) < 4:
        return None
    L = L[:, 0, :].astype("float64")
    ln = np.hypot(L[:, 2] - L[:, 0], L[:, 3] - L[:, 1])
    ang = np.degrees(np.arctan2(L[:, 3] - L[:, 1], L[:, 2] - L[:, 0]))
    d = ang % 90
    d = np.where(d > 45, d - 90, d)  # tilt of every line modulo 90°, in (-45, 45]
    hist, edges_ = np.histogram(d, bins=np.arange(-45, 46, 1.0), weights=ln)
    hist = np.convolve(hist, [1, 2, 1], mode="same")
    mode = float((edges_[int(np.argmax(hist))] + edges_[int(np.argmax(hist)) + 1]) / 2)
    near = np.abs(d - mode) <= 2.0
    mode = float((d[near] * ln[near]).sum() / ln[near].sum()) if near.any() else mode
    c = (W / 2, H / 2)
    best = None
    for tilt in ({mode, 0.0} if abs(mode) > 0.8 else {mode}):  # the dominant tilt, and "already straight"
        r = _rect_for_tilt(L, ln, tilt, c, H, W, im)
        if r and (best is None or r[0] > best[0]):
            best = r
    if best is None or best[2] < 0.35:
        return None
    _, (x1, y1, x2, y2), cov, M = best
    pad = 0.006 * max(H, W)
    box = np.array([[x1 - pad, y1 - pad], [x2 + pad, y1 - pad], [x2 + pad, y2 + pad], [x1 - pad, y2 + pad]], dtype="float64")
    inv = cv2.invertAffineTransform(M)
    quad = (box @ inv[:, :2].T) + inv[:, 2]
    return _order_quad(quad), "lines", float(min(1.0, cov))


def _side_contrast(rim, x1, y1, x2, y2):
    """Per side (top, bottom, left, right): colour difference between a thin strip just outside and just inside, 0..1."""
    H, W = rim.shape[:2]
    gx, gy = int(0.1 * (x2 - x1)), int(0.1 * (y2 - y1))
    d = max(3, int(0.008 * max(H, W)))

    def strip(xa, xb, ya, yb):
        xa, xb, ya, yb = max(0, int(xa)), min(W, int(xb)), max(0, int(ya)), min(H, int(yb))
        return rim[ya:yb, xa:xb].reshape(-1, 3).mean(0) if xb > xa and yb > ya else None

    pairs = [(strip(x1 + gx, x2 - gx, y1 - 3 * d, y1 - d), strip(x1 + gx, x2 - gx, y1 + d, y1 + 3 * d)),
             (strip(x1 + gx, x2 - gx, y2 + d, y2 + 3 * d), strip(x1 + gx, x2 - gx, y2 - 3 * d, y2 - d)),
             (strip(x1 - 3 * d, x1 - d, y1 + gy, y2 - gy), strip(x1 + d, x1 + 3 * d, y1 + gy, y2 - gy)),
             (strip(x2 + d, x2 + 3 * d, y1 + gy, y2 - gy), strip(x2 - 3 * d, x2 - d, y1 + gy, y2 - gy))]
    return [0.0 if a is None or b is None else min(1.0, float(np.abs(a - b).mean()) / 45.0) for a, b in pairs]


def _rect_for_tilt(L, ln, tilt, c, H, W, im):
    """Best card-shaped axis-aligned rectangle after de-tilting the segments by `tilt`. -> (score, box, coverage, M) or None."""
    M = cv2.getRotationMatrix2D(c, -tilt, 1.0)  # a line whose angle is `tilt` becomes horizontal
    p = np.stack([np.stack([L[:, 0], L[:, 1]], 1), np.stack([L[:, 2], L[:, 3]], 1)])  # (2,n,2)
    q = (p @ M[:, :2].T) + M[:, 2]
    dx, dy = np.abs(q[1, :, 0] - q[0, :, 0]), np.abs(q[1, :, 1] - q[0, :, 1])
    hor = [((q[0, i, 1] + q[1, i, 1]) / 2, min(q[:, i, 0]), max(q[:, i, 0]), ln[i]) for i in range(len(L)) if dy[i] < 0.08 * dx[i]]
    ver = [((q[0, i, 0] + q[1, i, 0]) / 2, min(q[:, i, 1]), max(q[:, i, 1]), ln[i]) for i in range(len(L)) if dx[i] < 0.08 * dy[i]]
    tol = 0.012 * max(H, W)
    ys = sorted(_cluster(hor, tol), key=lambda x: -x[2])[:16]
    xs = sorted(_cluster(ver, tol), key=lambda x: -x[2])[:16]
    pool = []
    for (y1, iy1, _), (y2, iy2, _) in ((a, b) for a in ys for b in ys if a[0] < b[0]):
        for (x1, ix1, _), (x2, ix2, _) in ((a, b) for a in xs for b in xs if a[0] < b[0]):
            w, h = x2 - x1, y2 - y1
            if min(w, h) < 0.2 * min(H, W) or not 1.4 <= max(w, h) / min(w, h) <= 1.8:
                continue
            cov = [_cover(iy1, x1, x2), _cover(iy2, x1, x2), _cover(ix1, y1, y2), _cover(ix2, y1, y2)]
            if sum(1 for v in cov if v >= 0.3) < 3:
                continue
            area = (w * h) / (H * W)
            pool.append((sum(cov) / 4 + 0.4 * min(area, 0.6) - 0.2 * abs(max(w, h) / min(w, h) - CARD_RATIO), (x1, y1, x2, y2), sum(cov) / 4))
    if not pool:
        return None
    # A card EDGE separates different content (card vs hand/table); a long line of printed text does not. Check the top candidates.
    rim = cv2.GaussianBlur(cv2.warpAffine(im, M, (W, H), borderMode=cv2.BORDER_REPLICATE), (5, 5), 0).astype("float32")
    best = None
    for sc, (x1, y1, x2, y2), cv_ in sorted(pool, key=lambda t: -t[0])[:80]:
        con = _side_contrast(rim, x1, y1, x2, y2)
        if sum(1 for v in con if v >= 0.3) < 3:
            continue
        sc += 1.5 * sum(con) / 4
        if best is None or sc > best[0]:
            best = (sc, (x1, y1, x2, y2), cv_, M)
    return best


def find_card(img: Image.Image) -> dict | None:
    """-> {'quad': 4x2 float array in ORIGINAL image pixels (tl,tr,br,bl), 'method', 'confidence'} or None when not reliable."""
    if cv2 is None:
        return None
    try:
        bgr = _to_bgr(img)
        H, W = bgr.shape[:2]
        s = 1000 / max(H, W) if max(H, W) > 1000 else 1.0
        im = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else bgr
        for fn in (_contour_quad, _line_rect):
            r = fn(im)
            if r:
                q, method, conf = r
                q = q / s
                q[:, 0] = np.clip(q[:, 0], 0, W - 1)
                q[:, 1] = np.clip(q[:, 1], 0, H - 1)
                return {"quad": q, "method": method, "confidence": round(conf, 2)}
    except Exception as e:  # never let detection break the pipeline
        log.warning("card detection skipped: %s", type(e).__name__)
    return None


def rectify_card(img: Image.Image, quad) -> Image.Image:
    """Perspective-warp the detected quadrilateral to a flat LANDSCAPE rectangle (which 180° variant is up is unknown here)."""
    q = _order_quad(quad)
    w = int(round(max(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[3]))))
    h = int(round(max(np.linalg.norm(q[3] - q[0]), np.linalg.norm(q[2] - q[1]))))
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype="float32")
    out = cv2.warpPerspective(_to_bgr(img), cv2.getPerspectiveTransform(q, dst), (w, h), flags=cv2.INTER_CUBIC)
    if h > w:
        out = cv2.rotate(out, cv2.ROTATE_90_CLOCKWISE)
    return _to_pil(out)


def rotate(img: Image.Image, degrees_ccw: int) -> Image.Image:
    """Lossless 0/90/180/270 rotation (counter-clockwise)."""
    return {0: img, 90: img.transpose(Image.ROTATE_90), 180: img.transpose(Image.ROTATE_180), 270: img.transpose(Image.ROTATE_270)}[degrees_ccw % 360].copy()


def orientation_candidates(img: Image.Image) -> list[Candidate]:
    """The orientation hypotheses to be scored by OCR, most likely first. Not blind: a detected card is first flattened to
    landscape, so only upright / upside-down remain; a full photo is tried in the orientations implied by its shape first."""
    card = find_card(img)
    out: list[Candidate] = []
    if card:
        flat = rectify_card(img, card["quad"])
        meta = {"detect": card["method"], "detect_confidence": card["confidence"], "card_size": list(flat.size)}
        out += [Candidate("card@0", 0, flat, "card", meta), Candidate("card@180", 180, rotate(flat, 180), "card", meta)]
    portrait = img.height > img.width
    order = (90, 270, 0, 180) if portrait else (0, 180, 90, 270)
    out += [Candidate(f"full@{r}", r, rotate(img, r), "full", {"portrait": portrait}) for r in order]
    return out


# ---------------------------------------------------------------- enhancement
def _upscale(img: Image.Image, min_width: int = MIN_OCR_WIDTH, max_side: int = 2600) -> Image.Image:
    f = 1.0
    if img.width < min_width:
        f = min_width / img.width
    if max(img.size) * f > max_side:
        f = max_side / max(img.size)
    return img if abs(f - 1) < 0.02 else img.resize((max(1, round(img.width * f)), max(1, round(img.height * f))), Image.LANCZOS)


def _gray_contrast(img: Image.Image) -> Image.Image:
    g = ImageOps.grayscale(img)
    if cv2 is not None:
        a = np.asarray(g)
        # CLAHE evens out uneven lighting / shadows; the clip limit is low on purpose so Urdu strokes are not eroded
        a = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(a)
        g = Image.fromarray(a)
    return ImageOps.autocontrast(g, cutoff=1)


def enhancement_variants(img: Image.Image, names=("A", "B", "C")) -> dict[str, Image.Image]:
    """OCR-friendly copies, computed only for the requested `names`.
    A: grayscale + contrast + upscale (default). B: A + mild edge-preserving denoise + sharpening.
    C: adaptive threshold (helps faint/low-contrast prints; a separate variant because it can erase thin strokes)."""
    out: dict[str, Image.Image] = {}
    A = _gray_contrast(_upscale(img))
    if "A" in names:
        out["A"] = A.convert("RGB")
    if "B" in names:
        d = Image.fromarray(cv2.bilateralFilter(np.asarray(A), 5, 40, 5)) if cv2 is not None else A.filter(ImageFilter.MedianFilter(3))
        out["B"] = d.filter(ImageFilter.UnsharpMask(radius=2, percent=140, threshold=2)).convert("RGB")
    if "C" in names and cv2 is not None:
        bs = max(15, (min(A.size) // 14) | 1)
        t = cv2.adaptiveThreshold(np.asarray(A), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, bs, 16)
        out["C"] = Image.fromarray(cv2.medianBlur(t, 3)).convert("RGB")
    return out


def find_qr_box(img: Image.Image):
    """(x1,y1,x2,y2) of the QR code in `img`, or None. The QR / number column is excluded when looking for address text,
    and its position (right-hand side on an upright back) is a weak orientation cue."""
    if cv2 is None:
        return None
    try:
        g = cv2.cvtColor(_to_bgr(_upscale(img, 900, 1600)), cv2.COLOR_BGR2GRAY)
        s = g.shape[1] / img.width
        ok, pts = cv2.QRCodeDetector().detect(g)
        if ok and pts is not None:
            p = pts.reshape(-1, 2) / s
            return float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max())
    except Exception:
        pass
    return None


def crop_relative(img: Image.Image, box, pad: float = 0.0) -> Image.Image:
    """Crop with pixel box (x1,y1,x2,y2), clamped to the image, with optional relative padding."""
    x1, y1, x2, y2 = box
    px, py = pad * img.width, pad * img.height
    x1, y1, x2, y2 = max(0, int(x1 - px)), max(0, int(y1 - py)), min(img.width, int(x2 + px)), min(img.height, int(y2 + py))
    return img.crop((x1, y1, max(x1 + 1, x2), max(y1 + 1, y2)))
