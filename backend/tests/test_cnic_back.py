"""CNIC BACK pipeline tests: image preprocessing, orientation selection, label/layout address extraction, confidence.
OCR.Space is simulated (no network, no keys, no real CNIC images). Run: cd backend && python -m pytest tests -q"""
import asyncio, os, random, unittest
os.environ.update(MOCK_LLM="1", OCR_SPACE_API_KEY="fake")
import numpy as np
from PIL import Image, ImageDraw
from app.services import cnic as C, cnic_back as B, cnic_image as CI, cnic_layout as L, ocr

CUR = "مکان نمبر B-II-8-S-33, سٹریٹ نمبر 3,محلہ ڈھوک جمعہ، جہلم"
PERM = "قلعہ روہتاس ڈاکخانہ خاص،دینہ، ضلع جہلم"


def w(t, x1, y1, x2, y2):  # words are laid out like a real CNIC back, in a 1164 x 420 reference frame
    return {"text": t, "x": x1 / 1164, "y": y1 / 420, "width": (x2 - x1) / 1164, "height": (y2 - y1) / 420}


def card_words(cur=True, perm=True, cur_label=("موجودہ", "پتہ:"), perm_label=("مستقل", "پتہ:"), junk=True):
    ws = [w("37301-4950901-3", 850, 38, 1080, 66)]
    if cur:
        ws += [w(cur_label[0], 765, 36, 822, 54), w(cur_label[1], 733, 36, 765, 54), w("مکان", 640, 45, 700, 80), w("نمبر", 585, 45, 640, 80),
               w("B-II-8-S-33,", 455, 45, 585, 80), w("سٹریٹ", 385, 45, 455, 80), w("نمبر", 330, 45, 385, 80), w("3,محلہ", 250, 45, 330, 80),
               w("ڈھوک", 150, 45, 215, 80), w("جہلم", 600, 105, 650, 135), w("جمعہ،", 650, 105, 690, 135)]
    if perm:
        ws += [w(perm_label[0], 765, 236, 822, 254), w(perm_label[1], 733, 236, 765, 254), w("قلعہ", 690, 245, 735, 275), w("روہتاس", 610, 245, 685, 275),
               w("ڈاکخانہ", 520, 245, 600, 275), w("خاص،دینہ،", 410, 245, 510, 275), w("ضلع", 340, 245, 390, 275), w("جہلم", 270, 245, 330, 275)]
    if junk:  # signature scribble, QR number, registrar caption, and the "lost card" instruction printed under the card
        ws += [w("m.", 20, 340, 40, 365), w("Teng", 50, 335, 120, 370), w("102021479382", 890, 340, 1045, 365), w("Registrar", 10, 400, 100, 415), w("General", 105, 400, 170, 415)]
    return ws


def px(words, W=1164, H=420):
    return L.to_words([{"text": d["text"], "x": d["x"] * W, "y": d["y"] * H, "width": d["width"] * W, "height": d["height"] * H} for d in words], (W, H))


def regions(words, qr=(850, 100, 1040, 290)):
    return L.extract_regions(px(words), (1164, 420), qr)["regions"]


