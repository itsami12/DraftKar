"""API-level tests. The Groq vision call and OCR.Space are stubbed (no network or keys needed).
Run: cd backend && python -m unittest discover tests -v"""
import io, json, logging, os, unittest
os.environ.update(MOCK_LLM="1", DEMO_USERNAME="admin", DEMO_PASSWORD="pw", JWT_SECRET="s" * 40, OCR_SPACE_API_KEY="fake", GROQ_VISION_API_KEY="fake")
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from app.main import app
from app.services import ocr, cnic as cnic_svc, cnic_vision

CUR1, PERM1 = "مکان نمبر 18، گلی نمبر 7، فرید ٹاؤن، جہلم، پنجاب", "گاؤں ایبیسی، تحصیل ایکس وائی زیڈ، ضلع جہلم"
CUR2, PERM2 = "House 7 Model Town Lahore", "Mohalla Rasool Pura Tehsil Dina District Jhelum"
P1 = dict(full_name="محمد احمد خان", father_or_husband_name="عبدالرحمن خان", cnic_number="0-9876543-35202", date_of_birth="12.04.1998", gender="M",
          current_address=CUR1, permanent_address=PERM1)
P2 = dict(full_name="Ali Hassan Malik", father_or_husband_name="Muhammad Ashraf Malik", cnic_number="35202-2468135-7", date_of_birth="03.09.1990", gender="Male",
          current_address=CUR2, permanent_address=PERM2)
REAL_CALL = cnic_vision._call_groq
CALLS = []      # every stubbed Groq request: (front_bytes, back_bytes)
REPLY = {}      # what the stub returns: {"content": str} or {"raise": Exception}


async def fake_groq(composite_jpeg):
    CALLS.append(composite_jpeg)
    if "raise" in REPLY:
        raise REPLY["raise"]
    return REPLY["content"]


def card_png(back=False):
    im = Image.new("RGB", (901 if back else 900, 570), (225, 235, 225)); ImageDraw.Draw(im).text((40, 40), "CNIC SAMPLE", fill=(0, 0, 0))
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


