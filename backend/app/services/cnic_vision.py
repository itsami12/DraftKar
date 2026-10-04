"""CNIC extraction with a Groq vision model (replaces the old OCR.Space CNIC pipeline).

    FRONT + BACK image --(one labeled composite in ONE multimodal Groq request, no retries, no second pass)--> structured JSON --> Pydantic (CNICExtractedData)
  --> deterministic normalization / sanity checks --> canonical fields + EN/UR presentation --> reviewable profile --> user edits --> applied.

Rules this module enforces:
    * the model sees the images directly (no OCR text in between); both sides are combined into one labeled image;
  * the CNIC number is NEVER trusted as returned: it is re-validated by cnic.normalize_cnic (group order only, never digits);
  * anything unreadable is null - addresses are never guessed, derived from each other or from other fields;
  * Urdu stays Urdu (no translation / transliteration);
  * images exist only in memory for the duration of the request; no values, addresses or images are logged.
OCR.Space is NOT used here (it stays in app.services.ocr for stamp-paper analysis only).
"""
import base64, json, logging, re
from datetime import date
from typing import Optional

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.config.settings import settings
from app.services import cnic as cnic_svc
from PIL import Image, ImageEnhance, ImageFilter
from app.services.image import _jpeg

log = logging.getLogger("draftkar.cnic_vision")
URL = "https://api.groq.com/openai/v1/chat/completions"

ERR_RATE_LIMIT = "GROQ_RATE_LIMIT"
FRONT_KEYS = ("name", "father_or_husband_name", "cnic", "date_of_birth", "gender")
BACK_KEYS = ("current_address", "permanent_address")
KEYS = FRONT_KEYS + BACK_KEYS
# human-readable fields that get an English and an Urdu rendering for the review form / document (CNIC number and date never do)
TEXT_KEYS = ("name", "father_or_husband_name", "current_address", "permanent_address")
_MODEL_KEY = {"name": "full_name"}   # profile key -> key the model returns
MODEL_BASE = ("full_name", "father_or_husband_name", "cnic_number", "date_of_birth", "gender", "current_address", "permanent_address")
MODEL_VARIANTS = tuple(f"{_MODEL_KEY.get(k, k)}_{l}" for k in TEXT_KEYS for l in ("en", "ur"))
MODEL_KEYS = MODEL_BASE + MODEL_VARIANTS

MSG_PARTIAL = "Could not confidently extract some information from the CNIC. Please review the highlighted fields or enter them manually."
MSG_FAILED = "We couldn't read the CNIC right now. Please try again, upload clearer images, or enter the information manually."
MSG_UNREADABLE = "Could not confidently read the CNIC. Please upload clearer images or enter the information manually."
MSG_RATE_LIMIT = "Groq is temporarily rate-limited. Please wait a moment and try again."
MSG_NEED_FRONT = "Please upload the front side of the CNIC."
MSG_NEED_BACK = "Please upload the back side of the CNIC."
VERIFY_CNIC = "Please verify CNIC number"
NO_CURRENT = "Current address could not be confidently extracted."
NO_PERMANENT = "Permanent address could not be confidently extracted."