class LayoutTests(unittest.TestCase):
    def test_both_addresses_mapped_by_label(self):
        r = regions(card_words())
        self.assertEqual(r["current"].text, CUR); self.assertEqual(r["permanent"].text, PERM)

    def test_word_order_irrelevant(self):
        ws = px(card_words()); random.Random(1).shuffle(ws)
        r = L.extract_regions(ws, (1164, 420), (850, 100, 1040, 290))["regions"]
        self.assertEqual((r["current"].text, r["permanent"].text), (CUR, PERM))

    def test_cnic_number_qr_number_and_signature_never_enter_an_address(self):
        r = regions(card_words())
        for k in ("current", "permanent"):
            for bad in ("37301", "1020214", "Registrar", "Teng"):
                self.assertNotIn(bad, r[k].text)

    def test_missing_current_address(self):
        r = regions(card_words(cur=False)); self.assertIsNone(r["current"]); self.assertEqual(r["permanent"].text, PERM)

    def test_missing_permanent_address(self):
        r = regions(card_words(perm=False)); self.assertIsNone(r["permanent"]); self.assertEqual(r["current"].text, CUR)

    def test_permanent_printed_first_still_follows_the_label(self):  # the top block carries the PERMANENT label: label decides, not position
        r = regions(card_words(cur_label=("مستقل", "پتہ:"), perm_label=("موجودہ", "پتہ:")))
        self.assertEqual((r["current"].text, r["permanent"].text), (PERM, CUR))

    def test_ocr_letter_errors_in_labels_are_tolerated(self):
        for cl, pl in ((("موجود", "پتہ"), ("مستقل", "پتا")), (("موجودہ", "بتہ"), ("مستفل", "پتہ")), (("موجوده", "پته:"), ("مستقل", "پته"))):
            r = regions(card_words(cur_label=cl, perm_label=pl))
            self.assertEqual((r["current"].text, r["permanent"].text), (CUR, PERM), (cl, pl))

    def test_merged_label_token(self):
        r = regions(card_words(cur_label=("موجودہپتہ:", "")))
        # an empty second token has zero width -> dropped by to_words; the merged token alone must still be a label
        self.assertEqual(r["current"].text, CUR)

    def test_unrelated_urdu_text_is_not_an_address(self):
        ws = [w("گمشدہ", 700, 300, 760, 330), w("کارڈ", 640, 300, 700, 330), w("ملنے", 590, 300, 640, 330), w("پر", 550, 300, 590, 330), w("قریبی", 480, 300, 550, 330),
              w("لیٹر", 420, 300, 480, 330), w("بکس", 360, 300, 420, 330), w("میں", 310, 300, 360, 330), w("ڈال", 260, 300, 310, 330), w("دیں", 210, 300, 260, 330)]
        r = L.extract_regions(px(ws), (1164, 420))
        self.assertEqual(r["labels"], []); self.assertEqual((r["regions"]["current"], r["regions"]["permanent"]), (None, None))

    def test_instruction_sentence_below_the_address_is_not_appended(self):
        ws = card_words() + [w("گمشدہ", 700, 300, 760, 330), w("کارڈ", 640, 300, 700, 330), w("ملنے", 590, 300, 640, 330), w("قریبی", 480, 300, 550, 330), w("لیٹر", 420, 300, 480, 330), w("بکس", 360, 300, 420, 330)]
        self.assertEqual(regions(ws)["permanent"].text, PERM)

    def test_only_first_word_of_label_read_is_flagged_partial(self):
        ws = [x for x in card_words() if x["text"] != "پتہ:"]
        labs = L.find_labels(px(ws)); self.assertTrue(all(l.partial for l in labs))

    def test_same_row_labels_of_both_kinds_are_ambiguous_not_guessed(self):
        ws = [w("موجودہ", 765, 36, 822, 54), w("پتہ", 733, 36, 765, 54), w("مستقل", 600, 36, 650, 54), w("پتہ", 560, 36, 600, 54), w("گلی", 500, 90, 540, 120), w("نمبر", 440, 90, 490, 120)]
        r = L.extract_regions(px(ws), (1164, 420)); self.assertTrue(r["ambiguous"]); self.assertEqual((r["regions"]["current"], r["regions"]["permanent"]), (None, None))


