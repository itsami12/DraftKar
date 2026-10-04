"""DEVELOPMENT TOOL — inspect the CNIC back pipeline on one image. Not used by the app; do not deploy with real images.

    cd backend
    python scripts/debug_cnic_back.py path/to/back.jpg --out debug_out           # real OCR.Space (needs OCR_SPACE_API_KEY in .env)
    python scripts/debug_cnic_back.py path/to/back.jpg --out debug_out --offline  # preprocessing only: no OCR, no network

Writes (into --out): 00_original_exif_corrected.png, 01_<candidate>.png for every orientation tried, 02_best_oriented.png,
03_variant_A/B/C.png (the OCR-ready copies). Prints orientation scores, masked raw OCR text, the address regions, confidence.
The original upload is never modified. Delete the --out folder afterwards: it contains the card image.
"""
import argparse, asyncio, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PIL import Image, ImageOps

from app.services import cnic as cnic_svc, cnic_back, cnic_image as ci


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("image"); ap.add_argument("--out", default="debug_out"); ap.add_argument("--offline", action="store_true")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    img = ImageOps.exif_transpose(Image.open(a.image)).convert("RGB"); img.save(f"{a.out}/00_original_exif_corrected.png")
    print(f"image {img.size}; card detection:", end=" ")
    card = ci.find_card(img); print(card and {"method": card["method"], "confidence": card["confidence"]} or "not found (full image used)")
    cands = ci.orientation_candidates(img)
    for c in cands:
        c.image.save(f"{a.out}/01_{c.label.replace('@', '_')}.png")
    if a.offline:
        cues = {c.label: cnic_back._qr_cue(c.image, c.source) for c in cands}
        print("QR-position cue per candidate (+ = QR on the right = looks upright):", cues)
        best = max(cands, key=lambda c: cues[c.label]); print("offline pick (QR cue only; real runs use OCR scores):", best.label)
        frame = best.image
    else:
        out = asyncio.run(cnic_back.run_cnic_ocr(img, want_debug=True)); frame = out["frame"]
        print(json.dumps(out["debug"], ensure_ascii=False, indent=2))
        data = cnic_svc.extract_address_data(out["texts"], layout=out["layout"])
        print("\nFINAL:", json.dumps({"fields": data["fields"], "confidence": data["confidence"]}, ensure_ascii=False, indent=2))
    frame.save(f"{a.out}/02_best_oriented.png")
    for k, v in ci.enhancement_variants(frame).items():
        v.save(f"{a.out}/03_variant_{k}.png")
    print("images written to", a.out)


if __name__ == "__main__":
    main()
