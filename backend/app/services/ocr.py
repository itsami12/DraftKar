"""OCR.Space adapter. Only the backend talks to OCR.Space; the API key never leaves the server."""
import logging
import httpx
from app.config.settings import settings

log = logging.getLogger("draftkar.ocr")
URL = "https://api.ocr.space/parse/image"


class OCRError(Exception):
    pass


async def _post(jpeg: bytes, language: str = "eng", engine: str = "2", detect_orientation: bool = True, is_table: bool = False) -> dict:
    if not settings.OCR_SPACE_API_KEY:
        raise OCRError("OCR key missing")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(URL, headers={"apikey": settings.OCR_SPACE_API_KEY},
                              files={"file": ("stamp.jpg", jpeg, "image/jpeg")},
                              data={"isOverlayRequired": "true", "language": language, "OCREngine": engine,
                                    "scale": "true", "detectOrientation": "true" if detect_orientation else "false",
                                    **({"isTable": "true"} if is_table else {})})
        r.raise_for_status()
        return r.json()


def normalize(resp: dict, width: int, height: int) -> dict:
    """OCR.Space response -> {text, regions[{text,x,y,width,height}], image{width,height}} (pixels of the image sent)."""
    try:
        if resp.get("IsErroredOnProcessing") or not resp.get("ParsedResults"):
            raise OCRError("OCR.Space reported an error")
        pr = resp["ParsedResults"][0]
        regions, all_words = [], []
        for line in (pr.get("TextOverlay") or {}).get("Lines") or []:
            words = line.get("Words") or []
            if not words:
                continue
            x1 = min(float(w["Left"]) for w in words)
            y1 = min(float(w["Top"]) for w in words)
            x2 = max(float(w["Left"]) + float(w["Width"]) for w in words)
            y2 = max(float(w["Top"]) + float(w["Height"]) for w in words)
            txt = line.get("LineText") or " ".join(str(w.get("WordText", "")) for w in words)
            regions.append({"text": str(txt), "x": round(x1), "y": round(y1), "width": round(x2 - x1), "height": round(y2 - y1)})
            for w in words:  # word boxes drive the CNIC back-side layout parser (label -> address region)
                all_words.append({"text": str(w.get("WordText", "")), "x": float(w["Left"]), "y": float(w["Top"]),
                                  "width": float(w["Width"]), "height": float(w["Height"])})
        return {"text": str(pr.get("ParsedText") or ""), "regions": regions, "words": all_words,
                "orientation": pr.get("TextOrientation"), "image": {"width": width, "height": height}}
    except OCRError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise OCRError("malformed OCR response") from e


def suggest_placement(regions: list, height: int) -> dict:
    """Heuristic: start the text below printed header text found in the top 40% of the sheet."""
    top = 0.0
    for r in regions:
        bottom = (r["y"] + r["height"]) / height
        if bottom < 0.4:
            top = max(top, bottom)
    return {"x": 0.1, "y": round(min(max(top + 0.03, 0.18), 0.45), 3), "width": 0.8, "font_scale": 1.0}


async def read_text(jpeg: bytes, width: int, height: int, language: str = "eng", engine: str = "2") -> str:
    """Raw OCR text only (used for CNIC reading). Reuses the same OCR.Space call/normalizer.
    `language`/`engine` are OCR.Space parameters (same provider): the CNIC back side is read once as English (Latin labels, digits)
    and once with an Arabic-script language so the Urdu labels/addresses have a chance to be read."""
    try:
        return normalize(await _post(jpeg, language, engine), width, height)["text"]
    except OCRError:
        raise
    except Exception as e:
        log.warning("OCR.Space call failed: %s", type(e).__name__)
        raise OCRError("OCR request failed") from e


async def read_layout(jpeg: bytes, width: int, height: int, language: str = "eng", engine: str = "2",
                      detect_orientation: bool = False, is_table: bool = False) -> dict:
    """OCR text + word boxes (pixels of the image sent). Used by the CNIC back pipeline, which rotates the image ITSELF and
    scores the result, so OCR.Space's own auto-rotate is off by default (it would hide which orientation was right)."""
    try:
        return normalize(await _post(jpeg, language, engine, detect_orientation, is_table), width, height)
    except OCRError:
        raise
    except Exception as e:
        log.warning("OCR.Space call failed: %s", type(e).__name__)
        raise OCRError("OCR request failed") from e


async def analyze(jpeg: bytes, width: int, height: int) -> dict:
    try:
        data = normalize(await _post(jpeg), width, height)
    except OCRError:
        raise
    except Exception as e:  # timeout, HTTP error, invalid JSON...
        log.warning("OCR.Space call failed: %s", type(e).__name__)
        raise OCRError("OCR request failed") from e
    data["suggested"] = suggest_placement(data["regions"], height)
    return data