class ScoringAndConfidence(unittest.TestCase):
    def test_orientation_score_prefers_meaningful_text(self):
        good = f"37301-4950901-3\nموجودہ پتہ: {CUR}\nمستقل پتہ: {PERM}\nRegistrar General of Pakistan"
        sideways = "l\n1\nت\nا\n.\nم\n,\n~\n3"
        self.assertGreater(B.score_text(good), 80); self.assertLess(B.score_text(sideways), 10); self.assertGreater(B.score_text(good), B.score_text(""))

    def test_confidence_levels(self):
        r = lambda t, ex=True, part=False: {"source": "full:A", "text": t, "exact": ex, "partial": part}
        band = {"source": "band", "text": CUR, "exact": True, "partial": False}
        self.assertEqual(B._decide("current", [r(CUR)], band)["confidence"], "high")                     # two agreeing reads
        self.assertEqual(B._decide("current", [r("کچھ اور بالکل مختلف متن")], band)["confidence"], "medium")  # disagree
        self.assertEqual(B._decide("current", [r(CUR)], None)["confidence"], "medium")                    # one read
        self.assertEqual(B._decide("current", [r(CUR, ex=False, part=True)], None)["confidence"], "low")  # partial label
        self.assertIsNone(B._decide("current", [], None))

    def test_junk_is_not_an_address(self):
        for j in ("", "~~ ..", "|| // \\\\", "ab"):
            self.assertFalse(B.address_quality(j))
        self.assertTrue(B.address_quality(CUR))

    def test_extract_address_data_uses_layout_and_keeps_fields_separate(self):
        d = C.extract_address_data([], layout={"current_address": {"text": CUR, "confidence": "high"}, "permanent_address": {"text": PERM, "confidence": "medium"}})
        self.assertEqual((d["fields"]["current_address"], d["fields"]["permanent_address"]), (CUR, PERM))
        self.assertEqual(d["confidence"], {"current_address": "high", "permanent_address": "medium"}); self.assertEqual(d["needs_review"], ["permanent_address"])
        self.assertNotIn("address", d["fields"])

    def test_missing_one_address_stays_none_even_with_other_present(self):
        d = C.extract_address_data([], layout={"permanent_address": {"text": PERM, "confidence": "high"}})
        self.assertIsNone(d["fields"]["current_address"]); self.assertEqual(d["fields"]["permanent_address"], PERM)


