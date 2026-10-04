"""ReportLab canvas engine. All layout (margins, fonts, page breaks, signatures) is decided here, never by the LLM.
Standard mode: A4 with fixed margins.
Stamp mode: PAGE 1 = the uploaded stamp-paper image (page takes its proportions) with text confined to a user-placed box;
PAGE 2+ = plain white pages of the same size, same column, with a normal top margin. The image is never repeated."""
import io, os, re
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONTS = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts")
pdfmetrics.registerFont(TTFont("Amiri", os.path.join(FONTS, "Amiri-Regular.ttf")))
pdfmetrics.registerFont(TTFont("Amiri-Bold", os.path.join(FONTS, "Amiri-Bold.ttf")))
_reshaper = arabic_reshaper.ArabicReshaper()
# In Urdu text, digits after Arabic letters become "Arabic numbers" and a hyphen no longer joins them, so the Unicode bidi
# algorithm lays "35202-9876543-0" out as "0-9876543-35202" (dates too). Every number-with-separators token is therefore
# swapped for a one-character left-to-right placeholder before bidi, and restored afterwards: the token keeps its LTR order.
_NUM_TOKEN = re.compile(r"\d+(?:[-/.:]\d+)+")
_FORMAT = re.compile("[\u200e\u200f\u2066-\u2069]")  # invisible isolate/mark characters are stripped before drawing


class Writer:
    def __init__(self, rtl, page_label, page_size=A4, bg=None, box=None, scale=1.0):
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=page_size)
        self.W, self.H = page_size
        self.rtl, self.page_label, self.page, self.bg = rtl, page_label, 1, bg
        if box:  # (x, y, width) as fractions of the page, y measured from the top
            self.left, self.right = box[0] * self.W, min((box[0] + box[2]) * self.W, self.W * 0.98)
            self.top, self.bottom = self.H - box[1] * self.H, self.H * 0.07
            self.top_plain = self.H - 25 * mm  # pages 2+ are plain paper: normal top margin, same left/right as page 1
        else:
            self.left, self.right = 25 * mm, self.W - 25 * mm
            self.top, self.bottom = self.H - 25 * mm, 37 * mm
            self.top_plain = self.top
        self.reg, self.bold = ("Amiri", "Amiri-Bold") if rtl else ("Times-Roman", "Times-Bold")
        self.size = (14 if rtl else 11.5) * scale
        self.lead = self.size * (1.9 if rtl else 1.55)
        self.y = self.top
        self._bg()

    def _bg(self):
        if self.bg and self.page == 1:  # stamp paper is the background of the FIRST page only
            self.c.drawImage(self.bg, 0, 0, self.W, self.H)

    def shape(self, t):
        t = _FORMAT.sub("", t)
        if not self.rtl:
            return t
        toks = []

        def hold(m):
            toks.append(m.group(0))
            return chr(0xE000 + len(toks) - 1)  # private-use char: strong LTR, never reshaped

        out = get_display(_reshaper.reshape(_NUM_TOKEN.sub(hold, t)), base_dir="R")
        for i, tok in enumerate(toks):
            out = out.replace(chr(0xE000 + i), tok)
        return out

    def width(self, t, font, size):
        return stringWidth(self.shape(t), font, size)

    def ensure(self, h):
        if self.y - h < self.bottom:
            self.new_page()

    def footer(self):
        if self.bg and self.page == 1:  # no printed page number on the physical stamp paper
            return
        self.c.setFont(self.reg, 9)
        self.c.setFillGray(0.4)
        self.c.drawCentredString(self.W / 2, 14 * mm, self.shape(f"{self.page_label} {self.page}"))
        self.c.setFillGray(0)

    def new_page(self):
        self.footer()
        self.c.showPage()
        self.page += 1
        self._bg()
        self.y = self.top_plain

    def wrap(self, text, font, size, maxw):
        lines, cur = [], ""
        for w in text.split():
            t = f"{cur} {w}".strip()
            if self.width(t, font, size) <= maxw or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        return lines + ([cur] if cur else [])

    def line(self, text, font, size, indent=0, center=False):
        self.c.setFont(font, size)
        s = self.shape(text)
        if center:
            self.c.drawCentredString((self.left + self.right) / 2, self.y, s)
        elif self.rtl:
            self.c.drawRightString(self.right - indent, self.y, s)
        else:
            self.c.drawString(self.left + indent, self.y, s)

    def title(self, text):
        self.y -= 6 * mm
        size = self.size + 6
        self.line(text, self.bold, size, center=True)
        w, cx = self.width(text, self.bold, size), (self.left + self.right) / 2
        self.c.setLineWidth(1)
        self.c.line(cx - w / 2, self.y - 2.5 * mm, cx + w / 2, self.y - 2.5 * mm)
        self.y -= 12 * mm

    def para(self, text, bold=False, indent=0, gap=3 * mm, num=None):
        font = self.bold if bold else self.reg
        lines = self.wrap(text, font, self.size, self.right - self.left - indent)
        for i, ln in enumerate(lines):
            self.ensure(self.lead * (2 if i == 0 else 1))
            if i == 0 and num:
                self.line(num, self.bold, self.size)
            self.line(ln, font, self.size, indent=indent)
            self.y -= self.lead
        self.y -= gap

    def _cols(self, items):
        items = list(items)[::-1] if self.rtl else list(items)
        colw = (self.right - self.left) / len(items)
        return [(self.left + colw * i + colw / 2, colw, it) for i, it in enumerate(items)]

    def sig_blocks(self, signers, lab):
        self.ensure(38 * mm)  # 14mm gap + signature line + role/name/CNIC lines
        self.y -= 14 * mm
        for cx, colw, (role, name, cnic) in self._cols(signers):
            self.c.line(cx - colw * 0.4, self.y, cx + colw * 0.4, self.y)
            self.c.setFont(self.bold, self.size)
            self.c.drawCentredString(cx, self.y - 5 * mm, self.shape(role))
            self.c.setFont(self.reg, self.size - 1)
            self.c.drawCentredString(cx, self.y - 10.5 * mm, self.shape(f"{lab['name']}: {name}"))
            self.c.drawCentredString(cx, self.y - 16 * mm, self.shape(f"{lab['cnic']}: {cnic}"))
        self.y -= 28 * mm

    def witness_blocks(self, wits, lab):
        if not wits:
            return
        self.ensure(36 * mm)
        self.para(lab["wit"], bold=True, gap=10 * mm)
        for cx, colw, (name, cnic) in self._cols(wits):
            self.c.line(cx - colw * 0.4, self.y, cx + colw * 0.4, self.y)
            self.c.setFont(self.reg, self.size - 1)
            self.c.drawCentredString(cx, self.y - 5 * mm, self.shape(f"{lab['name']}: {name}"))
            if cnic:
                self.c.drawCentredString(cx, self.y - 10.5 * mm, self.shape(f"{lab['cnic']}: {cnic}"))
        self.y -= 18 * mm


