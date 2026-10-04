"""Image validation and preparation (Pillow). Images are processed in memory only and never stored."""
import io
from PIL import Image, ImageOps

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 10 * 1024 * 1024
BAD_UPLOAD_MESSAGE = "Please upload a JPG, JPEG, PNG, or WebP image under 10 MB."
Image.MAX_IMAGE_PIXELS = 50_000_000


class BadUpload(Exception):
    pass


async def read_upload(file) -> Image.Image:
    if file.content_type not in ALLOWED_TYPES:
        raise BadUpload()
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise BadUpload()
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in {"JPEG", "PNG", "WEBP"}:  # content is checked, not just the header the client sent
            raise BadUpload()
        img = ImageOps.exif_transpose(img)
        img.load()
        return img.convert("RGB")
    except Exception:
        raise BadUpload()


def _jpeg(img: Image.Image, max_side: int, max_bytes: int | None = None):
    im = img.copy()
    im.thumbnail((max_side, max_side))
    q = 85
    while True:
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, optimize=True)
        if max_bytes is None or buf.tell() <= max_bytes or (q <= 45 and max(im.size) <= 800):
            return buf.getvalue(), im.size
        if q > 45:
            q -= 10
        else:
            im = im.resize((int(im.width * 0.8), int(im.height * 0.8)))


def prepare_for_ocr(img):
    """OCR.Space's free tier accepts files up to ~1 MB, so shrink/compress before sending."""
    data, size = _jpeg(img, 2000, 950_000)
    return data, size[0], size[1]


def prepare_for_pdf(img) -> bytes:
    return _jpeg(img, 2400)[0]