PROMPT = """You are extracting information from a Pakistani CNIC.

The single image contains two labeled panels: FRONT SIDE on top and BACK SIDE below it. Read both panels.

Extract only information that is visibly present in the images.

Return the following fields:

- full_name
- father_or_husband_name
- cnic_number
- date_of_birth
- gender
- current_address
- permanent_address

The back side contains two address sections, written in Urdu Nastaliq script.

موجودہ پتہ = Current Address
مستقل پتہ = Permanent Address

On Pakistani CNICs, the Current Address section is above the Permanent Address section.

Do not swap these fields. Use the printed labels. Never copy one address into the other field.

Preserve Urdu names and addresses exactly as printed when they appear in Urdu.

Do not translate Urdu addresses unless explicitly requested.

Do not correct spelling, standardize names, or replace a place with a more familiar place. For example, if the card says جہلم/Jhelum, never change it to لاہور/Lahore. Copy every visible name, town, district, and address word literally from the card. If any address word or character is not readable, return that address as null; never guess, correct, or replace a word.

Do not invent, infer, or hallucinate missing information.

For name, father name, CNIC number, date of birth and gender: if a field cannot be read confidently, return null.

For the two addresses: transcribe only text that is clearly printed after the label. Include house number, street, locality, city/district exactly as printed. Return null if the address is not fully readable. Never return just the label.

The CNIC must be returned in canonical format:

XXXXX-XXXXXXX-X

Do not reverse individual digits.

If the visual RTL layout makes the CNIC appear as:

0-9876543-35202

interpret the three numeric groups correctly and return:

35202-9876543-0

The seven fields above are what is PRINTED on the card, exactly as printed. In addition, fill these rendering fields so the application can show the same person in both languages:

- full_name_en, full_name_ur
- father_or_husband_name_en, father_or_husband_name_ur
- current_address_en, current_address_ur
- permanent_address_en, permanent_address_ur

Rules for the rendering fields:
- Personal names are TRANSLITERATED into the other script (Naeem Tahir -> نعیم طاہر, محمد حسین -> Muhammad Hussain). Never translate the meaning of a name and never change who the person is.
- Addresses are carried into the other language without changing any fact: keep every house number, street number, block and place name; do not add or drop details.
- The rendering in the script that is already printed on the card must be identical to the printed field.
- Never put the CNIC number or a date in a rendering field.
- If the printed field is null, both of its rendering fields are null.

Return structured JSON only: an object with exactly the fifteen fields above (seven printed + eight rendering); every value is a string or null."""

SCHEMA = {
    "name": "cnic_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {k: {"type": ["string", "null"]} for k in MODEL_KEYS},
        "required": list(MODEL_KEYS),
        "additionalProperties": False,
    },
}


# ---------- Pydantic model of what the vision model returns ----------
class CNICExtractedData(BaseModel):
    """Everything is nullable: reading a photo can fail. Extra keys are dropped. Non-string values never get through."""
    model_config = ConfigDict(extra="ignore")
    full_name: Optional[str] = None
    father_or_husband_name: Optional[str] = None
    cnic_number: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    current_address: Optional[str] = None
    permanent_address: Optional[str] = None
    # renderings in the other script (transliterated names, carried-over addresses); never trusted without the checks in build_presentation
    full_name_en: Optional[str] = None
    full_name_ur: Optional[str] = None
    father_or_husband_name_en: Optional[str] = None
    father_or_husband_name_ur: Optional[str] = None
    current_address_en: Optional[str] = None
    current_address_ur: Optional[str] = None
    permanent_address_en: Optional[str] = None
    permanent_address_ur: Optional[str] = None

    @field_validator("*", mode="before")
    @classmethod
    def _clean(cls, v):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            v = str(v)
        if not isinstance(v, str):
            return None
        v = re.sub(r"\s+", " ", v).strip()
        return None if v.lower() in {"", "null", "none", "n/a", "na", "unknown", "not visible", "unreadable", "-"} else v


# ---------- deterministic checks ----------
_DIG = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_DATE = re.compile(r"(?<!\d)(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4})(?!\d)")
_LABEL_ONLY = re.compile(r"^[\s:：;\-–—]*(?:موجود\S{0,4}|مستق\S{0,3})?(?:\s*پت\S{0,2})?[\s:：;\-–—]*$|^(?:current|present|permanent)?\s*address\s*:?$", re.I)
_GENDER = {"m": "Male", "male": "Male", "f": "Female", "female": "Female", "x": "Transgender", "t": "Transgender", "transgender": "Transgender"}


def _name(v):
    return v if v and not re.search(r"\d", v.translate(_DIG)) and re.search(r"[^\W\d_]", v) else None


def _dob(v):
    """Returns (DD-MM-YYYY or None, exact). Unparseable / impossible dates -> None so they are re-entered, never guessed."""
    if not v:
        return None
    m = _DATE.search(v.translate(_DIG))
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    try:
        dt = date(y, mo, d)
    except ValueError:
        return None
    return f"{d:02d}-{mo:02d}-{y}" if 1900 <= y <= date.today().year and dt <= date.today() else None


def _gender(v):
    return _GENDER.get((v or "").strip().lower().strip("."), v) if v else None


