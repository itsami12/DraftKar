"""Verify OCR.Space language=urd / OCREngine=3 on a REAL Pakistani CNIC back. HTTP 200 alone is not a pass.

    cd backend && OCR_SPACE_API_KEY=... python scripts/verify_urdu_ocr.py path/to/cnic_back.jpg [--lang urd] [--engine 3]

Prints the exact language/engine, any OCR.Space error, the raw Urdu text returned, and whether the labels
موجودہ / مستقل / پتہ are present. Nothing is stored. Sends the image to OCR.Space only.
"""
import argparse, asyncio, io, os, re, sys, unicodedata
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import httpx
from PIL import Image

URL = "https://api.ocr.space/parse/image"
URDU = re.compile(r"[\u0600-\u06FF]")


def norm(s):  # drop diacritics/tatweel, unify Arabic/Urdu letter variants so label matching is fair
    s = "".join(c for c in unicodedata.normalize("NFKC", s) if not unicodedata.category(c).startswith("M")).replace("\u0640", "")
    return s.replace("ي", "ی").replace("ك", "ک").replace("ہ", "ه").replace("ۃ", "ه").replace("ھ", "ه")


def small_jpeg(path, limit=1_000_000):
    im = Image.open(path).convert("RGB")
    for q, w in ((90, 2000), (80, 1800), (70, 1500), (60, 1200)):
        t = im.copy(); t.thumbnail((w, w)); b = io.BytesIO(); t.save(b, "JPEG", quality=q)
        if b.tell() <= limit:
            break
    return b.getvalue()


async def main():
    ap = argparse.ArgumentParser(); ap.add_argument("image"); ap.add_argument("--lang", default="urd"); ap.add_argument("--engine", default="3")
    a = ap.parse_args()
    key = os.getenv("OCR_SPACE_API_KEY")
    if not key:
        sys.exit("OCR_SPACE_API_KEY is not set")
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(URL, headers={"apikey": key}, files={"file": ("cnic_back.jpg", small_jpeg(a.image), "image/jpeg")},
                         data={"language": a.lang, "OCREngine": a.engine, "isOverlayRequired": "true", "scale": "true", "detectOrientation": "true"})
    print(f"language={a.lang} OCREngine={a.engine} HTTP={r.status_code}")
    j = r.json()
    print("IsErroredOnProcessing:", j.get("IsErroredOnProcessing"), "| ErrorMessage:", j.get("ErrorMessage"), "| ErrorDetails:", j.get("ErrorDetails"))
    if j.get("IsErroredOnProcessing") or not j.get("ParsedResults"):
        sys.exit("FAIL: OCR.Space did not return a parsed result (see message above)")
    text = j["ParsedResults"][0].get("ParsedText") or ""
    n = norm(text)
    print("--- RAW TEXT ---\n" + text + "\n----------------")
    print("urdu_chars:", len(URDU.findall(text)))
    for w in ("موجودہ", "مستقل", "پتہ"):
        print(f"contains {w}:", norm(w) in n)
    print("(a human must still confirm the printed address text is readable and correct)")

asyncio.run(main())