class Api(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        cnic_vision._call_groq = REAL_CALL

    @classmethod
    def setUpClass(cls):
        cnic_vision._call_groq = fake_groq
        cls.c = TestClient(app)
        cls.H = {"Authorization": "Bearer " + cls.c.post("/auth/login", json={"username": "admin", "password": "pw"}).json()["token"]}

    def extract(self, data=None, raw=None, send_front=True, send_back=True, **kw):
        CALLS.clear(); REPLY.clear()
        if raw is not None: REPLY["content"] = raw
        elif "exc" in kw: REPLY["raise"] = kw["exc"]
        else: REPLY["content"] = json.dumps(data if data is not None else P1, ensure_ascii=False)
        files = {}
        if send_front: files["front"] = ("f.png", kw.get("fdata", card_png()), kw.get("fct", "image/png"))
        if send_back: files["back"] = ("b.png", kw.get("bdata", card_png(True)), kw.get("bct", "image/png"))
        return self.c.post("/cnic/extract", headers=self.H, files=files, data={"language": kw.get("language", "english")})

    def test_requires_auth(self):
        self.assertEqual(self.c.post("/cnic/extract", files={"front": ("c.png", card_png(), "image/png")}).status_code, 401)

    def test_both_sides_required(self):
        self.assertEqual(self.c.post("/cnic/extract", headers=self.H).status_code, 400)
        r = self.extract(send_back=False); self.assertEqual(r.status_code, 400); self.assertIn("back side", r.json()["detail"])
        r = self.extract(send_front=False); self.assertEqual(r.status_code, 400); self.assertIn("front side", r.json()["detail"])
        self.assertEqual(CALLS, [])  # nothing was sent to Groq

    def test6_both_sides_go_to_groq_in_ONE_request(self):
        r = self.extract(); self.assertEqual(r.status_code, 200); self.assertEqual(len(CALLS), 1)
        composite = CALLS[0]; self.assertEqual(Image.open(io.BytesIO(composite)).format, "JPEG")
        self.assertGreater(Image.open(io.BytesIO(composite)).height, Image.open(io.BytesIO(composite)).width // 2)

    def test1_to_5_profile_front_back_urdu_addresses_and_rtl_cnic(self):
        r = self.extract().json(); f = r["fields"]
        self.assertTrue(r["ok"]); self.assertEqual(r["status"], {"front": "ok", "back": "ok"}); self.assertEqual(r["warnings"], [])
        self.assertEqual((f["name"], f["father_or_husband_name"]), ("محمد احمد خان", "عبدالرحمن خان"))
        self.assertEqual((f["current_address"], f["permanent_address"]), (CUR1, PERM1))   # TESTS 3 + 4, Urdu preserved
        self.assertEqual(f["cnic"], "35202-9876543-0")                                      # TEST 5: 0-9876543-35202 -> canonical
        self.assertEqual(f["date_of_birth"], "12-04-1998"); self.assertNotIn("address", f); self.assertEqual(set(r["confidence"]), set(f))

    def test_english_card(self):
        f = self.extract(P2).json()["fields"]
        self.assertEqual((f["name"], f["cnic"], f["gender"], f["current_address"]), ("Ali Hassan Malik", "35202-2468135-7", "Male", CUR2))

    def test7_8_landlord_then_tenant_are_independent_profiles(self):
        ll = self.extract(P1).json()["fields"]; tn = self.extract(P2).json()["fields"]; again = self.extract(P1).json()["fields"]
        self.assertEqual(ll, again)  # the API keeps no state between people
        self.assertTrue(all(v not in tn.values() for v in (ll["name"], ll["cnic"], ll["current_address"], ll["permanent_address"])))

    def test11_unreadable_field_is_null_and_flagged(self):
        r = self.extract({**P1, "permanent_address": None, "date_of_birth": None}).json()
        self.assertTrue(r["ok"]); self.assertIsNone(r["fields"]["permanent_address"]); self.assertIn("permanent_address", r["needs_review"])
        self.assertIn(cnic_vision.NO_PERMANENT, r["warnings"]); self.assertEqual(r["message"], cnic_vision.MSG_PARTIAL); self.assertEqual(r["fields"]["current_address"], CUR1)

    def test_invalid_cnic_is_null_and_flagged(self):
        r = self.extract({**P1, "cnic_number": "1234-5678"}).json()
        self.assertIsNone(r["fields"]["cnic"]); self.assertIn("cnic", r["needs_review"]); self.assertIn("Please verify CNIC number", r["warnings"])

    def test_nothing_readable(self):
        r = self.extract({k: None for k in P1}).json()
        self.assertFalse(r["ok"]); self.assertEqual(r["status"], {"front": "unreadable", "back": "unreadable"}); self.assertIn("clearer", r["message"])

    def test_errors_never_make_the_workflow_unusable(self):  # Groq down, timeout, invalid JSON, wrong shape: 200 + ok=false + empty fields
        import httpx
        for kw in ({"exc": cnic_vision.VisionError("timeout")}, {"exc": RuntimeError("boom")}, {"raw": "I cannot read this"}, {"raw": "[1]"}, {"raw": ""}):
            r = self.extract(**kw); self.assertEqual(r.status_code, 200, kw); j = r.json()
            self.assertFalse(j["ok"]); self.assertEqual(j["status"], {"front": "failed", "back": "failed"}); self.assertTrue(all(v is None for v in j["fields"].values()))
            self.assertIn("enter the information manually", j["message"]); self.assertNotIn("Traceback", r.text)

    def test_missing_vision_key_is_friendly(self):
        from app.config.settings import settings
        old, settings.GROQ_VISION_API_KEY = settings.GROQ_VISION_API_KEY, ""
        try:
            cnic_vision._call_groq = self._real_call
            r = self.extract(); self.assertEqual(r.status_code, 200); self.assertFalse(r.json()["ok"])
        finally:
            cnic_vision._call_groq = fake_groq; settings.GROQ_VISION_API_KEY = old
    _real_call = staticmethod(REAL_CALL)

    def test_vision_key_is_separate_and_falls_back(self):  # fresh interpreter: the settings module is read once at import
        import subprocess, sys
        def read(**env):
            e = {k: v for k, v in os.environ.items() if not k.startswith("GROQ_")}; e.update(env)
            out = subprocess.run([sys.executable, "-c", "from app.config.settings import settings as s; print('|'.join([s.GROQ_API_KEY, s.GROQ_VISION_API_KEY, s.GROQ_VISION_MODEL]))"],
                                 capture_output=True, text=True, env=e, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).stdout.strip().split('|')
            return tuple(out)
        self.assertEqual(read(GROQ_API_KEY="doc-key", GROQ_VISION_API_KEY="vision-key"), ("doc-key", "vision-key", "qwen/qwen3.8-27b"))
        self.assertEqual(read(GROQ_API_KEY="doc-key")[1], "doc-key")  # no separate key set -> falls back to the existing one
        self.assertEqual(read(GROQ_VISION_API_KEY="v", GROQ_VISION_MODEL="other/model")[1:], ("v", "other/model"))

    def test_bad_uploads_either_side(self):
        for data, ct in ((b"%PDF-1.4", "application/pdf"), (b"hello", "text/plain"), (b"not an image", "image/png")):
            for side in ("fdata", "bdata"):
                r = self.extract(**{side: data, "fct" if side == "fdata" else "bct": ct})
                self.assertEqual(r.status_code, 400); self.assertIn("JPG, JPEG, PNG, or WebP", r.json()["detail"])
        self.assertEqual(CALLS, [])

    def test_oversized_image(self):
        r = self.extract(fdata=b"\x89PNG" + b"0" * (10 * 1024 * 1024 + 10)); self.assertEqual(r.status_code, 400)

    def test_no_identity_or_address_in_logs(self):
        h = logging.Handler(); seen = []; h.emit = lambda r: seen.append(r.getMessage()); logging.getLogger().addHandler(h)
        try:
            self.extract(); self.extract(raw="garbage 2468135 گلشن"); self.extract(exc=RuntimeError("x"))
        finally:
            logging.getLogger().removeHandler(h)
        self.assertFalse(any(x in s for s in seen for x in ("9876543", "2468135", "فرید", "ایبیسی", "محمد احمد", "Ali Hassan")))

    def test_no_files_written_during_extraction(self):
        import tempfile
        before = set(os.listdir(tempfile.gettempdir())); self.extract()
        self.assertEqual(set(os.listdir(tempfile.gettempdir())) - before, set())

    def test_cnic_path_never_calls_ocr_space_but_stamp_path_still_does(self):
        calls = []
        async def spy(*a, **k): calls.append(1); return {"ParsedResults": [{"ParsedText": "STAMP", "TextOverlay": {"Lines": []}}], "IsErroredOnProcessing": False}
        old, ocr._post = ocr._post, spy
        try:
            self.extract(); self.assertEqual(calls, [])
            r = self.c.post("/documents/rent_agreement/stamp-paper/analyze", headers=self.H, files={"file": ("s.png", card_png(), "image/png")})
            self.assertEqual(r.status_code, 200); self.assertTrue(r.json()["ok"]); self.assertGreaterEqual(len(calls), 1)
        finally:
            ocr._post = old

    # ---------- documents: current vs permanent address ----------
    @staticmethod
    def answers(**over):
        a = {"landlord_name": "احمد خان", "landlord_father": "محمد خان", "landlord_cnic": "0-9876543-35202", "landlord_current_address": "جہلم",
             "tenant_name": "علی", "tenant_father": "رشید", "tenant_cnic": "35202-2468135-7", "tenant_current_address": "لاہور",
             "property_address": "جہلم", "monthly_rent": "35000", "security_deposit": "70000", "duration": "11 ماہ", "start_date": "2026-10-05"}
        a.update(over); return a

    def gen(self, a, lang="english", doc="rent_agreement"):
        r = self.c.post(f"/documents/{doc}/generate?as=json", headers=self.H, json={"language": lang, "answers": a}); self.assertEqual(r.status_code, 200, r.text); return r.json()

    def test8_9_edited_addresses_reach_the_document_and_stay_separate(self):
        a = self.answers(landlord_current_address="EDITED CURRENT 12 Lane 3 Jhelum", landlord_permanent_address="EDITED PERMANENT Village Kala Gujran", tenant_name="Ali", tenant_father="Rashid")
        intro = self.gen(a)["content"]["intro"]; first = intro[0]
        self.assertIn("currently residing at EDITED CURRENT 12 Lane 3 Jhelum", first); self.assertNotIn("EDITED PERMANENT", first)   # never merged into one sentence
        self.assertTrue(any("Permanent address of the Landlord" in p and "EDITED PERMANENT Village Kala Gujran" in p and "EDITED CURRENT" not in p for p in intro))
        self.assertFalse(any("Tenant" in p and "Permanent address" in p for p in intro))   # tenant gave none -> nothing invented

    def test_no_permanent_address_means_no_permanent_paragraph(self):
        intro = self.gen(self.answers())["content"]["intro"]; self.assertFalse(any("مستقل" in p or "Permanent" in p for p in intro))

    def test_urdu_keeps_current_and_permanent_labels_distinct(self):
        a = self.answers(landlord_permanent_address="گاؤں ایبیسی ضلع جہلم", tenant_permanent_address="موہڑہ رسول پورہ")
        intro = self.gen(a, "urdu")["content"]["intro"]
        self.assertIn("موجودہ پتہ: جہلم", intro[0]); self.assertIn("موجودہ پتہ: لاہور", intro[0]); self.assertNotIn("مستقل", intro[0])
        perm = intro[1]; self.assertIn("مستقل پتہ: گاؤں ایبیسی ضلع جہلم", perm); self.assertIn("مستقل پتہ: موہڑہ رسول پورہ", perm); self.assertNotIn("موجودہ", perm)

    def test_all_document_types_generate_with_new_address_fields(self):
        for doc, parties in (("affidavit", ["deponent"]), ("undertaking", ["person"]), ("authority_letter", ["principal", "agent"])):
            a = {"purpose": "p", "declaration": "d", "date": "2026-10-05", "subject": "s", "commitment": "c", "scope": "sc"}
            for k in parties:
                a.update({f"{k}_name": "Ali", f"{k}_father": "Bob", f"{k}_cnic": "35202-2468135-7", f"{k}_current_address": f"CUR {k}", f"{k}_permanent_address": f"PERM {k}"})
            for lang in ("english", "urdu"):
                intro = self.gen(a, lang, doc)["content"]["intro"]; text = " ".join(intro)
                for k in parties: self.assertIn(f"CUR {k}", intro[0]); self.assertIn(f"PERM {k}", text); self.assertNotIn(f"PERM {k}", intro[0])

    def test_final_english_pdf_shows_edited_current_and_permanent_addresses_separately(self):
        import shutil, subprocess, tempfile
        if not shutil.which("pdftotext"):
            self.skipTest("poppler-utils not installed")
        a = self.answers(landlord_name="Ahmed Khan", landlord_father="Muhammad Khan", landlord_cnic="0-9876543-35202", tenant_name="Ali", tenant_father="Rashid",
                         landlord_current_address="EDITED CURRENT 12 Lane 3 Jhelum", landlord_permanent_address="EDITED PERMANENT Village Kala Gujran", tenant_current_address="Tenant Home Lahore")
        j = self.gen(a)
        pdf = self.c.post("/documents/rent_agreement/render", headers=self.H, json=j["content"]).content
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(pdf); f.flush(); raw = subprocess.run(["pdftotext", f.name, "-"], capture_output=True, text=True).stdout
        flat = " ".join(raw.split())
        self.assertIn("currently residing at EDITED CURRENT 12 Lane 3 Jhelum", flat)
        self.assertIn("Permanent address of the Landlord (Ahmed Khan): EDITED PERMANENT Village Kala Gujran.", flat)
        self.assertIn("35202-9876543-0", flat); self.assertNotIn("0-9876543-35202", flat)

    def test_current_address_is_required_permanent_is_optional(self):
        a = self.answers(); a["landlord_current_address"] = ""
        self.assertEqual(self.c.post("/documents/rent_agreement/generate", headers=self.H, json={"language": "english", "answers": a}).status_code, 422)
        spec = self.c.get("/documents/rent_agreement", headers=self.H).json(); req = {f["key"]: f["required"] for f in spec["fields"]}
        self.assertTrue(req["landlord_current_address"]); self.assertFalse(req["landlord_permanent_address"]); self.assertNotIn("landlord_address", req)

    def test_generate_normalizes_cnic_typed_in_reverse_order_and_urdu_pdf_renders(self):
        a = {"landlord_name": "احمد خان", "landlord_father": "محمد خان", "landlord_cnic": "0-9876543-35202", "landlord_current_address": "جہلم",
             "tenant_name": "علی", "tenant_father": "رشید", "tenant_cnic": "35202-2468135-7", "tenant_current_address": "لاہور",
             "property_address": "جہلم", "monthly_rent": "35000", "security_deposit": "70000", "duration": "11 ماہ", "start_date": "2026-10-05"}
        j = self.c.post("/documents/rent_agreement/generate?as=json", headers=self.H, json={"language": "urdu", "answers": a}).json()
        text = " ".join(j["content"]["intro"])
        self.assertIn("35202-9876543-0", text); self.assertNotIn("0-9876543-35202", text)  # canonical LTR data, not the reversed form
        self.assertEqual(j["content"]["signers"][0][2], "35202-9876543-0")

    def test_urdu_pdf_draws_cnic_left_to_right(self):
        """Test 9. `pdftotext -raw` returns text in drawing order, so it shows exactly what was drawn left-to-right."""
        import shutil, subprocess, tempfile
        if not shutil.which("pdftotext"):
            self.skipTest("poppler-utils not installed")
        a = {"landlord_name": "احمد خان", "landlord_father": "محمد خان", "landlord_cnic": "0-9876543-35202", "landlord_current_address": "جہلم",
             "tenant_name": "علی", "tenant_father": "رشید", "tenant_cnic": "7-2468135-35202", "tenant_current_address": "لاہور",
             "property_address": "جہلم", "monthly_rent": "35000", "security_deposit": "70000", "duration": "11 ماہ", "start_date": "2026-10-05"}
        j = self.c.post("/documents/rent_agreement/generate?as=json", headers=self.H, json={"language": "urdu", "answers": a}).json()
        pdf = self.c.post("/documents/rent_agreement/render", headers=self.H, json=j["content"]).content
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(pdf); f.flush()
            raw = subprocess.run(["pdftotext", "-raw", f.name, "-"], capture_output=True, text=True).stdout
        self.assertIn("35202-9876543-0", raw); self.assertIn("35202-2468135-7", raw)
        self.assertNotIn("0-9876543-35202", raw); self.assertNotIn("7-2468135-35202", raw)

    def test_reversed_cnic_in_model_prose_is_repaired(self):
        self.assertEqual(cnic_svc.fix_reversed_cnics_in_text("شناختی کارڈ 0-9876543-35202 والا"), "شناختی کارڈ 35202-9876543-0 والا")
        self.assertEqual(cnic_svc.fix_reversed_cnics_in_text("35202-9876543-0 stays"), "35202-9876543-0 stays")
        self.assertEqual(cnic_svc.fix_reversed_cnics_in_text("ref 5-1234567-12345 end"), "ref 12345-1234567-5 end")  # clear 1-7-5 pattern
        self.assertEqual(cnic_svc.fix_reversed_cnics_in_text("ref 5-1234567-1234 end"), "ref 5-1234567-1234 end")  # wrong lengths: untouched

if __name__ == "__main__":
    unittest.main()
