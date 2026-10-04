"""Deterministic CNIC number rules (no OCR, no model). Used by the vision pipeline (cnic_vision.py), document generation and tests.

Canonical Pakistani CNIC: XXXXX-XXXXXXX-X, always stored/rendered left-to-right (even inside Urdu documents).
The RTL group-order reversal 1-7-5 (e.g. 0-9876543-35202) is reordered to 5-7-1; digits INSIDE a group are never reversed;
anything ambiguous -> None (manual verification).
"""
import re

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")  # Urdu/Arabic-Indic -> ASCII
_FORMAT_CHARS = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_DASHES = re.compile("[\u2010-\u2015\u2212\ufe63\uff0d_]")
# 5-7-1 (canonical) or 1-7-5 (RTL group-order reversal). Group LENGTHS decide; digits inside a group are never touched.
_CNIC = re.compile(r"(?<!\d)(\d{5}|\d)[-\s]+(\d{7})[-\s]+(\d{5}|\d)(?!\d)")
_CANON = re.compile(r"[1-7]\d{4}-\d{7}-\d")  # leading digit = province code 1-7


def _prep(raw) -> str:
    return _DASHES.sub("-", _FORMAT_CHARS.sub("", str(raw or "")).translate(_DIGITS))


def validate_cnic(value) -> bool:
    """True only for the canonical XXXXX-XXXXXXX-X form (leading digit 1-7)."""
    return isinstance(value, str) and _CANON.fullmatch(value) is not None


def normalize_cnic(raw):
    """Canonical 'XXXXX-XXXXXXX-X' or None.
    - 5-7-1 groups are preserved as-is.
    - 1-7-5 groups (RTL group-order reversal) are reordered to 5-7-1; digits inside groups are NOT reversed.
    - anything else (wrong lengths, 13 unseparated digits, several different numbers) is ambiguous -> None."""
    found = set()
    for m in _CNIC.finditer(_prep(raw)):
        a, b, c = m.groups()
        cand = f"{a}-{b}-{c}" if (len(a), len(c)) == (5, 1) else f"{c}-{b}-{a}" if (len(a), len(c)) == (1, 5) else None
        if cand and validate_cnic(cand):
            found.add(cand)
    return found.pop() if len(found) == 1 else None


_REVERSED_IN_TEXT = re.compile(r"(?<![\d-])(\d)[-\u2010-\u2015](\d{7})[-\u2010-\u2015](\d{5})(?![\d-])")


def fix_reversed_cnics_in_text(text):
    """Data-layer guard for model-written prose: a CNIC that appears with RTL-reversed groups (1-7-5) is rewritten to 5-7-1.
    Digits inside groups are untouched; anything that is not a clear 1-7-5 pattern is left exactly as written."""
    def fix(m):
        cand = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        return cand if validate_cnic(cand) else m.group(0)
    return _REVERSED_IN_TEXT.sub(fix, text) if isinstance(text, str) else text