def _address(v, cnic=None, names=()):
    """Reject values that cannot be an address: label only, no letters, the person's own name, or a CNIC number."""
    if not v or len(v) < 6 or _LABEL_ONLY.match(v) or not re.search(r"[^\W\d_]", v):
        return None
    if v in names or cnic_svc.normalize_cnic(v):
        return None
    return cnic_svc.fix_reversed_cnics_in_text(v)


def validate_extracted(data: CNICExtractedData):
    """CNICExtractedData -> (fields, confidence, extra warnings) using the profile key names the frontend uses.
    The CNIC number is accepted only if it normalizes deterministically; otherwise it is null and flagged."""
    warns, conf = [], {}
    cnic = cnic_svc.normalize_cnic(data.cnic_number) if data.cnic_number else None
    if data.cnic_number and not cnic:
        warns.append(VERIFY_CNIC)
    name, father = _name(data.full_name), _name(data.father_or_husband_name)
    dob = _dob(data.date_of_birth)
    names = tuple(x for x in (name, father) if x)
    cur, perm = _address(data.current_address, cnic, names), _address(data.permanent_address, cnic, names)
    fields = {"name": name, "father_or_husband_name": father, "cnic": cnic, "date_of_birth": dob,
              "gender": _gender(data.gender), "current_address": cur, "permanent_address": perm}
    for k, v in fields.items():
        conf[k] = "high" if v else None
    if data.date_of_birth and not dob:
        warns.append("The date of birth could not be read reliably - please enter it manually.")
    if cur and perm and cur == perm:  # legitimate when someone lives at their permanent address, but also what a confused read looks like
        conf["current_address"] = conf["permanent_address"] = "medium"
    return fields, conf, warns


# ---------- EN / UR presentation (deterministic checks on top of the model's renderings; no extra AI call) ----------
_ARABIC = re.compile(r"[\u0600-\u06FF]")
_GENDER_UR = {"Male": "مرد", "Female": "خاتون", "Transgender": "خواجہ سرا"}


def _is_urdu(v):
    return bool(v and _ARABIC.search(v))


def _digits(v):
    return sorted(re.findall(r"\d+", v.translate(_DIG)))


def _variant(canonical, candidate, want_urdu, is_address):
    """The canonical value is what is printed on the card. A rendering is accepted only if it is in the right script, is not the
    CNIC number, and (addresses) keeps every house/street/block number unchanged. Otherwise None (the UI then shows the printed value)."""
    if not canonical:
        return None
    if _is_urdu(canonical) == want_urdu:
        return canonical               # already in the requested script: preserved exactly as printed, never rewritten
    if not candidate or _is_urdu(candidate) != want_urdu or not re.search(r"[^\W\d_]", candidate):
        return None
    if cnic_svc.normalize_cnic(candidate) or _digits(candidate) != _digits(canonical):
        return None
    return cnic_svc.fix_reversed_cnics_in_text(candidate) if is_address else candidate


def build_presentation(fields, data: CNICExtractedData):
    """canonical fields (as printed) -> {"en": {...}, "ur": {...}} for name, father, both addresses and gender.
    CNIC number and date of birth are language-independent and are NOT in here. Missing values stay None (never invented)."""
    pres = {"en": {}, "ur": {}}
    for k in TEXT_KEYS:
        mk = _MODEL_KEY.get(k, k)
        for lang in ("en", "ur"):
            pres[lang][k] = _variant(fields[k], getattr(data, f"{mk}_{lang}"), lang == "ur", k in BACK_KEYS)
    g = fields["gender"]
    pres["en"]["gender"] = g
    pres["ur"]["gender"] = _GENDER_UR.get(g, g) if g else None
    return pres


# ---------- Groq request ----------
class VisionError(Exception):
    pass


class RateLimited(VisionError):
    """Groq HTTP 429. Never retried automatically."""
    def __init__(self, retry_after=None):
        super().__init__("http 429 rate_limit_exceeded")
        self.retry_after = retry_after


