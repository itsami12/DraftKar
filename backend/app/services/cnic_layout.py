"""CNIC back side: REGION DETECTION from OCR word boxes (stage 3 of the pipeline). Deterministic, no LLM.

    OCR words with coordinates (an UPRIGHT card)
      -> find_labels()       "موجودہ پتہ" / "مستقل پتہ" (tolerant of small OCR letter errors, never of unrelated text)
      -> extract_regions()   for each label: the words to its LEFT on the same row (Urdu is right-to-left) and the rows
                             BELOW it, stopping at the next label, a large vertical gap, a non-Urdu row (signature,
                             "Registrar General of Pakistan"), the QR / number column or other printed card text.

Why geometry instead of text order: on the card the label sits at the right end of the first address row and the address
continues to its left, and the CNIC number / QR sit on the same rows. A plain text dump interleaves all of that, and a left-to-right
OCR pass emits the address BEFORE its label. Coordinates make the association explicit.
All coordinates are RELATIVE (0..1) of the image the words were read from; `size` converts them to pixels so tolerances
are isotropic.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from app.services.cnic import _CNIC, _norm_map, _prep

_PUNCT = re.compile(r"[\s:：;؛,،.\-–—_/|\\()\[\]{}'\"*«»]+")
CUR1, PER1, ADDR = "موجوده", "مستقل", "پته"
_ADDR_ALT = {"پته", "پتا", "پت", "پتة"}
_URDU = re.compile(r"[\u0600-\u06FF]")
_LATIN = re.compile(r"[A-Za-z]")
# printed card text that is never part of an address (instruction under the card, registrar / signature caption, barcode caption)
_STOP_WORDS = {"گمشده", "کارد", "ملنے", "قریبي", "لير", "ليتر", "بكس", "ڈال", "دیں", "ديں", "رجسٹرار", "جنرل", "پاکستان"}
_STOP_LATIN = {"registrar", "general", "pakistan", "of", "signature", "holder", "national", "identity", "card"}
MAX_ROWS = 4


def _ed(a: str, b: str) -> int:
    """Levenshtein distance (short strings only)."""
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def norm_token(t: str) -> str:
    """Letters only, Urdu letter forms unified (ہ/ه, ی/ي, ک/ك), diacritics removed — for LABEL comparison only."""
    return _PUNCT.sub("", _norm_map(str(t or ""))[0])


@dataclass
class W:
    text: str
    x: float  # pixels
    y: float
    w: float
    h: float

    @property
    def cx(self): return self.x + self.w / 2
    @property
    def cy(self): return self.y + self.h / 2
    @property
    def x2(self): return self.x + self.w
    @property
    def y2(self): return self.y + self.h


@dataclass
class Label:
    kind: str                # "current" | "permanent"
    box: tuple               # (x1, y1, x2, y2) pixels
    words: list              # the W objects that form the label
    exact: bool              # both words matched with 0 edits (English labels count as exact)
    partial: bool = False    # only the first word (موجودہ / مستقل) was read


@dataclass
class Region:
    kind: str
    text: str
    box: tuple
    rows: int
    label: Label
    words: list = field(default_factory=list)


def to_words(rel_words, size) -> list[W]:
    """OCR word dicts. Accepts pixel or relative boxes: `size` = (W, H) of the image the words refer to; values are used as-is
    (the caller supplies pixels of that image)."""
    out = []
    for d in rel_words or []:
        try:
            out.append(W(str(d["text"]), float(d["x"]), float(d["y"]), float(d["width"]), float(d["height"])))
        except (KeyError, TypeError, ValueError):
            continue
    return [w for w in out if w.text.strip() and w.w > 0 and w.h > 0]


def _median_h(words):
    hs = [w.h for w in words if _URDU.search(w.text) or _LATIN.search(w.text)]
    return statistics.median(hs) if hs else (statistics.median([w.h for w in words]) if words else 10.0)


def _row_groups(words, tol):
    rows = []
    for w in sorted(words, key=lambda w: w.cy):
        if rows and abs(w.cy - rows[-1]["cy"]) <= tol:
            rows[-1]["w"].append(w)
            rows[-1]["cy"] = sum(x.cy for x in rows[-1]["w"]) / len(rows[-1]["w"])
        else:
            rows.append({"cy": w.cy, "w": [w]})
    return rows


# ---------------------------------------------------------------- labels
def find_labels(words: list[W]) -> list[Label]:
    """Address labels in the word list, reading order independent (matching works on coordinates, not OCR sequence).
    Matching is deliberately strict: BOTH words must be within 1 edit of the printed label (e.g. one wrong letter), a single
    word is accepted only when it is an exact 'موجودہ' / 'مستقل' (flagged partial), and unrelated Urdu text never matches."""
    if not words:
        return []
    mh = _median_h(words)
    labels: list[Label] = []
    used: set[int] = set()
    for row in _row_groups(words, 0.9 * mh):
        rw = sorted(row["w"], key=lambda w: -w.cx)  # right-to-left
        toks = [norm_token(w.text) for w in rw]
        i = 0
        while i < len(rw):
            t = toks[i]
            nxt = toks[i + 1] if i + 1 < len(rw) else ""
            # merged single token "موجودہپتہ"
            for kind, first in (("current", CUR1), ("permanent", PER1)):
                if t and len(t) >= 6 and _ed(t, first + ADDR) <= 1 and id(rw[i]) not in used:
                    labels.append(Label(kind, (rw[i].x, rw[i].y, rw[i].x2, rw[i].y2), [rw[i]], exact=(t == first + ADDR)))
                    used.add(id(rw[i]))
                    break
            else:
                hit = None
                for kind, first in (("current", CUR1), ("permanent", PER1)):
                    d1 = _ed(t, first) if t else 9
                    if d1 > 1 or id(rw[i]) in used:
                        continue
                    d2 = min((_ed(nxt, a) for a in _ADDR_ALT), default=9) if nxt else 9
                    if d2 <= 1 and nxt and len(nxt) >= 2:
                        pair = [rw[i], rw[i + 1]]
                        hit = Label(kind, (min(p.x for p in pair), min(p.y for p in pair), max(p.x2 for p in pair), max(p.y2 for p in pair)),
                                    pair, exact=(d1 == 0 and d2 == 0))
                    elif d1 == 0:  # lone, exactly-read first word; the "پتہ" part was lost or merged by the OCR
                        hit = Label(kind, (rw[i].x, rw[i].y, rw[i].x2, rw[i].y2), [rw[i]], exact=False, partial=True)
                    if hit:
                        break
                if hit:
                    labels.append(hit)
                    used.update(id(w) for w in hit.words)
                    i += len(hit.words) - 1
                else:
                    # English labels: "Present|Current|Permanent Address"
                    tl = rw[i].text.strip().lower().strip(":.")
                    if tl in ("present", "current", "permanent") and i + 1 < len(rw) and rw[i + 1].text.strip().lower().startswith("add"):
                        pair = [rw[i], rw[i + 1]]
                        labels.append(Label("permanent" if tl == "permanent" else "current",
                                            (min(p.x for p in pair), min(p.y for p in pair), max(p.x2 for p in pair), max(p.y2 for p in pair)), pair, exact=True))
                        used.update(id(w) for w in pair)
                        i += 1
            i += 1
    labels.sort(key=lambda l: ((l.box[1] + l.box[3]) / 2, -l.box[2]))
    return labels


# ---------------------------------------------------------------- text assembly
def _is_cnic_or_number(text: str) -> bool:
    p = _prep(text)
    return bool(_CNIC.search(p)) or bool(re.fullmatch(r"[\d\-\s]{9,}", p.strip())) or bool(re.fullmatch(r"\d{4,}", re.sub(r"[^\d]", "", p)) and len(re.sub(r"[^\d]", "", p)) >= 9)


def _scrub_numbers(words: list[W]) -> list[W]:
    """If OCR returns a line-level 'word' that holds Urdu address text AND the CNIC number printed on the same row, remove only the
    number (the whole row used to be discarded). Pure numbers are left for the existing number filter."""
    out = []
    for w in words:
        if _CNIC.search(w.text) and _URDU.search(w.text):
            rest = " ".join(_CNIC.sub(" ", w.text).split())
            if _URDU.search(rest):
                w = W(rest, w.x, w.y, w.w, w.h)
        out.append(w)
    return out


def _has_latin_digit(t: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9]", t)) and not _URDU.search(t)


def join_rtl(words: list[W]) -> str:
    """One row, right-to-left. Runs of Latin/digit tokens (house numbers, "B-II-8-S-33") read left-to-right inside the run."""
    ws = sorted(words, key=lambda w: -w.cx)
    out, run = [], []
    for w in ws + [None]:
        if w is not None and _has_latin_digit(w.text):
            run.append(w.text)
            continue
        out.extend(reversed(run))
        run = []
        if w is not None:
            out.append(w.text)
    return " ".join(t.strip() for t in out if t.strip())


def _urdu_dominant(words) -> bool:
    txt = " ".join(w.text for w in words)
    u, l = len(_URDU.findall(txt)), len(_LATIN.findall(txt))
    return u > 0 and u >= l


def _stop_row(words) -> bool:
    toks = [norm_token(w.text) for w in words]
    if sum(1 for t in toks if t in _STOP_WORDS) >= 2:
        return True
    return any(w.text.strip().lower().strip(".,:") in _STOP_LATIN for w in words) and not _urdu_dominant(words)


def extract_regions(words: list[W], size: tuple, qr_box=None) -> dict:
    """-> {'labels': [Label], 'regions': {'current': Region|None, 'permanent': Region|None}, 'ambiguous': bool}
    `size` = (width, height) in pixels of the image the words refer to; `qr_box` = (x1,y1,x2,y2) pixels or None."""
    Wd, Ht = size
    words = _scrub_numbers(words)
    words = [w for w in words if not (qr_box and qr_box[0] - 4 <= w.cx <= qr_box[2] + 4 and qr_box[1] - 4 <= w.cy <= qr_box[3] + 4)]
    labels = find_labels(words)
    res = {"current": None, "permanent": None}
    if not labels:
        return {"labels": [], "regions": res, "ambiguous": False}
    mh = _median_h(words)
    label_ids = {id(w) for l in labels for w in l.words}
    kinds = [l.kind for l in labels]
    # the same label twice (e.g. English + Urdu, or both OCR passes merged): keep the first occurrence of each kind per row block
    ambiguous = False
    for k, lab in enumerate(labels):
        if res[lab.kind] is not None:
            continue
        lcy = (lab.box[1] + lab.box[3]) / 2
        nxt = next((l for l in labels[k + 1:] if (l.box[1] + l.box[3]) / 2 - lcy > 0.9 * mh and l.kind != lab.kind), None)
        nxt_cy = ((nxt.box[1] + nxt.box[3]) / 2) if nxt else None
        # same-row neighbour of a different kind: label order on the row decides nothing -> ambiguous, never guessed
        if any(l is not lab and l.kind != lab.kind and abs((l.box[1] + l.box[3]) / 2 - lcy) <= 0.6 * mh for l in labels):
            ambiguous = True
            continue
        right_limit = lab.box[2] + 0.12 * Wd  # address column: nothing to the right of its label (CNIC number / QR live there)
        picked: list[W] = []
        # row 0: same visual row as the label, to its LEFT
        row0 = [w for w in words if id(w) not in label_ids and abs(w.cy - lcy) <= 0.95 * mh and w.cx < lab.box[0] + 0.15 * (lab.box[2] - lab.box[0])
                and not _is_cnic_or_number(w.text)]
        if row0:
            picked.append(join_rtl(row0))
        used = list(row0)
        # rows below
        rest = [w for w in words if id(w) not in label_ids and w.cy > lcy + 0.95 * mh and w.cx < right_limit and not _is_cnic_or_number(w.text)
                and (nxt_cy is None or w.cy < nxt_cy - 0.9 * mh)]
        rows = _row_groups(rest, 0.6 * mh)
        prev_cy, pitch, n = (sum(w.cy for w in row0) / len(row0) if row0 else lcy), 1.6 * mh, 0
        for r in rows:
            if n >= MAX_ROWS - 1 or r["cy"] - prev_cy > 2.2 * pitch:
                break
            if _stop_row(r["w"]) or not _urdu_dominant(r["w"]):
                break
            picked.append(join_rtl(r["w"]))
            used += r["w"]
            pitch = max(1.3 * mh, r["cy"] - prev_cy)
            prev_cy, n = r["cy"], n + 1
        text = " ".join(picked).strip()
        if text:
            box = (min(w.x for w in used + lab.words), min(w.y for w in used + lab.words), max(w.x2 for w in used + lab.words), max(w.y2 for w in used + lab.words))
            res[lab.kind] = Region(lab.kind, text, box, len(picked), lab, used)
    return {"labels": labels, "regions": res, "ambiguous": ambiguous and not any(res.values())}
