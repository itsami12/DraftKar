"""CNIC BACK pipeline orchestration.

    image validation (image.read_upload)           -> app.main
    orientation candidates + card isolation        -> cnic_image.orientation_candidates()
    detect_best_orientation()                      OCR-scored; never rotates blindly
    enhancement variants + full-image OCR          run_cnic_ocr()
    address-region extraction (label + geometry)   cnic_layout.extract_regions()
    targeted address-band OCR (bigger glyphs)      _targeted_pass()
    current / permanent address + confidence       extract_current_address() / extract_permanent_address()
    validation + user review                       cnic.extract_address_data() / combine_profile() / the review UI

OCR.Space is the only OCR provider; it is reached through an injectable `ocr_call` so the pipeline can be tested offline.
Nothing is stored. Identity values are never logged; the optional debug dict masks CNIC numbers.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Awaitable, Callable

from PIL import Image

from app.config.settings import settings
from app.services import cnic_image as ci
from app.services import cnic_layout as lay
from app.services import ocr
from app.services.cnic import _CNIC, _address_labels, _norm_addr, _prep, normalize_cnic, strip_card_text

log = logging.getLogger("draftkar.cnic.back")
_URDU = re.compile(r"[\u0600-\u06FF]")
_LAT = re.compile(r"[A-Za-z]")
_KEYWORDS_LATIN = ("registrar", "general", "pakistan")
_ADDR_WORDS = ("مکان", "گلی", "محلہ", "ضلع", "تحصیل", "ڈاکخانہ", "سٹریٹ", "نمبر", "ڈھوک", "گاؤں", "موضع", "شہر", "کالونی", "روڈ", "house", "street", "mohalla", "district", "tehsil")
ORIENT_MIN_SCORE = 20.0   # below this a candidate set is considered "nothing meaningful read"
OcrCall = Callable[..., Awaitable[dict]]


# ---------------------------------------------------------------- OCR plumbing
async def default_ocr_call(image: Image.Image, language: str = "eng", engine: str = "2", is_table: bool = False) -> dict:
    """OCR.Space on a PIL image -> {text, words:[{text,x,y,width,height}] (pixels of the image sent), image:{width,height}}."""
    from app.services.image import prepare_for_ocr
    jpeg, w, h = prepare_for_ocr(image)
    return await ocr.read_layout(jpeg, w, h, language, engine, detect_orientation=False, is_table=is_table)


def _scaled_words(res: dict, frame_size: tuple) -> list[lay.W]:
    """OCR words -> pixels of the (oriented) frame. Variants are uniform scales of the frame, so relative coordinates carry over."""
    sw, sh = res["image"]["width"], res["image"]["height"]
    fw, fh = frame_size
    conv = [{"text": d["text"], "x": d["x"] / sw * fw, "y": d["y"] / sh * fh, "width": d["width"] / sw * fw, "height": d["height"] / sh * fh}
            for d in res.get("words") or []]
    return lay.to_words(conv, frame_size)


# ---------------------------------------------------------------- orientation scoring
def score_text(text: str, qr_cue: float = 0.0) -> float:
    """How much meaningful CNIC-back text did this orientation produce? Sideways/upside-down text yields little, and what it
    yields is short fragments of junk characters."""
    t = text or ""
    p = _prep(t)
    s = 0.0
    if normalize_cnic(t):
        s += 30                                        # the printed CNIC number
    if _CNIC.search(p):
        s += 5
    low = t.lower()
    s += 10 * min(2, sum(1 for k in _KEYWORDS_LATIN if k in low))   # "Registrar General of Pakistan"
    if re.search(r"(?<!\d)\d{12}(?!\d)", re.sub(r"[\s-]", "", p)):
        s += 8                                         # the 12-digit number printed under the QR code
    s += min(25.0, len(_URDU.findall(t)) * 0.15)       # Urdu present
    labs = _address_labels(t)
    s += 25 * min(2, len(labs))                        # address labels
    s += 3 * min(6, sum(1 for k in _ADDR_WORDS if k in low or k in t))   # address vocabulary
    lines = [l for l in t.splitlines() if l.strip()]
    if lines:
        avg = sum(len(l.strip()) for l in lines) / len(lines)
        if avg < 3.0:
            s *= 0.4                                   # a column of 1-2 character lines = sideways text
        junk = len(re.findall(r"[^\w\s\-.,:/()]", t)) / max(1, len(t))
        if junk > 0.25:
            s *= 0.6
    return round(s + qr_cue, 1)


def _qr_cue(frame: Image.Image, source: str) -> float:
    box = ci.find_qr_box(frame)
    if not box:
        return 0.0
    cx = (box[0] + box[2]) / 2 / frame.width
    mag = 8.0 if source == "card" else 5.0
    return mag if cx > 0.58 else -mag if cx < 0.42 else 0.0   # an upright back has the QR on the right


async def _score_candidate(c: ci.Candidate, ocr_call: OcrCall, lang: str, engine: str) -> dict:
    small = ci.enhancement_variants(c.image, ("A",))["A"]
    if small.width > 1600:
        small = small.resize((1600, round(small.height * 1600 / small.width)), Image.LANCZOS)
    try:
        res = await ocr_call(small, lang, engine)
        text = res.get("text") or ""
    except ocr.OCRError:
        text = ""
    return {"label": c.label, "text": text, "score": score_text(text, _qr_cue(c.image, c.source))}


async def detect_best_orientation(cands: list[ci.Candidate], ocr_call: OcrCall, dbg: dict | None = None):
    """Try orientations, let OCR decide. Rounds (each only if the previous found nothing meaningful):
       1. card-crop candidates (upright / 180°) — or all four photo rotations when no card was found
       2. the full-photo rotations (safety net when the crop was wrong)
       3. an Arabic-script pass on the most promising candidates (when the Latin text is unreadable)
    -> (best Candidate, {label: score}, english_text_of_best)"""
    card = [c for c in cands if c.source == "card"]
    full = [c for c in cands if c.source == "full"]
    scores: dict[str, float] = {}
    texts: dict[str, str] = {}

    async def run(group, lang="eng", engine="2"):
        for r in await asyncio.gather(*[_score_candidate(c, ocr_call, lang, engine) for c in group]):
            if r["score"] > scores.get(r["label"], -1e9):
                scores[r["label"]], texts[r["label"]] = r["score"], r["text"]

    await run(card or full)
    if card and max(scores.values(), default=0) < ORIENT_MIN_SCORE:
        await run(full)
    if max(scores.values(), default=0) < ORIENT_MIN_SCORE and settings.OCR_BACK_URDU_LANGUAGE:
        top = sorted(cands, key=lambda c: -scores.get(c.label, 0))[:2 if card else 4]
        await run(top, settings.OCR_BACK_URDU_LANGUAGE, settings.OCR_BACK_URDU_ENGINE)
    order = {c.label: i for i, c in enumerate(cands)}
    best = max(cands, key=lambda c: (scores.get(c.label, -1e9), -order[c.label]))
    if dbg is not None:
        dbg["orientation"] = {"chosen": best.label, "rotation_ccw": best.rotation, "source": best.source, "scores": scores, **best.meta}
    return best, scores, texts.get(best.label, "")


# ---------------------------------------------------------------- region helpers
def _pick_variants() -> list[str]:
    v = [x.strip().upper() for x in settings.OCR_BACK_VARIANTS.split(",") if x.strip() in ("A", "B", "C", "a", "b", "c")]
    return v or ["A"]


def _lang() -> tuple[str, str]:
    return (settings.OCR_BACK_URDU_LANGUAGE or "eng", settings.OCR_BACK_URDU_ENGINE if settings.OCR_BACK_URDU_LANGUAGE else "2")


def _tokens(s: str) -> set:
    return set(re.findall(r"\w+", (s or "").lower()))


def _agree(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.5


def address_quality(text: str) -> bool:
    """Is this plausibly an address (and not OCR junk)? Conservative: a wrong 'maybe' is worse than an empty field."""
    t = " ".join((text or "").split())
    letters = len(_URDU.findall(t)) + len(_LAT.findall(t))
    if letters < 4:
        return False
    if len(re.findall(r"[^\w\s\-.,:/()،؛]", t)) / max(1, len(t)) > 0.25:
        return False
    toks = t.split()
    return len(toks) >= 2 or len(t) >= 6


def _mask(s: str) -> str:
    """Debug output only: hide CNIC numbers and any long digit run."""
    s = _CNIC.sub("[CNIC]", _prep(s or ""))
    return re.sub(r"\d{9,}", "[NUMBER]", s)


# ---------------------------------------------------------------- the two address extractors
def _from_passes(passes: list[dict], kind: str) -> list[dict]:
    """Candidate addresses of one kind from the full-image passes (each: {'source','region'})."""
    out = []
    for p in passes:
        r = (p.get("regions") or {}).get(kind)
        if r is not None and address_quality(strip_card_text(r.text)):
            out.append({"source": p["source"], "text": strip_card_text(r.text), "exact": r.label.exact, "partial": r.label.partial, "region": r})
    return out


def _decide(kind: str, full_cands: list[dict], band: dict | None) -> dict | None:
    """Pick one address for `kind` and grade it.
       high   = exact label, and two independent reads (full image + targeted crop, or two enhancement variants) agree
       medium = exact label, one usable read OR reads disagree (the larger-glyph targeted crop wins)
       low    = fuzzy / partial label, or very short text — flagged for review in the UI"""
    cands = ([band] if band else []) + full_cands
    if not cands:
        return None
    chosen = cands[0]
    agree = any(_agree(chosen["text"], o["text"]) for o in cands[1:])
    exact = chosen.get("exact", True) and not chosen.get("partial", False) and all(c.get("exact", True) for c in cands if c is chosen)
    short = len(chosen["text"].split()) < 2
    conf = "low" if (not exact or short) else ("high" if agree else "medium")
    if conf == "low" and agree and not short:
        conf = "medium"
    return {"text": chosen["text"], "confidence": conf, "source": chosen["source"]}


def prune_fragments(cands: dict) -> dict:
    """{'current': [cand...], 'permanent': [cand...]} -> same, minus any candidate whose text is a strict fragment of a candidate of the
    OTHER address (e.g. current = 'ضلع جہلم', the tail of the permanent address). Such a candidate was read from the wrong region."""
    def frag(c, others):
        n = _norm_addr(c["text"])
        return any(n and n != _norm_addr(o["text"]) and n in _norm_addr(o["text"]) for o in others)
    return {k: [c for c in v if not frag(c, cands.get("permanent" if k == "current" else "current", []))] for k, v in cands.items()}


def extract_current_address(passes, band=None):
    """Address printed under 'موجودہ پتہ' (Present/Current Address), or None."""
    return _decide("current", _from_passes(passes, "current"), band)


def extract_permanent_address(passes, band=None):
    """Address printed under 'مستقل پتہ' (Permanent Address), or None."""
    return _decide("permanent", _from_passes(passes, "permanent"), band)


def extract_address_regions(words: list[lay.W], size: tuple, qr_box=None) -> dict:
    """Layout extraction for one OCR pass (thin wrapper kept as a named pipeline stage)."""
    return lay.extract_regions(words, size, qr_box)


# ---------------------------------------------------------------- targeted address-band OCR
def _band_box(lab: lay.Label, region, labels, frame_size, qr_box, mh):
    W, H = frame_size
    cy = (lab.box[1] + lab.box[3]) / 2
    nxt = next((l for l in labels if (l.box[1] + l.box[3]) / 2 - cy > 0.9 * mh and l.kind != lab.kind), None)
    top = max(0, lab.box[1] - 0.9 * mh)
    bottom = (nxt.box[1] - 0.45 * mh) if nxt else min(H, (region.box[3] if region else lab.box[3]) + 2.4 * mh)
    right = min(W, lab.box[2] + 0.04 * W)
    if qr_box:
        right = min(right, max(qr_box[0] - 0.01 * W, lab.box[2]))   # keep the QR column out of the crop
    return (0, top, right, max(bottom, top + 2 * mh))


async def _targeted_pass(frame: Image.Image, enhanced: Image.Image, labels, regions, qr_box, mh, ocr_call, dbg) -> dict:
    """For each detected label, crop ONLY its address band from the enhanced image, upscale it and OCR again.
    Larger glyphs relative to the image make Nastaliq text noticeably easier to read. Returns {kind: candidate dict}."""
    lang, engine = _lang()
    out: dict = {}
    scale = enhanced.width / frame.width
    kinds = {}
    for lab in labels:
        kinds.setdefault(lab.kind, lab)

    async def one(kind, lab):
        box = _band_box(lab, regions.get(kind), labels, frame.size, qr_box, mh)
        crop = ci.crop_relative(enhanced, tuple(v * scale for v in box))
        crop = ci._upscale(crop, 1400, 2400)
        try:
            res = await ocr_call(crop, lang, engine)
        except ocr.OCRError:
            return kind, None, ""
        words = _scaled_words(res, crop.size)
        sub = lay.extract_regions(words, crop.size)
        r = sub["regions"].get(kind)
        if r is None:  # label unreadable at this scale: the band itself is defined by the label found in the full image
            ws = [w for w in words if not lay._is_cnic_or_number(w.text)]
            rows = [lay.join_rtl(g["w"]) for g in lay._row_groups(ws, 0.6 * lay._median_h(ws))] if ws else []
            txt = strip_card_text(" ".join(rows))
            return kind, ({"source": "band", "text": txt, "exact": False, "partial": True} if address_quality(txt) else None), res.get("text", "")
        rt = strip_card_text(r.text)
        return kind, ({"source": "band", "text": rt, "exact": r.label.exact, "partial": r.label.partial} if address_quality(rt) else None), res.get("text", "")

    for kind, cand, raw in await asyncio.gather(*[one(k, l) for k, l in kinds.items()]):
        if cand:
            out[kind] = cand
        dbg.setdefault("band_text", {})[kind] = _mask(raw)
    return out


# ---------------------------------------------------------------- main entry
async def run_cnic_ocr(img: Image.Image, ocr_call: OcrCall = default_ocr_call, want_debug: bool = False) -> dict:
    """BACK image -> {'frame': oriented card image (PIL), 'texts': [raw OCR texts], 'layout': {'current_address': {text, confidence, source}|absent, ...},
                      'ambiguous': bool, 'debug': dict}. Raises ocr.OCRError only if OCR never worked at all."""
    dbg: dict = {"steps": []}
    cands = ci.orientation_candidates(img)
    best, scores, eng_text = await detect_best_orientation(cands, ocr_call, dbg)
    frame = best.image
    log.info("cnic back: orientation=%s scores=%s", best.label, scores)
    variants = ci.enhancement_variants(frame, ("A", "B", "C"))
    qr_box = ci.find_qr_box(frame)
    lang, engine = _lang()
    texts = [eng_text] if eng_text.strip() else []
    passes: list[dict] = []
    ok_calls = 0

    async def full_pass(name: str, image: Image.Image):
        nonlocal ok_calls
        try:
            res = await ocr_call(image, lang, engine)
        except ocr.OCRError:
            return
        ok_calls += 1
        words = _scaled_words(res, frame.size)
        ex = extract_address_regions(words, frame.size, qr_box)
        passes.append({"source": f"full:{name}", "regions": ex["regions"], "labels": ex["labels"], "ambiguous": ex["ambiguous"], "words": words})
        texts.append(res.get("text") or "")
        dbg["steps"].append({"pass": name, "lang": lang, "labels": [(l.kind, l.exact, l.partial) for l in ex["labels"]], "raw_text": _mask(res.get("text") or "")})

    await asyncio.gather(*[full_pass(v, variants[v]) for v in _pick_variants() if v in variants])
    if not any(p["labels"] for p in passes):          # nothing label-like yet: try the remaining variants and the untouched card image
        extra = [(v, variants[v]) for v in ("A", "B", "C") if v in variants and v not in _pick_variants()] + [("orig", frame)]
        await asyncio.gather(*[full_pass(n, im) for n, im in extra])
    if ok_calls == 0 and not eng_text.strip():
        raise ocr.OCRError("no OCR pass succeeded")

    # targeted address-band OCR, driven by the label positions found above
    band: dict = {}
    anchor = max(passes, key=lambda p: (len({l.kind for l in p["labels"]}), len(p["labels"])), default=None)
    if settings.OCR_BACK_TARGETED and anchor and anchor["labels"]:
        mh = lay._median_h(anchor["words"])
        band = await _targeted_pass(frame, variants["A"], anchor["labels"], anchor["regions"], qr_box, mh, ocr_call, dbg)
    elif settings.OCR_BACK_TARGETED and not any(p["labels"] for p in passes) and ok_calls:
        # no label found anywhere: look at the address half of the card (left of the QR) at higher scale — labels are small print
        W, H = frame.size
        box = (0, 0, (qr_box[0] - 0.01 * W) if qr_box else 0.74 * W, 0.86 * H)
        crop = ci._upscale(ci.crop_relative(variants["A"], tuple(v * variants["A"].width / W for v in box)), 1600, 2600)
        try:
            res = await ocr_call(crop, lang, engine)
            words = _scaled_words(res, crop.size)
            ex = lay.extract_regions(words, crop.size)
            passes.append({"source": "region", "regions": ex["regions"], "labels": ex["labels"], "ambiguous": ex["ambiguous"], "words": words})
            texts.append(res.get("text") or "")
            dbg["steps"].append({"pass": "region", "labels": [(l.kind, l.exact, l.partial) for l in ex["labels"]], "raw_text": _mask(res.get("text") or "")})
        except ocr.OCRError:
            pass

    layout, amb = {}, any(p["ambiguous"] for p in passes)
    pool = {k: ([band[k]] if band.get(k) else []) + _from_passes(passes, k) for k in ("current", "permanent")}
    pool = prune_fragments(pool)   # a candidate that is only a piece of the other address is dropped; the next candidate (if any) is used
    for kind in ("current", "permanent"):
        c = pool[kind]
        r = _decide(kind, [x for x in c if x.get("source") != "band"], next((x for x in c if x.get("source") == "band"), None))
        if r:
            layout[f"{kind}_address"] = r
    dbg["address_regions"] = {k: _mask(v["text"]) if v else None for k, v in {"current": layout.get("current_address"), "permanent": layout.get("permanent_address")}.items()}
    dbg["confidence"] = {k: (v or {}).get("confidence") for k, v in {"current_address": layout.get("current_address"), "permanent_address": layout.get("permanent_address")}.items()}
    dbg["variants_used"] = sorted({s["pass"] for s in dbg["steps"]})
    dbg["qr_box_found"] = qr_box is not None
    return {"frame": frame, "texts": [t for t in texts if t and t.strip()], "layout": layout, "ambiguous": amb and not layout, "debug": dbg if want_debug else {}}