def render_pdf(d: dict, bg: bytes | None = None, placement: dict | None = None) -> bytes:
    lab = d["labels"]
    if bg:
        reader = ImageReader(io.BytesIO(bg))
        iw, ih = reader.getSize()
        s = A4[1] / max(iw, ih)  # page takes the image's own proportions, long side = A4 long side
        w = Writer(d["rtl"], lab["page"], (iw * s, ih * s), reader, (placement["x"], placement["y"], placement["width"]), placement["font_scale"])
    else:
        w = Writer(d["rtl"], lab["page"])
    w.title(d["title"])
    for m in d["meta"]:
        w.para(m, bold=True, gap=1 * mm)
    if d["meta"]:
        w.y -= 3 * mm
    for p in d["intro"]:
        w.para(p)
    n = 0
    for c in d["clauses"]:
        n += 1
        w.para(c, indent=9 * mm, num=(f"{n}۔" if d["rtl"] else f"{n}."))
    if d.get("extra_clauses"):  # section appears only when the user supplied clauses
        w.y -= 2 * mm
        w.ensure(w.lead * 4)  # keep the heading with its first clause
        w.para(d["extra_title"], bold=True, gap=2 * mm)
        for c in d["extra_clauses"]:
            n += 1
            w.para(c, indent=9 * mm, num=(f"{n}۔" if d["rtl"] else f"{n}."))
    w.para(d["closing"], gap=2 * mm)
    w.sig_blocks(d["signers"], lab)
    w.witness_blocks(d["witnesses"], lab)
    w.footer()
    w.c.save()
    return w.buf.getvalue()