# ------------------------------------------------------------------ image preprocessing + orientation, end to end
def synthetic_photo(rot_ccw: int, tilt: float = 4.0, size=(900, 1200)):
    """An upright 'CNIC back' (pale green card, black QR-like square top-right) photographed on a grey table, rotated by `rot_ccw`
    degrees (+ a few degrees of tilt)."""
    card = Image.new("RGB", (856, 540), (222, 238, 222)); d = ImageDraw.Draw(card)
    d.rectangle((650, 40, 800, 190), fill=(0, 0, 0)); d.rectangle((40, 300, 500, 310), fill=(60, 60, 60))
    bg = Image.new("RGB", size, (110, 105, 100)); bg.paste(card.rotate(0, expand=True), ((size[0] - 856) // 2, (size[1] - 540) // 2))
    return bg.rotate(rot_ccw + tilt, expand=True, fillcolor=(110, 105, 100), resample=Image.BICUBIC)


def upright_marker(img: Image.Image) -> bool:
    """The simulated OCR can 'read' only if the black marker is in the upper-right quadrant (i.e. the card is upright)."""
    a = np.asarray(img.convert("L").resize((64, 40)))
    ys, xs = np.where(a < 40)
    return len(xs) > 3 and xs.mean() > 40 and ys.mean() < 18


def fake_ocr(calls):
    async def call(image, language="eng", engine="2", is_table=False):
        calls.append((language, image.size))
        if not upright_marker(image):
            return {"text": "l\n1\n~\n.", "words": [], "image": {"width": image.width, "height": image.height}}
        ws = card_words(); W, H = image.size
        return {"text": f"37301-4950901-3\nRegistrar General of Pakistan\nموجودہ پتہ {CUR}\nمستقل پتہ {PERM}",
                "words": [{"text": d["text"], "x": d["x"] * W, "y": d["y"] * H, "width": d["width"] * W, "height": d["height"] * H} for d in ws],
                "image": {"width": W, "height": H}}
    return call


class PipelineTests(unittest.TestCase):
    def run_pipeline(self, img, ocr_call=None):
        calls = []
        out = asyncio.run(B.run_cnic_ocr(img, ocr_call or fake_ocr(calls), want_debug=True)); return out, calls

    def test_card_is_isolated_from_the_photo(self):
        q = CI.find_card(synthetic_photo(90))
        self.assertIsNotNone(q); flat = CI.rectify_card(synthetic_photo(90), q["quad"])
        self.assertGreater(flat.width, flat.height); self.assertAlmostEqual(flat.width / flat.height, 1.585, delta=0.12)

    def test_all_four_rotations_are_corrected_and_both_addresses_extracted(self):
        for rot in (0, 90, 180, 270):
            out, _ = self.run_pipeline(synthetic_photo(rot))
            lay = out["layout"]
            self.assertEqual(lay["current_address"]["text"], CUR, f"rot {rot}"); self.assertEqual(lay["permanent_address"]["text"], PERM, f"rot {rot}")
            self.assertEqual(out["debug"]["orientation"]["source"], "card")
            self.assertEqual(lay["current_address"]["confidence"], "high")

    def test_rotation_is_chosen_by_ocr_not_applied_blindly(self):
        out, calls = self.run_pipeline(synthetic_photo(0))
        sc = out["debug"]["orientation"]["scores"]; self.assertEqual(len(sc), 2)  # card@0 and card@180 were both tried
        self.assertGreater(max(sc.values()), 50); self.assertLess(min(sc.values()), 10)

    def test_no_card_found_falls_back_to_full_image_and_all_four_rotations(self):
        img = Image.new("RGB", (900, 600), (110, 105, 100)); d = ImageDraw.Draw(img); d.rectangle((700, 40, 850, 190), fill=(0, 0, 0))  # no card, marker only
        out, _ = self.run_pipeline(img)
        self.assertEqual(out["debug"]["orientation"]["source"], "full"); self.assertEqual(len(out["debug"]["orientation"]["scores"]), 4)

    def test_unreadable_image_never_fabricates_an_address(self):
        async def blank(image, language="eng", engine="2", is_table=False):
            return {"text": "~ . ,", "words": [], "image": {"width": image.width, "height": image.height}}
        out, _ = self.run_pipeline(synthetic_photo(90), blank)
        self.assertEqual(out["layout"], {})
        d = C.extract_address_data(out["texts"], layout=out["layout"])
        self.assertEqual(d["fields"], {"current_address": None, "permanent_address": None})

    def test_ocr_failure_everywhere_raises(self):
        async def down(*a, **k): raise ocr.OCRError("down")
        with self.assertRaises(ocr.OCRError): asyncio.run(B.run_cnic_ocr(synthetic_photo(0), down))

    def test_debug_output_masks_cnic_numbers(self):
        out, _ = self.run_pipeline(synthetic_photo(0))
        blob = str(out["debug"]); self.assertNotIn("4950901", blob); self.assertNotIn("102021479382", blob)

    def test_enhancement_variants_do_not_modify_the_original_and_upscale_small_images(self):
        small = Image.new("RGB", (400, 250), (200, 220, 200)); before = small.tobytes()
        v = CI.enhancement_variants(small)
        self.assertEqual(small.tobytes(), before); self.assertEqual(set(v), {"A", "B", "C"}); self.assertGreaterEqual(v["A"].width, 1500)

    def test_targeted_ocr_is_used_for_each_address(self):
        out, calls = self.run_pipeline(synthetic_photo(0))
        self.assertIn("band_text", out["debug"]); self.assertEqual(set(out["debug"]["band_text"]), {"current", "permanent"})

class UrduDefaults(unittest.TestCase):
    def test_urdu_pass_defaults_are_urd_engine3(self):
        """Urdu pass must be OCR.Space language=urd / Engine 3 — never Arabic/Engine 1 by default."""
        from app.config.settings import Settings
        for k in ("OCR_BACK_URDU_LANGUAGE", "OCR_BACK_URDU_ENGINE"):
            os.environ.pop(k, None)
        st = Settings()
        self.assertEqual((st.OCR_BACK_URDU_LANGUAGE, st.OCR_BACK_URDU_ENGINE), ("urd", "3"))

CUR_REAL = "مکان نمبر B-II-8-S-33، سٹریٹ نمبر 3، محلہ ڈھوک جمعہ، جہلم"
PER_REAL = "قلعہ روہتاس، ڈاکخانہ خاص، دینہ، ضلع جہلم"


class RealCardRegressions(unittest.TestCase):
    """Strings taken from the real CNIC back that produced the wrong review screen."""

    def test_registrar_general_never_enters_an_address(self):
        for txt in ("مستقل پتہ: Registrar General of Pakistan " + PER_REAL, "مستقل پتہ: " + PER_REAL + "\nRegistrar General of Pakistan",
                    "مستقل پتہ: " + PER_REAL + " Registrar General of Pakistan"):
            r = C.extract_address_data([txt])["fields"]["permanent_address"]
            self.assertEqual(r, PER_REAL, txt)
            self.assertNotIn("Registrar", r)
        lay = {"permanent_address": {"text": "Registrar General of Pakistan " + PER_REAL, "confidence": "medium"}}
        self.assertEqual(C.extract_address_data([], layout=lay)["fields"]["permanent_address"], PER_REAL)

    def test_current_address_that_is_only_the_tail_of_the_permanent_one_is_dropped(self):
        lay = {"current_address": {"text": "ضلع جہلم", "confidence": "medium"}, "permanent_address": {"text": PER_REAL, "confidence": "medium"}}
        f = C.extract_address_data([], layout=lay)["fields"]
        self.assertIsNone(f["current_address"]); self.assertEqual(f["permanent_address"], PER_REAL)

    def test_identical_addresses_are_still_allowed(self):
        lay = {"current_address": {"text": PER_REAL, "confidence": "high"}, "permanent_address": {"text": PER_REAL, "confidence": "high"}}
        f = C.extract_address_data([], layout=lay)["fields"]
        self.assertEqual((f["current_address"], f["permanent_address"]), (PER_REAL, PER_REAL))

    def test_first_row_keeps_its_urdu_when_ocr_merges_it_with_the_cnic_number(self):
        # label at the right; the first address row comes back as ONE line-level word that also contains the CNIC number
        words = L.to_words([
            {"text": "موجودہ", "x": 900, "y": 100, "width": 60, "height": 28}, {"text": "پتہ:", "x": 860, "y": 100, "width": 36, "height": 28},
            {"text": "مکان نمبر B-II-8-S-33، سٹریٹ نمبر 3، محلہ ڈھوک 37301-4950901-3", "x": 170, "y": 98, "width": 685, "height": 30},
            {"text": "جمعہ،", "x": 760, "y": 160, "width": 60, "height": 30}, {"text": "جہلم", "x": 690, "y": 160, "width": 60, "height": 30},
        ], (1308, 520))
        r = L.extract_regions(words, (1308, 520))["regions"]["current"]
        self.assertIsNotNone(r)
        self.assertIn("مکان نمبر", r.text); self.assertIn("ڈھوک", r.text); self.assertIn("جہلم", r.text)
        self.assertNotIn("37301", r.text)


class UrduDocumentMode(unittest.TestCase):
    def profile(self):
        return {"ok": True, "fields": {"name": "Sami Naeem", "father_or_husband_name": "Naeem Tahir", "cnic": "37301-4950901-3", "date_of_birth": "12-09-2003",
                                       "gender": "Male", "current_address": CUR_REAL, "permanent_address": PER_REAL},
                "confidence": {k: "high" for k in C.KEYS}, "needs_review": []}

    def test_gender_is_mapped_without_a_model(self):
        self.assertEqual([C.gender_urdu(x) for x in ("Male", "M", "Female", "F")], ["مرد", "مرد", "عورت", "عورت"])

    def test_names_become_urdu_and_are_flagged_and_addresses_cnic_untouched(self):
        async def fake(system, text):
            return {"names": ["سامی نعیم", "نعیم طاہر"]}
        old, C._groq_json = C._groq_json, fake
        try:
            p = asyncio.run(C.localize_profile_urdu(self.profile()))
        finally:
            C._groq_json = old
        f = p["fields"]
        self.assertEqual((f["name"], f["father_or_husband_name"], f["gender"]), ("سامی نعیم", "نعیم طاہر", "مرد"))
        self.assertEqual(p["latin"], {"name": "Sami Naeem", "father_or_husband_name": "Naeem Tahir"})
        self.assertIn("name", p["needs_review"])
        self.assertEqual((f["cnic"], f["current_address"], f["permanent_address"]), ("37301-4950901-3", CUR_REAL, PER_REAL))

    def test_bad_model_output_leaves_the_card_spelling(self):
        for bad in ({"names": ["Sami Naeem", "Naeem Tahir"]}, {"names": ["سامی نعیم"]}, None, {"names": "x"}):
            async def fake(system, text, bad=bad):
                return bad
            old, C._groq_json = C._groq_json, fake
            try:
                f = asyncio.run(C.localize_profile_urdu(self.profile()))["fields"]
            finally:
                C._groq_json = old
            self.assertEqual((f["name"], f["father_or_husband_name"]), ("Sami Naeem", "Naeem Tahir"))

class ScreenshotRegressions(unittest.TestCase):
    """Exact strings from the second real run (lost-card instruction pasted into the permanent address, label read as 'موجودیت')."""

    def test_lost_card_instruction_is_removed_from_permanent_address(self):
        txt = "مستقل پتہ: قلعہ روہتاس ڈاکخانہ خاص، دینہ، ضلع جہلم گمشدہ کارڈ ملنے پر قریبی لیٹر بکس میں ڈال دیں"
        f = C.extract_address_data([txt])["fields"]
        self.assertEqual(f["permanent_address"], "قلعہ روہتاس ڈاکخانہ خاص، دینہ، ضلع جہلم")
        # OCR variants of the same instruction (Arabic yeh/kaf, other spellings)
        for v in ("گمشده کارد ملنے پر قريبي لير بكس ميں ڈال ديں", "کارڈ ملنے پر قریبی لیٹر بکس میں ڈال دیں", "قریبی لیٹر بکس میں ڈال دیں"):
            self.assertEqual(C.strip_card_text("قلعہ روہتاس، دینہ، ضلع جہلم " + v), "قلعہ روہتاس، دینہ، ضلع جہلم", v)

    def test_instruction_on_its_own_line_after_the_address(self):
        txt = "مستقل پتہ:\nقلعہ روہتاس، دینہ، ضلع جہلم\nگمشدہ کارڈ ملنے پر قریبی لیٹر بکس میں ڈال دیں"
        self.assertEqual(C.extract_address_data([txt])["fields"]["permanent_address"], "قلعہ روہتاس، دینہ، ضلع جہلم")

    def test_misread_leading_label_is_removed_but_address_text_is_kept(self):
        self.assertEqual(C.strip_card_text("موجودیت مکان نمبر 33، سٹریٹ نمبر 3، محلہ ڈھوک"), "مکان نمبر 33، سٹریٹ نمبر 3، محلہ ڈھوک")
        self.assertEqual(C.strip_card_text("موجودہ پتہ: مکان نمبر 5"), "مکان نمبر 5")
        self.assertEqual(C.strip_card_text("مکان نمبر 5، محلہ ڈھوک جہلم"), "مکان نمبر 5، محلہ ڈھوک جہلم")   # untouched

    def test_fragment_candidate_is_replaced_by_the_next_candidate(self):
        frag = {"source": "band", "text": "ضلع جہلم", "exact": True}
        good = {"source": "full:A", "text": "مکان نمبر 5، گلی 3، محلہ ڈھوک، جمعہ، جہلم", "exact": True}
        perm = {"source": "band", "text": "قلعہ روہتاس، ڈاکخانہ خاص، دینہ، ضلع جہلم", "exact": True}
        out = B.prune_fragments({"current": [frag, good], "permanent": [perm]})
        self.assertEqual([c["text"] for c in out["current"]], [good["text"]])
        self.assertEqual(out["permanent"], [perm])
        self.assertEqual(B._decide("current", out["current"], None)["text"], good["text"])
        # if the fragment was the only candidate, nothing is invented
        self.assertEqual(B.prune_fragments({"current": [frag], "permanent": [perm]})["current"], [])


if __name__ == "__main__":
    unittest.main()