def prepare_cnic_composite(front_img, back_img):
    """Create one labeled image while reserving most pixels for the back-side addresses."""
    width = 1600
    padding, label_height, gap = 24, 44, 20

    def card_panel(source, max_width):
        panel = source.convert("RGB").copy()
        if panel.height > panel.width:
            panel = panel.rotate(90, expand=True)
        panel.thumbnail((max_width, 700), Image.LANCZOS)
        return panel

    front = card_panel(front_img, (width - 3 * padding) // 2)
    back = card_panel(back_img, (width - 3 * padding) // 2)
    address = back_img.convert("RGB").copy()
    address = address.crop((0, 0, address.width, max(1, int(address.height * 0.84))))
    address = ImageEnhance.Contrast(address).enhance(1.25)
    address = address.filter(ImageFilter.UnsharpMask(radius=1.2, percent=130, threshold=3))
    address.thumbnail((width - 2 * padding, 1050), Image.LANCZOS)

    top_height = label_height + max(front.height, back.height)
    height = padding + top_height + gap + label_height + address.height + padding
    canvas = Image.new("RGB", (width, height), "white")
    from PIL import ImageDraw
    draw = ImageDraw.Draw(canvas)
    y = padding
    for x, label, panel in ((padding, "FRONT SIDE", front), (width // 2 + padding // 2, "BACK SIDE", back)):
        draw.rectangle((x, y, x + panel.width, y + label_height), fill=(20, 55, 72))
        draw.text((x + 12, y + 12), label, fill="white")
        canvas.paste(panel, (x, y + label_height))
    y += top_height + gap
    draw.rectangle((padding, y, width - padding, y + label_height), fill=(20, 55, 72))
    draw.text((padding + 12, y + 12), "BACK ADDRESS DETAIL", fill="white")
    canvas.paste(address, (padding, y + label_height))
    data, _ = _jpeg(canvas, width, 3_000_000)
    return data


def _data_url(jpeg):
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()


def _build_payload(composite_jpeg, structured=True):
    p = {"model": settings.GROQ_VISION_MODEL, "temperature": 0, "max_completion_tokens": 4000,
         "messages": [{"role": "user", "content": [{"type": "text", "text": PROMPT}] +
                       [{"type": "image_url", "image_url": {"url": _data_url(composite_jpeg)}}]}],
         "response_format": {"type": "json_schema", "json_schema": SCHEMA} if structured else {"type": "json_object"}}
    if getattr(settings, "GROQ_VISION_REASONING_EFFORT", ""):
        p["reasoning_effort"] = settings.GROQ_VISION_REASONING_EFFORT
    if getattr(settings, "GROQ_VISION_REASONING_FORMAT", ""):
        p["reasoning_format"] = settings.GROQ_VISION_REASONING_FORMAT
    return p


def _err_code(r):
    """Groq's error code/type only (e.g. 'rate_limit_exceeded'); never the message, which can echo model output."""
    try:
        e = r.json().get("error", {})
        return str(e.get("code") or e.get("type") or "")[:60]
    except Exception:
        return ""


def _failed_generation(r):
    """On HTTP 400 json_validate_failed Groq returns the text the model produced in error.failed_generation. It is usually the right
    JSON wrapped in <think>...</think>, a code fence or a trailing sentence - parse_model_json() can read that, so it is used locally
    instead of sending a second request. Returns the text or None. Never logged."""
    try:
        e = r.json().get("error", {})
        if (e.get("code") or e.get("type")) == "json_validate_failed" and isinstance(e.get("failed_generation"), str):
            return e["failed_generation"]
    except Exception:
        pass
    return None


def _shape(text):
    """Content-free description of a model output, for diagnosing failures without logging card data."""
    t = (text or "").strip()
    return f"len={len(t)} think={'<think' in t.lower()} fence={'```' in t} starts_brace={t[:1] == '{'} ends_brace={t[-1:] == '}'}"


def _retry_after(r):
    try:
        return max(1, min(int(float(r.headers.get("retry-after", ""))), 3600))
    except (TypeError, ValueError):
        return None


async def _call_groq(composite_jpeg):
    """EXACTLY ONE HTTP request to Groq per call - no retry, no fallback request, no second pass. HTTP 429 raises RateLimited at once
    (the user retries manually); every other failure raises VisionError. Returns the raw message content. Never logs the content."""
    if not settings.GROQ_VISION_API_KEY:
        raise VisionError("vision key missing")
    headers = {"Authorization": f"Bearer {settings.GROQ_VISION_API_KEY}"}
    payload = _build_payload(composite_jpeg, getattr(settings, "GROQ_VISION_STRUCTURED", True))
    try:
        async with httpx.AsyncClient(timeout=settings.GROQ_VISION_TIMEOUT) as c:
            r = await c.post(URL, headers=headers, json=payload)
    except httpx.TimeoutException as e:
        raise VisionError("timeout") from e
    except Exception as e:
        raise VisionError(type(e).__name__) from e
    if r.status_code == 429:
        raise RateLimited(_retry_after(r))
    if r.status_code == 400 and _failed_generation(r) is not None:
        fg = _failed_generation(r)
        log.warning("Groq rejected the model's JSON (json_validate_failed; %s); parsing it locally, no new request", _shape(fg))
        return fg
    if r.status_code >= 400:
        raise VisionError(f"http {r.status_code} {_err_code(r)}".strip())
    try:
        return r.json()["choices"][0]["message"]["content"] or ""
    except Exception as e:
        raise VisionError("bad response") from e


_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def parse_model_json(content: str) -> CNICExtractedData:
    """Raw model text -> CNICExtractedData. Tolerates <think> blocks and code fences; anything else raises VisionError."""
    text = _THINK.sub("", content or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.I | re.M).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        try:
            data = json.loads(text[a:b + 1]) if 0 <= a < b else None
        except json.JSONDecodeError:
            data = None
    if not isinstance(data, dict):
        raise VisionError("invalid json")
    try:
        return CNICExtractedData.model_validate(data)
    except ValidationError as e:
        raise VisionError("validation") from e


# ---------- public entry point ----------
def _failed(message=MSG_FAILED, error_code=None, retry_after=None):
    out = {"ok": False, "success": False, "message": message, "warnings": [message], "status": {"front": "failed", "back": "failed"},
           "fields": {k: None for k in KEYS}, "confidence": {k: None for k in KEYS}, "needs_review": list(KEYS),
           "presentation": {"en": {k: None for k in TEXT_KEYS + ("gender",)}, "ur": {k: None for k in TEXT_KEYS + ("gender",)}}}
    if error_code:
        out["error_code"] = error_code
    if retry_after:
        out["retry_after"] = retry_after
    return out


async def extract_cnic(front_img, back_img):
    """front_img / back_img: PIL images (already validated by read_upload). Returns the profile dict the frontend reviews.
    ONE Groq request per call. A failed or partial read is a normal result (ok=False / null fields), never an exception:
    manual entry always works. Logs contain no CNIC number, name or address."""
    log.info("CNIC extraction started")
    try:
        log.info("Combining front + back and sending one image to Groq Vision (1 request)")
        content = await _call_groq(prepare_cnic_composite(front_img, back_img))
        log.info("Groq Vision response received")
        try:
            data = parse_model_json(content)
        except VisionError:
            log.warning("model output not usable as JSON (%s)", _shape(content))
            raise
    except RateLimited as e:
        log.warning("CNIC extraction stopped: Groq rate limit (HTTP 429), not retrying")
        return _failed(MSG_RATE_LIMIT, ERR_RATE_LIMIT, e.retry_after)
    except VisionError as e:
        log.warning("CNIC vision extraction failed: %s", e)
        return _failed()
    except Exception as e:  # type only: tracebacks/messages could echo image-derived values
        log.error("CNIC vision extraction crashed: %s", type(e).__name__)
        return _failed()
    fields, conf, warns = validate_extracted(data)
    presentation = build_presentation(fields, data)
    front_ok, back_ok = any(fields[k] for k in FRONT_KEYS), any(fields[k] for k in BACK_KEYS)
    status = {"front": "ok" if front_ok else "unreadable", "back": "ok" if back_ok else "unreadable"}
    if back_ok:
        if not fields["current_address"]:
            warns.append(NO_CURRENT)
        if not fields["permanent_address"]:
            warns.append(NO_PERMANENT)
    review = [k for k in KEYS if fields[k] is None or conf[k] in ("medium", "low")]
    ok = front_ok or back_ok
    if not ok:
        warns.insert(0, MSG_UNREADABLE)
    elif review:
        warns.insert(0, MSG_PARTIAL)
    log.info("CNIC extraction completed: %d/%d fields read", sum(1 for k in KEYS if fields[k]), len(KEYS))
    return {"ok": ok, "success": ok, "message": warns[0] if warns else "", "warnings": warns, "status": status,
            "fields": fields, "confidence": conf, "needs_review": review, "presentation": presentation}